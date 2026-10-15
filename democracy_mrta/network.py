from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import math
from pathlib import Path
import ssl
import urllib.error
import urllib.request

from .diagnostics import Diagnostic, ProtocolError


RADY_SOURCE_REPOSITORY = "minarady1/wifi_for_industrial_robotics"
RADY_SOURCE_COMMIT = "1996e5bb69b9ba4d25060cbc14838ddedf65cff2"
RADY_SOURCE_BLOB_SHA = "11e70e685229cc26458f272b0c954487c87d7953"
RADY_SOURCE_PATH = "plots/perama_range_testing.json"
RADY_SOURCE_URL = (
    "https://raw.githubusercontent.com/"
    f"{RADY_SOURCE_REPOSITORY}/{RADY_SOURCE_COMMIT}/{RADY_SOURCE_PATH}"
)

PRIMARY_LOCATION = "2"
PRIMARY_LOCATION_LABEL = "Medium range LoS (60 m)"
PRIMARY_CONFIG = "ax_160mhz_6ghz"
PRIMARY_CONFIG_LABEL = "Wi-Fi 6E ax/6/160"
PRIMARY_STEADY_START_S = 120.0
PRIMARY_STEADY_END_S = 181.0


@dataclass(frozen=True)
class EmpiricalLatencyProfile:
    source_repository: str
    source_commit: str
    source_blob_sha: str
    location: str
    location_label: str
    config: str
    config_label: str
    steady_start_s: float
    steady_end_s: float
    samples_ms: tuple[float, ...]

    @property
    def sample_count(self) -> int:
        return len(self.samples_ms)


def compute_git_blob_sha(data: bytes) -> str:
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()


def verify_rady_dataset_bytes(data: bytes) -> None:
    actual = compute_git_blob_sha(data)
    if actual != RADY_SOURCE_BLOB_SHA:
        raise ProtocolError(
            Diagnostic(
                owner="network",
                function="verify_rady_dataset_bytes",
                category="data",
                code="RADY_DATASET_BLOB_MISMATCH",
                expected=RADY_SOURCE_BLOB_SHA,
                actual=actual,
                details=f"source_commit={RADY_SOURCE_COMMIT}",
            )
        )


def build_verified_https_context() -> ssl.SSLContext:
    try:
        import certifi
    except ImportError as exc:
        raise ProtocolError(
            Diagnostic(
                owner="network",
                function="build_verified_https_context",
                category="dependency",
                code="CERTIFI_NOT_INSTALLED",
                expected="certifi installed from requirements.txt",
                actual="missing",
                details="run: python3 -m pip install -r requirements.txt",
            )
        ) from exc

    return ssl.create_default_context(cafile=certifi.where())


def ensure_rady_dataset(
    destination: Path,
    *,
    allow_download: bool = True,
) -> Path:
    if destination.exists():
        data = destination.read_bytes()
        verify_rady_dataset_bytes(data)
        return destination

    if not allow_download:
        raise ProtocolError(
            Diagnostic(
                owner="network",
                function="ensure_rady_dataset",
                category="dependency",
                code="RADY_DATASET_MISSING",
                expected=str(destination),
                actual="missing",
                details="download disabled",
            )
        )

    destination.parent.mkdir(parents=True, exist_ok=True)
    ssl_context = build_verified_https_context()
    try:
        with urllib.request.urlopen(
            RADY_SOURCE_URL,
            timeout=120,
            context=ssl_context,
        ) as response:
            data = response.read()
    except (OSError, urllib.error.URLError) as exc:
        raise ProtocolError(
            Diagnostic(
                owner="network",
                function="ensure_rady_dataset",
                category="dependency",
                code="RADY_DATASET_DOWNLOAD_FAILED",
                expected=RADY_SOURCE_URL,
                actual=type(exc).__name__,
                details=str(exc),
            )
        ) from exc

    verify_rady_dataset_bytes(data)

    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_bytes(data)
    temporary.replace(destination)
    return destination


