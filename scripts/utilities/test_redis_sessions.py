#!/usr/bin/env python3
"""
Quick integration test for Redis sessions.
Tests basic flow: login → verify session in Redis → refresh → logout
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from services.shared.secret_redaction import read_secret  # noqa: E402

BASE_URL = os.environ.get("TEST_BASE_URL", "http://localhost:8400")


def run_redis_cmd(cmd):
    """Execute Redis CLI command"""
    result = subprocess.run(
        ["docker", "exec", "regengine-redis-1", "redis-cli"] + cmd.split(), capture_output=True, text=True
    )
    return result.stdout.strip()


def test_redis_sessions():
    print("=" * 60)
    print("Redis Sessions Integration Test")
    print("=" * 60)

    # Test 1: Redis connectivity
    print("\n1. Testing Redis connectivity...")
    pong = run_redis_cmd("PING")
    if pong == "PONG":
        print("   ✅ Redis is accessible")
    else:
        print(f"   ❌ Redis not responding: {pong}")
        return False

    # Test 2: Check initial key count
    print("\n2. Checking initial Redis state...")
    initial_keys = run_redis_cmd("DBSIZE")
    print(f"   Initial keys in Redis: {initial_keys}")

    # Test 3: Login
    print("\n3. Testing login endpoint...")
    # Credentials come from the environment so no committed password can
    # drift into a shared or production-adjacent account. The defaults only
    # match the local throwaway dev seed.
    login_data = {
        "email": os.environ.get("TEST_USER_EMAIL", "admin@example.com"),
        "password": read_secret("TEST_USER_PASSWORD", default="password123"),
    }

    try:
        response = requests.post(f"{BASE_URL}/auth/login", json=login_data)
        print(f"   Status: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            access_token = data.get("access_token")
            refresh_token = data.get("refresh_token")
            print(f"   ✅ Login successful")
            # Masked fingerprints only: a 20-char token prefix in a log
            # still exposes enough of the credential to abuse it.
            # Log presence only — never print token material (CodeQL clear-text-logging).
            print(f"   Access token: {'present' if access_token else 'missing'}")
            print(f"   Refresh token: {'present' if refresh_token else 'missing'}")
        else:
            print(f"   ❌ Login failed: {response.text}")
            print(f"   Note: Make sure test user exists in database")
            return False
    except Exception as e:
        print(f"   ❌ Connection error: {e}")
        print(f"   Make sure admin-api is running: docker-compose ps admin-api")
        return False

    # Test 4: Verify session in Redis
    print("\n4. Verifying session created in Redis...")
    session_keys = run_redis_cmd("KEYS session:*")
    user_session_keys = run_redis_cmd("KEYS user_sessions:*")
    token_hash_keys = run_redis_cmd("KEYS token_hash:*")

    print(f"   Session keys: {len(session_keys.split()) if session_keys else 0}")
    print(f"   User session keys: {len(user_session_keys.split()) if user_session_keys else 0}")
    print(f"   Token hash keys: {len(token_hash_keys.split()) if token_hash_keys else 0}")

    if session_keys and user_session_keys and token_hash_keys:
        print("   ✅ Session data structures created in Redis")

        # Inspect session data
        session_key = session_keys.split()[0] if session_keys else None
        if session_key:
            print(f"\n   Inspecting {session_key}...")
            session_data = run_redis_cmd(f"HGETALL {session_key}")
            print(f"   Data preview: {session_data[:200]}...")
    else:
        print("   ❌ Session not found in Redis")
        return False

    # Test 5: List sessions
    print("\n5. Testing session listing...")
    headers = {"Authorization": f"Bearer {access_token}"}
    response = requests.get(f"{BASE_URL}/auth/sessions", headers=headers)

    if response.status_code == 200:
        sessions = response.json()
        print(f"   ✅ Found {len(sessions)} active session(s)")
        if sessions:
            print(f"   Session ID: {sessions[0].get('id')}")
            print(f"   User Agent: {sessions[0].get('user_agent', 'N/A')[:50]}")
    else:
        print(f"   ❌ Failed to list sessions: {response.status_code}")

    # Test 6: Refresh token
    print("\n6. Testing token refresh...")
    refresh_data = {"refresh_token": refresh_token}
    response = requests.post(f"{BASE_URL}/auth/refresh", json=refresh_data)

    if response.status_code == 200:
        data = response.json()
        new_access_token = data.get("access_token")
        new_refresh_token = data.get("refresh_token")
        print(f"   ✅ Token refresh successful")
        print(f"   New access token: {'present' if new_access_token else 'missing'}")
        print(f"   Token rotation: {'Yes' if new_refresh_token != refresh_token else 'No'}")
    else:
        print(f"   ❌ Token refresh failed: {response.status_code}")

    # Test 7: Logout all
    print("\n7. Testing logout all...")
    response = requests.post(f"{BASE_URL}/auth/logout-all", headers={"Authorization": f"Bearer {access_token}"})

    if response.status_code == 200:
        data = response.json()
        revoked_count = data.get("revoked_count", 0)
        print(f"   ✅ Logout successful")
        print(f"   Revoked {revoked_count} session(s)")
    else:
        print(f"   ❌ Logout failed: {response.status_code}")

    # Test 8: Verify revocation in Redis
    print("\n8. Verifying revocation in Redis...")
    if session_key:
        is_revoked = run_redis_cmd(f"HGET {session_key} is_revoked")
        if is_revoked == "true":
            print(f"   ✅ Session marked as revoked in Redis")
        else:
            print(f"   ⚠️  Session revocation status: {is_revoked}")

    # Test 9: Final key count
    print("\n9. Final Redis state...")
    final_keys = run_redis_cmd("DBSIZE")
    print(f"   Final keys in Redis: {final_keys}")

    print("\n" + "=" * 60)
    print("✅ Integration test complete!")
    print("=" * 60)

    return True


if __name__ == "__main__":
    success = test_redis_sessions()
    exit(0 if success else 1)
