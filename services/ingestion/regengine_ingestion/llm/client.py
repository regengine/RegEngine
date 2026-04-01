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
            # We allow init without key, but calls will fail or we can mock for dev
            pass
        self.client = AsyncOpenAI(api_key=self.api_key)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(), reraise=True)
    async def analyze_image_structured(self, image_b64: str, prompt: str) -> Dict[str, Any]:
        """
        Analyze an image using GPT-4o and return structured JSON.
        """
        if not self.api_key:
             return {
                 "error": "Missing OPENAI_API_KEY",
                 "condition": "UNKNOWN",
                 "text_content": "[SIMULATED] API Key missing. Please set env var."
             }

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
