from datetime import UTC, datetime

from mimolo.core.protocol import (
    AgentMessage,
    HandshakeMessage,
    HeartbeatMessage,
    SummaryMessage,
    parse_agent_message,
)


def test_parse_handshake() -> None:
    line = (
        '{"type":"handshake","timestamp":"'
        + datetime.now(UTC).isoformat()
        + '","agent_id":"a1","agent_label":"agent","agent_version":"1.0","min_app_version":"0.3","capabilities":["x"]}'
    )
    msg = parse_agent_message(line)
    assert isinstance(msg, HandshakeMessage)
    assert msg.capabilities == ["x"]


def test_parse_summary() -> None:
    line = (
        '{"type":"summary","timestamp":"'
        + datetime.now(UTC).isoformat()
        + '","agent_id":"a1","agent_label":"agent","agent_version":"1.0","data":{"value":42}}'
    )
    msg = parse_agent_message(line)
    assert isinstance(msg, SummaryMessage)
    assert msg.data["value"] == 42


def test_parse_heartbeat() -> None:
    line = (
        '{"type":"heartbeat","timestamp":"'
        + datetime.now(UTC).isoformat()
        + '","agent_id":"a1","agent_label":"agent","agent_version":"1.0","metrics":{"cpu":0.1}}'
    )
    msg = parse_agent_message(line)
    assert isinstance(msg, HeartbeatMessage)
    assert msg.metrics["cpu"] == 0.1


def test_parse_generic_fallback() -> None:
    line = (
        '{"type":"status","timestamp":"'
        + datetime.now(UTC).isoformat()
        + '","agent_id":"a1","agent_label":"agent","agent_version":"1.0","message":"ok"}'
    )
    msg = parse_agent_message(line)
    assert isinstance(msg, AgentMessage)
    assert msg.message == "ok"
