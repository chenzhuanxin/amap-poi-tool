# -*- coding: utf-8 -*-
"""POI 分类加载与查询条件构建。

数据结构（data/poi_categories.json）：
  [{ "code": "050000", "name": "餐饮服务", "children": ["中餐厅", ...] }]

查询时：
  - 只选一级分类 -> type = "餐饮服务"
  - 选了二级分类 -> type = "餐饮服务;中餐厅"
  - 用户手动输入的 typecode 直接透传。
"""
import json
import os

_DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "poi_categories.json")


def load_categories(path=_DATA):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


_CATS = load_categories()


def first_levels():
    """[{code, name, child_count}]"""
    return [{"code": c["code"], "name": c["name"], "child_count": len(c["children"])} for c in _CATS]


def second_levels(first_code):
    for c in _CATS:
        if c["code"] == first_code or c["name"] == first_code:
            return c["children"]
    return []


def resolve_type(selected):
    """selected: [{first: code/name, second: [names]}] -> 用于高德 type 参数的列表。
    返回：["餐饮服务", "餐饮服务;中餐厅", ...]，以及自定义 typecode。
    """
    types = []
    for item in selected:
        first = item.get("first")
        seconds = item.get("second") or []
        if not first:
            continue
        if str(first).isdigit() and len(str(first)) == 6:
            # 手动 typecode
            types.append(str(first))
            continue
        # 名称模式
        if seconds:
            for s in seconds:
                types.append(f"{first};{s}")
        else:
            types.append(first)
    return types
