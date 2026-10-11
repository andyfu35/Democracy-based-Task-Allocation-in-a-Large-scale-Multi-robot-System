# Democracy-based Task Allocation in a Large-scale Multi-robot System

This repository contains the reproducible benchmark and experimental record for a **leaderless, fully decentralized, quorum-based multi-robot task-allocation protocol** designed to remain useful under packet loss.

Target venue: **IEEE Robotics and Automation Letters (RA-L)**.

> Claim boundary: the paper contribution is the **communication / agreement protocol**, not a new optimization algorithm.

---

# 1. Canonical paper architecture

The system is intentionally separated into two layers.

## 1.1 Fixed optimization layer

Every evaluated coordination method uses the **same deterministic Hungarian optimizer**.

For one static allocation epoch with robot set \(R\), task set \(T\), and fixed cost matrix \(C=[c_{ij}]\):

\[
X^*=\arg\min_X\sum_i\sum_j c_{ij}x_{ij}
\]

subject to the one-to-one assignment constraints

\[
\sum_j x_{ij}\le1,\qquad
\sum_i x_{ij}=1.
\]

The Hungarian algorithm is used because it returns a global optimum for this linear assignment problem.

The optimizer is **not** the contribution being compared.

## 1.2 Communication / agreement layer

Each robot computes its own cost row and communicates cost information according to the evaluated coordination protocol.

For Democracy-based allocation:

1. a task set / allocation epoch is reliably announced;
2. robot \(i\) computes its own cost row;
3. each robot broadcasts its cost row once to peers;
4. every robot builds its local cost matrix \(\hat C_i\);
5. every robot runs the same deterministic Hungarian implementation on \(\hat C_i\);
6. its local assignment proposal is converted into one vote per task;
7. each vote is sent directly as a unicast to the robot proposed for that task;
8. a robot commits a task only after a strict-majority quorum;
9. the winner broadcasts one commit announcement for that task;
10. if quorum is not reached before timeout, the allocation round fails and is retried.

Strict-majority quorum for an eligible voter set of size \(N\):

\[
Q=\left\lfloor\frac{N}{2}\right\rfloor+1.
\]

### Required invariants

- one voter casts at most one vote per task per round;
- duplicate/retransmitted votes count once;
- stale-round votes are rejected;
- every robot uses the same voter set and quorum denominator;
- deterministic matrix ordering and tie handling are identical on every robot;
- with complete identical information, every robot must produce the same Hungarian optimum;
- strict majority prevents two different robots from both obtaining a valid majority for the same task/round.

---

# 2. Controlled coordination baselines

The main paper experiments hold the Hungarian optimizer fixed. They compare **coordination architectures**, not optimization algorithms.

| Method | Optimizer | Decision owner | Information strategy | Leaderless |
|---|---|---|---|---:|
| **Ideal Full Information** | Hungarian | reference only | complete matrix, no network impairment | n/a |
| **Leader-Hungarian** | Hungarian | one coordinator | robots unicast costs to leader; leader emits one assignment broadcast | No |
| **Flooding/Full-View Hungarian** | Hungarian | every robot | one cost-row broadcast per robot until full view or timeout | Yes |
| **Democracy-Hungarian (Ours)** | Hungarian | majority quorum | cost-row broadcasts -> local Hungarian proposals -> direct votes -> commit broadcast | **Yes** |

CBAA / ACBBA / DHBA remain important **Related Work** and may be reproduced later as a separate cross-method reference. They are not the primary controlled comparison because their allocation mechanism is coupled to their coordination protocol and therefore does not hold the optimizer fixed.

---

# 3. Realistic communication-time model

## 3.1 Primary empirical source

Primary latency reference:

**M. Rady, O. Iova, H. Rivano, A. Deligianni, and L. Drikos,  
“How does Wi-Fi 6 fare? An industrial outdoor robotic scenario,”  
Ad Hoc Networks, vol. 156, 103418, 2024.  
DOI: 10.1016/j.adhoc.2024.103418.**

Why this source is used:

- real industrial robotic environment;
- ROS 2 application-level control messages;
- real Wi-Fi 4 / 5 / 6 links;
- short/medium/long and LoS/NLoS conditions;
- application-level delay, not only nominal PHY bitrate;
- public source data are provided by the authors.

The authors' public dataset contains per-message fields including:

- `control_delay_ms`
- `control_loss`

and multiple locations / PHY configurations.

Source repository:

`minarady1/wifi_for_industrial_robotics`

Primary paper experiments will use an explicitly pinned Wi-Fi 6 trace/profile from this dataset.

## 3.2 Empirical bootstrap rule

Do **not** replace real communication with a single fixed delay.

For each successfully transmitted simulated protocol message \(m\):

\[
L_m \sim \text{EmpiricalBootstrap}(D_{WiFi6}),
\]

where \(D_{WiFi6}\) is the selected paper-derived array of measured ROS application delays.

Then:

\[
t_{arrival}(m)=t_{send}(m)+L_m.
\]

Packet loss is applied separately in experiments that sweep a controlled loss probability. This isolates the effect of packet loss from the empirical latency distribution.

A later trace-replay experiment will use both the paper-derived latency and loss observations together.

## 3.3 Communication time is event time, not message count times mean delay

Messages sent concurrently are not charged as

\[
N_{messages}\times E[L].
\]

The simulator is event-driven.

Examples:

- a quorum phase completes when the **Q-th valid vote arrives**;
- a full-information phase completes when all required information arrives or timeout occurs;
- retries add their actual timeout and subsequent communication events.

Per run, record:

\[
T_{total}=T_{compute}+T_{communication}+T_{retry}.
\]

The main quantity for the communication-cost claim is:

\[
T_{communication}.
\]

Also record message count and bytes so latency improvements cannot be hidden by excessive network traffic.

---

# 4. Common metrics

## Assignment quality

Central complete-information Hungarian optimum:

\[
J^*.
\]

Evaluated final assignment:

\[
J.
\]

Optimality gap:

\[
Gap=\frac{J-J^*}{J^*}\times100\%.
\]

At zero packet loss with complete information, the canonical implementation must satisfy:

\[
Gap=0.
\]

## Agreement / success

