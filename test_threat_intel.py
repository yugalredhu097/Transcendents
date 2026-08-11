"""
Comprehensive Test Suite for Threat Intelligence Agent (agents/threat_intel.py) - P2: Navya

Validates the 12-field contract schema, dynamic confidence scoring, Gemini AI reasoning integration (mocked),
and error recovery/fallback behavior across 8 core test scenarios:

1. Live Gemini AI reasoning with high multi-source confidence
2. Conflicting evidence handling (medium dynamic confidence)
3. No threat nearby (disruption_stage: "none")
4. Stopped truck with current disruption (disruption_stage: "current")
5. Moving truck with upcoming disruption (disruption_stage: "upcoming")
6. Gemini API failure / network timeout fallback
7. Malformed LLM JSON retry recovery
8. Web Search API failure fallback to mock_disruptions.json
"""

import json
import os
import sys
import unittest.mock as mock
from agents.threat_intel import (
    assess_threat,
    ContractValidator,
    GeminiThreatAnalyzer,
    REQUIRED_CONTRACT_KEYS,
    VALID_STAGES,
    VALID_SEVERITIES,
)


def validate_12_field_contract(result: dict) -> None:
    """Validates that output dictionary matches the exact 12-field contract schema."""
    missing = REQUIRED_CONTRACT_KEYS - set(result.keys())
    assert not missing, f"Missing required contract keys: {missing}"
    assert len(result.keys()) == 12, (
        f"Expected exactly 12 fields in contract, found {len(result.keys())}: {list(result.keys())}"
    )

    assert result["disruption_stage"] in VALID_STAGES, f"Invalid stage: {result['disruption_stage']}"
    assert result["severity"] in VALID_SEVERITIES, f"Invalid severity: {result['severity']}"
    assert isinstance(result["truck_id"], str), "truck_id must be str"
    assert isinstance(result["disruption_type"], str), "disruption_type must be str"
    assert isinstance(result["description"], str), "description must be str"
    assert isinstance(result["source"], str), "source must be str"
    assert isinstance(result["confidence"], (int, float)), "confidence must be numeric"
    assert 0.0 <= result["confidence"] <= 1.0, f"confidence must be between 0.0 and 1.0, got {result['confidence']}"
    assert isinstance(result["verified"], bool), "verified must be boolean"
    assert isinstance(result["predicted_delay_hours"], (int, float)), "predicted_delay_hours must be numeric"
    assert isinstance(result["start_time"], str), "start_time must be str"
    assert isinstance(result["expected_end_time"], str), "expected_end_time must be str"
    assert isinstance(result["affected_corridor"], str), "affected_corridor must be str"
    assert isinstance(result["severity"], str), "severity must be str"


