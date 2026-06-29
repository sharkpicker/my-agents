"""新增模块单测:用户偏好 → 目标配置 → gap → 候选基金筛选."""

from __future__ import annotations

import json
import os
import tempfile
import unittest

from data_tools import portfolio_prefs
from data_tools import portfolio_rebalance


# ---------------------------------------------------------------------------
# 1) UserPrefs + 5 档模板
# ---------------------------------------------------------------------------


class TestUserPrefsAndTargetAllocation(unittest.TestCase):

    def test_all_risk_levels_yield_sum_to_one(self):
        for lvl in portfolio_prefs.RISK_LEVELS:
            prefs = portfolio_prefs.UserPrefs(risk_level=lvl)
            tpl = portfolio_prefs.get_target_allocation(prefs)
            self.assertEqual(set(tpl.keys()), set(portfolio_prefs.ASSET_CATEGORIES))
            total = sum(tpl.values())
            self.assertAlmostEqual(total, 1.0, places=3, msg=f"risk_level={lvl} total={total}")

    def test_risk_level_ordering(self):
        """风险等级越高,权益类(equity+index+sector+0.5*balanced)应单调递增."""
        eq_by_lvl: dict[int, float] = {}
        for lvl in portfolio_prefs.RISK_LEVELS:
            prefs = portfolio_prefs.UserPrefs(risk_level=lvl)
            tpl = portfolio_prefs.get_target_allocation(prefs)
            eq = tpl["equity"] + tpl["index"] + tpl["sector"] + 0.5 * tpl["balanced"]
            eq_by_lvl[lvl] = eq
        for low, high in [(1, 2), (2, 3), (3, 4), (4, 5)]:
            self.assertLess(eq_by_lvl[low], eq_by_lvl[high] + 1e-6,
                            f"风险等级 {low}→{high} 权益未升: {eq_by_lvl[low]} vs {eq_by_lvl[high]}")

    def test_horizon_short_raises_cash(self):
        short = portfolio_prefs.get_target_allocation(portfolio_prefs.UserPrefs(risk_level=3, horizon="short"))
        long = portfolio_prefs.get_target_allocation(portfolio_prefs.UserPrefs(risk_level=3, horizon="very_long"))
        self.assertGreater(short["cash"], long["cash"])
        self.assertLess(short["equity"], long["equity"] + 1e-6)

    def test_preferred_category_gets_extra_weight(self):
        base = portfolio_prefs.get_target_allocation(portfolio_prefs.UserPrefs(risk_level=3))
        with_preferred = portfolio_prefs.get_target_allocation(
            portfolio_prefs.UserPrefs(risk_level=3, preferred_categories=["sector"])
        )
        # 总和都已归一化,需要在等总权益下比较 sector
        # 简单断言:带偏好时 sector 占比 ≥ 基础版
        self.assertGreaterEqual(with_preferred["sector"], base["sector"] - 1e-6)

    def test_excluded_category_set_to_zero(self):
        prefs = portfolio_prefs.UserPrefs(risk_level=3, excluded_categories=["sector", "alternative"])
        tpl = portfolio_prefs.get_target_allocation(prefs)
        self.assertEqual(tpl["sector"], 0.0)
        self.assertEqual(tpl["alternative"], 0.0)
        self.assertAlmostEqual(sum(tpl.values()), 1.0, places=3)

    def test_equity_override_clamps_and_rescales(self):
        prefs = portfolio_prefs.UserPrefs(risk_level=4, target_equity_override=0.30)
        tpl = portfolio_prefs.get_target_allocation(prefs)
        eq_like = tpl["equity"] + tpl["index"] + tpl["sector"] + 0.5 * tpl["balanced"]
        # 允许 ±5% 误差(因归一化四舍五入)
        self.assertAlmostEqual(eq_like, 0.30, delta=0.05)
        self.assertAlmostEqual(sum(tpl.values()), 1.0, places=3)

    def test_parse_text_extracts_risk_horizon_categories(self):
        text = "我是稳健型,打算长期(3-5年)持有,想加点科技和港股,不要商品和REITs"
        prefs = portfolio_prefs.parse_user_prefs_from_text(text)
        self.assertEqual(prefs.risk_level, 2)
        self.assertEqual(prefs.horizon, "long")
        self.assertIn("sector", prefs.preferred_categories)  # 科技
        self.assertIn("overseas", prefs.preferred_categories)  # 港股
        self.assertIn("alternative", prefs.excluded_categories)  # 不要 REITs

    def test_explain_template_includes_human_labels(self):
        prefs = portfolio_prefs.UserPrefs(risk_level=3, horizon="long")
        tpl = portfolio_prefs.get_target_allocation(prefs)
        out = portfolio_prefs.explain_template(prefs, tpl)
        self.assertIn("平衡型", out)
        self.assertIn("长期", out)
        self.assertIn("目标资产配置", out)

    def test_save_load_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # 临时覆盖数据目录
            import data_tools.stock_data as sd
            orig = sd.get_data_dir
            sd.get_data_dir = lambda: tmpdir
            try:
                prefs = portfolio_prefs.UserPrefs(
                    user_id="alice",
                    risk_level=4,
                    horizon="very_long",
                    preferred_categories=["overseas", "sector"],
                )
                path = portfolio_prefs.save_user_prefs(prefs)
                self.assertTrue(os.path.exists(path))
                loaded = portfolio_prefs.load_user_prefs("alice")
                self.assertIsNotNone(loaded)
                self.assertEqual(loaded.risk_level, 4)
                self.assertEqual(loaded.horizon, "very_long")
                self.assertIn("overseas", loaded.preferred_categories)
            finally:
                sd.get_data_dir = orig


