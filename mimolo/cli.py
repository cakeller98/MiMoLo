"""Command-line interface for MiMoLo using Typer.

Commands:
- ops: Run the operations orchestrator (singleton)
- monitor: Backward-compatible alias for ops
- test: Emit synthetic test events
- register: Print plugin registration info (stub)
"""

from __future__ import annotations

import json
import os
import signal
import sys
import time
import tomllib
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from mimolo.common.paths import get_mimolo_data_dir, get_mimolo_runtime_dir
from mimolo.core.config import Config, load_config_or_default
from mimolo.core.errors import ConfigError
from mimolo.core.event import Event
from mimolo.core.ipc import (
    check_platform_support,
    create_ipc_channel,
    derive_slowpoke_dirs,
    derive_slowpoke_root,
    effective_ipc_mode,
    normalize_ipc_mode,
)
from mimolo.core.logging_setup import init_orchestrator_logging
from mimolo.core.ops_singleton import OperationsSingletonLock
from mimolo.core.runtime import Runtime

console = Console()


def _check_platform_or_exit(require_ipc: bool) -> None:
    requested_mode = normalize_ipc_mode(os.environ.get("MIMOLO_IPC_MODE"))
    resolved_mode = effective_ipc_mode(os.environ.get("MIMOLO_IPC_MODE"))
    supported, reason = check_platform_support()
    if not supported:
        if require_ipc:
            if requested_mode == "unix":
                console.print(f"[red]ERROR: {reason}[/red]")
                console.print("\n[yellow]MiMoLo IPC currently requires:[/yellow]")
                console.print("  - A Python build with AF_UNIX socket support")
                console.print("  - Windows 10 version 1803+ when using Windows AF_UNIX")
                console.print("  - macOS 10.13 High Sierra or later")
                console.print("  - Modern Linux (kernel 2.6+)")
                console.print(
                    "\n[dim]Switch MIMOLO_IPC_MODE to auto/slowpoke, disable IPC, or use a supported Python build.[/dim]"
                )
                sys.exit(1)
            console.print(f"[yellow]Platform check warning:[/yellow] {reason}")
            console.print(
                f"[dim]Continuing with {resolved_mode} IPC mode (requested={requested_mode}).[/dim]"
            )
            return
        console.print(f"[yellow]Platform check warning:[/yellow] {reason}")
        console.print("[dim]Continuing without IPC support.[/dim]")
        return
    console.print(f"[dim]Platform check: {reason}[/dim]")
    if require_ipc:
        console.print(
            f"[dim]IPC mode: requested={requested_mode} resolved={resolved_mode}[/dim]"
        )


def _apply_monitor_env_overrides(config: Config) -> None:
    """Apply optional monitor path overrides from environment."""
    log_dir = os.getenv("MIMOLO_MONITOR_LOG_DIR")
    if log_dir is not None and log_dir.strip():
        config.monitor.log_dir = log_dir.strip()

    journal_dir = os.getenv("MIMOLO_MONITOR_JOURNAL_DIR")
    if journal_dir is not None and journal_dir.strip():
        config.monitor.journal_dir = journal_dir.strip()

    cache_dir = os.getenv("MIMOLO_MONITOR_CACHE_DIR")
    if cache_dir is not None and cache_dir.strip():
        config.monitor.cache_dir = cache_dir.strip()


def _install_graceful_sigterm_handler(runtime: Runtime) -> None:
    """Handle SIGTERM as a graceful orchestrator stop request."""

    def _on_sigterm(signum: int, _frame: object | None) -> None:
        if signum == signal.SIGTERM:
            runtime._running = False

    signal.signal(signal.SIGTERM, _on_sigterm)


def _load_launcher_table(config_path: Path | None) -> dict[str, object]:
    """Read the optional [launcher] table from mml.toml-style config."""
    if config_path is None or not config_path.is_file():
        return {}

    with config_path.open("rb") as handle:
        payload = tomllib.load(handle)

    launcher = payload.get("launcher")
    return launcher if isinstance(launcher, dict) else {}


def _resolve_launcher_path(
    raw_value: object,
    *,
    config_path: Path | None,
) -> Path | None:
    """Resolve one launcher path override relative to the config file when needed."""
    if not isinstance(raw_value, str):
        return None

    text = raw_value.strip()
    if not text:
        return None

    candidate = Path(text).expanduser()
    if not candidate.is_absolute() and config_path is not None:
        candidate = config_path.parent / candidate
    return candidate.resolve(strict=False)


def _resolve_ops_ipc_settings(config_path: Path | None) -> tuple[str, str, str]:
    """Resolve IPC socket path, slowpoke root, and transport mode for ops control."""
    launcher = _load_launcher_table(config_path)

    ipc_path = os.getenv("MIMOLO_IPC_PATH", "").strip()
    if not ipc_path:
        launcher_ipc_path = _resolve_launcher_path(
            launcher.get("ipc_path"),
            config_path=config_path,
        )
        if launcher_ipc_path is not None:
            ipc_path = str(launcher_ipc_path)
        else:
            ipc_path = str((get_mimolo_runtime_dir() / "operations.sock").resolve(strict=False))

    slowpoke_root = os.getenv("MIMOLO_IPC_SLOWPOKE_ROOT", "").strip()
    if not slowpoke_root:
        slowpoke_root = derive_slowpoke_root(ipc_path)

    ipc_mode = effective_ipc_mode(os.getenv("MIMOLO_IPC_MODE"))
    return ipc_path, slowpoke_root, ipc_mode


