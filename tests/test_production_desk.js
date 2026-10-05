const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
let removed=false,renders=0;
const hint={textContent:''};
const context=vm.createContext({console,window:{addEventListener(){}},document:{querySelector:s=>s==='.desk-workspace'?{}:null,querySelectorAll:()=>[]},
 $:s=>s==='#novel-main'?{removeAttribute(){removed=true}}:s==='#novel-unsaved'?hint:null,
 renderNovelStudio(){renders++},novelFresh:()=>({phase:'draft'}),novelDefaultTab:p=>p==='complete'?'tasks':'story',novelLoad:async()=>{},
 novelView:{project:{id:'a'},tab:'shots',busy:false,error:'failed validation'},state:{page:'novel'},
 confirmAction:async()=>false,esc:s=>String(s||''),productionHint:()=>['完成','可以交付'],active:()=>false,
 novelPhases:{},novelToolbar:()=>'',novelTasks:()=>'',novelScript:()=>'',novelAssets:()=>'',novelStory:()=>''});
vm.runInContext(fs.readFileSync('public/production-desk.js','utf8'),context);
assert.equal(vm.runInContext('novelFresh().professional_workflow',context),true);
assert.equal(vm.runInContext("novelDefaultTab('complete')",context),'delivery');
const overview=vm.runInContext("deskOverview({id:'a',phase:'complete',jobs:[],production_state:{}})",context);
assert.ok(overview.includes('data-desk-go="delivery"'));
assert.ok(overview.includes('旧项目 · 新审图规则待启用'));
vm.runInContext("desk.dirty=true;desk.projectId='a';desk.tab='shots';renderNovelStudio()",context);
assert.equal(removed,true);assert.equal(renders,0);assert.equal(hint.textContent,'failed validation');
vm.runInContext("novelView.project={id:'b'};renderNovelStudio()",context);
assert.equal(renders,1);assert.equal(vm.runInContext('desk.dirty',context),false);
console.log('Production desk: stage routing, legacy labels, failed form recovery and project switch passed.');
