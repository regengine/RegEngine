"""
CloudWatch logging integration for production environments.

This module provides CloudWatch Logs integration for RegEngine services,
enabling centralized log aggregation in AWS production deployments.
"""

import os
import logging
import boto3
from typing import Optional
from datetime import datetime, timezone
import json


class CloudWatchHandler(logging.Handler):
    """
    Custom logging handler that sends logs to AWS CloudWatch Logs.

    This handler batches log messages and sends them to CloudWatch in production,
    while falling back to standard logging in local development.
    """

    def __init__(
        self,
        log_group: str,
        log_stream: str,
        region: str = "us-east-1",
        batch_size: int = 10,
        batch_interval: int = 5
    ):
        """
        Initialize CloudWatch logging handler.

        Args:
            log_group: CloudWatch log group name
            log_stream: CloudWatch log stream name (typically service name + instance ID)
            region: AWS region for CloudWatch
            batch_size: Number of messages to batch before sending
            batch_interval: Seconds to wait before flushing batch
        """
        super().__init__()
        self.log_group = log_group
        self.log_stream = log_stream
        self.region = region
        self.batch_size = batch_size
        self.batch = []
        self.sequence_token: Optional[str] = None

        # Initialize CloudWatch client
        try:
            self.client = boto3.client('logs', region_name=region)
            self._ensure_log_stream_exists()
        except Exception as e:
            logging.warning(f"Failed to initialize CloudWatch client: {e}")
            self.client = None

    def _ensure_log_stream_exists(self):
        """Create log group and stream if they don't exist."""
        if not self.client:
            return

        try:
            # Create log group
            self.client.create_log_group(logGroupName=self.log_group)
        except self.client.exceptions.ResourceAlreadyExistsException:
            pass
        except Exception as e:
            logging.warning(f"Failed to create log group: {e}")

        try:
            # Create log stream
            self.client.create_log_stream(
                logGroupName=self.log_group,
                logStreamName=self.log_stream
            )
        except self.client.exceptions.ResourceAlreadyExistsException:
            # Get the sequence token for existing stream
            try:
                response = self.client.describe_log_streams(
                    logGroupName=self.log_group,
                    logStreamNamePrefix=self.log_stream
                )
                if response['logStreams']:
                    self.sequence_token = response['logStreams'][0].get('uploadSequenceToken')
            except Exception as e:
                logging.warning(f"Failed to get sequence token: {e}")
        except Exception as e:
            logging.warning(f"Failed to create log stream: {e}")

    def emit(self, record: logging.LogRecord):
        """
        Emit a log record to CloudWatch.

        Args:
            record: Log record to emit
        """
        if not self.client:
            return

        try:
            # Format the log message
            log_message = self.format(record)

            # Add to batch
            self.batch.append({
                'timestamp': int(record.created * 1000),  # CloudWatch expects milliseconds
                'message': log_message
            })

            # Flush if batch is full
            if len(self.batch) >= self.batch_size:
                self.flush()

        except Exception as e:
            logging.warning(f"Failed to emit log to CloudWatch: {e}")

    def flush(self):
        """Flush the batch of log messages to CloudWatch."""
        if not self.batch or not self.client:
            return

        try:
            # Sort by timestamp (required by CloudWatch)
            self.batch.sort(key=lambda x: x['timestamp'])

            # Build put_log_events request
            kwargs = {
                'logGroupName': self.log_group,
                'logStreamName': self.log_stream,
                'logEvents': self.batch
            }

            if self.sequence_token:
                kwargs['sequenceToken'] = self.sequence_token

            # Send to CloudWatch
            response = self.client.put_log_events(**kwargs)

            # Update sequence token
            self.sequence_token = response.get('nextSequenceToken')

            # Clear batch
            self.batch = []

        except Exception as e:
            logging.warning(f"Failed to flush logs to CloudWatch: {e}")
            # Don't clear batch on failure - will retry

    def close(self):
        """Close handler and flush remaining logs."""
        self.flush()
        super().close()


def configure_cloudwatch_logging(
    service_name: str,
    log_level: str = "INFO",
    environment: str = "production",
    region: str = "us-east-1"
) -> logging.Logger:
    """
    Configure CloudWatch logging for a service.

    Args:
        service_name: Name of the service (e.g., 'ingestion', 'nlp')
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        environment: Deployment environment (production, staging, development)
        region: AWS region

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(service_name)
    logger.setLevel(getattr(logging, log_level.upper()))

    # Only enable CloudWatch in production/staging
    if environment in ["production", "staging"]:
        # Generate unique log stream name (service + instance + timestamp)
        instance_id = os.getenv("ECS_CONTAINER_METADATA_URI_V4", "local")
        if instance_id != "local":
            # Extract task ID from ECS metadata
            instance_id = instance_id.split("/")[-1][:8]

        log_stream = f"{service_name}-{instance_id}-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"

        # Create CloudWatch handler
        cw_handler = CloudWatchHandler(
            log_group=f"/regengine/{environment}/{service_name}",
            log_stream=log_stream,
            region=region
        )

        # JSON formatter for structured logging
        formatter = logging.Formatter(
            '{"timestamp":"%(asctime)s","level":"%(levelname)s","service":"%(name)s","message":"%(message)s"}'
        )
        cw_handler.setFormatter(formatter)
        logger.addHandler(cw_handler)

    # Always add console handler for local debugging
    console_handler = logging.StreamHandler()
    console_handler.setLevel(getattr(logging, log_level.upper()))
    console_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    return logger


def get_cloudwatch_config_for_ecs(service_name: str, environment: str = "production") -> dict:
    """
    Generate CloudWatch logging configuration for ECS task definitions.

    Args:
        service_name: Name of the service
        environment: Deployment environment

    Returns:
        ECS logConfiguration dict for task definition
    """
    return {
        "logDriver": "awslogs",
        "options": {
            "awslogs-group": f"/regengine/{environment}/{service_name}",
            "awslogs-region": os.getenv("AWS_DEFAULT_REGION", "us-east-1"),
            "awslogs-stream-prefix": service_name,
            "awslogs-create-group": "true"
        }
    }


# Example usage for services
if __name__ == "__main__":
    # Configure logger with CloudWatch
    logger = configure_cloudwatch_logging(
        service_name="example-service",
        log_level="INFO",
        environment=os.getenv("ENVIRONMENT", "development")
    )

    logger.info("CloudWatch logging configured successfully")
    logger.warning("This is a warning message")
    logger.error("This is an error message", extra={"tenant_id": "test-123"})
