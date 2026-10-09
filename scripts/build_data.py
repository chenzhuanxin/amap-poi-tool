# -*- coding: utf-8 -*-
"""构建项目数据文件：
1) data/china_regions.json  —— 全国省市区三级（含 6 位行政区划代码），合并港澳台
2) data/poi_categories.json —— 高德 POI 20 个大类 + 二级分类
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXTRACT = os.path.join(ROOT, "_extract", "package", "dist")
DATA = os.path.join(ROOT, "data")
os.makedirs(DATA, exist_ok=True)


# ---------------------------------------------------------------------------
# 1) 行政区划
# ---------------------------------------------------------------------------
def build_regions():
    with open(os.path.join(EXTRACT, "pca-code.json"), "r", encoding="utf-8") as f:
        mainland = json.load(f)  # [ {code:'11', name:'北京市', children:[{code:'1101',name:'市辖区',children:[{code:'110101',name:'东城区'}]}]} ]

    with open(os.path.join(EXTRACT, "HK-MO-TW.json"), "r", encoding="utf-8") as f:
        hmt = json.load(f)  # { '香港特别行政区': {'香港岛': ['中西区',...]}, ... }

    # 港澳台没有官方统计代码，使用高德约定的 adcode 段
    hmt_meta = {
        "香港特别行政区": ("81", "820000"),
        "澳门特别行政区": ("82", "820000"),
        "台湾省": ("71", "710000"),
    }

    result = []

    for p in mainland:
        prov_code = p["code"]  # 2 位
        prov_name = p["name"]
        prov_children = []
        for c in p.get("children", []):
            city_code = c["code"]  # 4 位
            city_name = c["name"]
            areas = []
            for a in c.get("children", []):
                areas.append({"code": a["code"], "name": a["name"]})
            prov_children.append({
                "code": city_code,
                "name": city_name,
                "children": areas,
            })
        result.append({"code": prov_code, "name": prov_name, "children": prov_children})

    # 港澳台
    for prov_name, (prov_code, default_adcode) in hmt_meta.items():
        prov_children = []
        seq = 0
        for city_name, area_names in hmt.get(prov_name, {}).items():
            seq += 1
            city_code = f"{prov_code}{seq:02d}"
            areas = []
            for a in area_names:
                # 用城区编号生成一个稳定的 6 位代码
                areas.append({"code": f"{city_code}{len(areas)+1:02d}", "name": a})
            prov_children.append({"code": city_code, "name": city_name, "children": areas})
        result.append({"code": prov_code, "name": prov_name, "children": prov_children})

    with open(os.path.join(DATA, "china_regions.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, separators=(",", ":"))

    total = sum(len(p["children"]) for p in result)
    total_area = sum(len(c["children"]) for p in result for c in p["children"])
    print(f"regions: {len(result)} 省 | {total} 市 | {total_area} 区县")


# ---------------------------------------------------------------------------
# 2) POI 分类码表（20 大类 + 二级分类）
#    一级 typecode 前缀与官方一致；二级以中文名为准（高德搜索 API 的 type 参数
#    直接接受分类名），同时在 UI 中允许用户手动输入 typecode 精确控制。
# ---------------------------------------------------------------------------
POI_CATEGORIES = [
    {"code": "010000", "name": "汽车服务", "children": ["加油站", "汽车维修", "汽车养护", "汽车配件销售", "汽车租赁", "汽车回收", "汽车俱乐部"]},
    {"code": "020000", "name": "汽车销售", "children": ["综合经销商", "品牌专卖店", "二手车经销商", "汽车销售"]},
    {"code": "030000", "name": "汽车维修", "children": ["汽车修理厂", "4S店维修", "汽车美容", "汽车检测"]},
    {"code": "040000", "name": "摩托车服务", "children": ["摩托车销售", "摩托车维修", "摩托车服务相关"]},
    {"code": "050000", "name": "餐饮服务", "children": ["中餐厅", "外国餐厅", "快餐厅", "咖啡厅", "茶艺馆", "冷饮店", "糕饼店", "甜品店", "食堂", "餐饮相关场所"]},
    {"code": "060000", "name": "购物服务", "children": ["商场", "便民商店", "家电卖场", "超级市场", "市场", "专卖店", "综合市场", "个人用品商店", "商业街", "购物相关场所"]},
    {"code": "070000", "name": "生活服务", "children": ["通讯营业厅", "美容美发店", "洗衣店", "中介机构", "照相冲印店", "维修点", "家政服务", "殡葬服务", "生活服务场所", "物流速递", "彩票销售点", "公共厕所", "洗浴推拿场所", "报刊亭", "事务所"]},
    {"code": "080000", "name": "体育休闲服务", "children": ["运动场馆", "高尔夫相关", "娱乐场所", "度假村", "影剧院", "休闲场所", "体育休闲服务场所", "旅游景点", "健身场所", "游戏场所", "网吧"]},
    {"code": "090000", "name": "医疗保健服务", "children": ["综合医院", "专科医院", "诊所", "急救中心", "疾病预防机构", "医药保健销售店", "动物医疗场所", "医疗保健服务场所"]},
    {"code": "100000", "name": "住宿服务", "children": ["宾馆酒店", "旅馆招待所", "住宿服务相关"]},
    {"code": "110000", "name": "风景名胜", "children": ["公园广场", "风景名胜", "寺庙道观", "纪念场所", "观光景点"]},
    {"code": "120000", "name": "商务住宅", "children": ["商务住宅相关", "产业园区", "楼宇", "住宅区"]},
    {"code": "130000", "name": "政府机构及社会团体", "children": ["政府机关", "行政单位", "政府及社会团体相关", "外国机构", "民主党派", "社会团体", "公检法机构", "交通车辆管理", "工商税务机构"]},
    {"code": "140000", "name": "科教文化服务", "children": ["学校", "科研机构", "培训机构", "图书馆", "文化场所", "博物馆", "展览馆", "档案馆", "科技馆", "驾校", "传媒机构", "科教文化服务相关"]},
    {"code": "150000", "name": "交通设施服务", "children": ["飞机场", "火车站", "港口码头", "长途汽车站", "地铁站", "公交车站", "停车场", "收费站", "服务区", "交通设施服务相关"]},
    {"code": "160000", "name": "金融保险服务", "children": ["银行", "自动提款机", "保险公司", "证券公司", "财务公司", "金融保险服务机构", "信托公司", "期货公司", "证券交易所"]},
    {"code": "170000", "name": "公司企业", "children": ["公司", "企业", "厂矿", "农林牧渔基地", "公司企业相关"]},
    {"code": "180000", "name": "道路附属设施", "children": ["道路附属设施", "环岛", "道路信息"]},
    {"code": "190000", "name": "地名地址信息", "children": ["地名", "门牌信息", "道路名", "交叉路口", "区域名", "地标"]},
    {"code": "200000", "name": "公共设施", "children": ["公共设施", "紧急避难场所", "公共厕所", "其他公共设施"]},
]


def build_categories():
    with open(os.path.join(DATA, "poi_categories.json"), "w", encoding="utf-8") as f:
        json.dump(POI_CATEGORIES, f, ensure_ascii=False, separators=(",", ":"))
    total_sub = sum(len(c["children"]) for c in POI_CATEGORIES)
    print(f"categories: {len(POI_CATEGORIES)} 大类 | {total_sub} 二级分类")


if __name__ == "__main__":
    build_regions()
    build_categories()
