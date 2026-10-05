// Execute the real wizard handlers against a minimal form; no network or keys.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const root=path.resolve(__dirname,'..');
class Element {
  constructor(value=''){this.value=value;this.dataset={};this.classList={toggle(){}};this.checked=false;this.hidden=false;this.options=[]}
  set innerHTML(html){this.html=html;if(this.select){this.options=[...html.matchAll(/<option value="([^"]*)"([^>]*)>/g)].map(m=>m[1]);this.value=[...html.matchAll(/<option value="([^"]*)"([^>]*)>/g)].find(m=>m[2].includes('selected'))?.[1]||this.options[0]||''}}
  get innerHTML(){return this.html||''}
  setAttribute(name,value){this[name]=value}
  focus(){this.focused=true}
  checkValidity(){return true}
  addEventListener(){}
}
const presets=[
  {id:'openai',name:'OpenAI',base_url:'https://api.openai.com/v1',model_types:['chat','audio','image','video'],protocols:{chat:'openai_chat',image:'openai_image',audio:'openai_speech',video:'openai_video'}},
  {id:'deepseek',name:'DeepSeek',base_url:'https://api.deepseek.com',model_types:['chat'],protocols:{chat:'openai_chat'}},
  {id:'groq',name:'Groq',base_url:'https://api.groq.com/openai/v1',model_types:['chat','audio'],protocols:{chat:'openai_chat'}},
  {id:'media',name:'Media',base_url:'https://media.example/v1',model_types:['image','video'],protocols:{}},
  {id:'comfy_h3',name:'Local H3',base_url:'http://127.0.0.1:8188',model_types:['video'],protocols:{video:'comfy_h3'},discovery_protocol:'comfy_h3',allow_local:true},
  {id:'custom',name:'Custom',base_url:'',model_types:['chat','audio','image','video'],protocols:{}}
];
function wizard(kind='chat',original,savedProviders=original?[original]:[],reuseSource=null){
  const fields={},nodes={},buttons=['chat','audio','image','video'].map(k=>{const e=new Element();e.dataset.modelType=k;return e});
  const field=name=>fields[name]||(fields[name]=new Element());
  ['platform','protocol','discovery_protocol'].forEach(k=>field(k).select=true);
  field('kind').value=kind;field('base_url').value=original?.base_url||'';
  field('model').value=original?.model||'';
  let radios=[];
  const form={isConnected:true,elements:{namedItem:field},querySelector:id=>nodes[id]||(nodes[id]=new Element()),querySelectorAll:selector=>{
    if(selector==='[data-model-type]')return buttons;
    if(selector==='[name=model_choice]'){
      radios=[...(nodes['#connection-model-list']?.innerHTML||'').matchAll(/name="model_choice" value="([^"]*)"/g)].map(m=>new Element(m[1]));return radios;
    }
    return [];
  }};
  const dialog=new Element();dialog.open=true;
  const context=vm.createContext({console,setTimeout,clearTimeout,document:{querySelector:s=>s==='#provider-form'?form:s==='#provider-dialog'?dialog:undefined,querySelectorAll:()=>[]}});
  vm.runInContext(fs.readFileSync(path.join(root,'public/connections.js'),'utf8'),context);
  vm.runInContext(fs.readFileSync(path.join(root,'public/app.js'),'utf8').split("document.addEventListener('click'")[0],context);
  context.form=form;context.savedProviders=savedProviders;vm.runInContext('state.providers=savedProviders',context);context.original=original;context.presets=presets;context.kind=kind;
  context.reuseSource=reuseSource;
  vm.runInContext('api=()=>{throw Error("Unexpected request")};wizardApi=setupConnectionWizard(form,original,presets,kind,reuseSource)',context);
  return {context,form,fields,nodes,field,choose:identity=>{nodes['#connection-model-select'].value=identity;nodes['#connection-model-select'].onchange()},type:k=>{nodes['#connection-kind-select'].value=k;nodes['#connection-kind-select'].onchange()}};
}

