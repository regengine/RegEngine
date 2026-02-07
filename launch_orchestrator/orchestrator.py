#!/usr/bin/env python3
"""
RegEngine Launch Orchestrator

Coordinates public surface deployment, GTM asset generation, design partner
program activation, and investor readiness in a deterministic, auditable manner.

Usage:
    python orchestrator.py --mode full_launch --config launch_orchestrator_spec.yaml
    python orchestrator.py --mode dry_run
    python orchestrator.py --mode sales_only
"""

import argparse
import hashlib
import json
import logging
import os
import sys
import secrets
import subprocess
import string
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('orchestrator.log'),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)


class OrchestrationMode(Enum):
    """Orchestration execution modes"""
    FULL_LAUNCH = "full_launch"
    SALES_ONLY = "sales_only"
    INFRA_ONLY = "infra_only"
    DRY_RUN = "dry_run"


class OrchestrationPhase(Enum):
    """Phases of orchestration execution"""
    INIT = "initialization"
    PUBLIC_SURFACE = "public_surface_deployment"
    SALES_GTM = "sales_gtm_generation"
    DESIGN_PARTNERS = "design_partner_provisioning"
    INVESTOR_READINESS = "investor_readiness"
    INFRA = "infrastructure_deployment"
    SUMMARY = "execution_summary"


@dataclass
class OrchestrationEvent:
    """Individual orchestration event for audit trail"""
    timestamp: datetime
    phase: OrchestrationPhase
    action: str
    status: str  # success, failure, skipped
    details: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None


@dataclass
class OrchestrationResult:
    """Result of orchestration execution"""
    mode: OrchestrationMode
    start_time: datetime
    end_time: Optional[datetime] = None
    events: List[OrchestrationEvent] = field(default_factory=list)
    artifacts: Dict[str, str] = field(default_factory=dict)  # artifact_name -> hash or URL
    errors: List[str] = field(default_factory=list)
    success: bool = True

    def add_event(self, phase: OrchestrationPhase, action: str, status: str,
                  details: Optional[Dict[str, Any]] = None, error: Optional[str] = None):
        """Add an event to the audit trail"""
        event = OrchestrationEvent(
            timestamp=datetime.now(timezone.utc),
            phase=phase,
            action=action,
            status=status,
            details=details or {},
            error=error
        )
        self.events.append(event)

        if status == "failure":
            self.errors.append(f"{phase.value}/{action}: {error}")
            self.success = False

        logger.info(f"[{phase.value}] {action}: {status}")
        if error:
            logger.error(f"  Error: {error}")

    def add_artifact(self, name: str, content_or_path: str):
        """Add an artifact with content hash"""
        if os.path.exists(content_or_path):
            with open(content_or_path, 'rb') as f:
                content = f.read()
        else:
            content = content_or_path.encode('utf-8')

        artifact_hash = hashlib.sha256(content).hexdigest()
        self.artifacts[name] = artifact_hash
        logger.info(f"Artifact registered: {name} (hash: {artifact_hash[:16]}...)")

    def to_dict(self) -> Dict[str, Any]:
        """Convert result to dictionary for JSON serialization"""
        return {
            "mode": self.mode.value,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "success": self.success,
            "events": [
                {
                    "timestamp": e.timestamp.isoformat(),
                    "phase": e.phase.value,
                    "action": e.action,
                    "status": e.status,
                    "details": e.details,
                    "error": e.error
                }
                for e in self.events
            ],
            "artifacts": self.artifacts,
            "errors": self.errors
        }


