#!/usr/bin/env python3
"""Manual test script for IPC-based logging system.

This script tests the logging functionality without requiring pytest or
full package installation.
"""

import json
import sys
from datetime import UTC, datetime
from io import StringIO

# Add project to path
sys.path.insert(0, ".")


def test_protocol_extension():
    """Test that LOG message type is defined in protocol."""
    from mimolo.core.protocol import LogLevel, LogMessage, MessageType

    print("✓ Protocol imports successful")

    # Test MessageType
    assert MessageType.LOG == "log", "LOG message type should equal 'log'"
    print(f"✓ MessageType.LOG = {MessageType.LOG}")

    # Test LogLevel
    assert LogLevel.DEBUG == "debug"
    assert LogLevel.INFO == "info"
    assert LogLevel.WARNING == "warning"
    assert LogLevel.ERROR == "error"
    print(f"✓ LogLevel enum defined: {[level.value for level in LogLevel]}")

    # Test LogMessage model
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
    assert msg.message == "Test message"
    print("✓ LogMessage model validation works")


def test_agent_logger():
    """Test AgentLogger emits valid JSON log packets."""
    from mimolo.core.agent_logging import AgentLogger

    print("\n✓ AgentLogger import successful")

    # Capture stdout
    old_stdout = sys.stdout
    sys.stdout = StringIO()

    try:
        logger = AgentLogger(agent_id="test-001", agent_label="test_agent")

        # Test each log level
        logger.debug("[cyan]Debug message[/cyan]")
        logger.info("[green]Info message[/green]")
        logger.warning("[yellow]Warning message[/yellow]")
        logger.error("[red]Error message[/red]")

        # Get captured output
        output = sys.stdout.getvalue()
        lines = output.strip().split("\n")

        assert len(lines) == 4, f"Expected 4 log lines, got {len(lines)}"
        print("✓ AgentLogger emitted 4 log messages")

        # Parse each line and validate
        for i, line in enumerate(lines):
            packet = json.loads(line)
            assert packet["type"] == "log", f"Line {i}: type should be 'log'"
            assert packet["agent_id"] == "test-001"
            assert packet["agent_label"] == "test_agent"
            assert "timestamp" in packet
            assert "level" in packet
            assert "message" in packet
            assert packet["markup"] is True

        print("✓ All log packets have valid structure")

        # Validate log levels
        levels = [json.loads(line)["level"] for line in lines]
        assert levels == ["debug", "info", "warning", "error"]
        print(f"✓ Log levels correct: {levels}")

        # Validate Rich markup preserved
        messages = [json.loads(line)["message"] for line in lines]
        assert "[cyan]" in messages[0], "Debug message should preserve Rich markup"
        assert "[green]" in messages[1], "Info message should preserve Rich markup"
        print("✓ Rich markup preserved in messages")

    finally:
        sys.stdout = old_stdout


def test_protocol_parsing():
    """Test protocol parser handles LOG messages."""
    from mimolo.core.protocol import LogMessage, MessageType, parse_agent_message

    print("\n✓ Testing protocol parsing")

    log_json = {
        "type": "log",
        "timestamp": datetime.now(UTC).isoformat(),
        "agent_id": "test-001",
        "agent_label": "test_agent",
        "protocol_version": "0.3",
        "agent_version": "1.0.0",
        "level": "info",
        "message": "Test message with [bold]markup[/bold]",
        "markup": True,
        "data": {},
        "extra": {"key": "value"},
    }

    json_str = json.dumps(log_json)
    msg = parse_agent_message(json_str)

    assert isinstance(msg, LogMessage), "Should parse as LogMessage"
    assert msg.type == MessageType.LOG
    assert msg.level == "info"
    assert msg.message == "Test message with [bold]markup[/bold]"
    assert msg.extra["key"] == "value"
    print("✓ Protocol parser handles LOG messages correctly")


def test_agent_logger_with_context():
    """Test AgentLogger with extra context data."""
    from mimolo.core.agent_logging import AgentLogger

    print("\n✓ Testing logger with context data")

    old_stdout = sys.stdout
    sys.stdout = StringIO()

    try:
        logger = AgentLogger(agent_id="test-001", agent_label="test_agent")
        logger.info("Batch processed", count=100, duration=1.23, status="success")

        output = sys.stdout.getvalue()
        packet = json.loads(output.strip())

        assert packet["extra"]["count"] == 100
        assert packet["extra"]["duration"] == 1.23
        assert packet["extra"]["status"] == "success"
        print("✓ Extra context data included in log packets")

    finally:
        sys.stdout = old_stdout


def main():
    """Run all tests."""
    print("=" * 60)
    print("MiMoLo Logging System Integration Test")
    print("=" * 60)

    try:
        test_protocol_extension()
        test_agent_logger()
        test_protocol_parsing()
        test_agent_logger_with_context()

        print("\n" + "=" * 60)
        print("✅ All tests passed!")
        print("=" * 60)
        return 0

    except Exception as e:
        print("\n" + "=" * 60)
        print(f"❌ Test failed: {e}")
        print("=" * 60)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
