# P2I Figure 2 — formal provenance and four-method source audit (2026-10-21)

**Published Figure 2 replaces the old four-method P2G primary view.** Current display order is Full Retransmission, Cost Retransmission Only, CBAA, Baseline Centralized. Original P2G Figure2 remains archived at `docs/figures/p2g/formal/figure2_repeatable_no_footer.svg` and is not deleted or used as the P2I native result.

## Source files and verification

- User-supplied P2I ZIP: `p2i_reliable_transport_100seed.zip`, SHA256 `3be637d2949e2db2760b962668275b62730ae75bfc9fab025b36e4ac8acd5503`.
- P2I source native Git SHA: `d28a8d0e6aa7fa9b52cc2f7730543a24f1a7ee3d` (original experimental branch `experiment/p2i-cost-vote-ackretry-20261021`); P2I manifest identifies 2,000 original native cases, 20 method/loss groups, 100 seeds at each 0% to 90% loss level.
- Manifest SHA256 matches uploaded `run_config_p2i.json` (`d6b0c2939e501456ff1cb95a1375d15dc9838fdda0dff70bd2ee2ef6c600c8be`), `per_seed_p2i.csv` (`2a2890ffb0a438e2feca6156caaded9cf2d824288269ac02f4780477167a2a01`), and `summary_p2i.csv` (`56166f361393ea15b04e38acfa5f5adff34ba921ced8ae173023bf296ab95cb5`). Independent checks on the uploaded ZIP found 1,000 `full_retry` and 1,000 `cost_retry_vote_once` rows, 2,000 recorded native successes, zero nonzero recorded cost gaps; all three manifest file digests matched. The ZIP does not contain every individual radio arrival/ACK trace, so this does not claim full RF packet-level replay.
- Historical CBAA 10 cells are copied from the verified `docs/figures/p2de/formal/verified_50point_summary.csv`, native source SHA `f514cfa3613e7b0bad5c739d136b09fea8c3f92c`, original mean time as recorded (6 decimal places).
- Historical Baseline Centralized 10 cells use the original verified `docs/figures/p2g/formal/figure2_repeatable_no_footer.svg` tooltips (original P2G source SHA `7cab1b5f7979b2f45104c529de7e25015b4ff7e8`): completion, successful-only cost, mean modeled stop seconds and sender kB are **only available here at four decimal places**. The displayed historical central values are source-derived approximations at SVG output precision, not falsely labeled full-precision new source rows.
- All four methods' 40 display cells are published in [verified_40point_summary.csv](figures/p2i/formal/verified_40point_summary.csv). Every circle tooltip in the [current SVG](figures/p2i/formal/figure2_reliable_four_method.svg) is sourced from that corresponding cell, with success/quality sample count 100 per loss and method.

## Fixed comparison and numerical conclusions

100 robots, 100 tasks, capacity 1, 100 seeds per plotted loss rate and 10 loss rates. Complete allocation = all 100 tasks assigned (not task coverage). All 40 plotted cells show complete allocation 100% and signed gap 0% **relative to full-information global minimum-pair Greedy, not Hungarian and not task-ID Greedy**. All-seed native modeled stop is in seconds, and sender application payload in kB (1000 bytes). Data SEND attempts including loss and modeled Cost/Vote receipt-bitmap ACKs are paid for P2I.

| Method | PL90 native complete | PL90 signed cost gap | PL90 modeled stop (s) | PL90 sender kB |
|---|---:|---:|---:|---:|
| Full Retransmission | 100/100 | 0% | 148.5252 | 8661.7952 |
| Cost Retransmission Only | 100/100 | 0% | 75.0786 | 4405.0126 |
| CBAA | 100/100 | 0% | 71.3832 | 14135.6000 |
| Baseline Centralized | 100/100 | 0% | 32.3970 | 828.9269 |

The paired P2I outcome has the **important scientific dependency** of self-vote plus one-vote received plurality and modeled reliable Score/Commit; full Cost recovery alone does not establish a general-purpose distributed consensus or MAC-layer delivery guarantee. P2I ACKs are modeled as reliable and charged as application SENDs; Wi-Fi frame-level ACK loss, collisions, adaptive retransmissions/EDCA and OFDMA are not implemented. Original CBAA native stopping and native Proposed's paid Commit differ; this is a source-honest comparison of four named implementations, not a homogeneous proof about all baseline algorithms.

## Change boundary / explicit exclusions

This is a **publication-only replacement of the README Figure 2** and does not modify original native code, old per-seed raw evidence, `experiments.p2g_plot.render_p2g_figure` or historical Git-backed SVG. Old multi-round Proposed and CBBA curves are excluded from the currently promoted figure, **not erased from archival experiments or section D's independent research questions**. Figure 1 in the README remains P2H task-ordered sequential allocation unchanged. Historical section 57/58 descriptions remain accurate for their explicitly dated experimental families; section 59 documents this newer figure. No Mac unittest/CI suite is claimed from this documentation-only publication.

