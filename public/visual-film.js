'use strict';
let visualFilm=null;
const visualFilmPending=new Map();
let vfPlanTimer=null,vfPlanSequence=0;
function vfProviders(){return state.providers.filter(p=>p.kind==='video'&&providerUsable(p)&&capabilities(p).reference_images)}
async function chooseVisualFilm(){
 try{const projects=(await api('/api/visual-projects')).projects;vsModal('选择已保存的分镜项目',`<div class="vs-choice-list">${projects.map(p=>`<button class="button secondary" data-film-project="${p.id}">${esc(p.title)}</button>`).join('')||'<p>还没有保存的分镜项目。</p>'}</div>`);document.querySelectorAll('[data-film-project]').forEach(el=>el.onclick=async()=>{try{await openVisualFilm(await api('/api/visual-projects?id='+el.dataset.filmProject))}catch(e){toast(e.message)}})}catch(e){toast(e.message)}
}
async function openVisualFilm(project){
 const providers=vfProviders(),saved=project.film_options||{},shots=project.nodes.filter(n=>n.kind==='shot');
 if(!shots.length)return toast('请先添加分镜节点并采用图片');
 const ids=(saved.node_ids||[]).filter(id=>shots.some(n=>n.id===id)),order=[...ids,...shots.map(n=>n.id).filter(id=>!ids.includes(id))];
 const provider=providers.find(p=>p.id===saved.provider_id)||providers.find(p=>p.id===state.selected.video)||providers[0],o=videoOptions(provider);
 visualFilm={project:VisualGraph.clone(project),order,selected:new Set(ids.length?ids:order),provider:provider?.id||'',seconds:saved.seconds||o.durations[0]||15,execution_mode:saved.execution_mode||'serial',plan:null,durations:new Map(ids.map((id,i)=>[id,saved.durations?.[i]])),reviews:new Set(),busy:false};
 if(!ids.length)vfDistribute();vfRender();
}
function vfNodes(){const f=visualFilm;return f.order.map(id=>f.project.nodes.find(n=>n.id===id))}
function vfSelected(){return vfNodes().filter(n=>visualFilm.selected.has(n.id))}
function vfDistribute(){const f=visualFilm,nodes=vfSelected();if(!nodes.length)return;let used=0;nodes.forEach((n,i)=>{const t=i===nodes.length-1?Math.round((f.seconds-used)*10)/10:Math.floor(f.seconds/nodes.length*10)/10;f.durations.set(n.id,t);used+=t})}
function vfError(message){const el=$('#film-error');if(el){el.hidden=false;el.textContent=message}}
function vfRender(){
 const f=visualFilm,providers=vfProviders(),provider=providers.find(p=>p.id===f.provider),o=videoOptions(provider),pending=visualFilmPending.has(f.project.id);
 const dlg=vsModal('分镜 → 整片视频',`<div class="film-workflow"><p class="film-intro">${esc(f.project.title)} · 按下方顺序生成一条视频</p><div class="film-controls"><label>视频模型<select id="film-provider">${providers.map(p=>`<option value="${p.id}" ${p.id===f.provider?'selected':''}>${esc(p.name)}</option>`).join('')||'<option value="">尚未接入多图视频模型</option>'}</select></label><label>整片时长 · 秒<input id="film-seconds" type="number" min="1" max="600" step="0.1" value="${f.seconds}"></label><label>提交方式<select id="film-mode"><option value="serial" ${f.execution_mode==='serial'?'selected':''}>串行 · 逐段提交</option><option value="parallel" ${f.execution_mode==='parallel'?'selected':''}>并行 · 最多 3 段</option></select></label><button class="button secondary" id="film-distribute">均分时长</button></div><div class="film-shots">${vfNodes().map((n,i)=>{const a=vsCurrent(n)?.asset,selected=f.selected.has(n.id);return `<article class="film-shot ${selected?'':'omitted'}" data-film-node="${n.id}"><div class="film-shot-image">${a?`<img src="${esc(a.url)}" alt="${esc(n.title)}">`:'<span>尚未采用图片</span>'}</div><div class="film-shot-content"><div class="film-shot-head"><label><input type="checkbox" data-film-select="${n.id}" ${selected?'checked':''}>${esc(n.title)}</label><span class="film-range"></span><button data-film-move="${n.id}" data-direction="-1" ${i===0?'disabled':''} aria-label="上移 ${esc(n.title)}">↑</button><button data-film-move="${n.id}" data-direction="1" ${i===f.order.length-1?'disabled':''} aria-label="下移 ${esc(n.title)}">↓</button></div><div class="film-shot-prompt"><textarea data-film-prompt="${n.id}" rows="3" maxlength="16000" placeholder="必填：这一镜头的动作、运镜、对白…">${esc(n.video_prompt)}</textarea><label>秒<input type="number" min="0.1" max="600" step="0.1" data-film-duration="${n.id}" value="${f.durations.get(n.id)||''}" ${selected?'':'disabled'}></label></div>${!a?'<p class="film-warning">请返回画布，为此分镜采用一张图片。</p>':n.stale?`<div class="film-review"><details><summary>图片需复核 · 查看当前画面描述</summary><p>${esc(n.prompt)}</p></details><label><input type="checkbox" data-film-review="${n.id}" ${f.reviews.has(n.id)?'checked':''}>我已核对，此图片与当前描述、参考一致</label></div>`:''}</div></article>`}).join('')}</div><div class="film-total" id="film-total"></div><div class="film-warning" id="film-readiness"></div><div id="film-plan" class="film-plan" aria-live="polite"></div><p class="film-note">超出模型单次时长自动拆段，完成后按顺序合成一条视频，保留原片段和音轨。镜头衔接仍需检查；尾段超出成片所需的部分会裁去。</p><p class="film-error" id="film-error" role="alert" hidden></p><div class="film-footer"><button class="button secondary" id="film-save">保存配置</button><button class="button primary" id="film-generate" ${provider?'':'disabled'}>${pending?'确认上次提交结果':'生成整片视频 · 1 次任务'}</button></div></div>`);dlg.classList.add('film-modal');
 $('#film-provider').onchange=e=>{f.provider=e.target.value;vfRender()};
 $('#film-mode').onchange=e=>{f.execution_mode=e.target.value;vfTotals()};
 $('#film-seconds').onchange=e=>{f.seconds=Number(e.target.value);vfDistribute();vfRender()};$('#film-distribute').onclick=()=>{vfDistribute();vfRender()};
 dlg.querySelectorAll('[data-film-select]').forEach(el=>el.onchange=()=>{el.checked?f.selected.add(el.dataset.filmSelect):f.selected.delete(el.dataset.filmSelect);vfDistribute();vfRender()});
 dlg.querySelectorAll('[data-film-move]').forEach(el=>el.onclick=()=>{const i=f.order.indexOf(el.dataset.filmMove),j=i+Number(el.dataset.direction);[f.order[i],f.order[j]]=[f.order[j],f.order[i]];vfRender()});
 dlg.querySelectorAll('[data-film-prompt]').forEach(el=>el.oninput=()=>{f.project.nodes.find(n=>n.id===el.dataset.filmPrompt).video_prompt=el.value;vfTotals()});
 dlg.querySelectorAll('[data-film-duration]').forEach(el=>el.oninput=()=>{f.durations.set(el.dataset.filmDuration,Number(el.value));f.seconds=+vfSelected().reduce((s,n)=>s+(f.durations.get(n.id)||0),0).toFixed(3);$('#film-seconds').value=f.seconds;vfTotals()});
 dlg.querySelectorAll('[data-film-review]').forEach(el=>el.onchange=()=>{el.checked?f.reviews.add(el.dataset.filmReview):f.reviews.delete(el.dataset.filmReview);vfTotals()});
 $('#film-save').onclick=()=>vfSaveOnly();$('#film-generate').onclick=vfGenerate;vfTotals();
 if(pending){dlg.querySelectorAll('.film-controls input,.film-controls select,.film-controls button,.film-shots input,.film-shots textarea,.film-shots button,#film-save').forEach(el=>el.disabled=true);vfError('上次提交尚未确认。点击“确认上次提交结果”使用同一请求编号查询，不会重复创建任务。')}
}
function vfTotals(){const f=visualFilm;let total=0;for(const n of vfNodes()){const el=document.querySelector(`[data-film-node="${n.id}"] .film-range`);if(f.selected.has(n.id)){const next=total+(f.durations.get(n.id)||0);el.textContent=`${+total.toFixed(1)}–${+next.toFixed(1)} 秒`;total=next}else el.textContent='不包含'}const info=$('#film-total');info.textContent=`${f.selected.size} 个镜头 · 已分配 ${+total.toFixed(1)} / ${f.seconds} 秒`;info.classList.toggle('invalid',Math.abs(total-f.seconds)>.01);const nodes=vfSelected(),missing=nodes.filter(n=>!n.video_prompt.trim()).length,review=nodes.filter(n=>n.stale&&!f.reviews.has(n.id)).length,images=nodes.filter(n=>!vsCurrent(n)?.asset).length;$('#film-readiness').textContent=[images?images+' 镜尚未采用图片':'',review?review+' 张图片待复核':'',missing?missing+' 镜缺少视频提示词':''].filter(Boolean).join(' · ');vfSchedulePlan()}
async function vfSave(){const f=visualFilm,nodes=vfSelected();f.project.film_options={provider_id:f.provider,seconds:f.seconds,execution_mode:f.execution_mode,node_ids:nodes.map(n=>n.id),durations:nodes.map(n=>f.durations.get(n.id)||0)};f.project=await api('/api/visual-projects/save',f.project);if(visualStudio.project?.id===f.project.id){vsMerge(f.project);visualStudio.dirty=false}}
async function vfSaveOnly(){const f=visualFilm;if(f.busy)return;f.busy=true;$('#film-save').disabled=true;$('#film-generate').disabled=true;try{await vfSave();toast('整片顺序、时长和视频提示词已保存');vfRender()}catch(e){vfError(e.message)}finally{f.busy=false;if($('#film-save'))$('#film-save').disabled=false;vfSchedulePlan()}}
async function vfGenerate(){
 const f=visualFilm;if(f.busy)return;f.busy=true;const dlg=$('#vs-modal');dlg.querySelector('.film-workflow').inert=true;$('#vs-modal-close').disabled=true;
 try{
  let body=visualFilmPending.get(f.project.id);
  if(!body){const nodes=vfSelected();if(nodes.length<2||nodes.length>9)throw Error('请选择 2–9 个分镜');if(!f.plan)throw Error('请先填写有效时长，等待拆段计划完成');for(const n of nodes){if(!vsCurrent(n)?.asset)throw Error(`“${n.title}”尚未采用图片`);if(!n.video_prompt.trim())throw Error(`请填写“${n.title}”的视频提示词`);if(n.stale&&!f.reviews.has(n.id))throw Error(`“${n.title}”需复核，请核对图片后勾选确认`)}
   await vfSave();body={id:f.project.id,version:f.project.version,request_id:VisualGraph.uid(),provider_id:f.provider,seconds:f.seconds,execution_mode:f.execution_mode,node_ids:nodes.map(n=>n.id),durations:nodes.map(n=>f.durations.get(n.id)),review_versions:Object.fromEntries(nodes.filter(n=>f.reviews.has(n.id)).map(n=>[n.id,vsCurrent(n).id]))};visualFilmPending.set(f.project.id,body);
  }
  const result=await api('/api/visual-projects/film-generate',body);visualFilmPending.delete(f.project.id);f.project=result.project;if(visualStudio.project?.id===f.project.id){vsMerge(result.project);visualStudio.dirty=false}
  const j=result.job;state.jobs=state.jobs.filter(x=>x.id!==j.id);state.jobs.unshift(j);state.currentJob.video=j.id;state.selected.video=j.provider_id;
  if(!j.film_batch){const draft=makeDraft();Object.assign(draft,{prompt:j.prompt,size:j.size,seconds:j.seconds,parameters:j.parameters,collection_id:j.collection_id,mode:'reference',assets:{references:[],first_frame:null,last_frame:null,...j.input_assets}});state.drafts.video=draft;if(typeof creative!=='undefined')delete creative.draftId.video;}
  for(const n of result.project.nodes){const a=vsCurrent(n)?.asset;if(a)state.assets[a.id]=a}dlg.close();storyboardView.open=false;go('video');toast(j.film_batch?`已安排 ${j.film_segments.length} 段，完成后自动合成一条视频`:'整片视频已提交，完成后在当前项目作品合集中查看');
 }catch(e){if(e.httpStatus&&e.httpStatus<500)visualFilmPending.delete(f.project.id);vfRender();vfError(e.message+(visualFilmPending.has(f.project.id)?'；请确认上次提交结果，避免重复生成。':''))}finally{f.busy=false;if($('#vs-modal-close'))$('#vs-modal-close').disabled=false;$('#vs-modal .film-workflow')?.removeAttribute('inert')}
}

