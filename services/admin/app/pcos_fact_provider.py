"""
PCOS Fact Provider — Data Aggregation Service

Provides compiled project facts, risk summaries, and guidance items
by aggregating data from the PCOS database tables.
"""

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from .pcos_models import (
    PCOSProjectModel,
    PCOSLocationModel,
    PCOSEngagementModel,
    PCOSTaskModel,
    PCOSEvidenceModel,
    PCOSPersonModel,
    GateState,
    TaskStatus,
    ClassificationType,
    LocationType,
    Jurisdiction,
    EvidenceType,
)


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class ProjectFacts:
    """Compiled facts about a project for gate evaluation."""
    project_id: UUID
    name: str
    project_type: str
    gate_state: str
    first_shoot_date: Optional[date] = None
    last_shoot_date: Optional[date] = None
    days_until_shoot: Optional[int] = None
    
    # Location facts
    location_count: int = 0
    has_permit_locations: bool = False
    has_public_row_locations: bool = False
    has_certified_studio_locations: bool = False
    jurisdictions: list[str] = field(default_factory=list)
    
    # Crew facts
    engagement_count: int = 0
    employee_count: int = 0
    contractor_count: int = 0
    has_employees: bool = False
    has_contractors: bool = False
    minor_involved: bool = False
    
    # Task facts
    total_tasks: int = 0
    completed_tasks: int = 0
    blocking_tasks: int = 0
    
    # Evidence facts
    evidence_types_present: list[str] = field(default_factory=list)
    missing_required_evidence: list[str] = field(default_factory=list)


@dataclass
class RiskCategory:
    """Risk category summary."""
    id: str
    name: str
    score: int  # 0-100
    tasks: int  # Number of pending tasks
    status: str  # 'low', 'medium', 'high', 'critical'
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "score": self.score,
            "tasks": self.tasks,
            "status": self.status,
        }


@dataclass
class GuidanceItem:
    """A how-to guidance item."""
    id: str
    title: str
    category: str
    priority: str  # 'low', 'medium', 'high', 'critical'
    deadline: Optional[str] = None
    days_until: Optional[int] = None
    steps: list[dict] = field(default_factory=list)
    documents_required: list[str] = field(default_factory=list)
    estimated_time: str = ""
    resource_url: Optional[str] = None
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "category": self.category,
            "priority": self.priority,
            "deadline": self.deadline,
            "daysUntil": self.days_until,
            "steps": self.steps,
            "documentsRequired": self.documents_required,
            "estimatedTime": self.estimated_time,
            "resourceUrl": self.resource_url,
        }


# =============================================================================
# FACT PROVIDER CLASS
# =============================================================================