- assignment success rate
- full assignment commit rate
- task-level commit rate
- timeout rate
- mean retry rounds

## Timing

- local Hungarian computation time
- cost-exchange communication time
- voting/quorum communication time
- commit communication time
- retry/timeout time
- total decision latency

## Communication overhead

- attempted messages
- delivered messages
- dropped messages
- attempted bytes
- delivered bytes
- counts by message type

## Safety diagnostics

These must remain zero:

- multiple valid winners for one task/round
- duplicate execution in a one-to-one epoch
- duplicate vote counted
- stale-round vote accepted
- inconsistent quorum denominator

---

# 5. Formal experiment roadmap

All formal conditions use **100 paired seeds** unless explicitly documented otherwise.

## E0 — Perfect-Information Correctness

Purpose: validate the canonical algorithm before adding network impairment.

Conditions:

- packet loss = 0
- network latency = 0 for the correctness oracle run
- every robot receives the complete cost matrix
- every robot runs the same deterministic Hungarian optimizer

Required result:

\[
X_1=X_2=\cdots=X_N=X^*
\]

and

\[
Gap=0,\quad ASR=1,\quad SafetyFailures=0.
\]

The previous sequential-greedy E0 implementation/results are retained only as **legacy invalid evidence from an obsolete problem definition** and must not be cited as the paper algorithm.

### E0 result record

Status: **FORMAL LOCAL RUN PASSED**

Date: `2026-10-09`

Formal corrected E0:

- unit tests: **12/12 passed**
- conditions: 10R/5T, 25R/10T, 50R/30T, 100R/50T, 100R/100T
- 100 seeds per condition
- 500 scenarios total

| Robots | Tasks | Seeds | Gap | ASR | Oracle mismatch | Non-unanimous tasks | Safety failures | Replay failures |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 10 | 5 | 100 | 0.000000000000% | 1.000000 | 0 | 0 | 0 | 0 |
| 25 | 10 | 100 | 0.000000000000% | 1.000000 | 0 | 0 | 0 | 0 |
| 50 | 30 | 100 | 0.000000000000% | 1.000000 | 0 | 0 | 0 | 0 |
| 100 | 50 | 100 | 0.000000000000% | 1.000000 | 0 | 0 | 0 | 0 |
| 100 | 100 | 100 | 0.000000000000% | 1.000000 | 0 | 0 | 0 | 0 |

Corrected local raw file:

`results/e0_protocol_correctness/raw/e0_corrected_20261009T141508Z.csv`

Corrected local summary:

`results/e0_protocol_correctness/summary.csv`

These generated files must still be committed from the machine that executed the formal run.

**Conclusion:** under complete identical information, every robot produces the same Hungarian assignment, every task vote is unanimous, and Democracy-Hungarian exactly matches the global Hungarian optimum.

The earlier sequential-greedy E0 result is legacy invalid evidence from an obsolete implementation and must not be cited as the paper algorithm.

---

## E1 — Realistic Wi-Fi Communication-Time Cost

Purpose: answer:

> How much decision time does each coordination architecture spend on trace-driven wireless communication when there is no packet loss?

Conditions:

- packet loss = 0
- fixed Hungarian optimizer
- empirical ROS 2 Wi-Fi application delay sampled from the pinned Rady et al. dataset
- broadcast-corrected transport semantics
- 100 paired seeds per condition

Compare:

- Ideal Full Information
- Leader-Hungarian
- Flooding/Full-View Hungarian
- Democracy-Hungarian

Primary outputs:

- actionable decision time
- global agreement time
- cost-exchange time
- local Hungarian compute time
- message count
- logical payload bytes

### E1 result record

Status: **FORMAL TRACE-DRIVEN RUN COMPLETE**

Pinned empirical profile:

- source repository: `minarady1/wifi_for_industrial_robotics`
- source commit: `1996e5bb69b9ba4d25060cbc14838ddedf65cff2`
- source JSON Git blob: `11e70e685229cc26458f272b0c954487c87d7953`
- location: **Medium range LoS (60 m)**
- PHY: **Wi-Fi 6E ax/6/160**
- steady-state window: **120–181 s**
- ROS delay samples: **121**
- empirical mean: **33.593687 ms**
- P50: **19.962509 ms**
- P95: **64.149866 ms**
- P99: **159.419021 ms**
- maximum: **531.535123 ms**

Corrected local raw output:

`results/e1_latency/raw/e1_20261009T144026Z.csv`

Corrected local audit events:

`results/e1_latency/events/e1_events_20261009T144026Z.csv.gz`

Corrected local summary:

`results/e1_latency/summary.csv`

These generated result files remain pending user-side git commit.

| Robots | Tasks | Method | Actionable mean | Global mean | P95 global | Messages | Payload bytes |
|---:|---:|---|---:|---:|---:|---:|---:|
| 10 | 5 | Leader | 157.162 ms | 157.162 ms | 551.821 ms | 10 | 560 |
| 10 | 5 | Full-View | 142.228 ms | 142.228 ms | 531.535 ms | 10 | 560 |
| 10 | 5 | Democracy | 168.375 ms | 247.598 ms | 605.326 ms | 60 | 2,140 |
| 25 | 10 | Leader | 268.586 ms | 268.586 ms | 568.001 ms | 25 | 2,400 |
| 25 | 10 | Full-View | 236.312 ms | 236.312 ms | 531.535 ms | 25 | 2,400 |
| 25 | 10 | Democracy | 260.792 ms | 391.655 ms | 1,068.761 ms | 275 | 10,360 |
| 50 | 30 | Leader | 370.827 ms | 370.827 ms | 580.675 ms | 50 | 12,800 |
| 50 | 30 | Full-View | 336.090 ms | 336.090 ms | 531.535 ms | 50 | 12,800 |
| 50 | 30 | Democracy | 362.120 ms | 659.889 ms | 1,083.071 ms | 1,550 | 60,680 |
| 100 | 50 | Leader | 477.409 ms | 477.409 ms | 581.239 ms | 100 | 41,600 |
| 100 | 50 | Full-View | 452.627 ms | 452.627 ms | 531.535 ms | 100 | 41,600 |
| 100 | 50 | Democracy | 477.742 ms | 796.165 ms | 1,084.052 ms | 5,100 | 201,400 |
| 100 | 100 | Leader | 477.409 ms | 477.409 ms | 581.239 ms | 100 | 81,600 |
| 100 | 100 | Full-View | 452.627 ms | 452.627 ms | 531.535 ms | 100 | 81,600 |
| 100 | 100 | Democracy | 478.327 ms | 918.551 ms | 1,084.184 ms | 10,100 | 401,200 |

