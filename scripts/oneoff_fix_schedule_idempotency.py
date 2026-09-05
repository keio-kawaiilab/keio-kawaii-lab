from pathlib import Path

path = Path("scripts/fix_schedule_shell.py")
text = path.read_text(encoding="utf-8")

old_offer = '''def install_offer_adapter(page: str) -> str:
    if "function expandCanonicalOffers(raw)" not in page:
        anchor = page.find("function prepare(raw)")
        if anchor < 0:
            raise RuntimeError("could not locate prepare() for canonical special-event adapter")
        page = page[:anchor] + CANONICAL_OFFER_JS + page[anchor:]

    if PREPARE_NEW in page:
        return page
    if PREPARE_OLD not in page:
        raise RuntimeError("schedule prepare() changed; canonical special-event offers could not be installed")
    return page.replace(PREPARE_OLD, PREPARE_NEW, 1)
'''

new_offer = '''def install_offer_adapter(page: str) -> str:
    if "function expandCanonicalOffers(raw)" not in page:
        anchor = page.find("function prepare(raw)")
        if anchor < 0:
            raise RuntimeError("could not locate prepare() for canonical special-event adapter")
        page = page[:anchor] + CANONICAL_OFFER_JS + page[anchor:]

    # Idempotent: a page that already has the canonical expansion may also
    # contain later reconciliation steps. Do not require the entire prepare()
    # function to equal an older exact string.
    if "raw=expandCanonicalOffers(raw)" in page:
        return page
    if PREPARE_OLD not in page:
        raise RuntimeError("schedule prepare() changed; canonical special-event offers could not be installed")
    return page.replace(PREPARE_OLD, PREPARE_NEW, 1)
'''

old_reconcile = '''def install_performance_reconcile(page: str) -> str:
    if "function reconcilePerformanceTimes(all)" not in page:
        anchor = page.find("function prepare(raw)")
        if anchor < 0:
            raise RuntimeError("could not locate prepare() for performance reconciliation")
        page = page[:anchor] + PERFORMANCE_RECONCILE_JS + page[anchor:]
    if PREPARE_RECONCILE_NEW in page:
        return page
    if PREPARE_RECONCILE_OLD not in page:
        raise RuntimeError("schedule prepare() changed; performance reconciliation could not be installed")
    return page.replace(PREPARE_RECONCILE_OLD, PREPARE_RECONCILE_NEW, 1)
'''

new_reconcile = '''def install_performance_reconcile(page: str) -> str:
    if "function reconcilePerformanceTimes(all)" not in page:
        anchor = page.find("function prepare(raw)")
        if anchor < 0:
            raise RuntimeError("could not locate prepare() for performance reconciliation")
        page = page[:anchor] + PERFORMANCE_RECONCILE_JS + page[anchor:]

    # Idempotent for already-generated pages. This is intentionally token-based
    # rather than an exact prepare() string match so future compatible steps can
    # coexist without breaking the release pipeline.
    if "fixed=reconcilePerformanceTimes(fixed)" in page:
        return page
    if PREPARE_RECONCILE_OLD not in page:
        raise RuntimeError("schedule prepare() changed; performance reconciliation could not be installed")
    return page.replace(PREPARE_RECONCILE_OLD, PREPARE_RECONCILE_NEW, 1)
'''

if old_offer not in text:
    raise SystemExit("install_offer_adapter block not found")
if old_reconcile not in text:
    raise SystemExit("install_performance_reconcile block not found")

text = text.replace(old_offer, new_offer, 1)
text = text.replace(old_reconcile, new_reconcile, 1)
path.write_text(text, encoding="utf-8")
