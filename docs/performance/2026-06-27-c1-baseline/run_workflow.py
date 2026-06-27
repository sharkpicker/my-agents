"""真实持仓 C-1 工作流运行 + 性能数据采集。

基于 9 只基金真实持仓数据,跑完整的 C-1 portfolio 工作流,
记录每步耗时,产出 HTML 报告 + 性能基线。
"""
import json
import time
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from data_tools.detect import detect_input
from data_tools.portfolio import (
    calculate_concentration,
    calculate_balance,
    detect_overlap,
)
from data_tools.template_renderer import render

PERF = []


def step(name):
    """记录步骤开始时间。"""
    PERF.append({"step": name, "t_start": time.perf_counter()})


def end():
    """记录步骤结束时间。"""
    PERF[-1]["t_end"] = time.perf_counter()
    PERF[-1]["duration_ms"] = round(
        (PERF[-1]["t_end"] - PERF[-1]["t_start"]) * 1000, 2
    )


# ====== 加载真实持仓 ======
HOLDINGS_PATH = REPO / "reports" / "2026-06-27" / "portfolio" / "real_holdings_c1.json"
HOLDINGS = json.loads(HOLDINGS_PATH.read_text(encoding="utf-8"))["positions"]
TOTAL_AMOUNT = sum(p["amount"] for p in HOLDINGS)

print(f"\n{'=' * 60}")
print(f"C-1 工作流:9 基金组合诊断")
print(f"持仓数: {len(HOLDINGS)}, 总金额: ¥{TOTAL_AMOUNT:,.2f}")
print(f"{'=' * 60}\n")

# ====== Step 0: 输入识别 ======
step("Step 0: input_router")
r0 = detect_input("分析我的持仓", holdings=HOLDINGS)
end()
print(f"[Step 0] 类型={r0.type.value}, 持仓={len(r0.positions)}, 耗时={PERF[-1]['duration_ms']}ms")
assert r0.type.value == "C-1"

# ====== Step 1 (mock): 7 角色 × 9 基金 = 63 subagent ======
# 真实场景需要 LLM 调用,这里用 mock 模拟调度开销
step("Step 1: 7 角色 × 9 基金 = 63 subagent (mock)")
roles = [
    "fund_market", "fund_fundamentals", "holdings", "flows",
    "fund_news", "fund_policy", "fund_sentiment",
]
SUBAGENT_COUNT = len(HOLDINGS) * len(roles)
mock_report_count = SUBAGENT_COUNT
# 模拟 subagent 调度延迟(每次 ~50ms 启动开销)
time.sleep(0.05 * SUBAGENT_COUNT)
end()
print(f"[Step 1] 模拟 {SUBAGENT_COUNT} 个 subagent 并行调度,耗时={PERF[-1]['duration_ms']}ms")

# ====== Step 2: data_quality_auditor (mock) ======
step("Step 2: data_quality_auditor (mock)")
audit_result = {"status": "pass", "warnings": 0, "errors": 0}
time.sleep(0.02)  # mock 审计
end()
print(f"[Step 2] 审计: {audit_result['status']}, 耗时={PERF[-1]['duration_ms']}ms")

# ====== Step 2.5: portfolio_analyst(真实计算) ======
step("Step 2.5: portfolio_analyst (真实)")

# 集中度
hhi = calculate_concentration(HOLDINGS)
if hhi < 0.18:
    hhi_level = "分散"
elif hhi < 0.25:
    hhi_level = "中等分散"
elif hhi < 0.50:
    hhi_level = "中等集中"
else:
    hhi_level = "高度集中"

# 穿透股债平衡(根据基金类型估算 penetration)
PENETRATION_MAP = {
    "007466": 0.50,  # 红利低波 ETF 联接 - 50% 权益
    "080005": 0.60,  # 量化红利混合 - 60% 权益
    "024419": 0.90,  # 新能源 ETF - 90% 权益
    "014767": 0.20,  # 稳健 6 个月 - 20% 权益
    "005313": 0.95,  # 1000 指数增强 - 95% 权益
    "010673": 0.95,  # 800 指数增强 - 95% 权益
    "004069": 0.95,  # 证券公司 ETF - 95% 权益
    "001717": 0.95,  # 前沿医疗股票 - 95% 权益
    "015143": 0.85,  # 智能制造混合 - 85% 权益
}
balance_holdings = [
    {**p, "stock_penetration": PENETRATION_MAP.get(p["code"], 0.5)}
    for p in HOLDINGS
]
balance = calculate_balance(balance_holdings)

# overlap(无直接持仓,但调用验证)
overlaps = detect_overlap({}, [])  # 空数据,期望 []

end()
print(f"[Step 2.5] HHI={hhi:.4f} ({hhi_level}), "
      f"权益={balance['equity_ratio']*100:.1f}%, "
      f"耗时={PERF[-1]['duration_ms']}ms")

