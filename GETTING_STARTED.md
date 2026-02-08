# Getting Started with MiMoLo

## Installation

MiMoLo uses Poetry for dependency management:

```bash
# Install dependencies
poetry install --with dev

# Run tests
poetry run pytest -v

# Check types
poetry run mypy mimolo

# Lint code
poetry run ruff check .
```

## Quick Start

### 1. Test Event Generation

Generate synthetic test events:

```bash
poetry run mimolo test
```

### 2. View Available Plugins

See registered plugins and their specifications:

```bash
poetry run mimolo register
```

### 3. Run the Monitor

Start the orchestrator with the example plugin (configured in [mimolo.toml](mimolo.toml)):

```bash
poetry run mimolo monitor
```

Press `Ctrl+C` to stop gracefully.

## Configuration

Edit `mimolo.toml` to configure:

- **Cooldown duration**: How long after the last resetting event before closing a segment
- **Poll intervals**: How often each plugin is polled
- **Log format**: JSONL (default), YAML, or Markdown
- **Plugin settings**: Enable/disable and configure individual plugins

Example configuration:

```toml
[monitor]
cooldown_seconds = 600
poll_tick_s = 0.2
log_dir = "./logs"
log_format = "jsonl"

[plugins.example]
enabled = true
poll_interval_s = 3.0
resets_cooldown = true
```

## Understanding Segments

MiMoLo aggregates events into time segments:

1. **Opening**: First resetting event opens a segment
2. **Active**: Additional events extend and reset the cooldown timer
3. **Closing**: After cooldown expires with no resetting events, segment closes
4. **Output**: Aggregated segment written to log files

## Output Formats

### JSONL (Default)

One JSON object per line in `logs/YYYY-MM-DD.mimolo.jsonl`:

```json
{"type":"segment","start":"2025-11-05T10:00:00Z","end":"2025-11-05T10:10:05Z","duration_s":605.0,"labels":["example"],"aggregated":{"examples":["fake_item_1","fake_item_2"]},"resets_count":3,"events":[...]}
```

### YAML

Human-readable YAML documents in `logs/YYYY-MM-DD.mimolo.yaml`.

### Markdown

Summary tables in `logs/YYYY-MM-DD.mimolo.md`.

## Writing Custom Plugins

**Quick Start:**
1. Copy `mimolo/plugins/template.py` to create your plugin
2. Fill in the TODOs with your monitoring logic
3. Follow the complete guide: [developer_docs/agent_dev/AGENT_DEV_GUIDE.md](developer_docs/agent_dev/AGENT_DEV_GUIDE.md)

**Example plugins:**
- [example.py](mimolo/plugins/example.py) - Basic event emission with aggregation
- [folderwatch.py](mimolo/plugins/folderwatch.py) - Stateful monitoring with custom config

**Minimal structure:**
```python
from mimolo.core.plugin import BaseMonitor, PluginSpec
from mimolo.core.event import Event

class MyMonitor(BaseMonitor):
    spec = PluginSpec(
        label="mymonitor",
        data_header="items",
        resets_cooldown=True,
        poll_interval_s=5.0,
    )

    def emit_event(self) -> Event | None:
        # Return Event or None
        pass

    @staticmethod
    def filter_method(items: list) -> list:
        # Aggregate collected data
        return sorted(set(items))
```

## Testing

Run the full test suite:

```bash
poetry run pytest -v

# With coverage
poetry run pytest --cov=mimolo --cov-report=html
```

All 46 tests should pass.

## Development

VS Code tasks are configured in [.vscode/tasks.json](.vscode/tasks.json):

- **install**: Install dependencies
- **lint**: Run ruff + mypy
- **test**: Run pytest
- **run:monitor**: Start the monitor

## Architecture

```
mimolo/
├── core/           # Framework core
│   ├── event.py    # Event primitives
│   ├── plugin.py   # Plugin contracts
│   ├── registry.py # Plugin management
│   ├── cooldown.py # Segment FSM
│   ├── aggregate.py # Data aggregation
│   ├── config.py   # Configuration
│   ├── sink.py     # Output writers
│   └── runtime.py  # Orchestrator
├── plugins/        # Plugin implementations
│   ├── example.py
│   └── folderwatch.py
└── cli.py          # CLI commands
```

## Next Steps

- Customize `mimolo.toml` for your use case
- Write custom plugins for your monitoring needs
- Integrate with your workflow (run as service, cron job, etc.)
- Explore log output and adjust aggregation filters

## Support

- Report issues on GitHub
- See the spec in [README.md](README.md) for detailed architecture
- Check [tests/](tests/) for usage examples
