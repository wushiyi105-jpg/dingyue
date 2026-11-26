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


class TestAmountGreediness(unittest.TestCase):
    """issue #2:行首日期与容量里的数字被当金额。"""

    def test_storage_number_is_not_amount(self):
        rows = rules.parse_bill("2026-11-20 iCloud+ 200G 连续包月 ¥6.00")
        self.assertEqual(rows[0]["merchant"], "iCloud+")
        self.assertEqual(rows[0]["amount"], 6)
        self.assertEqual(rows[0]["annual"], 72)

    def test_chinese_date_is_not_amount(self):
        rows = rules.parse_bill("2026年11月3日 爱奇艺 黄金VIP 首月 9.9 元，次月起 25 元/月")
        self.assertEqual(rows[0]["merchant"], "爱奇艺")
        self.assertEqual(rows[0]["last_charge"], "2026-11-03")
        self.assertEqual(rows[0]["amount"], 25)

    def test_chinese_date_alone(self):
        rows = rules.parse_bill("2026年11月10日 百度网盘 超级会员 25 元/月")
        self.assertEqual(rows[0]["last_charge"], "2026-11-10")
        self.assertEqual(rows[0]["amount"], 25)

    def test_currency_wins_over_bare_number(self):
        rows = rules.parse_bill("2026-11-09 腾讯视频 4K 电视端 ¥30.00")
        self.assertEqual(rows[0]["amount"], 30)

    def test_plain_number_still_works(self):
        rows = rules.parse_bill("2026-10-03 爱奇艺 25 连续包月")
        self.assertEqual(rows[0]["amount"], 25)


class TestThousandsSeparator(unittest.TestCase):
    """issue #3:¥1,288.00 被读成 1 元。"""

    def test_comma_amount(self):
        rows = rules.parse_bill("2026-03-02 山姆会员 卓越会员 年费 ¥1,288.00")
        self.assertEqual(rows[0]["amount"], 1288)
        self.assertEqual(rows[0]["annual"], 1288)

    def test_comma_without_currency(self):
        rows = rules.parse_bill("2026-06-18 Adobe Creative Cloud 1,888 元 年费")
        self.assertEqual(rows[0]["amount"], 1888)

    def test_total_adds_up(self):
        a = rules.analyze("2026-03-02 山姆会员 年费 ¥1,288.00\n2026-09-09 京东PLUS 年费 149 元")
        self.assertEqual(a["total"], 1437)


class TestPromoPrice(unittest.TestCase):
    """issue #4:首月 9.9 被当成常规价,年化少算一半。"""

    def test_first_month_is_not_regular_price(self):
        rows = rules.parse_bill("2026年11月3日 爱奇艺 黄金VIP 首月 9.9 元，次月起 25 元/月")
        self.assertEqual(rows[0]["amount"], 25)
        self.assertEqual(rows[0]["annual"], 300)
        self.assertTrue(rows[0]["flags"])

    def test_promo_note_mentions_first_month(self):
        rows = rules.parse_bill("2026-11-06 腾讯视频 VIP 首月 9.9 元，次月起 30 元/月")
        self.assertIn("9.9", "".join(rows[0]["flags"]))

    def test_trial_note(self):
        rows = rules.parse_bill("2026-11-10 百度网盘 超级会员 7 天免费试用，试用结束后 25 元/月")
        self.assertEqual(rows[0]["amount"], 25)
        self.assertIn("7 天", "".join(rows[0]["flags"]))


class TestOneOff(unittest.TestCase):
    """issue #5:一次性买断被按订阅年化 12 倍。"""

    BILL = "2026-11-09 Steam 钱包充值 30 元 一次性"

    def test_cycle_is_one_off(self):
        rows = rules.parse_bill(self.BILL)
        self.assertEqual(rows[0]["cycle"], "一次性")

    def test_not_multiplied_by_twelve(self):
        rows = rules.parse_bill(self.BILL)
        self.assertEqual(rows[0]["annual"], 30)

    def test_no_next_renewal(self):
        rows = rules.parse_bill(self.BILL)
        self.assertIsNone(rows[0]["next"])

    def test_excluded_from_annual_total(self):
        a = rules.analyze(self.BILL + "\n2026-11-02 酷狗音乐 15 元 连续包月")
        self.assertEqual(a["total"], 180)
        self.assertEqual(a["one_off_total"], 30)
        self.assertEqual(a["one_off_count"], 1)
        self.assertEqual(a["subscription_count"], 1)

    def test_not_in_cut_list(self):
        a = rules.analyze(self.BILL)
        self.assertEqual(a["cut"], [])


class TestRefundClosed(unittest.TestCase):
    """issue #6:「不可退」的商户被算成 7 天可退,给出假希望。"""

    def test_virtual_goods_not_refundable(self):
        r = {"last_charge": "2026-11-24", "refund": "虚拟商品一般不可退,未消费点数可申请",
             "cycle": "一次性"}
        w = rules.refund_window(r, date(2026, 11, 25))
        self.assertEqual(w["days"], 0)
        self.assertFalse(w["open"])
        self.assertTrue(w["note"])

    def test_year_card_still_has_window(self):
        r = {"last_charge": "2026-11-20", "refund": "年卡 7 天内未使用可退,已享权益按比例扣减",
             "cycle": "年"}
        w = rules.refund_window(r, date(2026, 11, 24))
        self.assertEqual(w["days"], 7)
        self.assertTrue(w["open"])

    def test_monthly_clause_wins_for_month_plan(self):
        r = {"last_charge": "2026-11-20", "refund": "月付按周期计费不退,年付 14 天内可申请",
             "cycle": "月"}
        self.assertEqual(rules.refund_days(r), 0)

    def test_yearly_clause_wins_for_year_plan(self):
        r = {"last_charge": "2026-11-20", "refund": "月付按周期计费不退,年付 14 天内可申请",
             "cycle": "年"}
        self.assertEqual(rules.refund_days(r), 14)


class TestZeroUse(unittest.TestCase):
    """issue #7:明确填 0 次被当成「未填」,砍单顺序和措辞都跟着错。"""

    BILL = "2026-11-02 酷狗音乐 15 元 连续包月\n2026-11-15 咪咕视频 30 元 连续包月"

    def test_zero_use_ranks_first(self):
        a = rules.analyze(self.BILL, {"酷狗音乐": 0, "咪咕视频": 8})
        self.assertEqual(a["cut"][0]["merchant"], "酷狗音乐")
        self.assertTrue(a["cut"][0]["zero_use"])

    def test_zero_use_is_not_none(self):
        a = rules.analyze(self.BILL, {"酷狗音乐": 0})
        row = [c for c in a["cut"] if c["merchant"] == "酷狗音乐"][0]
        self.assertEqual(row["uses"], 0)
        self.assertFalse(row["uses"] is None)

    def test_advice_says_cut_it(self):
        base = rules.analyze(self.BILL, {"酷狗音乐": 0})
        self.assertIn("直接砍", mock.advice(base)[0])
        self.assertNotIn("先补次数", mock.advice(base)[0])


if __name__ == "__main__":
    unittest.main()