function vfSchedulePlan(){
 const f=visualFilm,sequence=++vfPlanSequence;clearTimeout(vfPlanTimer);f.plan=null;
 if(visualFilmPending.has(f.project.id))return;
 const button=$('#film-generate');if(button){button.disabled=true;button.textContent='正在计算拆段…'}
 vfPlanTimer=setTimeout(async()=>{try{const plan=await api('/api/visual-projects/film-plan',{provider_id:f.provider,durations:vfSelected().map(n=>f.durations.get(n.id)||0),execution_mode:f.execution_mode});if(sequence!==vfPlanSequence||f!==visualFilm)return;f.plan=plan;
  const el=$('#film-plan');if(!el)return;const clips=plan.segments,extra=+(plan.requested_seconds-plan.seconds).toFixed(3);
  el.innerHTML=`<strong>${clips.length} 次模型任务 · ${plan.execution_mode==='parallel'?'最多 3 段并行':'串行提交'} · 最终 ${plan.seconds} 秒</strong><span>请求合计 ${plan.requested_seconds} 秒${extra>0?`，超出部分 ${extra} 秒会裁去，平台可能按完整请求计费`:''}</span><details><summary>查看各段</summary>${clips.map(s=>`<div>第 ${s.index} 段：成片 ${s.start}–${s.end} 秒 · 请求 ${s.request_seconds} 秒 · 使用 ${s.used_seconds} 秒</div>`).join('')}</details>`;
  if(button){button.disabled=f.busy;button.textContent=`生成整片视频 · ${clips.length} 次任务`}
 }catch(e){if(sequence!==vfPlanSequence)return;const el=$('#film-plan');if(el)el.textContent=e.message;if(button)button.textContent='请完善时长配置'}},180);
}
function vfProgress(job){
 if(job.film_parent_id)return `<div class="film-parent-link"><button class="text-button" data-select-job="${job.film_parent_id}">← 返回整片进度</button> · 第 ${job.film_segment_index} 段</div>`;
 if(!job.film_batch)return '';
 if(job.status==='succeeded'&&!job.film_segments?.length)return `<section class="film-progress"><div class="film-progress-heading"><strong>整片已完成</strong><span>${Number(job.seconds)||0} 秒 · 已保留成片</span></div></section>`;
 const phase=job.status==='succeeded'?'整片已完成':{generating:'片段生成中',paused:'部分片段待处理',composing:'正在本机合成',compose_failed:'本机合成待重试',done:'整片已完成'}[job.film_phase]||'等待提交';
 return `<section class="film-progress"><div class="film-progress-heading"><strong>${phase}</strong><span>${job.film_completed||0} / ${job.film_segments.length} 段 · ${job.film_execution_mode==='parallel'?'并行':'串行'} · ${job.seconds} 秒</span></div>${job.film_phase==='compose_failed'?`<button class="button secondary" data-film-retry="${job.id}">重试本机合成</button>`:''}<div class="film-progress-clips">${job.film_segments.map(s=>{const child=state.jobs.find(j=>j.id===s.job_id),waiting=child?.film_dispatch_state==='waiting',label=waiting?'等待提交':child?.status==='succeeded'&&child?.archive_status!=='saved'?'待保存':statusNames[child?.status]||'读取中';return `<div><button class="text-button" data-select-job="${s.job_id}">第 ${s.index} 段 · ${s.start}–${s.end} 秒</button><span>${esc(label)}</span>${child?.status==='failed'?`<button class="text-button" data-film-retry="${job.id}" data-film-retry-child="${child.id}">仅重试此段</button>`:child?.status==='interrupted'&&child?.upstream_id?`<button class="text-button" data-resume="${child.id}">查询原任务</button>`:child?.status==='succeeded'&&['failed','partial'].includes(child?.archive_status)?`<button class="text-button" data-archive="${child.id}">重试保存</button>`:''}</div>`}).join('')}</div></section>`;
}
document.addEventListener('click',async event=>{
 const button=event.target.closest('[data-film-retry]');if(!button)return;
 const child=button.dataset.filmRetryChild;if(child&&!confirm('仅重新生成这个失败片段，其他已完成片段会保留。这会新增一次模型请求，可能产生费用。继续？'))return;
 button.disabled=true;try{const job=await api('/api/visual-projects/film-retry',{id:button.dataset.filmRetry,retry_job_id:child});state.jobs=state.jobs.map(j=>j.id===job.id?job:j);state.currentJob.video=job.id;updateResult(true);toast(child?'已安排失败片段重试':'正在重新合成，未提交模型生成')}catch(e){toast(e.message);button.disabled=false}
});
