# -*- coding: utf-8 -*-
"""配额计算与超额预警。

核心口径（与前端一致，可在面板参数区调整）：
  - per_request     每次请求返回条数 offset（0-25，建议 20）
  - max_per_combo   单参数翻页上限（官方默认 200；超过需分片）
  - daily_quota_calls  单个 key 当日免费调用次数（个人认证搜索类默认 5000）
  - qps             单个 key 每秒调用上限（默认 3）

结论：
  - required_calls = Σ ceil(单组合POI / per_request)    （翻页/分片所需 API 调用次数）
  - 单 key 最大可获取 POI ≈ daily_quota_calls × per_request
  - 全部 key 单日可支撑调用 = Σ daily_quota_calls
  - 若 required_calls > 全部 key 单日可支撑调用 -> 超额，强制预警（可能限号）
"""
import math


def build_report(estimate, keys, params):
    """estimate: {total_poi, combos:[{region,category,count}], estimate_calls, ...}
    keys: [{key, daily_quota_calls, qps, note}]
    params: {per_request, max_per_combo}
    返回完整配额报告 dict。"""
    per_request = max(1, int(params.get("per_request", 20)))
    max_per_combo = max(per_request, int(params.get("max_per_combo", 200)))

    combos = estimate.get("combos", [])
    # 每个组合的翻页调用次数；超过单组合上限的组合需分片，仍约等于 ceil(count/per_request)
    required_calls = 0
    need_shard_combos = 0
    for c in combos:
        cnt = c.get("count", 0)
        calls = math.ceil(cnt / per_request) if cnt > 0 else 0
        c["_calls"] = calls
        required_calls += calls
        if cnt > max_per_combo:
            need_shard_combos += 1

    total_quota_calls = sum(max(0, k.get("daily_quota_calls", 0)) for k in keys)
    total_qps = sum(max(1, k.get("qps", 3)) for k in keys) or 1

    # 单 key 最大可获取 POI（按免费配额）
    per_key_max_poi = []
    for k in keys:
        q = max(0, k.get("daily_quota_calls", 0))
        per_key_max_poi.append({
            "key": k.get("key"), "note": k.get("note", ""),
            "quota_calls": q,
            "max_poi": q * per_request,
        })

    all_key_max_poi = sum(x["max_poi"] for x in per_key_max_poi)

    # 是否超额
    over = required_calls > total_quota_calls
    days_needed = math.ceil(required_calls / total_quota_calls) if total_quota_calls > 0 else None
    # 若按全量数据抓，是否超出所有 key 免费可获取条数
    over_poi_capacity = estimate["total_poi"] > all_key_max_poi

    crawl_seconds = required_calls / total_qps

    return {
        "per_request": per_request,
        "max_per_combo": max_per_combo,
        "total_poi": estimate["total_poi"],
        "combo_count": len(combos),
        "need_shard_combos": need_shard_combos,
        "required_calls": required_calls,
        "total_quota_calls": total_quota_calls,
        "total_qps": total_qps,
        "per_key_max_poi": per_key_max_poi,
        "all_key_max_poi": all_key_max_poi,
        "over": over,
        "over_poi_capacity": over_poi_capacity,
        "days_needed": days_needed,
        "crawl_seconds": crawl_seconds,
        "estimate_calls": estimate.get("estimate_calls", 0),
    }
