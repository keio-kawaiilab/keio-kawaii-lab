#!/usr/bin/env node
import fs from 'node:fs';

const file='data/transit/through-service-boundaries.json';
const data=JSON.parse(fs.readFileSync(file,'utf8'));
const list=Array.isArray(data.boundaries)?data.boundaries:[];
const byId=new Map(list.map(row=>[String(row.id||''),row]));

function upsert(spec){
  const current=byId.get(spec.id);
  if(current)Object.assign(current,spec);
  else{list.push(spec);byId.set(spec.id,spec);}
}

upsert({
  id:'yurakucho-seibuyurakucho-kotakemukaihara',station:'小竹向原',
  fromRailway:'odpt.Railway:TokyoMetro.Yurakucho',toRailway:'odpt.Railway:Seibu.SeibuYurakucho',
  fromStation:'odpt.Station:TokyoMetro.Yurakucho.KotakeMukaihara',toStation:'odpt.Station:Seibu.SeibuYurakucho.KotakeMukaihara',
  bidirectional:true,status:'verified',source:'https://www.tokyometro.jp/station/line_yurakucho/index.html',
  note:'東京メトロ公式有楽町線路線情報が小竹向原の他社線として西武有楽町線を掲載。列車単位の直通可否は別途exact evidenceで判定。',
});
upsert({
  id:'yurakucho-tojo-wakoshi',station:'和光市',
  fromRailway:'odpt.Railway:TokyoMetro.Yurakucho',toRailway:'odpt.Railway:Tobu.Tojo',
  fromStation:'odpt.Station:TokyoMetro.Yurakucho.Wakoshi',toStation:'odpt.Station:Tobu.Tojo.Wakoshi',
  bidirectional:true,status:'verified',source:'https://www.tobu.co.jp/corporation/rail/route/',
  note:'東武公式路線概要が有楽町線の相互乗入区間を森林公園〜新木場と明記。列車単位の直通可否はexact endpoint evidenceで判定。',
});
upsert({
  id:'seibuyurakucho-ikebukuro-nerima',station:'練馬',
  fromRailway:'odpt.Railway:Seibu.SeibuYurakucho',toRailway:'odpt.Railway:Seibu.Ikebukuro',
  fromStation:'odpt.Station:Seibu.SeibuYurakucho.Nerima',toStation:'odpt.Station:Seibu.Ikebukuro.Nerima',
  bidirectional:true,status:'verified',source:'https://www.seiburailway.jp/railway/station/',
  note:'西武公式路線情報は西武有楽町線を練馬〜小竹向原として掲載し、練馬を東京メトロ線直通電車の経路として示す。',
});
upsert({
  id:'seibu-ikebukuro-seibuchichibu-agano',station:'吾野',
  fromRailway:'odpt.Railway:Seibu.Ikebukuro',toRailway:'odpt.Railway:Seibu.SeibuChichibu',
  fromStation:'odpt.Station:Seibu.Ikebukuro.Agano',toStation:'odpt.Station:Seibu.SeibuChichibu.Agano',
  bidirectional:true,status:'verified',source:'https://www.seiburailway.jp/railway/station/agano/',
  note:'西武公式吾野駅情報が池袋線と西武秩父線の双方を同駅に掲載。土休日S-TRAINの西武秩父〜元町・中華街直通は列車単位exact evidenceで別途確認する。',
});

data.version=Math.max(Number(data.version)||0,4);
data.updatedAt=new Date().toISOString().slice(0,10);
data.boundaries=list;
fs.writeFileSync(file,JSON.stringify(data,null,2)+'\n','utf8');
console.log(JSON.stringify({verified:['yurakucho-seibuyurakucho-kotakemukaihara','yurakucho-tojo-wakoshi','seibuyurakucho-ikebukuro-nerima','seibu-ikebukuro-seibuchichibu-agano'],boundaryCount:list.length},null,2));
