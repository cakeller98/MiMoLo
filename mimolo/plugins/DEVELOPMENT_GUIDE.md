# MiMoLo Plugin Development Guide

Complete guide for creating custom monitor plugins for the MiMoLo framework.

## Overview

MiMoLo plugins extend the framework by implementing custom event monitors. Each plugin polls for events, emits them when detected, and optionally aggregates collected data when segments close.

## Quick Start

### Use the Template

The fastest way to get started:

1. **Copy the template:**
   ```bash
   cp mimolo/plugins/template.py mimolo/plugins/myplugin.py
   ```

2. **Fill in the TODOs:**
   - Change class name from `TemplateMonitor` to `MyMonitor`
   - Update `spec.label` to unique identifier
   - Add detection logic in `emit_event()`
   - Customize `filter_method()` if needed

3. **Follow registration steps** (see below)

### Minimal Working Example

Here's what a complete minimal plugin looks like:

```python
"""My custom monitor plugin."""

from __future__ import annotations

from datetime import UTC, datetime

from mimolo.core.event import Event
from mimolo.core.plugin import BaseMonitor, PluginSpec


class MyMonitor(BaseMonitor):
    """Monitor that does something useful."""

    spec = PluginSpec(
        label="mymonitor",           # Unique identifier
        data_header="items",          # Key in event.data for aggregation
        resets_cooldown=True,         # Reset segment timer on events
        infrequent=False,             # False = participate in aggregation
        poll_interval_s=5.0,          # Poll every 5 seconds
    )

    def emit_event(self) -> Event | None:
        """Check for events and emit if found."""
        # Your detection logic here
        if something_detected:
            return Event(
                timestamp=datetime.now(UTC),
                label=self.spec.label,
                event="event_type",
                data={"items": ["detected_item"]},
            )
        return None

    @staticmethod
    def filter_method(items: list[list[str]]) -> list[str]:
        """Aggregate collected items (optional)."""
        # Flatten and deduplicate
        flat = [item for sublist in items for item in sublist]
        return sorted(set(flat))
```

## Creating a New Plugin

### Step 1: Implement the Plugin Class

**Create a new file:** `mimolo/plugins/myplugin.py`

#### 1.1 Inherit from BaseMonitor

```python
from mimolo.core.plugin import BaseMonitor, PluginSpec
from mimolo.core.event import Event
```

#### 1.2 Define PluginSpec

```python
spec = PluginSpec(
    label="mymonitor",              # Required: unique identifier (must be valid Python identifier)
    data_header="items",             # Optional: key in event.data for aggregation
    resets_cooldown=True,            # Whether events reset segment timer (default: True)
    infrequent=False,                # Bypass aggregation, flush immediately (default: False)
    poll_interval_s=5.0,             # Polling frequency in seconds (default: 5.0)
)
```

**PluginSpec Fields:**
- `label`: Unique identifier across all plugins. Must be a valid Python identifier.
- `data_header`: If set, events must include this key in their `data` dict. Used for aggregation.
- `resets_cooldown`: If `True`, events from this plugin reset the segment cooldown timer.
- `infrequent`: If `True`, events bypass segment aggregation and are written immediately.
- `poll_interval_s`: How often the runtime calls `emit_event()` in seconds.

#### 1.3 Implement emit_event()

```python
def emit_event(self) -> Event | None:
    """Poll for events and return Event if detected, None otherwise.
    
    This method is called periodically based on poll_interval_s.
    Must be non-blocking and time-bounded.
    
    Returns:
        Event instance if something to report, None otherwise.
    """
    # Your detection logic
    if condition_met:
        return Event(
            timestamp=datetime.now(UTC),
            label=self.spec.label,
            event="event_type",
            data={self.spec.data_header: [value]} if self.spec.data_header else None,
        )
    return None
```

**Requirements:**
- Must be non-blocking (no long-running operations)
- Return `Event` when something detected, `None` otherwise
- Exceptions are caught by runtime and wrapped in `PluginEmitError`
- Use `datetime.now(UTC)` for timestamps

#### 1.4 Implement filter_method() (Optional)

Only needed if you want custom aggregation logic:

