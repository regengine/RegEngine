"""
Standalone Graph Arbitrage Demo API
Self-contained FastAPI application with in-memory data
No external dependencies on shared modules or Neo4j
"""

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Optional
from enum import Enum

# ============================================================================
# DATA MODELS
# ============================================================================

class Effort(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

class Priority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

class Control(BaseModel):
    control_id: str
    requirement: str
    description: Optional[str] = None
    effort_hours: float = 4.0

class ControlMapping(BaseModel):
    control_from: str
    control_to: str
    confidence: float = 1.0
    requirement_from: Optional[str] = None
    requirement_to: Optional[str] = None

class ArbitrageOpportunity(BaseModel):
    id: str
    from_framework: str
    to_framework: str
    overlap_controls: int
    total_controls: int
    overlap_percentage: float
    estimated_savings_hours: float
    path: List[ControlMapping] = []

class ComplianceGap(BaseModel):
    control_id: str
    control_name: str
    missing_in: str
    description: Optional[str] = None
    remediation_effort: Effort
    priority: Priority
    estimated_hours: float = 4.0

class FrameworkRelationship(BaseModel):
    framework_id: str
    framework_name: str
    relationship_type: str
    strength: float
    control_overlap: int

# ============================================================================
# IN-MEMORY DATA STORE
# ============================================================================

FRAMEWORKS = {
    "SOC2": {
        "name": "SOC 2",
        "version": "2017",
        "category": "Security and Privacy",
        "controls": [
            {"id": "CC6.1", "req": "Logical access controls", "hours": 8.0},
            {"id": "CC6.2", "req": "User identification", "hours": 4.0},
            {"id": "CC6.3", "req": "Network security", "hours": 6.0},
            {"id": "CC7.1", "req": "Security event detection", "hours": 12.0},
            {"id": "CC7.2", "req": "Incident response", "hours": 8.0},
        ]
    },
    "ISO27001": {
        "name": "ISO 27001",
        "version": "2022",
        "category": "Information Security",
        "controls": [
            {"id": "A.9.2.1", "req": "User registration", "hours": 4.0},
            {"id": "A.9.2.2", "req": "User access provisioning", "hours": 4.0},
            {"id": "A.9.4.1", "req": "Information access restriction", "hours": 6.0},
            {"id": "A.12.4.1", "req": "Event logging", "hours": 8.0},
            {"id": "A.16.1.1", "req": "Incident management", "hours": 12.0},
        ]
    },
    "HIPAA": {
        "name": "HIPAA",
        "version": "2013",
        "category": "Healthcare Privacy",
        "controls": [
            {"id": "164.308(a)(1)", "req": "Security Management", "hours": 16.0},
            {"id": "164.308(a)(3)", "req": "Workforce Security", "hours": 8.0},
            {"id": "164.308(a)(4)", "req": "Access Management", "hours": 6.0},
            {"id": "164.312(a)(1)", "req": "Access Control", "hours": 8.0},
            {"id": "164.312(b)", "req": "Audit Controls", "hours": 12.0},
        ]
    },
    "NIST_CSF": {
        "name": "NIST CSF",
        "version": "1.1",
        "category": "Cybersecurity",
        "controls": [
            {"id": "ID.AM-1", "req": "Asset inventory", "hours": 4.0},
            {"id": "PR.AC-1", "req": "Identity management", "hours": 6.0},
            {"id": "PR.AC-4", "req": "Access permissions", "hours": 6.0},
            {"id": "DE.CM-1", "req": "Network monitoring", "hours": 8.0},
            {"id": "RS.RP-1", "req": "Response plan", "hours": 12.0},
        ]
    },
    "PCI_DSS": {
        "name": "PCI-DSS",
        "version": "4.0",
        "category": "Payment Security",
        "controls": [
            {"id": "1.1.1", "req": "Firewall configuration", "hours": 8.0},
            {"id": "2.2.1", "req": "Configuration standards", "hours": 6.0},
            {"id": "8.2.1", "req": "User identification", "hours": 4.0},
            {"id": "10.2.1", "req": "Audit logs", "hours": 8.0},
            {"id": "12.10.1", "req": "Incident response plan", "hours": 16.0},
        ]
    }
}

# Simulated control overlaps (for demo purposes)
CONTROL_OVERLAPS = [
    ("CC6.2", "A.9.2.1"),  # SOC2 <-> ISO27001: User ID
    ("CC6.2", "8.2.1"),     # SOC2 <-> PCI-DSS: User ID
    ("A.9.2.1", "8.2.1"),   # ISO27001 <-> PCI-DSS: User ID
    ("CC7.1", "A.12.4.1"),  # SOC2 <-> ISO27001: Logging
    ("CC7.1", "10.2.1"),    # SOC2 <-> PCI-DSS: Logging
    ("A.12.4.1", "10.2.1"), # ISO27001 <-> PCI-DSS: Logging
]

# ============================================================================
# FASTAPI APPLICATION
# ============================================================================

app = FastAPI(
    title="Graph Arbitrage Demo API",
    version="1.0.0-demo",
    description="Standalone demo of framework arbitrage detection (no Neo4j required)",
)
from shared.cors import get_allowed_origins, should_allow_credentials

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_allowed_origins(),
    allow_credentials=should_allow_credentials(),
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_control(framework_key: str, control_id: str):
    """Get control details from framework"""
    framework = FRAMEWORKS.get(framework_key)
    if not framework:
        return None
    for ctrl in framework["controls"]:
        if ctrl["id"] == control_id:
            return ctrl
    return None

def find_overlaps(from_fw: str, to_fw: str):
    """Find overlapping controls between two frameworks"""
    from_controls = {c["id"] for c in FRAMEWORKS.get(from_fw, {}).get("controls", [])}
    to_controls = {c["id"] for c in FRAMEWORKS.get(to_fw, {}).get("controls", [])}
    
    overlaps = []
    for c1, c2 in CONTROL_OVERLAPS:
        if c1 in from_controls and c2 in to_controls:
            overlaps.append((c1, c2))
        elif c2 in from_controls and c1 in to_controls:
            overlaps.append((c2, c1))
    
    return overlaps

# ============================================================================
# API ENDPOINTS
# ============================================================================

@app.get("/")
async def root():
    """Service information"""
    return {
        "service": "Graph Arbitrage Demo API",
        "version": "1.0.0-demo",
        "status": "operational",
        "mode": "standalone-demo",
        "note": "In-memory data, no Neo4j required",
        "endpoints": {
            "docs": "/docs",
            "arbitrage": "/graph/arbitrage?framework_from=SOC2&framework_to=ISO27001",
            "gaps": "/graph/gaps?current_framework=SOC2&target_framework=HIPAA",
            "relationships": "/graph/frameworks/SOC2/relationships",
            "frameworks": "/graph/frameworks",
        }
    }

@app.get("/health")
async def health():
    """Health check"""
    return {"status": "healthy", "mode": "demo"}

@app.get("/graph/frameworks")
async def list_frameworks():
    """List all available frameworks"""
    frameworks = []
    for key, data in FRAMEWORKS.items():
        frameworks.append({
            "id": key,
            "name": data["name"],
            "version": data["version"],
            "category": data["category"],
            "control_count": len(data["controls"])
        })
    return {"count": len(frameworks), "frameworks": frameworks}

@app.get("/graph/arbitrage")
async def find_arbitrage(
    framework_from: str = Query(..., description="Source framework"),
    framework_to: str = Query(..., description="Target framework")
):
    """Find arbitrage opportunities between frameworks"""
    from_fw = FRAMEWORKS.get(framework_from)
    to_fw = FRAMEWORKS.get(framework_to)
    
    if not from_fw:
        raise HTTPException(404, f"Framework {framework_from} not found")
    if not to_fw:
        raise HTTPException(404, f"Framework {framework_to} not found")
    
    overlaps = find_overlaps(framework_from, framework_to)
    total_controls = len(to_fw["controls"])
    overlap_count = len(overlaps)
    
    mappings = []
    total_savings = 0.0
    
    for from_id, to_id in overlaps:
        from_ctrl = get_control(framework_from, from_id)
        to_ctrl = get_control(framework_to, to_id)
        
        if from_ctrl and to_ctrl:
            mappings.append(ControlMapping(
                control_from=from_id,
                control_to=to_id,
                confidence=1.0,
                requirement_from=from_ctrl["req"],
                requirement_to=to_ctrl["req"]
            ))
            total_savings += to_ctrl["hours"]
    
    opportunity = ArbitrageOpportunity(
        id=f"arb-{framework_from.lower()}-{framework_to.lower()}",
        from_framework=framework_from,
        to_framework=framework_to,
        overlap_controls=overlap_count,
        total_controls=total_controls,
        overlap_percentage=round((overlap_count / total_controls * 100), 2),
        estimated_savings_hours=total_savings,
        path=mappings
    )
    
    return {"opportunities": [opportunity]}

@app.get("/graph/gaps")
async def analyze_gaps(
    current_framework: str = Query(..., description="Current framework"),
    target_framework: str = Query(..., description="Target framework")
):
    """Identify compliance gaps"""
    current = FRAMEWORKS.get(current_framework)
    target = FRAMEWORKS.get(target_framework)
    
    if not current:
        raise HTTPException(404, f"Framework {current_framework} not found")
    if not target:
        raise HTTPException(404, f"Framework {target_framework} not found")
    
    # Find controls in target but not in current (simplified)
    current_reqs = {c["req"] for c in current["controls"]}
    
    gaps = []
    total_hours = 0.0
    
    for ctrl in target["controls"]:
        if ctrl["req"] not in current_reqs:
            hours = ctrl["hours"]
            total_hours += hours
            
            if hours <= 4:
                effort, priority = Effort.LOW, Priority.HIGH
            elif hours <= 12:
                effort, priority = Effort.MEDIUM, Priority.MEDIUM
            else:
                effort, priority = Effort.HIGH, Priority.LOW
            
            gaps.append(ComplianceGap(
                control_id=ctrl["id"],
                control_name=ctrl["req"],
                missing_in=current_framework,
                remediation_effort=effort,
                priority=priority,
                estimated_hours=hours
            ))
    
    covered = len(target["controls"]) - len(gaps)
    coverage = (covered / len(target["controls"]) * 100)
    
    return {
        "gaps": gaps,
        "coverage_percentage": round(coverage, 2),
        "total_gaps": len(gaps),
        "estimated_total_hours": round(total_hours, 2)
    }

@app.get("/graph/frameworks/{framework_id}/relationships")
async def get_relationships(framework_id: str):
    """Get framework relationships"""
    if framework_id not in FRAMEWORKS:
        raise HTTPException(404, f"Framework {framework_id} not found")
    
    relationships = []
    
    for other_id, other_data in FRAMEWORKS.items():
        if other_id == framework_id:
            continue
        
        overlaps = find_overlaps(framework_id, other_id)
        if not overlaps:
            continue
        
        overlap_count = len(overlaps)
        total = len(other_data["controls"])
        strength = overlap_count / total
        
        relationships.append(FrameworkRelationship(
            framework_id=other_id,
            framework_name=other_data["name"],
            relationship_type="maps_to",
            strength=round(strength, 3),
            control_overlap=overlap_count
        ))
    
    # Sort by strength
    relationships.sort(key=lambda x: x.strength, reverse=True)
    
    return {
        "framework": framework_id,
        "related_frameworks": relationships
    }

# Run with: uvicorn demo_api:app --reload --port 8003