def load_rady_latency_profile(
    dataset_path: Path,
    *,
    location: str = PRIMARY_LOCATION,
    location_label: str = PRIMARY_LOCATION_LABEL,
    config: str = PRIMARY_CONFIG,
    config_label: str = PRIMARY_CONFIG_LABEL,
    steady_start_s: float = PRIMARY_STEADY_START_S,
    steady_end_s: float = PRIMARY_STEADY_END_S,
) -> EmpiricalLatencyProfile:
    try:
        data = json.loads(dataset_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProtocolError(
            Diagnostic(
                owner="network",
                function="load_rady_latency_profile",
                category="data",
                code="RADY_DATASET_PARSE_FAILED",
                expected="valid JSON dataset",
                actual=type(exc).__name__,
                details=str(exc),
            )
        ) from exc

    if location not in data:
        raise ProtocolError(
            Diagnostic(
                owner="network",
                function="load_rady_latency_profile",
                category="data",
                code="RADY_LOCATION_MISSING",
                expected=location,
                actual=tuple(sorted(data.keys())),
            )
        )

    location_data = data[location]
    if config not in location_data:
        raise ProtocolError(
            Diagnostic(
                owner="network",
                function="load_rady_latency_profile",
                category="data",
                code="RADY_CONFIG_MISSING",
                expected=config,
                actual=tuple(sorted(location_data.keys())),
                details=f"location={location}",
            )
        )

    profile_data = location_data[config]
    timestamps = profile_data.get("control_timestamp_s")
    delays = profile_data.get("control_delay_ms")
    if not isinstance(timestamps, list) or not isinstance(delays, list):
        raise ProtocolError(
            Diagnostic(
                owner="network",
                function="load_rady_latency_profile",
                category="data",
                code="RADY_CONTROL_SERIES_MISSING",
                expected="control_timestamp_s and control_delay_ms arrays",
                actual=tuple(sorted(profile_data.keys())),
            )
        )
    if len(timestamps) != len(delays):
        raise ProtocolError(
            Diagnostic(
                owner="network",
                function="load_rady_latency_profile",
                category="data",
                code="RADY_CONTROL_SERIES_LENGTH_MISMATCH",
                expected=len(timestamps),
                actual=len(delays),
            )
        )

    samples: list[float] = []
    for timestamp, delay in zip(timestamps, delays):
        try:
            t = float(timestamp)
            d = float(delay)
        except (TypeError, ValueError):
            continue
        if (
            math.isfinite(t)
            and math.isfinite(d)
            and d >= 0.0
            and steady_start_s <= t <= steady_end_s
        ):
            samples.append(d)

    if not samples:
        raise ProtocolError(
            Diagnostic(
                owner="network",
                function="load_rady_latency_profile",
                category="data",
                code="RADY_STEADY_PROFILE_EMPTY",
                expected="at least one finite delay sample",
                actual=0,
                details=(
                    f"location={location}, config={config}, "
                    f"window=[{steady_start_s},{steady_end_s}]"
                ),
            )
        )

    return EmpiricalLatencyProfile(
        source_repository=RADY_SOURCE_REPOSITORY,
        source_commit=RADY_SOURCE_COMMIT,
        source_blob_sha=RADY_SOURCE_BLOB_SHA,
        location=location,
        location_label=location_label,
        config=config,
        config_label=config_label,
        steady_start_s=steady_start_s,
        steady_end_s=steady_end_s,
        samples_ms=tuple(samples),
    )


def percentile(values: tuple[float, ...] | list[float], probability: float) -> float:
    if not values:
        raise ValueError("values must not be empty")
    if not 0.0 <= probability <= 1.0:
        raise ValueError("probability must be within [0,1]")
    ordered = sorted(float(value) for value in values)
    index = int(probability * (len(ordered) - 1))
    return ordered[index]


def summarize_latency_profile(profile: EmpiricalLatencyProfile) -> dict[str, float | int]:
    samples = profile.samples_ms
    return {
        "sample_count": len(samples),
        "mean_ms": sum(samples) / len(samples),
        "p50_ms": percentile(samples, 0.50),
        "p90_ms": percentile(samples, 0.90),
        "p95_ms": percentile(samples, 0.95),
        "p99_ms": percentile(samples, 0.99),
        "min_ms": min(samples),
        "max_ms": max(samples),
    }


class EmpiricalLatencySampler:
    def __init__(self, profile: EmpiricalLatencyProfile, seed: int):
        if profile.sample_count <= 0:
            raise ValueError("profile must contain samples")
        self._samples = profile.samples_ms
        self._seed = int(seed)

    def sample_ms(self, key: str) -> float:
        digest = hashlib.sha256(
            f"{self._seed}|{key}".encode("utf-8")
        ).digest()
        index = int.from_bytes(digest[:8], "big") % len(self._samples)
        return self._samples[index]


def validate_packet_loss_probability(p_loss: float) -> float:
    value = float(p_loss)
    if not math.isfinite(value) or value < 0.0 or value > 1.0:
        raise ProtocolError(
            Diagnostic(
                owner="network",
                function="validate_packet_loss_probability",
                category="data",
                code="INVALID_PACKET_LOSS_PROBABILITY",
                expected="finite probability within [0, 1]",
                actual=p_loss,
            )
        )
    return value


def validate_vote_repetitions(vote_repetitions: int) -> int:
    """Bound a no-ACK, sender-side repetition transport experiment.

    One physical remote vote is sent for each copy. Local self-votes remain
    local and are never repeated. The 1-copy setting is the original E2 model.
    """
    if type(vote_repetitions) is not int or not 1 <= vote_repetitions <= 3:
        raise ProtocolError(
            Diagnostic(
                owner="network",
                function="validate_vote_repetitions",
                category="data",
                code="INVALID_VOTE_REPETITIONS",
                expected="integer in {1, 2, 3} (physical copies per remote ballot)",
                actual=vote_repetitions,
            )
        )
    return vote_repetitions



class SenderBudgetExhausted(ProtocolError):
    """A physical SEND would exceed a configured byte cap; no packet was sent."""


def validate_sender_payload_budget(limit_bytes: int) -> int:
    """Validate one sender-accounted application payload byte cap."""
    if type(limit_bytes) is not int or limit_bytes < 0:
        raise ProtocolError(Diagnostic(
            owner="network", function="validate_sender_payload_budget",
            category="data", code="INVALID_SENDER_PAYLOAD_BUDGET",
            expected="nonnegative integer application payload byte limit",
            actual=limit_bytes,
        ))
    return limit_bytes


@dataclass
class SenderPayloadBudget:
    """One independently reset SEND-byte ledger per benchmark seed/condition.

    There is no network or allocation state machine here. A broadcast is
    reserved once at emission, not multiplied by receiver opportunities.
    """
    limit_bytes: int
    sent_bytes: int = field(default=0, init=False)
    sent_messages: int = field(default=0, init=False)
    denied_messages: int = field(default=0, init=False)
    last_denied_diagnostic: Diagnostic | None = field(default=None, init=False)

    def __post_init__(self) -> None:
        validate_sender_payload_budget(self.limit_bytes)

    @property
    def remaining_bytes(self) -> int:
        return self.limit_bytes - self.sent_bytes


def reserve_sender_payload(
    budget: SenderPayloadBudget, *, payload_bytes: int, phase: str,
) -> None:
    """Atomically admit one physical SEND, or fail before the event exists.

    Denied sends consume zero bytes/messages. The benchmark runtime is
    responsible for catching SenderBudgetExhausted and ending its current
    incomplete stage WITHOUT fabricating any Commit or winner.
    """
    if type(payload_bytes) is not int or payload_bytes <= 0:
        raise ProtocolError(Diagnostic(
            owner="network", function="reserve_sender_payload",
            category="data", code="INVALID_SENDER_PAYLOAD_SIZE",
            expected="positive integer application payload Bytes per SEND",
            actual=payload_bytes, details=f"phase={phase}",
        ))
    if payload_bytes > budget.remaining_bytes:
        budget.denied_messages += 1
        diagnostic = Diagnostic(
            owner="network", function="reserve_sender_payload",
            category="runtime", code="SEND_PAYLOAD_BUDGET_EXHAUSTED",
            expected={"max_next_send_bytes": budget.remaining_bytes},
            actual={"attempted_send_bytes": payload_bytes},
            details=f"phase={phase}; used={budget.sent_bytes}; limit={budget.limit_bytes}",
        )
        budget.last_denied_diagnostic = diagnostic
        raise SenderBudgetExhausted(diagnostic)
    budget.sent_bytes += payload_bytes
    budget.sent_messages += 1



class BernoulliLossSampler:
    def __init__(self, seed: int):
        self._seed = int(seed)

    def is_delivered(self, key: str, p_loss: float) -> bool:
        probability = validate_packet_loss_probability(p_loss)
        digest = hashlib.sha256(
            f"{self._seed}|loss|{key}".encode("utf-8")
        ).digest()
        unit = int.from_bytes(digest[:8], "big") / float(1 << 64)
        return unit >= probability


# E9G-1: explicitly modeled shared-radio *sensitivity*, not an ns-3 PHY result.
# Rady (2024) supplies measured ROS delay, Bianchi (2000) motivates the
# contention/backoff abstraction, and NIST IR 8506 (2024) cautions against
# assuming OFDMA is always active. Per-hop parameters remain hypotheses.
@dataclass(frozen=True)
class WifiTimingConfig:
    phy_rate_mbps: float
    mac_overhead_bytes: int = 64
    phy_preamble_us: float = 120.0
    aifs_us: float = 34.0
    slot_us: float = 9.0
    cw_min: int = 15
    mac_ack_us: float = 45.0
    reference_ros_payload_bytes: int = 16


def validate_wifi_phy_config(config: WifiTimingConfig) -> WifiTimingConfig:
    """Data boundary for an opt-in, non-ns-3 shared-medium sensitivity model."""
    valid = (
        type(config) is WifiTimingConfig
        and type(config.phy_rate_mbps) in (int, float)
        and math.isfinite(config.phy_rate_mbps)
        and 0 < config.phy_rate_mbps <= 10000
        and type(config.mac_overhead_bytes) is int
        and config.mac_overhead_bytes >= 0
        and type(config.cw_min) is int and 0 <= config.cw_min <= 1023
        and type(config.reference_ros_payload_bytes) is int
        and config.reference_ros_payload_bytes > 0
    )
    if valid:
        for value in (
            config.phy_preamble_us, config.aifs_us, config.slot_us,
            config.mac_ack_us,
        ):
            if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
                valid = False
                break
    if not valid:
        raise ProtocolError(Diagnostic(
            owner="network", function="validate_wifi_phy_config",
            category="data", code="E9G_INVALID_WIFI_PHY",
            expected="finite positive PHY Mbps; nonnegative MAC/PHY timing and overhead; CWmin 0..1023",
            actual=repr(config),
        ))
    return config


class WifiCausalTimingSampler:
    """Causal opt-in single-shared-medium service model, NOT an ns-3 emulator.

    Each original application SEND is scheduled by the original packet owner
    as it occurs. A modeled infrastructure BSS adds two radio hops for
    inter-robot traffic (uplink -> AP and AP -> peer[s]) and one AP downlink
    for TASK announcement. Each hop includes size-sensitive PHY time,
    deterministic seeded BE backoff and hypothesized MAC ACK cost. All hops
    share ONE serialized resource; there is no simulated collision, RU
    allocation, per-STA EDCA queue, retransmission or correlated RF loss.
    Preserve a measured ROS delay residual without adding all of the
    Rady end-to-end delay on top of another full modeled network delay.
    """

    def __init__(self, profile: EmpiricalLatencyProfile, seed: int,
                 config: WifiTimingConfig):
        self.config = validate_wifi_phy_config(config)
        if type(profile) is not EmpiricalLatencyProfile or not profile.samples_ms:
            raise ProtocolError(Diagnostic(
                owner="network", function="WifiCausalTimingSampler.__init__",
                category="dependency", code="E9G_CALIBRATION_MISSING",
                expected="verified nonempty EmpiricalLatencyProfile",
                actual=type(profile).__name__,
            ))
        self._empirical = EmpiricalLatencySampler(profile, seed)
        self._seed = int(seed)
        self._epoch_start_ms = 0.0
        self._last_release_ms = 0.0
        self._medium_free_ms = 0.0
        self.packet_trace: list[dict[str, float | int | str]] = []

    def set_epoch_start_ms(self, elapsed_ms: float) -> None:
        """Advance original Voting epoch clock, never rewind network history."""
        value = float(elapsed_ms)
        if not math.isfinite(value) or value < self._epoch_start_ms - 1e-9:
            raise ProtocolError(Diagnostic(
                owner="network", function="WifiCausalTimingSampler.set_epoch_start_ms",
                category="time", code="E9G_NONCAUSAL_EPOCH_START",
                expected=f">={self._epoch_start_ms} ms", actual=elapsed_ms,
            ))
        self._epoch_start_ms = value

    def _frame_airtime_ms(self, payload_bytes: int) -> float:
        c = self.config
        return (c.phy_preamble_us / 1000.0
                + 8.0 * (payload_bytes + c.mac_overhead_bytes)
                / (1000.0 * c.phy_rate_mbps))

    def _backoff_ms(self, key: str, hop: int) -> float:
        c = self.config
        digest = hashlib.sha256(
            f"{self._seed}|e9g-backoff|{key}|hop={hop}".encode("utf-8")
        ).digest()
        slots = int.from_bytes(digest[:8], "big") % (c.cw_min + 1)
        return (c.aifs_us + slots * c.slot_us) / 1000.0

    def _reference_service_ms(self) -> float:
        c = self.config
        return (
            self._frame_airtime_ms(c.reference_ros_payload_bytes)
            + (c.aifs_us + 0.5 * c.cw_min * c.slot_us + c.mac_ack_us) / 1000.0
        )

    def sample_packet_ms(self, *, key: str, phase: str,
                         sender_id: int, receiver_id: int,
                         send_time_ms: float, payload_bytes: int) -> float:
        """Schedule one original SEND causally and return its observed latency.

        Events MUST be submitted by increasing absolute release time. In
        particular, original vote emission is sorted by sender ready-time
        only in this opt-in model; all legacy owners preserve their order.
        """
        if (type(payload_bytes) is not int or payload_bytes <= 0
            or not math.isfinite(float(send_time_ms)) or send_time_ms < 0):
            raise ProtocolError(Diagnostic(
                owner="network", function="WifiCausalTimingSampler.sample_packet_ms",
                category="data", code="E9G_INVALID_PACKET_INPUT",
                expected="positive application payload Bytes and finite nonnegative send time",
                actual={"bytes": payload_bytes, "send_time_ms": send_time_ms},
            ))
        release = self._epoch_start_ms + float(send_time_ms)
        if release < self._last_release_ms - 1e-9:
            raise ProtocolError(Diagnostic(
                owner="network", function="WifiCausalTimingSampler.sample_packet_ms",
                category="time", code="E9G_NONCAUSAL_PACKET_RELEASE",
                expected={"minimum_release_ms": self._last_release_ms},
                actual={"release_ms": release, "phase": phase, "key": key},
                details="Original packets must enter shared-medium timing in release order",
            ))
        self._last_release_ms = release
        is_broadcast = receiver_id == -1
        hops = 1 if phase == "task_announcement" else 2
        # Peer broadcast: STA->AP is an acknowledged uplink, AP->peer[s]
        # is multicast/broadcast without normal per-recipient MAC ACK.
        acked_hops = (0 if phase == "task_announcement" else
                      1 if is_broadcast else 2)
        airtime = hops * self._frame_airtime_ms(payload_bytes)
        backoff = sum(self._backoff_ms(key, hop) for hop in range(hops))
        ack = acked_hops * self.config.mac_ack_us / 1000.0
        wait = max(0.0, self._medium_free_ms - release)
        finish = max(self._medium_free_ms, release) + airtime + backoff + ack
        self._medium_free_ms = finish

        # Reference is a light-load single-hop ROS control packet; its
        # empirical end-to-end latency already includes PHY/MAC service.
        # Subtract the reference *expected* service and clamp residual >=0.
        empirical = float(self._empirical.sample_ms(key))
        residual = max(0.0, empirical - self._reference_service_ms())
        arrival = finish + residual
        latency = arrival - release
        if not math.isfinite(latency) or latency < 0:
            raise ProtocolError(Diagnostic(
                owner="network", function="WifiCausalTimingSampler.sample_packet_ms",
                category="time", code="E9G_NONCAUSAL_PACKET_ARRIVAL",
                expected="arrival >= release and finite",
                actual={"arrival": arrival, "release": release},
            ))
        self.packet_trace.append({
            "key": key, "phase": phase, "sender_id": sender_id,
            "receiver_id": receiver_id, "payload_bytes": payload_bytes,
            "release_abs_ms": release, "start_abs_ms": release + wait,
            "media_finish_abs_ms": finish, "arrival_abs_ms": arrival,
            "queue_ms": wait, "airtime_ms": airtime,
            "backoff_ms": backoff, "mac_ack_ms": ack,
            "rady_nonoverlap_residual_ms": residual,
            "wireless_hops": hops,
            "wireless_payload_equivalent_bytes": hops * (
                payload_bytes + self.config.mac_overhead_bytes
            ),
        })
        return latency

    def summarize_network(self) -> dict[str, float | int | dict]:
        """Account every physical SEND, including packets lost by receivers."""
        rows = self.packet_trace
        by_phase: dict[str, dict[str, int]] = {}
        for packet in rows:
            phase = str(packet["phase"])
            account = by_phase.setdefault(phase, {"sender_sends": 0, "sender_bytes": 0})
            account["sender_sends"] += 1
            account["sender_bytes"] += int(packet["payload_bytes"])
        return {
            "sender_by_phase": {phase: by_phase[phase] for phase in sorted(by_phase)},
            "packet_count": len(rows),
            "application_sender_bytes": sum(int(r["payload_bytes"]) for r in rows),
            "radio_hop_count": sum(int(r["wireless_hops"]) for r in rows),
            "radio_payload_equivalent_bytes": sum(
                int(r["wireless_payload_equivalent_bytes"]) for r in rows),
            "total_airtime_ms": sum(float(r["airtime_ms"]) for r in rows),
            "total_backoff_ms": sum(float(r["backoff_ms"]) for r in rows),
            "total_ack_ms": sum(float(r["mac_ack_ms"]) for r in rows),
            "total_queue_ms": sum(float(r["queue_ms"]) for r in rows),
            "total_residual_ms": sum(
                float(r["rady_nonoverlap_residual_ms"]) for r in rows),
            "medium_busy_until_ms": self._medium_free_ms,
        }


@dataclass(frozen=True)
class RadyAdaptiveDeadlineEstimate:
    """Frozen per-phase service budget, with no held-out run outcome leakage."""
    phase: str
    active_robots: int
    total_tasks: int
    reference_phy_mbps: float
    margin_factor: float
    rady_mean_ms: float
    rady_p95_ms: float
    statistical_margin_ms: float
    radio_burst_ms: float
    deadline_ms: float
    application_packet_bytes: int


def estimate_e9h_adaptive_deadline(
    *, profile: EmpiricalLatencyProfile,
    active_robots: int,
    total_tasks: int,
    reference_phy_mbps: float,
    margin_factor: float,
    phase: str,
) -> RadyAdaptiveDeadlineEstimate:
    """E9H Rady-anchored deadline: mean + margin + hypothesized N-radio burst.

    D_phase(n,R,k) = mean(Rady) + k*[p95(Rady)-mean(Rady)]
                 + 2*n*[preamble+AIFS+E(backoff)+ACK+
                         8*(bytes(phase)+H)/(1000*R)].
    The end-to-end measured ROS latency is used ONLY as a statistical base.
    The modeled radio-burst term is a conservative *sensitivity assumption*,
    NOT a claimed independently calibrated 802.11ax 100-station load.
    k is a predeclared sensitivity (0,1,2), never trained on evaluation seeds.
    """
    correct = (
        type(active_robots) is int and active_robots >= 1
        and type(total_tasks) is int and total_tasks >= active_robots
        and phase in ("cost", "vote", "vote_batch")
        and type(margin_factor) in (int, float)
        and math.isfinite(float(margin_factor)) and 0 <= margin_factor <= 4
    )
    if not correct:
        raise ProtocolError(Diagnostic(
            owner="network", function="estimate_e9h_adaptive_deadline",
            category="data", code="E9H_INVALID_DEADLINE_INPUT",
            expected="active_robots>=1; total_tasks>=active_robots; phase=cost/vote/vote_batch; k in [0,4]",
            actual={"active_robots":active_robots,"tasks":total_tasks,
                    "phase":phase,"margin_factor":margin_factor},
        ))
    config = validate_wifi_phy_config(
        WifiTimingConfig(phy_rate_mbps=reference_phy_mbps)
    )
    if (type(profile) is not EmpiricalLatencyProfile
        or not profile.samples_ms or any(
            not math.isfinite(x) or x < 0 for x in profile.samples_ms
        )):
        raise ProtocolError(Diagnostic(
            owner="network", function="estimate_e9h_adaptive_deadline",
            category="dependency", code="E9H_MISSING_RADY_SAMPLES",
            expected="verified nonempty finite nonnegative Rady ROS delay profile",
            actual=type(profile).__name__,
        ))
    mean = sum(profile.samples_ms) / len(profile.samples_ms)
    p95 = percentile(profile.samples_ms, 0.95)
    payload = (
        16 + 8 * total_tasks if phase == "cost"
        else 16 + 8 * active_robots if phase == "vote_batch"
        else 32
    )
    frame_ms = (
        config.phy_preamble_us + config.aifs_us
        + 0.5 * config.cw_min * config.slot_us
        + config.mac_ack_us
    ) / 1000.0 + (
        8.0 * (payload + config.mac_overhead_bytes)
        / (1000.0 * config.phy_rate_mbps)
    )
    radio_burst = 2 * active_robots * frame_ms
    margin = margin_factor * max(0.0, p95 - mean)
    deadline = mean + margin + radio_burst
    return RadyAdaptiveDeadlineEstimate(
        phase=phase, active_robots=active_robots,
        total_tasks=total_tasks, reference_phy_mbps=reference_phy_mbps,
        margin_factor=float(margin_factor), rady_mean_ms=mean,
        rady_p95_ms=p95, statistical_margin_ms=margin,
        radio_burst_ms=radio_burst, deadline_ms=deadline,
        application_packet_bytes=payload,
    )



def estimate_e9h_guarded_initial_cost_ms(
    *, profile: EmpiricalLatencyProfile,
    total_robots: int, total_tasks: int, reference_phy_mbps: float,
) -> float:
    """Once-per-run bounded Cost protection, never a repeated Vote deadline.

    Frozen worst-sample Rady ROS control latency + all original Cost sender
    packets' conservative max CWmin radio service and a 1ms clock allowance.
    Cost is broadcast only once per initial Greedy allocation run.
    100R@144Mbps matches the historical E9G ~609.113ms Cost budget.
    This is a safe envelope IN THE E9G PROXY, not field Wi-Fi worst case.
    """
    if (type(total_robots) is not int or total_robots < 1
        or type(total_tasks) is not int or total_tasks < 1):
        raise ProtocolError(Diagnostic(
            owner="network",function="estimate_e9h_guarded_initial_cost_ms",
            category="data",code="E9H_INVALID_GUARDED_COST_GRID",
            expected="positive integer robots and original tasks",
            actual=(total_robots,total_tasks),
        ))
    config=validate_wifi_phy_config(
        WifiTimingConfig(phy_rate_mbps=reference_phy_mbps)
    )
    if (type(profile) is not EmpiricalLatencyProfile
        or not profile.samples_ms
        or any(not math.isfinite(x) or x < 0 for x in profile.samples_ms)):
        raise ProtocolError(Diagnostic(
            owner="network",function="estimate_e9h_guarded_initial_cost_ms",
            category="dependency",code="E9H_GUARDED_COST_RADY_MISSING",
            expected="pinned nonempty finite Rady control-delay samples",
            actual=type(profile).__name__,
        ))
    payload=16+8*total_tasks
    worst_perhop_ms=(
        config.phy_preamble_us + config.aifs_us
        + config.cw_min*config.slot_us + config.mac_ack_us
        + 8.0*(payload+config.mac_overhead_bytes)/config.phy_rate_mbps
    )/1000.0
    return max(profile.samples_ms) + 2*total_robots*worst_perhop_ms + 1.0



def estimate_e9j_cbaa_consensus_window_ms(
    *, profile: EmpiricalLatencyProfile, robots: int, tasks: int,
    reference_phy_mbps: float,
) -> float:
    """Original CBAA full-vector broadcast wave: paper packet, Rady tail, AP service."""
    if type(robots) is not int or type(tasks) is not int or not 1 <= tasks <= robots:
        raise ProtocolError(Diagnostic(
            owner="network", function="estimate_e9j_cbaa_consensus_window_ms",
            category="data", code="E9J_INVALID_CBAA_WAVE_INPUT",
            expected="integer robots >= tasks >= 1", actual=(robots,tasks),
        ))
    config=validate_wifi_phy_config(WifiTimingConfig(phy_rate_mbps=reference_phy_mbps))
    if type(profile) is not EmpiricalLatencyProfile or not profile.samples_ms or any(
        not math.isfinite(x) or x < 0 for x in profile.samples_ms
    ):
        raise ProtocolError(Diagnostic(
            owner="network", function="estimate_e9j_cbaa_consensus_window_ms",
            category="dependency", code="E9J_CBAA_RADY_PROFILE_MISSING",
            expected="valid Rady application delay samples",actual=type(profile).__name__,
        ))
    size=16+12*tasks
    hop=(config.phy_preamble_us+config.aifs_us
        +config.cw_min*config.slot_us+config.mac_ack_us)/1000.0
    hop+=8*(size+config.mac_overhead_bytes)/(1000.0*config.phy_rate_mbps)
    return max(profile.samples_ms)+2*robots*hop+1.0


def estimate_e9l_price_auction_stage_ms(
    *, profile: EmpiricalLatencyProfile, robots: int, packet_bytes: int,
    reference_phy_mbps: float,
) -> float:
    """Size-aware, conservative Rady+E9G upper wave for 28B BID/AWARD.

    One full stage is charged only if it has actual SENDs; this is a
    shared-medium model, not measured 802.11/nS-3 throughput or MAC ACK.
    """
    if (type(robots) is not int or robots < 2
        or type(packet_bytes) is not int or not 16 <= packet_bytes <= 1200):
        raise ProtocolError(Diagnostic(
            owner="network", function="estimate_e9l_price_auction_stage_ms",
            category="data", code="E9L_INVALID_PRICE_WAVE",
            expected="robots>=2, 16<=actual packet Bytes<=1200",
            actual=(robots,packet_bytes),
        ))
    config=validate_wifi_phy_config(WifiTimingConfig(
        phy_rate_mbps=reference_phy_mbps,
    ))
    if (type(profile) is not EmpiricalLatencyProfile or not profile.samples_ms
        or any(not math.isfinite(x) or x < 0 for x in profile.samples_ms)):
        raise ProtocolError(Diagnostic(
            owner="network", function="estimate_e9l_price_auction_stage_ms",
            category="dependency", code="E9L_RADY_PROFILE_MISSING",
            expected="verified nonempty finite Rady ROS application delay",
            actual=type(profile).__name__,
        ))
    perhop_ms=(config.phy_preamble_us+config.aifs_us
        +config.cw_min*config.slot_us+config.mac_ack_us)/1000.0
    perhop_ms+=8.0*(packet_bytes+config.mac_overhead_bytes)/(
        1000.0*config.phy_rate_mbps
    )
    return max(profile.samples_ms)+2*robots*perhop_ms+1.0