### E1 interpretation

The fixed Hungarian computation is negligible relative to communication. At 100R/100T the measured local Hungarian wall-clock mean is only **0.752068 ms**, while trace-driven communication reaches hundreds of milliseconds.

The most important timing result is the distinction between **actionable decision** and **global agreement**:

- Democracy adds only about **25–26 ms** to the Full-View actionable time across the larger conditions.
- At 100R/50T, Democracy actionable time is **477.742 ms**, essentially identical to Leader-Hungarian at **477.409 ms**.
- At 100R/100T, Democracy actionable time is **478.327 ms**, also essentially identical to Leader-Hungarian at **477.409 ms**.
- Democracy global-agreement time is much larger because every task winner still broadcasts a commit and the experiment reports the final commit arrival across all tasks.

The communication-volume trade-off is substantial:

- 100R/100T Leader: **100** logical transmissions, **81.6 kB** payload.
- 100R/100T Full-View: **100** logical transmissions, **81.6 kB** payload.
- 100R/100T Democracy: **10,100** logical transmissions, **401.2 kB** payload.

Therefore E1 supports a precise trade-off statement: **leaderless democratic quorum adds little actionable latency after full information is available, but it incurs substantially higher message count and global commit dissemination cost.**

### E1 claim boundary

E1 is a **trace-driven application-delay model**, not a full 802.11 shared-medium contention simulator.

It preserves the measured application-delay distribution from the cited robotic Wi-Fi experiment, but it does not add new fleet-size-dependent CSMA/CA contention caused by thousands of protocol transmissions. Message-count and payload results must therefore be reported alongside latency, and later scalability experiments must not interpret E1 latency as a complete on-air saturation model.

The earlier pre-broadcast E1 run is retained only as diagnostic pilot evidence and must not be cited.

---

## E2 — Bernoulli Packet-Loss Robustness

Purpose: measure how each coordination architecture degrades when **cost information and decision votes are independently lost**.

Loss sweep:

`p_loss ∈ {0, 0.1, 0.3, 0.5, 0.7, 0.9}`

Canonical E2 scope:

- same fixed Hungarian optimizer as E0/E1;
- same pinned Rady empirical latency profile as E1;
- one round only — no retry in E2;
- cost broadcast delivery is Bernoulli per receiver;
- each robot always retains its own cost row;
- hidden rows stay hidden;
- Democracy and Leader run Hungarian only over rows locally available;
- partial local Hungarian assignments are allowed;
- a Democracy voter abstains on tasks absent from its partial assignment;
- vote unicasts use the same Bernoulli loss probability;
- quorum denominator remains the full eligible robot count;
- commit broadcast is reliable;
- Full-View succeeds only when every robot has a complete matrix.

Primary outputs:

- task commit rate;
- **correct executor rate (CER)**;
- **correctness among committed tasks**;
- full-assignment success rate;
- optimal-solution rate;
- optimality gap among full successful assignments;
- task timeout rate;
- decision/global completion time;
- logical messages and payload bytes;
- delivery drops;
- mean visible robot rows;
- safety failures.

### E2 result record

Status: **CER RERUN COMPLETED — VOTE-LEVEL AUDIT PENDING**

The E2 communication phase timeout is pinned to the maximum E1 empirical delay:

`T_phase = 531.535123 ms`

This means `p_loss = 0` must reduce to the E1 zero-loss behavior instead of introducing a new arbitrary deadline.

Run:

```bash
git pull
python3 -m unittest discover -s tests -v
python3 -m experiments.run_e2 --seeds 100
```

Formal outputs:

- `results/e2_packet_loss/raw/e2_<timestamp>.csv`
- `results/e2_packet_loss/events/e2_events_<timestamp>.csv.gz`
- `results/e2_packet_loss/summary.csv`

Required sanity checks before accepting the formal result:

- at `p = 0`: task commit = 1, full success = 1, optimal rate = 1, successful gap = 0 for every method;
- Democracy safety failures = 0 at every loss level;
- Full-View should degrade rapidly because it explicitly requires complete information;
- no missing cost may be silently filled from the global matrix.

A first 100-seed E2 run on 2026-10-09 passed all safety/correctness preflights and exposed a strong availability-versus-quality trade-off, but it did not record task-level correct-executor metrics. That run is retained as **diagnostic pilot evidence**, not the final paper E2.

Pilot observations include:

- all (p=0) conditions exactly reproduce the zero-loss correctness boundary;
- Full-View collapses under any nonzero loss because this E2 baseline requires every robot to receive a complete matrix in one round;
- Democracy retains high task commit rate around 10% loss for non-saturated loads while its fully successful assignments remain near the complete-information optimum;
- Leader-Hungarian often retains high assignment completion while its optimality gap grows sharply as rows disappear.

The CER-instrumented 100-seed rerun was completed locally on 2026-10-09 with **30/30 tests passing**. At 100R/50T and cost/vote loss both 30%, it reported mean visible rows 70.285, task commit rate 15.22%, CER 15.06%, and conditional correctness 98.706%.

These totals are **not** sufficient to verify raw voter correctness or rule out a ledger accounting error. The experiment now has an opt-in, read-only forensic vote audit. Before treating E2 as paper evidence, run:

```bash
python3 -m experiments.audit_e2_votes --robots 100 --tasks 50 --p-loss 0.3 --seeds 100
```

This independently checks each local view against cost deliveries, each ballot against vote transport, and reconstructed ballots against the actual counted protocol ledger. It emits per-voter, per-task, and per-candidate CSVs without changing allocation behavior.

**Paper result:** pending vote-level audit acceptance.

### E2 cost-information-loss threshold sweep (vote channel reliable)

The optional runner flag `--vote-loss-probability 0` fixes Democracy vote packet loss to **zero**, while the existing `--loss-probabilities` sweep changes only the independently lost cost rows received by each robot. The original E2 experiment is **unchanged when the override flag is omitted**.

