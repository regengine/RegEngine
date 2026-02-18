
import os
from supabase import create_client, Client
import structlog

logger = structlog.get_logger("supabase_client")

class SupabaseManager:
    _instance = None
    
    @classmethod
    def get_client(cls) -> Client:
        if cls._instance:
            return cls._instance
            
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_SERVICE_KEY") # Service role key for backend admin tasks
        
        if not url or not key:
            logger.warning("supabase_credentials_missing", detail="SUPABASE_URL or SERVICE_KEY not set")
            # Return None or raise? For now, return None to handle gracefully if not configured
            return None
            
        try:
            cls._instance = create_client(url, key)
            return cls._instance
        except Exception as e:
            logger.error("supabase_init_failed", error=str(e))
            return None

def get_supabase() -> Client:
    return SupabaseManager.get_client()
