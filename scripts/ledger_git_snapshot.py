#!/usr/bin/env python3
"""Append a machine git snapshot to an Evidence Ledger."""

from hermes_cli.agent_loop_capture import git_main


if __name__ == "__main__":
    raise SystemExit(git_main())
