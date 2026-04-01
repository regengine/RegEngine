import os
from tenacity import retry, stop_after_attempt, wait_exponential
from typing import Dict, Any, Optional
import openai
from openai import AsyncOpenAI
import json

class LLMClient:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError(
                "LLM client not configured: OPENAI_API_KEY is not set. "
                "Set the OPENAI_API_KEY environment variable before using LLMClient."
            )
        self.client = AsyncOpenAI(api_key=self.api_key)

    @backoff.on_exception(
        backoff.expo,
        (IOError, ConnectionError, TimeoutError, openai.APIConnectionError, openai.RateLimitError),
        max_tries=3,
    )
    async def analyze_image_structured(self, image_b64: str, prompt: str) -> Dict[str, Any]:
        """
        Analyze an image using GPT-4o and return structured JSON.
        """

        response = await self.client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{image_b64}"
                            },
                        },
                    ],
                }
            ],
            response_format={"type": "json_object"},
            max_tokens=1000,
        )

        content = response.choices[0].message.content
        if not content:
            return {}
            
        return json.loads(content)
