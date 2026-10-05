const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const nodes={};let navigated='',loaded='',confirmation=false;
const ctx=vm.createContext({console,
 document:{readyState:'loading',addEventListener(){},querySelector:()=>null,querySelectorAll:()=>[],body:{classList:{remove(){}}}},
 $:s=>nodes[s]||null,renderControl(){},renderProjects(){},renderNovelStudio(){},
 go:p=>{navigated=p},names:{},novelPhases:{},icon:k=>`<svg data-icon="${k}"></svg>`,
 connectionPlatforms:[],connectionSources:ps=>[{address:'https://secret-location.example',providers:ps}],connectionSourceLabel:()=> 'Saved platform',
 esc:v=>String(v??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;'),
 active:j=>['queued','submitting','polling'].includes(j.status),
 desk:{shot:0,dirty:false,contractDirty:false},novelView:{project:{id:'p'},dirty:false,tab:'story'},
 state:{page:'novel',providers:[]},controlView:{dirty:false},visualStudio:{dirty:false},productionView:{setup:0},autoMode:()=>'<mode>',
 confirmAction:async()=>confirmation,novelLoad:async id=>{loaded=id},novelFresh:()=>({phase:'draft'}),
 novelStory:()=>'<textarea>story</textarea>',novelToolbar:()=>'<button>start</button>',
 deskShots:p=>(p.plan?.episodes||[]).flatMap(e=>e.shots.map((s,i)=>({e,s,i,key:`shot:${e.id}:${s.id}`}))),
 deskStatus:(p,k)=>p.production_state?.shots?.[k]||{},deskBook:p=>p.production_book||{},
 deskBadge:()=>'<span>待审</span>',deskImage:(p,k)=>`<img data-key="${k}">`,deskText:(l,k)=>`<textarea data-desk-field="${k}"></textarea>`,
 deskFields:{start:'首帧',end:'镜尾'},deskChecks:{identity:'人物',bridge:'衔接'},deskEmpty:()=>'',
 novelScript:()=>'',novelAssets:()=>'',novelTasks:()=>'',deskSound:()=>'',deskDeliver:()=>'',deskOverview:()=>''
});
vm.runInContext(fs.readFileSync('public/studio-shell.js','utf8'),ctx);
assert.equal(vm.runInContext("studioPhaseStep('auto_shots_review')",ctx),3);
assert.equal(vm.runInContext("studioPhaseStep('complete')",ctx),6);
assert.match(vm.runInContext("studioProjectCover({title:'<unsafe>',kind:'novel'})",ctx),/studio-cover-art/);
assert.doesNotMatch(vm.runInContext("studioProjectCover({title:'<unsafe>',kind:'novel',cover_url:'/media/a.png'})",ctx),/<unsafe>/);
assert.equal(vm.runInContext(`studioModelOptions([{id:'a',name:'Model',model:'Model'}],'a').includes('https://')`,ctx),false);
assert.match(vm.runInContext(`studioModelOptions([{id:'a',name:'Model',model:'Model'}],'a')`,ctx),/selected>Model<\/option>/);
const filmSource=fs.readFileSync('public/visual-film.js','utf8'),filmStart=filmSource.indexOf('function vfProgress(job)'),filmEnd=filmSource.indexOf("document.addEventListener('click'",filmStart);
vm.runInContext(filmSource.slice(filmStart,filmEnd),ctx);
const completed=vm.runInContext("vfProgress({film_batch:true,status:'succeeded',seconds:141,film_segments:[],film_completed:28})",ctx);
assert.match(completed,/整片已完成/);assert.doesNotMatch(completed,/等待提交|28 \/ 0/);
const queue=vm.runInContext(`studioTaskList([{id:'a',status:'failed',created_at:'1'},{id:'b',status:'polling',created_at:'2'},{id:'c',status:'interrupted',created_at:'3'}],'failed').map(x=>x.id).join(',')`,ctx);
assert.equal(queue,'c,a');
assert.equal(vm.runInContext("studioReviewProjects([{status:'complete',phase:'complete',paused:true},{status:'paused',phase:'shots'}]).length",ctx),1);
const fresh=vm.runInContext("novelProjectHTML({phase:'draft',title:'Draft'})",ctx);
assert.match(fresh,/创建你的漫剧项目/);assert.doesNotMatch(fresh,/aria-label="制作步骤"/);assert.match(fresh,/<textarea>story/);
vm.runInContext(`sample={id:'p',phase:'shot_review',plan:{assets:[],episodes:[{id:'e',title:'Episode',shots:[{id:'s',title:'<shot>',seconds:5,action:'Action',asset_ids:[],dialogue:'Hello',image_prompt:'img',video_prompt:'vid'}]}]},images:{'shot:e:s':'a'},image_assets:{a:{url:'/media/a.png'}},production_state:{shots:{'shot:e:s':{status:'approved',fingerprint:'abc'}}}}`,ctx);
const board=vm.runInContext('deskStoryboard(sample)',ctx);assert.match(board,/data-desk-shot="0"/);assert.match(board,/&lt;shot>/);assert.match(board,/\/media\/a.png/);
vm.runInContext("studioUI.shotFilter='pending'",ctx);assert.match(vm.runInContext('deskStoryboard(sample)',ctx),/没有符合筛选/);
vm.runInContext("studioUI.shotView='edit';studioUI.inspector='review'",ctx);
const edit=vm.runInContext('deskStoryboard(sample)',ctx);assert.match(edit,/id="desk-contract"/);assert.match(edit,/id="desk-shot-review"/);assert.match(edit,/data-studio-pane="contract" hidden/);assert.match(edit,/name="inspected"/);
// Switching inspector tabs changes hidden state only; it does not rebuild forms.
const buttons=[{dataset:{studioInspector:'contract'},setAttribute(){}},{dataset:{studioInspector:'review'},setAttribute(){}}];
const panes=[{dataset:{studioPane:'contract'},hidden:false},{dataset:{studioPane:'review'},hidden:true}];
ctx.document.querySelectorAll=s=>s==='[data-studio-inspector]'?buttons:s==='[data-studio-pane]'?panes:[];
vm.runInContext('renderNovelStudio()',ctx);buttons[1].onclick();assert.equal(panes[0].hidden,true);assert.equal(panes[1].hidden,false);
(async()=>{vm.runInContext('desk.dirty=true',ctx);await vm.runInContext("go('history')",ctx);assert.equal(navigated,'');assert.equal(loaded,'');assert.equal(vm.runInContext('desk.dirty',ctx),true);
 confirmation=true;await vm.runInContext("go('history')",ctx);assert.equal(loaded,'p');assert.equal(navigated,'history');
 console.log('PASS Studio: escaped cards, stage mapping, filtered task queue, focused wizard, storyboard views, retained forms and dirty-navigation cancellation/reload');
})().catch(e=>{console.error(e);process.exitCode=1});
