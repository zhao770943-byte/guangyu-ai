// Minimal DOM contract test of the real renderer and form event handlers.
// This checks state transitions, not browser layout or visual appearance.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),crypto=require('node:crypto');
const root=path.resolve(__dirname,'..');let all=[],ids={};
class Element{
 constructor(tag='div',attrs=''){this.tag=tag;this.dataset={};this.value='';this.classList={add(){},remove(){},toggle(){}};
  for(const m of attrs.matchAll(/([\w-]+)="([^"]*)"/g)){this[m[1]]=m[2];if(m[1].startsWith('data-'))this.dataset[m[1].slice(5).replace(/-([a-z])/g,(_,c)=>c.toUpperCase())]=m[2]}
  this.disabled=/\sdisabled(?:\s|$)/.test(attrs);this.hidden=/\shidden(?:\s|$)/.test(attrs);
 }
 set innerHTML(html){this.html=html;if(this.id==='page'){all=[];ids={'page':this}}parse(html)}
 get innerHTML(){return this.html||''}
 insertAdjacentHTML(_,html){this.html+=html;parse(html)}
 querySelectorAll(s){return queryAll(s)}
 querySelector(s){return document.querySelector(s)}
}
function parse(html){for(const m of html.matchAll(/<(button|input|textarea|select|p|div|span)\b([^>]*)>/g)){const e=new Element(m[1],m[2]);all.push(e);if(e.id)ids[e.id]=e}}
function queryAll(selectors){return all.filter(e=>selectors.split(',').some(s=>s.startsWith('[')?Object.hasOwn(e,s.slice(1,-1)):e.tag===s))}
const page=new Element('div','id="page"');ids.page=page;
const document={querySelector:s=>ids[s.slice(1)]||null,querySelectorAll:queryAll};
const ctx=vm.createContext({document,console,crypto,setTimeout,clearTimeout});
vm.runInContext(fs.readFileSync(path.join(root,'public/app.js'),'utf8').split("document.addEventListener('click'")[0],ctx);
vm.runInContext(fs.readFileSync(path.join(root,'public/storyboards.js'),'utf8').split("document.addEventListener('click'")[0],ctx);
async function run(){
 vm.runInContext(`state.page='video';state.providers=[{id:'image',name:'Fixture image',kind:'image',capabilities:{reference_images:true},model:'gpt-image-1'}];storyboardView.open=true;storyboardView.board=sbFresh();storyboardView.board.story='A shopping street';storyboardView.dirty=true;renderStoryboards();`,ctx);
 assert.ok(ids['sb-confirm'].disabled);assert.ok(ids['sb-generate-shots'].disabled);
 ids['sb-title'].oninput({target:{value:'London fashion'}});
 assert.equal(vm.runInContext('storyboardView.board.title',ctx),'London fashion');
 ctx.requests=[];
 vm.runInContext(`api=async(url,body)=>{requests.push({url,body});if(url==='/api/storyboards/save')return {...body,id:'b'.repeat(32),version:1,jobs:[],busy:false};if(url==='/api/storyboards')return {boards:[{id:'b'.repeat(32),title:'London fashion'}]};throw Error('Unexpected API')};`,ctx);
 await ids['sb-save'].onclick();
 assert.equal(vm.runInContext('storyboardView.dirty',ctx),false);
 assert.equal(ctx.requests[0].url,'/api/storyboards/save');assert.ok(!('jobs' in ctx.requests[0].body));
 vm.runInContext(`storyboardView.board.master_job_id='master';storyboardView.board.jobs=[{id:'master',status:'succeeded',result:{assets:[{type:'image',local:true,url:'/media/a.png'}]}}];sbUpdateResults();`,ctx);
 assert.equal(ids['sb-confirm'].disabled,false);assert.equal(ids['sb-generate-shots'].disabled,true);
 vm.runInContext(`storyboardView.board.master_upload_id='reference';sbUpdateResults()`,ctx);
 assert.equal(ids['sb-confirm'].disabled,true);assert.equal(ids['sb-generate-shots'].disabled,false);
 vm.runInContext(`state.providers[0].capabilities.reference_images=false;sbUpdateResults()`,ctx);
 assert.equal(ids['sb-generate-shots'].disabled,true);
 vm.runInContext(`storyboardView.board.busy=true;sbUpdateResults()`,ctx);
 assert.equal(ids['sb-master-generate'].disabled,true);assert.equal(ids['sb-close'].disabled,false);
 console.log('PASS actual storyboard form renders, saves edits, gates confirmation/reference generation and allows leaving active tasks');
}
run().catch(e=>{console.error(e);process.exitCode=1});
