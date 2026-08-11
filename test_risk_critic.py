"""
Comprehensive Test Suite for Risk Critic Agent (Agent 4 - AI Risk Auditor)
"""

import json
import unittest
from typing import Dict, Any
from agents.risk_critic import (
    evaluate_risk,
    RiskCriticService,
    LLMClient,
    JSONValidator,
    DeterministicEvaluator,
    PromptBuilder
)


class TestRiskCritic(unittest.TestCase):

    def setUp(self):
        self.standard_plan = {
            "truck_id": "TRK-104",
            "recommended_action": "reroute",
            "reasoning": "Protest expected in ~2 hours on current route; alternate adds 1.5h, still within deadline",
            "estimated_delay_hours": 1.5,
            "estimated_cost": 850,
            "alternative_route": {"distance_km": 62, "duration_min": 95}
        }

    def test_1_planner_accepted_via_mocked_llm(self):
        """Test Case 1: Gemini Auditor accepts plan with detailed reasoning."""
        mock_response = json.dumps({
            "truck_id": "TRK-104",
            "decision": "ACCEPT",
            "reasoning": "Auditor Analysis: The proposed 1.5h detour is operationally sound and protects perishable produce.",
            "risk_factors": {
                "shelf_life_ok": True,
                "cost_ok": True,
                "eta_ok": True,
                "safety_ok": True
            }
        })
        llm = LLMClient(mock_handler=lambda sys, user: mock_response)
        service = RiskCriticService(llm_client=llm)
        out = service.evaluate(self.standard_plan)

        self.assertEqual(out["truck_id"], "TRK-104")
        self.assertEqual(out["decision"], "ACCEPT")
        self.assertIn("Auditor Analysis", out["reasoning"])
        self.assertTrue(out["risk_factors"]["shelf_life_ok"])

    def test_2_planner_rejected_via_mocked_llm(self):
        """Test Case 2: Gemini Auditor challenges planner and rejects recommendation."""
        mock_response = json.dumps({
            "truck_id": "TRK-104",
            "decision": "REJECT",
            "reasoning": "Auditor Reject: Planner recommends waiting for 6h, but remaining safe shelf-life is only 3h.",
            "risk_factors": {
                "shelf_life_ok": False,
                "cost_ok": True,
                "eta_ok": False,
                "safety_ok": True
            }
        })
        llm = LLMClient(mock_handler=lambda sys, user: mock_response)
        service = RiskCriticService(llm_client=llm)
        out = service.evaluate(self.standard_plan)

        self.assertEqual(out["decision"], "REJECT")
        self.assertFalse(out["risk_factors"]["shelf_life_ok"])
        self.assertIn("Auditor Reject", out["reasoning"])

    def test_3_malformed_json_with_retry_recovery(self):
        """Test Case 3: Malformed response on attempt 1, clean JSON recovery on attempt 2."""
        attempts = 0

        def mock_retry_handler(sys_prompt, user_prompt):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                return "INVALID JSON TEXT WITHOUT SCHEMA"
            return json.dumps({
                "truck_id": "TRK-104",
                "decision": "ACCEPT",
                "reasoning": "Recovered via 1-shot retry prompt.",
                "risk_factors": {
                    "shelf_life_ok": True,
                    "cost_ok": True,
                    "eta_ok": True,
                    "safety_ok": True
                }
            })

        llm = LLMClient(mock_handler=mock_retry_handler)
        service = RiskCriticService(llm_client=llm)
        out = service.evaluate(self.standard_plan)

        self.assertEqual(attempts, 2)
        self.assertEqual(out["decision"], "ACCEPT")
        self.assertIn("Recovered via 1-shot retry", out["reasoning"])

    def test_4_gemini_timeout_and_fallback(self):
        """Test Case 4: LLM failure/timeout triggers safe deterministic fallback."""
        llm = LLMClient(mock_handler=lambda sys, user: None)
        service = RiskCriticService(llm_client=llm)
        out = service.evaluate(self.standard_plan)

        # Baseline plan delay 1.5h <= 6h shelf life & cost 850 <= 5000 -> ACCEPT
        self.assertEqual(out["truck_id"], "TRK-104")
        self.assertEqual(out["decision"], "ACCEPT")
        self.assertTrue(out["risk_factors"]["shelf_life_ok"])

    def test_5_high_risk_vs_low_risk_cargo(self):
        """Test Case 5: High cost plan rejection on cost constraint."""
        high_cost_plan = dict(self.standard_plan)
        high_cost_plan["estimated_cost"] = 8500.0  # Exceeds 5000 budget

        llm = LLMClient(mock_handler=lambda sys, user: None)
        service = RiskCriticService(llm_client=llm)
        out = service.evaluate(high_cost_plan)

        self.assertEqual(out["decision"], "REJECT")
        self.assertFalse(out["risk_factors"]["cost_ok"])

    def test_6_excessive_delay_rejection(self):
        """Test Case 6: Excessive delay plan rejection on shelf-life and ETA."""
        excessive_delay_plan = dict(self.standard_plan)
        excessive_delay_plan["estimated_delay_hours"] = 14.0

        llm = LLMClient(mock_handler=lambda sys, user: None)
        service = RiskCriticService(llm_client=llm)
        out = service.evaluate(excessive_delay_plan)

        self.assertEqual(out["decision"], "REJECT")
        self.assertFalse(out["risk_factors"]["shelf_life_ok"])
        self.assertFalse(out["risk_factors"]["eta_ok"])

    def test_7_safety_concern_rejection(self):
        """Test Case 7: Unsafe action recommended by planner."""
        unsafe_plan = dict(self.standard_plan)
        unsafe_plan["recommended_action"] = "drive_through_flood"

        llm = LLMClient(mock_handler=lambda sys, user: None)
        service = RiskCriticService(llm_client=llm)
        out = service.evaluate(unsafe_plan)

        self.assertEqual(out["decision"], "REJECT")
        self.assertFalse(out["risk_factors"]["safety_ok"])

    def test_8_contract_and_schema_validation(self):
        """Test Case 8: Strict Contract 5 field validation."""
        valid_raw = json.dumps({
            "truck_id": "TRK-999",
            "decision": "ACCEPT",
            "reasoning": "Valid reasoning",
            "risk_factors": {
                "shelf_life_ok": True,
                "cost_ok": True,
                "eta_ok": True,
                "safety_ok": True
            }
        })
        validated = JSONValidator.validate(valid_raw, "TRK-999")
        self.assertIsNotNone(validated)
        self.assertEqual(validated["truck_id"], "TRK-999")

        invalid_raw = '{"truck_id": "TRK-999", "decision": "MAYBE"}'
        self.assertIsNone(JSONValidator.validate(invalid_raw))


def run_tests():
    print("--- Running Risk Critic Agent Tests ---")
    suite = unittest.TestLoader().loadTestsFromTestCase(TestRiskCritic)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    if not result.wasSuccessful():
        raise RuntimeError("Risk Critic tests failed!")
    print("All Risk Critic Agent tests passed successfully!\n")


if __name__ == "__main__":
    run_tests()