class PCOSFactProvider:
    """Aggregates project data into compiled facts and risk summaries."""
    
    def __init__(self, db: Session, tenant_id: UUID):
        self.db = db
        self.tenant_id = tenant_id
    
    def get_project_facts(self, project_id: UUID) -> Optional[ProjectFacts]:
        """Compile all facts for a project."""
        # Get project
        project = self.db.execute(
            select(PCOSProjectModel).where(
                PCOSProjectModel.id == project_id,
                PCOSProjectModel.tenant_id == self.tenant_id,
            )
        ).scalar_one_or_none()
        
        if not project:
            return None
        
        # Calculate days until shoot
        days_until_shoot = None
        if project.first_shoot_date:
            delta = project.first_shoot_date - date.today()
            days_until_shoot = delta.days
        
        facts = ProjectFacts(
            project_id=project.id,
            name=project.name,
            project_type=project.project_type.value if project.project_type else "unknown",
            gate_state=project.gate_state.value if project.gate_state else "draft",
            first_shoot_date=project.first_shoot_date,
            last_shoot_date=project.last_shoot_date,
            days_until_shoot=days_until_shoot,
        )
        
        # Gather location facts
        self._gather_location_facts(project_id, facts)
        
        # Gather engagement facts
        self._gather_engagement_facts(project_id, facts)
        
        # Gather task facts
        self._gather_task_facts(project_id, facts)
        
        # Gather evidence facts
        self._gather_evidence_facts(project_id, facts)
        
        return facts
    
    def _gather_location_facts(self, project_id: UUID, facts: ProjectFacts) -> None:
        """Populate location-related facts."""
        locations = self.db.execute(
            select(PCOSLocationModel).where(
                PCOSLocationModel.project_id == project_id,
            )
        ).scalars().all()
        
        facts.location_count = len(locations)
        jurisdictions_set = set()
        
        for loc in locations:
            if loc.requires_permit:
                facts.has_permit_locations = True
            if loc.location_type == LocationType.PUBLIC_ROW:
                facts.has_public_row_locations = True
            if loc.location_type == LocationType.CERTIFIED_STUDIO:
                facts.has_certified_studio_locations = True
            if loc.jurisdiction:
                jurisdictions_set.add(loc.jurisdiction.value)
        
        facts.jurisdictions = list(jurisdictions_set)
    
    def _gather_engagement_facts(self, project_id: UUID, facts: ProjectFacts) -> None:
        """Populate engagement-related facts."""
        engagements = self.db.execute(
            select(PCOSEngagementModel).where(
                PCOSEngagementModel.project_id == project_id,
            )
        ).scalars().all()
        
        facts.engagement_count = len(engagements)
        
        for eng in engagements:
            if eng.classification == ClassificationType.EMPLOYEE:
                facts.employee_count += 1
                facts.has_employees = True
            elif eng.classification == ClassificationType.CONTRACTOR:
                facts.contractor_count += 1
                facts.has_contractors = True
            
            # Check for minors via person lookup
            if eng.person_id:
                person = self.db.execute(
                    select(PCOSPersonModel).where(PCOSPersonModel.id == eng.person_id)
                ).scalar_one_or_none()
                if person and person.is_minor:
                    facts.minor_involved = True
    
    def _gather_task_facts(self, project_id: UUID, facts: ProjectFacts) -> None:
        """Populate task-related facts."""
        tasks = self.db.execute(
            select(PCOSTaskModel).where(
                PCOSTaskModel.project_id == project_id,
            )
        ).scalars().all()
        
        facts.total_tasks = len(tasks)
        
        for task in tasks:
            if task.status == TaskStatus.COMPLETED:
                facts.completed_tasks += 1
            elif task.is_blocking and task.status != TaskStatus.COMPLETED:
                facts.blocking_tasks += 1
    
    def _gather_evidence_facts(self, project_id: UUID, facts: ProjectFacts) -> None:
        """Populate evidence-related facts."""
        evidence = self.db.execute(
            select(PCOSEvidenceModel).where(
                PCOSEvidenceModel.project_id == project_id,
            )
        ).scalars().all()
        
        facts.evidence_types_present = [
            e.evidence_type.value for e in evidence if e.evidence_type
        ]
        
        # Determine required evidence based on project facts
        required = []
        if facts.has_permit_locations:
            required.extend(["permit_approved", "coi"])
        if facts.has_employees:
            required.append("workers_comp_policy")
        if facts.has_contractors:
            required.append("classification_memo_signed")
        if facts.minor_involved:
            required.append("minor_work_permit")
        
        facts.missing_required_evidence = [
            r for r in required if r not in facts.evidence_types_present
        ]
    
    def get_risk_summary(self, project_id: UUID) -> list[RiskCategory]:
        """Calculate risk scores by category."""
        facts = self.get_project_facts(project_id)
        if not facts:
            return []
        
        categories = []
        
        # Labor & Classification
        labor_score = 0
        labor_tasks = 0
        if facts.has_contractors:
            labor_score += 30 if "classification_memo_signed" not in facts.evidence_types_present else 0
            labor_tasks += 1 if "classification_memo_signed" not in facts.evidence_types_present else 0
        if facts.has_employees:
            labor_score += 20 if "workers_comp_policy" not in facts.evidence_types_present else 0
            labor_tasks += 1 if "workers_comp_policy" not in facts.evidence_types_present else 0
        categories.append(RiskCategory(
            id="labor",
            name="Labor & Classification",
            score=min(labor_score, 100),
            tasks=labor_tasks,
            status=self._score_to_status(labor_score),
        ))
        
        # Permits & Locations
        permit_score = 0
        permit_tasks = 0
        if facts.has_permit_locations:
            permit_score += 40 if "permit_approved" not in facts.evidence_types_present else 0
            permit_tasks += 1 if "permit_approved" not in facts.evidence_types_present else 0
            permit_score += 25 if "coi" not in facts.evidence_types_present else 0
            permit_tasks += 1 if "coi" not in facts.evidence_types_present else 0
        categories.append(RiskCategory(
            id="permits",
            name="Permits & Locations",
            score=min(permit_score, 100),
            tasks=permit_tasks,
            status=self._score_to_status(permit_score),
        ))
        
        # Insurance & Liability
        insurance_score = 0
        insurance_tasks = 0
        if facts.has_employees and "workers_comp_policy" not in facts.evidence_types_present:
            insurance_score += 35
            insurance_tasks += 1
        if "coi" not in facts.evidence_types_present and facts.has_permit_locations:
            insurance_score += 25
        categories.append(RiskCategory(
            id="insurance",
            name="Insurance & Liability",
            score=min(insurance_score, 100),
            tasks=insurance_tasks,
            status=self._score_to_status(insurance_score),
        ))
        
        # Union Compliance
        union_score = 0  # Placeholder - would need union affiliation data
        categories.append(RiskCategory(
            id="union",
            name="Union Compliance",
            score=union_score,
            tasks=0,
            status=self._score_to_status(union_score),
        ))
        
        # Minor Protection
        minor_score = 0
        minor_tasks = 0
        if facts.minor_involved:
            minor_score = 80 if "minor_work_permit" not in facts.evidence_types_present else 20
            minor_tasks = 2 if "minor_work_permit" not in facts.evidence_types_present else 0
        categories.append(RiskCategory(
            id="minors",
            name="Minor Protection",
            score=minor_score,
            tasks=minor_tasks,
            status=self._score_to_status(minor_score),
        ))
        
        # Safety & IIPP
        safety_score = 20  # Baseline check
        safety_tasks = 1
        if "iipp_policy" in facts.evidence_types_present:
            safety_score = 0
            safety_tasks = 0
        categories.append(RiskCategory(
            id="safety",
            name="Safety & IIPP",
            score=safety_score,
            tasks=safety_tasks,
            status=self._score_to_status(safety_score),
        ))
        
        return categories
    
    def _score_to_status(self, score: int) -> str:
        """Convert numeric score to status label."""
        if score >= 70:
            return "critical"
        elif score >= 50:
            return "high"
        elif score >= 25:
            return "medium"
        return "low"
    
    def get_guidance_items(self, project_id: UUID) -> list[GuidanceItem]:
        """Get prioritized guidance items based on project state."""
        facts = self.get_project_facts(project_id)
        if not facts:
            return []
        
        items = []
        today = date.today()
        
        # Generate guidance based on missing evidence and facts
        if facts.minor_involved and "minor_work_permit" not in facts.evidence_types_present:
            deadline = facts.first_shoot_date - timedelta(days=7) if facts.first_shoot_date else None
            items.append(GuidanceItem(
                id="minor-permit",
                title="Minor Work Permit (Form B1-4)",
                category="minors",
                priority="critical",
                deadline=deadline.isoformat() if deadline else None,
                days_until=(deadline - today).days if deadline else None,
                steps=[
                    {"id": 1, "text": "Parent/guardian completes Section A of Form B1-4", "completed": False},
                    {"id": 2, "text": "Production company completes Section B", "completed": False},
                    {"id": 3, "text": "Submit to CA Labor Commissioner", "completed": False, "link": "https://dir.ca.gov/dlse/permit.html"},
                ],
                documents_required=["Birth certificate or passport", "School enrollment verification"],
                estimated_time="5-7 business days",
                resource_url="https://dir.ca.gov/dlse/permit.html",
            ))
        
        if facts.has_permit_locations and "permit_approved" not in facts.evidence_types_present:
            deadline = facts.first_shoot_date - timedelta(days=7) if facts.first_shoot_date else None
            items.append(GuidanceItem(
                id="filmla-permit",
                title="FilmLA Permit Application",
                category="permits",
                priority="high",
                deadline=deadline.isoformat() if deadline else None,
                days_until=(deadline - today).days if deadline else None,
                steps=[
                    {"id": 1, "text": "Create FilmLA account", "completed": False},
                    {"id": 2, "text": "Complete online permit application", "completed": False},
                    {"id": 3, "text": "Upload insurance certificate (COI)", "completed": False},
                    {"id": 4, "text": "Pay permit fee", "completed": False},
                    {"id": 5, "text": "Await approval (2-3 days)", "completed": False},
                ],
                documents_required=["Certificate of Insurance", "Location agreement"],
                estimated_time="2-3 business days",
                resource_url="https://www.filmla.com/permits/",
            ))
        
        if facts.has_employees and "workers_comp_policy" not in facts.evidence_types_present:
            deadline = facts.first_shoot_date - timedelta(days=3) if facts.first_shoot_date else None
            items.append(GuidanceItem(
                id="workers-comp",
                title="Workers' Compensation Verification",
                category="insurance",
                priority="medium",
                deadline=deadline.isoformat() if deadline else None,
                days_until=(deadline - today).days if deadline else None,
                steps=[
                    {"id": 1, "text": "Obtain WC policy from insurance broker", "completed": False},
                    {"id": 2, "text": "Verify coverage includes all crew classifications", "completed": False},
                    {"id": 3, "text": "Upload policy to evidence locker", "completed": False},
                ],
                documents_required=["Workers' Comp Policy Declaration Page"],
                estimated_time="1 day",
            ))
        
        if facts.has_contractors and "classification_memo_signed" not in facts.evidence_types_present:
            items.append(GuidanceItem(
                id="classification-memo",
                title="Contractor Classification Memos",
                category="labor",
                priority="medium",
                steps=[
                    {"id": 1, "text": "Generate classification memo for each contractor", "completed": False},
                    {"id": 2, "text": "Have contractors sign and return", "completed": False},
                    {"id": 3, "text": "Upload to evidence locker", "completed": False},
                ],
                documents_required=["Classification Memo (per contractor)"],
                estimated_time="1-2 days",
            ))
        
        # Sort by priority
        priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        items.sort(key=lambda x: priority_order.get(x.priority, 4))
        
        return items