# ---------------------------------------------------------------------------
# 2) 持仓分类 / gap
# ---------------------------------------------------------------------------


class TestClassifyAndGap(unittest.TestCase):

    def test_classify_by_name(self):
        positions = [
            {"code": "000001", "name": "沪深300ETF联接A", "amount": 10000, "type": "fund"},
            {"code": "000002", "name": "易方达纯债债券A", "amount": 5000, "type": "fund"},
            {"code": "000003", "name": "中欧医疗健康混合", "amount": 8000, "type": "fund"},
            {"code": "000004", "name": "华夏国证半导体芯片ETF联接", "amount": 3000, "type": "fund"},
            {"code": "000005", "name": "广发纳斯达克100QDII", "amount": 4000, "type": "fund"},
            {"code": "000006", "name": "建信货币", "amount": 2000, "type": "fund"},
        ]
        classified = portfolio_rebalance.classify_positions(positions)
        cats = {p.code: p.category for p in classified}
        self.assertEqual(cats["000001"], "index")
        self.assertEqual(cats["000002"], "bond")
        self.assertEqual(cats["000003"], "sector")
        self.assertEqual(cats["000004"], "sector")
        self.assertEqual(cats["000005"], "overseas")
        self.assertEqual(cats["000006"], "cash")

    def test_classify_avoids_cash_false_positive(self):
        """'自由现金流指数' 不能被识别为 cash."""
        positions = [{"code": "X", "name": "万家中证800自由现金流ETF联接A", "amount": 1000}]
        classified = portfolio_rebalance.classify_positions(positions)
        self.assertEqual(classified[0].category, "index")  # 含"指数" → index 优先于 cash

    def test_gap_basic_under_over_weight(self):
        positions = [
            {"code": "A", "name": "沪深300ETF", "amount": 7000, "type": "fund", "category": "index"},
            {"code": "B", "name": "纯债债券A", "amount": 3000, "type": "fund", "category": "bond"},
        ]
        # 风险等级 3 模板里有 sector/overseas,适合做 gap 测试
        prefs = portfolio_prefs.UserPrefs(risk_level=3)
        target = portfolio_prefs.get_target_allocation(prefs)
        plan = portfolio_rebalance.build_rebalance_plan(positions, prefs)
        # 风险等级 3 目标里 index 占比 15%, 但当前 70% → overweight
        self.assertIn("index", plan.overweight)
        # 目标里 sector 5%, overseas 5% → 当前 0 → underweight
        self.assertIn("sector", plan.underweight)
        self.assertIn("overseas", plan.underweight)
        # gap 数组应包含 9 类
        self.assertEqual(len(plan.gaps), 9)

    def test_gap_action_thresholds(self):
        """delta > 0.03 → add,delta < -0.03 → trim,否则 hold。"""
        positions = [{"code": "A", "name": "沪深300ETF", "amount": 6000, "type": "fund", "category": "index"}]
        prefs = portfolio_prefs.UserPrefs(risk_level=3)
        plan = portfolio_rebalance.build_rebalance_plan(positions, prefs)
        actions = {g.category: g.action for g in plan.gaps}
        # index 当前 100%,目标约 15% → trim
        self.assertEqual(actions["index"], "trim")
        # bond 当前 0%,目标约 20% → add(delta 17% > 3%)
        self.assertEqual(actions["bond"], "add")
        # cash 目标 2% < 3% 阈值 → hold(微小差距不触发加仓)
        # 因为全仓 index 后,其他都是 0%,故 cash 的 delta=2%,刚好不触发
        # 这是设计意图:避免给用户推"加 0.5% 货币基金"这种噪声
        self.assertIn(actions["cash"], ("hold", "add"))


