'use strict';
let connectionOpenVersion=0;
const connectionView={filter:'all',query:''};

function renderSettings(){
  $('#page').innerHTML=heading('模型接入','管理图像、视频与 AI 助手使用的模型。',`<button class="button primary" data-action="add-provider">${icon('plus')} 接入模型</button>`)+`
    <section class="panel connections-panel"><div class="connections-toolbar"><div class="connection-filters" aria-label="按用途筛选">${[['all','全部'],['image','图像'],['video','视频'],['chat','AI 助手']].map(([k,label])=>`<button type="button" data-connection-filter="${k}" aria-pressed="${connectionView.filter===k}" class="${connectionView.filter===k?'active':''}">${label}<span>${state.providers.filter(p=>k==='all'||p.kind===k).length}</span></button>`).join('')}</div><label class="connection-search">${icon('search')}<input type="search" aria-label="搜索已接入模型" placeholder="搜索名称或模型 ID" value="${esc(connectionView.query)}"></label></div><div id="connection-rows"></div></section>
    <div class="connection-guidance"><span>${icon('lock')} 密钥加密保存在本机</span><p>同一平台可以接入多个模型，图像、视频与 AI 助手分别选择使用。</p><button type="button" class="text-button" data-page="usage">查看模型用量 ${icon('arrow')}</button></div>`;
  const draw=()=>{
    const q=connectionView.query.trim().toLowerCase();
    const rows=state.providers.filter(p=>(connectionView.filter==='all'||p.kind===connectionView.filter)&&[p.name,p.model,p.base_url].join(' ').toLowerCase().includes(q));
    $('#connection-rows').innerHTML=rows.length?`<div class="connection-table-head"><span>模型 / 名称</span><span>接入地址</span><span>用途</span><span>管理</span></div>`+rows.map(p=>`<article class="connection-row"><div class="connection-identity"><div class="connection-kind-icon ${esc(p.kind)}">${icon(p.kind==='chat'?'assistant':p.kind)}</div><div><h3>${esc(p.name)}</h3><p>${esc(p.model)}</p></div></div><div class="connection-address"><span>${esc(p.base_url)}</span><small>${esc(protocolNames[p.protocol])} · ${p.has_key?'密钥已加密':'无密钥'}</small></div><div><span class="connection-kind-label ${esc(p.kind)}">${p.kind==='chat'?'AI 助手':kindNames[p.kind]}</span></div><div class="connection-row-actions"><button class="icon-button" data-check="${p.id}" title="读取模型目录" aria-label="检查 ${esc(p.name)}">${icon('refresh')}</button><button class="button secondary compact" data-edit="${p.id}" aria-label="编辑 ${esc(p.name)}">编辑</button><button class="icon-button" data-delete="${p.id}" title="移除连接" aria-label="删除 ${esc(p.name)}">${icon('trash')}</button></div></article>`).join(''):`<div class="connections-empty"><div class="connections-empty-symbol">${icon('model')}</div><h2>${state.providers.length?'没有匹配的模型':'接入第一个模型'}</h2><p>${state.providers.length?'试试其他关键词，或切换上方用途。':'选择平台，读取模型列表，即可开始创作。'}</p>${state.providers.length?'':`<button class="button primary" data-action="add-provider">${icon('plus')} 接入模型</button><div class="connection-supported">OpenAI · Claude · Gemini · DeepSeek · 更多兼容平台</div>`}</div>`;
  };
  $('.connection-search input').oninput=e=>{connectionView.query=e.target.value;draw()};
  document.querySelectorAll('[data-connection-filter]').forEach(button=>button.onclick=()=>{connectionView.filter=button.dataset.connectionFilter;renderSettings()});draw();
}

