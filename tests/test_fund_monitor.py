import unittest

from fund_monitor import FUND_SECTORS, enrich_series, max_drawdown, parse_json_object, period_return, supported_stock_history_market


class FundMonitorTest(unittest.TestCase):
    def test_all_user_funds_have_a_sector(self):
        self.assertEqual(len(FUND_SECTORS), 29)
        self.assertEqual(len(set(FUND_SECTORS)), 29)

    def test_nav_metrics_are_continuous(self):
        series = enrich_series([{"date": f"2026-01-{day:02d}", "value": 100 + day} for day in range(1, 29)])
        self.assertIsNotNone(series[-1]["ma20"])
        self.assertGreater(period_return(series, 5), 0)
        self.assertEqual(max_drawdown(series), 0)

    def test_unqualified_foreign_stock_history_is_cache_only(self):
        self.assertFalse(supported_stock_history_market("000660"))
        self.assertFalse(supported_stock_history_market("005930"))
        self.assertTrue(supported_stock_history_market("105.NVDA"))
        self.assertTrue(supported_stock_history_market("116.09899"))

    def test_parse_json_object_tolerates_wrapped_json(self):
        self.assertEqual(parse_json_object("```json\n{\"ok\": true}\n```")["ok"], True)
        self.assertEqual(parse_json_object("说明：\n{\"ok\": true}\n结束")["ok"], True)


if __name__ == "__main__":
    unittest.main()
