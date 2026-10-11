# E8 — Published CBAA Family: Independent Single-Assignment Auction/Consensus

**STATUS: source/tests committed, new CBAA unit tests and simulations NOT YET VERIFIED on the user's Mac.**

This directory is the separate evidence root for the first CBAA literature-method baseline. It is NOT the historical 51%-majority, pure 25%-plurality, Vote K2/K3 redundancy, CBBA or ACBBA.

**Publication:** Choi, Brunet & How, "Consensus-Based Decentralized Auctions for Robust Task Allocation," IEEE T-RO 25(4), 2009, DOI 10.1109/TRO.2009.2022423. [MIT archived article](https://dspace.mit.edu/entities/publication/b0bf0a05-be3b-433b-9f4b-ce314ed5178b).

This code implements CBAA's single-assignment Phase 1 auction and Phase 2 local maximum-consensus, with each agent holding its own winning bid and task; outbid agents release their claims and can bid on other tasks in later iterations. Distinct engineering controls: c_ij = 1/(1+cost_ij), synchronous complete-graph fixed iteration budget, piggybacked winner-origin IDs for deterministic tie-breaking, one unreliable bid-vector broadcast per robot per iteration, and **NO centralized correction, voting threshold, final authoritative Commit, hidden guaranteed peer delivery, or global oracle stopping feedback**. An omniscient evaluator checks only AFTER the run whether each agent agrees with all other agents on a task winner, and reports any split-brain claims instead of pretending the task is assigned.

## Mac preflight and smoke

From repo root:

    git pull
    python3 -m unittest discover -s tests -v
    python3 -m experiments.run_cbaa_baseline \
      --robots 10 --tasks 5 --seeds 3 \
      --loss-probabilities 0,0.30,0.50 --max-iterations 20 \
      --output-root results/e8_cbaa_single_assignment_smoke

Expected first smoke evidence: 9 per-seed condition rows in raw/cbaa_<UTC>.csv, 3 p-level rows in summary.csv, a gzip-compressed seed-0 consensus-broadcast send/delivery/final-local-state audit, and manifest.json with source SHA, score rule, pinned Rady profile, scenario sizes and fixed iteration budget. Every incomplete or conflicting run retains its failure/claim evidence and has NaN full-batch cost, never an artificially low partial cost.

Then AFTER suite + first smoke pass:

    python3 -m experiments.run_cbaa_baseline \
      --robots 100 --tasks 50 --seeds 3 \
      --loss-probabilities 0,0.30,0.50 --max-iterations 20 \
      --output-root results/e8_cbaa_100r50t_pilot

At p=0, 100R/50T whole-team agreement must be checked BEFORE any paper comparison or expansion to 100 seeds. This is an independent algorithm-level comparison: local CBAA bidding is not fixed Greedy, so do not attribute all cost differences to packet loss. More importantly, **CBAA loses consensus vector packets, whereas the original E2 loses distinct Cost and Vote messages but treats its Commit channel as reliable**. The loss probability p is not a declaration of identical communication mechanisms.

A fixed iteration budget does not solve decentralized termination detection. Its communication overhead and modeled time are deliberately NOT final paper-ready efficiency claims until we implement and validate genuine distributed stopping, dynamic topology, and message accounting equivalence. A later genuine CBBA/ACBBA reproduction will be separate, not renamed CBAA.

Canonical source/metrics/diagnostic contracts: docs/EXPERIMENT_PROTOCOL.md §18; project change ledger: docs/CHANGE_CONTINUITY.md. All previous E2/E3/E4/Greedy-only/redundancy outputs must remain untouched.
