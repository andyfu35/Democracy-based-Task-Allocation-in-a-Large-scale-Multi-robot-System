# Democracy-based Task Allocation in a Large-scale Multi-robot System

**Language:** **English** | [繁體中文](README.zh-TW.md)

**Research goal:** fully decentralized multi-robot task allocation under unreliable communication, with reproducible experiments on assignment correctness, packet loss, coordination time, and alternative algorithms. **Target venue:** IEEE Robotics and Automation Letters (RA-L).

> **Measurement boundary.** All reported communication times are **simulated protocol allocation/stop time**, not Python execution time or measurements from a 100-robot wireless deployment. Sender Bytes are attempted **application-layer** payload (including dropped packets). Rady provides real application-delay traces, but the shared **144 Mbps radio service is a hypothetical model**, not verified Wi-Fi MAC/PHY or ns-3. Voting pays reliable Commit; other algorithms use different native stopping conditions.

## Research map

There are **four experiment families**. Internal development IDs are kept out of this overview and documented separately in the [historical study index](docs/EXPERIMENT_LEGACY_INDEX.md).

| Family | Scientific question | Accepted evidence |
|---|---|---|
| **[A. Correctness](#a-correctness-and-distributed-agreement)** | Does decentralized assignment preserve a controlled optimal decision, and how costly is agreement? | Perfect-information and trace-bootstrap controlled Hungarian experiments |
| **[B. Packet loss](#b-packet-loss-resilience-and-communication-traffic)** | How does packet loss affect single-round versus iterative assignment success, Bytes, modeled stop time and assignment cost? | **Completed P2H sequential Figure 1 + P2G repeatable Figure 2**; 100 Seeds, 0–90% loss |
| **[C. Time](#c-coordination-time-and-deadline-design)** | How much delay comes from waiting and deadlines versus the radio model? | 30% Loss adaptive-deadline experiment and separate zero-loss timing control |
| **[D. Algorithms](#d-algorithm-comparison-and-task-capacity)** | How do native Voting, CBAA, Price Auction and CBBA compare under common capacity? | Five-series single-task comparison; separate capacity-four multi-task study |

### Implementation ownership

| Concern | Owning module |
|---|---|
| Task announcement and voting | [Task announcements](democracy_mrta/task_information.py), [Voting coordination](democracy_mrta/coordination.py), [multi-task Voting](democracy_mrta/voting_multitask.py) |
| Alternative allocators | [Original CBAA](democracy_mrta/cbaa.py) and [original CBBA](democracy_mrta/cbba_multitask.py) (current branch); [Price Auction (historical source branch)](https://github.com/andyfu35/Democracy-based-Task-Allocation-in-a-Large-scale-Multi-robot-System/blob/experiment/e9l-distributed-price-auction/democracy_mrta/price_auction.py) |
| Transport, loss, modeled time | [Network](democracy_mrta/network.py), [native multi-task packets](democracy_mrta/multitask_wire.py) |
| Scene / route / independent assessment | [Single-task scenes](democracy_mrta/scenario.py), [capacity-aware scenes](democracy_mrta/multitask_scenario.py), [route audit](democracy_mrta/multitask_evaluation.py) |
| Reproduction | [Experiment runners](experiments/), [canonical protocol](docs/EXPERIMENT_PROTOCOL.md), [change continuity](docs/CHANGE_CONTINUITY.md) |

**Architecture:** task announcement → each robot's local Cost / route utility → method-owned voting, bidding, auction or bundle consensus → externally audited assignment and physical message ledger. The observer **does not** inject a global solution or constitute a paid distributed termination protocol.

## A. Correctness and distributed agreement

**Scientific question:** holding the **Hungarian optimizer fixed**, does decentralized coordination preserve a correct assignment?

| Completed experiment | Formal condition | Verified finding |
|---|---|---|
| Perfect-information correctness | 5 robot/task scales × 100 Seeds, zero loss | **500/500 complete**, zero optimality gap and reference mismatches |
| Trace-sampled agreement overhead | 2,000 original records, 20 cells | At 100 robots/50 tasks, Democracy-Hungarian takes **796.2 ms** for global agreement and **201,400 B**; Leader-Hungarian **477.4 ms** and **41,600 B** |

The study establishes correctness when information is complete, but decentralized agreement adds communication. Its Hungarian-controlled results **must not be pooled** with Greedy Voting versus CBAA or CBBA optimization-quality claims.

**Original evidence:** [correctness raw](results/e0_protocol_correctness/raw/e0_corrected_20261009T141508Z.csv) / [summary](results/e0_protocol_correctness/summary.csv); [agreement raw](results/e1_latency/raw/e1_20261009T144026Z.csv) / [summary](results/e1_latency/summary.csv).

The earlier one-round lossy Hungarian Vote pilot did not receive full per-vote acceptance. It is **archived, not an outstanding requirement** for these two completed claims. [Historical study index](docs/EXPERIMENT_LEGACY_INDEX.md).

## B. Packet-loss resilience and communication traffic — TWO completed formal experiments (2026-10-19–20)

Both final figures are **completed and independently checked against the user's original uploaded archives**. Both use 100 robots, 100 tasks, robot capacity 1, the same scenario Seeds 0–99 and receiver packet-loss levels 0–90% in 10% steps. **The two figures test different protocols and have different cost denominators**; they are deliberately not presented as an equal-message-budget or real RF experiment. The earlier P2D/P2E one-shot figures and old P2G **one-batch** task-ordered Voting remain archived in the [canonical experiment history](docs/EXPERIMENT_PROTOCOL.md); they are **not** the final Figure 1.

### Figure 1 — Real sequential per-task Voting vs Baseline Centralized (P2H)

![Figure 1 — Task completion rate, cost, simulated stop time and attempted sender payload for true sequential Voting versus the task-ordered Centralized Greedy baseline](docs/figures/p2hi/formal/figure1_task_completion.svg)

**Actual native protocol:** Proposed performs **T0 Vote → Score → paid Commit → retire the winner → T1 Vote**, through T99, with newly computed task-local candidate choices, one physical Cost broadcast at the beginning, **at most one Vote attempt per task** and no retry of the same task. **Baseline Centralized** receives each remote Cost at most once, then sends a **separate paid assignment and executor Commit per task** before selecting the next task; this is one specified task-ordered Greedy centralized reference, **not all centralized algorithms**.

**Panel A is average *task completion rate*, NOT the percentage of seeds that completely finish all 100 tasks.** It is `100 × mean_task_coverage = 100 × (sum of native committed tasks)/(100 tasks × 100 seeds)`. An incomplete Seed with 50 accepted tasks still contributes 50%, not zero. Panel B is **complete-success-only** signed cost gap against the *same-seed full-information Task-ID-ordered Greedy* (no values invented where there are zero fully completed cases). C is modeled **native stop time** in seconds over **all** seeds; D is the sum of **attempted application sender payloads**, including frames dropped by receivers, in decimal kB.

| Packet loss | Proposed task completion | Baseline Centralized task completion | Proposed cost gap¹ | Proposed / Centralized modeled stop (s) | Proposed / Centralized sender (kB) |
|---|---:|---:|---:|---:|---:|
| 0% | **100.00%** | 100.00% | 0.00% | 16.47 / **7.48** | 249.25 / **89.23** |
| 30% | **100.00%** | 70.33% | +0.85% | 20.13 / 5.38 | 255.50 / 87.69 |
| 50% | **100.00%** | 50.06% | +4.77% | 21.47 / 4.01 | 257.64 / 86.64 |
| 90% | **100.00%** | 10.54% | +79.26% | 27.50 / 1.37 | 254.23 / 84.58 |

¹ Cost gap uses only complete native assignments. Baseline Centralized has **no complete-success Seeds at packet loss 10–90%**, so its complete-assignment cost gap is **undefined** at those levels; a blank point is not 0%. Strict 100/100-Seed success remains available in the raw and verified summary but is intentionally **not** Figure 1 A.

**What this result does and does not show.** In the current communication contract, Proposed completes all 100 tasks in all 100 Seeds even at 90% Cost/Vote drop. That strong result depends on locally available **self-votes**, **received plurality** (at least one vote suffices) and **assumed reliable Score/Commit**. It is not proof of 90%-loss tolerance for arbitrary wireless protocols. At PL0 the Proposed sequential protocol uses substantially **more time and sender Bytes** than this centralized baseline. At PL90 its allocation cost is **79.26% above its own full-information task-order Greedy reference**, despite full task completion. The baseline's short stop at high loss is mainly early incomplete termination, not fast successful completion.

**Evidence:** [20 exact plotted source groups](docs/figures/p2hi/formal/figure1_verified_summary.csv) · [P2H canonical protocol §58](docs/EXPERIMENT_PROTOCOL.md) · [P2H reproducibility instructions](docs/P2H_INTERACTIVE_FIGURE1.md) · [full independent study/communication-model record](docs/COMMUNICATION_MODEL_AND_P2HI_RESULTS_20261020.md). Formal P2H archive: **2,000 native cases / 20 groups**, original source Git `a54a13d454bb07cdfa9a20aa53753f9b6f61039d`, user ZIP SHA256 `171508bd596060352c7d8a7493c2724e293225b17c9a7af2390713770490373f`. The corrected published Figure 1 is a **derived replot from source-verifiable original results**; the original raw CSV and formal manifest have not been overwritten.

### Figure 2 — Repeatable allocation with a named Centralized Greedy baseline (P2G)

![Figure 2 — Original Proposed, CBAA, CBBA and Baseline Centralized methods across packet loss, with no explanatory footer](docs/figures/p2hi/formal/figure2_repeatable.svg)

The legend names are **Proposed, CBAA, CBBA, Baseline Centralized**. Proposed is the original **Multi-Round Global minimum-pair Greedy** protocol: a fresh Vote/Score/Commit decision on pending tasks after an earlier unfinished decision, **not retransmission of the original Cost**. CBAA and CBBA retain their **original native auction/consensus optimization**, not a secretly substituted Greedy optimizer. **Baseline Centralized** is specifically *Centralized Global Greedy with retransmission of only missing Cost* (up to 300 Cost attempts), followed by one final paid global assignment/Commit; it does **not** represent all centralized methods.

**Figure 2 A is strict full-100-task native success rate** (% of 100 Seeds), unlike Figure 1 A. B is complete-success-only signed cost increase relative to a **full-information Global minimum-pair Greedy reference** (different from Figure 1's task-order reference); C/D are all-Seed modeled native stop and physically attempted sender payload.

| PL90 · 100 paired Seeds | Proposed | CBAA | CBBA | Baseline Centralized |
|---|---:|---:|---:|---:|
| Native complete-assignment success | **100/100** | 100/100 | 0/100 | 100/100 |
| Complete-success-only cost gap vs Global Greedy | **+5.04%** | 0.00% | — | 0.00% |
| Modeled native stop, all Seeds (s) | **4.49** | 71.38 | 112.53 | 32.40 |
| Attempted sender application payload (kB) | **105.67** | 14,135.60 | 56,343.95 | 828.93 |

At PL90 Proposed is about **7.21× shorter** and sends **7.84× fewer application payload Bytes** than this *specific retransmitting centralized reference*, while yielding **+5.04%** full-info Global Greedy-relative cost. CBBA also retains **71.90% final conflict-free observed proposals** at PL90 despite 0/100 *full native completion*; that observed coverage is **not** a paid Commit. CBAA/CBBA native observer stopping and Proposed/centralized paid finalization are **not equivalent guarantees**; no universal winner or universal centralized disadvantage is claimed.

**Evidence:** [40 exact plotted source groups](docs/figures/p2hi/formal/figure2_verified_summary.csv) · [original SHA-pinned P2D/P2E/CBBA/CBAA aggregate](docs/figures/p2de/formal/verified_50point_summary.csv) · [P2G canonical §57](docs/EXPERIMENT_PROTOCOL.md) · [complete source/communication-model record](docs/COMMUNICATION_MODEL_AND_P2HI_RESULTS_20261020.md). P2G ZIP contains **3,000 fresh native cases**, of which the **1,000 centralized Cost-retry cases** are plotted here, while prior source-verified P2E Proposed/CBAA/CBBA supply the other 3,000 plotted method cases. The **2,000 archived P2G one-batch Figure 1 cases are not shown or counted as new P2H**. P2G original simulation source Git `7cab1b5f7979b2f45104c529de7e25015b4ff7e8`; user's formal ZIP SHA256 `2ba3615e54e91e96cbb606446bbe61cf531e9f23f9552e6a957a635d240fce2c`.

**Communication-model limit for both studies:** delays are sampled from Rady et al. (2024) industrial **ROS control-packet delay** measurements, with a separately hypothesized serialized **144 Mbps** radio/queue/backoff/ACK proxy and **synthetic independent Bernoulli Cost/Vote receiver loss**. TASK, Score and Commit are modeled reliable and paid; they are not tested as lossy RF packets. The Rady measurements are **not** measurements of 100 concurrently contending MRTA robots; this study does **not** run ns-3 and does not model collisions, OFDMA scheduling, actual MAC retransmissions or spatial RF fading. [See the full implemented model, parameter table, exact equations and paper-by-paper evidence](docs/COMMUNICATION_MODEL_AND_P2HI_RESULTS_20261020.md).

## C. Coordination time and deadline design

**Current shared timing model (applies to completed P2H/P2G experiments):** Rady et al. [2024](https://doi.org/10.1016/j.adhoc.2024.103418) measured real industrial ROS packet delays. We pin a **121-sample** medium-range LoS (60 m), 6GHz/160MHz, 120–181s steady-state subset (mean **33.593687 ms**, P95 **64.149866 ms**, P99 **159.419021 ms**, max **531.535123 ms**). The original `democracy_mrta/network.py` bootstraps those measurements and combines a separately **assumed 144Mbps**, one-serialized-medium/AP-hop airtime/backoff/ACK queue with independent seeded packet loss. The `~609.113ms` guarded Cost cutoff and shorter adaptive Vote cutoff are designed **inside this proxy**, not paper-measured Wi-Fi 6E deadlines. The network model is **not ns-3**, and real Rady measurements are **not** from 100 simultaneously contending robots. [Exact code-backed equations, assumptions, paper roles and validation limits](docs/COMMUNICATION_MODEL_AND_P2HI_RESULTS_20261020.md) · [citation BibTeX](docs/references/e9g_wifi_timing.bib).


**Historical-protocol figure:** the E9G/E9I deadline experiments here used earlier sequential-task Voting (or their stated original control), **not** the new P2-B batched Greedy Voting. Their source curves and data are preserved and must not be interpreted as the current batch-protocol latency across robot sizes. Updating these plots would require **new Voting-only runs at the original E9I sizes and seeds**, not rerunning unchanged native baselines.

**Scientific question:** does the communication delay come mostly from waiting for late Cost / Vote packets or from modeled shared-medium packet service?

### Adaptive deadlines under 30% packet loss

**Formal setting:** robots=tasks, 5–100 in steps of 5, 100 Seeds per size; both Cost and Vote drop probabilities are **30%**. Original baseline and revised deadline policy use matched settings.

![Fixed and adaptive deadline policy with 30 percent Cost and Vote loss](docs/figures/e9i_cost30/formal/fig02_time_vote30.svg)

At **100 robots/100 tasks**, the old fixed received-plurality deadline averaged **71.918 s** versus **20.132 s** with guarded one-time Cost and adaptive Vote deadlines (**72.01% lower modeled time**). Both compared arms completed 100/100 Seeds at that size; this **does not** imply 72% less sender payload or better optimality. [20-point original source](docs/figures/e9i_cost30/formal/formal_20point_plot_data.csv) · [source manifest](docs/figures/e9i_cost30/formal/formal_publication_manifest.json).

### Radio-model sensitivity — separate control

With 100 robots, zero application-layer loss, and a **fixed 609.113 ms task wait**, the Rady-delay-only model yielded **68.143 s**, versus **68.224 s** with the *assumed* 144 Mbps shared radio (**81.722 ms** more). This is a **zero-loss control**, not an empirical 100-robot Wi-Fi result or a second curve of the 30%-Loss deadline experiment. [Source](docs/figures/e9g_wifi/formal/scaling_20points_verified.csv) · [manifest](docs/figures/e9g_wifi/formal/publication_manifest.json).

## D. Algorithm comparison and task capacity

**Historical P1 benchmark, not current P2-B:** this archived P1 figure was executed under the earlier serialized Voting protocol, before batch Greedy. It also retains a five-method archival extension; **Voting Multi-task is not part of the current official four-method P2-B comparison**. All original P1 cases remain historical evidence. The current new batched Voting N=T=100 comparison is README B; other P1 sizes require separate matched Voting-only runs.

**Scientific question:** on common task-capacity and geometry, what are the trade-offs among original assignment algorithms?

### Five original algorithms — matched capacity-one, original 100 Seeds verified

**P1 formal original ZIP independently audited — zero data-integrity errors.** Same N=T=25,50,100, capacity **one**, packet Loss **30%** on each original method-native lossy packet, **100 paired Seeds per N**. All **five methods were newly run in the same source commit (1,500 original method cases)**, rather than mixing frozen historical three-algorithm averages with newer runs. An external observer records the first globally unique feasible assignment **after an originally incurred communication phase**; it neither adds messages nor stops or changes a robot. Native method-specific termination/guard is recorded **separately**.

![P1 verified: five native original algorithms, native stop, external first feasible, Bytes and same-success Hungarian cost](docs/figures/p1/formal/primary_matched_five_protocol_time_bytes_quality.svg)

| N=100; 30% Loss; 100 Seeds | Voting | Original CBAA | Price Auction | Voting Multi-task | Original CBBA |
|---|---:|---:|---:|---:|---:|
| **External first globally feasible (s)** | 20.132 | **7.898** | 119.400¹ | 101.919 | 11.539 |
| Original protocol modeled stop (s) | 20.132 | 13.647 | 135.828 | 101.919 | **12.368** |
| Attempted application sender (decimal kB) | **255.50** | 2,693.04 | 353.94 | 305.39 | 6,488.06 |
| **Native complete** | 100/100 | 100/100 | **78/100** | 100/100 | 100/100 |
| First feasible observable | 100/100 | 100/100 | 79/100 | 100/100 | 100/100 |
| Euclidean/Hungarian ratio² (lower better) | 1.3668 | 1.2348 | **1.1173** | 1.3673 | 1.2348 |

¹ Auction first-feasible time averages **79 observed Seeds**; 22 guard-limited failures remain in the **all-100-Seed native stop and sender Bytes**. Missing first-feasible timestamps are **not** imputed. ² Hungarian ratios are conditioned on the **same 78 Seeds where all five native methods completed**; this is explicitly different from the unconditional success counts.

**Key discovery — rankings reverse under a common observed event.** At 100 robots CBAA's first feasible assignment is **7.898 s**, ahead of CBBA **11.539 s in all 100 paired Seeds**, but CBBA reaches its **original native stop** sooner (**12.368 s** vs CBAA **13.647 s**). The paired mean CBAA−CBBA first-feasible difference is **−3.640 s** (10k paired-bootstrap 95% CI **[−3.939,−3.364]**). CBAA and CBBA produced **the exact same final assignment on all 300 N/Seed paired scenes**; CBBA transmitted **2.41×** the CBAA application Bytes at N100. Thus this observation isolates their packet and native stopping trade-off, not a change in CBAA/CBBA allocation quality.

**Completion and quality trade-off:** Price Auction has the lowest matched Hungarian cost ratio, but N100 native completion is just **78%**. Of the **1,500 complete original cases**, 1,476 natively completed and 1,478 ever formed a first externally feasible assignment. All **24 original native guard failures** belong to Auction (2 at N50, 22 at N100); two failed native endpoints already had an externally feasible snapshot, proving the two time/stop definitions cannot be substituted.

**Limits:** original Voting pays Score/Commit while CBAA, CBBA and Price Auction have native local/observer stopping; **first feasible is a read-only simulator event, not paid distributed termination or common knowledge**. Lossy native packet classes and objective formulations still differ, even with identical geometry/Seed/measurement. Timing combines Rady application-delay traces with a **hypothetical 144Mbps shared radio**, not measured 100-robot Wi-Fi latency.

**Formal evidence:** [Original ZIP independent audit/report](docs/P1_FORMAL_100SEED.md) · [original 15-row summary](docs/figures/p1/formal/original_summary_p1.csv) · [same-five-success quality](docs/figures/p1/formal/original_same_success_quality_p1.csv) · [machine audit](docs/figures/p1/formal/p1_independent_original_zip_audit.json) · [pre-registered implementation](docs/P1_MATCHED_FIVE_NATIVE.md). The previous original **20-size historical descriptive comparison** is retained separately in the [E9N source audit](docs/E9N_FORMAL_100SEED.md) and [archived source figure](docs/figures/e9n/formal/primary_five_method_time_bytes_success.svg), not overwritten or relabeled.

### Multi-task assignment — separate capacity-four cohort

**Formal cell:** 25 robots, 100 tasks, maximum **4 tasks per robot**, 30% loss, 100 paired Seeds; corrected full source ZIP, route and packet ledgers independently verified.

| Capacity-four metric | Voting Multi-task | Original CBBA |
|---|---:|---:|
| Assignment complete | **100/100** | **100/100** |
| Modeled allocation/stop | 63.023 s | **6.878 s** |
| Sender payload | **116.83 kB** | 1,006.87 kB |
| Total robot travel | 1,319.76 m | **1,209.48 m** |
| Longest robot route (makespan) | **134.55 s** | 148.64 s |

Total route length and longest route duration are **different** objectives; physical route makespan is not allocation time. This capacity-four cohort is deliberately **not** a point on the capacity-one plot. [Source-verified multi-task report](docs/E9M_CORRECTED_ORIGINAL_ZIP_AUDIT_100SEED.md).

## Remaining acceptance work — main A/B evidence accepted; next tests conditional

The previously identified **first-priority five-original-method fairness-of-external-measurement study is now COMPLETE and source-verified**. We will not automatically rerun historical pilots or open new optimization baselines. [Bounded closure plan](docs/RESEARCH_CLOSURE_PLAN.md).

| Conditional need | Next action |
|---|---|
| **Claim actual network / Wi-Fi communication time** | First validate the hypothetical 144Mbps radio service and packet timing against a packet-level or controlled multi-host setting. Not needed for claims explicitly limited to **modeled communication time**. |
| **Claim capacity-four multi-task scalability** | One prespecified additional C4 scale (e.g. 50R/200T) if needed; current 25R/100T original result is a single accepted C4 point, not a scaling curve. |
| **Incomplete exploratory controls** | Archive only; no required backfilling. |

## Reproducibility, archives and limitations

- [Historical internal study IDs, names and status](docs/EXPERIMENT_LEGACY_INDEX.md) · [Detailed historical results](docs/EXPERIMENT_RESULTS_ARCHIVE_20261012.md) · [prior README snapshot](docs/README_PRE_ABCD_20261013.md).
- [Cross-experiment audit](docs/EXPERIMENT_RESULTS_AUDIT_20261012.md) · [canonical protocol](docs/EXPERIMENT_PROTOCOL.md) · [change continuity](docs/CHANGE_CONTINUITY.md) · [bibliography](docs/references/e9g_wifi_timing.bib).
- [Matched five-original-method source audit](docs/P1_FORMAL_100SEED.md) · [previous original single-task source audit](docs/E9N_FORMAL_100SEED.md) · [original multi-task source audit](docs/E9M_CORRECTED_ORIGINAL_ZIP_AUDIT_100SEED.md). Original ZIPs are retained unchanged in the user's personal Library with documented SHA-256 identities.

**Comparison boundaries:** *method-native* modeled endpoint ≠ shared paid terminal guarantee; synthetic-timing loss study ≠ Rady radio-proxy experiment; capacity 1 ≠ capacity 4; aggregate historical source ≠ newly rerun paired original source. These limits are preserved in the reports. No actual 100-robot Wi-Fi deployment is claimed.
