// Offline state regression tests. No browser, network, credentials or model calls.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const root=path.resolve(__dirname,'..');
const elements={};
const context=vm.createContext({console,setTimeout,clearTimeout,
  document:{querySelector:selector=>elements[selector],querySelectorAll:()=>[]},
  FileReader:class {readAsDataURL(){this.result='data:image/png;base64,dGVzdA==';this.onload()}},
});
vm.runInContext(fs.readFileSync(path.join(root,'public/video-controls.js'),'utf8'),context);
vm.runInContext(fs.readFileSync(path.join(root,'public/app.js'),'utf8').split("document.addEventListener('click'")[0],context);
async function run(){
  await vm.runInContext(`(async()=>{
    toast=()=>{};updateGenerate=()=>{};renderStudio=()=>{};
    api=async()=>({id:'first-fixture'});state.page='video';
    state.drafts.video.mode='first_last';
    await uploadFiles([{type:'image/png',size:10,name:'first.png'}],'video','first_frame');
  })()`,context);
  assert.equal(vm.runInContext('state.drafts.video.mode',context),'first_last','first upload must not hide the tail input');
  vm.runInContext(`state.drafts.video.assets.last_frame='last-fixture';state.providers=[{id:'fixture',kind:'video',model:'fixture',protocol:'custom',capabilities:{first_frame:true,last_frame:true,aspect_ratio:true,resolution:true,fps:true,audio:true},video_controls:{mode:'aspect',ratios:[],durations:[4,6],duration_enabled:true}}];state.drafts.video.parameters={aspect_ratio:'9:16',fps:24,audio:false}`,context);
  for(const key of ['#video-request-preview','#video-resolution','#seconds-input','#size-input'])elements[key]={setCustomValidity(){}};
  vm.runInContext(`bindVideoCanvas(chosen('video'));`,context);
  elements['#video-resolution'].oninput({target:{value:'1080p'}});
  elements['#seconds-input'].oninput({target:{value:'6'}});
  const payload=JSON.parse(vm.runInContext("JSON.stringify(payloadFor('video'))",context));
  assert.equal(payload.seconds,6,'typed duration must persist before blur');
  assert.equal(payload.parameters.resolution,'1080p');
  assert.equal(payload.parameters.fps,24);
  assert.equal(payload.parameters.audio,false);
  assert.equal(payload.input_assets.first_frame,'first-fixture');
  assert.equal(payload.input_assets.last_frame,'last-fixture');
  assert.match(elements['#video-request-preview'].textContent,/9:16 · 1080p · 6 秒/);
  console.log('PASS first/tail mode retention, immediate draft updates, typed parameters and payload');
}
run().catch(error=>{console.error(error);process.exitCode=1});
