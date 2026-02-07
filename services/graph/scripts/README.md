# Neo4j Database Constraints

This directory contains database constraints for the RegEngine Neo4j graph database.

## Files

- `init_constraints.cypher` - Cypher statements defining database constraints
- `apply_constraints.py` - Python script to apply constraints to Neo4j

## Constraints

### lot_tlc_tenant_unique

Ensures that the combination of `tlc` (Traceability Lot Code) and `tenant_id` is unique for Lot nodes.
This prevents duplicate lots from being created within the same tenant and guarantees data integrity at the database level.

## Usage

### Using Make

```bash
make apply-constraints
```

### Using Python directly

```bash
export NEO4J_PASSWORD=your_password
python services/graph/scripts/apply_constraints.py
```

### Environment Variables

- `NEO4J_URI` - Neo4j connection URI (default: `bolt://localhost:7687`)
- `NEO4J_USER` - Neo4j username (default: `neo4j`)
- `NEO4J_PASSWORD` - Neo4j password (required)

## Production Deployment

In production environments, these constraints should be applied:

1. During initial database setup
2. As part of infrastructure provisioning (e.g., in Terraform or CloudFormation)
3. Before deploying the application services

For ECS/Kubernetes deployments, the constraints can be applied via:
- Init containers
- Database migration jobs
- Infrastructure as Code (IaC) provisioning scripts

## Notes

- The script is idempotent - it will skip constraints that already exist
- Constraints are created with `IF NOT EXISTS` to prevent errors on re-runs
- All constraints are applied in a single session for consistency
