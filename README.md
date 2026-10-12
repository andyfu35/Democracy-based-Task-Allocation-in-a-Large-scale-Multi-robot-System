# Democracy-based Task Allocation in a Large-scale Multi-robot System

**Research topic:** fully decentralized multi-robot task allocation under unreliable communication.  
**Target publication:** IEEE Robotics and Automation Letters (RA-L).

This repository investigates whether a leaderless, voting-based assignment protocol can achieve correct task decisions with low communication overhead despite wireless packet loss. The contribution under study is **distributed communication and agreement**, not a new global optimization algorithm.

The README presents the motivation, experimental assumptions, measured results, and evidence for each completed study. Detailed protocol definitions and implementation history are preserved in the [Canonical Experiment Protocol](docs/EXPERIMENT_PROTOCOL.md) and [Change Continuity Record](docs/CHANGE_CONTINUITY.md).

## 1. Research motivation and objectives

Multi-robot task allocation requires robots to agree on who should execute each task. Centralized coordination can concentrate decision-making and communication at a leader; decentralized coordination avoids a permanent decision center but introduces two costs: **reaching agreement** and **remaining operational when messages are lost**.

Our evaluation addresses three questions:

1. **Correctness:** with identical complete information, does decentralized voting reproduce the reference assignment without conflicting or duplicate commits?
2. **Communication cost:** how much simulated decision time and sender payload does distributed coordination require relative to centralized or consensus-based alternatives?
3. **Robustness:** how do actual task completion, local convergence knowledge, message volume, and safety-guard censoring change as independent packet loss increases?

We deliberately separate **fixed-optimizer Hungarian studies** from **Greedy Democracy vs. CBAA studies**. They use different decision mechanisms and must not be presented as if they shared an optimizer.

## 2. Protocols, benchmark settings, and evaluation metrics

### 2.1 Algorithms and experimental families

| Family | Methods | Local decision process | What the comparison isolates |
|---|---|---|---|
| **A. Fixed-optimizer coordination (E0–E2)** | Ideal full information, Leader–Hungarian, Full-view Hungarian, Democracy–Hungarian | The same deterministic Hungarian solver | Correctness, quorum overhead, and communication effects when the optimizer is controlled |
| **B. Decentralized communication (E9C–E9E)** | Greedy Democracy (ours) and original CBAA-family single-assignment auction/consensus | Greedy sequential assignment vs. CBAA local bids | Actual emitted payload, iterative information propagation, and packet-loss robustness; **not** optimizer-controlled assignment quality |

**Hungarian-based Democracy (Family A):** a task set is announced; each robot computes and broadcasts its local cost row, forms the visible cost matrix, computes a Hungarian proposal, and sends votes to candidate executors. The canonical fixed-optimizer study uses **strict-majority quorum** and a reliable commit announcement.

**Greedy Democracy (Family B):** each robot receives the same task set, computes and broadcasts its own cost row **once**, then votes directly for the lowest-cost eligible executor of the current task. A candidate must receive **more than 25% of all active voters' ballots** to make a qualified score announcement; among qualified candidates, the highest tally wins and a reliable commit retires that executor. **No fallback or forced assignment is permitted.** Uncommitted tasks can be retried within an explicit round limit.

**CBAA (Family B):** every robot bids for at most one task using its **own** local cost information, exchanges its current bid/winning-origin vector, updates maximum consensus and releases/rebids when outbid. **No unnecessary broadcast of every other robot's original position or state is included.** The tested synchronous complete-network reference is based on [Choi, Brunet & How (2009)](https://doi.org/10.1109/TRO.2009.2022423), with disclosed winner-origin metadata and an experimental local-receipt convergence certificate; this is not a complete implementation of distributed termination and final commit.

### 2.2 Common scenarios and controlled assumptions

