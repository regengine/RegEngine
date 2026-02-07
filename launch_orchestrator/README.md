# RegEngine Launch Orchestrator

Automated system for coordinating RegEngine's go-to-market launch across five domains:

1. **Public Surface** - Marketing site, API docs, status page
2. **Sales & GTM** - Outbound campaigns, persona collateral, CRM initialization
3. **Design Partner Program** - Legal agreements, sandbox provisioning
4. **Investor Readiness** - Investor memo, pitch materials validation
5. **Infrastructure** - AWS deployment via Terraform

## Features

- ✅ **Deterministic Execution**: YAML-defined workflow ensures repeatable launches
- ✅ **Audit Trail**: Every action logged with timestamp and status
- ✅ **Artifact Tracking**: Content-addressable hashing of all generated materials
- ✅ **Dry Run Mode**: Test orchestration without external API calls
- ✅ **Modular Phases**: Run individual components (sales-only, infra-only)
- ✅ **Risk Management**: Clear separation of demo/sandbox/production environments

## Quick Start

### Prerequisites

```bash
# Install Python dependencies
pip install -r requirements.txt

# Set required environment variables
export AWS_ACCESS_KEY_ID="your-key"
export AWS_SECRET_ACCESS_KEY="your-secret"
export AWS_REGION="us-east-1"
export CRM_API_TOKEN="your-crm-token"
export EMAIL_PROVIDER_API_KEY="your-email-key"
```

### Run Orchestrator

```bash
# Dry run (simulation mode)
python orchestrator.py --mode dry_run

# Full launch
python orchestrator.py --mode full_launch

# Sales/GTM only
python orchestrator.py --mode sales_only

# Infrastructure only
python orchestrator.py --mode infra_only
```

## Configuration

Edit `launch_orchestrator_spec.yaml` to customize:

- Target URLs for deployments
- Email/LinkedIn campaign sequences
- Design partner program parameters
- Infrastructure workspaces (demo, sandbox, production)
- Required environment variables

## Output

The orchestrator generates:

1. **orchestration_result.json**: Complete audit trail with timestamps, statuses, artifacts
2. **orchestrator.log**: Detailed execution log
3. **generated/**: Persona collateral, one-pagers, campaign materials

## Directory Structure

```
launch_orchestrator/
├── orchestrator.py              # Main orchestrator
├── launch_orchestrator_spec.yaml # Configuration
├── requirements.txt             # Python dependencies
├── README.md                    # This file
├── templates/
│   ├── email/                   # Email campaign templates
│   │   ├── fintech_ccos_step1.md
│   │   ├── fintech_ccos_step2.md
│   │   ├── regtech_ctos_step1.md
│   │   └── regtech_ctos_step2.md
│   └── linkedin/                # LinkedIn outreach templates
│       └── fintech_ccos_step3.txt
├── legal/
│   └── design_partner_agreement.md  # Legal template (requires counsel review)
├── investors/
│   └── investor_memo.md             # Investor memo
└── generated/                   # Auto-generated artifacts (gitignored)
```

## Security & Compliance

### What This System Does NOT Do

- ❌ Provide legal or regulatory advice
- ❌ Make binding compliance guarantees
- ❌ Access production customer data without approval
- ❌ Execute irreversible actions without explicit confirmation

### What This System DOES

- ✅ Log all actions to audit trail
- ✅ Separate demo/sandbox/production environments
- ✅ Require human review of AI-generated legal text
- ✅ Validate environment before external API calls
- ✅ Support dry-run mode for safety

## Integration Points

### CRM (HubSpot, Salesforce)
- Create contact lists
- Initialize outbound sequences
- Track deal pipeline

### Email Provider (SendGrid, Mailchimp)
- Load email templates
- Schedule drip campaigns
- Track opens/clicks

### LinkedIn Automation (Sales Navigator, Apollo)
- Load LinkedIn outreach sequences
- Send connection requests + messages
- Track engagement

### Infrastructure (AWS, Terraform)
- Deploy VPC, ECS, RDS, Neo4j, Redpanda
- Create sandboxes for design partners
- Configure monitoring and alerting

## Phases Explained

### Phase 1: Initialization
- Validate required environment variables
- Load and parse configuration
- Initialize audit trail

### Phase 2: Public Surface Deployment
- Deploy marketing website (Next.js, Vercel)
- Publish API documentation (OpenAPI/Swagger)
- Configure status page (Statuspage.io or equivalent)

### Phase 3: Sales & GTM Generation
- Generate persona-specific one-pagers
- Initialize outbound email campaigns (fintech CCOs, RegTech CTOs)
- Configure LinkedIn sequences
- Create CRM pipelines

### Phase 4: Design Partner Provisioning
- Validate legal agreement template
- Pre-provision N sandbox environments
- Generate API keys with rate limits
- Seed demo data

### Phase 5: Investor Readiness
- Validate investor memo completeness
- Check pitch deck for required slides
- Prepare data room access

### Phase 6: Infrastructure Deployment
- Run Terraform for demo/sandbox/production workspaces
- Deploy ECS services
- Configure Neo4j, Redpanda, S3
- Set up CloudWatch monitoring

### Phase 7: Summary Generation
- Count successful/failed events
- List generated artifacts with hashes
- Output execution summary
- Write result to JSON

## Extending the Orchestrator

To add new capabilities:

1. **Add to spec**: Update `launch_orchestrator_spec.yaml` with new section
2. **Add method**: Create `_deploy_your_feature()` method in orchestrator
3. **Call in run()**: Add method call to appropriate mode
4. **Log events**: Use `self.result.add_event()` for audit trail
5. **Track artifacts**: Use `self.result.add_artifact()` for generated files

Example:

```python
def _deploy_your_feature(self):
    """Deploy your new feature"""
    phase = OrchestrationPhase.PUBLIC_SURFACE

    # Your deployment logic here

    self.result.add_event(
        phase,
        "deploy_your_feature",
        "success",
        details={"feature": "description"}
    )
```

## Troubleshooting

### Missing Environment Variables

```
Error: Missing environment variables: AWS_ACCESS_KEY_ID
```

**Solution**: Set required environment variables (see Prerequisites)

### Configuration Validation Failed

```
Error: Missing required config key: orchestrator
```

**Solution**: Ensure `launch_orchestrator_spec.yaml` has all required sections

### Terraform Deployment Failed

```
Error: Terraform apply failed in workspace: sandbox
```

**Solution**: Check AWS credentials, Terraform state, and module configuration

## Production Checklist

Before running in production mode:

- [ ] Review and customize all email/LinkedIn templates
- [ ] Have legal counsel review design partner agreement
- [ ] Set real environment variables (not defaults)
- [ ] Test in dry-run mode first
- [ ] Back up existing infrastructure state
- [ ] Configure monitoring and alerting
- [ ] Set up incident response plan
- [ ] Document rollback procedures

## Support

- **Documentation**: See this README and inline code comments
- **Issues**: File issues in main RegEngine repository
- **Security**: For security concerns, email security@regengine.ai

---

**Status**: Ready for use (with human oversight)

**Last Updated**: January 2025

**License**: Proprietary (part of RegEngine commercial infrastructure)
