# Canonical Experiment Protocol

## 1. Research question

The paper studies a **leaderless fully decentralized communication and agreement protocol for multi-robot task allocation under unreliable wireless communication**.

The paper does **not** claim a new optimizer.

## 2. Fixed optimizer

All primary controlled methods use the same deterministic Hungarian implementation.

The allocation problem for one epoch is a static linear one-to-one assignment problem:

\[
X^*=\arg\min_X\sum_i\sum_j c_{ij}x_{ij}
\]

with

\[
\sum_jx_{ij}\le1,\qquad \sum_ix_{ij}=1.
\]

With a complete identical matrix and deterministic ordering/tie handling, every robot must compute the same optimal assignment.

## 3. Democracy protocol

For each allocation round:

1. the allocation epoch/task set is reliably disseminated;
2. each robot computes its own cost row;
3. each robot broadcasts its cost row once to the peer set;
4. robot \(i\) constructs local matrix \(\hat C_i\);
5. unknown/unreceived entries are explicitly represented as unavailable and never silently replaced by ground-truth data;
6. robot \(i\) runs Hungarian on its local feasible matrix;
7. each local assignment becomes one task-level vote per proposed robot;
8. votes are sent directly as unicasts to proposed executors;
9. task \(j\) commits to robot \(k\) only when robot \(k\) receives strict majority
   \[
   Q=\lfloor N/2\rfloor+1;
   \]
10. after quorum, the winner broadcasts one commit announcement for that task;
11. votes are unique by voter/task/round;
12. stale votes are rejected;
13. if the required assignment cannot be committed before timeout, the round fails and is retried.

## 4. Zero-loss correctness contract

At zero packet loss with complete information:

\[
\hat C_1=\hat C_2=\cdots=\hat C_N=C.
\]

Therefore:

\[
X_1=X_2=\cdots=X_N=X^*
\]

must hold.

Any nonzero optimality gap in this condition is a **contract failure**, not a performance result.

The earlier sequential per-task minimum-cost implementation is obsolete and is not the canonical paper algorithm.

## 5. Timing model

Primary empirical latency source:

M. Rady et al., “How does Wi-Fi 6 fare? An industrial outdoor robotic scenario,” Ad Hoc Networks 156, 103418, 2024, DOI 10.1016/j.adhoc.2024.103418.

The authors publish real ROS 2 application-delay observations. Their processed dataset exposes `control_delay_ms` and `control_loss` across locations and PHY configurations.

E1 pins the external evidence to:

- repository: `minarady1/wifi_for_industrial_robotics`
- commit: `1996e5bb69b9ba4d25060cbc14838ddedf65cff2`
- JSON Git blob: `11e70e685229cc26458f272b0c954487c87d7953`
- location 2: Medium range LoS (60 m)
- configuration: `ax_160mhz_6ghz` (Wi-Fi 6E ax/6/160)
- steady-state interval: 120–181 s

This pinned profile contains 121 finite ROS control-delay samples in the steady-state interval. The verified descriptive values are mean 33.593687 ms, P50 19.962509 ms, P95 64.149866 ms, P99 159.419021 ms, and maximum 531.535123 ms.

For controlled latency experiments, each successfully delivered protocol message receives an empirical latency sample:

\[
L_m\sim Bootstrap(D_{WiFi6}).
\]

Arrival:

\[
t_{arrival}=t_{send}+L_m.
\]

Packet-loss sweeps are injected independently from latency unless an experiment explicitly runs real trace replay.

## 6. Event-time accounting

The simulator must be discrete-event.

Do not estimate communication time as message count times mean latency.

Required timing boundaries:

- cost exchange start/end;
- local optimization start/end;
- vote send / arrival;
- quorum achieved time;
- commit send / arrival;
- timeout;
- retry start;
- final decision time.

For Democracy voting, quorum time is the arrival time of the Q-th valid vote.

Per run:

\[
T_{total}=T_{compute}+T_{communication}+T_{retry}.
\]

## 7. Primary controlled methods

- Ideal Full Information — reference.
- Leader-Hungarian.
- Flooding/Full-View Hungarian.
- Democracy-Hungarian — ours.

CBAA/ACBBA/DHBA are Related Work and possible secondary cross-method comparisons, not primary controlled baselines.

## 8. Formal experiment sequence

- E0: perfect-information correctness.
- E1: empirical Wi-Fi communication-time cost.
- E2: Bernoulli packet-loss robustness.
- E3: robot scalability.
- E4: task-load saturation.
- E5: Gilbert-Elliott burst loss.
- E6: message-type failure localization.
- E7: published real Wi-Fi trace replay.

## 9. Diagnostics

Allowed categories:

`data / time / state / dependency / planning / safety / runtime / contract`.

Timing-model failures belong to owner `network` / category `time` or `data` as appropriate.

Optimizer-input incompleteness must be explicit; missing costs must never be silently filled from ground truth.

## 10. Reproducibility

Every formal run stores:

- code commit SHA;
- source network dataset provenance and pinned revision;
- selected location / PHY profile;
- scenario seed;
- network sampling/replay seed;
- per-seed aggregate metrics;
- aggregate summary;
- raw per-message network event logs for designated audit seeds.

The full event stream is deterministic from the network seed and message key. Formal E1 defaults to preserving audit event logs for seed 0 while retaining aggregate metrics for all 100 seeds.


## 11. E1 zero-loss coordination timing semantics

E1 isolates latency cost; packet loss is disabled.

Primary methods:

1. **Ideal Full Information**: no network communication; reference only.
2. **Leader-Hungarian**: every non-leader unicasts one cost-row message to robot 0; the leader solves Hungarian and emits one logical wireless assignment broadcast.
3. **Full-View Hungarian**: every robot emits one logical wireless cost-row broadcast. At zero loss, every peer receives each broadcast and obtains a complete matrix.
4. **Democracy-Hungarian**: uses the same one-broadcast-per-robot cost exchange as Full-View in E1, then each robot independently forms the identical Hungarian proposal, sends task votes as direct unicasts to proposed executors, and each task winner emits one logical wireless commit broadcast after strict-majority quorum.

All network messages are concurrent discrete events. A phase completes from actual simulated arrival events, never from message count multiplied by mean latency.

For E1, one logical broadcast is counted as **one attempted wireless transmission and one payload copy**, not \(N-1\) unicasts. Because E1 has zero packet loss, one broadcast uses one trace-derived application-delay sample and becomes visible to all intended peers at that simulated arrival time. Receiver-specific loss/delivery semantics are intentionally deferred to E2.

For Democracy-Hungarian:

- robot \(i\)'s local matrix becomes ready after all required peer cost broadcasts have arrived;
- a self-vote is a zero-latency local event and is not counted as a network message;
- task quorum time is the arrival time of the \(Q\)-th valid vote;
- actionable decision time is the maximum task quorum time;
- global agreement time is the final required commit arrival.

E1 reports hardware-dependent Hungarian wall-clock time separately from trace-driven network waiting time; it does not serialize the computation of different robots, because robots are physically separate compute nodes.

The E1 empirical model does not claim to simulate additional fleet-size-dependent 802.11 MAC contention. That limitation must remain explicit. E3 may add a separately justified contention sensitivity model; no contention penalty may be invented silently.


## 12. E2 Bernoulli packet-loss semantics

E2 isolates **single-round packet-loss robustness**. It does not evaluate retry policy.

Loss sweep:

`p_loss ∈ {0, 0.1, 0.3, 0.5, 0.7, 0.9}`

The same pinned empirical latency profile as E1 is used for all successfully delivered transmissions.

### 12.1 Cost dissemination

Each robot always knows its own cost row.

Each logical cost-row broadcast is one attempted wireless transmission. For every peer receiver, delivery is sampled independently with Bernoulli probability:

`P(drop) = p_loss`

A dropped row remains absent from that receiver's local view. It must never be reconstructed, imputed, or copied from the ground-truth matrix.

If all expected peer rows arrive, a local view becomes ready at the final required arrival time. If one or more expected rows are missing, the receiver closes its cost phase at the fixed E2 phase timeout.

The phase timeout is the maximum measured delay in the pinned E1 profile:

`T_phase = 531.535123 ms`

This makes `p_loss = 0` timing-compatible with E1 while giving receivers a deterministic boundary at which absence becomes observable.

### 12.2 Partial local Hungarian optimization

For Democracy-Hungarian and Leader-Hungarian, the Hungarian optimizer receives only the robot rows visible to that decision maker.

If `K` robot rows are visible for `M` tasks, the local optimizer returns exactly

`min(K, M)`

one-to-one assignment pairs.

When `K < M`, the proposal is partial. No synthetic cost is inserted for hidden robots.

A Democracy voter casts votes only for the task pairs present in its own partial assignment. Tasks omitted by that local assignment are abstentions from that voter.

### 12.3 Voting and quorum

Votes are direct unicasts to proposed executors and use the same Bernoulli packet-loss probability `p_loss`.

The quorum denominator never shrinks with packet reception:

`Q = floor(N / 2) + 1`

A task commits only if one candidate receives at least `Q` distinct valid delivered votes.

No-quorum is an expected E2 outcome and produces a task timeout rather than an exception.

### 12.4 Commit reliability

Commit broadcasts remain reliable in E2.

This is intentional: cost loss and vote loss are the independent variables in E2. Commit loss can create duplicate-execution safety hazards and is therefore isolated for the later message-type failure experiment.

### 12.5 Controlled-method behavior

- **Ideal Full Information**: unaffected reference.
- **Leader-Hungarian**: the leader optimizes over its self row plus cost rows actually received. A partial leader assignment is allowed.
- **Full-View Hungarian**: succeeds only if every robot receives a complete matrix in that round. Otherwise the full-view coordination round times out.
- **Democracy-Hungarian**: every robot optimizes its own visible rows, casts votes from that partial proposal, and relies on strict-majority aggregation.

### 12.6 E2 metrics

Primary metrics:

- task commit rate;
- **correct executor rate (CER)**, defined as oracle-matching committed tasks divided by total tasks;
- **correctness among committed tasks**, defined as oracle-matching committed tasks divided by committed tasks;
- full-assignment success rate;
- optimal-solution rate;
- optimality gap among full successful assignments;
- task timeout rate;
- decision completion time;
- global agreement time;
- logical transmission count;
- logical payload bytes;
- lossy delivery opportunities / delivered / dropped;
- mean visible robot rows;
- safety failures.

Retry count is fixed to zero in E2.

### 12.7 Correctness boundaries

At `p_loss = 0`:

- all methods must have task commit rate 1;
- all methods must have full-assignment success 1;
- all methods must have zero optimality gap;
- Democracy timing/message behavior must reduce to the E1 zero-loss implementation.

At every loss level:

- quorum denominator remains fixed at `N`;
- no duplicate robot/task commit is permitted;
- safety failures must remain zero.

E2 assumes independent receiver-level Bernoulli delivery. Correlated burst loss is not modeled here; that is reserved for E5.


### 12.8 Correct-executor metrics

Let the deterministic complete-information Hungarian oracle assign task (j) to robot (r_j^*).

For an evaluated method, if task (j) is committed to robot (hat r_j), that commit is correct iff:

[
hat r_j = r_j^*.
]

The **Correct Executor Rate (CER)** is:

[
CER = rac{#{	ext{correct committed tasks}}}{N_T}.
]

This metric penalizes both wrong commits and uncommitted tasks.

The conditional **correctness among committed tasks** is:

[
C_{commit}
=
rac{#{	ext{correct committed tasks}}}
{#{	ext{committed tasks}}}.
]

If no task is committed, (C_{commit}) is undefined and is reported as NaN.

These metrics are required for E2 because full-assignment success alone can hide assignment-quality degradation. A method may assign every task while selecting executors that differ substantially from the complete-information Hungarian oracle.


## 12.9 E2 vote provenance and forensic acceptance gate

The formal 100-seed E2 result is **under audit**, not yet paper-accepted.
The observed 100R/50T at p_cost=p_vote=0.30 has:
- mean visible cost rows = 70.285 of 100;
- task commit rate = 0.1522;
- correct executor rate = 0.1506;
- correctness among committed = 0.98706.

These aggregate values do not determine the fraction of raw ballots matching the full-information Hungarian oracle, or whether quorum failure was caused by proposal disagreement versus vote transport loss.

The forensic audit must reuse **the same coordination state machine and same keyed network samplers**, not an independently reimplemented vote collector. It captures read-only:
- local visible robot rows by voter;
- actual local Hungarian proposal by voter, including non-network self-votes;
- final counted task/candidate vote ledger.

The audit checks that:
1. each voter local view equals its delivered cost rows plus its own row;
2. each proposed non-self vote has exactly one unicast delivery observation;
3. reconstructed delivered+self-votes equal the actual protocol counted ledgers;
4. majority reconstruction equals committed task winners;
5. audit capture does not alter protocol events, decisions, or timing.

Required outputs:
- per-voter visible-row count and raw/delivered oracle-matching ballots;
- per-task raw oracle support and raw top-candidate support;
- per-task delivered oracle support and delivered top-candidate support;
- per-task candidate raw/delivered vote counts;
- rates for (a) no majority before vote loss, (b) majority lost during vote transport, and (c) majority actually committed.

The independent Bernoulli cost/vote losses are unchanged. Cost loss of 30% does NOT imply exactly 30% incorrect local Hungarian proposals.

Audit command:

    python3 -m experiments.audit_e2_votes --robots 100 --tasks 50 --p-loss 0.3 --seeds 100

The change is instrumentation-only. Until the audit and its regression tests pass, E2's 30%-loss robustness claim is not considered validated.

The selected forensic seed also exports individual ballots, one row per voter/task
proposal: voter_id, task_id, candidate_id, oracle_robot, oracle_match,
local_visible_rows, is_self_vote, transport_delivered, transport_dropped.
This ballot table includes local self-votes that were not present in the previous
network-only event log. The output is audit evidence, not a second vote ledger.


## 12.10 Controlled E2 cost-information-loss sweep

The E2 loss sampler continues to use distinct deterministic Bernoulli packet keys for cost-row reception and vote transport.

To isolate **local-information loss**, vary the probability of *receiving a peer cost row* while fixing the vote-packet delivery loss to zero:

- `p_cost_loss = p` independently for each sender-to-receiver cost-row delivery, with each robot always retaining its own row;
- `p_vote_loss = 0` for each remote vote;
- reliable task announcement and commit as before;
- unchanged partial-row Hungarian, strict majority and no retry.

The `experiments.run_e2` CLI option `--loss-probabilities` still controls the cost-delivery loss sweep. New optional `--vote-loss-probability VALUE` fixes Democracy's vote-transport packet loss independently for the entire sweep.

**Backward-compatibility contract:** if `--vote-loss-probability` is omitted, Democracy keeps the prior `p_vote_loss = p_cost_loss` for each point. When set to `0`, cost loss alone is tested. Leader/Full-View methods do not transmit Democracy votes, so this vote override does not change their behavior.

The legacy raw/summary/events field `p_loss` identifies cost loss. The additional `p_vote_loss` field records the effective vote loss at each point, including the original default two-stage experiment. Audit and per-seed event records continue to be paired by the same seeds. Use a distinct `--output-root` for this ablation to avoid replacing formal E2 summaries.

Suggested initial analysis: fixed 100 robots / 50 tasks, 100 paired scenario/network seeds, cost loss 0% to 70% at 2-percentage-point increments, vote loss fixed 0%. Report task commit, CER and all-tasks global-optimal solution rates separately. A claimed `unusable` transition requires a stated operational criterion; for inspection one may report the first sampled loss level where task commit falls below 90%, 50% and 10%, without treating those as predefined success standards.

This sweep remains single-round and does not quantify eventual completion under retries.


## 13. Sequential Greedy voting with executor retirement (new opt-in experiment)

**Scope:** This protocol replaces Hungarian **in the new retiring-executor experiment only**. Existing E0/E1/E2 single-round Hungarian experiments and their historical results remain unchanged. The previous `simulate_democracy_hungarian_retirement` strategy remains accessible for backwards compatibility when explicitly called with `voting_strategy="hungarian"`, but the `experiments.run_e2_retirement` runner now always selects `voting_strategy="greedy_task"` and reports `democracy_greedy_retirement`.

### 13.1 Data exchange happens exactly once

For an initial N-robot, T-task static cost matrix, each robot keeps its own row and broadcasts **its complete T-task cost row once**. Each peer independently receives or loses that message with Bernoulli Cost Loss `p_cost_loss`. The result is one voter-specific local visible-robot-row set. Unknown rows remain unknown for the entire allocation run, never imputed from global truth and never retransmitted or resampled in later voting rounds.

Later rounds filter these persistent views to remove robots that have already committed; every voter still retains its own active row. These **static** views are appropriate to the present static-cost experiment. Dynamic robot locations, stale costs, or cost changes would require a separately defined refresh policy.

### 13.2 Greedy vote for ONE task per epoch

Maintain:
- `A_k`: frozen set of active, unassigned robot IDs at epoch k;
- `P_k`: ordered queue of uncommitted task IDs;
- `C_k`: already committed one-to-one assignments;
- an epoch ID (strictly increasing).

For the head task `t=P_k[0]`, each active robot i independently votes for:

    candidate(i,t) = argmin [ (cost[r,t], original_robot_id[r]) ]
                     over r in (i's visible rows intersection A_k)

Each voter always sees its own row, so at least one candidate exists. This greedy selection **does not call Hungarian** and **does not optimize or reserve other tasks**. Equal costs use the lowest original robot ID. It is an O(number-of-visible-active-robots) local scan per task.

Each voter casts **one** task-specific vote to its chosen executor. A self-vote is local and does not use wireless transmission; other votes are direct unicasts whose delivery is separately sampled by Bernoulli Vote Loss `p_vote_loss`.

The current epoch's strict majority is frozen:

    Q_k = floor(|A_k| / 2) + 1

The candidate receives the task only when at least Q_k distinct valid votes arrive. Duplicate, ineligible and stale votes continue to be rejected by the original `protocol.record_vote`; the existing `find_unique_majority` still resolves exactly one winner.

### 13.3 Commit, exit, and failed-task queue

Upon quorum, the winning executor broadcasts a **reliable commit announcement** before the next epoch. The committed task is removed from P, and the committed robot is removed from both the voter and candidate sets. It is treated as busy executing and does not participate again in this allocation run. The next task is then selected from the remaining queue, with a new Q based on the smaller active electorate.

If no candidate achieves quorum before the timeout, **no robot is retired**. The failed task moves from the queue head to its tail, and the next epoch votes on the next queued task. With only one task left, the task stays at the head for retry. New epoch IDs ensure vote transmissions and latency have distinct keyed samples. **Cost rows are not retransmitted**; only new votes can be retransmitted, and changed membership may alter the selection.

Both cases transition through the single existing owner `protocol.apply_announced_retirement_commits`, now with optional `attempted_task_id` for task-queue rotation. All voting remains in the single existing `coordination.simulate_democracy_hungarian_lossy` owner with `voting_strategy="greedy_task"`, rather than a second majority collector.

A fixed max-round limit counts **task-voting attempts, not entire 50-task allocation passes**. At least T rounds are needed to commit T tasks without any failures. For 100R/50T use `max_rounds=100` initially (50 tasks + up to 50 failed attempts) and separately report cost and failure rates. No unlimited retry.

### 13.4 Stable original identities and time

Robot/task physical IDs never change when compact active matrices shrink. Proposal IDs, packet loss keys, vote ledgers and final assignments use original IDs. A reliable commit is completed before the next round starts, and the current round's voter count is fixed until then.

The initial whole-row cost exchange follows the same original 0th-epoch E2 loss and latency keys, now with a payload sized for **all tasks**. Subsequent epochs have **no cost exchange**. Vote/commit keys include each new epoch ID; round-zero legacy keys are unchanged.

The simulator sums round-relative quorum/timeout/commit event times into elapsed assignment decision time. It **does not** simulate physical robot task motion, task-execution duration, robot rejoining, packet loss on commits, or MAC contention.

### 13.5 Comparisons, metrics, and correctness

The experiment saves a separate result family:

- method: `democracy_greedy_retirement`;
- raw rows with code SHA, seed, T, N, cost/vote loss and max-rounds;
- per-round active population, queue, attempted task, quorum, commit and time;
- a designated seed-0 per-message and per-delivery log;
- final summary by paired seeds and loss.

Two offline references MUST be kept distinct:

1. **Full-information sequential Greedy reference** (same ascending task order and no drop). Used to measure `greedy_correct_executor_rate`, `greedy_gap_percent_successful`. Zero-loss greedy voting must reproduce this reference.
2. **Full-information Hungarian global optimum** (evaluation oracle only; **never used for voter decisions**). Used to measure the legacy CER, `optimal_solution_rate`, and `optimality_gap_percent_successful`.

At zero loss, full task coverage and 100% match to the sequential Greedy reference are expected, but **zero global Hungarian gap is NOT expected or required**. An irreversible Greedy sequence can have much higher total cost than global Hungarian.

Only if all tasks commit do total-cost gaps have a valid same-task-set denominator. For incomplete allocations, report task commit rate, Greedy-reference correctness, Hungarian-reference CER, and rounds/time/message cost; the partial cost sum is not a global optimality gap.

With sequential Greedy, `first_task_vote_success` measures only the first attempted task; it MUST NOT be labeled as the original E2 full-set first-round task commit rate. Comparing an end-to-end multi-round success rate with single-round E2 directly is an **intervention comparison**, not a like-for-like one-round packet-loss robustness claim.

### 13.6 Commands and initial acceptance

```bash
git pull
python3 -m unittest discover -s tests -v
python3 -m experiments.run_e2_retirement --robots 100 --tasks 50 --seeds 3 --cost-loss-probabilities 0,0.3,0.5 --vote-loss-probability 0 --max-rounds 100 --output-root results/e2_greedy_retirement_smoke
python3 -m experiments.run_e2_retirement --robots 100 --tasks 50 --seeds 100 --vote-loss-probability 0 --max-rounds 100 --output-root results/e2_greedy_retirement_100r50t
```

The formal sweep defaults to Cost Loss 0%–70% in 2-point increments; Vote Loss fixed at 0%. The old E2 output roots remain untouched. New results are NOT paper-accepted until all local tests and the first smoke establish correct voter exit, task-order rotation, stable physical IDs, no duplicate commits, no repeated cost broadcasts, and correct Greedy-vs-global-cost metrics.



### 13.7 Full Vote Loss benchmark (independent channel sensitivity)

Formal extension to the same sequential Greedy + committed-executor retirement **without changing the protocol**. Each active voter selects one cheapest visible active candidate for one pending task. The vote is a direct unicast and its loss probability may differ from the single initial cost-row exchange loss probability.

- Cost-row delivery: independent per sender/receiver, with probability p_cost_loss; each robot retains its own row.
- Vote unicast delivery: independent packet event with probability p_vote_loss. **Self-votes have no wireless transport and cannot be dropped by this parameter.**
- Reliable commit announcements and strict-majority voting over all currently unassigned/active robots are unchanged.
- A new task-voting epoch retries with distinct round keys; no cost-row rebroadcast or ground-truth imputation is permitted.
- Failed tasks move to the pending queue tail, and a successful executor retires before the next round.
- Max 100 **task-voting attempts** for 100R/50T; partial allocations remain partial and cost gaps must be NaN unless all tasks commit.

All curves use 100 robots, 50 tasks and the **same 100 scenario and network seeds**. Loss levels for line curves are 0.00–0.70 in steps of 0.02 (36 points). Required independent experiments:

| Identifier | p_cost_loss | p_vote_loss | Question | Output root |
|---|---|---|---|---|
| COST_ONLY (existing) | sweep 0–70% | fixed 0 | Fragility of voters' incomplete cost information | results/e2_greedy_retirement_100r50t |
| VOTE_ONLY | fixed 0 | sweep 0–70% | Pure vote-channel packet loss under consistent cost views | results/e2_vote_only_100r50t |
| COST30_VOTE_SWEEP | fixed 30% | sweep 0–70% | Additional vote loss under the previously selected 30% cost-row loss | results/e2_cost30_vote_sweep_100r50t |
| JOINT_DIAGONAL | sweep 0–70% | equal numeric percentage to cost loss at each point | Joint end-to-end sensitivity; cost/vote packet draws still independent | results/e2_joint_loss_diagonal_100r50t |

For a coarse **two-dimensional interaction surface**, optionally also run a full grid with each probability in {0.0,0.1,0.2,0.3,0.4,0.5,0.6,0.7}: 8*8 = 64 cells, 100 seeds each, in results/e2_joint_loss_grid_100r50t. This optional grid measures interactions; do not accidentally substitute a 36*36 full-factorial sweep (129,600 seed-condition simulations) without an explicit compute and storage budget.

The experiment CLI supports:
- `--vote-loss-probability 0.3`: existing fixed Vote Loss behavior (unchanged);
- `--vote-loss-probabilities 0,0.02,...`: NEW Vote Loss axis independent of the Cost Loss axis (mutually exclusive with fixed Vote Loss);
- `--loss-pairing grid`: Cartesian product of the two loss axes (default; also used for a single fixed cost level);
- `--loss-pairing diagonal`: one pair for each loss level, **requiring exactly identical cost and vote axes**. Without a Vote Loss axis the implementation uses the Cost Loss axis automatically; a simultaneous fixed Vote Loss is rejected.
- Missing axes, duplicate pairs, invalid probabilities and mismatched diagonal axes MUST fail with explicit diagnostic codes before running simulations.

Outputs continue to include `p_cost_loss` and `p_vote_loss` separately on raw/round/event and summary rows; the raw rows include paired seed, git SHA, timestamp, and the method `democracy_greedy_retirement`. Additionally report:
- `cost_packet_attempts`, `cost_packet_dropped`, `observed_cost_drop_rate` for actual cost deliveries in the initial epoch;
- `remote_vote_attempts`, `remote_vote_dropped`, `observed_vote_drop_rate`, `self_votes` for actual vote packets, excluding self-votes from the wireless Vote Loss denominator;
- `quorum_failed_attempts`, mean rounds/elapsed time, final task commit rate and full 50-task success rate;
- Greedy-oracle executor correctness, global Hungarian-oracle executor correctness, and **complete-assignment only** cost gap to both full-information references.

In aggregate summaries, observed packet-loss rate is **the number of dropped packets divided by attempted packets across all seeds at that condition** (not an unweighted average of per-seed loss rates). Cost and Vote Loss counts plus delivery counts must reconcile exactly with the underlying coordination observations, otherwise fail with a diagnostic.

The core figure should show `mean_task_commit_rate`, `full_assignment_success_rate`, `mean_greedy_correct_executor_rate` versus `p_vote_loss` separately for VOTE_ONLY and COST30_VOTE_SWEEP, plus a JOINT_DIAGONAL curve. Plot mean rounds, mean elapsed time, and vote drop audit as separate supporting panels. Do not label Hungarian-based CER as Greedy reference accuracy.

Do NOT conclude "30% loss is safe" from a Vote Loss-only curve with 0% Cost Loss, or from task commit rate alone. Under 100 voting attempts there is a material difference between a single task reaching quorum and all 50 tasks completing. The user must inspect full-task success and cost among completed runs.

All tests for these new sweep parameters and stage delivery accounting must pass before claiming the formal Vote Loss results were validated. The earlier 62-unit-test pass and Cost-only 100-seed scan occurred **before** this new experiment-axis code change.

### 13.8 Vote Loss reproducibility commands

After pulling and running unit tests, begin with a 3-seed two-axis smoke (cost 0/30%, vote 0/30/70%); then run three separated 100-seed sweeps:

```bash
python3 -m experiments.run_e2_retirement --robots 100 --tasks 50 --seeds 3 --cost-loss-probabilities 0,0.30 --vote-loss-probabilities 0,0.30,0.70 --max-rounds 100 --output-root results/e2_vote_loss_smoke

LEVELS="$(python3 -c 'print(",".join(f"{i/100:.2f}" for i in range(0, 71, 2)))')"
python3 -m experiments.run_e2_retirement --robots 100 --tasks 50 --seeds 100 --cost-loss-probabilities 0 --vote-loss-probabilities "$LEVELS" --max-rounds 100 --output-root results/e2_vote_only_100r50t
python3 -m experiments.run_e2_retirement --robots 100 --tasks 50 --seeds 100 --cost-loss-probabilities 0.30 --vote-loss-probabilities "$LEVELS" --max-rounds 100 --output-root results/e2_cost30_vote_sweep_100r50t
python3 -m experiments.run_e2_retirement --robots 100 --tasks 50 --seeds 100 --cost-loss-probabilities "$LEVELS" --loss-pairing diagonal --max-rounds 100 --output-root results/e2_joint_loss_diagonal_100r50t
```

Optional 8x8 grid:

```bash
GRID="0,0.10,0.20,0.30,0.40,0.50,0.60,0.70"
python3 -m experiments.run_e2_retirement --robots 100 --tasks 50 --seeds 100 --cost-loss-probabilities "$GRID" --vote-loss-probabilities "$GRID" --max-rounds 100 --output-root results/e2_joint_loss_grid_100r50t
```

Separate output roots are REQUIRED to prevent overwriting the prior 100-seed Cost-only evidence and to preserve condition-specific summary.csv files. The experiment prints condition count before running, which must equal 6 for smoke, 36 for each line sweep, and 64 for the optional interaction grid.


## 14. E2 Greedy 25%-Announcement Plurality — NO fallback

### 14.1 User-authorized decision rule

The sole new voting mode is quarter_plurality. The former quarter_plurality_fallback was **removed at the user's explicit request on 2026-10-10**. A programmatic request for the removed rule must fail at coordination.validate_vote_decision_rule / contract / REMOVED_PLURALITY_FALLBACK_RULE, never silently alias to another algorithm. Historical fallback results remain archived and cannot be used as evidence of the new no-fallback algorithm.

For each task, use a **frozen** active electorate A of N currently unassigned robots. Each robot independently chooses the least-cost active executor in its own retained local Cost view. Every voter casts a single task ballot, with Vote Loss affecting only remote unicasts; its own ballot is local and reliable. Cost rows were broadcast only once and are not refreshed.

A candidate can reliably announce its actual FINAL counted votes only when its count is STRICTLY greater than 25% of the full eligible electorate:

    announcement_threshold = floor(N/4) + 1

Examples: N=100 requires 26 votes; N=99 requires 25 votes; N=4 requires 2; N=2 requires 1. The denominator is never the number of delivered votes. Recalculate the threshold only between completed task-voting epochs, after successful committed executors retire.

At the existing vote-collection deadline, each qualified candidate broadcasts its own final score with original robot/task IDs and round ID. Qualified score announcements (and subsequent commit announcements) are reliable in this simulator, and their message count, bytes and latency are charged. Everyone selects highest announced score, ties resolved by smallest original robot ID. ONE selected executor commits and is removed from future voter/candidate sets. Other robots remain eligible.

### 14.2 If nobody exceeds 25%, nobody wins

**No fallback, self-claim, self-election, provisional victory, or alternate selection is allowed.** With zero qualified candidates:
- zero score announcements and zero commit broadcasts for that task;
- zero executors retire, and the task is NOT assigned;
- the existing protocol.apply_announced_retirement_commits state owner rotates the failed task to the tail of the pending queue;
- the next task-voting attempt has a new round ID and new independent Vote Loss packet samples but unchanged incomplete Cost rows;
- if max_rounds is reached, all remaining tasks are explicitly incomplete.

This is a normal failed vote attempt, not a safety exception. protocol.resolve_unique_plurality_claims returns None for empty qualified announcements. coordination.simulate_quarter_plurality_announcement_phase then returns no event and no winner. The same coordination.simulate_democracy_hungarian_lossy owner handles the resulting task timeout; no second vote collector or new state machine is created.

In a tiny active electorate (e.g. two robots), one self-vote can genuinely satisfy the strict 25% threshold. That is a qualified announcement, NOT a fallback. The rule does not guarantee minimum global assignment cost even with zero packet loss.

### 14.3 Owners and first-failure contract

- protocol.quarter_vote_announcement_threshold: validates electorate size; computes strictly-greater-than-25% integer threshold.
- protocol.resolve_unique_plurality_claims: validates original robot IDs, vote counts, uniqueness and threshold, then uniquely resolves announced candidates or returns None.
- coordination.validate_vote_decision_rule: accepts strict_majority (unchanged default) or quarter_plurality for a single Greedy task; rejects removed quarter_plurality_fallback with REMOVED_PLURALITY_FALLBACK_RULE.
- coordination.build_quarter_plurality_claims: reads only counted candidate-local ledgers and returns ZERO or more qualified announcements.
- coordination.simulate_quarter_plurality_announcement_phase: broadcasts ONLY qualified score announcements after vote collection; if none qualify, emits no message or commit.
- coordination.simulate_democracy_hungarian_lossy: unchanged owner of vote transport/ledgers, now correctly treats an absent plurality result as a noncommit timeout. Original strict-majority behavior remains its default.
- protocol.apply_announced_retirement_commits: single owner of task rotation and successfully committed robot retirement, unchanged.
- coordination.simulate_democracy_hungarian_retirement: bounded round scheduler and stable physical IDs. New method name is democracy_greedy_quarter_plurality_retirement.
- experiments.run_e2_retirement.retirement_plurality_diagnostics: reports qualified-announcement/commit counts, **no-qualified attempts** and winner scores. Missing qualified announcements MUST match a failed attempt (PLURALITY_ANNOUNCEMENT_COMMIT_MISMATCH, category contract). No fallback metrics/transport phase exist in the new schema.

Reliable score announcements remain an explicit assumption and are not exposed to Cost/Vote Loss. It must not be claimed that the system tolerates loss of these control messages, which would require its own protocol.

### 14.4 Paired formal no-fallback experiment

Historical evidence MUST remain unchanged:
- strict-majority Greedy: results/e2_joint_loss_diagonal_100r50t;
- the now-rejected fallback-based experiment: results/e2_greedy_quarter_plurality_100r50t.

New no-fallback output root: results/e2_greedy_quarter_plurality_no_fallback_100r50t.

Run with 100 Robots / 50 Tasks, seeds 0..99, 100 seeds per point, 100 maximum INDIVIDUAL task-voting attempts, p_cost_loss = p_vote_loss (numerically equal probability, independent packet draws), 0%–70% every 2% (36 conditions, 3,600 paired runs). Keep existing local Greedy, one initial lossy Cost exchange, same Rady Wi-Fi latency sampling, task ordering and commit/retirement. Do not overwrite the old majority or archived fallback summary CSV files.

Output raw per-seed and per-round CSV, designated seed-0 message/delivery audits and summary.csv. Report committed tasks, full 50-task success, Greedy CER, external Hungarian CER, total-cost gap only if ALL tasks commit, failed/no-qualified attempts, announced score counts, winning score, tie count, mean task attempts, simulated coordination latency, traffic bytes/messages and observed physical Cost/Vote drop rates. Incomplete tasks MUST NOT be replaced by forced or fake successes.

### 14.5 Reproducibility

After git pull and full unit tests, first smoke with 3 seeds and equal Cost/Vote Loss of 0%, 30%, 70%:

    python3 -m experiments.run_e2_retirement --robots 100 --tasks 50 --seeds 3 --cost-loss-probabilities 0,0.30,0.70 --loss-pairing diagonal --max-rounds 100 --vote-decision-rule quarter_plurality --output-root results/e2_greedy_quarter_plurality_no_fallback_smoke

Only if tests/smoke pass, run formal 100-seed sweep in the same shell:

    LEVELS="$(python3 -c 'print(",".join(f"{i/100:.2f}" for i in range(0, 71, 2)))')"
    python3 -m experiments.run_e2_retirement --robots 100 --tasks 50 --seeds 100 --cost-loss-probabilities "$LEVELS" --loss-pairing diagonal --max-rounds 100 --vote-decision-rule quarter_plurality --output-root results/e2_greedy_quarter_plurality_no_fallback_100r50t

Acceptance checks: no fallback event phases, no commit without a qualifying announcement, failed attempts rotate tasks without retiring any robot, zero-loss matches full-information sequential Greedy, zero duplicate assignments, all actual loss probabilities as configured, and new SHA/seeds/evidence saved separately. The new code/tests are committed but the NEW suite and formal no-fallback run remain pending local execution.


## 15. E3/E4 — Robot/task scaling (maximum 100 robots, up to 1:1)

### 15.1 Experiment matrix and unchanged voting

This experiment implements the user's requested maximum fleet size 100, with no more tasks than robots (one-to-one maximum task load). It supersedes the earlier planned 200-robot E3 point in README for this primary study, without changing any E2 protocol behavior.

Use the following primary factorial grid:
- Robot counts R: 10, 20, 40, 60, 80, 100.
- Target task-load ratios T/R: 0.10, 0.25, 0.50, 0.75, 1.00.
- Convert fractional T using ROUND HALF UP: T=floor(R*target_ratio+0.5), enforce 1 <= T <= R, and always report the actual resulting T/R.
- R=10: tasks 1,3,5,8,10; R=20: 2,5,10,15,20; R=40: 4,10,20,30,40; R=60: 6,15,30,45,60; R=80: 8,20,40,60,80; R=100: 10,25,50,75,100.
- 30 unique size cells, including the previous 100R/50T reference and requested 100R/100T full load.
- The full set of all integer 1<=T<=R<=100 would contain 5,050 size cells. Use this structured representative grid instead; full dense enumeration is explicitly out of scope.

The ONLY voting method in the scaling experiment is the existing PURE quarter_plurality rule: each active robot independently casts one Greedy vote using its locally retained incomplete Cost rows, strictly more than 25% of the entire active electorate must be received before a candidate can announce, highest score among qualified announcements wins with global robot ID tie-break, and successful executors retire. If no one qualifies, no one commits, and the task rotates to the tail of the existing pending queue. No self-claim, fallback message, alternate winner selection or new state machine.

### 15.2 Fair controlled conditions

For each R/T cell test two conditions:
- 0% Cost Loss AND 0% Vote Loss (control).
- 30% Cost Loss AND 30% Vote Loss (primary packet-loss condition).

Cost and Vote stage physical packets are independently sampled at the same numerical loss probability. As before, only the initial Cost exchange is lossy; candidate final-score announcements and commits remain modeled as reliable and incur explicit communication time and payload bytes. Use the existing Rady Wi-Fi latency dataset, unchanged greedy cost model, scenario generation and network seed scheme. Each cell uses the same seed and static cost scene under both 0% and 30% loss, but distinct R/T cells represent distinct generated scenes even with matching integer seeds. The geometry continues to be a 100x100 Euclidean world and spatial density therefore changes when the robot count changes.

100 seeds per size cell per loss condition: 30 x 2 x 100 = 6,000 seed-condition runs.

**Attempt budget must depend on T.** A fixed 100 rounds would make 100R/100T unable to complete all tasks after even one failed voting attempt. Therefore use max_rounds = 2*T for every grid cell, giving exactly one failed-attempt allowance per task (and two attempts for T=1). This matches the previous 100R/50T max-rounds=100 baseline. Raw total rounds, no-qualified failures and attempts per requested task must all be reported; 1:1 successes should not be evaluated with a secretly smaller retry ratio.

Report: per-task completion and full T-task success; correct-executor rate against full-information sequential Greedy and the offline Hungarian optimum; total-cost gap only for fully completed assignments (NaN otherwise); mean voting attempts; time/messages/bytes both absolute and PER REQUESTED TASK; Cost/Vote observed physical drop rates; actual load ratio, R, T, method, SHA, seeds and zero safety errors. A final remaining robot may be forced into a costly last task even if the overall assignment completes. Thus global gap remains a critical metric at 1:1.

### 15.3 New scaling owner and evidence boundaries

New sole experiment-dimension owner: experiments.run_e3_e4_scaling. It MUST reuse experiments.run_e2_retirement.run_retirement_experiment for every (R,T) cell. It MUST NOT introduce a second vote ledger, state machine, network sampler, optimizer or altered quorum.

Named functions by responsibility:
- validate_scaling_axes: validate ordered/distinct robot counts, ratios, loss levels, seeds, round factor. Fail when R>100 or ratios exceed 1.
- build_scaling_cells: deterministic round-half-up conversion, prevent tasks exceeding active robots and prevent duplicated integer task counts from ratio rounding.
- make_scaling_plan: immutable source SHA, grid, seed, dataset and packet/attempt policy metadata.
- prepare_scaling_output: reject output reuse unless explicitly resumed with exactly the same plan and git SHA.
- read_completed_scaling_cell: require existing raw per-seed rows, per-round CSV, per-seed-zero message audit and summary; validate method/rule/R/T/seed-loss pair/SHA/round cap before reusing any previous cell.
- build_scaling_aggregate_rows: preserve original E2 per-cell summary metrics and add actual vs planned load ratios and attempts/time/messages/bytes PER REQUESTED TASK.
- run_scaling_benchmark: execute each unique cell via existing E2 experiment owner, append complete verified rows to the root summary after each cell, and support safe resume without overwriting incomplete evidence.
- main: fixed 100-R ceiling and configurable levels/ratios/loss/seeds/output root; no change to earlier E2 CLI.

Critical diagnostic codes: INVALID_SCALING_ROBOT_LEVELS, INVALID_SCALING_LOAD_RATIOS, INVALID_SCALING_LOSS_LEVELS, INVALID_SCALING_SEEDS, INVALID_SCALING_ATTEMPT_MULTIPLIER, SCALING_TASK_COUNT_OUT_OF_RANGE, SCALING_DUPLICATE_TASK_CELL, SCALING_OUTPUT_ALREADY_EXISTS, SCALING_UNMANAGED_OUTPUT_ROOT, SCALING_RESUME_PLAN_MISMATCH, SCALING_CELL_EVIDENCE_INCOMPLETE, SCALING_CELL_PROVENANCE_MISMATCH, SCALING_PARTIAL_CELL_REQUIRES_MANUAL_REVIEW. All use a structured owner/function/category and expected/actual/details; run-level protocol failures continue to come from the existing actual owners.

### 15.4 Output and commands

The new root is results/e3_e4_scaling_100robot_cap with benchmark_plan.json, cells/R###_T###/summary.csv, per-cell raw/round/event files, and an aggregated summary.csv with one row per (R,T,loss) condition (expected 60 rows). This root must never overwrite E2 majority or pure 25% previous results. Aborted runs can be resumed using --resume with an IDENTICAL grid, git SHA, seed count, dataset, attempt factor and verified existing cell files. Incomplete partially written cells require explicit inspection/moving aside; no silent overwrites.

User Mac preflight:

    git pull
    python3 -m unittest discover -s tests -v
    python3 -m experiments.run_e3_e4_scaling --robot-levels 10,100 --load-ratios 0.5,1.0 --loss-probabilities 0,0.30 --seeds 3 --attempts-per-task 2 --output-root results/e3_e4_scaling_smoke_100cap

Expect 4 unique size cells x 2 losses x 3 seeds = 24 seed-condition simulations.

Formal default:

    python3 -m experiments.run_e3_e4_scaling --seeds 100 --output-root results/e3_e4_scaling_100robot_cap

Expect 30 cells x 2 losses x 100 seeds = 6,000 runs. On interruption, repeat the identical command with --resume. Compare the 100R/50T 30% cell against the previously validated standalone E2 result, with matching method, seed set and max_rounds=100.

The earlier 89/89 tests and 3,600-run E2 no-fallback curve were verified by the user on a PRE-scaling commit. New scaling tests and full formal scaling runs are pending Mac execution and may NOT be presented as completed results.


## 16. Greedy-only communication comparison: fixed optimizer, varying packet loss and vote rule

### 16.1 Research question and explicit scope

The user explicitly chose **communication robustness and decentralized coordination**, NOT global multi-task optimization, as the contribution of the study. The experimental objective is to quantify performance loss induced by Cost/Vote packet loss, with local Sequential Greedy held fixed, and to compare the **51% strict-majority communication protocol** with the **pure, no-fallback >25% final-score-announcement protocol**.

No Hungarian solver, global-optimum reference, additional greedy planner, new task scheduler, or new packet transport is needed in this DERIVED REPORT. Previously generated Hungarian raw/oracle fields are preserved as historical evidence in their original E2 files; this analysis ignores those columns entirely and does not modify or delete any old data. Do not conflate this with an algorithmic claim of global optimality.

The experiment is evidence-only: consume the two completed and separately stored **100R/50T, 100-seed, max_rounds=100, Cost Loss = Vote Loss 0..70% step2%** E2 raw CSVs (not just rounded summary curves):

- source A, majority: results/e2_joint_loss_diagonal_100r50t/raw/retirement_*.csv; method=democracy_greedy_retirement; voting rule=strict_majority;
- source B, current pure 25%: results/e2_greedy_quarter_plurality_no_fallback_100r50t/raw/retirement_*.csv; method=democracy_greedy_quarter_plurality_retirement; voting rule=quarter_plurality;
- **forbidden source**: results/e2_greedy_quarter_plurality_100r50t (historic rejected self-claim fallback version).

Both inputs must have exactly one raw CSV each, valid source git SHA, the SAME robot/task dimensions, complete seed×loss coverage, matching per-seed **full-information zero-loss Sequential Greedy reference cost** and fully committed/Greedy-matching 0% controls. A historical majority raw dataset may legitimately lack the later-added vote_decision_rule column; accept ONLY method=democracy_greedy_retirement as a grounded indication of that legacy rule. Reject any wrong method or explicit obsolete fallback rule.

### 16.2 Controlled condition axes and paired measurement semantics

Primary figure selection: p_cost_loss = p_vote_loss = p for p ∈ {0.00,0.10,0.20,0.30,0.40,0.50}. These six points already exist in the historical 36-level 2%-step raw runs. No re-simulation is needed and **no different random scenario should be substituted**. An extended analysis can use the entire originally tested p=0.00,0.02,...,0.70 axis; the 0% level must always be present.

For each rule separately, compare each seed/loss scenario to THE SAME seed/rule's 0% loss run. The cost-loss degradation on a fully assigned batch is:

    Delta_GreedyCost(rule, seed, p) =
        100 * [Cost(rule, seed, p) / Cost(rule, seed, 0) - 1]

By validation, Cost(rule, seed, 0) is that seed's full-information Sequential Greedy cost, and is the same across majority and pure-25% archives.

- The batch **must** have committed ALL T requested tasks before reporting a full-task-set cost delta. For any partial allocation, record cost_comparison_eligible=0 and the cost delta as NaN; do NOT compute a misleading low partial cost, infer a penalty, or erase that seed from assignment-completion statistics.
- Curves report mean cost degradation **only among fully assigned runs** AND the exact number of successful cost-eligible seeds. The selection effect when loss is high must be disclosed prominently.
- For a directly paired cross-protocol cost delta, include ONLY those same seeds where BOTH protocols fully committed. If that intersection is empty, output NaN with both_completed_count=0; do NOT substitute a zero difference or unpaired successful-only means.
- For each seed and p, record task Commit fraction, full T-task success, Greedy executor identity agreement measured against full-information per-task Sequential Greedy (with a per-requested-task denominator), agreement AMONG committed tasks separately when available, failed vote attempts, total simulated coordination milliseconds, number of logical messages and payload bytes.
- Compare elapsed time/messages/bytes both as absolute magnitudes and as per-seed changes from THAT PROTOCOL's own 0% loss run; this preserves the known very different zero-loss timing model for majority vs final-score-announcement plurality.
- Pair protocols by the SAME seed and p. Record batch success percentage-point difference (quarter - majority), counts of both completed / quarter-only completed / majority-only completed / neither completed; Greedy executor rate difference, elapsed time/message/byte difference, and cost difference ONLY over BOTH-complete seeds.
- Observed Cost/Vote packet drop rates are **aggregate number of drops / physical attempts**, not naive averaging of seed-level ratios; a zero-attempt vote stage yields NaN (no evidence), not an arbitrary claim of zero packet loss.

The new report does NOT recompute any task decisions or call solve_hungarian_assignment. It must not be mistaken for a controlled comparison of protocol delivery mechanisms beyond the model's reliable qualified-score announcements and reliable Commit assumption. Historical raw sources may have different code SHAs; require a single SHA within each source and independently verify per-seed Greedy reference costs. Source revision equality BETWEEN the two protocol implementations is not required because their formal runs were committed at different revisions, but this is an explicit limitation.

### 16.3 Reporting owner and diagnostic contract

New read-only analysis owner: experiments.compare_greedy_communication. It consumes the original E2 evidence, which remains append-only, and writes a separate derived report root without editing either input.

Named-function ownership:
- validate_comparison_configuration: data validation for requested R/T/seeds/attempt cap/strictly sorted diagonal loss axis containing p=0.
- locate_single_raw_evidence: dependency/contract validation of exactly one timestamped raw input CSV per protocol.
- validate_greedy_evidence_row: per-row data, rule, method, seed, R/T, packet loss, success/commit accounting and safety-contract validation.
- read_greedy_raw_evidence: source integrity/coverage: no duplicate seed/loss, one SHA per source, full selected seed×loss Cartesian coverage, no fallback methods.
- validate_paired_greedy_scenarios: verify equal scenario Greedy-reference costs across both inputs and all p; zero-loss batch fully complete with Greedy score 100%, cost identical to reference.
- build_greedy_per_seed_rows: compare to own rule/seed p=0, excluding partial batches from full cost gaps.
- summarize_greedy_rule_curves: per-rule mean task/full success, Greedy executor accuracy, cost delta on completed subsets with n, attempts/latency/messages/bytes and physical stage drop rates.
- summarize_paired_protocol_differences: same-seed cross-rule success disagreement and ONLY both-complete cost delta; missing shared completion stays NaN.
- write_greedy_only_comparison: immutable separated output guard, three CSVs and timestamp/source SHA/SHA256 manifest.
- compare_existing_greedy_evidence: orchestrates only these read/validation/analysis steps; it does not own physical voting, planner or Hungarian computations.

First-failure diagnostic codes with owner/function/category/expected/actual:
- INVALID_GREEDY_COMPARISON_SHAPE / validate_comparison_configuration / data
- INVALID_GREEDY_COMPARISON_LOSS_AXIS / validate_comparison_configuration / data
- MISSING_GREEDY_RAW_EVIDENCE / locate_single_raw_evidence / dependency
- AMBIGUOUS_GREEDY_RAW_EVIDENCE / locate_single_raw_evidence / contract
- MISSING_GREEDY_RAW_COLUMNS / read_greedy_raw_evidence / dependency
- INVALID_GREEDY_RAW_VALUE / validate_greedy_evidence_row / data
- GREEDY_RAW_CONTRACT_MISMATCH / validate_greedy_evidence_row / contract
- DUPLICATE_GREEDY_SEED_CONDITION / read_greedy_raw_evidence / contract
- GREEDY_SEED_LOSS_COVERAGE_MISMATCH / read_greedy_raw_evidence / contract
- PAIRED_GREEDY_SCENE_MISMATCH / validate_paired_greedy_scenarios / contract
- ZERO_LOSS_GREEDY_BASELINE_MISMATCH / validate_paired_greedy_scenarios / contract
- GREEDY_ANALYSIS_SOURCE_OUTPUT_COLLISION / write_greedy_only_comparison / state
- GREEDY_ANALYSIS_OUTPUT_EXISTS / write_greedy_only_comparison / state

No voting, cost exchange, packet sampling, membership/retirement, optimizer or runtime execution owner is modified; no new wrapper, hidden fallback, or second state machine.

### 16.4 Outputs, acceptance and Mac commands

New derived report root: results/e2_greedy_only_communication_comparison. Expected generated outputs:
- greedy_per_seed.csv: 2 protocols × 100 seeds × 6 selected loss points = 1,200 rows for the primary axis (with a full-completion indicator and NaN full cost for failures).
- greedy_rule_curve.csv: 2 × 6 = 12 aggregate rows.
- greedy_protocol_delta.csv: 6 paired condition rows.
- manifest.json: exact inputs, source git SHAs, source raw SHA256 hashes, analysis git SHA, UTC time, selected seeds/loss axis and statistical limitations.

Preflight and primary comparison (from Mac checkout where BOTH previous E2 raw archives already exist):

    git pull
    python3 -m unittest discover -s tests -v
    python3 -m experiments.compare_greedy_communication

Extended full 36-point Greedy-only curves can be generated to a DISTINCT new root by providing an explicit 2% axis, leaving the primary report unchanged:

    LEVELS="$(python3 -c 'print(",".join(f"{i/100:.2f}" for i in range(0, 71, 2)))')"
    python3 -m experiments.compare_greedy_communication --loss-probabilities "$LEVELS" --output-root results/e2_greedy_only_communication_comparison_36point

Acceptance requires exact source SHA/seed/scene matching, zero baseline cost differences at p0, no references to Hungarian in any GENERATED CSV column, all 0% scenario controls valid, no incomplete allocation included in a full-batch cost mean, and counts of paired successes reconciling to seeds for every p. Historical raw E2 roots and E3/E4 6,000-run scaling results must remain untouched.

Status when authored: source and regression tests committed; actual run on user's Mac pending. Do not claim the newly derived report has been generated until its files and console results are observed.


## 17. Literature-grounded packet-loss defense baseline — vote-copy redundancy (NO ACK)

### 17.1 Scientific comparison, published baselines, scope

User-requested priority: compare our decentralized packet-loss-resilient task allocation against OTHER established communication/reliability and decentralized MRTA techniques. Preserve the unchanged Sequential Greedy optimizer and compare complete-task success, assignment accuracy relative to 0%-loss Greedy, physical traffic bytes, time and safety.

Sources used for study design:
- IEEE Technology Navigator, Automatic repeat request (https://technav.ieee.org/topic/automatic-repeat-request/). Genuine ARQ uses receiver acknowledgement and retransmission feedback; this initial baseline has NO ACK and is NOT ARQ.
- Retransmission or Redundancy: Transmission Reliability in Wireless Sensor Networks, IEEE 2007, DOI 10.1109/MOBHOC.2007.4428620. Published reliability/energy tradeoff motivation, NOT an identical published algorithm implementation.
- Choi, Brunet, How, Consensus-Based Decentralized Auctions for Robust Task Allocation, IEEE Transactions on Robotics 25(4), 2009, DOI 10.1109/TRO.2009.2022423 (CBAA and CBBA, separate distributed assignment algorithms).
- MIT Aerospace Controls Lab official CBBA/ACBBA overview https://acl.mit.edu/projects/consensus-based-bundle-algorithm; Rantanen et al., Performance of the Asynchronous Consensus Based Bundle Algorithm in Lossy Network Environments, IEEE SAM 2018, DOI 10.1109/SAM.2018.8448984.

This initial code change implements ONE narrow and correctly labeled external reliability-control mechanism: FIXED OPEN-LOOP REDUNDANT REMOTE VOTE TRANSMISSION. It is neither ARQ, coded redundancy, CBAA, CBBA nor ACBBA. Future separate blocks should implement real ACK/retry and faithfully reproduce published CBAA/CBBA/ACBBA including their consensus/deconfliction and duplicate-allocation behavior, with separate owners/tests.

### 17.2 Exact transport policy and unchanged election semantics

Add opt-in vote_repetitions = K where K is an actual integer in {1, 2, 3}. K=1 is the historical default, preserving the EXACT original first physical Vote key and all existing per-seed Cost/Vote Bernoulli draws.

For each remote Greedy Vote:
- K=1 emits one physical unicast, as before.
- K=2 or 3 sends K unconditional packet copies at send_time + copy_index * phase_timeout_ms. There is no ACK and copies are sent even when an earlier copy was delivered.
- Each copy uses independent Bernoulli Vote Loss and a separately keyed empirical latency sample. Physical event and delivery observation include transmission_index (0..K-1). Every copy is charged in logical_message_count, payload_bytes and remote_vote_attempts, including copies that are dropped or redundant.
- Select the EARLIEST delivered physical copy and feed exactly one logical Vote to protocol.record_vote. Never count another packet copy as an extra voter. Local self-votes are never transmitted or repeated.
- Vote decisions at K>1 wait for the physically scheduled copies to complete. For the 25% final-score announcement, the vote collection deadline is max(cost_ready_times)+K*phase_timeout_ms. Strict majority also waits for scheduled copies before final Commit. This intentionally charges a conservative sequential slot delay. The model does NOT simulate collision, byte-rate or MAC scheduling.
- Initial Cost rows are broadcast ONCE with original independent Cost Loss and never resent. Hence this first baseline defends against VOTE LOSS only. Later Cost Loss recovery is its own separate concern. Reliable qualified final-score announcements and Commit assumptions remain unchanged.
- Neither the decision threshold, local Greedy, task queue rotation, robot retirement, nor the forbidden self-claim fallback is altered. 25% means strictly greater than 25% of the whole active electorate, not physical packet-copy count.
- A single remote vote delivery probability with independent copy loss p is 1-p^K, but full-task success also depends on missing Cost rows, candidate-vote disagreement and finite voting attempts; never infer whole-team performance from that packet formula alone.

### 17.3 One owner per concern / diagnostic contract

- network.validate_vote_repetitions: data / INVALID_VOTE_REPETITIONS; K must be an integer in 1..3.
- coordination._unicast_event and coordination._lossy_unicast_delivery: original physical transport owner functions, now accept/record optional transmission_index=0; index 0 retains original keyed samples, indices >0 get unique copy-suffixed keys.
- coordination.transmit_repeated_remote_vote: one named FIXED-COPY physical Vote sender function; return K physical events, K physical delivery observations and earliest successful observation (or None). It neither records votes nor chooses winners.
- coordination.simulate_democracy_hungarian_lossy: unchanged owner of vote ledger/threshold/Commit; consumes only earliest delivered remote copy as one voter and enforces end-of-copy decision time at K>1.
- coordination.simulate_democracy_hungarian_retirement: unchanged task queue and executor retirement owner; forwards validated K; one-to-one and failed-round task rotation preserved.
- experiments.run_e2_retirement.retirement_transport_stage_metrics: original physical packet counter, now computes self-votes from DISTINCT (round, sender, receiver, task) remote ballot identities and checks each has copy indices EXACTLY [0..K-1]. Contract / REPEATED_VOTE_PHYSICAL_COPIES_MISMATCH with expected, actual and details.
- experiments.run_e2_retirement.run_retirement_experiment, retirement_result_row, retirement_round_rows, summarize_retirement_results and write_retirement_audit_events: existing data-evidence owners; add vote_repetitions to new raw/round/summary/audit records and transmission_index to compressed seed-0 message/delivery events. Expose --vote-repetitions {1,2,3}, default=1. Refuse known archived output directories for K>1.
- tests/test_vote_repetition_baseline.py: K input bounds, 1-copy deterministic parity, first physical votes all lost but second copy reaches old majority, no duplicate voter, higher physical messages/bytes/time at 0% loss, no emergency Commit when all copies lost, unchanged retirement and Cost exchange, nonnegative self-votes and physical copy audit.

This is a bounded physical vote-transport concern. No second coordinator, voting state machine, optimizer, or safety workaround was added. All historical E2/E3/E4 entry points default to K=1.

### 17.4 Paired experiment and commands

Compare 100 Robots / 50 Tasks, Cost Loss=Vote Loss=p (independent draws), 100 seeds at each condition, max 100 individual task attempts, same original per-seed scene, optimizer and physical network model:

A: old 51% strict-majority with K=1 (historical E2, already recorded).
B: strict-majority with K=2 redundant Vote copies (NEW).
C: strict-majority with K=3 redundant Vote copies (NEW).
D: pure >25% final-score Greedy with K=1 and NO fallback (historical E2, already recorded).
Optional E: pure >25% with K=2 (transport ablation, not necessary for first formal comparison).

First execute all unit tests and three-seed smoke at p = 0,0.30,0.50 into NEW separate results:

    git pull
    python3 -m unittest discover -s tests -v
    python3 -m experiments.run_e2_retirement --robots 100 --tasks 50 --seeds 3 --cost-loss-probabilities 0,0.30,0.50 --loss-pairing diagonal --max-rounds 100 --vote-decision-rule strict_majority --vote-repetitions 2 --output-root results/e2_repeat2_majority_smoke
    python3 -m experiments.run_e2_retirement --robots 100 --tasks 50 --seeds 3 --cost-loss-probabilities 0,0.30,0.50 --loss-pairing diagonal --max-rounds 100 --vote-decision-rule strict_majority --vote-repetitions 3 --output-root results/e2_repeat3_majority_smoke

After tests and smoke PASS, run the two 100-seed × 36-level (0..0.70 every 0.02) formal baselines into separate NEW directories. 3,600 runs per additional K:

    LEVELS="$(python3 -c 'print(",".join(f"{i/100:.2f}" for i in range(0, 71, 2)))')"
    python3 -m experiments.run_e2_retirement --robots 100 --tasks 50 --seeds 100 --cost-loss-probabilities "$LEVELS" --loss-pairing diagonal --max-rounds 100 --vote-decision-rule strict_majority --vote-repetitions 2 --output-root results/e2_repeat2_majority_100r50t
    python3 -m experiments.run_e2_retirement --robots 100 --tasks 50 --seeds 100 --cost-loss-probabilities "$LEVELS" --loss-pairing diagonal --max-rounds 100 --vote-decision-rule strict_majority --vote-repetitions 3 --output-root results/e2_repeat3_majority_100r50t

Primary plots: full assignment success and committed task fraction versus p; physical vote packets/bytes, simulated end-to-end coordinator time versus p; Greedy executor agreement and complete-task cost gap versus each seed's 0%-loss Greedy (report complete-case sample n); actual physical vote drop rate and per-copy audit; safety errors / duplicate assignment must remain zero.

The legacy E2 experiment runner still computes a Hungarian oracle for backward-compatible existing raw columns; this is NOT an optimized method or comparison metric in this baseline analysis. Keep the Greedy-only primary plots/claims. Do not overwrite any historical E2/E3/E4 evidence or mislabel redundancy as ARQ or published CBBA.

### 17.5 Limitations, verification and next steps

This fixed K-copy scheme assumes independent Bernoulli losses, ignores shared airtime/collision and correlated outages, and does not repair initial Cost packet loss or test loss of reliably modeled announcement/Commit messages. It is a fundamental communications-control baseline, not yet a fair published MRTA algorithm-to-algorithm comparison. Next separately implement true ACBBA/CBAA if feasible under a validated 1 robot : 1 task policy and a distributed winner/conflict state model, keeping score/travel costs and communication accounting comparable.

Source and new tests are committed, but tests and K>1 experiments have NOT yet been run on the user's Mac. The last 111/111 test pass was for the previous code revision. Do not claim any new packet-loss success rates until evidence is observed.


## 18. External published-family baseline: synchronous single-assignment CBAA (E8)

### 18.1 Source fidelity, research scope and explicit adaptations

Published source: Han-Lim Choi, Luc Brunet and Jonathan P. How, "Consensus-Based Decentralized Auctions for Robust Task Allocation," IEEE Transactions on Robotics 25(4), 912–926 (2009), DOI https://doi.org/10.1109/TRO.2009.2022423, publicly archived MIT https://dspace.mit.edu/entities/publication/b0bf0a05-be3b-433b-9f4b-ce314ed5178b . CBAA Section III comprises an iterative **single-assignment auction** (each robot chooses at most ONE task for which its own score beats known winning bids) followed by a **bid maximum-consensus** process through neighbor communication; a robot releases its currently claimed task when outbid. CBBA in Section IV builds multi-task bundles and has different conflict-handling and timestamp logic: this baseline DOES NOT implement or claim to be CBBA/ACBBA.

This standalone CBAA implementation uses the published two-phase mechanism, with transparently documented engineering restrictions/adaptations:
- synchronous iteration barriers with a COMPLETE communication topology; there is no simulated asynchrony or sparse topology in this first milestone;
- score=c_ij=1/(1+Euclidean distance cost_ij)>0, a strictly decreasing nonnegative-cost utility. No Hungarian, own 25% election, own Greedy one-task voting, global optimal assignment, or global bid normalization drives the CBAA decisions. Any difference in cost vs sequential Greedy may reflect a different assignment optimizer, not packet-loss performance;
- deterministic tie-breaking by lower task ID (own task choice) and lower robot ID (equal winning scores). A winner-origin ID accompanies each winning-bid vector entry so a relay cannot wrongly claim to be the original winning bidder. This extra metadata is explicit, and message length includes it: one broadcast payload APP_HEADER_BYTES + Nt*(FLOAT64_BYTES + ID_BYTES);
- every robot broadcasts its entire bid and winner-origin vector once per iteration; independently sampled Bernoulli physical loss at EACH receiver for every one of the other N-1 nodes; local self information is always available;
- phase delay sampled from the exact same pinned Rady Wi-Fi empirical-delay profile as E2, and each iteration is fixed at one profile-maximum phase timeout. A physically delivered packet arriving after this deadline is accounted as late but NOT ingested. The initial test uses a fixed number of iterations; **there is currently NO decentralised network-wide stop-detection protocol** and no hidden global inspector used to terminate the iteration loop early. Fixed-budget time/message overhead is a deliberate conservative study control, not a claim of optimized CBAA runtime;
- **no centralized rescue, arbitration or reliable final Commit**. Only a separate external evaluation observer, AFTER the fixed iteration budget, can assess whether ALL local nodes agree on task winning bid and owner, and whether exactly that agent has an unconflicted local task claim. If beliefs disagree, the task is UNCONFIRMED; if multiple robots claim it, the task is in a raw split-brain conflict. No global observer winner is broadcast or fed back into any robot. Observer agreement is NOT equivalent to an actual distributed Commit or physical task execution;
- CBAA consensus-message loss probability p is numerically compared with the old E2 Cost Loss = Vote Loss = p, but CBAA has ONE physical consensus-packet stage per iteration, while old E2 has a one-time Cost and repeated Vote stage with reliably modeled Commit. These are NOT equivalent packet-message workload or reliable control-message assumptions. Do NOT ascribe all differences to a single "packet-loss algorithm" without reporting message semantics and byte/time accounting.

This is explicitly a synchronous single-assignment CBAA **reference implementation** rather than an exact reproduction of the original paper's asynchronous network scheduling, termination control or multi-assignment CBBA. It is the FIRST bounded source-based baseline. Actual CBAA zero-loss convergence must pass tests and a 100R/50T smoke before the results may be used as a paper headline. A later bounded concern can add a proper distributed termination protocol, direct sparse/burst networks, or separate CBBA/ACBBA owners.

### 18.2 Exact source/owner/function and data lifecycle

New CBAA auction-consensus owner: democracy_mrta.cbaa. It holds only the CBAA local state; the original democracy_mrta.coordination multi-round Vote quorum/quarter-plurality membership state machine is untouched.

- CBAALocalState(robot_id, assigned_task, winning_bids, winning_robots): local ONLY. x_i is at most one task, y_i is per-task max known bid and origin; starts empty.
- validate_cbaa_configuration: check original optimizer.validate_cost_matrix and network.validate_packet_loss_probability owners first; then CBAA score's nonnegative costs, exact integer max_iterations>=1 and valid positive finite phase_timeout_ms. New first-failure data/CBAA_NEGATIVE_COST, data/CBAA_INVALID_ITERATION_BUDGET and time/CBAA_INVALID_PHASE_TIMEOUT.
- initial_cbaa_states: initialize independent per-agent state at no assignments / zero bids / None owners.
- cbaa_score: locally transform Euclidean cost to positive descending reward, independent of other agents' private costs.
- cbaa_bid_outbids: deterministic max bid / lower origin-ID tie-break, called by both CBAA auction and CBAA consensus phases; no centrally assumed winning agent.
- cbaa_auction_phase: published Phase 1 owner; agents with assigned tasks keep them; unassigned agents only bid for tasks where their own reward beats stored bid, then choose their own maximum reward / lower task ID.
- exchange_cbaa_consensus_packets: physical CBAA one-broadcast-per-agent transport stage, reuse existing coordination._broadcast_event and _lossy_broadcast_deliveries so sender message count, one-sender latency and per-receiver drops are charged consistently with E2. Returns each receiver's OWN received local-state snapshots, N sent broadcasts, N*(N-1) physical reception opportunities, bytes, physical drops and late arrivals, plus seed-0 audit when requested. No global winner selection inside it. A delivered packet without an arrival time fails contract/CBAA_DELIVERED_PACKET_WITHOUT_TIME.
- cbaa_consensus_phase: published Phase 2 owner; per agent update each bid entry with maximum from RECEIVED neighbors and itself, propagate real winner origin metadata, release its own assignment if outbid.
- audit_cbaa_local_agreement: EXTERNAL observer after protocol, not called by agents to elect or Commit. Reports ALL local task claims, per-task conflicts, unanimous winner origin+score confirmation and still-unconfirmed tasks. Never arbitrates a split-brain task or creates a new valid robot allocation.
- simulate_cbaa: runs original CBAA two named phases for exactly max_iterations, counts physical broadcasts/bytes/delivery attempts/late messages and performs one post-hoc read-only audit. Safety/CBAA_DUPLICATE_OBSERVER_AGREEMENT guards an impossible duplicate robot in observer-confirmed pairs. Never calls solve_hungarian_assignment, the Greedy task-vote engine, or the 25% Commit/score owner.

New independent experiment/evidence owner: experiments.run_cbaa_baseline:
- validate_cbaa_benchmark_axes: data / INVALID_CBAA_BENCHMARK_AXES, INVALID_CBAA_LOSS_AXIS. Current user-approved R<=100, T<=R, seeds>=1, iterations>=1, increasing loss levels.
- prepare_cbaa_output: state / CBAA_OUTPUT_SOURCE_COLLISION or CBAA_OUTPUT_ALREADY_EXISTS. Never overwrite historical E2 strict/25%, K2/K3 or E3/E4 raw. Permit dedicated ledger README-only output. Partial abort requires manual new output path instead of overwriting.
- cbaa_result_row: per seed and p, include ALL raw local claims, conflicts, observer confirmed tasks, unconfirmed tasks, task agreement, physical packets/drops, bytes, elapsed time, fixed iterations, SHA, Greedy offline reference for evaluation only, timestamp.
- cbaa_full_batch_cost: only FULL observer agreed task batches receive total cost. Missing/conflicted batches have NaN cost, never bogus cheap partial assignment; this is POST-HOC evaluation, not a CBAA decision.
- summarize_cbaa_conditions: per-p results with full-agreement sample count, task agreement, conflicts, completed-only cost, actual physical drops/attempts, bytes and time.
- write_cbaa_seed_zero_audit: compressed seed-0 per-sender broadcasts, per-receiver physical deliveries and each final local CBAA bid/owner vector, with NO fake consensus Commit.
- run_cbaa_baseline: independent benchmarking orchestration; same generate_e0_scenario cost rows/seed, same pinned Rady Wi-Fi latency sampler, independent Bernoulli loss per physical consensus reception, source git SHA, deterministic seed and separate output root.
- main: CLI only.

No existing Vote owner, quorum, runner, optimizer, packet-loss keyed behavior, E2/E3/E4 historical data or K-copy baseline is modified in this first CBAA block.

### 18.3 Study design and acceptance

**Primary current acceptance is algorithm correctness, not best-performance claims.** First run all existing/new unit tests, then small realistic CBAA smoke on Mac:

    git pull
    python3 -m unittest discover -s tests -v
    python3 -m experiments.run_cbaa_baseline --robots 10 --tasks 5 --seeds 3 --loss-probabilities 0,0.30,0.50 --max-iterations 20 --output-root results/e8_cbaa_single_assignment_smoke

Expected one new root with:
- raw/cbaa_<UTC>.csv — 3 seeds x 3 p = 9 rows; no Hungarian metrics/solver calls, no fabricated Commit;
- summary.csv — one line per p, complete-only batch cost count and full observer agreement, task consensus, local split-brain metrics, packet/byte/time;
- events/cbaa_audit_<UTC>.csv.gz — all physical consensus-broadcast send/reception events for seed 0, and final local winner bid and ID vectors;
- manifest.json — original publication DOI, pinned Rady dataset and Git SHA, exact R/T/seeds/max_iterations/loss axis/timeout, score and adaptation disclosures.

After SMALL smoke and unit suite pass, run a 100R/50T 3-seed pilot into a DIFFERENT evidence root; confirm p=0 achieves whole-team observer agreement, no hidden global arbitration, and physical drop ~p for finite samples:

    python3 -m experiments.run_cbaa_baseline --robots 100 --tasks 50 --seeds 3 --loss-probabilities 0,0.30,0.50 --max-iterations 20 --output-root results/e8_cbaa_100r50t_pilot

If 0%-loss full observer agreement fails, treat as a convergence/iteration-budget contract or algorithm bug to investigate BEFORE formal comparison; do NOT accept a fragmented CBAA method in a paper comparison or quietly promote post-hoc observer assignments to authoritative Commit. If p>0 creates duplicated local claims, report them directly as failure/unsafe convergence, do not censor them by selecting one global winning robot.

Only after validating CBAA's 0%-loss convergence, independent loss protocol, message byte/time policy, and distributed stopping fairness should we design and launch formal 100 seeds x 36 p levels and compare with the already user-completed Greedy 51%, Greedy 25%, and Vote K2/K3 baselines. Unlike previous fixed-Greedy-only ablations, an algorithm-level CBAA comparison MUST disclose that the CBAA local auction optimizes a distinct task-selection objective and its packet semantics differ from the original E2 Cost+Vote model.

### 18.4 Verification limits / next concern

User already completed prior 51%-majority K1, K2, K3 and pure 25% K1 100R/50T, 36 levels, 100 seeds each; new CBAA code/tests have only been committed through GitHub, not executed on the user's Mac as of this change. There is currently no proof of zero-loss full agreement at 100R/50T and no actual new CBAA baseline numerical results. The fixed iteration budget deliberately does not include an implementable fully distributed "all agents stopped" detection; a subsequent bounded change and its own continuity record are required before claiming general fair latency comparisons with the old E2 termination model or published original's asynchronous scheduling. Published CBBA/ACBBA faithfully implemented as separate standalone algorithms remains subsequent work.


## 19. E9A observed sent-Bytes communication calibration — NOT hard-capped

### 19.1 Goal, fairness and boundaries

After the user's Mac verified CBAA at 100R/50T, 3 seeds, p=0/.30/.50 (135/135 tests), they requested a communication-matched rather than arbitrarily 20-round or one-round comparison against the previously completed Greedy pure25 protocol. Existing CBAA 20 fixed rounds generate 2000 physical broadcast SEND events, 1,232,000 sender-accounted payload Bytes, and 198,000 per-receiver delivery opportunities. The user-approved initial change is one bounded READ-ONLY analysis, not a global refactoring of either runtime.

Owner experiments.compare_cbaa_budget reads existing E2 pure25 RAW data and independently executed CBAA raw for different iteration budgets, without running the model again or modifying source CSVs. It never chooses task winners or changes CBAA bids, Greedy votes, network delivery, task queue, timeout, or safety. The historical p0 Greedy run is the baseline for choosing a *nearby CBAA transmission budget*.

### 19.2 What equal/near observed payload means

Primary unit: application payload Bytes transmitted by sender. A broadcast is counted ONCE at sender even if it offers N-1 independent recipient delivery opportunities. Vote unicasts are counted once per actual physical send. Message counts, receiver opportunities and simulated elapsed time are separately reported, never mistaken for transmitted Bytes. Greedy pure25 payload includes one-time Cost exchange, remote Vote packets, qualified-score announcements and reliably modeled Commit packets. CBAA sends one vector with task bids plus original winning robot IDs each round: R*K*(16+12*T) Bytes across K iterations (in current model).

Same seed, robots, tasks and p are required across sources; every source must report the same offline full-information Greedy scenario reference cost per seed, and Greedy p=0 must successfully allocate every task and match its full-information Greedy oracle. Greedy uses independent Cost and Vote losses at equal numeric p, while CBAA uses one consensus-vector per-receiver loss stage at p. Greedy's reliable Commit/score announcements vs CBAA's post-hoc observer agreement are NOT interchangeable. Neither simulator models MAC channel contention, retry airtime or radio bandwidth. The resulting E9A analysis is observed traffic calibration, NOT a controlled equal-hard-budget intervention.

Selection rule (prevents outcome cherry-picking):
- Compute mean sender payload bytes of pure25 Greedy p=0 over selected paired scenario seeds.
- Compute mean CBAA p=0 sender payload bytes for each available integer max_iterations K. This does not inspect any CBAA success/metric or p>0 result.
- Choose the K with smallest absolute fractional difference to Greedy p=0 sent bytes; tie-break by smaller K.
- Require the closest candidate to be within +/-10% by default, else explicitly UNMATCHED. No made-up fractional round or selective success conditioning.
- Independently test actual mean byte ratios at EACH later loss p, and report how many individual paired seeds are within the same tolerance. A p=0 match is NOT presumed matched at p=.30/.50.
- Keep all failed/incomplete runs and CBAA split-brain/unconfirmed tasks in success-rate denominators; never treat a partial task set as a cheap full allocation. No retrospectively invented budget-abort state.

### 19.3 One named concern per function and diagnostics

New owner experiments.compare_cbaa_budget:
- validate_budget_calibration_config: typed R,T,seeds,max_rounds, sorted unique p including 0, tolerance and distinct source roots. data / INVALID_BUDGET_CALIBRATION_SHAPE and INVALID_BUDGET_CALIBRATION_GRID.
- locate_budget_source_file: exactly one timestamped raw CSV per historical Greedy and CBAA source; dependency / MISSING_BUDGET_SOURCE_CSV, contract / AMBIGUOUS_BUDGET_SOURCE_CSV.
- validate_budget_source_row: original algorithm identity, no rejected fallback, valid source dimensions/physical messages/sent bytes/observed outcome, exact CBAA send+receive arithmetic. data / INVALID_BUDGET_SOURCE_VALUE, contract / BUDGET_SOURCE_CONTRACT_MISMATCH.
- read_budget_source: exact requested seed-loss coverage, one source revision and one CBAA max_iterations per root (while permitting extra historical seeds). dependency / MISSING_BUDGET_SOURCE_COLUMNS; contract / DUPLICATE_BUDGET_SEED_LOSS and BUDGET_SOURCE_COVERAGE_MISMATCH.
- validate_paired_budget_scenes: same offline Greedy scenario cost across original sources and zero-loss original task/Greedy correctness. contract / BUDGET_PAIRED_SCENARIO_MISMATCH and BUDGET_ZERO_LOSS_GREEDY_FAILURE.
- calibrate_cbaa_send_budget: p=0 traffic-only nearest K, never CBAA outcome-based. contract / BUDGET_ZERO_TRANSMISSION_REFERENCE.
- build_budget_observation_rows: per-seed per-loss per-CBAA-budget observed Greedy and CBAA full success, task/observer coverage, actual packet sender bytes, messages/time, split-brain and per-recipient physical loss (observation only).
- write_budget_calibration: immutable output root, new budget_options.csv, budget_per_seed.csv, budget_curve.csv and manifest.json (source Git SHA, SHA256, analysis SHA, calibration rule and limitations). state / BUDGET_REPORT_SOURCE_COLLISION, BUDGET_REPORT_ALREADY_EXISTS.
- compare_cbaa_communication_budget: read-only orchestration, rejects duplicate CBAA K across roots. contract / DUPLICATE_CBAA_BUDGET_CONFIGURATION. Always prints OBSERVED_SEND_BYTE_CALIBRATION_ONLY_NOT_HARD_CAPPED.
- main: experimental CLI, 3 seeds, p=0/.30/.50, 100R/50T, tolerance=.10 by default.

New tests/test_cbaa_budget_comparison.py uses synthetic 2R2T/3 seeds data, checks selection by p0 traffic even when that configuration has LOWER success, raw immutable SHA256, p-specific mismatch, source columns and key coverage, physical send/receive counts, no output overwrite, collision guard, duplicate CBAA budgets and original p0 Greedy correctness. Existing E2/CBAA protocol owners, their original runner code, historical 100-seed evidence and canonical §13-18 are not modified.

### 19.4 Reproducible Mac E9A pilot commands

First, from project root where the original 100R/50T pure25 RAW and CBAA 20-round pilot exist:

    git pull
    python3 -m unittest discover -s tests -v
    python3 -m experiments.compare_cbaa_budget --cbaa-roots results/e8_cbaa_100r50t_pilot --output-root results/e9_cbaa_budget_calibration_20only

That is an intentional preliminary single-choice traffic comparison, NOT proof of a near-budget match.

Then reuse the existing CBAA runner at different integer budgets without changing its algorithm:

    for K in 1 2 3 4 5 8 10; do
      python3 -m experiments.run_cbaa_baseline --robots 100 --tasks 50 --seeds 3 --loss-probabilities 0,0.30,0.50 --max-iterations "$K" --output-root "$(printf 'results/e8_cbaa_budget%s_100r50t_smoke' "$K")" || break
    done

Then run a NEW E9A report root with all 7 new K sources and the original 20-round pilot:

    python3 -m experiments.compare_cbaa_budget --robots 100 --tasks 50 --seeds 3 --loss-probabilities 0,0.30,0.50 --tolerance 0.10 --cbaa-roots results/e8_cbaa_budget1_100r50t_smoke results/e8_cbaa_budget2_100r50t_smoke results/e8_cbaa_budget3_100r50t_smoke results/e8_cbaa_budget4_100r50t_smoke results/e8_cbaa_budget5_100r50t_smoke results/e8_cbaa_budget8_100r50t_smoke results/e8_cbaa_budget10_100r50t_smoke results/e8_cbaa_100r50t_pilot --output-root results/e9_cbaa_budget_calibration_3seed

Never run those into existing source roots or overwrite past reports. Read budget_options.csv for the p0-only selected K and its traffic mismatch; budget_curve.csv for ALL curves and observed near-budget flags; budget_per_seed.csv for individual outcome/byte cost, and manifest.json for immutable SHA provenance. Do not present K20 or a mismatched K as an equal-resource experimental result.

### 19.5 Future separate E9B hard-cap concern

E9B must implement actual sender-side byte budgeting BEFORE physical transmission in the real original network/coordination owners (without creating a second voting state machine), with recorded budget-exhaustion/incomplete-task semantics and consistent accounting for BOTH algorithms. E9A cannot approximate runtime-aborted assignments from completed historical runs. Proper identical channel/reliable-control assumptions, bandwidth, and distributed stop/deadline handling also remain separate future concerns. No formal paper-level equal-budget success superiority is established by E9A.


## 20. E9B-1 sender application-Payload Bytes admission (opt-in infrastructure, not yet an experiment)

E9A passed its first user-Mac validation with 145/145 tests (main HEAD 68499c9): 3 paired seeds at 100R/50T, p=0/.30/.50. The closest CBAA p0 traffic budget was K=3: 184,800 sender payload Bytes vs 163,800 Greedy Bytes, relative gap +12.82%, outside the predeclared +/-10% match. CBAA at K=3 fully agreed on 3/3 p0 but 0/3 p30 and p50 seeds; this is a small pilot and is NOT an equal-budget outcome comparison. E9A historical CSVs remain immutable.

E9B-1 introduces ONE physical transport admission concern, owned by network.reserve_sender_payload, with a per-run SenderPayloadBudget ledger. The caller may pass the ledger via send_budget to the existing coordination._unicast_event or coordination._broadcast_event physical event constructors. The reservation happens BEFORE the physical CommunicationEvent is constructed or latency is sampled. Broadcast SEND is charged once, independently of its number of receiver opportunities; remote Vote unicast is charged once per physical copy. A local self-vote does not invoke either physical constructor. An integer budget of 0 is valid, and packets larger than the remaining budget are NEVER fragmented or partially paid for.

A denied send raises the distinguishable SenderBudgetExhausted, Diagnostic owner=network / function=reserve_sender_payload / category=runtime / code=SEND_PAYLOAD_BUDGET_EXHAUSTED with expected max_next_send_bytes, attempted_send_bytes and current-used details. It increments denied_messages, not sent_messages or sent_bytes. Invalid initial cap is network.validate_sender_payload_budget / data / INVALID_SENDER_PAYLOAD_BUDGET; invalid packet size is network.reserve_sender_payload / data / INVALID_SENDER_PAYLOAD_SIZE. Only exact nonnegative integers are allowed for caps; only exact positive integers for payload size (bool is never an integer byte size).

The send_budget=None DEFAULT leaves all previous E0-E8/E9A behavior, sampler packet keys, packet outcomes, election rules, CBAA bidding, timing, Commit reliability, result shape and recorded evidence unchanged. NO simulator/runner yet passes a budget object and none catches the budget exhaustion exception. This stage is thus ONLY the opt-in transport contract, NOT a claim of a runnable E9B hard-cap experiment. Never pass send_budget to a production simulator until its owning algorithm function has explicit stop/partial-result rules that prevent phantom Vote/score/Commit or split-brain execution.

Next bounded blocks must: (1) integrate Greedy retirement budget with incomplete Cost/Vote/score/Commit accounting and safety-preserving budget termination, (2) integrate CBAA broadcast budgets without global arbitration or fake Commit, (3) add a paired E9B runner that instantiates fresh budgets per seed/method/loss, enforces immutable raw/manifest and exact common byte caps, and adds 100-seed experimental acceptance after three-seed smoke. A later separate concern must harmonize lossy control-message assumptions and actual wireless bandwidth/airtime; no claim of equal physical channel time from this byte-only cap.


## 21. E9B-2 opt-in Greedy pure25 hard-cap runtime (one owner, not yet a paired benchmark)

On 2026-10-11 the user's Mac validated E9B-1 at 152/152 tests on branch experiment/e9b-sender-byte-admission. The new E9B-2 subset activates the existing network SenderPayloadBudget in the ORIGINAL democracy_mrta.coordination Greedy retirement owner. E9B-2 accepts send_budget ONLY for voting_strategy=greedy_task, vote_decision_rule=quarter_plurality (strictly more than 25%, no fallback), vote_repetitions=1; other budgeted algorithms fail at coordination.validate_budgeted_retirement_scope / planning / BUDGETED_RETIREMENT_REQUIRES_GREEDY_QUARTER_K1. Existing runners always omit send_budget, so all historical E2/E3/E4/E9A and CBAA execution remain unchanged.

One budget is instantiated per seed/method/p/limit by a future E9B runner and passed into coordination.simulate_democracy_hungarian_retirement. Real physical SEND events are reserved BEFORE transmission through the E9B-1 network owner, never retrospectively excluded. The initial COST row broadcast is charged exactly once per sender for the entire retirement run; each remote Vote unicast, qualified reliable vote-score broadcast and reliable Commit broadcast is separately charged once at sender. Local self-votes are free. Broadcast reception opportunities do NOT multiply sender Bytes; reliable score/Commit packets consume SEND Bytes despite retaining the original E2 reliable-delivery model.

Stop on the FIRST denied SEND at stage cost/vote/vote_score_announcement/commit. Previously emitted stage packets and deliveries remain in the round trace and ledger. Partial votes or partial qualified scores do NOT create a committed executor; a decision without a successfully emitted Commit is NOT a valid allocation. No task, robot, or round is silently retired/rotated after a budget abort. Already valid committed tasks in earlier epochs REMAIN committed and retired, with all remaining tasks pending. No artificial fallback or central decision rescue is allowed. A budget limit equal to the actual sum of all original sent payload may complete normally without any exhausted stop, whereas cap zero creates no physical events.

Owner/function boundaries:
- network.reserve_sender_payload: unchanged pre-emission SEND admission, now stores last_denied_diagnostic on the run-local SenderPayloadBudget ledger so the original failure's first owner/function/category/code survive a normal budget stop.
- coordination._simulate_lossy_cost_broadcasts / capture_retirement_cost_snapshot: stop at first physically rejected COST, expose original partial events, and mark the retained snapshot as incomplete; no fresh Cost or missing-ground-truth row.
- coordination.transmit_repeated_remote_vote: preserve partial transmitted Vote events, return actual delivery information; epoch owner detects sender denial before authorizing a winner.
- coordination.simulate_quarter_plurality_announcement_phase: if one qualified score send is rejected, return no authorized election result and preserve all previously emitted score events (but not a Commit).
- coordination.simulate_democracy_hungarian_lossy: preserve original vote ledger and one-to-one/Commit rules in unbudgeted mode; in budgeted mode detect first SEND denial and use the common _summarize_lossy_result with zero newly committed tasks.
- coordination.summarize_budget_exhausted_epoch: owns no-phantom-Commit aborted-round summary, exact transmitted physical event count, and the first network diagnostic. A timeout-like incomplete attempt is NOT a quorum result.
- coordination.simulate_democracy_hungarian_retirement: retains the ONLY membership/queue state machine; after an aborted round STOP before apply_announced_retirement_commits. A previous fully emitted Commit remains valid.
- coordination.require_retirement_sender_accounting: contract / BUDGET_LEDGER_EVENT_MISMATCH ensures that the physical-budget ledger's sent bytes/messages equal all trace-emitted physical SEND events. A mismatch is fatal, never repaired by post-hoc clipping.

Budget stop is exposed as budget_exhausted, budget_stop_phase, and budget_stop_diagnostic on existing LossyCoordinationResult and MultiRoundRetirementResult (defaults False/None when unbudgeted). Network first-failure diagnostic remains network.reserve_sender_payload / runtime / SEND_PAYLOAD_BUDGET_EXHAUSTED; coordination.summarize_budget_exhausted_epoch / contract / MISSING_PHYSICAL_BUDGET_FAILURE only applies to broken internal stop propagation. Budgeted single-round direct calls without the prior retained Greedy cost snapshot fail coordination.simulate_democracy_hungarian_lossy / planning / BUDGETED_EPOCH_REQUIRES_RETAINED_COSTS.

Simulated elapsed time on an aborted round is the latest ARRIVAL of an actually emitted packet (if zero SENDs, zero elapsed), not a fabricated later Commit/deadline. This budget still limits application sender Bytes, not physical radio airtime or total recipient delivery work. This change is NOT a claim that reliable control packets are comparable with CBAA observer consensus; E9B-3 must integrate CBAA own local auction/consensus owner and E9B-4 must pair both methods under identical caps in an immutable raw runner with 3-seed smoke before 100-seed formal work. No new 100-seed result is claimed from this change.


## 22. E9B-3 original CBAA per-SEND Bytes hard-cap runtime (no paired runner yet)

The 2026-10-11 user Mac run confirmed E9B-2 at 159/159 unit tests (7/7 targeted) at SHA 9c24de1aa8c345536dccfab19db595c3850b3275. E9B-3's changes are NOT yet Mac verified. This phase changes ONLY original democracy_mrta.cbaa: CBAA bid/consensus sender-side Bytes admission under optional network.SenderPayloadBudget. It does not implement another state machine, decentralised termination detection, fallback, final Commit, CBBA/ACBBA or extra per-receiver SEND charging. Historical E8 runner and E9A derived reports are untouched.

The unchanged exchange_cbaa_consensus_packets physical broadcast stage now passes opt-in send_budget to the existing coordination._broadcast_event, which invokes network.reserve_sender_payload BEFORE event construction and latency. Per vector packet cost is APP_HEADER_BYTES + T*(FLOAT64_BYTES + ID_BYTES) = 16+12T sender Bytes. A broadcast is counted ONCE at the sender, independently of N-1 recipient delivery opportunities. On first denied packet, preserve all already emitted broadcasts, all of their independent per-receiver Bernoulli receive/drop/late outcomes, and only the snapshots actually in each recipient's on-time local inbox; no denied packet ever appears in audit, packet totals or receivers. Stop sending and stop subsequent iterations.

Original simulate_cbaa remains the one TWO-PHASE agent-state owner. For any aborted iteration with >=1 physically emitted broadcast, every robot completes that iteration's LOCAL auction+consensus using its OWN inbox; this executed partial barrier counts one iteration and phase_timeout_ms. If zero broadcasts were emitted in the attempted iteration, discard speculative auction bids, leave the preceding local state unchanged, and count no extra iteration/time. No global convergence test is used to decide the stop; only the physical Bytes cap or max_iterations, and observer agreement is audited separately AFTER stopping and NEVER fed back to agents or called a Commit. With send_budget=None, existing K rounds/time/packet keys and results are identical.

CBAAResult adds budget_exhausted, budget_stop_phase and budget_stop_diagnostic with default False/None. The original network diagnostic network.reserve_sender_payload / runtime / SEND_PAYLOAD_BUDGET_EXHAUSTED is kept unchanged in the result. New CBAA diagnostics: validate_cbaa_sender_budget / data / CBAA_INVALID_SEND_BUDGET for malformed ledger; require_cbaa_sender_budget_accounting / contract / CBAA_SEND_BUDGET_LEDGER_MISMATCH if actual physical transmitted message/byte totals differ from the original shared ledger. Original exchange_cbaa_consensus_packets / contract / CBAA_DELIVERED_PACKET_WITHOUT_TIME and simulate_cbaa / safety / CBAA_DUPLICATE_OBSERVER_AGREEMENT remain.

Budget exhaustion can coexist with full OBSERVER agreement if the local distributed phase had already converged. This is neither a distributed Commit nor a global early-stop algorithm. Reporting must retain any split-brain and unconfirmed tasks; incomplete runs must not be assigned a cheap full-task-set cost. This benchmark controls sender APPLICATION payload only, NOT PHY airtime, MAC retransmissions, competing-radio contention or harmonized control-message reliability (Greedy score and Commit remain reliable in the existing E2 model, while CBAA vectors are lossy). Next E9B-4 independently builds a paired seed/p/common-cap immutable runner and requires 3-seed smoke before formal 100-seed experiments.


## 23. E9B-4 same sender-Bytes HARD-CAP paired experiment (new evidence owner)

The user-Mac checkpoint on 2026-10-11 verified E9B-3 on SHA bcb4f2483e106dacfb0a63636e0d3a99db9eddf3: 9/9 new CBAA budget tests PASS and 168/168 full regression suite PASS. This E9B-4 block introduces only experiments.run_e9b_equal_budget (new experimental/evidence owner), with ten new tests. Unlike E9A's retrospective fixed-K transmitted-bytes observation, E9B-4 instantiates actual sender-side caps that stop the physical packet BEFORE a SEND would breach its limit. No voting, auction, state machine, network loss model, existing E2/E8 runner or historical evidence is modified.

### 23.1 Protocol-matched scenario and transmission resource

For each unique (seed, loss p, sender payload limit B) run a SINGLE deterministic generate_e0_scenario(seed,R,T) and compute a read-only full-information Sequential Greedy reference once for that seed. Invoke original coordination.simulate_democracy_hungarian_retirement in greedy_task + quarter_plurality (strictly MORE than 25% electorate, no fallback, one Vote copy, Cost broadcast once, reliable score/Commit) and original cbaa.simulate_cbaa in synchronous single-assignment local auction + max-consensus with no reliable final Commit. Each call gets its OWN independent network.SenderPayloadBudget(B), EmpiricalLatencySampler(profile, seed), and BernoulliLossSampler(seed). This is the SAME cap on physical sender APPLICATION payload Bytes for each method, but NOT necessarily the same number of emitted Bytes: packet sizes, protocol workflow, p-dependent retransmission opportunities and stop conditions differ. Both actual counters and exhausted status must be output.

The numeric p is applied to Greedy COST and VOTE loss and to CBAA per-receiver vector consensus loss, respectively. These are NOT identical stage reliability/packet sizes, nor equal airtime, delivered messages, MAC retransmission count, sender power, or task execution semantics. CBAA may have external observer consensus but NEVER a distributed Commit. The primary outcomes are therefore two separately labeled quantities: Greedy full_commit_success and CBAA full_observer_agreement, not a single claimed equivalent completion percentage. Actual local CBAA conflicting claims and unconfirmed tasks remain visible. Partial task sets retain NaN full-batch costs, never cheap-looking partial totals. Max Greedy voting rounds and max CBAA synchronous iterations are independent predeclared limits and are reported, never conflated with equal resources.

### 23.2 Exact functions, diagnostics, and immutable evidence

- parse_sender_budgets: CLI comma-separated exact integer Bytes, no float truncation.
- validate_equal_budget_config: data / E9B_INVALID_DIMENSIONS, E9B_INVALID_LOSS_GRID, E9B_INVALID_BUDGET_GRID; individual per-p/per-B owners stay network.validate_packet_loss_probability and network.validate_sender_payload_budget.
- prepare_equal_budget_output: state / E9B_OUTPUT_SOURCE_COLLISION for historical E2/E3/E4/E8/E9A or ancestor output roots; state / E9B_OUTPUT_ALREADY_EXISTS for existing non-README-only output. Never overwrite previous raw, including prior E9B.
- run_budgeted_greedy_trial and run_budgeted_cbaa_trial: separately invoke the ORIGINAL algorithm/runtime owners with a fresh ledger; no winning robot, local bid, physical packet, or Commit is chosen here.
- validate_paired_sender_accounting: contract / E9B_PAIRED_SENDER_ACCOUNTING_MISMATCH if physically emitted event counters vs original network ledgers differ or actual Bytes exceed the shared cap; contract / E9B_INCOMPLETE_OUTCOME_ACCOUNTING when task coverage fails.
- budget_stop_fields: preserve first-failure network.reserve_sender_payload / runtime / SEND_PAYLOAD_BUDGET_EXHAUSTED diagnostic owner/function/category/code, expected remaining Bytes, actual attempted packet, phase/details without rewriting it.
- build_equal_budget_pair_row: one paired per seed/p/B raw row with original identifiers, outcomes, physical sender Bytes/messages, stop diagnostics, CBAA conflicts/unconfirmed, both completed-only costs and source SHA; contract / E9B_INVALID_GREEDY_REFERENCE_COST for invalid normalizer.
- summarize_equal_budget_conditions: summary across ALL paired seeds per B/p, completion denominators include incomplete/failed trials; full task-set costs only from fully committed Greedy or fully observer-agreed CBAA.
- write_equal_budget_evidence: new root with raw/e9b_pairs_<UTC>.csv, summary.csv, manifest.json; record Git SHA, scene generation rule, R/T/seeds/p/B, individual protocol iteration limits, pinned Rady source commit/blob, row counts, CSV SHA256 and both success semantics. Raw root cannot be silently reused.
- run_e9b_equal_budget_experiment: loops paired conditions only; no method reads the other's result; no post-hoc output clipping or success-driven K selection. main: the CLI entrypoint.

### 23.3 Mac acceptance and experiment ladder

Pilot default is R=100, T=50, seeds=3, p=0,.30,.50, B=(100000,163800,184800,250000,500000,1000000) Bytes, Greedy max_rounds=100 and CBAA max_iterations=40. 3 seeds * 3 p * 6 caps = 54 distinct paired conditions (108 algorithm executions). The 163800 and 184800 levels are exploratory p0 traffic reference points known from historical E9A, not selected for successful CBAA convergence; those do not become equal actual transmitted Bytes by using a common cap.

From the repository root:
    python3 -m unittest discover -s tests -p 'test_e9b_equal_budget.py' -v
    python3 -m unittest discover -s tests -v
    python3 -m experiments.run_e9b_equal_budget --robots 100 --tasks 50 --seeds 3 --loss-probabilities 0,0.30,0.50 --budget-bytes 100000,163800,184800,250000,500000,1000000 --max-rounds 100 --max-iterations 40 --output-root results/e9b_equal_sender_budget_pilot

Do not launch 100-seed formal analysis before validating the 3-seed pilot's paired loss/seed/cap grid, actual accounting, external CBAA-only observer semantics, all incomplete results, and output SHA256. If later approved, 100 seeds * 36 p levels from 0 to .70 step .02 * 6 cap levels yields 21600 paired conditions (43200 full method calls). Such a run must use a DIFFERENT fresh output root, remain scientifically exploratory until control-message loss/reliability, on-air Bytes and stopping conditions are harmonized. The present code is a runnable experiment design, not an assertion that pilot results were executed or performance superiority was proven.


## 24. E9C-1 actual binary task announcement and end-to-end sender Byte audit

### 24.1 Information availability, original owner boundaries

This is an opt-in ZERO-LOSS real-wire first-scene experiment, NOT a replacement for existing E2/E8/E9B, NOT a different vote/auction algorithm, and NOT real ROS2/DDS/Wi-Fi PHY airtime measurement. Use the E0 seed-defined 2D Euclidean scenario, with each robot's own pose available locally. An external task announcement source sends the same task information physically to all R robots (charged), but does not allocate work. CBAA needs local per-robot costs for its own bids plus exchanged winning-bid/winner-origin vectors, not all remote Cost rows. Existing Democracy Greedy requires OTHER candidates' costs/positions to vote for the lowest cost; TASK announcements alone cannot supply those under own-pose-only availability. Never give hidden remote robot positions or global Cost data to a voter for free.

The E9C task wire is a benchmark-defined compact binary v1, not a claim to a universal robot task wire standard. There is a REAL struct.pack/struct.unpack 16-byte little-endian header (<4sHHHHI): 4-B magic TASK or POSE; version uint16; frame index uint16; frame total uint16; records in packet uint16; epoch uint32. Each TASK record (<IddIII) is 32 B: task ID uint32, x and y float64, task type uint32, priority uint32, deadline_ms uint32. E0 sends explicit task type 0, priority 1, deadline 0 (unused in E0 Euclidean cost, but still charged). Each POSE record (<Idd) is 20 B: robot ID uint32, own x/y float64. The maximum application packet is 1200 B; one TASK message contains at most 37 records. At T=50 the real two packet lengths are 1200 and 432 B, so the external TASK source emits 1632 total sender Bytes. At R=100 the optional robot-POSE exchange is 100 different source robots, each broadcasting its own 16+20=36 B packet, total 3600 Bytes; self pose is local, each broadcast has 99 receiver opportunities. Sender broadcast Bytes are counted ONCE at source, not multiplied by delivery opportunities. The original Democracy Cost rows cost 100*(16+50*8)=41600 B, whereas original CBAA full bid/winner vectors cost 100*(16+50*(8+4))=61600 B PER iteration.

democracy_mrta.task_information.encode_task_announcement creates the actual payload and fragments, decode_task_announcement validates all received frames/IDs. broadcast_task_information and broadcast_robot_positions use ORIGINAL coordination._broadcast_event plus _lossy_broadcast_deliveries for real physical SEND events and receiver-independent receipt. Missing data produces a dependency diagnostic BEFORE voting, never oracle imputation. reconstruct_local_cost_rows computes EACH robot's own cost row from its actual decoded TASK records and its locally known own position. Source scenario cost matrix is used only by experiment.require_local_source_consistency as an external contract audit, not an algorithm input in lieu of received information.

### 24.2 Controlled protocol cases

1. democracy_original_cost_rows: common physically sent TASK + each robot's OWN cost row locally calculated + ORIGINAL Cost broadcast + one Vote per task/robot with existing qualified Score, reliable Commit and retirement. No free other-robot costs. Original existing owner behavior unchanged.
2. democracy_received_peer_positions: common TASK + PAID robot POSE broadcasts. Only once every voter has actually received all R source positions can original coordination.build_received_pose_retirement_snapshot set the existing Cost view to all visible rows. This is an explicit optional input to the existing simulate_democracy_hungarian_retirement (new preknown_cost_snapshot argument, default None), and it suppresses the now-redundant Cost-row exchange. Original Greedy candidate choice, 25% qualification, Vote, Score, Commit and retirement do NOT change. No extra position/cost exchange counted twice. The original owner validate_preknown_retirement_cost_snapshot rejects forged/malformed snapshot shape.
3. cbaa_sync_single_assignment_K1/K3/K8: same task-announcement broadcast, each CBAA robot locally computes its own bid, original CBAA algorithm exchanges its full winning-bid/winner-origin vectors for K specified synchronous iterations. No remote Cost Matrix broadcast, no paid other-robot POSE exchange required. K1 is a deliberately nonconverged control. External observer agreement is not an implemented final Commit, so outcomes stay separately labeled.

The initial E9C-1 p_TASK=p_POSE=p_COORDINATION=0 experiment is deliberately ONE seed and a real information payload calibration, not a high-loss study. Nonzero transmission loss in the task/pose source owners already raises dependency if any fragment/pose fails; a dedicated bounded future step must implement sender retries, ACK, deadline and safe incomplete task announcement before a lossy full experiment. Prior E9B hard sender-cap comparisons are separate. This version does not use an end-to-end hard cap; its purpose is to establish the actual full information + protocol sender size. It does not count 802.11/UDP headers, real fragmentation below MAC, interference, retransmission control or contention.

### 24.3 Functions, first-failure diagnostics, evidence and Mac command

- democracy_mrta.task_information.encode_task_announcement: data/INVALID_TASK_ANNOUNCEMENT_SOURCE; contract/TASK_PACKET_EXCEEDS_LIMIT. decode_task_announcement: dependency/TASK_FRAMES_INCOMPLETE, dependency/TASK_RECORDS_MISSING, data/TASK_FRAME_MALFORMED or data/TASK_RECORD_INVALID. broadcast_task_information: dependency/TASK_ANNOUNCEMENT_INCOMPLETE. broadcast_robot_positions: data/INVALID_ROBOT_POSITION, contract/POSE_PACKET_INVALID, dependency/ROBOT_POSE_VIEWS_INCOMPLETE. reconstruct_local_cost_rows: data/TASK_ROBOT_COUNT_MISMATCH.
- Original coordination.build_received_pose_retirement_snapshot: dependency/INCOMPLETE_PEER_POSE_VIEWS or contract/INCONSISTENT_PEER_POSE_SOURCE. validate_preknown_retirement_cost_snapshot: contract/INVALID_PREKNOWN_COST_PROVENANCE; simulate_democracy_hungarian_retirement stays the only Greedy membership/election/Commit state owner, default packet path unaffected.
- experiments.run_e9c_real_information.validate_e9c_case: data/E9C_INVALID_CASE_SHAPE, data/E9C_INVALID_CBAA_ITERATIONS. prepare_e9c_evidence: state/E9C_PROTECTED_RESULT_ROOT, state/E9C_OUTPUT_ALREADY_EXISTS. require_local_source_consistency: contract/E9C_TASK_WIRE_COST_RECONSTRUCTION_MISMATCH. summarize_greedy_wire_phases: contract/E9C_UNKNOWN_GREEDY_WIRE_PHASE, contract/E9C_GREEDY_BYTES_MISMATCH. assemble_method_row: contract/E9C_PHASE_BYTE_SUM_MISMATCH. run_original_methods_from_local_information invokes ORIGINAL owners, no second optimizer or state machine. write_e9c_evidence writes NEW immutable actual_wire_bytes.csv and manifest.json with source SHA, SHA256, actual wire field sizes, seed, assumptions and method-specific end-to-end SEND bytes. run_e9c_real_information coordinates exactly one scenario, no global arbitration. main is CLI only.
- New tests/test_e9c_real_information.py has 11 named tests covering exact binary frames, both physical sender stages, no loss-of-data imputation, original Greedy same-winner parity with paid POSE view, distinct CBAA byte costs, first-owner diagnostics, immutable raw and SHA256.

Mac from repository root: git fetch origin; git switch experiment/e9c-real-task-wire-bytes; git pull --ff-only; python3 -m unittest discover -s tests -p test_e9c_real_information.py -v; python3 -m unittest discover -s tests -v; python3 -m experiments.run_e9c_real_information --robots 100 --tasks 50 --seed 0 --max-rounds 300 --cbaa-iterations 1,3,8 --output-root results/e9c_real_information_100r50t_seed0.

The repository connector cannot execute code on the user's Mac or fetch the locally stored pinned Rady dataset. Any new E9C experimental end-to-end measurements stay UNVERIFIED until user Mac command executes; previous E9B printed data is historical context, not substitute evidence. All existing result roots and canonical E2/E8/E9B protocols stay intact.


## 25. E9C-2: 100-seed original Cost/Vote versus original CBAA physical SEND-byte benchmark

### 25.1 Shared task, robot, and cost provenance
The user's clarified Democracy algorithm is common TASK announcement to all robots; each robot calculates only its own cost row using locally known pose; then each robot broadcasts its task COST row ONCE; all robots vote for candidates from their own actually received cost rows; quorum-qualified Score and reliable Commit are physically counted. It is WRONG to substitute E9C-1 paid-peer-position optimization for this primary original Democracy test. Both methods receive the SAME physically transmitted and decoded binary task announcement, using the existing TASK v1 16-byte little-endian header plus 32-byte TASK records: 50 tasks require 2 actual physical sender packets totaling 1632 B. E0's robot record is exactly robot ID, own x and y coordinates, not invented battery, speed or capability. Each robot knows its OWN pose locally, never other robots' poses or costs for free. Locally computed Euclidean cost rows are reconstructed ONLY from physically received tasks and local own pose, with the E9C-1 original observer-only consistency contract.

Published-family CBAA is not a global robot-state propagation algorithm: each robot needs its OWN cost row, and transmits winning bid + winner origin for each task every consensus iteration. Each iteration is 100*(16+50*(8+4)) = 61600 actual original SEND payload Bytes. Adding all remote robot poses is NOT part of published CBAA, so primary source-faithful CBAA must NOT be charged for unnecessary global robot info. To answer the explicit user request also show a separate non-standard FULL RAW ROBOT INFORMATION counterfactual where every robot physically broadcasts one existing POSE v1 packet: 16 B header + 20 B robot ID/x/y = 36 B, total 3600 sender Bytes for R100. That extra exchange is physically received and charged; it is labeled cbaa_raw_robot_information and NEVER called original/paper-standard CBAA. It produces the same original CBAA auction/observer outcome and cannot provide a hidden centralized winner.

### 25.2 Original algorithms, fixed K, loss/timing controls
For 100 paired scene seeds 0..99, R=100, T=50, p_TASK=p_COST=p_VOTE=p_BID=0, call original coordination.simulate_democracy_hungarian_retirement once per seed, greedy_task + quarter_plurality + vote_repetitions=1 + max_rounds=300. Preserve all actual emitted original Cost, Vote, Score and reliable Commit SENDs and full-Commit outcome; no alternate voting engine, shortcut optimizer or invisible cost knowledge. Call original cbaa.simulate_cbaa independently for every predeclared K in (1,2,3,4,5,6,8); preserve complete CBAA bid/winner vector transmissions, local auctions and read-only post-hoc observer agreement. No one observes network-wide CBAA state during runtime to stop robots. Full CBAA observation is NOT distributed final Commit. Each K is a SEPARATE predeclared simulation. Repeating the same CBAA outcome as an optional raw-pose-charge row never relabels this as published CBAA.

Current first sweep is p=0, not equal capped high-loss comparison. The default constant latency is an explicit deterministic 1ms per SEND with 10ms receive deadline for portable no-download CI; the alternative rady mode uses original pinned Rady latency profile, seed-bound sampler and same original loss owner. Constant mode supports correct p0 bytes but is NOT measured Wi-Fi delay. TASK and POSE payloads are actually binary packed and unpacked; original Cost/Vote/Score/Commit/CBAA bid stages are accounted as physically emitted original CommunicationEvent payload sizes, NOT fully serialized MAC/PHY/IP/ACK/wire airtime. For the primary source-faithful comparisons, physically emitted sender application payload bytes are counted ONCE per broadcast SEND, never multiplied by 99 receivers.

### 25.3 Actual per-seed and aggregate evidence
- per_seed_method_bytes.csv: one row per paired seed and method/K; mandatory task, Cost, Vote, Score, Commit, Bid/Winner, raw optional POSE bytes, messages and original real outcome. All incomplete conditions count; an interrupted run retains flushed per_seed_method_bytes.partial.csv rather than falsely claiming complete 100-seed evidence.
- summary.csv: denominator=all requested seeds; method full success of its OWN semantic (Democracy genuine Commit, CBAA post-hoc all-local observer agreement), average confirmed task count and actual sender Bytes over ALL seeds; completed-only mean separately.
- offline_min_cbaa_k_per_seed.csv: the earliest fixed K showing full CBAA observer agreement for each seed, if any. This is an OFFLINE optimistic lower-bound, NEVER a runnable decentralized termination mechanism. Missing full agreement at maximum requested K must remain explicit.
- manifest.json: exact source git SHA, 100 seeds, R100 T50, p0, K grid, E0 scene, binary task/robot schema, networking timing mode, original vs non-standard variant disclosure, file SHA256 and paired offline stats. Each output root immutable; previous E0-E9C evidence not overwritten.

### 25.4 Named function owner, diagnostics, checks
NEW experiment-only owner experiments.run_e9c_100seed_comms:
- validate_100seed_comms_config: data/E9C2_INVALID_SCENARIO_GRID, data/E9C2_INVALID_K_GRID or planning/E9C2_UNKNOWN_LATENCY_MODE.
- prepare_100seed_comms_output: state/E9C2_PROTECTED_OUTPUT_ROOT or state/E9C2_OUTPUT_EXISTS.
- select_network_sampler and create_seed_sampler: original empirical pinned data or explicitly constant event latency.
- capture_seed_information: real TASK source broadcast and local own-cost reconstruction; optional true full robot POSE broadcasts in named extra ablation.
- run_democracy_100seed_case: original election/retirement owner unchanged.
- run_cbaa_100seed_cases: original bidding owner unchanged, dependency/E9C2_ROBOT_INFO_NOT_TRANSMITTED if ablation source missing.
- require_complete_seed_pairing: contract/E9C2_PAIRED_OUTCOME_COVERAGE.
- summarize_100seed_conditions, calculate_offline_minimum_k, summarize_offline_paired_comparison: report only; no hidden agents/second consensus state.
- write_100seed_comms_evidence: immutable CSVs/sha256 and exact assumption manifest; run_e9c_100seed_comms: iterate original actors and persist every seed; main: CLI.
- tests/test_e9c_100seed_comms.py: 7 named tests for 2R2T 3-seed real event byte totals, outcomes, raw POSE extra 72 B versus published CBAA, SHA256/manifest, offline K labeling, immutable roots and data boundaries.
- GitHub Actions workflow .github/workflows/e9c_100seed_comms.yml: automated attempt at this SAME 100-seed p0 code after commit. Its success cannot be claimed until jobs pass. No network or original protocol owner modifications.

Mac local run:
    python3 -m unittest discover -s tests -p 'test_e9c_100seed_comms.py' -v
    python3 -m experiments.run_e9c_100seed_comms --robots 100 --tasks 50 --seeds 100 --first-seed 0 --cbaa-iterations 1,2,3,4,5,6,8 --max-rounds 300 --latency-mode constant --output-root results/e9c_100seed_100r50t

Optional repeat using the pinned Rady profile:
    python3 -m experiments.run_e9c_100seed_comms --latency-mode rady --output-root results/e9c_100seed_rady_100r50t


## 26. E9C-2r1 ORIGINAL CBAA ONLY correction — supersedes E9C-2 nonstandard ablation (2026-10-11)

### 26.1 User-confirmed scope and strict admissible method set

The user's explicit correction is: **USE ORIGINAL CBAA, DO NOT USE the mistaken CBAA + all robots' raw-information transmission variant**. This section supersedes only the extra cbaa_raw_robot_information_K option and reporting within historical Section 25. Historical E9C-2 original-source measurements remain valid and immutable. From this correction onward the ONE comparison owner experiments.run_e9c_100seed_comms admits ONLY the following method rows:
- democracy_task_cost_vote: common physically binary TASK announcement, own Cost rows computed locally, original once-per-owner COST broadcast, one Vote per active voter for chosen task, original Score announcements, reliable Commit and executor retirement. Existing pure25 election/optimizer owner completely unchanged.
- cbaa_original_local_bid_K{K}: the original E8 published-family **synchronous single-assignment CBAA** auction/maximum-consensus reference implementation for each prespecified fixed K. Every agent locally computes its own bid from its own task-cost row and transmits its current bid/winning-origin vector in each round, **without broadcasting raw robot locations, global robot capabilities, or other private Cost rows**. No new derived winner or alternative algorithm is introduced. Important E8 restrictions STILL APPLY: synchronous complete network, fixed K, explicit origin ID, post-hoc observer agreement not a distributed Commit/stop. Do not call it a byte-identical reproduction of every packet in the 2009 paper.

The old optional CLI flag --no-cbaa-raw-robot-info is REMOVED; there is no raw-robot-info variant to enable OR disable. The physical broadcast of robot POSE packets is REMOVED from the E9C-2r1 100-seed runner; the baseline common TASK framing is retained. Thus 100R50T K=(1,2,3,4,5,6,8), seeds 0..99, p=0, max_rounds=300 creates exactly 100*(1+7)=800 **original-only** raw rows, eight summary method conditions, and 100 paired offline earliest-K rows. A full-original protocol run is not equivalent to the extra synthetic raw-robot-data intervention. Existing E9C-1 optional pose information mode remains in its earlier independent experiment; it is NOT part of this corrected run.

### 26.2 Information and Bytes contract

Common information: 50 tasks physically sent as two actual binary TASK v1 packets totaling 1632 sender application Bytes, received and decoded by every robot. Local robot ID/x/y is own state and is not a SEND; neither method obtains full other-robot state. The original Democracy **physically** emits 100 original Cost packets of 416 sender Bytes each (50 float64 values plus 16-B original modeled header), then physically emitted Vote, Score, Commit with prior sender payload accounting. The original CBAA physically emits exactly 100 bid/winner-origin vector packets of 616 modeled sender Bytes each per predeclared iteration, with no extra robot info packets. A broadcast is counted once at the sender, not 99 times. TASK is actually binary serialized and received, while the original Cost/Vote/Score/Commit/Bid stages are accounted by their original communication-event payload sizes, not separately serialized full IP/802.11 frames. The zero-loss deterministic one-ms latency mode and optional Rady empirical latency mode remain documented; no packet loss and no on-air wireless PHY claim.

Evidence root remains immutable, outputs remain per_seed_method_bytes.csv, summary.csv, offline_min_cbaa_k_per_seed.csv, manifest.json with SHA256 and source Git SHA. Metadata now explicitly records no_optional_nonstandard_cbaa_variants=true, no_peer_robot_position_broadcast=true. No cbaa_raw_robot_information_K row, no raw robot POSE bytes, no incorrect offline-raw-CBAA bound. The historical 1500-row pre-correction dataset remains as immutable prior evidence but is not the corrected 800-row raw analysis.

### 26.3 Ownership / diagnostics / acceptance

ONLY the existing experiment evidence owner experiments.run_e9c_100seed_comms is changed:
- capture_seed_information now only broadcasts TASK and reconstructs each own Cost row. No optional peer pose transport or synthetic CBAA data required.
- run_cbaa_100seed_cases now invokes the unchanged cbaa.simulate_cbaa for each fixed K and produces ONLY cbaa_original_local_bid_K rows.
- require_complete_seed_pairing rejects ANY unexpected method or nonstandard variant using the existing experiment / require_complete_seed_pairing / contract / E9C2_PAIRED_OUTCOME_COVERAGE diagnostic with explicit expected/actual. No new wrapper or alternate CBAA state machine.
- summarize_100seed_conditions, calculate_offline_minimum_k, write_100seed_comms_evidence and run_e9c_100seed_comms eliminate nonstandard input/output fields and adapt expected row coverage.
- main removes the obsolete optional robot-information flag. Original algorithm and transport owners unchanged: democracy_mrta.cbaa.simulate_cbaa / auction / consensus / physical SEND; coordination.simulate_democracy_hungarian_retirement; task_information.broadcast_task_information; all previous first-failure boundaries remain intact.
- tests/test_e9c_100seed_comms.py now tests original-only 3-seed rows, explicitly rejects any cbaa_raw_robot_information_K row, ensures peer POSE sender Bytes ==0, checks 8-method deterministic 100-seed shape via manifest, SHA256, no-overwrite, and all existing diagnostics. GitHub Actions .github/workflows/e9c_100seed_comms.yml runs dedicated/full regression and 100-seed source-only experiment with a distinctly named artifact.

Execute on Mac or trusted CI:
    python3 -m unittest discover -s tests -p 'test_e9c_100seed_comms.py' -v
    python3 -m unittest discover -s tests -v
    python3 -m experiments.run_e9c_100seed_comms --robots 100 --tasks 50 --seeds 100 --first-seed 0 --cbaa-iterations 1,2,3,4,5,6,8 --max-rounds 300 --latency-mode constant --output-root results/e9c_original_cbaa_only_100seed

Do not claim results from this new executable SHA until new CI run or user Mac execution confirms them. The earlier 100-seed p0 results for original method rows SHOULD be numerically identical at the same seed/K/timing assumptions; verify by actual re-run, do not assume a pass. Future fairness research remains separate (actual serialized Cost/Vote/CBAA fields, paid retransmissions and distributed termination/Commit under packet loss).


## 27. E9D-1 opt-in original CBAA iterative local-evidence convergence mode (not fixed K experiment)

### 27.1 Purpose and epistemic boundary

The user wants the ORIGINAL published-family CBAA auction/consensus process to iterate naturally with rising independent per-receiver packet loss, without trying manually fixed comparison grids K=1,2,3,6. Source: Choi, Brunet and How, IEEE T-RO (2009), DOI 10.1109/TRO.2009.2022423, original CBAA Section III auction+max consensus. The existing FULL bidding/consensus state update, winning-bid+origin vector physical SEND, original per-receiver Bernoulli packet loss, score utility, deterministic tie-break, single-task assignment, original fixed-K mode and original E2/E8/E9B/E9C experiments MUST remain unchanged.

The original paper proves convergence under its stated communication/score assumptions; it does NOT provide this project's existing runtime with free global all-agent observer knowledge. Thus E9D's new opt-in stop_mode=local_certification is an explicitly DISCLOSED source-based **local-receipt convergence monitoring and simulation scheduling adaptation**, NOT an unsupported claim that CBAA includes a reliable all-agent stop/Commit protocol. Each node's readiness comes exclusively from its own CBAA state and physically received peer messages, never an external observer assignment. Simulation scheduling stops when ALL independent local readiness flags are true, without feeding a central winning bid or early stopping decision back to any agent. This aggregate stop represents an OPTIMISTIC global-halt assumption: it does not include real distributed stop coordination/ACK signaling. Results are application-sender-Bytes LOWER BOUNDS for an implementation that would need a termination handshake. Compare CBAA POST-HOC observer agreement to Democracy actual reliable Commit separately.

### 27.2 Autonomous local convergence certificate from received messages

New named original owner function cbaa_local_convergence_certified tests a node's OWN max-consensus vector: every task has a positive winning bid and a valid uniquely owned robot origin; its own single-task assignment matches the winning origin, and every physically received cached OTHER robot snapshot must match this bid/winner vector and must claim exactly the task the matching origin indicates (or None for unassigned peers). Each cached receipt must be from an iteration STRICTLY AFTER the local node's most recent bid/claim update. Missing peers, stale receipts, disagreement, incomplete task coverage, conflicting assignments and dropped messages can NEVER trigger readiness. This avoids the dangerous fallacy "no messages arrived for a while therefore consensus" under packet loss. Robots still transmit the unchanged original full-vector message while certification is being established for the full team; each sender physical packet is counted. Receiver-specific loss may delay termination; if a finite safety guard is reached without every node's local proof, stop_reason=iteration_safety_guard, NOT "converged". This guard is a runtime safety bound, not manually selected K for a successful result.

New owner function update_cbaa_received_peer_evidence caches only states returned by the ORIGINAL exchange_cbaa_consensus_packets receiver inbox, with iteration number, no global scenario cost or observer inspection. Self-on-wire unexpectedly arriving fails contract/CBAA_SELF_ON_WIRE. validate_cbaa_stop_mode accepts fixed (default, all existing behavior) and local_certification; invalid input fails data/CBAA_UNKNOWN_STOP_MODE. The original simulate_cbaa remains the SINGLE auction/consensus state owner, retains original iteration loop and original E8 fixed mode default, and in opt-in mode updates only per-node peer evidence/last-local-change counters and stops after all independent locally certified flags. No second CBAA state machine, no fabricated Vote or Commit, no new physical SEND or packet content. A CBAAResult adds backward-compatible default fields stop_mode, stop_reason and locally_certified_count for diagnostics (legacy fixed mode preserves old outcomes and bytes). For a finite send-budget denial stop_reason=sender_budget_exhausted has priority and original per-sender budget accounting is intact.

### 27.3 Acceptance and limitations

tests/test_cbaa_local_convergence.py covers no-loss two-robot proof, initial collision and rebid, missing/stale/contradicting peer evidence, p=1 loss guard, reproducible packet loss, original physical accounting, observer one-call-after-run, budget failure, invalid mode and legacy fixed mode. Only task/bid/score original CBAA messages are modeled; no new robot position propagation, no centralized arbitration or hidden oracle. The aggregation of all local ready bits by simulation scheduling is NOT a genuine distributed halt. Real fully decentralized termination at nonzero loss would need a separate paid handshake in its true owner as a future bounded change. The safety guard can obscure an empirical high-loss limit: report guard reached as a distinct category, never conclude a theoretical p upper bound. This E9D-1 change alone does not run the loss sweep; E9D-2 adds separate experiment evidence owner and Mac CLI.


## 28. E9D-2 paired natural local-certificate CBAA / original Democracy rising-loss experiment

### 28.1 Intent, scope, source methodology and not-misrepresented outcomes

The user explicitly asks to dispense with K=1,2,3,6 tuning: run ORIGINAL CBAA iteratively until its own physically received peer-information convergence evidence meets E9D-1 Section 27, then compare actual transmitter application payload Bytes and sampled packet-loss failure region with ORIGINAL Democracy Cost+Vote quorum. Original CBAA's published Section III auction and max-consensus owner remains unchanged; NO extra raw other-robot pose transmission, centralized task winner, hidden full cost sharing or CBBA bundle planning is allowed. E9D-1 local-evidence monitor is an engineering adaptation, not a claim of a real paid fully decentralized all-stopped handshake. Simulation scheduler stops when all R independent readiness flags turn true (optimistic free global scheduling), so the measured CBAA Bytes are a LOWER BOUND for a complete system with termination notifications. This asymmetry and the lack of CBAA distributed Commit must appear prominently in every result.

Every seed uses the SAME physically serialized common 50 TASK packets as E9C (TASK v1 header+32 B/task, split into <=1200-byte real source physical broadcasts). TASK ANNOUNCEMENT IS MODELLED AS GUARANTEED / p_task=0 and charged once per sender physical broadcast (1632 B at 50 tasks), NOT reissued across repeated voting rounds. Locally computed own Cost rows derive only from actually decoded TASK records and own robot ID/x/y pose. Coordination stages are lossy with independent per-RECEIVER Bernoulli p for original CBAA full Bid/Winner vectors, while original Democracy uses the SAME p for its one-time Cost broadcast and each one-shot Vote unicast. Democracy's qualified Score and Commit remain their existing reliably modelled control channel stages, and full success means ACTUAL reliable Commit of all 50 tasks. CBAA success reports TWO distinct outcomes: final EXTERNAL observer all-local bid/winner agreement, and *all local-received-evidence convergence certificate flags*, each computed from physically delivered per-node data; neither is a final distributed Commit. Under p>0 no cost or pose knowledge is gifted to any algorithm.

### 28.2 Fixed scientific axes, natural stop, guard and protocol totals

Default: R=100, T=50, seeds=100 beginning seed 0. Loss vector ascending 0,.10,.20,.30,.40,.50,.60,.70,.80,.90,.95, editable as --loss-probabilities comma-separated values. The user DOES NOT supply CBAA K per test. Each CBAA algorithm proceeds iteratively until every robot's own local certificate is true OR a non-convergence safety round limit (default 160) is reached; this limit is NOT "converged" and MUST appear as stop_reason=iteration_safety_guard. The Democracy still has its own finite max 300 original retry epochs; reaching it with pending tasks is democracy_round_guard, not proof of theoretical loss impossibility. Loss p=1 is a valid optional adversarial endpoint and cannot magically complete node-to-node CBAA agreement (R>=2) without physically delivered packets.

All real original coordinator SENDs are counted once at the sender (not R-1 receiver multiplication): 50T TASK common 1632 B; original Democracy Cost row once per robot, original Vote/Score/Commit physically emitted event payload; CBAA full bid/winner vector once per robot per REAL iteration, including when no peer receipt occurred. Failed physical receiver deliveries COST sender Bytes. No artificial "free stop" control bytes are added; instead the optimistic aggregate scheduler limitation is honestly labelled. Original Cost/Vote/CBAA messages still use previous modeled event payload lengths, while Task announcement is genuinely packed/unpacked. PHY/MAC/IP/ACK/header retry airtime and full 2009 original transport envelope are NOT measured.

### 28.3 Independent owner boundaries and diagnostic contracts

The ONLY experiment/evidence owner is NEW experiments.run_e9d_natural_loss:
- validate_e9d_natural_loss_axes: data/E9D_INVALID_SCENARIO_OR_GUARD, data/E9D_INVALID_LOSS_GRID; planning/E9D_UNKNOWN_LATENCY_MODE; reuse original network.validate_packet_loss_probability for [0,1].
- prepare_e9d_output_root: state/E9D_PROTECTED_OUTPUT_ROOT or E9D_OUTPUT_ALREADY_EXISTS; never rewrite prior E2-E9D, even on interruptions.
- run_e9d_democracy_loss_case: invoke original coordination.simulate_democracy_hungarian_retirement with greedy_task + quarter_plurality, vote_repetitions=1, p_cost=p_vote=p, task binary INFO already delivered, original phase sender Bytes and actual reliable Commit. Does NOT alter owner voting/quorum/retirement.
- run_e9d_original_cbaa_loss_case: invoke ORIGINAL cbaa.simulate_cbaa with stop_mode=local_certification and max_iterations=safety guard, original p loss per physical consensus receiver and per-peer local receipt evidence; report both external observer state and all_local_evidence_certified or iteration_safety_guard. Does not check observer agreement inside runtime.
- validate_e9d_physical_accounting: contract/E9D_PAIRED_METHOD_MISMATCH or E9D_SENDER_BYTES_OR_DELIVERIES_MISMATCH, first physically paid SEND+delivery accounting check and exactly two original method rows per seed/p.
- summarize_e9d_loss_results: all seeds in denominator, method-disjoint success semantic; mean sender Bytes, rounds, tasks, guard counts and separate CBAA observer agreement.
- calculate_e9d_empirical_limits: only highest TESTED p with all-seed/any-seed observed success, and first tested decline; flag guard censoring; NEVER call this a theoretical supremum loss.
- write_e9d_final_evidence: immutable raw/summary/manifest (SHA256/source Git SHA plus assumptions and sampled limits).
- run_e9d_natural_loss: one experiment orchestrator, physically emit the common task source once per paired seed, independently replay each method at each fixed LOSS (NOT fixed K), flush raw two-row pairs immediately, output completed summary; main: CLI owner.

Reuses established E9C original experiment network/timing and task information owners capture_seed_information/select_network_sampler/create_seed_sampler, not duplicate information dissemination. Reuses established original Greedy stage-byte counting summarize_greedy_wire_phases, not duplicate Greedy state machine.

NEW tests/test_e9d_natural_loss.py: eight tests covering original packet accounting/paired methods, no artificial success from p=1 CBAA silence, true no-loss local evidence and original Greedy Commit, separate observer/guard summary, exact SHA256/manifest, protected outputs, typed grid validation, and first contract failure diagnostic. New GitHub Actions .github/workflows/e9d_natural_loss.yml runs focused plus whole suite then a short R5T3 smoke p=0,.5,1.0 without running the full expensive 100-seed sweep in CI.

### 28.4 Actual run on user Mac

Once new branch has passed focused and full regression, run pilot:
    python3 -m experiments.run_e9d_natural_loss --robots 100 --tasks 50 --seeds 3 --loss-probabilities 0,0.30,0.50,0.60,0.70,0.80,0.90,0.95 --output-root results/e9d_pilot_100r50t_3seed

Formal:
    python3 -m experiments.run_e9d_natural_loss --robots 100 --tasks 50 --seeds 100 --loss-probabilities 0,0.10,0.20,0.30,0.40,0.50,0.60,0.70,0.80,0.90,0.95 --cbaa-safety-round-limit 160 --democracy-safety-round-limit 300 --output-root results/e9d_formal_100r50t_100seed

All files go only to brand-new results/e9d_* roots. raw per_seed_loss_method.csv includes both original method rows per seed/p, task/cost/vote/score/commit/bid Bytes, delivered/dropped, rounds, current actual Commit or local-CBAA certify and post-hoc full observer, explicit stop_reason and guard; summary_by_loss.csv aggregates all seeds and guard-censored cases; manifest.json has reproducible full SHA and Sha256. When stopped during the run, per_seed_loss_method.partial.csv is flushed and can be inspected but the current version does not automatically resume; restart in a NEW root or smaller seed partition, never overwrite partial. A future resume protocol is another bounded evidence-owner concern.

E9D-2 is first a short smoke and user-Mac 3-seed pilot, NOT a claim that 70%-90% packet loss yields full consensus. If 160-round guard masks high-p results, rerun the SAME methods with a clearly different, explicitly documented guard and distinct output root; DO NOT reinterpret guard as a physical packet-loss impossibility. Zero packet loss vs higher loss may also differ due the necessary Cost single-send and CBAA repeated bid transmission, which is the actual algorithmic robustness comparison under the specified controls.


## 29. E9E-1 loss-axis density presets: unchanged E9D algorithm and evidence contract

### 29.1 Purpose and boundaries

The user wants denser experimentally sampled curves near the Democracy abrupt drop around 50%-60% and CBAA high-loss guard censoring near 90%-99%, before posting independently verified figures and data into README. E9E-1 changes only the experiment loss sampling grid, NEVER the original CBAA auction/consensus or peer-local certificate, original Democracy Cost/Vote/Commit, network sampler or any packet sizes.

The one named data owner experiments.run_e9d_natural_loss.resolve_e9d_loss_grid_profile(profile, explicit_losses) builds an ascending unique integer-percent-based probability tuple. Named profiles:
- legacy: EXACT original 11-point E9D-2 default (0,.10,.20,.30,.40,.50,.60,.70,.80,.90,.95). Unchanged existing CLI defaults.
- transition: 5%-spaced global baseline 0 to 95% PLUS every 1% in 40..65% inclusive: 40 unique levels.
- tail: 5%-spaced global baseline 0 to 95% PLUS every 1% in 85..99% inclusive: 32 unique levels.
- dense: union of transition/tail: 52 unique levels (base 5% plus both high-density bands). For 100 paired seeds and 2 original algorithms exactly 52*100*2=10400 method runs. Every profile contains p=0 baseline.

CLI --loss-grid-profile accepts legacy,transition,tail,dense; former --loss-probabilities comma-list stays available. With no selection existing behavior remains byte-for-byte identical; explicit probabilities in legacy mode override the default as before. Explicit --loss-probabilities together with nonlegacy profile is rejected by TRUE data owner resolve_e9d_loss_grid_profile, category=data, code=E9D_CONFLICTING_LOSS_GRID_CHOICES, expected named profile OR explicit list, actual both. Unknown programmatic profile fails at the SAME owner/function/data/E9D_UNKNOWN_LOSS_GRID_PROFILE. No silent precedence and no duplicate experimental state machine. Existing validate_e9d_natural_loss_axes retains final probability checks.

### 29.2 Experimental controls and runnable Mac command

Keep 100R/50T, 100 paired seeds, original independent per-receiver Bernoulli packet loss, original true Democracy Commit and original CBAA external observer agreement versus peer-local certification separate, TASK announcements guaranteed/charged, original CBAA optimistic simulation aggregate stop, and default CBAA safety guard160 and Democracy retry guard300. A guard-limited failure is censored, NOT mathematical impossibility. A 100/100 empirical success count is a finite-sample fact, NOT general guaranteed reliability. Do not interpolate between sampled p levels as if directly measured. Reusing old results in README without noting original coarser sampling is forbidden.

3-seed pilot (52 p values):
    python3 -m experiments.run_e9d_natural_loss --robots 100 --tasks 50 --seeds 3 --loss-grid-profile dense --output-root results/e9d_e9e_dense_pilot_3seed

100-seed formal (10400 original protocol simulations):
    python3 -m experiments.run_e9d_natural_loss --robots 100 --tasks 50 --seeds 100 --loss-grid-profile dense --cbaa-safety-round-limit 160 --democracy-safety-round-limit 300 --output-root results/e9d_e9e_dense_formal_100seed

Smaller focus datasets: transition has 40 p levels; tail has 32. Each independently produces immutable E9D per_seed_loss_method.csv, summary_by_loss.csv, manifest.json with original per-seed raw and provenance; a fresh output root is mandatory. Figure generation and README update occur ONLY after formal evidence verification in a separate bounded change.

### 29.3 Named functions, diagnostic and tests

Changed experiments/run_e9d_natural_loss.py ONLY for resolve_e9d_loss_grid_profile (experiment data owner) and CLI main (arguments only); run_e9d_natural_loss and original algorithm owners are unchanged. NEW tests/test_e9e_dense_grid.py has 6 named tests for legacy parity, 52/40/32 profiles, conflict/unknown first-failure diagnostics and original canonical validation. docs/CHANGE_CONTINUITY.md documents this change in the same commit. No new dense numerical results are claimed until local execution.


## 30. E9E-2 read-only SVG figure derivation + README publication boundary

### 30.1 User intent and scientific constraints

The user requests denser plotted sampled Packet Loss levels and later direct publication of REAL tested data and figures into the repository README after they supply complete local run outputs. This is a SEPARATE experiment-reporting concern. The figure owner MUST NOT rerun simulations, alter raw results, claim unmeasured points or auto-publish incomplete/pilot/guard-censored results as universal reliability thresholds. Original E9D-2 + E9E-1 algorithm and input sampling remain unchanged. The formal dense profile contains 52 measured p levels; global plots place x at exact numeric p and draw markers for each measured p; line segments between adjacent independently measured p are visual guides, NOT evidence of experiments at intermediate values. No smoothing/regression/extrapolation is permitted.

Original E9D full Commit (Democracy) and CBAA per-robot local-receipt certificate are DISTINCT success metrics. CBAA external post-hoc observer assignment agreement is shown separately from local certificate on its own chart, especially at high packet loss, to avoid reporting a 160-round stopping guard as task inconsistency. A safety-guard hit is a censored runtime limit, not a mathematical algorithm upper bound. CBAA simulator aggregate all-ready halt is optimistic and has no paid distributed termination handshake. The graph title/subtitle/footnote MUST disclose these nuances. Every sender-byte chart counts physically emitted application payload even for incomplete attempts and uses explicit logarithmic MB scale, NOT bandwidth or actual Wi-Fi airtime.

### 30.2 One evidence/reporting owner, no duplicate algorithm state

New pure experiment reporting owner experiments.plot_e9d_results has named functions and first diagnostic boundaries:
- load_e9d_plot_evidence: load immutable E9D raw per_seed_loss_method.csv, summary_by_loss.csv and manifest.json; dependency/E9E_PLOT_EVIDENCE_MISSING for incomplete/missing run; data/E9E_PLOT_EVIDENCE_UNREADABLE for malformed CSV/JSON.
- verify_e9d_plot_provenance: contract/E9E_PLOT_SHA256_MISMATCH for changed raw/summary; contract/E9E_PLOT_RAW_SUMMARY_CONTRACT for incomplete/duplicate paired seed*p*method cells, missing source SHA, mismatching raw robots/tasks, mismatching summary values or differing success semantics. The original experiment owner summarize_e9d_loss_results is used as an independent existing report-summary recomputation, NOT a separate result state machine.
- prepare_e9d_figure_root: state/E9E_PLOT_OUTPUT_NOT_EMPTY to avoid destructive regeneration over historical plots; no source/raw writes.
- wilson_interval: pure pointwise binomial 95% Wilson interval from actual full success count and N of seeds; no causal claims.
- build_e9d_plot_series: pure CSV projection for actual measured p, no smoothing.
- render_e9d_svg_chart: one reusable native SVG line/marker renderer, exact x position, axis/tick labels, log y option, explicit legends/disclaimers.
- e9d_chart_traces: pure legend/plot-series selection that cannot relabel an observer-success count as a real Commit.
- e9d_log_ticks: original positive payload number scaling; data/E9E_NO_POSITIVE_BYTES for invalid zero-byte-only data.
- compose_e9d_figures: generate up to SIX SVGs named e9d_full_success.svg, e9d_democracy_transition.svg (40%-65% if >=2 measured points), e9d_cbaa_agreement_vs_stop.svg, e9d_cbaa_high_loss_zoom.svg (85%-99% if >=2 actual points), e9d_sender_payload.svg (logarithmic MB), e9d_guard_censoring.svg (two method guard-hit curves). Zooms NEVER interpolate new point data.
- write_e9d_figure_evidence: create only new SVGs and figure_manifest.json with source SHA, raw/summary hashes, precise measured loss list, figure names and SHA256. Never edits README or old raw.
- plot_e9d_results: read-only orchestrator after verification, then state gate, figures and printed paths; main: CLI only.

New tests/test_e9e_figures.py: six tests use actually run tiny E9D evidence, render parseable standalone SVG and verify each SHA, both zoom scopes, refuse missing evidence, refuse raw tampering, refuse forged summary even with updated SHA, refuse output overwrite and confirm raw unchanged. No heavy renderer dependency required (Python stdlib emits SVG). New workflow .github/workflows/e9e_dense_figures.yml runs full original regression and E9E tests, small dense 5R/3T 2-seed smoke and SVG generation, uploads only small smoke evidence. Formal 100R/50T 100-seed results NOT claimed until completed on Mac and uploaded by the user.

### 30.3 Publication boundary and commands

README section has BEGIN/END markers for future E9E verified formal figure/result material, but initially says PENDING and contains NO fabricated numbers/images. User should run formal E9E-1 dense study in unique results/e9d_* root with 100 seeds, then:
    python3 -m experiments.plot_e9d_results --run-root <YOUR_FORMAL_RESULT_ROOT>
The plot command refuses incomplete raw and any summary/manifest inconsistency; exports figures/ SVGs and figure_manifest.json within that result directory. User then uploads the result directory as ZIP including original raw/summary/manifest and figures for assistant verification. Once received, update the REAL README result block inside markers, commit the verified SVG files to docs/figures/e9e_dense and cite them via normal relative Markdown image links; include 100 seeds, p grid, SHA and numerically grounded results, separate success semantics, specific empirical guard censoring and Bytes. Publishing is a separate bounded change with canonical+continuity updates and exact image/raw SHA. Never publish charts based on old 11-point study as new 52-point results or on pilot alone.


## 31. E9E-3 provisional console-log preview on README; formal raw-data publication remains blocked

### 31.1 Evidence received and what is still absent

The user provided the terminal stdout transcript of the E9E-1/E9E-2 Mac 100R50T 100seed dense 52-point formal job, including E9D_PROGRESS seeds=100/100 cells=5200, E9D_RESULT for 104 method/loss cells, E9D_SOURCE_SHA=2808fa12fcd89aa8c2251e7e6438312a95a9df8f and E9E_PLOT_VERIFIED_SOURCE_SHA of that same source, reporting a successfully completed on-Mac raw/summary validation and six SVGs. This is valuable SOURCE-IDENTIFIED TERMINAL EVIDENCE, but the COMPLETE ORIGINAL OUTPUT ZIP, 10400 per-seed raw cells, summary CSV, manifest SHA256, figure manifest and six source-generated SVGs have NOT been uploaded into this conversation or stored in the repo. The assistant MUST NOT claim to have independently inspected these original artifacts.

The original Section 30 formal-block gate remains in force: the HTML comment bounds E9E_DENSE_RESULTS_BEGIN and E9E_DENSE_RESULTS_END in README still indicate PENDING VERIFIED FORMAL RESULTS. They must NOT be replaced with terminal-only values. The user also requested seeing charts and selected numbers on README now; Section 31 therefore permits a separate, conspicuous TERMINAL-LOG-ONLY PREVIEW section AFTER the unchanged formal gate, with no implication of independently verified/raw-complete paper evidence.

### 31.2 Preview asset origin, correctness and interpretation

New static preview assets in docs/figures/e9e_dense:
- log_preview_success.svg: 52 actual console-reported sampled probabilities; Democracy actual Commit and CBAA optimistic per-robot local certification, separately labeled.
- log_preview_democracy_zoom.svg: original discrete 40..65% console-reported values, no fabricated intermediate grid points.
- log_preview_cbaa_tail.svg: local certification and actual guard-hit counts at 85..99%; cannot be represented as a task-agreement failure.
- log_preview_sender_bytes.svg: source-reported mean application SEND Bytes converted to MB (1e6 decimal) with logarithmic Y axis, including incomplete/guard-limited transmissions.
- log_preview_summary_rounded.csv: 52 source-reported conditions with exactly two original algorithms and 100 Seeds each, printed mean Bytes ROUNDED TO WHOLE BYTE solely for preview rendering. This is a NEW DERIVED RECAP, not the 10400-row original experiment raw or verified official summary. The original terminal excerpt has the exact one-decimal mean byte values in the console output, and the README selected table uses them rounded only to 0.1 kB.

Original 52 p levels: 5%-spaced base 0..95, plus 1%-spaced 40..65 and 85..99, no duplicate. Source-reported finite sample thresholds are Democracy first not-perfect p=48%, highest all 100 successful p=50% (nonmonotonic at p48,49,50), p52 91/100, p53 65/100, p54 14/100, p55 0/100. Original CBAA per-node certificate p91 100/100, p92 97/100, p93 87/100, p94 48/100, p95 2/100; CBAA later guard exhaustion is CENSORED, not proof of observed absence of task agreement. At p30 each method reports full success by DIFFERENT semantics; mean B=164750.1 Democracy versus 838160.0 CBAA, hence 80.34% less *modeled emitted application sender Bytes* for Democracy. Do not claim mathematical loss threshold, identical Commit semantics or accurate Wi-Fi airtime.

Preview vector images are small static renderings from the exact printed summary. They are NOT the six formally validated source SVGs; the user must still upload e9e_dense_formal_evidence.zip for the Section 30 canonical verified formal README chart/result promotion. Once the verified real manifest and all 10400 raw method records arrive, independently run the existing experiment owner verification from Section 30, compare summaries with provisional log numbers, remove/relabel provisional figures as appropriate, copy all SIX source-generated SVGs into docs/figures/e9e_dense/formal, replace the formal result marker and record the exact source/chart SHA256 and publication commit. Never overwrite original prior experiments or change original algorithm behavior as part of publication.

### 31.3 Responsibility, files and unchanged diagnostics

This E9E-3 stage changes ONLY README.md, new static preview image/CSV files in docs/figures/e9e_dense, docs/EXPERIMENT_PROTOCOL.md and docs/CHANGE_CONTINUITY.md. No code, owner, function, network, optimizer, stop rule, diagnostic contract or physical packet model is changed. The user-facing log snapshot is not a replacement for original result validation; the established experiments.plot_e9d_results.load_e9d_plot_evidence and verify_e9d_plot_provenance continue owning original data dependency/E9E_PLOT_EVIDENCE_MISSING and contract/E9E_PLOT_SHA256_MISMATCH / E9E_PLOT_RAW_SUMMARY_CONTRACT. No bypass, dummy manifest or forged per-seed raw is introduced. Publication of unverified formal reports is intentionally blocked. After full evidence is provided, do a separately bounded authenticated formal publication.


## 32. E9E-4 VERIFIED formal 52-point / 100-seed results published to README (supersedes provisional Section 31 status)

### 32.1 Independent complete-original evidence acceptance

On 2026-10-11 the user supplied the originally generated e9e_dense_formal_evidence.zip, not merely terminal aggregate text. Its contents were independently inspected in a local container: 2,199,690-byte per_seed_loss_method.csv (10,400 original distinct paired method rows), 14,927-byte summary_by_loss.csv (104 original p/method rows), original run manifest.json, original figure_manifest.json, and all six original source-generated SVGs. The 100 seeds 0..99, 52 unique p, 2 ORIGINAL methods coverage is complete with no duplicates. All per-sender application Byte phase sums and physically recorded coordination delivered/dropped arithmetic were verified. Each of the 104 summary entries was recomputed from its own original 100 seed records and found consistent within numerical precision.

Original source executable SHA is 2808fa12fcd89aa8c2251e7e6438312a95a9df8f. Original independently SHA256-verified raw CSV e2337a157b96593d441c143b19d5b2b9b1c64604b4bc0a651da1e566c060c727; summary CSV 3408ccd1978ca66d58ff4dd195d3b31b8e2805c798e1adfa872d5d45ea6706db; original run manifest SHA256 eaffa7a9be1dfe034443bc8004280689f7b3d67228b57bbe0feb1fc4c8735876; original figure manifest SHA256 3292484251ff11157c191029c06822c77526875f97ce667fa394751c08691e31. All six original SVG SHA256 hashes were independently verified against original figure_manifest.json and XML-parsed before publishing. The results are independently reproducible from the original uploaded archive and are NOT mere reconstructions from console output.

### 32.2 Exactly reproduced original source SVGs and summary on GitHub

One-time guarded GitHub Actions publish workflow independently checks the original summary SHA256 and exact 104-row p-method coverage, reuses the ORIGINAL reporting owner experiments.plot_e9d_results.build_e9d_plot_series + compose_e9d_figures and refuses publication unless each regenerated source SVG SHA256 EXACTLY matches the original verified Mac figure_manifest. The workflow completed successfully as GitHub Actions run 38146438737, resulting in figure publication commit d0311a2ef961c281d4c27b70267ecaffdaea5763. Git tree source Git Blob SHAs of all SIX committed originals matched those independently computed from the local ZIP byte for byte, with unmodified original widths, legends, actual measured probability points and numeric data:
- docs/figures/e9e_dense/formal/e9d_full_success.svg SHA256 3b923f849e045d74efcedabb6b122b1e0e95e071b7ef9f882c1b19c9b55c9697
- docs/figures/e9e_dense/formal/e9d_democracy_transition.svg SHA256 84a403ccd9092e0292f4a4340741c3f24363e97c881526366a96b17eca8ab51f
- docs/figures/e9e_dense/formal/e9d_cbaa_agreement_vs_stop.svg SHA256 a70e7db23fcfb1f3c778e0246a23e311d1ba44ec035684be26b61b2e1c4c1aad
- docs/figures/e9e_dense/formal/e9d_cbaa_high_loss_zoom.svg SHA256 23dee05effe7afa2d8808fc1465b2bf1b7fab9a1943a7726e3bcbf12259a3a92
- docs/figures/e9e_dense/formal/e9d_sender_payload.svg SHA256 b6b1c0f637c1dfd5476a3e6c9e76212c3cf4b2284310ebcd918e91d8de780b5d
- docs/figures/e9e_dense/formal/e9d_guard_censoring.svg SHA256 3343e63cbbd45dec8ae21fda29125b61da6ec49a32b41585b89cca333172d654

The exact original 104-row summary_by_loss.csv is committed at docs/figures/e9e_dense/formal/summary_by_loss.csv with byte-identical original Git Blob SHA cd26a0f1ef9d8afc18daf8e79a74b4e1b7e19611, SHA256 3408ccd1978ca66d58ff4dd195d3b31b8e2805c798e1adfa872d5d45ea6706db. Its recorded publication_manifest.json preserves original 104-row summary SHA and original 10,400-row per-seed RAW SHA, all six SVG hashes, source experiment SHA, and scope qualifiers. The original full raw 2.2MB file remains in the user's uploaded ZIP and is NOT synthesized from aggregate data or falsely claimed stored in GitHub repo. User may submit the same ZIP for source-level reproduction later; the report can be peer-reviewed with the original per-seed input.

### 32.3 Numerical results and scientific success semantics

At 30% packet loss: Democracy original Cost+Vote -> actual reliable full Commit in 100/100, mean emitted sender application payload 164750.08 B; source-family CBAA with optimistic all independent receiver-local readiness aggregation -> locally certified 100/100, mean sender application payload 838160 B. The Democracy difference is 80.3438% fewer modeled sender Bytes in that particular equally successful-by-distinct-criteria cell.

Democracy 100/100 at sampled 50%, first non-perfect sampled result is 48%=99/100 (non-monotone finite-sample observation), 51%=99/100, 52%=91/100, 53%=65/100, 54%=14/100 and 55%=0/100 with 300-round guard. Original CBAA local readiness 91%=100/100, 92%=97/100, 93%=87/100, 94%=48/100, 95%=2/100, 96..99%=0/100 at 160-iteration guard; however original CBAA POST-HOC observer agreement was 100/100 for 50 tasks at ALL sampled loss values including 99% in the 100 finite seeds. This last fact does NOT mean an implementable fully distributed final Commit or stopped algorithm: all locally known stopping conditions and paid stop acknowledgement are separate. Explicit CBAA high-loss observer-versus-local-certified and guard-censoring charts remain required.

Never represent the sampled 50%/91% as mathematical packet-loss limits; no 802.11 MAC/PHY/ACK, airtime or retransmission overhead beyond the original modeled per-SEND event accounting. Tasks are guaranteed delivered while Democracy Cost/Vote and CBAA bid/winner are independently lossy; original Democracy reliable Score/Commit remain fixed. Actual success endpoints differ and should not be numerically equated as identical reliability or optimized traffic.

### 32.4 Changed files / owner / diagnostic boundary / continuity

This bounded formal E9E publication modifies README.md formal result block (six verified source images, selected SHA-grounded original summary table, direct links to original summary and source provenance), docs/EXPERIMENT_PROTOCOL.md this Section 32, docs/CHANGE_CONTINUITY.md, and removes prior temporary preview-only link block from README. Optionally removes now-superseded temporary one-off uploader workflow and derived preview figures from HEAD after successful exact source SVG publishing; former historical Git commits retain traceability.

NO robot algorithm, CBAA original auction/consensus, Democracy original Cost/Vote/Commit, original CBAA certificate, random sampling, physical packet emission or runtime state machine changes. No new named owner function or diagnostic classification. The verification contract remains the original experiments.plot_e9d_results.verify_e9d_plot_provenance (contract/E9E_PLOT_SHA256_MISMATCH and E9E_PLOT_RAW_SUMMARY_CONTRACT), load_e9d_plot_evidence (dependency/E9E_PLOT_EVIDENCE_MISSING), and original manifest source-SHA chaining. This is result REPORTING/publication only, in line with one concern -> one original owner. Update docs/CHANGE_CONTINUITY.md with exact publication commit and remaining risks. All published numerical claims are derived from the independent original ZIP, not invented extrapolations or general high-loss guarantees.


## 33. E9F-1 causal Cost-source repetition in the TRUE Democracy coordination owner

### Goal, hypothesis and controlled scope
The independently verified E9E 100R50T ×100seed result found Democracy real full Commit 100/100 at sampled p=0.50, then 91/100 at 0.52, 65/100 at 0.53, 14/100 at 0.54 and 0/100 at 0.55; original CBAA naturally rebroadcasts winning Bid/Winner vectors under packet loss, while original Greedy Democracy sends each robot's Cost ONCE for the entire run. E9F isolates whether original initial Cost loss is a causal driver of the Democracy cliff, while paying for every additional physically emitted Cost packet. It does NOT change voting rule, CBAA, task release, final Score/Commit reliability, the opponent cost oracle, or hard budgets. It does NOT claim equal sender-byte protocol budgets yet.

### Original owner and named functions
Only democracy_mrta.coordination.py changes in this bounded E9F-1 source concern:
- validate_cost_repetitions: one independent data/E9F first failure under owner="coordination", function="validate_cost_repetitions", category="data", code="INVALID_COST_REPETITIONS", expected integer 1..5. Python bool is NOT a valid repeat count.
- validate_repeated_cost_scope: one explicit contract/E9F first failure owner="coordination", function="validate_repeated_cost_scope", category="contract", code="REPEATED_COST_REQUIRES_GREEDY_COST_SOURCE"; prohibit >1 repeats for non-greedy Hungarian epoch and for any preknown_cost_snapshot, so no free remote-pose data or newly invented Cost packets appear in separate algorithms.
- transmit_cost_row_copies: single physical Cost packet emitter. For m in {1,2,3,4,5} each robot emits exactly m physical original Cost row packets, each cost_row_payload_bytes(T)=16+8*T Bytes, first sends at t=0 then t=phase_timeout_ms,2*phase_timeout_ms etc. Every original sender event, modeled payload Byte and receiver-specific independent loss observation is accounted for; no ACK, free implicit resend, or incremental global Cost knowledge. The first Cost packet retains EXACT original physical event/loss key; copy i>0 uses distinct explicit "|copy=i" sender and per receiver Bernoulli loss keys, with real transmission_index on CommunicationEvent/DeliveryObservation. A sender budget rejection prevents the denied packet and any extra cost; never emits an unpaid Cost or declares a false reliable Commit.
- _simulate_lossy_cost_broadcasts: unchanged TRUE owner of receiver-visible Cost rows except opt-in union of physically DELIVERED original Cost duplicates. Each robot always knows its own row locally, and adds each peer's row only when AT LEAST ONE actually received Cost copy succeeds; multiple delivered copies of a peer do NOT create duplicate rows or votes. One copy uses exactly the original E2/E9D cost-ready clock behavior. For >1 open-loop copies, conservative vote-ready clock waits through the final physical Cost timeout window m*phase_timeout_ms; this is an INTENTIONAL time behavior change only for the opt-in experimental variant.
- capture_retirement_cost_snapshot: forwards opt-in number of Cost copies ONCE at the beginning of original Greedy retirement; every later voting/retirement epoch only filters its retained receiver-visible Cost source. No new network copy per retry and no second state machine.
- simulate_democracy_hungarian_retirement: only exposes backward-compatible cost_repetitions=1 keyword, validates it, restricts valid source, and forwards to the true existing Cost owner; original Greedy votes (one), >25% qualification, candidate Score, Commit/retirement, per-round logic and 300-round guard are byte-for-byte identical in default mode.
- _broadcast_event/_lossy_broadcast_deliveries: original packet constructors get backward-compatible transmission_index=0 default and append distinct "|copy=i" keys ONLY for additional physical Cost broadcasts. Original E0..E9E first-copy sampled loss keys, messages, counts and timers remain unchanged.

### Interpretation and verification
A 100R50T m=1 initial Cost stage costs 100*(16+50*8)=41,600 sender application Bytes; m=2 costs 83,200, m=3 124,800, m=5 208,000. All additional bytes are part of the ACTUAL original sender ledger; the common TASK once cost 1,632 B remains separate. Expected one directed sender->receiver Cost reach probability under independently lossy physical repetitions is 1-p^m; this is only a single-link marginal argument, NOT a predicted task full-Commit success probability (vote propagation is separately lossy, quorum thresholds and robot retirement couple events). Original CBAA algorithm and original max-consensus, external observer agreement and optimistic global local-ready scheduler remain unchanged and must be labeled separate from real reliable Greedy Commit.

New tests/test_e9f_cost_repetition.py: eight named tests for default m=1 parity, paid m=3 Cost event/delivery keys, actual missing-row recovery only on copy=1 packet receipt, total p=1 negative control, no subsequent Greedy-epoch rebroadcast, invalid count named first failure, invalid source/plan contract, physical sender byte denial no phantom Commit. Run full old regression; never claim it has passed until CI or Mac execution. E9F-2 is a SEPARATE bounded study of 100 matched seeds, natural original CBAA reference and Greedy Cost copies 1/2/3/5, physical payload accounting, finite guard and empirical loss frontier near 0.50–0.70. The READMEs must not publish unverified new outcomes.


## 34. E9F-2 paired 100-seed original Greedy Cost-copy causal sweep vs original CBAA

### 34.1 Research question and controlled actors
The next bounded experiment tests whether the original Democracy Greedy success cliff around p=0.52..0.55 is causally associated with each robot sending its Cost vector only ONE time. E9F-1 Section 33 adds true physical initial Cost row sender copies (NOT ACK/ARQ). This E9F-2 is only a NEW experiment, result and diagnostic owner; it DOES NOT create its own voting state machine, replan any task, change original Cost/Score/Commit data, charge CBAA for a fake full robot-position broadcast, silently alter the original E9D results, or claim the two protocol endpoint semantics are equal.

For EVERY paired (seed,p) scenario, the original independent TASK binary broadcast is charged and delivered once, local true own cost rows reconstructed only from that physically decoded source plus each robot's own pose. Independently run original Greedy Cost copies m in (1,2,3,5) at the original Cost source in democracy_mrta.coordination.simulate_democracy_hungarian_retirement with voting_strategy=greedy_task, vote_decision_rule=quarter_plurality, vote_repetitions=1 and default max_rounds=300. Each robot emits m fixed open-loop Cost packets at physical application sender size 16+8*T; all peer physical copies independently face Bernoulli loss p. Voting always uses only rows physically received before the paid last-copy Cost-phase deadline. Success is real all-50-task reliable Commit and robot retirement. All Cost and Vote send attempts, Score/Commit control, drop counts and round guard are charged/recorded.

As an UNCHANGED reference, run **original source CBAA** from experiments.run_e9d_natural_loss.run_e9d_original_cbaa_loss_case EXACTLY ONCE for each paired (seed,p), independently with only own costs, own full Bid/Winner repeated vector, and receiver-specific Bernoulli loss p; 160-iteration guard. It has no manual fixed K or raw robot-location propagation. The CBAA optimistic simulator-wide all-local-ready halt and no paid distributed final stop/Commit must be prominently disclosed, along with distinct post-hoc observer agreement. This is a paid Cost redundancy CAUSAL ABLATION and observable sender-byte comparison, NOT yet matched end-to-end hard sender-budget parity. An E9G equal cap/paid termination study may be scoped separately after E9F evidence.

### 34.2 Full protocol and sample axes
- Main fixed scenario: R=100, T=50; matched seed IDs 0..99.
- Cost copy grid frozen m=1,2,3,5; integer and ascending with mandatory m=1 control.
- Default sampled p grid: 0%, 30%, 40%, 45%, 48%, EVERY integer percent 50%..65% inclusive, plus 70%, 80%, 90%: **24 UNIQUE levels**. Main requested 100-seed run is 100 * 24 * (4 original Greedy ablations + 1 original CBAA) = **12,000 actual protocol runs**. A 3-seed pilot precedes the full 100 seeds.
- The p1=1.0 failure negative control is available via custom --loss-probabilities even though omitted from the default p0..90 focus. --cost-copies accepts a comma list of unique ascending valid m in [1,5] with mandatory initial 1; no configured fixed CBAA K (only safety guard).
- Independent p assigned to initial Cost and each Vote for Greedy, and Bid/Winner per receiver for original CBAA. No Cost copy is free or multiplies by number of receivers in sender Bytes. Task announcement p_task=0 and paid, original qualified Score/Commit remain reliable, constant synthetic 1ms timing/10ms deadline. Sending m>1 Cost windows lengthens simulated start before votes; this is intentionally reflected in elapsed_ms, not hidden.
- Original m=1 explicitly remains bit-for-bit equivalent to run_e9d_democracy_loss_case at the same scene/seed,p, network sampler and guard. Cross-method source does not receive hidden peer pose/cost metadata.
- Full CBAA post-hoc observer assignment and full receipt-based local stop are reported SEPARATELY; neither equals the Greedy actual reliable task Commit.
- 160/300 safety guard exhaustion is right-censored; report does not claim theoretical p critical value.

### 34.3 Named true experiment owner, diagnostics, tests, raw artifacts
Only new experiments.run_e9f_cost_redundancy.py owns E9F-2:
- parse_e9f_cost_copy_grid, validate_e9f_cost_grid: data/E9F_INVALID_COST_GRID (unique ascending 1..5 with original 1-copy mandatory). The actual Cost sender's validate_cost_repetitions remains its ORIGINAL owner and data/INVALID_COST_REPETITIONS boundary.
- validate_e9f_sweep_axes: reuses original E9D validation, additional data/E9F_ROBOTS_REQUIRE_PEER_RECEIPTS.
- prepare_e9f_output_root: state/E9F_PROTECTED_OUTPUT_ROOT, state/E9F_OUTPUT_EXISTS; prior E9C/E9D/E9E evidence immutable.
- run_e9f_democracy_cost_case: calls original actual Greedy coordination owner, calculates actual physically received distinct sender/receiver Cost pair coverage from original events/deliveries, keeps duplicate Cost receptions from forming extra rows, and verifies existing true first epoch visible rows against receipts; contract/E9F_VISIBLE_COST_SOURCE_MISMATCH with expected/actual if inconsistent. No duplicated voting engine.
- run_e9f_cbaa_reference_case: delegates unchanged E9D original source CBAA once per seed/p; no new CBAA auction, hidden global stop, pose broadcast or Cost source.
- require_e9f_paired_sender_contract: contract/E9F_METHOD_PAIRING_MISMATCH, E9F_PHYSICAL_SENDER_BYTES_MISMATCH, E9F_FAKE_CBAA_COST, E9F_COST_RETRANSMISSION_LEDGER; each method/seed/p complete and physically accounted including duplicate open-loop transmissions, no input missing/fabricated.
- summarize_e9f_cost_study: all configured Seeds are included in denominators, even if incomplete or guard-censored; original sender Bytes, Cost-only Bytes, observed peer Cost receipt fraction, actual committed task count, original CBAA observer and local success separately. Completed-only mean shown only as secondary statistic, never replace all-seed sender mean.
- calculate_e9f_empirical_frontier: only finite test sample highest all/any success p and first imperfect p; guard-censoring explicit, NOT mathematical critical p.
- write_e9f_cost_evidence: immutable final per_seed_cost_copy_method.csv, summary_cost_copies_by_loss.csv, and manifest.json with executable git_sha, loss/copy axes, observed original method names, modeled original wire-phase warnings and exact SHA256 of both complete CSVs; incomplete runs retain flushed per_seed_cost_copy_method.partial.csv and MUST NOT be declared formal.
- run_e9f_cost_redundancy: one paired seed/loss orchestration owner, emits exactly 5 method rows per default cell; CBAA only once, original true TASK always charged; prints progress and method/loss totals; main CLI only.

Eight tests/tests/test_e9f_cost_study.py independently exercise one-copy E9D parity, exact Cost and CBAA paid messages/deliveries, p0/p1 source visibility limits and paid failure behavior, separate semantics with ALL seeds denominator, manifest/checksum/coverage, invalid data/profile, protected immutable roots, invalid pair/byte owner/category/code. Whole repository unittest regression and real small-source CI smoke must pass before formal use.

### 34.4 Mac on-host execution (instructions kept OUT of presentation README)
Focused original true Cost source: python3 -m unittest discover -s tests -p 'test_e9f_cost_repetition.py' -v
Focused original 100-seed runner: python3 -m unittest discover -s tests -p 'test_e9f_cost_study.py' -v

Pilot:
    python3 -m experiments.run_e9f_cost_redundancy --robots 100 --tasks 50 --seeds 3 --cost-copies 1,2,3,5 --output-root results/e9f_pilot_100r50t_3seed

Formal:
    python3 -m experiments.run_e9f_cost_redundancy --robots 100 --tasks 50 --seeds 100 --cost-copies 1,2,3,5 --cbaa-safety-round-limit 160 --democracy-safety-round-limit 300 --output-root results/e9f_formal_100r50t_100seed

The user must use unique fresh output roots; if long formal run is interrupted it cannot resume automatically. User supplies complete raw + summary + manifest archive for independent verification before README result/chart publication. Do NOT claim E9F measured uplift before actual user Mac formal data is received. Existing README remains a results-only research document, with no how-to-run code inserted.


## 35. E9G evidence-calibrated Wi-Fi 6E timing — scoped research contract (not implemented)

### 35.1 Research question
For original Greedy Voting **only**, study actual application SEND count, source payload Bytes, channel contention/queueing, radio airtime and end-to-end task-allocation wall-clock time, initially R=T=N for N=5,10,...,100, zero application loss, one original Cost broadcast, 100 paired seeds. This supersedes neither the E9E loss curves nor E9F Cost repetition protocols. In particular the old \`phase_timeout_ms=max(Rady.control_delay_ms)=531.535123 ms\` makes old allocation timing largely proportional to N even with no shared RF congestion: it is a protocol deadline, not measured Wi-Fi airtime.

### 35.2 Exact sources and attribution
See README.md §3.6 and docs/references/e9g_wifi_timing.bib for individually attributed papers, DOIs, repository links and explicit limits:
- Rady et al. 2024: pinned industrial 60 m LoS 6 GHz/160 MHz application delay calibration (source dataset commit/blob already pinned in §5).
- Liu & Choi 2023: commercial Wi-Fi 6 throughput, multi-user OFDMA, latency small-scale external validation; obtain and independently hash exact public samples before fitting.
- Montgomery & Candell NIST IR 8506 (2024): load/AP-dependent OFDMA activation; do not generalize hardware-specific triggers.
- Bianchi 2000: theoretical DCF collision/backoff, not standalone 802.11ax-OFDMA calibration.
- Riley & Henderson 2010 + ns-3 official Wi-Fi model: prospective EDCA/PHY simulation implementation; pin supported version and all model parameters, do not imply already tested.
- Choi, Brunet & How 2009: original consensus auction background, not RF calibration.

### 35.3 Responsibility / diagnostic design for later physical implementation
Network/PHY/MAC time is a **network owner** concern. Existing \`democracy_mrta.network.EmpiricalLatencySampler.sample_ms\` remains unchanged for legacy E1–E9F. New *opt-in* network backend must validate profile/PHY/traffic parameters under network/data or network/dependency; guarantee strictly monotonically causal delivered event timestamps under network/time, and verify packet/source mapping under network/contract. Original \`coordination._broadcast_event\` and \`coordination._unicast_event\`, \`coordination._lossy_broadcast_deliveries\`, \`coordination._lossy_unicast_delivery\`, \`task_information.broadcast_task_information\`, \`coordination.simulate_democracy_hungarian_retirement\` own original protocol sends/receives, deadlines, voting, qualified score and Commit and MUST NOT be forked or silently changed. No second voting state machine. Proposed named boundaries (NOT presently implemented): \`network.validate_wifi_phy_config\` / data / E9G_INVALID_WIFI_PHY; \`network.load_verified_wifi_calibration\` / dependency / E9G_CALIBRATION_MISSING; \`network.validate_network_event_trace\` / contract / E9G_EVENT_TRACE_MISMATCH; \`network.require_causal_arrivals\` / time / E9G_NONCAUSAL_PACKET_ARRIVAL. Each diagnostic shall state owner, function, category, code and expected/actual/details when useful.

Do not calculate ns-3 completion by re-timing an already-completed application trace if arrival differences change eligibility/commit; the network model must participate in original causal event execution. Include AP uplink/downlink broadcast forwarding, configured multicast vs unicast radio transmissions, ACK/retries as actually enabled, channel bandwidth/MCS, EDCA backoff, queues, fixed headers and residual ROS/DDS stack time without overlapping Rady's end-to-end measured delay. A broadcast application SEND is counted once in application ledger; it is NOT necessarily a single wireless airtime transmission across an infrastructure BSS. Separate channel losses from application-layer Bernoulli loss. Include timeouts even if not radio airtime, failures and guard-censored seeds in the record.

### 35.4 Provenance and acceptance
Required for *actual* E9G results: exact original voting Git SHA; ns-3 installed/runtime version/commit and configuration; sourced measurement revisions + SHA256; trace schema, per-packet SEND/receive/PHY accounting and network seeds; at least one reference 1-client and small multi-client external measurement validation; N=5 parity; 20-scale ×100seed raw and summary with SHA256; explicit 100-client extrapolation and parameter sensitivity; plots derived from raw; all source citations in README. No fixed Mbps choices may be presented as measured throughput absent verified source. A network simulator is not available in current verified execution context; this section is a frozen plan, not a code feature, validation run, or new measured result.

### 35.5 Current controlled milestone
Only a **documentation/citation** milestone: docs/references/e9g_wifi_timing.bib, README §3.6, this canonical section and continuity. No algorithm, Python network backend, emulator, simulator, or test changed in this milestone. Implementation must proceed as a separate bounded owner change with a new continuity entry.


## 36. E9G-1/E9G-2 implemented simplified shared-radio Voting timing pilot (not ns-3)

### 36.1 Exact implementation scope and literature
This **bounded** source change supplies a runnable, purely Python, **one-shared-radio contention and packet-size sensitivity** model for the EXISTING original Greedy Voting owner. The source papers, with per-method citations and limits, are in README §3.6 and \`docs/references/e9g_wifi_timing.bib\`. They are **not all implemented protocols**. Specifically:
1. Rady et al. 2024 (DOI 10.1016/j.adhoc.2024.103418): published measured industrial robotics 60 m LoS, 6GHz 160MHz **ROS delay** distribution; initial idle-service subtraction of modeled frame from published application delay is an *approximate* residual separation, not independently measured residual. Keep the original pinned commit/blob/profile, 121 samples.
2. Bianchi 2000 (DOI 10.1109/49.840210): motivates the contention/backoff term; implemented model has deterministic hashed CWmin backoff and one shared radio serialization, but **not the Bianchi saturation fixed-point analytical solution**, wireless frame collisions, exponential retry, or a full EDCA MAC.
3. Montgomery & Candell, NIST IR 8506 2024 (DOI 10.6028/NIST.IR.8506): AP-dependent OFDMA uplink behavior justifies **not assuming OFDMA**; **OFDMA is NOT implemented** here.
4. Liu & Choi 2023 (DOI 10.1145/3579451): small-user commercial 802.11ax evidence that should inform future calibration; **no samples from Liu were fitted or replayed here**.
5. Riley & Henderson 2010 (DOI 10.1007/978-3-642-12331-3_2), ns-3 official Wi-Fi design: reference for future external packet-level PHY/MAC backend; **no ns-3 compiled/executed here**.
6. Choi, Brunet & How 2009 (DOI 10.1109/TRO.2009.2022423): task-allocation background only; **CBAA not executed in E9G**.

The user can therefore measure **modeled trade-offs** immediately on a Mac while the separately bounded actual ns-3 integration remains pending. NEVER label this E9G proxy “full literature-calibrated Wi-Fi 6E” or “real 100-robot observed time”.

### 36.2 Implemented owner and stateful trace contract
- \`democracy_mrta.network.WifiTimingConfig\`: typed PHY-rate and header/timing sensitivity assumptions; rates 144/600/1200 Mbps are *hypothetical*, not claimed measured Rady 60m throughput. Physical models use 64 B extra per radio hop, 120us preamble, 34us AIFS, 9us slot, CWmin=15, 45us ACK; these are **explicit bounded hypothetical configuration constants** for this approximation, not paper-measured configuration estimates.
- \`network.validate_wifi_phy_config\` / data / \`E9G_INVALID_WIFI_PHY\`: rejects invalid rate/overhead/CW/time.
- \`network.WifiCausalTimingSampler.sample_packet_ms\` / time / \`E9G_NONCAUSAL_PACKET_RELEASE\`, \`E9G_NONCAUSAL_PACKET_ARRIVAL\`, data / \`E9G_INVALID_PACKET_INPUT\`: original owner emitter must submit chronological original app SENDs. Radio medium \`t_start=max(t_release,t_medium_free)\`; queued time and per-hop airtime/AIFS/backoff/ACK are charged; network \`t_medium_free\` advances by modeled service; ROS residual is \`max(0,L_Rady - E[T_reference_single_hop_service])\` and ends after medium service without globally blocking subsequent radio transmissions.
- \`network.WifiCausalTimingSampler.set_epoch_start_ms\` / time / \`E9G_NONCAUSAL_EPOCH_START\`: original sequential Voting round end advances the transport epoch in monotone absolute simulated time; no uncharged backtracking. \`summarize_network\` includes every original app sender event + total simulated wire hop-equivalent Bytes, modeled queue/backoff/ack/airtime/residual sums, separately from overall end-to-end time.
- \`coordination._unicast_event\` / \`_broadcast_event\`: opt-in use of \`WifiCausalTimingSampler.sample_packet_ms\` only when sampler is exactly this modeled timing owner; all existing Rady/constant samplers use unchanged \`sample_ms(key)\`.
- \`coordination._simulate_lossy_cost_broadcasts\`: for opt-in E9G only, Cost packet physically delivered **after** original Cost-phase deadline is recorded as delivered on wire but excluded from voter visible rows. The legacy E9F Cost source semantics remain unchanged.
- \`coordination.transmit_repeated_remote_vote\`: for opt-in E9G only, physically delivered **after** vote deadline cannot be counted. Record late physical delivery in trace, do not suppress Bytes.
- \`coordination.simulate_democracy_hungarian_lossy\`: only opt-in E9G sorts original sender Vote emissions by their existing ready-time before packet timing. It **does not** replace original vote proposals, winner/quorum/plurality, reliable Score or Commit logic; legacy order is unchanged.
- \`coordination.simulate_democracy_hungarian_retirement\`: rejects opt-in E9G with nonoriginal Hungarian mode, Cost m>1 or Vote m>1, contract / \`E9G_WIRE_TIMING_ORIGINAL_GREEDY_ONLY\`; sets epoch offset before original round execution, exact existing cost snapshot first. E9G **does not** implement general m>1 packet-time-order scheduling.
- \`task_information.broadcast_task_information\`: unmodified true TASK wire owner. Existing packets incur modeled one-hop AP broadcast, receiver reliable announcement happens before any Cost. Original Greedy Cost/Vote/Score/Commit packets each model two-hop STA→AP→receiver(s); a broadcast incurs one application SEND, not \`N\` SENDs, but modeled two radio hops. ACK for unicast on both hops, uplink peer broadcast on one, AP downstream broadcast zero normal per-recipient ACK. This is a **network topology assumption** that may differ from actual MAC/AP implementation.
- \`experiments.run_e9g_wifi_scaling\`: **one experiment orchestration concern**, no second state machine. \`parse_e9g_sizes\`, \`parse_e9g_rates\`, \`validate_e9g_run\`, \`prepare_e9g_output\`, \`create_e9g_sampler\`, \`run_e9g_one_voting_case\`, \`summarize_e9g_scaling\`, \`e9g_loglog_exponent\`, \`summarize_e9g_exponents\`, \`calculate_e9g_phase_timeout_ms\`, \`write_e9g_evidence\`, \`run_e9g_wifi_scaling\`, \`main\`. Key diagnostics data/\`E9G_INVALID_SIZE_GRID\`, \`E9G_INVALID_RATE_GRID\`, \`E9G_INVALID_EXPERIMENT_AXES\`; state/\`E9G_OUTPUT_EXISTS\`; contract/\`E9G_PACKET_LEDGER_MISMATCH\`, \`E9G_INCOMPLETE_PAIRED_GRID\`; dependency/\`E9G_INVALID_SOURCE_SHA\`. Never overwrite original raw or completed result roots; incomplete stream stays in \`per_seed_wifi_timing.partial.csv\`.

### 36.3 Frozen primary axes, timing endpoint and censoring
- \`R=T=N\`, \`N={5,10,...,100}\`, matched \`seeds=0..99\`, \`p=0\`, \`Cost copies=1\`, and actual Greedy qualification >25%, original reliable Score/Commit, \`max_rounds=300\`.
- Reference path \`rady_bootstrap_no_shared_channel\`; modeled path \`e9g_shared_medium_backoff_proxy\`, hypothetical modeled PHY Mbps = \`144,600,1200\` (not measured 60m rate). No OFDMA, no real retransmission/collision, no client-specific queues or spatial attenuation; each original sender physical packet is submitted once, even if its receiver becomes late. See §35 for the full ns-3 plan.
- **One common fixed deadline for ALL N and modes within a sweep**, not an N-specific timeout: \`T_limit = max(D_Rady) + [2 N_max (PHY_preamble + AIFS + CWmin*slot + ACK + 8*(16+8 N_max+header)/rate_min)] + 1ms\`. The radio term is a **modeled upper envelope of one source Cost burst**, not empirical Wi-Fi delay or a proof of complete delivery. It prevents silently retaining a 531.535ms max-sample deadline after explicitly adding radio service; the same computed value is used by reference and modeled methods. The prior 531.535ms legacy E9E/E9F deadline is not modified; end-to-end scaling under this study is conditional on the new declared timeout assumption.
- TASK is charged and reliably delivered at \`p=0\` with no additional TASK deadline; only when every original frame arrived can own local costs be reconstructed. Each run reports \`T_once = max(original TASK arrival) + original sequential Greedy result.global_agreement_ms\` for full Commit; incomplete/guard-censored cases report stop time and committed count but DO NOT label stopped time “successful allocation time”. The per-frame modeled queue/airtime/backoff/residual **SUMS are diagnostic service load, not additive components of \`T_once\`** because residual processing/network phases overlap. Physical task execution/travel time excluded.
- Original application sender ledger must match \`network.summarize_network()\` counts and sender Bytes exactly. Each run records full-Commit flag, uncensored seed denominator, guard, Cost/Vote event timing affected by on-time receipt, total modeled radio hops/Bytes, residual sums, all-seed P50/P95, completed-only means secondary.
- Per-group \`Y(N)=aN^beta\` least-squares slope is **empirical** across 5..100, not mathematical asymptotic Big-O. The original analytic application sender Bytes follows \`B(N)=24N²+92N+16 ceil(N/37)\` under zero-loss on-time original unanimous Greedy single-attempt cases; no claim of a theoretically subquadratic byte bound.

### 36.4 Reproducible Mac local commands (not added to research-facing README)
Run from main and install existing requirements; the pinned Rady JSON downloads if missing, with Git blob SHA verification.

Smoke, 5/20/50/100 robots, 3 seeds each, reference + 3 hypothesized rates:
    python3 -m unittest discover -s tests -p 'test_e9g_wifi_timing.py' -v
    python3 -m experiments.run_e9g_wifi_scaling --sizes 5,20,50,100 --seeds 3 --rates-mbps 144,600,1200 --output-root results/e9g_wifi_pilot_3seed

Full original Voting-only scaling (20×100 seeds×4 conditions = 8000 actual original-protocol executions):
    python3 -m experiments.run_e9g_wifi_scaling --sizes 5,10,15,20,25,30,35,40,45,50,55,60,65,70,75,80,85,90,95,100 --seeds 100 --rates-mbps 144,600,1200 --output-root results/e9g_wifi_formal_100seed

Outputs are \`per_seed_wifi_timing.csv\`, \`scaling_by_size_mode.csv\`, \`empirical_scaling_exponents.csv\`, \`manifest.json\` and an immutable source branch SHA. Verify all listed SHA256 before publishing result graphs/README findings. Upload the four files as a ZIP for independent QA. Do not publish unsupported 100-client measured Wi-Fi or ns-3 claims.

### 36.5 Tests and scientific next step
\`tests/test_e9g_wifi_timing.py\` focuses data/time owners, two-hop sender Byte preservation, backoff queue, original Vote/Cost/Score/Commit causal integration, 0%-loss source parity, exact manifest SHA, immutable roots, and finite exponent logic. GitHub workflow \`.github/workflows/e9g_wifi_timing.yml\` runs E9G-focused + full historical unittest suite and a 2seed real pinned-Rady smoke (on main). **Workflow outcome is only PASS when observed in GitHub Actions; code upload is not proof.** E9G-1 is a *simplified sensitivity baseline*; the next separately scoped network owner can integrate actual ns-3 802.11ax EDCA/OFDMA timing with robust multi-client calibration from Liu/NIST and real radio/packet trials. No such result is claimed in E9G-1.


## 37. E9G-2 verified **modeled** 100-seed source publication (no protocol behavior change)

Original uploaded source `e9g_wifi_formal.zip` was SHA256 checked: source executable commit `910c5eac738367738907b18fce86e56adf86697d`, original 8000-row per-seed SHA256 `ba79fd138d84d6d3bb7f04430a36a8c3e973d7ca0978834d4ad3a3b1d3f85be6`, original 80-row summary SHA256 `bdc2b784297d1465800e094fe2dd611c79578c20a7ec2efb04216faecd77a590`, four finite exponent rows SHA256 `5a36eab796192de8c95d18c06ee31ac573c9aae697e9648c71ebd3312866d62f`. Full grid `N=5,10,...,100; R=T=N; seeds 0..99; 0% application loss; one Cost copy; original Greedy qualified Score/Commit; Rady-only vs opt-in modeled 144,600,1200 Mbps`. Every single source outcome was full Commit; the original sender traffic matched its exact analytic quadratic formula in all 8,000 rows. All 80 summary rows and all four exponent rows independently recomputed.

The **fixed per-task phase deadline 609.11290078 ms** makes near-linear end-to-end source estimates largely *protocol-wait dominated*; `N=100` nominal `N*deadline=60.91129s` is 89.39% of Rady-only 68.14266s modeled mean, but this is not an exact additive timing decomposition. Original model `N=100` means 68.14266s (Rady), 68.224382s (144 Mbps), 68.218596s (600 Mbps), 68.217682s (1200 Mbps). Mean modeled PHY airtime 144 Mbps 1.325218s; sum of local queue waits ~90.768s must never be read as end-to-end queue delay. Figure plot-driving data is rounded 0.001 numeric units and its source hashes are pinned. See README §3.7 and `docs/figures/e9g_wifi/formal/publication_manifest.json`.

This source-publishing-only change modifies no actual packet, runtime, owner functions, optimizer, timeout, canonical behavior or diagnostic. Do **not** interpret hypothetical rates as verified external PHY throughput; Bianchi 2000, NIST 2024, Liu/Choi 2023 and ns-3 references retain the precise **used-versus-future** source distinctions documented in README §3.6. The original complete raw and 80-row source summary remain in the user archive, not Git committed. The full Wi-Fi 6E PHY/MAC/ns-3 validation requirement in §35 remains **OPEN**, not satisfied merely by this proxy evidence.


## 38. E9H opt-in truthful deadline and received-plurality (not yet formal results)
The user requires a frozen quantitative N-active-aware phase deadline and a rule that compares each eligible candidate's own **actually received and counted on-time votes** without an arbitrary 25% admission floor. Mathematically this is **relative plurality**, not a >50%-of-all-voters strict majority. The original Score announcer still broadcasts each candidate's final tally *after* the vote window; winner=max(count), deterministic lowest-ID tie; no zero-receipt self-claim, no winner if all counts zero, and no forced default assignment. Old 25% and other E9G/E9F modes are unchanged by default.
- `protocol.plurality_announcement_threshold` / data / E9H_INVALID_ANNOUNCEMENT_RULE; original quarter remains floor(active/4)+1, new `received_plurality` accepts >=1 physically on-time ballot. Actual `protocol.resolve_unique_plurality_claims` retains unique candidate, valid vote counts and tie validation.
- `coordination.simulate_democracy_hungarian_lossy` opts into `enforce_vote_deadline=True`. Its frozen global vote cutoff equals max(local Cost ready-times) plus the *current active-robot deadline*. Only remote physical arrivals <= cutoff (inclusive) and local self ballots sent by cutoff enter ledgers; late physical packets still count as SENDs and network delays. `transmit_repeated_remote_vote` accepts new optional absolute global cutoff only for E9H; original per-sender deadline remains as before when omitted. `simulate_quarter_plurality_announcement_phase` and `build_quarter_plurality_claims` remain actual announcement owner with rule parameter, no duplicate Vote/Score engine. `coordination/contract/E9H_RECEIVED_PLURALITY_REQUIRES_CUTOFF` refuses the new rule without real on-time filtering.
- `coordination.simulate_democracy_hungarian_retirement` optionally chooses precomputed immutable per-active robot schedule (index active count minus 1). Cost snapshot uses the longest initial entry. The schedule validation owner `coordination.validate_e9h_deadline_schedule` / contract / E9H_INVALID_DEADLINE_SCHEDULE refuses missing/wrong length, nonpositive/nonfinite, nonmonotone, or mismatch with initial Cost phase timeout.
- All existing Cost/Vote/Score/Commit state, physical sender accounting, safety unique-Commit and packet reliability assumptions remain unchanged unless this explicitly new policy is chosen. Document empirical Rady + previous E9G paper-supported numeric deadline estimator and an E9H factorial ablation in the next bounded milestone. New results are NOT claimed yet.


### 38.1 E9H cross-model receipt correction and phase-aware schedule condition
E9H opt-in cutoff must work in **both** physical shared-medium and original Rady-only sampler; an explicit global cutoff takes precedence over the old E9G Wi-Fi-type-specific cutoff. The Cost receiver must also enforce explicit E9H deadline regardless of sampler type. The old Rady and E9G behavior is unaffected unless `enforce_vote_deadline=True`. Cost traffic includes full N-task row and may take longer than a 32-byte Vote; therefore validator allows `D_cost(N)>=D_vote(N)` rather than equality. `protocol` winner safety and original eligibility membership remain unchanged. These corrections are required before any E9H comparison can be trusted.


## 39. E9H frozen numeric Rady + E9G traffic deadline estimator
The real deadline calculation owner is `democracy_mrta.network.estimate_e9h_adaptive_deadline`, output typed `RadyAdaptiveDeadlineEstimate`. Its **predeclared frozen equation**, separately for initial 16+8T Byte Cost packets and each subsequent 32 Byte Vote packet, is

\[D_p(n,R,k)=\mu_{Rady}+k\max(0,P95_{Rady}-\mu_{Rady})+2n\bigl[(T_{preamble}+AIFS+CW_{min}\,slot/2+ACK)/1000+8(B_p+H)/(1000R)\bigr]\ \mathrm{ms}.\]

Units: `R` Mbps **hypothetical design reference**, `n` CURRENT active robots (Cost uses original N and original T tasks), `B_cost=16+8T`, `B_vote=32`, `H=64 modeled bytes per radio hop`, 120us preamble, 34us AIFS, CWmin=15, 9us slot, 45us ACK. It is a **hypothesized 2-hop N-source single-medium worst burst**, not a measured Wi-Fi throughput function; reference μ/P95 are pinned 121 ROS control latency samples from Rady et al. 2024. `k∈{0,1,2}` sensitivity chosen **before** new run, k=1 primary (Rady mean + 1× P95-minus-mean). If Rady profile, rate, n, T or k invalid, diagnostic is network/data/E9H_INVALID_DEADLINE_INPUT or network/dependency/E9H_MISSING_RADY_SAMPLES; original network.validate_wifi_phy_config still owns rate validity. The N scaling of Cost/Vote original Bytes and number of SENDs was independently verified with the user's E9G 8,000-row archive, source executable SHA 910c5eac738367738907b18fce86e56adf86697d and original per-seed CSV SHA256 ba79fd138d84d6d3bb7f04430a36a8c3e973d7ca0978834d4ad3a3b1d3f85be6.

The Cost deadline D_cost(N) is allowed to exceed D_vote(N); voter/epoch time owner receives immutable vector `(D_vote(1),...,D_vote(N))` and initial cost D_cost(N). Same design reference R=144 Mbps for ALL compared physical sensitivities 144/600/1200 plus Rady-only, to isolate network differences. No grid is chosen or tuned using test seed success, agreement or speed. Every result must report enough details to recompute D. A previous E9G fixed 609.1129007777778 ms reference is an explicit separate controlled fixed-timeout arm, never recomputed using evaluation results. This is a reproducible **simulation formula with paper-supported empirical base**, not a validated optimal field timeout.


## 40. E9H experiment orchestration and evidence plan (formal unexecuted)
True orchestrator owner `experiments/run_e9h_adaptive_deadline.py`: strictly original Greedy Voting Task/Cost/Vote/Score/Commit sender owners, no second state machine; physically causal network owners already implemented E9G, no ns-3. `parse_e9h_floats` (data/E9H_INVALID_LOSS_OR_MARGIN_GRID), `validate_e9h_experiment` (data/E9H_INVALID_EXPERIMENT_AXES), `verify_historical_e9g_zip` (dependency/E9H_PREVIOUS_E9G_ZIP_MISSING or contract/E9H_UNVERIFIED_HISTORICAL_SOURCE), `build_e9h_deadline_schedule` (contract/E9H_COST_VOTE_DEADLINE_ORDER), `iter_e9h_arms` (2×2 frozen ablation), `run_e9h_original_voting_case` (contract/E9H_PACKET_LEDGER_MISMATCH, safety/E9H_COMMIT_LEDGER_MISMATCH), `pair_e9h_against_fixed` (contract/E9H_MISSING_PAIRED_BASELINE), `summarize_e9h_cases` and `summarize_e9h_scaling` (accurate censored/completed-only stats), `create_e9h_deadline_curve`, `save_e9h_evidence` (contract/E9H_EMPTY_EVIDENCE_TABLE), `run_e9h_experiment` (state/E9H_OUTPUT_EXISTS, contract/E9H_INCOMPLETE_FACTORIZED_GRID, dependency/E9H_GIT_SHA_UNVERIFIED), `main` CLI. Primary conditions 5..100/5 R=T=N, 100seeds per cell, p_loss=0/0.3 on Cost+Vote, reliable TASK/Score/Commit, models Rady-only and 144/600/1200 Mbps hypothetical E9G proxy, baseline fixed 609.1129007777778ms and positive/25% threshold, adaptive D_cost(N)/D_vote(n) at k=1 and same 25%/positive threshold; total 64,000 original executions. k=0/2 optional independently frozen sensitivity. `full_commit`, STOP time on failed/censored, only successful allocation time when all tasks Commit, missing Cost/late Votes, candidate Score, share/ties, two-hop radio counts, original Byte ledger and cost vs external Hungarian observer reported; no supplied oracle to voters. Baseline pair matching only after all on-chain messages complete. SHA256 source raw, summary, exponent, deadline curve and immutable output paths. Only publish E9H graphs to README after user runs and independent audit. All paper citations with used versus pending limits in README §3.8. `docs/figures/e9g_wifi/formal/publication_manifest.json` E9G earlier source raw SHA corrected from transcription typo to actual user ZIP verified SHA `ba79fd138d84d6d3bb7f04430a36a8c3e973d7ca0978834d4ad3a3b1d3f85be6` without changing original raw experiment content.


### 40.1 E9H predeclared evaluation gates (before primary 100-seed data)
No post hoc optimization of safety margin or hidden truncation of failed runs. All N/loss/network/mode combinations report original 100 matched seeds, p50/P95 of successful completed time, all-seed stop-time (when censored), noninferiority in full-Commit rate, sender Bytes/SENDs, late physical Vote and Cost, tie Score messages, winner vote share and exact cost ratio to **external observer** full Hungarian. At p_loss=0, adaptive received should attain >=99/100 complete per N/network; at p_loss=0.30, compare matched difference and flag >5 percentage-point loss. N100 loss0 goal is >=50% shorter conditional successful mean time than fixed-quarter under same modeled channel; cost ratio to Hungarian must not increase by >5 percentage points (when both full). Safety no duplicate Commit or zero-vote announcement is absolute. Negative outcomes count; never tune k using the formal seed results, never present reference phy rates as actual 100-station measured throughput.


### 40.2 Explicit test and audit for both Rady and shared-medium late Cost/Vote
Formal E9H on-time Cost/remote Vote filtering is implemented for both original pinned Rady-only and E9G simplified shared-medium samplers, and *does not* apply to legacy old opt-out paths. Tests prove a physically delivered Cost late relative to one original initial-Cost deadline remains in ledger while excluded from local visible source view (and legacy original still includes it); a remote Vote late relative to **global** cutoff remains physically delivered but not logically counted; no Score from zero received; k0/k1/k2 timing sensitivity increases monotonically if P95>mean; actual old original Voting source and new variant each preserve one-to-one Commit. E9H CI prints 100R zero and 30% loss, including cost and support, without conflating one-seed smoke with formal 100-seed statistics.


## 41. E9H-4 one-time guarded Cost source subexperiment (added from 1-seed pilot, before user 100seed)
Bounded Cost-time concern owner `democracy_mrta.network.estimate_e9h_guarded_initial_cost_ms`: `max(Rady_control_delay_ms) + 2*N*((preamble+AIFS+CWmin*slot+ACK)/1000 + 8*(CostBytes(N)+H)/(1000*designPHY_Mbps)) + 1ms`. Deterministic upper envelope from Rady's **observed maximum** and the same E9G PHY/MAC assumed single-medium model, not a field-guaranteed bound. New first-failure codes network/data/E9H_INVALID_GUARDED_COST_GRID and network/dependency/E9H_GUARDED_COST_RADY_MISSING. The original Cost is broadcast ONCE for one N-task problem; the new guard never repeats every task. The active-round **Vote** still uses `D_vote(n)` from §39 with k predeclared and n decreasing; all Score/Commit logic original unchanged. Strictly 2 added experimental arms `adaptive_guarded_k1_quarter`/`adaptive_guarded_k1_received`; former short Cost variant and all fixed arms remain. N100 1seed CI with short Cost (before change) had external Hungarian-relative cost ratio fixed1.306 vs short1.669, showing a quality-risk and motivating this separately identifiable experimental factor. **The new 6-arm 96k formal study still has no user-provided 100seed result**; do not treat one-seed pilot as a formal outcome. Full physical receipts/cost quality must be independently checked; no new radios, Vote state machine, negative results deletion or reference contamination.


### 41.1 E9H-4 observed one-seed preflight (NOT formal) and verification
CI [run 38195938305](https://github.com/andyfu35/Democracy-based-Task-Allocation-in-a-Large-scale-Multi-robot-System/actions/runs/38195938305) source commit `57a02bc6640c6afdc956d67c627d5266a365c45a` **SUCCESS**: 13 targeted E9H tests, 8 E9G tests, whole repository regression, and pinned Rady 5/20/100 1seed×2 loss×2 radio settings×6 original Voting arms (72 rows). N100 zero-loss modeled 144 Mbps, fixed-quarter 69.280s cost/Hungarian1.306135; shortCost/adaptiveVote received 17.402s ratio1.669075; guardedCost/adaptiveVote received 17.530s ratio1.306135. One-time guarded Cost did not make the 100 short per-task Vote deadlines long. p_loss=0.30 N100 guarded received 20.092s cost/Hungarian1.306135 vs fixed-quarter69.873s ratio1.334136. All N100 one-seed cases full Commit; no inference permitted about 100-seed distribution or real Wi-Fi. Artifact ID11723467031 archive SHA256 b5591c89ebab0fe5e04fc11743175e7916abcdf1c10699e127e9e66bc3d5fea6, exact CI log discloses all variants. User formal 100-seed E9H evidence remains MISSING and README shall only publish formal graphs after SHA256 verification.


## 42. E9I Cost-only 30% loss-isolation in existing original E9H experiment owner
User-fixed `P(Cost receiver loss)=0.30`, independent `P(Vote receiver loss)=0` primary and `P(Vote receiver loss)=0.30` companion, original reliable TASK/Score/Commit unchanged. The true original `coordination.simulate_democracy_hungarian_retirement(p_loss,p_vote_loss)` already owns independent Bernoulli loss semantics and must not be modified. `experiments.run_e9h_adaptive_deadline.run_e9h_original_voting_case` now accepts **only optional** `p_vote_loss=None`: None preserves old E9H `p_vote_loss=p_loss` behavior, explicitly supplied vote loss forwarded to true owner. Per-run outputs new `cost_loss_probability` and `vote_loss_probability`, original two counters for Cost and Vote `physically_lost_*_count`, `cost_remote_receiver_observation_count` (should equal N(N-1)), `cost_effective_peer_view_fraction=(Cost_receipts_on_time)/(N(N-1))` accounting both receiver-drop and late receipt. Ledger contract `experiments.run_e9h_adaptive_deadline.run_e9h_original_voting_case/contract/E9I_COST_RECEIVER_LEDGER_MISMATCH` ensures first failure if a claimed Cost receiver opportunity was not recorded. This is **receiver-level Bernoulli loss**, NOT exactly 30% missing *physical broadcast SENDs*: one sender packet may reach some peers but not others. No change to old algorithms, default E9H loss pairing, deadline formula, relative plurality, or original radio model.


## 43. E9I original Cost 30%-fixed R=T=N scaling, Vote loss 0/30 controlled

The experiment source is the original Greedy Voting Cost/Vote/Score/Commit owner; there is no new Vote state machine or network behavior. Independent Cost/Vote Bernoulli parameters already belong to coordination.simulate_democracy_hungarian_retirement(p_loss,p_vote_loss) and network.BernoulliLossSampler.is_delivered. Frozen Cost receiver delivery failure is p_cost=.30 for all 20 N sizes, 100 seeds formal, Tasks=N. Paired primary Vote failure p_vote=0 and companion p_vote=.30; reliable TASK/Score/Commit unchanged. This is per-REMOTE-RECEIVER Cost observation Bernoulli, not physical correlated Wi-Fi frame loss or an exact 30% broadcast-SEND failure.

The existing E9H experiment owner run_e9h_original_voting_case has only an opt-in p_vote_loss argument; None exactly preserves the previous E9H p_vote_loss=p_loss behavior. It reports actual n(n-1) Cost remote receiver observations (contract E9I_COST_RECEIVER_LEDGER_MISMATCH), Cost drops vs late Cost, Vote drops, on-time Cost peer view completeness, original real source application Bytes and SENDs, Vote Score and Commit, quality and success. First diagnostic in owner experiments.run_e9h_adaptive_deadline.run_e9h_original_voting_case category contract for nonmatching original Cost ledger.

New E9I orchestration owner experiments.run_e9i_cost30_scaling contains validation validate_e9i_cost30_axes / data / E9I_VOTE_LOSS_PAIR_NOT_FROZEN, output root prepare_e9i_output / state / E9I_OUTPUT_EXISTS, chosen original named four arms selected_e9i_arms / contract / E9I_ARM_CONTRACT_MISSING, run_e9i_cost30_scaling / dependency / E9I_GIT_SOURCE_SHA_INVALID and contract / E9I_GRID_INCOMPLETE, summarize_e9i_scaling separating successful and stopped time, summarize_e9i_empirical_exponents refusing to label censored-stop fit as successful-time growth, write_e9i_provenance / contract / E9I_EMPTY_OUTPUT. All original formal raw/summary/exponent CSV and manifest SHA256 are immutable. At 144 Mbps assumed shared-medium original E9G proxy, 20 sizes x10 pilot seeds x2 Vote-loss conditions x4 arms = 1,600 original simulations. 100 seeds formal gives 16,000; with optional original Rady-only timing model 32,000. No CBAA, ns-3, OFDMA, physical robot test or real RF throughput measurement implied. Each source and limitations are cited individually in README §3.9, referring to the pinned Rady dataset and historical E9G E9H documented QoS constraints.


### 43.4 Source-verified 10seed pilot and research status (NOT 100seed)
Original source 28bf8ccd96950b9d23c6daf4c57db729ae3d65bc, CI run38196908382, artifact11724211340, archive SHA256 cf441ea596e3907b8d0e2f8e5f60ff26ab7c1b150fdc33ac1b054a38f1165e85. Raw source 1,600 rows SHA256 6edc32c4fa026f4f03b55f24e593dd66ebc8682654b5153cbd4a717710a0063d, group160 rows SHA256 23fb11663fc46126e0ce40fc8fbb70ec39f07ba9df92bbfdd84127e6206f5f3b, exponent SHA256 9bee58e8cde35ff9f8acdad586e08a3ffb72bf8b9ce0d32a56fc34b7b9f9eb2d. Independently recomputed all source group average true successes, Bytes, SEND, original Cost per-peer validity, dropped frame observations, elapsed/stop times. All 1600/1600 fully committed in 10seed pilot, no guard. N100 original received plurality Cost .30 Vote0 fixed 72.004s, guarded Cost+short Vote20.134s, short Cost+short Vote19.777s; all cost/Hungarian ratios respectively1.3513,1.3513,1.4508. Sender Bytes 256.413kB fixed and256.336kB guarded, 69.93% original Cost peer view vs shortCost67.90%, ~2,976.7 dropped peer Cost observations per 9,900 at N100. Source graph values are rounded, full 1600-row original CSV preserved in CI artifact not committed to Git. README §3.9 cites all used and still-pending papers. This is only a source-backed 10seed simulator pilot and is not a 100seed statistical or physical 100robot Wi-Fi result. No protocol/runtime function, diagnostic category or source state machine changed by this documentation/chart publication.


### 43.5 E9I verified 100-seed formal 30%-Cost original Voting results (post-run publication)

User-executed source ZIP e9i_cost30_formal_100seed.zip SHA256 5d275bebd8d6f985e8eef1bbba9a0947991cd71660c1cc49817619e6bc276ee5; original executable HEAD 408ff70a31e8c2957602cae3f09ad8f239cd3224. Its original 16,000-row per-seed SHA256 1249661d6efeee70c377e76b04176f0923a8051fd983e4aeef3571918041d3f7; original 160-group summary SHA256 caae0ee64f8ccdd4febbbebb63240fa2e66502c8c99b20ff95383a653c3fafb3; original eight exponents SHA256 3c524a07610cdeeb0859c2301715cd9a419eca51e82278728cc33051809b9feb. All source SHA match. Independently recalculated every source summary group and exponent, checked 20 N points x100 seeds x2 Vote p x4 arms unique and complete, actual original SEND/Cost reception accounting. User source run was NOT modified.

15998/16000 original simulated tasks sets fully committed; 2 real 300-round guard-censored failures exclusively fixed_quarter: 25R Seed99 Vote0 21/25 tasks; 70R Seed67 Vote0.30 66/70 tasks. Any plots of fixed_quarter successful completion time necessarily exclude these 2; full-Commit rate and all-seed stop time retain them. All three received-plurality arms have 100/100 task full Commit in each N/Vote condition in THIS simulator only. N100 Cost30 Vote0 fixed_received full100 mean72.261719s sender256430 B cost/Hungarian1.359439 vs adaptive_guarded received full100 mean20.450382s sender256342 B cost/Hungarian1.360430. N100 one-time guarded saves71.6996% paired mean (6000 fixed-seed paired bootstrap 95% 71.4235%-71.9764%), small paired Cost/Hungarian delta +0.000991 (95% +0.000100..+0.002269); exactly same assignment in88/100. Short Cost mean20.225145s but reduced remote Cost view67.857% vs guarded69.985%, worsened Cost/Hungarian to1.473663. Vote30 guarded mean20.131588s vs fixed71.917725s, 72.0075% paired reduction, Cost ratio delta+0.002859, exact assignment82/100. 100R Vote0 received Score announcements364.77 for guarded vs122.62 old 25%-qualified, clear traffic/liveness trade-off.

Empirical completed-time finite log-log slopes Vote0 fixed_received0.969830 vs guarded0.956871; application Bytes1.843 and SENDs1.804 over N5..100, NEVER claims physical Big-O/802.11ax. The old quarter threshold has two failures and source slope is censored STOP time, not completed-time scaling. The formal nine source-driven rounded SVG plots and plot-driving 20-point CSV, manifest source digests are at docs/figures/e9i_cost30/formal/. The exact full raw records stay in user upload and downloadable analysis, not artificially cloned into Git. DOI-based paper attribution, measured vs modeled, and future ns3/EDCA/OFDMA/field limits remain explicit in README §3.9. This is a result-publication concern, NO changes to runtime owner or protocol/diagnostic contracts.


## 44. E9J immutable E9I Voting baseline versus source CBAA
Frozen E9I 100-seed original user archive SHA256 5d275bebd8d6f985e8eef1bbba9a0947991cd71660c1cc49817619e6bc276ee5 and source SHA 408ff70a31e8c2957602cae3f09ad8f239cd3224. Compare N=T=5..100, matched seeds 0..99, original E9G hypothetical 144Mbps shared-medium Rady bootstrap. Voting original Cost receiver loss30%, Vote0/30% arms fixed_received and adaptive_guarded_k1_received; CBAA uses its OWN original full Bid/Winner vector (16+12*T Bytes) per original Auction/Max-Consensus iteration, original receiver loss30%, no Cost/pose exchange. Do NOT equalize each algorithm's natural number of SENDs. Original CBAA simulator local_certification stop is optimistic aggregation of local evidence, without paid distributed stop or reliable Commit. Separate observer agreement, local certification, guard-censored stopping time, sender Bytes, SENDs, and external Hungarian cost from Voting real Commit. New network owner estimate_e9j_cbaa_consensus_window_ms uses max published Rady sample plus full-CW 2-hop N packet-wave service +1ms, not a PHY field guarantee; structured failures network/data/E9J_INVALID_CBAA_WAVE_INPUT or network/dependency/E9J_CBAA_RADY_PROFILE_MISSING, existing PHY validator. Choi, Brunet & How IEEE T-RO 2009 DOI 10.1109/TRO.2009.2022423 authentic CBAA/CBBA distinction. Native original CBAA and Voting runtime remain unchanged. No ns-3, real 100-station collision model or distributed CBAA halt. Full paper attribution in README section E9J.


### 44.4 E9J source runner and future protocol comparison
New experiment owner experiments.run_e9j_cbaa_vs_e9i consumes ONLY SHA256-pinned original E9I ZIP and calls existing cbaa.simulate_cbaa with local_certification and default 160-iteration safety guard; original CBAA full Bid/Winner packet, no new state machine or CBAA raw other-robot data. Named boundaries: validate_e9j_axes data/E9J_INVALID_SCALING_AXES, contract/E9J_BASELINE_REQUIRED_FOR_FORMAL_COMPARISON or E9J_PAIRED_AND_SMOKE_MODES_MIXED; load_e9j_pinned_e9i_baseline dependency/E9J_E9I_ORIGINAL_ARCHIVE_MISSING, contract/E9J_BASELINE_ARCHIVE_SHA_MISMATCH, E9J_BASELINE_SOURCE_CONTRACT, E9J_INCOMPLETE_BASELINE_PAIRING, E9J_DUPLICATE_BASELINE_KEY, data/E9J_INVALID_BASELINE_SOURCE and E9J_INVALID_BASELINE_ROW; prepare_e9j_root state/E9J_OUTPUT_EXISTS; run_e9j_original_cbaa_case contract/E9J_CBAA_PHYSICAL_LEDGER_MISMATCH, safety/E9J_CBAA_OVERSUBSCRIBED_TASKS; pair_e9j_against_e9i only read-only paired reporting; summarize_e9j_comparison segregates completed time vs censored stop; write_e9j_evidence contract/E9J_EMPTY_EVIDENCE; run_e9j_cbaa_vs_e9i dependency/E9J_INVALID_EXECUTABLE_SHA, contract/E9J_INCOMPLETE_CBAA_GRID. All timestamps, original application sender Bytes/SENDs, modeled radio airtime/hops, CBAA posthoc observer and local optimistic certificates separately. One CBAA physical execution per size/seed, never repeated for each Vote comparison arm. Output raw original CBAA CSV, pair CSV, group CSV, SHA manifest. If baseline missing allow ONLY explicitly named <=3seed <=20robot UNPAIRED smoke with no formal comparison. No claims of actual measured 802.11ax, no CBAA paid Commit/stop.


### 44.5 E9J original source tests
E9J verifies original CBAA packet vector 16+12*T, one SEND each active source per iteration, N*(N-1) receiver opportunities per iteration, causal modeled radio airtime, source input scene/seed consistency, unchanged CBAA natural local certification and implicit observer (not a paid Commit), read-only paired Voting baseline record, strict rejection of wrong original source ZIP, and SHA256 manifest. An unpaired smoke is constrained by E9J_BASELINE_REQUIRED_FOR_FORMAL_COMPARISON to <=3seeds <=20robots and cannot be misreported as a formal comparison.


### 44.6 E9J runtime CI and paper-source contract
README §3.10 links exact CBAA 2009 paper and fully scopes sampled Rady timing versus other reference-only papers; unmodified 100seed E9I ZIP is a SHA256-hard gate to formal comparison, not rerecorded Voting data. CI must run named E9J/CBAA/E9I tests then a 5/10/20 one-seed CBAA UNPAIRED smoke and never present its results as paired. Original Vote real Commit and CBAA optimistic local-certified observer outcomes remain distinct.


### 44.7 Shared immutable E9I baseline archive owner (future methods)
The single E9I user archive SHA256 and original-row provenance/validation owner is now experiments.voting_baseline_registry.load_pinned_e9i_voting_baseline, not E9J CBAA orchestration. E9J invokes this true shared archival reader; CBBA and later original methods MUST also call it instead of copying or circumventing proof. Frozen constants BASE_ZIP_SHA, BASE_GIT_SHA, BASE_CSV_SHA, BASE_ARM_NAMES, BASE_VOTE_LOSSES in that same owner. First structured errors use owner experiments.voting_baseline_registry with original named function and existing dependency/E9J_E9I_ORIGINAL_ARCHIVE_MISSING, contract/E9J_BASELINE_ARCHIVE_SHA_MISMATCH, contract/E9J_BASELINE_SOURCE_CONTRACT, data/E9J_INVALID_BASELINE_SOURCE/E9J_INVALID_BASELINE_ROW, contract/E9J_DUPLICATE_BASELINE_KEY/E9J_INCOMPLETE_BASELINE_PAIRING (kept for old tests and evidence compatibility). Responsibility moved: source archival evidence only; CBAA experiment owner still owns scenario execution, radio summarization and paired empirical comparison. No new Vote engine or source rewriting; actual original archive hash and all 100 paired IDs remain immutable.


### 44.8 E9J source-backed single-seed preliminary verification
E9J source moved-baseline owner source commit 4f81a48d8b7730660148011f980a0c17a4b145f0, GitHub Actions run 38199947659 SUCCESS; original CBAA CI artifact11725340203 SHA256 aeef1908efd18f8b532645e1d77c74e609977b28858136c2547127777a962161. All 6 E9J, 13 E9I and existing CBAA tests pass. Original N5/10/20 seed0 CBAA local certified+observer agreement after 7/10/15 rounds; modeled task-plus-CBAA time3770.781/5407.629/8267.804ms, application sender Bytes2836/13936/77456. Independently joined exact E9I source archive seed0 Vote0 original guarded received-plurality input: N5 1276.393ms 1108B, N10 1691.560ms 3560B, N20 3316.837ms 11936B. This is a three-point one-seed PREVIEW with DIFFERENT CBAA versus Voting success contracts, NOT validated formal 100seed original-CBAA results. No original source code touched by this documentation and not claimed measured 802.11ax.

### 44.9 E9J formal original-source 100-seed evidence (source-only publication)
Original user-run ZIP SHA256 106fc14aa9088edf980a744bf9e129c516ce8cabf9c23322baa76be9b33c82bb; E9J executable Git SHA 3a69bdef32fa4f430de5949768bf38a54987ffd1; original CBAA per-seed SHA256 a586b364a5861fc383c62f5f327afa16a796b46076e42d15ef4722dad40ba189; paired E9I/E9J SHA256 58da8db65ef32fee20e9d94601ed391337bc664caaccbcd23c01f5d6769cb3a2; group summary SHA256 5c2e89ed8962ca54377aea8204fde0126ae5fb99acbbd70379818276b1e6ac83; user Vote30 extracted summary SHA256 36ff0e8c33af3ecad43fc40e50f5cfb74819e0a344d306f5fd1eabcd7696e092. Audit independently checks all manifest digests, 2000 unique native CBAA N×seed runs, 8000 paired cases, 80 group means and all 40 selected Vote30 group cells, exact n(n-1) receiver opportunities per CBAA iteration, original sender Bid/Winner packet 16+12N Bytes, original sender byte ledger and CBAA task count.
Predeclared canonical native dynamics remain unchanged: TASK reliable; E9I Voting Cost p=.30, Vote p=0/.30; native CBAA full-vector Bid/Winner p=.30. Primary published plot compares Voting Cost.30/Vote.30 with CBAA Bid.30 at N=T=5..100 step5 100 seeds. CBAA 2000/2000 local certified AND observer consistent, every N tasks assigned, guard failures 0; Voting both frozen control arms with Vote30 2000/2000 full genuine Commit. N100 guarded Voting elapsed20.13159s vs original CBAA local-certificate 13.64743s, original sender255497.6 B vs2693040 B, observer cost/Hungarian1.36215 vs1.23526. Model time crossover N55/60 is not seed-paired 95% significant; at N65 mean difference CBAA−Voting−1.22771 s CI95 [−1.57182,−.87881]s. N100 time change 32.2089% shorter for CBAA paired bootstrap CI95 [30.3355,34.0648]%, mean Cost/Hungarian delta −.12689 CI95 [−.14391,−.11020]. Bootstrap source 10000 paired draws rng20261012; graph input 20-point means rounded 5 decimals in docs/figures/e9j_cbaa/formal/, raw data only user archived.
NO owner code or diagnostics changed; do not infer equivalent stopping guarantees: CBAA simulator global optimistic certificate lacks paid CBAA terminal messages/Commit while Voting has reliable Commit. Time/airtime from hypothetical 144Mbps radio with Rady samples are not physical measured throughput, ns-3, collision/OFDMA or universal scaling. Future full paid distributed CBAA halt/Commit and RF/MAC is separately scoped; archived 100seed E9I original unchanged.

### 44.10 E9J primary figure condensation (presentation-only)
To keep E9J README/paper figures focused, exactly two primary source-backed SVG images are displayed: `primary_time_and_sender_bytes.svg` (two panels: modeled algorithm-specific elapsed time and original sender application KiB) and `primary_cost_quality.svg` (Hungarian-normalized assignment quality). Both use only the existing immutable 20-point rounded CSV from §44.9, compare Voting original Cost30/Vote30 guarded adaptive with CBAA original Bid30 and maintain explicit CBAA optimistic no-paid-stop qualification. All original eight detailed E9J SVG files, original plot CSV, original source manifest, full user-run ZIP SHA and E9J/E9I source execution SHA are preserved. The separate presentation_manifest.json records the selection, source and unchanged supplementary figures. No algorithm, network, method output, success definition, timing data, diagnostic, CI or test behavior is modified; per-method time CI shading must never be substituted for paired-difference CI inference.

## 45. Cross-experiment result selection and public evidence audit (presentation-only)
The main README publishes only four core SVG figures: E9E 52-loss-point original outcomes, E9I original Cost30/Vote30 deadline comparison, E9J combined modeled time and actual attempted sender Bytes, and E9J Hungarian-normalized assignment cost. Formal E0/E1 evidence is described numerically. E9G is a verified but auxiliary simplified network-proxy sensitivity; E9C is a method-accounting control; E2 is provisional pending a vote-level forensic audit; the separate E9H complete factorial has not been formally established. Every older experiment and image remains in docs/EXPERIMENT_RESULTS_ARCHIVE_20261012.md, a snapshot of the pre-curation root README with only relative document/image links adjusted. Verification methods and all immutable original source hashes are indexed in docs/EXPERIMENT_RESULTS_AUDIT_20261012.md. No source protocol behavior, packet loss, scoring, optimizer, named owner function, diagnostic boundary or experiment source case has changed. E9E 100R/50T synthetic latency vs E9I/E9J 100R/100T Rady+assumed radio cannot be pooled. CBAA optimistic observer/global stopping certification is not an actual paid distributed Commit.

## 46. E9K — paid CBAA experiment implemented on `experiment/e9k-paid-cbaa-finalization` (not merged into main source)

**Single scoped functional extension** of original native CBAA; no change to E9J `stop_mode="local_certification"` or legacy `fixed`. `democracy_mrta.cbaa.simulate_cbaa` invokes `democracy_mrta.cbaa_finalization.advance_paid_cbaa_finalization` iff `stop_mode="paid_termination"`. Native `cbaa_auction_phase`, `cbaa_consensus_phase`, `exchange_cbaa_consensus_packets`, `cbaa_local_convergence_certified` remain the original decision and peer-evidence owners, with same Bid/Winner payload `16+12T` B. `cbaa_finalization` is a distinct owner exclusively for paid control messages and local proof ledgers, never a second Auction/Consensus or a wrapper applying free global proofs.

Two control stages: per-node READY follows native local physical peer convergence evidence, packet 48B = original 16B application header + SHA256 32B common Bid/Winner vector digest (not authenticated). READY sent each later iteration while ready, independently dropped per receiver. COMMIT sent iff that node's own local digest-matching READY inbox contains all N peers. A node is individually finalized iff its *physically received*, on-time, digest-matching READY and COMMIT inboxes both contain all N peers, counting only its own local emission as loopback. If local state/digest becomes invalid, its own READY and COMMIT receipts reset; stale or mismatching new packets cannot be counted. No simulator global stop-ready signal is an agent's input; overall simulation halts only if all these independent local receipt completions are observed, or guard160 is reached. A posthoc observer assertion checks full unique N assignment on full success; it never awards a local certificate. Finite READY/COMMIT cannot establish common knowledge of globally final completion, and no physical distributed FINAL_ACK protocol is yet proven. Never call this Voting-equivalent reliable Commit or native original paper CBAA.

**Time/transport contract:** native CBAA Auction/Consensus repeats between paid control rounds; each stage sends original broadcast application packets through shared `_broadcast_event` and receiver-specific `_lossy_broadcast_deliveries`, with delivered *on-time* packets only. Every original SEND charged once; `pBid=pReady=pCommit=0.30` independently by message-specific hash key; original Task announcement reliable and paid. Assumed E9G shared 144Mbps + pinned Rady application residual (NO ns-3, OFDMA, MAC collisions or measured 100station throughput). Paid READY and COMMIT windows each use the **same conservative E9J native full-vector phase window**, charged only if at least one sender actually broadcasts in that wave; no free control stage or summation of concurrent per-packet latency. This conservative synchronization-window assumption is a potential overestimate and must be separately varied in a future controlled ablation; it is NOT paper-measured Wi-Fi time. E9K native CBAA may continue additional rounds, so native Bid SENDs and assignment can differ from E9J free-stop scenario; do NOT calculate paid time by adding a guessed constant to E9J.

**Paired source invariant:** formal E9K requires the original immutable E9I ZIP SHA256 `5d275bebd8d6f985e8eef1bbba9a0947991cd71660c1cc49817619e6bc276ee5` via original true `experiments.voting_baseline_registry.load_pinned_e9i_voting_baseline` and original immutable E9J ZIP SHA256 `106fc14aa9088edf980a744bf9e129c516ce8cabf9c23322baa76be9b33c82bb` via new separate archive-source owner `experiments.cbaa_baseline_registry.load_pinned_e9j_cbaa_baseline`. Both preserve original full per-seed provenance; zero baseline simulation or copying of source rows. Original E9J native executable SHA `3a69bdef32fa4f430de5949768bf38a54987ffd1`. E9K scenario keys `N=T=5,10,...,100` and seed0..99; 100 actual paired repetitions each cell, guard160. Unpaired smoke only explicitly flagged and restricted <=3seed N<=20. Formal output original E9K per-seed CSV, group summary, SHA manifest, no overwriting existing output. Full success report **separate** per-node all-N proof count, native observer agreement, guard, actual Voting full Commit, all-seed censored stop versus conditional paid success time, original native E9J optimistic stop and immutable sender Bytes. No E9K formal result is declared before local user-run source archive is verified.

**Named diagnostic boundaries:** owner `democracy_mrta.cbaa_finalization` functions `validate_paid_cbaa_finalization_config` time/E9K_INVALID_CONTROL_TIMEOUT, `create_paid_cbaa_finalization` data/E9K_INVALID_FINALIZATION_ROBOTS, `synchronize_paid_cbaa_local_proofs` contract/E9K_LOCAL_PROOF_CARDINALITY, `exchange_paid_cbaa_control_packets` contract/E9K_INVALID_CONTROL_PHASE, state/E9K_CONTROL_WITHOUT_LOCAL_CERTIFICATE and contract/E9K_CONTROL_DELIVERED_WITHOUT_TIME, `advance_paid_cbaa_finalization` owns the separate communication execution boundary. Existing `democracy_mrta.cbaa.simulate_cbaa` contract/E9K_CONTROL_OPTIONS_REQUIRE_PAID_MODE and safety/E9K_PAID_PROOFS_CONFLICT_WITH_OBSERVER. New `experiments.cbaa_baseline_registry.load_pinned_e9j_cbaa_baseline` dependency/E9K_E9J_ARCHIVE_MISSING, contract/E9K_E9J_ZIP_SHA_MISMATCH/E9K_E9J_SOURCE_CONTRACT/E9K_E9J_DUPLICATE_OR_INVALID_KEY/E9K_E9J_INCOMPLETE_FULL_ARCHIVE/E9K_E9J_MISSING_MATCHED_CASE, data/E9K_E9J_ARCHIVE_INVALID/E9K_E9J_ROW_INVALID. `experiments.run_e9k_paid_cbaa`: `validate_e9k_axes` data/E9K_INVALID_AXES and contract/E9K_BOTH_PINNED_BASELINES_REQUIRED/E9K_SMOKE_WITH_BASELINE_OR_FORMAL_SIZE; `prepare_e9k_output` state/E9K_OUTPUT_EXISTS; `validate_e9k_original_scene` contract/E9K_E9J_SCENE_OR_RADIO_MISMATCH; `run_e9k_paid_case` contract/E9K_NATIVE_VS_PAID_PACKET_LEDGER_MISMATCH/E9K_PHYSICAL_RADIO_LEDGER_MISMATCH; `run_e9k` dependency/E9K_INVALID_GIT_SHA and contract/E9K_INCOMPLETE_GRID. Shared network/optimizer/input owner diagnostics unchanged.

**First acceptance:** local `test_cbaa.py`, `test_e9j_cbaa_vs_e9i.py` regression and `test_e9k_*.py` boundary tests plus small 3seed 5/10/20 local smoke; NO CI requested and **no accepted full formal E9K results yet**. Full 20 sizes × 100 seeds to be user-run. Local commands and SHA checks in [E9K guide](E9K_PAID_CBAA.md).

### 46.1 E9K actual user-run 100seed source audit (2026-10-12)
Original E9K executable Git SHA `715dfa6c262b7081c241b54a7bddec16354990a3`, immutable 2000-case user ZIP SHA256 `1495612c65a4fb40733af225b2121275e2b2309070695f2594c620079a6b8281`; per-seed CSV SHA256 `c6183a59177b37aaaf1ff2cd723ce4913f22646f137b4260813999df023be39b` and summary SHA256 `74de2dca68da7d8aff4c2d3c35742dc1a306e1d7fdcd6cd7b12b74c4ae4a1b56` both independently checked. Original E9J ZIP SHA256 `106fc14aa9088edf980a744bf9e129c516ce8cabf9c23322baa76be9b33c82bb` re-opened, all old source hashes verified, 2000 unique exact N/seed E9J CBAA raw and frozen original Vote30 guarded Voting paired source rows matched exactly. 20x100 E9K unique grid, 2000/2000 all-N READY/COMMIT local proof complete, no guard. Every per-seed physical original Bid/Control/TASK SEND-byte ledger, receiver attempts, drops bounds, phase time identity and original E9J/Voting time/bytes reproduced. All 20 E9K grouped means independently recalculated. E9K final assignment cost identical original E9J for all 2000 paired seeds.
N100 mean simulated time Voting 20.131588s, original E9J CBAA free stop 13.647431s, E9K paid 37.527083s. E9K paid−Voting paired +17.395495s CI95 [16.798490,18.038409]s; paid−free +23.879652s CI95 [23.486975,24.284600]s, deterministic 10000 paired bootstrap resamples. Sender original Bytes Voting255497.6, E9J2693040, E9K4074431.2, paid/Voting15.947x. Extra E9K original+paid Bytes versus E9J +1381391.2: paid control121615.2, additional native Bid1259776. Mean extra time 17.523198s paid phase waiting plus 6.356454s added native consensus waiting; original E9J22.12 vs E9K32.48 native iterations. Hungarian-normalized CBAA cost1.235261 vs Voting1.362148 at N100. This is a **source-backed MODEL and distinct protocol endpoints only**; 48B control packets are conservatively charged the original E9J full-vector timeout each nonempty stage. The 144Mbps radio rate and 30% Bernoulli drops are assumptions, ns-3/real 100station RF absent; finite per-node receipts do not prove a distributed final common knowledge of stopping. Do not infer real-airtime speed ranking or native CBAA paper terminal protocol. Derived figure CSV, SHA manifest, concise report at docs/figures/e9k_paid/formal/ and docs/E9K_FORMAL_100SEED.md. Frozen E9I/E9J/E9K original ZIP raw untouched.

## 47. E9L — Bertsekas-style distributed epsilon-price auction, 100-seed comparison (design + test stage)

**New comparator, not original CBAA/CBBA:** The task-home allocation extension uses the classical Bertsekas \(epsilon\)-auction price increment \(v_{best}-v_{second}+epsilon\) with physically sent, loss-aware BID and AWARD messages. Classical Bertsekas 1988 Auction algorithm: DOI 10.1007/BF02186476; original 1979 distributed auction documentation from the Bertsekas faculty archive. This project implements a **new 28-byte application-wire variant** (BID1/AWD1, per-task home, local versioned winner prices, independent Bernoulli loss, optimistic all-local-evidence stop). Never assert these wire details, packet losses, or stopping rules were specified by the original paper. Do not call it CBBA. Original CBBA (Choi/Brunet/How T-RO 2009) supports multi-task bundles; N=T one-task case would suppress its defining benefit and requires a separate R<T, capacity>1 benchmark, not a relabel of E9L.

**Fixed initial formal matrix:** N=T=5,10,...100; each seed0..99; every robot capacity=1; fixed epsilon=10.0 Euclidean cost units (world length100), not selected per formal-seed result; pBid=pAward=.30 native receiver loss; TASK announced by original reliable source; no pose sharing or global cost matrix to bidders; task home j is robot j for N=T, holds ONLY own task's bids and prices. Full packet sender Bytes count once per actual native 28B BID unicast / 28B AWARD broadcast, task owner self-access is local and unpaid. Task homes broadcast price/winner AWARD every iteration to overcome receiver loss, only physically on-time matching-version packets update peers. Bidder never holds more than one unresolved bid; no fictional extra winner or second auction state machine. Winner local certificate requires 1:1 nonconflicting all-N local AWARD views, no pending bid, and fresh physical evidence after own last bid. Observer full global output is posthoc and NEVER corrects local state; stopping when all local certificates is optimistic simulator aggregation, NOT Vote reliable Commit. Guard160 is only safety censoring; report failed cases in all-seed denominator. Bid increment epsilon is a method parameter and affects speed/quality; no covert posthoc tuning.

**Network / time owner:** democracy_mrta.network.estimate_e9l_price_auction_stage_ms computes from pinned empirical Rady max, assumed E9G 144Mbps PHY/backoff and **actual 28B message**, with two radio hops for one N-sender stage and 1ms guard, identical declared model family to E9J. Each occupied BID and AWARD stage charges one whole window, not packets multiplied by receivers; empty BID wave is not charged. Diagnostic: network.data/E9L_INVALID_PRICE_WAVE, network.dependency/E9L_RADY_PROFILE_MISSING, inherited network time and PHY validators. This is NOT physical MAC/DCF ns-3 collision/ARQ.

**Method owner:** democracy_mrta.price_auction named validation, encode_price_bid / encode_price_award, initialize_price_auction, propose_price_bid, apply_price_auction_bids, accept_price_award, transmit_price_bids, transmit_price_awards, price_auction_local_certified, audit_price_auction_homes, simulate_price_auction. First errors owner/function/category/code: data/E9L_REQUIRES_SQUARE_ONE_TASK_CAPACITY, data/E9L_INVALID_COSTS, data/E9L_INVALID_EPSILON, time/E9L_INVALID_STAGE_WINDOW, data/E9L_INVALID_SAFETY_ROUNDS, planning/E9L_NONPOSITIVE_AUCTION_BID, contract/E9L_SAME_VERSION_CONFLICT, contract/E9L_BID_DELIVERED_WITHOUT_TIME, contract/E9L_AWARD_DELIVERED_WITHOUT_TIME, data/E9L_INVALID_SENDER_BUDGET, contract/E9L_PHYSICAL_SENDER_LEDGER_MISMATCH.

**Baseline source (planned E9L runner):** no re-runs of E9I Voting, E9J original CBAA, or E9K paid CBAA; require exact original 100seed source ZIP SHA256s E9I 5d275bebd8d6f985e8eef1bbba9a0947991cd71660c1cc49817619e6bc276ee5, E9J 106fc14aa9088edf980a744bf9e129c516ce8cabf9c23322baa76be9b33c82bb, E9K 1495612c65a4fb40733af225b2121275e2b2309070695f2594c620079a6b8281. Baseline archive readers alone own raw source attestations; preserve actual original terms of completion: Voting paid reliable Commit; E9J optimistic CBAA local certificate + observer, E9K physical local double READY/COMMIT (no global terminal ACK), E9L optimistic local AWARD evidence + observer. This initial code stage makes **NO formal E9L 100seed numerical claim**. E9L per-seed physical new method and compared baseline row, all-seed grouped outcomes, SHA + Git/seed manifest and first named failures are required before promotion.

### 47.1 Frozen E9K paid CBAA source-gate owner
Original E9K user source ZIP SHA256 1495612c65a4fb40733af225b2121275e2b2309070695f2594c620079a6b8281 and original raw CSV SHA256 c6183a59177b37aaaf1ff2cd723ce4913f22646f137b4260813999df023be39b are loaded read-only by the **same existing** experiments.cbaa_baseline_registry owner, new named load_pinned_e9k_paid_baseline. It checks original E9K executed Git SHA 715dfa6c262b7081c241b54a7bddec16354990a3, exact E9J/E9I archive identities, complete 2000 case N=5..100/seed0..99 grid, native 48B paid-control and source sender ledgers. No E9K algorithm reexecution, no second E9K file validator copied into the E9L runner, no mutation of source original rows. Error boundary documented in continuity E9L archive entry.

### 47.2 Executable E9L runner and local acceptance boundaries

True study runner owner experiments.run_e9l_price_auction named validate_e9l_axes, prepare_e9l_root, validate_e9l_paired_scene, run_e9l_case, summarize_e9l, write_e9l_evidence, run_e9l, main. Source fields from immutable E9I Voting (via existing voting_baseline_registry), E9J original native CBAA and E9K paid CBAA (via existing cbaa_baseline_registry) are merged only by exact (N,seed) **after complete archived ZIP SHA validation**. None of those algorithms re-run. Frozen source data validation includes original Task announcement Bytes and time, same external scene/Hungarian optimum, identical original Voting/E9J result summary in the E9K archive. New per-run method produces native original 28B BID/AWARD SENDs, receiver attempts/drops, queue-model service, original Task bytes, all-seed stop and completed-only time/cost, optimistic locally certified count/observer full, safety censoring. 100 Seeds x N5..100 step5 = 2000 unique E9L runs. Smoke without any pinned archive is explicitly <=3 Seeds <=20 Robots and labeled UNPAIRED_SMOKE_ONLY. E9L epsilon10.0m is a predeclared *design-stage choice after limited synthetic seed0 exploration*, so method claims must not treat this as an unbiased held-out epsilon optimum; use separately held-out replication to test generality.

Errors: owner experiments.run_e9l_price_auction: validate_e9l_axes data/E9L_INVALID_GRID, contract/E9L_SMOKE_REQUIRES_SMALL_UNPAIRED or E9L_THREE_FROZEN_ARCHIVES_REQUIRED; prepare_e9l_root state/E9L_OUTPUT_EXISTS; validate_e9l_paired_scene contract/E9L_PARTIAL_PAIR_INVALID or E9L_E9I_E9J_E9K_SCENE_OR_PAIR_MISMATCH; run_e9l_case contract/E9L_NATIVE_PACKET_LEDGER_MISMATCH; write_e9l_evidence contract/E9L_EMPTY_SUMMARY; run_e9l dependency/E9L_INVALID_GIT_SHA and contract/E9L_INCOMPLETE_RUN_GRID. Original E9K ZIP loader in experiments.cbaa_baseline_registry owns dependency/E9L_E9K_ARCHIVE_MISSING, contract/E9L_E9K_ZIP_SHA_MISMATCH/E9L_E9K_SOURCE_CONTRACT/E9L_E9K_DUPLICATE_OR_INVALID_ROW/E9L_E9K_INCOMPLETE_GRID/E9L_E9K_UNPAIRED_SOURCE, data/E9L_E9K_INVALID_ARCHIVE/E9L_E9K_INVALID_RAW_ROW. Network time own categories remain in network. All original E9I/J/K runtime diagnostics unchanged.

**Acceptance:** tests/test_e9l_price_auction.py covers 8 native price/transport/diagnostic cases and tests/test_e9l_runner.py covers 5 source/runner/stage boundaries. This tool environment tested the module with synthetic imported stub transport and 2-size unpaired mocked runner (13/13); this does **not** replace native full-repository Mac unit tests or formal original-source 100seed evidence. No CI requested or executed. Do not display E9L timing/quality in main research README until formal raw ZIP is user-run, verified and statistical CI audited. Full Mac run instructions docs/E9L_DISTRIBUTED_PRICE_AUCTION.md.

### 47.3 E9L sender-paid wave boundary correction
Native task-home-local BID (bidder robot equals auctioneer robot) never physically emits a unicast. The BID wave is charged a network phase timeout only when `bid_wave.sends > 0`; local-only offers are computed without phantom communication wait. AWARD waves are charged iff their actual physical source SEND count is nonzero. This preserves independent original causal shared-medium scheduling and local source message semantics; no packet loss, epsilon, stop, task assignment or other method behavior changed.

### 47.4 Actual E9L user-run 100-seed original archive (2026-10-12)

Original executable Git `0e1a091c547b7cc0d545e0707c51138dfa626d5c`, original exact user E9L ZIP SHA256 `2b51cecbd84f105a2cee35bfcd8825de174cb3617f35596a81d94d4de6e5ff41`, per-seed original raw `4dd54863f7cb7392c29a0c91682a85c90750df8dc4af162ccb42ec2a9c426ad5` and original summary `220f2fa9c6446ada8daca3cdf14e8b7acd75b1feb640de83343595a3e8f4d3ac` SHA256s rehashed and match user manifest. 2,000/2,000 unique N=5..100 step5×seed0..99, exactly 100 each N; all per-row original 28B price BID/AWARD and TASK packet fees, sender SENDs, receiver trials/drops, optimistic local vs observer success, packet model clock counts and all 20 group means independently audited with zero errors.

Native E9L local+observer successes 1,867/2,000, 133 round160 guard censored; observer full 1,880/2,000, **13 observers-full but not locally certified**. First E9L full local failures at N45 (98/100), N100 78/100 local full and 79/100 observer full (Wilson local success CI95 68.93–85.00%). N100 simulated all-seed stop means Voting20.131588s/E9J original CBAA13.647431s/E9K paid CBAA37.527083s/E9L auction135.828345s **including guard-censored E9L attempts**. N100 E9L mean successful time 122.329249s on just 78 cases; sender Bytes in same order 255497.6 /2693040/4074431.2/**353939.04** B averaged all Seeds. Exact N100 E9L-complete matched-78 Cost/Hungarian means Voting1.366830/CBAA+paid1.234752/**E9L1.117319**. E9L completed-time minus Voting on same 78 seeds +102.127625s paired bootstrap CI95 [+93.834787,+110.483371]; E9L cost minus original CBAA −0.117433 CI95 [−0.131696,−0.104087] (10,000 paired bootstrap draws seed20261012). E9L has much lower sender Bytes than native vector CBAA, but **38.53% higher Bytes than Voting**, many more small packets, slower optimistic modeled stop, and greater guard failure at high N. Do not rank cost across unequal selected success cohorts or report all-seed stop as time-to-success.

Old ZIP SHA values E9I/E9J/E9K were preserved from the E9L executed manifest and cross-checked with original public E9K 20-point all-Seed source means, **but old original ZIP bytes were not supplied/rehashed in this turn**. Nothing reexecuted, altered or relabeled. Result is a frozen epsilon10 physical-cost task-home variant with independent pBid=pAward30%, simulator unpaid all-local certificate, not full Voting paid Commit, CBBA or physical ns-3/802.11. Full report docs/E9L_FORMAL_100SEED.md, 20point plot source and exactly two E9L compact SVGs in docs/figures/e9l_price/formal; README remains FOUR main embedded figures by replacing redundant E9J/E9K image usage, while original E9J/E9K SVGs remain supplementary. Diagnostic owner/function/category/code unchanged (source-only publication).

### 47.5 Official three-original-algorithm comparator contract (supersedes four-way *presentation*, 2026-10-12)

**Research decision:** the official E9L cross-method benchmark comprises **exactly 3 distinct task-allocation algorithms**: (1) Democracy/Voting E9I, (2) original/native CBAA E9J, (3) Bertsekas-style distributed Price Auction E9L. **E9K's 'Paid CBAA' is a novel team-authored change to original CBAA's termination protocol; it is NOT a fourth original/literature task-assignment algorithm and must not appear in primary algorithm comparison charts, per-method cost/time/bytes/success rankings, or headline performance tables.** Preserve E9K formal original ZIP, SHA/provenance, technical report and ablation figures unchanged as an internal protocol-validation experiment, not scientific baseline deletion. This clause changes only publication comparator membership, never the executed E9L algorithm or original frozen result.

20 N=T=5..100, seed0..99, loss30% and E9L 1867/2000 local proof successes / 133 guard-censored remain identical. Official 100R/100T rows: original Voting 20.132s / 255.5 decimal kB / 100/100, original CBAA 13.647s / 2693.0 kB / 100/100, E9L 135.828s all-seed censored stop / 353.9 kB / 78/100 complete; E9L 122.329s **only 78 successes**, conditional cost on matched 78 seeds Voting1.366830, native CBAA1.234752, E9L1.117319. Compare different stopping-contract semantics explicitly: Voting reliable Commit, original CBAA/E9L unpaid simulator aggregator. No physical ns-3, empirical 100-station RF or equal-airtime guarantee.

Public three-algorithm presentation files are `docs/figures/e9l_price/formal/three_algorithm_plot_source_20point.csv`, `docs/figures/e9l_price/formal/primary_three_algorithm_time_and_sender_bytes.svg`, `docs/figures/e9l_price/formal/primary_three_algorithm_completion_and_quality.svg`, and `docs/figures/e9l_price/formal/three_algorithm_presentation_manifest.json`. They extract unmodified columns from source-derived original `docs/figures/e9l_price/formal/plot_source_20point_rounded.csv`; the original four-way figure and its complete plot CSV remain immutable archival evidence, not current algorithm-ranking output. The E9L historical original executable `experiments.run_e9l_price_auction.run_e9l` currently requires an E9K ZIP as a **frozen data-provenance gate only**, as explicitly recorded by the original-run source SHA `0e1a091c547b7cc0d545e0707c51138dfa626d5c`. Never edit or claim that historical source/run was different. For *future* benchmarks use a separate scoped runner/source owner so only genuine algorithm baseline inputs are needed; do not change the committed E9L 100seed source. No code owner, function, transport, diagnostic first-failure category/code, or experimental protocol behavior changes in this presentation correction.

## 48. E9M — original multi-task CBBA versus new multi-task Voting (executable candidate; native Mac verification pending)

Original CBBA is the two-phase bundled multi-assignment algorithm in Choi/Brunet/How, IEEE T-RO 2009, DOI 10.1109/TRO.2009.2022423, not CBAA repeated four times. This experiment fixes 25 robots, 100 tasks, maximum capacity4, 100 paired seeds (0..99), square 100m world, same robot/task coordinates, speed1m/s and service0, independent p=.30 receiver loss on original CBBA consensus vectors and separately on Voting Cost/Vote; Task announcement plus Voting Score/Commit reliable and paid. Common path-aware utility sum_j (100 * 0.999 ** cumulative route distance at j). Original CBBA must retain actual ordered bundle, separate execution path, best path insertion, task winner/bid/timestamp consensus with true Choi decision rules and loss-triggered suffix release; classify our wire packet framing as network extension, NOT specified by original paper. Voting is a NEW multi-task capacity-aware extension of original Cost/Vote plurality, not the original one-task E9I runtime itself. CBBA and Voting only; E9K paid CBAA is explicitly excluded.

Every original application SEND and native byte is counted once, including drops, with max1200B per physical frame and complete round+sender fragment reassembly before a recipient accepts CBBA peer snapshot. Same Rady-sampled plus assumed E9G 144Mbps shared-medium causal transport family; no measured ns3/real WiFi. Nonmatching observer vs agent-local certification remains visible. Round160 guard is safety censor, failures remain in denominator. Report unique allocated tasks, capacity violations, total travel, longest route, discounted reward, original Bytes/SENDs and modeled allocation time; do NOT reuse 1:1 Hungarian optimum for T>R or old E9I/J/L N=T single-task numbers.

Existing true owners scenario.validate_scenario_shape/generate_e0_scenario and optimizer.validate_cost_matrix reject T>R; keep them unchanged. New owners: democracy_mrta.multitask_scenario, democracy_mrta.cbba_multitask, democracy_mrta.voting_multitask, democracy_mrta.multitask_evaluation, experiments.run_e9m_multitask, and only if necessary the true network.py timing owner. Named-function and owner/function/category/code diagnostic boundaries must be specified in the SAME bounded implementation commit as each concern; allowed categories data/time/state/dependency/planning/safety/runtime/contract. Required first acceptance local tests + 0loss three seeds full/feasible 25R100T, then p30 three seeds, then original user-run p30 100 seeds; scaling to 10R40T/50R200T/100R400T only after first-cell source audit. Original raw source SHA and Git SHA recorded per run, never silently change old baselines.

**STATUS 2026-10-13:** E9M source, named owners, local stand-in-interface unit tests and 3-seed 0/30% smoke exist on feature branch. Native Mac repository integration and verified 100-seed source are still pending. CBBA receiver-snapshot consensus and Voting reliable Score/Commit have different terminal contracts; 160 is CBBA safety censor only. Original paper does NOT specify E9M application frame wire format, receiver loss, or modeled radio. Original E9I/J/K/L remain untouched. No CI or formal 100 seeds executed.


### 48.1 Vote native unicast correction (2026-10-13, supersedes original candidate behavior)

The first E9M source candidate at commit `f347e260d9d76c347859dbc691de6d724946d9de` incorrectly charged wireless SENDs for local self-votes and scheduled every Vote as a broadcast to all peers even though only the elected candidate could use the ballot. Correct native E9M Voting transport is: (1) self-ballots are local and incur zero physical SENDs/Bytes/receiver attempts; (2) remote ballots are physically targeted UNICAST to the candidate and independently dropped at pLoss; (3) each remote Vote incurs ONE physical sender SEND and at most ONE receiver attempt; (4) Cost, Score, Commit, TASK and CBBA consensus remain broadcasts with exactly their earlier accounting and loss model. Shared-medium `WifiCausalTimingSampler` uses actual receiver ID for unicast so MAC ACK modeling and causal service differ from broadcast. This is an intentional transport/protocol correction, not a new comparator or change to Voting plurality, CBBA, scene, utility, 160 guard, or 30% receiver drop probability.

The first formal Terminal-only 100-seed results on commit `f347e26` are retained as **superseded preliminary evidence, not validated official communication/time baselines**. A new 100-seed run after native unit tests and 3-seed loss0/loss30 smoke is required. Named failure boundary: owner `democracy_mrta.multitask_wire`, function `E9MChannel.send`, category `contract`, code `E9M_INVALID_UNICAST_DESTINATION`, with expected remote target/actual provided recipient tuple. Original 2009 CBBA excludes this team-authored wire framing; methods still have non-equivalent CBBA observer vs Voting paid reliable-Commit stopping evidence.


E9M physical transport further enforces `multitask_wire.E9MChannel.send` contract/E9M_VOTE_REQUIRES_UNICAST: attempting a Vote broadcast fails *before* physical SEND/Bytes. This protects the original 30% candidate-only Vote assumption against later callers. The existing independent-loss broadcast unit test now legitimately uses the Cost phase rather than misrepresenting Vote semantics.


### 48.2 One source-gated five-method dashboard — different workload families, never pooled rank (2026-10-13)

The new owner `experiments.plot_e9m_unified_comparison` implements the requested compact **single six-panel SVG** comparing every official non-E9K method under its published study condition, rather than producing a new independent figure for each added method. A = original E9I Voting, E9J CBAA, E9L Price Auction on historical paired N=T capacity1 100-seed/size grids. B = corrected E9M capacity4 on 25R100T paired 100 seeds for Voting Multi-task and original CBBA. Each cohort plots modeled allocation/stop time, attempted sender application payload and data-supported completion. Old source lacks E9I/J full per-N success counts, so those are not fabricated in A's completion panel. Source time metrics have method-dependent stopping guarantees and possible E9L guard censor. Conditions, reward/Cost, robot count and capacity differ across A/B; **no pooled absolute speed ranking or cross-cohort significance test is permitted**. Distance/makespan/discounted-reward of E9M are preserved separately as original raw and source summary, not compared with historical N=T Hungarian-ratio metrics.

Source contract: owner `validate_legacy_source` requires Git blob `950ea0c2bd28dff280181fcc2f8b58d6db27633a` of original `docs/figures/e9l_price/formal/three_algorithm_plot_source_20point.csv`, complete N=5..100 step5. `validate_e9m_formal_source` verifies actual `manifest.json` SHA256 for original E9M per_seed and summary CSV, R25T100 capacity4, p=.30, paired seeds0..99 × 2 methods (200 distinct records), exact per-phase sender/receiver physical ledger equality, route coverage/capacity for successful cases and complete failure/guard retention. `verify_corrected_git_source` requires the E9M executed commit be descendant of audited Vote unicast fix `638081b9c040cde5a796a4de83fc3b025fe10b48`. Invalid or superseded original E9M source is rejected; output directories cannot overwrite. New errors carry first owner/function/category/code: `dependency/E9M_LEGACY_SOURCE_IDENTITY`, `contract/E9M_LEGACY_GRID_INVALID`, `contract/E9M_EVIDENCE_SHA_MISMATCH`, `contract/E9M_INCOMPLETE_PAIRED_100SEED`, `contract/E9M_UNCORRECTED_VOTE_SOURCE`, `contract/E9M_INVALID_ORIGINAL_RAW_ROW`, `state/E9M_UNIFIED_OUTPUT_EXISTS`. Named render function `render_unified_svg` is presentation-only. E9I/J/K/L runtime unchanged. E9K excluded as a team-authored paid-protocol modification, not an algorithm competitor.

Publication gate: corrected original E9M ZIP is NOT yet provided in this turn; code/tests and plotting template are preparation, not a new numerical experimental claim or publicly embedded image. The unified SVG only replaces one old README figure after corrected source arrives and is independently audited. No CI or background experiment.


### 48.3 Corrected E9M 100-seed user-run Terminal evidence (2026-10-13, raw ZIP pending)

The user independently executed all 100 Seeds for CBBA and Voting Multi-task with `25R/100T/C4/loss=.30` on source SHA `7e857fd232c9459d0777cf130bc36766467e1ff0`. Source Terminal paste SHA256 `e634d00290df25296c69a2c474417b9b7e31ecfc68d87d2049b81126342ef3fa` yielded exactly 200 unique seed/method result rows: 100/100 complete in each method. Reported means: Voting time 63.022630s sender 116827.40B, CBBA time 6.878180s sender 1006873.34B; paired modeled stop difference +56.144450s (Voting minus CBBA). Evidence is `docs/E9M_CORRECTED_TERMINAL_100SEED.md` and immutable terminal-derived 200row CSV plus summary JSON. **This is not original per-seed CSV/manifest verification.** Raw ZIP with original routes, costs, SEND/receiver breakdown, manifest SHA remains missing; no final paper-quality data/cost claim. CBBA simulator observer stop vs Voting paid reliable Commit still inequivalent and simulated 144 Mbps network is not measured physical Wi-Fi. Next: request raw ZIP for audit; run E9N capacity1 separately.


## 49. E9N common capacity1 N=T comparison with five named algorithm series (preregistered implementation stage, 2026-10-13)

**Study question:** What are the traffic, modeled allocation time and completion tradeoffs when no robot can hold more than one task? Same 20 N values (5..100 step5), N tasks, C=1, 100 scenario Seeds each N, 30% receiver loss, 100m square, Rady sampled ROS residual/assumed144 Mbps channel, method-native packet/control. **New 4000 executions**: CBBA and Voting Multi-task both constrained to capacity1, with unchanged owners `democracy_mrta.cbba_multitask.run_cbba`, `democracy_mrta.voting_multitask.run_voting_multitask`; capacity-one is a valid CBBA specialization but intentionally removes its bundle-size benefit. **Frozen historical 6000 aggregate inputs**: E9I Voting, E9J original CBAA and E9L Bertsekas-style distributed Price Auction, already executed 100seed per N; excluded Paid CBAA E9K. No original E9I/J/L reruns or fabricated raw rows. Original frozen source Git blob `950ea0c2bd28dff280181fcc2f8b58d6db27633a` is identity-gated by the existing presentation owner. Exact paired geometry is tested by reproducing `scenario.generate_e0_scenario(seed,N,N)` and comparing every robot/task coordinate with `multitask_scenario.generate_multitask_scene(seed,N,N,1)`; original network-loss draws/end-of-protocol guarantees still differ by method.

**Formal command:** `python3 -m experiments.run_e9n_one_task --formal --seeds 100 --loss 0.30 --max-rounds 160 --output-root NEW_ROOT`. Formal requires full fixed 20-point grid; both 3-seed 0% and 30% smoke must run first. Native per-seed appended records, summary, original raw/summary/chart hashes, git SHA, same-scene SHA, Rady source blob and historical original 20point source blob in manifest. Chart `five_method_common_cap1.svg` with exactly three metric panels (all-seed modeled time, original native attempted sender Bytes, available completion); five methods are distinct legend entries on the SAME N-axis, no mixing C4 E9M with C1 E9N. E9I/J per-N completion unavailable from frozen plot source and is intentionally blank. E9L guard-censored means are all-seed stop, not successful-mean time. Older CBAA/CBBA/auction stopping may use optimistic simulator aggregation unlike paid Voting Commit; this is not a matched physical termination benchmark. Original E9M 25R100T C4 correct user Terminal 100seed evidence remains separate.

One concern/new owners: `experiments.run_e9n_one_task` owns study setup/scene identity and executed E9N data evidence, `experiments.plot_e9n_unified` owns only shared-workload figure presentation; original algorithm and transport owners unchanged. First failure diagnostic boundaries: runner `parse_e9n_sizes data/E9N_INVALID_SIZES`; `validate_e9n_contract contract/E9N_FORMAL_CONFIG_FROZEN or safety/E9N_SMOKE_TOO_LARGE`; `verify_geometry_identity contract/E9N_SCENE_NOT_IDENTICAL`; `prepare_e9n_output state/E9N_OUTPUT_EXISTS`; `read_e9n_git_sha dependency/E9N_GIT_SHA_UNAVAILABLE or contract/E9N_GIT_SHA_INVALID`; `summarize_e9n_cases contract/E9N_INCOMPLETE_SEED_GRID`. Presentation `require_e9n_plot_grid contract/E9N_INVALID_PLOT_ROW/E9N_INCOMPLETE_PLOT_GRID`; `compose_five_method_rows contract/E9N_LEGACY_GRID_MISMATCH`; `render_five_method_svg contract/E9N_FIVE_WAY_ROWS_REQUIRED`. Reuse existing source gates `validate_legacy_source`/ `verify_corrected_git_source` instead of copying a second archive verifier. No CI or formal E9N executions initiated by source publication; plot publication only after original ZIP independent audit.


### 48.4 E9M corrected source ZIP independent receipt and verification (2026-10-13)

This section **supersedes the earlier "raw ZIP pending" status in §48.3**; that earlier entry remains immutable historical evidence. Exact user original ZIP `e9m_fixed_25r100t_loss30_100seed.zip`, 63,098 Bytes, SHA256 `de68d1cce8045a46b8e37f2d8f91e3988004db39d29544e1865d4759336e46b5` received and archived persistently at personal Library `/投票演算法/E9M/e9m_fixed_25r100t_loss30_100seed.zip`. The binary ZIP is NOT added to Git; Git records the source cryptographic identity and an independently recomputed `docs/E9M_CORRECTED_ORIGINAL_ZIP_AUDIT_100SEED.md` report plus JSON. Original `per_seed_e9m.csv` SHA `1268c3ca82dd3d40793da94c46900cee4648f1903cfcf847dc5113dc6d04f753`; original `summary_e9m.csv` SHA `1f2a3468b52d36eb09b2cfd58b3df699cadb2d376c10cf0b6466988b6cbe950f`; executed source Git `7e857fd232c9459d0777cf130bc36766467e1ff0`.

Independent acceptance PASS: original manifest SHA for raw and summary, 200/200 unique 100 paired seeds×2 methods, original 200 per-phase ledgers and physical byte/receipt accounting, 100 unique tasks and max4 route length in every successful case, recompute all 200 travel/longest-route/discounted-reward values from deterministic original coordinates and route ordering, regenerate full-precision CSV summary means, and reproduce 200 terminal log entries within printed rounding tolerance. No failures/round-guard censor. Original source means: Voting modeled 63.0226396215s/116827.4B, total travel1319.7644m, makespan134.5540s, discounted reward9735.4498; CBBA modeled 6.8781628625s/1006873.34B, total travel1209.4796m, makespan148.6351s, discounted reward9754.4692. Voting mean makespan is shorter, while CBBA mean total travel is shorter. **Model-specific stop conditions remain inequivalent; no real RF measured.** E9N independent C1 study remains separate and is NOT yet a completed five-algorithm live rerun.


### 49.1 E9N original formal ZIP verified and one five-method presentation (2026-10-13)

The user provided the exact 773,072-byte original E9N ZIP `e9n_cap1_100seed_20261013_102240.zip` SHA256 `f4807e70fe5c58ec9908c6adc39f2fbc50a31312222d757ca8205ee6ca3cc86d`; original executing source `5bb3f7ca18c3812413539550edb3a2b370fa11d3`. Original 4000 N/Seed/method cases, 40 source summary rows, 100 plotted rows and original figure's SHA-256 verified independently. Each E9N method completed all 100 Seeds at every N=5..100 (step5), C1, p30 without round160 censor. Recomputed all 2,000 scene digests, 4,000 unique route assignments and discounted/path/makespan values, all native packet phase ledgers with 20B unicast Vote/paid broadcasts and 4,000 Terminal printed lines, and all 40 method/size summary rows. Historical E9I/J/L chart data Git blob `950ea0c2bd28dff280181fcc2f8b58d6db27633a`: all 60 original time/Bytes figure values match source; E9I/J per-N completion intentionally absent. All source integrity diagnostics: **0 failures**. The raw original ZIP is in the user's persistent personal Library `/投票演算法/E9N/`, not rewritten or reexecuted.

Five-method original figure source `docs/figures/e9n/formal/original_five_method_common_cap1_source.csv` (SHA256 e7469f50fb47b96d79a467ab2f030597ed76a1d85d0c72a7a3284005856b789f) and original SVG (SHA256 2753bcb8c336bdd9ba91d1877c7a09bfdef7603b64f902a0f641464819f076f2) are kept byte-exact. Publication SVG at `docs/figures/e9n/formal/primary_five_method_time_bytes_success.svg` SHA256 d7508314bfaf2b0f474d857fe8184fca6aca15f5dc4bc4c0780dee8df40f634a changes vertical chart spacing/omitted-success-note only, no plotted numbers; the presentation owner `experiments.plot_e9n_unified._render_panel/render_five_method_svg` now uses this gap for future renders, without altering the historical executed commit `5bb3f7ca18c3812413539550edb3a2b370fa11d3`. N100 C1 two-new-method time Voting101.919s vs CBBA12.368s, original sender 305393.60B vs6488061.61B. CBBA lower total robot travel1260.847m vs1385.148m; Voting lower makespan85.745s vs99.450s. Full source and limitations at `docs/E9N_FORMAL_100SEED.md` and machine JSON.

No claim of equal finalization: CBBA uses simulator observer stop versus paid Voting Commit; legacy E9I/J/L were not newly rerun and old per-N E9I/J success counts absent in frozen plot input. Model is Rady delay + **hypothetical** 144Mbps, not real Wi-Fi. E9M original C4 benchmark remains strictly separate. No CI or formal rerun was done for the *presentation-only* source change.


## 50. P1 — five ORIGINAL algorithms, one matched, read-only first-feasible external measurement (preregistered candidate, 2026-10-13)

**Approved P1 study:** exactly `N=T in {25,50,100}`, one task per robot, p(receiver native lossy packet)=0.30, 100 paired Seeds0..99 per N, deterministic 100m square original geometry, original reliable Task broadcasts, native Rady ROS application-delay samples plus *assumed* 144Mbps Wi-Fi service. Full formal grid = **1,500 NEW executions**, five original algorithms `voting,cbaa,price_auction,voting_multitask,cbba`. Price Auction restored from original E9L source blob `2d2f1c0eaff94143ce256eebf0a0ee30603d8cba`, actual owner `democracy_mrta.price_auction.simulate_price_auction`; true legacy 28B BID/AWARD packet / epsilon10 / original network estimate restored to `network.estimate_e9l_price_auction_stage_ms`. E9K user-authored Paid CBAA is excluded. No source of historical E9I/J/L price/Cost averages is reused as a fresh result here.

**Two independently labeled event notions, never pooled as the same guarantee:** (1) after every **originally incurred** native communication phase a read-only external observer may record the **first** full unique robot/task capacity-one assignment snapshot and its true modeled phase-end timestamp. It cannot correct assignments, signal STOP, influence a bid, choose an executor, add a hidden message or access future network results; absence of the event is **missing**, not fabricated from final state; (2) each original **native protocol stop** with native local certificate, optimistic observer versus paid full Commit and guard censor recorded independently. Voting original guarded Cost once + received plurality adaptive Vote with pCost=pVote=0.30 uses native 300-epoch guard; original CBAA, Price Auction and CBBA use native 160-iteration guard, and Voting Multi-task retains original task epoch count; guards are safety bounds, not enforced common stopping. Time is a modeled protocol proxy, not Python wall clock, actual RF or equal paid distributed finalization.

**Pure common evaluation** from original unique observed/terminal pairs: exact sum of Euclidean robot/task distances, max robot travel / route makespan and external independent Hungarian minimal cost and gap/ratio, never inserted into any agent input. Native optimization objective still differs (discounted route score versus Euclidean Cost), so claim **common external cost comparison** only, not identical policies. Failure/guard cases always remain in each method's 100-Seed denominator. Same-success-five quality applies exclusively to Seeds where all five native endpoints fully succeed and has a separate paired subset size; unsuccessful auctions cannot be silently omitted from all-seed success/time. All original SEND/Bytes and native receive/drop ledgers are copied from true owners; if a native exception prevents returning complete physical traffic, the corresponding time/Bytes are marked unavailable and the formal source requires review, not imputed zeros.

**One observer concern, true original owners:** `experiments.p1_feasibility.FirstFeasibleObserver.observe` validates immutable post-phase snapshots (monotone and unique C1) while `assess_euclidean_assignment` computes pure quality. Optional `external_observer=None` hooks at named native owners `cbaa.simulate_cbaa` (after physical consensus), `price_auction.simulate_price_auction` (after BID / AWARD), `cbba_multitask.run_cbba` (after consensus inbox application), `voting_multitask.run_voting_multitask` (after paid Commit), and existing original immutable `RetirementRoundTrace` read-only in `run_e9h_adaptive_deadline.run_e9h_original_voting_case`. Existing `run_e9j_cbaa_vs_e9i.run_e9j_original_cbaa_case` and `run_e9m_multitask.run_e9m_case` only pass opt-in observers to actual native owners and otherwise preserve their prior default interface, bytes and behavior. The observer reads immutable tuple copies of actual native state and never owns an alternative assignment machine. One bounded experiment orchestration owner `experiments.run_p1_matched_five`, separate figure owner `experiments.p1_plot`.

**Native output contract:** `per_seed_p1.csv` append-and-fsync, `summary_p1.csv`, `same_success_quality_p1.csv`, one 4-panel `five_original_matched_comparison.svg`, and `manifest_p1.json` with SHA256 evidence files, executed Git SHA, original Price source blob, exact method/source settings and all failures. No CI. Formal CLI: `python3 -m experiments.run_p1_matched_five --formal --sizes 25,50,100 --seeds 100 --loss 0.30 --output-root NEW_ROOT`; only after Mac native tests and p0, p30 small-seed Smokes. Previous accepted original studies are never overwritten, and README is not numerically updated until the original P1 ZIP has been independently verified.

**Diagnostic first-failure boundaries:** `experiments.p1_feasibility.FirstFeasibleObserver.observe` `time/P1_NONCAUSAL_OBSERVER_TIMESTAMP`, `data/P1_INVALID_NATIVE_SNAPSHOT`; `assess_euclidean_assignment` `contract/P1_BELOW_HUNGARIAN_OPTIMUM`; `experiments.run_p1_matched_five.validate_config` `data/P1_INVALID_EXPERIMENT_AXES`, `contract/P1_FORMAL_CONFIG_NOT_FROZEN`, `contract/P1_FORMAL_METHOD_SET_CHANGED`; `verify_one_scene` `contract/P1_SCENE_GEOMETRY_NOT_MATCHED`; `run_original_auction` `contract/P1_AUCTION_PACKET_ACCOUNTING`; `run_matched_case` `contract/P1_NATIVE_SUCCESS_NOT_EXTERNAL_FEASIBLE`, `time/P1_FIRST_FEASIBLE_AFTER_NATIVE_STOP`; `validate_complete_grid` `contract/P1_INCOMPLETE_OR_DUPLICATE_GRID` / `P1_PAIRED_SCENE_SHA_MISMATCH`; `experiments.p1_plot.validate_plot_source` `contract/P1_FIGURE_SOURCE_GRID_INCOMPLETE`. Original errors preserve original owner/function/category/code with expected/actual; an invalid read-only observer must propagate rather than being mislabeled as native algorithm failure. Optional callbacks return no action and do not cause new network SEND or new local state machine. Detailed engineering and local commands: `docs/P1_MATCHED_FIVE_NATIVE.md`.


### 50.1 P1 original formal ZIP received, independently audited and main D figure source published (2026-10-13)

Executed **fixed original P1** source Git `24e002695748e976c7b2abdfce661431839c4a7b` on user's Mac Python3.13.5/macOS14.5-arm64, UTC 2026-10-13 04:07:02–04:29:05. Original ZIP `p1_matched_five_100seed_20261013_122905.zip` 362773 Bytes SHA256 `d2f30bf39d1f4aff336a5b7220a4f15ee887d0d79ccc8c8a536819f40691de58` stored unchanged Library `/投票演算法/P1/`, **not** checked in to Git. Original raw CSV SHA256 `86c2d0473329f479924f5c7233bf77f95fd4a6ca13d02184027d37e31501c4af` (1500 rows); 15-row summary `79a14809f515278095c735e28abd17f8a35a460ccafb0be5b8f64093bc7e2abe`; 15-row five-way same-success quality `3247136535a56af94e49213b0df4c100cc17344c1a31e3f88de156d12af0e239`; original SVG `0aaf63d6f5eeba77a5a02ab04f87f45df24c7cc78b9eb9120d048240fc193e97`; original Manifest `9daa190b5e28ee65dee41527d6225f41248a73ca2d40a08be6e99ea72d0afd02`; terminal log `bfa7ba057852f12edafce54c0c06f679e58fc4e510181e2393d3bb7a67e90f8a`.

**Independent source acceptance 0 errors:** complete safe CRC/hash original ZIP; exact three original N×100 paired Seeds×five methods; regenerate all 300 geometry scene SHA from deterministic Random and all 1500 Hungarian minima; independently recompute native unique task assignment/route cost/makespan and ratios where feasible; original method-native application sender and receipt/drop ledger math including 28B Auction BID/AWARD, CBAA (16+12N)B snapshot and per-phase E9M accounting; raw-to-summary 15 rows, exactly same successful Seed intersection 15 quality rows; all 1500 original Mac Terminal rows verified. Native complete1476/1500; first globally feasible1478/1500; 24 Price Auction original 160-round guard (N50 2, N100 22), two guard cases N50 Seed42 and N100 Seed88 formed externally feasible snapshots but lacked native terminal certificate. All 300 original CBAA/CBBA final task assignment pairs match exactly. At N100 CBAA first feasible7.898398s vs CBBA11.538602s (paired difference -3.640204s), native CBAA stop13.647431s vs CBBA12.367643s (opposite mean rank); CBBA6488061.61B vs CBAA2693040B. Original N100 all-five-native-complete intersection **78 Seeds**; original Auction ratio1.117319, CBAA=CBBA1.234752 on that exact subset. Missing/guard first feasible not imputed; Auction original successes only78/100.

Source-verified report `docs/P1_FORMAL_100SEED.md`, machine audit JSON/original manifest/15-row raw source summaries/unchanged original run SVG in `docs/figures/p1/formal`. README D primary four-panel publication SVG SHA256 `30fbd9847ff43da192b56d55217c988ac1cbf566d291ecead0dc1805aa1c3f63` corrects *only presentation*: original source SVG preserved byte-identical; moves original overlapping footnotes and replots only the **existing** same-success ratio panel from original exact 15 source values on a labeled [1.00,1.50] y-axis (pixel locations independently validated); no modeled time, Bytes or quality values modified, no algorithm executed. Other verified B and C SVG remain unchanged, E9N prior descriptive five-method chart and E9M C4 stay archived, not mixed with P1 C1.

Scientific limits remain: first-feasible is external **read-only simulator observation**, not local proof, native paid shared STOP or real RF; original methods' lossy packet classes and native stop conditions differ, Voting pays Score/Commit and CBAA/CBBA/Price have optimistic local/observer stopping. Rady ROS residual + **assumed** 144Mbps radio is hypothetical. P1 closes matched external measurement priority only; physical Wi-Fi timing requires separate validation **if claimed**, C4 scaling only if claimed. No changes to native owner, function, category or diagnostic contracts; source analysis and publication-only docs do not alter actual original experiment protocol.


## 51. P2 — four original single-task algorithms under dense receiver packet loss (2026-10-13)

**Preregistered only, not yet formally run.** P2 retains the original P1 native owners, P1 read-only first-feasible observer, unchanged application traffic, native guard and native stop semantics, and freezes **100R/100T/capacity1** with 100 paired Seeds0..99 per loss probability **p in {0.00,0.10,...,0.90}**. Exactly four **original** algorithms are included: `voting,cbaa,cbba,price_auction`; exclude the team-authored Voting Multi-task capacity-one variant and Paid CBAA. Total expected 10 × 100 × 4 = **4000** method-cases, 40 group summaries. Original P1 five-method source and ZIP remain immutable, and P1 30%-loss 100R matched results are a **post-run audit cross-check** only, not reused as substituted P2 results. This is not a fresh physical 802.11 packet measurement; Rady ROS delay plus hypothetical 144Mbps remains the model.

Outputs: new-folder per-seed append+fsync CSV, summary, immutable run-config SHA gate and manifest with source SHA and per-file SHA256, and one four-panel loss-vs-completion, native modeled stop, attempted sender Bytes and matched-four-native-success Euclidean/Hungarian quality SVG. Native failure/guard cases **remain in all 100 denominators**; missing native sender/time after genuine exceptions remain blanks and do not become zeros. Matched-four quality is conditional and displays cohort size. Voting paid reliable Score/Commit vs simulator/local stops remain **unequal terminal guarantees**. Native methods and original packet/loss owners unchanged; no new wrapper STOP, state machine, or method redefinition. Detailed canonical cell and Mac smoke/formal/resume commands in `docs/P2_PACKET_LOSS_FOUR_ORIGINAL.md`.

New experiment-only owners `experiments.run_p2_packet_loss` functions `validate_config,prepare_evidence,validate_complete_grid,summarize,run_p2` and presentation-only `experiments.p2_packet_loss_plot` functions `validate_plot_source,panel,render_p2_figure`. Diagnostic first failures include `data/P2_INVALID_LOSS_GRID,P2_INVALID_SEED_RANGE`, `contract/P2_FORMAL_GRID_NOT_FROZEN,P2_RESUME_CONFIG_MISMATCH,P2_RESUME_FIELDS_CHANGED,P2_RESUME_INVALID_PREFIX,P2_INCOMPLETE_OR_DUPLICATE_GRID,P2_SCENE_NOT_PAIRED,P2_INCOMPLETE_FOUR_METHOD_PLOT,P2_INVALID_PLOT_DENOMINATOR,P2_MISMATCHED_QUALITY_COHORT`, `state/P2_OUTPUT_EXISTS,P2_INVALID_RESUME_STATE`, `data/P2_NONFINITE_PLOT_VALUE`. Native original diagnostic owner/function/category/code is preserved. **Formal P2 results pending user's local execution; no CI.**


### 51.1 P2 loss-resolution correction: 5% → 10% (supersedes the original §51 grid)

The user changed P2's **sampling resolution only**, from original 19 levels (0%..90% in 5% steps; 7600 planned cases) to **10 levels (0%,10%,20%,30%,40%,50%,60%,70%,80%,90%; 4000 method-cases = 40 summary rows)**. §51 above now expresses the current approved setting; its initial 5% preregistration and user-started old run remain traceable in Git and the continuity log. The previously supplied 5%-grid formal terminal excerpt was **in progress, not a verified complete P2 formal ZIP**; its partial CSV/log must be preserved, never rewritten as complete or merged into the newly started source. The formal runner's `LOSSES` owner, its `validate_config` diagnostic and the source figure's PL labels now enforce the 10% protocol. The existing SHA/config resume contract *rejects* continuing the legacy 5% evidence with the new code. Start the new study in a new directory with an independently recorded commit SHA.

Unchanged: original 4 algorithms, paired 100 Seeds, 100R/100T/C1, native packet loss semantics, guards 160/300, read-only global first-feasible observation, charged application Bytes, Rady + **hypothetical** 144Mbps, native stop guarantee caveat, success denominators and conditional-four-Hungarian quality evaluation. Added test gate: every loss belongs to the 10-value grid, 0.05 is rejected, formal requires all 10 levels and 100 Seeds. No original allocation owner, network owner or termination logic modified; no CI/formal execution is claimed by this source-only change.


### 51.2 P2 actual formal ZIP independently verified and source-backed B figure published (2026-10-13)

**Status supersedes §51/51.1 "not formally run" implementation milestones:** the exact user-provided 1,276,228-byte original ZIP `p2_loss10_100seed.zip` SHA256 `1d08a167308b9368ee2a764737066223ac041a5bd6508621c7b6cd0320036bb9` was received and independently audited. It was run with original Git SHA `f514cfa3613e7b0bad5c739d136b09fea8c3f92c`, finished 2026-10-13 10:57:28 UTC; original per-seed CSV SHA256 `78c4871a9f0e391c11c92ace9c2b532695d2a2c4ca40d31166e31bf89901e5fc`, original summary SHA256 `de725d3d2737ceebafb99fa44e57fe583853077db242803e7f82d33e8d587aa7`, original SVG SHA256 `f7317099d8f71bcd3cc0ce597d7eea6f5e8bcfc2896a4dcf8aa3116040f73e43`. Source manifest records ZIP CRC PASS, 4000/4000 unique complete paired 10 PL×100 Seed×4 original methods, 40 exact group summary rows, independent 4000 deterministic geometry/Hungarian/assignment-cost/quality checks, all 4000 original physical application sender/receiver ledgers, 4000 original Terminal log entries and all 4 original file SHA256, **zero audit mismatches**. Independent originally audited P1 loss30 N100 control: **all 400/400 matching records field-for-field identical**. Original native source/radio/termination owners and previous P1 five-method raw remain byte-unchanged.

Original native completion per PL 0/10/.../90: **Voting [100,100,100,100,100,100,100,100,100,100]**, **CBAA [100,100,100,100,100,100,100,100,100,100]**, **CBBA [100,100,100,100,100,100,100,100,0,0]**, **Price Auction [98,99,90,78,51,31,14,9,0,0]**, all denominators 100 original paired Seeds. Total 3,270 original native completions, 730 guarded failures (CBBA200 + Auction530), 3,293 first-feasible external observations; **23 externally feasible without native completion are not successes**. Price Auction already fails two zero-loss Seeds, so guard or native convergence is not equivalent to packet-loss failure; CBBA 80% receiver-loss 8 feasible observer snapshots still do not imply native completion. Guard-based 80% collapse is not a theoretical limit.

At 90% PL: original attempted sender Bytes per Seed Voting254229B, CBAA14135600B, CBBA56343948B, Auction558031B. Voting sender payload reduction versus CBAA **98.2015%**; native modeled stop Voting27.4967s vs CBAA71.3832s (**different terminal guarantees**), yet CBAA first externally feasible12.770s versus Voting27.4967s. On the **same 100 native-success** Voting/CBAA 90%-loss Seeds, independent Euclidean/Hungarian cost ratios **2.4175 vs 1.2353**, showing strong quality loss at high packet loss; full-four-method success intersection becomes zero at 80/90, so no original *paired-four* cost is defined there. Preserve original success rates including all failure/guard cases; successful-only quality is explicitly conditional and cannot be ranked across algorithms on unequal success subsets.

**Presentation-only publication on research experiment branch:** `docs/P2_FORMAL_100SEED.md`, `docs/figures/p2/formal/source_manifest.json`, `verified_10point_plot_source.csv` and `primary_four_original_loss_robustness.svg`. The new figure is **derived and rounded**, not the byte-exact original SVG; sender MB uses a log scale, quality uses original success-only method cohorts with variable sizes (clearly labeled). README B now points to the new four-original-method P2 source and preserves older E9E synthetic 100R50T study only as historical control. Original ZIP/complete per-seed CSV and log are **NOT committed to GitHub** and never falsely represented as published raw binary. No experiment script, method-native owner/function/category/code, packet semantics, network timing, or end condition changed by this evidence-only publication; no CI/rerun. Independent Rady bootstrap + **hypothetical** 144Mbps and nonmatching native stop guarantees remain mandatory study limitations.


### 51.3 P2-B revised communication protocol after discovered serial Greedy epochs (2026-10-13)

**Current status: NEW source committed; local targeted integration/formal results PENDING.** This subsection explicitly **does not rewrite** the original P2 executed ZIP SHA256 `1d08a167308b9368ee2a764737066223ac041a5bd6508621c7b6cd0320036bb9` or its formerly audited results. The previous P2 100R/100T Voting source uses **one logical TASK announcement, one per-robot Cost row announcement, but serial Greedy one-task-at-a-time Vote/Score/Commit epochs** in `coordination.simulate_democracy_hungarian_retirement`. The prior timing is valid for that *serial voting protocol* and no longer estimates the newly requested *batched voting protocol*; do not subtract cost phases heuristically or quietly replace its underlying raw dataset.

**Change scope:** One experimental communication-flow correction with opt-in new method `voting_strategy="greedy_batch"` at the original **coordination** owner. TASK initial announcement once (all task positions; physical fragmentation under original 1,200B frame limit), per-robot full 100-task Cost calculations/one 100-row Cost exchange before voting (retained delivered views), then active robots prepare independent ascending-task Greedy capacity-one plans over physically visible Cost rows and broadcast one 16+8×entries byte batch Vote packet each. Candidates count only their received on-time votes/self-votes, reliably broadcast one Score vector each, and deterministic common task-order count ranking resolves eligible unique robots before reliable per-winner Commit. The **same original retirement membership state machine** retires committed robots/tasks and retries remaining tasks in another *batch* epoch, without reannouncing TASK or Cost. Partial Cost views cannot receive invisible data; no optimistic completion, no Cost re-send, no duplicate task/robot Commit. At PL0 full-cost batching must match offline sequential Greedy exactly; difference to global Hungarian can be nonzero. New native Score and Vote are actual sender-accounted application packets (16+8×pairs, max1,200B) and radio causal timing; cost/score/commit and original guardian deadlines still applied. Time budget for `vote_batch` at 100 active robots uses an actual **816-byte** vote packet rather than the previous 32-byte single-task Vote deadline. Distinguish this opt-in revised protocol from historical 'Original Voting' and user-authored Voting Multi-task; no 'Original' in public method display labels.

**Study rerun freeze:** N=T=100, capacity=1, 100 original paired Seeds, PL=0%,10%,...,90%; four methods `voting` (**new batched Greedy**) vs `cbaa/cbba/price_auction` (baseline original native method code and guards **unchanged**). The revised 4,000 original executions and 40 group summaries **must be collected afresh** at a new source SHA and root. Original P2 4000-case result and older E9E/E9I/P1 results are preserved as prior-protocol evidence and **not valid numerical evidence of the revised Voting time/traffic**. New manifest includes new `voting_strategy` frozen field; old P2 CSV/manifest cannot be resumed with new source. New Voting row's `original_traffic_ledger_json.batch` explicitly reports task frame count, Cost frame count=100, batch Vote frames, Score frames, Commit frames and additive TASK/Cost/Vote+Score/Commit stage durations. P2-B figure uses no 'Original' prefixes and co-located completion curves get visibly differentiated dashed tracks/concentric rings at **the same numerical coordinates**, with no data-point movement. Full canonical operational plan and local commands: `docs/P2_BATCH_GREEDY_PROTOCOL.md`.

**Named owners / diagnostics:** `optimizer.solve_visible_batched_greedy_assignment` state `BATCH_GREEDY_NO_VISIBLE_ROWS`, data `BATCH_GREEDY_INVALID_VISIBLE_ROW`; `coordination.encode_greedy_batch_packet` data `BATCH_GREEDY_INVALID_PACKET_KIND,BATCH_GREEDY_INVALID_PACKET_RECORD` and contract `BATCH_GREEDY_PACKET_EXCEEDS_LIMIT`; `coordination.decode_greedy_batch_packet` contract `BATCH_GREEDY_INVALID_RECEIVED_PACKET`, `collect_greedy_batch_votes,publish_greedy_batch_scores,resolve_capacity_one_batch_winners,emit_greedy_batch_commits,simulate_greedy_batch_vote_epoch` preserve existing first-failure original sender/time/safety diagnostic owner. Original `coordination.validate_epoch_voting_strategy,validate_vote_decision_rule,build_epoch_local_proposals,simulate_democracy_hungarian_lossy,simulate_democracy_hungarian_retirement` accept opt-in greedy_batch only; original `network.estimate_e9h_adaptive_deadline` computes opt-in vote_batch payload and `experiments.run_e9h_adaptive_deadline.build_e9h_deadline_schedule,run_e9h_original_voting_case` route the opt-in mode without altering default Greedy. Stage-time validation `experiments.run_e9h_adaptive_deadline.summarize_e9h_phase_timing` produces `time/P2_BATCH_NEGATIVE_PHASE_DURATION,P2_BATCH_STAGE_TIME_MISMATCH`; `experiments.run_p2_packet_loss.validate_config` `contract/P2_BATCH_FORMAL_VOTING_STRATEGY`. Original P1/E9 sequential default remains unchanged. No new wrapper, model-free score, extra retirement state machine, CI or formal execution is claimed by this source change.


### 51.4 P2-B executable first-failure evidence gates

Per-row source owner `experiments.run_p2_packet_loss.validate_batched_voting_evidence` checks the exact original task frame count, exactly 100 original Cost SEND frames, Commit count equal to recorded unique assigned tasks, and TASK+Cost-once+Vote-and-Score+Commit stage time equal to native stop. At PL0 the correct protocol must use exactly one batched epoch and return the identical full-information sequential Greedy pairs; its Hungarian cost ratio is not required to equal 1. The diagnostic codes are `contract/P2_BATCH_ONE_TIME_PHASE_CONTRACT,P2_BATCH_NO_LOSS_GREEDY_MISMATCH,P2_BATCH_NO_LOSS_REQUIRES_ONE_EPOCH,P2_BATCH_ZERO_LOSS_NATIVE_DIAGNOSTIC`, `time/P2_BATCH_TIME_LEDGER_MISMATCH`, `data/P2_BATCH_EVIDENCE_MISSING`. True native failures at other loss levels retain their original owner/function/category/code and do not have missing evidence imputed as zero. `coordination.validate_vote_decision_rule` additionally rejects unsupported batched strict-majority configuration with `planning/BATCH_GREEDY_REQUIRES_RECEIVED_PLURALITY`. These are validation constraints for the revised P2-B only; no new formal results are claimed.


### 51.5 P2-B efficient fair rerun — only new Voting, exact original baseline reuse (2026-10-13)

**Status: code and tests committed; no executed 1,000-case new Voting result has been verified.** The new P2-B batch protocol changes **only Voting**, not the true native CBAA, CBBA or Price Auction implementation or environment. The prior P2 original 4,000-record archive remains an independently audited source of all **3,000 original native baseline rows** at identical N=100, T=100, capacity=1, receiver PL=0/10/.../90% and Seeds0..99. Therefore **only 1,000 new batched Voting cases are scientifically necessary** to replace old serialized Voting data. Do not rerun, modify or regenerate original baseline-native observations.

**Execution owner:** `experiments.run_p2_packet_loss.keys` enumerates only `(loss,seed,"voting")`. The new runner's `prepare_evidence` is append-only for **1,000 fresh Voting rows**, `validate_complete_grid` checks its 1,000-case source; `validate_batched_voting_evidence` verifies original physical TASK/COST/Score/Commit stage gates and no-loss full-Greedy exactness. **Read-only evidence owner:** `experiments.p2_baseline_reuse.read_verified_original_baselines` requires explicit `--baseline-zip` for formal execution; before running Voting, it SHA-pins the original 1,276,228B archive `p2_loss10_100seed.zip` (ZIP SHA256 `1d08a167308b9368ee2a764737066223ac041a5bd6508621c7b6cd0320036bb9`, per-seed CSV SHA256 `78c4871a9f0e391c11c92ace9c2b532695d2a2c4ca40d31166e31bf89901e5fc`, original executed Git `f514cfa3613e7b0bad5c739d136b09fea8c3f92c`). It validates CRC, original manifest/config, complete original 4,000 case keys, exact source CSV field schema, selected 3,000 baseline rows, deterministic paired scene SHA and PL. A changed/re-zipped/missing source aborts before running. **No original serialized Voting rows** may be imported. New `merge_paired_baseline_evidence` requires exactly 1,000 fresh Voting and 3,000 SHA-attested unchanged baselines, rechecks equal paired scenario SHA, and attaches per-row `source_role` and `source_git_sha`.

**Fresh evidence outputs and plotting:** `per_seed_p2.csv` (1,000 newly executed Voting rows); `summary_voting_p2b.csv` (10 Voting rows); `per_seed_p2_combined.csv` (4,000 fresh+verified reused rows **with unambiguous row provenance**); `summary_p2.csv` (40 **recomputed** four-method groups, including exact native guard denominator and common-four-success conditional quality); newly generated `packet_loss_robustness.svg` (all four subplots), new SHA256 manifest with `new_voting_executions=1000`, `baseline_reused_rows=3000`, `combined_comparison_rows=4000`, original baseline ZIP/CSV/source provenance, and exact new original Git SHA. Graph A shows co-located completion values through distinct dashed and concentric markers without shifting numerical coordinates; all four method labels omit "Original". A chart is not accepted until **all** four panels are regenerated from full paired source and rechecked. External experiment sections A/C/D in README with different sizes/conditions **cannot** silently borrow P2-B Voting values: retain their original version until only the matching revised Voting rows (if needed) are rerun and combined with unchanged original baseline evidence.

**Validation/diagnostics:** `experiments.run_p2_packet_loss.validate_config` `dependency/P2_REUSE_BASELINE_ZIP_REQUIRED` for formal; `experiments.p2_baseline_reuse.read_verified_original_baselines` first failing diagnostic includes `dependency/P2_BASELINE_ZIP_NOT_FOUND`, `contract/P2_BASELINE_ZIP_SHA_MISMATCH,P2_BASELINE_ZIP_MEMBERS_MISSING,P2_BASELINE_SOURCE_IDENTITY_MISMATCH,P2_BASELINE_MANIFEST_INVALID,P2_BASELINE_CONFIG_MISMATCH,P2_BASELINE_CSV_SCHEMA_MISMATCH,P2_BASELINE_INCOMPLETE_GRID,P2_BASELINE_PAIRED_SCENE_MISMATCH,P2_BASELINE_SELECTED_GRID_INCOMPLETE`, `data/P2_BASELINE_ZIP_CRC,P2_BASELINE_ZIP_INVALID`. `merge_paired_baseline_evidence` `contract/P2_COMBINED_SOURCE_GRID_MISMATCH,P2_COMBINED_SEED_SCENE_MISMATCH`. Original per-seed native and time/contract diagnostics remain true-owner boundaries. Reuse changes no underlying baseline allocation/packet/timing/stop behavior. The historical original 4,000-case P2 archive, readme plot and prior P1 records remain immutable. No CI or local Mac formal integration claimed; see `docs/P2_BATCH_GREEDY_PROTOCOL.md` for exact local smoke/formal commands requiring `--baseline-zip`.


### 51.6 P2-B received full verified Voting-only ZIP — supersedes earlier pending statuses


**Confirmed original user-executed formal evidence:** `p2_batch_voting_only_100seed.zip` size 1,742,540B SHA256 `acd3dd389303a58cb27a16f46f29b6008f8b4678ff786d249e13caf60d61c08a`, source Git `7c082610bb3e3489ab09d07aaa339d1bbcd9acaa`, finished `2026-10-13T13:00:01.494096+00:00`, new Voting raw `per_seed_p2.csv` SHA256 `0a55d5a3d2016de8346be7b005ae26959202c206205e7164eaeb0a42bb2f0958`, new original combined `per_seed_p2_combined.csv` SHA256 `dca1f1b1db3ba1425dc64ae43641d838ea2881b9f6dcc9a94c6d4ad4afb3b24a`, original 40-group `summary_p2.csv` SHA256 `63ad7ee2c37f93f3f39ef761ab8138fdc1e5a6bc010c95b301d5655d90d6369b`, original 4-panel run SVG SHA256 `7a3a14e7bd84c6f1d876a1379e75168f51b2db50f0d68042318ae53f10721d88`. All original user ZIP members passed CRC and six recorded manifest SHA256 validations, with zero independent audit discrepancies.

**Immutable reused baselines:** historical completed P2 archive `p2_loss10_100seed.zip` SHA256 `1d08a167308b9368ee2a764737066223ac041a5bd6508621c7b6cd0320036bb9`, per-seed raw SHA256 `78c4871a9f0e391c11c92ace9c2b532695d2a2c4ca40d31166e31bf89901e5fc`, old executed Git `f514cfa3613e7b0bad5c739d136b09fea8c3f92c`. All 3,000 reused native CBAA/CBBA/Price Auction rows match their old raw fields *exactly*; the 1,000 old serialized Voting rows were excluded. New source identity per `(PL, Seed, method)` combines precisely 1,000 new Voting cases with precisely 3,000 unchanged original baseline cases, 10 PL0–90 step10 × 100 paired Seeds × 4 methods = 4,000 total, 40 recomputed summary groups. No baseline native method or termination owner re-executed or modified.

**Independent audit:** recompute 4,000 seeded 100m scene SHA, Hungarian optima, physical robot/task uniqueness and actual Euclidean cost/gap/makespan; independently check all 1,000 Voting TASK(3 framed sends)/Cost(100 row sends exactly once)/Vote/Score/Commit physical sender counts and stage-time additive equality and all 1,000 printed terminal cases; 100/100 no-loss Voting pairwise match full-information sequential Greedy and complete in one epoch. All pass. Voting natively completes all **1,000/1,000**; unchanged CBAA 100/100 at all 10 PL values, CBBA 0/100 at PL80/90, Price Auction native success across PL0–90 `[98,99,90,78,51,31,14,9,0,0]`. Overall 3,270 native complete, 730 baseline guard outcomes, all failures retained.

**Measured simulated trade-off:** Voting PL0 old-sequential native stop mean16.474s→new-batched2.027s (87.7% less); PL30 20.132→3.120s (84.5% less); PL90 27.497→11.742s (57.3% less). New Voting PL90 sender payload142,007.76B mean, old Voting254,229.44B mean, original CBAA14,135,600B mean (new vs CBAA **98.995% fewer attempted application Bytes**). Original Greedy pair identity at PL0 gives `Voting / full-information Greedy cost=1`, while `Voting / Hungarian optimum mean=1.351195` because Greedy is not globally optimal. PL90 new Voting native-success mean cost/Hungarian **3.840376**, old serialized Voting **2.4175**, unchanged CBAA **1.235261** on the same 100 Seeds. Thus faster/leaner but significantly poorer greedy assignment quality under extreme receiver loss. The 90%-loss modeled stages TASK0.076s + Cost0.609s + Vote/Score9.533s + Commit1.524s =11.742s mean; 20.78 mean batch epochs reuse original Cost and TASK. Native stop guarantee differs across methods (Voting paid reliable Score/Commit); Rady delay with assumed144Mbps is not real physical Wi-Fi evidence.

**Publication presentation boundary:** README B now presents exactly one four-panel graph `docs/figures/p2b/formal/p2b_packet_loss_four_panel.svg`, derived 40-group rounded `verified_40point_summary.csv`, `source_manifest.json` preserving original ZIP SHA. Figure A coincident completion curves are visible with concentric rings and dash pattern at *exact* data coordinates, panels B and C use visibly labeled logarithmic scales, panel D uses **each native-success method cohort**, so Voting/CBAA full n=100 costs at PL80/90 remain visible; CBBA/Auction nonexistent native-success quality there is **absent**, not zero. This D presentation denominator differs from the original run's *four-way intersection of native successes*, which is 0 at PL80/90; label source and report explicitly. The publication SVG is not the byte-exact user run SVG and does not replace it. Older P2 serial, E9E different 100R/50T and other original A/C/D experiments remain separate historical cohorts and unchanged.

**Owners/functions and diagnostics unchanged in this publication:** `optimizer.solve_visible_batched_greedy_assignment`, `coordination.simulate_greedy_batch_vote_epoch`, `protocol.apply_announced_retirement_commits`, `network.estimate_e9h_adaptive_deadline`, `experiments.run_p2_packet_loss.run_p2/summarize`, and `experiments.p2_baseline_reuse.read_verified_original_baselines/merge_paired_baseline_evidence`. No additional executable code, wire, loss, timer, state machine, planner, safety or diagnostics modified, no CI claimed; evidence-only docs and chart update. Structured diagnostic boundary `owner/function/category/code/expected/actual`, allowed `data,time,state,dependency,planning,safety,runtime,contract` preserved, zero audit failures. Original complete data ZIP remains with user, SHA pinned, not falsely committed to Git. Full report `docs/P2B_FORMAL_100SEED.md` and `docs/P2_BATCH_GREEDY_PROTOCOL.md`.


### 51.7 P2-C Global Greedy assignment-order correction (2026-10-13, pre-registered only)

**Intent and current evidence status:** subsequent P2-B 100-seed PL0 cost diagnosis showed that `optimizer.solve_visible_batched_greedy_assignment` used **Task-ID-first** greedy and the batched Vote winner owner `coordination.resolve_capacity_one_batch_winners` also used Task-ID-first conflict resolution. This caused a systematic last-task quality penalty even at 0% loss. The user explicitly approved a **new Global minimum-cost-pair Greedy variant** for Voting and requested a new execution, while preserving native CBAA/CBBA/Price Auction and the previously verified Task-ID Voting ZIPs. On the new `experiment/p2-global-greedy-voting` source branch the *implementation is changed*, and the local native radio experiment is **pending**. Old P2-B formal ZIP and README published numbers are valid historical Task-ID Greedy evidence only.

**One bounded real-owner planning change:** `democracy_mrta.optimizer.solve_visible_batched_greedy_assignment` now greedily selects the globally lowest tuple `(cost,task_id,robot_id)` over **all unassigned tasks and only truly locally received candidate robot Cost rows**; after each pick both the task and robot become ineligible, enforcing capacity one. Missing rows are never magically recovered, and greedy is not Hungarian. The next received-public-Score coordination decision `democracy_mrta.coordination.resolve_capacity_one_batch_winners` sorts all candidate/task edges by **descending physically received count**, then `(task_id,robot_id)` only as an exact-score tie break; the original task-first Score resolver could otherwise override the globally planned ballots when views differed. A deterministic one-to-one selection uses the already existing original `protocol.validate_one_to_one_commits` safety boundary. This **does not** turn a public Score into all-to-all Cost or use an invisible centralized optimizer. Each task and robot appears at most once; unfilled tasks only retry using the original retirement state.

**Everything else preserved:** TASK logical announcement once (3 physically charged frames at 100 tasks), each of 100 robots sends its full own 100-task Cost row exactly once per execution, original physically lossy batch Vote, reliable Score and executor Commit, existing packet byte widths and network timing/guard/retry state machine, original Voting 300-epoch guard, 100R/100T/C1, 100 Seeds, PL0..90 step10, original baseline native guards160 and unmodified all 3,000 previously audited baseline rows. There is no new message and no change to other algorithms' optimizer definitions, simulator-only finalization or their native source. Other archived A/C/D manuscript figures remain historical versions until comparable new Voting-only runs exist at their original distinct configurations.

**Independent *offline* reference, not yet native execution:** with deterministic full 100R/100T Seed0..99 Euclidean matrices, an independent exhaustive Global Greedy pair ranking (10,000 edges/seed, deterministic cost/task/robot tie order) yields **mean Global Greedy/Hungarian 1.2352608182858986**, mean distance **1260.8468915753372m**; the old Task-ID Voting results gave mean ratio **1.3511949850163498**, mean distance **1375.4837254424779m**. All **100/100** independently computed global-pair assignments match the existing fully successful CBAA and CBBA PL0 allocations pair-for-pair. **This is a full-information offline prediction only** and must not be labeled new Voting packet/Score/Commit success, time or overhead.

**Acceptance gate in `experiments.run_p2_packet_loss.validate_batched_voting_evidence`:** native PL0 observations must match `solve_visible_batched_greedy_assignment(scene.cost_matrix, all_robots_visible)` exactly as unordered pairs, complete all tasks in **one** batched Vote epoch, preserve one TASK/Cost exchange, and have additively consistent TASK+Cost+Vote/Score+Commit time. Diagnostic `contract/P2_GLOBAL_GREEDY_NO_LOSS_MISMATCH` includes full expected/actual assignment; optimizer `planning/GLOBAL_GREEDY_CARDINALITY_MISMATCH` identifies cardinality errors at first owner. `tests/test_p2_global_greedy.py` independently computes all 100 zero-loss global pairs, checking deterministic 1.235260818 expected ratio and uniqueness; `tests/test_p2_batched_greedy.py` contains an adversarial Task-ID versus Global pair fixture and ensures Score selection examines all reported task/robot edges rather than hard-wiring task order; `tests/test_p2_packet_loss.py` asserts the 0%-loss new native evidence rejects the old Task-ID result. All original first-failure contracts `owner/function/category/code/expected/actual/details` and category enum remain unchanged.

**Pre-registered rerun:** first **only 0% loss × 100 Seeds = 100 new Voting-native trials** (requires local Mac, no new CBAA/CBBA/Auction). Accept only if **100/100 match Global Greedy**, complete one native batch, and all sender/event/Cost/Hungarian audits hold. Then rerun **only Voting** on PL=0,10,...,90% at 100 seeds (1,000 **new Voting-only** method-cases) using a *new* output root and source Git SHA. The SHA-pinned historical original P2 3,000 CBAA/CBBA/Auction rows are imported as read-only comparison evidence by `experiments.p2_baseline_reuse` with ZIP SHA256 `1d08a167308b9368ee2a764737066223ac041a5bd6508621c7b6cd0320036bb9`; all 4,000 source-attributed rows, 40 summaries and four graph panels must be **recomputed after** new results, and only then should README B be updated. Original `greedy_task` P1 code and all old P2B Git/run manifests remain immutable. The full command and failure gates live in `docs/P2C_GLOBAL_GREEDY_PROTOCOL.md`.

**Scientific limits:** high PL can still alter candidate views and voted scores, cause additional batch retry cost and reduce matching quality; the offline Global Greedy equals neither Hungarian nor a universal optimal solver. Strong reliable TASK/Score/Commit and Rady app delay+*hypothetical 144Mbps* remain modeling assumptions, not measured 100-robot wireless performance. Native stop guarantees differ across methods; never interpret original baseline native STOP as equivalent to reliable final Commit. No native Mac rerun, CI or new high-loss publication is claimed at source-commit time.


### 51.8 P2-C actual native Global Greedy source accepted (2026-10-13)


**Accepted P2-C formal source:** Original Mac ZIP `p2c_global_greedy_100seed.zip`, 1,705,448 bytes, SHA256 `f50068e4569771538f3083b8434bc91bce1f42bdec44e8feb74407be90682055`, actual executed Git `8038370205d586c697295b42eb255812be7aa88e`, completed `2026-10-13T14:52:04.135167+00:00`. Manifest directly pins 1,000 new Global Greedy Voting native executions and 3,000 source-verified unchanged CBAA/CBBA/Price Auction native rows, 4,000 combined, 40 summary groups, robots=100, tasks=100, capacity1, paired Seeds0..99, PL 0/10/…/90. Original raw Voting SHA256 `a5f6c59837b80596066752c6546a37a387b4ccf177f8d4f1c03c527309a4a5fe`, original combined SHA256 `859ad11170a387c6d950b7bde82857e6370b4d1cfa1803b62984090eff698448`, original summary SHA256 `1f6077ee3ec0deed1ec90b7d90f0b8547330a66b97f12dbc76389bd4dfb722ac` and source runtime SVG SHA256 `615e024a83e13a4e1d354550b47353dfc1704642575d68e1a728817c21a89a1c`. Original immutable baseline ZIP SHA256 `1d08a167308b9368ee2a764737066223ac041a5bd6508621c7b6cd0320036bb9`, native baseline executed Git `f514cfa3613e7b0bad5c739d136b09fea8c3f92c`; original P2-B prior executed Git `7c082610bb3e3489ab09d07aaa339d1bbcd9acaa`, prior ZIP SHA256 `acd3dd389303a58cb27a16f46f29b6008f8b4678ff786d249e13caf60d61c08a`. Never recompute original CBAA/CBBA/Auction or rewrite any historical raw output.

**Independent original-file audit passed:** 71,156 check invocations and **zero mismatches**. ZIP CRC + all manifest SHA256, 1,000 native new method/log/source keys, 3,000 byte-equivalent original baseline row values, 4,000 complete scenario geometry and independent Hungarian oracles, 3,293 fully feasible final assignment costs and 23 feasible yet native-guard-censored original baseline cases kept non-native-success, 1,000 physical TASK/Cost/Vote/Score/Commit sender counts and stage-time identities, 40 four-way stats and 10 Voting group summaries all agree. **100/100 PL0 new Voting native Robot–Task pair assignments exactly match independently computed Global minimum-cost pair Greedy** (not Hungarian) and each finishes in one Vote batch; original CBAA/CBBA exactly match those pairs in 100/100 original native PL0 cases each. At PL0, mean Voting cost/Hungarian =1.2352608182858986, not1.0. All 1,000 Global Greedy Voting scenarios natively complete 100/100 at each of ten PL points.

**Measured result under the actual frozen simulator:** at PL90 new Voting mean modeled native stop **4.493584s**, Cost/Hungarian **1.296574**, original sender attempts **105.67064kB**, compared with accepted older P2-B Task-ID Voting **11.742267s**, **3.840376** and **142.00776kB** on same Seeds. Cost ratio improved **66.24%** and modeled Stop improved **61.73%**, but original CBAA still obtains lower Cost/Hungarian **1.235261** at PL90; CBAA modeled stop is 71.383177s and sender bytes 14,135.6kB, but native terminal certificates are not equivalent. PL90 observed new Global Greedy Vote batch epoch count **7.34** mean vs previous Task-ID Greedy **20.78**. Initial TASK logically broadcast once/3 real frames, 100 Cost sender frames exactly once per run, not per epoch; original Vote is lossy and real candidate Score/Commit reliably billed. Rady delay profile plus hypothetical144Mbps shared medium remains simulation, not physical RF. Native lower-loss quality may be marginally better than deterministic full-information Global Greedy on average because a heuristic local matching is not a universal lower bound.

**Protocol owner and preserved behavior:** `optimizer.solve_visible_batched_greedy_assignment` ranks `(Cost,task_id,robot_id)` for the physically visible rows, emits capacity-one entire-task local proposals. `coordination.resolve_capacity_one_batch_winners` ranks received and publicly reported `(score,task_id,robot_id)` globally, skips used robots/tasks, and still invokes `protocol.validate_one_to_one_commits`. The actual code change and first diagnostics are fully pre-registered in P2-C §51.7 and [protocol](P2C_GLOBAL_GREEDY_PROTOCOL.md); P2-C formal acceptance here is **docs-only**, not a new change of these runtime owner functions. No hidden Hungarian execution, Cost resend, message-payload change, second state machine or new external baseline solver. Preserved original categories `data,time,state,dependency,planning,safety,runtime,contract` and existing code labels `planning/GLOBAL_GREEDY_CARDINALITY_MISMATCH`, `contract/P2_GLOBAL_GREEDY_NO_LOSS_MISMATCH`.

**Publication visualization:** One verified publication four-panel SVG `docs/figures/p2c/formal/p2c_packet_loss_four_panel.svg` derives from 40 source groups, plotted A completion with non-shifted concentric rings, B native modeled time log axis, C physical attempted sender MB log axis, D **per-method native-success-conditioned** Hungarian cost. This D is deliberately **different** from original native source SVG's four-way common-success cohort, empty at PL80/90; at those loss values successful-only Voting and CBAA n=100 remain plotted, while CBBA and Price Auction costs are missing. The original user ZIP SVG remains SHA-pinned, unmodified. [Exact audit source](P2C_FORMAL_100SEED.md), [plot source](figures/p2c/formal/verified_40point_summary.csv), [original ZIP and derived Git blob provenance](figures/p2c/formal/source_manifest.json).

**Remaining risks:** zero performance claim beyond the frozen synthetic 100R100T/C1 PL model, no physical network RF test or equal terminal certificate standard, partial Score and Cost receipt under lossy sources may differ, original Auction price/CBBA native guard outcomes cannot be implicitly called infeasible physical assignment, 0% auction only 98/100 native complete. The combined planner+Score change was evaluated as a bundle, so per-function causal contribution is not identified without an ablation. Other manuscript A/C/D charts using historical serialized Voting or different sizes remain historical and require *only matched new Voting* runs if a P2-C-wide paper figure suite is requested.


## 54. P2D — One-shot Centralized Method and Full-Info Greedy comparison (2026-10-14)

**Implementation source committed; Mac native unit and formal results pending.** This is a NEW experiment and does **not** relabel/overwrite historical P2/P2-B/P2-C experiments, Price Auction data or previously published figures. Binding [P2D reviewed design](superpowers/specs/2026-10-14-p2d-centralized-one-shot-comparator-design.md); [implementation plan](superpowers/plans/2026-10-14-p2d-centralized-one-shot-implementation.md).

### 54.1 Frozen cohort and comparator
- `100R / 100T / capacity=1`, 100m × 100m deterministic original scene per seed 0..99; `p={0%,10%,...,90%}` independent receiver loss for Cost/Vote per original native owner.
- Figure labels EXACTLY: **Proposed Method, CBAA, CBBA, Centralized Method**. Price Auction **excluded** from P2D only, old P2 results immutable.
- Only **Centralized Method** is newly executed (10 losses × 100 seeds = 1,000 cases). **Proposed Method (P2-C Global Greedy Voting), CBAA and CBBA** are 3,000 SHA-attested original method cases reused, not rerun. Exact archive checks: original P2-C ZIP `f50068e4569771538f3083b8434bc91bce1f42bdec44e8feb74407be90682055`, native new Voting CSV `a5f6c59837b80596066752c6546a37a387b4ccf177f8d4f1c03c527309a4a5fe`, executed Git `8038370205d586c697295b42eb255812be7aa88e`; original P2 ZIP `1d08a167308b9368ee2a764737066223ac041a5bd6508621c7b6cd0320036bb9`, 4000-row original SHA `78c4871a9f0e391c11c92ace9c2b532695d2a2c4ca40d31166e31bf89901e5fc`, executed Git `f514cfa3613e7b0bad5c739d136b09fea8c3f92c`.
- Both complete, original, user-run ZIPs must verify before new output, with source Git SHA, CSV SHA, manifest and same-seed scene SHA. No generated figure/rounded publication summary may substitute for original raw.

### 54.2 One-shot Centralized native method
- Robot `0` acts as one single coordinator and knows **only its own row** without network. Original one-time TASK frames are reliable by existing P2-C control assumption, paid on radio.
- Each other robot `1..99` emits **exactly one 816 B unicast Cost** to coordinator robot 0. No retransmission, repeated Cost, backup exchange, timeout retry, requested replay, extra assignment epoch or recovery. An unseen or late Cost remains unavailable.
- Native owner `democracy_mrta.centralized_method.collect_one_shot_cost_rows` physically emits with original `coordination._unicast_event` and network `WifiCausalTimingSampler.sample_packet_ms` **before** original `coordination._lossy_unicast_delivery` receiver decision. Failed sender attempts incur application sender bytes, PHY/MAC service, airtime, queue, and budget. The guarded original Cost budget uses `network.estimate_e9h_guarded_initial_cost_ms`; final cost phase end includes physical in-flight send arrivals even when no receiver gets those frames.
- Planner `democracy_mrta.centralized_method.plan_from_received_cost_rows` passes **only** visible rows, in physical robot-ID order, to existing `optimizer.solve_visible_batched_greedy_assignment`; remaps local row indices to true robots. Ties `(cost,task_id,robot_id)`. No Hungarian, Price Auction, invisible complete matrix, or fallback.
- **P2D partial-input regression (2026-10-14):** 100% Cost loss can leave a rectangular received matrix of **1 visible robot × 100 pending tasks**. The true owner `optimizer.validate_cost_matrix(cost_matrix, *, allow_tasks_exceed_robots=False)` continues to reject `tasks > robots` by default with the exact original `contract/TASKS_EXCEED_ROBOTS` diagnostic, preserving the contract for Hungarian and all other existing callers. Only `optimizer.solve_visible_batched_greedy_assignment` opts in with `allow_tasks_exceed_robots=True`, while keeping finite/nonempty/rectangular validation. This produces `min(received robot rows, pending tasks)` partial Greedy assignments, which Centralized maps to **received physical robot IDs**. Missing Cost rows are never synthesized; no additional retry, wrapper, optimizer or recovery mechanism is introduced.
- After Cost, exactly one paid assignment broadcast plus one paid reliable Commit per assigned executor, no repetition; TASK, assignment and Commit are assumed delivered once by the model. This is NOT a field claim of end-to-end all-lossy reliability. If fewer than 100 Cost rows arrive on time, Centralized does **not** invent the others, so native full completion fails; `task_coverage` reports the actual one-shot partial assignment.
- `native_stop_ms` includes task, paid attempted Cost including drops, Cost wait cutoff and actual assignment/Commit events. In incomplete scenarios it is **native stop**, not successful allocation time. Physical travel and execution excluded. CBAA/CBBA native endpoints remain distinct; source timing is Rady ROS latency bootstrap plus *hypothetical* 144 Mbps shared medium (not measured field Wi-Fi 100-robot airtime, ns-3, or ARQ).

### 54.3 New owners and diagnostics
- Native `democracy_mrta.centralized_method`: `validate_centralized_configuration` (data/P2D_INVALID_CENTRALIZED_GRID), `collect_one_shot_cost_rows` (contract/P2D_ONE_SHOT_SEND_COUNT_MISMATCH), `plan_from_received_cost_rows` (state/P2D_NO_CENTRALIZED_COST_ROWS; contract/P2D_HIDDEN_COST_ROW_USED), `publish_centralized_assignment` (data/P2D_ASSIGNMENT_FRAME_TOO_LARGE), `emit_centralized_commits` (original protocol safety), `simulate_one_shot_centralized` (contract/P2D_SENDER_LEDGER_MISMATCH). No second Voting/Cost state machine.
- True original archive owner `experiments.p2_baseline_reuse.read_verified_p2c_voting` and `merge_p2d_paired_evidence`: dependency/ P2D_P2C_ARCHIVE_NOT_FOUND; contract/ P2D_P2C_ZIP_SHA_MISMATCH, P2D_P2C_SOURCE_MISMATCH, P2D_P2C_CONFIG_MISMATCH, P2D_P2C_INCOMPLETE_GRID, P2D_P2C_PAIRED_SCENE_MISMATCH, P2D_SOURCE_GRID_MISMATCH, P2D_SCENE_MISMATCH. Existing original P2 archive owner remains unchanged.
- New experiment `experiments.run_p2d_centralized`: `validate_config` data/P2D_INVALID_LOSS_GRID,P2D_INVALID_SEEDS, contract/P2D_FORMAL_GRID_CHANGED, dependency/P2D_TWO_ARCHIVES_REQUIRED; `prepare_evidence` state/P2D_OUTPUT_EXISTS,P2D_RESUME_INVALID and contract/P2D_RESUME_IDENTITY_CHANGED,P2D_RESUME_COLUMNS_CHANGED,P2D_RESUME_PREFIX_CHANGED; `run_one_centralized_case` contract/P2D_ZERO_LOSS_GREEDY_MISMATCH; `validate_complete_grid` contract/P2D_INCOMPLETE_CELL_GRID,P2D_UNPAIRED_SEED_SCENE. `augment_full_info_quality,summarize,write_evidence,run_p2d,main` have separated named responsibilities.
- New figure `experiments.p2d_plot.validate_p2d_plot_source` contract/P2D_INCOMPLETE_FOUR_METHOD_PLOT, P2D_INVALID_SUCCESS_DENOMINATOR, P2D_NO_SUCCESS_HAS_FAKE_QUALITY; `_panel` data/P2D_NONFINITE_PLOT_VALUE; `render_p2d_figure` reporting only. Errors retain first owner/function/category/code/expected/actual, allowed categories `data,time,state,dependency,planning,safety,runtime,contract`.

### 54.4 Statistics and Full-Info Baseline
- New raw append-only `per_seed_p2d.csv` + frozen `run_config_p2d.json` (same-SHA resume), resulting `per_seed_p2d_combined.csv` (method source identities), `summary_p2d.csv` (40 groups), SVG, `manifest_p2d.json` SHA256. Missing time/bytes are blank and not imputed.
- A: native completion / all 100 seeds, optional thin **black dashed Full-Info Baseline at 100%**.
- B: all 100 native modeled *stop* values incl incomplete and guard outcomes; log y, no fictitious ideal time.
- C: attempted physical sender application payload bytes incl dropped Cost; log y, no fictitious ideal 0 bytes.
- D: `actual cost / full-information minimum-pair Greedy cost` on each method's **own successful cohort**, with quality sample size; black dashed **Full-Info Baseline at 1.0**, no line at empty cohort. The greedy reference is not an actual fifth transmitted method nor a proven global optimum; a valid ratio may be below 1.0.
- Centralized `mean_task_coverage` is additionally available per loss as partial-progress diagnostic. Native different stop guarantees and model assumptions must remain clearly shown.

### 54.5 Verification and next step
- Tests: `python3 -m unittest discover -s tests -p 'test_p2d*.py' -v`; full suite `python3 -m unittest discover -s tests -v`. **Not locally executed by assistant in current restricted container**; original user Mac must provide PASS/failure log. Do NOT claim formal results or replace existing README P2-C figures before the new ZIP is audited.
- See plan Task 5 / reproduction guide `docs/P2D_ONE_SHOT_CENTRALIZED.md` for 0%-loss 100-Seed gate and new-root 1,000-case P2D execution.


## 55. P2E — Proposed redecision A/B, one vs 300 epochs (2026-10-15)

**Status: code committed, awaiting Mac source/QA run.** This is an independently archived Proposed-only *ablation*; not a fifth method on the P2D four-way main plot and not a retroactive change to P2-C, CBAA, CBBA or Centralized Method. Original older per-seed records remain immutable.

### 55.1 Research question and frozen arms
- Is the Proposed Method's packet-loss resilience due partly to permission to **repeat a decision epoch** after an incomplete first global-greedy batch, rather than to the single-batch voting rule alone?
- Arms and display labels: `single_round` → **Proposed (Single-Round)**, exact native `max_rounds=1`; `multi_round` → **Proposed (Multi-Round)**, exact native `max_rounds=300`. Same owner function `coordination.simulate_democracy_hungarian_retirement`, original E9H deadline schedule, `greedy_batch` planner, plurality Score, and one-per-run full Cost snapshot. Distinguish multi-round repeated **new Vote decisions** from packet retransmission of a previous Cost/Vote; neither arm retransmits the same source packet.
- Scenarios: N=T=100, one robot per task, original seed 0..99, 100m × 100m geometry. Independent per-receiver Bernoulli Cost/Vote loss `p=0%,10%,...,90%`. Both arms use the same robot/seed/PL pair and their native initial Cost/first Vote events must be **bitwise-semantically paired by SHA256**.
- Exactly 100 Seeds × 10 losses × 2 configurations = **2,000 *new native executions***; no copying or renaming prior Proposed source ZIP and no pretending CBAA/CBBA/Centralized were rerun in this study. Existing P2D four-method plot is unchanged and may be refreshed in a separate complete fresh-run study.

### 55.2 Actual SEND Byte boundary
- Real original Cost/Vote/Score/Commit owners remain unchanged. Real physical SENDs enter `network.WifiCausalTimingSampler.sample_packet_ms` **before** Cost/Vote delivery loss decisions. Every physically emitted SEND contributes its full application `payload_bytes`, whether 0, 1, or many peers receive the frame. A broadcast frame is charged **once per sender SEND**, not once per receiver; dropped/unreceived packets remain paid. Never multiply Bytes by loss probability or count only delivered packets.
- `network.WifiCausalTimingSampler.summarize_network` additionally exposes `sender_by_phase` with exact `{sender_sends,sender_bytes}` from the same immutable packet trace, alongside the unchanged aggregate `packet_count` and `application_sender_bytes`. Its counters are **application payload Bytes**, not additional Wi-Fi MAC/PHY equivalent Bytes.
- Native reporting owner `experiments.run_e9h_adaptive_deadline.summarize_e9h_sender_phase_breakdown` maps genuine phases `task_announcement,cost,vote,vote_score_announcement,commit` to `task,cost,vote,score,commit`, preserving the real sum of physical SEND Bytes and counts. Unknown event phases fail, and phase sums must equal the actual existing aggregate packet/byte ledger.
- `experiments.run_e9h_adaptive_deadline.fingerprint_e9h_first_epoch` hashes original first-epoch emitted TASK/Cost/Vote/Score/Commit events, receiver delivery observations, and first-epoch Commit pairs. Later epochs deliberately excluded. The new runner requires identical SHA for each seed/PL pair across arms; mismatch is **contract/P2E_FIRST_EPOCH_NOT_PAIRED**, and no study summary/figure is published.
- `experiments.run_p1_matched_five.run_original_voting` forwards the new diagnostic `sender_by_phase,first_epoch_sha256,rounds_executed` only in the existing original `batch` evidence ledger. This adds *read-only reporting* to subsequent runs, does not change prior P1/P2-C frozen original user archives, native Vote/Score/Commit, Cost timing, or emitted SEND count.
- Original TASK announcement, final Score and executor Commit remain modeled as reliable control; this **does not** claim all-lossy real RF without a reliability layer. Native timings remain Rady-app-delay + hypothetical shared 144Mbps shared-medium service, not actual RF measurements.

### 55.3 Experiment functions and output
- Dedicated `experiments.run_p2e_redecision_ablation` owns `validate_ablation_config` (data and frozen grid), `case_keys` (deterministic pair order), `prepare_ablation_evidence` (fresh append-only output and same-commit resume), `extract_validated_native_batch` (original first-error source + Cost/epoch native contract), `count_observed_commits` (independent one-to-one safety), `audit_native_sender_phases` (sum of *attempted* SEND frames/Bytes), `measure_ablation_offline_quality` (read-only complete-information Greedy denominator), `run_one_ablation_case` (same native run, only 1/300 epoch bound), `validate_ablation_grid`, `validate_paired_initial_epochs`, `summarize_ablation`, `write_ablation_results`, `run_ablation`, `parse_args/main`.
- Strict per-case raw columns include `loss_percent,seed,mode,max_rounds,native_success,native_stop_ms,native_guard_censored,native_sender_sends,native_sender_bytes,task_coverage,committed_task_count,rounds_executed,first_epoch_sha256`, original native JSON ledger and assignment, full-info Greedy cost and completed-only quality, plus `task/cost/vote/score/commit_sender_sends` and `task/cost/vote/score/commit_sender_bytes`. Every first-round Cost sender must physically SEND exactly 100 once regardless of loss; reliable original TASK framing remains 3 packets for 100 Tasks.
- `summary_p2e.csv` has exactly 20 method/loss groups. Each reports native full completion %, mean Task Coverage (all seeds), modeled **native stop** seconds (all seeds, including incomplete), attempted application sender kB (all seeds, including losses), mean decision epochs, completed-only assignment-cost ratio to *offline full-info Greedy* and explicit quality cohort n, plus phase-specific mean SEND counts and Bytes. Unavailable/incomplete metrics are **blank**, never imputed as zero.
- `experiments.p2e_redecision_plot.validate_p2e_figure_source/_ablation_panel/render_p2e_figure` owns an independent SVG with six panels: completion, coverage, all-seed sender Bytes, all-seed native stop, native round count, success-only cost ratio. Black dashed offline full-info only on completion (100%) and cost ratio (1.0); no zero-time/zero-byte reference. Missing success quality points show `n=0` gap, not zero.
- Raw append-only `per_seed_p2e.csv`, `run_config_p2e.json`, derived `summary_p2e.csv`, `p2e_redecision_ablation.svg`, SHA256 `manifest_p2e.json`. Output root never overwritten, and `--resume` only for unchanged exact source/config/prefix.

### 55.4 Diagnostic/acceptance contract
- **Data:** `experiments.run_p2e_redecision_ablation.validate_ablation_config/data/P2E_INVALID_LOSS_GRID,P2E_INVALID_SEED_RANGE`; nonfinite and off-grid PL must fail before simulation. Runtime guard `run_one_ablation_case/data/P2E_INVALID_ROUND_LIMIT` accepts only 1 or 300.
- **State/contract:** `prepare_ablation_evidence/state/P2E_OUTPUT_EXISTS,P2E_INVALID_RESUME_ROOT`; `contract/P2E_RESUME_CONFIG_CHANGED,P2E_RESUME_COLUMNS_CHANGED,P2E_RESUME_PREFIX_CHANGED,P2E_RESUME_CASE_CHANGED`; `extract_validated_native_batch/contract/P2E_INVALID_ORIGINAL_EPOCH,P2E_COST_ONCE_CONTRACT`; `validate_ablation_grid/contract/P2E_INCOMPLETE_GRID,P2E_SENDER_LEDGER_MISMATCH,P2E_ROUND_LIMIT_MISMATCH,P2E_INVALID_TASK_COVERAGE`; `validate_paired_initial_epochs/contract/P2E_FIRST_EPOCH_NOT_PAIRED`. Native first failing Diagnostic is preserved verbatim rather than replaced by a generic wrapper.
- **Network/traffic:** `experiments.run_e9h_adaptive_deadline.summarize_e9h_sender_phase_breakdown/contract/P2E_UNEXPECTED_SENDER_PHASE,P2E_SENDER_PHASE_TOTAL_MISMATCH`; `experiments.run_p2e_redecision_ablation.audit_native_sender_phases/contract/P2E_MISSING_NATIVE_SENDER_PHASE,P2E_SENDER_LEDGER_MISMATCH`.
- **Safety:** `count_observed_commits/safety/P2E_DUPLICATE_NATIVE_COMMIT`; original `protocol.validate_one_to_one_commits` safety remains authoritative for native Commits.
- **First-round pairing:** both arms must have same scene SHA and SHA256 of physical first-epoch messages, delivery outcomes, first-epoch awarded pairs; all 100 PL0 seeds must reproduce P2-C Global Greedy exactly with one native epoch, and identical one-/300-arm first results.
- **Fresh-run gate:** new exact 2000 method cases/20 group summary, Cost=100 sends per case, TASK=3 frame send per case, no extra Cost round, count sum/Bytes sum exact and all dropped SENDs charged; both native stops accurately labeled, no generated outcome before actual Mac execution.

### 55.5 Mac execution
On branch `experiment/p2e-redecision-ablation` with the user's **already active** Python environment:

```bash
python3 -m compileall -q democracy_mrta experiments tests
python3 -m unittest discover -s tests -p 'test_p2e*.py' -v
python3 -m unittest discover -s tests -v

python3 -m experiments.run_p2e_redecision_ablation \
  --losses 0.00,0.90 --seeds 2 \
  --output-root "results/p2e_smoke_$(date +%Y%m%d_%H%M%S)"

python3 -m experiments.run_p2e_redecision_ablation \
  --losses 0.00 --seeds 100 \
  --output-root "results/p2e_zero_$(date +%Y%m%d_%H%M%S)"

python3 -m experiments.run_p2e_redecision_ablation \
  --formal --seeds 100 \
  --output-root "results/p2e_formal_$(date +%Y%m%d_%H%M%S)"
```
Tests and formal data **have not yet been executed by the assistant in this GitHub-only editing environment**; Mac output must be independently audited and result figures only then promoted to README. See `docs/P2E_REDECISION_ABLATION.md` for full reproduction/handoff.


## 56. P2F — Repeatable Global Greedy Batch vs Sequential task voting (2026-10-16)

### Purpose and preserved scientific boundary
Compare decision granularity, **not one-shot versus retry**. Two Proposed arms both allow up to **300 native decision epochs** (stop early on full Commit), use identical (100R,100T,capacity=1) seeded scenes, per-receiver Cost/Vote Bernoulli loss, original Global minimum-pair Greedy local planner and same TASK/Cost/Rady+144Mbps model. Formal proposed grid 10 losses (PL0..90 step 10) x 100 seeds x 2 native modes = 2,000 NEW observations. CBAA/CBBA/original Centralized experiments are unchanged archival comparisons; they are not relabeled as newly rerun or forced to use another algorithm.

- `batch`: original `greedy_batch` in `coordination.simulate_democracy_hungarian_retirement`, all remaining tasks in one frame per voter per epoch; unfinished tasks retry.
- `sequential`: **same** `greedy_batch` Global Greedy planner over the entire remaining task matrix, but one voting epoch filters each local proposal to the **first pending physical task**. Only positive physically delivered vote records for that one task produce publicly reliable Score/Commit. If Commit succeeds, retire its robot and task, re-plan against remaining active robots/tasks next epoch. If no positive eligible vote, `protocol.apply_announced_retirement_commits` rotates the unassigned head task; do not permanently discard it. Up to 300 epochs. No assignment is made from invisible costs or invisible votes. This is NOT the legacy `greedy_task` Task-ID-local Greedy planning variant.
- The opt-in scope is `batch_vote_scope="one_task"`; the original default `"all"` preserves prior behavior. Neither arm resends the one-time Cost snapshot after initial Cost SENDs. Subsequent Vote packets are fresh task-specific decisions, not unaccounted retransmissions.
- At 100 robots, each original 100-task Cost is a sender-paid 816B SEND once/robot, every Vote SEND is 16+8x(number of voted pairs) payload (full batch up to 816B, sequential 24B), Score is physically billed and relevant Commit 28B. Every actual attempted SEND counts bytes **even when all recipients drop it**. Shared-medium time is recorded including radio queue, airtime and Rady residual; all-seed native STOP is not mislabeled allocation-complete time.
- **Compare** full 100/100 native paid-Commit completion, all-seed conflict-free coverage, attempted sender application Bytes broken into TASK/Cost/Vote/Score/Commit, all-seed modeled STOP seconds, number of epochs, and full-info Global Greedy-relative cost only for natively complete cases. For incomplete trials the cost ratio is blank, not 0. Additionally compare Bytes and time per completed task with explicit denominators; do not call early incomplete stop a fast successful allocation.
- At PL0, both must have all 100 physical pairs without duplicate robot/task; batch should complete in one epoch; sequential may require approximately 100 successful task epochs, possibly extra failed/task-rotation epochs if first-task candidate has no vote. Full-information Global Greedy is the unchanged **offline reference**; serial decisions are not assumed to produce exactly the same pairs as full batched Greedy because local Global Greedy is recomputed after every final task decision.
- A/B physical first-epoch Vote/Score traces are **deliberately different**. Paired acceptance requires identical seed, scene digest and each mode's once-only physically attempted Cost count, but this currently does **not** independently prove identical per-receiver Cost delivery under the later changed Vote packet trace. Do not claim first-epoch SHA equality; independent Cost receipt parity audit is a future stronger gate.
- Abandon unpublished P2F experimental variant if owner tests or native no-loss/packet-loss smoke fail and cannot be fixed without breaking original contracts; preserve the failed diagnostics locally, retire only the experimental branch, never rewrite original P2/P2C/P2D/P2E results or delete their evidence.

### Named owners and diagnostics
- `coordination.validate_batch_vote_scope` planning/`P2F_INVALID_BATCH_VOTE_SCOPE`; `validate_batch_vote_task_ids` contract/`P2F_INVALID_VOTED_TASK_ID`; `collect_greedy_batch_votes` filters physically transmitted ballot records; `simulate_greedy_batch_vote_epoch` filters eligible per-epoch tasks at Score/Commit; `simulate_democracy_hungarian_lossy` and `simulate_democracy_hungarian_retirement` own existing epoch execution and membership, not a second state machine.
- `experiments.run_e9h_adaptive_deadline.build_e9h_deadline_schedule` selects the original 32B vote deadline model for 24B single-task Vote; `run_e9h_original_voting_case` forwards scope; `experiments.run_p1_matched_five.run_original_voting/run_matched_case` forwards opt-in only.
- `experiments.run_p2f_sequential_voting.validate_comparison_config`, `prepare_comparison_evidence`, `run_one_comparison_case`, `validate_comparison_grid`, `validate_paired_scenes_and_cost`, `summarize_comparison`, `write_comparison_results`, `run_comparison` each own named study responsibilities, append-only raw CSV and source/config/seed SHA manifest. Other functions retain the specific original audit contract.
- First failure categories remain data/time/state/dependency/planning/safety/runtime/contract, with owner/function/code/expected/actual/details. Example P2F codes: contract/`P2F_COST_ONCE_CONTRACT,P2F_UNPAIRED_SCENE,P2F_INCOMPLETE_GRID,P2F_SENDER_LEDGER_MISMATCH`, data/`P2F_INVALID_VOTE_SCOPE,P2F_INVALID_ROUND_LIMIT`, safety/`P2F_DUPLICATE_NATIVE_COMMIT`.
- Evidence owner `experiments.run_p2f_sequential_voting`: `per_seed_p2f.csv`, `summary_p2f.csv`, `p2f_comparison_summary.json`, `run_config_p2f.json`, `manifest_p2f.json`. The JSON is a numerical summary, **not** an SVG chart. Do not update README main experimental figures before the user Mac run and independent source audit.

### 56. P2F terminal-only formal outcome (2026-10-16; not source-ZIP audited)
A user-submitted Mac terminal transcript (4,747 lines, `p2f_formal_100seed_20261016_130658`) reports compileall, 4/4 new targeted tests, 359/359 full regression tests, paired PL0/PL90 2-seed smoke (8 cases), two separate PL0 100-seed acceptance runs (200 cases each), and complete P2F formal 2,000 rows/20 method-loss groups. All 2,000 formal printed rows report `committed=100`. Independent parsing of the user-visible formal log identified exactly 1,000 unique (loss,seed) matched pairs and no missing/duplicate keys. The following numbers are **recomputed from the printed terminal rows**, not yet from `per_seed_p2f.csv` or its `manifest_p2f.json`:

| PL | Batch mean sender B | Sequential mean sender B | Batch mean stop s | Sequential mean stop s | Batch / sequential mean rounds |
|---|---:|---:|---:|---:|---:|
| 0% | 171648.00 | 211248.00 | 2.014 | 40.907 | 1.00 / 100.00 |
| 10% | 165660.56 | 205728.00 | 2.382 | 41.666 | 2.02 / 100.93 |
| 20% | 158307.44 | 199491.84 | 2.551 | 41.318 | 2.47 / 102.93 |
| 30% | 150764.72 | 191412.72 | 2.686 | 40.490 | 2.94 / 105.16 |
| 40% | 143107.76 | 183129.12 | 2.859 | 39.382 | 3.51 / 108.38 |
| 50% | 135622.24 | 172724.40 | 3.094 | 37.720 | 3.91 / 111.41 |
| 60% | 128164.32 | 161914.56 | 3.285 | 36.325 | 4.63 / 116.16 |
| 70% | 120827.28 | 149918.88 | 3.607 | 34.885 | 5.43 / 122.95 |
| 80% | 113440.96 | 136313.04 | 4.075 | 32.884 | 6.36 / 132.04 |
| 90% | 105670.64 | 120211.68 | 4.494 | 30.454 | 7.34 / 144.34 |

Every one of the **1,000 matched seed/loss pairs** has greater sender application Bytes **and** greater modeled stop time in Sequential than Batch, while both have identical 100/100 final task Commit count. Under the user's communication/time-first elimination criterion, **P2F Sequential Voting is NOT promoted to the main experimental comparison**. The entire study remains isolated on the experimental branch; do not silently delete raw data, rewrite old results or merge the optional `one_task` algorithm into the original default/main. At 0% the measured payload difference is exactly 39,600B (=121,200B vs 81,600B Vote broadcasts), despite each serial Vote being smaller. Higher PL can reduce **attempted** sender payload in this algorithm because active membership and emitted Vote/Score workloads change; this is not receiver-delivered-byte accounting and does not imply packet loss makes RF faster.

**Pending independent audit:** no original P2F `per_seed_p2f.csv`, phase-by-phase sender ledger, manifest SHA, complete-cost `quality_vs_full_info_greedy`, or Cost receiver trace was uploaded in this turn. These claims are provisional terminal-observation findings only, not accepted paper-source evidence. Obtain the exact original ZIP for independent cost/per-phase checks only if needed for appendix/archival verification. Both methods use the original modeled 144Mbps and Rady timing proxy, not measured physical Wi-Fi. No executable owner function, diagnostic code, frozen protocol or previously published README was changed by documenting this outcome.


## 57. P2G — One-Batch Task-Ordered Greedy vs native Repeatable Global Greedy (revised 2026-10-19)

**Version correction:** this section supersedes the PREVIOUS P2G Figure 1 definition of 100 sequential physical voting epochs. The user's new Figure 1 is **one task-ID-order local Greedy planning pass followed by ONE batched Vote transmission epoch**, not one broadcast per task. Both One Shot arms use the same task-order Greedy planner. P2F's old 300-epoch sequential experiment is separate and must never be relabeled as this experiment.

### 57.1 Two large figures, fixed scientific methods

**Figure 1: One-Shot, Task-ID-Ordered Greedy (2 new native methods)**

1. `task_ordered_vote_once`: each robot starts from only the one-time physically received Cost rows (its own row is locally known). The true optimizer `solve_visible_task_ordered_greedy_assignment(cost_matrix,visible_rows)` processes physical tasks strictly `T0,T1,...,T99`. At each T, assign the lowest `(cost,physical_robot_id)` visible robot that its **local plan** has not assigned yet, then remove that local robot. The robot transmits **exactly one 16B+8B per proposed pair BVOT broadcast** for the entire 100-task plan (up to 816B). Packet loss acts on this ONE broadcast per voter; all physically attempted SEND Bytes count, even if receivers drop the frame. Candidate-received Score announcements are modeled reliable and paid. The true `coordination.resolve_capacity_one_task_ordered_winners` processes tasks in ascending task ID, selecting the still-free candidate with the most **positive physically delivered votes** for that task (tie `robot_id` ascending), then emits the same paid reliable executor Commits. A task with no eligible voted candidate stays unassigned; never fill with hidden Cost. Original `voting_strategy="greedy_batch_task_order",batch_vote_scope="all",max_rounds=1,vote_repetitions=1,cost_repetitions=1`; the full 100-task vote phase happens **once only** with no packet retransmission or subsequent redecision. This is NOT the original `greedy_batch` Global minimum-edge planner or 100 task-by-task communication epochs.
2. `centralized_task_ordered_once`: the original `centralized_method.simulate_one_shot_centralized(max_cost_rounds=1,planning_rule="task_ordered")` captures **one physical Cost unicast** from each noncoordinator robot to coordinator 0 (no retry), coordinator locally knows its own row, then the SAME `solve_visible_task_ordered_greedy_assignment` on physically received robot Cost rows. It publishes one paid assignment frame and one Commit per executor, using existing reliable-control assumptions. No Hungarian, unseen Cost restoration, different task order, or repeat. Figure 1 Centralized is newly executed and **must NOT reuse the old P2D One-Shot Centralized Global Greedy aggregate** because it used another planner.

**Figure 2: Repeatable original methods (4 curves)**

1. `proposed_multi`: original/source-verified P2E Proposed Global **minimum-pair** Greedy with `greedy_batch,max_rounds=300`, locally retained one initial Cost snapshot; missing tasks have a fresh batched Vote/Score/Commit in later epochs. The lost Cost snapshot is **not** retransmitted.
2. `cbaa,cbba`: original SHA-pinned 100 Seed P2 CBAA and CBBA with their own native iterative auction/consensus and stopping mechanics. No Greedy replacement: Global Greedy is their read-only full-information **cost baseline only**.
3. `centralized_retry`: original Centralized true Cost owner with `max_cost_rounds=300,planning_rule="global"`. A sender whose Cost has not been timely received may repeat the physical Cost unicast, counted each attempted SEND. The coordinator retains successfully received rows, waits for all rows or guard, then executes **one original Global minimum-pair Greedy** assignment with one paid assignment and executor Commits. This is Cost retransmission, unlike Proposed repeated fresh decision epochs; labels must distinguish these.

### 57.2 Baselines, fixed fairness, metrics and output

- Formal scene: 100 robots x 100 tasks, capacity 1; same 100 seeded E0 geometries (0..99) per loss, 10 independent per-receiver Bernoulli Cost/Vote losses `0,10,...,90%`; original reliable TASK / Score / Commit modeling assumption, Rady latency with hypothetical 144Mbps shared medium. This is a simulated communication model, **not actual RF measurement**.
- **Figure 1 cost denominator is FULL-INFO TASK-ORDERED GREEDY**, evaluated on the same seed. **Figure 2 denominator is FULL-INFO GLOBAL MINIMUM-PAIR GREEDY**, same seed. Different planner baselines must be labeled on Figure titles, cost axis and paper caption; do not compare the figures' signed cost-increase numbers as if they shared a single reference. For each full one-to-one assignment only, `increase_percent=100*(actual_total_distance/reference_greedy_distance-1)`. For incomplete/unfeasible run, cost is blank and `n=0` rather than 0. Negative values are possible (Greedy is not globally optimal).
- Each **separate 1800×1240 four-panel 2×2 SVG** shows (a) strict full-native 100/100 task allocation rate (% complete trials / all trials), (b) signed cost difference to the **family-matched** full-info Greedy reference on natively completed trials only, (c) modeled all-seed **stop time** in seconds (incomplete stop isn't allocation success), (d) all-seed application sender payload kB for every physically emitted TASK/Cost/Vote/Score/Commit **including dropped packets**. A broadcast is one physical SEND, not its received recipient count. Explicitly distinguish native Proposed/central paid Commit from CBAA/CBBA observer terminal snapshots/stop guarantees.
- Exactly **3,000 fresh native P2G cases**: `task_ordered_vote_once`, `centralized_task_ordered_once`, `centralized_retry` × 10 PL × 100 seeds (30 new groups). Figure 2 reuses **3,000 previously SHA-verified native method cases** (P2E Multi-Round, P2 CBAA, P2 CBBA); original P2D centralized one-shot **not** plotted. We never claim 6,000 newly executed cases. The historical CSV is `docs/figures/p2de/formal/verified_50point_summary.csv` pinned by original Git blob/SHA+source identity and used for only the three unchanged methods. Original source ZIPs provide stronger raw provenance if separately independently audited.
- Output isolated fresh root: `per_seed_p2g.csv` (new source SHA and method, seed/PL, physical sender bytes, native coverage, family-specific reference), `summary_p2g.csv` (30 new groups, success-quality cohort n), `figure1_task_ordered_one_shot.svg`, `figure2_repeatable.svg`, `run_config_p2g.json`, `manifest_p2g.json` (per-file SHA). Append-only raw + source/config-and-case-locked resume, never overwrite historical files or published README primary figures before formal source audit.
- Tests, then **12-case smoke** (2 methods? no: 3 new modes × 2 seeds × 2 loss points), then **300-case PL0 gate** (3 new modes × 100 seeds; all three should achieve native 100/100), then 3,000 fresh formal native cases/30 groups. Separate a genuine method failure from study first-error contract; no imputation.

### 57.3 Owners, boundaries and diagnostic contract

- True `optimizer.solve_visible_task_ordered_greedy_assignment` owns local task-first candidate selection and physical Cost view validation; data/state/planning diagnostics `TASK_ORDER_GREEDY_INVALID_VISIBLE_ROW,TASK_ORDER_GREEDY_NO_VISIBLE_ROWS,TASK_ORDER_GREEDY_CARDINALITY_MISMATCH`. Existing `solve_visible_batched_greedy_assignment` (Global min-edge) and `solve_sequential_greedy_reference` retained unchanged.
- `coordination.validate_epoch_voting_strategy`, `build_epoch_local_proposals` and `validate_vote_decision_rule` admit explicit `greedy_batch_task_order` using the existing batched Vote/Score/Commit. `resolve_capacity_one_task_ordered_winners` owns deterministic T0-first **positive delivered** votes and capacity-one conflict, separate from `resolve_capacity_one_batch_winners` Global score-first owner. `simulate_greedy_batch_vote_epoch`, `simulate_democracy_hungarian_lossy` and existing `simulate_democracy_hungarian_retirement` use the exact same original one-epoch loop at max_rounds=1 with physically attempted SENDs; no second state machine.
- `centralized_method.validate_centralized_planning_rule` is planning/`P2G_INVALID_CENTRAL_GREEDY_RULE`. `plan_from_received_cost_rows` selects the exact shared optimizer only with `planning_rule=task_ordered`. `simulate_one_shot_centralized` forwards this opt-in with default `global`, and existing `max_cost_rounds` default=1 still preserves all P2D behavior. `experiments.run_p2d_centralized.run_one_centralized_case` forwards rule and validates PL0 against the appropriate full-information reference. Figure 2 central retry stays untouched `global`.
- Original E9H `build_e9h_deadline_schedule` and `run_e9h_original_voting_case`, original P1 `run_original_voting` record physically the exact one-batch strategy with original traffic/observer. P2G `execute_p2g_native,validate_p2g_native_outcome,measure_p2g_complete_quality,validate_p2g_grid,build_figure_source` own separate native calls, source/case pairing, two baselines and reporting. `p2g_plot.render_p2g_figure` labels family-specific figure and reference.
- All errors must point to first `owner/function/category/code`, including expected/actual/details where useful; valid categories exactly `data/time/state/dependency/planning/safety/runtime/contract`. Test failure/diagnostic means no formal promotion or silent fallback, and no old history is overwritten. Verification is pending user Mac; this GitHub editing session cannot execute remote Mac Python tests.
