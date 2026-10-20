# Completed P2H/P2G formal comparisons and exact modeled communication foundations (2026-10-20)

**Research status:** Both requested main Figure families are complete, source-audited, and presented separately below. This is a documentation/publication update, **not** a new simulated 100-robot wireless experiment. Original user-uploaded ZIPs, raw CSVs, hashes, protocol states, and original plots are immutable. Communication times are **modeled native stop times**; they are not Python wall time, over-the-air measurements from 100 robots, a true packet-level Wi-Fi 6 implementation, or a common paid termination certificate for all algorithms.

## A. Figure 1 — actual sequential per-task Voting (P2H; NEW, completed)

- Real procedure per task **T0 Vote/Score/Commit → retire the committed executor → T1 new Vote/Score/Commit → ... T99**; the initial physical Cost snapshot is sent **once**, each task receives only one Vote attempt, no repeat Cost/Vote. Proposed uses native `greedy_task` / received plurality; its own Cost row and local self-vote are known even if other robot traffic is lost. Paid reliable Score and Commit are **assumed**.
- **Baseline Centralized** is a specific task-ID-ordered Greedy reference, not every centralized MRTA implementation. It receives an attempted Cost row once from each remote robot, makes a new cheapest-visible-unretired choice for each task, publishes a **paid per-task assignment**, gets a **paid executor Commit**, then proceeds to the next task. No Cost retry.
- **Panel A: mean *task completion rate*, not all-or-nothing 100/100 Seed success.** Each Seed contributes its count of native committed distinct task pairs divided by 100. The cohort mean is `100 * mean_task_coverage`. A Seed with 50 valid tasks contributes 50%, not 0%. Full-100/100-Seed-success count still exists in the raw/summary CSV for separate discussion; it is *not* plotted as A.
- B: complete-native-only signed percentage above the same full-information task-ID-ordered Greedy **per-Seed** cost, sample count `n`; missing for methods with no 100/100 native successes, never forced to zero. C: all-Seed modeled native stop seconds, including incomplete runs. D: all physically **attempted** application SEND payload kB (decimal kB=1000B), including packets lost at receivers.
- Configuration: 100 robots, 100 tasks, capacity 1, PL `0,10,...,90%`, 100 common scenario Seeds (0–99), **2,000 new original-native cases / 20 aggregated method×loss cells**.
- Original user-supplied formal archive `p2h_interactive_figure1_100seed.zip`: ZIP SHA256 `171508bd596060352c7d8a7493c2724e293225b17c9a7af2390713770490373f`, original simulation Git SHA `a54a13d454bb07cdfa9a20aa53753f9b6f61039d`, `per_seed_p2h.csv` SHA256 `fe2f6dd92ca6fd66da272addde4380fdb55a06b0a045b0d8e6b76894513e61a6`, `summary_p2h.csv` SHA256 `80f8404eb06499e6191caf1e64466bb5367d6ba2cf622eb186f1fa56846f11c3`. The original formal `figure1_interactive_sequential.svg` used the *wrong full-scene success metric for A*; the **source-derived corrected Figure 1** changes only A and lives at `docs/figures/p2hi/formal/figure1_task_completion.svg` (derived aggregate source in `figure1_verified_summary.csv`). Original ZIP/manifest/SVG are kept unmodified.

| PL | Proposed task completion | Baseline Centralized task completion | Proposed full-success-only cost gap | Proposed native stop | Baseline native stop | Proposed attempted kB | Baseline attempted kB |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 0% | 100.00% | 100.00% | 0.00% | 16.47s | 7.48s | 249.25 | 89.23 |
| 30% | 100.00% | 70.33% | +0.85% | 20.13s | 5.38s | 255.50 | 87.69 |
| 50% | 100.00% | 50.06% | +4.77% | 21.47s | 4.01s | 257.64 | 86.64 |
| 90% | 100.00% | 10.54% | +79.26% | 27.50s | 1.37s | 254.23 | 84.58 |