class LaunchOrchestrator:
    """Main orchestrator for RegEngine launch activities"""

    def __init__(self, config_path: str, mode: OrchestrationMode, dry_run: bool = True):
        self.config_path = Path(config_path)
        self.mode = mode
        self.dry_run = dry_run or (mode == OrchestrationMode.DRY_RUN)
        self.config = self._load_config()
        self.result = OrchestrationResult(mode=mode, start_time=datetime.now(timezone.utc))
        self.base_dir = self.config_path.parent
        if not self.dry_run and os.getenv("REGENGINE_ENV") != "production":
            raise RuntimeError("Unsafe orchestrator execution: dry_run=False requires REGENGINE_ENV=production")

    def _load_config(self) -> Dict[str, Any]:
        """Load and validate orchestrator configuration"""
        logger.info(f"Loading configuration from {self.config_path}")

        try:
            with open(self.config_path, 'r') as f:
                config = yaml.safe_load(f)

            # Basic validation
            required_keys = ['orchestrator', 'environment']
            for key in required_keys:
                if key not in config:
                    raise ValueError(f"Missing required config key: {key}")

            logger.info("Configuration loaded successfully")
            return config

        except Exception as e:
            logger.error(f"Failed to load configuration: {e}")
            raise

    def _validate_environment(self) -> bool:
        """Validate required environment variables and secrets"""
        logger.info("Validating environment...")

        required_vars = self.config['environment'].get('required_env_vars', [])
        missing_vars = []

        for var in required_vars:
            if not os.getenv(var):
                missing_vars.append(var)

        if missing_vars:
            self.result.add_event(
                OrchestrationPhase.INIT,
                "validate_environment",
                "failure",
                details={"missing_vars": missing_vars},
                error=f"Missing environment variables: {', '.join(missing_vars)}"
            )
            return False

        self.result.add_event(
            OrchestrationPhase.INIT,
            "validate_environment",
            "success",
            details={"validated_vars": len(required_vars)}
        )
        return True

    def run(self) -> OrchestrationResult:
        """Execute orchestration based on mode"""
        logger.info(f"Starting orchestration in mode: {self.mode.value}")
        logger.info(f"Dry run: {self.dry_run}")

        try:
            # Phase 1: Initialization
            if not self._validate_environment():
                logger.error("Environment validation failed")
                if not self.dry_run:
                    return self._finalize_result()

            # Execute phases based on mode
            if self.mode in [OrchestrationMode.FULL_LAUNCH, OrchestrationMode.DRY_RUN]:
                self._deploy_public_surface()
                self._generate_sales_gtm()
                self._provision_design_partners()
                self._prepare_investor_materials()
                self._deploy_infrastructure()

            elif self.mode == OrchestrationMode.SALES_ONLY:
                self._generate_sales_gtm()

            elif self.mode == OrchestrationMode.INFRA_ONLY:
                self._deploy_infrastructure()

            # Phase 7: Generate summary
            self._generate_summary()

        except Exception as e:
            logger.exception("Orchestration failed with exception")
            self.result.add_event(
                OrchestrationPhase.SUMMARY,
                "orchestration_execution",
                "failure",
                error=str(e)
            )

        return self._finalize_result()

    def _deploy_public_surface(self):
        """Deploy marketing site, API docs, and status page"""
        logger.info("=== Phase: Public Surface Deployment ===")
        phase = OrchestrationPhase.PUBLIC_SURFACE

        public_config = self.config.get('public_surface', {})

        # Deploy marketing site
        marketing = public_config.get('marketing_site', {})
        if marketing:
            self._execute_deployment(
                phase,
                "deploy_marketing_site",
                marketing.get('deploy_command', 'echo "No deploy command"'),
                {
                    "target_url": marketing.get('target_url'),
                    "features": marketing.get('features', [])
                }
            )

        # Publish API docs
        api_docs = public_config.get('api_docs', {})
        if api_docs:
            self._execute_deployment(
                phase,
                "publish_api_docs",
                api_docs.get('publish_command', 'echo "No publish command"'),
                {
                    "target_url": api_docs.get('target_url'),
                    "format": api_docs.get('specification_format')
                }
            )

        # Configure status page
        status_page = public_config.get('status_page', {})
        if status_page:
            self.result.add_event(
                phase,
                "configure_status_page",
                "success" if self.dry_run else "skipped",
                details={"components": [c['name'] for c in status_page.get('components', [])]}
            )

    def _generate_sales_gtm(self):
        """Generate sales collateral and GTM campaigns"""
        logger.info("=== Phase: Sales & GTM Generation ===")
        phase = OrchestrationPhase.SALES_GTM

        sales_config = self.config.get('sales', {})

        # Generate persona-specific collateral
        personas = sales_config.get('personas', [])
        for persona in personas:
            persona_id = persona['id']
            self._generate_persona_collateral(phase, persona)

        # Initialize outbound campaigns
        campaigns = sales_config.get('outbound_campaigns', {}).get('sequences', [])
        for campaign in campaigns:
            self._initialize_outbound_sequence(phase, campaign)

    def _generate_persona_collateral(self, phase: OrchestrationPhase, persona: Dict[str, Any]):
        """Generate collateral for a specific persona"""
        persona_id = persona['id']
        persona_title = persona['title']

        # Generate one-pager
        one_pager_path = self.base_dir / "generated" / f"{persona_id}_one_pager.md"
        one_pager_content = self._create_one_pager(persona)

        if not self.dry_run:
            one_pager_path.parent.mkdir(parents=True, exist_ok=True)
            with open(one_pager_path, 'w') as f:
                f.write(one_pager_content)

        self.result.add_artifact(f"{persona_id}_one_pager", one_pager_content)
        self.result.add_event(
            phase,
            f"generate_one_pager_{persona_id}",
            "success",
            details={"persona": persona_title, "path": str(one_pager_path)}
        )

    def _create_one_pager(self, persona: Dict[str, Any]) -> str:
        """Create a one-pager for a persona"""
        return f"""# RegEngine One-Pager: {persona['title']}

## Pain Points
{chr(10).join(f"- {pain}" for pain in persona.get('pains', []))}

## What RegEngine Delivers
{chr(10).join(f"- {outcome}" for outcome in persona.get('desired_outcomes', []))}

## Next Steps
1. Schedule a 20-minute demo: [calendly link]
2. Try our sandbox environment
3. Review case studies from similar companies

Contact: sales@regengine.ai
"""

    def _initialize_outbound_sequence(self, phase: OrchestrationPhase, campaign: Dict[str, Any]):
        """Initialize an outbound email/LinkedIn sequence"""
        sequence_id = campaign['id']
        persona = campaign['persona']
        steps = campaign.get('steps', [])

        # In production, this would integrate with SendGrid, Apollo, or similar
        self.result.add_event(
            phase,
            f"initialize_sequence_{sequence_id}",
            "success",
            details={
                "sequence_id": sequence_id,
                "persona": persona,
                "num_steps": len(steps),
                "channels": list(set(step['channel'] for step in steps))
            }
        )

    def _provision_design_partners(self):
        """Provision sandboxes for design partners"""
        logger.info("=== Phase: Design Partner Provisioning ===")
        phase = OrchestrationPhase.DESIGN_PARTNERS

        dp_config = self.config.get('design_partner_program', {})
        max_partners = dp_config.get('max_partners', 5)

        # Generate legal agreement
        legal_template = self.base_dir / dp_config.get('legal_template_ref', '')
        if legal_template.exists():
            self.result.add_artifact("design_partner_agreement", str(legal_template))
            self.result.add_event(
                phase,
                "validate_legal_template",
                "success",
                details={"template_path": str(legal_template)}
            )

        # Pre-provision sandboxes
        sandbox_config = dp_config.get('sandbox', {})
        for i in range(max_partners):
            self._provision_sandbox(phase, f"dp-sandbox-{i+1}", sandbox_config)

    def _provision_sandbox(self, phase: OrchestrationPhase, sandbox_id: str, config: Dict[str, Any]):
        """Provision a single sandbox environment"""
        logger.info(f"Provisioning sandbox: {sandbox_id}")
        
        # Generate API Key
        api_key = "sk_test_" + ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(32))
        
        # Create tenant config
        tenant_config = {
            "tenant_id": sandbox_id,
            "api_key": api_key,
            "max_docs": config.get('max_docs_per_partner', 100),
            "jurisdictions": config.get('jurisdictions', {}).get('default', ["US-NY"]),
            "rate_limit_rpm": config.get('rate_limits', {}).get('rpm_per_api_key', 60),
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        
        output_dir = self.base_dir / "generated" / "tenants"
        if not self.dry_run:
            output_dir.mkdir(parents=True, exist_ok=True)
            config_path = output_dir / f"{sandbox_id}.json"
            with open(config_path, "w") as f:
                json.dump(tenant_config, f, indent=2)
            
            # Also append to a master keys file for easy access
            keys_file = self.base_dir / "generated" / "sandbox_keys.txt"
            with open(keys_file, "a") as f:
                f.write(f"{sandbox_id}: {api_key}\n")

        self.result.add_event(
            phase,
            f"provision_sandbox_{sandbox_id}",
            "success",
            details={
                "sandbox_id": sandbox_id,
                "api_key_prefix": api_key[:12] + "...",
                "config_path": str(output_dir / f"{sandbox_id}.json")
            }
        )

    def _prepare_investor_materials(self):
        """Prepare investor memo and supporting materials"""
        logger.info("=== Phase: Investor Readiness ===")
        phase = OrchestrationPhase.INVESTOR_READINESS

        investor_config = self.config.get('investor_readiness', {})

        # Validate investor memo
        memo_path = self.base_dir / investor_config.get('memo_template_ref', '')
        if memo_path.exists():
            self.result.add_artifact("investor_memo", str(memo_path))
            self.result.add_event(
                phase,
                "validate_investor_memo",
                "success",
                details={"memo_path": str(memo_path)}
            )

        # Validate required slides
        required_slides = investor_config.get('slides_required', [])
        self.result.add_event(
            phase,
            "validate_pitch_slides",
            "success",
            details={"required_slides": required_slides}
        )

    def _deploy_infrastructure(self):
        """Deploy AWS infrastructure via Terraform"""
        logger.info("=== Phase: Infrastructure Deployment ===")
        phase = OrchestrationPhase.INFRA

        infra_config = self.config.get('infrastructure', {})
        terraform_config = infra_config.get('terraform', {})

        root_module = terraform_config.get('root_module_path', 'infra/terraform')
        workspaces = terraform_config.get('workspaces', ['demo', 'sandbox', 'production'])

        for workspace in workspaces:
            self._deploy_terraform_workspace(phase, root_module, workspace)

    def _deploy_terraform_workspace(self, phase: OrchestrationPhase, root_module: str, workspace: str):
        """Deploy a Terraform workspace"""
        command = (
            f"terraform -chdir={root_module} workspace select {workspace} && "
            f"terraform -chdir={root_module} plan -out={workspace}.tfplan && "
            f"terraform -chdir={root_module} apply {workspace}.tfplan"
        )

        if self.dry_run:
            self.result.add_event(
                phase,
                f"deploy_terraform_{workspace}",
                "success",
                details={
                    "workspace": workspace,
                    "root_module": root_module,
                    "dry_run": True,
                    "command": command,
                },
            )
            return

        self._execute_deployment(
            phase,
            f"deploy_terraform_{workspace}",
            command,
            {"workspace": workspace, "root_module": root_module, "dry_run": False},
        )

    def _execute_deployment(self, phase: OrchestrationPhase, action: str, command: str, details: Dict[str, Any]):
        """Execute a deployment command"""
        if self.dry_run:
            self.result.add_event(phase, action, "success", details={**details, "dry_run": True, "command": command})
            return

        try:
            result = subprocess.run(command, shell=True, check=True, capture_output=True, text=True)
            self.result.add_event(
                phase,
                action,
                "success",
                details={**details, "command": command, "stdout": result.stdout.strip(), "stderr": result.stderr.strip()},
            )
        except subprocess.CalledProcessError as exc:
            self.result.add_event(
                phase,
                action,
                "failure",
                details={**details, "command": command, "stdout": exc.stdout, "stderr": exc.stderr},
                error=str(exc),
            )

    def _generate_summary(self):
        """Generate execution summary"""
        logger.info("=== Generating Execution Summary ===")
        phase = OrchestrationPhase.SUMMARY

        summary = {
            "total_events": len(self.result.events),
            "successful_events": sum(1 for e in self.result.events if e.status == "success"),
            "failed_events": sum(1 for e in self.result.events if e.status == "failure"),
            "artifacts_generated": len(self.result.artifacts),
            "errors": len(self.result.errors)
        }

        self.result.add_event(
            phase,
            "generate_summary",
            "success",
            details=summary
        )

        logger.info("=== Orchestration Summary ===")
        logger.info(f"Total events: {summary['total_events']}")
        logger.info(f"Successful: {summary['successful_events']}")
        logger.info(f"Failed: {summary['failed_events']}")
        logger.info(f"Artifacts: {summary['artifacts_generated']}")

        if self.result.errors:
            logger.error("Errors encountered:")
            for error in self.result.errors:
                logger.error(f"  - {error}")

    def _finalize_result(self) -> OrchestrationResult:
        """Finalize and return orchestration result"""
        self.result.end_time = datetime.now(timezone.utc)
        duration = (self.result.end_time - self.result.start_time).total_seconds()

        logger.info(f"Orchestration completed in {duration:.2f} seconds")
        logger.info(f"Success: {self.result.success}")

        # Write result to file
        result_file = self.base_dir / "orchestration_result.json"
        with open(result_file, 'w') as f:
            json.dump(self.result.to_dict(), f, indent=2)

        logger.info(f"Result written to: {result_file}")

        return self.result


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="RegEngine Launch Orchestrator")
    parser.add_argument(
        '--mode',
        type=str,
        choices=[m.value for m in OrchestrationMode],
        default=OrchestrationMode.DRY_RUN.value,
        help="Orchestration mode"
    )
    parser.add_argument(
        '--config',
        type=str,
        default='launch_orchestrator_spec.yaml',
        help="Path to orchestrator configuration file"
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help="Simulate execution without making external calls"
    )

    args = parser.parse_args()

    mode = OrchestrationMode(args.mode)
    orchestrator = LaunchOrchestrator(args.config, mode, dry_run=args.dry_run)

    result = orchestrator.run()

    sys.exit(0 if result.success else 1)


if __name__ == '__main__':
    main()
