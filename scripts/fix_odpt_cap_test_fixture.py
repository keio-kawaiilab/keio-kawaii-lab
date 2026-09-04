from pathlib import Path

path = Path("scripts/test_import_odpt_timetables.py")
text = path.read_text(encoding="utf-8")
old = '''        initial = [
            {"owl:sameAs": f"tt:initial:{index}", "odpt:operator": "odpt.Operator:Test", "odpt:railDirection": inbound if index < 500 else outbound}
            for index in range(1000)
        ]
        inbound_rows = [
            {"owl:sameAs": f"tt:in:{index}", "odpt:operator": "odpt.Operator:Test", "odpt:railDirection": inbound}
            for index in range(700)
        ]
        outbound_rows = [
            {"owl:sameAs": f"tt:out:{index}", "odpt:operator": "odpt.Operator:Test", "odpt:railDirection": outbound}
            for index in range(650)
        ]
        missing = {"owl:sameAs": "tt:out:missing", "odpt:operator": "odpt.Operator:Test", "odpt:railDirection": outbound}
        outbound_rows.append(missing)
'''
new = '''        inbound_rows = [
            {"owl:sameAs": f"tt:in:{index}", "odpt:operator": "odpt.Operator:Test", "odpt:railDirection": inbound}
            for index in range(700)
        ]
        outbound_rows = [
            {"owl:sameAs": f"tt:out:{index}", "odpt:operator": "odpt.Operator:Test", "odpt:railDirection": outbound}
            for index in range(650)
        ]
        missing = {"owl:sameAs": "tt:out:missing", "odpt:operator": "odpt.Operator:Test", "odpt:railDirection": outbound}
        outbound_rows.append(missing)
        # The broad API response is a capped subset of the same underlying
        # direction rows. The missing outbound row exists only beyond the cap.
        initial = inbound_rows + outbound_rows[:300]
'''
if old not in text:
    raise SystemExit("cap regression fixture anchor missing")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