**Interpretation:** this protocol gets complete native allocations at all PL levels under **reliable Score/Commit and local self-voting**. It is **not** a proof of general RF fault tolerance, and allocation quality degrades sharply under lost Cost. Proposed incurs greater time and payload than the one-Cost centralized reference when both succeed at PL0. A shorter baseline stop after loss is not a faster 100-task completion.

## B. Figure 2 — repeated methods with a named Centralized Global Greedy baseline (P2G; completed)

- **Proposed**: original Global minimum-edge Greedy multi-round batch, fresh ballots and redecision for pending tasks (up to 300 native epochs), no re-sending missing initial Cost. **CBAA/CBBA**: original native optimization, auction/consensus and termination rules (not replaced with Global Greedy). **Baseline Centralized**: original centralized coordinator repeatedly transmits only missing Cost rows, up to 300 Cost attempts, then performs **one** Global minimum-edge Greedy over physically received rows and paid assignment/Commit. These are intentionally different retry semantics; this Centralized comparator is not a claim about every centralized MRTA approach.
- A: strict native **100/100 Seed complete assignment** (%), unlike Figure 1 A. B: successful-only signed cost % relative to same full-info Global minimum-edge Greedy, which differs from Figure 1's **task-order** cost denominator. C: all-Seed simulated native stop time. D: all-attempted sender application kB including lost frames. CBAA/CBBA native terminal observer snapshots do not imply the same paid reliable Commit as Proposed/Centralized.
- Configuration: same 100R/100T/C1, 100 paired Seeds, PL0–90. Source used for Figure 2: new P2G Centralized Cost Retry original 1,000 native cases (inside **3,000** new P2G cases overall), plus historical verified 1,000 original Proposed Multi-Round + 1,000 CBAA + 1,000 CBBA cases. Only 1,000 P2G central cases are on the final Figure 2; the other 2,000 P2G one-batch methods remain archived, not substituted for P2H true sequential Figure 1.
- Original user-supplied `封存.zip` SHA256 `2ba3615e54e91e96cbb606446bbe61cf531e9f23f9552e6a957a635d240fce2c`; P2G formal source Git SHA `7cab1b5f7979b2f45104c529de7e25015b4ff7e8`; P2G `per_seed_p2g.csv` SHA256 `c96799424efe6ca78d240627a9c561383c9843165a7e85d6f29c9995257bea5a`; original `summary_p2g.csv` SHA256 `5aaed14e696accd4e05843744cb490f6573acd32238055d4a789920818039e09`. Verified old 50-cell aggregate used for P2E Proposed/CBAA/CBBA: Git blob `5326876027a9b42ac0fb95033b14cea79e46672e`. Figure 2 is republished with short legends Proposed/CBAA/CBBA/Baseline Centralized, **no bottom explanatory paragraphs**, and zero alteration of plotted source values; derived 40-row source `docs/figures/p2hi/formal/figure2_verified_summary.csv`.

| PL=90% (100 seeds) | Proposed | CBAA | CBBA | Baseline Centralized |
|---|---:|---:|---:|---:|
| Native complete-100 rate | 100% | 100% | 0% | 100% |
| Successful-only cost gap vs full-info Global Greedy | +5.04% | 0.00% | — | 0.00% |
| Modeled native stop (all Seeds) | **4.49 s** | 71.38 s | 112.53 s | 32.40 s |
| Attempted sender application payload | **105.67 kB** | 14,135.60 kB | 56,343.95 kB | 828.93 kB |

At PL90, Proposed and this specific retried-Cost centralized baseline both achieve 100/100 native completion, but Proposed trades +5.04% Greedy-relative assignment cost for ≈7.21× shorter native stop and ≈7.84× lower attempted application payload. CBBA still has **71.90% conflict-free terminal observer task coverage** despite 0% complete native cases, NOT a paid Commit proof. These results apply only under the specified different native message loss and stopping rules.

