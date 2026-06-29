"""新单测:fund_list FTYPE 修复 + 评分提升.

覆盖:
1) _is_dirty_type 识别脏数据
2) _parse_primary_response 不再带 type 字段
3) enrich_fund_list_with_ftype 写入 ftype 字段(用 mock 跳过真实网络)
4) repair_fund_list 清理脏 type + 补全 ftype
5) screener 评分在有 ftype 时提升 + 在脏 type 时不误判
6) is_offexchange_fund 兼容 ftype 字段
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from unittest.mock import patch

from data_tools import fund_universe
from data_tools.fund_universe import (
    _is_dirty_type,
    _parse_primary_response,
    enrich_fund_list_with_ftype,
    is_offexchange_fund,
    repair_fund_list,
)
from data_tools.portfolio_rebalance import (
    _score_fund,
    screen_replacement_funds,
)
from data_tools.portfolio_prefs import UserPrefs


# ---------------------------------------------------------------------------
# 1) _is_dirty_type
# ---------------------------------------------------------------------------


class TestIsDirtyType(unittest.TestCase):

    def test_dirty_numeric_navigated_to_nav(self):
        """数字(实际是累计净值)判为脏."""
        for v in ["113.1107", "2.6002", "0.00%", "0.15", "-1.5", ""]:
            self.assertTrue(_is_dirty_type(v), f"应判为脏: {v!r}")

    def test_dirty_none(self):
        self.assertTrue(_is_dirty_type(None))

    def test_clean_chinese_fund_type(self):
        """中文基金类型判为干净."""
        for v in ["股票型", "混合型-灵活", "债券型-中短债", "指数型-股票", "QDII", "货币型"]:
            self.assertFalse(_is_dirty_type(v), f"应判为干净: {v!r}")

    def test_dirty_too_long(self):
        self.assertTrue(_is_dirty_type("x" * 50))

    def test_dirty_special_chars(self):
        for v in ["a/b", "a\\b", "a?b", "a=b"]:
            self.assertTrue(_is_dirty_type(v), f"应判为脏: {v!r}")


# ---------------------------------------------------------------------------
# 2) _parse_primary_response — 主端点不再带 type
# ---------------------------------------------------------------------------


class TestParsePrimaryNoType(unittest.TestCase):

    REAL_JS = (
        'var db={chars:["0","1"],datas:[["270007","广发大盘成长混合","GFDPCZHH","","",'
        '"2.4288","2.6002","","","开放申购","开放赎回","","1","0","1","","1","0.15%","0.15%","1","1.50%"],'
        '["270010","广发沪深300ETF联接A","GFHS300ETFLJA","","","1.8681","2.6984","","",'
        '"开放申购","开放赎回","","1","0","3","","1","0.12%","0.12%","1","1.20%"]],'
        'count:["0","0","0","0"],record:"23592",pages:"7864",curpage:"1"}'
    )

    def test_primary_response_omits_type(self):
        rows = _parse_primary_response(self.REAL_JS)
        self.assertEqual(len(rows), 2)
        for r in rows:
            # 主端点不返回 FTYPE — 修复后 type 字段不应再被误填
            self.assertNotIn("type", r, f"主端点不应输出 type 字段: {r}")
            self.assertIn("code", r)
            self.assertIn("name", r)

    def test_primary_response_preserves_code_and_name(self):
        rows = _parse_primary_response(self.REAL_JS)
        self.assertEqual(rows[0]["code"], "270007")
        self.assertEqual(rows[0]["name"], "广发大盘成长混合")
        self.assertEqual(rows[1]["code"], "270010")


# ---------------------------------------------------------------------------
# 3) enrich_fund_list_with_ftype — 用 mock 跳过真实网络
# ---------------------------------------------------------------------------


class TestEnrichFtype(unittest.TestCase):

    def test_enrich_writes_ftype_per_fund(self):
        funds = [
            {"code": "270007", "name": "广发大盘成长混合", "is_offexchange": True},
            {"code": "161725", "name": "招商中证白酒指数", "is_offexchange": True},
        ]
        with patch("data_tools.fund_data.get_fund_ftype") as mock:
            mock.side_effect = lambda code, save=False: {
                "270007": "混合型-灵活",
                "161725": "指数型-股票",
            }.get(code, "")
            result = enrich_fund_list_with_ftype(funds, sleep_min=0, sleep_max=0)
        self.assertEqual(result["ok"], 2)
        self.assertEqual(result["fail"], 0)
        self.assertEqual(funds[0]["ftype"], "混合型-灵活")
        self.assertEqual(funds[1]["ftype"], "指数型-股票")
        self.assertEqual(result["stats"]["混合型-灵活"], 1)
        self.assertEqual(result["stats"]["指数型-股票"], 1)

    def test_enrich_partial_failure(self):
        funds = [
            {"code": "A", "name": "f1"},
            {"code": "B", "name": "f2"},
            {"code": "C", "name": "f3"},
        ]
        with patch("data_tools.fund_data.get_fund_ftype") as mock:
            mock.side_effect = lambda code, save=False: {"A": "股票型"}.get(code, "")
            result = enrich_fund_list_with_ftype(funds, sleep_min=0, sleep_max=0)
        self.assertEqual(result["ok"], 1)
        self.assertEqual(result["fail"], 2)
        self.assertEqual(funds[0].get("ftype"), "股票型")
        self.assertNotIn("ftype", funds[1])
        self.assertNotIn("ftype", funds[2])

    def test_enrich_batch_size_limits_processing(self):
        funds = [{"code": str(i), "name": f"f{i}"} for i in range(20)]
        with patch("data_tools.fund_data.get_fund_ftype") as mock:
            mock.side_effect = lambda code, save=False: "股票型" if code != "5" else ""
            result = enrich_fund_list_with_ftype(funds, batch_size=10, sleep_min=0, sleep_max=0)
        self.assertEqual(result["total"], 10)
        self.assertEqual(result["ok"], 9)
        # 后面 10 只不应被处理
        for f in funds[10:]:
            self.assertNotIn("ftype", f)


# ---------------------------------------------------------------------------
# 4) repair_fund_list
# ---------------------------------------------------------------------------


class TestRepairFundList(unittest.TestCase):

    def test_dry_run_does_not_modify_or_save(self):
        funds = [
            {"code": "A", "name": "f1", "type": "113.1107"},
            {"code": "B", "name": "f2", "type": "股票型"},
            {"code": "C", "name": "f3", "type": ""},
        ]
        result = repair_fund_list(funds=funds, dry_run=True)
        self.assertTrue(result["dry_run"])
        self.assertEqual(result["before_dirty"], 2)  # "113.1107" 和 "" 是脏
        # dry_run 不写 ftype
        self.assertNotIn("ftype", funds[0])
        self.assertNotIn("ftype", funds[1])

    def test_repair_clears_dirty_type_and_enriches(self):
        funds = [
            {"code": "A", "name": "f1", "type": "113.1107"},
            {"code": "B", "name": "f2", "type": "股票型"},
            {"code": "C", "name": "f3", "type": ""},
        ]
        with patch("data_tools.fund_data.get_fund_ftype") as mock:
            mock.side_effect = lambda code, save=False: {
                "A": "指数型-股票",
                "B": "股票型",
                "C": "货币型",
            }.get(code, "")
            result = repair_fund_list(funds=funds, dry_run=False)
        # A 和 C 的 type 被清空
        self.assertEqual(funds[0]["type"], "")
        # B 的 type 原本是干净的"股票型",不强制清空(force_repair=False)
        self.assertEqual(funds[1]["type"], "股票型")
        self.assertEqual(funds[2]["type"], "")
        # ftype 全部 enrich 成功
        self.assertEqual(funds[0]["ftype"], "指数型-股票")
        self.assertEqual(funds[1]["ftype"], "股票型")
        self.assertEqual(funds[2]["ftype"], "货币型")
        # saved=False 因为我们传入了外部 funds 列表(in_place=False)
        self.assertFalse(result["saved"])
        self.assertEqual(result["ftype_added"], 3)

    def test_repair_force_clears_clean_type_too(self):
        funds = [{"code": "A", "name": "f1", "type": "股票型"}]
        with patch("data_tools.fund_data.get_fund_ftype") as mock:
            mock.side_effect = lambda code, save=False: "股票型"
            repair_fund_list(funds=funds, dry_run=False, force_repair=True)
        # force_repair=True → 干净 type 也被清空
        self.assertEqual(funds[0]["type"], "")
        # ftype 仍然写入
        self.assertEqual(funds[0]["ftype"], "股票型")

    def test_repair_with_empty_list(self):
        result = repair_fund_list(funds=[], dry_run=False)
        self.assertEqual(result["ftype_added"], 0)
        self.assertIn("message", result)


# ---------------------------------------------------------------------------
# 5) screener 评分:有 ftype 时提升
# ---------------------------------------------------------------------------


class TestScreenerFtypeScoreBoost(unittest.TestCase):

    def test_score_with_ftype_higher_than_without(self):
        prefs = UserPrefs(risk_level=3)
        fund_no_ftype = {
            "code": "X1",
            "name": "易方达沪深300ETF联接A",
            "is_offexchange": True,
        }
        fund_with_ftype = {
            "code": "X2",
            "name": "易方达沪深300ETF联接A",
            "is_offexchange": True,
            "ftype": "指数型-股票",
        }
        score1, reasons1 = _score_fund(fund_no_ftype, "index", prefs)
        score2, reasons2 = _score_fund(fund_with_ftype, "index", prefs)
        # 有 ftype 时,得分应高出 20 分
        self.assertAlmostEqual(score2 - score1, 20.0, places=5)
        self.assertTrue(any("FTYPE" in r for r in reasons2))
        self.assertFalse(any("FTYPE" in r for r in reasons1))

    def test_score_ignores_dirty_numeric_type(self):
        """历史脏数据 type='113.1107' 不应被误判为有效类型加分."""
        prefs = UserPrefs(risk_level=3)
        fund_dirty = {
            "code": "Y1",
            "name": "中欧医疗健康混合A",
            "is_offexchange": True,
            "type": "113.1107",  # 脏数据(实际是累计净值)
        }
        score, reasons = _score_fund(fund_dirty, "sector", prefs)
        # 名称"中欧医疗健康"含"医疗"关键词 → +50
        # 但脏 type 不应加分 → 总分 50
        self.assertEqual(score, 50.0)
        # 应在 reasons 中显式标注"FTYPE 脏数据"
        self.assertTrue(any("脏数据" in r for r in reasons))

    def test_score_falls_back_to_type_when_no_ftype(self):
        """没有 ftype 但有干净 type 时,仍然能拿到 ftype 评分."""
        prefs = UserPrefs(risk_level=3)
        fund = {
            "code": "Z1",
            "name": "招商中证白酒指数A",
            "is_offexchange": True,
            "type": "指数型-股票",  # 没有 ftype,但 type 是干净中文
        }
        score, reasons = _score_fund(fund, "index", prefs)
        # 名称"指数" → +50
        # 干净 type"指数型-股票" → +20(因为 ftype 字段为空,fallback 到 type)
        self.assertEqual(score, 70.0)


# ---------------------------------------------------------------------------
# 6) is_offexchange_fund 兼容 ftype 字段
# ---------------------------------------------------------------------------


class TestIsOffexchangeFtypeCompat(unittest.TestCase):

    def test_offexchange_by_ftype(self):
        """通过 ftype 字段识别场内基金."""
        record = {
            "code": "510500",
            "name": "广发中证500ETF",
            "ftype": "场内 ETF",
        }
        self.assertFalse(is_offexchange_fund(record))

    def test_offexchange_by_name_etf(self):
        record = {"code": "510500", "name": "广发中证500ETF", "type": ""}
        self.assertFalse(is_offexchange_fund(record))

    def test_offexchange_true_for_offexchange(self):
        record = {
            "code": "270007",
            "name": "广发大盘成长混合",
            "ftype": "混合型-灵活",
        }
        self.assertTrue(is_offexchange_fund(record))

    def test_offexchange_handles_missing_type(self):
        """没有 type / ftype 字段时,不应崩溃."""
        record = {"code": "270007", "name": "广发大盘成长混合"}
        self.assertTrue(is_offexchange_fund(record))


# ---------------------------------------------------------------------------
# 7) 端到端:小内存 universe + ftype enrich + screener
# ---------------------------------------------------------------------------


def _write_temp_universe(rows: list[dict]) -> str:
    fd, path = tempfile.mkstemp(suffix=".json", prefix="universe_")
    os.close(fd)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False)
    return path


class TestE2EFtypeEnrichment(unittest.TestCase):

    def test_screener_uses_ftype_when_present(self):
        """含 ftype 的基金评分应高于无 ftype 的同名基金."""
        universe = _write_temp_universe([
            # 无 ftype: 名称含"医药",但 ftype 未知
            {"code": "W1", "name": "中欧医疗健康混合A", "is_offexchange": True},
            # 有 ftype: 名称含"医药",ftype 是"股票型"(主动) → sector 加分
            {"code": "W2", "name": "中欧医疗健康混合C", "is_offexchange": True, "ftype": "股票型"},
        ])
        prefs = UserPrefs(risk_level=3)
        out = screen_replacement_funds(
            categories=["sector"],
            prefs=prefs,
            universe_path=universe,
            per_category=5,
        )
        self.assertEqual(len(out["sector"]), 2)
        # 有 ftype 的 W2 评分更高
        w2 = next(c for c in out["sector"] if c["code"] == "W2")
        w1 = next(c for c in out["sector"] if c["code"] == "W1")
        self.assertGreater(w2["score"], w1["score"])
        self.assertEqual(w2["score"] - w1["score"], 20.0)

    def test_repair_then_screener_end_to_end(self):
        """repair → enrich 后 screener 评分应提升."""
        universe = _write_temp_universe([
            {"code": "P1", "name": "广发大盘成长混合", "type": "113.1107", "is_offexchange": True},
            {"code": "P2", "name": "易方达沪深300ETF联接A", "type": "", "is_offexchange": True},
        ])
        # 模拟 repair(用 mock 不打网络,显式传 funds + batch_size)
        funds = json.load(open(universe, encoding="utf-8"))
        with patch("data_tools.fund_data.get_fund_ftype") as mock:
            mock.side_effect = lambda code, save=False: {
                "P1": "混合型-灵活",
                "P2": "指数型-股票",
            }.get(code, "")
            repair_fund_list(funds=funds, dry_run=False, batch_size=2)
        # 落盘 + 再读
        with open(universe, "w", encoding="utf-8") as f:
            json.dump(funds, f, ensure_ascii=False)

        prefs = UserPrefs(risk_level=3)
        # index 类目下 P2 的 ftype 是"指数型-股票" → 应拿到 70 分
        out = screen_replacement_funds(
            categories=["index"],
            prefs=prefs,
            universe_path=universe,
            per_category=5,
        )
        # P1 名称不含"指数",应被过滤;P2 应保留
        codes = [c["code"] for c in out["index"]]
        self.assertIn("P2", codes)
        self.assertNotIn("P1", codes)
        p2 = next(c for c in out["index"] if c["code"] == "P2")
        self.assertEqual(p2["score"], 70.0)


if __name__ == "__main__":
    unittest.main()
