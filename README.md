# Democracy-based Task Allocation in a Large-scale Multi-robot System

**Language:** **English** | [繁體中文](README.zh-TW.md)

**Research goal:** fully decentralized multi-robot task allocation under unreliable communication, with reproducible experiments on assignment correctness, packet loss, coordination time, and alternative algorithms. **Target venue:** IEEE Robotics and Automation Letters (RA-L).

> **Measurement boundary.** All reported communication times are **simulated protocol allocation/stop time**, not Python execution time or measurements from a 100-robot wireless deployment. Sender Bytes are attempted **application-layer** payload (including dropped packets). Rady provides real application-delay traces, but the shared **144 Mbps radio service is a hypothetical model**, not verified Wi-Fi MAC/PHY or ns-3. Voting pays reliable Commit; other algorithms use different native stopping conditions.

## Research map

There are **four experiment families**. Internal development IDs are kept out of this overview and documented separately in the [historical study index](docs/EXPERIMENT_LEGACY_INDEX.md).

| Family | Scientific question | Accepted evidence |
|---|---|---|
| **[A. Correctness](#a-correctness-and-distributed-agreement)** | Does decentralized assignment preserve a controlled optimal decision, and how costly is agreement? | Perfect-information and trace-bootstrap controlled Hungarian experiments |
| **[B. Packet loss](#b-packet-loss-resilience-and-communication-traffic)** | How does packet loss affect single-round versus iterative assignment success, Bytes, modeled stop time and assignment cost? | P2D/P2E two four-panel 100-seed comparisons, 0–90% loss |
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

### Archived one-batch Voting comparison (non-sequential)

![Archived one-batch task-ordered Voting versus single-upload Centralized Greedy, with mean committed task coverage, full-success-only cost, modeled stop time and attempted sender payload](docs/figures/p2g/formal/figureA_one_batch_task_coverage.svg)

**Protocol distinction:** This is the audited **P2G one-batch**, not P2H sequential Voting. Each robot first greedily plans the task order T0–T99 using its locally received Cost, then broadcasts **one batch Vote** containing its entire proposed allocation. The original Score/Commit resolution processes that batch; **there is no per-task Vote–Commit–retire–replan cycle**. The Centralized baseline receives remote Cost once and makes a corresponding one-batch task-ordered assignment. Both methods use the same 100 robots, 100 tasks, capacity one, 100 paired seeds per loss level, and full-information **task-ordered Greedy** cost reference as P2H Figure 1. Different native packet timing and assignment/Commit patterns remain method-specific.

Panel A shows **average committed task coverage across all seeds**, reconstructed from the independently audited P2G summary rather than binary all-task success. At 90% loss, one-batch Proposed covers **16.12%** versus **10.54%** for this Centralized baseline; neither has any 100/100 complete seeds. By contrast, the newer sequential P2H Figure 1 in Section B has **100%** committed coverage for Proposed at the same loss, but with far greater communications and a distinct execution protocol. This is a **descriptive cross-experiment comparison**, not an isolated causal estimate of sequential voting: both the Vote schedule and communication/Commit timing differ. For incomplete seeds the full-success-only cost is undefined, not zero; failed runs' shorter modeled stop is not faster successful completion. Sender application Bytes count attempted packets including receiver losses. [Original P2G audit](docs/P2G_TWO_FIGURES.md) · [20 audited figure cells](docs/figures/p2g/formal/verified_figureA_20point_summary.csv).

## B. Packet-loss resilience and communication traffic

**Accepted main experiment direction (2026-10-20):** Figure 1 uses TRUE sequential one-task-at-a-time Voting versus a specific task-ordered Centralized Greedy baseline, each with one initial Cost exchange and no Cost retransmissions. Figure 2 preserves the independent repeatable coordination comparison: Proposed, CBAA, CBBA, Baseline Centralized. All plotted studies use 100 robots, 100 tasks, capacity 1, packet loss 0%–90% at 10% steps and 100 paired seeds per point. **The two figures have distinct greedy reference costs and native termination contracts; their cost percentages cannot be compared as if they used the same denominator.**

### Figure 1 — Sequential task allocation

![Figure 1: verified per-task committed coverage, conditional assignment cost, modeled stop and attempted sender payload](docs/figures/p2h/formal/figure1_sequential_task_completion.svg)

Each task T0 through T99 is voted on once, followed by native Score/Commit and robot retirement before the next task. The centralized reference issues and pays for its own sequential Assignment/Commit events, using only its one-time received Cost rows. The figure's panel A reports **mean committed task coverage**, not all-or-nothing complete success. At 90% loss, Proposed achieves 100% committed task coverage and 100/100 complete allocations, whereas this **specific no-Cost-retry centralized baseline** achieves 10.54% mean coverage and 0/100 complete. Proposed at PL90 uses 254.23 kB and stops at 27.50 modeled seconds; Centralized uses 84.58 kB and stops at 1.37 s *after incomplete allocation*, which is not a faster successful completion. Proposed's mean full-success cost increase is +79.26% against the **full-information task-ID-ordered Greedy**, not global-minimum-pair Greedy.

At zero loss both methods complete 100/100, with exactly 0% task-order Greedy cost increase. Proposed takes 16.47 s and 249.25 kB versus Centralized 7.48 s and 89.23 kB. P2H contains **2,000 formal cases / 20 cells**, independently checked with **266,856 validations, 0 failures**. The source-bound audit notes that Proposed's 100% completion depends strongly on local self-votes, a one-vote received-plurality threshold and reliable Score/Commit; it is not an RF-wide resilience guarantee.

[Independent P2H formal audit](docs/P2H_FORMAL_100SEED_AUDIT.md) · [Verified 20-point data](docs/figures/p2h/formal/verified_20point_summary.csv) · [Canonical P2H protocol](docs/P2H_INTERACTIVE_FIGURE1.md).

### Figure 2 — Repeatable task allocation

![Figure 2: Proposed, CBAA, CBBA and Baseline Centralized; original verified curves, no footer notes](docs/figures/p2g/formal/figure2_repeatable_no_footer.svg)

This remains the prior accepted P2G Figure 2. **Proposed, CBAA, CBBA, Baseline Centralized** are exactly the displayed method names. The Centralized reference here retries missing Cost acquisition (unlike Figure 1), and represents one particular centralized baseline, not every centralized design. At 90% loss, Proposed has 100/100 complete, +5.04% cost increase against **full-info global minimum-pair Greedy**, 4.49 s and 105.67 kB; the Centralized retry reference has 100/100 complete, 0% cost increase against that same global Greedy, 32.40 s and 828.93 kB. Native CBAA is 100/100 complete, 71.38 s and 14,135.60 kB; CBBA reaches its native guard without full completion (0/100), with 71.90% conflict-free *observer* coverage at 90% loss. Observed CBAA/CBBA termination is not equivalent to paid Proposed Commit.

**Measurement boundaries:** Both figures report attempted sender **application** Bytes, including dropped SENDs; elapsed times are modeled using measured Rady ROS delay samples plus a hypothetical shared 144 Mbps medium, **not real 100-robot Wi-Fi MAC/PHY measurements**. Cost is only defined for fully completed native assignments, never filled with zero for failures. The finalized P2H study replaces the older one-batch Figure 1 as the primary paper illustration; past P2D/P2E/P2G plots remain in the repository as historical and source-auditable evidence, not parallel primary claims.

## C. Coordination time and deadline design

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

## Remaining acceptance work — P1 completed; next tests conditional

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
