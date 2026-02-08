# Secrets Management Guide

This document outlines best practices for managing sensitive credentials and secrets in RegEngine.

## Quick Start (Development)

1. **Copy the example environment file:**
   ```bash
   cp .env.example .env
   ```

2. **Generate secure secrets:**
   ```bash
   bash scripts/generate-secrets.sh
   ```

3. **Update `.env` with generated secrets**

4. **NEVER commit `.env` to version control** (already in `.gitignore`)

## Secrets Inventory

RegEngine uses the following sensitive credentials:

| Secret | Purpose | Default (Dev) | Production Requirement |
|--------|---------|---------------|------------------------|
| `ADMIN_MASTER_KEY` | API key management admin | `dev-admin-key-change-in-production` | **CRITICAL - Must change** |
| `NEO4J_PASSWORD` | Graph database access | `change-me-in-production` | **CRITICAL - Must change** |
| `AWS_ACCESS_KEY_ID` | S3 bucket access | `test` (LocalStack) | Use IAM roles instead |
| `AWS_SECRET_ACCESS_KEY` | S3 bucket access | `test` (LocalStack) | Use IAM roles instead |
| API Keys | Client authentication | Generated via `/admin/keys` | Rotate every 90 days |

## Production Deployment Strategies

### Option 1: AWS Secrets Manager (Recommended for AWS)

**Store secrets:**
```bash
aws secretsmanager create-secret \
  --name regengine/admin-master-key \
  --secret-string "$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"

aws secretsmanager create-secret \
  --name regengine/neo4j-password \
  --secret-string "$(python3 -c 'import secrets; print(secrets.token_urlsafe(24))')"
```

**Retrieve in ECS task definition:**
```json
{
  "secrets": [
    {
      "name": "ADMIN_MASTER_KEY",
      "valueFrom": "arn:aws:secretsmanager:region:account:secret:regengine/admin-master-key"
    },
    {
      "name": "NEO4J_PASSWORD",
      "valueFrom": "arn:aws:secretsmanager:region:account:secret:regengine/neo4j-password"
    }
  ]
}
```

### Option 2: HashiCorp Vault

**Store secrets:**
```bash
vault kv put secret/regengine/admin \
  master_key="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"

vault kv put secret/regengine/neo4j \
  password="$(python3 -c 'import secrets; print(secrets.token_urlsafe(24))')"
```

**Retrieve with Vault agent or init container**

### Option 3: Kubernetes Secrets

**Create secrets:**
```bash
kubectl create secret generic regengine-secrets \
  --from-literal=admin-master-key="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')" \
  --from-literal=neo4j-password="$(python3 -c 'import secrets; print(secrets.token_urlsafe(24))')"
```

**Mount in deployment:**
```yaml
env:
  - name: ADMIN_MASTER_KEY
    valueFrom:
      secretKeyRef:
        name: regengine-secrets
        key: admin-master-key
  - name: NEO4J_PASSWORD
    valueFrom:
      secretKeyRef:
        name: regengine-secrets
        key: neo4j-password
```

### Option 4: Environment Variables (NOT RECOMMENDED)

Only use for development. In production:
- ❌ Never pass secrets as plain environment variables
- ❌ Never commit secrets to git
- ❌ Never log secrets
- ❌ Never expose secrets in API responses

## AWS IAM Roles (Best Practice)

Instead of using `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY`, use IAM roles:

### ECS Task Role

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject"
      ],
      "Resource": [
        "arn:aws:s3:::reg-engine-raw-data-prod/*",
        "arn:aws:s3:::reg-engine-processed-data-prod/*"
      ]
    },
    {
      "Effect": "Allow",
      "Action": [
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::reg-engine-raw-data-prod",
        "arn:aws:s3:::reg-engine-processed-data-prod"
      ]
    }
  ]
}
```

Then remove `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` from environment - boto3 will use the task role automatically.

## Secrets Rotation

### Automated Rotation (Recommended)

**AWS Secrets Manager with Lambda:**
1. Create Lambda rotation function
2. Configure rotation schedule (every 90 days)
3. Update services to fetch secrets on startup

**Kubernetes with External Secrets Operator:**
1. Install External Secrets Operator
2. Configure SecretStore pointing to AWS/Vault
3. Create ExternalSecret resources
4. Secrets auto-sync on rotation

### Manual Rotation

**Admin Master Key:**
```bash
# 1. Generate new key
NEW_KEY=$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')