# ====== Step 3-7: 多空辩论 → 经理 → 交易 → 风险 → 组合经理 (mock) ======
for name in ["Step 3: 多空辩论", "Step 4: 研究经理", "Step 5: 交易员",
             "Step 6: 风险评估(3 路并行)", "Step 7: 组合经理"]:
    step(name + " (mock)")
    time.sleep(0.05)
    end()
    print(f"[{name[:10]}] 耗时={PERF[-1]['duration_ms']}ms")

# ====== Step 8: html_renderer ======
step("Step 8: html_renderer")
total_return = sum(p["holding_return"] for p in HOLDINGS)
total_return_pct = total_return / TOTAL_AMOUNT * 100

# 加 ratio 字段
for p in HOLDINGS:
    p["ratio"] = round(p["amount"] / TOTAL_AMOUNT * 100, 2)

meta = {
    "code": "C1_PORTFOLIO",
    "name": f"我的 9 基金组合 (¥{TOTAL_AMOUNT:,.0f})",
    "date": "2026-06-27",
    "report_type": "C-1",
}
sections = [
    {"title": "1. 持仓概览", "content": f"共 {len(HOLDINGS)} 只基金, 总金额 ¥{TOTAL_AMOUNT:,.2f}, 加权收益率 {total_return_pct:+.2f}%"},
    {"title": "2. 集中度", "content": f"HHI = {hhi:.4f} ({hhi_level})"},
    {"title": "3. 穿透股债", "content": f"权益 {balance['equity_ratio']*100:.1f}% / 债券 {balance['bond_ratio']*100:.1f}%"},
    {"title": "4. 收益排行", "content": "\n".join([
        f"{i+1}. {p['name']} ({p['holding_return_pct']:+.2f}%)"
        for i, p in enumerate(sorted(HOLDINGS, key=lambda x: x["holding_return_pct"], reverse=True))
    ])},
    {"title": "5. 目标配置建议", "content": (
        f"权益 {balance['equity_ratio']*100:.0f}% → 建议 50% "
        f"({'偏高' if balance['equity_ratio'] > 0.7 else '合理' if balance['equity_ratio'] > 0.4 else '偏低'})"
    )},
    {"title": "6. 风险提示", "content": "集中度偏高, 工银前沿医疗(27.07%)与华泰柏瑞红利低波(36.35%)合计超 60%, 建议分散"},
]

target_allocation = [
    {"name": p["name"], "target_ratio": round(100 / len(HOLDINGS), 2), "current_ratio": p["ratio"]}
    for p in HOLDINGS
]

html = render(
    template="portfolio",
    meta=meta,
    portfolio_subtype="c1",
    portfolio={
        "fund_count": len(HOLDINGS),
        "stock_count": 0,
        "positions": HOLDINGS,
    },
    overlaps=[],
    balance={
        "equity_ratio": round(balance["equity_ratio"] * 100, 2),
        "bond_ratio": round(balance["bond_ratio"] * 100, 2),
    },
    risk_views=[
        {"view": "neutral", "risk_level": "Medium", "max_drawdown": 18, "suggested_position": 60},
    ],
    target_allocation=target_allocation,
    sections=sections,
    stock_items=[],
    fund_meta={},
    trade={},
)

REPORT_PATH = REPO / "reports" / "2026-06-27" / "portfolio" / "portfolio_c1_real_2026-06-27.html"
REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
REPORT_PATH.write_text(html, encoding="utf-8")
end()
print(f"[Step 8] 报告生成: {REPORT_PATH.name} ({REPORT_PATH.stat().st_size:,} bytes), 耗时={PERF[-1]['duration_ms']}ms")

# ====== 性能汇总 ======
total_ms = sum(s["duration_ms"] for s in PERF)
print(f"\n{'=' * 60}")
print(f"性能汇总(本地 + mock 混合,仅供参考):")
print(f"{'=' * 60}")
for s in PERF:
    print(f"  {s['step']:<40} {s['duration_ms']:>8.2f} ms")
print(f"  {'-' * 50}")
print(f"  {'TOTAL':<40} {total_ms:>8.2f} ms")
print(f"\n  注:Step 1/3-7 含 mock 模拟,真实 LLM 调用时间会显著更长")

# 保存 perf 数据
PERF_PATH = REPO / "reports" / "2026-06-27" / "portfolio" / "perf_baseline.json"
PERF_PATH.write_text(
    json.dumps({
        "scenario": "C-1",
        "holdings_count": len(HOLDINGS),
        "total_amount": TOTAL_AMOUNT,
        "steps": PERF,
        "total_ms": total_ms,
        "html_path": str(REPORT_PATH.relative_to(REPO)),
        "html_size_bytes": REPORT_PATH.stat().st_size,
    }, ensure_ascii=False, indent=2),
    encoding="utf-8",
)
print(f"\n  性能数据保存到: {PERF_PATH.relative_to(REPO)}")
print(f"  HTML 报告: {REPORT_PATH.relative_to(REPO)}")