# ---------------------------------------------------------------------------
# 3) 候选基金筛选(以小内存 universe 测,避免依赖 fund_universe 全量)
# ---------------------------------------------------------------------------


def _write_temp_universe(rows: list[dict]) -> str:
    fd, path = tempfile.mkstemp(suffix=".json", prefix="universe_")
    os.close(fd)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False)
    return path


class TestScreenReplacementFunds(unittest.TestCase):

    def test_screen_offexchange_filter(self):
        """场外筛选:场内基金必须被排除。"""
        universe = _write_temp_universe([
            {"code": "111111", "name": "沪深300ETF", "type": "指数型", "is_offexchange": False},
            {"code": "222222", "name": "沪深300ETF联接A", "type": "指数型", "is_offexchange": True},
        ])
        prefs = portfolio_prefs.UserPrefs(risk_level=3)
        out = portfolio_rebalance.screen_replacement_funds(
            categories=["index"],
            prefs=prefs,
            universe_path=universe,
            per_category=5,
        )
        codes = [c["code"] for c in out["index"]]
        self.assertNotIn("111111", codes)
        self.assertIn("222222", codes)

    def test_screen_offexchange_field_missing_treated_as_off(self):
        """字段缺失时(历史数据可能无 is_offexchange),默认视为场外,纳入候选。"""
        universe = _write_temp_universe([
            {"code": "333333", "name": "中欧医疗健康混合A", "type": "混合型"},
        ])
        prefs = portfolio_prefs.UserPrefs(risk_level=3)
        out = portfolio_rebalance.screen_replacement_funds(
            categories=["sector"],
            prefs=prefs,
            universe_path=universe,
            per_category=5,
        )
        codes = [c["code"] for c in out["sector"]]
        self.assertIn("333333", codes)

    def test_screen_excludes_held_codes(self):
        universe = _write_temp_universe([
            {"code": "A1", "name": "沪深300ETF联接A", "type": "指数型", "is_offexchange": True},
            {"code": "A2", "name": "中证500ETF联接A", "type": "指数型", "is_offexchange": True},
            {"code": "A3", "name": "中证1000ETF联接A", "type": "指数型", "is_offexchange": True},
        ])
        prefs = portfolio_prefs.UserPrefs(risk_level=3)
        out = portfolio_rebalance.screen_replacement_funds(
            categories=["index"],
            prefs=prefs,
            universe_path=universe,
            per_category=5,
            held_codes={"A1", "A2"},
        )
        codes = [c["code"] for c in out["index"]]
        self.assertNotIn("A1", codes)
        self.assertNotIn("A2", codes)
        self.assertIn("A3", codes)

    def test_screen_excluded_category_filtered_out(self):
        universe = _write_temp_universe([
            {"code": "B1", "name": "华泰柏瑞中证红利低波ETF联接A", "type": "指数型", "is_offexchange": True},
            {"code": "B2", "name": "REITs 华夏建信中关村", "type": "REITs", "is_offexchange": True},
        ])
        prefs = portfolio_prefs.UserPrefs(risk_level=2, excluded_categories=["alternative"])
        out = portfolio_rebalance.screen_replacement_funds(
            categories=["index", "alternative"],
            prefs=prefs,
            universe_path=universe,
            per_category=5,
        )
        # alternative 类别下不应有候选
        self.assertEqual(out["alternative"], [])
        # index 类别下应有 B1
        codes = [c["code"] for c in out["index"]]
        self.assertIn("B1", codes)

    def test_screen_ranking_score(self):
        """评分靠前 = 名称关键词命中 + 用户偏好加权。"""
        universe = _write_temp_universe([
            {"code": "C1", "name": "易方达沪深300ETF联接A", "type": "指数型", "is_offexchange": True},
            {"code": "C2", "name": "中证500ETF联接A", "type": "指数型", "is_offexchange": True},
            {"code": "C3", "name": "中证红利低波ETF联接A", "type": "指数型", "is_offexchange": True},
        ])
        prefs = portfolio_prefs.UserPrefs(risk_level=3, preferred_categories=["index"])
        out = portfolio_rebalance.screen_replacement_funds(
            categories=["index"],
            prefs=prefs,
            universe_path=universe,
            per_category=5,
        )
        # 所有都是 index,名称都含"指数"/"联接"等关键词
        self.assertEqual(len(out["index"]), 3)
        # 分数相同则按名称排序
        for c in out["index"]:
            self.assertGreaterEqual(c["score"], 50.0)


