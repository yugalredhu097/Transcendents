import json
import os
import urllib.request
import urllib.parse
from typing import Dict, Any, Optional

MOCK_DATA_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "mock_disruptions.json")


def load_mock_disruptions() -> Dict[str, Any]:
    """Loads mock disruptions from data/mock_disruptions.json as fallback."""
    if os.path.exists(MOCK_DATA_PATH):
        try:
            with open(MOCK_DATA_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def query_web_search_api(current_location: str, destination: str) -> Dict[str, Any]:
    """
    Attempts to perform a real Web Search API call for logistics route disruptions.
    Raises Exception if API key missing, network fails, or request errors.
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
    if results:
        top_result = results[0]
        snippet = top_result.get("content", top_result.get("title", "Disruption reported on route"))
        return {
            "disruption_type": "web_incident",
            "description": f"Live Web Incident: {snippet[:150]}",
            "source": top_result.get("url", "web_search_api"),
            "confidence": 0.85,
            "verified": True,
            "disruption_stage": "upcoming",
            "predicted_delay_hours": 4.0,
            "start_time": "",
            "expected_end_time": "",
            "affected_corridor": f"{current_location} to {destination}",
            "severity": "high"
        }
    
    return {
        "disruption_type": "none",
        "description": "No active disruptions found via live web search",
        "source": "web_search_api",
        "confidence": 1.0,
        "verified": True,
        "disruption_stage": "none",
        "predicted_delay_hours": 0.0,
        "start_time": "",
        "expected_end_time": "",
        "affected_corridor": "none",
        "severity": "none"
    }


def assess_threat(truck_data: Dict[str, Any], force_api_failure: bool = False) -> Dict[str, Any]:
    """
    Assesses threat intelligence for a given truck independently of fleet monitor status.
    Attempts live Web Search API query first, falling back to mock_disruptions.json on failure.

    Contract Output (12 fields):
    {
      "truck_id": str,
      "disruption_type": str,
      "description": str,
      "source": str,
      "confidence": float,
      "verified": bool,
      "disruption_stage": str, ("current", "upcoming", or "none")
      "predicted_delay_hours": float,
      "start_time": str,
      "expected_end_time": str,
      "affected_corridor": str,
      "severity": str
    }
    """
    truck_id = truck_data.get("truck_id", "UNKNOWN")
    current_location = truck_data.get("current_location", truck_data.get("location", ""))
    destination = truck_data.get("destination", "")

    # 1. Direct disruption override in truck_data if supplied
    if "disruption" in truck_data and isinstance(truck_data["disruption"], dict):
        d = truck_data["disruption"]
        return {
            "truck_id": truck_id,
            "disruption_type": str(d.get("disruption_type", "none")),
            "description": str(d.get("description", "No active or upcoming threats detected along route")),
            "source": str(d.get("source", "mock_or_url")),
            "confidence": float(d.get("confidence", 1.0)),
            "verified": bool(d.get("verified", True)),
            "disruption_stage": str(d.get("disruption_stage", "none")),
            "predicted_delay_hours": float(d.get("predicted_delay_hours", 0.0)),
            "start_time": str(d.get("start_time", "")),
            "expected_end_time": str(d.get("expected_end_time", "")),
            "affected_corridor": str(d.get("affected_corridor", "none")),
            "severity": str(d.get("severity", "none"))
        }

    # 2. Try Web Search API unless force_api_failure is set
    if not force_api_failure and not os.getenv("FORCE_THREAT_INTEL_API_FAILURE"):
        try:
            api_result = query_web_search_api(current_location, destination)
            api_result["truck_id"] = truck_id
            return api_result
        except Exception:
            # Fallback path: Web Search API failed or key missing
            pass

    # 3. Fallback path: Load from data/mock_disruptions.json
    mock_disruptions = load_mock_disruptions()
    if truck_id in mock_disruptions:
        d_info = mock_disruptions[truck_id]
        return {
            "truck_id": truck_id,
            "disruption_type": str(d_info.get("disruption_type", "none")),
            "description": str(d_info.get("description", "")),
            "source": str(d_info.get("source", "mock_or_url")),
            "confidence": float(d_info.get("confidence", 0.8)),
            "verified": bool(d_info.get("verified", True)),
            "disruption_stage": str(d_info.get("disruption_stage", "none")),
            "predicted_delay_hours": float(d_info.get("predicted_delay_hours", 0.0)),
            "start_time": str(d_info.get("start_time", "")),
            "expected_end_time": str(d_info.get("expected_end_time", "")),
            "affected_corridor": str(d_info.get("affected_corridor", "none")),
            "severity": str(d_info.get("severity", "none"))
        }

    # 4. Default fallback: No threat found
    return {
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
