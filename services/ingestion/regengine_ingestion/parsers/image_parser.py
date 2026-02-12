import base64
import json
import asyncio
from typing import Optional, Dict, Any, List
from .base import DocumentParser
from ..llm.client import LLMClient

class ImageParser(DocumentParser):
    """
    Parser for image documents (JPEG, PNG, WEBP).
    
    Uses Multimodal LLM (stubbed for now) to extract structured data
    from visual evidence.
    """
    
    SUPPORTED_TYPES = [
        "image/jpeg",
        "image/png",
        "image/webp",
        "image/jpg"
    ]
    
    def can_parse(self, content_type: str, content: bytes) -> bool:
        """Check if content is an image."""
        if any(t in content_type.lower() for t in self.SUPPORTED_TYPES):
            return True
            
        # Magic bytes check could be added here
        return False
    
    def parse(self, content: bytes, metadata: Optional[Dict[str, Any]] = None) -> str:
        """
        Extract structured data from image using Multimodal LLM.
        
        Args:
            content: Image bytes
            metadata: Optional metadata
            
        Returns:
            Extracted text description (JSON string)
        """
        
        # Convert to base64
        image_b64 = base64.b64encode(content).decode("utf-8")
        
        # Prepare prompt
        prompt = """
        You are an expert supply chain inspector. Analyze this image for regulatory compliance and logistics data.
        
        Extract the following structured data:
        1. summary: A brief 1-sentence description of what is in the image.
        2. condition: The physical condition of the item (e.g., "GOOD", "DAMAGED", "LEAKING", "UNKNOWN").
        3. text_content: Any visible text, including labels, dates, or handwriting.
        4. shipping_labels: Extract any tracking numbers, barcodes (human readable), or addresses.
        5. hazards: Identify any potential hazards (e.g., "spill", "sharp object", "none").
        
        Return ONLY valid JSON.
        """
        
        client = LLMClient()
        
        # Run async LLM call in sync context (since parse is sync)
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
        try:
            result = loop.run_until_complete(client.analyze_image_structured(image_b64, prompt))
            
            # Augment with metadata
            result["_metadata"] = {
                "captured_at": metadata.get('captured_at', 'Unknown'),
                "user_id": metadata.get('user_id', 'Unknown'),
                "size_kb": len(content) / 1024
            }
            
            return json.dumps(result, indent=2)
            
        except Exception as e:
            return f"Error analyzing image: {str(e)}"
    
    def get_parser_name(self) -> str:
        return "image_llm_parser"
