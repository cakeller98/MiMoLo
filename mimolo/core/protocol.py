"""Field-Agent protocol message types and validation."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class MessageType(str, Enum):
    """Agent → Orchestrator message types."""

    HANDSHAKE = "handshake"
    SUMMARY = "summary"
    HEARTBEAT = "heartbeat"
    STATUS = "status"
    ERROR = "error"


class CommandType(str, Enum):
    """Orchestrator → Agent command types."""

    ACK = "ack"
    REJECT = "reject"
    FLUSH = "flush"
    STATUS = "status"
    SHUTDOWN = "shutdown"


class AgentMessage(BaseModel):
    """Base message envelope for all agent → orchestrator messages."""

    type: MessageType
    timestamp: datetime
    agent_id: str
    agent_label: str
    protocol_version: str = "0.3"
    agent_version: str
    data: dict[str, Any] = Field(default_factory=dict)

    # Optional fields
    metrics: dict[str, Any] = Field(default_factory=dict)
    health: Literal["ok", "degraded", "overload", "failed"] | None = None
    message: str | None = None


class HandshakeMessage(AgentMessage):
    """Initial agent registration message."""

    type: MessageType = MessageType.HANDSHAKE
    min_app_version: str
    capabilities: list[str]


class SummaryMessage(AgentMessage):
    """Data flush from agent."""

    type: MessageType = MessageType.SUMMARY


class HeartbeatMessage(AgentMessage):
    """Health ping from agent."""

    type: MessageType = MessageType.HEARTBEAT
    metrics: dict[str, Any] = Field(default_factory=dict, description="Required for heartbeats")


class OrchestratorCommand(BaseModel):
    """Base command envelope for orchestrator → agent commands."""

    cmd: CommandType
    args: dict[str, Any] = Field(default_factory=dict)
    id: str | None = None


def parse_agent_message(line: str) -> AgentMessage:
    """Parse JSON line into appropriate message type.

    Args:
        line: JSON string from agent stdout

    Returns:
        Parsed message object

    Raises:
        ValueError: If JSON invalid or type unknown
    """
    import json

    data = json.loads(line)
    msg_type = data.get("type")

    if msg_type == MessageType.HANDSHAKE:
        return HandshakeMessage(**data)
    elif msg_type == MessageType.SUMMARY:
        return SummaryMessage(**data)
    elif msg_type == MessageType.HEARTBEAT:
        return HeartbeatMessage(**data)
    else:
        return AgentMessage(**data)
