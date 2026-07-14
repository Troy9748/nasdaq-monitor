import unittest

from fund_monitor import FUND_SECTORS, SKIP_LIVE_STOCK_HISTORY, analyze_stocks, enrich_series, keyed_analysis_items, max_drawdown, normalize_sections, parse_json_object, period_return, supported_stock_history_market, yahoo_ticker


class FundMonitorTest(unittest.TestCase):
    def test_all_user_funds_have_a_sector(self):
        self.assertEqual(len(FUND_SECTORS), 29)
        self.assertEqual(len(set(FUND_SECTORS)), 29)

    def test_nav_metrics_are_continuous(self):
        series = enrich_series([{"date": f"2026-01-{day:02d}", "value": 100 + day} for day in range(1, 29)])
        self.assertIsNotNone(series[-1]["ma20"])
        self.assertGreater(period_return(series, 5), 0)
        self.assertEqual(max_drawdown(series), 0)

    def test_supported_foreign_stock_history_markets(self):
        self.assertTrue(supported_stock_history_market("000660"))
        self.assertTrue(supported_stock_history_market("005930"))
        self.assertTrue(supported_stock_history_market("105.NVDA"))
        self.assertTrue(supported_stock_history_market("106.BRK_B"))
        self.assertTrue(supported_stock_history_market("116.09899"))

    def test_yahoo_ticker_maps_foreign_holdings(self):
        self.assertEqual(yahoo_ticker("000660", "000660"), "000660.KS")
        self.assertEqual(yahoo_ticker("005930", "005930"), "005930.KS")
        self.assertEqual(yahoo_ticker("106.BRK_B", "BRK_B"), "BRK-B")

    def test_rate_limited_holdings_are_cache_only(self):
        self.assertEqual(SKIP_LIVE_STOCK_HISTORY, {"106.BRK_B", "000660", "005930"})

    def test_parse_json_object_tolerates_wrapped_json(self):
        self.assertEqual(parse_json_object("```json\n{\"ok\": true}\n```")["ok"], True)
        self.assertEqual(parse_json_object("说明：\n{\"ok\": true}\n结束")["ok"], True)

    def test_keyed_analysis_items_accepts_dict_or_list(self):
        self.assertEqual(dict(keyed_analysis_items({"001": {"ok": True}}, "code"))["001"]["ok"], True)
        self.assertEqual(dict(keyed_analysis_items([{"code": "001", "ok": True}, []], "code"))["001"]["ok"], True)

    def test_normalize_sections_accepts_lists(self):
        sections = normalize_sections(["a", {"text": "b"}], ("first", "second"))
        self.assertEqual(sections, {"first": "a", "second": "b"})

    def test_stock_deepseek_analysis_is_off_by_default(self):
        analysis = analyze_stocks([{"stock_id": "x", "name": "X", "news": [], "summary": {}, "financial": None}])
        self.assertEqual(analysis["x"]["source"], "规则分析")


if __name__ == "__main__":
    unittest.main()
