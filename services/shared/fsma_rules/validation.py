from typing import List, Protocol, Optional, Any
from dataclasses import dataclass
from .models import TraceEvent

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
    
    Rule: A downstream event (e.g. Shipping) cannot occur before an 
    upstream event (e.g. Receiving/Production) in the causal chain.
    """
    
    def validate(self, events: List[TraceEvent]) -> ValidationResult:
        violations = []
        
        # Sort by normalized timestamp to establish chronological order
        # Note: In a graph traversal, we usually rely on the path order, 
        # but 'Time Arrow' specifically checks that the *causal* path 
        # (as traversed) matches the *temporal* reality.
        #
        # If we receive a path [A, B, C], we expect time(A) <= time(B) <= time(C).
        # We assume the input 'events' list represents the causal chain order.
        
        if not events or len(events) < 2:
            return ValidationResult(passed=True, violations=[])

        for i in range(1, len(events)):
            upstream = events[i-1]
            downstream = events[i]
            
            # Allow for some tolerance? strict for now.
            if upstream.normalized_timestamp > downstream.normalized_timestamp:
                violations.append(ValidationViolation(
                    rule_name="TIME_ARROW",
                    description=(
                        f"Temporal Paradox: Event {downstream.event_id} ({downstream.normalized_timestamp}) "
                        f"occurred before its cause {upstream.event_id} ({upstream.normalized_timestamp})"
                    ),
                    event_ids=[upstream.event_id, downstream.event_id],
                    details={
                        "upstream_date": upstream.event_date,
                        "downstream_date": downstream.event_date,
                        "upstream_ts": upstream.normalized_timestamp.isoformat(),
                        "downstream_ts": downstream.normalized_timestamp.isoformat()
                    }
                ))
                
        return ValidationResult(
            passed=len(violations) == 0,
            violations=violations
        )