def _send_ops_control_request(
    *,
    action: str,
    config_path: Path | None,
    timeout_s: float,
) -> dict[str, object]:
    """Send one control_orchestrator request over the active IPC transport."""
    ipc_path, slowpoke_root, ipc_mode = _resolve_ops_ipc_settings(config_path)
    request: dict[str, object] = {
        "cmd": "control_orchestrator",
        "action": action,
    }

    if ipc_mode == "slowpoke":
        from mimolo.core.ipc_slowpoke import create_slowpoke_channel

        _root_dir, control_to_ops_dir, ops_to_control_dir = derive_slowpoke_dirs(
            ipc_path,
            slowpoke_root,
        )
        channel = create_slowpoke_channel(
            read_dir=ops_to_control_dir,
            write_dir=control_to_ops_dir,
            create=False,
        )
    else:
        channel = create_ipc_channel(ipc_path, server=False)

    try:
        channel.write_line(request)
        deadline = time.monotonic() + max(timeout_s, 0.1)
        while time.monotonic() < deadline:
            raw_line = channel.read_line()
            if raw_line is None:
                continue
            try:
                payload = json.loads(raw_line)
            except json.JSONDecodeError as exc:
                raise RuntimeError(
                    f"Invalid IPC response from orchestrator: {raw_line!r}"
                ) from exc
            if not isinstance(payload, dict):
                raise RuntimeError(f"Unexpected IPC response type: {type(payload).__name__}")
            return payload
    finally:
        channel.close()

    raise RuntimeError(
        f"Timed out waiting {timeout_s:.1f}s for orchestrator response."
    )

app = typer.Typer(
    name="mimolo",
    help="MiMoLo - Modular Monitor & Logger Framework",
    add_completion=False,
)

# Typer option metadata constants to avoid function calls in annotations/defaults
CONFIG_OPTION = typer.Option(
    "--config",
    "-c",
    help="Path to configuration file",
)
ONCE_OPTION = typer.Option(
    "--once",
    help="Exit after first segment closes",
)
DRY_RUN_OPTION = typer.Option(
    "--dry-run",
    help="Validate config and exit",
)
LOG_FORMAT_OPTION = typer.Option(
    "--log-format",
    help="Override log format (jsonl|yaml|md)",
)
COOLDOWN_OPTION = typer.Option(
    "--cooldown",
    help="Override cooldown seconds",
)


def _run_ops_command(
    config_path: Annotated[Path | None, CONFIG_OPTION] = Path("mimolo.toml"),
    once: Annotated[bool, ONCE_OPTION] = False,
    dry_run: Annotated[bool, DRY_RUN_OPTION] = False,
    log_format: Annotated[str | None, LOG_FORMAT_OPTION] = None,
    cooldown: Annotated[float | None, COOLDOWN_OPTION] = None,
) -> None:
    """Run the MiMoLo operations orchestrator.

    Loads configuration, registers plugins, and runs the main event loop.
    """
    try:
        require_ipc = bool(os.environ.get("MIMOLO_IPC_PATH"))
        _check_platform_or_exit(require_ipc=require_ipc)

        # Load config
        config = load_config_or_default(config_path)
        _apply_monitor_env_overrides(config)

        # Initialize orchestrator logging (for internal diagnostics)
        init_orchestrator_logging(verbosity=config.monitor.console_verbosity)

        # Apply CLI overrides
        if log_format:
            config.monitor.log_format = log_format
        if cooldown is not None:
            config.monitor.cooldown_seconds = cooldown

        console.print(f"[cyan]Configuration loaded from: {config_path or 'defaults'}[/cyan]")

        if dry_run:
            console.print("[yellow]Dry-run mode: validating only[/yellow]")
            console.print(json.dumps(config.model_dump(), indent=2))
            return

        # Check for Agent plugins in config
        agent_count = sum(1 for pc in config.plugins.values() if pc.enabled and pc.plugin_type == "agent")

        if agent_count == 0:
            console.print("[red]No Agents configured. Nothing to monitor.[/red]")
            sys.exit(1)

        lock = OperationsSingletonLock(get_mimolo_data_dir())
        lock_status = lock.acquire()
        if not lock_status.acquired:
            pid_text = (
                f" (pid={lock_status.existing_pid})"
                if lock_status.existing_pid is not None
                else ""
            )
            console.print(
                "[red]Operations singleton already running"
                f"{pid_text}. Attach Control to existing instance.[/red]"
            )
            sys.exit(3)

        # Create and run runtime
        runtime = Runtime(config, console, config_path=config_path)
        _install_graceful_sigterm_handler(runtime)
        try:
            runtime.run(max_iterations=1 if once else None)
        finally:
            lock.release()

    except ConfigError as e:
        console.print(f"[red]Configuration error: {e}[/red]")
        sys.exit(2)
    except (OSError, RuntimeError, TypeError, ValueError) as e:
        console.print(f"[red]Unexpected error: {e}[/red]")
        import traceback

        traceback.print_exc()
        sys.exit(1)