Run a 100R/50T paired-seed sweep from 0% through 70% cost loss at 2-point increments (100 seeds per point):

```bash
python3 -m experiments.run_e2 \
  --seeds 100 \
  --conditions 100x50 \
  --loss-probabilities "$(python3 -c 'print(",".join(f"{i/100:.2f}" for i in range(0, 71, 2)))')" \
  --vote-loss-probability 0 \
  --output-root results/e2_cost_only_100r50t
```

In that output, `p_loss` is cost-row loss and `p_vote_loss` is zero. Track Democracy `mean_task_commit_rate`, `mean_correct_executor_rate`, `optimal_solution_rate`, and `full_assignment_success_rate` separately. Declare the operational usability threshold explicitly; report the first sampled loss where task commit falls below selected cutoffs rather than inferring it from full-assignment optimality alone.



### New sequential Greedy Democracy with executor retirement

**Active experimental optimizer: Greedy — not Hungarian.** Original E0/E1/E2 Hungarian results remain untouched and are used only as existing controls / offline global-optimal cost references.

- Broadcast all task costs once; every receiver independently keeps only delivered peer cost rows, plus its own row.
- Vote on **one pending task at a time**: each active robot chooses the lowest-cost visible active executor (ties: lowest original robot ID).
- Winner with strict majority broadcasts a reliable commit and is removed from all later voter/candidate sets; the task leaves the queue.
- With no majority, move the failed task to the end of the queue; keep the same incomplete local views and retry with a new vote-round ID. No cost rebroadcast.
- Recalculate strict majority from the **remaining unassigned robots** at each new voting round; stop at `--max-rounds`.
- `max_rounds` counts task-vote attempts. To finish 50 tasks at zero loss you need at least 50 rounds; the default is twice the requested task count (100 for 50 tasks).

Run the regression suite and a **3-seed smoke** first:

```bash
git pull
python3 -m unittest discover -s tests -v
python3 -m experiments.run_e2_retirement \
  --robots 100 --tasks 50 --seeds 3 \
  --cost-loss-probabilities 0,0.3,0.5 \
  --vote-loss-probability 0 --max-rounds 100 \
  --output-root results/e2_greedy_retirement_smoke
```

After that passes, 100 paired seeds / 36 Cost Loss levels (0–70% in 2% steps), Vote Loss fixed 0:

```bash
python3 -m experiments.run_e2_retirement \
  --robots 100 --tasks 50 --seeds 100 \
  --vote-loss-probability 0 --max-rounds 100 \
  --output-root results/e2_greedy_retirement_100r50t
```

Results include `summary.csv`, timestamped raw per-seed CSV, per-round attempted-task/active-voter/quorum/commit CSV, and seed-0 network event evidence. The summary separates **Greedy-reference correctness** from **Hungarian global-optimal cost gap**. A Greedy outcome need not have zero global cost gap even with 0% loss.

**Status: CODE COMMITTED, LOCAL TEST / FORMAL RESULTS PENDING.** No physical task execution, rejoining, or unreliable commit announcements are modeled. See `docs/EXPERIMENT_PROTOCOL.md` §13 for the complete new protocol.



### Full Vote Loss sensitivity suite for Sequential Greedy

The completed 100-seed Cost-only run had p_vote_loss=0. The separate Vote Loss experiments now hold Cost Loss fixed or vary it jointly. All use **the same existing Greedy local voter, majority, executor retirement, static cost-row snapshot, 100-robot/50-task scenarios, 100 paired seeds and at most 100 task-voting attempts**. Self-votes remain reliable; only remote vote unicasts experience Vote Loss.

Upgrade and smoke test **before** starting the three full runs:

```bash
git pull
python3 -m unittest discover -s tests -v
python3 -m experiments.run_e2_retirement \
  --robots 100 --tasks 50 --seeds 3 \
  --cost-loss-probabilities 0,0.30 \
  --vote-loss-probabilities 0,0.30,0.70 \
  --max-rounds 100 \
  --output-root results/e2_vote_loss_smoke
```

Formal 36-point Vote Loss-only curve (p_cost_loss=0):

```bash
LEVELS="$(python3 -c 'print(",".join(f"{i/100:.2f}" for i in range(0, 71, 2)))')"
python3 -m experiments.run_e2_retirement \
  --robots 100 --tasks 50 --seeds 100 \
  --cost-loss-probabilities 0 \
  --vote-loss-probabilities "$LEVELS" \
  --max-rounds 100 --output-root results/e2_vote_only_100r50t
```

Formal 36-point Vote Loss sweep with fixed 30% Cost Loss:

```bash
python3 -m experiments.run_e2_retirement \
  --robots 100 --tasks 50 --seeds 100 \
  --cost-loss-probabilities 0.30 \
  --vote-loss-probabilities "$LEVELS" \
  --max-rounds 100 --output-root results/e2_cost30_vote_sweep_100r50t
```

Formal 36-point joint diagonal curve (p_cost_loss=p_vote_loss; packet draws independent):

```bash
python3 -m experiments.run_e2_retirement \
  --robots 100 --tasks 50 --seeds 100 \
  --cost-loss-probabilities "$LEVELS" \
  --loss-pairing diagonal \
  --max-rounds 100 --output-root results/e2_joint_loss_diagonal_100r50t
```

Each command independently reports actual `observed_cost_drop_rate` and `observed_vote_drop_rate` from physical packet records, `mean_task_commit_rate`, `full_assignment_success_rate`, `mean_greedy_correct_executor_rate`, rounds/time/payload and complete-allocation cost gap relative to the external full-information Hungarian benchmark. The Vote Loss denominator excludes self-votes; raw rows also expose self-vote counts and vote-quorum failures.

Optional coarse 2D interaction test (64 cells × 100 seeds):

```bash
GRID="0,0.10,0.20,0.30,0.40,0.50,0.60,0.70"
python3 -m experiments.run_e2_retirement \
  --robots 100 --tasks 50 --seeds 100 \
  --cost-loss-probabilities "$GRID" \
  --vote-loss-probabilities "$GRID" \
  --max-rounds 100 --output-root results/e2_joint_loss_grid_100r50t
```