function connectionAdvancedHTML(p){
  const c=p?.custom||{};
  return `<div class="connection-advanced-intro"><h3>高级参数与协议映射</h3><p>标准接口通常无需调整。自定义接口请按平台文档填写。</p></div>
    <label>附加请求参数（JSON）<textarea name="extra_json" rows="3" spellcheck="false">${esc(JSON.stringify(p?.extra||{},null,2))}</textarea></label>
    <div class="field-grid">${fieldHTML('discovery_path','模型列表路径',c.discovery_path||'',{placeholder:'/models'})}${fieldHTML('auth_header','自定义认证请求头',c.auth_header||'Authorization')}</div>
    ${fieldHTML('auth_prefix','自定义认证前缀',c.auth_prefix??'Bearer ')}<p class="field-hint">认证头与前缀用于自定义 JSON 协议。标准协议使用平台原生鉴权。</p>
    <div id="connection-custom-fields">${fieldHTML('submit_path','提交路径',c.submit_path||'',{placeholder:'/generate'})}
    <label>请求模板（JSON）<textarea name="body_template" rows="6" spellcheck="false">${esc(JSON.stringify(c.body||{model:'{{model}}',prompt:'{{prompt}}'},null,2))}</textarea></label>
    <p class="field-hint">可使用 {{model}}、{{prompt}}、{{messages}}、{{first_frame}}、{{last_frame}}、{{reference_images}} 与高级参数变量。列表路径仅支持相对路径。</p>
    <div class="section-label">模型能力 <small>需在模板中引用对应变量</small></div><div class="capability-grid">${Object.entries(capabilityNames).map(([key,label])=>`<label class="check-label"><input type="checkbox" name="cap_${key}" ${c.capabilities?.[key]?'checked':''}>${label}</label>`).join('')}</div>
    <div class="field-grid">${fieldHTML('text_path','文本响应路径',c.text_path||'',{placeholder:'choices.0.message.content'})}${fieldHTML('media_path','媒体 URL 路径',c.media_path||'',{placeholder:'data.0.url'})}</div>${fieldHTML('base64_path','图片 Base64 路径',c.base64_path||'',{placeholder:'data.0.b64_json'})}
    <div class="field-grid">${fieldHTML('id_path','任务 ID 路径',c.id_path||'',{placeholder:'id'})}${fieldHTML('status_path','状态路径',c.status_path||'',{placeholder:'status'})}</div>${fieldHTML('poll_path','轮询路径',c.poll_path||'',{placeholder:'/tasks/{id}'})}
    <div class="field-grid">${fieldHTML('success_values','成功状态（英文逗号分隔）',(c.success_values||['completed','succeeded','success']).join(','))}${fieldHTML('failure_values','失败状态（英文逗号分隔）',(c.failure_values||['failed','error','cancelled']).join(','))}</div>
    <label>Token 字段映射（JSON）<textarea name="usage_paths" rows="3" spellcheck="false">${esc(JSON.stringify(c.usage_paths||{},null,2))}</textarea></label><p class="field-hint">例如 {"input_tokens":"usage.prompt_tokens","output_tokens":"usage.completion_tokens"}。</p>
    <div class="field-grid">${fieldHTML('response_model_path','返回模型字段',c.response_model_path||'')}${fieldHTML('response_id_path','响应 ID 字段',c.response_id_path||'')}</div></div>`;
}

