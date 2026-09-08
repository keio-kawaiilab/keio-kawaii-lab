#!/usr/bin/env python3
from __future__ import annotations

# Keep the established release-boundary implementation intact in the core
# module, then apply P1-5 as the final UI correctness guard.  The wrapper keeps
# existing imports working while making the new guard impossible for publishers
# that already call strip_schedule_explanations.py to bypass.
from strip_schedule_explanations_core import *  # noqa: F401,F403
import strip_schedule_explanations_core as _core
import fix_missing_application_start_ui as _missing_start


def main() -> int:
    result = _core.main()
    if result != 0:
        return result
    return _missing_start.main()


if __name__ == "__main__":
    raise SystemExit(main())
