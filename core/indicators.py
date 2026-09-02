# -*- coding: utf-8 -*-
"""Indicator dictionary: consistent with the paper's data dictionary (C1-C15 / Z1-Z15, directions, paper weights).

The software ships with these preset indicators; user-uploaded or manually pasted data overrides them
(indicators whose names do not match any preset default to positive direction and can be toggled manually).
Chinese aliases of the preset names are mapped automatically so that data tables from the paper's data
package (Chinese headers) work out of the box.
"""
# (id, name, direction(+1/-1), paper weight, system)
# English names match the paper terminology (e.g., machine-ploughing/sowing/harvesting rates,
# mechanization power per sown area, irrigation-area share, flood-prevention/erosion-control areas,
# rural per-capita disposable income); demo data columns are named accordingly.
MECH_INDICATORS = [
    ("C1",  "Total agricultural machinery power (10^4 kW) (China Rural Statistical Yearbook)",       +1, 0.046),
    ("C2",  "Total agricultural output value (10^8 yuan) (China Rural Statistical Yearbook)",        +1, 0.040),
    ("C3",  "Agricultural mechanization service organizations at year-end (units) (China Agricultural Machinery Industry Yearbook)", +1, 0.077),
    ("C4",  "Agricultural machinery households at year-end (units) (China Agricultural Machinery Industry Yearbook)", +1, 0.046),
    ("C5",  "Cultivated land area per agricultural laborer (10^3 ha/10^4 persons)",                  +1, 0.074),
    ("C6",  "Machine-ploughing rate (%)",                                                            +1, 0.039),
    ("C7",  "Machine-sowing rate (%)",                                                               +1, 0.093),
    ("C8",  "Machine-harvesting rate (%)",                                                           +1, 0.065),
    ("C9",  "Mechanized irrigation rate (%)",                                                        +1, 0.061),
    ("C10", "Mechanized plant-protection rate (%)",                                                  +1, 0.066),
    ("C11", "Agricultural machinery power per sown area (10^4 kW/10^3 ha)",                          +1, 0.095),
    ("C12", "Agricultural output value per agricultural laborer (10^8 yuan/10^4 persons)",           +1, 0.080),
    ("C13", "Agricultural output value per unit cultivated area (10^8 yuan/10^3 ha)",                +1, 0.079),
    ("C14", "Operation income of agricultural machinery per 10^4 kW (10^8 yuan/10^4 kW)",            +1, 0.055),
    ("C15", "Agricultural carbon emissions",                                                         -1, 0.085),
]

GREEN_INDICATORS = [
    ("Z1",  "Cropland multiple-cropping index",                                                      -1, 0.052),
    ("Z2",  "Water consumption per unit agricultural output value",                                  -1, 0.046),
    ("Z3",  "Electricity consumption per unit agricultural output value",                            -1, 0.028),
    ("Z4",  "Agricultural machinery power per sown area",                                            -1, 0.044),
    ("Z5",  "Irrigation-area share",                                                                 +1, 0.088),
    ("Z6",  "Chemical fertilizer application intensity",                                             -1, 0.061),
    ("Z7",  "Plastic film application intensity",                                                    -1, 0.030),
    ("Z8",  "Diesel application intensity",                                                          -1, 0.034),
    ("Z9",  "Pesticide application intensity",                                                       -1, 0.079),
    ("Z10", "Forest coverage rate",                                                                  +1, 0.062),
    ("Z11", "Flood-prevention area",                                                                 +1, 0.198),
    ("Z12", "Erosion-control area",                                                                  +1, 0.072),
    ("Z13", "Total output value of agriculture / forestry / animal husbandry / fishery",             +1, 0.051),
    ("Z14", "Grain yield per unit area",                                                             +1, 0.048),
    ("Z15", "Rural per-capita disposable income",                                                    +1, 0.108),
]

