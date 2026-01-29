from pydantic import AliasChoices, BaseModel, Field, HttpUrl


class ServerSettings(BaseModel):
    host: str = "0.0.0.0"
    port: int = Field(
        50051, validation_alias=AliasChoices("AURA_SERVER__PORT", "GRPC_PORT")
    )
    log_level: str = "info"
    grpc_max_workers: int = Field(
        10,
        validation_alias=AliasChoices(
            "AURA_SERVER__GRPC_MAX_WORKERS", "GRPC_MAX_WORKERS"
        ),
    )

    # Telemetry
    otel_service_name: str = Field(
        "aura-core",
        validation_alias=AliasChoices(
            "AURA_SERVER__OTEL_SERVICE_NAME", "OTEL_SERVICE_NAME"
        ),
    )
    otel_exporter_otlp_endpoint: HttpUrl = Field(
        "http://jaeger:4317",
        validation_alias=AliasChoices(
            "AURA_SERVER__OTEL_EXPORTER_OTLP_ENDPOINT", "OTEL_EXPORTER_OTLP_ENDPOINT"
        ),
    )

    # Monitoring
    prometheus_url: HttpUrl = Field(
        "http://prometheus-kube-prometheus-prometheus.monitoring:9090",
        validation_alias=AliasChoices(
            "AURA_SERVER__PROMETHEUS_URL", "PROMETHEUS_URL"
        ),
    )
