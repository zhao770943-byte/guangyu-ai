'use strict';
const visualStudio={project:null,projects:[],selected:new Set(),dirty:false,busy:false,loading:false,error:'',undo:[],redo:[],pending:null,space:false,drag:null,candidates:{},clipboard:null,promptTabs:{}};
const vsTypes={character:'角色定稿',scene:'场景定稿',prop:'道具定稿',style:'风格定稿'};
const vsCurrent=VisualGraph.current;
function vsSelected(){return visualStudio.project?.nodes.find(n=>n.id===[...visualStudio.selected].at(-1))}
function vsJob(id){return visualStudio.project?.jobs?.find(j=>j.id===id)}
function vsJobAsset(j){return j?.status==='succeeded'&&!j.work_deleted_at?j.result?.assets?.find(a=>a.type==='image'&&a.local):null}
function vsNodeAsset(n){return vsCurrent(n)?.asset||state.assets[n.upload_id]||null}
function vsPayload(){const p=visualStudio.project;if(p.film_options){const f=p.film_options,keep=f.node_ids.map((id,i)=>({id,d:f.durations[i]})).filter(x=>p.nodes.some(n=>n.id===x.id&&n.kind==='shot'));p.film_options={...f,node_ids:keep.map(x=>x.id),durations:keep.map(x=>x.d)}}return {id:p.id,version:p.version,title:p.title,story:p.story,ratio:p.ratio,provider_id:p.provider_id,viewport:p.viewport,...(p.film_options?{film_options:p.film_options}:{}),nodes:p.nodes.map(n=>({...n,upload_id:vsCurrent(n)?.upload_id||n.upload_id||null}))}}
function vsCheckpoint(){const v=visualStudio;v.undo.push(VisualGraph.clone(v.project));if(v.undo.length>50)v.undo.shift();v.redo=[]}
function vsChanged(redraw=true){visualStudio.dirty=true;for(const n of visualStudio.project.nodes)n.stale=VisualGraph.stale(visualStudio.project.nodes,n);const e=$('#vs-save-state');if(e)e.textContent='有未保存的编辑 · Ctrl+S';if(redraw)vsDrawCanvas();else vsCanvasStatus()}
function vsEdit(fn){if(visualStudio.busy)return;vsCheckpoint();fn();vsChanged();renderVisualStudio()}
function vsMerge(p){visualStudio.project=p;for(const j of p.jobs||[]){state.jobs=state.jobs.filter(x=>x.id!==j.id);state.jobs.unshift(j)}}
function vsFresh(){return {id:null,version:0,title:'新的定稿项目',story:'',provider_id:chosen('image')?.id||'',ratio:'9:16',viewport:{x:20,y:20,zoom:.8},nodes:[],jobs:[]}}
async function vsLoad(id){
 const v=visualStudio;if(v.loading)return;v.loading=true;v.error='';
 try{v.projects=(await api('/api/visual-projects')).projects;const selected=id||v.projects[0]?.id;vsMerge(selected?await api('/api/visual-projects?id='+selected):vsFresh());v.selected=new Set();v.dirty=false;v.undo=[];v.redo=[];v.pending=null}
 catch(e){v.error=e.message}finally{v.loading=false;if(state.page==='visual')renderVisualStudio()}
}
async function vsSave(){
 const v=visualStudio;if(!v.dirty&&v.project.id)return;
 vsMerge(await api('/api/visual-projects/save',vsPayload()));v.dirty=false;v.undo=[];v.redo=[];
 v.projects=(await api('/api/visual-projects')).projects;
}
async function vsAction(fn){
 const v=visualStudio;if(v.busy)return;v.busy=true;v.error='';const root=$('#visual-workbench');if(root)root.inert=true;
 try{await fn()}catch(e){v.error=e.message;toast(e.message)}finally{v.busy=false;if(root)root.inert=false;if(state.page==='visual')renderVisualStudio()}
}
function vsAdd(kind,subtype='character'){
 vsEdit(()=>{const p=visualStudio.project;if(p.nodes.length>=64)throw Error('一个项目最多64个节点');const n=VisualGraph.make(kind,subtype,p.nodes.length);const viewport=$('#vs-canvas');if(viewport){n.x=(viewport.clientWidth/2-p.viewport.x)/p.viewport.zoom-VisualGraph.width/2;n.y=(viewport.clientHeight/2-p.viewport.y)/p.viewport.zoom-VisualGraph.height/2}if(kind==='shot'){n.ratio=p.ratio;n.refs=[...visualStudio.selected].filter(id=>vsCurrent(p.nodes.find(x=>x.id===id))).slice(0,8)}p.nodes.push(n);visualStudio.selected=new Set([n.id])});
}
function vsProviderOptions(selected,inherit=false){return (inherit?'<option value="">沿用项目模型</option>':'<option value="">请选择图像模型</option>')+state.providers.filter(p=>p.kind==='image'&&providerUsable(p)).map(p=>`<option value="${p.id}" ${p.id===selected?'selected':''}>${esc(p.name)}</option>`).join('')}
function vsRatioOptions(ratio){return ['9:16','16:9','1:1','3:2','2:3','4:3','3:4'].map(r=>`<option ${r===ratio?'selected':''}>${r}</option>`).join('')}
function renderVisualStudio(){
 const v=visualStudio,p=v.project;
 if(!p){$('#page').innerHTML='<div class="boot-state">正在读取定稿与分镜画布…</div>';if(!v.loading)vsLoad();return}
 $('#page').innerHTML=`<div class="visual-page" id="visual-workbench"><div class="vs-top"><input id="vs-project-title" class="vs-project-title" aria-label="项目名称" value="${esc(p.title)}" maxlength="80"><details class="vs-menu"><summary>项目 ▾</summary><div class="vs-menu-panel"><select id="vs-project" aria-label="切换项目"><option value="">切换项目</option>${v.projects.map(b=>`<option value="${b.id}">${esc(b.title)}</option>`).join('')}</select><button id="vs-new">新建项目</button><button id="vs-legacy">导入旧分镜</button><button id="vs-export">导出工作流</button><button id="vs-import">导入工作流</button></div></details><button class="button secondary compact" id="vs-project-settings">项目设置</button><span class="vs-save-state" id="vs-save-state">${v.dirty?'未保存 · Ctrl+S':'已保存'}</span><button class="button secondary compact" id="vs-fullscreen" aria-label="全屏画布">全屏</button><button class="button secondary compact" id="vs-film">生成整片视频</button><button class="button primary compact" id="vs-save">保存</button></div>${v.error?`<div class="vs-error" role="alert">${esc(v.error)}</div>`:''}<div class="vs-body"><section class="vs-center"><div class="vs-canvas-tools"><span class="vs-add-label">添加</span>${Object.entries(vsTypes).map(([key,label])=>`<button data-vs-add="${key}">＋ ${label.replace('定稿','')}</button>`).join('')}<button id="vs-add-shot">＋ 分镜</button><button id="vs-upload-new">导入图片</button><span class="vs-toolbar-divider"></span><button id="vs-fit">适配</button><button id="vs-arrange">整理</button><details class="vs-menu"><summary>操作 ▾</summary><div class="vs-menu-panel"><button id="vs-undo" ${v.undo.length?'':'disabled'}>撤销</button><button id="vs-redo" ${v.redo.length?'':'disabled'}>重做</button><button id="vs-copy">复制节点</button><button id="vs-duplicate">复制一份</button><button id="vs-delete">移除所选</button><button id="vs-generate-selected">生成所选节点</button><button id="vs-help">快捷键</button></div></details><span class="vs-selection-count" id="vs-selection-count"></span></div><div id="vs-canvas" class="vs-canvas" tabindex="0" aria-label="定稿分镜节点画布"><div class="vs-world" id="vs-world"><svg class="vs-links" id="vs-links"></svg><div id="vs-nodes"></div></div><div id="vs-marquee" class="vs-marquee"></div><div class="vs-empty" id="vs-empty"><strong>从一张定稿开始</strong><span>从上方添加节点，或拖入、粘贴图片</span></div></div><div class="vs-zoom-tools"><button id="vs-zoom-out" aria-label="缩小画布">−</button><span id="vs-zoom-label"></span><button id="vs-zoom-in" aria-label="放大画布">＋</button></div></section></div><input type="file" id="vs-upload" accept="image/png,image/jpeg,image/webp" multiple hidden><input type="file" id="vs-import-file" accept="application/json,.json" hidden></div>`;
 $('#vs-project').onchange=async e=>{const id=e.target.value;if(!id)return;if(v.dirty&&!await confirmAction('切换项目？','当前编辑尚未保存，切换将放弃这些编辑。')){e.target.value='';return}vsLoad(id)};
 $('#vs-project-title').onfocus=()=>vsCheckpoint();$('#vs-project-title').oninput=e=>{p.title=e.target.value;vsChanged(false)};
 $('#vs-new').onclick=async()=>{if(v.dirty&&!await confirmAction('新建项目？','当前编辑尚未保存，先保存可保留它们。'))return;v.project=vsFresh();v.selected.clear();v.dirty=true;v.undo=[];v.redo=[];renderVisualStudio()};
 $('#vs-save').onclick=()=>vsAction(async()=>{await vsSave();toast('定稿项目已保存')});$('#vs-legacy').onclick=vsLegacyDialog;
 $('#vs-project-settings').onclick=vsProjectSettings;$('#vs-film').onclick=()=>vsAction(async()=>{await vsSave();await openVisualFilm(visualStudio.project)});
 $('#vs-fullscreen').onclick=async()=>{try{if(document.fullscreenElement)await document.exitFullscreen();else await $('#page').requestFullscreen()}catch(e){toast('无法进入全屏：'+e.message)}};
 document.querySelectorAll('[data-vs-add]').forEach(e=>e.onclick=()=>vsAdd('master',e.dataset.vsAdd));$('#vs-add-shot').onclick=()=>vsAdd('shot');
 $('#vs-upload-new').onclick=()=>{$('#vs-upload').dataset.target='';$('#vs-upload').click()};$('#vs-upload').onchange=e=>vsUpload([...e.target.files],e.target.dataset.target||null);
 $('#vs-export').onclick=vsExport;$('#vs-import').onclick=()=>$('#vs-import-file').click();
 $('#vs-import-file').onchange=async e=>{try{const file=e.target.files[0];if(!file)return;if(file.size>1024*1024)throw Error('工作流JSON超过1MiB');vsPaste(JSON.parse(await file.text()))}catch(err){toast(err.message)}};
 $('#vs-fit').onclick=()=>vsFit();$('#vs-zoom-in').onclick=()=>vsZoom(1.15);$('#vs-zoom-out').onclick=()=>vsZoom(1/1.15);
 $('#vs-undo').onclick=()=>vsUndo(false);$('#vs-redo').onclick=()=>vsUndo(true);$('#vs-copy').onclick=vsCopy;
 $('#vs-duplicate').onclick=()=>vsPaste(VisualGraph.serialize(p.nodes,v.selected));$('#vs-delete').onclick=vsRemove;$('#vs-generate-selected').onclick=vsGenerate;
 $('#vs-arrange').onclick=()=>{vsEdit(()=>{const canvas=$('#vs-canvas');let columns=1,best=0;for(let c=1;c<=Math.min(6,p.nodes.length);c++){const rows=Math.ceil(p.nodes.length/c),score=Math.min((canvas.clientWidth-70)/(c*(VisualGraph.width+70)-70),(canvas.clientHeight-70)/(rows*(VisualGraph.height+60)-60));if(score>best){columns=c;best=score}}p.nodes.forEach((n,i)=>{n.x=40+(i%columns)*(VisualGraph.width+70);n.y=40+Math.floor(i/columns)*(VisualGraph.height+60)})});vsFit()};
 $('#vs-help').onclick=()=>vsModal('画布快捷键','<div class="vs-shortcuts"><p>拖动节点标题移动 · 输出圆点拖到输入圆点连线</p><p>滚轮缩放 · 空格＋拖动或鼠标中键平移</p><p>空白处拖动框选 · Shift / Ctrl 多选</p><p>Ctrl+C / V 复制粘贴节点或图片</p><p>Ctrl+Z / Y 撤销重做 · Ctrl+S 保存项目</p><p>提示词输入框内使用正常的文字编辑快捷键</p></div>');
 vsDrawCanvas();vsInspector();vsBindCanvas();
}
function vsProjectSettings(){
 const p=visualStudio.project;vsModal('项目设置',`<div class="vs-node-settings"><label>默认图像模型<select id="vs-project-provider">${vsProviderOptions(p.provider_id)}</select></label><label>分镜默认画幅<select id="vs-project-ratio">${vsRatioOptions(p.ratio)}</select></label><label>故事背景<textarea id="vs-story" rows="6" maxlength="16000">${esc(p.story)}</textarea></label></div>`);
 for(const [id,key] of [['vs-project-provider','provider_id'],['vs-project-ratio','ratio'],['vs-story','story']]){const el=$('#'+id);el.onfocus=()=>vsCheckpoint();el.oninput=()=>{p[key]=el.value;vsChanged(false)}}
}
function vsOpenNode(id){
 const n=visualStudio.project.nodes.find(x=>x.id===id);if(!n)return;visualStudio.selected=new Set([id]);vsCanvasStatus();vsModal(n.title,`<div class="vs-node-settings" id="vs-node-settings" data-node-id="${n.id}"></div>`);vsInspector();
}
function vsCanvasStatus(){
 const v=visualStudio,p=v.project;if(!p)return;
 document.querySelectorAll('[data-vs-node]').forEach(el=>{const n=p.nodes.find(x=>x.id===el.dataset.vsNode);if(!n)return;el.classList.toggle('selected',v.selected.has(n.id));const label=el.querySelector('.vs-node-state');if(label){label.textContent=n.stale?'需复核':vsCurrent(n)?'已采用':'待定稿';label.className='vs-node-state '+(n.stale?'warn':vsCurrent(n)?'good':'')}});
 if($('#vs-selection-count'))$('#vs-selection-count').textContent=v.selected.size?'已选 '+v.selected.size:'';
 if($('#vs-undo'))$('#vs-undo').disabled=!v.undo.length;if($('#vs-redo'))$('#vs-redo').disabled=!v.redo.length;
}
function vsDrawCanvas(){
 const v=visualStudio,p=v.project,root=$('#vs-nodes');if(!root||!p)return;
 v.selected=new Set([...v.selected].filter(id=>p.nodes.some(n=>n.id===id)));
 if(root.contains(document.activeElement)&&vsTyping(document.activeElement)){vsCanvasStatus();vsTransform();return}
 root.innerHTML=p.nodes.map(n=>{const a=vsNodeAsset(n),jobs=n.job_ids.map(vsJob).filter(Boolean),j=jobs.find(x=>x.id===v.candidates[n.id])||jobs.at(-1),candidate=vsJobAsset(j),adopted=vsCurrent(n),fresh=candidate&&adopted?.job_id!==j.id,shown=a||candidate,video=n.kind==='shot'&&v.promptTabs[n.id]==='video_prompt',key=video?'video_prompt':'prompt';return `<article class="vs-node ${n.kind} ${v.selected.has(n.id)?'selected':''}" data-vs-node="${n.id}"><button class="vs-port input" data-vs-in="${n.id}" title="参考输入" aria-label="${esc(n.title)}参考输入"></button><button class="vs-port output" data-vs-out="${n.id}" title="拖到另一节点的输入圆点" aria-label="${esc(n.title)}参考输出"></button><div class="vs-node-head"><strong title="${esc(n.title)}">${esc(n.title)}</strong><small>${n.kind==='shot'?'分镜':vsTypes[n.subtype].replace('定稿','')}</small></div><button class="vs-node-image" data-vs-preview="${n.id}" aria-label="预览 ${esc(n.title)}">${shown?`<img src="${esc(shown.url)}" alt="${esc(n.title)}">`:'<span>导入图片或生成定稿</span>'}${!a&&candidate?'<small class="vs-candidate-label">候选 · 待采用</small>':''}</button><div class="vs-prompt-tabs"><button data-vs-prompt-tab="prompt" data-node-id="${n.id}" class="${video?'':'active'}">画面提示词</button>${n.kind==='shot'?`<button data-vs-prompt-tab="video_prompt" data-node-id="${n.id}" class="${video?'active':''}">视频提示词</button>`:''}<span>${esc(n.ratio)} · ${n.refs.length} 参考</span></div><textarea class="vs-inline-prompt" data-vs-prompt="${n.id}" data-field="${key}" aria-label="${esc(n.title)}${video?'视频':'画面'}提示词" maxlength="${video?16000:6000}" placeholder="${video?'描述动作、运镜与声音…':'在这里描述角色、场景或镜头画面…'}">${esc(n[key])}</textarea><div class="vs-node-actions"><button data-vs-settings="${n.id}">设置 / 版本${fresh?' •':''}</button>${fresh?`<button data-vs-adopt="${n.id}" data-job-id="${j.id}">采用候选</button>`:''}${video?`<button class="vs-node-primary" data-vs-video="${n.id}" ${a?'':'disabled'}>视频草稿 →</button>`:`<button class="vs-node-primary" data-vs-generate="${n.id}" ${j&&active(j)?'disabled':''}>${j&&active(j)?'生成中…':'生成'}</button>`}</div><div class="vs-node-footer"><span class="vs-node-state"></span><span title="${esc(j?.error||'')}">${j?.status==='failed'?'生成失败 · 查看版本':fresh?'有新候选':n.versions.length?n.versions.length+' 个版本':''}</span></div></article>`}).join('');
 p.nodes.forEach(n=>{const el=root.querySelector(`[data-vs-node="${n.id}"]`);el.style.left=n.x+'px';el.style.top=n.y+'px'});
 root.querySelectorAll('[data-vs-prompt]').forEach(el=>{el.onfocus=()=>{vsCheckpoint();v.selected=new Set([el.dataset.vsPrompt]);vsCanvasStatus()};el.oninput=()=>{const n=p.nodes.find(x=>x.id===el.dataset.vsPrompt);n[el.dataset.field]=el.value;vsChanged(false)}});
 root.querySelectorAll('[data-vs-prompt-tab]').forEach(el=>el.onclick=()=>{v.promptTabs[el.dataset.nodeId]=el.dataset.vsPromptTab;vsDrawCanvas()});
 root.querySelectorAll('[data-vs-settings]').forEach(el=>el.onclick=()=>vsOpenNode(el.dataset.vsSettings));
 root.querySelectorAll('[data-vs-generate]').forEach(el=>el.onclick=()=>{v.selected=new Set([el.dataset.vsGenerate]);vsCanvasStatus();vsGenerate()});
 root.querySelectorAll('[data-vs-adopt]').forEach(el=>el.onclick=()=>vsAdopt(el.dataset.vsAdopt,{job_id:el.dataset.jobId}));
 root.querySelectorAll('[data-vs-video]').forEach(el=>el.onclick=()=>vsToVideo(el.dataset.vsVideo));
 root.querySelectorAll('[data-vs-preview]').forEach(el=>el.onclick=()=>{const n=p.nodes.find(x=>x.id===el.dataset.vsPreview),j=vsJob(v.candidates[n.id]||n.job_ids.at(-1)),a=vsNodeAsset(n)||vsJobAsset(j);if(a)previewAsset(a,n.title);else vsOpenNode(n.id)});
 $('#vs-empty').hidden=!!p.nodes.length;$('#vs-empty').style.display=p.nodes.length?'none':'flex';vsCanvasStatus();vsTransform();
}

