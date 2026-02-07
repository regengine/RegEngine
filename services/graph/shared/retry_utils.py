"""
Retry and exponential backoff utilities for RegEngine services.

This module provides robust connection retry logic with exponential backoff
to handle transient failures in databases, Kafka, and other external services.
"""

import time
import logging
from typing import Callable, TypeVar, Optional, List, Type
from functools import wraps
import random

logger = logging.getLogger(__name__)

T = TypeVar('T')


class RetryConfig:
    """Configuration for retry behavior."""

    def __init__(
        self,
        max_attempts: int = 5,
        initial_delay: float = 1.0,
        max_delay: float = 60.0,
        exponential_base: float = 2.0,
        jitter: bool = True
    ):
        """
        Initialize retry configuration.

        Args:
            max_attempts: Maximum number of retry attempts
            initial_delay: Initial delay in seconds before first retry
            max_delay: Maximum delay in seconds between retries
            exponential_base: Base for exponential backoff calculation
            jitter: Whether to add random jitter to delay
        """
        self.max_attempts = max_attempts
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.jitter = jitter

    def get_delay(self, attempt: int) -> float:
        """
        Calculate delay for given attempt number.

        Args:
            attempt: Current attempt number (0-indexed)

        Returns:
            Delay in seconds
        """
        # Exponential backoff: delay = initial_delay * (base ^ attempt)
        delay = min(
            self.initial_delay * (self.exponential_base ** attempt),
            self.max_delay
        )

        # Add jitter to prevent thundering herd
        if self.jitter:
            delay = delay * (0.5 + random.random())

        return delay


def retry_with_backoff(
    retryable_exceptions: Optional[List[Type[Exception]]] = None,
    config: Optional[RetryConfig] = None,
    on_retry: Optional[Callable[[Exception, int], None]] = None
):
    """
    Decorator for retrying functions with exponential backoff.

    Args:
        retryable_exceptions: List of exception types to retry on
        config: RetryConfig instance
        on_retry: Callback function called on each retry attempt

    Returns:
        Decorated function with retry logic

    Example:
        @retry_with_backoff(
            retryable_exceptions=[ConnectionError, TimeoutError],
            config=RetryConfig(max_attempts=3, initial_delay=2.0)
        )
        def connect_to_database():
            return db.connect()
    """
    if retryable_exceptions is None:
        retryable_exceptions = [Exception]

    if config is None:
        config = RetryConfig()

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            last_exception = None

            for attempt in range(config.max_attempts):
                try:
                    return func(*args, **kwargs)

                except tuple(retryable_exceptions) as e:
                    last_exception = e

                    if attempt < config.max_attempts - 1:
                        delay = config.get_delay(attempt)
                        logger.warning(
                            f"Attempt {attempt + 1}/{config.max_attempts} failed for {func.__name__}: {e}. "
                            f"Retrying in {delay:.2f}s..."
                        )

                        if on_retry:
                            on_retry(e, attempt)

                        time.sleep(delay)
                    else:
                        logger.error(
                            f"All {config.max_attempts} attempts failed for {func.__name__}: {e}"
                        )

            # Re-raise the last exception if all retries failed
            raise last_exception

        return wrapper

    return decorator


class Neo4jConnectionManager:
    """Connection manager for Neo4j with retry logic."""

    def __init__(
        self,
        uri: str,
        username: str,
        password: str,
        retry_config: Optional[RetryConfig] = None
    ):
        """
        Initialize Neo4j connection manager.

        Args:
            uri: Neo4j connection URI
            username: Neo4j username
            password: Neo4j password
            retry_config: Retry configuration
        """
        self.uri = uri
        self.username = username
        self.password = password
        self.retry_config = retry_config or RetryConfig(
            max_attempts=5,
            initial_delay=2.0,
            max_delay=30.0
        )
        self.driver = None

    @retry_with_backoff(
        retryable_exceptions=[ConnectionError, OSError, Exception],
        config=None  # Will be set in __init__
    )
    def connect(self):
        """Establish connection to Neo4j with retry logic."""
        from neo4j import GraphDatabase
        from neo4j.exceptions import ServiceUnavailable, AuthError

        try:
            self.driver = GraphDatabase.driver(
                self.uri,
                auth=(self.username, self.password),
                max_connection_lifetime=3600,
                max_connection_pool_size=50,
                connection_acquisition_timeout=60
            )

            # Verify connection
            self.driver.verify_connectivity()
            logger.info(f"Successfully connected to Neo4j at {self.uri}")

        except (ServiceUnavailable, AuthError) as e:
            logger.error(f"Failed to connect to Neo4j: {e}")
            raise ConnectionError(f"Neo4j connection failed: {e}")

    def get_driver(self):
        """Get Neo4j driver, connecting if necessary."""
        if self.driver is None:
            self.connect()
        return self.driver

    def close(self):
        """Close Neo4j connection."""
        if self.driver:
            self.driver.close()
            self.driver = None


