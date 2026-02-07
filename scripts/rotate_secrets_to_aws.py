#!/usr/bin/env python3
"""Migrate existing secrets from .env to AWS Secrets Manager.

This script reads secrets from environment variables or .env file and
uploads them to AWS Secrets Manager for secure storage in production.

Usage:
    python scripts/rotate_secrets_to_aws.py --environment production
    python scripts/rotate_secrets_to_aws.py --environment staging --region us-west-2
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

try:
    import boto3
    from botocore.exceptions import ClientError
except ImportError:
    print("ERROR: boto3 is required. Install with: pip install boto3")
    sys.exit(1)

try:
    from dotenv import load_dotenv
except ImportError:
    print("WARNING: python-dotenv not installed. Will use existing environment variables only.")
    load_dotenv = None


def load_environment_secrets(env_file: str = ".env") -> None:
    """Load secrets from .env file if available.

    Args:
        env_file: Path to .env file
    """
    if load_dotenv is not None:
        env_path = Path(env_file)
        if env_path.exists():
            load_dotenv(env_path)
            print(f"✓ Loaded environment from {env_file}")
        else:
            print(f"⚠ {env_file} not found, using existing environment variables")
    else:
        print("⚠ Using existing environment variables only")


def create_or_update_secret(
    client,
    secret_name: str,
    secret_data: dict,
    description: str = "",
) -> None:
    """Create or update a secret in AWS Secrets Manager.

    Args:
        client: boto3 Secrets Manager client
        secret_name: Name of the secret
        secret_data: Secret data as dictionary
        description: Description of the secret
    """
    secret_string = json.dumps(secret_data, indent=2)

    try:
        # Try to create the secret
        client.create_secret(
            Name=secret_name,
            Description=description,
            SecretString=secret_string,
        )
        print(f"✓ Created secret: {secret_name}")
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "ResourceExistsException":
            # Secret exists, update it instead
            client.update_secret(
                SecretId=secret_name,
                SecretString=secret_string,
            )
            print(f"✓ Updated secret: {secret_name}")
        else:
            print(f"✗ Failed to create/update {secret_name}: {exc}")
            raise


def rotate_database_secrets(client, environment: str) -> None:
    """Rotate PostgreSQL database secrets.

    Args:
        client: boto3 Secrets Manager client
        environment: Environment name (production, staging, dev)
    """
    db_secret = {
        "username": os.getenv("POSTGRES_USER", "postgres"),
        "password": os.getenv("POSTGRES_PASSWORD", ""),
        "host": os.getenv("POSTGRES_HOST", "localhost"),
        "port": os.getenv("POSTGRES_PORT", "5432"),
        "database": os.getenv("POSTGRES_DB", "regengine"),
    }

    # Validate required fields
    if not db_secret["password"]:
        print("⚠ WARNING: POSTGRES_PASSWORD is empty")

    secret_name = f"regengine/{environment}/database"
    create_or_update_secret(
        client,
        secret_name,
        db_secret,
        f"PostgreSQL database credentials for RegEngine {environment}",
    )


def rotate_neo4j_secrets(client, environment: str) -> None:
    """Rotate Neo4j database secrets.

    Args:
        client: boto3 Secrets Manager client
        environment: Environment name (production, staging, dev)
    """
    neo4j_secret = {
        "uri": os.getenv("NEO4J_URI", "bolt://localhost:7687"),
        "username": os.getenv("NEO4J_USER", "neo4j"),
        "password": os.getenv("NEO4J_PASSWORD", ""),
    }

    # Validate required fields
    if not neo4j_secret["password"]:
        print("⚠ WARNING: NEO4J_PASSWORD is empty")

    secret_name = f"regengine/{environment}/neo4j"
    create_or_update_secret(
        client,
        secret_name,
        neo4j_secret,
        f"Neo4j database credentials for RegEngine {environment}",
    )


def rotate_kafka_secrets(client, environment: str) -> None:
    """Rotate Kafka secrets.

    Args:
        client: boto3 Secrets Manager client
        environment: Environment name (production, staging, dev)
    """
    kafka_secret = {
        "bootstrap_servers": os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092"),
        "username": os.getenv("KAFKA_USERNAME", ""),
        "password": os.getenv("KAFKA_PASSWORD", ""),
        "security_protocol": os.getenv("KAFKA_SECURITY_PROTOCOL", "PLAINTEXT"),
    }

    secret_name = f"regengine/{environment}/kafka"
    create_or_update_secret(
        client,
        secret_name,
        kafka_secret,
        f"Kafka credentials for RegEngine {environment}",
    )


def rotate_s3_secrets(client, environment: str) -> None:
    """Rotate S3/AWS credentials.

    Args:
        client: boto3 Secrets Manager client
        environment: Environment name (production, staging, dev)
    """
    s3_secret = {
        "access_key_id": os.getenv("AWS_ACCESS_KEY_ID", ""),
        "secret_access_key": os.getenv("AWS_SECRET_ACCESS_KEY", ""),
        "region": os.getenv("AWS_REGION", "us-east-1"),
        "bucket_prefix": os.getenv("S3_BUCKET_PREFIX", f"regengine-{environment}"),
    }

    # Validate required fields
    if not s3_secret["access_key_id"] or not s3_secret["secret_access_key"]:
        print("⚠ WARNING: AWS credentials (access_key_id/secret_access_key) are empty")

    secret_name = f"regengine/{environment}/s3"
    create_or_update_secret(
        client,
        secret_name,
        s3_secret,
        f"S3/AWS credentials for RegEngine {environment}",
    )


def rotate_admin_secrets(client, environment: str) -> None:
    """Rotate admin API secrets.

    Args:
        client: boto3 Secrets Manager client
        environment: Environment name (production, staging, dev)
    """
    admin_secret = {
        "master_key": os.getenv("ADMIN_MASTER_KEY", ""),
    }

    # Validate required fields
    if not admin_secret["master_key"]:
        print("⚠ WARNING: ADMIN_MASTER_KEY is empty")

    secret_name = f"regengine/{environment}/admin"
    create_or_update_secret(
        client,
        secret_name,
        admin_secret,
        f"Admin API master key for RegEngine {environment}",
    )


def main():
    """Main entry point for secrets rotation script."""
    parser = argparse.ArgumentParser(
        description="Migrate secrets from .env to AWS Secrets Manager"
    )
    parser.add_argument(
        "--environment",
        required=True,
        choices=["production", "staging", "dev"],
        help="Target environment (production, staging, dev)",
    )
    parser.add_argument(
        "--region",
        default="us-east-1",
        help="AWS region for Secrets Manager (default: us-east-1)",
    )
    parser.add_argument(
        "--env-file",
        default=".env",
        help="Path to .env file (default: .env)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be uploaded without actually uploading",
    )

    args = parser.parse_args()

    print(f"\n{'='*60}")
    print(f"RegEngine Secrets Rotation to AWS Secrets Manager")
    print(f"{'='*60}")
    print(f"Environment: {args.environment}")
    print(f"Region: {args.region}")
    print(f"Dry Run: {args.dry_run}")
    print(f"{'='*60}\n")

    # Load environment variables from .env file
    load_environment_secrets(args.env_file)

    if args.dry_run:
        print("DRY RUN MODE - No secrets will be uploaded\n")
        print("Secrets that would be created:")
        print(f"  - regengine/{args.environment}/database")
        print(f"  - regengine/{args.environment}/neo4j")
        print(f"  - regengine/{args.environment}/kafka")
        print(f"  - regengine/{args.environment}/s3")
        print(f"  - regengine/{args.environment}/admin")
        print("\nRun without --dry-run to upload secrets")
        return

    # Initialize AWS Secrets Manager client
    try:
        client = boto3.client("secretsmanager", region_name=args.region)
        print(f"✓ Connected to AWS Secrets Manager ({args.region})\n")
    except Exception as exc:
        print(f"✗ Failed to connect to AWS Secrets Manager: {exc}")
        sys.exit(1)

    # Rotate all secrets
    try:
        print("Rotating Database secrets...")
        rotate_database_secrets(client, args.environment)

        print("\nRotating Neo4j secrets...")
        rotate_neo4j_secrets(client, args.environment)

        print("\nRotating Kafka secrets...")
        rotate_kafka_secrets(client, args.environment)

        print("\nRotating S3 secrets...")
        rotate_s3_secrets(client, args.environment)

        print("\nRotating Admin secrets...")
        rotate_admin_secrets(client, args.environment)

        print(f"\n{'='*60}")
        print(f"✅ Successfully rotated secrets for environment: {args.environment}")
        print(f"{'='*60}")
        print("\nNext steps:")
        print(f"1. Set USE_AWS_SECRETS=true in your {args.environment} environment")
        print(f"2. Set ENVIRONMENT={args.environment}")
        print("3. Ensure IAM role has secretsmanager:GetSecretValue permission")
        print("4. Remove .env file from production servers")

    except Exception as exc:
        print(f"\n✗ Secrets rotation failed: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
