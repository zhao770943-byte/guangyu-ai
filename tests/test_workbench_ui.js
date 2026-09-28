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
vm.runInContext(fs.readFileSync(path.join(root,'public/connections.js'),'utf8'),context);
vm.runInContext(fs.readFileSync(path.join(root,'public/image-controls.js'),'utf8'),context);
vm.runInContext(fs.readFileSync(path.join(root,'public/app.js'),'utf8').split("document.addEventListener('click'")[0],context);
async function run(){
  for(const key of ['#page','#model-select','#prompt','#size-input','#seconds-input','#generation-form','#video-resolution','#video-request-preview'])elements[key]={setCustomValidity(){}};
  vm.runInContext(`state.page='video';state.providers=[{id:'h3',kind:'video',name:'Local H3',model:'minimax-h3-local-8gb',protocol:'comfy_h3',capabilities:{first_frame:true,last_frame:true,aspect_ratio:true,seed:true},video_controls:{mode:'aspect',ratios:[{value:'16:9',label:'Landscape',enabled:true,sizes:{}}],durations:[5],duration_enabled:true,custom_duration:false,custom_size:false,default_ratio:'16:9'}}];state.drafts.video.mode='text';state.drafts.video.seconds=30;state.drafts.video.size='1920x1080';renderStudio('video');`,context);
  assert.equal(vm.runInContext('state.drafts.video.mode',context),'first');
  assert.equal(vm.runInContext('state.drafts.video.seconds',context),5);
  assert.equal(vm.runInContext('state.drafts.video.size',context),'auto');
  assert.match(elements['#page'].innerHTML,/data-mode="text"[^>]*disabled/);
  assert.throws(()=>vm.runInContext("payloadFor('video')",context),/首帧/);
  vm.runInContext(`state.providers=[];state.drafts.video=makeDraft();`,context);
  assert.equal(vm.runInContext("connectionMappingIssues('weijin_video','video',{}).length",context),0);
  assert.equal(vm.runInContext("connectionMappingIssues('custom','video',{}).length",context),2);
  assert.equal(vm.runInContext("connectionMappingIssues('custom','video',{submit_path:'https://example.com/videos',media_path:'url'})[0].field",context),'submit_path');
  assert.equal(vm.runInContext("connectionMappingIssues('custom','video',{submit_path:'/videos',media_path:'url',poll_path:'/tasks/{id}'}).length",context),3);
  assert.equal(vm.runInContext("connectionMappingIssues('custom','video',{submit_path:'/videos',media_path:'url'}).length",context),0);
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
  await vm.runInContext(`(async()=>{
    state.providers=[{id:'image-fixture',kind:'image',model:'fixture',protocol:'openai_image',capabilities:{quality:true,background:true,output_format:true}}];
    state.drafts.image.prompt='Retain this landscape';state.drafts.image.assets.references=['keep-reference'];
    state.drafts.image.size='2160x3840';state.drafts.image.parameters={quality:'max',background:'transparent'};
    resetImageParameters();
    if(state.drafts.image.prompt!=='Retain this landscape'||state.drafts.image.assets.references[0]!=='keep-reference')throw Error('Reset lost creative input');
    if(state.drafts.image.size!=='auto'||Object.keys(payloadFor('image').parameters).length)throw Error('Manual parameters survived reset');
    if(!imageOutputInfo({size:'2160x3840',parameters:{}},{type:'image',width:940,height:1672}).includes('不一致'))throw Error('Missing mismatch notice');
    const job={id:'delete-fixture',kind:'image',prompt:'fixture',status:'succeeded',archive_status:'saved',result:{assets:[{type:'image',url:'/media/aaaa.png'}]}};
    state.jobs=[job];state.currentJob.image=job.id;state.detail=job.id;
    confirmAction=async()=>false;api=async()=>{throw Error('Cancel must not call API')};
    await deleteWork(job.id);if(libraryWorks().length!==1)throw Error('Cancel deleted work');
    confirmAction=async()=>true;api=async()=>({...job,result:{assets:[]},work_deleted_at:'fixture'});render=()=>{};
    await deleteWork(job.id);
    if(libraryWorks().length||currentJob('image')||state.detail||state.currentJob.image)throw Error('Deleted work remains selected');
  })()`,context);
  console.log('PASS video controls, image parameter reset, output mismatch, delete confirmation/cancellation and selection cleanup');
}
run().catch(error=>{console.error(error);process.exitCode=1});
