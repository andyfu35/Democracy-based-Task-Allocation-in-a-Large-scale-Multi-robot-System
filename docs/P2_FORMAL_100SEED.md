# P2 original-source formal audit — 10% packet-loss resolution, 100 Seeds

**Status: original 4,000-case user Mac ZIP independently verified; zero audit discrepancies.** This report covers exactly 100 robots, 100 tasks, capacity one, 10 receiver-loss levels (0/10/.../90%), 100 paired Seeds (0..99), and the four original native algorithms: `voting`, `cbaa`, `cbba`, `price_auction`. It deliberately excludes the team-authored Voting Multi-task C1 extension and Paid CBAA. **Original P1 five-method historical evidence remains unchanged**.

**Provenance.** Executed source Git commit `f514cfa3613e7b0bad5c739d136b09fea8c3f92c`. Original ZIP `p2_loss10_100seed.zip`, 1,276,228 bytes, SHA256 `1d08a167308b9368ee2a764737066223ac041a5bd6508621c7b6cd0320036bb9`. Original per-seed CSV SHA256 `78c4871a9f0e391c11c92ace9c2b532695d2a2c4ca40d31166e31bf89901e5fc`; source summary SHA256 `de725d3d2737ceebafb99fa44e57fe583853077db242803e7f82d33e8d587aa7`; original generated four-panel SVG SHA256 `f7317099d8f71bcd3cc0ce597d7eea6f5e8bcfc2896a4dcf8aa3116040f73e43`. Original manifest finished UTC 2026-10-13 10:57:28. Original ZIP is retained unchanged by the user, **not fabricated as a Git file or silently substituted with the summary**. [SHA provenance and plot derivation](figures/p2/formal/source_manifest.json).

## Independent source verification

- All seven original ZIP entries passed safe-name, CRC, and integrity checks; all four manifest-attested original evidence files have the exact recorded SHA256.
- Exactly 4,000 distinct, correctly ordered and paired `(PL, seed, method)` rows and **40** correct group summaries; all original native guard failures remain in the denominator. Zero method-native diagnostic exceptions; all 4,000 native time and original attempted sender-Byte records are present.
- All 4,000 deterministic scene SHA256 values, independently computed original 100m coordinates and 100×100 Hungarian optimal costs match. All available assignments, one-to-one validity, actual Euclidean costs, makespans and ratios match independent recomputation. Genuine infeasible outputs have **blank**, not imputed, quality.
- All 4,000 native original packet ledgers audited: Voting Cost/Vote send and recorded drops; CBAA full 1,216-byte bid/winner vector with native Cost/TASK traffic; CBBA frame/SEND and receiver accounting; Price Auction original 28B BID/AWARD accounting, and reliable task announcement. No discrepancies.
- All 4,000 original terminal lines match the original per-seed CSV; source manifest declares 730 native failures, independently recomputed as **200 CBBA guard** and **530 Price Auction guard**. **3,270/4,000 native complete**, with **3,293/4,000 first globally feasible observed**; 23 first-feasible-but-no-native-stop cases must not be classified as successes.
- The **entire P2 30% loss cell** (100 Seeds × four algorithms = 400 records) is **field-for-field identical** to original independently audited P1 100R/100T matched native rows, despite new P2 study/source SHA. P1 original ZIP SHA256 `d2f30bf39d1f4aff336a5b7220a4f15ee887d0d79ccc8c8a536819f40691de58`.

## Original method-native completion / 100 Seeds

| Receiver loss | Voting | CBAA | CBBA | Price Auction | All-four native-success intersection |
|---|---:|---:|---:|---:|---:|
| 0% | 100 | 100 | 100 | 98 | 98 |
| 10% | 100 | 100 | 100 | 99 | 99 |
| 20% | 100 | 100 | 100 | 90 | 90 |
| 30% | 100 | 100 | 100 | 78 | 78 |
| 40% | 100 | 100 | 100 | 51 | 51 |
| 50% | 100 | 100 | 100 | 31 | 31 |
| 60% | 100 | 100 | 100 | 14 | 14 |
| 70% | 100 | 100 | 100 | 9 | 9 |
| 80% | 100 | 100 | 0 | 0 | **0 (quality intersection undefined)** |
| 90% | 100 | 100 | 0 | 0 | **0 (quality intersection undefined)** |

Voting and CBAA both complete 1,000/1,000 source cases through 90% **under their actual different native stopping conditions**. CBBA has 800/1,000 completions, with all 200 failed cases at 80–90% reaching its native round-160 guard. Original Auction completes 470/1,000, with 530 round-160 guard outcomes. Auction already fails in two of 100 zero-loss Seeds: such failures cannot be attributed to packet loss. At 80%, eight CBBA and one Auction cases reached a read-only globally feasible snapshot **without** native completion; they are **not** native successes. These are empirical, guard-dependent fixed-model outcomes, not packet-loss impossibility thresholds.

## Communication / speed / quality trade-off