async function editProvider(id,kind){
  closeAssistant();const openVersion=++connectionOpenVersion;
  let platforms;try{platforms=(await api('/api/platforms')).platforms}catch(err){if(openVersion===connectionOpenVersion)toast(err.message);return}
  if(openVersion!==connectionOpenVersion)return;
  const original=state.providers.find(p=>p.id===id), defaultKind=original?.kind||kind||(['image','video'].includes(state.page)?state.page:'chat');
  const dialog=$('#provider-dialog');
  if(dialog.open)dialog.close();
  dialog.innerHTML=`<form id="provider-form" novalidate><div class="dialog-head"><div><h2 id="provider-title">${original?'编辑模型':'接入模型'}</h2><p>连接你的平台，选择需要的模型。</p></div><button type="button" class="icon-button" data-action="close-provider" aria-label="关闭设置">${icon('close')}</button></div>
    <nav class="connection-progress" aria-label="模型接入步骤"><button type="button" id="connection-step-one"><span>1</span>连接平台</button><i></i><button type="button" id="connection-step-two"><span>2</span>选择模型</button></nav>
    <input type="hidden" name="id" value="${original?.id||''}"><input type="hidden" name="model" value="${esc(original?.model||'')}"><input type="hidden" name="kind" value="${defaultKind}">
    <div class="connection-body"><section id="connection-platform-pane" class="connection-platform-pane">
      <div class="connection-pane-intro"><h3>先连接模型平台</h3><p>填入你的 API Key，读取平台返回的模型。</p></div>
      <label>模型平台<select name="platform">${platforms.map(p=>`<option value="${esc(p.id)}">${esc(p.name)}</option>`).join('')}</select></label>
      <label>API Key <span class="connection-optional" id="connection-key-note"></span><div class="connection-secret"><input name="api_key" type="password" autocomplete="new-password" placeholder="粘贴当前平台的 API Key"><button type="button" id="connection-key-toggle" aria-label="显示密钥">显示</button></div></label>
      <label><span class="connection-label-row">API 基础地址 <span id="connection-address-origin">由平台自动填写，可修改</span></span><input name="base_url" type="url" value="${esc(original?.base_url||'')}" placeholder="https://api.example.com/v1" spellcheck="false"></label>
      <p class="connection-platform-hint" id="connection-platform-hint"></p>
      <details class="connection-network-options"><summary>连接选项</summary><label>模型目录协议<select name="discovery_protocol"><option value="openai_chat">OpenAI 兼容</option><option value="anthropic">Anthropic</option><option value="gemini">Gemini</option><option value="custom">自定义 JSON</option></select></label><label class="check-label"><input name="allow_local" type="checkbox" ${original?.allow_local?'checked':''}>允许本机 HTTP（仅回环地址）</label><button type="button" class="text-button" id="connection-network-advanced">自定义认证与列表路径 ${icon('arrow')}</button></details>
    </section>
    <section id="connection-model-pane" class="connection-model-pane" hidden><div class="connection-model-browser"><div class="connection-browser-head"><div><h3>选择模型</h3><span id="connection-result-count"></span></div><button type="button" id="connection-refresh" class="text-button">${icon('refresh')} 刷新</button></div><label class="connection-model-search">${icon('search')}<input type="search" id="connection-model-search" aria-label="搜索可用模型" placeholder="搜索模型名称或 ID"></label><div id="connection-model-list" class="connection-model-list" aria-label="可用模型"></div><div class="connection-manual-area"><button type="button" class="text-button" id="connection-manual-toggle">找不到模型？手动填写</button><label id="connection-manual-field" hidden>模型 ID / 接入点<input name="manual_model" placeholder="输入平台提供的完整模型 ID" value="${esc(original?.model||'')}" maxlength="200" spellcheck="false"></label></div></div>
      <aside class="connection-selection"><div class="connection-selection-title">连接预览</div><div id="connection-selected-summary"></div>
      <div id="connection-selected-fields" hidden><label>连接名称<input name="name" maxlength="60" value="${esc(original?.name||'')}" placeholder="自动使用模型名称"></label>
      <fieldset class="connection-purpose"><legend>模型用途</legend>${Object.entries(kindNames).map(([k,label])=>`<label><input type="radio" name="purpose" value="${k}"><span>${k==='chat'?'AI 助手':label}</span></label>`).join('')}</fieldset><p id="connection-purpose-note" class="field-hint"></p>
      <details class="connection-protocol-options"><summary>协议与请求地址</summary><label>接口协议<select name="protocol"></select></label><code id="connection-request-url"></code></details></div>
      <button type="button" class="connection-advanced-button" id="connection-open-advanced">${icon('sliders')} 高级参数与映射 ${icon('arrow')}</button><p class="connection-small-note">读取模型和保存连接不会生成内容。</p></aside></section>
    <section id="connection-advanced-pane" class="connection-advanced-pane" hidden>${connectionAdvancedHTML(original)}</section></div>
    <div class="connection-error" id="connection-error" role="alert" hidden></div><div class="dialog-footer"><div class="connection-footer-left"><button type="button" id="connection-back" class="button secondary" hidden>上一步</button><button type="button" id="connection-manual-next" class="text-button">手动填写模型</button></div><span id="connection-footer-hint"></span><button type="submit" id="connection-primary" class="button primary">读取模型 ${icon('arrow')}</button></div></form>`;
  setupConnectionWizard($('#provider-form'),original,platforms,defaultKind);dialog.showModal();
}