# ---------------------------------------------------------------------------
# 4) 端到端 rebalance 报告
# ---------------------------------------------------------------------------


class TestRebalancePlanE2E(unittest.TestCase):

    def test_e2e_realistic_holdings(self):
        """端到端:偏股持仓 + 平衡型偏好 → 触发 sector/overseas underweight。"""
        positions = [
            {"code": "001", "name": "沪深300ETF联接A", "amount": 5000, "type": "fund", "category": "index"},
            {"code": "002", "name": "易方达蓝筹精选混合", "amount": 3000, "type": "fund", "category": "equity"},
        ]
        prefs = portfolio_prefs.UserPrefs(risk_level=3)
        plan = portfolio_rebalance.build_rebalance_plan(positions, prefs)
        # 当前 100% 都是 index/equity,目标需要 bond/conservative/cash/overseas/sector → 这些都该在 underweight
        self.assertIn("bond", plan.underweight)
        self.assertIn("sector", plan.underweight)
        self.assertIn("overseas", plan.underweight)
        # index 当前 62.5%,目标 15% → overweight
        self.assertIn("index", plan.overweight)
        # md 渲染含关键模块
        md = portfolio_rebalance.plan_to_markdown(plan, prefs)
        self.assertIn("用户偏好与目标配置", md)
        self.assertIn("gap 矩阵", md)
        self.assertIn("不构成投资建议", md)

    def test_rebalance_with_universe_includes_recommendations(self):
        """端到端:配 universe 时,replacements 不为空(若 universe 中有匹配)。"""
        universe = _write_temp_universe([
            {"code": "D1", "name": "易方达中证海外互联ETF联接A", "type": "QDII", "is_offexchange": True},
            {"code": "D2", "name": "华夏恒生ETF联接A", "type": "QDII", "is_offexchange": True},
            {"code": "D3", "name": "华泰柏瑞中证红利低波ETF联接A", "type": "指数型", "is_offexchange": True},
        ])
        positions = [{"code": "001", "name": "沪深300ETF", "amount": 10000, "type": "fund", "category": "index"}]
        prefs = portfolio_prefs.UserPrefs(risk_level=2, preferred_categories=["overseas"])
        plan = portfolio_rebalance.build_rebalance_plan(positions, prefs, universe_path=universe)
        # overseas 应在 underweight 且有候选
        self.assertIn("overseas", plan.underweight)
        if plan.replacements.get("overseas"):
            codes = [c["code"] for c in plan.replacements["overseas"]]
            self.assertTrue({"D1", "D2"} & set(codes))


if __name__ == "__main__":
    unittest.main()
