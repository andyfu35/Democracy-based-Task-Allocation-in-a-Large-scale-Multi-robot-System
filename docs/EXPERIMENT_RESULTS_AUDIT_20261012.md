# Cross-experiment result audit — 2026-10-12

## Audit scope

This is a recheck of GitHub-visible original rows (E0, E1), published summary rows (E9E) and published rounded source-derived plot tables and manifests (E9G, E9I, E9J). **It is not a rerun and does not claim that the original E9E/E9G/E9I/E9J user ZIP bytes were independently re-imported in this pass.** The earlier original-source SHA256 attestations remain in their respective publication manifests. All original figures and source data are retained without modification.

| Study | Present verification | Evidence quality / scientific status |
|---|---|---|
| **E0** | [500 raw records](../results/e0_protocol_correctness/raw/e0_corrected_20261009T141508Z.csv): 500 distinct robot/task/seed keys, all full assignment, zero gap, zero oracle mismatch, zero recorded safety errors; published [5 cells](../results/e0_protocol_correctness/summary.csv) consistent | Formal verified, **Hungarian-controlled** zero-loss correctness |
| **E1** | [2,000 raw records](../results/e1_latency/raw/e1_20261009T144026Z.csv): 2,000 distinct robot/task/method/seed keys across [20 summary cells](../results/e1_latency/summary.csv), exactly 100/cell. Recomputed all 20 mean global agreement times and source Bytes; maximum absolute floating-point time difference 5.7e-13 ms, sender-byte error 0 B | Formal trace-bootstrap **simulation**, not multi-robot physical measurements |
| **E2** | [Study notes](../results/e2_packet_loss/README.md) describe one-round Hungarian Cost/Vote loss; committed results folder has no full audited original loss raw/summary. Vote-level forensic audit still pending | **Provisional**, not principal claim |
| **E9C** | Message-size / fixed-iteration accounting validation and historical CI source documented in [full results archive](EXPERIMENT_RESULTS_ARCHIVE_20261012.md) | **Validation control**, not comparable final CBAA completion |
| **E9E** | Published [104 rows](figures/e9e_dense/formal/summary_by_loss.csv) = 52 loss points × 2 methods, all 100 seeds. At loss 30%: Voting 164750.08 sender B and CBAA 838160 B; 80.3438389% less for Voting, with both outcomes 100/100 **under their different completion contracts**. Voting full Commit 0/100 at loss55%; CBAA locally certified 0/100 at loss96% but externally observer-agreed 100/100. [Source attestations](figures/e9e_dense/formal/publication_manifest.json) | **Formal original-source** 100R/50T synthetic-latency result; no inference about universal thresholds |
| **E9F** | Historical Cost-source repetition family retained in the canonical protocol | Not promoted: no newly accepted matched formal comparison in this pass |
| **E9G-2** | Published [20-point N:N table](figures/e9g_wifi/formal/scaling_20points_verified.csv) exactly obeys B(N)=24N²+92N+16ceil(N/37) Bytes and M(N)=N(N−1)/2+3N+ceil(N/37) SENDs for all 20 rows. At N100, Rady-only 68.142660s and modeled 144Mbps 68.224382s, extra 81.722ms. [Source attestations](figures/e9g_wifi/formal/publication_manifest.json) | **Formal simplified-model sensitivity**, 0% application loss; no 802.11ax/ns-3 or real 100-node RF |
| **E9H** | Implemented adaptive time/received-plurality contract and recorded single-seed/CI pilot; separate complete 96k-case formal factorial not established in the source ledger | **Pilot/design**, not formal population effect |
| **E9I** | [Published 20-point table](figures/e9i_cost30/formal/formal_20point_plot_data.csv): at N100 Cost30/Vote30, fixed received71.918s vs guarded received20.132s (72.0070% lower). [Original archive manifest](figures/e9i_cost30/formal/formal_publication_manifest.json) records 15998/16000 full across four arms, including two failures solely in legacy fixed-quarter | **Formal 100-seed model**; original 16000-case raw held in user source archive |
| **E9J** | [Published 20-point table](figures/e9j_cbaa/formal/plot_source_20point_rounded.csv): N100 Voting20.13159s vs CBAA13.64743s (32.2089% less for CBAA in current model); original sender ratio 2629.92188/249.50938 = 10.54037. N100 E9I Vote30 guard mean agrees within 0.00041s due published rounding. [Original source manifest](figures/e9j_cbaa/formal/source_manifest.json) records 2000 original CBAA runs and 8000 offline paired entries | **Formal source-backed model comparison**, but CBAA unpaid global halt is NOT Voting paid reliable Commit |

## What remains non-equivalent

E0/E1/E2 hold Hungarian fixed; E9E/E9I/E9J use original Greedy/Voting versus CBAA with different allocation strategies. E9E uses 100R/50T and fixed synthetic latency, whereas E9I/E9J use N=N and a sampled Rady + assumed 144Mbps simplified shared channel. E9G is zero application loss, E9I/E9J primary are original Cost30/Vote30 vs Bid/Winner30, and all packet loss is per-receiver independent Bernoulli rather than a measured universal RF rate.

Voting's **complete reliable Commit**, CBAA's **posthoc observer agreement**, and CBAA's **local convergence certificate** are distinct outcomes. CBAA's simulator-wide stop aggregation has no physically paid distributed stop/Commit; treating it as equivalent would bias time and bytes conclusions. All 100-seed confidence intervals refer to modeled scenario/packet randomness, not field-radio hardware uncertainties.

## Immutable source provenance

- E9E: original source Git 2808fa12fcd89aa8c2251e7e6438312a95a9df8f; original raw SHA256 e2337a157b96593d441c143b19d5b2b9b1c64604b4bc0a651da1e566c060c727.
- E9G: original source Git 910c5eac738367738907b18fce86e56adf86697d; original raw SHA256 ba79fd138d84d6d3bb7f04430a36a8c3e973d7ca0978834d4ad3a3b1d3f85be6.
- E9I: original source Git 408ff70a31e8c2957602cae3f09ad8f239cd3224; original user ZIP SHA256 5d275bebd8d6f985e8eef1bbba9a0947991cd71660c1cc49817619e6bc276ee5.
- E9J: original source Git 3a69bdef32fa4f430de5949768bf38a54987ffd1; original user ZIP SHA256 106fc14aa9088edf980a744bf9e129c516ce8cabf9c23322baa76be9b33c82bb.

See the [full historical results](EXPERIMENT_RESULTS_ARCHIVE_20261012.md), [canonical protocol](EXPERIMENT_PROTOCOL.md) and [change continuity](CHANGE_CONTINUITY.md). The README curates only key claims and **four** core figures, not the earlier 27 embedded historical images.
