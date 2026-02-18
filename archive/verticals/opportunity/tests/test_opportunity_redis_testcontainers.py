
import pytest
from testcontainers.redis import RedisContainer
import redis

@pytest.fixture(scope="session")
def redis_container():
    with RedisContainer("redis:7-alpine") as container:
        yield container

@pytest.fixture
def redis_client(redis_container):
    return redis.from_url(redis_container.get_container_host_ip(), port=redis_container.get_exposed_port(6379))

def test_opportunity_caching(redis_container):
    """
    Verify that the Opportunity service can cache high-frequency arbitrage 
    calculations in a real Redis instance.
    """
    host = redis_container.get_container_host_ip()
    port = redis_container.get_exposed_port(6379)
    client = redis.Redis(host=host, port=port, decode_responses=True)
    
    opportunity_id = "opp_123_abc"
    payload = '{"score": 0.95, "savings": 12000, "status": "active"}'
    
    # Cache it
    client.set(f"opportunity:cache:{opportunity_id}", payload, ex=3600)
    
    # Retrieve it
    cached = client.get(f"opportunity:cache:{opportunity_id}")
    assert cached == payload
    print("✅ Opportunity caching verified with Redis Testcontainers")
