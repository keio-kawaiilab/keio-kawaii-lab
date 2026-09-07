#!/usr/bin/env python3
"""Require review when the published timetable changes; never reuse old identities."""
import hashlib
import json
import tempfile
from pathlib import Path

from keikyu_official_pdf import download_official_pdf
from keikyu_internal_runtime import NETWORK

if __name__ == '__main__':
    expected = json.loads(NETWORK.read_text())['sourceSha256']
    with tempfile.TemporaryDirectory(prefix='keikyu-source-') as folder:
        raw = download_official_pdf(Path(folder) / 'schedule_all.pdf')
    if hashlib.sha256(raw).hexdigest() != expected:
        raise RuntimeError('Keikyu official timetable changed: review and rebuild before publishing')
    print('Keikyu published source revision verified:', expected)
