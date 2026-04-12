from datetime import datetime, timezone
from typing import Optional, Any, List, Protocol
from pydantic import BaseModel, Field, field_validator
import dateutil.parser
from dataclasses import dataclass

class TraceEvent(BaseModel):
    """
    Immutable trace event with strict temporal normalization.
    
    Serves as the canonical data structure for all FSMA compliance rules,
    ensuring that 'Time Arrow' and other logic operates on consistent 
    UTC timestamps rather than fragile strings.
    """
    event_id: str
    lot_code: str = Field(alias="tlc", default="N/A")  # Support legacy 'tlc' alias
    event_date: str  # Original string preserved for audit/evidence
    normalized_timestamp: Optional[datetime] = Field(default=None) # Computed, always UTC
    event_type: Optional[str] = None
    responsible_party_contact: Optional[str] = None  # FSMA 204 KDE

    @field_validator('normalized_timestamp', mode='before')
    @classmethod
    def parse_and_normalize(cls, v: Any) -> datetime:
        """
        Parse any reasonable date format and normalize to UTC.
        """
        if isinstance(v, datetime):
            return v.astimezone(timezone.utc)
            
        if v is not None:
             return cls._parse_string_date(str(v))
        
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
        """
        if self.normalized_timestamp is None and self.event_date:
            try:
                self.normalized_timestamp = self._parse_string_date(self.event_date)
            except ValueError:
                pass


@dataclass
class ValidationViolation:
    rule_name: str
    description: str
    event_ids: List[str]
    details: Optional[Any] = None


@dataclass
class ValidationResult:
    passed: bool
    violations: List[ValidationViolation]


class ComplianceRule(Protocol):
    """Protocol for all FSMA compliance rules."""
    def validate(self, events: List[TraceEvent]) -> ValidationResult: ...


class TimeArrowRule:
    """
    Validates that a sequence of events respects the 'Time Arrow' constraint.
    """
    
    def validate(self, events: List[TraceEvent]) -> ValidationResult:
        violations = []
        
        if not events or len(events) < 2:
            return ValidationResult(passed=True, violations=[])

        for i in range(1, len(events)):
            upstream = events[i-1]
            downstream = events[i]
            
            u_ts = upstream.normalized_timestamp
            d_ts = downstream.normalized_timestamp
            
            if u_ts and d_ts and u_ts > d_ts:
                violations.append(ValidationViolation(
                    rule_name="TIME_ARROW",
                    description=(
                        f"Temporal Paradox: Event {downstream.event_id} ({d_ts}) "
                        f"occurred before its cause {upstream.event_id} ({u_ts})"
                    ),
                    event_ids=[upstream.event_id, downstream.event_id],
                    details={
                        "upstream_date": upstream.event_date,
                        "downstream_date": downstream.event_date,
                        "upstream_ts": u_ts.isoformat(),
                        "downstream_ts": d_ts.isoformat()
                    }
                ))
                
        return ValidationResult(
            passed=len(violations) == 0,
            violations=violations
        )
