const assert=require("node:assert/strict");
const fs=require("node:fs");
const path=require("node:path");
const core=require("../../route-core.js");
const planner=require("./engine.js");
const root=path.join(__dirname,"../..");
const operators=["tx","tokyo-metro","tokyu","jr-east","toei","sotetsu","tobu","yokohama-subway"];
const files=operators.map(s=>JSON.parse(fs.readFileSync(path.join(root,"data/transit",s,"entities.json"),"utf8")));
const blocks=JSON.parse(fs.readFileSync(path.join(root,"data/transit/transfer-blocks.json"),"utf8"));
const rules=JSON.parse(fs.readFileSync(path.join(root,"data/transit/transfer-rules.json"),"utf8"));
const model=core.createModel(files,{blockedStationPairs:blocks.blockedStationPairs});
const from=model.resolveInput("八潮").group,to=model.resolveInput("日吉").group;
assert.ok(from&&to,"Yashio/Hiyoshi both present");
const result=planner.compare(model,from,to,rules);
assert.ok(result.length>=2&&result.length<=6,"2 to 6 different routes");
assert.equal(new Set(result.map(x=>x.signature)).size,result.length,"no exact line-family duplicates");
assert.ok(result.some(x=>x.category.includes("早い")),"fast category");
assert.ok(result.some(x=>x.category.includes("楽")),"easy category");
assert.ok(result.some(x=>x.lineChanges===2),"two-line-change route");
for(const x of result){
 assert.ok(x.estimatedMinutes>0&&Number.isFinite(x.estimatedMinutes),"finite estimate");
 assert.ok(x.legs.length>0,"legs exist");
 assert.equal(x.fareYen,null,"do not fabricate fares");
 for(const leg of x.legs)assert.ok(model.railwayById.has(leg.railway),"known railway");
}
assert.deepEqual(planner.compare(model,to,to,rules),[],"same-station path is not offered");
console.log("route-triple: PASS",result.map(x=>x.category+":"+x.estimatedMinutes+"min/"+x.lineChanges+"changes").join(", "));
