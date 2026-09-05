#!/usr/bin/env python3
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import build_transit_v2 as b
idx={"stationTitle":{"upstream":"成城学園前","boundaryA":"相模大野","boundaryB":"相模大野"}}
assert b.physical_station_match("boundaryA","boundaryB",idx,"相模大野")
assert not b.physical_station_match("upstream","boundaryB",idx,"相模大野")
print("strict boundary endpoint regression passed")
