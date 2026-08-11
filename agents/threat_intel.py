"""
Threat Intelligence Agent (P2 - Navya)
AI-Assisted Logistics Intelligence Analyst

Gathers external intelligence on route disruptions (floods, protests, road closures, landslides, weather alerts)
and uses Gemini AI reasoning to evaluate evidence credibility, estimate operational delays, determine severity,
and return a validated 12-field disruption contract.
"""

import json
import os
import urllib.request
import urllib.parse
from typing import Dict, Any, List, Optional

MOCK_DATA_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "mock_disruptions.json")

# Required 12-Field Contract Keys and Valid Stages
REQUIRED_CONTRACT_KEYS = {
    "truck_id",
    "disruption_type",
    "description",
    "source",
    "confidence",
    "verified",
    "disruption_stage",
    "predicted_delay_hours",
    "start_time",
    "expected_end_time",
    "affected_corridor",
    "severity",
}
VALID_STAGES = {"current", "upcoming", "none"}
VALID_SEVERITIES = {"high", "medium", "low", "critical", "none"}

# Senior Logistics Intelligence Analyst System Prompt
SYSTEM_PROMPT = """You are a Senior Logistics Intelligence Analyst for an autonomous fleet management system.
Your responsibility is to analyze raw search evidence and route telemetry to produce high-quality, verified threat intelligence.

Rules:
1. Base your evaluation strictly on the provided evidence snippets and route details. Never invent facts or hallucinate events.
2. Estimate confidence (0.0 to 1.0) based on evidence quality and source agreement:
   - 0.85 - 1.0: Multiple agreeing official/news sources or verified telemetry.
   - 0.60 - 0.84: Single credible source or slightly unverified report.
   - 0.30 - 0.59: Conflicting reports or vague social media hints.
   - 0.00 - 0.29: Speculative or unconfirmed rumor.
3. Classify disruption_stage as strictly one of: "current", "upcoming", or "none".
4. Classify severity as strictly one of: "high", "medium", "low", "critical", or "none".
5. Estimate realistic operational delay in hours (predicted_delay_hours). If no disruption, return 0.0.
6. Provide a concise, factual summary (description) under 200 characters.

You MUST return ONLY a valid JSON object with these exact 12 fields (no markdown wrapper, no extra text):
{
  "truck_id": "<string>",
  "disruption_type": "<flood|protest|roadblock|landslide|weather|breakdown|none>",
  "description": "<string>",
  "source": "<string>",
  "confidence": <float between 0.0 and 1.0>,
  "verified": <boolean>,
  "disruption_stage": "<current|upcoming|none>",
  "predicted_delay_hours": <float>,
  "start_time": "<ISO timestamp string or empty>",
  "expected_end_time": "<ISO timestamp string or empty>",
  "affected_corridor": "<string corridor or none>",
  "severity": "<high|medium|low|critical|none>"
}
"""


