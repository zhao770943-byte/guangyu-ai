// Offline state/markup contracts. No browser or provider network requests.
const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..');const nodes={};
const document={querySelector:s=>nodes[s]??= {open:true,close(){this.open=false}},querySelectorAll:()=>[]};
const ctx=vm.createContext({document,console,setTimeout,clearTimeout});
for(const file of ['app.js','storyboards.js','library-picker.js'])vm.runInContext(fs.readFileSync(path.join(root,'public',file),'utf8').split("document.addEventListener('click'")[0],ctx);
vm.runInContext(fs.readFileSync(path.join(root,'public/video-controls.js'),'utf8'),ctx);
async function run(){
 await vm.runInContext(`(async()=>{
 state.providers=[{id:'v',kind:'video',protocol:'weijin_video',capabilities:{reference_images:true,first_frame:true,last_frame:true}}];
 toast=()=>{};renderStudio=()=>{};
 const good={id:'a',kind:'image',status:'succeeded',prompt:'<private> title',result:{assets:[{type:'image',local:true,url:'/media/a.png'},{type:'image',local:true,url:'/media/b.png'},{type:'video',local:true,url:'/media/c.mp4'},{type:'image',local:false,url:'https://example.invalid/a.png'}]}};
 const imgs=libraryImages([good,{...good,id:'deleted',work_deleted_at:'now'},{...good,id:'failed',status:'failed'},{...good,id:'text',kind:'chat'}]);
 if(imgs.length!==2||imgs[1].asset_index!==1)throw Error('Wrong library filtering or multi-output indexing');
 libraryPicker.items=imgs;libraryPicker.slot='references';libraryPicker.selected=['a:1','a:0'];
 state.drafts.video.prompt='keep my video prompt';let calls=[];
 api=async(url,body)=>{calls.push({url,body});if(body.asset_index===0)throw Error('File removed');return {id:'b',url:'/uploads/b.png'}};
 await applyLibrarySelection();
 if(state.drafts.video.assets.references.length||!libraryPicker.error.includes('File removed'))throw Error('Failed import partially changed draft');
 api=async(url,body)=>{calls.push({url,body});return {id:'a',url:'/uploads/a.png'}};
 await applyLibrarySelection();
 if(state.drafts.video.assets.references.join(',')!=='b,a')throw Error('Import did not preserve selected order');
 if(calls.some(c=>c.url!=='/api/library/image'))throw Error('Import submitted a generation');
 if(state.drafts.video.prompt!=='keep my video prompt')throw Error('Import overwrote prompt');
 if(libraryLimit('references')!==7)throw Error('Wrong remaining capacity');
 libraryPicker.slot='first_frame';libraryPicker.selected=['a:0'];await applyLibrarySelection();
 if(state.drafts.video.assets.first_frame!=='a'||state.drafts.video.mode!=='first')throw Error('First frame failed');
 libraryPicker.slot='last_frame';libraryPicker.selected=['a:1'];await applyLibrarySelection();
 if(state.drafts.video.assets.last_frame!=='b'||state.drafts.video.mode!=='first_last')throw Error('Last frame failed');
 state.providers[0].capabilities={first_frame:true};state.drafts.video.mode='text';
 const html=videoAssets(chosen('video'),state.drafts.video);
 if(!html.includes('data-library-slot="first_frame"')||html.includes('data-library-slot="last_frame"')||html.includes('data-library-slot="references"'))throw Error('Unsupported library option shown');
 const previous=JSON.stringify(state.drafts.video);libraryPicker.slot='references';await applyLibrarySelection();
 if(JSON.stringify(state.drafts.video)!==previous)throw Error('Unsupported mode mutated draft');
 sbAcceptVideoAsset({id:'newfirst'},'first_frame');if(state.drafts.video.mode!=='first')throw Error('Stale tail enabled unsupported mode');
 })()`,ctx);
 const escaped=vm.runInContext("libraryPicker.busy=false;libraryPicker.slot='first_frame';libraryPicker.query='';renderLibraryItems();document.querySelector('#library-grid').innerHTML",ctx);
 assert.ok(escaped.includes('&lt;private&gt;'));assert.ok(!escaped.includes('<private>'));
 console.log('PASS library filtering, exact asset selection, order/capacity, atomic draft updates on failure, cached retries, first/tail modes, capability gates, escaping and no generation calls');
}
run().catch(e=>{console.error(e);process.exitCode=1});
