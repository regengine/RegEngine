"""
CA AB5 ABC Test Classification Engine

Evaluates worker engagements against California's ABC Test to determine
employee vs independent contractor classification per AB5/AB2257.

The ABC Test presumes a worker is an employee unless the hiring entity
can prove ALL THREE prongs:
- A: Free from control and direction
- B: Work is outside the usual course of the hiring entity's business
- C: Worker is customarily engaged in an independently established trade
"""

import structlog
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, List, Any
from enum import Enum

logger = structlog.get_logger(__name__)


class ClassificationResult(str, Enum):
    EMPLOYEE = "employee"
    CONTRACTOR = "contractor"
    UNCERTAIN = "uncertain"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ConfidenceLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass
class ProngAnalysis:
    """Analysis result for a single prong of the ABC Test."""
    prong: str  # 'A', 'B', 'C'
    passed: bool
    score: int  # 0-100
    factors: Dict[str, Any]
    reasoning: str
    key_indicators: List[str] = field(default_factory=list)


@dataclass
class ExemptionCheck:
    """Result of checking for AB5 exemptions."""
    is_applicable: bool
    exemption_type: Optional[str]
    exemption_code: Optional[str]
    reasoning: str
    matching_criteria: List[str] = field(default_factory=list)


@dataclass
class ABCTestResult:
    """Complete ABC Test analysis result."""
    prong_a: ProngAnalysis
    prong_b: ProngAnalysis
    prong_c: ProngAnalysis
    overall_result: ClassificationResult
    overall_score: int
    confidence: ConfidenceLevel
    risk_level: RiskLevel
    risk_factors: List[str]
    recommended_action: str
    exemption: Optional[ExemptionCheck]
    analyzed_at: datetime


@dataclass
class QuestionnaireResponse:
    """A single questionnaire response."""
    question_code: str
    question_text: str
    category: str
    response: str  # 'yes', 'no', 'partial', 'unknown'
    details: Optional[str] = None
    supports_contractor: Optional[bool] = None
    impact_score: int = 0  # -100 to +100


