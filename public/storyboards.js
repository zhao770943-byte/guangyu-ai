'use strict';
const storyboardView={open:false,board:null,projects:[],busy:false,dirty:false,loading:false,pending:null,error:'',transfers:{}};
const storyboardDefaults=[
 ['环境与出场','建立故事环境，以全景或全身构图呈现主角和关键穿搭、道具。选择故事开始时的一个自然静态瞬间，为后续动作留出空间。'],
 ['主要动作','根据脚本选择主角即将开始核心动作的瞬间。中景或半身构图，手部、关键道具与视线关系清晰，不要在一张图里表现多个动作。'],
 ['细节展示','突出故事中的关键物件、穿搭或人物表情，使用合适的近景或细节构图。保持参考图中的材质、配饰与色彩一致。'],
 ['结尾定格','表现故事结束时的状态与情绪，构图完整、姿态自然、留有呼吸感，适合视频片尾停留。']
];
const sbId=()=>crypto.randomUUID().replaceAll('-','');
function sbFresh(){return {id:null,version:0,title:'我的分镜项目',story:state.drafts.video.prompt||'',master_prompt:'',provider_id:state.providers.find(p=>p.kind==='image'&&providerUsable(p)&&p.capabilities?.reference_images)?.id||chosen('image')?.id||'',ratio:'9:16',shots:storyboardDefaults.map(([title,prompt])=>({id:sbId(),title,prompt,job_id:null})),jobs:[],busy:false}}
function sbJob(id){return storyboardView.board?.jobs?.find(j=>j.id===id)}
function sbAsset(j){return !j?.work_deleted_at&&j?.status==='succeeded'?j.result?.assets?.find(a=>a.type==='image'&&a.local):null}
function sbCanReference(){return state.providers.find(p=>p.id===storyboardView.board?.provider_id)?.capabilities?.reference_images}
function sbMerge(board){for(const j of board.jobs||[]){state.jobs=state.jobs.filter(x=>x.id!==j.id);state.jobs.unshift(j)}storyboardView.board=board}
async function sbOpen(){storyboardView.open=true;renderStudio('video')}
async function sbLoad(id){
 storyboardView.loading=true;storyboardView.error='';renderStoryboards();
 try{storyboardView.projects=(await api('/api/storyboards')).boards;const chosenId=id||storyboardView.projects[0]?.id;sbMerge(chosenId?await api('/api/storyboards?id='+encodeURIComponent(chosenId)):sbFresh());storyboardView.dirty=false;storyboardView.pending=null}
 catch(err){storyboardView.error=err.message}
 finally{storyboardView.loading=false;if(storyboardView.open&&state.page==='video')renderStoryboards()}
}
function renderStoryboards(){
 const v=storyboardView,b=v.board;
 $('#page').innerHTML=heading('分镜准备','先确认一张视觉定稿，再让每个镜头围绕同一人物、服装和场景展开。',`<button class="button secondary" id="sb-close">${icon('video')} 返回视频生成</button>`,'video')+`<section class="panel sb-project-bar"><label>本机项目<select id="sb-project"><option value="">${b&&!b.id?'未保存的新项目':'选择项目'}</option>${v.projects.map(p=>`<option value="${p.id}" ${p.id===b?.id?'selected':''}>${esc(p.title)}</option>`).join('')}</select></label><button class="button secondary" id="sb-new">${icon('plus')} 新建项目</button><button class="button secondary" id="sb-reload">重新载入</button><span id="sb-save-note">${v.dirty?'有未保存的修改':'项目保存在本机'}</span><button class="button primary" id="sb-save" ${!b?'disabled':''}>保存项目</button></section><p id="sb-error" class="sb-error" role="alert" ${v.error?'':'hidden'}>${esc(v.error)}</p>`;
 $('#sb-close').onclick=async()=>{if(v.dirty&&!await confirmAction('暂不保存分镜修改？','项目的未保存修改仍留在当前页面会话中；刷新页面将丢失这些修改。'))return;v.open=false;renderStudio('video')};
 $('#sb-new').onclick=async()=>{if(v.dirty&&!await confirmAction('新建分镜项目？','当前未保存的修改将被放弃。'))return;v.board=sbFresh();v.dirty=true;v.pending=null;renderStoryboards()};
 $('#sb-reload').onclick=async()=>{if(v.dirty&&!await confirmAction('重新载入项目？','当前未保存的修改将被放弃。'))return;sbLoad(b?.id)};
 $('#sb-project').onchange=async e=>{const id=e.target.value;if(!id)return;if(v.dirty&&!await confirmAction('切换项目？','当前未保存的修改将被放弃。')){e.target.value=b?.id||'';return}sbLoad(id)};
 if(!b||v.loading){$('#page').insertAdjacentHTML('beforeend',`<section class="panel sb-loading">${v.loading?'正在读取分镜项目…':'尚未读取项目'}</section>`);if(!v.loading&&!v.error)sbLoad();return}
 const images=state.providers.filter(p=>p.kind==='image'&&providerUsable(p));
 $('#page').insertAdjacentHTML('beforeend',`<div class="sb-layout"><section class="panel sb-brief"><div class="sb-section-title"><span>01</span><div><h2>创意与定稿</h2><p>先固定人物和视觉风格，再决定镜头。</p></div></div><label>项目名称<input id="sb-title" maxlength="80" value="${esc(b.title)}"></label><label>图像模型<select id="sb-provider">${images.length?images.map(p=>`<option value="${p.id}" ${p.id===b.provider_id?'selected':''}>${esc(p.name)} · ${p.capabilities.reference_images?'支持参考图':'不支持参考图'}</option>`).join(''):'<option value="">请先接入图像模型</option>'}</select></label><p id="sb-capability" class="field-hint"></p><label>整段创意 / 视频脚本<textarea id="sb-story" rows="7" maxlength="16000" placeholder="粘贴完整创意，包括人物、服装、环境与动作顺序。生成定稿图时会提炼为一个静态画面。">${esc(b.story)}</textarea></label><label>定稿图补充要求<textarea id="sb-master-prompt" rows="3" maxlength="6000" placeholder="例如：完整全身、服装和包清晰可辨；这里的要求也会传给每个分镜。">${esc(b.master_prompt)}</textarea></label><label>画幅<select id="sb-ratio">${['9:16','16:9','1:1','3:2','2:3','4:3','3:4'].map(r=>`<option ${b.ratio===r?'selected':''}>${r}</option>`).join('')}</select></label><p class="field-hint">支持比例参数的接口会直接传入；其他接口写入提示词，像素尺寸使用模型默认值。</p><button class="button primary wide" id="sb-master-generate">${icon('image')} ${b.master_job_id?'重新生成定稿图':'生成 1 张定稿图'}</button><p class="field-hint">调用上方图像模型。每次生成均按你的平台账户计费。</p></section><section class="panel sb-master"><div class="sb-section-title"><span>02</span><div><h2>确认定稿图</h2><p>全部分镜共用这张参考图，减少人物和服饰变化。</p></div></div><div id="sb-master-result"></div><button class="button primary wide" id="sb-confirm">确认此图，作为共同参考</button><p class="field-hint">重新生成并确认定稿图后，当前分镜结果关联会重置；旧作品仍在作品库。</p></section></div><section class="panel sb-shots"><div class="sb-shots-heading"><div class="sb-section-title"><span>03</span><div><h2>分镜安排</h2><p>先按镜头顺序修改描述。每张独立生成，不合成多宫格。</p></div></div><div class="sb-actions"><button class="button secondary" id="sb-add-shot">${icon('plus')} 添加镜头</button><button class="button primary" id="sb-generate-shots">${icon('spark')} 同时生成 ${b.shots.length} 张分镜</button></div></div><p class="sb-queue-note">一键提交全部镜头 · 最多 3 个任务并发，其余排队 · 失败镜头可单独重做 · 不自动生成视频</p><div class="sb-shot-grid">${b.shots.map((s,i)=>`<article class="sb-shot"><div class="sb-shot-top"><b>镜头 ${String(i+1).padStart(2,'0')}</b><button type="button" class="text-button" data-sb-remove="${s.id}">移除</button></div><label class="sr-only" for="sb-title-${s.id}">镜头 ${i+1} 标题</label><input id="sb-title-${s.id}" data-sb-title="${s.id}" value="${esc(s.title)}" maxlength="80"><label class="sr-only" for="sb-prompt-${s.id}">镜头 ${i+1} 描述</label><textarea id="sb-prompt-${s.id}" data-sb-prompt="${s.id}" rows="4" maxlength="4000">${esc(s.prompt)}</textarea><div id="sb-result-${s.id}"></div></article>`).join('')}</div></section>`);
 for(const [id,key] of [['sb-title','title'],['sb-provider','provider_id'],['sb-story','story'],['sb-master-prompt','master_prompt'],['sb-ratio','ratio']])$('#'+id).oninput=e=>{b[key]=e.target.value;sbDirty();sbUpdateResults()};
 document.querySelectorAll('[data-sb-title],[data-sb-prompt]').forEach(e=>e.oninput=()=>{const s=b.shots.find(s=>s.id===(e.dataset.sbTitle||e.dataset.sbPrompt));s[e.dataset.sbTitle?'title':'prompt']=e.value;sbDirty()});
 document.querySelectorAll('[data-sb-remove]').forEach(e=>e.onclick=()=>{if(b.shots.length===1)return toast('至少保留一个镜头');b.shots=b.shots.filter(s=>s.id!==e.dataset.sbRemove);sbDirty();renderStoryboards()});
 $('#sb-add-shot').onclick=()=>{if(b.shots.length>=8)return;b.shots.push({id:sbId(),title:'补充镜头',prompt:'描述这一镜头的静态画面、景别、姿态和道具位置。',job_id:null});sbDirty();renderStoryboards()};
 $('#sb-save').onclick=()=>sbAction(()=>sbCommit());
 $('#sb-master-generate').onclick=()=>sbGenerate('master');$('#sb-generate-shots').onclick=()=>sbGenerate('shots');
 $('#sb-confirm').onclick=()=>sbAction(async()=>{await sbCommit();sbMerge(await api('/api/storyboards/confirm',{id:v.board.id,version:v.board.version}));toast('定稿图已确认，可以批量生成分镜')});
 sbUpdateResults();
}
function sbDirty(){storyboardView.dirty=true;storyboardView.pending=null;const n=$('#sb-save-note');if(n)n.textContent='有未保存的修改'}
function sbPreview(j,placeholder){const a=sbAsset(j);return `<div class="sb-preview">${a?`<button type="button" data-sb-preview="${j.id}" aria-label="放大预览"><img src="${esc(a.url)}" alt="生成的分镜图"></button>`:`<div>${j&&active(j)?'<span class="spinner"></span>':icon('image')}<p>${j?j.work_deleted_at?'作品已从作品库删除':j.status==='succeeded'?'正在等待原图保存到本机':esc(statusNames[j.status]||j.status):placeholder}</p></div>`}</div>${j?`<div class="sb-result-status">${badge(j)}<span>${elapsed(j.elapsed_ms)}</span></div>${j.error?`<p class="sb-error">${esc(j.error)}</p>`:''}${j.archive_status==='failed'?`<p class="sb-error">原图保存失败，请到作品库重试保存；无需重新生成。</p>`:''}`:''}`}
function sbUpdateResults(){
 const v=storyboardView,b=v.board;if(!b||!$('#sb-master-result'))return;
 const locked=v.busy||b.busy,master=sbJob(b.master_job_id),confirmed=!!b.master_upload_id;
 $('#sb-master-result').innerHTML=sbPreview(master,'先生成一张视觉定稿图');
 $('#sb-capability').textContent=sbCanReference()?'此连接支持参考图，可用于定稿与分镜。':'当前图像连接不支持参考图，生成分镜前需更换；不会降级成无参考图生成。';
 $('#sb-confirm').textContent=confirmed?'已确认 · 全部分镜共用此图':'确认此图，作为共同参考';
 $('#page').querySelectorAll('input,textarea,select,button').forEach(e=>e.disabled=locked);
 $('#sb-confirm').disabled=locked||confirmed||!sbAsset(master);
 $('#sb-master-generate').disabled=locked||!b.provider_id;
 $('#sb-generate-shots').disabled=locked||!confirmed||!sbCanReference();
 $('#sb-add-shot').disabled=locked||b.shots.length>=8;
 // Navigation does not cancel background jobs.
 $('#sb-close').disabled=v.busy;$('#sb-reload').disabled=v.busy;$('#sb-new').disabled=v.busy;$('#sb-project').disabled=v.busy;
 for(const s of b.shots){const root=$('#sb-result-'+s.id);if(!root)continue;const j=sbJob(s.job_id),a=sbAsset(j),c=capabilities(chosen('video'));
  root.innerHTML=sbPreview(j,'等待定稿确认与分镜生成')+`<div class="sb-shot-actions"><button class="button secondary compact" data-sb-retry="${s.id}" ${locked||!confirmed||!sbCanReference()?'disabled':''}>${j?'重做这一镜头':'生成这一镜头'}</button>${a?`<a class="text-button" href="${esc(a.url)}" download="镜头-${esc(s.title)}">下载</a>`:''}</div>${a?`<div class="sb-transfer"><span>用于当前视频模型</span><button class="button secondary compact" data-sb-transfer="${j.id}" data-slot="references" ${!c.reference_images||v.busy?'disabled':''}>加入参考图</button><button class="button secondary compact" data-sb-transfer="${j.id}" data-slot="first_frame" ${!c.first_frame||v.busy?'disabled':''}>设为首帧</button><button class="button secondary compact" data-sb-transfer="${j.id}" data-slot="last_frame" ${!c.last_frame||v.busy?'disabled':''}>设为尾帧</button></div>`:''}`;
 }
 document.querySelectorAll('[data-sb-preview]').forEach(e=>e.onclick=()=>previewAsset(sbAsset(sbJob(e.dataset.sbPreview)),'分镜图'));
 document.querySelectorAll('[data-sb-retry]').forEach(e=>e.onclick=()=>sbGenerate('shot',e.dataset.sbRetry));
 document.querySelectorAll('[data-sb-transfer]').forEach(e=>e.onclick=()=>sbTransfer(e.dataset.sbTransfer,e.dataset.slot));
 $('#sb-error').hidden=!v.error;$('#sb-error').textContent=v.error;
}
async function sbCommit(){
 const v=storyboardView;if(!v.dirty&&v.board.id)return;
 const payload=Object.fromEntries(['id','version','title','story','master_prompt','provider_id','ratio','shots'].map(k=>[k,v.board[k]]));
 sbMerge(await api('/api/storyboards/save',payload));v.dirty=false;
 v.projects=(await api('/api/storyboards')).boards;
}
async function sbAction(fn){const v=storyboardView;if(v.busy)return;v.busy=true;v.error='';sbUpdateResults();try{await fn()}catch(err){v.error=err.message}finally{v.busy=false;if(v.open&&state.page==='video')renderStoryboards()}}
async function sbGenerate(stage,shot_id){
 const v=storyboardView,b=v.board;
 if(v.busy||b.busy)return;
 const existing=stage==='master'?b.master_job_id:stage==='shots'?b.shots.some(s=>s.job_id):b.shots.find(s=>s.id===shot_id)?.job_id;
 if(existing&&!v.pending&&!await confirmAction('重新生成图片？',stage==='shots'?`将重新提交 ${b.shots.length} 次图像生成，包括已成功的镜头。旧作品保留，每次调用可能产生费用。`:'将提交一次新的图像生成，旧作品保留，本次调用可能产生费用。'))return;
 await sbAction(async()=>{await sbCommit();const current=v.board;v.pending=v.pending||{id:current.id,version:current.version,request_id:sbId(),stage,shot_id};sbMerge(await api('/api/storyboards/generate',v.pending));v.pending=null;toast(stage==='master'?'定稿图已提交':'分镜已提交，最多 3 个任务同时执行')});
}
function sbAcceptVideoAsset(asset,slot){
 const p=chosen('video'),c=capabilities(p),d=state.drafts.video;
 if(!c[slot==='references'?'reference_images':slot])throw Error('当前视频模型不支持此素材模式');
 if(slot==='references'&&d.assets.references.includes(asset.id))return;
 if(slot==='references'&&d.assets.references.length>=(p?.protocol==='weijin_video'?9:8))throw Error('视频参考图已达到数量上限');
 state.assets[asset.id]=asset;
 if(slot==='references'){d.assets.references.push(asset.id);d.mode='reference'}
 else{d.assets[slot]=asset.id;d.mode=slot==='last_frame'||(d.assets.first_frame&&d.assets.last_frame)?'first_last':'first'}
}
async function sbTransfer(job_id,slot){await sbAction(async()=>{
 const c=capabilities(chosen('video'));if(!c[slot==='references'?'reference_images':slot])throw Error('请先选择支持此输入模式的视频模型');
 const cached=storyboardView.transfers[job_id],d=state.drafts.video,p=chosen('video');
 if(slot==='references'&&!d.assets.references.includes(cached?.id)&&d.assets.references.length>=(p?.protocol==='weijin_video'?9:8))throw Error('视频参考图已达到数量上限');
 const asset=cached||await api('/api/storyboards/transfer',{id:storyboardView.board.id,job_id});storyboardView.transfers[job_id]=asset;sbAcceptVideoAsset(asset,slot);toast('已加入视频草稿；返回视频生成后检查描述与素材，不会自动提交视频');
})}
let sbPolling=false;
async function sbPoll(){const v=storyboardView;if(sbPolling||v.busy||!v.board?.id||!v.board.busy)return;sbPolling=true;const id=v.board.id;try{const b=await api('/api/storyboards?id='+id);if(v.board?.id===id&&!v.busy){if(v.dirty){v.board.jobs=b.jobs;v.board.busy=b.busy}else sbMerge(b);if(v.open&&state.page==='video')sbUpdateResults()}}catch(err){v.error=err.message;if(v.open&&state.page==='video')sbUpdateResults()}finally{sbPolling=false}}
document.addEventListener('click',e=>{if(e.target.closest('[data-action="storyboard-open"]'))sbOpen()});
setInterval(sbPoll,2500);
