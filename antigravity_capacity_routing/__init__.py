"""Scarce-token-aware routing and pilot evaluation for C3P."""

from .policy import evaluate_pilot, route_task, validate_evidence_packet
from .telemetry import (
    TelemetryParseError,
    extract_telemetry,
    parse_cli_json,
    parse_stream_json,
    record_telemetry_event,
    summarize_telemetry,
)

__all__ = [
    "evaluate_pilot",
    "route_task",
    "validate_evidence_packet",
    "TelemetryParseError",
    "extract_telemetry",
    "parse_cli_json",
    "parse_stream_json",
    "record_telemetry_event",
    "summarize_telemetry",
]
