'use strict';
const libraryPicker={slot:null,items:[],selected:[],cache:{},busy:false,error:'',query:''};
function libraryImages(jobs){return jobs.filter(j=>j.kind==='image'&&j.status==='succeeded'&&!j.work_deleted_at).flatMap(j=>(j.result?.assets||[]).map((a,i)=>({key:j.id+':'+i,job_id:j.id,asset_index:i,url:a.url,width:a.width,height:a.height,title:j.prompt||'未命名图片',model:j.model||'',created_at:j.created_at})).filter(a=>j.result.assets[a.asset_index].type==='image'&&j.result.assets[a.asset_index].local))}
function libraryLimit(slot){if(slot!=='references')return 1;return Math.max(0,(chosen('video')?.protocol==='weijin_video'?9:8)-state.drafts.video.assets.references.length)}
function librarySupported(slot){return !!capabilities(chosen('video'))[slot==='references'?'reference_images':slot]}
function libraryButton(slot,label){return `<button type="button" class="button secondary compact" data-library-slot="${slot}">${icon('grid')} ${label}</button>`}
function videoWorkflow(activeView){return `<nav class="video-workflow" aria-label="视频创作流程"><button type="button" data-action="storyboard-open" class="${activeView==='storyboards'?'selected':''}" aria-current="${activeView==='storyboards'?'page':'false'}"><span class="workflow-icon">${icon('grid')}</span><span><b>定稿图与分镜</b><small>固定视觉 · 编排镜头 · 批量生图</small></span><span class="workflow-index">01</span></button><button type="button" data-action="video-workspace" class="${activeView==='video'?'selected':''}" aria-current="${activeView==='video'?'page':'false'}"><span class="workflow-icon">${icon('video')}</span><span><b>视频生成</b><small>选择素材 · 设置首尾帧 · 生成视频</small></span><span class="workflow-index">02</span></button></nav>`}
async function openLibraryPicker(slot){
 if(libraryPicker.busy)return;
 if(!librarySupported(slot))return toast('当前视频模型不支持此素材模式');
 if(!libraryLimit(slot))return toast('参考图数量已达上限，请先移除一张');
 Object.assign(libraryPicker,{slot,selected:[],items:[],query:'',error:'',busy:true});
 const dlg=$('#library-dialog');dlg.innerHTML=`<div class="dialog-head"><h2 id="library-title">从作品库选图</h2><button type="button" class="icon-button" id="library-close" aria-label="关闭">${icon('close')}</button></div><div class="library-toolbar"><label class="sr-only" for="library-search">搜索描述或模型</label><input id="library-search" placeholder="搜索图片描述或模型"><span id="library-total"></span></div><div id="library-grid" class="library-grid"></div><p id="library-error" class="sb-error" role="alert" hidden></p><div class="dialog-footer"><span id="library-note"></span><button type="button" class="button secondary" id="library-cancel">取消</button><button type="button" class="button primary" id="library-use">使用所选图片</button></div>`;
 $('#library-close').onclick=$('#library-cancel').onclick=()=>{if(!libraryPicker.busy)dlg.close()};
 dlg.oncancel=e=>{if(libraryPicker.busy)e.preventDefault()};
 $('#library-search').oninput=e=>{libraryPicker.query=e.target.value;renderLibraryItems()};
 $('#library-use').onclick=applyLibrarySelection;
 if(!dlg.open)dlg.showModal();renderLibraryItems();
 try{const response=await api('/api/jobs');libraryPicker.items=libraryImages(Array.isArray(response)?response:response.jobs||[])}catch(e){libraryPicker.error=e.message}
 finally{libraryPicker.busy=false;renderLibraryItems()}
}
function renderLibraryItems(){
 const v=libraryPicker,limit=libraryLimit(v.slot),q=v.query.toLowerCase().trim();
 const items=v.items.filter(a=>(a.title+' '+a.model).toLowerCase().includes(q));
 const selected=v.selected;
 $('#library-title').textContent=({references:'从作品库选择参考图',first_frame:'从作品库选择首帧',last_frame:'从作品库选择尾帧'})[v.slot];
 $('#library-total').textContent=`${items.length} 张可用图片`;
 $('#library-grid').innerHTML=v.busy&&!v.items.length?'<p class="library-empty">正在读取作品库…</p>':items.length?items.map(a=>{const n=selected.indexOf(a.key);return `<button type="button" class="library-tile ${n>=0?'selected':''}" data-library-image="${a.key}" aria-pressed="${n>=0}" ${v.busy?'disabled':''}><span class="library-thumb"><img loading="lazy" src="${esc(a.url)}" alt="${esc(a.title.slice(0,80))}"><span class="library-tick">${n>=0?n+1:'+'}</span></span><strong>${esc(a.title.slice(0,90))}</strong><small>${esc(a.model)}${a.width&&a.height?' · '+a.width+' × '+a.height:''}</small></button>`}).join(''):`<p class="library-empty">${v.items.length?'没有匹配的图片，请换个关键词。':'作品库暂无已保存的成功图片。可先生成图片，或在工作台上传本机图片。'}</p>`;
 $('#library-note').textContent=`已选 ${selected.length} / ${limit} 张${v.slot==='references'?' · 按选择顺序加入':' · 将替换当前'+(v.slot==='first_frame'?'首帧':'尾帧')}`;
 $('#library-use').disabled=v.busy||!selected.length;
 $('#library-use').textContent=v.busy?'正在读取…':`使用所选 ${selected.length||''} 张`;
 $('#library-cancel').disabled=$('#library-close').disabled=v.busy;
 $('#library-error').hidden=!v.error;$('#library-error').textContent=v.error;
 document.querySelectorAll('[data-library-image]').forEach(e=>e.onclick=()=>{
  const key=e.dataset.libraryImage,index=v.selected.indexOf(key);
  if(index>=0)v.selected.splice(index,1);else if(v.slot!=='references')v.selected=[key];else if(v.selected.length<libraryLimit(v.slot))v.selected.push(key);else return toast('已达到本次可选数量');
  renderLibraryItems();
 });
}
async function applyLibrarySelection(){
 const v=libraryPicker;if(v.busy||!v.selected.length)return;
 if(!librarySupported(v.slot)||v.selected.length>libraryLimit(v.slot)){v.error='模型能力或剩余数量已变化，请重新选择';renderLibraryItems();return}
 v.busy=true;v.error='';renderLibraryItems();
 try{
  // Resolve all images before changing the draft. Failed imports preserve it.
  const assets=[];
  for(const key of v.selected){const item=v.items.find(a=>a.key===key);const asset=v.cache[key]||await api('/api/library/image',{job_id:item.job_id,asset_index:item.asset_index});v.cache[key]=asset;assets.push(asset)}
  if(!librarySupported(v.slot)||assets.length>libraryLimit(v.slot))throw Error('当前模型或素材数量已变化，请重新选择');
  for(const asset of assets)sbAcceptVideoAsset(asset,v.slot);
  $('#library-dialog').close();renderStudio('video');toast('图片已放入视频草稿，请检查镜头描述后再生成');
 }catch(e){v.error=e.message}finally{v.busy=false;if($('#library-dialog').open)renderLibraryItems()}
}
document.addEventListener('click',e=>{const pick=e.target.closest('[data-library-slot]');if(pick)openLibraryPicker(pick.dataset.librarySlot);if(e.target.closest('[data-action="video-workspace"]')){storyboardView.open=false;renderStudio('video')}});
