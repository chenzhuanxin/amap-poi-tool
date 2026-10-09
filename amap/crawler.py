# -*- coding: utf-8 -*-
"""POI 爬取调度。

流程（对每个「区县 × 分类」组合）：
  1. 首次请求拿到 count。
  2. count <= max_per_combo：直接翻页抓完（每页 per_request 条）。
  3. count >  max_per_combo：自动分片——
       a. 先尝试按二级分类展开（若该 type 是一级且未锁定二级）；
       b. 仍超限则获取区县边界，用「多边形网格自适应细分」分片，每片 <= 上限。
  4. 多 key 轮询：单个 key 配额耗尽/被封自动切换下一个；全部耗尽则暂停并报告。
  5. 结果按 POI id 去重，写入 CSV。

参数：
  per_request      每次请求返回条数
  max_per_combo    单参数翻页上限（超限触发分片）
"""
import csv
import math
import os
import time
from datetime import datetime
from amap.client import AmapError, AmapClient
from amap import categories as cat_mod


def _bbox_polyline(b):
    min_lng, min_lat, max_lng, max_lat = b
    return f"{min_lng},{min_lat};{max_lng},{min_lat};{max_lng},{max_lat};{min_lng},{max_lat};{min_lng},{min_lat}"


def _fetch_pages(client, types, city, offset, limit, is_polygon=False, polyline=None):
    """翻页抓取一个（已限制单组合上限的）子任务的 POI 列表。"""
    pois = []
    page = 1
    while True:
        if is_polygon:
            page_pois, count = client.polygon_page(types, polyline, offset, page)
        else:
            page_pois, count = client.poi_page(types, city, offset, page)
        pois.extend(page_pois)
        if not page_pois:
            break
        if len(pois) >= min(count, limit) or page * offset >= min(count, limit):
            break
        page += 1
        if page > 100:
            break
    return pois


def _polygon_cells(client, types, adcode, offset, max_per_combo, progress):
    """多边形网格自适应分片，返回抓取到的 POI 列表。"""
    polyline, center = client.district_polyline(adcode)
    if not polyline:
        raise AmapError("NO_BOUNDS", f"未获取到 {adcode} 的边界，无法分片（可改用二级分类展开）")
    # 计算 bbox
    lngs, lats = [], []
    for pt in polyline.split(";"):
        if not pt:
            continue
        parts = pt.split(",")
        if len(parts) < 2:
            continue
        try:
            lngs.append(float(parts[0])); lats.append(float(parts[1]))
        except ValueError:
            continue
    if not lngs:
        raise AmapError("NO_BOUNDS", f"{adcode} 边界解析失败")
    bbox = (min(lngs), min(lats), max(lngs), max(lats))

    result = []
    seen = set()
    # BFS 自适应细分
    queue = [(bbox, 0)]
    while queue:
        b, level = queue.pop(0)
        count, _ = client.polygon_count(types, _bbox_polyline(b), offset=offset)
        if count == 0:
            continue
        if count > max_per_combo and level < 6:
            min_lng, min_lat, max_lng, max_lat = b
            mid_lng, mid_lat = (min_lng + max_lng) / 2, (min_lat + max_lat) / 2
            for nb in [(min_lng, min_lat, mid_lng, mid_lat),
                       (mid_lng, min_lat, max_lng, mid_lat),
                       (min_lng, mid_lat, mid_lng, max_lat),
                       (mid_lng, mid_lat, max_lng, max_lat)]:
                queue.append((nb, level + 1))
        else:
            for poi in _fetch_pages(client, types, None, offset, count, is_polygon=True, polyline=_bbox_polyline(b)):
                pid = poi.get("id")
                if pid and pid in seen:
                    continue
                if pid:
                    seen.add(pid)
                result.append(poi)
            if progress:
                progress(f"分片网格(层级{level}) 抓取 {len(result)} 条")
    return result


