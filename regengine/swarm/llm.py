"""Standalone LLM client for the agent swarm.

Extracts the BaseLLMClient / LLMClientFactory pattern from the NLP service
so agents can call LLMs without importing the full NLP stack.
"""

import abc
import json
import os
from typing import Optional

import httpx
import structlog

from regengine.swarm.sse import collect_openai_stream_text

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
        self.api_key = api_key
        self.client = OpenAI(api_key=api_key)

    def _extract_responses_text(self, payload: dict) -> str:
        output = payload.get("output", [])
        if not isinstance(output, list):
            return ""

        text_parts = []
        for item in output:
            if not isinstance(item, dict):
                continue
            content = item.get("content", [])
            if not isinstance(content, list):
                continue
            for block in content:
                if isinstance(block, dict):
                    text_value = block.get("text")
                    if isinstance(text_value, str):
                        text_parts.append(text_value)
        return "".join(text_parts)

    def _generate_via_responses_stream(self, prompt: str, system_prompt: str = "") -> str:
        payload = {
            "model": self.model,
            "input": prompt,
            "stream": True,
            "temperature": 0.1,
        }
        if system_prompt:
            payload["instructions"] = system_prompt

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        with httpx.stream(
            "POST",
            "https://api.openai.com/v1/responses",
            headers=headers,
            json=payload,
            timeout=self.timeout,
        ) as response:
            response.raise_for_status()

            def chunk_iter():
                for chunk in response.iter_text():
                    if chunk:
                        yield chunk

            streamed_text = collect_openai_stream_text(chunk_iter())
            if streamed_text:
                return streamed_text

        fallback_payload = {
            "model": self.model,
            "input": prompt,
            "stream": False,
            "temperature": 0.1,
        }
        if system_prompt:
            fallback_payload["instructions"] = system_prompt

        fallback_response = httpx.post(
            "https://api.openai.com/v1/responses",
            headers=headers,
            json=fallback_payload,
            timeout=self.timeout,
        )
        fallback_response.raise_for_status()
        parsed = fallback_response.json()
        return self._extract_responses_text(parsed)

    def _generate_via_chat_completions(self, prompt: str, system_prompt: str = "") -> str:
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

    def generate(self, prompt: str, system_prompt: str = "") -> str:
        force_responses = os.getenv("OPENAI_USE_RESPONSES_API", "").lower() in {"1", "true", "yes"}
        prefers_responses = "codex" in self.model.lower() or self.model.lower().startswith("gpt-5")

        if force_responses or prefers_responses:
            try:
                return self._generate_via_responses_stream(prompt, system_prompt)
            except Exception as error:
                logger.warning(
                    "openai_responses_stream_failed_fallback_chat",
                    model=self.model,
                    error=str(error),
                )

        return self._generate_via_chat_completions(prompt, system_prompt)


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
        full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
        resp = httpx.post(
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
    """Mock client for testing — returns predefined responses based on role."""

    def __init__(self, responses: Optional[list] = None):
        super().__init__(model="mock", timeout=0)
        self._responses = responses
        self._call_count = 0

    def generate(self, prompt: str, system_prompt: str = "") -> str:
        if self._responses:
            idx = min(self._call_count, len(self._responses) - 1)
            self._call_count += 1
            return self._responses[idx]

        # Behavior based on system prompt or prompt content
        if "Planner" in system_prompt or "Planner" in prompt:
            return json.dumps({
                "plan": [{"step": 1, "action": "Analyze service", "files": ["main.py"]}],
                "files_to_edit": ["main.py"]
            })
        if "Coder" in system_prompt or "Coder" in prompt:
            return json.dumps({
                "explanation": "Added compliance headers",
                "files_written": ["main.py"]
            })
        if "Reviewer" in system_prompt or "Reviewer" in prompt:
            return json.dumps({
                "verdict": "approve",
                "review": "Code looks good and implements the requested headers.",
                "critical_issues": []
            })
        if "Tester" in system_prompt or "Tester" in prompt:
            return json.dumps({
                "verdict": "pass",
                "tests_run": 5,
                "passed": 5,
                "failed": 0
            })

        # Specific fallback for word 'plan' only if no other role matched
        if "plan" in prompt.lower() and "review" not in prompt.lower():
            return json.dumps({
                "plan": [{"step": 1, "action": "Analyze service", "files": ["main.py"]}],
                "files_to_edit": ["main.py"]
            })

        return json.dumps({"result": "mock response", "verdict": "pass", "status": "completed"})


class LLMClientFactory:
    """Instantiate the correct LLM provider from environment variables.

    Environment variables:
        LLM_MODEL       - Model name (default: llama3:8b)
        LLM_TIMEOUT_S   - Timeout in seconds (default: 60)
        OPENAI_API_KEY   - OpenAI API key (activates OpenAI provider)
        OPENAI_USE_RESPONSES_API - Force Responses API (SSE stream parsing)
        GOOGLE_CLOUD_PROJECT - GCP project ID (activates Vertex AI)
        OLLAMA_HOST      - Ollama endpoint (default: http://localhost:11434)
    """

    @staticmethod
    def create(model: Optional[str] = None) -> BaseLLMClient:
        # Simulation Mode
        if os.getenv("REGENGINE_USE_MOCK_LLM", "").lower() == "true":
            logger.info("llm_client_created", provider="mock", mode="simulation")
            return MockLLMClient()

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
