"""E9M native application framing/receipt and physical SEND ledger owner.

Uses network.WifiCausalTimingSampler as the sole causal radio model. Synchronous
study phases are simulation barriers, not a distributed termination protocol.
"""
from __future__ import annotations

from collections import defaultdict
import hashlib
import json
import struct

from .diagnostics import Diagnostic, ProtocolError
from .network import BernoulliLossSampler, WifiCausalTimingSampler, validate_packet_loss_probability

MAX_FRAME_BYTES = 1200
CBBA_HEADER = struct.Struct("<4sIHHH32s")  # magic, round, sender, index, total, digest
SMALL_HEADER = struct.Struct("<4sIHHd")  # magic, task, sender, candidate, value


def encode_cbba_snapshot(round_id: int, sender_id: int, winners: list[int],
                         bids: list[float], timestamps: list[float]) -> tuple[bytes, ...]:
    """Encode full y,z,s vectors, splitting whole-snapshot digest-bound frames."""
    payload = json.dumps({"z": winners, "y": bids, "s": timestamps},
                         allow_nan=False, separators=(",", ":")).encode("utf-8")
    chunk_size = MAX_FRAME_BYTES - CBBA_HEADER.size
    chunks = [payload[i:i + chunk_size] for i in range(0, len(payload), chunk_size)]
    if len(chunks) > 65535:
        raise ProtocolError(Diagnostic("multitask_wire", "encode_cbba_snapshot",
                                       "data", "E9M_TOO_MANY_FRAGMENTS",
                                       expected="<=65535", actual=len(chunks)))
    digest = hashlib.sha256(payload).digest()
    return tuple(CBBA_HEADER.pack(b"CBB1", round_id, sender_id, idx,
                                  len(chunks), digest) + chunk
                 for idx, chunk in enumerate(chunks))


def decode_cbba_snapshot(frames: list[bytes] | tuple[bytes, ...], *,
                         round_id: int, sender_id: int, robots: int,
                         tasks: int) -> dict | None:
    """Incomplete snapshot is ignored, never partially applied to a receiver."""
    if not frames:
        return None
    pieces: dict[int, bytes] = {}
    expected_total = None
    expected_digest = None
    for frame in frames:
        if len(frame) <= CBBA_HEADER.size or len(frame) > MAX_FRAME_BYTES:
            return None
        magic, epoch, sender, idx, total, digest = CBBA_HEADER.unpack_from(frame)
        if (magic != b"CBB1" or epoch != round_id or sender != sender_id or
                total == 0 or idx >= total or idx in pieces or
                (expected_total is not None and total != expected_total) or
                (expected_digest is not None and digest != expected_digest)):
            return None
        expected_total, expected_digest = total, digest
        pieces[idx] = frame[CBBA_HEADER.size:]
    if len(pieces) != expected_total:
        return None
    payload = b"".join(pieces[i] for i in range(expected_total))
    if hashlib.sha256(payload).digest() != expected_digest:
        return None
    try:
        obj = json.loads(payload)
    except (ValueError, UnicodeDecodeError):
        return None
    if (not isinstance(obj, dict) or set(obj) != {"z", "y", "s"} or
            not all(isinstance(obj[x], list) for x in ("z", "y", "s")) or
            len(obj["z"]) != tasks or len(obj["y"]) != tasks or
            len(obj["s"]) != robots or
            any(type(z) is not int or z < -1 or z >= robots for z in obj["z"]) or
            any(type(y) not in (int, float) or not 0 <= y < 1e10 for y in obj["y"]) or
            any(type(s) not in (int, float) or not 0 <= s < 1e12 for s in obj["s"])):
        return None
    return obj


def encode_small_packet(phase: str, task_id: int, sender: int,
                        candidate: int, value: float) -> bytes:
    magics = {"voting_cost": b"COST", "voting_vote": b"VOTE",
              "voting_score": b"SCOR", "voting_commit": b"CMIT"}
    return SMALL_HEADER.pack(magics[phase], task_id, sender, candidate, float(value))


def decode_small_packet(phase: str, frame: bytes, task_id: int,
                        sender: int) -> tuple[int, float]:
    if len(frame) != SMALL_HEADER.size:
        raise ProtocolError(Diagnostic("multitask_wire", "decode_small_packet",
                                       "data", "E9M_INVALID_SMALL_PACKET_SIZE",
                                       expected=SMALL_HEADER.size, actual=len(frame)))
    magic, task, peer, candidate, value = SMALL_HEADER.unpack(frame)
    expected = {"voting_cost": b"COST", "voting_vote": b"VOTE",
                "voting_score": b"SCOR", "voting_commit": b"CMIT"}[phase]
    if (magic, task, peer) != (expected, task_id, sender):
        raise ProtocolError(Diagnostic("multitask_wire", "decode_small_packet",
                                       "contract", "E9M_SMALL_PACKET_MISMATCH",
                                       expected=(expected, task_id, sender),
                                       actual=(magic, task, peer)))
    return candidate, value


