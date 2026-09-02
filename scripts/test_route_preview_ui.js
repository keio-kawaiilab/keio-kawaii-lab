#!/usr/bin/env node
'use strict';
const fs=require('fs');
const path=require('path');
const vm=require('vm');
const core=require(process.cwd()+'/route-core.js');
const root=process.cwd();
function readJson(relative){return JSON.parse(fs.readFileSync(path.join(root,relative),'utf8'));}
function element(initial){return Object.assign({
  value:'',disabled:false,textContent:'',innerHTML:'',className:'',hidden:false,dataset:{},listeners:{},
  addEventListener(type,handler){this.listeners[type]=handler;},focus(){},closest(){return null;}
},initial||{});}
const elements={
  'preview-lock':element(), 'preview-lock-message':element(), 'preview-app':element({hidden:true}),
  'route-status':element({className:'route-status is-loading'}), 'route-form':element(),
  'route-from':element({value:'横浜'}), 'route-to':element({value:'元町・中華街'}),
  'route-datetime':element({value:'2026-09-03T10:00'}), 'route-calendar':element({value:'weekday'}),
  'route-priority':element({value:'fastest'}), 'route-swap':element(), 'route-submit':element(),
  'route-stations':element(), 'results-section':element(), 'recent-section':element({hidden:true}),
  'recent-searches':element(), 'clear-history':element(), 'coverage-operators':element(),
  'coverage-lines':element(), 'coverage-stations':element()
};
const store=new Map([['routePreviewAuthorized','1']]);
const sessionStorage={getItem(k){return store.has(k)?store.get(k):null;},setItem(k,v){store.set(k,String(v));},removeItem(k){store.delete(k);}};
const local=new Map();
const localStorage={getItem(k){return local.has(k)?local.get(k):null;},setItem(k,v){local.set(k,String(v));},removeItem(k){local.delete(k);}};
function fakeFetch(url){
  let clean=String(url).split('?')[0].replace(/^\.\.\/\.\.\//,'');
  if(clean==='data/transit/manifest.json'){
    const manifest=readJson(clean);manifest.operators={'yokohama-minatomirai':manifest.operators['yokohama-minatomirai']};
    return Promise.resolve({ok:true,status:200,json:()=>Promise.resolve(manifest)});
  }
  const file=path.join(root,clean);
  if(!fs.existsSync(file))return Promise.resolve({ok:false,status:404,json:()=>Promise.reject(new Error('404 '+clean))});
  return Promise.resolve({ok:true,status:200,json:()=>Promise.resolve(JSON.parse(fs.readFileSync(file,'utf8')))});
}
const document={getElementById(id){return elements[id]||null;},querySelectorAll(){return[];}};
const context={
  window:{RoutePlannerCore:core},document,fetch:fakeFetch,sessionStorage,localStorage,
  history:{replaceState(){}},location:{hash:'#preview',search:'',pathname:'/preview/transfer-guide/',href:'https://example.test/preview/transfer-guide/#preview'},
  URL,URLSearchParams,Date,Set,Map,Promise,console,TextEncoder,
  crypto:require('crypto').webcrypto,setTimeout,clearTimeout
};
context.window.crypto=context.crypto;context.globalThis=context;
const source=fs.readFileSync(path.join(root,'preview/transfer-guide/preview.js'),'utf8');
new vm.Script(source,{filename:'preview.js'}).runInNewContext(context);
async function waitFor(predicate,label,timeout=10000){const started=Date.now();while(Date.now()-started<timeout){if(predicate())return;await new Promise(r=>setTimeout(r,20));}throw new Error('Timed out waiting for '+label);}
(async()=>{
  await waitFor(()=>elements['route-status'].className.includes('is-ready'),'preview data load');
  if(elements['preview-app'].hidden)throw new Error('preview app did not unlock from authorized session');
  if(!elements['preview-lock'].hidden)throw new Error('preview lock did not hide');
  if(!String(elements['coverage-lines'].textContent).includes('1'))throw new Error('coverage display did not update');
  const submit=elements['route-form'].listeners.submit;if(typeof submit!=='function')throw new Error('submit handler missing');
  submit({preventDefault(){}});
  await waitFor(()=>elements['results-section'].innerHTML.includes('result-card'),'preview result render');
  const html=elements['results-section'].innerHTML;
  if(!html.includes('横浜 → 元町・中華街'))throw new Error('route title missing');
  if(!html.includes('乗換 0回'))throw new Error('zero-transfer result missing');
  if(!html.includes('おすすめ'))throw new Error('recommended badge missing');
  if(!localStorage.getItem('routePreviewRecent'))throw new Error('recent-search history was not saved');
  console.log('Owner route preview UI OK');
})().catch(error=>{console.error(error);process.exit(1);});
