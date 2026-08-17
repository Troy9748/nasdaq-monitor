import json
import unittest
from unittest.mock import patch

import pandas as pd

from monitor import (
    NEW_YORK,
    annotate_context_freshness,
    build_alert,
    build_ai_request,
    build_calibration_audit,
    build_regime_analysis,
    calculate_asof_robust_log_trend,
    calculate_risk_dashboard,
    calculate_stress_scenarios,
    calculate_walk_forward_validation,
    calculate_indicators,
    calculate_robust_log_trend,
    classify_signal,
    download_history,
    job,
    merge_recent_history,
    parse_and_validate_ai_analysis,
)


class MonitorTest(unittest.TestCase):
    def test_professional_risk_and_walk_forward_outputs(self):
        index = pd.bdate_range("1999-01-01", periods=1800)
        close = pd.Series(1000 * (1.0004 ** pd.RangeIndex(len(index))), index=index)
        close.iloc[900:980] *= 0.7
        data = calculate_indicators(pd.DataFrame({"Close": close}, index=index))

        risk = calculate_risk_dashboard(data)
        validation = calculate_walk_forward_validation(data)

        self.assertGreaterEqual(risk["historical_var95_1d_pct"], 0)
        self.assertGreaterEqual(risk["expected_shortfall95_1d_pct"], risk["historical_var95_1d_pct"])
        self.assertFalse(validation["uses_future_data"])
        self.assertEqual(validation["transaction_cost_bps"], 10)
        self.assertIn("max_drawdown_pct", validation["strategy"])

    def test_stress_scenarios_are_point_in_time(self):
        index = pd.bdate_range("1999-01-01", "2023-12-31")
        close = pd.Series(1000.0, index=index)
        close.loc["2000-03-10":"2002-10-09"] = range(1000, 1000 - len(close.loc["2000-03-10":"2002-10-09"]), -1)
        close.loc["2002-10-10":] = 1100

        scenarios = calculate_stress_scenarios(close)

        self.assertEqual(scenarios[0]["name"], "科技泡沫")
        self.assertLess(scenarios[0]["peak_to_trough_pct"], 0)
    def test_indicators_cover_risk_and_trend(self):
        index = pd.bdate_range("2024-01-01", periods=300)
        data = calculate_indicators(pd.DataFrame({"Close": range(1000, 1300)}, index=index))

        self.assertEqual(len(data), 300)
        self.assertTrue(
            {
                "EMA20", "EMA50", "EMA200", "SMA200", "Bollinger_Upper",
                "Bollinger_Lower", "MACD", "MACD_Signal", "MACD_Histogram",
                "ROC20_Pct", "RSI14", "Volatility20_Pct", "Drawdown_Pct",
                "Robust_Log_Trend",
            }.issubset(data.columns)
        )
        self.assertAlmostEqual(data.iloc[-1]["Drawdown_Pct"], 0)
        self.assertAlmostEqual(
            data.iloc[-1]["MACD"] - data.iloc[-1]["MACD_Signal"],
            data.iloc[-1]["MACD_Histogram"],
        )
        self.assertAlmostEqual(
            data.iloc[-1]["ROC20_Pct"],
            (1299 / 1279 - 1) * 100,
            places=4,
        )
        self.assertIn("annualized_growth_pct", data.attrs["robust_log_trend"])

    def test_robust_log_trend_limits_extreme_price_shock(self):
        index = pd.bdate_range("2000-01-03", periods=5200)
        years = (index - index[0]).days / 365.25
        close = pd.Series(100 * (1.08 ** years), index=index)
        close.iloc[2600:2660] *= 20

        trend, summary = calculate_robust_log_trend(close)

        self.assertAlmostEqual(summary["annualized_growth_pct"], 8, delta=0.15)
        self.assertAlmostEqual(trend.iloc[-1]["Robust_Log_Deviation_Pct"], 0, delta=0.5)
        self.assertGreater(summary["downweighted_pct"], 0)
        self.assertAlmostEqual(summary["central_coverage_pct"], 80, delta=0.2)
        self.assertTrue(0 < summary["deviation_percentile"] <= 100)

    def test_asof_trend_does_not_change_when_future_data_is_appended(self):
        index = pd.bdate_range("2000-01-03", periods=800)
        years = (index - index[0]).days / 365.25
        close = pd.Series(100 * (1.08 ** years), index=index)

        prefix, _ = calculate_asof_robust_log_trend(close.iloc[:600], min_observations=200)
        extended = pd.concat([close.iloc[:600], close.iloc[600:] * 8])
        full, _ = calculate_asof_robust_log_trend(extended, min_observations=200)

        pd.testing.assert_series_equal(
            prefix["AsOf_Robust_Log_Trend"],
            full.loc[prefix.index, "AsOf_Robust_Log_Trend"],
        )

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
        self.assertEqual(payload["response_format"], {"type": "json_object"})

    def test_structured_ai_analysis_validates_fact_values(self):
        snapshot = {
            "close": 123.45,
            "daily_return_pct": 1.2,
            "ema200": 110.0,
            "robust_log_trend": {"deviation_pct": 8.0, "deviation_percentile": 72.0},
        }
        raw = json.dumps(
            {
                "market_state": "趋势保持，但仍需观察数据口径。",
                "momentum_trend": "动量偏强，结论来自已提供指标。",
                "risks": "临时数据可能校准，避免外推。",
                "next_session_watch": "观察趋势与风险条件是否同步变化。",
                "facts": [
                    {"metric": "close", "value": 123.45},
                    {"metric": "daily_return_pct", "value": 1.2},
                    {"metric": "ema200", "value": 110.0},
                ],
            },
            ensure_ascii=False,
        )

        text = parse_and_validate_ai_analysis(raw, snapshot)

        self.assertIn("事实校验：已核对 3 项", text)

    def test_structured_ai_analysis_rejects_changed_fact(self):
        snapshot = {"close": 123.45, "daily_return_pct": 1.2, "ema200": 110.0}
        raw = json.dumps(
            {
                "market_state": "状态。",
                "momentum_trend": "趋势。",
                "risks": "风险。",
                "next_session_watch": "观察。",
                "facts": [
                    {"metric": "close", "value": 999},
                    {"metric": "daily_return_pct", "value": 1.2},
                    {"metric": "ema200", "value": 110.0},
                ],
            },
            ensure_ascii=False,
        )

        with self.assertRaisesRegex(ValueError, "数值不一致"):
            parse_and_validate_ai_analysis(raw, snapshot)

    def test_fred_calibration_audits_provisional_rows(self):
        index = pd.to_datetime(["2026-07-10", "2026-07-13"])
        stored = pd.DataFrame(
            {"Close": [100.0, 102.0], "Is_Provisional": [False, True]}, index=index
        )
        fred = pd.DataFrame({"Close": [101.9]}, index=index[-1:])

        audit = build_calibration_audit(stored, fred)

        self.assertEqual(audit["corrected_rows"], 1)
        self.assertEqual(audit["max_diff_date"], "2026-07-13")
        self.assertGreater(audit["max_abs_diff_pct"], 0)

    def test_regime_analysis_has_forward_samples_without_warmup_rows(self):
        index = pd.bdate_range("2024-01-01", periods=400)
        data = calculate_indicators(pd.DataFrame({"Close": range(1000, 1400)}, index=index))

        analysis = build_regime_analysis(data)

        self.assertEqual(analysis["current"], "多头")
        self.assertGreater(analysis["stats"]["多头"]["forward"]["60日"]["samples"], 0)
        self.assertLess(
            analysis["stats"]["多头"]["forward"]["60日"]["samples"],
            analysis["stats"]["多头"]["forward"]["60日"]["overlapping_samples"],
        )
        self.assertIn("median_ci95_low_pct", analysis["stats"]["多头"]["forward"]["60日"])
        self.assertIn("高波动", analysis["environment_stats"])
        self.assertEqual(
            sum(value["observations"] for value in analysis["stats"].values()), 201
        )

    def test_context_freshness_and_alert_level(self):
        context = annotate_context_freshness(
            {
                "vxn": {"value": 35.0, "as_of": "2026-07-10", "source": "FRED"},
                "breadth": {"above_ema200_pct": 32.0, "as_of": "2026-07-13"},
            },
            pd.Timestamp("2026-07-14").date(),
        )
        alert = build_alert(
            {
                "freshness": {"status": "正常"},
                "status": "多头趋势",
                "status_detail": "趋势延续",
                "volatility20_pct": 20.0,
                "context": context,
            }
        )

        self.assertEqual(context["vxn"]["freshness"], "延迟")
        self.assertEqual(alert["level"], "注意")
        self.assertEqual(len(alert["reasons"]), 2)

    @patch.dict("os.environ", {"ALERT_CALIBRATION_DIFF_PCT": "0.5"})
    def test_calibration_difference_triggers_alert(self):
        alert = build_alert(
            {
                "freshness": {"status": "正常"},
                "status": "多头趋势",
                "status_detail": "趋势延续",
                "volatility20_pct": 20.0,
                "distance_ema200_pct": 5.0,
                "context": {"calibration": {"max_abs_diff_pct": 0.8}},
            }
        )

        self.assertEqual(alert["level"], "注意")
        self.assertIn("Yahoo/FRED 校准差异", alert["reasons"][0])

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

    @patch("monitor.download_history")
    @patch("monitor.previous_market_date")
    @patch("monitor.last_scheduled_email_date")
    def test_scheduled_run_fails_when_cached_market_date_is_severely_stale(
        self, last_email, previous, download
    ):
        end = (pd.Timestamp.now(tz=NEW_YORK) - pd.Timedelta(days=6)).tz_localize(None).normalize()
        index = pd.bdate_range(end=end, periods=300)
        download.return_value = pd.DataFrame(
            {"Close": range(1000, 1300), "Source": "FRED", "Is_Provisional": False},
            index=index,
        )
        previous.return_value = index[-1].date()
        last_email.return_value = index[-1].date().isoformat()

        with self.assertRaisesRegex(RuntimeError, "连续未取得新行情"):
            job(scheduled_email=True)

    @patch("monitor.write_health")
    @patch("monitor.send_email")
    @patch("monitor.export_data")
    @patch("monitor.request_ai_analysis", return_value=("analysis", "DeepSeek", "model"))
    @patch("monitor.build_market_context", return_value=(pd.DataFrame(), {}))
    @patch("monitor.download_history")
    @patch("monitor.previous_market_date")
    def test_force_email_sends_once(
        self, previous, download, _context, _analysis, _export, send_email, _health
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

    @patch("monitor.record_scheduled_email")
    @patch("monitor.write_health")
    @patch("monitor.send_email")
    @patch("monitor.export_data")
    @patch("monitor.request_ai_analysis", return_value=("analysis", "DeepSeek", "model"))
    @patch("monitor.build_market_context", return_value=(pd.DataFrame(), {}))
    @patch("monitor.download_history")
    @patch("monitor.previous_market_date")
    @patch("monitor.last_scheduled_email_date", return_value=None)
    def test_scheduled_email_sends_when_data_was_already_written(
        self, _last_email, previous, download, _context, _analysis, _export,
        send_email, _health, record_email
    ):
        end = pd.Timestamp.now(tz=NEW_YORK).tz_localize(None).normalize()
        index = pd.bdate_range(end=end, periods=300)
        download.return_value = pd.DataFrame(
            {"Close": range(1000, 1300), "Source": "FRED", "Is_Provisional": False},
            index=index,
        )
        previous.return_value = index[-1].date()

        self.assertTrue(job(scheduled_email=True))
        send_email.assert_called_once()
        record_email.assert_called_once_with(index[-1].date().isoformat())


if __name__ == "__main__":
    unittest.main()