```python
@staticmethod
def filter_method(items: list[Any]) -> Any:
    """Aggregate collected data when segment closes.
    
    Args:
        items: List of values collected during the segment.
        
    Returns:
        Aggregated result (must be JSON-serializable).
    """
    # Default: return items as-is
    # Custom: deduplicate, sort, transform, etc.
    return sorted(set(items))
```

**Notes:**
- Called when a segment closes (only if `data_header` is set)
- Receives list of all values collected for your `data_header`
- Must return JSON-serializable data
- Default implementation returns items list unchanged

### Step 2: Register the Plugin

#### 2.1 Add to `mimolo/plugins/__init__.py`

```python
from mimolo.plugins.myplugin import MyMonitor

__all__ = [
    "ExampleMonitor",
    "FolderWatchMonitor",
    "MyMonitor",  # Add your plugin
]
```

#### 2.2 Register in `mimolo/cli.py`

Find the `_discover_and_register_plugins()` function and add your plugin:

```python
def _discover_and_register_plugins(config: Config, registry: PluginRegistry) -> None:
    # Explicit plugin list for v0.2 (entry points later)
    available_plugins = {
        "example": ExampleMonitor,
        "folderwatch": FolderWatchMonitor,
        "mymonitor": MyMonitor,  # Add your plugin
    }
    
    for plugin_name, plugin_class in available_plugins.items():
        plugin_config = config.plugins.get(plugin_name)
        # ...
        
        # Instantiate plugin with config
        if plugin_name == "example":
            instance = plugin_class()
        elif plugin_name == "folderwatch":
            watch_dirs = plugin_config.model_extra.get("watch_dirs", [])
            extensions = plugin_config.model_extra.get("extensions", [])
            instance = plugin_class(watch_dirs=watch_dirs, extensions=extensions)
        elif plugin_name == "mymonitor":
            # Add instantiation logic if your plugin needs custom args
            custom_arg = plugin_config.model_extra.get("custom_arg", default_value)
            instance = plugin_class(custom_arg=custom_arg)
        else:
            instance = plugin_class()
```

### Step 3: Add Configuration

Add a section to `mimolo.toml`:

```toml
[plugins.mymonitor]
enabled = true
poll_interval_s = 5.0
resets_cooldown = true
infrequent = false

# Add plugin-specific settings here
custom_setting = "value"
custom_list = ["item1", "item2"]
```

**Standard Fields:**
- `enabled`: Whether plugin is active
- `poll_interval_s`: Override default polling interval
- `resets_cooldown`: Override default cooldown reset behavior
- `infrequent`: Override default aggregation behavior

**Custom Fields:**
- Add any plugin-specific settings
- Access via `plugin_config.model_extra.get("field_name", default)`

### Step 4: Verify Registration

Run the register command to see your plugin:

```bash
poetry run mimolo register
```

Your plugin should appear in the output with its spec details.

## Event Structure

Events must have these fields:

```python
Event(
    timestamp=datetime.now(UTC),      # UTC timezone required
    label="mymonitor",                 # Must match spec.label
    event="event_type",                # Short event identifier
    data={"items": [value]},           # Optional dict (include data_header if set)
)
```

**Requirements:**
- `timestamp`: Must be timezone-aware (use `UTC` from `datetime`)
- `label`: Must match your plugin's `spec.label`
- `event`: Short string describing event type
- `data`: Optional dict. If `spec.data_header` is set, must include that key

## Segment Lifecycle

Understanding how segments work helps design better plugins:

1. **IDLE**: No segment open, waiting for first resetting event
2. **First Event**: Opens segment (if `resets_cooldown=True`)
3. **ACTIVE**: Segment open, cooldown timer running
4. **Additional Events**: 
   - Resetting events reset timer and increment `resets_count`
   - Non-resetting events are recorded but don't reset timer
5. **Cooldown Expires**: Segment enters CLOSING state
6. **Aggregation**: `filter_method()` called for each `data_header`
7. **Write**: Segment written to logs
8. **Back to IDLE**: Ready for next segment

## Advanced Features

### Stateful Monitoring

