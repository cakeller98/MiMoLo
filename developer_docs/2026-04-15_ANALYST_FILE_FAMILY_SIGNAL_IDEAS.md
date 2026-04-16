# 2026-04-15 Analyst File-Family Signal Ideas

## Why this note exists

The current day blip chart is useful, but it is generous. The next step is not to split into many new trackers yet. The next step is to preserve evidence and let the analyst layer classify it better.

Key current conclusion:

- Do not create 25 different file trackers by default.
- Keep the generic folder/file watcher evidence-rich.
- Let the analyst layer apply file-family rules and filtered interpretations.
- Add app-native activity emitters only when filesystem evidence is fundamentally insufficient.

## Core direction

Treat this as an analyst problem first, not an agent proliferation problem.

Preferred model:

1. Generic file watcher emits rich raw evidence.
2. Analyst rules classify raw paths by file family.
3. Daily derived summaries answer:
   - what file families dominated the day
   - what logical work files were most active
   - what activity was likely "real work" vs support churn
4. Only add app-specific activity emitters when file activity alone is too weak.

## Evidence preservation requirement

The current `50+ files` style truncation is not enough for serious analysis.

We likely need the full changed-file list in events, or something very close to it.

Reason:

- later analyst filters need to answer "was this mostly Plasticity autosaves?"
- later analyst filters need to answer "was this mostly Creo revision saves?"
- later analyst filters need to answer "what exact changed files made this 15m bucket look active?"

Initial bias:

- log the full changed-file list inline
- keep summary counts too
- do not prematurely compress per-event payloads unless data volume proves it is necessary

## Daily derived ledger idea

Build an analyst-side daily derived database / index from the raw logs.

Potential per-day output:

- canonical file identity when applicable
- raw paths seen
- hit count
- hit timestamps
- active 15m buckets touched
- file family classification
- normalization rule used

This can support questions like:

- "what file did I work on most today?"
- "which files stayed hot all day?"
- "was this one file or many files?"
- "was this autosave churn or explicit saves?"

## Creo work-file idea

Creo likely wants analyst-side normalization for revisioned work files.

Candidate filename regex:

```regex
^(.+?)\.(prt|asm)\.(\d+)$
```

Interpretation:

- group 1 = base file stem
- group 2 = Creo work-file type
- group 3 = revision number

Examples:

- `widget.prt.17`
- `widget.prt.18`
- `assembly.asm.4`

Possible analyst normalization:

- `widget.prt.17` and `widget.prt.18` collapse to logical file `widget.prt`
- `assembly.asm.4` collapses to logical file `assembly.asm`

This is for analyst identity and reporting, not necessarily for raw-event replacement.

Useful outputs:

- top logical Creo work files for the day
- hit counts by logical file
- revision growth over time
- active buckets for each logical file

## Plasticity idea

Plasticity should **not** be normalized the same way as Creo.

Current conclusion:

- autosave / backup files are real distinct files
- each autosave hit is meaningful activity evidence
- repeated hits on the same autosave file are meaningful
- explicit saves in the parent folder are a separate stronger signal

Implication:

- preserve Plasticity raw file identity by default
- classify later, do not collapse early

Potential analyst distinctions:

- autosave / backup file hits
- explicit project save hits
- parent-folder main file hits
- backup directory churn vs explicit save events

Important note:

Plasticity autosaves may be a very good sustained-work signal because they appear periodically when actual work is happening.

## Blender idea

Blender may need layered evidence.

Current thinking:

- track Blender autosave/temp file hits as filesystem evidence
- track real save hits separately
- only add an app-native trail/addon if autosaves are too sparse or too coarse

Potential addon direction if needed:

- a very lightweight Blender trail writer
- writes a tiny timestamped line only every N meaningful events
- intentionally rate-limited
- examples: every 20 / 50 / 100 meaningful actions
- optional transition markers like `session_open`, `active`, `idle`, `session_close`

Why:

- long Blender sessions may not produce enough file writes
- an ultralight trail can provide "still actively working" evidence without heavy churn

But:

- do not assume the addon is needed until Blender autosave evidence is measured

## Modo / LXO / other families

Blender and Modo/LXO likely need different treatment from Creo and Plasticity.

General rule:

- if filesystem behavior is enough, stay analyst-side
- if filesystem behavior is not enough, add app-native activity emitters

This suggests a family-rule registry, not a tracker explosion.

## Suggested architecture direction

Build a file-family analyst rules registry with categories like:

- raw-preserved families
  - example: Plasticity autosaves/backups
- canonicalized families
  - example: Creo `.prt.#` / `.asm.#`
- app-assisted families
  - example: Blender / Modo if file writes undercount active work

This keeps the generic watcher simple while letting analysis become smarter.

## Near-term next steps

1. Inspect the existing logs for Plasticity backup/autosave patterns.
2. Inspect existing Creo revision file patterns.
3. Confirm whether current blip-chart solid blocks are mostly autosave churn, explicit saves, or both.
4. Decide whether the generic watcher should start logging the full changed-file list.
5. Sketch a daily derived analyst ledger format.
6. Revisit whether Blender needs only autosave tracking or also a lightweight addon trail.

## Current stance

Do not overbuild tonight.

What is already proven:

- the blip chart is useful
- the evidence needs richer interpretation
- different file families carry different meaning

What should happen next:

- collect evidence
- preserve more evidence
- classify better in the analyst layer
- only then decide where app-specific emitters are justified
