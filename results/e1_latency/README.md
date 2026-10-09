# E1 — Realistic Wi-Fi Communication-Time Cost

E1 uses the pinned Rady et al. ROS 2 application-delay dataset.

Primary profile:

- location 2 — Medium range LoS (60 m)
- configuration `ax_160mhz_6ghz` — Wi-Fi 6E ax/6/160
- steady-state window: 120–181 s
- source repository commit: `1996e5bb69b9ba4d25060cbc14838ddedf65cff2`
- source JSON Git blob SHA: `11e70e685229cc26458f272b0c954487c87d7953`

Prepare dependencies and source data:

```bash
python3 -m pip install -r requirements.txt
python3 -m scripts.prepare_rady_wifi_dataset
```

HTTPS certificate verification remains enabled. The downloader uses the `certifi` CA bundle for portability across Python installations.

Run formal E1:

```bash
python3 -m experiments.run_e1 --seeds 100
```

Outputs:

- `raw/e1_<UTC timestamp>.csv`
- `events/e1_events_<UTC timestamp>.csv`
- `summary.csv`

The network simulator uses concurrent event arrival times. It does not multiply message count by mean latency.


## Broadcast transport correction

The first E1 local run performed on 2026-10-09 used an obsolete transport interpretation in which cost announcements and commits were expanded into peer-to-peer unicasts. Those results are diagnostic only.

The canonical E1 transport is now:

- cost exchange: one logical broadcast per robot;
- votes: direct unicasts to proposed executors;
- commit: one logical broadcast per committed task;
- leader result: one logical assignment broadcast.

Rerun E1 after pulling the broadcast correction. Only corrected outputs are paper-eligible.
