import fs from 'node:fs';

const file='route.js';
let source=fs.readFileSync(file,'utf8');

function replaceOnce(before,after,label){
  if(source.includes(after))return;
  const count=source.split(before).length-1;
  if(count!==1)throw new Error(`${label}: expected exactly one match, got ${count}`);
  source=source.replace(before,after);
}

replaceOnce(
'  var timetableNetworks=[];\n  var timetableNetworkCache=new Map();',
'  var timetableNetworks=[];\n  var timetableNetworkCache=new Map();\n  var transferRulesByKey=new Map();',
'add transfer rule map'
);

replaceOnce(
'  function fillStations(){stationList.innerHTML=model.stations.map(function(station){return\'<option value="\'+esc(station.label)+\'\"></option>\';}).join("");}',
`  function transferRuleKey(fromStation,toStation,fromRailway,toRailway){return[fromStation,toStation,fromRailway,toRailway].join("\\u0001");}
  function indexTransferRules(payload){
    transferRulesByKey.clear();
    var rules=payload&&Array.isArray(payload.rules)?payload.rules:[];
    rules.forEach(function(rule){
      var fromStation=String(rule&&rule.fromStation||""),toStation=String(rule&&rule.toStation||"");
      var fromRailway=String(rule&&rule.fromRailway||""),toRailway=String(rule&&rule.toRailway||"");
      var minutes=Number(rule&&rule.minutes);
      if(!fromStation||!toStation||!fromRailway||!toRailway||!Number.isFinite(minutes)||minutes<0)return;
      var normalized={minutes:minutes,id:String(rule.id||""),label:String(rule.label||""),samePlatform:Boolean(rule.samePlatform)};
      transferRulesByKey.set(transferRuleKey(fromStation,toStation,fromRailway,toRailway),normalized);
      if(rule.bidirectional!==false){
        var reverseMinutes=Number(rule.reverseMinutes),reverseSamePlatform=rule.reverseSamePlatform;
        transferRulesByKey.set(transferRuleKey(toStation,fromStation,toRailway,fromRailway),{
          minutes:Number.isFinite(reverseMinutes)&&reverseMinutes>=0?reverseMinutes:minutes,
          id:String(rule.id||"")+(rule.id?":reverse":""),
          label:String(rule.reverseLabel||rule.label||""),
          samePlatform:reverseSamePlatform==null?Boolean(rule.samePlatform):Boolean(reverseSamePlatform)
        });
      }
    });
  }
  function resolveTransferRule(context){
    if(!context)return null;
    return transferRulesByKey.get(transferRuleKey(context.fromStationId,context.toStationId,context.fromRailway,context.toRailway))||null;
  }
  function fillStations(){stationList.innerHTML=model.stations.map(function(station){return'<option value="'+esc(station.label)+'"></option>';}).join("");}`,
'add transfer rule helpers'
);

replaceOnce(
'      })).then(function(bundles){\n        model=core.createModel(bundles.map(function(bundle){return bundle.entities;}).filter(Boolean));',
`      })).then(function(bundles){
        return fetchJson("./data/transit/transfer-rules.json?v="+encodeURIComponent(manifest.fetchedAt||Date.now())).catch(function(error){console.warn(error);return{rules:[]};}).then(function(payload){
          indexTransferRules(payload);return bundles;
        });
      }).then(function(bundles){
        model=core.createModel(bundles.map(function(bundle){return bundle.entities;}).filter(Boolean));`,
'load transfer rules'
);

replaceOnce(
'    var normal=model.timedItinerary(path,timetables,earliest,service,5);',
'    var normal=model.timedItinerary(path,timetables,earliest,service,5,resolveTransferRule);',
'use transfer resolver'
);

replaceOnce(
'        var transferDetail=timed?"（"+(segment.transferMinutes?"乗換目安 "+segment.transferMinutes+"分・":"")+formatTime(segment.departure)+"発）":"";',
`        var transferRuleNote=timed&&segment.transferRuleLabel?"・"+segment.transferRuleLabel:timed&&segment.transferSamePlatform?"・同一ホーム":"";
        var transferDetail=timed?"（"+(segment.transferMinutes?"乗換目安 "+segment.transferMinutes+"分"+transferRuleNote+"・":"")+formatTime(segment.departure)+"発）":"";`,
'show transfer rule metadata'
);

fs.writeFileSync(file,source);
console.log('route.js transfer-rule integration is present');
