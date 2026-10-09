# Canonical Experiment Protocol

This document is the canonical specification for the current benchmark protocol.

## Scope

The primary contribution under study is a **leaderless, fully decentralized task-allocation decision protocol**. Initial task dissemination is reliable; executor selection is decentralized.

## Allocation epoch

For an eligible robot set \(R\), every task is processed in a deterministic task order in the current protocol version.

For each task and round:

1. all currently eligible robots know the task;
2. each eligible robot computes its own scalar execution cost;
3. robots announce costs to peers;
4. each robot forms a local view from successfully received cost announcements plus its own cost;
5. each robot selects the minimum-cost visible candidate, breaking ties by robot ID;
6. each robot sends at most one vote to that candidate;
7. votes are deduplicated by voter ID;
8. a robot wins only after receiving
   \[
   Q=\lfloor N/2\rfloor+1
   \]
   distinct valid votes, where \(N\) is the fixed eligible-set size for that task/round;
9. the winner is removed from the eligible set for subsequent tasks in that epoch;
10. stale-round messages do not count.

## E0 scope

E0 uses zero packet loss and synthetic Euclidean-distance costs only to verify protocol mechanics.

Synthetic E0 cost:

\[
c_{ij}=\|p_i-p_j\|_2.
\]

This is **not** yet the final paper cost model.

The centralized Hungarian solution over the same cost matrix is an oracle/reference. Because the protocol currently assigns tasks sequentially, E0 may expose a non-zero global optimality gap even when packet loss is zero. That is an experimental finding, not a protocol correctness failure.

## E0 safety invariants

- no task has multiple valid winners;
- a voter contributes at most one counted vote per task/round;
- stale-round votes are rejected;
- quorum denominator is common and fixed per task/round;
- assigned robots are not assigned again in the same one-to-one allocation epoch.

## Reproducibility

Same configuration + same seed must reproduce the same:

- robot positions
- task positions
- cost matrix
- winners
- metrics
