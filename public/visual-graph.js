'use strict';
// Pure graph editing helpers shared by the UI and regression tests.
const VisualGraph = (() => {
 const width=320,height=390;
 const uid=()=>crypto.randomUUID().replaceAll('-','');
 const clone=x=>JSON.parse(JSON.stringify(x));
 const current=n=>(n.versions||[]).find(v=>v.id===n.active_version_id);
 function stale(nodes,node,memo=new Map()){
  if(memo.has(node.id))return memo.get(node.id);memo.set(node.id,false);const v=current(node);if(!v)return false;
  const snapshot=node.refs.map(id=>{const ref=nodes.find(n=>n.id===id),version=ref&&current(ref);return {node_id:id,version_id:version?.id||null,upload_id:version?.upload_id||null}});
  const changed=v.prompt!==node.prompt||JSON.stringify(v.reference_snapshot||[])!==JSON.stringify(snapshot)||node.refs.some(id=>{const ref=nodes.find(n=>n.id===id);return !ref||stale(nodes,ref,memo)});memo.set(node.id,changed);return changed;
 }
 function reaches(nodes,start,end,seen=new Set()){
  if(start===end)return true;if(seen.has(start))return false;seen.add(start);
  return (nodes.find(n=>n.id===start)?.refs||[]).some(r=>reaches(nodes,r,end,seen));
 }
 function connect(nodes,source,target){
  const to=nodes.find(n=>n.id===target);if(!to||!nodes.some(n=>n.id===source))throw Error('请选择画布上的节点');
  if(reaches(nodes,source,target))throw Error('不能连接自身或形成循环');
  if(to.refs.includes(source))return;if(to.refs.length>=8)throw Error('每个节点最多引用8个节点');to.refs.push(source);
 }
 function serialize(nodes,selected){
  return {format:'guangyu-visual-nodes',schema:1,nodes:nodes.filter(n=>selected.has(n.id)).map(n=>({id:n.id,kind:n.kind,subtype:n.subtype,title:n.title,prompt:n.prompt,video_prompt:n.video_prompt,provider_id:n.provider_id,ratio:n.ratio,layout:n.layout,x:n.x,y:n.y,refs:[...n.refs],upload_id:current(n)?.upload_id||n.upload_id||null}))};
 }
 function paste(data,existing,offset={x:45,y:45}){
  if(data?.format!=='guangyu-visual-nodes'||data.schema!==1||!Array.isArray(data.nodes)||!data.nodes.length||existing.length+data.nodes.length>64)throw Error('剪贴板不是有效的光屿节点，或超过64个节点');
  const map=new Map(data.nodes.map(n=>[n.id,uid()]));if(map.size!==data.nodes.length)throw Error('节点ID重复');
  const available=new Set(existing.map(n=>n.id));
  return data.nodes.map(n=>{
   if(!['master','shot'].includes(n.kind)||typeof n.prompt!=='string'||typeof n.title!=='string'||!Array.isArray(n.refs)||!Number.isFinite(n.x)||!Number.isFinite(n.y))throw Error('节点内容无效');
   return {id:map.get(n.id),kind:n.kind,subtype:n.subtype||'character',title:n.title,prompt:n.prompt,video_prompt:n.video_prompt||'',provider_id:n.provider_id||'',ratio:n.ratio||'9:16',layout:n.layout||'single',x:n.x+offset.x,y:n.y+offset.y,refs:n.refs.map(r=>map.get(r)||(available.has(r)?r:null)).filter(Boolean),upload_id:n.upload_id||null,versions:[],active_version_id:null,job_ids:[]};
  });
 }
 function make(kind,subtype='character',index=0){
  const sheet=kind==='master'&&subtype==='character';
  return {id:uid(),kind,subtype,title:kind==='shot'?'镜头 '+String(index+1).padStart(2,'0'):({character:'角色定稿',scene:'场景定稿',prop:'道具定稿',style:'风格定稿'})[subtype],prompt:'',video_prompt:'',provider_id:'',ratio:sheet?'16:9':'9:16',layout:sheet?'sheet':'single',x:60+(index%4)*(width+60),y:80+Math.floor(index/4)*(height+60),refs:[],versions:[],active_version_id:null,job_ids:[]};
 }
 function fit(nodes,canvasWidth,canvasHeight){
  if(!nodes.length)return {x:40,y:40,zoom:1};
  const x=Math.min(...nodes.map(n=>n.x)),y=Math.min(...nodes.map(n=>n.y));
  const w=Math.max(...nodes.map(n=>n.x+width))-x,h=Math.max(...nodes.map(n=>n.y+height))-y;
  const zoom=Math.min(1.1,Math.max(.15,Math.min((canvasWidth-70)/w,(canvasHeight-70)/h)));
  return {x:(canvasWidth-w*zoom)/2-x*zoom,y:(canvasHeight-h*zoom)/2-y*zoom,zoom};
 }
 return {width,height,uid,clone,current,connect,serialize,paste,make,fit,stale};
})();
if(typeof module!=='undefined')module.exports=VisualGraph;
