const assert=require('node:assert/strict'),express=require('express'),fs=require('node:fs/promises'),os=require('node:os'),path=require('node:path');
const {installDeleteRoutes,runOperation}=require('./delete-routes');
(async()=>{
 const root=await fs.mkdtemp(path.join(os.tmpdir(),'music-delete-fixtures-'));let jobs=false,time=Date.now(),operations=0;
 const app=express();app.use(express.json());
 let release,gate=false;
 const busy=installDeleteRoutes(app,{musicDir:root,authorize:async token=>token==='fixture-a'?'a':token==='fixture-b'?'b':null,hasActiveJobs:()=>jobs,onDeleted(){operations++},now:()=>time,operate:async(...args)=>{if(gate&&args[1].operation==='delete')await new Promise(resolve=>{release=resolve});return runOperation(...args)}});
 const server=app.listen(0,'127.0.0.1');await new Promise(resolve=>server.once('listening',resolve));const base='http://127.0.0.1:'+server.address().port;
 const headers={'Content-Type':'application/json','Origin':'https://music.zzxx.ooo','Sec-Fetch-Site':'same-origin','X-Music-Action':'delete','Cf-Access-Jwt-Assertion':'fixture-a'};
 const request=async(endpoint,body,extra={})=>{const response=await fetch(base+endpoint,{method:'POST',headers:{...headers,...extra},body:JSON.stringify(body)});return{status:response.status,data:await response.json()}};
 const make=async name=>{const file=path.join(root,'Artist','Album',name+'.m4a');await fs.mkdir(path.dirname(file),{recursive:true});await fs.writeFile(file,'disposable fixture');return'Artist/Album/'+name+'.m4a'};
 try{
  const target=await make('target'),keep=await make('keep');
  for(const extra of [{'Origin':'https://attacker.test'},{'Sec-Fetch-Site':'cross-site'},{'X-Music-Action':''}])assert.equal((await request('/api/library/delete/preview',{path:target,kind:'song'},extra)).status,403);
  assert.equal((await request('/api/library/delete/preview',{path:target,kind:'song'},{'Cf-Access-Jwt-Assertion':''})).status,401);
  let preview=await request('/api/library/delete/preview',{path:target,kind:'song'});assert.equal(preview.status,200);assert(!('fingerprint'in preview.data));assert.equal(preview.data.permanent,true);
  const token=preview.data.token;assert.equal((await request('/api/library/delete',{token,confirmed:false})).status,409);
  assert.equal((await request('/api/library/delete',{token,confirmed:true},{'Cf-Access-Jwt-Assertion':'fixture-b'})).status,409);
  assert.equal((await request('/api/library/delete',{token:'invented',confirmed:true})).status,409);
  assert.equal((await request('/api/library/delete',{token,confirmed:true,path:keep})).status,200);await assert.rejects(fs.stat(path.join(root,target)));assert((await fs.stat(path.join(root,keep))).isFile());assert.equal(operations,1);
  assert.equal((await request('/api/library/delete',{token,confirmed:true})).status,409);
  preview=await request('/api/library/delete/preview',{path:keep,kind:'song'});time+=120001;assert.equal((await request('/api/library/delete',{token:preview.data.token,confirmed:true})).status,409);
  jobs=true;assert.equal((await request('/api/library/delete/preview',{path:keep,kind:'song'})).status,409);jobs=false;
  preview=await request('/api/library/delete/preview',{path:keep,kind:'song'});await fs.appendFile(path.join(root,keep),' changed');assert.equal((await request('/api/library/delete',{token:preview.data.token,confirmed:true})).status,409);assert((await fs.stat(path.join(root,keep))).isFile());
  assert.equal((await request('/api/library/delete/preview',{path:'../outside',kind:'artist'})).status,409);
  preview=await request('/api/library/delete/preview',{path:keep,kind:'song'});gate=true;const deleting=request('/api/library/delete',{token:preview.data.token,confirmed:true});
  for(let i=0;i<100&&!release;i++)await new Promise(resolve=>setTimeout(resolve,5));assert(busy());assert.equal((await request('/api/library/delete/preview',{path:keep,kind:'song'})).status,409);release();assert.equal((await deleting).status,200);assert(!busy());
  console.log('Delete routes: auth/CSRF, fresh confirmation, expiry, ownership, replay, scope binding, changed files, job/operation locks passed (disposable fixtures only)');
 }finally{await new Promise(resolve=>server.close(resolve));await fs.rm(root,{recursive:true,force:true})}
})().catch(error=>{console.error(error);process.exitCode=1});