def _write_csv(path, rows):
    cols = ["province", "city", "district", "category", "name", "type", "address",
            "location", "lng", "lat", "pname", "cityname", "adname", "id", "tel"]
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            loc = r.get("location", "")
            lng, lat = "", ""
            if loc and "," in loc:
                lng, lat = loc.split(",", 1)
            w.writerow({
                "province": r.get("_province", ""), "city": r.get("_city", ""),
                "district": r.get("_district", ""), "category": r.get("_category", ""),
                "name": r.get("name", ""), "type": r.get("type", ""),
                "address": r.get("address", ""), "location": loc, "lng": lng, "lat": lat,
                "pname": r.get("pname", ""), "cityname": r.get("cityname", ""),
                "adname": r.get("adname", ""), "id": r.get("id", ""), "tel": r.get("tel", ""),
            })


def crawl(districts, types, keys, params, out_dir, on_status=None):
    """执行爬取。on_status(dict) 用于实时进度上报。"""
    per_request = max(1, int(params.get("per_request", 20)))
    max_per_combo = max(per_request, int(params.get("max_per_combo", 200)))
    client = AmapClient(keys)

    def status(**kw):
        if on_status:
            on_status(kw)

    total_combos = len(districts) * len(types)
    processed = 0
    collected = 0
    all_rows = []
    seen = set()
    combos_done = []

    os.makedirs(out_dir, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = os.path.join(out_dir, f"poi_{stamp}.csv")

    status(phase="start", processed=0, total=total_combos, collected=0, current="开始爬取")

    try:
        for d in districts:
            for t in types:
                processed += 1
                combo_rows = []
                try:
                    _, count = client.poi_page(t, d["code"], per_request, 1)
                except AmapError as e:
                    status(processed=processed, total=total_combos, collected=collected,
                           current=f"[{d['name']}/{t}] 失败: {e.message}", error=e.message)
                    if e.infocode == "NO_KEY":
                        raise
                    combos_done.append({"region": d["name"], "category": t, "got": 0, "error": e.message})
                    continue

                # 单组合上限检测 -> 分片
                if count > max_per_combo:
                    status(processed=processed, total=total_combos, collected=collected,
                           current=f"[{d['name']}/{t}] 共{count}条>上限{max_per_combo}，开始分片")
                    try:
                        combo_rows = _polygon_cells(client, t, d["code"], per_request, max_per_combo, status)
                    except AmapError as e:
                        if e.infocode == "NO_KEY":
                            status(processed=processed, total=total_combos, collected=collected,
                                   current=f"[{d['name']}/{t}] 所有 key 配额耗尽，暂停", error=e.message)
                            raise
                        combo_rows = []
                        combos_done.append({"region": d["name"], "category": t, "got": 0, "error": e.message})
                else:
                    # count <= 上限：直接翻页抓完（_fetch_pages 从第 1 页开始）
                    combo_rows = _fetch_pages(client, t, d["code"], per_request, count)

                got = 0
                for p in combo_rows:
                    pid = p.get("id")
                    if pid and pid in seen:
                        continue
                    if pid:
                        seen.add(pid)
                    p["_province"] = d["province"]; p["_city"] = d["city"]
                    p["_district"] = d["name"]; p["_category"] = t
                    all_rows.append(p)
                    got += 1
                collected += got
                combos_done.append({"region": d["name"], "category": t, "got": got})
                status(processed=processed, total=total_combos, collected=collected,
                       current=f"[{d['name']}/{t}] 新增{got}条，累计{collected}条")
                # 每完成一个组合增量落盘
                _write_csv(csv_path, all_rows)

    except AmapError as e:
        if e.infocode == "NO_KEY":
            status(phase="paused", processed=processed, total=total_combos, collected=collected,
                   current="已暂停：所有 API key 当日配额耗尽或被封，请补充 key 或明日继续",
                   error=e.message)
            _write_csv(csv_path, all_rows)

    # 汇总
    _write_csv(csv_path, all_rows)
    summary = {
        "total_poi": collected,
        "combos_done": combos_done,
        "csv": csv_path,
        "keys_usage": client.pool.usage(),
    }
    status(phase="done", processed=processed, total=total_combos, collected=collected,
           current="完成", summary=summary)
    return summary
