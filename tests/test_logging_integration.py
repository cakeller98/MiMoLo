"""Integration tests for IPC-based logging system.

Tests:
1. Protocol extension (LOG message type)
2. AgentLogger packet emission
3. Orchestrator log message handling
4. Verbosity filtering
5. Rich markup preservation
"""

import json
from datetime import UTC, datetime

import pytest

from mimolo.core.agent_logging import AgentLogger
from mimolo.core.protocol import LogLevel, LogMessage, MessageType, parse_agent_message


def test_log_message_type_exists() -> None:
    """Test that LOG message type is defined in protocol."""
    assert MessageType.LOG.value == "log"
    assert "log" in [mt.value for mt in MessageType]


def test_log_level_enum() -> None:
    """Test LogLevel enum is properly defined."""
    assert LogLevel.DEBUG.value == "debug"
    assert LogLevel.INFO.value == "info"
    assert LogLevel.WARNING.value == "warning"
    assert LogLevel.ERROR.value == "error"


def test_log_message_model() -> None:
    """Test LogMessage model validation."""
    msg = LogMessage(
        type=MessageType.LOG,
        timestamp=datetime.now(UTC),
        agent_id="test-001",
        agent_label="test_agent",
        agent_version="1.0.0",
        level=LogLevel.INFO,
        message="Test message",
        markup=True,
        data={},
        extra={"context": "value"},
    )

    assert msg.type == MessageType.LOG
    assert msg.level == LogLevel.INFO
    assert msg.message == "Test message"
    assert msg.markup is True
    assert msg.extra["context"] == "value"


def test_agent_logger_basic_output(capsys: pytest.CaptureFixture[str]) -> None:
    """Test AgentLogger emits valid JSON log packets."""
    logger = AgentLogger(agent_id="test-001", agent_label="test_agent")

    # Emit a log message
    logger.info("Test info message")

    # Capture stdout
    captured = capsys.readouterr()
    lines = captured.out.strip().split("\n")

    # Should have exactly one line
    assert len(lines) == 1

    # Parse JSON
    packet = json.loads(lines[0])

    # Validate structure
    assert packet["type"] == "log"
    assert packet["agent_id"] == "test-001"
    assert packet["agent_label"] == "test_agent"
    assert packet["level"] == "info"
    assert packet["message"] == "Test info message"
    assert packet["markup"] is True
    assert "timestamp" in packet


def test_agent_logger_with_rich_markup(capsys: pytest.CaptureFixture[str]) -> None:
    """Test AgentLogger preserves Rich markup in messages."""
    logger = AgentLogger(agent_id="test-001", agent_label="test_agent")

    # Emit message with Rich markup
    logger.warning("[yellow]⚠[/yellow] Warning with [bold]emphasis[/bold]")

    captured = capsys.readouterr()
    packet = json.loads(captured.out.strip())

    # Markup should be preserved in message
    assert packet["message"] == "[yellow]⚠[/yellow] Warning with [bold]emphasis[/bold]"
    assert packet["markup"] is True


def test_agent_logger_all_levels(capsys: pytest.CaptureFixture[str]) -> None:
    """Test AgentLogger emits all log levels correctly."""
    logger = AgentLogger(agent_id="test-001", agent_label="test_agent")

    logger.debug("Debug message")
    logger.info("Info message")
    logger.warning("Warning message")
    logger.error("Error message")

    captured = capsys.readouterr()
    lines = captured.out.strip().split("\n")

    assert len(lines) == 4

    levels = [json.loads(line)["level"] for line in lines]
    assert levels == ["debug", "info", "warning", "error"]


def test_agent_logger_with_extra_context(capsys: pytest.CaptureFixture[str]) -> None:
    """Test AgentLogger includes extra context data."""
    logger = AgentLogger(agent_id="test-001", agent_label="test_agent")

    logger.info("Process batch", count=100, duration=1.23, status="success")

    captured = capsys.readouterr()
    packet = json.loads(captured.out.strip())

    # Extra context should be in 'extra' field
    assert packet["extra"]["count"] == 100
    assert packet["extra"]["duration"] == 1.23
    assert packet["extra"]["status"] == "success"


def test_parse_agent_log_message() -> None:
    """Test protocol parser handles LOG messages."""
    log_json = {
        "type": "log",
        "timestamp": datetime.now(UTC).isoformat(),
        "agent_id": "test-001",
        "agent_label": "test_agent",
        "protocol_version": "0.3",
        "agent_version": "1.0.0",
        "level": "info",
        "message": "Test message",
        "markup": True,
        "data": {},
        "extra": {},
    }

    json_str = json.dumps(log_json)
    msg = parse_agent_message(json_str)

    # Should parse as LogMessage
    assert isinstance(msg, LogMessage)
    assert msg.type == MessageType.LOG
    assert msg.level == LogLevel.INFO
    assert msg.message == "Test message"


def test_agent_logger_no_markup_mode(capsys: pytest.CaptureFixture[str]) -> None:
    """Test AgentLogger with markup disabled."""
    logger = AgentLogger(agent_id="test-001", agent_label="test_agent")

    # Send message with markup=False
    logger.info("Plain text message [no markup]", markup=False)

    captured = capsys.readouterr()
    packet = json.loads(captured.out.strip())

    assert packet["message"] == "Plain text message [no markup]"
    assert packet["markup"] is False


def test_agent_logger_error_handling(capsys: pytest.CaptureFixture[str]) -> None:
    """Test AgentLogger handles errors gracefully."""
    logger = AgentLogger(agent_id="test-001", agent_label="test_agent")

    # This should not crash even if there are special characters
    logger.error("Error with unicode: 🔥 and quotes: \"test\"")

    captured = capsys.readouterr()
    packet = json.loads(captured.out.strip())

    assert "🔥" in packet["message"]
    assert "test" in packet["message"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
