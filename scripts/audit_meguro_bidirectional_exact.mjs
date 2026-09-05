#!/usr/bin/env node
import fs from 'node:fs';
const r=JSON.parse(fs.readFileSync('data/transit/meguro/identity-coverage-report.json','utf8'));
if(r.policy?.runtimeInference!==false||r.policy?.timeGapMayEstablishTrainIdentity!==false||r.policy?.trainNumberMayEstablishTrainIdentity!==false||r.policy?.publishedDestinationAloneMayEstablishIdentity!==false||r.policy?.bidirectionalExactEvidenceRequired!==true)throw new Error('Meguro audit policy must remain fail-closed');
if(r.summary?.boundaryPairs!==7||r.summary?.verifiedBoundaries!==7||r.summary?.exactIdentityReadyPairs!==7||r.summary?.complete!==true)throw new Error(`Meguro corridor incomplete: ${JSON.stringify(r.summary)}`);
for(const p of r.pairs||[]){if(!p.exactIdentityReady||!p.exactBidirectional||!(p.directions?.ab>0)||!(p.directions?.ba>0)||p.directions?.other!==0)throw new Error(`Meguro boundary not bidirectional exact: ${p.id}`);}
console.log('All seven Meguro through-service boundaries have exact bidirectional evidence');
