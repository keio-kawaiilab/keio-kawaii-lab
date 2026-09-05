from pathlib import Path

path = Path("scripts/strip_schedule_explanations.py")
text = path.read_text(encoding="utf-8")

anchor = 'BAND_KEY_TAIL = "String(e.applyEnd||\'\'),performanceTitleKey(e)].join(\'|\')"\n'
addition = '''BAND_KEY_TAIL = "String(e.applyEnd||''),performanceTitleKey(e)].join('|')"
APPLICATION_BAND_MARKERS = (
    "function applicationBandSubjectKey(e)",
    "function applicationBandKey(e,index)",
    "applicationBandSubjectKey(e)",
)
'''
if "APPLICATION_BAND_MARKERS" not in text:
    if anchor not in text:
        raise SystemExit("band key anchor not found")
    text = text.replace(anchor, addition, 1)

function_anchor = '''def ensure_visible_title_performance_identity(page: str) -> str:\n'''
helper = '''def has_application_band_identity(page: str) -> bool:
    return BAND_KEY_TAIL in page or all(marker in page for marker in APPLICATION_BAND_MARKERS)


'''
if "def has_application_band_identity" not in text:
    if function_anchor not in text:
        raise SystemExit("identity function anchor not found")
    text = text.replace(function_anchor, helper + function_anchor, 1)

old = '''    if BAND_KEY_TAIL in fixed:
        return fixed
    if LEGACY_BAND_KEY_TAIL not in fixed:
        raise RuntimeError("schedule application-band identity changed; title dedupe could not be installed")
    return fixed.replace(LEGACY_BAND_KEY_TAIL, BAND_KEY_TAIL, 1)
'''
new = '''    if has_application_band_identity(fixed):
        return fixed
    if LEGACY_BAND_KEY_TAIL not in fixed:
        raise RuntimeError("schedule application-band identity changed; title dedupe could not be installed")
    return fixed.replace(LEGACY_BAND_KEY_TAIL, BAND_KEY_TAIL, 1)
'''
if old in text:
    text = text.replace(old, new, 1)
elif new not in text:
    raise SystemExit("application-band compatibility block not found")

old_final = '''    if not has_visible_title_performance_identity(page) or BAND_KEY_TAIL not in page:
        raise RuntimeError("visible-title performance dedupe is missing from schedule renderer")
'''
new_final = '''    if not has_visible_title_performance_identity(page) or not has_application_band_identity(page):
        raise RuntimeError("visible-title performance dedupe is missing from schedule renderer")
'''
if old_final in text:
    text = text.replace(old_final, new_final, 1)
elif new_final not in text:
    raise SystemExit("final identity invariant block not found")

path.write_text(text, encoding="utf-8")
