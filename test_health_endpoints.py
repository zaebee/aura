#!/usr/bin/env python3
"""
Test script for health check endpoints.
Run this after starting services with docker-compose.
"""

import sys
import time

import requests


def test_gateway_health_endpoints():
    """Test API Gateway health endpoints"""
    base_url = "http://localhost:8000"
    endpoints = {
        "/healthz": "liveness",
        "/readyz": "readiness",
        "/health": "detailed health",
    }

    print("Testing API Gateway Health Endpoints\n" + "=" * 50)

    for endpoint, description in endpoints.items():
        url = f"{base_url}{endpoint}"
        try:
            response = requests.get(url, timeout=5)
            status = "✓ PASS" if response.status_code == 200 else "✗ FAIL"
            print(f"{status} [{endpoint}] ({description})")
            print(f"  Status: {response.status_code}")
            print(f"  Response: {response.json()}")
            print()
        except requests.exceptions.RequestException as e:
            print(f"✗ FAIL [{endpoint}] ({description})")
            print(f"  Error: {e}")
            print()
            return False

    return True


def test_core_service_grpc_health():
    """Test Core Service gRPC health using grpc_health_probe if available"""
    print("\nTesting Core Service gRPC Health\n" + "=" * 50)

    try:
        import subprocess

        result = subprocess.run(
            ["grpc_health_probe", "-addr=localhost:50051"],
            capture_output=True,
            text=True,
            timeout=5,
        )

        if result.returncode == 0:
            print("✓ PASS Core Service gRPC Health")
            print(f"  {result.stdout.strip()}")
            return True
        else:
            print("✗ FAIL Core Service gRPC Health")
            print(f"  {result.stderr.strip()}")
            return False
    except FileNotFoundError:
        print("⚠ SKIP grpc_health_probe not installed")
        print(
            "  Install: go install github.com/grpc-ecosystem/grpc-health-probe@latest"
        )
        return None
    except Exception as e:
        print(f"✗ ERROR: {e}")
        return False


def test_readiness_when_core_unavailable():
    """Test that readiness endpoint returns 503 when core service is down"""
    print("\nTesting Readiness Failure Scenario\n" + "=" * 50)
    print("(This test requires core service to be stopped)")

    url = "http://localhost:8000/readyz"
    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 503:
            print("✓ PASS Readiness returns 503 when core unavailable")
            print(f"  Response: {response.json()}")
        elif response.status_code == 200:
            print("⚠ INFO Readiness returns 200 (core service is running)")
            print("  To test failure scenario, stop core-service first")
        else:
            print(f"✗ FAIL Unexpected status code: {response.status_code}")
        print()
    except requests.exceptions.RequestException as e:
        print(f"✗ ERROR: {e}")
        print()


def main():
    print("\n" + "=" * 50)
    print("Health Endpoints Test Suite")
    print("=" * 50 + "\n")

    print("Waiting for services to be ready...")
    time.sleep(2)

    results = []

    # Test gateway endpoints
    results.append(test_gateway_health_endpoints())

    # Test gRPC health (optional)
    grpc_result = test_core_service_grpc_health()
    if grpc_result is not None:
        results.append(grpc_result)

    # Test failure scenario info
    test_readiness_when_core_unavailable()

    print("\n" + "=" * 50)
    print("Test Summary")
    print("=" * 50)

    passed = sum(1 for r in results if r is True)
    failed = sum(1 for r in results if r is False)

    print(f"Passed: {passed}")
    print(f"Failed: {failed}")

    if failed > 0:
        print("\n❌ Some tests failed")
        sys.exit(1)
    else:
        print("\n✅ All tests passed!")
        sys.exit(0)


if __name__ == "__main__":
    main()