Maintain state between `emit_event()` calls:

```python
class StatefulMonitor(BaseMonitor):
    def __init__(self):
        self._last_check = None
        self._cache = {}
    
    def emit_event(self) -> Event | None:
        # Use state to detect changes
        current_state = get_current_state()
        if current_state != self._cache:
            self._cache = current_state
            return Event(...)
        return None
```

### Custom Initialization

Pass configuration to your plugin:

```python
class ConfigurableMonitor(BaseMonitor):
    def __init__(self, paths: list[str], threshold: int = 10):
        self.paths = paths
        self.threshold = threshold
```

Then in `cli.py`:
```python
paths = plugin_config.model_extra.get("paths", [])
threshold = plugin_config.model_extra.get("threshold", 10)
instance = ConfigurableMonitor(paths=paths, threshold=threshold)
```

### Infrequent Events

For rare events that shouldn't wait for segment closing:

```python
spec = PluginSpec(
    label="rare_event",
    infrequent=True,  # Write immediately, bypass aggregation
    poll_interval_s=60.0,
)
```

Use cases:
- Error/exception monitoring
- System alerts
- One-off notifications

### Complex Aggregation

Custom aggregation logic in `filter_method()`:

```python
@staticmethod
def filter_method(items: list[dict]) -> dict:
    """Aggregate with statistics."""
    return {
        "count": len(items),
        "unique": len(set(items)),
        "first": items[0] if items else None,
        "last": items[-1] if items else None,
    }
```

## Testing

Create tests in `tests/test_plugins_mymonitor.py`:

```python
"""Tests for mymonitor plugin."""

from mimolo.plugins.mymonitor import MyMonitor


def test_mymonitor_spec():
    """Test MyMonitor spec attributes."""
    spec = MyMonitor.spec
    
    assert spec.label == "mymonitor"
    assert spec.data_header == "items"
    assert spec.resets_cooldown is True
    assert spec.poll_interval_s == 5.0


def test_mymonitor_emit_event():
    """Test MyMonitor event emission."""
    monitor = MyMonitor()
    event = monitor.emit_event()
    
    # Test based on your logic
    if event:
        assert event.label == "mymonitor"
        assert "items" in event.data


def test_mymonitor_filter_method():
    """Test MyMonitor aggregation."""
    items = [["item1", "item2"], ["item2", "item3"]]
    result = MyMonitor.filter_method(items)
    
    assert isinstance(result, list)
    assert len(result) == 3  # Deduplicated
```

Run tests:
```bash
poetry run pytest tests/test_plugins_mymonitor.py -v
```

## Debugging

### Enable Debug Logging

In `mimolo.toml`:
```toml
[monitor]
console_verbosity = "debug"
```

### Check Plugin Registration

```bash
poetry run mimolo register
```

### Dry Run

Test configuration without running:
```bash
poetry run mimolo monitor --dry-run
```

### Common Issues

**Plugin not registered:**
- Check `__init__.py` exports
- Check `cli.py` available_plugins dict
- Verify plugin enabled in config

**Events not emitting:**
- Add debug prints in `emit_event()`
- Check `poll_interval_s` timing
- Verify `emit_event()` returns Event, not dict

**Aggregation not working:**
- Verify `data_header` is set in spec
- Check event.data includes data_header key
- Ensure `filter_method()` returns JSON-serializable data

**Type errors:**
- Run `poetry run mypy mimolo`
- Check Event timestamp has UTC timezone
- Verify filter_method signature matches

## Error Handling

MiMoLo distinguishes between **fatal errors** that should crash the application and **graceful failures** that should be handled without killing the runtime.

### Framework-Level Error Handling

The runtime handles plugin errors gracefully:

- **PluginEmitError**: Exceptions from `emit_event()` are caught and logged
- **Exponential Backoff**: Failing plugins are quarantined temporarily
- **Error Tracking**: Consecutive errors increase backoff duration
- **Recovery**: Successful calls reset error count

You don't need explicit try/catch in `emit_event()` unless you want custom error handling.

### Fatal vs. Non-Fatal Errors