## C. Exact current communication model: empirically bootstrapped ROS delay + hypothesized shared 802.11 medium

### C1. Real ROS delay profile pinned to a specific published measurement, not synthetic literature numbers

**Direct quantitative source:** Rady, Iova, Rivano, Deligianni, Drikos, **“How does Wi-Fi 6 fare? An industrial outdoor robotic scenario,” Ad Hoc Networks 156 (2024), article 103418**, DOI [10.1016/j.adhoc.2024.103418](https://doi.org/10.1016/j.adhoc.2024.103418). Real industrial Perama shipyard Wi-Fi/ROS controller experiment, **not 100 simultaneous MRTA robot endpoints**. Pinned open data: [minarady1/wifi_for_industrial_robotics](https://github.com/minarady1/wifi_for_industrial_robotics) commit `1996e5bb69b9ba4d25060cbc14838ddedf65cff2`, JSON `plots/perama_range_testing.json`, Git blob `11e70e685229cc26458f272b0c954487c87d7953`. The original code `democracy_mrta.network.verify_rady_dataset_bytes` rejects mismatched bytes. `load_rady_latency_profile` selects location `2` = **Medium-range LoS ~60 m**, Wi-Fi `ax_160mhz_6ghz` **6 GHz / 160 MHz**, steady interval **120–181 s**, and the original `control_delay_ms` ROS control-delay values (not the original real-world loss record).

| Actual extracted profile, 121 delay samples | Value |
|---|---:|
| Mean | 33.593687 ms |
| Median (P50) | 19.962509 ms |
| P95 | 64.149866 ms |
| P99 | 159.419021 ms |
| Maximum | 531.535123 ms |

**Rady paper's own scientific findings:** nine PHY configurations at four industrial locations, up to ≈900 Mbps streaming throughput for wide channels, but narrower channels can have ≈9 ms delay; no single Wi-Fi configuration maximizes all application KPIs. Neither **144 Mbps** nor our **100-robot shared-medium model** is a rate or deployment directly measured by Rady.

`EmpiricalLatencySampler.sample_ms(key)` chooses a sample reproducibly using `SHA256(seed + "|" + event_key)` modulo 121. Different causal packet keys create reproducible bootstrap samples; this is a deterministic pseudorandom resampling of the empirical marginal **not time-correlated trace replay**.

### C2. Independently assumed shared-medium timing proxy (not ns-3)

The true owner is `democracy_mrta.network.WifiCausalTimingSampler`. Each original protocol application SEND enters a single **serialized** shared medium; in the assumed infrastructure BSS, robot→robot traffic costs **two radio hops** (robot→AP→other robot[s]); TASK announcement is modeled as one AP→robot(s) hop. All SENDs still count once at the **application sender**, regardless of fan-out or receiver drops.

`WifiTimingConfig(phy_rate_mbps=144)` sets a **hypothetical** service rate of 144 Mbps with the following **implementation parameters, not calibrated physical Wi-Fi 6E AP measurements**:

| Parameter | Model value |
|---|---:|
| Application PHY service rate | 144 Mbps |
| Extra modeled MAC/PHY bytes per hop | 64 B |
| Preamble | 120 μs |
| AIFS | 34 μs |
| Slot | 9 μs |
| Initial contention window, CWmin | 15 |
| MAC ACK service for acknowledged hop | 45 μs |
| Reference ROS control payload | 16 B |

For a payload of `B` application bytes and rate `R` Mbps, the modeled **one-hop airtime** is `preamble_ms + 8*(B+64)/(1000*R)`. Per-hop Backoff is `(34 + slots*9)/1000` ms, where integer `slots ∈ {0..15}` is deterministically sampled from `SHA256(seed, packet key, hop)`. ACK adds 45 μs for each modeled acknowledged hop. Packet queue wait is `max(0, shared_medium_free_time − SEND_release_time)`. One physical SEND first occupies the shared radio for all of its hops; subsequent SENDs cannot start radio service until the medium becomes free.

Measured **ROS packet end-to-end latency already contains radio/MAC components**. To avoid naïvely double-charging full radio service, the code subtracts a *modeled reference packet expected service* from the selected measured ROS delay and clamps residual at zero:

```text
empirical_residual = max(0, sampled_Rady_delay - reference_service)
radio_finish       = max(release_time, medium_free_time) + hops*(airtime+backoff) + acknowledged_hops*ACK
packet_arrival     = radio_finish + empirical_residual
sender_to_arrival  = packet_arrival - release_time
```

The real implementation sums each hop's seeded backoff. Note: *one* serialized medium, additive ACK/backoff and residual are our **sensitivity approximations**. The simulator does **not** implement real CSMA collision dynamics, hardware MCS negotiation, OFDMA resource units, hidden terminals, RF path loss/fading, multi-STA QoS queues, real MAC automatic repeat-request (ARQ), correlated RF packet loss, or a full ns-3 Wi-Fi MAC/PHY.

### C3. Independent receive loss and protocol-specific reliability assumptions

`democracy_mrta.network.BernoulliLossSampler.is_delivered(key,p)` compares a SHA256-seeded uniform `U ∈ [0,1)` with packet-loss probability `p`. A receiver gets an attempted packet iff `U >= p`. Reproducible keys include packet identity/recipient, so different receivers can independently miss the *same sender-paid broadcast*. This loss is **separately injected**: it is **not** a measured 0–90% loss trace from Rady; measured delay bootstrap and loss probability are independent.

- **Proposed**: Cost/Vote receive can fail; the modeled reliable TASK announcement, Score and Commit are still physically billed and delivered. An individual local self-vote requires no radio transmission; one physically received plurality/self-vote can produce Commit. P2H each task is tried once, sequentially (100 physical Vote/Score/Commit epochs). P2G Figure 2 Proposed uses repeated **fresh decisions on pending tasks**, not repeated original Cost.
- **Baseline Centralized** Figure 1: only Cost is lossy/attempted once, task assignment and executor Commit are reliable and sender-paid. Figure 2: only still-missing remote Cost is retransmitted up to 300 rounds, sender-paid even on drop; after collection the owner runs one Global Greedy and paid assignment/Commit.
- **CBAA/CBBA**: retain their original native iterative message/observer stop, and those native completion/quality outputs are not equivalent to paid Proposed/centralized Commit evidence. Any paper claim must state this fairness boundary.
- **Communication volume** counts **attempted sender-side application payload Bytes**, not delivered receiver copies, not 64B MAC overhead or two wireless hops. `WifiCausalTimingSampler.summarize_network` keeps both `application_sender_bytes` and a separate `radio_payload_equivalent_bytes` estimate. For an initial 100-task Cost row, payload ≈`16+8×100 = 816` B, physically sent once per active sender; a one-task Vote has its own smaller native payload. A broadcast is **one SEND**, not multiplied by 99 recipients. A dropped Cost/Vote still consumes counted SEND Bytes and modeled radio service.

### C4. Deadline and experimental time endpoints

True deadline function `network.estimate_e9h_adaptive_deadline` uses the **Rady mean/P95 plus assumed packet burst service**, not a paper-prescribed 100-robot deadline:

`D_phase(n,R,k) = Rady_mean + k*(Rady_P95 − Rady_mean) + 2*n*(preamble + AIFS + E(backoff) + ACK + 8*(payload_phase+H)/(1000*R))`.

Here `n` is the active robot count and `k` a predeclared safety factor (P2H uses guarded Cost once and `k=1` received-plurality Vote deadlines). The bounded Cost protection `estimate_e9h_guarded_initial_cost_ms` uses Rady maximum 531.535 ms plus conservative modeled worst contention, yielding about **609.113 ms at 100 robots / 144Mbps**. **This is a chosen simulation guard**, not a guaranteed RF deadline.

End-to-end simulated native stop time includes causal TASK phase, one-time Cost phase, per-task Vote/Score and paid Commit or a controlled guard stop (depending on method). It is NOT wall-clock CPU execution, and a short incomplete stop cannot be compared as a faster completed allocation.

### C5. Other actual bibliographic sources and what they do — never silently attribute our model to them

| Citation in repo `docs/references/e9g_wifi_timing.bib` | Actual scientific contribution | How it is used here |
|---|---|---|
| **Rady et al. (2024)** [DOI](https://doi.org/10.1016/j.adhoc.2024.103418) | Industrial outdoor Wi-Fi configurations, streaming/ROS/PTP delay and throughput | **Only direct numeric packet-delay calibration source** used in the current primary model |
| **Bianchi (2000)** [DOI](https://doi.org/10.1109/49.840210) | Analytical IEEE 802.11 DCF CSMA/CA backoff/throughput under idealized channel assumptions | Motivates using contention/backoff. We **do not implement or validate his full DCF collision fixed-point model** |
| **Liu & Choi (2023)** [DOI](https://doi.org/10.1145/3579451) | Measured Wi-Fi 6 multi-client OFDMA/TWT performance and trade-offs (paper reports ~3× throughput, ~5× lower latency in studied coexistence, higher OFDMA power consumption) | Context and limitation, **not** packet delay parameters or 100-robot calibration |
| **Montgomery & Candell (2024), NIST IR 8506** [DOI](https://doi.org/10.6028/NIST.IR.8506) | Actual OFDMA trigger activation in commercial Wi-Fi 6 APs; their tested devices activated uplink OFDMA for ≥2 stations with >100 packets/s | Evidence **against blindly assuming continuous OFDMA**; our current model does not schedule OFDMA |
| **Riley & Henderson (2010)** [DOI](https://doi.org/10.1007/978-3-642-12331-3_2) and [ns-3 Wi-Fi docs](https://www.nsnam.org/docs/models/html/wifi-design.html) | Packet-level network simulation methodology and actual Wi-Fi software modeling | Future validation path, **not executed** |
| **Choi, Brunet & How (2009)** [DOI](https://doi.org/10.1109/TRO.2009.2022423) | Original CBBA/CBAA decentralized auction and consensus task allocation | Original algorithmic baseline background, **not** our radio delay or packet-loss calibration |

### C6. Already completed checks and the next communications research question

E9G's independent zero-loss control (100 robots, same fixed 609.113ms task wait) produced a modeled **68.14266 s** without shared-radio service versus **68.224382 s** with assumed 144Mbps service: **+81.722ms**. This means adding the simplified shared-radio proxy had a small effect on that particular full-protocol mean and **does not validate 144Mbps as a real Wi-Fi deployment rate**. In the final P2H Figure 1, PL90 Proposed finishes 100/100 in **27.50 modeled seconds**, while Baseline Centralized only completes 10.54% of tasks and stops early in **1.37s**. In Figure 2, at PL90 Proposed and Centralized both finish, but Proposed uses **4.49s/105.67kB** vs Centralized **32.40s/828.93kB**.

**Main remaining external-validity risk:** Current 100%-successful high-loss P2H Proposed outcome relies on **local self-votes plus reliable Score/Commit**. The first worthwhile next communication experiment is a separate, predeclared **Score/Commit loss + ACK/timeout/ARQ** ablation, with actual counted physical retries and common paid termination (not rewriting the already accepted P2H and P2G formal runs). For stronger physical realism, additionally validate the shared-medium/packet-size/overhead assumptions with a version-pinned ns-3 Wi-Fi 6 simulation or a controlled multi-node AP measurement under 100-client-like load. Only then can conclusions extend from *modeled* communication efficiency to Wi-Fi implementation performance.
