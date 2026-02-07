"""
AWS Lambda function for automatic secret rotation in AWS Secrets Manager.

This function handles automatic rotation of database credentials, API keys,
and other sensitive secrets used by RegEngine services.
"""

import json
import boto3
import os
import logging
from typing import Dict, Any
import secrets
import string

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
secrets_client = boto3.client('secretsmanager')
rds_client = boto3.client('rds')


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Main Lambda handler for secret rotation.

    This function is triggered by AWS Secrets Manager rotation events.
    It supports rotating RDS credentials, Neo4j passwords, and API keys.

    Args:
        event: Lambda event containing rotation metadata
        context: Lambda context

    Returns:
        Success/failure response
    """
    arn = event['SecretId']
    token = event['ClientRequestToken']
    step = event['Step']

    logger.info(f"Rotating secret {arn}, step: {step}, token: {token}")

    try:
        # Get secret metadata
        metadata = secrets_client.describe_secret(SecretId=arn)
        if not metadata['RotationEnabled']:
            raise ValueError(f"Secret {arn} is not enabled for rotation")

        # Check if version already exists
        if step != "testSecret" and token not in metadata.get('VersionIdsToStages', {}):
            raise ValueError(f"Secret version {token} not found")

        # Execute rotation step
        if step == "createSecret":
            create_secret(secrets_client, arn, token)
        elif step == "setSecret":
            set_secret(secrets_client, rds_client, arn, token)
        elif step == "testSecret":
            test_secret(secrets_client, arn, token)
        elif step == "finishSecret":
            finish_secret(secrets_client, arn, token)
        else:
            raise ValueError(f"Invalid step: {step}")

        logger.info(f"Successfully completed {step} for secret {arn}")
        return {"statusCode": 200, "body": f"Successfully completed {step}"}

    except Exception as e:
        logger.error(f"Error rotating secret: {str(e)}", exc_info=True)
        raise


def create_secret(client: Any, arn: str, token: str) -> None:
    """
    Step 1: Create a new version of the secret with a new password.

    Args:
        client: Secrets Manager client
        arn: Secret ARN
        token: Rotation token
    """
    # Get current secret value
    current_dict = get_secret_dict(client, arn, "AWSCURRENT")

    # Determine secret type and generate new credentials
    secret_name = arn.split(':')[-1]

    if "postgres" in secret_name.lower() or "rds" in secret_name.lower():
        # Generate new PostgreSQL password
        new_password = generate_password(length=32)
        current_dict['password'] = new_password

    elif "neo4j" in secret_name.lower():
        # Generate new Neo4j password
        new_password = generate_password(length=32)
        current_dict['password'] = new_password

    elif "admin-master-key" in secret_name.lower():
        # Generate new admin master key
        new_key = generate_api_key()
        current_dict['key'] = new_key

    else:
        raise ValueError(f"Unsupported secret type: {secret_name}")

    # Store new secret version
    client.put_secret_value(
        SecretId=arn,
        ClientRequestToken=token,
        SecretString=json.dumps(current_dict),
        VersionStages=['AWSPENDING']
    )

    logger.info(f"Created new secret version for {arn}")


def set_secret(client: Any, rds_client: Any, arn: str, token: str) -> None:
    """
    Step 2: Update the actual service (database, etc.) with the new credentials.

    Args:
        client: Secrets Manager client
        rds_client: RDS client
        arn: Secret ARN
        token: Rotation token
    """
    pending_dict = get_secret_dict(client, arn, "AWSPENDING", token)
    secret_name = arn.split(':')[-1]

    if "postgres" in secret_name.lower() or "rds" in secret_name.lower():
        # Update PostgreSQL/RDS password
        update_rds_password(rds_client, pending_dict)

    elif "neo4j" in secret_name.lower():
        # Update Neo4j password via Cypher
        update_neo4j_password(pending_dict)

    elif "admin-master-key" in secret_name.lower():
        # Admin key doesn't need external update - it's validated in-app
        logger.info("Admin master key updated in Secrets Manager")

    logger.info(f"Set new credentials for {arn}")


def test_secret(client: Any, arn: str, token: str) -> None:
    """
    Step 3: Test the new secret to ensure it works.

    Args:
        client: Secrets Manager client
        arn: Secret ARN
        token: Rotation token
    """
    pending_dict = get_secret_dict(client, arn, "AWSPENDING", token)
    secret_name = arn.split(':')[-1]

    if "postgres" in secret_name.lower() or "rds" in secret_name.lower():
        # Test PostgreSQL connection
        test_postgres_connection(pending_dict)

    elif "neo4j" in secret_name.lower():
        # Test Neo4j connection
        test_neo4j_connection(pending_dict)

    elif "admin-master-key" in secret_name.lower():
        # Admin key validation
        if not pending_dict.get('key'):
            raise ValueError("Admin master key is empty")

    logger.info(f"Successfully tested new secret for {arn}")


def finish_secret(client: Any, arn: str, token: str) -> None:
    """
    Step 4: Finalize the rotation by updating version stages.

    Args:
        client: Secrets Manager client
        arn: Secret ARN
        token: Rotation token
    """
    # Get current version
    metadata = client.describe_secret(SecretId=arn)
    current_version = None

    for version, stages in metadata['VersionIdsToStages'].items():
        if 'AWSCURRENT' in stages:
            if version == token:
                # Already current
                logger.info(f"Version {token} already marked as AWSCURRENT")
                return
            current_version = version
            break

    # Move AWSCURRENT stage to new version
    client.update_secret_version_stage(
        SecretId=arn,
        VersionStage='AWSCURRENT',
        MoveToVersionId=token,
        RemoveFromVersionId=current_version
    )

    logger.info(f"Finished rotation for {arn}")


# Helper functions

def get_secret_dict(client: Any, arn: str, stage: str, token: str = None) -> Dict[str, Any]:
    """Get secret value as dictionary."""
    params = {'SecretId': arn, 'VersionStage': stage}
    if token:
        params['VersionId'] = token

    response = client.get_secret_value(**params)
    return json.loads(response['SecretString'])


def generate_password(length: int = 32) -> str:
    """Generate a secure random password."""
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    return ''.join(secrets.choice(alphabet) for _ in range(length))


def generate_api_key() -> str:
    """Generate a secure API key."""
    return secrets.token_urlsafe(32)


def update_rds_password(rds_client: Any, secret_dict: Dict[str, Any]) -> None:
    """Update RDS database password."""
    try:
        # Modify DB instance master password
        db_instance_id = secret_dict.get('dbInstanceIdentifier')
        if not db_instance_id:
            logger.warning("No DB instance ID found, skipping RDS password update")
            return

        rds_client.modify_db_instance(
            DBInstanceIdentifier=db_instance_id,
            MasterUserPassword=secret_dict['password'],
            ApplyImmediately=True
        )
        logger.info(f"Updated RDS password for {db_instance_id}")

    except Exception as e:
        logger.error(f"Failed to update RDS password: {e}")
        raise


def update_neo4j_password(secret_dict: Dict[str, Any]) -> None:
    """Update Neo4j password via Cypher query."""
    try:
        from neo4j import GraphDatabase

        uri = secret_dict.get('uri', os.getenv('NEO4J_URI'))
        username = secret_dict.get('username', 'neo4j')
        old_password = secret_dict.get('old_password')
        new_password = secret_dict['password']

        # Connect with old password
        driver = GraphDatabase.driver(uri, auth=(username, old_password))

        # Update password
        with driver.session() as session:
            session.run(f"ALTER USER {username} SET PASSWORD $password", password=new_password)

        driver.close()
        logger.info(f"Updated Neo4j password for user {username}")

    except Exception as e:
        logger.error(f"Failed to update Neo4j password: {e}")
        raise


def test_postgres_connection(secret_dict: Dict[str, Any]) -> None:
    """Test PostgreSQL connection with new credentials."""
    try:
        import psycopg2

        conn = psycopg2.connect(
            host=secret_dict['host'],
            port=secret_dict.get('port', 5432),
            database=secret_dict['dbname'],
            user=secret_dict['username'],
            password=secret_dict['password']
        )
        conn.close()
        logger.info("PostgreSQL connection test successful")

    except Exception as e:
        logger.error(f"PostgreSQL connection test failed: {e}")
        raise


def test_neo4j_connection(secret_dict: Dict[str, Any]) -> None:
    """Test Neo4j connection with new credentials."""
    try:
        from neo4j import GraphDatabase

        uri = secret_dict.get('uri', os.getenv('NEO4J_URI'))
        driver = GraphDatabase.driver(
            uri,
            auth=(secret_dict.get('username', 'neo4j'), secret_dict['password'])
        )

        # Test connection
        with driver.session() as session:
            session.run("RETURN 1")

        driver.close()
        logger.info("Neo4j connection test successful")

    except Exception as e:
        logger.error(f"Neo4j connection test failed: {e}")
        raise
