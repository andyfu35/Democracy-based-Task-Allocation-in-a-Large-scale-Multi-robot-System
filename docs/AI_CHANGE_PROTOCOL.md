# AI Change Protocol

## Required reading order

Before code changes:

1. `AGENTS.md`
2. this file
3. `docs/CHANGE_CONTINUITY.md`
4. subsystem canonical specification
5. owner module and exact function

## Change discipline

Each change should modify one clear concern at a time.

Each important behavior must have:

- one owner module
- one named function
- explicit inputs/outputs
- a diagnostic boundary

Do not silently change experimental behavior.

## Diagnostics

Structured errors use:

- owner
- function
- category
- code
- expected
- actual
- details

Allowed categories:

`data | time | state | dependency | planning | safety | runtime | contract`

## Experimental reproducibility

Formal experiments must record:

- git commit SHA
- configuration
- seed
- raw per-seed result
- summary result
- algorithm identifier
- timestamp/environment when available

Raw data is append-only evidence. Aggregated summaries may be regenerated from raw data.
