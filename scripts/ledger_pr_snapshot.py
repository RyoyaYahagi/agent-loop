#!/usr/bin/env python3
"""Append a machine GitHub PR snapshot to an Evidence Ledger."""

from hermes_cli.agent_loop_capture import pr_main


if __name__ == "__main__":
    raise SystemExit(pr_main())
