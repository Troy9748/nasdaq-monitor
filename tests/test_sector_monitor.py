import os
import unittest

import pandas as pd

from sector_monitor import build_ai_request, build_summary, make_analysis_bundle, prepare_frame


class SectorMonitorTest(unittest.TestCase):
    def test_indicators_and_summary_are_continuous(self):
        dates = pd.bdate_range("2023-01-02", periods=260)
        frame = pd.DataFrame(
            {
                "High": range(1010, 1270),
                "Low": range(990, 1250),
                "Close": range(1000, 1260),
                "Amount": [1_000_000_000] * 260,
            },
            index=dates,
        )
        summary = build_summary(prepare_frame(frame))
        self.assertAlmostEqual(summary["amount_ratio20"], 1)
        self.assertAlmostEqual(summary["estimated_inflow_billion"], 0.5)
        self.assertAlmostEqual(summary["estimated_outflow_billion"], 0.5)
        self.assertAlmostEqual(summary["money_flow_ratio_pct"], 0)
        self.assertAlmostEqual(summary["estimated_net_flow_5_billion"], 0)
        self.assertAlmostEqual(summary["estimated_net_flow_20_billion"], 0)
        self.assertAlmostEqual(summary["flow_confidence_pct"], 100)
        self.assertGreater(summary["ema20"], summary["ema50"])
        self.assertEqual(summary["trend"], "多头排列")

    def test_deepseek_request_enables_thinking(self):
        old = os.environ.pop("OPENAI_BASE_URL", None)
        try:
            _, payload, _, provider = build_ai_request({})
        finally:
            if old is not None:
                os.environ["OPENAI_BASE_URL"] = old
        self.assertEqual(provider, "DeepSeek")
        self.assertEqual(payload["thinking"], {"type": "enabled"})
        self.assertEqual(payload["reasoning_effort"], "high")
        self.assertGreaterEqual(payload["max_tokens"], 6000)
        self.assertEqual(payload["response_format"], {"type": "json_object"})
        self.assertIn("严禁称为主力资金", payload["messages"][0]["content"])

    def test_ai_evidence_uses_backend_value(self):
        sections = {key: "审慎观察。" for key in ("today", "rotation", "confirmation", "risks", "next")}
        bundle = make_analysis_bundle(
            sections,
            [{"code": "931743", "metric": "daily_return_pct"}, {"code": "bad", "metric": "trend"}],
            {"931743": {"daily_return_pct": 1.23}},
        )
        self.assertEqual(bundle["evidence"][0]["value"], 1.23)
        self.assertEqual(len(bundle["evidence"]), 1)
        with self.assertRaises(ValueError):
            make_analysis_bundle({**sections, "today": "上涨1%。"}, [], {})


if __name__ == "__main__":
    unittest.main()
