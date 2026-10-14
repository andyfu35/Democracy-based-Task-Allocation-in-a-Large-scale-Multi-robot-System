# P2D Design — One-Shot Centralized Comparator and Full-Info Reference

**Status:** design for user review; no executable P2D implementation or new numerical results are claimed.
**Base branch:** `experiment/p2-global-greedy-voting` (the independently verified P2-C evidence remains immutable).
**Research purpose:** isolate communication/coordination structure while retaining the same task-cost definition and a common complete-information greedy reference.

## 1. User requirements and presentation labels

1. The primary method legend must contain exactly **Proposed Method**, **CBAA**, **CBBA**, and **Centralized Method**.
2. **Price Auction is excluded** from the new P2D comparison and plots. All original Price Auction/P1/P2/P2-C raw data, source hashes, and historical figures remain unchanged.
3. `Centralized Method` performs **no retransmissions, repeat Cost sends, request-again control, recovery loop, ACK/ARQ replay, or second optimization round**. A missing Cost packet stays missing.
4. A separate black dashed **Full-Info Baseline** appears in assignment-quality plots. It is an offline complete-information reference, **not a fifth algorithm** and not information supplied to lossy methods.
5. Internal implementation documentation must transparently state that Centralized Method and the current Proposed Method use the **same minimum-pair Global Greedy planner** when given the same information; the public figure legend displays only `Centralized Method`.

## 2. Frozen experiment and preservation boundary

- `N=T=100`, capacity `1`, same 100 seeded 100m × 100m scenes `seed=0..99`.
- Packet loss `p={0.00,0.10,...,0.90}`, independent per eligible receiving event, matching current P2-C sampling assumptions.
- Four rows per seed/loss: original native P2-C Proposed Method (1,000), original native CBAA (1,000), original native CBBA (1,000), and **new** Centralized Method (1,000). Total `4,000` method-cases / `40` groups; only `1,000` new method executions.
- Reuse the exact original `p2c_global_greedy_100seed.zip` source (ZIP SHA256 `f50068e4569771538f3083b8434bc91bce1f42bdec44e8feb74407be90682055`, executed Git `8038370205d586c697295b42eb255812be7aa88e`) and `p2_loss10_100seed.zip` original external baselines (ZIP SHA256 `1d08a167308b9368ee2a764737066223ac041a5bd6508621c7b6cd0320036bb9`, executed Git `f514cfa3613e7b0bad5c739d136b09fea8c3f92c`). Verify both original ZIPs, key uniqueness, scene hashes and stable method source SHA **before** reading any comparator row; only take P2-C Voting and original CBAA/CBBA rows.
- Preserve original P2-C report, original runner, plot, and source fields. P2D gets fresh result directory and distinct versioned experiment/reporting owners; never resume P2-C data into P2D.
- Keep original Rady-sampled application delays, stated hypothetical 144Mbps shared-medium timing, no claim of measured physical Wi-Fi.

## 3. Centralized Method: exact one-shot communication contract

The designated coordinator is fleet robot `0` (one ordinary capacity-one robot, not an external cost oracle).