class E9MChannel:
    """One physically charged broadcast per emitted frame; receiver drops independent."""

    def __init__(self, *, robots: int, timing: WifiCausalTimingSampler,
                 loss_seed: int, method: str):
        self.robots = robots
        self.timing = timing
        self.loss = BernoulliLossSampler(loss_seed)
        self.method = method
        self.clock_ms = 0.0
        self._phase_end = 0.0
        self._ledger: dict[str, dict[str, int]] = defaultdict(lambda: {
            "sender_sends": 0, "sender_bytes": 0, "receiver_attempts": 0,
            "receiver_delivered": 0, "receiver_dropped": 0,
        })

    def begin_phase(self) -> None:
        self._phase_end = self.clock_ms
        self.timing.set_epoch_start_ms(self.clock_ms)

    def send(self, *, phase: str, sender: int, frame: bytes, round_id: int,
             frame_id: int, p_loss: float, receivers: tuple[int, ...] | None = None
             ) -> dict[int, bytes]:
        validate_packet_loss_probability(p_loss)
        if not 0 < len(frame) <= MAX_FRAME_BYTES:
            raise ProtocolError(Diagnostic("multitask_wire", "E9MChannel.send",
                                           "contract", "E9M_PACKET_TOO_LARGE",
                                           expected="1..1200B", actual=len(frame)))
        key = f"e9m:{self.method}:{phase}:{round_id}:{sender}:{frame_id}"
        latency = self.timing.sample_packet_ms(
            key=key, phase=phase, sender_id=sender, receiver_id=-1,
            send_time_ms=0.0, payload_bytes=len(frame))
        arrival = self.clock_ms + latency
        self._phase_end = max(self._phase_end, arrival)
        ledger = self._ledger[phase]
        ledger["sender_sends"] += 1
        ledger["sender_bytes"] += len(frame)
        delivered: dict[int, bytes] = {}
        for receiver in (receivers if receivers is not None else tuple(range(self.robots))):
            if receiver == sender:
                continue  # local observations are free, never wireless packets
            ledger["receiver_attempts"] += 1
            ok = self.loss.is_delivered(f"{key}:receiver={receiver}", p_loss)
            ledger["receiver_delivered" if ok else "receiver_dropped"] += 1
            if ok:
                delivered[receiver] = frame
        return delivered

    def end_phase(self) -> None:
        self.clock_ms = self._phase_end

    def ledger(self) -> dict[str, dict[str, int]]:
        return {phase: dict(values) for phase, values in sorted(self._ledger.items())}

    def audit_physical_bytes(self) -> None:
        charged = sum(x["sender_bytes"] for x in self._ledger.values())
        physical = int(self.timing.summarize_network()["application_sender_bytes"])
        if physical != charged:
            raise ProtocolError(Diagnostic("multitask_wire", "E9MChannel.audit_physical_bytes",
                                           "contract", "E9M_NATIVE_BYTE_MISMATCH",
                                           expected=physical, actual=charged))


def announce_tasks(channel: E9MChannel,
                   task_positions: tuple[tuple[float, float], ...]) -> tuple[tuple[tuple[float, float], ...], ...]:
    """External reliable actual task frames, decoded separately by every agent."""
    from .task_information import encode_task_announcement, decode_task_announcement
    frames = encode_task_announcement(task_positions)
    inbox: list[list[bytes | None]] = [[None] * len(frames) for _ in range(channel.robots)]
    channel.begin_phase()
    for idx, frame in enumerate(frames):
        delivered = channel.send(phase="task_announcement", sender=channel.robots,
                                 frame=frame, round_id=0, frame_id=idx, p_loss=0.0)
        for receiver, payload in delivered.items():
            inbox[receiver][idx] = payload
    channel.end_phase()
    local_tasks = []
    for receiver, parts in enumerate(inbox):
        if any(part is None for part in parts):
            raise ProtocolError(Diagnostic("multitask_wire", "announce_tasks",
                                           "dependency", "E9M_TASK_BROADCAST_INCOMPLETE",
                                           expected=len(frames), actual=sum(p is not None for p in parts),
                                           details=f"robot={receiver}"))
        decoded = decode_task_announcement(tuple(p for p in parts if p is not None),
                                           expected_tasks=len(task_positions))
        local_tasks.append(tuple((t.x, t.y) for t in decoded))
    return tuple(local_tasks)
