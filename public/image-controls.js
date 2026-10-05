/* Image controls follow the server's model-specific capability schema. */
function imageOptions(p){return p?.image_controls||{mode:'none',ratios:[],levels:[],sizes:[],quality:[]}}
function imageRatio(p,d){
  const o=imageOptions(p);
  if(o.mode==='aspect')return d.parameters.aspect_ratio||'auto';
  if(d.size==='auto')return 'auto';
  const match=/^(\d+)x(\d+)$/.exec(d.size);
  if(!match)return 'custom';
  return o.ratios.find(r=>{const [w,h]=r.value.split(':').map(Number);return Number(match[1])*h===Number(match[2])*w})?.value||'custom';
}
function imageLevel(p,d){
  const o=imageOptions(p);
  if(o.mode==='aspect')return d.parameters.resolution||'';
  const ratio=o.ratios.find(r=>r.value===imageRatio(p,d));
  return Object.entries(ratio?.sizes||{}).find(([,size])=>size===d.size)?.[0]||'';
}
function imageCanvas(p){
  const o=imageOptions(p),d=state.drafts.image,ratio=imageRatio(p,d),level=imageLevel(p,d);
  const enabled=o.mode!=='none',pixels=['pixels','fixed','custom'].includes(o.mode);
  const choices=[{value:'auto',label:'模型默认'},...o.ratios];
  const control=o.ratios.length?`<label>比例<select id="image-ratio-select">${choices.map(r=>`<option value="${r.value}" ${ratio===r.value?'selected':''}>${r.value==='auto'?'模型默认':r.value+' · '+r.label}</option>`).join('')}${ratio==='custom'?'<option value="custom" selected>自定义</option>':''}</select></label>`:`<label>尺寸<select id="image-size-select" ${enabled?'':'disabled'}>${['auto',...o.sizes].map(v=>`<option value="${v}" ${d.size===v?'selected':''}>${v==='auto'?'模型默认':v}</option>`).join('')}</select></label>`;
  return `${control}
    ${o.levels.length?`<label class="canvas-level">输出尺寸档位<select id="image-level" ${o.mode==='pixels'&&['auto','custom'].includes(ratio)?'disabled':''}><option value="" ${o.mode==='pixels'?'disabled':''}>${o.mode==='aspect'?'模型默认':ratio==='custom'?'自定义尺寸':ratio==='auto'?'先选择比例':'自定义尺寸'}</option>${o.levels.map(([v,label])=>`<option value="${v}" ${level===v?'selected':''}>${label}</option>`).join('')}</select></label>`:''}
    <div class="canvas-request"><span>${pixels?'实际请求尺寸':'尺寸由模型决定'}</span><strong id="image-size-preview">${pixels?esc(d.size==='auto'?'模型默认':d.size.replace('x',' × ')):esc([d.parameters.aspect_ratio||'默认比例',d.parameters.resolution||'默认分辨率'].join(' · '))}</strong></div>
    ${pixels?`<details class="pixel-editor" ${ratio==='custom'&&o.mode==='pixels'?'open':''}><summary>自定义像素尺寸</summary><label>宽 × 高<input id="size-input" value="${esc(d.size)}" placeholder="auto 或 864x1536" ${o.mode==='fixed'?'readonly':''}></label><p class="field-hint">${o.mode==='pixels'?'宽高须为 16 的倍数，最长边 ≤ 3840；总像素 0.66–8.29MP，比例不超过 3:1。':'当前模型尺寸以平台支持为准。'}</p></details>`:'<input id="size-input" type="hidden" value="auto">'}
    <p class="field-hint canvas-note">${o.mode==='pixels'?'平台名称是常用构图参考；比例会换算为上方像素尺寸。更大尺寸可能增加耗时和费用，超清档位为实验性。':o.mode==='fixed'?'此模型仅支持以上固定尺寸。抖音、B站等精确比例可切换 GPT Image 2 / 2.5 等支持多比例的模型。':o.mode==='aspect'?'比例直接传给模型，实际像素由接口返回；分辨率档位仅在模型支持时显示。':o.mode==='custom'?'此连接使用自定义尺寸，请按平台支持范围填写。':'当前连接未提供尺寸控制；自定义接口可在模型接入中映射尺寸或画幅比例。'}</p>`;
}
function refreshImageCanvas(){const p=chosen('image');$('#image-canvas-controls').innerHTML=imageCanvas(p);bindImageCanvas(p);if(typeof creatorParameterSummary==='function')creatorParameterSummary()}
function bindImageCanvas(p){
  const d=state.drafts.image,o=imageOptions(p);
  const select=$('#image-ratio-select');if(select)select.onchange=()=>{
    const ratio=select.value,level=imageLevel(p,d)||'standard';
    if(o.mode==='aspect'){d.parameters.aspect_ratio=ratio==='auto'?'':ratio;d.size='auto'}
    else if(ratio!=='custom')d.size=ratio==='auto'?'auto':o.ratios.find(r=>r.value===ratio).sizes[level];
    refreshImageCanvas();
  };
  const sizeSelect=$('#image-size-select');if(sizeSelect)sizeSelect.onchange=()=>{d.size=sizeSelect.value;refreshImageCanvas()};
  const levels=$('#image-level');if(levels)levels.onchange=()=>{
    if(o.mode==='aspect')d.parameters.resolution=levels.value;
    else if(levels.value)d.size=o.ratios.find(r=>r.value===imageRatio(p,d)).sizes[levels.value];
    refreshImageCanvas();
  };
  const input=$('#size-input');input.oninput=()=>{
    d.size=input.value.trim().toLowerCase();
    $('#image-size-preview').textContent=d.size.replace('x',' × ')||'模型默认';
    document.querySelectorAll('[data-image-ratio]').forEach(b=>{const selected=b.dataset.imageRatio===imageRatio(p,d);b.classList.toggle('active',selected);b.setAttribute('aria-pressed',selected)});
    if(levels){levels.value=imageLevel(p,d);levels.disabled=['auto','custom'].includes(imageRatio(p,d))}
  };
}
function imageAdvancedFields(p){
  const c=capabilities(p),control=(label,key,opts)=>c[key==='n'?'batch':key]?advancedControl(label,key,'image',c,opts):'';
  const available=[control('生成质量','quality',{choices:qualityOptions(p)}),control('生成数量','n',{choices:Array.from({length:p?.protocol==='minimax_image'?9:10},(_,i)=>[i+1,`${i+1} 张`])}),
    control('文件格式','output_format',{choices:[['png','PNG · 无损'],['jpeg','JPEG · 体积小'],['webp','WebP · 支持透明']]}),control('背景处理','background',{choices:[['opaque','不透明'],['transparent','透明 · 抠图素材']]}),
    control('输出压缩（0–100）','output_compression',{type:'number',min:0,max:100,step:1,placeholder:'仅 JPEG / WebP'}),control('图像风格','style',{choices:[['natural','自然'],['vivid','鲜明']]}),
    control('随机种子','seed',{type:'number',min:0,max:2147483647,step:1,placeholder:'随机'}),control('参考强度（0–1）','strength',{type:'number',min:0,max:1,step:.05}),
    imageOptions(p).mode!=='aspect'?control('输出分辨率','resolution',{choices:[['1K','1K'],['2K','2K'],['4K','4K']]}):''].filter(Boolean).join('');
  const unsupported=[['negative_prompt','负面提示词'],['seed','随机种子'],['strength','参考强度']].filter(([k])=>!c[k]).map(([,label])=>label);
  return `<details class="advanced image-advanced"><summary><span>${icon('sliders')} 高级参数</span>${icon('down')}</summary><div class="advanced-body"><button type="button" class="button secondary wide" data-action="reset-image-parameters">${icon('refresh')} 恢复默认参数</button><p class="field-hint">同时重置画幅和高级参数，保留画面描述与参考图；连接中设置的默认参数仍会生效。</p><div class="field-grid">${available}</div>${control('负面提示词','negative_prompt',{type:'textarea',placeholder:'不希望出现的元素'})}
    <p class="field-hint" id="image-background-hint"></p><p class="field-hint" id="image-format-hint">仅 JPEG / WebP 可设置压缩；透明背景需用 PNG / WebP。留空沿用连接或模型默认值。</p>
    ${unsupported.length?`<details class="unsupported-controls"><summary>当前接口未提供的参数 · ${unsupported.length} 项</summary><p>${unsupported.join('、')}：${p?.protocol==='custom'?'尚未在自定义请求模板中映射。可前往模型接入配置。':'当前协议没有这些独立请求参数。可在画面描述中写清排除元素与参考要求；需要精确控制时请选择支持这些参数的模型。'}</p></details>`:''}
    <p class="field-hint">${p?`生成响应等待上限 ${p.effective_request_timeout||600} 秒，可在模型接入的高级配置中调整。大图、最高质量与透明背景可能需要更久。`:""}</p><p class="field-hint">画质档位取决于平台实现；max / xhigh 是扩展值，不保证比默认更好。风景、人物场景建议先用默认背景，透明仅用于抠图素材。</p></div></details>`;
}
function updateImageFormatControls(){
  const p=chosen('image'),d=state.drafts.image,format=d.parameters.output_format||p?.extra?.output_format||'png';
  const input=$('[data-param="output_compression"]'),select=$('[data-param="output_format"]');
  if(input){input.disabled=!['jpeg','webp'].includes(format);if(input.disabled){delete d.parameters.output_compression;input.value=''}}
  const backgroundHint=$('#image-background-hint');if(backgroundHint){const transparent=(d.parameters.background||p?.extra?.background)==='transparent';backgroundHint.classList.toggle('parameter-error',transparent);backgroundHint.textContent=transparent?'已开启透明背景：天空、云雾等背景可能被移除或出现抠图边缘。完整场景请改为默认或不透明。':'背景默认适合完整场景；透明背景用于独立商品、贴纸等抠图素材。'}
  const conflict=format==='jpeg'&&(d.parameters.background||p?.extra?.background)==='transparent';
  if(select)select.setCustomValidity(conflict?'JPEG 不支持透明背景，请选择 PNG 或 WebP。':'');
  $('#image-format-hint').classList.toggle('parameter-error',conflict);
  $('#image-format-hint').textContent=conflict?'JPEG 不支持透明背景，请选择 PNG 或 WebP。':'仅 JPEG / WebP 可设置压缩；透明背景需用 PNG / WebP。留空沿用连接或模型默认值。';
}

function resetImageParameters(){const d=state.drafts.image;d.size='auto';d.parameters={}}
function imageOutputInfo(job,asset){
  if(!asset||asset.type!=='image')return '';
  const actual=asset.width&&asset.height?`${asset.width}x${asset.height}`:null;
  const mismatch=actual&&job.size&&job.size!=='auto'&&job.size!==actual;
  return `<div class="image-output-info ${mismatch?'mismatch':''}"><strong>实际出图：${actual?esc(actual.replace('x',' × ')):'尺寸尚未读取'}</strong><span>${mismatch?`平台返回尺寸与请求 ${esc(job.size.replace('x',' × '))} 不一致，未在本机放大或裁切。`:'显示原始作品文件，不对图片进行放大或重编码。'}</span>${job.parameters?.background==='transparent'?'<span>本次请求使用透明背景，可能移除天空等场景内容。</span>':''}</div>`;
}
