#!/usr/bin/env python3
"""Fail-closed merge guard for AI-authored PRs."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hermes_cli.agent_loop_pr_guard import main

if __name__ == "__main__":
    raise SystemExit(main())
