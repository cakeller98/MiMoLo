# MiMoLo Rewrite Packet Manifest

## Purpose

This document defines the intended handoff packet for an external rewrite vendor.

The goal is to provide a clean, explicit, self-contained specification package that is sufficient to design and implement the Rust rewrite from scratch.

The existing codebase is included only as:

- behavioral reference
- ambiguity resolution aid
- question-generation material

The existing codebase is **not** the intended architecture.

## Governing Rule

The rewrite packet should be sufficient to guide implementation even if the codebase did not exist.

The codebase is supplied:

- to inspect legacy behavior
- to confirm edge cases
- to extract examples
- to ask clarifying questions

The codebase is **not** supplied:

- as architectural truth
- as required design inheritance
- as the source of subsystem boundaries
- as a mandate to preserve shell-script or Electron-era structure

## Packet Structure

The rewrite handoff should contain exactly three categories:

1. Normative rewrite documents
2. Curated evidence examples
3. Reference-only legacy codebase

## 1. Normative Rewrite Documents

These documents define what should be built.

Required:

- `2026-04-16_RUST_REWRITE_SPEC.md`
- `agent_dev/AGENT_PROTOCOL_SPEC.md`
- `4_Data_Schema_and_Message_Types.md`
- `2026-04-15_ANALYST_FILE_FAMILY_SIGNAL_IDEAS.md`

Strongly recommended:

- `2026-04-12_TRAIL_SIGNAL_AND_FAULT_TOLERANCE.md`
- `agent_dev/client_folder_activity/client_folder_activity_SPEC.md`
- `agent_dev/trail_tracker/trail_tracker_SPEC.md`

Optional only if still useful after curation:

- tightly scoped extracted notes that clarify unresolved behavior

Do not include broad historical note dumps unless they are explicitly curated and justified.

## 2. Curated Evidence Examples

These examples define what kinds of evidence the system must preserve and interpret.

Include:

- representative `.mimolo.jsonl` samples
- representative diagnostics log samples
- sample cases showing:
  - folder activity summaries
  - trail tracker summaries
  - lifecycle signals
  - heartbeats
  - IPC failure alerts
  - clean shutdown sequences

The sample set should be small, explicit, and intentionally selected.

Do not dump the entire logs directory into the packet unless a specific reason exists.

## 3. Reference-Only Legacy Codebase

The codebase may be included, but it must be clearly labeled:

- `REFERENCE ONLY`
- `NOT TARGET ARCHITECTURE`
- `USE FOR BEHAVIORAL QUESTIONS ONLY`

The vendor should be told explicitly:

- the rewrite must be guided by the normative packet documents
- the codebase may reveal historical behavior
- the codebase must not dictate architecture, crate layout, UI technology, or process model

## Exclusion Rule

The normative packet should avoid including legacy material that muddies intent.

If a document or directory exists primarily to explain:

- shell glue
- transient tooling
- obsolete UI stack
- ad hoc wrappers
- historical scaffolding

then it should be excluded unless explicitly recast as clean specification.

## Ideal Delivery Shape

The ideal handoff package looks like this:

- `rewrite_packet/`
- `rewrite_packet/spec/`
- `rewrite_packet/spec/2026-04-16_RUST_REWRITE_SPEC.md`
- `rewrite_packet/spec/agent_protocol/...`
- `rewrite_packet/spec/analyst/...`
- `rewrite_packet/examples/logs/...`
- `rewrite_packet/reference_codebase/...`
- `rewrite_packet/README_REWRITE_PACKET.md`

## Required Instruction To Vendor

The vendor should receive this instruction clearly:

“Build the Rust rewrite from the normative specification documents and curated evidence packet. The included legacy codebase is for reference only. It is provided to help discover behavioral details and ask questions, not to define intended architecture.”

## Success Criterion

The packet is correct when:

- a competent vendor can design the rewrite from the packet alone
- the packet does not require shell scripts, Electron code, or legacy wrappers to explain architecture
- the legacy codebase is helpful but unnecessary for core design direction
