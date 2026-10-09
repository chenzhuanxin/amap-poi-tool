# -*- coding: utf-8 -*-
"""POI 数量预估。

核心方法：对「勾选区县 × 勾选分类」的每一个组合，调用一次高德搜索接口读取
count 字段（该组合下的真实 POI 总数），再汇总。

支持两种模式：
  - full   全量：逐个组合查询，最准确，调用次数 = 组合数
  - sample 抽样：按随机种子抽 sample_size 个组合查询，按比例外推（粗略，用于
             组合过多、不想烧配额时的快速估算）

若某组合查询失败（如该 key 配额耗尽），记 0 并记录错误。
"""
import random
import math
from amap.client import AmapError


def estimate(client, districts, types, params, mode="full", sample_size=50, seed=42,
             on_progress=None):
    """返回 estimate 字典。"""
    per_request = max(1, int(params.get("per_request", 20)))
    combos = []
    for d in districts:
        for t in types:
            combos.append({"region": d, "category": t})

    total = len(combos)
    sampling = (mode == "sample") and total > sample_size

    if sampling:
        rng = random.Random(seed)
        chosen = rng.sample(range(total), sample_size)
        scale = total / sample_size
    else:
        chosen = list(range(total))
        scale = 1.0

    results = []
    est_total = 0
    errors = []
    done = 0
    for idx in chosen:
        combo = combos[idx]
        count = 0
        try:
            count, _ = client.poi_count(combo["category"], combo["region"]["code"], offset=per_request)
        except AmapError as e:
            errors.append({
                "region": combo["region"]["name"],
                "category": combo["category"],
                "info": e.message, "infocode": e.infocode,
            })
        scaled = math.ceil(count * scale) if sampling else count
        results.append({
            "region": combo["region"]["name"],
            "province": combo["region"]["province"],
            "city": combo["region"]["city"],
            "category": combo["category"],
            "count": count,
            "scaled": scaled,
        })
        est_total += scaled
        done += 1
        if on_progress:
            on_progress(done, len(chosen), est_total)

    return {
        "total_poi": est_total,
        "combos": results,
        "combo_total": total,
        "estimate_calls": len(chosen),
        "sampling": sampling,
        "sample_size": sample_size,
        "scale": scale,
        "errors": errors[:50],
        "error_count": len(errors),
    }