**Fatal Errors** - These should crash the application:
- Invalid plugin configuration that prevents basic functionality
- Duplicate plugin labels during registration
- Missing required dependencies
- Malformed plugin spec (invalid label, negative poll_interval_s)

Use these only in `__init__()` or validation methods when the plugin cannot function at all.

**Non-Fatal Errors** - Handle gracefully with user feedback:
- Invalid configuration values (bad paths, missing files, etc.)
- Runtime failures that don't prevent core functionality
- Transient errors (network issues, temporary file locks)
- Partial configuration problems

### Graceful Error Handling Pattern

The `FolderWatchMonitor` demonstrates the best practice for graceful error handling:

#### 1. Validate Configuration Without Raising

```python
def _validate_and_filter(self) -> tuple[list[Path], list[str], list[str]]:
    """Validate configured watch directories and normalize them without raising.
    
    Returns:
        (valid_dirs, missing, not_dirs)
    """
    if self._validated:
        return self.watch_dirs, [], []
    
    resolved_valid: list[Path] = []
    missing: list[str] = []
    not_dirs: list[str] = []
    
    for d in self.watch_dirs:
        try:
            p = d.resolve()
        except OSError:
            p = d
        if not p.exists():
            missing.append(str(p))
            continue
        if not p.is_dir():
            not_dirs.append(str(p))
            continue
        resolved_valid.append(p)
    
    # Store only valid paths
    self.watch_dirs = sorted(set(resolved_valid))
    self._validated = True
    return self.watch_dirs, missing, not_dirs
```

**Key principles:**
- Don't raise exceptions for bad config values
- Separate valid from invalid inputs
- Continue working with valid subset
- Return diagnostic information for feedback

#### 2. Emit Warning Events for Invalid Configuration

```python
def emit_event(self) -> Event | None:
    """Check watched directories for file modifications."""
    # Validate configuration on first tick without raising
    if not self._validated:
        valid_dirs, missing, not_dirs = self._validate_and_filter()
        
        # Emit warning event if there are invalid entries
        if (missing or not_dirs) and not self._warn_emitted:
            self._warn_emitted = True
            now = datetime.now(UTC)
            return Event(
                timestamp=now,
                label=self.spec.label,
                event="watch_warning",
                data={
                    "folders": [str(p) for p in valid_dirs],
                    "invalid": {
                        "missing": missing,
                        "not_dirs": not_dirs,
                    },
                    "message": (
                        "Some configured folders are invalid. Please fix your config."
                    ),
                    "extensions": sorted(self.extensions) if self.extensions else [],
                },
            )
```

**Key principles:**
- Emit special event types for warnings (`watch_warning`)
- Include diagnostic information in event data
- Provide actionable message for users
- Use one-time flags to avoid spam (`self._warn_emitted`)

#### 3. Emit Acknowledgment Events for Valid Configuration

```python
        # If there are valid entries, emit a one-time ack that lists them
        if valid_dirs and not self._ack_emitted:
            self._ack_emitted = True
            now = datetime.now(UTC)
            return Event(
                timestamp=now,
                label=self.spec.label,
                event="watch_started",
                data={
                    "folders": [str(p) for p in valid_dirs],
                    "extensions": sorted(self.extensions) if self.extensions else [],
                },
            )
```

**Key principles:**
- Confirm what the plugin is actually monitoring
- Give users visibility into working configuration
- Emit once to avoid log spam

#### 4. Handle Edge Cases

```python
        # If nothing configured, warn once
        if not valid_dirs and not self._warn_emitted:
            self._warn_emitted = True
            now = datetime.now(UTC)
            return Event(
                timestamp=now,
                label=self.spec.label,
                event="watch_warning",
                data={
                    "folders": [],
                    "invalid": {"missing": [], "not_dirs": []},
                    "message": (
                        "No watch_dirs configured for FolderWatchMonitor. "
                        "Set plugins.folderwatch.watch_dirs."
                    ),
                    "extensions": sorted(self.extensions) if self.extensions else [],
                },
            )
```

**Key principles:**
- Detect and warn about empty/missing configuration
- Provide specific guidance on what to fix
- Reference exact config keys the user should set

### Complete Implementation Checklist