Each output root contains its own `summary.csv`, per-seed raw rows, per-round state/commit rows and seed-0 event/delivery evidence. **Do not overwrite the completed Cost-only summary.** The new Vote Loss runner extension must pass the expanded unit suite and local smoke before any formal numerical conclusions.



### Pure 25%-Announcement Plurality — no fallback or self-election

This is the user-authorized 25% voting experiment. **The previously added self-claim fallback was explicitly removed**. The archived experiment with fallback in results/e2_greedy_quarter_plurality_100r50t is no longer a valid estimate of pure 25% voting behavior. Existing strict-majority and Hungarian experiments remain unchanged.

- Active robots independently choose the cheapest currently visible active executor for the next pending task, using Greedy and the single initial lossy Cost exchange.
- A candidate may send a reliable **final-score announcement** only if it has more than 25% of ALL active voter ballots: floor(N/4)+1. At N=100 this is 26 received votes.
- If several qualify, highest announced tally wins; ties use the lowest original robot ID. One winner sends a reliable Commit and retires from subsequent voting.
- **If no candidate qualifies, there is NO announcement and NO Commit.** The task rotates to the pending queue tail, everyone remains active, and the next vote attempt uses fresh Vote Loss packet draws. There is no emergency self-claim or other winner-selection channel.
- The total attempt budget stays at 100 for 100R/50T. Incomplete tasks stay incomplete; only complete assignments receive an overall cost-gap metric.
- Qualified score announcements are assumed reliable and charged to communication counts/time; Cost and Vote packet loss remain independent with equal numeric probabilities in the formal test. This assumption must not be generalized to unreliable control broadcasts.

Upgrade and run tests / a 3-seed smoke:

    git pull
    python3 -m unittest discover -s tests -v
    python3 -m experiments.run_e2_retirement --robots 100 --tasks 50 --seeds 3 --cost-loss-probabilities 0,0.30,0.70 --loss-pairing diagonal --max-rounds 100 --vote-decision-rule quarter_plurality --output-root results/e2_greedy_quarter_plurality_no_fallback_smoke

Full paired 100-seed, 36-point Cost Loss = Vote Loss sweep:

    LEVELS="$(python3 -c 'print(",".join(f"{i/100:.2f}" for i in range(0, 71, 2)))')"
    python3 -m experiments.run_e2_retirement --robots 100 --tasks 50 --seeds 100 --cost-loss-probabilities "$LEVELS" --loss-pairing diagonal --max-rounds 100 --vote-decision-rule quarter_plurality --output-root results/e2_greedy_quarter_plurality_no_fallback_100r50t

Do not reuse the archived fallback result root. New per-round and summary results report no-qualified-announcement attempts, qualified announcements, actual winner tally, remaining tasks, successful commits, total elapsed time, bytes/messages, and two oracle comparisons. Historical fallback-only metrics are deliberately not generated.

Status: **new code/tests committed; updated local tests and full no-fallback scan pending**. Canonical rule: docs/EXPERIMENT_PROTOCOL.md Section 14.


---

## E3/E4 — Robot × Task-Load Scaling (up to 100 robots and 1:1)

**Status: driver and tests committed; local scaling validation and formal runs pending.** The planned 200-robot E3 point is superseded by the user's explicit 100-robot ceiling.

The algorithm is the previously verified PURE 25%-announcement Greedy:
- One active robot casts one locally planned lowest-visible-cost ballot for the pending task.
- A candidate announces only after receiving strictly more than 25% of all currently active voters' votes.
- Compare qualifying final scores; highest vote count wins, lower physical robot ID breaks ties; one reliable Commit and executor retirement.
- **No fallback.** A failed threshold means no announcement and no Commit; rotate the still-unassigned task and retry, up to max_rounds.
- Initial Cost rows are sent once; Cost and Vote packet loss are sampled independently at equal configured loss probability; qualified score and Commit announcements remain modeled as reliable.

The 30-size-cell matrix is:

| Robots | 10% tasks | 25% tasks | 50% tasks | 75% tasks | 100% tasks (1:1) |
|---:|---:|---:|---:|---:|---:|
| 10 | 1 | 3 | 5 | 8 | 10 |
| 20 | 2 | 5 | 10 | 15 | 20 |
| 40 | 4 | 10 | 20 | 30 | 40 |
| 60 | 6 | 15 | 30 | 45 | 60 |
| 80 | 8 | 20 | 40 | 60 | 80 |
| 100 | 10 | 25 | 50 | 75 | 100 |

Target ratio -> task count uses round-half-up. Record the actual T/R, and never permit R>100 or T>R. The previously measured 100R/50T point is retained as a comparison anchor, and 100R/100T is the maximum-load case.

Two paired conditions per cell: Cost Loss = Vote Loss = **0% and 30%**, with 100 seeds per loss condition. Total: **30 cells × 2 losses × 100 seeds = 6,000 simulations**.

**Fair retry allowance:** max_rounds = 2 × requested tasks, not a fixed global 100. Thus 100R/50T has 100 attempts (as before) and 100R/100T has 200 attempts. One failure should not mathematically prevent 1:1 full assignment before reaching the retry budget.

### Run on Mac

~~~bash
git pull
python3 -m unittest discover -s tests -v

# Smoke: 4 size cells x 2 loss levels x 3 seeds = 24 runs
python3 -m experiments.run_e3_e4_scaling \
  --robot-levels 10,100 --load-ratios 0.5,1.0 \
  --loss-probabilities 0,0.30 --seeds 3 \
  --attempts-per-task 2 \
  --output-root results/e3_e4_scaling_smoke_100cap

# Formal: 30 size cells x 2 loss levels x 100 seeds = 6,000 runs
python3 -m experiments.run_e3_e4_scaling \
  --seeds 100 \
  --output-root results/e3_e4_scaling_100robot_cap

# Exact same code/config/dataset only; resume after interruption:
python3 -m experiments.run_e3_e4_scaling \
  --seeds 100 \
  --output-root results/e3_e4_scaling_100robot_cap \
  --resume
~~~

The scaling root stores benchmark_plan.json, per-cell raw/round/message files in cells/R###_T### and aggregate summary.csv (expected 60 rows when complete). It writes the summary after each completed verified cell, and refuses an incompatible resume or silently overwriting partial data.

