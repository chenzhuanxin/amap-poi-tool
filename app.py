# -*- coding: utf-8 -*-
"""高德 POI 数量预估与多 key 爬取工具 —— Flask 后端。

启动：
    python app.py
然后浏览器打开 http://127.0.0.1:8787

接口：
    GET  /                       静态面板
    GET  /api/regions            省市区树（含代码）
    GET  /api/categories         POI 分类（一级 + 二级）
    POST /api/estimate           预估数量 + 配额报告
    POST /api/crawl              开始爬取（SSE 实时进度）
    GET  /api/keys               查看/导入 key（内存态）
"""
import io
import os
import sys
import json
import threading
import webbrowser
import time
from datetime import datetime

from flask import Flask, jsonify, request, Response, send_from_directory

from amap import regions as R
from amap import categories as CAT
from amap.client import AmapClient, AmapError
from amap.estimator import estimate
from amap.quota import build_report
from amap import crawler as CR
from amap import regions as regions_mod

# 资源路径：源码运行时用本目录；PyInstaller 打包后在 _MEIPASS 内解包
if getattr(sys, "frozen", False):
    BASE = sys._MEIPASS
else:
    BASE = os.path.dirname(os.path.abspath(__file__))
STATIC = os.path.join(BASE, "static")
if getattr(sys, "frozen", False):
    # 打包后输出目录放到 exe 同级的 output 下（_MEIPASS 为只读临时目录）
    OUTPUT = os.path.join(os.path.dirname(sys.executable), "output")
else:
    OUTPUT = os.path.join(BASE, "output")
os.makedirs(OUTPUT, exist_ok=True)

app = Flask(__name__, static_folder=STATIC, static_url_path="")


@app.after_request
def add_cors(resp):
    """极简 CORS：允许本机任意来源（便于直接以 file:// 打开 index.html 调试）。"""
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return resp


@app.route("/", methods=["GET", "OPTIONS"])
def index():
    if request.method == "OPTIONS":
        return ("", 204)
    return send_from_directory(STATIC, "index.html")

# 内存态：API key 列表（不入库，重启即清空）
KEYS = []  # [{key, note, qps, daily_quota_calls}]


# ---------------------------------------------------------------- 页面
@app.route("/favicon.ico")
def favicon():
    return ("", 204)


# ---------------------------------------------------------------- 基础数据
@app.route("/api/regions")
def api_regions():
    return jsonify({"provinces": R.provinces()})


@app.route("/api/regions/tree")
def api_regions_tree():
    return jsonify({"regions": R.load_regions()})


@app.route("/api/categories")
def api_categories():
    return jsonify({"categories": CAT.first_levels()})


# ---------------------------------------------------------------- Key 管理
@app.route("/api/keys", methods=["GET", "POST"])
def api_keys():
    if request.method == "POST":
        payload = request.get_json(silent=True) or {}
        action = payload.get("action", "add")
        if action == "add":
            key = (payload.get("key") or "").strip()
            if not key:
                return jsonify({"error": "key 不能为空"}), 400
            if any(k["key"] == key for k in KEYS):
                return jsonify({"error": "该 key 已存在"}), 400
            KEYS.append({
                "key": key,
                "note": (payload.get("note") or "").strip(),
                "qps": int(payload.get("qps") or 3),
                "daily_quota_calls": int(payload.get("daily_quota_calls") or 5000),
            })
        elif action == "import":
            text = payload.get("text") or ""
            added = 0
            for line in text.splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                # 支持 "key" 或 "key|备注"
                parts = [p.strip() for p in line.split("|")]
                key = parts[0]
                if not key or any(k["key"] == key for k in KEYS):
                    continue
                KEYS.append({
                    "key": key,
                    "note": parts[1] if len(parts) > 1 else "",
                    "qps": int(payload.get("qps") or 3),
                    "daily_quota_calls": int(payload.get("daily_quota_calls") or 5000),
                })
                added += 1
            return jsonify({"added": added, "keys": KEYS})
        elif action == "remove":
            key = (payload.get("key") or "").strip()
            KEYS[:] = [k for k in KEYS if k["key"] != key]
        elif action == "update":
            key = (payload.get("key") or "").strip()
            for k in KEYS:
                if k["key"] == key:
                    if "qps" in payload:
                        k["qps"] = max(1, int(payload.get("qps")))
                    if "daily_quota_calls" in payload:
                        k["daily_quota_calls"] = max(0, int(payload.get("daily_quota_calls")))
                    if "note" in payload:
                        k["note"] = payload.get("note")
        elif action == "clear":
            KEYS.clear()
        return jsonify({"keys": KEYS})
    return jsonify({"keys": KEYS})


