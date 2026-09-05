#!/usr/bin/env node
import fs from 'node:fs';

const trips=JSON.parse(fs.readFileSync('data/transit/through-service-trips.json','utf8'));
const MM='manual.Railway:YokohamaMinatomirai.Minatomirai',TY='odpt.Railway:Tokyu.Toyoko',TSH='odpt.Railway:Tokyu.TokyuShinYokohama',SSH='odpt.Railway:Sotetsu.SotetsuShinYokohama',SM='odpt.Railway:Sotetsu.Main',SIZ='odpt.Railway:Sotetsu.Izumino',F='odpt.Railway:TokyoMetro.Fukutoshin',Y='odpt.Railway:TokyoMetro.Yurakucho',SY='odpt.Railway:Seibu.SeibuYurakucho',SI='odpt.Railway:Seibu.Ikebukuro',SC='odpt.Railway:Seibu.SeibuChichibu',TJ='odpt.Railway:Tobu.Tojo';
const SYSTEMS={
  line13:[
    ['minatomirai-toyoko-yokohama','横浜',MM,TY,''],['toyoko-tokyushinyokohama-hiyoshi','日吉',TY,TSH,''],['tokyushinyokohama-sotetsushinyokohama-shinyokohama','新横浜',TSH,SSH,''],['sotetsushinyokohama-main-nishiya','西谷',SSH,SM,''],['sotetsu-main-izumino-futamatagawa','二俣川',SM,SIZ,''],['toyoko-fukutoshin-shibuya','渋谷',TY,F,''],['fukutoshin-seibuyurakucho-kotakemukaihara','小竹向原',F,SY,''],['seibuyurakucho-ikebukuro-nerima','練馬',SY,SI,'line13'],['seibu-ikebukuro-seibuchichibu-agano','吾野',SI,SC,'line13'],['fukutoshin-tojo-wakoshi','和光市',F,TJ,''],
  ],
  line8:[['yurakucho-seibuyurakucho-kotakemukaihara','小竹向原',Y,SY,'line8'],['seibuyurakucho-ikebukuro-nerima','練馬',SY,SI,'line8'],['yurakucho-tojo-wakoshi','和光市',Y,TJ,'line8']],
};
const exactTypes=new Set(['odpt-train-timetable-link','train-timetable-network','official-single-train-page','official-same-printed-column','odpt-explicit-boundary-endpoint']);
function direction(row,a,b){const route=Array.isArray(row.routeRailways)?row.routeRailways.map(String):[];for(let i=0;i+1<route.length;i++){if(route[i]===a&&route[i+1]===b)return'ab';if(route[i]===b&&route[i+1]===a)return'ba';}const from=String(row.fromRailway||''),to=String(row.toRailway||'');if(from===a&&to===b)return'ab';if(from===b&&to===a)return'ba';return'';}
let failed=false;const output={};
for(const [system,pairs] of Object.entries(SYSTEMS)){
  output[system]={};
  for(const [id,label,a,b,corridor] of pairs){
    const c={ab:0,ba:0,malformed:0,types:{}};
    for(const row of trips.records||[]){
      const type=String(row.identityType||row.evidenceType||'');if(!exactTypes.has(type))continue;if(corridor&&String(row.corridor||'')!==corridor)continue;
      const d=direction(row,a,b);if(d){c[d]++;c.types[type]=(c.types[type]||0)+1;}
      else if(String(row.canonicalBoundaryId||'')===id)c.malformed++;
    }
    const pass=c.ab>0&&c.ba>0&&c.malformed===0;output[system][id]={label,fromRailway:a,toRailway:b,requiredCorridor:corridor,...c,bidirectional:pass};if(!pass)failed=true;
  }
}
console.log(JSON.stringify(output,null,2));
if(failed)throw new Error('At least one Line 8/Line 13 through boundary lacks exact evidence in both directions');
console.log('All complete Line 8 and Line 13 through-service boundaries have exact bidirectional evidence');
