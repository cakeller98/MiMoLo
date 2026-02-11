"""Runtime performance telemetry helpers."""

from __future__ import annotations

import os
import platform
import subprocess
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from types import ModuleType
from typing import Any, cast

resource: ModuleType | None
try:
    import resource as _resource_module
except ImportError:
    resource = None
else:
    resource = _resource_module


@dataclass
class RollingMsStats:
    """Rolling millisecond stats for one metric."""

    window: deque[float] = field(default_factory=lambda: deque(maxlen=300))
    count: int = 0
    total_ms: float = 0.0
    max_ms: float = 0.0

    def add(self, value_ms: float) -> None:
        """Record one sample."""
        value = max(0.0, float(value_ms))
        self.window.append(value)
        self.count += 1
        self.total_ms += value
        if value > self.max_ms:
            self.max_ms = value

    @property
    def avg_ms(self) -> float:
        """Lifetime mean."""
        if self.count <= 0:
            return 0.0
        return self.total_ms / self.count

    @property
    def p95_ms(self) -> float:
        """Window p95."""
        if not self.window:
            return 0.0
        ordered = sorted(self.window)
        index = max(0, int(round(0.95 * (len(ordered) - 1))))
        return ordered[index]


@dataclass
class AgentPerfStats:
    """Per-agent runtime performance aggregates."""

    tick_count: int = 0
    drain_total_ms: float = 0.0
    drain_max_ms: float = 0.0
    messages_total: int = 0
    flush_due_total: int = 0
    flush_sent_total: int = 0
    handler_errors_total: int = 0
    unknown_messages_total: int = 0
    by_type: dict[str, int] = field(
        default_factory=lambda: {
            "heartbeat": 0,
            "summary": 0,
            "log": 0,
            "error": 0,
        }
    )

    def update(
        self,
        drain_ms: float,
        message_counts: dict[str, int],
        flush_due: bool,
        flush_sent: bool,
    ) -> None:
        """Apply one per-tick agent sample."""
        self.tick_count += 1
        self.drain_total_ms += max(0.0, float(drain_ms))
        self.drain_max_ms = max(self.drain_max_ms, max(0.0, float(drain_ms)))
        self.messages_total += int(message_counts.get("total", 0))
        if flush_due:
            self.flush_due_total += 1
        if flush_sent:
            self.flush_sent_total += 1
        self.handler_errors_total += int(message_counts.get("handler_errors", 0))
        self.unknown_messages_total += int(message_counts.get("unknown", 0))
        for key in ("heartbeat", "summary", "log", "error"):
            self.by_type[key] += int(message_counts.get(key, 0))

    @property
    def drain_avg_ms(self) -> float:
        """Mean drain cost per sampled tick."""
        if self.tick_count <= 0:
            return 0.0
        return self.drain_total_ms / self.tick_count


@dataclass
class RuntimePerfState:
    """Runtime-level performance state."""

    started_at_iso: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    wall_start_s: float = field(default_factory=time.perf_counter)
    cpu_start_s: float = field(default_factory=time.process_time)
    cpu_last_sample_s: float = field(default_factory=time.process_time)
    wall_last_sample_s: float = field(default_factory=time.perf_counter)
    tick_total: RollingMsStats = field(default_factory=RollingMsStats)
    stage_stats: dict[str, RollingMsStats] = field(
        default_factory=lambda: {
            "control_actions_ms": RollingMsStats(),
            "reap_ms": RollingMsStats(),
            "cooldown_ms": RollingMsStats(),
            "agents_ms": RollingMsStats(),
        }
    )
    messages_total: int = 0
    messages_by_type: dict[str, int] = field(
        default_factory=lambda: {
            "heartbeat": 0,
            "summary": 0,
            "log": 0,
            "error": 0,
            "unknown": 0,
        }
    )
    slow_tick_threshold_ms: float = 10.0
    slow_ticks_total: int = 0
    agents: dict[str, AgentPerfStats] = field(default_factory=dict)


def new_runtime_perf_state() -> RuntimePerfState:
    """Create runtime performance state."""
    return RuntimePerfState()


def record_tick_sample(
    state: RuntimePerfState,
    total_ms: float,
    stage_ms: dict[str, float],
    agent_samples: list[dict[str, Any]],
) -> None:
    """Record one orchestrator tick sample."""
    total = max(0.0, float(total_ms))
    state.tick_total.add(total)
    if total >= state.slow_tick_threshold_ms:
        state.slow_ticks_total += 1

    for stage_name, value in stage_ms.items():
        metric = state.stage_stats.get(stage_name)
        if metric is None:
            continue
        metric.add(value)

    for sample in agent_samples:
        label_raw = sample.get("label")
        if not isinstance(label_raw, str) or not label_raw:
            continue

        message_counts_raw = sample.get("message_counts")
        if not isinstance(message_counts_raw, dict):
            message_counts = {}
        else:
            message_counts = {
                key: int(value) if isinstance(value, int) else 0
                for key, value in message_counts_raw.items()
            }

        agent_stats = state.agents.get(label_raw)
        if agent_stats is None:
            agent_stats = AgentPerfStats()
            state.agents[label_raw] = agent_stats

        agent_stats.update(
            drain_ms=float(sample.get("drain_ms", 0.0)),
            message_counts=message_counts,
            flush_due=bool(sample.get("flush_due", False)),
            flush_sent=bool(sample.get("flush_sent", False)),
        )

        state.messages_total += int(message_counts.get("total", 0))
        for key in ("heartbeat", "summary", "log", "error", "unknown"):
            state.messages_by_type[key] += int(message_counts.get(key, 0))