Primary E3 comparison: robots vs communication time, messages/bytes, completion and global cost gap at constant task ratio (particularly 50% and 100%). Primary E4 comparison: task ratio vs completion, time, failed-vote count and greedy/global-optimum quality at fixed robots=100. Compare both absolute and per-requested-task communication metrics.

The model remains static ONE-TO-ONE assignment with retired executors: it does not simulate physical task completion and robots rejoining. See docs/EXPERIMENT_PROTOCOL.md section 15 and results/e3_e4_scaling_100robot_cap/README.md.

---

## Official Greedy-only communication comparison (historical E2 re-analysis)

**Research scope:** The optimizer is always **Sequential Greedy**; the subject of the paper is decentralized coordination and robustness to communication loss, NOT finding a new Hungarian/global minimum-cost assignment algorithm. Previous Hungarian output may remain in original historical CSVs for audit, but it is NOT used or plotted by the new primary comparison.

The two already-completed formal E2 experiments provide matched 100R/50T raw evidence:

- strict-majority (51% of the active electorate), results/e2_joint_loss_diagonal_100r50t/raw/retirement_*.csv;
- pure >25%-announcement Greedy, **NO fallback**, results/e2_greedy_quarter_plurality_no_fallback_100r50t/raw/retirement_*.csv.

Do NOT substitute the rejected 25%-with-self-claim-fallback experiment.

The Greedy-only read-only analysis uses the **same 100 seeds and same scenarios**, max_rounds=100, Cost Loss = Vote Loss (equal numeric p, independently sampled packets). The main figure uses the existing 0%, 10%, 20%, 30%, 40%, 50% points; all six are subsets of the original full 0–70%/2%-step runs. **No new simulation or Hungarian calculation is necessary.**

For each seed and each rule, use that rule's 0%-Loss full-information Greedy as the only performance reference. Show task Commit fraction, full T-task success, Greedy executor identity match, mean voting attempts, physical packet drops, simulated coordinator time, messages/bytes, and **loss-induced added cost among fully completed allocations ONLY**. Unfinished assignments are always counted as failures and have NaN full-assignment cost rather than an artificially cheap partial-cost score. Cross-rule cost is compared only on the exact seed intersection where both rules complete; report that sample size.

### Run after existing full E2 raw CSV files are present on your Mac

~~~bash
git pull
python3 -m unittest discover -s tests -v

# Pure evidence analysis — NO simulator / Hungarian / new seeds
python3 -m experiments.compare_greedy_communication
~~~

Results are written under results/e2_greedy_only_communication_comparison (README.md is preserved):

- greedy_per_seed.csv — expected 1,200 rows for 2 rules × 100 seeds × 6 losses.
- greedy_rule_curve.csv — expected 12 rows, including complete-case cost sample sizes.
- greedy_protocol_delta.csv — expected 6 rows showing paired 25%-minus-51% success and cost/traffic differences.
- manifest.json — source SHA256 hashes, source historical Git SHAs, current analysis commit SHA, UTC timestamp and full benchmark parameters.

To compare all previous 36 Cost/Vote loss points in a separate new derived directory:

~~~bash
LEVELS="$(python3 -c 'print(",".join(f"{i/100:.2f}" for i in range(0, 71, 2)))')"
python3 -m experiments.compare_greedy_communication \
  --loss-probabilities "$LEVELS" \
  --output-root results/e2_greedy_only_communication_comparison_36point
~~~

The analysis **rejects** mismatched per-seed Greedy reference costs, missing seeds, nonmatching dimensions, incorrect method IDs, fallback data, duplicate source files, false zero-loss baselines and overwriting already-derived results. It cannot compare raw E2 results if the previous experiments were run elsewhere and their files have not been copied into the same checkout. The known assumption that qualified score announcements and Commit are reliable is unchanged.

**Verification:** Earlier E2 runs and E3/E4 6,000-run scale sweep were completed by the user. This derived analysis code is NEW and its unit tests/output on the Mac are pending; no fresh output curves have been asserted yet. Full definitions: docs/EXPERIMENT_PROTOCOL.md Section 16 and results/e2_greedy_only_communication_comparison/README.md.

---

## External Packet-Loss Defense Benchmarks — first implementation

**Status: fixed-count vote-copy baseline added, tests and actual new runs pending Mac execution.** Our formal research contribution is decentralized task allocation under Packet Loss, NOT a new global optimizer. Keep exactly the same Greedy local decision rule and original task/robot scenarios in all primary communication comparisons.

Our existing two reference curves:
- Greedy + 51%-majority (one remote Vote packet).
- Greedy + pure >25%-qualified score announcement, NO fallback (one remote Vote packet).

**New external communications reliability control**: redundant physical sending of each remote Vote packet without acknowledgements. Command-line option --vote-repetitions=2 or 3, or default 1. This is fixed open-loop sender redundancy, NOT ACK-based ARQ, NOT CBAA, CBBA or ACBBA. All additional transmissions are physically sampled and charged in packet attempts, messages, payload bytes and conservative transmission time slots. Only one logical Vote per voter is counted, regardless of how many copies arrive; self-votes stay local, Cost row broadcast remains once and final score/Commit remain reliably modeled as before.

Compared variants at 100 Robots / 50 Tasks, 100 seeds, diagonal Cost Loss=Vote Loss=0..70% in 2% steps and max_rounds=100:
1. Original 51%-majority, one Vote packet (old E2 evidence).
2. 51%-majority, TWO Vote packet copies (new).
3. 51%-majority, THREE Vote packet copies (new).
4. Pure >25%-qualified score announcement, one Vote packet, NO fallback (old E2 evidence).

Start with unit tests and 3-seed smoke (0%, 30%, 50% joint Cost/Vote Loss):

~~~bash
git pull
python3 -m unittest discover -s tests -v
python3 -m experiments.run_e2_retirement \
  --robots 100 --tasks 50 --seeds 3 \
  --cost-loss-probabilities 0,0.30,0.50 --loss-pairing diagonal \
  --max-rounds 100 --vote-decision-rule strict_majority \
  --vote-repetitions 2 --output-root results/e2_repeat2_majority_smoke
