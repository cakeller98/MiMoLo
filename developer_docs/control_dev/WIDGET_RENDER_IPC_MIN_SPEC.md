# Control <-> Operations Widget Render IPC (Minimal Spec)

Date: 2026-02-11
Status: Planned contract (design locked, implementation in progress)
Security posture: trust-first, security-first

## 1. Scope

This spec defines the widget rendering request/response path where:
- agents own plugin-specific presentation,
- operations transports and caches frames,
- control sanitizes and renders generic fragments.

Path:
- Control IPC request -> Operations
- Operations routes request to target Agent via Agent JLP command
- Agent returns `widget_frame` payload
- Operations validates transport bounds/token refs and returns payload
- Control sanitizes HTML fragment and renders in widget canvas

## 2. Non-Goals

1. No arbitrary JS execution in widgets.
2. No direct `file://` paths from agent payloads to browser.
3. No plugin-specific HTML logic embedded in Operations or Control.

## 3. Terminology

- Agent JLP: Operations <-> Agent newline-delimited JSON protocol.
- Control IPC: Control <-> Operations local socket protocol.
- Widget Canvas: fixed container in Control UI where plugin content is rendered.
- Render Fragment: constrained `html_fragment_v1` returned by agent for display.
- Widget Frame: agent-produced render payload (`type = "widget_frame"`).
- Evidence Plane: canonical JSONL records (`summary`, `heartbeat`, `status`, `error`, etc.).
- Rendering Plane: ephemeral widget frame payloads.

## 4. Core Principles (Locked)

1. Agent decides plugin-specific representation.
2. Operations is transport/cache/index authority, not plugin-aware renderer.
3. Control is the authoritative HTML sanitizer before DOM insertion.
4. CSS class allowlist is owned by Control sanitizer policy.
5. Artifact references are tokenized through Operations (never raw filesystem paths).

## 5. Control IPC Commands

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
  - `html`: agent-provided fragment (unsanitized at transport layer)
  - `ttl_ms`: integer
  - `state_token`: opaque string for incremental refresh
  - `warnings`: optional transport/preflight notes

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
  "action":"refresh",
  "payload":{}
}
```

Success `data`:
- `accepted`: bool
- `state_token`: optional updated token

Action semantics lock:
- `action = "refresh"` must:
  - execute the same plugin pipeline used by scheduled tick/flush,
  - force immediate evidence emission (JSONL entry) regardless of tick timing,
  - make updated frame data available for `request_widget_render`.

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

Agent -> Operations response (new message type):
```json
{
  "type":"widget_frame",
  "timestamp":"2026-02-11T12:00:00Z",
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
  "args":{"action":"refresh","payload":{}}
}
```

## 7. HTML Fragment Safety Rules (`html_fragment_v1`)

Trust boundary:
- Agent HTML is untrusted input.
- Operations may apply preflight checks (mode/size/token sanity).
- Control sanitizer is final authority before DOM insertion.

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
- `class`
- `title`
- `aria-*`
- `alt`
- `src` (image only, must use `mimolo://artifact/<token>`)
- `href` (optional, allowlist policy if enabled)

Payload bounds:
- max fragment size enforced by Operations (for example `64KB`)
- max token/image count and row bounds enforced by Operations preflight

## 8. Artifact Token Rules

1. Agents never return raw absolute filesystem paths.
2. Operations maps artifact refs -> short-lived `mimolo://artifact/<token>` URLs.
3. Tokens are scoped to plugin instance and expire quickly.
4. Control resolves token through Operations bridge only.
5. Archived-but-not-rehydrated artifacts must return a warning (`archived_data_rehydrate_required`).

## 9. Data Plane Separation (Locked)

1. Evidence plane:
- canonical raw JSONL records are ground truth.
- evidence packets include plugin/instance identity and reconstructable payload references.

2. Rendering plane:
- `widget_frame` payloads are ephemeral cache data for UI rendering.
- not canonical evidence.

3. Activity timeline derivation:
- computed in post-processing from canonical raw records.
- no ingest-time timeline rounding/mutation.

## 10. Audit and Observability

Operations should emit lightweight events:
- `widget_render_requested`
- `widget_render_returned`
- `widget_render_rejected`
- `widget_action_dispatched`
- `widget_action_failed`
- `widget_action_refresh_forced_flush`

Include:
- `plugin_id`, `instance_id`, `request_id`, `bytes`, `duration_ms`, `reason`

## 11. Implementation Notes

Implemented today:
- IPC transport and command envelope.
- Agent JLP transport and ACK/summary/log/error patterns.

Planned:
- `widget_render` and `widget_action` handling in runtime command router.
- `widget_frame` message support in protocol parser/runtime routing.
- Operations preflight checks for render payload bounds/token shape.
- Control sanitizer + class/attribute allowlist enforcement.
- secure artifact token resolver in Control/Operations bridge.
