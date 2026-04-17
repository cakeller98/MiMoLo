# Legacy Artifacts To Ignore For Rewrite Architecture

## Purpose

This document identifies legacy material that should not be treated as normative architecture for the Rust rewrite.

These artifacts may be useful for behavioral reference only.

## Ignore As Architecture

- `mml.ps1`
- `mml.sh`
- `scripts/`
- wrapper installers
- short-command shim scripts
- Electron dashboard directories
- Node/npm/npx build plumbing
- temporary compatibility utilities
- local scratch / temp directories
- cache directories
- archived developer notes unless explicitly curated

## Why

These artifacts are:

- workaround-heavy
- implementation-contingent
- pre-architected poorly or not at all
- shaped by current stack limitations
- not suitable as the design basis for the rewrite

## Use Only For

- legacy command behavior reference
- edge-case examples
- understanding what users were trained to expect
- identifying current failure modes to avoid

## Do Not Infer From These

- final module boundaries
- final process layout
- final IPC design
- final UI architecture
- final installer design
- final command parsing design

## Preferred Rewrite Basis

Use instead:

- the rewrite specification
- agent protocol specification
- data schema/message docs
- analyst design notes
- curated log examples

The rewrite should be a cleanly designed Rust system, not a structural port of these artifacts.
