# E2 — Bernoulli Packet-Loss Robustness

E2 isolates one-round robustness to independent packet loss.

Loss sweep:

`p_loss ∈ {0, 0.1, 0.3, 0.5, 0.7, 0.9}`

Canonical E2 semantics:

- fixed Hungarian optimizer;
- same pinned Rady empirical latency profile as E1;
- cost broadcast delivery is Bernoulli per receiver;
- missing cost rows remain missing;
- each robot always knows its own cost row;
- Democracy runs Hungarian only on locally visible robot rows;
- a partial local assignment casts votes only for tasks it actually assigns;
- votes are direct lossy unicasts;
- quorum denominator remains the full fixed eligible robot count;
- commit broadcasts are reliable in E2;
- no retry is performed in E2; retry count is fixed to zero;
- Full-View succeeds only if every robot receives the complete cost matrix;
- Leader-Hungarian optimizes over the rows actually received by the leader.

The phase timeout is the maximum measured delay in the pinned E1 empirical profile. Therefore `p_loss = 0` preserves the E1 successful-delivery timing semantics, while missing cost packets become observable by absence at the end of the communication window.

Run:

```bash
git pull
python3 -m unittest discover -s tests -v
python3 -m experiments.run_e2 --seeds 100
```

Formal outputs:

- `raw/e2_<UTC timestamp>.csv`
- `events/e2_events_<UTC timestamp>.csv.gz`
- `summary.csv`

Primary metrics:

- task commit rate;
- correct executor rate (CER);
- correctness among committed tasks;
- full-assignment success rate;
- optimal-solution rate;
- optimality gap among full successful assignments;
- task timeout rate;
- decision/global completion time;
- logical messages and payload bytes;
- Bernoulli delivery opportunities / drops;
- visible robot rows;
- safety failures.

Commit loss is intentionally excluded from E2. It is a separate safety problem because a winner may execute while peers miss the commit; that failure source remains isolated for the later message-type experiment.


## CER instrumentation follow-up

The first 100-seed E2 run completed on 2026-10-09 and is retained as diagnostic pilot evidence. It did not record task-level oracle-match information, so it cannot distinguish “assigned every task” from “assigned the correct executor for each task” when only partial cost information is available.

The current runner additionally records:

- `correct_committed_tasks`
- `incorrect_committed_tasks`
- `correct_executor_rate`
- `correctness_among_committed`

Only the CER-instrumented rerun is eligible to become the formal E2 paper result.
