# -*- coding: utf-8 -*-
"""离线验证：预估 + 配额数学（不依赖真实网络）。"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from amap.estimator import estimate
from amap.quota import build_report

class FakeClient:
    def __init__(self, table):
        self.table = table  # (category, region_code) -> count
        self.calls = 0
    def poi_count(self, types, code, offset=20):
        self.calls += 1
        return self.table.get((types, code), 0), None

districts = [
    {"code": "110101", "name": "东城区", "province": "北京市", "city": "市辖区"},
    {"code": "110105", "name": "朝阳区", "province": "北京市", "city": "市辖区"},
]
types = ["餐饮服务", "中餐厅"]
table = {
    ("餐饮服务", "110101"): 500,
    ("餐饮服务", "110105"): 1200,
    ("中餐厅", "110101"): 300,
    ("中餐厅", "110105"): 600,
}
c = FakeClient(table)
params = {"per_request": 20, "max_per_combo": 200}

est = estimate(c, districts, types, params, mode="full")
print("total_poi:", est["total_poi"], "（期望 2600）")
print("estimate_calls:", est["estimate_calls"], "（期望 4）")
print("combo_total:", est["combo_total"])

keys = [{"key": "k1", "daily_quota_calls": 5000, "qps": 3},
        {"key": "k2", "daily_quota_calls": 2000, "qps": 3}]
report = build_report(est, keys, params)
print("required_calls:", report["required_calls"], "（期望 ceil(2600/20)=130）")
print("total_quota_calls:", report["total_quota_calls"], "（期望 7000）")
print("need_shard_combos:", report["need_shard_combos"], "（期望 2：朝阳两个都超200）")
print("all_key_max_poi:", report["all_key_max_poi"], "（期望 7000*20=140000）")
print("over:", report["over"], "（期望 False）")
print("days_needed:", report["days_needed"])
print("crawl_seconds:", round(report["crawl_seconds"]), "（期望 130/6≈22）")

# 超额场景：配额很小
keys2 = [{"key": "k1", "daily_quota_calls": 50, "qps": 3}]
r2 = build_report(est, keys2, params)
print("over(small quota):", r2["over"], "（期望 True）", "days:", r2["days_needed"], "（期望 ceil(130/50)=3）")

# 抽样模式
est_s = estimate(c, districts, types, params, mode="sample", sample_size=2, seed=1)
print("sample total_poi:", est_s["total_poi"], "sampling:", est_s["sampling"], "calls:", est_s["estimate_calls"])
