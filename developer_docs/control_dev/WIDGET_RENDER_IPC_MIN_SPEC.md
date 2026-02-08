# Control <-> Operations Widget Render IPC (Minimal Spec)

Date: 2026-02-08
Status: Planned contract (not fully implemented yet)
Security posture: trust-first, security-first

## 1. Scope

This spec defines how Control requests agent-owned widget content without requiring
Operations or Control to understand plugin-specific data schemas.

Path:
- Control IPC request -> Operations
- Operations routes request to target Agent via Agent JLP command
- Agent returns render payload
- Operations validates/sanitizes -> returns to Control widget

## 2. Non-Goals

1. No arbitrary JS execution in widgets.
2. No direct filesystem paths from agent to browser.
3. No unsanitized raw HTML insertion into Control DOM.

## 3. Terminology

- Agent JLP: Operations <-> Agent newline-delimited JSON protocol.
- Control IPC: Control <-> Operations local socket protocol.
- Widget Canvas: fixed container in Control UI where plugin content is rendered.
- Render Fragment: constrained HTML snippet returned by agent for display.

## 4. Core Principles

1. Agent decides plugin-specific representation.
2. Operations enforces safety and bounds.
3. Control renders only validated fragment output.
4. CSS classes are from an allowlist owned by Operations/Control.
5. Images are served via Operations-issued artifact tokens, not raw paths.

## 5. Control IPC Commands (Planned)

## 5.1 `get_widget_manifest`

Purpose:
- discover widget capabilities and defaults for an instance.

Request:
```json
{
  "cmd":"get_widget_manifest",
  "plugin_id":"screen_tracker",
  "instance_id":"inst_abc123"
}
```

Success `data`:
- `widget`:
  - `supports_render`: bool
  - `default_aspect_ratio`: string (example `"16:9"`)
  - `min_refresh_ms`: integer
  - `supported_actions`: list of action names
  - `content_modes`: list (example `["html_fragment_v1"]`)

## 5.2 `request_widget_render`

Purpose:
- request latest render payload for a widget canvas.

Request:
```json
{
  "cmd":"request_widget_render",
  "plugin_id":"screen_tracker",
  "instance_id":"inst_abc123",
  "request_id":"req_001",
  "canvas":{
    "aspect_ratio":"16:9",
    "max_width_px":1280,
    "max_height_px":720
  },
  "mode":"html_fragment_v1"
}
```

Success `data`:
- `request_id`
- `render`:
  - `mode`: `"html_fragment_v1"`
  - `html`: sanitized fragment
  - `ttl_ms`: integer
  - `state_token`: opaque string for incremental refresh
  - `warnings`: optional list of sanitization or truncation notes

Error codes:
- `widget_not_supported`
- `render_timeout`
- `render_payload_too_large`
- `render_validation_failed`

## 5.3 `dispatch_widget_action`

Purpose:
- route widget-originated action events to the target instance.

Request:
```json
{
  "cmd":"dispatch_widget_action",
  "plugin_id":"client_folder_activity",
  "instance_id":"inst_acme",
  "action":"set_filter",
  "payload":{"query":"*.prt"}
}
```

Success `data`:
- `accepted`: bool
- `state_token`: optional updated token

## 6. Agent JLP Commands and Responses (Planned Extension)

Operations -> Agent command:
```json
{
  "cmd":"widget_render",
  "id":"req_001",
  "args":{
    "canvas":{"aspect_ratio":"16:9","max_width_px":1280,"max_height_px":720},
    "mode":"html_fragment_v1",
    "state_token":"..."
  }
}
```

Agent -> Operations response (planned new message type):
```json
{
  "type":"widget",
  "timestamp":"2026-02-08T12:00:00Z",
  "agent_id":"screen_tracker-001",
  "agent_label":"screen_tracker_main",
  "protocol_version":"0.3",
  "agent_version":"1.0.0",
  "data":{
    "request_id":"req_001",
    "mode":"html_fragment_v1",
    "html":"<figure class=\"mml-card\"><img class=\"mml-image\" src=\"mimolo://artifact/tok_123\" alt=\"latest capture\"></figure>",
    "ttl_ms":1000,
    "state_token":"st_456"
  }
}
```

Operations -> Agent action dispatch:
```json
{
  "cmd":"widget_action",
  "id":"act_001",
  "args":{"action":"set_filter","payload":{"query":"*.prt"}}
}
```

Agent -> Operations action ack:
```json
{
  "type":"ack",
  "timestamp":"2026-02-08T12:00:01Z",
  "agent_id":"client_folder_activity-001",
  "agent_label":"client_acme",
  "protocol_version":"0.3",
  "agent_version":"1.0.0",
  "ack_command":"widget_action",
  "message":"action_applied",
  "data":{"action":"set_filter"}
}
```

## 7. HTML Fragment Safety Rules (`html_fragment_v1`)

Allowed tags:
- `div`, `section`, `article`, `header`, `footer`
- `h1`, `h2`, `h3`, `p`, `span`
- `ul`, `ol`, `li`
- `table`, `thead`, `tbody`, `tr`, `th`, `td`
- `figure`, `figcaption`, `img`
- `a` (restricted)

Disallowed:
- `script`, `style`, `iframe`, `object`, `embed`, `link`, `form`
- inline event handlers (`onclick`, etc.)
- inline CSS (`style` attribute)

Allowed attributes (subset):
- `class` (allowlisted class names only)
- `title`
- `aria-*`
- `alt` (for image)
- `src` (image only, must use `mimolo://artifact/<token>`)
- `href` (optional, allowlist policy if enabled)

Class names:
- Only class names registered in Operations/Control stylesheet allowlist.
- Unknown classes are stripped.

Payload bounds:
- maximum fragment bytes enforced by Operations (for example `64KB`).
- maximum image token count and table row count may be enforced.

## 8. Artifact Token Rules

1. Agents never return raw absolute filesystem paths.
2. Operations maps artifact refs -> short-lived `mimolo://artifact/<token>` URLs.
3. Tokens are scoped to plugin instance and expire quickly.
4. Control resolves token through Operations bridge only.

## 9. Widget Canvas Behavior

1. Control owns outer canvas size and scrolling behavior.
2. Fragment is scaled to fit canvas; overflow handled by canvas scroll region.
3. Long file lists are allowed through table/list markup within scrollable canvas.

## 10. Audit and Observability

Operations should emit lightweight events:
- `widget_render_requested`
- `widget_render_returned`
- `widget_render_rejected`
- `widget_action_dispatched`
- `widget_action_failed`

Include:
- `plugin_id`, `instance_id`, `request_id`, `bytes`, `duration_ms`, `reason`

## 11. Implementation Notes

Implemented today:
- IPC transport and command envelope.
- Agent JLP command transport and ACK/summary/log/error patterns.

Planned:
- `widget_render` and `widget_action` command handling in runtime.
- `widget` response message support in protocol parser/runtime routing.
- HTML sanitizer + class allowlist enforcement in Operations.
- secure artifact token resolver in Control/Operations bridge.
