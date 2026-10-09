# AGENTS.md

Before changing code in this repository, read in order:

1. `AGENTS.md`
2. `docs/AI_CHANGE_PROTOCOL.md`
3. `docs/CHANGE_CONTINUITY.md`
4. the canonical document for the subsystem being changed
5. the actual owner module and exact named function being changed

Architecture rule:

> one concern -> one owner -> one named function -> one diagnostic boundary

Do not combine data validation, time validation, state validation, dependency resolution, planning, safety, and runtime execution into one large function.

Diagnostic categories are fixed:

- data
- time
- state
- dependency
- planning
- safety
- runtime
- contract

Important failures should identify the first failing owner, function, category, code, and where useful expected / actual / details.

Do not add wrappers to avoid changing the true owner. Do not create a second state machine.

After every functional or architectural code change, update `docs/CHANGE_CONTINUITY.md`. If the protocol/canonical behavior changes, update the canonical document in the same change.