class ABCTestEvaluator:
    """
    California AB5 ABC Test evaluator for worker classification.
    
    Implements the ABC Test with industry-specific considerations
    for entertainment/production workers.
    """
    
    RULE_VERSION = "2.0"
    
    # Role-based exemption hints
    LIKELY_EXEMPT_ROLES = {
        "writer", "editor", "photographer", "videographer", 
        "composer", "musician", "attorney", "accountant",
        "fine artist", "sculptor", "painter"
    }
    
    # Roles that are almost always employees in entertainment
    LIKELY_EMPLOYEE_ROLES = {
        "production assistant", "pa", "grip", "gaffer", "camera operator",
        "sound mixer", "boom operator", "set decorator", "prop master",
        "wardrobe", "makeup", "hair", "craft services", "driver",
        "teamster", "location manager", "production coordinator"
    }
    
    def __init__(self, exemptions: Optional[List[Dict]] = None):
        """
        Initialize the evaluator.
        
        Args:
            exemptions: List of exemption definitions from database.
        """
        self.exemptions = exemptions or []
        logger.info(
            "abc_test_evaluator_initialized",
            exemption_count=len(self.exemptions)
        )
    
    def analyze(
        self,
        engagement: Dict,
        person: Optional[Dict] = None,
        company: Optional[Dict] = None,
        questionnaire_responses: Optional[List[Dict]] = None
    ) -> ABCTestResult:
        """
        Perform complete ABC Test analysis on an engagement.
        
        Args:
            engagement: Engagement data (role, pay_type, classification, etc.)
            person: Person data (business entity, other clients, etc.)
            company: Hiring company data
            questionnaire_responses: List of questionnaire responses
            
        Returns:
            ABCTestResult with full analysis
        """
        person = person or {}
        company = company or {}
        questionnaire_responses = questionnaire_responses or []
        
        # Check for exemptions first
        exemption = self._check_exemptions(engagement, person)
        
        # Analyze each prong
        prong_a = self._analyze_prong_a(engagement, person, questionnaire_responses)
        prong_b = self._analyze_prong_b(engagement, company, questionnaire_responses)
        prong_c = self._analyze_prong_c(engagement, person, questionnaire_responses)
        
        # Determine overall result
        # ABC Test requires ALL THREE prongs to pass for contractor status
        all_passed = prong_a.passed and prong_b.passed and prong_c.passed
        
        # Calculate overall score (weighted average)
        overall_score = int(
            prong_a.score * 0.35 +
            prong_b.score * 0.35 +
            prong_c.score * 0.30
        )
        
        # Determine result
        if exemption and exemption.is_applicable:
            # Exemption applies - use Borello test instead (more nuanced)
            overall_result = ClassificationResult.CONTRACTOR if overall_score >= 50 else ClassificationResult.UNCERTAIN
        elif all_passed and overall_score >= 70:
            overall_result = ClassificationResult.CONTRACTOR
        elif not prong_a.passed and not prong_b.passed and not prong_c.passed:
            overall_result = ClassificationResult.EMPLOYEE
        elif overall_score <= 30:
            overall_result = ClassificationResult.EMPLOYEE
        else:
            overall_result = ClassificationResult.UNCERTAIN
        
        # Assess confidence
        if all(p.score >= 80 or p.score <= 20 for p in [prong_a, prong_b, prong_c]):
            confidence = ConfidenceLevel.HIGH
        elif overall_score >= 60 or overall_score <= 40:
            confidence = ConfidenceLevel.MEDIUM
        else:
            confidence = ConfidenceLevel.LOW
        
        # Assess risk
        risk_factors = []
        risk_level = RiskLevel.LOW
        
        if overall_result == ClassificationResult.UNCERTAIN:
            risk_level = RiskLevel.HIGH
            risk_factors.append("Classification is uncertain; recommend legal review")
        
        if engagement.get("classification") == "contractor" and overall_result == ClassificationResult.EMPLOYEE:
            risk_level = RiskLevel.CRITICAL
            risk_factors.append("Currently classified as contractor but analysis suggests employee status")
        
        if not prong_b.passed:
            risk_factors.append("Work appears integrated into core business operations")
        
        if engagement.get("pay_type") == "hourly" and engagement.get("classification") == "contractor":
            risk_level = max(risk_level, RiskLevel.MEDIUM, key=lambda x: list(RiskLevel).index(x))
            risk_factors.append("Hourly pay is unusual for genuine independent contractors")
        
        # Generate recommendation
        if overall_result == ClassificationResult.EMPLOYEE:
            recommended_action = "Reclassify as W-2 employee or restructure engagement"
        elif overall_result == ClassificationResult.CONTRACTOR:
            recommended_action = "Maintain contractor status with proper documentation"
        else:
            recommended_action = "Consult employment attorney before proceeding"
        
        return ABCTestResult(
            prong_a=prong_a,
            prong_b=prong_b,
            prong_c=prong_c,
            overall_result=overall_result,
            overall_score=overall_score,
            confidence=confidence,
            risk_level=risk_level,
            risk_factors=risk_factors,
            recommended_action=recommended_action,
            exemption=exemption,
            analyzed_at=datetime.utcnow()
        )
    
    def _analyze_prong_a(
        self,
        engagement: Dict,
        person: Dict,
        responses: List[Dict]
    ) -> ProngAnalysis:
        """
        Prong A: Free from control and direction in performing the work.
        """
        factors = {}
        score = 50  # Start neutral
        indicators = []
        
        # Factor 1: Control over HOW work is done
        if engagement.get("sets_own_methods", False):
            score += 15
            factors["sets_own_methods"] = True
            indicators.append("Worker determines how work is performed")
        else:
            score -= 15
            factors["sets_own_methods"] = False
            indicators.append("Hiring entity controls work methods")
        
        # Factor 2: Control over WHEN work is done
        if engagement.get("sets_own_schedule", False):
            score += 15
            factors["sets_own_schedule"] = True
            indicators.append("Worker sets own schedule")
        else:
            score -= 10
            factors["sets_own_schedule"] = False
        
        # Factor 3: Location of work
        if engagement.get("works_offsite", False):
            score += 10
            factors["works_offsite"] = True
        else:
            score -= 5
            factors["works_offsite"] = False
        
        # Factor 4: Supervision level
        supervision = engagement.get("supervision_level", "medium")
        if supervision == "none":
            score += 15
            factors["supervision_level"] = "none"
            indicators.append("No direct supervision")
        elif supervision == "minimal":
            score += 5
            factors["supervision_level"] = "minimal"
        elif supervision == "high":
            score -= 20
            factors["supervision_level"] = "high"
            indicators.append("High level of supervision indicates employee status")
        
        # Factor 5: Training provided
        if engagement.get("training_provided", False):
            score -= 15
            factors["training_provided"] = True
            indicators.append("Hiring entity provides training (employee indicator)")
        else:
            score += 5
            factors["training_provided"] = False
        
        # Apply questionnaire responses
        for resp in responses:
            if resp.get("category") == "control":
                score += resp.get("impact_score", 0) // 2
        
        # Clamp score
        score = max(0, min(100, score))
        
        # Determine pass/fail
        passed = score >= 60
        
        reasoning = self._generate_prong_a_reasoning(factors, score, passed)
        
        return ProngAnalysis(
            prong="A",
            passed=passed,
            score=score,
            factors=factors,
            reasoning=reasoning,
            key_indicators=indicators
        )
    
    def _analyze_prong_b(
        self,
        engagement: Dict,
        company: Dict,
        responses: List[Dict]
    ) -> ProngAnalysis:
        """
        Prong B: Work is outside the usual course of the hiring entity's business.
        
        This is typically the hardest prong to pass in entertainment.
        """
        factors = {}
        score = 50
        indicators = []
        
        role = (engagement.get("role_title") or "").lower()
        
        # Factor 1: Is the role core to production?
        core_production_roles = {
            "director", "producer", "camera", "grip", "gaffer", "sound",
            "editor", "pa", "production assistant", "coordinator", "ad",
            "assistant director", "dp", "cinematographer"
        }
        
        is_core_role = any(core in role for core in core_production_roles)
        
        if is_core_role:
            score -= 25
            factors["is_core_production_role"] = True
            indicators.append("Role is integral to production operations")
        else:
            score += 15
            factors["is_core_production_role"] = False
            indicators.append("Role may be outside core production work")
        
        # Factor 2: Does company regularly engage this type of work?
        company_type = (company.get("business_type") or "production").lower()
        if "production" in company_type or "film" in company_type:
            if is_core_role:
                score -= 20
                factors["company_regularly_uses_role"] = True
            else:
                score += 5
        
        # Factor 3: Is this a one-off specialized service?
        if engagement.get("is_specialized_service", False):
            score += 20
            factors["specialized_service"] = True
            indicators.append("Work is specialized/one-time service")
        
        # Factor 4: Would company hire employee for this if contractor unavailable?
        if engagement.get("would_hire_employee", True):
            score -= 15
            factors["would_hire_employee"] = True
        else:
            score += 10
            factors["would_hire_employee"] = False
        
        # Check for likely employee roles
        if any(emp_role in role for emp_role in self.LIKELY_EMPLOYEE_ROLES):
            score -= 20
            indicators.append(f"Role '{role}' typically indicates employee status in production")
        
        # Apply questionnaire responses
        for resp in responses:
            if resp.get("category") == "integration":
                score += resp.get("impact_score", 0) // 2
        
        score = max(0, min(100, score))
        passed = score >= 60
        
        reasoning = self._generate_prong_b_reasoning(factors, score, passed, role)
        
        return ProngAnalysis(
            prong="B",
            passed=passed,
            score=score,
            factors=factors,
            reasoning=reasoning,
            key_indicators=indicators
        )
    
    def _analyze_prong_c(
        self,
        engagement: Dict,
        person: Dict,
        responses: List[Dict]
    ) -> ProngAnalysis:
        """
        Prong C: Customarily engaged in an independently established trade,
        occupation, or business of the same nature as the work performed.
        """
        factors = {}
        score = 50
        indicators = []
        
        # Factor 1: Has business entity
        if person.get("has_business_entity", False):
            score += 20
            factors["has_business_entity"] = True
            indicators.append("Worker has established business entity")
        else:
            score -= 10
            factors["has_business_entity"] = False
        
        # Factor 2: Has other clients
        other_clients = person.get("other_client_count", 0)
        if other_clients >= 3:
            score += 20
            factors["multiple_clients"] = True
            indicators.append(f"Worker has {other_clients} other clients")
        elif other_clients >= 1:
            score += 10
            factors["multiple_clients"] = True
        else:
            score -= 15
            factors["multiple_clients"] = False
            indicators.append("Worker has no other clients (employee indicator)")
        
        # Factor 3: Owns tools/equipment
        if person.get("owns_equipment", False):
            score += 10
            factors["owns_equipment"] = True
        else:
            score -= 5
            factors["owns_equipment"] = False
        
        # Factor 4: Advertises services
        if person.get("advertises_services", False):
            score += 15
            factors["advertises_services"] = True
            indicators.append("Worker actively markets services")
        
        # Factor 5: Has established business before this engagement
        if person.get("business_established_before_engagement", False):
            score += 15
            factors["established_business"] = True
        else:
            score -= 10
            factors["established_business"] = False
        
        # Factor 6: Sets own rates
        if engagement.get("negotiated_rate", False):
            score += 10
            factors["negotiated_rate"] = True
        
        # Apply questionnaire responses
        for resp in responses:
            if resp.get("category") in ("skill", "investment"):
                score += resp.get("impact_score", 0) // 2
        
        score = max(0, min(100, score))
        passed = score >= 60
        
        reasoning = self._generate_prong_c_reasoning(factors, score, passed)
        
        return ProngAnalysis(
            prong="C",
            passed=passed,
            score=score,
            factors=factors,
            reasoning=reasoning,
            key_indicators=indicators
        )
    
    def _check_exemptions(
        self,
        engagement: Dict,
        person: Dict
    ) -> Optional[ExemptionCheck]:
        """Check if an AB5 exemption applies."""
        role = (engagement.get("role_title") or "").lower()
        matching_exemptions = []
        
        for exemption in self.exemptions:
            criteria = exemption.get("qualifying_criteria", {})
            keywords = criteria.get("role_keywords", [])
            
            # Check role keywords
            if any(kw.lower() in role for kw in keywords):
                matching_exemptions.append(exemption)
        
        if not matching_exemptions:
            # Check built-in likely exempt roles
            if any(exempt in role for exempt in self.LIKELY_EXEMPT_ROLES):
                return ExemptionCheck(
                    is_applicable=True,
                    exemption_type="Potential Professional/Creative Exemption",
                    exemption_code=None,
                    reasoning=f"Role '{role}' may qualify for AB5 exemption. Verify specific criteria.",
                    matching_criteria=["role_match"]
                )
            return None
        
        # Use first matching exemption
        best_match = matching_exemptions[0]
        return ExemptionCheck(
            is_applicable=True,
            exemption_type=best_match.get("exemption_name"),
            exemption_code=best_match.get("exemption_code"),
            reasoning=best_match.get("description", ""),
            matching_criteria=list(best_match.get("qualifying_criteria", {}).keys())
        )
    
    def _generate_prong_a_reasoning(self, factors: Dict, score: int, passed: bool) -> str:
        """Generate human-readable reasoning for Prong A."""
        if passed:
            return (
                f"Analysis indicates worker is FREE from control and direction (score: {score}/100). "
                "Key factors: " + ", ".join([
                    "sets own methods" if factors.get("sets_own_methods") else "",
                    "sets own schedule" if factors.get("sets_own_schedule") else "",
                    "minimal supervision" if factors.get("supervision_level") in ("none", "minimal") else "",
                ]).strip(", ") + "."
            )
        else:
            return (
                f"Analysis indicates hiring entity exercises CONTROL over worker (score: {score}/100). "
                "Concerns: " + ", ".join([
                    "supervised work" if factors.get("supervision_level") == "high" else "",
                    "training provided" if factors.get("training_provided") else "",
                    "methods dictated" if not factors.get("sets_own_methods") else "",
                ]).strip(", ") + "."
            )
    
    def _generate_prong_b_reasoning(self, factors: Dict, score: int, passed: bool, role: str) -> str:
        """Generate human-readable reasoning for Prong B."""
        if passed:
            return (
                f"Work appears OUTSIDE usual course of business (score: {score}/100). "
                f"Role '{role}' is not integral to core production operations."
            )
        else:
            return (
                f"Work appears WITHIN usual course of business (score: {score}/100). "
                f"Role '{role}' is integral to production company operations. "
                "This is typically the hardest prong to satisfy in entertainment."
            )
    
    def _generate_prong_c_reasoning(self, factors: Dict, score: int, passed: bool) -> str:
        """Generate human-readable reasoning for Prong C."""
        if passed:
            return (
                f"Worker appears to have an ESTABLISHED independent business (score: {score}/100). "
                "Indicators: " + ", ".join([
                    "has business entity" if factors.get("has_business_entity") else "",
                    "multiple clients" if factors.get("multiple_clients") else "",
                    "owns equipment" if factors.get("owns_equipment") else "",
                ]).strip(", ") + "."
            )
        else:
            return (
                f"Worker does NOT appear to have established independent business (score: {score}/100). "
                "Missing: " + ", ".join([
                    "business entity" if not factors.get("has_business_entity") else "",
                    "other clients" if not factors.get("multiple_clients") else "",
                ]).strip(", ") + "."
            )


