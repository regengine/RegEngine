from typing import Dict, Any, List, Optional
from uuid import UUID
from datetime import datetime
import textwrap
import structlog

from .schemas import HealthcareProjectMetadata, HealthcareRuleStatus
# from services.graph.app.neo4j_utils import Neo4jClient

# In a real app, we'd import these from a shared module
# from services.admin.app.models import VerticalProject, VerticalRuleInstance

from sqlalchemy.orm import Session

logger = structlog.get_logger(__name__)

class HealthcareVerticalService:
    def __init__(self, db_session: Session):
        self.db = db_session
        self.rule_pack_id = "mscf_v1"

    async def create_clinic_project(
        self, 
        tenant_id: UUID, 
        name: str, 
        metadata: HealthcareProjectMetadata, 
        user_id: Optional[UUID] = None
    ) -> Dict[str, Any]:
        """
        Creates a new Healthcare project (Clinic) and instantiates the MSCF rule set.
        """
        from app.sqlalchemy_models import VerticalProjectModel, VerticalRuleInstanceModel
        
        # 1. Create the generic vertical project
        project = VerticalProjectModel(
            tenant_id=tenant_id,
            name=name,
            vertical="healthcare",
            vertical_metadata=metadata.dict(),
            created_by=user_id
        )
        self.db.add(project)
        self.db.flush() # distinct flush to get ID
        
        project_id = project.id
        
        # 2. Instantiate Rules based on Metadata
        rules_to_create = self._get_applicable_rules(metadata)
        
        created_rules = []
        for rule_def in rules_to_create:
            instance = VerticalRuleInstanceModel(
                project_id=project_id,
                rule_id=rule_def["id"],
                status=rule_def["status"]
            )
            self.db.add(instance)
            created_rules.append(rule_def)
            
        self.db.commit()
            
        return {
            "id": str(project_id),
            "name": name,
            "vertical": "healthcare",
            "metadata": metadata.dict(),
            "rule_count": len(created_rules),
            "status": "active"
        }

    def _load_rule_pack(self) -> Dict[str, Any]:
        """
        Loads the official MSCF v1 RulePack from the JSON source of truth.
        """
        import json
        import os
        from pathlib import Path
        
        # Resolve path relative to this file
        current_dir = Path(__file__).parent
        json_path = current_dir / "data" / "mscf_v1.json"
        
        with open(json_path, "r") as f:
            return json.load(f)

    def _get_applicable_rules(self, metadata: HealthcareProjectMetadata) -> List[Dict[str, Any]]:
        """
        Returns the list of rules from mscf_v1 that apply to this clinic.
        Dynamically filters based on JSON 'condition' fields.
        """
        rule_pack = self._load_rule_pack()
        applicable_rules = []
        
        for category in rule_pack.get("categories", []):
            for rule in category.get("rules", []):
                # Check condition if present
                if "condition" in rule:
                    # Simple eval for MVP (safe because we control the JSON)
                    # Support: dispenses_medication
                    condition = rule["condition"]
                    if "dispenses_medication" in condition:
                        # Parse condition logic (very basic for now)
                        # "dispenses_medication == true"
                        wanted = True if "true" in condition else False
                        if metadata.dispenses_medication != wanted:
                            continue
                            
                # Default status for new projects is RED (Non-Compliant until proven otherwise)
                rule_instance = {
                    "id": rule["id"],
                    "name": rule["name"],
                    "status": HealthcareRuleStatus.RED, 
                    "severity": rule.get("severity", "medium")
                }
                
                applicable_rules.append(rule_instance)
            
        return applicable_rules

    async def evaluate_safety_status(self, project_id: UUID, current_rules: List[Dict[str, Any]]) -> str:
        """
        The "Control Evaluation Engine".
        Determines if the clinic is "Safe to Operate" (Green/Yellow/Red).
        
        Logic:
        - ANY Critical Red Rule -> Project RED
        - ANY High Red Rule -> Project RED
        - > 3 Medium Red Rules -> Project YELLOW
        - Else -> GREEN (if all Critical/High are Green/Yellow)
        """
        medium_red_count = 0
        
        # Load severity map dynamically if not present in input, but our _get_applicable_rules now attaches it
        # If input comes from API, it might not have severity, so we re-map if needed.
        # Ideally, current_rules has 'severity' or we re-fetch the pack.
        # optimizing: Assume input might just be statuses, so let's load the pack to be safe.
        rule_pack = self._load_rule_pack()
        # Flatten pack for lookup
        severity_lookup = {}
        for cat in rule_pack["categories"]:
            for r in cat["rules"]:
                severity_lookup[r["id"]] = r.get("severity", "medium")

        for rule in current_rules:
            rule_id = rule["id"]
            status = rule["status"]
            # Trust input severity if present, else lookup
            severity = rule.get("severity", severity_lookup.get(rule_id, "medium"))
            
            if status == HealthcareRuleStatus.RED:
                if severity == "critical":
                    return HealthcareRuleStatus.RED
                elif severity == "high":
                    return HealthcareRuleStatus.RED
                elif severity == "medium":
                    medium_red_count += 1
        
        if medium_red_count > 3:
            return HealthcareRuleStatus.YELLOW
            
        return HealthcareRuleStatus.GREEN

    async def log_evidence(
        self,
        tenant_id: UUID,
        project_id: UUID,
        rule_id: str,
        evidence_type: str,
        data: Dict[str, Any],
        user_id: Optional[UUID] = None
    ) -> str:
        """
        Constitution 2.1: Writes to the Immutable Evidence Vault.
        Generates a SHA-256 hash of the content to ensure integrity.
        """
        import hashlib
        import json
        
        # 1. Deterministic Content Hash
        payload_str = json.dumps(data, sort_keys=True)
        content_hash = hashlib.sha256(payload_str.encode("utf-8")).hexdigest()
        
        # 2. Insert into Evidence Log (Constitution 2.1: Immutable Vault)
        from app.sqlalchemy_models import EvidenceLogModel
        
        evidence_entry = EvidenceLogModel(
            tenant_id=tenant_id,
            project_id=project_id,
            rule_id=rule_id,
            evidence_type=evidence_type,
            data=data,
            content_hash=content_hash,
            created_by=user_id,
            created_at=datetime.utcnow()
        )
        self.db.add(evidence_entry)
        self.db.commit()
        
        logger.info(
            "immutable_vault_evidence_persisted",
            rule_id=rule_id,
            content_hash=content_hash
        )
        return content_hash

    async def generate_lifeboat_archive(self, tenant_id: UUID, project_id: UUID) -> bytes:
        """
        Constitution 5.1: Generates a portable ZIP archive of the clinic's compliance state.
        Includes:
        - metadata.json (Clinic info)
        - status.json (Current Rule Statuses)
        - evidence/ (Directory of all immutable evidence logs)
        """
        import io
        import zipfile
        import json
        
        # 1. Fetch Data (Mocking fetching for now as per existing service patterns)
        # In real app: project = await self.db.execute(...)
        metadata = {
            "tenant_id": str(tenant_id),
            "project_id": str(project_id),
            "generated_at": datetime.utcnow().isoformat(),
            "software_version": "RegEngine MSCF v1.0"
        }
        
        # Mock Rule Statuses (reusing logic for demo)
        # In prod this would be: current_rules = await self.get_project_rules(project_id)
        current_rules = self._get_applicable_rules(HealthcareProjectMetadata(
            facility_type="free_clinic", 
            dispenses_medication=True, 
            operating_state="active",
            state="CA",
            annual_patient_volume=1000
        ))
        
        # 2. Build Archive
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            # Add Metadata
            zip_file.writestr("clinic_metadata.json", json.dumps(metadata, indent=2))
            
            # Add Status
            zip_file.writestr("compliance_status.json", json.dumps(current_rules, indent=2))
            
            # Add README (Constitution Requirement: "Readable without software")
            readme = """
            REG-ENGINE LIFEBOAT ARCHIVE
            ===========================
            This archive contains the full compliance state of your clinic.
            It is designed to be readable by any standard computer without specialized software.
            
            CONTENTS:
            - clinic_metadata.json: Basic information about this export.
            - compliance_status.json: The last known status of your safety controls.
            - evidence/: Folder containing immutable logs of your compliance activities.
            """
            zip_file.writestr("README.txt", textwrap.dedent(readme))
            
            # Mock Evidence Logs (Simulating DB fetch)
            evidence_logs = [
                {"id": "evt_1", "rule": "GOV-01", "hash": "sha256_mock_1...", "data": {"doc": "501c3.pdf"}},
                {"id": "evt_2", "rule": "CLIN-01", "hash": "sha256_mock_2...", "data": {"license": "MD-12345"}}
            ]
            
            for log in evidence_logs:
                zip_file.writestr(f"evidence/{log['id']}.json", json.dumps(log, indent=2))
                
        buffer.seek(0)
        return buffer.getvalue()
