#!/usr/bin/env python3
from __future__ import annotations

# Keep the established release-boundary implementation intact in the core
# module, then apply public-view correctness guards at the final boundary. The
# wrapper keeps existing imports working while making these guards impossible
# for publishers that already call strip_schedule_explanations.py to bypass.
from strip_schedule_explanations_core import *  # noqa: F401,F403
import strip_schedule_explanations_core as _core
import normalize_public_event_titles as _titles
import normalize_external_event_public_view as _external_view
import fix_missing_application_start_ui as _missing_start
import guard_schedule_latest_data_loading as _latest_data


def main() -> int:
    result = _core.main()
    if result != 0:
        return result
    result = _titles.main()
    if result != 0:
        return result
    result = _external_view.main()
    if result != 0:
        return result
    result = _missing_start.main()
    if result != 0:
        return result
    return _latest_data.main()


if __name__ == "__main__":
    raise SystemExit(main())
