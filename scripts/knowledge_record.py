#!/usr/bin/env python3
"""Record durable knowledge assets from agent-loop runs."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hermes_cli.agent_loop_knowledge import main

if __name__ == "__main__":
    raise SystemExit(main())
