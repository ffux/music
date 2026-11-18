// Persistent artist-only JPEGs. Never overwrite artwork not owned by this cache.
const fs=require('fs');
const fsp=fs.promises;
const path=require('path');
const crypto=require('crypto');
const {execFile,spawn}=require('child_process');
const {promisify}=require('util');
const {createArtistArtwork}=require('./artist-artwork');
const exec=promisify(execFile);
const OWNER='music-artist-portrait-v1',WEEK=7*86400000,RETRY=6*3600000,MAX_IMAGE=3*1024*1024;
const digest=b=>crypto.createHash('sha256').update(b).digest('hex');
const validId=id=>/^\d{1,20}$/.test(String(id));
function jpeg(buffer) {
  if(buffer.length<12||buffer.length>MAX_IMAGE||buffer[0]!==255||buffer[1]!==216||buffer[buffer.length-2]!==255||buffer[buffer.length-1]!==217)return false;
  // Require a bounded JPEG frame, not only an advertised MIME type.
  let p=2;
  while(p+4<=buffer.length){
    if(buffer[p++]!==255)return false;
    while(buffer[p]===255)p++;
    const marker=buffer[p++];
    if(marker===0xda||marker===0xd9)return false;
    const size=buffer.readUInt16BE(p);
    if(size<2||p+size>buffer.length)return false;
    if([0xc0,0xc1,0xc2].includes(marker)){
      if(size<8)return false;
      const h=buffer.readUInt16BE(p+3),w=buffer.readUInt16BE(p+5);
      return w>0&&h>0&&w<=4096&&h<=4096;
    }
    p+=size;
  }
  return false;
}
async function decodeJpeg(bytes) {
  return new Promise(resolve=>{
    const child=spawn('ffmpeg',['-v','error','-xerror','-nostdin','-i','pipe:0','-frames:v','1','-f','null','-'],{stdio:['pipe','ignore','ignore']});
    let finished=false;
    const finish=ok=>{if(finished)return;finished=true;clearTimeout(timer);resolve(ok);};
    const timer=setTimeout(()=>{child.kill('SIGKILL');finish(false);},5000);
    child.on('error',()=>finish(false));child.on('close',code=>finish(code===0));
    child.stdin.on('error',()=>{});child.stdin.end(bytes);
  });
}
async function regular(file,max) {
  try{const s=await fsp.lstat(file);if(!s.isFile()||s.isSymbolicLink()||s.size>max)return null;return await fsp.readFile(file);}catch{return null;}
}
async function identity(folder){
  const {stdout}=await exec('python3',[path.join(__dirname,'artist_identity.py'),folder],{timeout:15000,maxBuffer:65536});
  const id=JSON.parse(stdout).artistId;return validId(id)?String(id):null;
}
function createPortraitCache({musicDir,dataDir,fetchImpl=fetch,resolveIdentity=identity,validateImage=decodeJpeg,now=Date.now,refreshMs=WEEK,retryMs=RETRY}={}) {
  const musicRoot=fs.realpathSync(musicDir),dataRoot=path.resolve(dataDir);
  const lookup=createArtistArtwork(fetchImpl),pending=new Map(),waiting=[],blocked=new Map();let active=0;
  async function context(dir){
    const stat=await fsp.lstat(dir);if(!stat.isDirectory()||stat.isSymbolicLink())throw Error('Not a regular folder');
    if(await fsp.realpath(dir)!==dir)throw Error('Symlink folder');
    return{dir,ino:stat.ino,dev:stat.dev,image:path.join(dir,'.artist.jpg'),meta:path.join(dir,'.artist.json')};
  }
  async function unchangedDir(c){try{const x=await context(c.dir);return x.ino===c.ino&&x.dev===c.dev;}catch{return false;}}
  async function read(c){
    const [image,raw]=await Promise.all([regular(c.image,MAX_IMAGE),regular(c.meta,16384)]);
    let meta=null;try{meta=JSON.parse(raw);}catch{}
    const imageValid=image&&jpeg(image);
    let imageExists=false,metaExists=false;
    try{await fsp.lstat(c.image);imageExists=true;}catch{}
    try{await fsp.lstat(c.meta);metaExists=true;}catch{}
    const owned=meta?.owner===OWNER&&(!imageExists||(imageValid&&meta.imageSha256===digest(image)));
    return{image:imageValid?image:null,raw,meta,owned,foreign:(imageExists||metaExists)&&!owned};
  }
  async function atomic(file,bytes,replace){
    const temp=path.join(path.dirname(file),`.artist-tmp-${crypto.randomUUID()}`);
    try{const h=await fsp.open(temp,'wx');try{await h.writeFile(bytes);await h.sync();}finally{await h.close();}
      if(replace)await fsp.rename(temp,file);else await fsp.link(temp,file);
    }finally{await fsp.unlink(temp).catch(()=>{});}
  }
  async function save(c,prior,meta,image){
    if(!await unchangedDir(c))return false;
    const current=await read(c);
    if(current.foreign||String(current.raw)!==String(prior.raw)||digest(current.image||Buffer.alloc(0))!==digest(prior.image||Buffer.alloc(0)))return false;
    // Recheck immediately before every write; never mkdir a deleted music folder.
    if(image){if(!await unchangedDir(c))return false;await atomic(c.image,image,!!prior.image);meta.imageSha256=digest(image);}
    if(!await unchangedDir(c))return false;
    await atomic(c.meta,Buffer.from(JSON.stringify(meta)),!!prior.raw);
    return true;
  }
  async function download(url){
    const u=new URL(url);
    if(u.protocol!=='https:'||!/^is\d+-ssl\.mzstatic\.com$/.test(u.hostname)||!u.pathname.includes('/AMCArtistImages')||u.username||u.password)return null;
    const response=await fetchImpl(u.href,{signal:AbortSignal.timeout(12000),redirect:'error'});
    if(!response.ok||!/^image\/jpeg(?:;|$)/i.test(response.headers.get('content-type')||'')||Number(response.headers.get('content-length')||0)>MAX_IMAGE)return null;
    const chunks=[];let size=0;
    for await(const chunk of response.body){size+=chunk.length;if(size>MAX_IMAGE){await response.body.cancel?.().catch(()=>{});return null;}chunks.push(chunk);}
    const bytes=Buffer.concat(chunks);return jpeg(bytes)&&await validateImage(bytes)?bytes:null;
  }
  async function refresh(c,prior,id){
    let artistId=id;
    try{
      if(!artistId)artistId=await resolveIdentity(c.dir);
      if(!validId(artistId)){
        // Ambiguous/compilation folders must never acquire an arbitrary portrait.
        await save(c,prior,{owner:OWNER,artistId:null,disabled:true,imageSha256:prior.meta?.imageSha256||null,checkedAt:now(),nextCheck:now()+retryMs},null);
        return null;
      }
      artistId=String(artistId);
      const url=await lookup(artistId),image=url?await download(url):null;
      const meta={owner:OWNER,artistId,checkedAt:now(),nextCheck:now()+(image?refreshMs:retryMs),imageSha256:prior.meta?.imageSha256||null,lastSuccess:prior.meta?.lastSuccess||null};
      if(image){meta.sourceUrl=url;meta.lastSuccess=now();}
      else if(prior.meta?.sourceUrl)meta.sourceUrl=prior.meta.sourceUrl;
      if(await save(c,prior,meta,image))return image||prior.image?c.image:null;
    }catch{if(blocked.size>=512)blocked.delete(blocked.keys().next().value);blocked.set(c.dir,now()+retryMs);}
    return prior.image?c.image:null;
  }
  function schedule(c,prior,id){
    if(pending.has(c.dir))return pending.get(c.dir);
    if(waiting.length>=40)return Promise.resolve(prior.image?c.image:null);
    const task=(async()=>{if(active>=4)await new Promise(r=>waiting.push(r));active++;try{return await refresh(c,prior,id);}finally{active--;waiting.shift()?.();}})();
    pending.set(c.dir,task);task.finally(()=>pending.delete(c.dir));return task;
  }
  async function get(c,id){
    const prior=await read(c);
    if(prior.foreign)return prior.image?c.image:null;
    if((blocked.get(c.dir)||0)>now()||(prior.meta?.nextCheck||0)>now())return prior.image&&!prior.meta?.disabled?c.image:null;
    const task=schedule(c,prior,id);
    if(prior.image){task.catch(()=>{});return prior.meta?.disabled?null:c.image;}
    return task;
  }
  return{
    async library(folder){
      if(typeof folder!=='string'||!folder||folder.startsWith('.')||path.basename(folder)!==folder||folder.includes('\\')||['compilations','various artists'].includes(folder.toLowerCase()))return null;
      try{return await get(await context(path.join(musicRoot,folder)),null);}catch{return null;}
    },
    async catalogue(id){
      if(!validId(id))return null;
      try{await fsp.mkdir(dataRoot,{recursive:true});const catalogueRoot=path.join(await fsp.realpath(dataRoot),'artist-portraits');await fsp.mkdir(catalogueRoot,{recursive:true});if(await fsp.realpath(catalogueRoot)!==catalogueRoot)return null;const dir=path.join(catalogueRoot,String(id));await fsp.mkdir(dir,{recursive:true});return await get(await context(dir),String(id));}catch{return null;}
    },
    async waitForIdle(){while(pending.size)await Promise.allSettled([...pending.values()]);},
  };
}
module.exports={createPortraitCache,jpeg,decodeJpeg};
