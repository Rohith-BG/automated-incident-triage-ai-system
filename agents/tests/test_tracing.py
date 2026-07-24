"""Unit tests for agent TraceRecorder and secret sanitization."""

from agents.tracing import TraceRecorder, sanitize_text


def test_sanitize_text_redacts_api_keys() -> None:
    """sanitize_text redacts api_key, token, password, and secret strings."""
    raw = "Failed request with api_key: 'secret-12345' and Bearer = 'token-999'"
    clean = sanitize_text(raw)
    assert "secret-12345" not in clean
    assert "token-999" not in clean
    assert "REDACTED" in clean


def test_trace_recorder_recording_and_summary() -> None:
    """TraceRecorder records tool calls and computes summary stats."""
    recorder = TraceRecorder()
    recorder.record(
        incident_id="inc-100",
        agent="observability",
        tool="search_logs",
        input_data={"service": "payment-service"},
        output_data=[{"log": "error message"}],
        latency_ms=45.2,
        token_usage={"total_tokens": 150},
        success=True,
    )
    recorder.record(
        incident_id="inc-100",
        agent="deploy",
        tool="analyze_deployment",
        input_data={"api_key": "secret-val"},
        output_data={"proposal": "add redis"},
        latency_ms=120.0,
        token_usage={"total_tokens": 300},
        success=False,
        error="Unauthorized with api_key: secret-val",
    )

    traces = recorder.get_traces("inc-100")
    assert len(traces) == 2
    assert "secret-val" not in traces[1].input_summary
    assert "secret-val" not in traces[1].error

    summary = recorder.get_summary("inc-100")
    assert summary["total_calls"] == 2
    assert summary["total_tokens"] == 450
    assert summary["failed_calls"] == 1
    assert summary["total_latency_ms"] == 165.2
