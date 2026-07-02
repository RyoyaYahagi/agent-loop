#!/usr/bin/env python3
"""Append an AI/controller decision log to an Evidence Ledger."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hermes_cli.agent_loop_decision_log import main

if __name__ == "__main__":
    raise SystemExit(main())
