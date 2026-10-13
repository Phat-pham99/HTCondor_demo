#!/usr/bin/env python3
"""CPU-bound 2D heat diffusion (Jacobi iteration) with a wall-clock budget."""
import argparse
import json
import random
import time
from pathlib import Path

HOT_EDGE = 100.0
ALPHA = 0.2  # stable for the explicit scheme while <= 0.25


def initial_state(size: int, seed: int):
    if size < 3:
        raise ValueError("size must be at least 3")
    grid = [[0.0] * size for _ in range(size)]
    grid[0] = [HOT_EDGE] * size
    generator = random.Random(seed)
    sources = {}  # row -> {column: fixed temperature}
    for _ in range(max(1, size // 25)):
        i = generator.randrange(1, size - 1)
        j = generator.randrange(1, size - 1)
        sources.setdefault(i, {})[j] = generator.uniform(-50.0, 150.0)
        grid[i][j] = sources[i][j]
    return grid, sources


def step(grid, sources):
    size = len(grid)
    new = [row[:] for row in grid]
    residual = 0.0
    for i in range(1, size - 1):
        up, row, down = grid[i - 1], grid[i], grid[i + 1]
        out = new[i]
        fixed = sources.get(i)
        for j in range(1, size - 1):
            if fixed and j in fixed:
                continue
            centre = row[j]
            lap = up[j] + down[j] + row[j - 1] + row[j + 1]
            value = centre + ALPHA * (lap - 4.0 * centre)
            change = abs(value - centre)
            if change > residual:
                residual = change
            out[j] = value
    return new, residual


def interior_stats(grid):
    cells = [v for row in grid[1:-1] for v in row[1:-1]]
    return sum(cells) / len(cells), max(cells), min(cells)


def simulate(size, seed, duration, report_every, tolerance):
    if duration <= 0:
        raise ValueError("duration must be positive")
    grid, sources = initial_state(size, seed)
    start = time.monotonic()
    next_report = report_every
    iterations = 0
    residual = float("inf")
    while True:
        grid, residual = step(grid, sources)
        iterations += 1
        elapsed = time.monotonic() - start
        if elapsed >= next_report:
            mean, _, _ = interior_stats(grid)
            print(
                f"[{elapsed:6.1f}s] iteration={iterations}"
                f" residual={residual:.3e} mean={mean:.4f}",
                flush=True,
            )
            next_report += report_every
        if elapsed >= duration:
            break
    mean, high, low = interior_stats(grid)
    centre = grid[size // 2][size // 2]
    return {
        "size": size,
        "seed": seed,
        "heat_sources": sum(len(cols) for cols in sources.values()),
        "duration_budget_seconds": duration,
        "wall_seconds": round(time.monotonic() - start, 3),
        "cpu_seconds": round(time.process_time(), 3),
        "iterations": iterations,
        "final_residual": residual,
        "converged": residual < tolerance,
        "mean_temperature": mean,
        "max_temperature": high,
        "min_temperature": low,
        "centre_temperature": centre,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--size", type=int, default=150)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--duration", type=float, default=300.0)
    parser.add_argument("--report-every", type=float, default=30.0)
    parser.add_argument("--tolerance", type=float, default=1e-6)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = simulate(
        args.size, args.seed, args.duration,
        args.report_every, args.tolerance,
    )
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(f"done: {result['iterations']} iterations", flush=True)


if __name__ == "__main__":
    main()