| Parameter | Configuration and scope |
|---|---|
| Robot/task model | Static 2D positions, Euclidean cost; one robot can take at most one task |
| Formal repetitions | **100 paired seeds** per evaluated condition, unless specifically labelled exploratory |
| Main Greedy–CBAA scenario | **100 robots, 50 tasks**, 100 matched seeds |
| Packet loss | Independent Bernoulli delivery per receiver for original Cost/Vote or Bid/Winner messages |
| Shared task announcement | Guaranteed delivery in the E9C/E9E study, but **its sender payload is counted** |
| Reliable control messages | Democracy qualified Score and final Commit remain modelled reliable |
| E9E timing | Deterministic **1 ms synthetic message latency** with **10 ms** receive deadline; not measured radio delay |
| E9E stopping guards | Greedy Democracy: **300 task-vote attempts**; CBAA: **160 consensus iterations** |
| Sender payload | Counts **one transmitted payload per broadcast**, not one copy for each receiving robot |
| What is not simulated | 802.11 MAC/PHY contention, real airtime, retransmission ACK overhead, task travel/execution, and multi-task re-entry |

**Important distinction:** the trace-driven latency study **E1** uses measured Wi-Fi application-delay samples. The later **E9E** dense packet-loss study instead uses fixed synthetic latency. Their reported milliseconds must not be treated as the same measured channel.

### 2.3 Success and communication metrics

- **Actual full Commit (Democracy):** all requested tasks receive valid reliable assignment commits.
- **Local convergence certificate (CBAA):** all robots individually have sufficient **physically received peer evidence** to certify their locally matching winner vectors. The simulation ends when an optimistic shared scheduler observes all such flags; no real distributed stop-ACK traffic is paid.
- **External observer agreement (CBAA):** an auditor checks assignment agreement **after** a run. This is neither a local stopping certificate nor an actual distributed final Commit.
- **Sent payload:** all attempted application-layer sender Bytes, including dropped and unfinished transmissions; a dropped packet is still charged at its transmitter.
- **Guard-hit rate:** fraction of runs stopped by a finite simulation bound, not proof of a theoretical loss limit.
- **Hungarian accuracy (Family A):** optimality gap, oracle mismatch, full assignment success, and vote/commit safety errors.

The three end states—**Democracy Commit**, **CBAA local knowledge**, and **CBAA external agreement**—are reported separately throughout this report.

## 3. Completed experiments and results

### 3.1 E0 — Perfect-information correctness

**Why:** prove that communication and voting do not break an otherwise deterministic, globally optimal assignment when everyone sees the same complete cost matrix.

**Design:** zero packet loss and complete information, five robot/task scales, 100 seeds each; identical Hungarian proposal and strict-majority commit logic. The reference is the full-information Hungarian optimum.

| Robots | Tasks | Seeds | Mean optimality gap | Full assignment success | Oracle mismatches | Non-unanimous tasks | Safety failures |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 10 | 5 | 100 | 0.00% | 100% | 0 | 0 | 0 |
| 25 | 10 | 100 | 0.00% | 100% | 0 | 0 | 0 |
| 50 | 30 | 100 | 0.00% | 100% | 0 | 0 | 0 |
| 100 | 50 | 100 | 0.00% | 100% | 0 | 0 | 0 |
| 100 | 100 | 100 | 0.00% | 100% | 0 | 0 | 0 |

**Finding:** all **500 tested scenarios** achieved zero optimality gap, complete assignment, unanimous agreement, and no recorded voting/assignment safety failures. This verifies the Hungarian-based **Family A** correctness contract; it does **not** imply that later Greedy assignments globally minimize Hungarian cost.

Evidence: [E0 original summary](results/e0_protocol_correctness/summary.csv) · [E0 raw scenarios](results/e0_protocol_correctness/raw/e0_corrected_20261009T141508Z.csv).

### 3.2 E1 — Communication latency and overhead with measured Wi-Fi delays

**Why:** determine whether removing a leader changes actionable decision time, global agreement time, and communication volume even when packet delivery is loss-free.

**Design:** 100 paired seeds per scale, the same Hungarian optimizer and discrete-event network model for Leader–Hungarian, Full-view Hungarian, and Democracy–Hungarian. Delivered message latencies are bootstrapped from **Rady et al. (2024)**: industrial robotic ROS 2 measurements, **Wi-Fi 6E**, medium-range **60 m LoS**, source window **120–181 s**. The pinned **121** delay observations have mean **33.594 ms**, P95 **64.150 ms**, and maximum **531.535 ms**.

