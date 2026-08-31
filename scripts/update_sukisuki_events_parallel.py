#!/usr/bin/env python3
"""Compatibility entrypoint for SUKISUKI collection.

The workflow used a parallel filename after the implementation was consolidated
back into update_sukisuki_events.py. Accept the old --workers flag and delegate
to the maintained collector instead of failing before collection starts.
"""
from __future__ import annotations

import argparse

import update_sukisuki_events


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the maintained SUKISUKI collector")
    parser.add_argument("--workers", type=int, default=1, help="Compatibility option; collection is handled safely by the maintained collector")
    parser.parse_args()
    return update_sukisuki_events.main()


if __name__ == "__main__":
    raise SystemExit(main())
