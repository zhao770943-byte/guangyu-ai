'use strict';
let connectionOpenVersion=0;
const connectionView={filter:'all',query:''};

function renderSettings(){
  $('#page').innerHTML=heading('模型接入','按文本、音频、图像、视频管理模型连接。',`<button class="button primary" data-action="add-provider">${icon('plus')} 接入模型</button>`)+`
    <section class="panel connections-panel"><div class="connections-toolbar"><div class="connection-filters" aria-label="按用途筛选">${[['all','全部'],['chat','文本'],['audio','音频'],['image','图像'],['video','视频']].map(([k,label])=>`<button type="button" data-connection-filter="${k}" aria-pressed="${connectionView.filter===k}" class="${connectionView.filter===k?'active':''}">${label}<span>${state.providers.filter(p=>k==='all'||p.kind===k).length}</span></button>`).join('')}</div><label class="connection-search">${icon('search')}<input type="search" aria-label="搜索已接入模型" placeholder="搜索名称或模型 ID" value="${esc(connectionView.query)}"></label></div><div id="connection-rows"></div></section>
    <div class="connection-guidance"><span>${icon('lock')} 密钥加密保存在本机</span><p>同一平台可以接入多个模型，不同类型在各自工作台使用。</p><button type="button" class="text-button" data-page="usage">查看模型用量 ${icon('arrow')}</button></div>`;
  const draw=()=>{
    const q=connectionView.query.trim().toLowerCase();
    const rows=state.providers.filter(p=>(connectionView.filter==='all'||p.kind===connectionView.filter)&&[p.name,p.model,p.base_url].join(' ').toLowerCase().includes(q));
    $('#connection-rows').innerHTML=rows.length?`<div class="connection-table-head"><span>模型 / 名称</span><span>接入地址</span><span>用途</span><span>管理</span></div>`+rows.map(p=>`<article class="connection-row"><div class="connection-identity"><div class="connection-kind-icon ${esc(p.kind)}">${icon(p.kind==='chat'?'assistant':p.kind)}</div><div><h3>${esc(p.name)}</h3><p>${esc(p.model)}</p></div></div><div class="connection-address"><span>${esc(p.base_url)}</span><small>${esc(protocolNames[p.protocol])} · ${p.has_key?'密钥已加密':'无密钥'}</small></div><div><span class="connection-kind-label ${providerUsable(p)?esc(p.kind):'invalid'}">${providerUsable(p)?(p.kind==='chat'?'AI 助手':kindNames[p.kind]):'用途需修正'}</span></div><div class="connection-row-actions"><button class="button secondary compact" data-discover-provider="${p.id}" aria-label="获取 ${esc(p.name)} 的可用模型">${icon('refresh')} 获取模型</button><button class="button secondary compact" data-edit="${p.id}" aria-label="编辑 ${esc(p.name)}">编辑</button><button class="icon-button" data-delete="${p.id}" title="移除连接" aria-label="删除 ${esc(p.name)}">${icon('trash')}</button></div></article>`).join(''):`<div class="connections-empty"><div class="connections-empty-symbol">${icon('model')}</div><h2>${state.providers.length?'没有匹配的模型':'接入第一个模型'}</h2><p>${state.providers.length?'试试其他关键词，或切换上方用途。':'先选择模型类型，再连接厂商并获取对应型号。'}</p>${state.providers.length?'':`<button class="button primary" data-action="add-provider">${icon('plus')} 接入模型</button><div class="connection-supported">OpenAI · Claude · Gemini · DeepSeek · 更多兼容平台</div>`}</div>`;
  };
  $('.connection-search input').oninput=e=>{connectionView.query=e.target.value;draw()};
  document.querySelectorAll('[data-connection-filter]').forEach(button=>button.onclick=()=>{connectionView.filter=button.dataset.connectionFilter;renderSettings()});draw();
}

function connectionMappingIssues(protocol,kind,c){
  if(protocol!=='custom')return [];
  const issues=[];
  const path=(key,label,required=false)=>{
    const value=(c[key]||'').trim();
    if(!value){if(required)issues.push({field:key,message:`请填写${label}（以 / 开头的相对路径，按当前平台文档填写）。`});return}
    if(!value.startsWith('/')||value.startsWith('//'))issues.push({field:key,message:`${label}应以一个 / 开头，不要填写完整网址。`});
  };
  path('submit_path','提交路径',true);path('poll_path','轮询路径');
  if(kind==='chat'&&!c.text_path?.trim())issues.push({field:'text_path',message:'请填写文本响应字段路径。'});
  if(kind!=='chat'&&!c.media_path?.trim()&&!(kind==='image'&&c.base64_path?.trim()))issues.push({field:'media_path',message:'请填写媒体 URL 字段路径，用于读取生成结果。'});
  if(c.poll_path?.trim()){
    if(!c.poll_path.includes('{id}'))issues.push({field:'poll_path',message:'轮询路径需包含 {id}，用于查询原任务。'});
    for(const [field,label] of [['id_path','任务 ID 字段'],['status_path','状态字段'],['success_values','成功状态']])if(!c[field]?.trim())issues.push({field,message:`异步查询需填写${label}。`});
  }
  return issues;
}

