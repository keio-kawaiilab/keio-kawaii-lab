import fs from 'node:fs';

function patchFile(file,patches){
  let source=fs.readFileSync(file,'utf8');
  for(const patch of patches){
    if(source.includes(patch.after))continue;
    const count=source.split(patch.before).length-1;
    if(count!==1)throw new Error(`${file} / ${patch.label}: expected exactly one match, got ${count}`);
    source=source.replace(patch.before,patch.after);
  }
  fs.writeFileSync(file,source);
}

patchFile('route-core.js',[
  {
    label:'allow model options',
    before:'  function createModel(payloads){\n    var graph=new Map(),stationById=new Map(),railwayById=new Map(),trainTypeById=new Map(),railwaysByStation=new Map();',
    after:'  function stationPairKey(a,b){return a<b?a+"\\u0001"+b:b+"\\u0001"+a;}\n  function createModel(payloads,options){\n    var blockedStationPairs=new Set(options&&options.blockedStationPairs||[]);\n    var graph=new Map(),stationById=new Map(),railwayById=new Map(),trainTypeById=new Map(),railwaysByStation=new Map();'
  },
  {
    label:'skip blocked heuristic transfer edges',
    before:'      for(var i=0;i<group.nodes.length;i++)for(var j=i+1;j<group.nodes.length;j++){\n        var cost=transferCost(group.nodes[i],group.nodes[j]);',
    after:'      for(var i=0;i<group.nodes.length;i++)for(var j=i+1;j<group.nodes.length;j++){\n        if(blockedStationPairs.has(stationPairKey(group.nodes[i],group.nodes[j])))continue;\n        var cost=transferCost(group.nodes[i],group.nodes[j]);'
  }
]);

patchFile('route.js',[
  {
    label:'add blocked station state',
    before:'  var transferRulesByKey=new Map();',
    after:'  var transferRulesByKey=new Map();\n  var blockedStationPairs=[];'
  },
  {
    label:'add block indexer',
    before:'  function resolveTransferRule(context){\n    if(!context)return null;\n    return transferRulesByKey.get(transferRuleKey(context.fromStationId,context.toStationId,context.fromRailway,context.toRailway))||null;\n  }\n  function fillStations()',
    after:'  function resolveTransferRule(context){\n    if(!context)return null;\n    return transferRulesByKey.get(transferRuleKey(context.fromStationId,context.toStationId,context.fromRailway,context.toRailway))||null;\n  }\n  function indexTransferBlocks(payload){\n    blockedStationPairs=payload&&Array.isArray(payload.blockedStationPairs)?payload.blockedStationPairs.map(String):[];\n  }\n  function fillStations()'
  },
  {
    label:'load blocks with rules',
    before:'      })).then(function(bundles){\n        return fetchJson("./data/transit/transfer-rules.json?v="+encodeURIComponent(manifest.fetchedAt||Date.now())).catch(function(error){console.warn(error);return{rules:[]};}).then(function(payload){\n          indexTransferRules(payload);return bundles;\n        });\n      }).then(function(bundles){\n        model=core.createModel(bundles.map(function(bundle){return bundle.entities;}).filter(Boolean));',
    after:'      })).then(function(bundles){\n        var dataVersion=encodeURIComponent(manifest.fetchedAt||Date.now());\n        return Promise.all([\n          fetchJson("./data/transit/transfer-rules.json?v="+dataVersion).catch(function(error){console.warn(error);return{rules:[]};}),\n          fetchJson("./data/transit/transfer-blocks.json?v="+dataVersion).catch(function(error){console.warn(error);return{blockedStationPairs:[]};})\n        ]).then(function(payloads){\n          indexTransferRules(payloads[0]);indexTransferBlocks(payloads[1]);return bundles;\n        });\n      }).then(function(bundles){\n        model=core.createModel(bundles.map(function(bundle){return bundle.entities;}).filter(Boolean),{blockedStationPairs:blockedStationPairs});'
  }
]);

console.log('transfer-block integration is present');
