const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path'),assert=require('node:assert/strict');
const ctx=vm.createContext({document:{querySelector:()=>null},console});
vm.runInContext(fs.readFileSync(path.join(__dirname,'../public/app.js'),'utf8').split("document.addEventListener('click'")[0],ctx);
const legacy=vm.runInContext(`resultHTML({id:'test',kind:'video',status:'failed',model:'fixture',prompt:'test',upstream_id:'task_fixture',error:JSON.stringify({code:'generation_failed',message:'失败 <script>'}),result:{assets:[]}})`,ctx);
assert.ok(legacy.includes('平台已确认任务失败'));assert.ok(legacy.includes('失败 &lt;script&gt;'));assert.ok(!legacy.includes('<script>'));
assert.ok(legacy.includes('核对平台状态'));assert.ok(legacy.includes('未提供更具体原因'));assert.ok(!legacy.includes('&quot;message&quot;'));
const interrupted=vm.runInContext(`resultHTML({id:'test',kind:'video',status:'interrupted',prompt:'test',upstream_id:'task_fixture',error:'Connection interrupted',result:{assets:[]}})`,ctx);
assert.ok(interrupted.includes('生成状态尚未确认'));assert.ok(interrupted.includes('继续查询原任务'));assert.ok(!interrupted.includes('平台已确认任务失败'));
console.log('PASS terminal versus uncertain failures, legacy JSON readability, task-query labels and escaped error text');
