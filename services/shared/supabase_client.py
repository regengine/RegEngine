
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
            
        # Accept both naming conventions for the URL and service key so the
        # backend works whether env vars are prefixed for Next.js or not.
        url = os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL")
        key = (
            os.getenv("SUPABASE_SERVICE_KEY")           # legacy name (internal)
            or os.getenv("SUPABASE_SERVICE_ROLE_KEY")   # standard Supabase dashboard name
            or os.getenv("SUPABASE_ANON_KEY")           # anon key — sufficient for auth.get_user()
            or os.getenv("NEXT_PUBLIC_SUPABASE_ANON_KEY")  # Next.js-prefixed anon key
        )

        if not url or not key:
            logger.warning("supabase_credentials_missing", detail="SUPABASE_URL and one of SUPABASE_SERVICE_ROLE_KEY/SUPABASE_SERVICE_KEY/SUPABASE_ANON_KEY must be set")
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
