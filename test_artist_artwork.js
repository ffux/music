const assert=require('node:assert/strict');
const {portraitFromHtml,createArtistArtwork}=require('./artist-artwork');
const html=(url,type='music.musician')=>`<meta property="og:type" content="${type}"><meta property="og:image" content="${url}">`;
const url='https://is1-ssl.mzstatic.com/image/thumb/AMCArtistImages221/v4/test/portrait.png/1200x630cw.png';
(async()=>{
 assert.match(portraitFromHtml(html(url)),/600x600bb.jpg$/);
 for(const value of [html(url,'music.album'),html(url.replace('AMCArtistImages221','Music221')),html(url.replace('is1-ssl.mzstatic.com','attacker.test')),'<html>No portrait</html>'])assert.equal(portraitFromHtml(value),null);
 let calls=0;const lookup=createArtistArtwork(async u=>{calls++;return{ok:true,url:u,text:async()=>html(url)}});
 assert((await lookup('1223869670')).includes('AMCArtistImages')); await lookup('1223869670');assert.equal(calls,1);assert.equal(await lookup('../bad'),null);assert.equal(calls,1);
 assert.equal(await createArtistArtwork(async()=>{throw Error('network')})('1'),null);
 let active=0,maximum=0;const release=[];
 const limited=createArtistArtwork(async u=>{active++;maximum=Math.max(maximum,active);await new Promise(resolve=>release.push(resolve));active--;return{ok:true,url:u,text:async()=>html(url)}});
 const batch=Promise.all(Array.from({length:8},(_,index)=>limited(String(index+100))));
 for(let wave=0;wave<2;wave++){await new Promise(resolve=>setImmediate(resolve));const pending=release.splice(0);pending.forEach(resolve=>resolve());}
 await batch;assert.equal(maximum,4);
 console.log('Artist artwork: verified portrait path, album/foreign rejection, caching, input validation and graceful failures passed');
})();
