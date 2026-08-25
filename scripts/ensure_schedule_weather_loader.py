#!/usr/bin/env python3
from pathlib import Path
import re

path = Path("schedule.html")
text = path.read_text(encoding="utf-8")

loader = '<script src="./schedule-weather.js?v=202608260500" data-schedule-weather-direct></script>'

# Remove any prior direct loader so the cache-busting version is deterministic.
text = re.sub(
    r'\n?<script\s+src="\./schedule-weather\.js\?v=[^"]+"\s+data-schedule-weather-direct></script>',
    '',
    text,
)

anchor = '<script src="./train-status.js"></script>'
if anchor in text:
    text = text.replace(anchor, loader + '\n' + anchor, 1)
elif '</body>' in text:
    text = text.replace('</body>', loader + '\n</body>', 1)
else:
    raise SystemExit('Could not find script insertion point in schedule.html')

path.write_text(text, encoding="utf-8")
print('Ensured direct schedule weather loader')
