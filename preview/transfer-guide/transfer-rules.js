(function(root){
  "use strict";
  function stationMatches(context,name){
    return String(context&&context.fromStationName||"")===name&&String(context&&context.toStationName||"")===name;
  }
  function railwayHas(value,token){return String(value||"").indexOf(token)>=0;}
  function pair(context,a,b){
    return(railwayHas(context.fromRailway,a)&&railwayHas(context.toRailway,b))||(railwayHas(context.fromRailway,b)&&railwayHas(context.toRailway,a));
  }
  function isYokosukaFamily(value){
    var id=String(value||"");
    return id.indexOf("JR-East.Yokosuka")>=0||id.indexOf("JR-East.ShonanShinjuku")>=0||id.indexOf("JR-East.Sotetsu")>=0;
  }
  var rules=[
    {id:"musashi-kosugi-jr-yokosuka-tokyu",station:"武蔵小杉",minutes:10,label:"JR横須賀線系↔東急 長距離乗換",samePlatform:false},
    {id:"nakameguro-toyoko-hibiya",station:"中目黒",minutes:0,label:"東横線↔日比谷線 対面乗換",samePlatform:true}
  ];
  function resolve(context){
    if(!context)return null;
    if(stationMatches(context,"武蔵小杉")){
      var fromJR=isYokosukaFamily(context.fromRailway),toJR=isYokosukaFamily(context.toRailway);
      var fromTokyu=railwayHas(context.fromRailway,"Tokyu."),toTokyu=railwayHas(context.toRailway,"Tokyu.");
      if((fromJR&&toTokyu)||(toJR&&fromTokyu))return Object.assign({},rules[0]);
    }
    if(stationMatches(context,"中目黒")&&pair(context,"Tokyu.Toyoko","TokyoMetro.Hibiya"))return Object.assign({},rules[1]);
    return null;
  }
  root.RouteTransferRules={rules:rules,resolve:resolve};
})(typeof window!=="undefined"?window:globalThis);
