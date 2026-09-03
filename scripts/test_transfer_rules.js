global.window=global;
require('../preview/transfer-guide/transfer-rules.js');
const rules=global.RouteTransferRules;
function expect(condition,message){if(!condition)throw new Error(message);}
const musashi=rules.resolve({fromStationName:'武蔵小杉',toStationName:'武蔵小杉',fromRailway:'odpt.Railway:JR-East.Yokosuka',toRailway:'odpt.Railway:Tokyu.Toyoko'});
expect(musashi&&musashi.minutes===10,'武蔵小杉のJR横須賀線系→東急が10分になっていない');
const naka=rules.resolve({fromStationName:'中目黒',toStationName:'中目黒',fromRailway:'odpt.Railway:Tokyu.Toyoko',toRailway:'odpt.Railway:TokyoMetro.Hibiya'});
expect(naka&&naka.minutes===0&&naka.samePlatform===true,'中目黒の対面乗換が同一分接続になっていない');
expect(rules.resolve({fromStationName:'北千住',toStationName:'北千住',fromRailway:'odpt.Railway:MIR.TsukubaExpress',toRailway:'odpt.Railway:TokyoMetro.Hibiya'})===null,'未登録駅でルールを捏造している');
const core=require('../route-core.js');
const source=require('fs').readFileSync(require('path').join(__dirname,'..','route-core.js'),'utf8');
expect(source.includes('transferResolver'),'route-coreに乗換ルールresolverがない');
const preview=require('fs').readFileSync(require('path').join(__dirname,'..','preview','transfer-guide','preview.js'),'utf8');
expect(preview.includes('RouteTransferRules&&window.RouteTransferRules.resolve'),'previewが乗換ルールを渡していない');
console.log('Transfer rules OK',rules.rules);