def run_test_suite():
    print("=" * 75)
    print(" Running Production Threat Intelligence Agent Test Suite (8 Scenarios) ")
    print("=" * 75)

    # -------------------------------------------------------------
    # Scenario 1: Live Gemini AI Reasoning (High Confidence)
    # -------------------------------------------------------------
    truck_s1 = {
        "truck_id": "TRK-201",
        "status": "moving",
        "current_location": "Panvel",
        "destination": "Satara"
    }

    mock_search_evidence = [
        {
            "title": "Severe Waterlogging on NH-48",
            "snippet": "Official alert: Highway waterlogged near Khandala pass. Heavy traffic delay expected.",
            "source_url": "https://traffic.alert.gov/nh48"
        },
        {
            "title": "NH-48 Corridor Blockade",
            "snippet": "Highways authority confirms 3-hour delay near Khandala due to flooding.",
            "source_url": "https://news.express/nh48-flood"
        }
    ]

    mock_ai_json_s1 = json.dumps({
        "truck_id": "TRK-201",
        "disruption_type": "flood",
        "description": "Official confirmation of heavy waterlogging near Khandala pass on NH-48",
        "source": "https://traffic.alert.gov/nh48",
        "confidence": 0.92,
        "verified": True,
        "disruption_stage": "upcoming",
        "predicted_delay_hours": 3.0,
        "start_time": "2026-08-11T10:00:00",
        "expected_end_time": "2026-08-11T15:00:00",
        "affected_corridor": "NH-48 Khandala Section",
        "severity": "high"
    })

    with mock.patch("agents.threat_intel.EvidenceCollector.query_web_search_api", return_value=mock_search_evidence):
        with mock.patch("agents.threat_intel.GeminiThreatAnalyzer.query_gemini_api", return_value=mock_ai_json_s1):
            res_s1 = assess_threat(truck_s1, force_api_failure=False)
            validate_12_field_contract(res_s1)
            assert res_s1["confidence"] >= 0.90, f"Expected high confidence, got {res_s1['confidence']}"
            assert res_s1["disruption_stage"] == "upcoming"
            assert res_s1["severity"] == "high"
            print("\n[PASS] Scenario 1: Live Gemini AI Reasoning (High Multi-Source Confidence)")
            print(f"  Confidence: {res_s1['confidence']} | Stage: {res_s1['disruption_stage']} | Severity: {res_s1['severity']}")

    # -------------------------------------------------------------
    # Scenario 2: Conflicting Evidence Handling (Medium Dynamic Confidence)
    # -------------------------------------------------------------
    truck_s2 = {
        "truck_id": "TRK-202",
        "status": "moving",
        "current_location": "Pune",
        "destination": "Bangalore"
    }

    mock_ai_json_s2 = json.dumps({
        "truck_id": "TRK-202",
        "disruption_type": "protest",
        "description": "Unconfirmed local social media report of toll plaza demonstration",
        "source": "https://social.feed/post/102",
        "confidence": 0.45,
        "verified": False,
        "disruption_stage": "upcoming",
        "predicted_delay_hours": 1.5,
        "start_time": "2026-08-11T14:00:00",
        "expected_end_time": "2026-08-11T17:00:00",
        "affected_corridor": "NH-48 Khed Toll Plaza",
        "severity": "medium"
    })

    with mock.patch("agents.threat_intel.EvidenceCollector.query_web_search_api", return_value=mock_search_evidence):
        with mock.patch("agents.threat_intel.GeminiThreatAnalyzer.query_gemini_api", return_value=mock_ai_json_s2):
            res_s2 = assess_threat(truck_s2, force_api_failure=False)
            validate_12_field_contract(res_s2)
            assert 0.30 <= res_s2["confidence"] <= 0.60
            assert res_s2["verified"] is False
            print("\n[PASS] Scenario 2: Conflicting / Single Unverified Source Handling (Medium Confidence)")
            print(f"  Confidence: {res_s2['confidence']} | Verified: {res_s2['verified']}")

    # -------------------------------------------------------------
    # Scenario 3: No Threat Nearby -> disruption_stage: "none"
    # -------------------------------------------------------------
    truck_s3 = {
        "truck_id": "TRK-999",
        "status": "moving",
        "current_location": "Mumbai",
        "destination": "Pune"
    }

    res_s3 = assess_threat(truck_s3, force_api_failure=True)
    validate_12_field_contract(res_s3)
    assert res_s3["disruption_stage"] == "none"
    assert res_s3["severity"] == "none"
    assert res_s3["predicted_delay_hours"] == 0.0
    print("\n[PASS] Scenario 3: No Threat Nearby (disruption_stage: 'none')")
    print(f"  Stage: {res_s3['disruption_stage']} | Severity: {res_s3['severity']}")

    # -------------------------------------------------------------
    # Scenario 4: Stopped Truck with Current Disruption -> "current"
    # -------------------------------------------------------------
    truck_s4 = {
        "truck_id": "TRK-102",
        "status": "stopped",
        "current_location": "Kalyan",
        "destination": "Nashik"
    }

    res_s4 = assess_threat(truck_s4, force_api_failure=True)
    validate_12_field_contract(res_s4)
    assert res_s4["disruption_stage"] == "current"
    assert res_s4["disruption_type"] == "flood"
    assert res_s4["affected_corridor"] == "NH-60"
    print("\n[PASS] Scenario 4: Stopped Truck with Confirmed Current Issue (disruption_stage: 'current')")
    print(f"  Stage: {res_s4['disruption_stage']} | Corridor: {res_s4['affected_corridor']}")

    # -------------------------------------------------------------
    # Scenario 5: Moving Truck with Upcoming Disruption -> "upcoming"
    # -------------------------------------------------------------
    truck_s5 = {
        "truck_id": "TRK-104",
        "status": "moving",
        "current_location": "Kalyan",
        "destination": "Pune"
    }

    res_s5 = assess_threat(truck_s5, force_api_failure=True)
    validate_12_field_contract(res_s5)
    assert res_s5["disruption_stage"] == "upcoming"
    assert res_s5["disruption_type"] == "protest"
    assert res_s5["affected_corridor"] == "NH-48 Mumbai-Pune Expressway"
    print("\n[PASS] Scenario 5: Moving Truck with Threat Ahead (disruption_stage: 'upcoming')")
    print(f"  Stage: {res_s5['disruption_stage']} | Type: {res_s5['disruption_type']}")

    # -------------------------------------------------------------
    # Scenario 6: Gemini API Timeout / Network Failure Fallback
    # -------------------------------------------------------------
    truck_s6 = {
        "truck_id": "TRK-104",
        "status": "moving",
        "current_location": "Kalyan",
        "destination": "Pune"
    }

    with mock.patch("agents.threat_intel.EvidenceCollector.query_web_search_api", return_value=mock_search_evidence):
        with mock.patch("agents.threat_intel.GeminiThreatAnalyzer.query_gemini_api", side_effect=TimeoutError("Gemini API request timed out")):
            res_s6 = assess_threat(truck_s6, force_api_failure=False)
            validate_12_field_contract(res_s6)
            assert res_s6["truck_id"] == "TRK-104"
            assert res_s6["disruption_stage"] == "upcoming"
            print("\n[PASS] Scenario 6: Gemini API Timeout Fallback (Falls back gracefully to mock dataset)")
            print(f"  Fallback Stage: {res_s6['disruption_stage']} | Type: {res_s6['disruption_type']}")

    # -------------------------------------------------------------
    # Scenario 7: Malformed LLM JSON Retry Recovery
    # -------------------------------------------------------------
    truck_s7 = {
        "truck_id": "TRK-105",
        "status": "stopped",
        "current_location": "Thane",
        "destination": "Delhi"
    }

    malformed_first_response = "Here is your JSON: { truck_id: TRK-105, broken_json"
    valid_retry_response = json.dumps({
        "truck_id": "TRK-105",
        "disruption_type": "breakdown",
        "description": "Breakdown near Thane toll gate",
        "source": "telemetry",
        "confidence": 0.95,
        "verified": True,
        "disruption_stage": "current",
        "predicted_delay_hours": 3.0,
        "start_time": "2026-08-11T09:15:00",
        "expected_end_time": "2026-08-11T13:00:00",
        "affected_corridor": "NH-48 Thane Stretch",
        "severity": "medium"
    })

    side_effects = [malformed_first_response, valid_retry_response]
    with mock.patch("agents.threat_intel.EvidenceCollector.query_web_search_api", return_value=mock_search_evidence):
        with mock.patch("agents.threat_intel.GeminiThreatAnalyzer.query_gemini_api", side_effect=side_effects):
            res_s7 = assess_threat(truck_s7, force_api_failure=False)
            validate_12_field_contract(res_s7)
            assert res_s7["truck_id"] == "TRK-105"
            assert res_s7["disruption_type"] == "breakdown"
            print("\n[PASS] Scenario 7: Malformed LLM JSON Retry Recovery")
            print(f"  Recovered Stage: {res_s7['disruption_stage']} | Type: {res_s7['disruption_type']}")

    # -------------------------------------------------------------
    # Scenario 8: Web Search API Failure Fallback
    # -------------------------------------------------------------
    truck_s8 = {
        "truck_id": "TRK-105",
        "status": "stopped",
        "current_location": "Thane",
        "destination": "Delhi"
    }

    with mock.patch("agents.threat_intel.EvidenceCollector.query_web_search_api", side_effect=RuntimeError("Search API key missing")):
        res_s8 = assess_threat(truck_s8, force_api_failure=False)
        validate_12_field_contract(res_s8)
        assert res_s8["truck_id"] == "TRK-105"
        assert res_s8["disruption_stage"] == "current"
        print("\n[PASS] Scenario 8: Web Search API Failure Fallback to mock_disruptions.json")
        print(f"  Fallback Stage: {res_s8['disruption_stage']} | Type: {res_s8['disruption_type']}")

    print("\n" + "=" * 75)
    print(" ALL 8 PRODUCTION THREAT INTEL SCENARIOS PASSED SUCCESSFULLY! ")
    print("=" * 75)


if __name__ == "__main__":
    run_test_suite()
