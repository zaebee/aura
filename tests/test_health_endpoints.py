#!/usr/bin/env python3
"""
Test script for health check endpoints.
Run this after starting services with docker-compose.
"""

import sys
import time

import requests
import structlog

logger = structlog.get_logger(__name__)


def test_gateway_health_endpoints():
    """Test API Gateway health endpoints"""
    base_url = "http://localhost:8000"
    endpoints = {
        "/healthz": "liveness",
        "/readyz": "readiness",
        "/health": "detailed health",
    }
    all_passed = True

    logger.info("testing_api_gateway_health")

    for endpoint, description in endpoints.items():
        url = f"{base_url}{endpoint}"
        try:
            response = requests.get(url, timeout=5)
            # We expect all endpoints to be healthy and return 200 for this test
            if response.status_code == 200:
                logger.info("endpoint_pass", endpoint=endpoint, description=description)
            else:
                logger.error("endpoint_fail",
                             endpoint=endpoint,
                             description=description,
                             status_code=response.status_code)
                all_passed = False

            try:
                resp_data = response.json()
            except requests.exceptions.JSONDecodeError:
                resp_data = response.text

            logger.info("endpoint_response", endpoint=endpoint, response=resp_data)
        except requests.exceptions.RequestException as e:
            logger.error("endpoint_request_error",
                         endpoint=endpoint,
                         description=description,
                         error=str(e))
            all_passed = False

    return all_passed


def test_core_service_grpc_health():
    """Test Core Service gRPC health using grpc_health_probe if available"""
    logger.info("testing_core_service_grpc_health")

    try:
        import subprocess

        result = subprocess.run(
            ["grpc_health_probe", "-addr=localhost:50051"],
            capture_output=True,
            text=True,
            timeout=5,
        )

        if result.returncode == 0:
            logger.info("grpc_health_pass", output=result.stdout.strip())
            return True
        else:
            logger.error("grpc_health_fail", output=result.stderr.strip())
            return False
    except FileNotFoundError:
        logger.warning("grpc_health_skipped",
                       reason="grpc_health_probe not installed")
        return None
    except Exception as e:
        logger.error("grpc_health_error", error=str(e))
        return False


def test_readiness_when_core_unavailable():
    """Test that readiness endpoint returns 503 when core service is down"""
    logger.info("testing_readiness_failure_scenario",
                note="requires core service to be stopped")

    url = "http://localhost:8000/readyz"
    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 503:
            logger.info("readiness_fail_scenario_pass", response=response.json())
        elif response.status_code == 200:
            logger.info("readiness_core_running_info",
                        note="To test failure scenario, stop core-service first")
        else:
            logger.error("readiness_unexpected_status", status_code=response.status_code)
    except requests.exceptions.RequestException as e:
        logger.error("readiness_request_error", error=str(e))


def main():
    # Configure logging
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(),
        ]
    )
    logger.info("starting_health_endpoint_tests")

    logger.info("waiting_for_services")
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

    passed = sum(1 for r in results if r is True)
    failed = sum(1 for r in results if r is False)

    logger.info("test_summary", passed=passed, failed=failed)

    if failed > 0:
        logger.error("tests_failed")
        sys.exit(1)
    else:
        logger.info("all_tests_passed")
        sys.exit(0)


if __name__ == "__main__":
    main()