function vsTransform(){const p=visualStudio.project,w=$('#vs-world');if(!w)return;const t=p.viewport;w.style.transform=`translate(${t.x}px,${t.y}px) scale(${t.zoom})`;$('#vs-zoom-label').textContent=Math.round(t.zoom*100)+'%';vsDrawLinks()}
function vsDrawLinks(){
 const p=visualStudio.project,root=$('#vs-links');if(!root)return;let paths='';
 const path=(x,y,tx,ty,extra='')=>`<path class="vs-link ${extra}" d="M ${x} ${y} C ${x+Math.max(75,Math.abs(tx-x)*.4)} ${y}, ${tx-Math.max(75,Math.abs(tx-x)*.4)} ${ty}, ${tx} ${ty}"/>`;
 for(const n of p.nodes)for(const r of n.refs){const from=p.nodes.find(s=>s.id===r);if(from)paths+=path(from.x+VisualGraph.width,from.y+26,n.x,n.y+26)}
 const drag=visualStudio.drag;if(drag?.mode==='link'){const n=p.nodes.find(s=>s.id===drag.source);paths+=path(n.x+VisualGraph.width,n.y+26,drag.end.x,drag.end.y,'pending')}
 root.innerHTML=paths;
}
function vsInspector(){
 const v=visualStudio,root=$('#vs-node-settings');if(!root||!root.closest('dialog')?.open)return;const n=v.project.nodes.find(x=>x.id===root.dataset.nodeId);if(!n){root.closest('dialog').close();return}
 const p=v.project,a=vsNodeAsset(n),versions=n.versions||[],jobs=n.job_ids.map(vsJob).filter(Boolean),candidateId=v.candidates[n.id]||jobs.at(-1)?.id,j=jobs.find(j=>j.id===candidateId),candidate=vsJobAsset(j);
 root.innerHTML=`<label>名称<input id="vs-node-title" maxlength="80" value="${esc(n.title)}"></label><div class="vs-row"><label>画幅<select id="vs-node-ratio">${vsRatioOptions(n.ratio)}</select></label>${n.kind==='master'?`<label>版式<select id="vs-node-layout"><option value="single" ${n.layout==='single'?'selected':''}>单画面</option><option value="sheet" ${n.layout==='sheet'?'selected':''}>面部＋正侧背</option></select></label>`:'<div class="vs-status">一张独立镜头画面</div>'}</div><label>图像模型<select id="vs-node-provider">${vsProviderOptions(n.provider_id,true)}</select></label><strong>实际参考输入 · ${n.refs.length}/8</strong><div class="vs-ref-list">${p.nodes.filter(r=>r.id!==n.id).map(r=>`<label><input type="checkbox" data-vs-ref="${r.id}" ${n.refs.includes(r.id)?'checked':''}>${esc(r.title)}${vsCurrent(r)?'':' · 未采用图片'}</label>`).join('')||'<span class="vs-help">画布中没有其他参考节点</span>'}</div><div class="vs-row"><button class="button secondary" id="vs-node-upload">上传 / 粘贴图片</button><button class="button secondary" id="vs-node-library">从作品库选择</button></div>${n.stale?'<p class="vs-status warn">引用版本或描述已变化，当前图片保留。复核后继续使用，或重新生成。</p><button class="button secondary wide" id="vs-review">已复核，保留此图</button>':''}<details open><summary>已采用图片与版本</summary>${a?`<div class="vs-preview"><img id="vs-active-preview" src="${esc(a.url)}" alt="当前采用图片"></div>`:'<p class="vs-status">还没有采用图片。</p>'}${versions.length?`<label>历史版本<select id="vs-version">${[...versions].reverse().map((r,i)=>`<option value="${r.id}" ${r.id===n.active_version_id?'selected':''}>版本 ${versions.length-i} · ${timeLabel(r.created_at)}</option>`).join('')}</select></label>`:''}</details><details ${j?'open':''}><summary>生成候选 ${jobs.length}</summary>${jobs.length?`<select id="vs-candidate">${[...jobs].reverse().map((r,i)=>`<option value="${r.id}" ${r.id===candidateId?'selected':''}>第${jobs.length-i}次 · ${statusNames[r.status]||r.status}</option>`).join('')}</select>`:''}${candidate?`<div class="vs-preview"><img id="vs-candidate-preview" src="${esc(candidate.url)}" alt="新生成候选"><button class="button primary wide" id="vs-adopt">采用这张图片</button></div>`:j?`<p class="vs-status">${esc(j.error||statusNames[j.status]||'等待图片保存')}</p>`:'<p class="vs-status">还没有生成候选。</p>'}</details>${n.kind==='shot'?`<details open><summary>送往视频</summary><label>视频模型<select id="vs-video-model">${options('video')}</select></label><button class="button secondary wide" id="vs-to-video" ${a?'':'disabled'}>用当前版本打开视频草稿 →</button><p class="vs-status">替换草稿参考图和提示词，同步 ${esc(n.ratio)} 画幅；不提交视频生成。</p></details>`:''}`;
 for(const [id,key] of [['vs-node-title','title'],['vs-node-ratio','ratio'],['vs-node-layout','layout'],['vs-node-provider','provider_id'],['vs-node-prompt','prompt'],['vs-video-prompt','video_prompt']]){const el=$('#'+id);if(!el)continue;el.onfocus=()=>vsCheckpoint();el.oninput=()=>{n[key]=el.value;vsChanged()}}
 document.querySelectorAll('[data-vs-ref]').forEach(el=>el.onchange=()=>{try{vsCheckpoint();if(el.checked)VisualGraph.connect(p.nodes,el.dataset.vsRef,n.id);else n.refs=n.refs.filter(id=>id!==el.dataset.vsRef);vsChanged()}catch(e){el.checked=false;toast(e.message)}});
 $('#vs-node-upload').onclick=()=>{$('#vs-upload').dataset.target=n.id;$('#vs-upload').click()};$('#vs-node-library').onclick=()=>vsLibrary(n.id);
 if($('#vs-review'))$('#vs-review').onclick=()=>vsAction(async()=>{await vsSave();vsMerge(await api('/api/visual-projects/review',{id:v.project.id,version:v.project.version,node_id:n.id}))});
 if($('#vs-version'))$('#vs-version').onchange=e=>vsAdopt(n.id,{version_id:e.target.value});
 if($('#vs-candidate'))$('#vs-candidate').onchange=e=>{v.candidates[n.id]=e.target.value;vsInspector()};
 if($('#vs-adopt'))$('#vs-adopt').onclick=()=>vsAdopt(n.id,{job_id:j.id});
 if($('#vs-active-preview')){
  $('#vs-active-preview').onclick=()=>previewAsset(a);
  const row=document.createElement('div');row.className='vs-row';
  row.innerHTML=`<button class="button secondary" id="vs-copy-image">复制图片</button><a class="button secondary" href="${esc(a.url)}" download>下载图片</a>`;
  $('#vs-active-preview').after(row);$('#vs-copy-image').onclick=()=>vsCopyImage(a);
 }
 if($('#vs-candidate-preview'))$('#vs-candidate-preview').onclick=()=>previewAsset(candidate);
 if($('#vs-video-model'))$('#vs-video-model').onchange=e=>state.selected.video=e.target.value;
 if($('#vs-to-video'))$('#vs-to-video').onclick=()=>vsToVideo(n.id);
}
function vsPoint(e){const r=$('#vs-canvas').getBoundingClientRect(),t=visualStudio.project.viewport;return {x:(e.clientX-r.left-t.x)/t.zoom,y:(e.clientY-r.top-t.y)/t.zoom}}
async function vsCopyImage(asset){
 try{const png=(async()=>{const response=await fetch(asset.url);if(!response.ok)throw Error('图片读取失败');const blob=await response.blob();if(blob.type==='image/png')return blob;const bitmap=await createImageBitmap(blob),canvas=document.createElement('canvas');canvas.width=bitmap.width;canvas.height=bitmap.height;canvas.getContext('2d').drawImage(bitmap,0,0);bitmap.close();return await new Promise((resolve,reject)=>canvas.toBlob(b=>b?resolve(b):reject(Error('图片转换失败')),'image/png'))})();await navigator.clipboard.write([new ClipboardItem({'image/png':png})]);toast('图片已复制，可粘贴到画布或其他应用')}catch(e){toast('复制图片失败：'+e.message+'；也可以下载原图')}
}
function vsBindCanvas(){
 const canvas=$('#vs-canvas'),v=visualStudio;
 canvas.oncontextmenu=e=>{if(!vsTyping(e.target))e.preventDefault()};
 canvas.onwheel=e=>{if(vsTyping(e.target))return;e.preventDefault();vsZoom(Math.exp(-e.deltaY*.001),e.clientX,e.clientY)};
 canvas.onpointerdown=e=>{
  if(v.busy||e.button===2)return;if(e.button===0&&e.target.closest('input,textarea,select,a,button:not(.vs-port)'))return;canvas.focus();const p=v.project,r=canvas.getBoundingClientRect();
  if(e.button===1||v.space){e.preventDefault();v.drag={mode:'pan',x:e.clientX,y:e.clientY,viewport:{...p.viewport}}}
  else if(e.target.closest('[data-vs-out]')){const source=e.target.closest('[data-vs-out]').dataset.vsOut;v.drag={mode:'link',source,end:vsPoint(e)}}
  else if(e.target.closest('[data-vs-node]')){
   const id=e.target.closest('[data-vs-node]').dataset.vsNode;
   if(e.shiftKey||e.ctrlKey||e.metaKey){if(v.selected.has(id))v.selected.delete(id);else v.selected.add(id)}else if(!v.selected.has(id))v.selected=new Set([id]);
   if(e.target.closest('.vs-node-head')){vsCheckpoint();v.drag={mode:'nodes',start:vsPoint(e),positions:p.nodes.filter(n=>v.selected.has(n.id)).map(n=>({id:n.id,x:n.x,y:n.y}))}}
   vsCanvasStatus();
  }else{
   if(!e.shiftKey)v.selected.clear();v.drag={mode:'select',sx:e.clientX-r.left,sy:e.clientY-r.top,previous:new Set(v.selected)};
   vsDrawCanvas();vsInspector();
  }
  if(v.drag)canvas.setPointerCapture(e.pointerId);
 };
 canvas.onpointermove=e=>{
  const d=v.drag,p=v.project;if(!d)return;
  if(d.mode==='pan'){p.viewport.x=d.viewport.x+e.clientX-d.x;p.viewport.y=d.viewport.y+e.clientY-d.y;vsTransform()}
  if(d.mode==='link'){d.end=vsPoint(e);vsDrawLinks()}
  if(d.mode==='nodes'){const pos=vsPoint(e);d.positions.forEach(o=>{const n=p.nodes.find(n=>n.id===o.id);n.x=o.x+pos.x-d.start.x;n.y=o.y+pos.y-d.start.y;const el=document.querySelector(`[data-vs-node="${n.id}"]`);el.style.left=n.x+'px';el.style.top=n.y+'px'});vsDrawLinks()}
  if(d.mode==='select'){
   const r=canvas.getBoundingClientRect(),x=e.clientX-r.left,y=e.clientY-r.top,box=$('#vs-marquee');const left=Math.min(d.sx,x),top=Math.min(d.sy,y),width=Math.abs(x-d.sx),height=Math.abs(y-d.sy);
   Object.assign(box.style,{display:'block',left:left+'px',top:top+'px',width:width+'px',height:height+'px'});
   const t=p.viewport;v.selected=new Set(d.previous);for(const n of p.nodes){const nx=n.x*t.zoom+t.x,ny=n.y*t.zoom+t.y;if(nx<left+width&&nx+VisualGraph.width*t.zoom>left&&ny<top+height&&ny+VisualGraph.height*t.zoom>top)v.selected.add(n.id)}
   document.querySelectorAll('[data-vs-node]').forEach(el=>el.classList.toggle('selected',v.selected.has(el.dataset.vsNode)));
  }
 };
 canvas.onpointerup=e=>{
  const d=v.drag;if(!d)return;
  if(d.mode==='link'){const target=document.elementFromPoint(e.clientX,e.clientY)?.closest('[data-vs-in]')?.dataset.vsIn;if(target)try{vsCheckpoint();VisualGraph.connect(v.project.nodes,d.source,target);vsChanged()}catch(err){toast(err.message)}}
  if(['pan','nodes'].includes(d.mode))vsChanged(false);v.drag=null;$('#vs-marquee').style.display='none';vsDrawCanvas();vsInspector();
 };
 canvas.onpointercancel=()=>{v.drag=null;$('#vs-marquee').style.display='none';vsDrawCanvas()};
 canvas.ondragover=e=>e.preventDefault();canvas.ondrop=e=>{e.preventDefault();vsUpload([...e.dataTransfer.files])};
}
function vsZoom(factor,cx,cy){const canvas=$('#vs-canvas');if(!canvas)return;const r=canvas.getBoundingClientRect(),p=visualStudio.project,t=p.viewport,x=(cx??r.left+r.width/2)-r.left,y=(cy??r.top+r.height/2)-r.top,z=Math.min(2,Math.max(.15,t.zoom*factor));p.viewport={x:x-(x-t.x)*z/t.zoom,y:y-(y-t.y)*z/t.zoom,zoom:z};vsChanged(false);vsTransform()}
function vsFit(selected=false){const canvas=$('#vs-canvas');if(!canvas)return;const v=visualStudio;v.project.viewport=VisualGraph.fit(selected?v.project.nodes.filter(n=>v.selected.has(n.id)):v.project.nodes,canvas.clientWidth,canvas.clientHeight);vsChanged(false);vsTransform()}
function vsUndo(redo){const v=visualStudio,from=redo?v.redo:v.undo,to=redo?v.undo:v.redo;if(v.busy||!from.length)return;to.push(VisualGraph.clone(v.project));v.project=from.pop();v.selected=new Set([...v.selected].filter(id=>v.project.nodes.some(n=>n.id===id)));if(!v.selected.size&&v.project.nodes.length)v.selected.add(v.project.nodes.at(-1).id);v.dirty=true;renderVisualStudio()}
function vsRemove(){const v=visualStudio;if(!v.selected.size)return;vsEdit(()=>{v.project.nodes=v.project.nodes.filter(n=>!v.selected.has(n.id));v.project.nodes.forEach(n=>n.refs=n.refs.filter(id=>!v.selected.has(id)));v.selected.clear()})}
function vsCopyData(){const v=visualStudio;if(!v.selected.size)throw Error('先选择要复制的节点');v.clipboard=VisualGraph.serialize(v.project.nodes,v.selected);return JSON.stringify(v.clipboard)}
async function vsCopy(){try{const text=vsCopyData();await navigator.clipboard.writeText(text);toast('已复制节点及选中节点之间的连线')}catch(e){toast(e.name==='NotAllowedError'?'浏览器未允许读取剪贴板，请在画布按Ctrl+C复制':e.message)}}
function vsPaste(data){try{const v=visualStudio;if(v.busy)return;const nodes=VisualGraph.paste(data,v.project.nodes);vsEdit(()=>{v.project.nodes.push(...nodes);v.selected=new Set(nodes.map(n=>n.id))});for(const n of nodes)if(n.upload_id&&!state.assets[n.upload_id])api('/api/uploads/'+n.upload_id).then(a=>{state.assets[a.id]=a;if(state.page==='visual'){vsDrawCanvas();vsInspector()}}).catch(e=>toast(e.message));toast(`已粘贴${nodes.length}个节点；请保存项目`)}catch(e){toast(e.message)}}
function vsExport(){const v=visualStudio,data={...VisualGraph.serialize(v.project.nodes,new Set(v.project.nodes.map(n=>n.id))),title:v.project.title,story:v.project.story,ratio:v.project.ratio};const blob=new Blob([JSON.stringify(data,null,2)],{type:'application/json'}),a=document.createElement('a'),url=URL.createObjectURL(blob);a.href=url;a.download=(v.project.title||'定稿画布')+'.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)}
async function vsUpload(files,target=null){
 const list=files.filter(f=>f.type.startsWith('image/'));if(!list.length)return toast('请选择或粘贴PNG、JPEG、WebP图片');
 if(target&&list.length>1)return toast('替换节点一次只选一张图；多图请拖入画布');
 if(!target&&visualStudio.project.nodes.length+list.length>64)return toast('节点总数不能超过64');
 await vsAction(async()=>{
  await vsSave();
  for(const file of list){
   if(!['image/png','image/jpeg','image/webp'].includes(file.type)||file.size>10*1024*1024)throw Error('每张图片需为PNG、JPEG或WebP，且不超过10MiB');
   const raw=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result).split(',')[1]);reader.onerror=()=>reject(Error('无法读取图片'));reader.readAsDataURL(file)});
   const asset=await api('/api/uploads',{name:file.name||'剪贴板截图.png',data_base64:raw});state.assets[asset.id]=asset;
   if(target){vsMerge(await api('/api/visual-projects/adopt',{id:visualStudio.project.id,version:visualStudio.project.version,node_id:target,upload_id:asset.id}))}
   else{const p=visualStudio.project,n=VisualGraph.make('master','character',p.nodes.length);n.title=(file.name||'粘贴的图片').replace(/\.[^.]+$/,'').slice(0,80);n.prompt='保持这张参考图的主体身份、服装与关键视觉细节。';n.layout='single';n.ratio=asset.width>asset.height?'16:9':'9:16';n.upload_id=asset.id;p.nodes.push(n);visualStudio.selected=new Set([n.id]);visualStudio.dirty=true;await vsSave()}
  }
  toast('图片已保存到定稿画布，未调用模型');
 });
}
async function vsAdopt(nodeId,body){await vsAction(async()=>{await vsSave();vsMerge(await api('/api/visual-projects/adopt',{id:visualStudio.project.id,version:visualStudio.project.version,node_id:nodeId,...body}));toast('已采用该版本；下游旧结果保留，引用变化会标记')})}
async function vsGenerate(){
 const v=visualStudio,ids=[...v.selected];if(v.busy||!ids.length)return;
 if(!v.pending&&!await confirmAction('生成所选节点？',`将提交${ids.length}次图像请求，按所选平台计费。当前采用的图片保留，新图作为候选。`))return;
 await vsAction(async()=>{
  await vsSave();v.pending=v.pending||{id:v.project.id,version:v.project.version,node_ids:ids,request_id:VisualGraph.uid()};
  let result;try{result=await api('/api/visual-projects/generate',v.pending)}catch(e){if(e.httpStatus&&e.httpStatus<500)v.pending=null;throw e}v.pending=null;vsMerge(result);toast('已提交所选节点，结果完成后请检查并采用');
 });
}
function vsModal(title,body){let dlg=$('#vs-modal');if(!dlg){dlg=document.createElement('dialog');dlg.id='vs-modal';dlg.className='vs-modal';document.body.append(dlg)}dlg.classList.remove('film-modal');dlg.innerHTML=`<div class="vs-modal-head"><h2>${esc(title)}</h2><button class="button secondary" id="vs-modal-close">关闭</button></div>${body}`;$('#vs-modal-close').onclick=()=>dlg.close();if(!dlg.open)dlg.showModal();return dlg}
async function vsLegacyDialog(){
 try{const boards=(await api('/api/storyboards')).boards;const dlg=vsModal('导入旧分镜项目',`<p class="vs-status">导入到独立画布，旧项目与旧作品保留。原共同定稿会成为一个可替换节点。</p><div class="vs-choice-list">${boards.map(b=>`<button class="button secondary" data-vs-legacy="${b.id}">${esc(b.title)}</button>`).join('')||'<p>没有旧分镜项目。</p>'}</div>`);document.querySelectorAll('[data-vs-legacy]').forEach(el=>el.onclick=async()=>{if(visualStudio.dirty&&!await confirmAction('导入旧项目？','当前画布尚有未保存编辑，先保存后可保留。'))return;dlg.close();vsAction(async()=>{vsMerge(await api('/api/visual-projects/import-legacy',{legacy_id:el.dataset.vsLegacy}));visualStudio.dirty=false;visualStudio.undo=[];visualStudio.redo=[];visualStudio.selected.clear();visualStudio.projects=(await api('/api/visual-projects')).projects})})}catch(e){toast(e.message)}
}
async function vsLibrary(nodeId){
 try{const jobs=(await api('/api/jobs')).jobs,items=libraryImages(jobs);const dlg=vsModal('选择作品作为此节点的新版本','<input id="vs-library-search" placeholder="搜索图片描述"><div class="vs-library-grid" id="vs-library-grid"></div>');
  const draw=()=>{const q=$('#vs-library-search').value.toLowerCase();$('#vs-library-grid').innerHTML=items.filter(a=>a.title.toLowerCase().includes(q)).map(a=>`<button data-vs-work="${a.key}"><img src="${esc(a.url)}" alt="${esc(a.title.slice(0,70))}" loading="lazy"><small>${esc(a.title.slice(0,80))}</small></button>`).join('')||'<p>没有可用的本机图片。</p>';document.querySelectorAll('[data-vs-work]').forEach(el=>el.onclick=()=>{const a=items.find(i=>i.key===el.dataset.vsWork);dlg.close();vsAction(async()=>{await vsSave();const upload=await api('/api/library/image',{job_id:a.job_id,asset_index:a.asset_index});vsMerge(await api('/api/visual-projects/adopt',{id:visualStudio.project.id,version:visualStudio.project.version,node_id:nodeId,upload_id:upload.id}))})})};$('#vs-library-search').oninput=draw;draw();
 }catch(e){toast(e.message)}
}
function vsApplyVideo(data,provider){
 const caps=capabilities(provider);if(!caps.reference_images&&!caps.first_frame)throw Error('所选视频模型不支持图片输入，请先更换模型');
 if(!data.prompt.trim())throw Error('请先填写此镜头的视频提示词，再送往视频');
 const o=videoOptions(provider);if(o.ratios?.length&&!o.ratios.some(r=>r.value===data.ratio&&r.enabled))throw Error('所选视频模型不支持此镜头画幅，请更换模型');
 if(typeof creative!=='undefined')delete creative.draftId.video;const draft=makeDraft();draft.collection_id='visual:'+visualStudio.project.id;draft.prompt=data.prompt;draft.mode=caps.first_frame?'first':'reference';if(caps.first_frame)draft.assets.first_frame=data.asset.id;else draft.assets.references=[data.asset.id];draft.parameters.aspect_ratio=data.ratio;
 if(['weijin_video','ark_video','comfy_h3'].includes(provider.protocol)){draft.size='auto';draft.seconds=o.durations[0]||15}
 else{draft.size=data.ratio==='9:16'?'720x1280':data.ratio==='16:9'?'1280x720':'auto';draft.seconds=state.drafts.video.seconds||4}
 state.assets[data.asset.id]=data.asset;state.drafts.video=draft;state.selected.video=provider.id;
}
async function vsToVideo(nodeId){
 const provider=chosen('video');if(!provider)return toast('请先接入视频模型');
 if((state.drafts.video.prompt||state.drafts.video.assets.references.length||state.drafts.video.assets.first_frame)&&!await confirmAction('替换视频草稿？','将使用此镜头当前采用的图片、视频提示词与画幅，不会提交生成。'))return;
 await vsAction(async()=>{await vsSave();const data=await api('/api/visual-projects/transfer',{id:visualStudio.project.id,version:visualStudio.project.version,node_id:nodeId});vsApplyVideo(data,provider);storyboardView.open=false;$('#vs-modal')?.close();go('video');toast('已采用当前图片版本和'+data.ratio+'画幅，请检查视频参数后生成')});
}
function vsTyping(el){return !!el?.closest('input,textarea,select,[contenteditable="true"]')}
function vsKeyboardActive(){return state.page==='visual'&&visualStudio.project&&!visualStudio.busy&&!document.querySelector('dialog[open]')}
document.addEventListener('keydown',e=>{
 if(!vsKeyboardActive())return;const key=e.key.toLowerCase(),mod=e.ctrlKey||e.metaKey;
 if(mod&&key==='s'){e.preventDefault();vsAction(vsSave);return}if(vsTyping(e.target))return;
 if(e.code==='Space'){e.preventDefault();visualStudio.space=true}
 if(mod&&['s','z','y','a','d'].includes(key)){e.preventDefault();if(key==='s')vsAction(vsSave);if(key==='z')vsUndo(e.shiftKey);if(key==='y')vsUndo(true);if(key==='a'){visualStudio.selected=new Set(visualStudio.project.nodes.map(n=>n.id));vsDrawCanvas();vsInspector()}if(key==='d')vsPaste(VisualGraph.serialize(visualStudio.project.nodes,visualStudio.selected))}
 if(e.key==='Delete'||e.key==='Backspace'){e.preventDefault();vsRemove()}
 if(e.key==='Escape'){visualStudio.selected.clear();vsDrawCanvas();vsInspector()}
});
document.addEventListener('keyup',e=>{if(e.code==='Space')visualStudio.space=false});window.addEventListener('blur',()=>visualStudio.space=false);
document.addEventListener('copy',e=>{if(!vsKeyboardActive()||vsTyping(e.target)||!visualStudio.selected.size)return;try{e.clipboardData.setData('text/plain',vsCopyData());e.preventDefault();toast('节点已复制，可在本项目或其他定稿项目粘贴')}catch(err){toast(err.message)}});
document.addEventListener('paste',e=>{
 if(!vsKeyboardActive())return;const files=[...(e.clipboardData?.items||[])].filter(i=>i.kind==='file'&&i.type.startsWith('image/')).map(i=>i.getAsFile()).filter(Boolean);
 if(files.length){e.preventDefault();vsUpload(files);return}if(vsTyping(e.target))return;
 const text=e.clipboardData?.getData('text/plain');if(!text)return;try{const data=JSON.parse(text);if(data.format==='guangyu-visual-nodes'){e.preventDefault();vsPaste(data)}}catch{}
});
window.addEventListener('beforeunload',e=>{if(visualStudio.dirty){e.preventDefault();e.returnValue=''}});
let vsPolling=false;
async function vsPoll(){const v=visualStudio;if(vsPolling||v.busy||!v.project?.id||!v.project.jobs?.some(j=>active(j)||j.archive_status==='pending'))return;vsPolling=true;const id=v.project.id;try{const p=await api('/api/visual-projects?id='+id);if(v.project?.id!==id||v.busy)return;if(v.dirty){v.project.jobs=p.jobs}else vsMerge(p);if(state.page==='visual'){vsDrawCanvas();if(!vsTyping(document.activeElement))vsInspector()}else if(['image','video','audio'].includes(state.page))updateResult();else if(state.page==='history')renderHistory()}catch(e){v.error=e.message}finally{vsPolling=false}}
setInterval(vsPoll,2500);
