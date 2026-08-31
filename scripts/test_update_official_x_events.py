"""Compatibility test entrypoint used by the distributed workflow.

Import both real suites so the historical workflow filename exercises the
current special-event and birthday-specific X collectors.
"""
from test_update_official_x_special_events import *  # noqa: F401,F403
from test_update_official_x_birthday_events import *  # noqa: F401,F403