1. **Task data:** use the same one-time externally announced TASK positions and the original physical framing as other methods. TASK is assumed delivered under the existing P2-C reliable-control-plane model.
2. **Local information:** each robot computes **its own** 100-task cost row. Coordinator 0 knows its own row locally. Robots 1..99 each send **exactly one** 816-byte Cost row **unicast to robot 0**. No Cost broadcast to other robots, no retries and no request-again messages.
3. **Loss/time:** physically schedule each of the 99 Cost SENDs using the existing causal network owner **before** applying one receiver-specific Bernoulli loss test. Failed or late physical SENDs still consume sender bytes, modeled shared-medium airtime, backoff and phase time. The initial Cost cutoff uses the existing guarded Cost phase budget; a packet arriving later is excluded from planning, never silently accepted.
4. **Information integrity:** build a central visible-row matrix **only from its own row and received-on-time rows**; do not query hidden rows from the original full scene. Call the actual existing `optimizer.solve_visible_batched_greedy_assignment` on that received matrix, then remap local row indices to physical robot IDs. Its ordering is `(cost, task_id, robot_id)`. No Hungarian optimizer, alternative auction, or missing-row fallback.
5. **Single terminal decision:** the coordinator emits **one actual sender-accounted** assignment publication; selected executors emit one individually accounted Commit each. As in P2-C, TASK, final decision and Commit are modeled as **one-shot reliable control messages**. No application-level retransmission is implemented or charged. This inherits the common P2 control-channel assumption; it is **not** proof that real wireless loss-free control can be achieved without an underlying reliability mechanism.
6. **No re-planning:** after this single decision phase, stop. Do not issue another Cost, Vote, Score, Commit or assignment attempt. Missing robot Cost rows cannot yield a 100/100 one-to-one assignment because that robot is unavailable to the planner.
7. **Completion:** `native_success=1` only with 100 unique one-to-one robot/task final Commits; partial assignments record assigned count and `native_success=0`. `native_stop_ms` includes actual modeled TASK, Cost deadline and emitted terminal control stages even in incomplete cases. Distinguish *stop time* from *time to full completion*.
8. **Fairness:** native CBAA/CBBA consensus rounds and Proposed batch-retry epochs remain original (they are part of those methods); this change adds **no retransmission or recovery** to Centralized Method. Same scenario/loss probability does not imply identical sender counts, guaranteed completion contract or communication exposure. Disclose these distinctions instead of calling them fully controlled channel-matched algorithms.

## 4. Explicit owners, named functions and diagnostics

The *new central method* owns exactly its own runtime in `democracy_mrta/centralized_method.py`:
- `validate_centralized_configuration` — data / inputs and one-shot protocol parameters.
- `collect_one_shot_cost_rows` — runtime / physical Cost emission, delivery cutoff, observed rows and sender-event ledger; existing `coordination._unicast_event`, `coordination._lossy_unicast_delivery`, `network.WifiCausalTimingSampler.sample_packet_ms` remain real packet/time owners.
- `plan_from_received_cost_rows` — planning / reuse the original Greedy optimizer only with actually received rows; never use the full hidden matrix.
- `publish_centralized_assignment` — runtime / one terminal assignment publication; no duplicate send.
- `emit_centralized_commits` — runtime / one commit per actual selected executor, original `protocol.validate_one_to_one_commits` safety boundary.
- `simulate_one_shot_centralized` — bounded single-iteration orchestration, result/clock/ledger, no duplicate state machine.

Read-only source provenance remains owned by `experiments.p2_baseline_reuse`: extend with a **named P2-C Voting source reader**, retain existing original CBAA/CBBA source gates, and never copy a second SHA validator into the new runner.

The *P2D experiment* uses a dedicated `experiments.run_p2d_centralized` owner with separate `validate_config`, `prepare_evidence`, `run_one_centralized_case`, `validate_complete_grid`, `summarize`, `write_evidence`, `main`. Experimental source identities and output schemas explicitly tag native algorithm sources, original Bernoulli loss model, sender traffic, phase-stop time and stop/completion contract.

The *new figure* is owned by `experiments.p2d_plot` with separate source validation and render functions; no mutation of P2-C published historical SVG.

Every important first failure must report `owner/function/category/code/expected/actual/details`; categories restricted to `data/time/state/dependency/planning/safety/runtime/contract`. Example diagnostic contracts to implement/test: `data/P2D_INVALID_GRID`, `contract/P2D_ARCHIVE_SOURCE_MISMATCH`, `contract/P2D_ZERO_LOSS_GREEDY_MISMATCH`, `contract/P2D_ONE_SHOT_SEND_COUNT_MISMATCH`, `contract/P2D_HIDDEN_COST_ROW_USED`, `time/P2D_STAGE_TIME_MISMATCH`, `safety/P2D_DUPLICATE_ASSIGNMENT`, `state/P2D_OUTPUT_EXISTS`.