class PostgresConnectionManager:
    """Connection manager for PostgreSQL with retry logic."""

    def __init__(
        self,
        host: str,
        port: int,
        database: str,
        user: str,
        password: str,
        retry_config: Optional[RetryConfig] = None
    ):
        """
        Initialize PostgreSQL connection manager.

        Args:
            host: Database host
            port: Database port
            database: Database name
            user: Database user
            password: Database password
            retry_config: Retry configuration
        """
        self.host = host
        self.port = port
        self.database = database
        self.user = user
        self.password = password
        self.retry_config = retry_config or RetryConfig(
            max_attempts=5,
            initial_delay=1.0,
            max_delay=30.0
        )
        self.connection = None

    def connect(self):
        """Establish connection to PostgreSQL with retry logic."""
        import psycopg2
        from psycopg2 import OperationalError

        @retry_with_backoff(
            retryable_exceptions=[OperationalError],
            config=self.retry_config
        )
        def _connect():
            self.connection = psycopg2.connect(
                host=self.host,
                port=self.port,
                database=self.database,
                user=self.user,
                password=self.password,
                connect_timeout=10
            )
            logger.info(f"Successfully connected to PostgreSQL at {self.host}:{self.port}/{self.database}")

        _connect()

    def get_connection(self):
        """Get PostgreSQL connection, connecting if necessary."""
        if self.connection is None or self.connection.closed:
            self.connect()
        return self.connection

    def close(self):
        """Close PostgreSQL connection."""
        if self.connection and not self.connection.closed:
            self.connection.close()
            self.connection = None


class KafkaProducerManager:
    """Connection manager for Kafka producer with retry logic."""

    def __init__(
        self,
        bootstrap_servers: str,
        retry_config: Optional[RetryConfig] = None,
        **kafka_config
    ):
        """
        Initialize Kafka producer manager.

        Args:
            bootstrap_servers: Kafka bootstrap servers
            retry_config: Retry configuration
            **kafka_config: Additional Kafka configuration
        """
        self.bootstrap_servers = bootstrap_servers
        self.retry_config = retry_config or RetryConfig(
            max_attempts=5,
            initial_delay=2.0,
            max_delay=30.0
        )
        self.kafka_config = kafka_config
        self.producer = None

    def connect(self):
        """Establish connection to Kafka with retry logic."""
        from kafka import KafkaProducer
        from kafka.errors import NoBrokersAvailable, KafkaError

        @retry_with_backoff(
            retryable_exceptions=[NoBrokersAvailable, KafkaError],
            config=self.retry_config
        )
        def _connect():
            self.producer = KafkaProducer(
                bootstrap_servers=self.bootstrap_servers,
                **self.kafka_config
            )
            logger.info(f"Successfully connected to Kafka at {self.bootstrap_servers}")

        _connect()

    def get_producer(self):
        """Get Kafka producer, connecting if necessary."""
        if self.producer is None:
            self.connect()
        return self.producer

    def close(self):
        """Close Kafka producer connection."""
        if self.producer:
            self.producer.close()
            self.producer = None


class KafkaConsumerManager:
    """Connection manager for Kafka consumer with retry logic."""

    def __init__(
        self,
        bootstrap_servers: str,
        topics: List[str],
        group_id: str,
        retry_config: Optional[RetryConfig] = None,
        **kafka_config
    ):
        """
        Initialize Kafka consumer manager.

        Args:
            bootstrap_servers: Kafka bootstrap servers
            topics: List of topics to subscribe to
            group_id: Consumer group ID
            retry_config: Retry configuration
            **kafka_config: Additional Kafka configuration
        """
        self.bootstrap_servers = bootstrap_servers
        self.topics = topics
        self.group_id = group_id
        self.retry_config = retry_config or RetryConfig(
            max_attempts=5,
            initial_delay=2.0,
            max_delay=30.0
        )
        self.kafka_config = kafka_config
        self.consumer = None

    def connect(self):
        """Establish connection to Kafka with retry logic."""
        from kafka import KafkaConsumer
        from kafka.errors import NoBrokersAvailable, KafkaError

        @retry_with_backoff(
            retryable_exceptions=[NoBrokersAvailable, KafkaError],
            config=self.retry_config
        )
        def _connect():
            self.consumer = KafkaConsumer(
                *self.topics,
                bootstrap_servers=self.bootstrap_servers,
                group_id=self.group_id,
                **self.kafka_config
            )
            logger.info(f"Successfully connected Kafka consumer for topics {self.topics}")

        _connect()

    def get_consumer(self):
        """Get Kafka consumer, connecting if necessary."""
        if self.consumer is None:
            self.connect()
        return self.consumer

    def close(self):
        """Close Kafka consumer connection."""
        if self.consumer:
            self.consumer.close()
            self.consumer = None


# Example usage
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # Example: Retry a function with custom configuration
    @retry_with_backoff(
        retryable_exceptions=[ConnectionError],
        config=RetryConfig(max_attempts=3, initial_delay=1.0)
    )
    def flaky_function():
        import random
        if random.random() < 0.7:
            raise ConnectionError("Random failure")
        return "Success!"

    try:
        result = flaky_function()
        print(f"Result: {result}")
    except ConnectionError as e:
        print(f"Failed after all retries: {e}")