function connectionAdvancedHTML(p){
  const c=p?.custom||{};
  return `<div class="connection-advanced-intro"><h3>高级参数与协议映射</h3><p>标准接口通常无需调整。自定义接口请按平台文档填写。</p><div id="connection-mapping-guide" class="connection-mapping-guide" hidden></div></div>
    <label>生成请求响应等待上限（秒）<input name="request_timeout_seconds" type="number" min="60" max="1800" step="1" value="${esc(p?.request_timeout_seconds??'')}" placeholder="留空：图像 600、视频 300、其他 150"></label><p class="field-hint">控制提交后的网络等待，可设 60–1800 秒。视频收到任务 ID 后继续后台查询；超时不会自动重复提交。</p>
    <label>附加请求参数（JSON）<textarea name="extra_json" rows="3" spellcheck="false">${esc(JSON.stringify(p?.extra||{},null,2))}</textarea></label>
    <div class="field-grid">${fieldHTML('discovery_path','模型列表路径',c.discovery_path||'',{placeholder:'/models'})}${fieldHTML('auth_header','自定义认证请求头',c.auth_header||'Authorization')}</div>
    ${fieldHTML('auth_prefix','自定义认证前缀',c.auth_prefix??'Bearer ')}<p class="field-hint">认证头与前缀用于自定义 JSON 协议。标准协议使用平台原生鉴权。</p>
    <div id="connection-custom-fields">${fieldHTML('submit_path','提交路径',c.submit_path||'',{placeholder:'必填：平台文档中的提交路径，例如 /generate'})}
    <label>请求模板（JSON）<textarea name="body_template" rows="6" spellcheck="false">${esc(JSON.stringify(c.body||{model:'{{model}}',prompt:'{{prompt}}'},null,2))}</textarea></label>
    <p class="field-hint">可使用 {{model}}、{{prompt}}、{{messages}}、{{first_frame}}、{{last_frame}}、{{reference_images}} 与高级参数变量。提交和轮询路径会追加到 API 基础地址后，不要填写完整网址或重复基础地址中的 /v1。字段路径如 data.0.url 不加斜杠。</p>
    <div class="section-label">模型能力 <small>需在模板中引用对应变量</small></div><div class="capability-grid">${Object.entries(capabilityNames).map(([key,label])=>`<label class="check-label"><input type="checkbox" name="cap_${key}" ${c.capabilities?.[key]?'checked':''}>${label}</label>`).join('')}</div>
    <div class="field-grid">${fieldHTML('text_path','文本响应路径',c.text_path||'',{placeholder:'choices.0.message.content'})}${fieldHTML('media_path','媒体 URL 路径',c.media_path||'',{placeholder:'data.0.url'})}</div>${fieldHTML('base64_path','图片 Base64 路径',c.base64_path||'',{placeholder:'data.0.b64_json'})}
    <div class="field-grid">${fieldHTML('id_path','任务 ID 路径',c.id_path||'',{placeholder:'id'})}${fieldHTML('status_path','状态路径',c.status_path||'',{placeholder:'status'})}</div>${fieldHTML('poll_path','轮询路径',c.poll_path||'',{placeholder:'/tasks/{id}'})}
    <div class="field-grid">${fieldHTML('success_values','成功状态（英文逗号分隔）',(c.success_values||['completed','succeeded','success']).join(','))}${fieldHTML('failure_values','失败状态（英文逗号分隔）',(c.failure_values||['failed','error','cancelled']).join(','))}</div>
    <label>Token 字段映射（JSON）<textarea name="usage_paths" rows="3" spellcheck="false">${esc(JSON.stringify(c.usage_paths||{},null,2))}</textarea></label><p class="field-hint">例如 {"input_tokens":"usage.prompt_tokens","output_tokens":"usage.completion_tokens"}。</p>
    <div class="field-grid">${fieldHTML('response_model_path','返回模型字段',c.response_model_path||'')}${fieldHTML('response_id_path','响应 ID 字段',c.response_id_path||'')}</div></div>`;
}

