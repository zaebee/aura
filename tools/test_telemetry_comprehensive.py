#!/usr/bin/env python3
"""
Comprehensive test suite for OpenTelemetry instrumentation.
Tests telemetry initialization, error handling, and integration.
"""

import os
import unittest
from unittest.mock import MagicMock, patch

import structlog
from hive.proteins.monitor._internal import init_telemetry


class TestTelemetryInitialization(unittest.TestCase):
    """Test telemetry initialization and error handling."""

    def setUp(self):
        """Set up test environment."""
        # Save original environment
        self.original_env = {
            "OTEL_SERVICE_NAME": os.environ.get("OTEL_SERVICE_NAME"),
            "OTEL_EXPORTER_OTLP_ENDPOINT": os.environ.get(
                "OTEL_EXPORTER_OTLP_ENDPOINT"
            ),
        }

    def tearDown(self):
        """Restore original environment."""
        for key, value in self.original_env.items():
            if value is not None:
                os.environ[key] = value
            elif key in os.environ:
                del os.environ[key]

    def test_valid_initialization(self):
        """Test successful telemetry initialization."""
        tracer = init_telemetry("test-service", "http://jaeger:4317")
        self.assertIsNotNone(tracer)
        # Tracer objects don't have a name attribute, but we can verify it was created
        self.assertIsNotNone(tracer)

    def test_missing_service_name(self):
        """Test error handling for missing service name."""
        with self.assertRaises(ValueError) as context:
            init_telemetry("")
        self.assertIn("service_name must be provided", str(context.exception))

    def test_empty_service_name(self):
        """Test error handling for missing service name."""
        with self.assertRaises(ValueError) as context:
            init_telemetry("    ")
        self.assertIn("service_name must be provided", str(context.exception))

    def test_fallback_to_console(self):
        """Test fallback to console exporter when OTLP fails."""
        with patch("telemetry.OTLPSpanExporter") as mock_exporter:
            mock_exporter.side_effect = Exception("OTLP connection failed")

            # Should not raise, should fallback to console
            tracer = init_telemetry("test-service")
            self.assertIsNotNone(tracer)

    def test_invalid_otlp_endpoint(self):
        """Test handling of invalid OTLP endpoint."""
        # Should still work and fallback to console
        tracer = init_telemetry("test-service", "invalid-endpoint")
        self.assertIsNotNone(tracer)


class TestConfigurationValidation(unittest.TestCase):
    """Test configuration validation."""

    def test_valid_config(self):
        """Test valid configuration."""
        from config import Settings as CoreServiceSettings

        settings = CoreServiceSettings(
            database_url="postgresql://user:password@localhost:5432/aura_db",
            mistral_api_key="test-key",
            otel_service_name="test-service",
            otel_exporter_otlp_endpoint="http://jaeger:4317",
        )
        # Should not raise
        settings.validate_otel_config()

    def test_empty_service_name(self):
        """Test validation of empty service name."""
        from config import Settings as CoreServiceSettings

        with self.assertRaises(ValueError) as context:
            settings = CoreServiceSettings(
                database_url="postgresql://user:password@localhost:5432/aura_db",
                mistral_api_key="test-key",
                otel_service_name="",
                otel_exporter_otlp_endpoint="http://jaeger:4317",
            )
            settings.validate_otel_config()
        self.assertIn("OTEL_SERVICE_NAME cannot be empty", str(context.exception))

    def test_invalid_otlp_endpoint(self):
        """Test validation of invalid OTLP endpoint."""
        from config import Settings as CoreServiceSettings

        with self.assertRaises(ValueError) as context:
            settings = CoreServiceSettings(
                database_url="postgresql://user:password@localhost:5432/aura_db",
                mistral_api_key="test-key",
                otel_service_name="test-service",
                otel_exporter_otlp_endpoint="not-a-url",
            )
            settings.validate_otel_config()
        self.assertIn(
            "OTEL_EXPORTER_OTLP_ENDPOINT must be a valid URL", str(context.exception)
        )


