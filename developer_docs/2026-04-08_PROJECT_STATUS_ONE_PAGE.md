# MiMoLo Project Status: One-Page Explainer

Date: 2026-04-08

## Executive Verdict

MiMoLo is not a throwaway experiment anymore. It already has a real runtime, real agent process management, real IPC, a usable prototype Control surface, a real screenshot agent, and a real folder-activity agent.

But for the specific workflow you care about, it is not yet fully usable.

My current assessment:

- Platform/foundation readiness: roughly 70%
- Your actual breadcrumb workflow readiness: roughly 45%
- "Can this become in-house usable in less than 24 hours?": yes, if scope is narrowed hard to the 3 real evidence streams and not the broader product ambitions
- "Should this be rewritten from scratch?": no

The correct move is not a rewrite. The correct move is a spec reset around the real job, then a fast completion pass on top of the existing platform.

## What Already Works

The codebase already has important pieces that would be expensive to recreate:

- Operations runtime, agent spawning, shutdown, IPC command routing, and plugin packaging/install plumbing are real.
- `client_folder_activity` is a substantive implementation, not a stub. It tracks created/modified/deleted files, bounds payload sizes, emits summaries, and already has widget-oriented recent-row output.
- `screen_tracker` is also substantive. It captures screenshots, writes full and thumbnail artifacts, hashes them, emits lightweight references, and has working widget render support.
- `control_proto` is a real prototype control plane with instance management, runtime status polling, and widget refresh/render flows.
- Portable launcher/runtime work is already substantial.

That means the repo already contains a usable skeleton for "collect evidence from several lightweight agents and persist it."

## What Is Still Blocking Real Use

The blockers are specific and important:

1. The `trail_tracker` you actually need does not exist yet.
   - There is a spec in `developer_docs/agent_dev/trail_tracker/trail_tracker_SPEC.md`.
   - There is no implementation under `mimolo/agents/`.

2. The activity/cooldown model is not actually wired to the real agent summaries.
   - Agents emit `activity_signal`.
   - `client_folder_activity` even marks `keep_alive` true/false.
   - But runtime summary handling currently just writes events to the sink and caches the last summary.
   - The orchestrator cooldown logic exists, but it is not being driven by those summary activity signals.

This matters because your most important requirement is smart activity tracking with debounce, rather than just "log whatever happened."

3. `screen_tracker` is only partway to the spec you want.
   - It is effectively macOS-only today.
   - It creates `index/` and `archives/` directories, but does not actually write the artifact index/history you need.
   - Its `scale` setting is currently metadata, not a true capture-scaling behavior.

4. The operator experience is still rough.
   - Top-level docs are stale.
   - The default `mimolo.toml` enables scaffold/dev agents and includes a hardcoded watch path, so the default launch path is not cleanly usable as-is.

## Bottom Line

MiMoLo is best understood as:

"A solid in-progress evidence collection platform with two partially-real agents, one missing agent, and one missing core activity model."

That is not a reason to rewrite. It is a reason to cut scope and finish the right 20%.

## Recommended Path

Do not rewrite the platform.

Do this instead:

1. Freeze a very small spec for the 3 real evidence streams:
   - timed screenshots
   - Creo trail writes
   - artifact/file creation-modification history in selected folders
2. Wire the runtime so agent `activity_signal.keep_alive` actually drives session activity and cooldown.
3. Implement `trail_tracker` by reusing patterns from `client_folder_activity` and `screen_tracker`.
4. Add lightweight artifact index/history records for screenshots and trail/file evidence.
5. Clean the default config and docs so the portable launch path reflects the real in-house workflow.

If you do only that, I think this can reach "usable for your own working evidence" quickly.

If you instead chase archive/restore UX, signing policy, commercial Control parity, and broader plugin-system polish first, it will keep feeling unfinished.
