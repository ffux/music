// Only Apple's explicit artist portrait metadata is accepted, never album artwork.
function portraitFromHtml(html) {
  const metadata = new Map();
  for (const tag of html.matchAll(/<meta\s[^>]*>/gi)) {
    const attributes = new Map([...tag[0].matchAll(/([\w:-]+)\s*=\s*(["'])(.*?)\2/gs)].map(match=>[match[1].toLowerCase(),match[3]]));
    metadata.set(attributes.get('property'),attributes.get('content'));
  }
  if (metadata.get('og:type') !== 'music.musician') return null;
  try {
    const url = new URL((metadata.get('og:image') || '').replace(/&amp;/g,'&'));
    if(url.protocol!=='https:' || !/^is\d+-ssl\.mzstatic\.com$/.test(url.hostname) || !/\/AMCArtistImages\d*\//.test(url.pathname) || url.username || url.password) return null;
    url.pathname = url.pathname.replace(/\/\d+x\d+[^/]*\.(?:png|jpg|webp)$/,'/600x600bb.jpg');
    return url.href;
  } catch { return null; }
}
function createArtistArtwork(fetchImpl=fetch) {
  const cache=new Map(),pending=new Map(); let active=0; const waiting=[];
  return async function artwork(id) {
    if(!/^\d{1,20}$/.test(String(id)))return null;
    const hit=cache.get(id); if(hit && hit.until>Date.now())return hit.url;
    if(pending.has(id))return pending.get(id);
    if(waiting.length>=40)return null;
    const task=(async()=>{
      if(active>=4)await new Promise(resolve=>waiting.push(resolve));
      active++;
      let url=null;
      try {
        const response=await fetchImpl(`https://music.apple.com/us/artist/${id}`,{signal:AbortSignal.timeout(12000),redirect:'follow'});
        if(response.ok && new URL(response.url).hostname==='music.apple.com')url=portraitFromHtml(await response.text());
      } catch { /* Missing portraits retain the neutral browser placeholder. */ }
      if(cache.size>=300)cache.delete(cache.keys().next().value);
      cache.set(id,{url,until:Date.now()+(url?86400000:300000)});
      return url;
    })();
    pending.set(id,task);
    try{return await task;}finally{pending.delete(id);active--;waiting.shift()?.();}
  };
}
module.exports={portraitFromHtml,createArtistArtwork};