When implementing graceful error handling:

1. **Add validation flags to `__init__`:**
   ```python
   self._validated: bool = False
   self._ack_emitted: bool = False
   self._warn_emitted: bool = False
   ```

2. **Create validation method that returns diagnostics:**
   - Returns tuple of (valid_items, error1, error2, ...)
   - Never raises for config problems
   - Normalizes/resolves valid inputs

3. **First `emit_event()` call validates and emits feedback:**
   - Warning events for invalid config
   - Acknowledgment events for valid config
   - Specific guidance in messages

4. **Continue working with valid subset:**
   - Don't block on partial failures
   - Process what works, report what doesn't
   - Allow users to fix issues incrementally

### Event Types for Feedback

Recommended event types:

- `<plugin>_started` - Confirmation that plugin is running with valid config
- `<plugin>_warning` - Non-fatal configuration or runtime warnings
- `<plugin>_error` - Recoverable errors during operation
- `<plugin>_info` - Informational messages (use sparingly)

### When to Use Fatal Errors

Raise exceptions in `__init__()` only when:

```python
def __init__(self, required_param: str):
    # Fatal: Plugin cannot function without this
    if not required_param:
        raise ValueError("required_param is mandatory for MyPlugin")
    
    # Non-fatal: Warn via events instead
    self._optional_paths = self._validate_optional_paths(optional_paths)
```

Use fatal errors for:
- Missing required parameters with no sensible default
- Type mismatches that would cause immediate crashes
- Fundamental capability checks (e.g., missing required system library)

### Testing Error Handling

Add tests for error scenarios:

```python
def test_mymonitor_invalid_config():
    """Test MyMonitor handles invalid config gracefully."""
    monitor = MyMonitor(invalid_path="/nonexistent")
    
    # First emit should be warning event
    event = monitor.emit_event()
    assert event is not None
    assert event.event == "watch_warning"
    assert "invalid" in event.data
    assert "message" in event.data
    
    # Should not raise, should continue working
    event2 = monitor.emit_event()
    # May be None or valid event, but no exception


def test_mymonitor_valid_config():
    """Test MyMonitor emits ack for valid config."""
    monitor = MyMonitor(valid_path="/tmp")
    
    # First emit should be ack event
    event = monitor.emit_event()
    assert event is not None
    assert event.event == "watch_started"
    assert "folders" in event.data
```

### Real-World Example Summary

The `FolderWatchMonitor` demonstrates:

✅ **Validates without raising** - Separates good from bad paths
✅ **Emits warning events** - Lists invalid paths with actionable messages  
✅ **Emits acknowledgment** - Shows what's actually being monitored
✅ **Continues working** - Monitors valid paths despite invalid ones
✅ **One-time feedback** - Uses flags to avoid log spam
✅ **Specific guidance** - Points users to exact config keys to fix

This pattern ensures users get meaningful feedback they can act on, while keeping the runtime stable.

## Performance Tips

1. **Keep emit_event() Fast**: Aim for < 100ms execution time
2. **Use Caching**: Store computed state between polls
3. **Lazy Loading**: Initialize expensive resources only when needed
4. **Adjust poll_interval_s**: Don't poll faster than necessary
5. **Batch Operations**: Process multiple items per event if possible

## Example Plugins

### ExampleMonitor (`example.py`)
- Basic event emission
- Simple aggregation with `filter_method()`
- Synthetic data generation

### FolderWatchMonitor (`folderwatch.py`)
- Stateful monitoring (file mtimes)
- Custom initialization args
- Real-world detection logic

Study these for patterns and best practices.

## Future Enhancements

Planned features:
- **Entry Points**: Auto-discovery via setuptools
- **Plugin Metadata**: Version, author, description
- **Lifecycle Hooks**: on_start, on_stop, on_segment_close
- **Async Support**: async def emit_event()
- **Plugin Dependencies**: Declare dependencies on other plugins

## Getting Help

- Check existing plugins in `mimolo/plugins/`
- Review tests in `tests/test_plugins_*.py`
- Read framework docs in `GETTING_STARTED.md`
- Open GitHub issue for questions