# ---------------------------------------------------------------- 预估
@app.route("/api/estimate", methods=["POST"])
def api_estimate():
    payload = request.get_json(silent=True) or {}
    region_codes = payload.get("region_codes") or []
    category_items = payload.get("categories") or []   # [{first, second:[...]}]
    params = payload.get("params") or {}
    mode = payload.get("mode", "full")
    sample_size = int(payload.get("sample_size") or 50)

    if not region_codes:
        return jsonify({"error": "请至少选择一个省/市/区县"}), 400
    types = CAT.resolve_type(category_items)
    if not types:
        return jsonify({"error": "请至少选择一个 POI 分类"}), 400
    if not KEYS:
        return jsonify({"error": "请先添加至少一个高德 API key（预估需调用真实接口）"}), 400

    districts = regions_mod.expand_to_districts(region_codes)
    sel = regions_mod.selection_summary(region_codes)
    client = AmapClient(KEYS)

    est = estimate(client, districts, types, params, mode=mode, sample_size=sample_size)
    report = build_report(est, KEYS, params)

    return jsonify({
        "ok": True,
        "selection": sel,
        "district_count": len(districts),
        "type_count": len(types),
        "estimate": est,
        "quota": report,
        "keys_usage": client.pool.usage(),
    })


# ---------------------------------------------------------------- 爬取（SSE 进度）
@app.route("/api/crawl", methods=["POST"])
def api_crawl():
    payload = request.get_json(silent=True) or {}
    region_codes = payload.get("region_codes") or []
    category_items = payload.get("categories") or []
    params = payload.get("params") or {}

    if not region_codes:
        return jsonify({"error": "请至少选择一个省/市/区县"}), 400
    types = CAT.resolve_type(category_items)
    if not types:
        return jsonify({"error": "请至少选择一个 POI 分类"}), 400
    if not KEYS:
        return jsonify({"error": "请先添加至少一个高德 API key"}), 400

    districts = regions_mod.expand_to_districts(region_codes)
    out_dir = os.path.join(OUTPUT, datetime.now().strftime("%Y%m%d"))

    def gen():
        from queue import Queue
        q = Queue()

        def emit(s):
            q.put(s)

        def run():
            try:
                summary = CR.crawl(districts, types, KEYS, params, out_dir, on_status=emit)
                q.put({"phase": "summary", "summary": summary})
            except Exception as e:
                q.put({"phase": "error", "error": str(e)})
            finally:
                q.put({"__done__": True})

        threading.Thread(target=run, daemon=True).start()
        yield "retry: 3000\n\n"
        while True:
            item = q.get()
            if item.get("__done__"):
                yield "data: " + json.dumps({"phase": "end"}, ensure_ascii=False) + "\n\n"
                break
            yield "data: " + json.dumps(item, ensure_ascii=False) + "\n\n"

    return Response(gen(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ---------------------------------------------------------------- 参数说明
@app.route("/api/info")
def api_info():
    return jsonify({
        "limits": {
            "per_request_max": 25,
            "default_per_request": 20,
            "official_max_per_combo": 200,
            "default_daily_quota_calls": 5000,
            "default_qps": 3,
        },
        "note": "数据口径：单次 offset<=25；官方同参数翻页最多 200 条；个人认证搜索类日配额约 5000 次。",
    })


if __name__ == "__main__":
    print("=" * 60)
    print("  高德 POI 预估与爬取工具已启动")
    print("  请用浏览器打开: http://127.0.0.1:8787")
    print("  关闭本窗口即可停止服务")
    print("=" * 60)
    # 延迟自动打开浏览器
    threading.Thread(target=lambda: (time.sleep(1.5), webbrowser.open("http://127.0.0.1:8787")), daemon=True).start()
    app.run(host="127.0.0.1", port=8787, debug=False, threaded=True)
