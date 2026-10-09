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

> How much decision time does each coordination architecture spend on real wireless communication when there is no packet loss?

Conditions:

- packet loss = 0
- fixed Hungarian optimizer
- empirical ROS 2 Wi-Fi latency sampled from the Rady et al. dataset
- paired scenarios and paired latency traces

Compare:

- Ideal Full Information
- Leader-Hungarian
- Flooding/Full-View Hungarian
- Democracy-Hungarian

Primary outputs:

- \(T_{communication}\)
- total decision latency
- cost-exchange time
- quorum time
- commit time
- local compute time
- message count
- bytes

This is the experiment that quantifies the time spent on communication.

### E1 result record

Status: **BROADCAST-CORRECTED IMPLEMENTATION — AWAITING FORMAL RERUN**

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

The trace has a substantial latency tail; E1 therefore uses the full empirical sample distribution rather than a constant or Gaussian delay.

Run:

```bash
git pull
python3 -m unittest discover -s tests -v
python3 -m scripts.prepare_rady_wifi_dataset
python3 -m experiments.run_e1 --seeds 100
```

Raw: `results/e1_latency/raw/`  
Audit event logs: `results/e1_latency/events/*.csv.gz`  
Summary: `results/e1_latency/summary.csv`

Per-message event logs are stored for designated audit seeds (default seed 0) to avoid multi-million-row duplication; all 100 seeds retain per-run aggregate metrics.

The first local E1 run on 2026-10-09 is retained only as a **diagnostic pilot** because that implementation incorrectly expanded each cost/commit announcement into \(N-1\) unicasts. It must not be used as a paper result.

The corrected implementation now counts:

- one cost-row broadcast per robot;
- direct unicast task votes;
- one commit broadcast per committed task;
- one leader assignment broadcast for Leader-Hungarian.

**Paper result:** pending corrected local rerun.

---

## E2 — Bernoulli Packet-Loss Robustness

Purpose: test graceful degradation under independently lost messages.

Loss sweep:

\[
p_{loss}\in\{0,0.1,0.3,0.5,0.7,0.9\}.
\]

Every delivered message still receives an empirical Wi-Fi latency sample.

Compare the same coordination methods as E1.

Primary outputs:

- assignment success
- optimality gap
- decision latency
- retries
- timeout rate
- messages / bytes

### E2 result record

Status: **PLANNED**

Raw: `results/e2_packet_loss/raw/`  
Summary: `results/e2_packet_loss/summary.csv`

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
- [x] E1 — implementation complete; formal local run pending
- [ ] E2 — Bernoulli packet loss
- [ ] E3 — robot scalability
- [ ] E4 — task-load saturation
- [ ] E5 — burst loss
- [ ] E6 — message-type failure localization
- [ ] E7 — published trace replay

No later experiment begins until the current one has code, tests, raw output, summary output, README result record, and continuity entry.
