"""Run the whole offline pipeline: dataset -> train -> evaluate.

    python scripts/run_pipeline.py
    python scripts/run_pipeline.py --rows 15000 --seed 7
    python scripts/run_pipeline.py --skip-dataset

Each stage runs in its own interpreter (the same way ``python -m ml.train``
would), so a failure stops the chain with the exact error the stage printed.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def run(module_and_args) -> bool:
    label = " ".join(module_and_args)
    print("\n=== %s ===" % label)
    start = time.time()
    result = subprocess.run([sys.executable, "-m"] + module_and_args, cwd=str(ROOT))
    elapsed = time.time() - start
    print("=== %s finished in %.1fs (exit %d) ===" % (label, elapsed, result.returncode))
    return result.returncode == 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", type=int, default=12000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--skip-dataset", action="store_true",
                        help="reuse the existing CSV instead of regenerating it")
    parser.add_argument("--skip-evaluate", action="store_true",
                        help="train only; do not render the report figures")
    args = parser.parse_args()

    stages = []
    if not args.skip_dataset:
        stages.append(["ml.generate_dataset", "--rows", str(args.rows),
                       "--seed", str(args.seed)])
    stages.append(["ml.train", "--seed", str(args.seed)])
    if not args.skip_evaluate:
        stages.append(["ml.evaluate"])

    for stage in stages:
        if not run(stage):
            print("\nPipeline stopped: the stage above failed.")
            return 1

    print("\nPipeline complete. Models are in ml/artifacts, figures in reports/graphs.")
    print("Start the dashboard with: run.bat  (or: python -m backend.app)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
