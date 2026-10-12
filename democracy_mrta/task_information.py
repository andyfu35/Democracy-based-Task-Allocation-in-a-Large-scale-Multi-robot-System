"""E9C-1 actual wire-encoded common task data and optional peer-position exchange.

Task origin is an external announcement source, NOT a centralized allocator.
Each robot retains its own pose locally. Other robot poses require real SENDs.
Transport reuses the original communication event/loss owners; missing data
is never silently filled using the simulator's omniscient scenario.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import struct

from .coordination import (
    CommunicationEvent, DeliveryObservation,
    _broadcast_event, _lossy_broadcast_deliveries,
)
from .diagnostics import Diagnostic, ProtocolError
from .network import validate_packet_loss_probability


OWNER = "democracy_mrta.task_information"
WIRE_VERSION = 1
MAX_APPLICATION_PACKET_BYTES = 1200
WIRE_HEADER = struct.Struct("<4sHHHHI")  # 16 B: magic, version, index, total, count, epoch
TASK_RECORD = struct.Struct("<IddIII")   # 32 B: ID, x, y, type, priority, deadline ms
ROBOT_RECORD = struct.Struct("<Idd")    # 20 B: ID, x, y
TASKS_PER_PACKET = (MAX_APPLICATION_PACKET_BYTES - WIRE_HEADER.size) // TASK_RECORD.size


@dataclass(frozen=True)
class TaskRecord:
    task_id: int
    x: float
    y: float
    task_type: int = 0
    priority: int = 1
    deadline_ms: int = 0


@dataclass(frozen=True)
class TaskInformationTrace:
    per_robot_tasks: tuple[tuple[TaskRecord, ...], ...]
    events: tuple[CommunicationEvent, ...]
    deliveries: tuple[DeliveryObservation, ...]
    serialized_packets: tuple[bytes, ...]

    @property
    def sender_bytes(self) -> int:
        return sum(event.payload_bytes for event in self.events)


@dataclass(frozen=True)
class RobotPoseTrace:
    per_robot_positions: tuple[tuple[tuple[float, float], ...], ...]
    events: tuple[CommunicationEvent, ...]
    deliveries: tuple[DeliveryObservation, ...]

    @property
    def sender_bytes(self) -> int:
        return sum(event.payload_bytes for event in self.events)


def encode_task_announcement(
    task_positions: tuple[tuple[float, float], ...],
) -> tuple[bytes, ...]:
    """Real little-endian wire packets, limited to 1,200 application bytes."""
    if (not task_positions or len(task_positions) > 65535
        or any(len(position) != 2 or not all(math.isfinite(x) for x in position)
               for position in task_positions)):
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="encode_task_announcement",
            category="data", code="INVALID_TASK_ANNOUNCEMENT_SOURCE",
            expected="1..65535 tasks, each with two finite x/y coordinates",
            actual=task_positions[:4],
        ))
    total = (len(task_positions) + TASKS_PER_PACKET - 1) // TASKS_PER_PACKET
    packets = []
    for frame_id in range(total):
        start = frame_id * TASKS_PER_PACKET
        positions = task_positions[start:start + TASKS_PER_PACKET]
        header = WIRE_HEADER.pack(
            b"TASK", WIRE_VERSION, frame_id, total, len(positions), 0,
        )
        records = b"".join(
            TASK_RECORD.pack(task_id, float(x), float(y), 0, 1, 0)
            for task_id, (x, y) in enumerate(positions, start)
        )
        packet = header + records
        if len(packet) > MAX_APPLICATION_PACKET_BYTES:
            raise ProtocolError(Diagnostic(
                owner=OWNER, function="encode_task_announcement",
                category="contract", code="TASK_PACKET_EXCEEDS_LIMIT",
                expected=f"<= {MAX_APPLICATION_PACKET_BYTES} Bytes",
                actual=len(packet),
            ))
        packets.append(packet)
    return tuple(packets)


def decode_task_announcement(
    frames: tuple[bytes, ...], *, expected_tasks: int,
) -> tuple[TaskRecord, ...]:
    """Decode only physically received frames; never infer missing tasks."""
    if not frames:
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="decode_task_announcement",
            category="dependency", code="TASK_FRAMES_INCOMPLETE",
            expected="all contiguous task-information packets",
            actual=0,
        ))
    slots: list[TaskRecord | None] = [None] * expected_tasks
    for observed_index, frame in enumerate(frames):
        if len(frame) < WIRE_HEADER.size:
            raise ProtocolError(Diagnostic(
                owner=OWNER, function="decode_task_announcement",
                category="data", code="TASK_FRAME_MALFORMED",
                expected=f"header >= {WIRE_HEADER.size} bytes", actual=len(frame),
            ))
        magic, version, frame_id, total, count, epoch = WIRE_HEADER.unpack_from(frame)
        if (magic != b"TASK" or version != WIRE_VERSION or epoch != 0
            or total != len(frames) or frame_id != observed_index
            or len(frame) != WIRE_HEADER.size + count * TASK_RECORD.size):
            raise ProtocolError(Diagnostic(
                owner=OWNER, function="decode_task_announcement",
                category="data", code="TASK_FRAME_MALFORMED",
                expected="TASK v1 ordered frames, zero epoch, exact record byte length",
                actual=(magic, version, frame_id, total, count, epoch, len(frame)),
            ))
        for record_index in range(count):
            offset = WIRE_HEADER.size + record_index * TASK_RECORD.size
            task_id, x, y, kind, priority, deadline = TASK_RECORD.unpack_from(frame, offset)
            if (task_id >= expected_tasks or slots[task_id] is not None
                or not math.isfinite(x) or not math.isfinite(y)):
                raise ProtocolError(Diagnostic(
                    owner=OWNER, function="decode_task_announcement",
                    category="data", code="TASK_RECORD_INVALID",
                    expected="unique task IDs [0,T) with finite coordinates",
                    actual=(task_id, x, y),
                ))
            slots[task_id] = TaskRecord(task_id, x, y, kind, priority, deadline)
    if any(item is None for item in slots):
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="decode_task_announcement",
            category="dependency", code="TASK_RECORDS_MISSING",
            expected=expected_tasks,
            actual=sum(item is not None for item in slots),
        ))
    return tuple(slots)  # type: ignore[return-value]


def broadcast_task_information(
    *,
    task_positions: tuple[tuple[float, float], ...],
    num_robots: int,
    sampler,
    loss_sampler,
    p_loss: float,
    phase_timeout_ms: float,
) -> TaskInformationTrace:
    """Actual external-sender broadcast; each receiver decodes own delivered data."""
    validate_packet_loss_probability(p_loss)
    frames = encode_task_announcement(task_positions)
    inbox: list[list[bytes | None]] = [[None] * len(frames) for _ in range(num_robots)]
    events: list[CommunicationEvent] = []
    deliveries: list[DeliveryObservation] = []
    for frame_id, packet in enumerate(frames):
        # External announcer is identified as robot count, not as a voting robot.
        event = _broadcast_event(
            phase="task_announcement", sender_id=num_robots, task_id=frame_id,
            send_time_ms=0.0, payload_bytes=len(packet), sampler=sampler,
        )
        events.append(event)
        observations = _lossy_broadcast_deliveries(
            event=event, num_robots=num_robots, loss_sampler=loss_sampler,
            p_loss=p_loss, round_id=0,
        )
        deliveries.extend(observations)
        for observation in observations:
            if (observation.delivered and observation.arrival_time_ms is not None
                and observation.arrival_time_ms <= phase_timeout_ms):
                inbox[observation.receiver_id][frame_id] = packet
    for robot_id, received in enumerate(inbox):
        if any(frame is None for frame in received):
            raise ProtocolError(Diagnostic(
                owner=OWNER, function="broadcast_task_information",
                category="dependency", code="TASK_ANNOUNCEMENT_INCOMPLETE",
                expected={"robot_id": robot_id, "frames": len(frames)},
                actual={"received_frames": sum(frame is not None for frame in received)},
                details="No hidden simulator task information supplied to a missing receiver",
            ))
    local = tuple(
        decode_task_announcement(tuple(frame for frame in received if frame is not None),
                                 expected_tasks=len(task_positions))
        for received in inbox
    )
    return TaskInformationTrace(local, tuple(events), tuple(deliveries), frames)


def broadcast_robot_positions(
    *, robot_positions: tuple[tuple[float, float], ...],
    sampler, loss_sampler, p_loss: float, phase_timeout_ms: float,
) -> RobotPoseTrace:
    """Each robot SENDs its OWN 36-byte pose packet; receivers never get it free."""
    validate_packet_loss_probability(p_loss)
    robots = len(robot_positions)
    known: list[dict[int, tuple[float, float]]] = [
        {i: robot_positions[i]} for i in range(robots)
    ]
    events: list[CommunicationEvent] = []
    deliveries: list[DeliveryObservation] = []
    for sender_id, (x, y) in enumerate(robot_positions):
        if not math.isfinite(x) or not math.isfinite(y):
            raise ProtocolError(Diagnostic(
                owner=OWNER, function="broadcast_robot_positions",
                category="data", code="INVALID_ROBOT_POSITION",
                expected="finite local x/y", actual=(sender_id, x, y),
            ))
        packet = (
            WIRE_HEADER.pack(b"POSE", WIRE_VERSION, 0, 1, 1, 0)
            + ROBOT_RECORD.pack(sender_id, x, y)
        )
        event = _broadcast_event(
            phase="robot_pose", sender_id=sender_id, send_time_ms=0.0,
            payload_bytes=len(packet), sampler=sampler,
        )
        events.append(event)
        observations = _lossy_broadcast_deliveries(
            event=event, num_robots=robots,
            loss_sampler=loss_sampler, p_loss=p_loss, round_id=0,
        )
        deliveries.extend(observations)
        for observation in observations:
            if (observation.delivered and observation.arrival_time_ms is not None
                and observation.arrival_time_ms <= phase_timeout_ms):
                header = WIRE_HEADER.unpack_from(packet)
                peer_id, px, py = ROBOT_RECORD.unpack_from(packet, WIRE_HEADER.size)
                if header != (b"POSE", WIRE_VERSION, 0, 1, 1, 0) or peer_id != sender_id:
                    raise ProtocolError(Diagnostic(
                        owner=OWNER, function="broadcast_robot_positions",
                        category="contract", code="POSE_PACKET_INVALID",
                        expected=sender_id, actual=(header, peer_id),
                    ))
                known[observation.receiver_id][peer_id] = (px, py)
    for receiver_id, peers in enumerate(known):
        if len(peers) != robots:
            raise ProtocolError(Diagnostic(
                owner=OWNER, function="broadcast_robot_positions",
                category="dependency", code="ROBOT_POSE_VIEWS_INCOMPLETE",
                expected={"receiver_id": receiver_id, "robots": robots},
                actual={"received": len(peers)},
                details="Unavailable peer positions are never reconstructed from ground truth",
            ))
    return RobotPoseTrace(
        tuple(tuple(peers[i] for i in range(robots)) for peers in known),
        tuple(events), tuple(deliveries),
    )


def reconstruct_local_cost_rows(
    *, local_robot_positions: tuple[tuple[float, float], ...],
    announced_tasks_by_robot: tuple[tuple[TaskRecord, ...], ...],
) -> tuple[tuple[float, ...], ...]:
    """Each robot computes only its own cost row from locally received tasks."""
    if len(local_robot_positions) != len(announced_tasks_by_robot):
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="reconstruct_local_cost_rows",
            category="data", code="TASK_ROBOT_COUNT_MISMATCH",
            expected=len(local_robot_positions), actual=len(announced_tasks_by_robot),
        ))
    return tuple(
        tuple(math.dist(local_robot_positions[i], (task.x, task.y)) for task in tasks)
        for i, tasks in enumerate(announced_tasks_by_robot)
    )
