import json
import os
import time
import abc
from typing import List, Any, Dict, Optional

import structlog
from jsonschema import Draft202012Validator, ValidationError
from pydantic import BaseModel, Field

logger = structlog.get_logger("llm-extractor")


class LLMExtraction(BaseModel):
    provision_text: str = Field(..., description="The exact quote from the regulation.")
    obligation_type: str = Field(..., description="Type: REQUIREMENT, PROHIBITION, REPORTING, or EXEMPTION")
    confidence: float = Field(..., ge=0.0, le=1.0)
    entities: Optional[Dict[str, Any]] = Field(default_factory=dict)

    model_config = {"extra": "allow"}


class BaseLLMClient(abc.ABC):
    """Abstract base for LLM providers to ensure consistent agent behavior."""

    def __init__(self, model: str, timeout: int = 30):
        self.model = model
        self.timeout = timeout

    @abc.abstractmethod
    def generate(self, prompt: str, system_prompt: str = "") -> str:
        pass


class OpenAILegacyClient(BaseLLMClient):
    """Production client for OpenAI GPT-4/3.5."""

    def __init__(self, model: str, api_key: str, timeout: int):
        super().__init__(model, timeout)
        from openai import OpenAI
        self.client = OpenAI(api_key=api_key)

    def generate(self, prompt: str, system_prompt: str = "") -> str:
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            temperature=0,
            response_format={"type": "json_object"},
            timeout=self.timeout
        )
        return resp.choices[0].message.content or "{}"


class VertexAIClient(BaseLLMClient):
    """Production client for Google Gemini via Vertex AI."""

    def __init__(self, model: str, project_id: str, location: str, timeout: int):
        super().__init__(model, timeout)
        import vertexai
        from vertexai.generative_models import GenerativeModel
        vertexai.init(project=project_id, location=location)
        self.client = GenerativeModel(model)

    def generate(self, prompt: str, system_prompt: str = "") -> str:
        full_prompt = f"{system_prompt}\n\n{prompt}"
        resp = self.client.generate_content(
            full_prompt,
            generation_config={"response_mime_type": "application/json", "temperature": 0.0}
        )
        return resp.text


class OllamaClient(BaseLLMClient):
    """Local fallback client."""

    def __init__(self, model: str, host: str, timeout: int):
        super().__init__(model, timeout)
        self.host = host

    def generate(self, prompt: str, system_prompt: str = "") -> str:
        import requests
        try:
            resp = requests.post(
                f"{self.host}/api/generate",
                json={
                    "model": self.model,
                    "prompt": f"{system_prompt}\n\n{prompt}",
                    "stream": False,
                    "format": "json",
                    "options": {"temperature": 0.0}
                },
                timeout=self.timeout
            )
            resp.raise_for_status()
            return resp.json().get("response", "[]")
        except Exception as e:
            logger.error("ollama_failed", error=str(e))
            raise


class LLMClientFactory:
    """Factory to instantiate the correct provider based on env vars."""

    @staticmethod
    def create() -> BaseLLMClient:
        model = os.getenv("LLM_MODEL", "llama3:8b")
        timeout = int(os.getenv("LLM_TIMEOUT_S", "45"))

        if "gpt" in model.lower():
            api_key = os.getenv("OPENAI_API_KEY")
            if api_key:
                return OpenAILegacyClient(model, api_key, timeout)

        if "gemini" in model.lower():
            project = os.getenv("GOOGLE_CLOUD_PROJECT")
            location = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
            if project:
                return VertexAIClient(model, project, location, timeout)

        # Default fallback
        host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
        if os.getenv("REGENGINE_ENV") == "production" and "localhost" in host:
            logger.warning("OLLAMA_HOST points to localhost in production — set to a remote endpoint")
        return OllamaClient(model, host, timeout)


class LLMGenerativeExtractor:
    """
    Agentic Extractor that uses Self-Correction to ensure valid JSON output.
    """

    SYSTEM_PROMPT = (
        "You are a Senior Regulatory Compliance Officer. "
        "Extract specific compliance obligations from the provided text. "
        "Return a JSON object with a key 'results' containing a list of items. "
        "Each item must have: 'provision_text' (exact quote), 'obligation_type' (REQUIREMENT/PROHIBITION/REPORTING), and 'confidence' (float 0-1)."
    )

    JSON_SCHEMA = {
        "type": "object",
        "properties": {
            "results": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "provision_text": {"type": "string", "minLength": 5},
                        "obligation_type": {"type": "string", "enum": ["REQUIREMENT", "PROHIBITION", "REPORTING", "EXEMPTION", "UNKNOWN"]},
                        "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0}
                    },
                    "required": ["provision_text", "obligation_type", "confidence"]
                }
            }
        },
        "required": ["results"]
    }

    def __init__(self):
        self.client = LLMClientFactory.create()
        self.validator = Draft202012Validator(self.JSON_SCHEMA)
        self.max_retries = int(os.getenv("LLM_MAX_RETRIES", "3"))

    def extract(self, text: str, jurisdiction: str, correlation_id: Optional[str] = None) -> List[LLMExtraction]:
        start_time = time.perf_counter()
        log = logger.bind(corr_id=correlation_id, jurisdiction=jurisdiction, model=self.client.model)

        prompt = f"REGULATION TEXT ({jurisdiction}):\n{text[:50000]}"

        for attempt in range(self.max_retries + 1):
            try:
                # Generate
                raw_response = self.client.generate(prompt, self.SYSTEM_PROMPT)

                # Parse
                try:
                    data = json.loads(raw_response)
                except json.JSONDecodeError:
                    if attempt < self.max_retries:
                        log.warning("invalid_json_generated", attempt=attempt)
                        prompt += "\n\nERROR: The previous output was not valid JSON. Please output ONLY raw valid JSON."
                        continue
                    else:
                        raise

                # Validate Schema
                try:
                    self.validator.validate(data)
                except ValidationError as e:
                    if attempt < self.max_retries:
                        log.warning("schema_validation_failed", attempt=attempt, error=e.message)
                        prompt += f"\n\nERROR: JSON schema validation failed: {e.message}. Please fix the structure."
                        continue
                    else:
                        raise

                # Success - Map to Pydantic
                results = []
                for item in data.get("results", []):
                    # Basic hallucination check: Quote must exist in text (fuzzy check could be added here)
                    if item["provision_text"] not in text:
                        log.info("hallucination_detected", text_snippet=item["provision_text"][:20])
                        item["confidence"] = min(item["confidence"], 0.5)

                    results.append(LLMExtraction(**item))

                duration = time.perf_counter() - start_time
                log.info("extraction_success", items=len(results), duration=duration, attempts=attempt + 1)
                return results

            except Exception as e:
                log.error("extraction_attempt_failed", attempt=attempt, error=str(e))
                if attempt == self.max_retries:
                    log.error("extraction_failed_final")
                    return []

        return []
