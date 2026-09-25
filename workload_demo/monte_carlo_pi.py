#!/usr/bin/env python3
import argparse
import json
import random
from pathlib import Path


def estimate_pi(samples: int, seed: int) -> float:
    if samples < 1:
        raise ValueError("samples must be positive")
    generator = random.Random(seed)
    inside = 0
    for _ in range(samples):
        x = generator.random()
        y = generator.random()
        if x * x + y * y <= 1.0:
            inside += 1
    return 4.0 * inside / samples


def write_result(path: Path, samples: int, seed: int) -> float:
    estimate = estimate_pi(samples, seed)
    path.write_text(json.dumps({"samples": samples, "seed": seed, "pi": estimate}) + "\n")
    return estimate


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples", type=int, default=250_000)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    write_result(args.output, args.samples, args.seed)


if __name__ == "__main__":
    main()