python3 -m experiments.run_e2_retirement \
  --robots 100 --tasks 50 --seeds 3 \
  --cost-loss-probabilities 0,0.30,0.50 --loss-pairing diagonal \
  --max-rounds 100 --vote-decision-rule strict_majority \
  --vote-repetitions 3 --output-root results/e2_repeat3_majority_smoke
~~~

Only after tests and smoke pass, run full 36-point, 100-seed scans (3,600 runs per repeated-vote variant):

~~~bash
LEVELS="$(python3 -c 'print(",".join(f"{i/100:.2f}" for i in range(0, 71, 2)))')"
python3 -m experiments.run_e2_retirement \
  --robots 100 --tasks 50 --seeds 100 \
  --cost-loss-probabilities "$LEVELS" --loss-pairing diagonal \
  --max-rounds 100 --vote-decision-rule strict_majority \
  --vote-repetitions 2 \
  --output-root results/e2_repeat2_majority_100r50t
python3 -m experiments.run_e2_retirement \
  --robots 100 --tasks 50 --seeds 100 \
  --cost-loss-probabilities "$LEVELS" --loss-pairing diagonal \
  --max-rounds 100 --vote-decision-rule strict_majority \
  --vote-repetitions 3 \
  --output-root results/e2_repeat3_majority_100r50t
~~~

Compare FULL-task assignment success, Greedy executor accuracy and complete-only Greedy cost degradation alongside **number of physical Vote attempts, payload bytes and simulated total coordination time**. DO NOT claim winning solely from success percentage if another protocol sends significantly more packets; this is a success/traffic/time Pareto analysis.

The fixed-copy scheme is a standard general reliability CONTROL, not a faithful reproduction of published MRTA algorithms. A genuinely comparable next algorithm family is CBAA/CBBA and its asynchronous ACBBA variant, with their own true local bid/conflict and convergence mechanisms. Reference sources: Choi et al. (IEEE T-RO 2009 DOI 10.1109/TRO.2009.2022423), MIT ACL's CBBA project, Rantanen et al. (IEEE SAM 2018 DOI 10.1109/SAM.2018.8448984). Implement those in a separate bounded change; do not disguise our Vote plurality or duplicate-copy mechanism as those algorithms.

Protocol, code ownership, diagnostics, limitations: docs/EXPERIMENT_PROTOCOL.md Section 17.

---

## E9A — Observed matching of Greedy25 and CBAA transmitted Bytes (calibration only)

We must not compare CBAA's arbitrary 20 repeated full-vector broadcasts to a single run of our packet-loss-resistant Greedy 25% task voting and call them equal communication. E9A adds a **READ-ONLY** source-verified byte/resource calibration tool in experiments/compare_cbaa_budget.py. It reads the completed, historical 100R/50T 100-seed pure25 E2 raw evidence and already generated CBAA raw, optionally with new CBAA iteration configurations. It NEVER changes task decisions or historical results. Its candidate CBAA iteration count is chosen using **p=0 Greedy mean send Bytes only**, independent of CBAA success or p=.30/.50 outcome. For each p and seed it publishes actual sender Bytes, message counts, simulated time, Greedy complete Commit vs CBAA external observer agreement and CBAA conflicts. It flags any ratio outside a predeclared +/-10% tolerance.

The unit of budget is sender-COUNTED application payload Bytes. Each broadcast is counted ONCE, not multiplied by recipients; receiver delivery opportunities and physical packet drops remain separately reported. Neither project model includes radio channel contention/airtime, and the CBAA consensus channel differs from E2's Cost+Vote + reliable score/Commit. **This is NOT a true hard byte cap**, so no equal-budget superiority should yet be claimed.

Run from Mac where historical 25% and CBAA K20 pilot already exist:

~~~bash
git pull
python3 -m unittest discover -s tests -v

# Read-only validation of the existing CBAA K20 pilot against Greedy25 raw.
python3 -m experiments.compare_cbaa_budget \
  --cbaa-roots results/e8_cbaa_100r50t_pilot \
  --output-root results/e9_cbaa_budget_calibration_20only

# Independent new CBAA short-run sources, different iteration counts.
for K in 1 2 3 4 5 8 10; do
  python3 -m experiments.run_cbaa_baseline \
    --robots 100 --tasks 50 --seeds 3 \
    --loss-probabilities 0,0.30,0.50 \
    --max-iterations "$K" \
    --output-root "$(printf 'results/e8_cbaa_budget%s_100r50t_smoke' "$K")" || break
done

# Zero-loss-byte-only calibration across all options; output is distinct.
python3 -m experiments.compare_cbaa_budget \
  --robots 100 --tasks 50 --seeds 3 \
  --loss-probabilities 0,0.30,0.50 --tolerance 0.10 \
  --cbaa-roots \
    results/e8_cbaa_budget1_100r50t_smoke \
    results/e8_cbaa_budget2_100r50t_smoke \
    results/e8_cbaa_budget3_100r50t_smoke \
    results/e8_cbaa_budget4_100r50t_smoke \
    results/e8_cbaa_budget5_100r50t_smoke \
    results/e8_cbaa_budget8_100r50t_smoke \
    results/e8_cbaa_budget10_100r50t_smoke \
    results/e8_cbaa_100r50t_pilot \
  --output-root results/e9_cbaa_budget_calibration_3seed
~~~

Outputs: budget_options.csv (zero-loss traffic-selected K), budget_per_seed.csv, budget_curve.csv and source SHA256/Git-SHA manifest.json. Never overwrite archived source experiments or previous reports. If closest K fails tolerance, mark UNMATCHED and consider adding nearby integer K choices; never silently select best-performing K using packet-loss results.

Next E9B must enforce actual identical sender-byte caps BEFORE sending in original protocol owners, with honest incomplete outcomes, harmonized channel loss assumptions and fair timing before any claimed causal equal-budget result. Full provenance/diagnostics: docs/EXPERIMENT_PROTOCOL.md §19 and results/e9_cbaa_budget_calibration/README.md.

---

## E8 — Independent published CBAA single-assignment benchmark (first validation block)

