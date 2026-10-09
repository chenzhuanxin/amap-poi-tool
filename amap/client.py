# -*- coding: utf-8 -*-
"""高德地图开放平台 Web 服务 API 客户端。

覆盖：
  - 关键字/分类搜索      /v3/place/text     （用于预估 count 与翻页抓取）
  - 多边形搜索          /v3/place/polygon   （用于对超大组合做网格分片）
  - 行政区查询          /v3/config/district （获取区县边界 polyline，用于分片）

配额/限流（来自高德官方文档）：
  - 个人认证开发者「搜索服务」约 5000 次/月；日配额搜索类约 5000 次/日。
  - 单次 offset 建议 <=25；官方「同请求参数翻页查询最多获取 200 条」。
  - 10003 DAILY_QUERY_OVER_LIMIT 日访问量超限，自动封停、次日解封。
  - 10004 ACCESS_TOO_FREQUENT 单位时间内访问过于频繁，下一分钟解封。
  - 10008 账号被命中。
"""
import time
import threading
import requests

BASE = "https://restapi.amap.com/v3"


class AmapError(Exception):
    def __init__(self, infocode, message, key=None):
        super().__init__(message)
        self.infocode = infocode
        self.message = message
        self.key = key


class KeyPool:
    """多 key 轮询 + 单 key 调用计数 + QPS 节流。

    key 对象：{"key": str, "qps": int, "daily_quota_calls": int, "note": str}
    """

    def __init__(self, keys, global_qps=None):
        self.keys = [dict(k, used_calls=0, blocked_until=0.0) for k in keys if k.get("key")]
        self.lock = threading.Lock()
        self._rr = 0
        self.global_qps = global_qps
        self._last_call = [0.0] * len(self.keys)

    def __len__(self):
        return len(self.keys)

    @property
    def total_quota_calls(self):
        return sum(k.get("daily_quota_calls", 0) for k in self.keys)

    @property
    def total_qps(self):
        return sum(max(1, k.get("qps", 3)) for k in self.keys)

    def pick(self):
        """选择下一个可用 key；返回 None 表示所有 key 当日配额耗尽或被封。"""
        with self.lock:
            now = time.time()
            candidates = []
            for i, k in enumerate(self.keys):
                if k["blocked_until"] > now:
                    continue
                if k["used_calls"] >= k.get("daily_quota_calls", 0):
                    continue
                candidates.append(i)
            if not candidates:
                return None
            # 轮询选择，且优先选 QPS 空闲的
            for _ in range(len(candidates)):
                self._rr = (self._rr + 1) % len(self.keys)
                i = self._rr
                if i in candidates:
                    # 该 key 距上次调用已过 1/qps 秒则直接用
                    gap = 1.0 / max(1, self.keys[i].get("qps", 3))
                    wait = self._last_call[i] + gap - now
                    if wait <= 0:
                        self._last_call[i] = now
                        return i
                    # 否则找下一个
            # 所有候选都处于 QPS 等待，返回等待最短的
            best = min(candidates, key=lambda i: self._last_call[i])
            wait = self._last_call[best] + 1.0 / max(1, self.keys[best].get("qps", 3)) - now
            if wait > 0:
                time.sleep(wait)
            self._last_call[best] = time.time()
            return best

    def mark_used(self, i):
        self.keys[i]["used_calls"] += 1

    def mark_blocked(self, i, seconds):
        self.keys[i]["blocked_until"] = time.time() + seconds

    def usage(self):
        return [{"key": k["key"], "used": k["used_calls"], "quota": k.get("daily_quota_calls", 0),
                 "blocked": k["blocked_until"] > time.time()} for k in self.keys]

    def reset_daily(self):
        for k in self.keys:
            k["used_calls"] = 0


def _request(url, params, timeout=12):
    try:
        r = requests.get(url, params=params, timeout=timeout)
        data = r.json()
    except Exception as e:  # 网络错误
        raise AmapError("-1", f"网络请求失败: {e}")
    infocode = str(data.get("infocode", ""))
    status = data.get("status")
    if status != "1":
        msg = data.get("info", "未知错误")
        raise AmapError(infocode or "0", msg)
    return data