| Robots | Tasks | Method | Mean actionable decision (ms) | Mean global agreement (ms) | Mean logical SENDs | Mean sender payload (B) |
|---:|---:|---|---:|---:|---:|---:|
| 10 | 5 | Leader–Hungarian | 157.2 | 157.2 | 10 | 560 |
| 10 | 5 | Full-view Hungarian | 142.2 | 142.2 | 10 | 560 |
| 10 | 5 | Democracy–Hungarian | 168.4 | 247.6 | 60 | 2,140 |
| 50 | 30 | Leader–Hungarian | 370.8 | 370.8 | 50 | 12,800 |
| 50 | 30 | Full-view Hungarian | 336.1 | 336.1 | 50 | 12,800 |
| 50 | 30 | Democracy–Hungarian | 362.1 | 659.9 | 1,550 | 60,680 |
| 100 | 50 | Leader–Hungarian | 477.4 | 477.4 | 100 | 41,600 |
| 100 | 50 | Full-view Hungarian | 452.6 | 452.6 | 100 | 41,600 |
| 100 | 50 | Democracy–Hungarian | 477.7 | 796.2 | 5,100 | 201,400 |
| 100 | 100 | Leader–Hungarian | 477.4 | 477.4 | 100 | 81,600 |
| 100 | 100 | Full-view Hungarian | 452.6 | 452.6 | 100 | 81,600 |
| 100 | 100 | Democracy–Hungarian | 478.3 | 918.6 | 10,100 | 401,200 |

**Finding:** with 100 robots and 50 tasks, Democracy–Hungarian reached an actionable decision in **477.7 ms**, near Leader–Hungarian's **477.4 ms**. Its **796.2 ms** global agreement time and **201,400 B** sender payload were much higher because votes and final commits must also propagate. At 100 robots/100 tasks, the corresponding Democracy values were **478.3 ms** actionable, **918.6 ms** global, and **401,200 B** sent.

The experiment demonstrates a **cost of decentralized agreement**, not an unqualified latency win. These are trace-driven *application-delay simulations*, with no new shared-medium congestion induced by fleet size.

Evidence: [E1 original summary](results/e1_latency/summary.csv) · [E1 raw scenarios](results/e1_latency/raw/e1_20261009T144026Z.csv).

### 3.3 E2 — One-round Hungarian robustness under lossy Cost/Vote delivery

**Why:** distinguish how much packet loss prevents **task completion** versus merely reduces the quality of a still-committed assignment.

**Design:** same fixed Hungarian optimizer and Rady-derived latency samples as E1; a **single, non-retried allocation round**; independent receiver-level Cost packet drops and separately lossy Vote unicasts; the original electorate remains the quorum denominator. Commit announcements are reliably modelled.

At the **100-robot / 50-task, 30% Cost loss + 30% Vote loss** condition, the completed 100-seed correctness-instrumented rerun reported:

| Metric | Recorded value |
|---|---:|
| Mean visible robot cost rows | **70.285 / 100** |
| Mean task commit rate | **15.22%** |
| Correct executor rate (all requested tasks) | **15.06%** |
| Correct executor rate among committed tasks | **98.706%** |

**Interpretation:** the distinction between low task availability and high correctness **conditional on a successful Commit** is important. However, this specific Hungarian E2 result remains **provisional until the vote-level forensic ledger audit is accepted**. It is not a validated substitute for the completed E9E Greedy/CBAA sweep.

Definitions, audit provenance, and the complete one-round benchmark: [E2 evidence notes](results/e2_packet_loss/README.md) · [Experiment Protocol](docs/EXPERIMENT_PROTOCOL.md).

### 3.4 E9C — Message-size and zero-loss communication accounting validation

**Why:** ensure a comparison counts the information actually emitted on the network, instead of charging CBAA for unnecessary peer robot-state broadcasts or multiplying one broadcast by all receivers.

**Design:** 100 robots, 50 tasks, 100 paired seeds, no loss. Both methods receive the **same physically encoded task announcement**. Greedy sends its own Cost row once, followed by Vote/qualified Score/Commit; original-family CBAA sends its own Bid/Winner vector in each consensus iteration. This was a fixed-iteration **validation/control**, whereas the later E9E uses iterative local evidence without selecting a particular K in advance.

