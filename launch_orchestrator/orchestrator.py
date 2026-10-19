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
import secrets
import string
import subprocess
import sys
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("orchestrator.log"), logging.StreamHandler(sys.stdout)],
)

logger = logging.getLogger(__name__)

# Upper bound for any single deployment subprocess. A deploy step that hangs
# (wedged installer, interactive prompt on a non-tty) must fail loudly instead
# of blocking the run forever.
_DEPLOY_TIMEOUT_SECONDS = 600


def _spec_error(path: str, detail: str) -> ValueError:
    return ValueError(f"Invalid spec at '{path}': {detail}")


def _require_mapping(value: Any, path: str) -> Dict[str, Any]:
    if not isinstance(value, dict):
        raise _spec_error(path, f"must be a mapping, got {type(value).__name__}")
    return value


def _require_string(value: Any, path: str) -> str:
    if not isinstance(value, str):
        raise _spec_error(path, f"must be a string, got {type(value).__name__}")
    return value


def _require_string_list(value: Any, path: str) -> List[str]:
    if not isinstance(value, list) or any(not isinstance(v, str) for v in value):
        raise _spec_error(path, "must be a list of strings")
    return value


def _validate_config_schema(config: Dict[str, Any]) -> None:
    """Reject malformed specs with a clear field path.

    Without this, a bad spec (a string where a mapping belongs, a missing
    persona id, a mistyped step key) explodes mid-run as a bare KeyError,
    TypeError or AttributeError that aborts every remaining phase.
    """
    # An explicitly null block means "no environment requirements", the same
    # as an empty mapping (#3365); only a non-mapping value is malformed.
    if config["environment"] is None:
        config["environment"] = {}
    env = _require_mapping(config["environment"], "environment")
    required_vars = env.get("required_env_vars", [])
    if required_vars is None:
        env["required_env_vars"] = []
    else:
        _require_string_list(required_vars, "environment.required_env_vars")

    public = config.get("public_surface", {})
    if public:
        _require_mapping(public, "public_surface")
        for key in ("marketing_site", "api_docs", "status_page"):
            if public.get(key) is not None:
                _require_mapping(public[key], f"public_surface.{key}")
        components = (public.get("status_page") or {}).get("components", [])
        if components:
            if not isinstance(components, list):
                raise _spec_error("public_surface.status_page.components", "must be a list")
            for i, component in enumerate(components):
                _require_mapping(component, f"public_surface.status_page.components[{i}]")
                _require_string(component.get("name"), f"public_surface.status_page.components[{i}].name")

    sales = config.get("sales", {})
    if sales:
        _require_mapping(sales, "sales")
        for i, persona in enumerate(sales.get("personas", [])):
            base = f"sales.personas[{i}]"
            _require_mapping(persona, base)
            _require_string(persona.get("id"), f"{base}.id")
            _require_string(persona.get("title"), f"{base}.title")
            for key in ("pains", "desired_outcomes"):
                if persona.get(key) is not None:
                    _require_string_list(persona[key], f"{base}.{key}")
        campaigns = sales.get("outbound_campaigns", {})
        if campaigns:
            _require_mapping(campaigns, "sales.outbound_campaigns")
            sequences = campaigns.get("sequences", [])
            if not isinstance(sequences, list):
                raise _spec_error("sales.outbound_campaigns.sequences", "must be a list")
            for i, campaign in enumerate(sequences):
                base = f"sales.outbound_campaigns.sequences[{i}]"
                _require_mapping(campaign, base)
                _require_string(campaign.get("id"), f"{base}.id")
                _require_string(campaign.get("persona"), f"{base}.persona")
                steps = campaign.get("steps", [])
                if not isinstance(steps, list):
                    raise _spec_error(f"{base}.steps", "must be a list")
                for j, step in enumerate(steps):
                    step_base = f"{base}.steps[{j}]"
                    _require_mapping(step, step_base)
                    _require_string(step.get("channel"), f"{step_base}.channel")
                    _require_string(step.get("template_ref"), f"{step_base}.template_ref")

    design_partners = config.get("design_partner_program", {})
    if design_partners:
        _require_mapping(design_partners, "design_partner_program")
        if design_partners.get("max_partners") is not None:
            max_partners = design_partners["max_partners"]
            if not isinstance(max_partners, int) or max_partners < 0:
                raise _spec_error("design_partner_program.max_partners", "must be a non-negative integer")
        if design_partners.get("legal_template_ref") is not None:
            _require_string(design_partners["legal_template_ref"], "design_partner_program.legal_template_ref")
        if design_partners.get("sandbox") is not None:
            _require_mapping(design_partners["sandbox"], "design_partner_program.sandbox")

    investor = config.get("investor_readiness", {})
    if investor:
        _require_mapping(investor, "investor_readiness")
        if investor.get("memo_template_ref") is not None:
            _require_string(investor["memo_template_ref"], "investor_readiness.memo_template_ref")

    infra = config.get("infrastructure", {})
    if infra:
        _require_mapping(infra, "infrastructure")
        terraform = infra.get("terraform", {})
        if terraform:
            _require_mapping(terraform, "infrastructure.terraform")
            if terraform.get("root_module_path") is not None:
                _require_string(terraform["root_module_path"], "infrastructure.terraform.root_module_path")
            if terraform.get("workspaces") is not None:
                _require_string_list(terraform["workspaces"], "infrastructure.terraform.workspaces")


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

    def add_event(
        self,
        phase: OrchestrationPhase,
        action: str,
        status: str,
        details: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ):
        """Add an event to the audit trail"""
        event = OrchestrationEvent(
            timestamp=datetime.now(timezone.utc),
            phase=phase,
            action=action,
            status=status,
            details=details or {},
            error=error,
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
            with open(content_or_path, "rb") as f:
                content = f.read()
        else:
            content = content_or_path.encode("utf-8")

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
                    "error": e.error,
                }
                for e in self.events
            ],
            "artifacts": self.artifacts,
            "errors": self.errors,
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
            with open(self.config_path, "r") as f:
                config = yaml.safe_load(f)

            # Basic validation
            if config is None:
                raise ValueError(f"Empty configuration file: {self.config_path}")
            if not isinstance(config, dict):
                raise ValueError(
                    f"Invalid configuration file {self.config_path}: "
                    f"top level must be a mapping, got {type(config).__name__}"
                )
            required_keys = ["orchestrator", "environment"]
            for key in required_keys:
                if key not in config:
                    raise ValueError(f"Missing required config key: {key}")

            _validate_config_schema(config)

            logger.info("Configuration loaded successfully")
            return config

        except Exception as e:
            logger.error(f"Failed to load configuration: {e}")
            raise

    def _assert_live(self) -> None:
        """Re-check the production guard immediately before any side effect.

        The __init__ check alone is not enough: dry_run is a plain attribute,
        so flipping it after construction (or calling a phase method directly)
        would otherwise run real deployments with no guard at all. Callers
        only reach this on live paths (dry-run paths return before it).
        """
        if os.getenv("REGENGINE_ENV") != "production":
            raise RuntimeError("Unsafe orchestrator execution: live actions require REGENGINE_ENV=production")

    def _validate_environment(self) -> bool:
        """Validate required environment variables and secrets"""
        logger.info("Validating environment...")

        environment = self.config.get("environment") or {}
        required_vars = environment.get("required_env_vars", [])
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
                error=f"Missing environment variables: {', '.join(missing_vars)}",
            )
            return False

        self.result.add_event(
            OrchestrationPhase.INIT, "validate_environment", "success", details={"validated_vars": len(required_vars)}
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
            self.result.add_event(OrchestrationPhase.SUMMARY, "orchestration_execution", "failure", error=str(e))

        return self._finalize_result()

    def _deploy_public_surface(self):
        """Deploy marketing site, API docs, and status page"""
        logger.info("=== Phase: Public Surface Deployment ===")
        phase = OrchestrationPhase.PUBLIC_SURFACE

        public_config = self.config.get("public_surface") or {}

        # Deploy marketing site
        marketing = public_config.get("marketing_site", {})
        if marketing:
            self._execute_deployment(
                phase,
                "deploy_marketing_site",
                marketing.get("deploy_command", 'echo "No deploy command"'),
                {"target_url": marketing.get("target_url"), "features": marketing.get("features", [])},
            )

        # Publish API docs
        api_docs = public_config.get("api_docs", {})
        if api_docs:
            self._execute_deployment(
                phase,
                "publish_api_docs",
                api_docs.get("publish_command", 'echo "No publish command"'),
                {"target_url": api_docs.get("target_url"), "format": api_docs.get("specification_format")},
            )

        # Configure status page
        status_page = public_config.get("status_page") or {}
        if status_page:
            self.result.add_event(
                phase,
                "configure_status_page",
                "success" if self.dry_run else "skipped",
                details={
                    "components": [c["name"] for c in status_page.get("components", [])],
                    "reason": "dry_run" if self.dry_run else "not_implemented",
                    "detail": (
                        "Dry run records intent only."
                        if self.dry_run
                        else "No status-page provider call exists; nothing was configured."
                    ),
                },
            )

    def _generate_sales_gtm(self):
        """Generate sales collateral and GTM campaigns"""
        logger.info("=== Phase: Sales & GTM Generation ===")
        phase = OrchestrationPhase.SALES_GTM

        sales_config = self.config.get("sales") or {}

        # Generate persona-specific collateral
        personas = sales_config.get("personas", [])
        for persona in personas:
            persona_id = persona["id"]
            self._generate_persona_collateral(phase, persona)

        # Initialize outbound campaigns
        campaigns = sales_config.get("outbound_campaigns", {}).get("sequences", [])
        for campaign in campaigns:
            self._initialize_outbound_sequence(phase, campaign)

    def _generate_persona_collateral(self, phase: OrchestrationPhase, persona: Dict[str, Any]):
        """Generate collateral for a specific persona"""
        persona_id = persona["id"]
        persona_title = persona["title"]

        # Generate one-pager
        one_pager_path = self.base_dir / "generated" / f"{persona_id}_one_pager.md"
        one_pager_content = self._create_one_pager(persona)

        if not self.dry_run:
            self._assert_live()
            one_pager_path.parent.mkdir(parents=True, exist_ok=True)
            with open(one_pager_path, "w") as f:
                f.write(one_pager_content)

        self.result.add_artifact(f"{persona_id}_one_pager", one_pager_content)
        self.result.add_event(
            phase,
            f"generate_one_pager_{persona_id}",
            "success",
            details={"persona": persona_title, "path": str(one_pager_path)},
        )

    def _create_one_pager(self, persona: Dict[str, Any]) -> str:
        """Create a one-pager for a persona"""
        return f"""# RegEngine One-Pager: {persona["title"]}

## Pain Points
{chr(10).join(f"- {pain}" for pain in persona.get("pains", []))}

## What RegEngine Delivers
{chr(10).join(f"- {outcome}" for outcome in persona.get("desired_outcomes", []))}

## Next Steps
1. Schedule a 20-minute demo: [calendly link]
2. Try our sandbox environment
3. Review case studies from similar companies

Contact: sales@regengine.ai
"""

    def _initialize_outbound_sequence(self, phase: OrchestrationPhase, campaign: Dict[str, Any]):
        """Initialize an outbound email/LinkedIn sequence"""
        sequence_id = campaign["id"]
        persona = campaign["persona"]
        steps = campaign.get("steps", [])

        # A sequence whose template files do not exist cannot run. Claiming
        # success here used to hide a broken campaign until send time.
        missing_templates = [
            step["template_ref"] for step in steps if not (self.base_dir / step["template_ref"]).is_file()
        ]
        if missing_templates:
            self.result.add_event(
                phase,
                f"initialize_sequence_{sequence_id}",
                "failure",
                details={
                    "sequence_id": sequence_id,
                    "persona": persona,
                    "num_steps": len(steps),
                    "missing_templates": missing_templates,
                },
                error=f"Missing template files: {', '.join(missing_templates)}",
            )
            return

        # In production, this would integrate with SendGrid, Apollo, or similar
        self.result.add_event(
            phase,
            f"initialize_sequence_{sequence_id}",
            "success",
            details={
                "sequence_id": sequence_id,
                "persona": persona,
                "num_steps": len(steps),
                "channels": list(set(step["channel"] for step in steps)),
            },
        )

    def _provision_design_partners(self):
        """Provision sandboxes for design partners"""
        logger.info("=== Phase: Design Partner Provisioning ===")
        phase = OrchestrationPhase.DESIGN_PARTNERS

        dp_config = self.config.get("design_partner_program") or {}
        max_partners = dp_config.get("max_partners", 5)

        # Generate legal agreement
        legal_ref = dp_config.get("legal_template_ref", "")
        if not legal_ref:
            self.result.add_event(
                phase,
                "validate_legal_template",
                "skipped",
                details={"reason": "no legal_template_ref configured"},
            )
        else:
            legal_template = self.base_dir / legal_ref
            if legal_template.is_file():
                self.result.add_artifact("design_partner_agreement", str(legal_template))
                self.result.add_event(
                    phase, "validate_legal_template", "success", details={"template_path": str(legal_template)}
                )
            else:
                self.result.add_event(
                    phase,
                    "validate_legal_template",
                    "failure",
                    details={"template_path": str(legal_template)},
                    error=f"Legal template not found: {legal_ref}",
                )

        # Pre-provision sandboxes
        sandbox_config = dp_config.get("sandbox") or {}
        for i in range(max_partners):
            self._provision_sandbox(phase, f"dp-sandbox-{i + 1}", sandbox_config)

    def _provision_sandbox(self, phase: OrchestrationPhase, sandbox_id: str, config: Dict[str, Any]):
        """Provision a single sandbox environment"""
        logger.info(f"Provisioning sandbox: {sandbox_id}")

        # #2958: this method registers nothing. The module imports no HTTP
        # client of any kind (see the import block at the top of this file), so
        # no RegEngine API is contacted to create the tenant or register a key.
        # A key minted here would be rejected on the partner's first call.
        #
        # The candidate key is still generated so the shape of a real
        # implementation is visible, but it is NEVER written to disk: the
        # previous code appended it in cleartext to generated/sandbox_keys.txt
        # (mode 0644) inside the working tree, in a directory README.md:90
        # calls gitignored. Only the prefix is ever recorded.
        api_key = "sk_test_" + "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(32))
        api_key_prefix = api_key[:12] + "..."
        del api_key  # nothing below may persist or return the full value

        # Platform tenant ids are UUIDs; "dp-sandbox-1" could not be loaded.
        tenant_uuid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"regengine-sandbox/{sandbox_id}"))

        tenant_config = {
            "tenant_id": tenant_uuid,
            "sandbox_label": sandbox_id,
            "api_key_prefix": api_key_prefix,
            "max_docs": config.get("max_docs_per_partner", 100),
            "jurisdictions": config.get("jurisdictions", {}).get("default", ["US-NY"]),
            "rate_limit_rpm": config.get("rate_limits", {}).get("rpm_per_api_key", 60),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "provisioned": False,
            "note": (
                "Template only. No tenant was created and no API key was "
                "registered -- launch_orchestrator has no platform client."
            ),
        }

        output_dir = self.base_dir / "generated" / "tenants"
        if not self.dry_run:
            self._assert_live()
            output_dir.mkdir(parents=True, exist_ok=True)
            config_path = output_dir / f"{sandbox_id}.json"
            with open(config_path, "w") as f:
                json.dump(tenant_config, f, indent=2)

        self.result.add_event(
            phase,
            f"provision_sandbox_{sandbox_id}",
            "skipped",
            details={
                "sandbox_id": sandbox_id,
                "tenant_id": tenant_uuid,
                "api_key_prefix": api_key_prefix,
                "config_path": str(output_dir / f"{sandbox_id}.json"),
                "reason": "not_implemented",
                "detail": ("No platform API call was made; the sandbox does not exist and the key is not registered."),
            },
        )

    def _prepare_investor_materials(self):
        """Prepare investor memo and supporting materials"""
        logger.info("=== Phase: Investor Readiness ===")
        phase = OrchestrationPhase.INVESTOR_READINESS

        investor_config = self.config.get("investor_readiness") or {}

        # Validate investor memo
        memo_ref = investor_config.get("memo_template_ref", "")
        if not memo_ref:
            self.result.add_event(
                phase,
                "validate_investor_memo",
                "skipped",
                details={"reason": "no memo_template_ref configured"},
            )
        else:
            memo_path = self.base_dir / memo_ref
            if memo_path.is_file():
                self.result.add_artifact("investor_memo", str(memo_path))
                self.result.add_event(phase, "validate_investor_memo", "success", details={"memo_path": str(memo_path)})
            else:
                self.result.add_event(
                    phase,
                    "validate_investor_memo",
                    "failure",
                    details={"memo_path": str(memo_path)},
                    error=f"Investor memo template not found: {memo_ref}",
                )

        # Validate required slides
        required_slides = investor_config.get("slides_required", [])
        self.result.add_event(phase, "validate_pitch_slides", "success", details={"required_slides": required_slides})

    def _deploy_infrastructure(self):
        """Deploy infrastructure via Terraform"""
        logger.info("=== Phase: Infrastructure Deployment ===")
        phase = OrchestrationPhase.INFRA

        infra_config = self.config.get("infrastructure") or {}
        terraform_config = infra_config.get("terraform") or {}

        root_module = terraform_config.get("root_module_path", "infra/terraform")
        workspaces = terraform_config.get("workspaces", ["demo", "sandbox", "production"])

        for workspace in workspaces:
            self._deploy_terraform_workspace(phase, root_module, workspace)

    def _deploy_terraform_workspace(self, phase: OrchestrationPhase, root_module: str, workspace: str):
        """Deploy a Terraform workspace"""
        # #2961: this used to be one string joined with `&&`, handed to
        # _execute_deployment, which runs shlex.split(command). shlex does not
        # interpret `&&` -- it becomes a literal argv entry, so terraform was
        # invoked with "&&" as a positional argument and every non-dry-run
        # deployment failed. Three separate invocations, run in order.
        steps = [
            ("workspace_select", f"terraform -chdir={root_module} workspace select {workspace}"),
            ("plan", f"terraform -chdir={root_module} plan -out={workspace}.tfplan"),
            ("apply", f"terraform -chdir={root_module} apply {workspace}.tfplan"),
        ]

        if self.dry_run:
            command = "; ".join(cmd for _, cmd in steps)
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

        # #2961: the default root_module_path is "infra/terraform", which does
        # not exist in this repository. Report that rather than letting each
        # step fail with an opaque terraform error.
        if not (self.base_dir / root_module).is_dir() and not Path(root_module).is_dir():
            self.result.add_event(
                phase,
                f"deploy_terraform_{workspace}",
                # "failure", not "failed": OrchestrationResult.add_event and the
                # summary counter both key on the exact string "failure". Any
                # other spelling is recorded but never counted, so the run still
                # reports success -- the precise defect this PR exists to fix.
                "failure",
                details={"workspace": workspace, "root_module": root_module, "dry_run": False},
                error=f"Terraform root module not found: {root_module}",
            )
            return

        for step_name, step_command in steps:
            self._execute_deployment(
                phase,
                f"deploy_terraform_{workspace}_{step_name}",
                step_command,
                {"workspace": workspace, "root_module": root_module, "dry_run": False},
            )

    def _execute_deployment(self, phase: OrchestrationPhase, action: str, command: str, details: Dict[str, Any]):
        """Execute a deployment command"""
        if self.dry_run:
            self.result.add_event(phase, action, "success", details={**details, "dry_run": True, "command": command})
            return

        self._assert_live()

        if not command or not command.strip():
            self.result.add_event(
                phase,
                action,
                "failure",
                details={**details, "command": command},
                error="Refusing to execute an empty deployment command",
            )
            return

        try:
            # Use shlex.split instead of shell=True to prevent command injection
            import shlex

            result = subprocess.run(
                shlex.split(command),
                check=True,
                capture_output=True,
                text=True,
                timeout=_DEPLOY_TIMEOUT_SECONDS,
            )
            self.result.add_event(
                phase,
                action,
                "success",
                details={
                    **details,
                    "command": command,
                    "stdout": result.stdout.strip(),
                    "stderr": result.stderr.strip(),
                },
            )
        except subprocess.CalledProcessError as exc:
            self.result.add_event(
                phase,
                action,
                "failure",
                details={**details, "command": command, "stdout": exc.stdout, "stderr": exc.stderr},
                error=str(exc),
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            # OSError covers a missing binary or an unexecutable command;
            # TimeoutExpired covers a hung deploy step. Either way the rest
            # of the run must continue, so record the failure here instead of
            # letting the exception abort every remaining phase.
            self.result.add_event(
                phase,
                action,
                "failure",
                details={**details, "command": command},
                error=f"{type(exc).__name__}: {exc}",
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
            "errors": len(self.result.errors),
        }

        self.result.add_event(phase, "generate_summary", "success", details=summary)

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

        # Write result to file atomically: a crash or a concurrent run must
        # leave behind the previous complete file, never a truncated one.
        result_file = self.base_dir / "orchestration_result.json"
        tmp_file = result_file.with_name(f".{result_file.name}.{os.getpid()}.{threading.get_ident()}.tmp")
        with open(tmp_file, "w") as f:
            json.dump(self.result.to_dict(), f, indent=2)
        os.replace(tmp_file, result_file)

        logger.info(f"Result written to: {result_file}")

        return self.result


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="RegEngine Launch Orchestrator")
    parser.add_argument(
        "--mode",
        type=str,
        choices=[m.value for m in OrchestrationMode],
        default=OrchestrationMode.DRY_RUN.value,
        help="Orchestration mode",
    )
    parser.add_argument(
        "--config", type=str, default="launch_orchestrator_spec.yaml", help="Path to orchestrator configuration file"
    )
    parser.add_argument("--dry-run", action="store_true", help="Simulate execution without making external calls")

    args = parser.parse_args()

    mode = OrchestrationMode(args.mode)
    orchestrator = LaunchOrchestrator(args.config, mode, dry_run=args.dry_run)

    result = orchestrator.run()

    sys.exit(0 if result.success else 1)


if __name__ == "__main__":
    main()