def _memory_snapshot() -> dict[str, Any]:
    """Collect process memory snapshot."""
    if resource is None:
        return {"rss_bytes": None}
    try:
        usage = resource.getrusage(resource.RUSAGE_SELF)
    except OSError:
        # OSError: resource accounting can fail on constrained platforms.
        return {"rss_bytes": None}

    raw = int(usage.ru_maxrss)
    if platform.system() == "Darwin":
        rss_bytes = raw
    else:
        rss_bytes = raw * 1024
    return {"rss_bytes": rss_bytes}


def snapshot_runtime_perf(state: RuntimePerfState) -> dict[str, Any]:
    """Build JSON-safe runtime performance snapshot."""
    now_wall = time.perf_counter()
    now_cpu = time.process_time()
    elapsed_wall = max(0.000001, now_wall - state.wall_start_s)
    elapsed_cpu = max(0.0, now_cpu - state.cpu_start_s)
    lifetime_cpu_percent = (elapsed_cpu / elapsed_wall) * 100.0

    recent_wall = max(0.000001, now_wall - state.wall_last_sample_s)
    recent_cpu = max(0.0, now_cpu - state.cpu_last_sample_s)
    recent_cpu_percent = (recent_cpu / recent_wall) * 100.0
    state.wall_last_sample_s = now_wall
    state.cpu_last_sample_s = now_cpu

    stage_avg_ms = {
        key: metric.avg_ms
        for key, metric in state.stage_stats.items()
    }

    top_agents = sorted(
        (
            {
                "label": label,
                "drain_avg_ms": agent_stats.drain_avg_ms,
                "drain_max_ms": agent_stats.drain_max_ms,
                "messages_total": agent_stats.messages_total,
                "flush_due_total": agent_stats.flush_due_total,
                "flush_sent_total": agent_stats.flush_sent_total,
                "handler_errors_total": agent_stats.handler_errors_total,
                "unknown_messages_total": agent_stats.unknown_messages_total,
                "by_type": dict(agent_stats.by_type),
            }
            for label, agent_stats in state.agents.items()
        ),
        key=lambda item: cast(float, item["drain_avg_ms"]),
        reverse=True,
    )[:5]

    avg_messages_per_tick = (
        float(state.messages_total) / state.tick_total.count
        if state.tick_total.count > 0
        else 0.0
    )

    return {
        "started_at": state.started_at_iso,
        "uptime_s": elapsed_wall,
        "process": {
            "pid": os.getpid(),
            "cpu_percent_lifetime": lifetime_cpu_percent,
            "cpu_percent_recent": recent_cpu_percent,
            "thread_count": threading.active_count(),
            **_memory_snapshot(),
        },
        "tick": {
            "count": state.tick_total.count,
            "avg_ms": state.tick_total.avg_ms,
            "p95_ms": state.tick_total.p95_ms,
            "max_ms": state.tick_total.max_ms,
            "slow_tick_threshold_ms": state.slow_tick_threshold_ms,
            "slow_ticks_total": state.slow_ticks_total,
            "stage_avg_ms": stage_avg_ms,
        },
        "messages": {
            "total": state.messages_total,
            "avg_per_tick": avg_messages_per_tick,
            "by_type": dict(state.messages_by_type),
        },
        "agents": {
            "count": len(state.agents),
            "top_by_drain_avg_ms": top_agents,
        },
    }


def _sample_process_resource(pid: int) -> dict[str, Any]:
    """Read process CPU percent and RSS from ps."""
    if pid <= 0:
        return {
            "pid": pid,
            "cpu_percent": None,
            "rss_bytes": None,
        }
    try:
        completed = subprocess.run(
            ["ps", "-p", str(pid), "-o", "%cpu=,rss="],
            capture_output=True,
            check=False,
            text=True,
            timeout=0.5,
        )
    except (OSError, subprocess.SubprocessError):
        # Subprocess execution can fail due to platform/tooling constraints.
        return {
            "pid": pid,
            "cpu_percent": None,
            "rss_bytes": None,
        }

    if completed.returncode != 0:
        return {
            "pid": pid,
            "cpu_percent": None,
            "rss_bytes": None,
        }

    line = completed.stdout.strip()
    if not line:
        return {
            "pid": pid,
            "cpu_percent": None,
            "rss_bytes": None,
        }

    parts = line.split()
    if len(parts) < 2:
        return {
            "pid": pid,
            "cpu_percent": None,
            "rss_bytes": None,
        }

    try:
        cpu_percent = float(parts[0])
        rss_kib = float(parts[1])
    except ValueError:
        # ps output parse failure should not break telemetry flow.
        return {
            "pid": pid,
            "cpu_percent": None,
            "rss_bytes": None,
        }

    return {
        "pid": pid,
        "cpu_percent": cpu_percent,
        "rss_bytes": max(0, int(rss_kib * 1024)),
    }


def snapshot_runtime_perf_with_agents(
    state: RuntimePerfState,
    agent_pids: dict[str, int],
) -> dict[str, Any]:
    """Build snapshot and enrich with per-agent process CPU/RSS."""
    payload = snapshot_runtime_perf(state)
    agent_rows: list[dict[str, Any]] = []
    for label, pid in agent_pids.items():
        row = _sample_process_resource(pid)
        row["label"] = label
        agent_rows.append(row)

    top_by_cpu = sorted(
        agent_rows,
        key=lambda item: cast(float, item.get("cpu_percent", 0.0) or 0.0),
        reverse=True,
    )[:5]

    agents_payload = payload.get("agents")
    if not isinstance(agents_payload, dict):
        agents_payload = {}
        payload["agents"] = agents_payload
    agents_payload["process_samples"] = agent_rows
    agents_payload["top_by_cpu_percent"] = top_by_cpu
    return payload