class EvidenceCollector:
    """Deterministic collection service for gathering multi-source route evidence."""

    @staticmethod
    def query_web_search_api(current_location: str, destination: str) -> List[Dict[str, str]]:
        """
        Queries external web search API (Tavily/SerpAPI) for logistics route disruptions.
        Returns a list of structured evidence items.
        """
        api_key = os.getenv("WEB_SEARCH_API_KEY") or os.getenv("TAVILY_API_KEY") or os.getenv("SERPAPI_API_KEY")
        if not api_key:
            raise ValueError("No Web Search API key configured in environment.")

        query = f"road disruption traffic flood protest highway closure from {current_location} to {destination}"
        url = f"https://api.tavily.com/search?q={urllib.parse.quote(query)}"

        req = urllib.request.Request(
            url,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            if response.status != 200:
                raise RuntimeError(f"Web search API returned status {response.status}")
            data = json.loads(response.read().decode("utf-8"))

        results = data.get("results", [])
        evidence_list = []
        for item in results[:5]:
            snippet = item.get("content", item.get("title", ""))
            url_link = item.get("url", "web_search_api")
            if snippet:
                evidence_list.append({
                    "title": item.get("title", "Search Hit"),
                    "snippet": snippet[:300],
                    "source_url": url_link
                })
        return evidence_list

    @staticmethod
    def load_mock_disruptions() -> Dict[str, Any]:
        """Loads fallback mock disruptions dataset from data/mock_disruptions.json."""
        if os.path.exists(MOCK_DATA_PATH):
            try:
                with open(MOCK_DATA_PATH, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}


class ContractValidator:
    """Ensures 100% backward compatibility and validates the 12-field output contract schema."""

    @staticmethod
    def validate_and_format(raw_payload: Dict[str, Any], truck_id: str) -> Dict[str, Any]:
        """Validates, type-casts, and formats raw payload into the strict 12-field contract."""
        stage = str(raw_payload.get("disruption_stage", "none")).lower()
        if stage not in VALID_STAGES:
            stage = "none"

        severity = str(raw_payload.get("severity", "none")).lower()
        if severity not in VALID_SEVERITIES:
            severity = "none" if stage == "none" else "medium"

        disruption_type = str(raw_payload.get("disruption_type", "none")).lower()
        if stage == "none":
            disruption_type = "none"
            severity = "none"

        try:
            confidence = float(raw_payload.get("confidence", 1.0 if stage == "none" else 0.8))
            confidence = max(0.0, min(1.0, confidence))
        except (ValueError, TypeError):
            confidence = 1.0 if stage == "none" else 0.8

        try:
            delay_hours = float(raw_payload.get("predicted_delay_hours", 0.0))
            delay_hours = max(0.0, delay_hours)
        except (ValueError, TypeError):
            delay_hours = 0.0

        return {
            "truck_id": str(raw_payload.get("truck_id") or truck_id),
            "disruption_type": disruption_type,
            "description": str(raw_payload.get("description", "No active or upcoming threats detected along route")),
            "source": str(raw_payload.get("source", "mock_or_url")),
            "confidence": confidence,
            "verified": bool(raw_payload.get("verified", True)),
            "disruption_stage": stage,
            "predicted_delay_hours": delay_hours,
            "start_time": str(raw_payload.get("start_time", "")),
            "expected_end_time": str(raw_payload.get("expected_end_time", "")),
            "affected_corridor": str(raw_payload.get("affected_corridor", "none")),
            "severity": severity,
        }


class GeminiThreatAnalyzer:
    """AI Reasoning Engine utilizing Gemini LLM to synthesize evidence and assess operational threat."""

    @staticmethod
    def query_gemini_api(prompt_text: str, timeout: float = 6.0) -> str:
        """
        Sends prompt to Gemini REST API endpoint.
        Supports GEMINI_API_KEY or GOOGLE_API_KEY environment variables.
        """
        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("No GEMINI_API_KEY configured in environment.")

        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": SYSTEM_PROMPT},
                        {"text": prompt_text}
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.1,
                "responseMimeType": "application/json"
            }
        }

        req_data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=req_data,
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as response:
            if response.status != 200:
                raise RuntimeError(f"Gemini API returned HTTP status {response.status}")
            res_json = json.loads(response.read().decode("utf-8"))

        try:
            return res_json["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError) as e:
            raise ValueError(f"Malformed response structure from Gemini API: {e}")

    @classmethod
    def analyze_evidence_with_ai(
        cls, truck_data: Dict[str, Any], evidence_items: List[Dict[str, str]]
    ) -> Optional[Dict[str, Any]]:
        """
        Formulates structured prompt, queries Gemini AI with retry strategy, and parses JSON output.
        """
        truck_id = truck_data.get("truck_id", "UNKNOWN")
        current_loc = truck_data.get("current_location") or truck_data.get("location", "Unknown Location")
        destination = truck_data.get("destination", "Unknown Destination")
        status = truck_data.get("status", "moving")

        user_context = {
            "truck_id": truck_id,
            "status": status,
            "current_location": current_loc,
            "destination": destination,
            "evidence_snippets": evidence_items
        }

        prompt = f"Analyze the following truck telemetry and route evidence:\n{json.dumps(user_context, indent=2)}"

        # Attempt up to 2 calls (1 primary + 1 retry on malformed JSON)
        for attempt in range(2):
            try:
                raw_response = cls.query_gemini_api(prompt)
                # Clean code blocks if present
                clean_text = raw_response.strip()
                if clean_text.startswith("```json"):
                    clean_text = clean_text[7:]
                if clean_text.startswith("```"):
                    clean_text = clean_text[3:]
                if clean_text.endswith("```"):
                    clean_text = clean_text[:-3]
                clean_text = clean_text.strip()

                parsed = json.loads(clean_text)
                if isinstance(parsed, dict):
                    return parsed
            except Exception as e:
                if attempt == 0:
                    prompt += f"\n\nERROR ON PREVIOUS RESPONSE: {str(e)}. Please output ONLY raw valid JSON matching the exact schema."
                    continue

        return None


def assess_threat(truck_data: Dict[str, Any], force_api_failure: bool = False) -> Dict[str, Any]:
    """
    Public entry point for Threat Intelligence Agent.
    Assesses threat intelligence for a truck, attempting live AI reasoning over evidence first,
    and falling back gracefully to mock_disruptions.json or safe defaults on failure.

    Guarantees strict 12-field output contract backward compatibility.
    """
    truck_id = truck_data.get("truck_id", "UNKNOWN")

    # 1. Direct disruption override in truck_data payload (used for deterministic scenario testing)
    if "disruption" in truck_data and isinstance(truck_data["disruption"], dict):
        return ContractValidator.validate_and_format(truck_data["disruption"], truck_id)

    # 2. Attempt Live Search + Gemini AI Reasoning Pipeline
    if not force_api_failure and not os.getenv("FORCE_THREAT_INTEL_API_FAILURE"):
        try:
            current_location = str(truck_data.get("current_location") or truck_data.get("location", ""))
            destination = str(truck_data.get("destination", ""))

            evidence_items = EvidenceCollector.query_web_search_api(current_location, destination)
            if evidence_items:
                ai_result = GeminiThreatAnalyzer.analyze_evidence_with_ai(truck_data, evidence_items)
                if ai_result:
                    return ContractValidator.validate_and_format(ai_result, truck_id)
        except Exception:
            # Fallback path: Web Search API key missing/failed OR Gemini API key missing/failed
            pass

    # 3. Deterministic Fallback: Load scenario record from data/mock_disruptions.json
    mock_disruptions = EvidenceCollector.load_mock_disruptions()
    if truck_id in mock_disruptions:
        mock_payload = mock_disruptions[truck_id]
        return ContractValidator.validate_and_format(mock_payload, truck_id)

    # 4. Default Safe Fallback: No disruption detected
    default_payload = {
        "truck_id": truck_id,
        "disruption_type": "none",
        "description": "No active or upcoming threats detected along route",
        "source": "mock_or_url",
        "confidence": 1.0,
        "verified": True,
        "disruption_stage": "none",
        "predicted_delay_hours": 0.0,
        "start_time": "",
        "expected_end_time": "",
        "affected_corridor": "none",
        "severity": "none"
    }
    return ContractValidator.validate_and_format(default_payload, truck_id)
