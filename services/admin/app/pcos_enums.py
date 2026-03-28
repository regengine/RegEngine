"""
Production Compliance OS (PCOS) Enums

Python representations of PostgreSQL enums used by PCOS domain models.
Extracted from pcos_models.py for cleaner separation of concerns.
"""

from enum import Enum


class LocationType(str, Enum):
    """Types of filming locations."""
    CERTIFIED_STUDIO = "certified_studio"
    PRIVATE_PROPERTY = "private_property"
    RESIDENTIAL = "residential"
    PUBLIC_ROW = "public_row"


class ClassificationType(str, Enum):
    """Worker classification types."""
    EMPLOYEE = "employee"
    CONTRACTOR = "contractor"


class TaskStatus(str, Enum):
    """Status of compliance tasks."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"


class GateState(str, Enum):
    """Project gate states for go/no-go decisions."""
    DRAFT = "draft"
    READY_FOR_REVIEW = "ready_for_review"
    GREENLIT = "greenlit"
    IN_PRODUCTION = "in_production"
    WRAP = "wrap"
    ARCHIVED = "archived"


class EntityType(str, Enum):
    """Legal entity types."""
    SOLE_PROPRIETOR = "sole_proprietor"
    LLC_SINGLE_MEMBER = "llc_single_member"
    LLC_MULTI_MEMBER = "llc_multi_member"
    S_CORP = "s_corp"
    C_CORP = "c_corp"
    PARTNERSHIP = "partnership"


class OwnerPayMode(str, Enum):
    """Owner compensation methods."""
    DRAW = "draw"
    PAYROLL = "payroll"


class RegistrationType(str, Enum):
    """Types of business registrations."""
    SOS = "sos"  # Secretary of State
    FTB = "ftb"  # Franchise Tax Board
    BTRC = "btrc"  # LA Business Tax Registration Certificate
    DBA_FBN = "dba_fbn"  # DBA / Fictitious Business Name
    EDD = "edd"  # Employment Development Department
    DIR = "dir"  # Department of Industrial Relations


class InsuranceType(str, Enum):
    """Types of insurance policies."""
    GENERAL_LIABILITY = "general_liability"
    WORKERS_COMP = "workers_comp"
    ERRORS_OMISSIONS = "errors_omissions"
    EQUIPMENT = "equipment"
    AUTO = "auto"
    UMBRELLA = "umbrella"


class EvidenceType(str, Enum):
    """Types of evidence documents."""
    COI = "coi"
    PERMIT_APPROVED = "permit_approved"
    CLASSIFICATION_MEMO_SIGNED = "classification_memo_signed"
    WORKERS_COMP_POLICY = "workers_comp_policy"
    IIPP_POLICY = "iipp_policy"
    WVPP_POLICY = "wvpp_policy"
    W9 = "w9"
    I9 = "i9"
    W4 = "w4"
    VENDOR_COI = "vendor_coi"
    MINOR_WORK_PERMIT = "minor_work_permit"
    SIGNED_CONTRACT = "signed_contract"
    LOCATION_RELEASE = "location_release"
    TALENT_RELEASE = "talent_release"
    PAYSTUB = "paystub"
    TRAINING_RECORD = "training_record"
    OTHER = "other"


class ProjectType(str, Enum):
    """Types of production projects."""
    COMMERCIAL = "commercial"
    NARRATIVE_FEATURE = "narrative_feature"
    NARRATIVE_SHORT = "narrative_short"
    DOCUMENTARY = "documentary"
    MUSIC_VIDEO = "music_video"
    BRANDED_CONTENT = "branded_content"
    STILL_PHOTO = "still_photo"
    OTHER = "other"


class Jurisdiction(str, Enum):
    """Geographic jurisdictions for compliance."""
    LA_CITY = "la_city"
    LA_COUNTY = "la_county"
    CA_OTHER = "ca_other"
    OUT_OF_STATE = "out_of_state"
