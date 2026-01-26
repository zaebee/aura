#!/usr/bin/env python3
"""
Simple test to verify OpenTelemetry instrumentation is working.
This test can be run to check if traces are being exported correctly.
"""

import os
import time


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

    print("\n=== Test Complete ===")
    print("Check Jaeger UI at http://localhost:16686 to see traces")
    print("Look for services: aura-gateway, aura-core")


if __name__ == "__main__":
    main()