# Chinese aliases (paper data package headers) -> English canonical names, so uploaded/Chinese
# tables keep direction and paper-weight lookup after import.
CN_INDICATOR_ALIASES = {
    # mechanization
    "农业机械总动力（万千瓦）（中国农村统计年鉴）": "Total agricultural machinery power (10^4 kW) (China Rural Statistical Yearbook)",
    "农业总产值（亿元）（中国农村统计年鉴）": "Total agricultural output value (10^8 yuan) (China Rural Statistical Yearbook)",
    "农业机械化服务组织年末数量（个）（中国农业机械工业年鉴）": "Agricultural mechanization service organizations at year-end (units) (China Agricultural Machinery Industry Yearbook)",
    "农业机械户年末数量（个）（中国农业机械工业年鉴）": "Agricultural machinery households at year-end (units) (China Agricultural Machinery Industry Yearbook)",
    "劳均耕地面积（千公顷/万人）": "Cultivated land area per agricultural laborer (10^3 ha/10^4 persons)",
    "机耕率（%）": "Machine-ploughing rate (%)",
    "机播率（%）": "Machine-sowing rate (%)",
    "机收率（%）": "Machine-harvesting rate (%)",
    "机械灌溉率（%）": "Mechanized irrigation rate (%)",
    "机械植保率（%）": "Mechanized plant-protection rate (%)",
    "单位播种面积农机动力(万千瓦/千公顷）": "Agricultural machinery power per sown area (10^4 kW/10^3 ha)",
    "农业劳均产值（亿元/万人）": "Agricultural output value per agricultural laborer (10^8 yuan/10^4 persons)",
    "农业地均产值（亿元/千公顷）": "Agricultural output value per unit cultivated area (10^8 yuan/10^3 ha)",
    "万千瓦动力农机作业收入（亿元/万千瓦）": "Operation income of agricultural machinery per 10^4 kW (10^8 yuan/10^4 kW)",
    "碳排放量": "Agricultural carbon emissions",
    # greening
    "耕地复种指数": "Cropland multiple-cropping index",
    "单位农业产值耗水量": "Water consumption per unit agricultural output value",
    "单位农业产值耗电量": "Electricity consumption per unit agricultural output value",
    "单位播种面积农机动力": "Agricultural machinery power per sown area",
    "灌溉面积比重": "Irrigation-area share",
    "化肥使用强度": "Chemical fertilizer application intensity",
    "农膜使用强度": "Plastic film application intensity",
    "柴油使用强度": "Diesel application intensity",
    "农药使用强度": "Pesticide application intensity",
    "森林覆盖率": "Forest coverage rate",
    "除涝面积": "Flood-prevention area",
    "水土流失治理面积": "Erosion-control area",
    "农林牧渔总产值": "Total output value of agriculture / forestry / animal husbandry / fishery",
    "粮食单产量": "Grain yield per unit area",
    "农村居民人均可支配收入": "Rural per-capita disposable income",
}

# Exact entropy weights are the authoritative reference in the paper's data package
# (entropy_weights_mech.csv / entropy_weights_green.csv) and are compared by the regression
# tests; they are not hard-coded here. Copies live in data/demo/ for the front-end check.

SYSTEMS = {"M": "Agricultural mechanization", "G": "Agricultural greening"}

# Chinese province names <-> English names used in the paper (auto-mapped on import)
CN_PROVINCES = {
    "上海": "Shanghai", "江苏": "Jiangsu", "浙江": "Zhejiang", "安徽": "Anhui",
    "江西": "Jiangxi", "湖北": "Hubei", "湖南": "Hunan", "重庆": "Chongqing",
    "四川": "Sichuan", "贵州": "Guizhou", "云南": "Yunnan",
}
PROV_CN = {v: k for k, v in CN_PROVINCES.items()}

# Regional grouping (paper definition)
REGIONS = {
    "Downstream": ["Shanghai", "Jiangsu", "Zhejiang", "Anhui"],
    "Midstream": ["Jiangxi", "Hubei", "Hunan"],
    "Upstream": ["Chongqing", "Sichuan", "Guizhou", "Yunnan"],
}
REGION_CN = {"Downstream": "Downstream", "Midstream": "Midstream", "Upstream": "Upstream"}


def normalize_name(name):
    """Map a Chinese alias to its English canonical name; unknown names are returned unchanged."""
    return CN_INDICATOR_ALIASES.get(str(name), str(name))


def region_of(province):
    for r, ps in REGIONS.items():
        if province in ps:
            return r
    return None


def indicator_config():
    """Return the indicator configuration list for the front end."""
    out = []
    for iid, name, d, w in MECH_INDICATORS:
        out.append({"id": iid, "system": "M", "system_name": SYSTEMS["M"],
                    "name": name, "direction": d, "direction_text": "Positive" if d > 0 else "Negative",
                    "paper_weight": w})
    for iid, name, d, w in GREEN_INDICATORS:
        out.append({"id": iid, "system": "G", "system_name": SYSTEMS["G"],
                    "name": name, "direction": d, "direction_text": "Positive" if d > 0 else "Negative",
                    "paper_weight": w})
    return out


def default_direction(name):
    """Look up the preset direction by (English or Chinese) name; unknown indicators default to positive."""
    name = normalize_name(name)
    for _, n, d, _ in MECH_INDICATORS + GREEN_INDICATORS:
        if n == name:
            return d
    return +1
