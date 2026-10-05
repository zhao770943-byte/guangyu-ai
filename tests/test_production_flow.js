const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const elements={},all={};let confirmation=false,renderCount=0;
const ctx=vm.createContext({console,deskOverview:()=>'<old>',deskStoryboard:()=>'<board>',deskSound:()=>'<sound>',novelAssets:()=>'<div class="production-asset-preview"></div>',renderNovelStudio:()=>renderCount++,fidelityDialogue:()=>'',autoReport:()=>'<reports>',
 document:{querySelectorAll:s=>all[s]||[],querySelector:()=>null},$:s=>elements[s],icon:k=>`<svg class="icon">${k}</svg>`,esc:v=>String(v??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;'),
 novelView:{project:null,tab:'overview'},desk:{dirty:false,contractDirty:false},studioUI:{shotView:'board'},productionView:{},state:{jobs:[]},confirmAction:async()=>confirmation,toast(){},
 deskBook:p=>p.production_book||{},deskShots:p=>(p.plan?.episodes||[]).flatMap(e=>(e.shots||[]).map((s,i)=>({e,s,i,key:`shot:${e.id}:${s.id}`})))
});
vm.runInContext(fs.readFileSync('public/production-flow.js','utf8'),ctx);
vm.runInContext(`p={id:'p',title:'<unsafe>',phase:'complete',request_limit:75,requests_used:41,plan:{assets:[{id:'a1',kind:'character',name:'林青'},{id:'a2',kind:'character',name:'沈舟'}],episodes:[{id:'e1',title:'Episode',shots:[{id:'s1',title:'回应',seconds:8,action:'转身',dialogue:'林青：我回来了。',dialogue_ids:['d1']},{id:'s2',title:'入场',seconds:7,action:'走进庭院',dialogue:''}]}]},production_book:{voices:[{asset_id:'a1',voice:'自然声线',audio_job_id:'deleted'}]},jobs:[],readiness:{legacy:true,planned_seconds:15,film_seconds:141,active:0,stages:[{id:'delivery',title:'交付',done:1,total:1,status:'attention',detail:'成片'}],tasks:[{tab:'delivery',title:'检查成片',detail:'完整观看'}],shots:[{start:0,end:8,notes:['待检查'],image:true},{start:8,end:15,notes:[],image:false}],voices:[]}};novelView.project=p`,ctx);
assert.match(vm.runInContext('deskOverview(p)',ctx),/2:21/);assert.match(vm.runInContext('deskOverview(p)',ctx),/0:15/);assert.match(vm.runInContext('deskOverview(p)',ctx),/data-flow-route="delivery"/);
assert.equal(vm.runInContext("flowUI.filter='dialogue';flowRows(p).length",ctx),1);
assert.equal(vm.runInContext("flowUI.filter='missing';flowRows(p)[0].s.id",ctx),'s2');
assert.equal(vm.runInContext("flowUI.filter='all';flowUI.query='no-match';flowRows(p).length",ctx),0);
assert.match(vm.runInContext("studioUI.shotView='rhythm';deskStoryboard(p)",ctx),/没有符合条件/);
vm.runInContext(`state.jobs=[{id:'deleted',kind:'audio',status:'succeeded',work_deleted_at:'now',result:{assets:[{type:'audio',url:'/media/a.mp3'}]}},{id:'valid',kind:'audio',status:'succeeded',prompt:'真实台词',result:{assets:[{type:'audio',url:'/media/b.mp3'}]}},{id:'remote',kind:'audio',status:'succeeded',result:{assets:[{type:'audio',url:'https://example.test/a.mp3'}]}}]`,ctx);
assert.equal(vm.runInContext('flowAudioJobs(p).length',ctx),1);
const sound=vm.runInContext('deskSound(p)',ctx);assert.match(sound,/原试听暂不可用/);assert.match(sound,/真实台词/);assert.doesNotMatch(sound,/https:\/\/example/);assert.match(sound,/data-voice-asset="a2" hidden/);
// Role changes hide existing panes, not rebuild inputs or drop a dirty form.
const roleButtons=['a1','a2'].map(id=>({dataset:{flowRole:id},setAttribute(k,v){this[k]=v}}));
const cards=roleButtons.map(b=>({dataset:{voiceAsset:b.dataset.flowRole},hidden:false,querySelectorAll:()=>[]}));
all['[data-flow-role]']=roleButtons;all['[data-voice-asset]']=cards;
vm.runInContext('desk.dirty=true;renderNovelStudio()',ctx);const before=renderCount;roleButtons[1].onclick();assert.equal(renderCount,before);assert.equal(cards[0].hidden,true);assert.equal(cards[1].hidden,false);assert.equal(vm.runInContext('desk.dirty',ctx),true);
// Search keeps selected audio available and does not bubble into form dirty state.
let stopped=false;const options=[{value:'',textContent:'none',selected:false},{value:'keep',textContent:'selected clip',selected:true},{value:'match',textContent:'speech alpha',selected:false},{value:'miss',textContent:'beta',selected:false}];
const count={};const input={value:'alpha',closest:()=>({querySelector:s=>s.startsWith('select')?{options}:count})};all['[data-flow-audio-search]']=[input];
vm.runInContext('renderNovelStudio()',ctx);input.oninput({stopPropagation(){stopped=true}});assert.equal(options[1].hidden,false);assert.equal(options[2].hidden,false);assert.equal(options[3].hidden,true);assert.equal(stopped,true);
input.value='zzz';input.oninput({stopPropagation(){}});assert.match(count.textContent,/没有匹配/);
const exported=vm.runInContext('flowDialogueText(p)',ctx);assert.match(exported,/林青：我回来了/);assert.doesNotMatch(exported,/provider|secret|signature/);
(async()=>{await vm.runInContext("flowNavigate('shots',1)",ctx);assert.equal(vm.runInContext('novelView.tab',ctx),'overview');confirmation=true;await vm.runInContext("flowNavigate('shots',1)",ctx);assert.equal(vm.runInContext('desk.shot',ctx),1);assert.equal(vm.runInContext('novelView.tab',ctx),'shots');console.log('PASS: truthful time, project routes, shot filters, local audio, persistent role drafts, audio search and dirty navigation');})().catch(e=>{console.error(e);process.exitCode=1});