**User-selected next phase:** compare our packet-loss-resilient decentralized voting against actual literature-based decentralized task assignment, starting with CBAA (Choi, Brunet & How, IEEE T-RO 2009, DOI [10.1109/TRO.2009.2022423](https://doi.org/10.1109/TRO.2009.2022423)). This is **NOT CBBA/ACBBA**, NOT our own 25% voting state machine, and does NOT silently fall back to reliable Commit.

New independent owner: democracy_mrta/cbaa.py implements CBAA Phase 1 agent-local bid selection, Phase 2 lossy neighbor maximum-consensus, release/rebid if outbid, winner-origin tie metadata, and **post-hoc observer-only** agreement/conflict auditing. Each robot can claim at most one task. A locally conflicted task is NOT automatically assigned by the observer. experiments/run_cbaa_baseline.py records per-seed results, full-agreement counts, physical consensus packets/drops/bytes and simulated timing, source Git SHA and Rady latency provenance, with seed-0 compressed broadcast/delivery/local-state evidence.

**Scientific limitations:** This first reference is fixed-iteration and synchronized on a complete network, with CBAA reward 1/(1+Euclidean cost) and origin metadata added for deterministic equal-bid handling. The original publication includes more general communication conditions; this is NOT yet a validated full asynchronous or independently distributed stopping implementation. CBAA consensus broadcasts each have ONE independently sampled loss stage, whereas our old E2 had separate initial Cost loss and Vote loss, with reliable Commit. Thus matched nominal Packet Loss probabilities are not identically controlled network workloads. This initial study is algorithm correctness/preflight and not yet a paper-ready statement that our algorithm is globally superior.

### Mac validation — run these BEFORE formal CBAA comparison

~~~bash
git pull
python3 -m unittest discover -s tests -v

# Small CBAA 10R/5T, 3 seeds × p={0, 0.30, 0.50}
python3 -m experiments.run_cbaa_baseline \
  --robots 10 --tasks 5 --seeds 3 \
  --loss-probabilities 0,0.30,0.50 --max-iterations 20 \
  --output-root results/e8_cbaa_single_assignment_smoke

# Only after suite/small smoke pass: 100R/50T, 3-seed CBAA pilot
python3 -m experiments.run_cbaa_baseline \
  --robots 100 --tasks 50 --seeds 3 \
  --loss-probabilities 0,0.30,0.50 --max-iterations 20 \
  --output-root results/e8_cbaa_100r50t_pilot
~~~

Expected small smoke: raw/cbaa_*.csv (9 rows), summary.csv (3 conditions), events/cbaa_audit_*.csv.gz (seed 0 only), and manifest.json. **If CBAA does not produce full task agreement at 0% loss, first inspect the true auction/consensus owner or iteration budget.** Do not insert a central rescue or an extra vote to make it pass. The pilot must pass before planning 100-seed 36-point formal CBAA curves.

Original 51% K1/K2/K3 and pure 25% K1 formal results remain immutable; all four existing communication protocols were already independently evaluated at 100R/50T with 100 seeds × 36 loss levels. CBAA is a distinct optimizer-level baseline, so compare both full assignment agreement and packet/message/bytes/latency under disclosed differences. The old Greedy-only communication study remains the *controlled optimizer-fixed* test of our communication protocol's contribution.

Exact source adaptation/diagnostic contracts: docs/EXPERIMENT_PROTOCOL.md §18; evidence ledger: results/e8_cbaa_single_assignment_smoke/README.md; mandatory internal continuity: docs/CHANGE_CONTINUITY.md.

---

## E5 — Bursty Packet Loss

Purpose: determine whether conclusions from independent Bernoulli loss survive correlated outages.

Network model:

- Gilbert-Elliott Good / Bad channel state
- empirical Wi-Fi latency for delivered packets

Primary outputs are identical to E2.

### E5 result record

Status: **PLANNED**

Raw: `results/e5_burst_loss/raw/`  
Summary: `results/e5_burst_loss/summary.csv`

---

## E6 — Message-Type Failure Localization

Purpose: identify which communication stage causes failure.

Conditions:

1. cost-message loss only;
2. vote-message loss only;
3. commit-message loss only;
4. all peer message types lossy.

Measure:

- success rate
- optimality gap
- communication time
- timeout rate
- retries
- safety failures

### E6 result record

Status: **PLANNED**

Raw: `results/e6_loss_source/raw/`  
Summary: `results/e6_loss_source/summary.csv`

---

## E7 — Published Wi-Fi Trace Replay

Purpose: final realism check without independently synthesizing latency and loss.

Replay measured application-level Wi-Fi observations from the published Rady et al. dataset, using matched trace segments across coordination methods.

This experiment answers whether conclusions from the controlled sweeps survive an externally measured real wireless trace.

### E7 result record

Status: **PLANNED**

Raw: `results/e7_trace_replay/raw/`  
Summary: `results/e7_trace_replay/summary.csv`

---

# 6. Statistical protocol

For each formal condition:

- 100 paired seeds unless otherwise stated;
- same cost scenario for every coordination method;
- same network trace / sampled latency stream for every compared method where causally possible;
- raw per-seed evidence is retained;
- report mean and 95% CI for approximately symmetric metrics;
- report median / IQR and tail percentiles for latency;
- additionally report P90 / P95 / P99 decision latency because wireless delay is tail-sensitive.

---

# 7. Result-storage policy

```text
results/
  e0_protocol_correctness/
  e1_latency/
  e2_packet_loss/
  e3_robot_scalability/
  e4_task_load/
  e5_burst_loss/
  e6_loss_source/
  e7_trace_replay/
```

Each formal result must preserve:

- git commit SHA
- scenario config
- network-profile identifier
- source dataset commit / provenance
- seed list
- raw per-message network events
- raw per-seed algorithm metrics
- summary CSV
- environment/runtime metadata

---

# 8. Implementation order

- [x] E0 — corrected formal run passed
- [x] E1 — formal trace-driven latency run complete
- [x] E2 — implementation complete; formal local run pending
- [ ] E3 — robot scalability
- [ ] E4 — task-load saturation
- [ ] E5 — burst loss
- [ ] E6 — message-type failure localization
- [ ] E7 — published trace replay

No later experiment begins until the current one has code, tests, raw output, summary output, README result record, and continuity entry.
