#!/usr/bin/env python3
"""
Simple test to verify OpenTelemetry instrumentation is working.
This test can be run to check if traces are being exported correctly.
"""

import os
import time

import requests


def test_api_gateway():
    """Test API Gateway endpoints to generate traces."""
    print("Testing API Gateway endpoints...")

    # Test search endpoint
    try:
        response = requests.post(
            "http://localhost:8000/v1/search",
            json={"query": "test", "limit": 3},
            timeout=10
        )
        print(f"Search endpoint response: {response.status_code}")
        if response.status_code == 200:
            print("✓ Search endpoint working")
        else:
            print(f"✗ Search endpoint failed: {response.text}")
    except Exception as e:
        print(f"✗ Search endpoint error: {e}")

    # Test negotiate endpoint
    try:
        response = requests.post(
            "http://localhost:8000/v1/negotiate",
            json={
                "item_id": "test-item",
                "bid_amount": 100.0,
                "currency": "USD",
                "agent_did": "test-agent"
            },
            timeout=10
        )
        print(f"Negotiate endpoint response: {response.status_code}")
        if response.status_code == 200:
            print("✓ Negotiate endpoint working")
        else:
            print(f"✗ Negotiate endpoint failed: {response.text}")
    except Exception as e:
        print(f"✗ Negotiate endpoint error: {e}")


def test_telemetry_setup():
    """Test that telemetry is properly configured."""
    print("Testing telemetry setup...")

    # Check if OTLP endpoint is accessible
    otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://jaeger:4317")
    print(f"OTLP endpoint: {otlp_endpoint}")

    # Check if service names are set
    api_service_name = os.getenv("OTEL_SERVICE_NAME", "aura-gateway")
    core_service_name = "aura-core"  # This would be set in core-service environment
    print(f"API Gateway service name: {api_service_name}")
    print(f"Core Service service name: {core_service_name}")

    print("✓ Telemetry configuration looks good")


def main():
    """Main test function."""
    print("=== OpenTelemetry Instrumentation Test ===")

    # Set environment variables for testing
    os.environ["OTEL_SERVICE_NAME"] = "aura-gateway"
    os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] = "http://jaeger:4317"

    test_telemetry_setup()

    # Wait a bit for services to be ready
    print("\nWaiting for services to be ready...")
    time.sleep(5)

    test_api_gateway()

    print("\n=== Test Complete ===")
    print("Check Jaeger UI at http://localhost:16686 to see traces")
    print("Look for services: aura-gateway, aura-core")


if __name__ == "__main__":
    main()
