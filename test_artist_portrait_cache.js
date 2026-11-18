const assert=require('node:assert/strict'),fs=require('fs'),os=require('os'),path=require('path');
const {createPortraitCache,jpeg}=require('./artist-portrait-cache');
// Bounded JPEG framing fixture; network responses are mocked, never remote.
const image=Buffer.from([255,216,255,192,0,11,8,0,1,0,1,1,1,17,0,255,217]);
const url='https://is1-ssl.mzstatic.com/image/thumb/AMCArtistImages211/v4/example/600x600bb.jpg';
const html=`<meta property="og:type" content="music.musician"><meta property="og:image" content="${url}">`;
(async()=>{
 assert(jpeg(image));assert(!jpeg(Buffer.from('not jpeg')));
 const root=fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(),'artist-cache-'))),music=path.join(root,'music'),data=path.join(root,'data');fs.mkdirSync(music);
 const folder=name=>{const dir=path.join(music,name);fs.mkdirSync(dir);return dir;};
 let calls=0,identities=0,time=100000,fail=false,hold=null;
 const fetchImpl=async u=>{calls++;if(hold)await hold;if(fail)throw Error('offline');if(u.startsWith('https://music.apple.com'))return{ok:true,url:u,text:async()=>html};return{ok:true,headers:new Headers({'content-type':'image/jpeg','content-length':String(image.length)}),body:new Response(image).body};};
 const opts={musicDir:music,dataDir:data,fetchImpl,validateImage:async()=>true,resolveIdentity:async()=>{identities++;return '123';},now:()=>time,refreshMs:100,retryMs:30};
 try{
  const artist=folder('Artist'),cache=createPortraitCache(opts);
  const [a,b]=await Promise.all([cache.library('Artist'),cache.library('Artist')]);assert.equal(a,b);assert.equal(calls,2);assert.equal(identities,1);assert(fs.existsSync(a));
  const restarted=createPortraitCache(opts);assert.equal(await restarted.library('Artist'),a);assert.equal(calls,2);
  let release;hold=new Promise(r=>release=r);time+=101;
  assert.equal(await restarted.library('Artist'),a);assert.equal(fs.readFileSync(a).compare(image),0);release();hold=null;await restarted.waitForIdle();
  time+=101;fail=true;assert.equal(await restarted.library('Artist'),a);await restarted.waitForIdle();assert(fs.existsSync(a));fail=false;
  // Mixed identity after an owned portrait becomes generic without deleting bytes.
  const changing=folder('Changing');let artistIdentity='333';
  const changed=createPortraitCache({...opts,resolveIdentity:async()=>artistIdentity});
  const oldPortrait=await changed.library('Changing');assert(oldPortrait);artistIdentity=null;time+=101;
  assert.equal(await changed.library('Changing'),oldPortrait);await changed.waitForIdle();
  assert.equal(await changed.library('Changing'),null);assert(fs.existsSync(oldPortrait));
  const user=folder('User');fs.writeFileSync(path.join(user,'.artist.jpg'),image);const n=calls;assert.equal(await cache.library('User'),path.join(user,'.artist.jpg'));assert.equal(calls,n);assert(!fs.existsSync(path.join(user,'.artist.json')));
  const symlink=folder('Symlink');fs.symlinkSync(path.join(user,'.artist.jpg'),path.join(symlink,'.artist.jpg'));assert.equal(await cache.library('Symlink'),null);assert(fs.lstatSync(path.join(symlink,'.artist.jpg')).isSymbolicLink());
  assert.equal(await cache.library('../Artist'),null);assert.equal(await cache.library('Compilations'),null);assert.equal(await cache.catalogue('../bad'),null);
  const catalogue=await cache.catalogue('456');assert(catalogue.startsWith(data));assert.equal(await cache.catalogue('456'),catalogue);
  const mixed=folder('Mixed'),negative=createPortraitCache({...opts,resolveIdentity:async()=>null});assert.equal(await negative.library('Mixed'),null);assert.equal(JSON.parse(fs.readFileSync(path.join(mixed,'.artist.json'))).artistId,null);
  const gone=folder('Gone');let go;const waiting=new Promise(r=>go=r);const removing=createPortraitCache({...opts,resolveIdentity:async()=>{await waiting;return '789';}});const work=removing.library('Gone');await new Promise(r=>setTimeout(r,20));fs.rmSync(gone,{recursive:true});go();assert.equal(await work,null);assert(!fs.existsSync(gone));
  // An owned cache whose image was replaced by a symlink is not overwritten.
  fs.unlinkSync(a);fs.symlinkSync(path.join(user,'.artist.jpg'),a);time+=1000;assert.equal(await cache.library('Artist'),null);assert(fs.lstatSync(a).isSymbolicLink());
  console.log('Persistent portraits: cold/warm/restart, background refresh, failures, ownership, symlinks, traversal, compilations, catalogue, negative cache and deleted folder passed');
 }finally{fs.rmSync(root,{recursive:true,force:true});}
})().catch(e=>{console.error(e);process.exitCode=1;});