class AmapClient:
    def __init__(self, keys):
        self.pool = KeyPool(keys)

    # ---------------- 搜索 ----------------
    def _text_search(self, types, city, offset, page, keywords="", citylimit="false", key_index=None):
        """发起一次关键字/分类搜索，返回原始 json。"""
        i = self.pool.pick() if key_index is None else key_index
        if i is None:
            raise AmapError("NO_KEY", "所有 API key 当日配额已耗尽或被封")
        key = self.pool.keys[i]["key"]
        params = {
            "key": key, "keywords": keywords, "types": types,
            "city": city, "citylimit": citylimit,
            "offset": offset, "page": page, "extensions": "all",
        }
        try:
            data = _request(f"{BASE}/place/text", params)
            self.pool.mark_used(i)
            return data, i
        except AmapError as e:
            e.key = key
            self._handle_error(i, e)
            raise

    def poi_count(self, types, adcode, offset=20):
        """统计某个区县 + 分类下的 POI 总数（读取 count 字段）。"""
        data, i = self._text_search(types, adcode, offset, 1)
        return int(data.get("count") or 0), i

    def poi_page(self, types, adcode, offset, page):
        """抓取一页 POI，返回 (pois, count)。"""
        data, i = self._text_search(types, adcode, offset, page)
        return data.get("pois") or [], int(data.get("count") or 0)

    # ---------------- 多边形 ----------------
    def polygon_count(self, types, polyline, offset=20):
        i = self.pool.pick()
        if i is None:
            raise AmapError("NO_KEY", "所有 API key 当日配额已耗尽或被封")
        key = self.pool.keys[i]["key"]
        params = {"key": key, "types": types, "polygon": polyline,
                  "offset": offset, "page": 1, "extensions": "all"}
        try:
            data = _request(f"{BASE}/place/polygon", params)
            self.pool.mark_used(i)
            return int(data.get("count") or 0), i
        except AmapError as e:
            e.key = key
            self._handle_error(i, e)
            raise

    def polygon_page(self, types, polyline, offset, page):
        i = self.pool.pick()
        if i is None:
            raise AmapError("NO_KEY", "所有 API key 当日配额已耗尽或被封")
        key = self.pool.keys[i]["key"]
        params = {"key": key, "types": types, "polygon": polyline,
                  "offset": offset, "page": page, "extensions": "all"}
        try:
            data = _request(f"{BASE}/place/polygon", params)
            self.pool.mark_used(i)
            return data.get("pois") or [], int(data.get("count") or 0)
        except AmapError as e:
            e.key = key
            self._handle_error(i, e)
            raise

    # ---------------- 行政区边界 ----------------
    def district_polyline(self, adcode):
        """返回某区县的边界 polyline 字符串（lng,lat;lng,lat;...）及中心点。"""
        i = self.pool.pick()
        if i is None:
            raise AmapError("NO_KEY", "所有 API key 当日配额已耗尽或被封")
        key = self.pool.keys[i]["key"]
        params = {"key": key, "keywords": adcode, "subdistrict": 0, "extensions": "all"}
        try:
            data = _request(f"{BASE}/config/district", params)
            self.pool.mark_used(i)
            districts = data.get("districts") or []
            if not districts:
                return None, None
            polyline = districts[0].get("polyline")
            center = districts[0].get("center")
            return polyline, center
        except AmapError as e:
            e.key = key
            self._handle_error(i, e)
            raise

    # ---------------- 错误处理 ----------------
    def _handle_error(self, i, err):
        if err.infocode in ("10003", "10008"):
            # 日访问量超限 / 账号被命中 -> 封禁到次日，切下一个 key
            self.pool.mark_blocked(i, 24 * 3600)
        elif err.infocode == "10004":
            # 过于频繁 -> 封 60 秒
            self.pool.mark_blocked(i, 60)
        elif err.infocode in ("10001", "10007"):
            # key 无效 / 无权限 -> 永久跳过
            self.pool.mark_blocked(i, 24 * 3600)
        elif err.infocode == "10009":
            # 并发冲突
            self.pool.mark_blocked(i, 30)
        else:
            self.pool.mark_blocked(i, 5)