const modelTypeLabels={chat:'文本',audio:'音频',image:'图像',video:'视频'};
const modelTypeNotes={chat:'对话、答疑与文本创作',audio:'语音合成与音频模型',image:'文字生图与参考图创作',video:'视频生成与镜头创作'};
const audioTaskLabels={speech:'语音合成',transcription:'语音识别',realtime:'实时语音',music:'音乐',conversation:'音频对话'};
function platformsForKind(platforms,kind){return platforms.filter(p=>p.id==='custom'||p.model_types?.includes(kind))}
function connectionProfile(p,kind){return {...p,...(p?.profiles?.[kind]||{}),protocol:p?.profiles?.[kind]?.protocol??p?.protocols?.[kind]}}
const platformGroupLabels={domestic:'国内模型原厂',international:'国际模型原厂',hosted:'开源厂商 · 托管接入',gateway:'聚合与推理平台',local:'本地服务',custom:'自定义平台'};
function platformSupportLabel(p,kind){return p.id==='custom'?'自定义接入':connectionProfile(p,kind).protocol?'已有接口适配':'专用接口待适配'}
async function editProvider(id,kind,{autoDiscover=false}={}){
  closeAssistant();const openVersion=++connectionOpenVersion;
  let platforms;try{platforms=(await api('/api/platforms')).platforms}catch(err){if(openVersion===connectionOpenVersion)toast(err.message);return}
  if(openVersion!==connectionOpenVersion)return;
  const original=state.providers.find(p=>p.id===id), defaultKind=original?.kind||kind||(['image','video','audio'].includes(state.page)?state.page:'');
  const dialog=$('#provider-dialog');if(dialog.open)dialog.close();
  dialog.innerHTML=`<form id="provider-form" novalidate><div class="dialog-head"><div><h2 id="provider-title">${original?'编辑模型':'接入模型'}</h2><p>先选模型类型，再连接厂商，最后选择对应型号。</p></div><button type="button" class="icon-button" data-action="close-provider" aria-label="关闭设置">${icon('close')}</button></div>
  <nav class="connection-progress" aria-label="模型接入步骤">${['选择类型','连接厂商','选择模型'].map((label,i)=>`${i?'<i></i>':''}<button type="button" data-wizard-step="${i}"><span>${i+1}</span>${label}</button>`).join('')}</nav>
  <input type="hidden" name="id" value="${original?.id||''}"><input type="hidden" name="model" value="${esc(original?.model||'')}"><input type="hidden" name="kind" value="${defaultKind}">
  <div class="connection-body"><section id="connection-type-pane" class="connection-type-pane"><h3>你要接入哪类模型？</h3><p>厂商与型号会按所选类型筛选。</p><div class="connection-type-grid">${Object.entries(modelTypeLabels).map(([k,label])=>`<button type="button" class="connection-type-card" data-model-type="${k}" aria-pressed="false">${icon(k==='chat'?'assistant':k)}<strong>${label}模型</strong><span>${modelTypeNotes[k]}</span>${icon('check','type-check')}</button>`).join('')}</div></section>
  <section id="connection-platform-pane" class="connection-platform-pane" hidden><div class="connection-scope"><span id="connection-scope-label"></span><button type="button" class="text-button" id="connection-change-type">更改类型</button></div>
  <div class="connection-vendor-column"><label><span class="connection-label-row">模型厂商 <span id="connection-platform-count"></span></span><select name="platform" aria-label="选择模型厂商"></select></label><label class="connection-vendor-search">${icon('search')}<input type="search" id="connection-vendor-search" placeholder="搜索厂商或模型系列，如 GLM、香蕉、Seedance" aria-label="搜索厂商或模型系列"></label><div id="connection-vendor-grid" class="connection-vendor-grid" aria-label="当前类型的模型厂商"></div></div><div class="connection-credentials-column"><div id="connection-family-info" class="connection-family-info"></div>
  <div id="connection-platform-support" class="connection-platform-support" aria-live="polite"></div>
  <div class="connection-platform-access" id="connection-platform-access" hidden><span id="connection-platform-access-note">还没有 API Key？</span><a id="connection-api-key-link" href="#" target="_blank" rel="noopener noreferrer">获取 API Key ${icon('arrow')}</a></div>
  <label>API Key <span class="connection-optional" id="connection-key-note"></span><div class="connection-secret"><input name="api_key" type="password" autocomplete="new-password" placeholder="粘贴当前厂商的 API Key"><button type="button" id="connection-key-toggle" aria-label="显示密钥">显示</button></div></label>
  <label><span class="connection-label-row">API 基础地址 <span>由厂商自动填写，可修改</span></span><input name="base_url" type="url" value="${esc(original?.base_url||'')}" placeholder="https://api.example.com/v1" spellcheck="false"></label><p class="connection-platform-hint" id="connection-platform-hint"></p><p class="connection-platform-hint" id="connection-directory-preview" aria-live="polite"></p>
  <details class="connection-network-options"><summary>连接选项</summary><label>模型目录协议<select name="discovery_protocol"><option value="openai_chat">OpenAI 兼容</option><option value="anthropic">Anthropic</option><option value="gemini">Gemini</option><option value="custom">自定义 JSON</option><option value="comfy_h3">本地 ComfyUI H3</option></select></label><label class="check-label"><input name="allow_local" type="checkbox" ${original?.allow_local?'checked':''}>允许本机 HTTP（仅回环地址）</label><button type="button" class="text-button" id="connection-network-advanced">自定义认证与列表路径 ${icon('arrow')}</button></details>
  <button type="button" class="text-button connection-official-button" id="connection-official-first" hidden>选择官方公开型号（无需手填 ID） ${icon('arrow')}</button></div></section>
  <section id="connection-model-pane" class="connection-model-pane" hidden><div class="connection-model-browser"><div class="connection-browser-head"><div><h3 id="connection-model-heading">选择模型</h3><span id="connection-result-count"></span></div><button type="button" id="connection-refresh" class="button secondary connection-fetch-button">${icon('refresh')} 一键获取模型</button></div>
  <label class="connection-model-search">${icon('search')}<input type="search" id="connection-model-search" aria-label="搜索可用模型" placeholder="搜索所选类型的型号"></label><p class="connection-directory-note" id="connection-directory-note"></p>
  <div id="connection-model-list" class="connection-model-list" aria-label="可用模型"></div><label class="check-label connection-unknown-toggle" id="connection-unknown-label" hidden><input type="checkbox" id="connection-show-unknown">同时显示未识别类型的型号</label><button type="button" class="text-button connection-official-button" id="connection-official-models" hidden>查看官方型号（未验证权限）</button></div>
  <aside class="connection-selection"><div class="connection-selection-title">连接预览</div><div id="connection-selected-summary"></div><div id="connection-selected-fields" hidden><label>连接名称<input name="name" maxlength="60" value="${esc(original?.name||'')}" placeholder="自动使用模型名称"></label>
  <div class="connection-fixed-type"><span>模型类型</span><strong id="connection-fixed-type-label"></strong><button type="button" class="text-button" id="connection-change-selected-type">更改</button></div><p id="connection-purpose-note" class="field-hint"></p><label class="check-label" id="connection-unknown-confirm" hidden><input type="checkbox" id="connection-confirm-kind">我已确认该型号支持所选类型</label>
  <details class="connection-protocol-options"><summary>协议与请求地址</summary><label>接口协议<select name="protocol"></select></label><code id="connection-request-url"></code></details></div>
  <div id="connection-mapping-status" class="connection-mapping-status" role="status" hidden></div><button type="button" class="connection-advanced-button" id="connection-open-advanced">${icon('sliders')} 高级参数与映射 ${icon('arrow')}</button><p class="connection-small-note">读取目录和保存连接不会提交生成任务。</p></aside></section>
  <section id="connection-advanced-pane" class="connection-advanced-pane" hidden>${connectionAdvancedHTML(original)}</section></div>
  <div class="connection-error" id="connection-error" role="alert" hidden></div><div class="dialog-footer"><div class="connection-footer-left"><button type="button" id="connection-back" class="button secondary" hidden>上一步</button></div><span id="connection-footer-hint"></span><button type="submit" id="connection-primary" class="button primary">下一步</button></div></form>`;
  const wizard=setupConnectionWizard($('#provider-form'),original,platforms,defaultKind);dialog.showModal();if(autoDiscover)wizard.discover();
}
function setupConnectionWizard(form,original,platforms,defaultKind){
  const dialog=$('#provider-dialog'),f=name=>form.elements.namedItem(name),el=id=>form.querySelector('#'+id),current=()=>form.isConnected&&dialog.open&&$('#provider-form')===form;
  const canonical=value=>value.trim().replace(/\/+$/,'');
  const initialKinds=original?.model_constraints?.kinds?.length?original.model_constraints.kinds:[original?.kind];
  let step=original?2:0,advanced=false,advancedFrom=0,revision=0,busy=false,saving=false,models=[],loaded=false,catalogMode=false;
  let model=original?{id:original.model,name:original.model,model_kinds:initialKinds,model_constraints:original.model_constraints,protocol:original.protocol}:null,purposeConfirmed=!!original,automaticName='';
  const platform=()=>platforms.find(p=>p.id===f('platform').value);
  const profile=()=>connectionProfile(platform(),f('kind').value);
  const kindsOf=m=>m?.model_kinds?.length?m.model_kinds:m?.model_constraints?.kinds?.length?m.model_constraints.kinds:m?.supported_kinds||[];
  const allowed=m=>!kindsOf(m).length||kindsOf(m).includes(f('kind').value);
  const unavailable=m=>f('kind').value==='audio'&&['transcription','realtime','conversation'].includes(m?.audio_task);
  const officialModels=()=>platform()?.official_models?.filter(m=>kindsOf(m).includes(f('kind').value))||[];
  const discoveryProtocol=p=>['anthropic','gemini','comfy_h3','custom'].includes(p)?p:'openai_chat';
  function mappingIssues(){return connectionMappingIssues(f('protocol').value,f('kind').value,Object.fromEntries(['submit_path','poll_path','text_path','media_path','base64_path','id_path','status_path','success_values'].map(k=>[k,f(k).value])))}
  function requireMapping(){const issues=mappingIssues();if(!issues.length)return true;advanced=true;advancedFrom=2;update();error('模型已选中，但生成接口尚未配置完整。'+issues[0].message);f(issues[0].field).focus();return false}
  function error(message=''){el('connection-error').hidden=!message;el('connection-error').textContent=message}
  function endpoint(){const base=canonical(f('base_url').value),selected=f('model').value;el('connection-directory-preview').textContent=base?'模型目录请求：GET '+base+'/'+(f('discovery_protocol').value==='comfy_h3'?'/object_info':f('discovery_path').value||'/models').replace(/^\//,''):'填写 API 基础地址后，将自动请求模型目录。';const suffix={comfy_h3:'/prompt',openai_chat:'/chat/completions',openai_responses:'/responses',ark_image:'/images/generations',ark_video:'/contents/generations/tasks',openai_image:'/images/generations',minimax_image:'/image_generation',openai_video:'/videos',weijin_video:'/videos',openai_speech:'/audio/speech',minimax_speech:'/t2a_v2',anthropic:'/messages',gemini:'/models/'+encodeURIComponent(selected.replace(/^models\//,''))+':generateContent',custom:f('submit_path').value}[f('protocol').value];el('connection-request-url').textContent=base&&suffix?base+'/'+suffix.replace(/^\//,''):'按厂商文档配置提交路径';el('connection-custom-fields').hidden=f('protocol').value!=='custom'&&f('discovery_protocol').value!=='custom'}
  function protocols(value){f('protocol').innerHTML=(protocolOptions[f('kind').value]||[]).map(p=>`<option value="${p}" ${p===value?'selected':''}>${protocolNames[p]}</option>`).join('');endpoint()}
  function platformOptions(preferred){
    const kind=f('kind').value,available=platformsForKind(platforms,kind);
    const groups=Object.entries(platformGroupLabels).map(([group,label])=>[label,p=>(p.category||(p.id==='custom'?'custom':'international'))===group]);
    f('platform').innerHTML=groups.map(([label,match])=>{const items=available.filter(match);return items.length?`<optgroup label="${label}">${items.map(p=>`<option value="${esc(p.id)}">${esc(p.name)}</option>`).join('')}</optgroup>`:''}).join('');
    if(available.some(p=>p.id===preferred))f('platform').value=preferred;
    else f('platform').value=available.find(p=>p.id!=='custom'&&p.protocols?.[kind])?.id||available[0]?.id||'';
    el('connection-platform-count').textContent=`${available.filter(p=>p.id!=='custom').length} 个可选入口`;
  }
  function drawVendors(){
    const kind=f('kind').value,q=el('connection-vendor-search').value.trim().toLowerCase();
    const available=platformsForKind(platforms,kind).filter(p=>[p.name,p.id,p.families?.[kind]||''].join(' ').toLowerCase().includes(q));
    el('connection-vendor-grid').innerHTML=Object.entries(platformGroupLabels).map(([group,label])=>{
      const items=available.filter(p=>(p.category||(p.id==='custom'?'custom':'international'))===group);
      return items.length?`<section class="connection-vendor-group"><h4>${label}<span>${items.length}</span></h4><div>${items.map(p=>`<button type="button" class="connection-vendor-card ${p.id===f('platform').value?'selected':''}" data-vendor="${esc(p.id)}" aria-pressed="${p.id===f('platform').value}"><strong>${esc(p.name)}</strong><small>${esc(p.families?.[kind]||'按账户目录选择')}</small><em>${esc(platformSupportLabel(p,kind))}</em></button>`).join('')}</div></section>`:'';
    }).join('')||'<p class="connection-vendor-empty">此类型没有匹配厂商，试试名称或模型系列。</p>';
    form.querySelectorAll('[data-vendor]').forEach(b=>{b.disabled=busy||saving;b.onclick=()=>{if(busy||saving)return;f('platform').value=b.dataset.vendor;resetPlatform()}});
  }
  function platformNote(){const selected=platform(),link=el('connection-api-key-link');el('connection-platform-access').hidden=!selected?.api_key_url;link.href=selected?.api_key_url||'#';link.innerHTML=esc(selected?.api_key_label||'获取 API Key')+' '+icon('arrow');el('connection-platform-access-note').textContent=selected?.id==='comfy_h3'?'本机服务':selected?.allow_local?'尚未安装本机服务？':'还没有 API Key？';el('connection-key-note').textContent=original?.has_key&&canonical(original.base_url)===canonical(f('base_url').value)?'已保存，可留空复用':selected?.allow_local?'本机无鉴权可留空':'';el('connection-platform-hint').textContent=profile()?.note||'填写服务商提供的 API 基础地址。';el('connection-scope-label').textContent=modelTypeLabels[f('kind').value]+'模型';el('connection-official-first').hidden=!officialModels().length;el('connection-official-models').hidden=!officialModels().length||catalogMode}
  function update(){
    el('connection-type-pane').hidden=step!==0||advanced;el('connection-platform-pane').hidden=step!==1||advanced;el('connection-model-pane').hidden=step!==2||advanced;el('connection-advanced-pane').hidden=!advanced;
    dialog.classList.toggle('choosing-model',step===2&&!advanced);dialog.classList.toggle('editing-mapping',advanced);dialog.classList.toggle('fetching-models',step===1&&!advanced);
    form.querySelectorAll('[data-wizard-step]').forEach(b=>{const n=Number(b.dataset.wizardStep);b.setAttribute('aria-current',n===step?'step':'false');b.disabled=saving||busy||(n>0&&!f('kind').value)||(n===2&&!loaded&&!model)});
    form.querySelectorAll('input,select,textarea').forEach(control=>control.disabled=saving);form.querySelectorAll('[name=model_choice]').forEach(control=>control.disabled=saving||unavailable(models.find(m=>m.id===control.value)));form.querySelectorAll('[data-model-type]').forEach(b=>{b.setAttribute('aria-pressed',b.dataset.modelType===f('kind').value);b.disabled=saving});
    const validModel=model?.id&&purposeConfirmed&&allowed(model)&&!unavailable(model);
    const issues=mappingIssues(),needsMapping=validModel&&issues.length>0;
    const mappingStatus=el('connection-mapping-status');mappingStatus.hidden=!needsMapping;mappingStatus.textContent=needsMapping?'型号已获取，生成接口待配置。模型目录不会提供提交路径、查询方式和结果字段。':'';
    const guide=el('connection-mapping-guide');guide.hidden=f('protocol').value!=='custom';guide.innerHTML='<strong>按当前平台的视频或生成接口文档配置</strong><p>同步接口需提交路径、请求模板、结果字段；异步接口还需任务 ID、轮询路径、状态字段。不能仅凭 Seedance 等型号名称确定路径。</p>'+(issues.length?'<ul>'+issues.map(x=>'<li>'+esc(x.message)+'</li>').join('')+'</ul>':'<p>必填项已填写，具体参数和字段仍需与平台文档核对。</p>');
    el('connection-primary').disabled=busy||saving||(!advanced&&(step===0?!f('kind').value:step===2?!validModel:false));
    el('connection-primary').innerHTML=saving?'<span class="spinner"></span> 保存中':busy?'<span class="spinner"></span> 正在获取模型…':advanced?'完成配置':step===0?'下一步：选择厂商 '+icon('arrow'):step===1?icon('refresh')+' 一键获取模型':needsMapping?'配置'+modelTypeLabels[f('kind').value]+'接口':original?'保存修改':'接入所选模型';
    el('connection-back').hidden=step===0&&!advanced;el('connection-back').textContent=advanced?'返回':'上一步';el('connection-back').disabled=saving||busy;
    el('connection-footer-hint').textContent=advanced?'按厂商文档配置':step===0?'选择模型的用途':step===1?'自动读取，无需填写模型 ID':needsMapping?'还需配置生成接口':validModel?'将接入'+modelTypeLabels[f('kind').value]+'模型':'请选择匹配的型号';
    el('connection-refresh').disabled=busy||saving;el('connection-refresh').innerHTML=busy?'<span class="spinner"></span> 获取中':icon('refresh')+' 一键获取模型';
    el('connection-model-heading').textContent='选择'+modelTypeLabels[f('kind').value]+'模型';el('connection-selected-fields').hidden=!model?.id;
    el('connection-selected-summary').innerHTML=model?.id?`<div class="connection-selected-icon">${icon(f('kind').value==='chat'?'assistant':f('kind').value)}</div><h3>${esc(model.id)}</h3><p>${esc(platform()?.name||'自定义厂商')}${model.source==='official_catalog'?' · 官方型号':''}</p>`:`<div class="connection-selection-empty">${icon('model')}<h3>选择一个${modelTypeLabels[f('kind').value]}型号</h3><p>只展示与所选类型匹配的模型。</p></div>`;
    el('connection-fixed-type-label').textContent=modelTypeLabels[f('kind').value];el('connection-unknown-confirm').hidden=!model||!!kindsOf(model).length;el('connection-confirm-kind').checked=purposeConfirmed;
    el('connection-purpose-note').classList.toggle('purpose-mismatch',!!model&&!allowed(model));el('connection-purpose-note').textContent=!model?'':!allowed(model)?'当前连接与所选类型不匹配，请更改类型或选择正确型号。':unavailable(model)?'此音频子类型暂未适配，不能通过语音合成接口调用。':!kindsOf(model).length?'目录未标注类型，确认厂商文档后方可接入。':f('protocol').value==='custom'?(mappingIssues().length?'此厂商的专用接口尚待适配；仅列出型号不代表可直接生成。':'已自动填写该型号的提交路径、查询方式和结果字段。'):'已匹配对应接口，模型类型不会被自动改成其他用途。';
    endpoint();platformNote();drawVendors();
    el('connection-family-info').innerHTML=`<strong>${esc(platform()?.name||'自定义平台')}</strong><span>${esc(profile()?.family||platform()?.families?.[f('kind').value]||'读取当前账户的模型目录')}</span>`;
    const p=platform(),kind=f('kind').value,support=el('connection-platform-support');
    support.innerHTML=p?`<span class="connection-adapter-status ${profile().protocol?'ready':'pending'}">${esc(platformSupportLabel(p,kind))}</span><span>${(p.model_types||[]).map(k=>`<span class="connection-output-type ${k===kind?'active':''}">${modelTypeLabels[k]}</span>`).join('')}</span>${p.docs_url?`<a href="${esc(p.docs_url)}" target="_blank" rel="noopener noreferrer">接口文档 ${icon('arrow')}</a>`:''}`:'';
  }
  function drawModels(){
    const kind=f('kind').value,query=el('connection-model-search').value.trim().toLowerCase(),unknown=models.filter(m=>!kindsOf(m).length),matching=models.filter(m=>kindsOf(m).includes(kind));
    const pool=loaded?[...matching,...(el('connection-show-unknown').checked?unknown:[])]:model&&allowed(model)?[model]:[];
    const items=pool.filter(m=>(m.id+' '+m.name).toLowerCase().includes(query));el('connection-unknown-label').hidden=!unknown.length;el('connection-result-count').textContent=loaded?`${matching.length} / ${models.length}`:'当前连接';
    el('connection-directory-note').textContent=catalogMode?'官方公开型号，尚未验证当前密钥的权限、余额或服务可用性。':loaded?`已筛选${modelTypeLabels[kind]}模型，其他类型不显示。`:'已保存的连接；可一键刷新目录。';
    el('connection-model-list').innerHTML=items.length?items.map(m=>`<label class="connection-model-option ${model?.id===m.id?'selected':''} ${unavailable(m)?'unavailable':''}"><input type="radio" name="model_choice" value="${esc(m.id)}" ${model?.id===m.id?'checked':''} ${unavailable(m)?'disabled':''}><span class="connection-option-copy"><strong>${esc(m.name||m.id)}</strong>${m.name&&m.name!==m.id?`<small>${esc(m.id)}</small>`:''}<span class="connection-option-tags"><em>${unavailable(m)?esc(audioTaskLabels[m.audio_task])+' · 待适配':m.audio_task?esc(audioTaskLabels[m.audio_task]):kindsOf(m).length?modelTypeLabels[kind]:'类型未识别'}</em></span></span>${icon('check','connection-option-check')}</label>`).join(''):`<div class="connection-list-empty">${icon(kind==='chat'?'assistant':kind)}<h3>${query?'没有匹配的型号':'未返回'+modelTypeLabels[kind]+'模型'}</h3><p>${query?'换一个搜索关键词。':'可切换厂商、重新获取，或检查密钥权限。不会用其他类型的模型替代。'}</p></div>`;
    form.querySelectorAll('[name=model_choice]').forEach(radio=>radio.onchange=()=>selectModel(items.find(m=>m.id===radio.value)));
  }
  function applyModelMapping(value){
    // Use only our local preset, never a mapping/URL returned by a remote catalog.
    const known=platform()?.official_models?.find(m=>m.id===value.id.replace(/^models\//,''));
    if(original?.model===value.id&&original?.platform===f('platform').value&&canonical(original.base_url)===canonical(f('base_url').value))return;
    const mapping=known?.custom||{};
    for(const key of ['submit_path','poll_path','text_path','media_path','base64_path','id_path','status_path','response_model_path','response_id_path'])f(key).value=mapping[key]||'';
    if(known?.custom){f('auth_header').value=mapping.auth_header||'Authorization';f('auth_prefix').value=mapping.auth_prefix??'Bearer ';}
    f('body_template').value=JSON.stringify(mapping.body||{model:'{{model}}',prompt:'{{prompt}}'},null,2);f('usage_paths').value=JSON.stringify(mapping.usage_paths||{});
    for(const key of ['success_values','failure_values'])f(key).value=(mapping[key]||[]).join(',');
    for(const key of Object.keys(capabilityNames))f('cap_'+key).checked=!!mapping.capabilities?.[key];
    f('extra_json').value='{}';
  }
  function selectModel(value){if(!value||!allowed(value)||unavailable(value))return;model=value;f('model').value=value.id;applyModelMapping(value);purposeConfirmed=kindsOf(value).includes(f('kind').value);protocols((protocolOptions[f('kind').value]||[]).includes(value.protocol)?value.protocol:'custom');if(!f('name').value||f('name').value===automaticName){automaticName=(value.name||value.id).slice(0,60);f('name').value=automaticName}error();update();drawModels()}
  function invalidate({clearKey=false}={}){revision++;busy=false;loaded=false;catalogMode=false;models=[];model=null;purposeConfirmed=false;f('model').value='';el('connection-model-search').value='';el('connection-show-unknown').checked=false;if(clearKey)f('api_key').value='';error();update();drawModels()}
  function showStep(n){step=n;advanced=false;error();update();if(n===2)drawModels()}
  function resetPlatform(){f('base_url').value=profile()?.base_url||'';f('allow_local').checked=!!platform()?.allow_local;f('discovery_path').value='';f('auth_header').value='Authorization';f('auth_prefix').value='Bearer ';for(const key of ['submit_path','poll_path','text_path','media_path','base64_path','id_path','status_path','response_model_path','response_id_path'])f(key).value='';f('body_template').value='{}';f('extra_json').value='{}';f('usage_paths').value='{}';for(const key of Object.keys(capabilityNames))f('cap_'+key).checked=false;f('discovery_protocol').value=discoveryProtocol(platform()?.discovery_protocol);protocols(profile()?.protocol||'custom');invalidate({clearKey:true})}
  function validConnection(){if(!f('kind').value){showStep(0);return false}const base=f('base_url');if(!base.value.trim()||!base.checkValidity()){showStep(1);error('请填写有效的 API 基础地址。');base.focus();return false}return true}
  async function discover(){if(busy||saving||!validConnection())return;const requestRevision=++revision;busy=true;error();update();const payload={id:f('id').value,platform:f('platform').value,kind:f('kind').value,protocol:f('discovery_protocol').value,base_url:f('base_url').value,api_key:f('api_key').value,allow_local:f('allow_local').checked,custom:Object.fromEntries(['discovery_path','auth_header','auth_prefix'].map(k=>[k,f(k).value]))};try{const result=await api('/api/models/discover',payload);if(requestRevision!==revision||!current())return;models=result.models||[];loaded=true;catalogMode=false;step=2;advanced=false;const refreshed=models.find(m=>m.id===model?.id);if(refreshed)model={...refreshed};else if(model?.id!==original?.model){model=null;purposeConfirmed=false;f('model').value=''}if(model)purposeConfirmed=kindsOf(model).includes(f('kind').value);if(result.truncated)error('目录达到读取上限，当前是部分结果。');drawModels()}catch(err){if(requestRevision===revision&&current())error(err.message)}finally{if(requestRevision===revision&&current()){busy=false;update()}}}
  function showOfficial(){if(!validConnection())return;revision++;busy=false;models=officialModels().map(m=>({...m}));loaded=true;catalogMode=true;model=null;purposeConfirmed=false;f('model').value='';el('connection-model-search').value='';step=2;advanced=false;error();update();drawModels()}
  async function save(){
    if(saving||busy||!model?.id||!purposeConfirmed||!allowed(model)||unavailable(model)||!validConnection())return;
    if(!requireMapping())return;
    const name=f('name').value.trim();if(!name||name.length>60){error('请填写 1–60 字的连接名称。');return}
    const payload={};['id','platform','kind','protocol','base_url','api_key'].forEach(k=>payload[k]=f(k).value);payload.name=name;payload.model=model.id;payload.video_model_metadata=model.video_model_metadata||original?.video_model_metadata||{};payload.allow_local=f('allow_local').checked;payload.request_timeout_seconds=f('request_timeout_seconds').value===''?null:Number(f('request_timeout_seconds').value);
    try{payload.extra=JSON.parse(f('extra_json').value||'{}');payload.custom={body:JSON.parse(f('body_template').value||'{}'),usage_paths:JSON.parse(f('usage_paths').value||'{}')}}catch{advanced=true;advancedFrom=2;update();error('高级参数的 JSON 格式不正确。');return}
    ['submit_path','discovery_path','auth_header','auth_prefix','text_path','media_path','base64_path','id_path','status_path','poll_path','response_model_path','response_id_path'].forEach(k=>payload.custom[k]=f(k).value);['success_values','failure_values'].forEach(k=>payload.custom[k]=f(k).value.split(',').map(s=>s.trim().toLowerCase()).filter(Boolean));payload.custom.discovery_protocol=f('discovery_protocol').value;payload.custom.capabilities=Object.fromEntries(Object.keys(capabilityNames).map(k=>[k,f('cap_'+k).checked]));
    saving=true;error();update();try{const saved=await api('/api/providers/save',payload);state.providers=state.providers.filter(p=>p.id!==saved.id);state.providers.unshift(saved);state.selected[saved.kind]=saved.id;state.usage=null;if(current()){dialog.close();render();toast(modelTypeLabels[saved.kind]+'模型已接入')}else renderNavigation()}catch(err){if(current())error(err.message)}finally{saving=false;if(current())update()}
  }
  platformOptions(original?.platform);if(original&&!platformsForKind(platforms,defaultKind).some(p=>p.id===original.platform))f('platform').value='custom';if(!original)f('base_url').value=profile()?.base_url||'';f('discovery_protocol').value=original?.custom?.discovery_protocol||discoveryProtocol(original?.protocol||platform()?.discovery_protocol);protocols(original?.protocol||platform()?.protocols?.[defaultKind]||'custom');update();drawModels();
  form.querySelectorAll('[data-model-type]').forEach(b=>b.onclick=()=>{
    if(busy||saving)return;
    if(b.dataset.modelType!==f('kind').value){const first=!f('kind').value,previous=f('platform').value;f('kind').value=b.dataset.modelType;platformOptions(first?(b.dataset.modelType==='video'?'ark':b.dataset.modelType==='audio'?'minimax':'openai'):previous);if(first||f('platform').value!==previous)resetPlatform();else{const nextBase=profile()?.base_url||'',changed=canonical(nextBase)!==canonical(f('base_url').value);f('base_url').value=nextBase;protocols(profile()?.protocol||'custom');invalidate({clearKey:changed})}}
    showStep(1);el('connection-vendor-search').focus();
  });
  form.querySelectorAll('[data-wizard-step]').forEach(b=>b.onclick=()=>showStep(Number(b.dataset.wizardStep)));[el('connection-change-type'),el('connection-change-selected-type')].forEach(b=>b.onclick=()=>showStep(0));
  el('connection-vendor-search').oninput=drawVendors;f('platform').onchange=resetPlatform;f('base_url').oninput=()=>invalidate({clearKey:true});f('api_key').oninput=()=>invalidate();f('allow_local').onchange=()=>invalidate();f('discovery_protocol').onchange=()=>invalidate();['discovery_path','auth_header','auth_prefix'].forEach(k=>f(k).oninput=()=>{revision++;busy=false;loaded=false;models=[];update()});
  f('protocol').onchange=()=>{update();if(f('protocol').value==='custom'){advanced=true;advancedFrom=2;update()}};['submit_path','poll_path','text_path','media_path','base64_path','id_path','status_path','success_values'].forEach(k=>f(k).oninput=()=>{error();update()});el('connection-model-search').oninput=drawModels;el('connection-show-unknown').onchange=drawModels;el('connection-confirm-kind').onchange=e=>{purposeConfirmed=e.target.checked;update()};
  el('connection-key-toggle').onclick=()=>{const visible=f('api_key').type==='password';f('api_key').type=visible?'text':'password';el('connection-key-toggle').textContent=visible?'隐藏':'显示';el('connection-key-toggle').setAttribute('aria-label',visible?'隐藏密钥':'显示密钥')};
  el('connection-back').onclick=()=>{if(advanced){advanced=false;step=advancedFrom;update()}else showStep(Math.max(0,step-1))};el('connection-refresh').onclick=discover;[el('connection-official-first'),el('connection-official-models')].forEach(b=>b.onclick=showOfficial);[el('connection-open-advanced'),el('connection-network-advanced')].forEach(b=>b.onclick=()=>{advancedFrom=step;advanced=true;update()});
  form.onsubmit=e=>{e.preventDefault();if(advanced){if(advancedFrom===2&&model&&!requireMapping())return;advanced=false;step=advancedFrom;error();update()}else if(step===0)showStep(1);else if(step===1)discover();else save()};dialog.addEventListener('close',()=>{revision++;f('api_key').value='';models=[]},{once:true});return {discover};
}
function closeProvider(){const input=$('#provider-form [name=api_key]');if(input)input.value='';$('#provider-dialog').close()}
