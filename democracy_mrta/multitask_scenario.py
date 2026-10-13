"""E9M capacity-aware geometry and path-dependent discounted reward owner."""
from __future__ import annotations

from dataclasses import dataclass
import math
import random

from .diagnostics import Diagnostic, ProtocolError


@dataclass(frozen=True)
class MultiTaskScene:
    seed: int
    robot_positions: tuple[tuple[float, float], ...]
    task_positions: tuple[tuple[float, float], ...]
    capacity: int

    @property
    def robots(self) -> int:
        return len(self.robot_positions)

    @property
    def tasks(self) -> int:
        return len(self.task_positions)


def validate_multitask_shape(robots: int, tasks: int, capacity: int, world_size: float) -> None:
    if (type(robots) is not int or type(tasks) is not int or type(capacity) is not int
            or robots <= 0 or tasks <= 0 or capacity <= 0 or tasks > robots * capacity
            or not math.isfinite(world_size) or world_size <= 0):
        raise ProtocolError(Diagnostic(
            owner="multitask_scenario", function="validate_multitask_shape",
            category="data", code="E9M_INVALID_CAPACITY_SCENE",
            expected="positive R,T,C and T<=R*C, finite world_size>0",
            actual={"robots": robots, "tasks": tasks, "capacity": capacity,
                    "world_size": world_size},
        ))


def generate_multitask_scene(seed: int, robots: int, tasks: int, capacity: int,
                             world_size: float = 100.0) -> MultiTaskScene:
    validate_multitask_shape(robots, tasks, capacity, world_size)
    rng = random.Random(seed)
    return MultiTaskScene(
        seed=seed,
        robot_positions=tuple((rng.uniform(0, world_size), rng.uniform(0, world_size))
                              for _ in range(robots)),
        task_positions=tuple((rng.uniform(0, world_size), rng.uniform(0, world_size))
                             for _ in range(tasks)),
        capacity=capacity,
    )


def route_metrics(scene: MultiTaskScene, robot_id: int,
                  route: tuple[int, ...] | list[int]) -> tuple[float, float]:
    """Return distance in metres and discounted arrival reward; open route, 1m/s."""
    position = scene.robot_positions[robot_id]
    distance = 0.0
    score = 0.0
    for task_id in route:
        point = scene.task_positions[task_id]
        distance += math.dist(position, point)
        score += 100.0 * (0.999 ** distance)
        position = point
    return distance, score


def best_insertion(scene: MultiTaskScene, robot_id: int,
                   route: tuple[int, ...] | list[int], task_id: int) -> tuple[float, int]:
    """True marginal increase in total discounted route score (not nearest cost)."""
    old_score = route_metrics(scene, robot_id, route)[1]
    best_delta, best_position = -math.inf, 0
    for position in range(len(route) + 1):
        candidate = list(route)
        candidate.insert(position, task_id)
        delta = route_metrics(scene, robot_id, candidate)[1] - old_score
        if delta > best_delta + 1e-10:
            best_delta, best_position = delta, position
    return best_delta, best_position
