#!/usr/bin/env python3
"""Repair an AI-authored PR until CI is green, then merge safely."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hermes_cli.agent_loop_pr_ci_loop import main

if __name__ == "__main__":
    raise SystemExit(main())