# 2. Update secrets manager
aws secretsmanager update-secret \
  --secret-id regengine/admin-master-key \
  --secret-string "$NEW_KEY"

# 3. Restart admin service
kubectl rollout restart deployment/admin-api
```

**Neo4j Password:**
```bash
# 1. Connect to Neo4j
cypher-shell -u neo4j -p current-password

# 2. Change password
ALTER CURRENT USER SET PASSWORD FROM 'current-password' TO 'new-password';

# 3. Update secrets manager
aws secretsmanager update-secret \
  --secret-id regengine/neo4j-password \
  --secret-string "new-password"

# 4. Restart services
kubectl rollout restart deployment/graph-service
kubectl rollout restart deployment/opportunity-api
```

## API Key Rotation

**For clients:**
1. Create new API key via Admin API
2. Distribute new key to client
3. Wait for client to migrate (grace period)
4. Revoke old key

**Automated:**
```bash
# Create new key
NEW_KEY=$(curl -X POST http://admin-api:8400/admin/keys \
  -H "X-Admin-Key: $ADMIN_MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d '{"name": "Production Client", "rate_limit_per_minute": 500}' \
  | jq -r '.api_key')

# Notify client
echo "New API key: $NEW_KEY"

# After migration, revoke old key
curl -X DELETE http://admin-api:8400/admin/keys/$OLD_KEY_ID \
  -H "X-Admin-Key: $ADMIN_MASTER_KEY"
```

## Security Best Practices

### Development

- ✅ Use `.env` file (gitignored)
- ✅ Use different credentials than production
- ✅ Rotate development secrets quarterly
- ✅ Limit access to development secrets

### Production

- ✅ Use secrets manager (AWS Secrets Manager, Vault, etc.)
- ✅ Enable encryption at rest
- ✅ Enable encryption in transit (TLS)
- ✅ Use IAM roles instead of access keys
- ✅ Enable audit logging
- ✅ Implement least privilege access
- ✅ Rotate secrets every 90 days
- ✅ Monitor for secret exposure (git-secrets, truffleHog)

### CI/CD

- ✅ Use GitHub Secrets / GitLab Variables
- ✅ Never log secrets in build output
- ✅ Use temporary credentials where possible
- ✅ Scan for secrets in commits (pre-commit hooks)

## Secret Exposure Response

If a secret is compromised:

1. **Immediately rotate the secret**
2. **Revoke the compromised credential**
3. **Audit access logs** for unauthorized usage
4. **Notify security team**
5. **Update incident response documentation**

## Monitoring & Auditing

### AWS CloudTrail

Monitor secrets access:
```bash
aws cloudtrail lookup-events \
  --lookup-attributes AttributeKey=ResourceName,AttributeValue=regengine/admin-master-key \
  --max-items 50
```

### API Key Usage Logs

Check `services/*/app/routes.py` logs for:
- `api_key_validated` - Successful authentication
- `invalid_api_key` - Failed authentication attempts
- `rate_limit_exceeded` - Potential abuse

### Alerts

Set up alerts for:
- Failed authentication attempts (>10/minute)
- Secrets accessed from unusual IPs
- Secret rotation failures
- API keys nearing expiration

## Compliance

For regulated industries:

- **PCI DSS**: Encrypt all secrets, rotate quarterly
- **SOC 2**: Implement access controls, audit logging
- **GDPR**: Document data handling, implement encryption
- **HIPAA**: Use FIPS 140-2 validated encryption

## References

- [AWS Secrets Manager](https://docs.aws.amazon.com/secretsmanager/)
- [HashiCorp Vault](https://www.vaultproject.io/)
- [Kubernetes Secrets](https://kubernetes.io/docs/concepts/configuration/secret/)
- [OWASP Secrets Management](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html)
