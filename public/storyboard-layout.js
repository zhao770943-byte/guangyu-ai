'use strict';
function sbLayout(b,images){
 const v=storyboardView;
 if(!b.shots.some(s=>s.id===v.activeShot))v.activeShot=b.shots[0]?.id;
 return `<nav class="sb-stage-nav" aria-label="分镜制作步骤"><button type="button" data-sb-stage="master"><span>1</span><div><b>视觉定稿</b><small id="sb-master-summary">生成并确认共同参考</small></div></button><span class="sb-stage-arrow">→</span><button type="button" data-sb-stage="shots"><span>2</span><div><b>分镜工作台</b><small id="sb-shots-summary">编排镜头，逐张检查画面</small></div></button></nav>
 <div id="sb-stage-master" class="sb-layout">
  <section class="panel sb-brief"><div class="sb-section-title"><div><h2>定义这部影片的视觉</h2><p>人物、服装、环境在这里统一。</p></div></div>
   <label>项目名称<input id="sb-title" maxlength="80" value="${esc(b.title)}"></label>
   <label>图像模型<select id="sb-provider">${images.length?images.map(p=>`<option value="${p.id}" ${p.id===b.provider_id?'selected':''}>${esc(p.name)} · ${p.capabilities.reference_images?'可生成参考分镜':'仅定稿图'}</option>`).join(''):'<option value="">请先接入图像模型</option>'}</select></label><p id="sb-capability" class="field-hint"></p>
   <label>创意与故事脚本<textarea id="sb-story" rows="6" maxlength="16000" placeholder="人物是谁？穿什么？在哪里？接下来发生什么？也可以直接粘贴完整视频脚本。">${esc(b.story)}</textarea></label>
   <div class="sb-form-row"><label>统一画幅<select id="sb-ratio">${['9:16','16:9','1:1','3:2','2:3','4:3','3:4'].map(r=>`<option ${b.ratio===r?'selected':''}>${r}</option>`).join('')}</select></label><span class="field-hint">用于定稿与全部镜头<br>像素尺寸保持模型默认</span></div>
   <details class="sb-extra" ${b.master_prompt?'open':''}><summary>人物、服装与画面补充要求</summary><label class="sr-only" for="sb-master-prompt">定稿补充要求</label><textarea id="sb-master-prompt" rows="3" maxlength="6000" placeholder="例如：完整全身、包与配饰清晰可见，所有分镜保持相同穿搭。">${esc(b.master_prompt)}</textarea></details>
   <button class="button primary wide" id="sb-master-generate">${icon('image')} ${b.master_job_id?'重新生成定稿图':'生成 1 张定稿图'}</button><p class="field-hint">点击后调用所选图像模型，按平台计费。</p>
  </section>
  <section class="panel sb-master"><div class="sb-canvas-heading"><div><h2>视觉定稿</h2><p>先确认人物与风格，再展开分镜</p></div><span class="sb-ratio-badge">${esc(b.ratio)}</span></div><div id="sb-master-result"></div><div class="sb-master-footer"><button class="button primary" id="sb-confirm">确认定稿，进入分镜</button><button type="button" class="button secondary" data-sb-stage="shots">先编排镜头 →</button></div><p class="field-hint">所有镜头共享确认后的定稿图。重新确认定稿会重置当前分镜关联，旧作品仍保留在作品库。</p></section>
 </div>
 <section id="sb-stage-shots" class="panel sb-shots">
  <div class="sb-shots-heading"><div><h2>编排你的镜头</h2><p id="sb-readiness" class="field-hint"></p></div><div class="sb-actions"><button class="button secondary" data-sb-stage="master">查看 / 修改定稿</button><button class="button primary" id="sb-generate-shots">${icon('spark')} 同时生成 ${b.shots.length} 张分镜</button></div></div>
  <div class="sb-shot-workspace"><aside class="sb-shot-outline"><div class="sb-outline-heading"><strong>镜头顺序</strong><span>${b.shots.length} / 8</span></div><div id="sb-filmstrip"></div><button class="button secondary wide" id="sb-add-shot">${icon('plus')} 添加镜头</button><div class="sb-reference-note">${b.master_asset?`<img src="${esc(b.master_asset.url)}" alt="共同定稿参考"><div><b>共同参考图</b><small>所有镜头保持同一视觉</small></div>`:'<p>先确认定稿，再批量生成。现在也可以先编辑镜头描述。</p>'}</div></aside>
  <div class="sb-shot-grid">${b.shots.map((s,i)=>`<article class="sb-shot" id="sb-shot-${s.id}" ${s.id===v.activeShot?'':'hidden'}><div class="sb-shot-top"><b>镜头 ${String(i+1).padStart(2,'0')}</b><div class="sb-actions"><button type="button" class="text-button" data-sb-move="${s.id}" data-direction="-1" ${i===0?'disabled':''}>前移</button><button type="button" class="text-button" data-sb-move="${s.id}" data-direction="1" ${i===b.shots.length-1?'disabled':''}>后移</button><button type="button" class="text-button" data-sb-remove="${s.id}">移除镜头</button></div></div><div class="sb-shot-detail"><div class="sb-shot-editor"><label>镜头标题<input id="sb-title-${s.id}" data-sb-title="${s.id}" value="${esc(s.title)}" maxlength="80"></label><label>这一镜头的画面<textarea id="sb-prompt-${s.id}" data-sb-prompt="${s.id}" rows="9" maxlength="4000">${esc(s.prompt)}</textarea></label><p class="field-hint">描述一个静态瞬间：景别、姿态、道具位置。人物与穿搭沿用定稿，运镜与对白留给视频生成。</p></div><div id="sb-result-${s.id}" class="sb-shot-result"></div></div></article>`).join('')}</div></div>
  <div class="sb-production-footer"><p>每个镜头生成一张独立图片 · 最多 3 个任务并发 · 可单独重做失败镜头</p><div class="sb-handoff"><label>投喂到视频模型<select id="sb-video-target">${options('video')}</select></label><button type="button" class="button secondary" id="sb-collect">将已完成分镜加入参考图</button><button type="button" class="button primary" data-action="video-workspace">前往视频生成 →</button></div><p class="field-hint">加入素材只更新视频草稿。检查视频提示词与参数后，再手动生成视频。</p></div>
 </section>`;
}
function sbUpdateStage(){
 const v=storyboardView,b=v.board;if(!b)return;
 document.querySelectorAll('[data-sb-stage]').forEach(e=>{e.classList.toggle('active',e.dataset.sbStage===v.stage);e.disabled=v.busy;e.onclick=()=>{v.stage=e.dataset.sbStage;sbUpdateStage()}});
 const master=$('#sb-stage-master'),shots=$('#sb-stage-shots');if(master)master.hidden=v.stage==='shots';if(shots)shots.hidden=v.stage!=='shots';
 if($('#sb-master-summary'))$('#sb-master-summary').textContent=b.master_upload_id?'已确认 · 共同参考已就绪':'生成并确认共同参考';
 const done=b.shots.filter(s=>sbAsset(sbJob(s.job_id))).length;
 if($('#sb-shots-summary'))$('#sb-shots-summary').textContent=`${b.shots.length} 个镜头 · ${done} 张已完成`;
 if($('#sb-readiness'))$('#sb-readiness').textContent=b.busy?'图片正在生成或保存，可切换镜头查看进度。':!b.master_upload_id?'还未确认定稿。可以先编排镜头，再回到视觉定稿完成确认。':!sbCanReference()?'当前图像模型不支持参考图，请在视觉定稿中更换模型。':`定稿已就绪 · ${done} / ${b.shots.length} 张已完成 · 批量生成会调用 ${b.shots.length} 次图像接口`;
 sbUpdateFilmstrip();
}
function sbUpdateFilmstrip(){
 const v=storyboardView,b=v.board,root=$('#sb-filmstrip');if(!root||!b)return;
 root.innerHTML=b.shots.map((s,i)=>{const j=sbJob(s.job_id),a=sbAsset(j);return `<button type="button" class="sb-filmstrip-item ${v.activeShot===s.id?'active':''}" data-sb-select="${s.id}" aria-pressed="${v.activeShot===s.id}"><span class="sb-filmstrip-thumb">${a?`<img src="${esc(a.url)}" alt="">`:String(i+1).padStart(2,'0')}</span><span><b>${esc(s.title||'未命名镜头')}</b><small>${j?esc(statusNames[j.status]||j.status):'待生成'}</small></span></button>`}).join('');
 document.querySelectorAll('[data-sb-select]').forEach(e=>e.onclick=()=>{v.activeShot=e.dataset.sbSelect;for(const s of b.shots){const card=$('#sb-shot-'+s.id);if(card)card.hidden=s.id!==v.activeShot}sbUpdateFilmstrip()});
}
function sbBindLayout(){
 document.querySelectorAll('[data-sb-move]').forEach(e=>e.onclick=()=>{const b=storyboardView.board,i=b.shots.findIndex(s=>s.id===e.dataset.sbMove),n=i+Number(e.dataset.direction);if(n<0||n>=b.shots.length)return;[b.shots[i],b.shots[n]]=[b.shots[n],b.shots[i]];sbDirty();renderStoryboards()});
 $('#sb-video-target').onchange=e=>{state.selected.video=e.target.value;sbUpdateResults()};
 $('#sb-collect').onclick=()=>sbAction(async()=>{
  const p=chosen('video');if(!capabilities(p).reference_images)throw Error('当前视频模型不支持参考图，请选择支持的模型');
  const v=storyboardView,ready=v.board.shots.map(s=>sbJob(s.job_id)).filter(j=>sbAsset(j));
  const selected=ready.filter(j=>!state.drafts.video.assets.references.includes(v.transfers[j.id]?.id));
  if(!selected.length)throw Error('没有新的已完成分镜可以加入');
  if(selected.length+state.drafts.video.assets.references.length>(p.protocol==='weijin_video'?9:8))throw Error('剩余参考图位置不足，请先清理视频草稿，或逐张加入');
  const assets=[];for(const j of selected){const a=v.transfers[j.id]||await api('/api/storyboards/transfer',{id:v.board.id,job_id:j.id});v.transfers[j.id]=a;assets.push(a)}
  assets.forEach(a=>sbAcceptVideoAsset(a,'references'));toast(`已将 ${assets.length} 张分镜按镜头顺序加入视频参考图`);
 });
}
