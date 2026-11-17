const crypto=require('crypto');
const {execFile}=require('child_process');
const path=require('path');
const {createAccessAuthorizer}=require('./access-auth');
function runOperation(root,request){
  return new Promise((resolve,reject)=>{
    const child=execFile('python3',[path.join(__dirname,'library_delete.py'),root],{timeout:120000,maxBuffer:1024*1024},(error,stdout)=>{
      if(error)return reject(new Error('Library operation interrupted; refresh the library'));
      try{resolve(JSON.parse(stdout));}catch{reject(new Error('Library operation failed'));}
    });
    child.stdin.on('error',()=>{});
    child.stdin.end(JSON.stringify(request));
  });
}
function installDeleteRoutes(app,{musicDir,hasActiveJobs,onDeleted,authorize=createAccessAuthorizer(),operate=runOperation,origin='https://music.zzxx.ooo',now=()=>Date.now()}){
  const tickets=new Map();let busy=false;
  async function protect(req,res,next){
    res.setHeader('Cache-Control','no-store');
    if(req.get('origin')!==origin||req.get('sec-fetch-site')!=='same-origin'||req.get('x-music-action')!=='delete'||!req.is('application/json'))return res.status(403).json({error:'Use the signed-in app to delete music'});
    const subject=await authorize(req.get('cf-access-jwt-assertion'));
    if(!subject)return res.status(401).json({error:'Your Cloudflare Access session could not be verified. Reload the app and sign in again.'});
    req.deleteSubject=subject;next();
  }
  function available(res){
    if(busy||hasActiveJobs()){res.status(409).json({error:'Wait for active downloads or library operations to finish before deleting'});return false;}
    return true;
  }
  app.post('/api/library/delete/preview',protect,async(req,res)=>{
    if(!available(res))return;
    try{
      const result=await operate(musicDir,{path:req.body.path,kind:req.body.kind,operation:'preview'});
      if(!result.ok)return res.status(409).json(result);
      for(const [key,value] of tickets)if(value.expires<now())tickets.delete(key);
      if(tickets.size>=200)tickets.delete(tickets.keys().next().value);
      const token=crypto.randomBytes(32).toString('base64url');
      tickets.set(token,{...result,subject:req.deleteSubject,expires:now()+120000});
      const {fingerprint,...summary}=result;res.json({...summary,token,permanent:true});
    }catch{res.status(503).json({error:'Could not review this deletion. Refresh and try again.'});}
  });
  app.post('/api/library/delete',protect,async(req,res)=>{
    const token=typeof req.body.token==='string'?req.body.token:'',ticket=tickets.get(token);
    if(req.body.confirmed!==true||!ticket||ticket.expires<now()||ticket.subject!==req.deleteSubject)return res.status(409).json({error:'A fresh deletion confirmation is required'});
    tickets.delete(token);
    if(!available(res))return;
    busy=true;
    try{
      const result=await operate(musicDir,{path:ticket.path,kind:ticket.kind,fingerprint:ticket.fingerprint,operation:'delete'});
      if(result.ok||result.deletedFiles>0)onDeleted(ticket.path);res.status(result.ok?200:409).json(result);
    }catch{onDeleted(ticket.path);res.status(503).json({error:'Deletion was interrupted. Refresh the library before trying again.'});}
    finally{busy=false;}
  });
  return ()=>busy;
}
module.exports={installDeleteRoutes,runOperation};