@app.command(name="ops")
def ops(
    config_path: Annotated[Path | None, CONFIG_OPTION] = Path("mimolo.toml"),
    once: Annotated[bool, ONCE_OPTION] = False,
    dry_run: Annotated[bool, DRY_RUN_OPTION] = False,
    log_format: Annotated[str | None, LOG_FORMAT_OPTION] = None,
    cooldown: Annotated[float | None, COOLDOWN_OPTION] = None,
) -> None:
    """Run the MiMoLo operations orchestrator."""
    _run_ops_command(config_path, once, dry_run, log_format, cooldown)


@app.command(name="monitor", hidden=True)
def monitor_alias(
    config_path: Annotated[Path | None, CONFIG_OPTION] = Path("mimolo.toml"),
    once: Annotated[bool, ONCE_OPTION] = False,
    dry_run: Annotated[bool, DRY_RUN_OPTION] = False,
    log_format: Annotated[str | None, LOG_FORMAT_OPTION] = None,
    cooldown: Annotated[float | None, COOLDOWN_OPTION] = None,
) -> None:
    """Backward-compatible alias for `mimolo ops`."""
    _run_ops_command(config_path, once, dry_run, log_format, cooldown)


@app.command(name="ops-control")
def ops_control(
    action: Annotated[
        str,
        typer.Argument(help="One of: status, stop"),
    ] = "status",
    config_path: Annotated[Path | None, CONFIG_OPTION] = Path("mimolo.toml"),
    timeout: Annotated[
        float,
        typer.Option("--timeout", min=0.1, help="IPC response timeout in seconds."),
    ] = 5.0,
) -> None:
    """Query or stop a running orchestrator over IPC without launching Control."""
    normalized_action = action.strip().lower()
    if normalized_action not in {"status", "stop"}:
        console.print("[red]Invalid ops-control action. Use 'status' or 'stop'.[/red]")
        raise typer.Exit(2)

    try:
        response = _send_ops_control_request(
            action=normalized_action,
            config_path=config_path,
            timeout_s=timeout,
        )
    except (OSError, RuntimeError) as exc:
        console.print(f"[red]Ops control failed:[/red] {exc}")
        raise typer.Exit(1) from exc

    ok = bool(response.get("ok"))
    data_raw = response.get("data")
    data = data_raw if isinstance(data_raw, dict) else {}
    orchestrator_raw = data.get("orchestrator")
    orchestrator = orchestrator_raw if isinstance(orchestrator_raw, dict) else {}

    console.print(f"[cyan]action:[/cyan] {normalized_action}")
    console.print(f"[cyan]ok:[/cyan] {str(ok).lower()}")
    status = data.get("status")
    if isinstance(status, str) and status:
        console.print(f"[cyan]status:[/cyan] {status}")
    accepted = data.get("accepted")
    if isinstance(accepted, bool):
        console.print(f"[cyan]accepted:[/cyan] {str(accepted).lower()}")
    if orchestrator:
        running = orchestrator.get("running")
        shutting_down = orchestrator.get("shutting_down")
        ipc_enabled = orchestrator.get("ipc_enabled")
        if isinstance(running, bool):
            console.print(f"[cyan]running:[/cyan] {str(running).lower()}")
        if isinstance(shutting_down, bool):
            console.print(f"[cyan]shutting_down:[/cyan] {str(shutting_down).lower()}")
        if isinstance(ipc_enabled, bool):
            console.print(f"[cyan]ipc_enabled:[/cyan] {str(ipc_enabled).lower()}")

    if not ok:
        error = response.get("error")
        if isinstance(error, str) and error:
            console.print(f"[red]error:[/red] {error}")
        raise typer.Exit(1)


@app.command()
def test(
    rate: float = 1.0,
    count: int = 10,
) -> None:
    """Emit synthetic test events.

    Useful for testing event schema and validating sink configuration.
    """
    console.print(f"[cyan]Emitting {count} test events at {rate} EPS[/cyan]")

    interval = 1.0 / rate if rate > 0 else 0

    for i in range(count):
        now = datetime.now(UTC)
        event = Event(
            timestamp=now,
            label="test",
            event=f"synthetic_{i}",
            data={"iteration": i, "message": "Hello from MiMoLo test"},
        ).with_id()

        print(json.dumps(event.to_dict(), separators=(",", ":")))

        if i < count - 1:
            time.sleep(interval)

    console.print("[green]Test complete[/green]")


def main() -> None:
    """Entry point for the CLI."""
    app()


if __name__ == "__main__":
    main()
