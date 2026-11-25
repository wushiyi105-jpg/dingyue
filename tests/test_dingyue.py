import unittest
from datetime import date

from dingyue import agent, mock, rules

BILL = """2026-10-03 爱奇艺 25 连续包月
2026-10-05 腾讯视频 30 每月
2026-09-20 百度网盘 30 连续包月
2026-01-08 京东PLUS 198 年费
2026-10-01 iQiyi 30 连续包月
"""


class TestNormalize(unittest.TestCase):
    def test_count(self):
        self.assertEqual(len(rules.merchants()), 120)

    def test_exact(self):
        self.assertEqual(rules.normalize("爱奇艺")["category"], "视频")

    def test_alias(self):
        self.assertEqual(rules.normalize("iQiyi")["name"], "爱奇艺")

    def test_alias_tencent(self):
        self.assertEqual(rules.normalize("Tencent Video")["name"], "腾讯视频")

    def test_unknown(self):
        self.assertIsNone(rules.normalize("某某小店"))


class TestCycle(unittest.TestCase):
    def test_month_word(self):
        m = rules.normalize("爱奇艺")
        self.assertEqual(rules.infer_cycle("连续包月", m), "月")

    def test_year_word(self):
        m = rules.normalize("京东PLUS")
        self.assertEqual(rules.infer_cycle("年费", m), "年")

    def test_quarter(self):
        self.assertEqual(rules.infer_cycle("季度扣费", None), "季")

    def test_merchant_default(self):
        self.assertEqual(rules.infer_cycle("", rules.normalize("京东PLUS")), "年")

    def test_default_month(self):
        self.assertEqual(rules.infer_cycle("", None), "月")


class TestRenewal(unittest.TestCase):
    def test_month(self):
        self.assertEqual(rules.next_renewal(date(2026, 10, 3), "月"), date(2026, 11, 3))

    def test_month_clamp(self):
        self.assertEqual(rules.next_renewal(date(2026, 1, 31), "月"), date(2026, 2, 28))

    def test_year_leap(self):
        self.assertEqual(rules.next_renewal(date(2024, 2, 29), "年"), date(2025, 2, 28))

    def test_quarter(self):
        self.assertEqual(rules.next_renewal(date(2026, 11, 30), "季"), date(2027, 2, 28))

    def test_january_wrap(self):
        self.assertEqual(rules.next_renewal(date(2026, 12, 15), "半年"), date(2027, 6, 15))


class TestParse(unittest.TestCase):
    def test_rows(self):
        rows = rules.parse_bill(BILL)
        self.assertEqual(len(rows), 5)

    def test_amount_and_cycle(self):
        rows = rules.parse_bill(BILL)
        self.assertEqual(rows[0]["merchant"], "爱奇艺")
        self.assertEqual(rows[0]["amount"], 25)
        self.assertEqual(rows[0]["cycle"], "月")
        self.assertEqual(rows[0]["annual"], 300)

    def test_year_price(self):
        rows = rules.parse_bill(BILL)
        jd = [r for r in rows if r["merchant"] == "京东PLUS"][0]
        self.assertEqual(jd["annual"], 198)

    def test_next_date(self):
        rows = rules.parse_bill(BILL)
        self.assertEqual(rows[0]["next"], "2026-11-03")

    def test_unknown_skipped(self):
        rows = rules.parse_bill("2026-10-01 楼下水果店 50 元")
        self.assertEqual(rows, [])


class TestAnalysis(unittest.TestCase):
    def test_total(self):
        a = rules.analyze(BILL)
        self.assertEqual(a["total"], 300 + 360 + 360 + 198 + 360)

    def test_duplicates(self):
        a = rules.analyze(BILL)
        cats = {d["category"] for d in a["duplicates"]}
        self.assertIn("视频", cats)
        self.assertNotIn("云存储", cats)

    def test_inconsistent(self):
        a = rules.analyze(BILL)
        names = [c["merchant"] for c in a["inconsistent"]]
        self.assertIn("爱奇艺", names)

    def test_cost_per_use(self):
        row = {"annual": 300, "merchant": "爱奇艺"}
        self.assertEqual(rules.cost_per_use(row, 10), 2.5)

    def test_cost_per_use_none(self):
        self.assertIsNone(rules.cost_per_use({"annual": 300}, None))

    def test_cut_order_prefers_low_use(self):
        a = rules.analyze(BILL, {"爱奇艺": 1, "腾讯视频": 30})
        self.assertEqual(a["cut"][0]["merchant"], "爱奇艺")

    def test_refund_window(self):
        r = {"last_charge": "2026-11-20", "refund": "首次购买 7 天内且未使用可退"}
        w = rules.refund_window(r, date(2026, 11, 24))
        self.assertEqual(w["days"], 7)
        self.assertEqual(w["left"], 3)
        self.assertTrue(w["open"])


class TestAgent(unittest.TestCase):
    def test_offline_structure(self):
        r = agent.analyze(BILL, force_mock=True)
        self.assertEqual(r["mode"], "offline")
        for k in ("rows", "total", "duplicates", "cut", "summary", "advice", "risks"):
            self.assertTrue(r[k])

    def test_strip_money(self):
        self.assertNotIn("25", agent.strip_money("每月 25 元"))

    def test_mock_keys(self):
        base = rules.analyze(BILL)
        self.assertEqual(set(mock.draft(base)), {"summary", "advice", "risks"})


if __name__ == "__main__":
    unittest.main()
