#!/usr/bin/env python3
from __future__ import annotations

# Keep the established release-boundary implementation intact in the core
# module, then apply public-view correctness guards at the final boundary. The
# wrapper keeps existing imports working while making these guards impossible
# for publishers that already call strip_schedule_explanations.py to bypass.
from pathlib import Path

from strip_schedule_explanations_core import *  # noqa: F401,F403
import strip_schedule_explanations_core as _core
import normalize_public_event_titles as _titles
import normalize_external_event_public_view as _external_view
import fix_missing_application_start_ui as _missing_start
import guard_schedule_latest_data_loading as _latest_data
import guard_performance_runtime as _performance_runtime
import subprocess
from guard_candy_tune_tour_integrity import validate_data as _validate_candy_data
from guard_candy_tune_tour_integrity import validate_html as _validate_candy_html


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
    result = _latest_data.main()
    if result != 0:
        return result

    # Final publication boundary: every publisher already runs this wrapper.
    # Reject a refresh before commit if the official 23-date CANDY TUNE tour
    # disappears from canonical JSON or any upcoming tour card is lost from
    # the generated public snapshot.
    _validate_candy_data(Path("data/live-events.json"))
    _validate_candy_html(Path("schedule.html"), __import__("datetime").date.today().isoformat())
    _performance_runtime.main()
    subprocess.run(["node", "scripts/test_performance_runtime.js"], check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
