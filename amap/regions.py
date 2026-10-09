# -*- coding: utf-8 -*-
"""行政区划加载与层级展开。

数据结构（data/china_regions.json）：
  [{ "code": "11", "name": "北京市",
     "children": [{ "code": "1101", "name": "市辖区",
        "children": [{ "code": "110101", "name": "东城区" }] }] }]

code 长度：2=省，4=市，6=区县。6 位 code 即高德 adcode（近似，个别除外）。
"""
import json
import os

_DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "china_regions.json")


def load_regions(path=_DATA):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


_REGIONS = load_regions()


def provinces():
    """返回所有省级节点列表 [{code,name,child_count}]。"""
    return [{"code": p["code"], "name": p["name"], "child_count": len(p["children"])} for p in _REGIONS]


def _find_by_code(code):
    """返回 (province_dict, city_dict_or_None, area_dict_or_None)。

    兼容输入：2/4/6 位标准代码，或 6 位零填充 adcode（如 "110000"）。
    """
    code = str(code)
    exact = code
    if len(code) == 6:
        if code.endswith("0000"):
            exact = code[:2]
        elif code.endswith("00"):
            exact = code[:4]
    for p in _REGIONS:
        if p["code"] == exact:
            return p, None, None
        for c in p.get("children", []):
            if c["code"] == exact:
                return p, c, None
            for a in c.get("children", []):
                if a["code"] == exact:
                    return p, c, a
    return None, None, None


def expand_to_districts(selected_codes):
    """把用户勾选的省/市/区县展开为区县叶子节点列表。

    返回：[{code(6位adcode), name(区县名), city, province}]
    """
    leaves = {}
    for code in selected_codes:
        p, c, a = _find_by_code(code)
        if p is None:
            continue
        if a is not None:  # 区县
            leaves[a["code"]] = {"code": a["code"], "name": a["name"], "city": c["name"], "province": p["name"]}
        elif c is not None:  # 市
            for a2 in c.get("children", []):
                leaves[a2["code"]] = {"code": a2["code"], "name": a2["name"], "city": c["name"], "province": p["name"]}
        else:  # 省
            for c2 in p.get("children", []):
                for a2 in c2.get("children", []):
                    leaves[a2["code"]] = {"code": a2["code"], "name": a2["name"], "city": c2["name"], "province": p["name"]}
    return list(leaves.values())


def selection_summary(selected_codes):
    """统计勾选了多少省/市/区县。"""
    provs, cities, areas = set(), set(), set()
    for code in selected_codes:
        p, c, a = _find_by_code(code)
        if p is None:
            continue
        provs.add(p["code"])
        if c is not None:
            cities.add(c["code"])
            for a2 in c.get("children", []):
                areas.add(a2["code"])
        elif a is not None:
            cities.add(c["code"])
            areas.add(a["code"])
        else:
            for c2 in p.get("children", []):
                cities.add(c2["code"])
                for a2 in c2.get("children", []):
                    areas.add(a2["code"])
    return {"provinces": len(provs), "cities": len(cities), "districts": len(areas)}


def region_name(code):
    p, c, a = _find_by_code(code)
    if a:
        return f"{p['name']}{c['name']}{a['name']}"
    if c:
        return f"{p['name']}{c['name']}"
    if p:
        return p["name"]
    return code