## 5. Four primary graphs and explicit reference

- **A Native full completion (%)** versus packet loss. `Full-Info Baseline=100%` may be a thin black dashed ideal reference, marked as offline and not observed communication.
- **B Modeled native stop (s)** versus packet loss, all 100 seeds including failed/guard-stopped cases, logarithmic y; always label `stop`, never present incomplete-stop as successful allocation time.
- **C Attempted sender payload (kB)** versus packet loss, all physical application SENDs including all dropped Costs, logarithmic y.
- **D Assignment cost / Full-Information Global Greedy cost** versus packet loss, averaged over each method's **own natively complete trials**; provide `n` per point; missing success cohorts plot gaps rather than zero. On this panel, a **black dashed horizontal line at y=1.0** with label **Full-Info Baseline** is the deterministic, per-seed complete-information greedy reference. Full-Info is **not** a lower mathematical bound: a lossy greedy solution can occasionally have ratio below 1.0.
- Also report **task coverage (committed tasks / 100)** for Centralized Method in CSV and an optional supplemental plot so that one-shot central degradation is still visible as a graded quantity if full success collapses abruptly.
- Do not place a fictitious 0-second or 0-kB baseline in B/C.

## 6. Test-first acceptance, provenance and publication gates

1. **One-shot transport gate:** exactly 99 remote Cost physical SENDs, zero repeat requests/retries, same sender payload and positive radio airtime at p=0 and p=1 for an otherwise identical emission trace; p=1 leaves only robot-0's Cost row visible.
2. **0%-loss exactness:** for 100 paired seeds, 100/100 complete, match the independently calculated full-information Global Greedy physical robot/task pairs exactly; no Hungarian planning.
3. **Loss safety:** p=1 cannot fabricate unavailable cost rows or full completion; missing/late packets still incur transmission charges; partial commitments are one-to-one, physically received and explicitly incomplete.
4. **Isolation:** P2D reuses original P2-C Voting, CBAA and CBBA records **field-for-field**, source-SHA attested, and leaves Price Auction only in original P1/P2/P2-C evidence. Old runner behavior remains unchanged.
5. **Reporting:** exactly 10 × 100 × 4 groups' method-cases, 40 summary rows, valid Full-Info Greedy denominator per seed, unchanged original scene geometry/Cost. Quality missing for n=0, no fictitious successful time. Visual label `Centralized Method`; original figure unaffected.
6. **Execution plan:** focused unit tests, full repository unit tests, then user Mac no-loss 100-seed acceptance, then 1,000 new Centralized native cases only; package raw per-seed CSV, 40-row summary, SVG, manifest with the executed source SHA and SHA256 for independent audit. Do not assert a new 100-seed numerical result before these original Mac runs are complete.
7. **Documentation:** same bounded code change updates `docs/EXPERIMENT_PROTOCOL.md` with a new P2D section and `docs/CHANGE_CONTINUITY.md` recording owner/function, preserved/changed behavior, diagnostic boundary, residual risks, next step and Git commit SHA. Update README (and Chinese README) **only after** source audit verifies formal results.

## 7. Risks and interpretation

Without Cost retransmission, a centralized coordinator frequently lacks some of the 99 remote robot cost rows as soon as p>0, so a **steep collapse of full 100-task completion is expected**, not yet measured. This is an intentionally **one-shot centralized comparator**, not a universal upper bound on centralized architectures (real deployments can use acknowledgments, redundancy or fault-tolerant state replication). Proposed Voting, CBAA and CBBA have original native communication and termination contracts; this P2D chart compares them transparently under shared scenarios and loss parameters, not under strictly equal bytes/transmissions, and does not turn their distinct optimizers into identical algorithms.

The full-information dashed reference has no send traffic and no real observed time, so it is only a reference for completion and assignment-quality panels; the black line is not a fourth/fifth native packet-loss method.
