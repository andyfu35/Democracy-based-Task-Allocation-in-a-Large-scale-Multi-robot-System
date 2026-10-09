from __future__ import annotations

from dataclasses import dataclass
import math
import random


@dataclass(frozen=True)
class Scenario:
    seed: int
    robot_positions: tuple[tuple[float, float], ...]
    task_positions: tuple[tuple[float, float], ...]
    cost_matrix: tuple[tuple[float, ...], ...]

    @property
    def num_robots(self) -> int:
        return len(self.robot_positions)

    @property
    def num_tasks(self) -> int:
        return len(self.task_positions)


def validate_scenario_shape(num_robots: int, num_tasks: int) -> None:
    if num_robots <= 0:
        raise ValueError("num_robots must be positive")
    if num_tasks <= 0:
        raise ValueError("num_tasks must be positive")
    if num_tasks > num_robots:
        raise ValueError(
            "E0 currently requires num_tasks <= num_robots for one-to-one allocation"
        )


def compute_euclidean_cost_matrix(
    robot_positions: tuple[tuple[float, float], ...],
    task_positions: tuple[tuple[float, float], ...],
) -> tuple[tuple[float, ...], ...]:
    return tuple(
        tuple(math.dist(robot_position, task_position) for task_position in task_positions)
        for robot_position in robot_positions
    )


def generate_e0_scenario(
    seed: int,
    num_robots: int,
    num_tasks: int,
    world_size: float = 100.0,
) -> Scenario:
    validate_scenario_shape(num_robots, num_tasks)
    if world_size <= 0:
        raise ValueError("world_size must be positive")

    rng = random.Random(seed)
    robot_positions = tuple(
        (rng.uniform(0.0, world_size), rng.uniform(0.0, world_size))
        for _ in range(num_robots)
    )
    task_positions = tuple(
        (rng.uniform(0.0, world_size), rng.uniform(0.0, world_size))
        for _ in range(num_tasks)
    )
    cost_matrix = compute_euclidean_cost_matrix(robot_positions, task_positions)
    return Scenario(
        seed=seed,
        robot_positions=robot_positions,
        task_positions=task_positions,
        cost_matrix=cost_matrix,
    )
