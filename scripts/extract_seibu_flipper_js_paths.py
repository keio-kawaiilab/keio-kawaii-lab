#!/usr/bin/env python3
"""Extract only path-construction contexts from Seibu's official FLIPPER3 viewer JS."""
from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

URL = "https://www.seiburailway.jp/railways/2026digitaltimetable/html5/js/flipper.js"
OUT = Path("data/transit/fukutoshin/seibu-2026-flipper-path-report.json")
NEEDLES = (
    "textpoint.xml", "page.xml", "book.xml", "search.xml", "bookpath",
    "bookInformation.data", "setting.bookInformation.data", "pagePath",
    "thumbnail.jpg", "x1.jpg", "/pdf/", "pdf/"
)


def fetch() -> str:
    proc=subprocess.run([
        "curl","-fLsS","--retry","3","--retry-delay","1",
        "--connect-timeout","15","--max-time","60",
        "-A","Mozilla/5.0 (compatible; KeioKawaiiLabTransitDB/1.0)",URL
    ],stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=False)
    if proc.returncode:
        raise SystemExit(proc.stderr.decode("utf-8","replace")[-500:])
    return proc.stdout.decode("utf-8","replace")


def contexts(text: str, needle: str) -> list[str]:
    out=[]
    start=0
    while len(out)<12:
        pos=text.find(needle,start)
        if pos<0: break
        lo=max(0,pos-320); hi=min(len(text),pos+len(needle)+420)
        out.append(re.sub(r"\s+"," ",text[lo:hi]))
        start=pos+len(needle)
    return out


def main():
    text=fetch()
    found={needle:contexts(text,needle) for needle in NEEDLES}
    # Also retain short string literals that mention page/text/pdf paths.
    literals=[]
    for m in re.finditer(r"[\"']([^\"']{0,180}(?:page|textpoint|thumbnail|pdf)[^\"']{0,180})[\"']",text,re.I):
        value=m.group(1)
        if value not in literals:
            literals.append(value)
        if len(literals)>=120: break
    report={
        "version":1,
        "generatedAt":datetime.now(timezone.utc).isoformat(),
        "sourceUrl":URL,
        "identityPolicy":{
            "viewerPathLogicMayEstablishIdentity":False,
            "singlePublishedTrainColumnRequired":True,
            "timeProximityMayEstablishIdentity":False,
            "trainNumberAloneMayEstablishIdentity":False,
            "destinationAloneMayEstablishIdentity":False
        },
        "bytes":len(text.encode("utf-8")),
        "contexts":found,
        "pathLikeStringLiterals":literals,
        "summary":{needle:len(rows) for needle,rows in found.items()}
    }
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(report["summary"],ensure_ascii=False,indent=2))

if __name__=="__main__": main()
