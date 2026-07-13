import unittest
from unittest.mock import patch

import pandas as pd

from monitor import (
    NEW_YORK,
    build_ai_request,
    calculate_indicators,
    classify_signal,
    download_history,
    job,
    merge_recent_history,
)


class MonitorTest(unittest.TestCase):
    def test_indicators_cover_risk_and_trend(self):
        index = pd.bdate_range("2024-01-01", periods=300)
        data = calculate_indicators(pd.DataFrame({"Close": range(1000, 1300)}, index=index))

        self.assertEqual(len(data), 300)
        self.assertTrue(
            {"EMA50", "EMA200", "RSI14", "Volatility20_Pct", "Drawdown_Pct"}.issubset(data.columns)
        )
        self.assertAlmostEqual(data.iloc[-1]["Drawdown_Pct"], 0)

    def test_crossing_signal(self):
        previous = pd.Series({"Close": 99, "EMA50": 98, "EMA200": 100})
        current = pd.Series({"Close": 101, "EMA50": 99, "EMA200": 100})
        self.assertEqual(classify_signal(current, previous)[0], "转强")

    def test_defensive_signal(self):
        previous = pd.Series({"Close": 99, "EMA50": 98, "EMA200": 100})
        current = pd.Series({"Close": 98, "EMA50": 97, "EMA200": 100})
        self.assertEqual(classify_signal(current, previous)[0], "防御阶段")

    def test_recent_source_only_appends_after_fred(self):
        fred = pd.DataFrame(
            {"Close": [100.0, 101.0]}, index=pd.to_datetime(["2026-07-09", "2026-07-10"])
        )
        recent = pd.DataFrame(
            {"Close": [999.0, 102.0]}, index=pd.to_datetime(["2026-07-10", "2026-07-13"])
        )

        merged = merge_recent_history(fred, recent)

        self.assertEqual(merged.loc["2026-07-10", "Close"], 101.0)
        self.assertEqual(merged.loc["2026-07-13", "Close"], 102.0)

    @patch.dict(
        "os.environ",
        {"OPENAI_BASE_URL": "https://api.deepseek.com", "OPENAI_MODEL": "deepseek-v4-flash"},
    )
    def test_deepseek_uses_chat_completions(self):
        url, payload, model, provider = build_ai_request({"close": 123})

        self.assertEqual(url, "https://api.deepseek.com/chat/completions")
        self.assertEqual(model, "deepseek-v4-flash")
        self.assertEqual(provider, "DeepSeek")
        self.assertEqual(payload["messages"][1]["role"], "user")
        self.assertEqual(payload["thinking"], {"type": "enabled"})
        self.assertEqual(payload["reasoning_effort"], "high")

    @patch("monitor.download_recent_history")
    @patch("monitor.load_stored_history")
    @patch("monitor.download_fred_history", side_effect=TimeoutError("FRED timeout"))
    def test_fred_timeout_uses_stored_history(self, _fred, stored, recent):
        base = pd.DataFrame({"Close": [100.0]}, index=pd.to_datetime(["2026-07-10"]))
        stored.return_value = base
        recent.return_value = pd.DataFrame(
            {"Close": [101.0]}, index=pd.to_datetime(["2026-07-13"])
        )

        result = download_history(refresh_fred=True)

        self.assertEqual(result.iloc[-1]["Source"], "Yahoo")
        self.assertTrue(result.iloc[-1]["Is_Provisional"])

    @patch("monitor.send_email")
    @patch("monitor.download_history")
    @patch("monitor.previous_market_date")
    def test_no_new_market_day_does_not_email(self, previous, download, send_email):
        end = pd.Timestamp.now(tz=NEW_YORK).tz_localize(None).normalize()
        index = pd.bdate_range(end=end, periods=300)
        download.return_value = pd.DataFrame(
            {"Close": range(1000, 1300), "Source": "FRED", "Is_Provisional": False},
            index=index,
        )
        previous.return_value = index[-1].date()

        self.assertFalse(job())
        send_email.assert_not_called()

    @patch("monitor.send_email")
    @patch("monitor.export_data")
    @patch("monitor.request_ai_analysis", return_value=("analysis", "DeepSeek", "model"))
    @patch("monitor.build_market_context", return_value=(pd.DataFrame(), {}))
    @patch("monitor.download_history")
    @patch("monitor.previous_market_date")
    def test_force_email_sends_once(
        self, previous, download, _context, _analysis, _export, send_email
    ):
        end = pd.Timestamp.now(tz=NEW_YORK).tz_localize(None).normalize()
        index = pd.bdate_range(end=end, periods=300)
        download.return_value = pd.DataFrame(
            {"Close": range(1000, 1300), "Source": "FRED", "Is_Provisional": False},
            index=index,
        )
        previous.return_value = index[-1].date()

        self.assertTrue(job(force=True))
        send_email.assert_called_once()


if __name__ == "__main__":
    unittest.main()
