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
function wizard(kind='',original){
  const fields={},nodes={},buttons=['chat','audio','image','video'].map(k=>{const e=new Element();e.dataset.modelType=k;return e});
  const field=name=>fields[name]||(fields[name]=new Element());
  ['platform','protocol','discovery_protocol'].forEach(k=>field(k).select=true);
  field('kind').value=kind;field('base_url').value=original?.base_url||'';
  field('model').value=original?.model||'';
  const form={isConnected:true,elements:{namedItem:field},querySelector:id=>nodes[id]||(nodes[id]=new Element()),querySelectorAll:selector=>selector==='[data-model-type]'?buttons:[]};
  const dialog=new Element();dialog.open=true;
  const context=vm.createContext({console,setTimeout,clearTimeout,document:{querySelector:s=>s==='#provider-form'?form:s==='#provider-dialog'?dialog:undefined,querySelectorAll:()=>[]}});
  vm.runInContext(fs.readFileSync(path.join(root,'public/connections.js'),'utf8'),context);
  vm.runInContext(fs.readFileSync(path.join(root,'public/app.js'),'utf8').split("document.addEventListener('click'")[0],context);
  context.form=form;context.original=original;context.presets=presets;context.kind=kind;
  vm.runInContext('api=()=>{throw Error("Type selection must not send requests")};setupConnectionWizard(form,original,presets,kind)',context);
  return {fields,nodes,buttons,field,click:k=>buttons.find(b=>b.dataset.modelType===k).onclick()};
}
for(const kind of ['chat','audio','image','video']){
  const w=wizard();w.click(kind);
  assert.equal(w.field('kind').value,kind);
  assert.equal(w.nodes['#connection-platform-pane'].hidden,false,'type must advance to vendor page');
  assert.equal(w.nodes['#connection-type-pane'].hidden,true);
  assert.deepEqual([...w.field('platform').options].sort(),presets.filter(p=>p.model_types.includes(kind)).map(p=>p.id).sort());
}
const preselected=wizard('image');preselected.click('image');
assert.equal(preselected.nodes['#connection-platform-pane'].hidden,false,'clicking the default type also advances');
const w=wizard('chat');w.click('chat');
w.field('platform').value='deepseek';w.field('platform').onchange();w.field('api_key').value='fixture-only';w.field('model').value='old-model';
w.click('video');
assert.equal(w.field('platform').value,'openai');
assert.equal(w.field('base_url').value,presets[0].base_url);
assert.equal(w.field('api_key').value,'','a new vendor must never receive the old key');
assert.equal(w.field('model').value,'');
assert.ok(!w.field('platform').options.includes('deepseek'));
w.field('api_key').value='same-vendor-fixture';w.click('image');
assert.equal(w.field('api_key').value,'same-vendor-fixture','same destination keeps typed key');
assert.equal(w.field('protocol').value,'openai_image');
const edited=wizard('chat',{platform:'deepseek',kind:'chat',model:'deepseek-chat',protocol:'openai_chat',base_url:'https://api.deepseek.com',custom:{}});
edited.click('video');assert.ok(!edited.field('platform').options.includes('deepseek'),'original vendor must not leak into another type');
const legacy=wizard('video',{platform:'deepseek',kind:'video',model:'legacy',protocol:'custom',base_url:'https://proxy.example/v1',custom:{}});
assert.equal(legacy.field('platform').value,'custom');
assert.equal(legacy.field('base_url').value,'https://proxy.example/v1','legacy connections retain their destination');
const local=wizard('video');local.field('platform').value='comfy_h3';local.field('platform').onchange();
assert.equal(local.field('protocol').value,'comfy_h3');assert.equal(local.field('discovery_protocol').value,'comfy_h3');
assert.equal(local.field('base_url').value,'http://127.0.0.1:8188');assert.equal(local.field('allow_local').checked,true);
assert.ok(local.nodes['#connection-directory-preview'].textContent.endsWith('/object_info'));
console.log('PASS four type filters, automatic step advance, default selection, vendor changes, key isolation and legacy editing');
