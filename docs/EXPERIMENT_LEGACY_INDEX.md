# Internal Experiment ID Index — archived technical crosswalk

**Purpose:** keep historical \`E...\` implementation labels, failed/provisional controls, old artifact links and exact study identities discoverable **without presenting them as scientific categories or mandatory unfinished experiments in README**. The public experiment map is [A–D](../README.md). Historical source files and Git history are never renamed or deleted.

| Research group | Historical ID | Descriptive study | Evidence status / disposition |
|---|---|---|---|
| A — Correctness | E0 | Complete-information Hungarian correctness | **Accepted**; 500 original zero-loss cases |
| A — Agreement | E1 | Distributed vs leader Hungarian agreement overhead | **Accepted**; 2,000 original trace-bootstrap records |
| A — Historical control | E2 | One-round lossy Hungarian Cost/Vote | **Provisional**; per-vote original audit incomplete. **Archived, not required** for accepted correctness claims |
| B — Technical control | E9C | Packet-size / SEND-accounting checks | Validation control, **not** a formal final-termination comparison; retain only in archive |
| B — Packet loss | E9D / E9E | Dense Greedy Voting versus native CBAA loss sweep | **Accepted** final 52-point ×100seed ×2-method source from E9E; earlier variants historic |
| B/C — Technical pilot | E9F | Cost-source repetition variants | Not accepted as a separate matched benchmark; **do not rerun** for the closed claims |
| C — Timing control | E9G | Rady delay sampling and assumed 144Mbps shared medium | **Accepted modeled sensitivity only**; not actual Wi-Fi data |
| C — Pilot | E9H | Received-vote/deadline design pilot and incomplete broader factorial | Historical exploratory protocol; selected guarded follow-up has **accepted E9I** evidence. **Do not backfill** the huge abandoned factorial |
| C — Deadline | E9I | Fixed versus guarded/adaptive received-plurality time | **Accepted** formal 30% Cost/30% Vote population |
| D — Literature comparator | E9J | Original native CBAA versus original Voting | **Accepted** modeled 100seed/N, but no paid same-stop guarantee |
| D — Internal protocol extension | E9K | Paid-CBAA termination experiment | Technically archived; **user-authored modification excluded** from official original-algorithm ranking |
| D — Literature comparator | E9L | Distributed Price Auction with native BID/AWARD | **Accepted**, full original 2,000-run evidence, preserve guard-censored outcomes |
| D — Multi-task | E9M | Genuine CBBA versus capacity-four Voting Multi-task | **Accepted** corrected original 25R/100T/C4/30%-Loss paired100 ZIP |
| D — Single-task | E9N | Five-method N=T/C1 chart, original three archived plus two newly executed | **Accepted** 4,000 new original records; historical three source datasets **not** re-executed |

**Older E3–E7 and other small pilots:** preserved solely in [the full original experiment-history archive](EXPERIMENT_RESULTS_ARCHIVE_20261012.md); do not promote to accepted claims or create automatic to-do items.

## Controlled accepted source locations

- Correctness / agreement: [original zero-loss data](../results/e0_protocol_correctness/raw/e0_corrected_20261009T141508Z.csv), [original trace-bootstrap agreement](../results/e1_latency/raw/e1_20261009T144026Z.csv).
- Packet loss: [original dense sweep summary](figures/e9e_dense/formal/summary_by_loss.csv) and [source manifest](figures/e9e_dense/formal/publication_manifest.json).
- Deadline/communication: [adaptive deadline source](figures/e9i_cost30/formal/formal_20point_plot_data.csv) and [Rady radio-model sensitivity](figures/e9g_wifi/formal/scaling_20points_verified.csv).
- Alternatives: [original auction source report](E9L_FORMAL_100SEED.md), [capacity-one combined original ZIP report](E9N_FORMAL_100SEED.md), [capacity-four original ZIP report](E9M_CORRECTED_ORIGINAL_ZIP_AUDIT_100SEED.md).
- [Original experiment audit/limits](EXPERIMENT_RESULTS_AUDIT_20261012.md) and [canonical detailed protocol](EXPERIMENT_PROTOCOL.md).

## What does not belong on the required-experiment backlog

An unverified or abandoned historical pilot is **not necessarily a missing publication experiment**. E2 would need new original Vote-level data if one wanted a standalone lossy Hungarian claim; it is not a prerequisite to the already accepted no-loss correctness. E9H's larger factorial was supplanted by the accepted 30%-Loss deadline study, so rerunning the old factorial adds no required evidence. E9C/F and E3–E7 are validation or exploratory runs, not new official literature baselines.

The only recommended remaining acceptance questions are [common measurement/termination and channel timing validation](RESEARCH_CLOSURE_PLAN.md), plus conditional multi-task scaling *if explicitly claimed*. **Original methods remain original: Paid CBAA (E9K) is never renamed or included as a literature comparator.**
