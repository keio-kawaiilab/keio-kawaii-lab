from pathlib import Path
p=Path('scripts/build-through-service-db.mjs')
s=p.read_text(encoding='utf-8')
old="policy:{runtimeInference:false,timeGapMayEstablishIdentity:false,genericBoundaryChaining:false}"
new="policy:{runtimeInference:false,timeGapMayEstablishTrainIdentity:false,genericBoundaryChaining:false}"
if old not in s:
    raise SystemExit('target policy key not found')
p.write_text(s.replace(old,new,1),encoding='utf-8')
print('standardized through-service policy key')
