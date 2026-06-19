#!/usr/bin/env python3
"""Record lifecycle status for an agent-loop repair task."""

from hermes_cli.agent_loop_capture import repair_main


if __name__ == "__main__":
    raise SystemExit(repair_main())