(async()=>{
 const saved=[
  {id:'key-a',platform:'custom',base_url:'https://gateway.example/v1',kind:'chat',model:'text',name:'Account A',has_key:true,protocol:'openai_chat'},
  {id:'key-b',platform:'media',base_url:'https://gateway.example/v1/',kind:'image',model:'image',name:'Account B',has_key:true,protocol:'openai_image'},
  {id:'key-c',platform:'custom',base_url:'https://gateway.example/v2',kind:'chat',model:'text',name:'Different API path',has_key:true,protocol:'openai_chat'},
  {id:'key-d',platform:'openai',base_url:'https://api.openai.com/v1',kind:'chat',model:'text',name:'Official',has_key:true,protocol:'openai_chat'}
 ];
 const quick=wizard('chat',null,saved,saved[0]);
 assert.equal(quick.nodes['#connection-platform-pane'].hidden,true,'reuse opens model page directly');
 assert.equal(quick.nodes['#connection-model-pane'].hidden,false);
 assert.equal(quick.nodes['#connection-saved-access'].hidden,false);
 assert.equal(quick.field('api_key').value,'');
 let quickPayload;quick.context.mockApi=async(_,body)=>{quickPayload=body;return {models:[{id:'text-new',model_kinds:['chat'],protocol:'openai_chat'}]}};vm.runInContext('api=mockApi',quick.context);
 await quick.context.wizardApi.discover();assert.equal(quickPayload.credential_source_id,'key-a');assert.equal(quickPayload.api_key,'');
 quick.choose('text-new');assert.equal(quick.nodes['#connection-primary'].disabled,false);
 quick.nodes['#connection-quick-source'].value='key-b';await quick.nodes['#connection-quick-source'].onchange();assert.equal(quickPayload.credential_source_id,'key-b');assert.equal(quickPayload.api_key,'');
 quick.context.mockApi=async()=>{throw Error('401 Invalid token')};vm.runInContext('api=mockApi',quick.context);await quick.context.wizardApi.discover();
 assert.equal(quick.nodes['#connection-model-pane'].hidden,false);assert.match(quick.nodes['#connection-error'].textContent,/401/);assert.equal(quick.nodes['#connection-back'].textContent,'连接设置');
 const grouped=wizard('chat',null,saved);
 assert.equal(grouped.nodes['#connection-saved-source-label'].hidden,true,'new vendor starts independently of saved sources');
 assert.doesNotMatch(grouped.nodes['#connection-source-group'].innerHTML,/新增厂商|https?:\/\//,'saved choices contain names only');
 grouped.nodes['#connection-source-saved'].onclick();
 assert.equal(grouped.nodes['#connection-saved-source-label'].hidden,false);
 assert.equal(grouped.nodes['#connection-source-saved']['aria-pressed'],true);
 assert.equal(vm.runInContext('connectionSources(state.providers).length',grouped.context),3,'same endpoint groups rows but different paths remain distinct');
 grouped.nodes['#connection-source-group'].value='key-a';grouped.nodes['#connection-source-group'].onchange();
 assert.match(grouped.nodes['#connection-credential-source'].innerHTML,/key-a/);
 assert.match(grouped.nodes['#connection-credential-source'].innerHTML,/key-b/);
 assert.doesNotMatch(grouped.nodes['#connection-credential-source'].innerHTML,/key-c|key-d/);
 grouped.nodes['#connection-credential-source'].value='key-b';grouped.nodes['#connection-credential-source'].onchange();
 let sent;grouped.context.mockApi=async(_,body)=>{sent=body;return {models:[]}};vm.runInContext('api=mockApi',grouped.context);
 await grouped.context.wizardApi.discover();assert.equal(sent.credential_source_id,'key-b','exact chosen account is reused, not the first key of the group');
 grouped.field('api_key').value='fixture-only';grouped.nodes['#connection-source-group'].value='key-d';grouped.nodes['#connection-source-group'].onchange();
 assert.equal(grouped.field('api_key').value,'');assert.equal(grouped.field('base_url').value,'https://api.openai.com/v1');
 grouped.nodes['#connection-source-group'].value='';grouped.nodes['#connection-source-group'].onchange();
 assert.equal(grouped.nodes['#connection-credential-label'].hidden,true);assert.equal(grouped.field('platform').disabled,false);
 grouped.nodes['#connection-source-new'].onclick();assert.equal(grouped.nodes['#connection-saved-source-label'].hidden,true);
 grouped.context.mockApi=async(_,body)=>{sent=body;return {models:[]}};vm.runInContext('api=mockApi',grouped.context);await grouped.context.wizardApi.discover();assert.ok(!sent.credential_source_id,'new vendor never inherits the previous saved secret');
 assert.doesNotMatch(fs.readFileSync(path.join(root,'public/connections.js'),'utf8'),/connection-vendor-grid|connection-vendor-card|drawVendors/,'card wall removed from DOM generation');
 const w=wizard();
 assert.equal(w.nodes['#connection-platform-pane'].hidden,false,'vendor is the first page');
 assert.equal(w.nodes['#connection-type-pane'].hidden,true);
 assert.deepEqual([...w.field('platform').options].sort(),presets.map(p=>p.id).sort(),'all vendors shown before choosing output type');
 let requests=0;
 w.context.catalog={models:[{id:'text-one',model_kinds:['chat'],protocol:'openai_chat'},{id:'image-one',model_kinds:['image'],protocol:'openai_image'},{id:'video-one',model_kinds:['video'],protocol:'openai_video'},{id:'unknown-one',model_kinds:[],protocol:null}]};
 w.context.mockApi=async()=>{requests++;return w.context.catalog};vm.runInContext('api=mockApi',w.context);
 await w.context.wizardApi.discover();
 assert.equal(w.nodes['#connection-model-pane'].hidden,false);
 assert.ok(w.nodes['#connection-model-select'].innerHTML.includes('text-one'));
 assert.ok(!w.nodes['#connection-model-select'].innerHTML.includes('image-one'));
 w.field('api_key').value='fixture-only';const base=w.field('base_url').value;
 w.choose('text-one');assert.equal(w.field('model').value,'text-one');
 w.type('image');assert.equal(w.field('model').value,'');assert.equal(w.field('base_url').value,base);assert.equal(w.field('api_key').value,'fixture-only');
 assert.equal(requests,1,'switching output type reuses catalog');
 assert.ok(w.nodes['#connection-model-select'].innerHTML.includes('image-one'));w.choose('image-one');assert.equal(w.field('protocol').value,'openai_image');
 w.type('audio');assert.ok(w.nodes['#connection-model-list'].innerHTML.includes('connection-list-empty'));
 w.nodes['#connection-show-unknown'].checked=true;w.nodes['#connection-show-unknown'].onchange();w.choose('unknown-one');assert.equal(w.nodes['#connection-unknown-confirm'].hidden,false);assert.equal(w.nodes['#connection-primary'].disabled,true);
 w.field('platform').value='deepseek';w.field('platform').onchange();assert.equal(w.field('api_key').value,'');assert.equal(w.field('model').value,'');
 const failed=wizard();failed.context.mockApi=async()=>{throw Error('401 Invalid token')};vm.runInContext('api=mockApi',failed.context);await failed.context.wizardApi.discover();assert.equal(failed.nodes['#connection-platform-pane'].hidden,false);assert.ok(failed.nodes['#connection-error'].textContent.includes('401'));
 const stale=wizard();let resolve;stale.context.mockApi=()=>new Promise(r=>resolve=r);vm.runInContext('api=mockApi',stale.context);const task=stale.context.wizardApi.discover(); // submit handler intentionally doesn't await
 stale.field('base_url').value='https://different.example/v1';stale.field('base_url').oninput();resolve({models:[{id:'stale',model_kinds:['chat']}]});await task;assert.ok(!stale.nodes['#connection-model-select'].innerHTML.includes('stale'));
 console.log('PASS vendor-first flow, mixed catalog dropdown, no refetch/type mutation, unknown guard, failed discovery, stale response and key isolation');
})().catch(e=>{console.error(e);process.exitCode=1});
