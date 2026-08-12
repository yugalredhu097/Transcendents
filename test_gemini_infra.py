"""
Infrastructure Test Script for Gemini Service
Verifies .env loading, Gemini client initialization, prompt generation, and graceful error handling.
"""

import os
import sys

# Ensure UTF-8 output encoding for Windows terminal printing
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

from dotenv import load_dotenv
from services.gemini_client import GeminiClient, generate, GeminiConfigError, GeminiAPIError

def test_infrastructure():
    print("--- 1. Testing .env Loading ---")
    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY")
    assert api_key is not None, "GEMINI_API_KEY environment variable is missing"
    assert len(api_key.strip()) > 0, "GEMINI_API_KEY is empty"
    print(f"[OK] .env loaded successfully (API key length: {len(api_key.strip())})")

    print("\n--- 2. Testing Gemini Client Initialization ---")
    client = GeminiClient()
    assert client is not None, "Failed to instantiate GeminiClient"
    print("[OK] GeminiClient initialized successfully")

    print("\n--- 3. Testing Simple Gemini Generation Prompt ---")
    test_prompt = "Hello! Please reply with 'Gemini infrastructure verified successfully.'"
    response_text = generate(prompt=test_prompt)
    assert response_text is not None and len(response_text) > 0, "Received empty response"
    print(f"[OK] Response received from Gemini:\n{response_text}")

    print("\n--- 4. Testing Graceful Error Handling (Missing API Key) ---")
    try:
        invalid_client = GeminiClient(api_key="")
        assert False, "Expected GeminiConfigError when API key is empty"
    except GeminiConfigError as e:
        print(f"[OK] Caught expected GeminiConfigError: {e}")

    print("\n==========================================")
    print("ALL GEMINI INFRASTRUCTURE VERIFICATIONS PASSED!")
    print("==========================================")

if __name__ == "__main__":
    test_infrastructure()
