"""Standalone LLM client for the agent swarm.

Extracts the BaseLLMClient / LLMClientFactory pattern from the NLP service
so agents can call LLMs without importing the full NLP stack.
"""

import abc
import json
import os
from typing import Optional

import structlog

logger = structlog.get_logger("swarm.llm")


class BaseLLMClient(abc.ABC):
    """Abstract base for LLM providers."""

    def __init__(self, model: str, timeout: int = 60):
        self.model = model
        self.timeout = timeout

    @abc.abstractmethod
    def generate(self, prompt: str, system_prompt: str = "") -> str:
        """Send a prompt to the LLM and return the response text."""

    def generate_json(self, prompt: str, system_prompt: str = "") -> dict:
        """Generate and parse as JSON with retry on parse failure."""
        for attempt in range(3):
            raw = self.generate(prompt, system_prompt)
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                logger.warning("json_parse_failed", attempt=attempt, raw_len=len(raw))
                prompt += (
                    "\n\nERROR: Your previous output was not valid JSON. "
                    "Please output ONLY raw valid JSON with no markdown fencing."
                )
        return {}


class OpenAIClient(BaseLLMClient):
    """OpenAI GPT-4 / GPT-4o client."""

    def __init__(self, model: str, api_key: str, timeout: int = 60):
        super().__init__(model, timeout)
        from openai import OpenAI
        self.client = OpenAI(api_key=api_key)

    def generate(self, prompt: str, system_prompt: str = "") -> str:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        resp = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0.1,
            timeout=self.timeout,
        )
        return resp.choices[0].message.content or ""


class VertexAIClient(BaseLLMClient):
    """Google Gemini via Vertex AI."""

    def __init__(self, model: str, project_id: str, location: str = "us-central1", timeout: int = 60):
        super().__init__(model, timeout)
        import vertexai
        from vertexai.generative_models import GenerativeModel
        vertexai.init(project=project_id, location=location)
        self.client = GenerativeModel(model)

    def generate(self, prompt: str, system_prompt: str = "") -> str:
        full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
        resp = self.client.generate_content(
            full_prompt,
            generation_config={"temperature": 0.1},
        )
        return resp.text


class OllamaClient(BaseLLMClient):
    """Local Ollama client (no API key needed)."""

    def __init__(self, model: str, host: str = "http://localhost:11434", timeout: int = 120):
        super().__init__(model, timeout)
        self.host = host

    def generate(self, prompt: str, system_prompt: str = "") -> str:
        import requests
        full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
        resp = requests.post(
            f"{self.host}/api/generate",
            json={
                "model": self.model,
                "prompt": full_prompt,
                "stream": False,
                "options": {"temperature": 0.1},
            },
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return resp.json().get("response", "")


class MockLLMClient(BaseLLMClient):
    """Mock client for testing — returns predefined responses."""

    def __init__(self, responses: Optional[list] = None):
        super().__init__(model="mock", timeout=0)
        self._responses = responses or ['{"result": "mock response"}']
        self._call_count = 0

    def generate(self, prompt: str, system_prompt: str = "") -> str:
        idx = min(self._call_count, len(self._responses) - 1)
        self._call_count += 1
        return self._responses[idx]


class LLMClientFactory:
    """Instantiate the correct LLM provider from environment variables.

    Environment variables:
        LLM_MODEL       - Model name (default: llama3:8b)
        LLM_TIMEOUT_S   - Timeout in seconds (default: 60)
        OPENAI_API_KEY   - OpenAI API key (activates OpenAI provider)
        GOOGLE_CLOUD_PROJECT - GCP project ID (activates Vertex AI)
        OLLAMA_HOST      - Ollama endpoint (default: http://localhost:11434)
    """

    @staticmethod
    def create(model: Optional[str] = None) -> BaseLLMClient:
        model = model or os.getenv("LLM_MODEL", "llama3:8b")
        timeout = int(os.getenv("LLM_TIMEOUT_S", "60"))

        # OpenAI
        if "gpt" in model.lower() or "o1" in model.lower() or "o3" in model.lower():
            api_key = os.getenv("OPENAI_API_KEY")
            if api_key:
                logger.info("llm_client_created", provider="openai", model=model)
                return OpenAIClient(model, api_key, timeout)

        # Vertex AI / Gemini
        if "gemini" in model.lower():
            project = os.getenv("GOOGLE_CLOUD_PROJECT")
            location = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
            if project:
                logger.info("llm_client_created", provider="vertexai", model=model)
                return VertexAIClient(model, project, location, timeout)

        # Ollama fallback
        host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
        logger.info("llm_client_created", provider="ollama", model=model, host=host)
        return OllamaClient(model, host, timeout)