function setupConnectionWizard(form,original,platforms,defaultKind){
  const dialog=$('#provider-dialog'), f=name=>form.elements.namedItem(name), el=id=>form.querySelector('#'+id);
  const current=()=>form.isConnected&&dialog.open&&$('#provider-form')===form;
  let step=original?2:1, advanced=false, advancedFrom=1, revision=0, busy=false, saving=false, models=[], loaded=false, manual=false, model=original?{id:original.model,name:original.model,supported_kinds:[original.kind],protocol:original.protocol}:null, purposeConfirmed=!!original, automaticName='';
  const platform=()=>platforms.find(p=>p.id===f('platform').value);
  const canonical=value=>value.trim().replace(/\/+$/,'');
  const savedAddress=()=>original&&canonical(original.base_url)===canonical(f('base_url').value);
  const unsupported=()=>platform()?.discovery_protocol==='unsupported'&&!f('discovery_path').value.trim();
  function error(message=''){el('connection-error').hidden=!message;el('connection-error').textContent=message}
  function endpoint(){
    const base=canonical(f('base_url').value), selected=f('model').value;
    const suffix={openai_chat:'/chat/completions',openai_responses:'/responses',openai_image:'/images/generations',openai_video:'/videos',anthropic:'/messages',gemini:'/models/'+encodeURIComponent(selected.replace(/^models\//,''))+':generateContent',custom:f('submit_path').value}[f('protocol').value];
    el('connection-request-url').textContent=base&&suffix?base+'/'+suffix.replace(/^\//,''):'按平台文档配置提交路径';
    el('connection-custom-fields').hidden=f('protocol').value!=='custom'&&f('discovery_protocol').value!=='custom';
  }
  function protocols(value){f('protocol').innerHTML=protocolOptions[f('kind').value].map(p=>`<option value="${p}" ${p===value?'selected':''}>${protocolNames[p]}</option>`).join('');endpoint()}
  function platformNote(){
    el('connection-key-note').textContent=original?.has_key&&savedAddress()?'已保存，可留空复用':platform()?.allow_local?'本机无鉴权可留空':'';
    el('connection-platform-hint').textContent=unsupported()?platform().note:platform()?.allow_local?'请先启动本机模型服务，再读取模型。':platform()?.id==='custom'?'填写服务商给出的 API 前缀，默认使用 OpenAI 兼容协议。':'平台地址已填入。使用代理或专属端点时，可修改基础地址。';
  }
  function update(){
    el('connection-platform-pane').hidden=step!==1||advanced;el('connection-model-pane').hidden=step!==2||advanced;el('connection-advanced-pane').hidden=!advanced;
    dialog.classList.toggle('choosing-model',step===2&&!advanced);dialog.classList.toggle('editing-mapping',advanced);
    el('connection-step-one').setAttribute('aria-current',step===1?'step':'false');el('connection-step-one').disabled=saving;el('connection-step-two').setAttribute('aria-current',step===2?'step':'false');el('connection-step-two').disabled=!(loaded||model||manual)||busy||saving;
    form.querySelectorAll('input,select,textarea').forEach(control=>control.disabled=saving);
    el('connection-primary').disabled=busy||saving||(!advanced&&step===2&&(!model?.id||!purposeConfirmed));
    el('connection-primary').innerHTML=saving?'<span class="spinner"></span> 保存中':busy?'<span class="spinner"></span> 正在读取':advanced?'完成配置':step===1?(unsupported()?'填写模型 ID '+icon('arrow'):'读取模型 '+icon('arrow')):(original?'保存修改':'接入所选模型');
    el('connection-back').hidden=step===1&&!advanced;el('connection-back').textContent=advanced?'返回':'上一步';el('connection-back').disabled=saving;
    el('connection-manual-next').hidden=step!==1||advanced;el('connection-manual-next').disabled=busy||saving;
    el('connection-footer-hint').textContent=advanced?'仅在需要时修改':step===2?(model?.id?(purposeConfirmed?'已选择 1 个模型':'请确认模型用途'):'请选择一个模型'):'';
    el('connection-refresh').disabled=busy||saving||unsupported();
    el('connection-selected-fields').hidden=!model?.id;
    el('connection-selected-summary').innerHTML=model?.id?`<div class="connection-selected-icon">${icon(purposeConfirmed?(f('kind').value==='chat'?'assistant':f('kind').value):'model')}</div><h3>${esc(model.id)}</h3><p>${esc(platform()?.name||'自定义平台')}</p>`:`<div class="connection-selection-empty">${icon('model')}<h3>还未选择模型</h3><p>从左侧选择一个模型，<br>这里会显示连接信息。</p></div>`;
    f('purpose').forEach(radio=>radio.checked=!!model?.id&&purposeConfirmed&&radio.value===f('kind').value);
    el('connection-purpose-note').textContent=!model?.id?'':purposeConfirmed?'可根据实际接口能力调整用途。':'无法自动识别用途，请选择实际用途后保存。';
    el('connection-result-count').textContent=loaded?`${models.length} 个模型`:(original?'当前连接':'支持手动接入');
    endpoint();
  }
  function drawModels(){
    const query=el('connection-model-search').value.trim().toLowerCase(), filtered=models.filter(m=>(m.id+' '+m.name).toLowerCase().includes(query));
    const items=filtered.length?filtered:!loaded&&model&&!manual?[model]:[];
    el('connection-model-list').innerHTML=items.length?items.map(m=>`<label class="connection-model-option ${model?.id===m.id?'selected':''}"><input type="radio" name="model_choice" value="${esc(m.id)}" ${model?.id===m.id?'checked':''}><span class="connection-option-copy"><strong>${esc(m.name||m.id)}</strong>${m.name&&m.name!==m.id?`<small>${esc(m.id)}</small>`:''}<span class="connection-option-tags">${(m.supported_kinds||[]).length?(m.supported_kinds||[]).map(k=>`<em>${k==='chat'?'AI 助手':esc(kindNames[k]||k)}</em>`).join(''):'<em>用途待确认</em>'}</span></span>${icon('check','connection-option-check')}</label>`).join(''):`<div class="connection-list-empty">${icon('model')}<h3>${query?'没有匹配的模型':loaded?'平台未返回模型':'还没有模型列表'}</h3><p>${query?'换一个关键词，或手动填写模型 ID。':manual?'在下方填写模型 ID，再确认用途。':'可以返回读取模型，或在下方手动填写。'}</p></div>`;
    form.querySelectorAll('[name=model_choice]').forEach(radio=>radio.onchange=()=>selectModel(items.find(m=>m.id===radio.value)));
  }
  function selectModel(value,{fromManual=false}={}){
    model=value?.id?value:null;f('model').value=model?.id||'';f('manual_model').value=model?.id||'';
    const kinds=(model?.supported_kinds||[]).filter(k=>protocolOptions[k]);
    if(kinds.length){purposeConfirmed=true;if(!kinds.includes(f('kind').value))f('kind').value=kinds[0];protocols(model.protocol||platform()?.protocols?.[f('kind').value])}
    else if(!fromManual)purposeConfirmed=false;
    if(model&&(!f('name').value||f('name').value===automaticName)){automaticName=(model.name||model.id).slice(0,60);f('name').value=automaticName}
    if(!fromManual){manual=false;el('connection-manual-field').hidden=true;el('connection-manual-toggle').textContent='找不到模型？手动填写'}
    update();drawModels();
  }
  function invalidate({clearKey=false}={}){
    revision++;busy=false;loaded=false;models=[];model=null;purposeConfirmed=false;f('model').value='';f('manual_model').value='';el('connection-model-search').value='';
    if(clearKey)f('api_key').value='';error();platformNote();update();drawModels();
  }
  function showStep(value){step=value;advanced=false;error();update();if(step===2)drawModels()}
  function manualEntry(){
    if(!validConnection())return;revision++;busy=false;step=2;manual=true;model=null;purposeConfirmed=false;f('model').value='';f('manual_model').value='';el('connection-manual-field').hidden=false;el('connection-manual-toggle').textContent='手动填写模型 ID';error();update();drawModels();f('manual_model').focus();
  }
  function validConnection(){
    const base=f('base_url');if(!base.value.trim()||!base.checkValidity()){showStep(1);error('请填写有效的 API 基础地址。');base.focus();return false}
    return true;
  }
  async function discover(){
    if(busy||saving||!validConnection())return;if(unsupported()){manualEntry();return}
    const payload={id:f('id').value,platform:f('platform').value,kind:f('kind').value,protocol:f('discovery_protocol').value,base_url:f('base_url').value,api_key:f('api_key').value,allow_local:f('allow_local').checked,custom:Object.fromEntries(['discovery_path','auth_header','auth_prefix'].map(key=>[key,f(key).value]))};
    const requestRevision=++revision;busy=true;error();update();
    try{
      const result=await api('/api/models/discover',payload);if(requestRevision!==revision||!current())return;
      models=result.models||[];loaded=true;step=2;advanced=false;
      // Refresh catalog metadata without replacing a user's saved protocol or purpose.
      const refreshed=models.find(m=>m.id===model?.id);if(refreshed){model={...refreshed};manual=false}
      el('connection-manual-field').hidden=!manual;el('connection-manual-toggle').textContent=manual?'手动填写模型 ID':'找不到模型？手动填写';
      if(!models.length){manual=true;el('connection-manual-field').hidden=false;el('connection-manual-toggle').textContent='手动填写模型 ID';error(result.supported===false?result.caveat:'平台未返回模型，可手动填写模型 ID。')}
      if(result.truncated)error('目录较大，当前显示部分模型。未显示的模型可手动填写。');
      drawModels();
    }catch(err){if(requestRevision!==revision||!current())return;error(err.message+' 可重试或选择手动填写。')}
    finally{if(requestRevision===revision&&current()){busy=false;update()}}
  }
  async function save(){
    if(saving||busy||!model?.id||!purposeConfirmed||!validConnection())return;
    const name=f('name').value.trim();if(!name){error('请填写连接名称。');f('name').focus();return}
    if(name.length>60){error('连接名称最多 60 个字符。');f('name').focus();return}
    const payload={};['id','platform','kind','protocol','base_url','api_key'].forEach(key=>payload[key]=f(key).value);payload.name=name;payload.model=model.id;payload.allow_local=f('allow_local').checked;
    try{payload.extra=JSON.parse(f('extra_json').value||'{}');payload.custom={body:JSON.parse(f('body_template').value||'{}'),usage_paths:JSON.parse(f('usage_paths').value||'{}')}}catch{advanced=true;advancedFrom=2;update();error('高级参数中的 JSON 格式不正确，请检查引号、逗号与括号。');return}
    ['submit_path','discovery_path','auth_header','auth_prefix','text_path','media_path','base64_path','id_path','status_path','poll_path','response_model_path','response_id_path'].forEach(key=>payload.custom[key]=f(key).value);
    ['success_values','failure_values'].forEach(key=>payload.custom[key]=f(key).value.split(',').map(s=>s.trim().toLowerCase()).filter(Boolean));payload.custom.discovery_protocol=f('discovery_protocol').value;payload.custom.capabilities=Object.fromEntries(Object.keys(capabilityNames).map(key=>[key,f('cap_'+key).checked]));
    saving=true;error();update();
    try{const saved=await api('/api/providers/save',payload);state.providers=state.providers.filter(p=>p.id!==saved.id);state.providers.unshift(saved);state.selected[saved.kind]=saved.id;state.usage=null;if(current()){dialog.close();render();toast('模型已接入，可在工作台中选择使用')}else renderNavigation()}
    catch(err){if(current())error(err.message)}finally{saving=false;if(current())update()}
  }
  f('platform').value=original?.platform||platforms.find(p=>p.base_url&&canonical(p.base_url)===canonical(original?.base_url||''))?.id||(original?'custom':'openai');if(!platform())f('platform').value='custom';
  if(!original)f('base_url').value=platform()?.base_url||'';
  const discoveryProtocol=p=>['anthropic','gemini','custom'].includes(p)?p:'openai_chat';
  f('discovery_protocol').value=original?.custom?.discovery_protocol||discoveryProtocol(original?.protocol||platform()?.protocols?.[defaultKind]||platform()?.protocols?.chat);
  protocols(original?.protocol||platform()?.protocols?.[defaultKind]);platformNote();update();drawModels();
  f('platform').onchange=()=>{f('base_url').value=platform()?.base_url||'';f('allow_local').checked=!!platform()?.allow_local;f('discovery_path').value='';f('auth_header').value='Authorization';f('auth_prefix').value='Bearer ';f('kind').value=platform()?.protocols?.[defaultKind]?defaultKind:Object.keys(platform()?.protocols||{chat:''})[0];f('discovery_protocol').value=discoveryProtocol(platform()?.protocols?.[f('kind').value]);protocols(platform()?.protocols?.[f('kind').value]);invalidate({clearKey:true})};
  f('base_url').oninput=()=>invalidate({clearKey:true});f('api_key').oninput=()=>invalidate();f('allow_local').onchange=()=>invalidate();f('discovery_protocol').onchange=()=>{invalidate();if(f('discovery_protocol').value==='custom'){f('protocol').value='custom';advanced=true;advancedFrom=1;update()}};
  ['discovery_path','auth_header','auth_prefix'].forEach(key=>f(key).oninput=()=>{revision++;loaded=false;models=[];busy=false;platformNote();update()});
  f('purpose').forEach(radio=>radio.onchange=()=>{const custom=f('protocol').value==='custom';f('kind').value=radio.value;purposeConfirmed=true;protocols(custom?'custom':platform()?.protocols?.[radio.value]||model?.protocol);update()});f('protocol').onchange=()=>{endpoint();if(f('protocol').value==='custom'){advanced=true;advancedFrom=2;update()}};f('submit_path').oninput=endpoint;
  f('manual_model').oninput=()=>selectModel({id:f('manual_model').value.trim()},{fromManual:true});el('connection-model-search').oninput=drawModels;
  el('connection-key-toggle').onclick=()=>{const visible=f('api_key').type==='password';f('api_key').type=visible?'text':'password';el('connection-key-toggle').textContent=visible?'隐藏':'显示';el('connection-key-toggle').setAttribute('aria-label',visible?'隐藏密钥':'显示密钥')};
  el('connection-step-one').onclick=()=>showStep(1);el('connection-step-two').onclick=()=>showStep(2);el('connection-back').onclick=()=>{if(advanced){advanced=false;step=advancedFrom;update()}else showStep(1)};
  el('connection-manual-next').onclick=manualEntry;el('connection-manual-toggle').onclick=()=>{if(!manual)manualEntry();else f('manual_model').focus()};el('connection-refresh').onclick=discover;
  [el('connection-open-advanced'),el('connection-network-advanced')].forEach(button=>button.onclick=()=>{advancedFrom=step;advanced=true;update()});
  form.onsubmit=e=>{e.preventDefault();if(advanced){advanced=false;step=advancedFrom;update()}else if(step===1){if(loaded)showStep(2);else discover()}else save()};
  dialog.addEventListener('close',()=>{revision++;f('api_key').value='';models=[]},{once:true});
}

function closeProvider(){const input=$('#provider-form [name=api_key]');if(input)input.value='';$('#provider-dialog').close()}
