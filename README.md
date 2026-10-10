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
- `max_rounds` counts task-vote attempts. To finish 50 tasks at zero loss you need at least 50 rounds; the new default is 100.

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


---

## E3 — Robot Scalability

Purpose: measure how communication and decision cost scale with fleet size.

Primary sweep:

\[
N_R\in\{10,25,50,100,200\}.
\]

Primary network setting:

- empirical Wi-Fi latency
- Bernoulli packet loss = 30%

Hold task/robot load ratio fixed.

Primary outputs:

- communication time
- total decision latency
- messages / bytes
- success rate
- optimality gap

### E3 result record

Status: **PLANNED**

Raw: `results/e3_robot_scalability/raw/`  
Summary: `results/e3_robot_scalability/summary.csv`

---

## E4 — Task-Load / Saturation

Purpose: determine how close to full one-to-one assignment the protocol can operate before communication loss makes consensus difficult.

Primary fleet:

\[
N_R=100.
\]

Task sweep:

\[
N_T\in\{5,10,20,30,50,75,100\}.
\]

Primary network setting:

- empirical Wi-Fi latency
- Bernoulli packet loss = 30%

Primary outputs:

- success rate
- optimality gap
- quorum failures
- communication time
- retry count

### E4 result record

Status: **PLANNED**

Raw: `results/e4_task_load/raw/`  
Summary: `results/e4_task_load/summary.csv`

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
