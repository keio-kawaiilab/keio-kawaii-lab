"use strict";

global.window={setTimeout:setTimeout};
global.document={
  getElementById:function(){return null;},
  querySelectorAll:function(){return[];}
};
global.location={search:""};

require("../train-status.js");

var api=window.KawaiiTrainStatus;
var venues=require("../data/venues.json").venues;

function venue(id){
  return venues.find(function(item){return item.id===id;});
}

function assert(value,message){
  if(!value)throw new Error(message);
}

var cases=[
  ["横浜線","yokohama-arena",true],
  ["京浜東北根岸線","k-arena-yokohama",true],
  ["京急本線","k-arena-yokohama",true],
  ["小田急小田原線","atsugi-culture-hall",true],
  ["東京メトロ千代田線","nippon-budokan",false],
  ["ゆりかもめ","ariake-arena",true],
  ["りんかい線","ariake-arena",true],
  ["山手線","spotify-o-east",true],
  ["ポートライナー","kobe-world-hall",true],
  ["ゆいレール","okinawa-convention-theater",true]
];

cases.forEach(function(test){
  var actual=api.routeMatchesVenue({name:test[0]},venue(test[1]));
  assert(actual===test[2],test[0]+" / "+test[1]+": "+actual+" != "+test[2]);
});

assert(venues.every(function(item){return api.venueLineKeys(item).length>0;}),"all venues must have route matching keys");

var event={eventDate:"2026-08-25",venue:"日本武道館"};
var tokyoMetro=[{name:"東京メトロ東西線",url:"a",status:"列車遅延"}];
assert(api.disruptionsForEvent(event,"2026-08-25",venues,tokyoMetro).length===1,"today's matching disruption must be shown");
assert(api.disruptionsForEvent(event,"2026-08-24",venues,tokyoMetro).length===0,"a non-event day must stay empty");
assert(api.disruptionsForEvent(event,"2026-08-25",venues,[{name:"横浜線",url:"b"}]).length===0,"an unrelated route must stay empty");

console.log("train-status frontend matching tests passed");

var shared=[{name:'りんかい線',url:'https://example.com/rinkai',status:'列車遅延'}];
var shows=[{group:'CUTIE STREET',title:'梅田みゆ 生誕祭 2026',eventDate:'2026-09-14',venue:'SGCホール有明',startTime:'19:00'},
 {group:'CUTIE STREET',title:'ARENA TOUR',eventDate:'2026-09-29',venue:'有明アリーナ',startTime:'18:00'}];
var associated=api.summaryRoutes('2026-09-14',shows.concat(shows[0]),venues,shared);
assert(associated.length===1&&associated[0].performances.length===1,'same-day performance association must dedupe without adding future shows');
var html=api.alertHtml(associated,'test');
assert(html.includes('CUTIE STREET 梅田みゆ 生誕祭 2026')&&html.includes('SGCホール有明')&&html.includes('9/14 開演 19:00'),'summary must identify the concert and venue');
assert(!html.includes('ARENA TOUR'),'unrelated date appeared in summary');
assert(!shared[0].performances,'summary mutated route source');
console.log('train-status concert context tests passed');