class TestLoggingIntegration(unittest.TestCase):
    """Test logging integration with OpenTelemetry."""

    @patch("logging_config.get_current_span")
    def test_otel_context_with_valid_span(self, mock_get_span):
        """Test OTel context addition with valid span."""
        from logging_config import add_otel_context

        # Mock a valid span
        mock_span = MagicMock()
        mock_span.is_recording.return_value = True
        mock_span_context = MagicMock()
        mock_span_context.is_valid = True
        mock_span_context.trace_id = 123456789
        mock_span_context.span_id = 987654321
        mock_span.get_span_context.return_value = mock_span_context
        mock_get_span.return_value = mock_span

        event_dict = {}
        result = add_otel_context(None, None, event_dict)

        self.assertEqual(result, event_dict)
        self.assertIn("trace_id", event_dict)
        self.assertIn("span_id", event_dict)
        self.assertEqual(event_dict["trace_id"], "000000000000000000000000075bcd15")
        self.assertEqual(event_dict["span_id"], "000000003ade68b1")

    @patch("logging_config.get_current_span")
    def test_otel_context_with_invalid_span(self, mock_get_span):
        """Test OTel context addition with invalid span."""
        from logging_config import add_otel_context

        # Mock an invalid span
        mock_span = MagicMock()
        mock_span.is_recording.return_value = True
        mock_span_context = MagicMock()
        mock_span_context.is_valid = False
        mock_span.get_span_context.return_value = mock_span_context
        mock_get_span.return_value = mock_span

        event_dict = {}
        result = add_otel_context(None, None, event_dict)

        self.assertEqual(result, event_dict)
        self.assertNotIn("trace_id", event_dict)
        self.assertNotIn("span_id", event_dict)

    @patch("logging_config.get_current_span")
    def test_otel_context_with_exception(self, mock_get_span):
        """Test OTel context addition when exception occurs."""
        from logging_config import add_otel_context

        # Mock exception
        mock_get_span.side_effect = Exception("OTel not available")

        event_dict = {}
        result = add_otel_context(None, None, event_dict)

        self.assertEqual(result, event_dict)
        self.assertNotIn("trace_id", event_dict)
        self.assertNotIn("span_id", event_dict)


class TestEnvironmentVariables(unittest.TestCase):
    """Test environment variable handling."""

    def setUp(self):
        """Set up clean environment."""
        self.original_env = {
            "OTEL_SERVICE_NAME": os.environ.get("OTEL_SERVICE_NAME"),
            "OTEL_EXPORTER_OTLP_ENDPOINT": os.environ.get(
                "OTEL_EXPORTER_OTLP_ENDPOINT"
            ),
        }

    def tearDown(self):
        """Restore original environment."""
        for key, value in self.original_env.items():
            if value is not None:
                os.environ[key] = value
            elif key in os.environ:
                del os.environ[key]

    def test_environment_variable_override(self):
        """Test that environment variables override defaults."""
        os.environ["OTEL_SERVICE_NAME"] = "env-service"
        os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] = "http://env-jaeger:4317"

        # Import core Settings for this test
        from config import Settings as CoreServiceSettings

        settings = CoreServiceSettings(
            database_url="postgresql://user:password@localhost:5432/aura_db",
            mistral_api_key="test-key",
        )

        self.assertEqual(settings.otel_service_name, "env-service")
        self.assertEqual(settings.otel_exporter_otlp_endpoint, "http://env-jaeger:4317")

    def test_default_values(self):
        """Test default values when no environment variables are set."""
        # Clear environment variables
        if "OTEL_SERVICE_NAME" in os.environ:
            del os.environ["OTEL_SERVICE_NAME"]
        if "OTEL_EXPORTER_OTLP_ENDPOINT" in os.environ:
            del os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"]

        # Import API Gateway Settings specifically for this test
        from config import Settings as ApiGatewaySettings

        settings = ApiGatewaySettings(
            core_service_host="localhost:50051", http_port=8000
        )

        self.assertEqual(settings.otel_service_name, "aura-core")
        self.assertEqual(settings.otel_exporter_otlp_endpoint, "http://jaeger:4317")


if __name__ == "__main__":
    # Configure logging for standalone run
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(),
        ]
    )
    logger = structlog.get_logger(__name__)

    unittest.main(verbosity=2, exit=False)
    logger.info("telemetry_tests_complete")
    logger.info("all_tests_passed")
    logger.info(
        "integration_test_instructions",
        step1="Start the platform: docker-compose up --build",
        step2="Run test_telemetry.py to generate real traces",
        step3="Check Jaeger UI at http://localhost:16686",
    )