def analyze_engagement_classification(
    engagement: Dict,
    person: Optional[Dict] = None,
    company: Optional[Dict] = None,
    questionnaire_responses: Optional[List[Dict]] = None,
    exemptions: Optional[List[Dict]] = None
) -> Dict[str, Any]:
    """
    Convenience function to analyze an engagement for classification.
    
    Returns a dictionary suitable for JSON serialization and API response.
    """
    evaluator = ABCTestEvaluator(exemptions=exemptions)
    result = evaluator.analyze(engagement, person, company, questionnaire_responses)
    
    response = {
        "overall_result": result.overall_result.value,
        "overall_score": result.overall_score,
        "confidence": result.confidence.value,
        "risk_level": result.risk_level.value,
        "risk_factors": result.risk_factors,
        "recommended_action": result.recommended_action,
        "analyzed_at": result.analyzed_at.isoformat(),
        "rule_version": ABCTestEvaluator.RULE_VERSION,
        "prong_a": {
            "passed": result.prong_a.passed,
            "score": result.prong_a.score,
            "factors": result.prong_a.factors,
            "reasoning": result.prong_a.reasoning,
            "key_indicators": result.prong_a.key_indicators
        },
        "prong_b": {
            "passed": result.prong_b.passed,
            "score": result.prong_b.score,
            "factors": result.prong_b.factors,
            "reasoning": result.prong_b.reasoning,
            "key_indicators": result.prong_b.key_indicators
        },
        "prong_c": {
            "passed": result.prong_c.passed,
            "score": result.prong_c.score,
            "factors": result.prong_c.factors,
            "reasoning": result.prong_c.reasoning,
            "key_indicators": result.prong_c.key_indicators
        }
    }
    
    if result.exemption:
        response["exemption"] = {
            "is_applicable": result.exemption.is_applicable,
            "type": result.exemption.exemption_type,
            "code": result.exemption.exemption_code,
            "reasoning": result.exemption.reasoning
        }
    
    return response
