"""
Gemini Service Module
Centralized module responsible for all Google Gemini API communications.
"""

import os
import time
import logging
from typing import Optional, Any, Dict

import google.genai as genai
from google.genai import types
from google.genai.errors import APIError

logger = logging.getLogger(__name__)


class GeminiServiceError(Exception):
    """Base exception for Gemini service errors."""
    pass


class GeminiConfigError(GeminiServiceError):
    """Raised when GEMINI_API_KEY is missing or unconfigured."""
    pass


class GeminiAPIError(GeminiServiceError):
    """Raised when Gemini API request fails or returns invalid content."""
    pass


class GeminiClient:
    """
    Reusable Gemini Client wrapper.
    Handles API key verification, client initialization, retries, timeouts,
    error catching, and response validation.
    """

    def __init__(self, api_key: Optional[str] = None, timeout: float = 30.0):
        key = api_key if api_key is not None else os.getenv("GEMINI_API_KEY")
        if not key or not key.strip():
            raise GeminiConfigError(
                "GEMINI_API_KEY has not been configured. "
                "Please set your Gemini API key in the local .env file (GEMINI_API_KEY=your_key)."
            )

        self.api_key = key.strip()
        self.timeout = timeout

        try:
            http_opts = types.HttpOptions(timeout=int(self.timeout * 1000)) if hasattr(types, "HttpOptions") else None
            self._client = genai.Client(
                api_key=self.api_key,
                http_options=http_opts
            )
        except Exception as e:
            raise GeminiConfigError(f"Failed to initialize Gemini client: {e}") from e

    def generate(
        self,
        prompt: str,
        model: str = "gemini-3-flash-preview",
        system_instruction: Optional[str] = None,
        temperature: Optional[float] = None,
        max_output_tokens: Optional[int] = None,
        max_retries: int = 3,
        retry_delay: float = 2.0,
        **kwargs: Any
    ) -> str:
        """
        Public method to generate text responses from Gemini model.

        :param prompt: User query/prompt text
        :param model: Gemini model identifier (default: 'gemini-2.5-flash')
        :param system_instruction: Optional system instruction prompt
        :param temperature: Optional sampling temperature
        :param max_output_tokens: Optional maximum response tokens
        :param max_retries: Number of retries on transient API failure
        :param retry_delay: Base delay (seconds) between retries
        :return: Generated text content
        """
        if not prompt or not isinstance(prompt, str) or not prompt.strip():
            raise GeminiAPIError("Prompt must be a non-empty string.")

        config_dict = {}
        if system_instruction:
            config_dict["system_instruction"] = system_instruction
        if temperature is not None:
            config_dict["temperature"] = temperature
        if max_output_tokens is not None:
            config_dict["max_output_tokens"] = max_output_tokens

        config = types.GenerateContentConfig(**config_dict) if config_dict else None

        last_error = None
        for attempt in range(1, max_retries + 1):
            try:
                response = self._client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=config,
                )

                return self._validate_response(response)

            except GeminiAPIError:
                raise
            except APIError as e:
                last_error = e
                logger.warning(f"Gemini APIError on attempt {attempt}/{max_retries}: {e}")
            except Exception as e:
                last_error = e
                logger.warning(f"Unexpected error during Gemini call on attempt {attempt}/{max_retries}: {e}")

            if attempt < max_retries:
                sleep_time = retry_delay * (2 ** (attempt - 1))
                time.sleep(sleep_time)

        raise GeminiAPIError(
            f"Failed to generate response from Gemini after {max_retries} attempts. Last error: {last_error}"
        ) from last_error

    def _validate_response(self, response: Any) -> str:
        """Validates response object structure and returns extracted text."""
        if not response:
            raise GeminiAPIError("Gemini API returned an empty response object.")

        text = getattr(response, "text", None)
        if text is None:
            if hasattr(response, "candidates") and response.candidates:
                candidate = response.candidates[0]
                if hasattr(candidate, "finish_reason") and candidate.finish_reason:
                    logger.info(f"Gemini finish reason: {candidate.finish_reason}")
            raise GeminiAPIError("Gemini API response did not contain text output.")

        return text.strip()


_default_client: Optional[GeminiClient] = None


def get_client(api_key: Optional[str] = None, force_new: bool = False) -> GeminiClient:
    """Retrieves or creates a GeminiClient instance."""
    global _default_client
    if _default_client is None or force_new or api_key is not None:
        _default_client = GeminiClient(api_key=api_key)
    return _default_client


def generate(
    prompt: str,
    model: str = "gemini-3-flash-preview",
    system_instruction: Optional[str] = None,
    temperature: Optional[float] = None,
    max_retries: int = 3,
    api_key: Optional[str] = None,
    **kwargs: Any
) -> str:
    """
    Module-level convenience wrapper for generating content via Gemini.

    Agents and modules should call services.gemini_client.generate(prompt=...)
    rather than directly accessing the Gemini SDK.
    """
    client = get_client(api_key=api_key)
    return client.generate(
        prompt=prompt,
        model=model,
        system_instruction=system_instruction,
        temperature=temperature,
        max_retries=max_retries,
        **kwargs
    )
