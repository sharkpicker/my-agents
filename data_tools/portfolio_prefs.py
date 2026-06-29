"""用户投资偏好与目标资产配置.

目标:为组合工作流 (workflow-portfolio.md) 提供「用户风险偏好 → 目标配置」的可计算映射。
主对话收集用户偏好后,落盘到 data/portfolios/<user_id>/prefs.json,
后续 subagent 通过 read_file 读取并按 5 档风险等级匹配模板。

设计原则:
- 不联网: 5 档风险等级 + 4 档投资期限 + 偏好/回避品类是闭集枚举,仅基于本地规则生成目标配置。
- 可解释: 每个目标权重都有显式依据 (权益/债券/现金/海外),便于 portfolio-manager 引用。
- 可被覆盖: 用户在交互中可显式覆盖权益占比、偏好的品类。
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, field
from typing import Iterable

# ---------------------------------------------------------------------------
# 闭集枚举
# ---------------------------------------------------------------------------

RISK_LEVELS = (1, 2, 3, 4, 5)
RISK_LEVEL_NAMES = {
    1: "保守型",
    2: "稳健型",
    3: "平衡型",
    4: "成长型",
    5: "激进型",
}

HORIZONS = ("short", "medium", "long", "very_long")
HORIZON_NAMES = {
    "short": "短期(≤1年)",
    "medium": "中期(1-3年)",
    "long": "长期(3-5年)",
    "very_long": "超长期(>5年)",
}

# 资产大类(目标配置层),与基金名称关键词一一对应,便于 Step 2.6 gap 计算
ASSET_CATEGORIES = (
    "cash",        # 货币/现金等价
    "bond",        # 纯债 / 短债
    "conservative",  # 固收+ / 偏债混合
    "balanced",    # 平衡混合
    "equity",      # 主动权益 / 偏股混合
    "index",       # 宽基指数 / 指数增强
    "sector",      # 行业主题(医药/科技/消费/新能源等)
    "overseas",    # QDII / 海外
    "alternative", # REITs / 商品 / 另类
)

# 中文关键词 → 资产大类(用于名称匹配 & screener 关键词匹配)
# 注意: cash 仅匹配"货币"或"现金管理",避免误中"自由现金流"等指数产品
# 类别顺序对 classify_position 的优先级敏感:更具体的类别(sector)排在通用类别(index)之前
CATEGORY_KEYWORDS = {
    "cash":         ("货币", "现金管理", "活期理财"),
    "bond":         ("纯债", "短债", "中短债", "中长债", "信用债", "利率债", "债基", "债券"),
    "conservative": ("固收+", "偏债", "二级债基", "混合债", "稳健"),
    "balanced":     ("平衡", "均衡", "灵活配置"),
    "equity":       ("主动", "偏股", "股票型", "成长", "价值", "精选", "优质"),
    "sector":       ("医药", "医疗", "科技", "半导体", "芯片", "消费", "食品", "新能源", "光伏", "锂电",
                     "军工", "银行", "证券", "地产", "基建", "化工", "有色", "汽车", "智能", "制造",
                     "人工智能", "数字经济"),
    "overseas":     ("QDII", "纳斯达克", "标普", "恒生", "港股", "海外", "全球", "美国"),
    "alternative":  ("REITs", "商品", "黄金", "白银", "原油"),
    "index":        ("指数", "ETF联接", "增强", "中证", "沪深300", "中证500", "中证1000", "红利"),
}

# ---------------------------------------------------------------------------
# 数据类
# ---------------------------------------------------------------------------


@dataclass
class UserPrefs:
    """用户投资偏好快照(可被序列化到 JSON)。"""

    user_id: str = "default"
    risk_level: int = 3            # 1-5
    horizon: str = "long"          # short / medium / long / very_long
    investment_amount: float = 0.0 # 总可投金额(元),0 表示未提供
    preferred_categories: list[str] = field(default_factory=list)  # ASSET_CATEGORIES 子集
    excluded_categories: list[str] = field(default_factory=list)
    excluded_codes: list[str] = field(default_factory=list)        # 已不想再买的基金代码
    target_equity_override: float | None = None  # 显式覆盖权益占比(0-1)
    notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "UserPrefs":
        allowed = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in d.items() if k in allowed})


# ---------------------------------------------------------------------------
# 5 档风险等级默认模板
# ---------------------------------------------------------------------------

# 模板键: cash / bond / conservative / balanced / equity / index / sector / overseas / alternative
# 取值: 目标权重(0-1),合计必须为 1.0
DEFAULT_TEMPLATES: dict[int, dict[str, float]] = {
    1: {  # 保守: 现金+纯债为主,权益仅作底仓点缀
        "cash": 0.15, "bond": 0.45, "conservative": 0.25,
        "balanced": 0.00, "equity": 0.05, "index": 0.05,
        "sector": 0.00, "overseas": 0.05, "alternative": 0.00,
    },
    2: {  # 稳健: 债为主,权益(含宽基)≤ 30%
        "cash": 0.10, "bond": 0.35, "conservative": 0.25,
        "balanced": 0.05, "equity": 0.10, "index": 0.10,
        "sector": 0.00, "overseas": 0.05, "alternative": 0.00,
    },
    3: {  # 平衡: 股债 5:5
        "cash": 0.05, "bond": 0.20, "conservative": 0.20,
        "balanced": 0.10, "equity": 0.20, "index": 0.15,
        "sector": 0.05, "overseas": 0.05, "alternative": 0.00,
    },
    4: {  # 成长: 权益 70%+
        "cash": 0.05, "bond": 0.10, "conservative": 0.10,
        "balanced": 0.10, "equity": 0.30, "index": 0.20,
        "sector": 0.10, "overseas": 0.05, "alternative": 0.00,
    },
    5: {  # 激进: 权益 85%+
        "cash": 0.00, "bond": 0.05, "conservative": 0.05,
        "balanced": 0.05, "equity": 0.35, "index": 0.20,
        "sector": 0.20, "overseas": 0.05, "alternative": 0.05,
    },
}


def _normalize_template(tpl: dict[str, float]) -> dict[str, float]:
    """补齐缺失键 + 重新归一化到 1.0,容忍浮点误差。"""
    out = {c: 0.0 for c in ASSET_CATEGORIES}
    for k, v in tpl.items():
        if k in out:
            out[k] = max(0.0, float(v))
    total = sum(out.values())
    if total <= 0:
        # 全部为 0 时退化为平衡型默认
        return dict(DEFAULT_TEMPLATES[3])
    return {k: round(v / total, 4) for k, v in out.items()}


def get_target_allocation(prefs: UserPrefs) -> dict[str, float]:
    """根据用户偏好推导目标资产配置(权重 0-1,合计=1.0)。"""
    tpl = dict(DEFAULT_TEMPLATES.get(prefs.risk_level, DEFAULT_TEMPLATES[3]))

    # 1) 期限微调: 期限越短 → 提升现金/短债权重;期限越长 → 提升权益
    horizon_adj = {
        "short":      {"cash": 0.05, "bond": 0.05, "equity": -0.05, "index": -0.05},
        "medium":     {"cash": 0.00, "bond": 0.00, "equity":  0.00, "index":  0.00},
        "long":       {"cash": -0.03, "bond": -0.03, "equity": 0.03, "index": 0.03},
        "very_long":  {"cash": -0.05, "bond": -0.05, "equity": 0.05, "index": 0.05},
    }.get(prefs.horizon, {})
    for k, v in horizon_adj.items():
        if k in tpl:
            tpl[k] = max(0.0, tpl[k] + v)

    # 2) 偏好品类加权(每个偏好品类 +0.05,从现金/债券中扣除)
    for cat in prefs.preferred_categories:
        if cat in tpl and cat not in ("cash", "bond"):
            tpl[cat] += 0.05
            for d in ("cash", "bond"):
                tpl[d] = max(0.0, tpl[d] - 0.025)

    # 3) 显式排除的品类归零
    for cat in prefs.excluded_categories:
        if cat in tpl:
            tpl[cat] = 0.0

    tpl = _normalize_template(tpl)

    # 4) 显式覆盖权益占比(对总权益 = equity + index + sector + 0.5*balanced 生效)
    if prefs.target_equity_override is not None:
        target_eq = max(0.0, min(1.0, prefs.target_equity_override))
        # 当前"权益类"权重合计
        equity_like = tpl.get("equity", 0) + tpl.get("index", 0) + tpl.get("sector", 0) + 0.5 * tpl.get("balanced", 0)
        if equity_like > 0:
            scale = target_eq / equity_like
            tpl["equity"] *= scale
            tpl["index"] *= scale
            tpl["sector"] *= scale
            tpl["balanced"] = max(0.0, tpl["balanced"] * scale) if scale < 1 else tpl["balanced"] * scale
            # 补回非权益
            non_eq = 1.0 - sum(tpl[k] for k in ("equity", "index", "sector", "balanced"))
            if non_eq > 0:
                # 按 cash:bond:conservative:overseas:alternative 比例分配
                share_pool = {k: tpl[k] for k in ("cash", "bond", "conservative", "overseas", "alternative")}
                s = sum(share_pool.values())
                if s > 0:
                    for k in share_pool:
                        tpl[k] = share_pool[k] / s * non_eq
            tpl = _normalize_template(tpl)

    return tpl


# ---------------------------------------------------------------------------
# 落盘路径
# ---------------------------------------------------------------------------

def get_user_prefs_path(user_id: str = "default") -> str:
    """用户偏好文件落盘路径: data/portfolios/<user_id>/prefs.json。"""
    from .stock_data import get_data_dir
    base = os.path.join(get_data_dir(), "portfolios", user_id)
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, "prefs.json")


def save_user_prefs(prefs: UserPrefs) -> str:
    """持久化用户偏好,返回落盘路径。"""
    path = get_user_prefs_path(prefs.user_id)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(prefs.to_dict(), f, ensure_ascii=False, indent=2)
    return path


def load_user_prefs(user_id: str = "default") -> UserPrefs | None:
    """加载用户偏好;不存在时返回 None。"""
    path = get_user_prefs_path(user_id)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return UserPrefs.from_dict(json.load(f))


# ---------------------------------------------------------------------------
# 从用户自然语言中粗提取偏好(供主对话的 Step 0.5 使用)
# ---------------------------------------------------------------------------

# 风险等级关键词 → 数字
_RISK_KW = [
    (5, ("激进", "高风险", "能承受大波动", "all in", "梭哈")),
    (4, ("成长", "积极", "中高风险", "高收益")),
    (3, ("平衡", "中等风险", "中等收益")),
    (2, ("稳健", "低风险", "中低风险", "保本为主")),
    (1, ("保守", "不能亏", "保本", "零风险", "存款级")),
]

# 期限关键词 → horizon
_HORIZON_KW = [
    ("very_long", ("超长期", "10年", "5年以上", "养老")),
    ("long",      ("长期", "3年", "3-5年", "定投", "长期持有")),
    ("medium",    ("中期", "1-3年", "2年", "一到三年")),
    ("short",     ("短期", "半年内", "1年内", "3个月", "几个月")),
]

# 品类关键词(命中任一即加入偏好) → 资产大类
_CAT_KW: list[tuple[str, tuple[str, ...]]] = [
    ("cash",         ("货币", "现金管理", "活期")),
    ("bond",         ("纯债", "短债", "信用债", "债基")),
    ("conservative", ("固收+", "偏债")),
    ("balanced",     ("平衡", "均衡", "灵活")),
    ("equity",       ("主动权益", "偏股", "成长风格", "价值风格")),
    ("index",        ("指数", "宽基", "沪深300", "中证500", "红利")),
    ("sector",       ("医药", "科技", "新能源", "消费", "半导体", "军工", "银行", "券商")),
    ("overseas",     ("QDII", "纳斯达克", "港股", "美股", "海外")),
    ("alternative",  ("REITs", "黄金", "商品")),
]


def parse_user_prefs_from_text(text: str, user_id: str = "default") -> UserPrefs:
    """从用户自然语言中粗提取偏好。

    注意: 这里是**主对话的辅助工具**,不替代 AskUserQuestion 提问;
    实际执行时主对话应先调用此函数,若任一关键字段缺失则反问用户。

    实现细节: 用 "不要/不想/回避/排除" 切分文本为正向/反向段,
    避免 "想加点科技和港股,不要商品和REITs" 这种语句被误判为
    把科技/港股也加进 excluded 列表。
    """
    t = text or ""
    prefs = UserPrefs(user_id=user_id)

    # 风险等级 / 期限: 全文范围内取首次命中
    for lvl, kws in _RISK_KW:
        if any(kw in t for kw in kws):
            prefs.risk_level = lvl
            break
    for h, kws in _HORIZON_KW:
        if any(kw in t for kw in kws):
            prefs.horizon = h
            break

    # 类别偏好 / 排除: 切分"不要"前后的段
    # 一律按逗号、句号、分号、顿号切分,再按"不要"等标记把每段归到 positive / negative
    segments = re.split(r"[,。;、]+", t)
    positive_parts: list[str] = []
    negative_parts: list[str] = []
    neg_markers = ("不要", "不想", "回避", "排除", "别买", "不要买", "不买")
    for seg in segments:
        seg = seg.strip()
        if not seg:
            continue
        if any(m in seg for m in neg_markers):
            negative_parts.append(seg)
        else:
            positive_parts.append(seg)
    pos_text = "\n".join(positive_parts)
    neg_text = "\n".join(negative_parts)

    for cat, kws in _CAT_KW:
        if any(kw in pos_text for kw in kws):
            prefs.preferred_categories.append(cat)
        if any(kw in neg_text for kw in kws):
            prefs.excluded_categories.append(cat)

    # 显式权益占比: "权益 30%" / "股票占比 40%" / "equity 60%"
    m = re.search(r"(?:权益|股票占比|股票仓位|equity)[^0-9]{0,6}(\d{1,3})\s*%", t, re.I)
    if m:
        prefs.target_equity_override = min(1.0, int(m.group(1)) / 100.0)

    # 投资金额
    m = re.search(r"(\d+(?:\.\d+)?)\s*万(?:元|块)?", t)
    if m:
        prefs.investment_amount = float(m.group(1)) * 10000.0

    return prefs


def merge_prefs(*sources: UserPrefs | None) -> UserPrefs:
    """合并多份偏好: 后者覆盖前者;列表字段做并集并去重。"""
    base = UserPrefs()
    for s in sources:
        if s is None:
            continue
        for f in base.__dataclass_fields__:
            v = getattr(s, f)
            if isinstance(v, list):
                merged = list(dict.fromkeys(getattr(base, f) + v))
                setattr(base, f, merged)
            elif f == "user_id" and v:
                base.user_id = v
            elif f == "risk_level" and v != 3:
                base.risk_level = v
            elif f == "horizon" and v != "long":
                base.horizon = v
            elif f == "investment_amount" and v > 0:
                base.investment_amount = v
            elif f == "target_equity_override" and v is not None:
                base.target_equity_override = v
            elif f == "notes" and v:
                base.notes = (base.notes + "\n" + v).strip()
    return base


def explain_template(prefs: UserPrefs, tpl: dict[str, float] | None = None) -> str:
    """输出可读的偏好 → 目标配置解释,供 subagent 报告引用。"""
    tpl = tpl or get_target_allocation(prefs)
    lines = [
        f"风险等级: {prefs.risk_level} ({RISK_LEVEL_NAMES.get(prefs.risk_level, '?')})",
        f"投资期限: {prefs.horizon} ({HORIZON_NAMES.get(prefs.horizon, '?')})",
        f"偏好品类: {prefs.preferred_categories or '(无)'}",
        f"排除品类: {prefs.excluded_categories or '(无)'}",
    ]
    if prefs.target_equity_override is not None:
        lines.append(f"权益占比覆盖: {prefs.target_equity_override:.0%}")
    lines.append("目标资产配置:")
    for cat in ASSET_CATEGORIES:
        w = tpl.get(cat, 0)
        if w > 0:
            lines.append(f"  - {cat}: {w:.1%}")
    return "\n".join(lines)


def iter_category_keywords(categories: Iterable[str]) -> list[str]:
    """把资产大类展开为名称关键词(供 screener 使用)。"""
    out: list[str] = []
    for c in categories:
        out.extend(CATEGORY_KEYWORDS.get(c, ()))
    # 去重保序
    return list(dict.fromkeys(out))
