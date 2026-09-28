// Offline UI state tests: image transfers and explicit, idempotent submissions.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),crypto=require('node:crypto');
const root=path.resolve(__dirname,'..');
const context=vm.createContext({console,crypto,setTimeout,clearTimeout,document:{querySelector:()=>null,querySelectorAll:()=>[]}});
vm.runInContext(fs.readFileSync(path.join(root,'public/app.js'),'utf8').split("document.addEventListener('click'")[0],context);
vm.runInContext(fs.readFileSync(path.join(root,'public/storyboards.js'),'utf8').split("document.addEventListener('click'")[0],context);
async function run(){
 await vm.runInContext(`(async()=>{
  state.providers=[{id:'image',kind:'image',capabilities:{reference_images:true}},{id:'video',kind:'video',protocol:'weijin_video',capabilities:{reference_images:true}}];
  state.drafts.video.prompt='Preserve my video script';
  const b=sbFresh();if(b.story!==state.drafts.video.prompt||b.shots.length!==4||b.provider_id!=='image')throw Error('Bad project defaults');
  sbAcceptVideoAsset({id:'shot-a',url:'/uploads/a.png'},'references');
  if(state.drafts.video.mode!=='reference'||state.drafts.video.assets.references[0]!=='shot-a')throw Error('Reference not attached');
  sbAcceptVideoAsset({id:'shot-a'},'references');if(state.drafts.video.assets.references.length!==1)throw Error('Duplicate reference attached');
  if(state.drafts.video.prompt!=='Preserve my video script')throw Error('Video prompt overwritten');
  try{sbAcceptVideoAsset({id:'b'},'first_frame');throw Error('Unsupported mode accepted')}catch(e){if(e.message==='Unsupported mode accepted')throw e}
  state.providers[1].capabilities={first_frame:true,last_frame:true};
  sbAcceptVideoAsset({id:'first'},'first_frame');sbAcceptVideoAsset({id:'last'},'last_frame');
  if(state.drafts.video.mode!=='first_last')throw Error('Tail frame did not select first/last mode');
  storyboardView.board={...b,id:'a'.repeat(32),version:1,master_upload_id:'confirmed'};
  storyboardView.open=false;sbCommit=async()=>{};sbUpdateResults=()=>{};toast=()=>{};
  let requests=[];api=async(url,body)=>{requests.push({url,body});throw Error('Response lost')};
  await sbGenerate('shots');const first=storyboardView.pending.request_id;
  api=async(url,body)=>{requests.push({url,body});return {...storyboardView.board,busy:true}};
  await sbGenerate('shots');
  if(requests.length!==2||requests[1].body.request_id!==first)throw Error('Retry changed idempotency key');
  if(requests.some(r=>r.url!=='/api/storyboards/generate'||r.body.stage!=='shots'))throw Error('Unexpected generation route');
  if(storyboardView.pending)throw Error('Successful request remains pending');
  await sbGenerate('shots');if(requests.length!==2)throw Error('Active batch submitted twice');
 })()`,context);
 const preview=vm.runInContext("sbPreview({status:'failed',error:'<script>bad</script>'},'')",context);
 assert.ok(preview.includes('&lt;script&gt;'));assert.ok(!preview.includes('<script>'));
 console.log('PASS storyboard defaults, reference/first/tail transfers, draft preservation, unsupported modes, duplicate submission guards and escaped errors');
}
run().catch(e=>{console.error(e);process.exitCode=1});