| Component | Physical sender payload in the 100R / 50T setup |
|---|---:|
| Shared 50-task announcement (2 binary packets) | **1,632 B** |
| One original Greedy Cost packet per robot (100 total) | **41,600 B** |
| CBAA bid/winner-vector dissemination in **one** complete 100-robot consensus iteration | **61,600 B** |
| Additional global peer-position transfer required by original CBAA | **0 B** |

**Finding:** both original methods can be evaluated without hidden peer-state information. The **zero-loss** Greedy full 50-task Commit cost was **165,432 B per seed**, while CBAA's final traffic depends on how many real consensus exchanges are executed. Counting **only** one CBAA iteration without ensuring full agreement is not a meaningful completed-outcome comparison. The dynamic-stop E9E data below supersedes fixed-iteration settings as the primary loss/traffic result.

Evidence: [Original-only E9C CI verification](https://github.com/andyfu35/Democracy-based-Task-Allocation-in-a-Large-scale-Multi-robot-System/actions/runs/38112992924) · [Experiment Protocol](docs/EXPERIMENT_PROTOCOL.md).

### 3.5 E9E — Dense packet-loss robustness and actual sender payload (**primary cross-algorithm result**)

**Why:** identify the loss region where Democracy stops completing all tasks, determine whether CBAA preserves assignment agreement at high loss, and quantify the **additional attempted sender payload** required by continuing consensus transmissions.

**Design:** 100 robots, 50 tasks, 100 paired seeds and **52 measured loss levels** (5%-step global grid plus 1%-step resolution across **40–65%** and **85–99%**). This produces **10,400 original protocol executions**. Loss affects **Democracy Cost and Vote** and **CBAA Bid/Winner** independently per receiver. No extra CBAA robot-position exchange and no manually fixed K tuning is used. Original CBAA auction/consensus runs until local-receipt certification or its reported safety guard.

**Evidence status:** complete original per-seed, summary, manifest, and **all six source-generated SVGs independently SHA256-verified**. The exact original Mac SVGs are committed, not replotted from rounded terminal logs.

#### Experiment 1 — Complete protocol outcome versus packet loss

![Verified 52-point Democracy Commit versus CBAA local-receipt certification](docs/figures/e9e_dense/formal/e9d_full_success.svg)

Democracy retained **100/100 full Commit** at sampled 50% loss, dropped to **91/100 at 52%**, **65/100 at 53%**, **14/100 at 54%**, and **0/100 at 55%**. Its first **non-perfect** sample was **48% (99/100)**, so discrete sample success is not strictly monotonic.

CBAA retained **100/100 locally certified outcomes** through **91%** loss, before declining to **97/100 at 92%**, **87/100 at 93%**, **48/100 at 94%**, and **2/100 at 95%**. These are **measured, guard-limited outcomes**, not mathematical maximum loss tolerances.

![Verified close-up of Democracy's 40–65% transition with 1% measured spacing](docs/figures/e9e_dense/formal/e9d_democracy_transition.svg)

#### Experiment 2 — Communication volume and the performance trade-off

The table below is reproduced from the original **104-row verified summary CSV**, not from console output. **kB = 1,000 sender application Bytes**; incomplete and safety-guard-limited runs remain in the mean.

| Loss | Democracy full Commit | CBAA locally certified | CBAA external full agreement | Democracy mean sender (kB) | CBAA mean sender (kB) | CBAA guard hits |
|---:|---:|---:|---:|---:|---:|---:|
| 0% | 100/100 | 100/100 | 100/100 | 165.4 | 269.0 | 0/100 |
| 10% | 100/100 | 100/100 | 100/100 | 165.2 | 557.9 | 0/100 |
| 30% | 100/100 | 100/100 | 100/100 | 164.8 | 838.2 | 0/100 |
| 40% | 100/100 | 100/100 | 100/100 | 166.2 | 1,015.6 | 0/100 |
| 45% | 100/100 | 100/100 | 100/100 | 185.0 | 1,109.2 | 0/100 |
| 48% | 99/100 | 100/100 | 100/100 | 237.9 | 1,169.0 | 0/100 |
| 50% | 100/100 | 100/100 | 100/100 | 323.1 | 1,217.6 | 0/100 |
| 51% | 99/100 | 100/100 | 100/100 | 389.1 | 1,249.0 | 0/100 |
| 52% | 91/100 | 100/100 | 100/100 | 494.4 | 1,297.1 | 0/100 |
| 53% | 65/100 | 100/100 | 100/100 | 618.5 | 1,328.5 | 0/100 |
| 54% | 14/100 | 100/100 | 100/100 | 731.6 | 1,368.5 | 0/100 |
| 55% | 0/100 | 100/100 | 100/100 | 796.6 | 1,401.8 | 0/100 |
| 60% | 0/100 | 100/100 | 100/100 | 957.8 | 1,588.4 | 0/100 |
| 80% | 0/100 | 100/100 | 100/100 | 955.1 | 3,106.3 | 0/100 |
| 90% | 0/100 | 100/100 | 100/100 | 907.4 | 6,118.5 | 0/100 |
| 91% | 0/100 | 100/100 | 100/100 | 897.1 | 6,859.6 | 0/100 |
| 92% | 0/100 | 97/100 | 100/100 | 884.5 | 7,706.6 | 3/100 |
| 93% | 0/100 | 87/100 | 100/100 | 867.8 | 8,779.0 | 13/100 |
| 94% | 0/100 | 48/100 | 100/100 | 845.3 | 9,578.0 | 52/100 |
| 95% | 0/100 | 2/100 | 100/100 | 815.3 | 9,854.6 | 98/100 |
| 96% | 0/100 | 0/100 | 100/100 | 770.2 | 9,857.6 | 100/100 |
| 99% | 0/100 | 0/100 | 100/100 | 399.0 | 9,857.6 | 100/100 |

At **30% packet loss**, both methods achieved **100/100** of their respective full outcomes, while Democracy used **164,750.08 B** and CBAA used **838,160 B** per seed on average. This is **80.34% fewer modeled sender application Bytes** for Democracy **in that particular comparison condition**. It is not evidence of less communication for a *completed* task set at 55%+ loss, where Democracy frequently fails to finish.

![Verified emitted application Bytes against packet loss, logarithmic MB scale](docs/figures/e9e_dense/formal/e9d_sender_payload.svg)

#### Experiment 3 — CBAA task agreement is different from knowing when to stop

The **external observer** found complete CBAA assignment agreement in **100/100 seeds at every tested loss probability through 99%**. In contrast, each robot having enough **received peer evidence** to certify global agreement became increasingly difficult; at 96–99% none of the 100 trials satisfied the full local-certificate condition within 160 iterations.

This is a **stopping-knowledge and resource-limit finding**, not evidence that CBAA necessarily lost the 50-task assignment. The current CBAA model's optimistic simulator-wide halt does **not** charge physical distributed stop-ACK/Commit communication.

![Verified CBAA external observer agreement versus local certification](docs/figures/e9e_dense/formal/e9d_cbaa_agreement_vs_stop.svg)

![Verified 85–99% high-loss close-up of CBAA agreement versus stopping](docs/figures/e9e_dense/formal/e9d_cbaa_high_loss_zoom.svg)

#### Experiment 4 — Which apparent failures are safety-guard censored?

![Verified guard-hit rates: bounded execution is not a theoretical loss threshold](docs/figures/e9e_dense/formal/e9d_guard_censoring.svg)

Democracy was allowed up to **300** task-voting attempts; CBAA up to **160** consensus iterations. Exceeding either guard does **not** prove that an algorithm could never finish with more time or transmissions. Comparisons of payload must include these stopped runs rather than selectively discarding them.

**Verified E9E evidence:** [Original 104-row result summary](docs/figures/e9e_dense/formal/summary_by_loss.csv) · [Experiment and figure SHA256 manifest](docs/figures/e9e_dense/formal/publication_manifest.json).


### 3.6 E9G — Evidence-backed Wi-Fi timing, contention and task-allocation scaling (**design; no ns-3 results yet**)

**Research objective.** Explain the relationship between actual sender application Bytes, individual SEND operations, shared 802.11 airtime, congestion, and end-to-end completion of the original Greedy Voting task allocation. The first priority is a **Voting-only** R=T=N scaling study (N=5,10,...,100; 100 paired seeds; 0% application loss; one Cost copy), **not** an inter-algorithm win/loss contest. Earlier Rady-profile sampling estimated near-linear allocation time, but the conservative 531.535123 ms **per task-voting epoch** timeout dominates the estimate (~88% at N=100). It is **not** a measurement of real Wi-Fi 6E 100-robot airtime.

#### Published sources: explicit attribution, purpose and scientific boundary

Each numbered study has a stable BibTeX key in [E9G literature bibliography](docs/references/e9g_wifi_timing.bib). **Citing a paper does not imply that its radio traces are already implemented or that its authors tested our 100-robot MRTA scenario.**

| Source (cite in paper) | What it establishes / how E9G will use it | What it does **not** establish |
|---|---|---|
| **[Rady et al. (2024), *Ad Hoc Networks* 156, 103418](https://doi.org/10.1016/j.adhoc.2024.103418)** \`Rady2024IndustrialWifi6\` | Real industrial robotic Wi-Fi/ROS 2 application-layer delay and wireless performance; use the existing **pinned 60 m LoS, 6 GHz, 160 MHz** 121-sample empirical profile (33.594 ms mean; 531.535 ms max) as an external calibration/holdout target. [Exact pinned dataset and checksum](https://github.com/minarady1/wifi_for_industrial_robotics/tree/1996e5bb69b9ba4d25060cbc14838ddedf65cff2). | No 100-node simultaneous 802.11ax traffic/packet-size-specific delay distribution; ROS 2 delay already contains network/stack contributions and **must not be added wholesale to simulated PHY/MAC times**. |
| **[Liu & Choi (2023), *Proc. ACM Meas. Anal. Comput. Syst.*](https://doi.org/10.1145/3579451)** \`LiuChoi2023Wifi6Measurement\` | Empirical commercial Wi-Fi 6 device throughput, latency and OFDMA/aggregation behavior; use its [measurement artifacts](https://github.com/liux4189/wifi-ax-measurement) as a **separate small-population validation dataset once artifacts/versions are independently verified**. | Experimental users and equipment do not represent the extrapolated 100-robot industrial configuration. No calibrated parameters have been copied from this paper yet. |
| **[Montgomery & Candell (2024), NIST IR 8506](https://doi.org/10.6028/NIST.IR.8506)** \`MontgomeryCandell2024OfdmaIndustrial\` | Industrial uplink OFDMA activation can depend on offered load, AP and client implementation; compare EDCA baseline with **explicitly enabled** OFDMA as sensitivity. | **No universal “2 devices” or packet-rate threshold** can be imposed on all access points. |
| **[Bianchi (2000), *IEEE JSAC* 18(3)](https://doi.org/10.1109/49.840210)** \`Bianchi2000Dcf\` | DCF contention/backoff/collision foundational analytical model; reason about shared-medium scaling and why SEND count differs from elapsed time. | Traditional saturated DCF analysis alone does not model 802.11ax OFDMA, an actual AP, ROS/DDS, or the unsaturated MRTA burst pattern. |
| **[Riley & Henderson (2010), “The ns-3 Network Simulator”](https://doi.org/10.1007/978-3-642-12331-3_2)** \`RileyHenderson2010Ns3\` and [ns-3 official Wi-Fi model documentation](https://www.nsnam.org/docs/models/html/wifi-design.html) \`Ns3WifiModelDocumentation\` | Proposed trace-producing packet-level PHY/MAC/EDCA simulation backend; record ns-3 version, wifi model, MCS, AP/client roles, addresses, channel, transport, traffic scheduling, ACK/retries, random seeds and any OFDMA scheduler. | **Not installed or run by the current Python Voting simulator.** Version-specific features must be checked; bibliographic references are **not** a simulation result. |
| **[Choi, Brunet & How (2009), *IEEE T-RO* 25(4)](https://doi.org/10.1109/TRO.2009.2022423)** \`ChoiBrunetHow2009Auctions\` | Background citation for original consensus-based auctions in task allocation and separation of agreement from physical network cost. | Not a Wi-Fi timing calibration source; E9G currently runs **only our original Voting**. |

#### Proposed two-layer experiment and source-of-truth contract

**Layer A (existing, reproducible):** 0%-loss R=T scaling source events from the original \`coordination\` and \`task_information\` owners. Task / Cost / Vote / Score / Commit sender payloads are recorded once for physical broadcasts, never multiplied by nominal receivers. The previously uploaded Voting-only 100-seed scaling ZIP (20 groups, 2,000 runs) exists as user-provided exploratory analysis; its processed files are **not silently represented as formally committed E9G/ns-3 output**.

**Layer B (not yet implemented):** one external ns-3 run per seed/network configuration, using actual application SEND release times, sizes, sender/receiver roles, and packet types. E9G must export/import a **versioned per-packet network trace**, with a deterministic mapping from original application SEND to channel transmissions/deliveries. Preserve broadcast-vs-unicast semantics, AP uplink/downlink cost and lack of normal multicast ACK, and MAC ACK/retransmission only when corresponding to configured Wi-Fi network frames. Accounting must report separately (a) application sender Bytes/SENDs, (b) over-the-air transmissions/Bytes/airtime, (c) MAC backoff/queues/retries, (d) ROS/application residual delays, (e) original fixed protocol timeout/retries, and (f) real full-Commit endpoint. **Offline rescheduling of all already-generated packets is not enough:** if network arrivals affect vote eligibility/deadlines, the Voting owner must receive those actual arrivals during the original execution, rather than retrospectively rewriting a successful allocation. No second voting state machine or uncharged global clock.

For per-packet delay, write \`T_delivered = T_queue + T_backoff + T_PHY/MAC_service + T_stack_residual\`, where \`T_stack_residual\` can only be fitted from a **non-overlapping** measurement component. Do not add 33.594 ms to every ns-3 packet without double-count validation. Transport/application reliability assumptions (original reliable TASK, qualified Score, Commit vs lossy Cost and Vote), timeout decisions, packet loss, and censored runs must be disclosed. Use external measurements only within their supported equipment/traffic range; treat N=100 as **extrapolation**, not measurement.

**Acceptance gates before claiming results:** (1) source checksum/provenance and simulator version; (2) zero-loss original Voting/Cost/Score/Commit parity at N=5; (3) each SEND/delivery and PHY/MAC accounting auditable; (4) B=0/minimum and no-queue controls; (5) small-scale validation against published multi-user performance before N=100; (6) 100 seeds and immutable raw CSV + summary + manifest SHA256; (7) README plots *only after* verified executed runs. The original application Bytes at 0%-loss 1:1 scale follow \`B(N)=24N^2+92N+16 ceil(N/37)\` for the measured original one-attempt protocol path; that does **not** give a measured Wi-Fi airtime complexity. A log-log slope from 5..100 is an empirical finite-range exponent, not a theoretical Big-O proof.

**Current status:** source audit and paper-to-model traceability **documented**; citation database **committed**. **No ns-3 installation, channel simulator integration, calibration fit or 100-seed shared-channel results is claimed**. This section is a research methodology and evidence status, not invented new experiment output.

## 4. Synthesis and conclusions

### 4.1 What the completed studies establish

1. **Correctness under complete information (E0):** the fixed-Hungarian decentralized voting protocol matched the assignment oracle in 500/500 tests with zero safety failures.
2. **Cost of decentralized quorum (E1):** votes and commits add substantial transmission volume and final-agreement latency, even when actionable decision latency is near the leader baseline.
3. **Communication efficiency in the sampled robust regime (E9E):** at **30% loss**, Democracy completed all 50 tasks in 100/100 scenarios using **80.34% fewer modeled sender application Bytes** than the CBAA reference under its own fully certified local outcome.
4. **High-loss resilience and termination knowledge (E9E):** the CBAA reference retained full *external observer assignment agreement* even at 99% sampled loss, while its **per-robot stopping certificate** reached 0/100 by 96% under the 160-iteration limit.
5. **Bounded robustness (E9E):** Democracy's complete Commit success rapidly declined across the densely sampled **52–55%** region; CBAA's observed local-certification success declined across **92–96%**.

### 4.2 Interpretation boundaries

The two algorithm families are **not interchangeable**: E0–E2 hold Hungarian fixed, whereas E9C/E9E compare Greedy voting with CBAA bidding. Their optimum-quality, success and network budgets cannot be equated without additional controls.

In E9E, **Democracy actual Commit**, **CBAA observer agreement**, and **CBAA locally certified termination** are distinct endpoints. Task announcement and Democracy qualified-score/Commit use reliability assumptions; CBAA's shared simulation stop omits actual termination-handshake traffic. This should be treated as a **conservative scientific disclosure**, not as proof of one protocol's universal superiority.

The current experiments report **simulated, attempted application-layer sender payload**, not measured 802.11 throughput, congestion, MAC/PHY/ACK overhead, or robot energy. Per-receiver Bernoulli loss does not reproduce correlated bursts, asymmetric topology, or real on-robot packet traces. A finite set of 100 seeds and a hard stopping guard is not a theoretical loss threshold.

### 4.3 Unfinished or separately tracked evaluations

| Research question | Current evidence status |
|---|---|
| E2 Hungarian per-ballot forensic correctness | 100-seed aggregate rerun recorded; **vote-level audit remains pending** |
| E3/E4 robot scaling and task-load saturation | Benchmark design and historical local runs described; **no independently verified formal scaling summary is published in this README** |
| Greedy 51%-majority vs pure 25% plurality, and fixed Vote-copy sensitivity | Historical experimental variants exist; not merged into E9E's two-algorithm benchmark without a matched original-data acceptance record |
| E5/E6/E7 burst loss, message-type fault attribution and external Wi-Fi trace replay | **Not yet a verified formal result here** |
| Equal on-wire byte budgets, paid CBAA distributed termination and final Commit, real radio measurements | Necessary future validation; not included in the reported 80.34% figure |

## 5. Evidence and references

| Evidence | Original source |
|---|---|
| E0: zero-loss Hungarian correctness | [E0 100-seed summary](results/e0_protocol_correctness/summary.csv) |
| E1: empirical Wi-Fi latency study | [E1 100-seed summary](results/e1_latency/summary.csv) |
| E2: one-round loss study and audit boundary | [E2 benchmark evidence notes](results/e2_packet_loss/README.md) |
| E9C: original-only CBAA sender-byte validation | [100-seed original-method CI record](https://github.com/andyfu35/Democracy-based-Task-Allocation-in-a-Large-scale-Multi-robot-System/actions/runs/38112992924) |
| E9E: 52-loss-level formal results | [Verified original summary](docs/figures/e9e_dense/formal/summary_by_loss.csv) |
| E9E: six original SVGs and exact evidence hashes | [Formal figures and publication manifest](docs/figures/e9e_dense/formal/publication_manifest.json) |
| Experimental definitions, assumptions, ownership and limitations | [Canonical experiment protocol](docs/EXPERIMENT_PROTOCOL.md) |

**E9E source experiment SHA:** `2808fa12fcd89aa8c2251e7e6438312a95a9df8f`  
**Original per-seed raw SHA256:** `e2337a157b96593d441c143b19d5b2b9b1c64604b4bc0a651da1e566c060c727`  
**Original summary SHA256:** `3408ccd1978ca66d58ff4dd195d3b31b8e2805c798e1adfa872d5d45ea6706db`

The original **10,400-row per-seed raw CSV** was independently verified from the user-supplied experiment archive; the repository publishes the **original 104-row summary and six exact original SVGs**. The full raw is **not** falsely represented as committed here.

**Literature:** [Rady et al., *Ad Hoc Networks* 156 (2024), 103418](https://doi.org/10.1016/j.adhoc.2024.103418) (industrial Wi-Fi application delay); [Choi, Brunet & How, *IEEE Transactions on Robotics* 25(4), 2009](https://doi.org/10.1109/TRO.2009.2022423) (consensus-based decentralized auctions).
