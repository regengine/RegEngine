from datetime import datetime, timezone
from typing import Optional, Any
from pydantic import BaseModel, Field, field_validator
import dateutil.parser

class TraceEvent(BaseModel):
    """
    Immutable trace event with strict temporal normalization.
    
    Serves as the canonical data structure for all FSMA compliance rules,
    ensuring that 'Time Arrow' and other logic operates on consistent 
    UTC timestamps rather than fragile strings.
    """
    event_id: str
    lot_code: str = Field(alias="tlc")  # Support legacy 'tlc' alias
    event_date: str  # Original string preserved for audit/evidence
    normalized_timestamp: datetime = Field(default=None) # Computed, always UTC
    event_type: Optional[str] = None
    responsible_party_contact: Optional[str] = None  # FSMA 204 KDE

    @field_validator('normalized_timestamp', mode='before')
    @classmethod
    def parse_and_normalize(cls, v: Any, info: Any) -> datetime:
        """
        Parse any reasonable date format and normalize to UTC.
        If 'v' is None, attempts to parse from 'event_date' field if available.
        """
        # If value is already provided and is a datetime, ensure UTC
        if isinstance(v, datetime):
            return v.astimezone(timezone.utc)
            
        # If value is provided as string, parse it
        if v is not None:
             return cls._parse_string_date(str(v))

        # If normalized_timestamp is missing, try to derive from event_date
        # Note: field_validator with mode='before' runs before model creation,
        # so we can't fully access 'self'. However, pydantic V2 passes 'info' 
        # but we might be in V1 or V2. 
        # A safer pattern for derived fields is a root_validator or model_validator,
        # but for simplicity in this shared lib we'll assume the caller passes it 
        # or we accept it as None and compute it in a model_validator if needed.
        # But actually, let's make it required or derived in a @model_validator.
        
        # For now, let's keep it simple: if passed as string/datetime, normalize it.
        # If None, we will fail validation unless we add a root validator.
        # Let's fallback to strict parsing in the validator if a string is passed.
        return v

    @classmethod
    def _parse_string_date(cls, date_str: str) -> datetime:
        try:
            parsed = dateutil.parser.parse(date_str, fuzzy=False)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except (ValueError, TypeError) as e:
            raise ValueError(
                f"Unparseable date '{date_str}'. Expected ISO8601 or common format."
            ) from e

    def model_post_init(self, __context: Any) -> None:
        """
        Post-init hook to derive normalized_timestamp from event_date 
        if it wasn't explicitly provided.
        (Compatible with Pydantic V2, for V1 we'd use root_validator)
        """
        if self.normalized_timestamp is None and self.event_date:
            self.normalized_timestamp = self._parse_string_date(self.event_date)