| PL | Metric | Original Voting | Original CBAA | Original CBBA | Price Auction |
|---|---|---:|---:|---:|---:|
| 0% | Mean original attempted application sender payload (MB) | 0.249 | 1.325 | 3.612 | 0.193 |
| 30% | Mean sender payload (MB) | 0.255 | 2.693 | 6.488 | 0.354 |
| 70% | Mean sender payload (MB) | 0.259 | 5.484 | 31.820 | 0.491 |
| 80% | Mean sender payload (MB) | 0.258 | 7.715 | 61.881 | 0.515 |
| 90% | Mean sender payload (MB) | **0.254** | 14.136 | 56.344 | 0.558 |
| 90% | Mean **native modeled stop** (s; includes guard failures) | **27.497** | 71.383 | 112.530 | 192.190 |
| 90% | First globally feasible observer (s; when observed) | 27.497 | **12.770** | not observed | not observed |
| 90% | Euclidean/Hungarian cost ratio on **each method's successful 100 Seeds** | 2.4175 | **1.2353** | unavailable | unavailable |

The 90%-loss **application sender Byte reduction** of Voting compared with original CBAA is `(1−254229/14135600)×100 = 98.2015%` (factor 55.60 fewer Bytes). At 30% the reduction is 90.5127%. At 90% all 100 Voting and all 100 CBAA Seeds are paired natively successful, so the full-cohort **cost ratio** gap 2.4175−1.2353=**+1.1823** is valid and substantial: Voting's extremely low communication and 100% sample completion come with increasingly worse assignment quality as local Cost views disappear. CBAA yields the **same final assignment** for every Seed across all ten PL levels; CBAA and CBBA final assignments match all 800 paired 0%–70% cases. This is an observed property of this simulation, not a proof of general robustness.

The original full-four-success conditional quality CSV necessarily has **no values at PL 80/90**, because CBBA/Auction have no native-success cases. A separate *publication-only success-conditional* ratio panel can display Voting/CBAA quality at these losses; other algorithms' available quality uses a **different set of successful Seeds**, which is selection-biased if ranked unconditionally. Never invent unavailable failed-case costs.

**Paired bootstrap (100 Seeds, 12,000 resamples, seed 20261013, percentile 95% CI):** at 90% loss, CBAA − Voting original modeled native-stop time = **+43.8865 s** (95% CI **+42.2713 to +45.5743 s**). Voting − CBAA independent quality ratio = **+1.1823** (95% CI **+1.1176 to +1.2502**). A 60%-loss modeled stop-time difference is approximately zero (CBAA−Voting −0.0094 s, CI −0.6249 to +0.6240); at 70% Voting first overtakes CBAA in native stop (difference +4.4266 s). **However, CBAA first-feasible at 90% is earlier (12.77s) than Voting (27.50s)**: the native stop-time comparison does *not* measure equivalent distributed termination evidence.

## Figures and original evidence boundaries

- [One publication four-panel SVG](figures/p2/formal/primary_four_original_loss_robustness.svg) — four native original method series: full native completion, original modeled stop, log-scaled attempted sender MB, and success-conditional cost. The cost panel explicitly says sample counts differ. [Publication plotting source](figures/p2/formal/verified_10point_plot_source.csv) derives from the original raw/summary, with successful-only mean ratios rounded to four decimal places. It is a **new presentation**, not byte-identical to the original run SVG.
- The original immutable SVG is identified by SHA256 in the [manifest](figures/p2/formal/source_manifest.json), but not mislabeled as the publication derivative. Original 4,000 per-seed data and terminal log remain in the user's uploaded original ZIP, not in Git.
- Original prior `E9E` loss experiment uses **100 robots/50 tasks**, a different older synthetic channel, an earlier full-Commit protocol and 52 loss levels. Its 55%-loss Voting guard result must **NOT** be pooled with, explained away by, or presented as a contradiction of this separate `P2` 100R/100T Rady-proxy experiment. Keep its original ZIP/figure preserved as historical context, not the same test cohort.
- Native endpoint limitations remain unequal: Voting charges reliable Score/Commit; original CBAA reports local evidence certificate with unpaid shared simulation halt; original CBBA stops at simulator agreement, Price Auction has optimistic unpaid local halt. Therefore this experiment establishes **modeled native protocol completion and original sender traffic**, not a physical apples-to-apples paid distributed finalization time.
- Network model: independent receiver Bernoulli loss for method-native lossy packet classes, reliable TASK/Score/Commit where native, original Rady ROS application-delay bootstrap + hypothetical 144 Mbps shared radio. These numbers are **not** measured MAC collisions, ARQ, physical retransmission airtime or a real 100-robot Wi-Fi deployment.

**Suggested paper claim:** under 100R/100T/capacity1 and loss up to 90%, Voting trades a severe loss-dependent assignment optimality gap for large (up to 98.20%) reductions in attempted application sender bytes compared with CBAA, while both retain all 100 tested native completions; CBBA and Price Auction reach their configured guard at high loss. Distinguish externally first feasible from native termination and do not claim fundamental reliability thresholds.

**No executable code, original raw source, algorithm owner, network event, native timeout, state machine or method diagnostics were changed by this independent result publication.**
