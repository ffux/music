const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
const html=fs.readFileSync(process.argv[2]||'public/index.html','utf8'),script=html.match(/<script>([\s\S]*)<\/script>/)[1];
new vm.Script(script);
const elements=new Map(),listeners=new Map();
function element(id){if(!elements.has(id))elements.set(id,{id,value:'',hidden:false,textContent:'',innerHTML:'',style:{setProperty(){}},dataset:{},src:'',currentTime:0,offsetHeight:200,classList:{add(){},remove(){},toggle(){}},setAttribute(k,v){this[k]=v},getAttribute(k){return this[k]},removeAttribute(k){delete this[k]},addEventListener(event,fn){listeners.set(id+':'+event,fn)},querySelectorAll(){return[]},querySelector(){return null},insertAdjacentHTML(where,text){this.innerHTML+=text},play(){return Promise.resolve()},pause(){},load(){},focus(){},contains(){return false}});return elements.get(id)}
const doc={getElementById:element,querySelector:element,querySelectorAll(){return[]},addEventListener(){},documentElement:{style:{setProperty(){}}}};
let fetches=[]; const timers=new Map(); let timerId=0;
const context=vm.createContext({console,document:doc,window:{addEventListener(){},innerHeight:900,innerWidth:1200,visualViewport:null},localStorage:{getItem(){return null}},requestAnimationFrame(){return 1},cancelAnimationFrame(){},setTimeout(fn){const id=++timerId;timers.set(id,fn);return id},clearTimeout(id){timers.delete(id)},URL,fetch:async(url)=>{fetches.push(url);throw Error('Unexpected network call '+url)}});
vm.runInContext(script.slice(0,script.indexOf('// Init\n')),context);
const evaluate=source=>vm.runInContext(source,context);
const data=[{type:'dir',name:'Remi Wolf',path:'Remi Wolf',children:[{type:'dir',name:"You're A Dog! - EP",path:"Remi Wolf/You're A Dog! - EP",children:[{type:'file',name:'01 Sauce.m4a',path:"Remi Wolf/You're A Dog! - EP/01 Sauce.m4a",fidelity:{songId:1,albumId:10,artistId:100,title:'Sauce',artist:'Remi Wolf',codec:'ALAC',sampleRate:44100,bitDepth:24,duration:230}},{type:'file',name:'03 Doctor.m4a',path:"Remi Wolf/You're A Dog! - EP/03 Doctor.m4a",fidelity:{songId:2,albumId:10,artistId:100,title:'Doctor',artist:'Remi Wolf',codec:'ALAC',sampleRate:44100,bitDepth:24,duration:170}},{type:'file',name:'04 Guy.m4a',path:"Remi Wolf/You're A Dog! - EP/04 Guy.m4a",fidelity:{songId:3,albumId:10,artistId:100,title:'Guy',artist:'Remi Wolf',codec:'AAC',sampleRate:44100,duration:163}}]}]}];
context.fixture=data;evaluate('state.libraryData=fixture;state.libraryIndexReady=true;state.albumMetadata[fixture[0].children[0].path]={tracks:{},album:{}}');
const tracks=data[0].children[0].children;context.tracks=tracks; const originalFidelity=tracks.map(track=>({...track.fidelity}));
assert.equal(evaluate('libraryPresence({resultType:"song",trackId:1}).complete'),true);
assert.equal(evaluate('libraryPresence({resultType:"album",collectionId:10,trackCount:6}).complete'),false);
assert.match(evaluate('libraryPresence({resultType:"album",collectionId:10,trackCount:6}).label'),/3 of 6/);
assert.equal(evaluate('libraryPresence({resultType:"album",collectionId:10,trackCount:3}).complete'),true);
assert.equal(evaluate('libraryPresence({resultType:"song",trackId:999,trackName:"New song",artistName:"Someone else"}).complete'),false);
assert.equal(evaluate('libraryPresence({resultType:"song",trackId:999,trackName:"Guy",artistName:"Remi Wolf"}).alternate'),true);
evaluate('startPlaybackQueue(tracks,1,false)');assert.equal(evaluate('state.playIndex'),1);assert.equal(evaluate('state.currentTrack.fidelity.title'),'Doctor');
evaluate('moveQueue(1,true)');assert.equal(evaluate('state.currentTrack.fidelity.title'),'Guy');
evaluate('state.repeat="all";moveQueue(1,true)');assert.equal(evaluate('state.currentTrack.fidelity.title'),'Sauce');
evaluate('state.repeat="one";moveQueue(1,true)');assert.equal(evaluate('state.currentTrack.fidelity.title'),'Sauce');
evaluate('state.repeat="off";enqueueTracks([tracks[2]],true)');assert.equal(evaluate('state.playQueue[1].fidelity.title'),'Guy');assert.equal(evaluate('new Set(state.playQueue.map(item=>item.queueId)).size'),4);
const before=JSON.stringify(Array.from(evaluate('state.playQueue.map(item=>item.queueId)')));listeners.get('player-shuffle:click')();assert.equal(evaluate('state.shuffle'),true);listeners.get('player-shuffle:click')();assert.equal(evaluate('state.shuffle'),false);assert.equal(JSON.stringify(Array.from(evaluate('state.playQueue.map(item=>item.queueId)'))),before);
assert.equal(tracks.length,3);
(async()=>{
  element('search-input').value='Remi Wolf';await evaluate('doLocalSearch()');assert.deepEqual(fetches,[]);assert.match(element('library-content').innerHTML,/Artists/);assert.match(element('library-content').innerHTML,/Search Apple Music/);
  element('search-input').value='No Such Song';await evaluate('doLocalSearch()');assert.deepEqual(fetches,[]);assert.match(element('library-content').innerHTML,/Nothing found in your library/);
  // Typing coalesces locally; clearing and navigation invalidate pending work.
  timers.clear(); element('search-panel').hidden=false;
  for(const query of ['R','Re','Remi']) {element('search-input').value=query; listeners.get('search-input:input')({});}
  assert.equal(timers.size,1); [...timers.values()][0](); timers.clear();
  assert.match(element('library-subtitle').textContent,/Remi/); assert.deepEqual(fetches,[]);
  element('search-input').value='No Such Song'; listeners.get('search-input:input')({});
  const staleTyping=[...timers.values()][0];
  element('search-input').value=''; listeners.get('search-input:input')({});
  assert.equal(timers.size,0); staleTyping(); assert.match(element('library-content').innerHTML,/Find artists/);
  element('search-input').value='Remi'; listeners.get('search-input:input')({});
  const beforeNavigation=element('library-content').innerHTML; evaluate('state.searchRequestId++;');
  [...timers.values()][0](); timers.clear(); assert.equal(element('library-content').innerHTML,beforeNavigation);
  // An older asynchronous Apple response cannot replace a newly typed local query.
  let finishApple; context.fetch=()=>new Promise(resolve=>{finishApple=resolve});
  element('search-input').value='old'; const pendingApple=evaluate('doAppleSearch()');
  element('search-input').value='Remi'; listeners.get('search-input:input')({});
  [...timers.values()][0](); timers.clear();
  finishApple({ok:true,json:async()=>({results:[{trackName:'STALE APPLE RESULT'}]})}); await pendingApple;
  assert(!element('library-content').innerHTML.includes('STALE APPLE RESULT')); assert.match(element('library-subtitle').textContent,/Remi/);
  // Clearing while local quality metadata is in flight keeps the empty screen.
  evaluate('delete state.albumMetadata[fixture[0].children[0].path]');
  let finishMetadata; context.fetch=()=>new Promise(resolve=>{finishMetadata=resolve});
  element('search-input').value='Remi'; const pendingLocal=evaluate('doLocalSearch()');
  element('search-input').value=''; listeners.get('search-input:input')({});
  finishMetadata({ok:true,json:async()=>({tracks:{},album:{}})}); await pendingLocal;
  assert.match(element('library-content').innerHTML,/Find artists/);
  tracks.forEach((track,index)=>{track.fidelity=originalFidelity[index]});
  assert(!html.includes('New downloads prefer the highest available ALAC'));
  assert(html.includes('id="search-panel" hidden'));
  assert.equal(evaluate('formatTime(230)'),'3:50');
  assert.equal(evaluate('formatFidelity(tracks[0])'),'24-bit/44.1 kHz ALAC');
  assert.equal(evaluate('formatFidelity(tracks[2])'),'44.1 kHz AAC');
  // Device downloads are secondary menu actions; server saves stay primary.
  context.capturedActions=[];context.downloadCalls=[];
  evaluate('openMoreMenu=(anchor,actions)=>{capturedActions=actions};requestClientDownload=(...args)=>downloadCalls.push(args)');
  for(const [node,kind] of [[tracks[0],'song'],[data[0].children[0],'album'],[data[0],'artist']]){
    context.menuNode=node;evaluate('localMore({id:"test-more"},menuNode)');
    const action=context.capturedActions.find(action=>action.label.includes('to this device'));assert(action);await action.run();
    assert.equal(context.downloadCalls.at(-1)[0],node.path);assert.equal(context.downloadCalls.at(-1)[1],kind);
  }
  assert.equal(evaluate('saveButtonHtml({resultType:"song",trackId:1},0)'), '');
  assert.equal(evaluate('saveButtonHtml({resultType:"album",collectionId:10,trackCount:3},0)'), '');
  assert.match(evaluate('saveButtonHtml({resultType:"album",collectionId:10,trackCount:6},0)'), /Save missing songs to server/);
  assert.match(evaluate('saveButtonHtml({resultType:"song",trackId:999,trackName:"Missing",artistName:"Other"},0)'), /Save song to server/);
  assert(!html.includes('class="track-dl client-download"'));assert(!html.includes('class="track-dl album-download"'));assert(!html.includes('class="track-dl artist-download"'));assert(!html.includes('class="track-dl catalog-device"'));
  assert.equal(evaluate('catalogueArtwork({resultType:"artist",artistId:100})'),'/api/artist-artwork?id=100');
  assert.equal(evaluate('catalogueArtwork({resultType:"artist",artistId:"bad"})'),null);
  // Mobile presentation observes and controls the same audio element.
  element('player').paused=true; element('player').duration=230; element('player').currentTime=30;
  evaluate('syncMobilePlayer()');assert.equal(element('mobile-play-pause')['aria-label'],'Play');assert.equal(element('mobile-seek').max,'230');assert.equal(element('mobile-elapsed').textContent,'0:30');
  listeners.get('mobile-seek:change')({target:{value:'999'}});assert.equal(element('player').currentTime,230);
  assert.equal(element('desktop-seek').max,'230');assert.equal(element('desktop-seek').value,'30');
  listeners.get('desktop-seek:change')({target:{value:'42'}});assert.equal(element('player').currentTime,42);
  listeners.get('desktop-volume:input')({target:{value:'0.4'}});assert.equal(element('player').volume,0.4);assert.equal(element('player').muted,false);
  element('player').muted=true;listeners.get('player:volumechange')();assert.equal(element('desktop-volume').value,'0');
  element('player').paused=false;evaluate('syncMobilePlayer()');assert.equal(element('mini-play-pause')['aria-label'],'Pause');
  evaluate('openMobilePlayer()');assert.equal(element('mobile-now-playing').hidden,false);listeners.get('mobile-player-collapse:click')();assert.equal(element('mobile-now-playing').hidden,true);
  assert.match(html,/role="dialog" aria-modal="true" aria-labelledby="mobile-now-title"/);
  evaluate('showRoot("library")');assert.equal(evaluate('state.libraryView.level'),'hub');assert.match(element('library-content').innerHTML,/data-library-shortcut="artists"/);assert.match(element('library-content').innerHTML,/Recently Added/);
  assert(!html.includes('id="mobile-player-open"'));assert.equal((html.match(/data-mobile-destination=/g)||[]).length,3);
  context.window.matchMedia=()=>({matches:true});evaluate('configureMobileSummary()');
  evaluate('closeMobilePlayer()');listeners.get('player-bar:click')({target:{closest:()=>({})}});assert.equal(element('mobile-now-playing').hidden,true);
  listeners.get('player-bar:click')({target:{closest:()=>null}});assert.equal(element('mobile-now-playing').hidden,false);
  evaluate('closeMobilePlayer()');let prevented=false;listeners.get('mobile-player-summary:keydown')({target:element('mobile-player-summary'),key:'Enter',preventDefault(){prevented=true}});assert(prevented);assert.equal(element('mobile-now-playing').hidden,false);
  // Every delete attempt gets a new explicit confirmation, independent of device-download preferences.
  let confirmations=0,deletePosts=0;context.window.confirm=message=>{confirmations++;assert.match(message,/Permanently removes/);assert.match(message,/cannot be undone/);assert.match(message,/01 Sauce.m4a/);return false;};
  context.fetch=async(url,options)=>{assert.equal(url,'/api/library/delete/preview');deletePosts++;assert.equal(options.headers['X-Music-Action'],'delete');return{ok:true,json:async()=>({name:'01 Sauce.m4a',path:tracks[0].path,kind:'song',songs:1,files:1,token:'fixture-preview'})}};
  await evaluate('deleteFromServer(tracks[0])');await evaluate('deleteFromServer(tracks[0])');assert.equal(confirmations,2);assert.equal(deletePosts,2);
  evaluate('startPlaybackQueue(tracks,0,false)');const survivorId=evaluate('state.playQueue[2].queueId');
  evaluate('applyDeletedScope(tracks[0].path)');assert.equal(evaluate('state.currentTrack'),null);assert.equal(evaluate('state.playQueue.length'),2);assert.equal(evaluate('state.playIndex'),-1);assert.equal(evaluate('state.playQueue[1].queueId'),survivorId);
  evaluate('startPlaybackQueue(tracks,0,false);applyDeletedScope(tracks[2].path)');assert.equal(evaluate('state.currentTrack.path'),tracks[0].path);assert.equal(evaluate('state.playIndex'),0);assert.equal(evaluate('state.playQueue.length'),2);
  evaluate('applyDeletedScope(fixture[0].path)');assert.equal(evaluate('state.playQueue.length'),0);assert.equal(evaluate('state.currentTrack'),null);
  // Search-card download controls are separate from navigation and queue once.
  const downloadCases=[
    [{resultType:'album',collectionId:900,collectionName:'Album',trackCount:5},'https://music.apple.com/us/album/900'],
    [{resultType:'artist',artistId:901,artistName:'Artist'},'https://music.apple.com/us/artist/901'],
    [{resultType:'song',trackId:902,collectionId:900,trackName:'Song'},'https://music.apple.com/us/album/900?i=902'],
  ];
  let queueRequests=0;
  for(const [item,url] of downloadCases){
    context.queueItem=item;const card=evaluate('resultCardHtml(queueItem,0)');
    assert.match(card,/card-save-action/);assert.match(card,/catalog-save/);
    assert(!card.slice(card.indexOf('<button class="catalogue-open"'),card.indexOf('</button>')).includes('catalog-save'));
    const button=element('save-'+queueRequests);button.disabled=false;context.queueButton=button;
    let stopped=0;context.queueEvent={preventDefault(){stopped++;},stopPropagation(){stopped++;}};
    context.fetch=async(target,options)=>{assert.equal(target,'/api/queue');assert.equal(JSON.parse(options.body).url,url);queueRequests++;return{ok:true,json:async()=>({id:1000+queueRequests})};};
    await evaluate('saveCatalogueItem(queueItem,queueButton,queueEvent)');assert.equal(stopped,2);assert.equal(button.disabled,true);
    assert.match(evaluate('resultCardHtml(queueItem,0)'),/Queued for server/);
  }
  context.queueItem={resultType:'album',collectionId:9999};context.queueButton=element('pending-save');context.queueButton.disabled=false;
  let finishSave;context.fetch=()=>{queueRequests++;return new Promise(resolve=>{finishSave=resolve;});};
  const pendingSave=evaluate('saveCatalogueItem(queueItem,queueButton)');const beforeDuplicate=queueRequests;
  context.otherButton=element('rerendered-save');context.otherButton.disabled=false;
  await evaluate('saveCatalogueItem(queueItem,otherButton)');assert.equal(queueRequests,beforeDuplicate);
  assert.match(evaluate('saveButtonHtml(queueItem,0)'),/Queued for server/);
  context.queueButton.isConnected=false;context.rerenders=0;
  evaluate('state.searchActive=true;state.searchScope="apple";var originalCatalogueRender=renderCatalogue;renderCatalogue=()=>{rerenders++}');
  finishSave({ok:false,json:async()=>({error:'fixture rejection'})});await pendingSave;assert.equal(context.queueButton.disabled,false);assert.equal(context.rerenders,1);
  evaluate('renderCatalogue=originalCatalogueRender');context.queueButton.isConnected=true;
  context.fetch=async()=>({ok:true,json:async()=>({id:2000})});await evaluate('saveCatalogueItem(queueItem,queueButton)');assert.equal(context.queueButton.disabled,true);
  assert(!html.includes('separate from Download History'));
  evaluate('startPlaybackQueue(tracks,0,false)');
  assert(element('playback-list').innerHTML.includes('<h3>Now Playing</h3><div class="queue-item queue-now">'));
  assert(element('playback-list').innerHTML.includes('Remi Wolf'));
  assert(html.includes('#clear-upcoming { margin-top: 24px; }'));
  assert(!html.includes('Albums and songs ready to stream or download. Retained originals are not counted twice.'));
  assert(!html.includes('Free space available for downloads on the music storage drive (GB).'));
  // Welcome totals use the API-visible library (retained ALAC originals are filtered server-side).
  context.statsFixture=[{type:'dir',path:'Artist',children:[{type:'dir',path:'Artist/Album',children:[{type:'file',path:'Artist/Album/a.flac',size:1500000000},{type:'file',path:'Artist/Album/b.m4a',size:500000000}]}]}];
  assert.equal(JSON.stringify(evaluate('welcomeTotals(statsFixture)')),JSON.stringify({albums:1,songs:2,bytes:2000000000}));
  assert.equal(evaluate('welcomeTotals([]).songs'),0);
  assert.equal(evaluate('welcomeTotals([...statsFixture,...statsFixture]).bytes'),2000000000);
  const preferences=new Map();context.localStorage={getItem:k=>preferences.get(k),setItem:(k,v)=>preferences.set(k,v),removeItem:k=>preferences.delete(k)};
  const welcome=element('welcome-dialog');welcome.open=false;welcome.showModal=()=>welcome.open=true;welcome.close=()=>{welcome.open=false;listeners.get('welcome-dialog:close')();};
  evaluate('showWelcome()');assert.equal(welcome.open,true);listeners.get('welcome-start:click')();assert.equal(welcome.open,false);
  evaluate('showWelcome()');assert.equal(welcome.open,false);
  preferences.set('music-client-download-confirmed-v1','yes');listeners.get('reset-download-confirmation:click')();
  assert.equal(preferences.has('music-client-download-confirmed-v1'),false);assert.equal(welcome.open,true);
  // No title bar or Recently Added count; utilities remain available on mobile.
  assert(!html.includes('<header>'));assert(!html.includes('id="library-home"'));
  assert(!html.includes('Sorted by latest file date'));
  evaluate('state.libraryData=fixture;showRoot("recent")');assert.equal(element('library-subtitle').textContent,'');
  evaluate('showRoot("library")');assert.match(element('library-content').innerHTML,/data-mobile-drawer="downloads"/);assert.match(element('library-content').innerHTML,/data-mobile-drawer="settings"/);
  assert(html.indexOf('id="downloads-toggle"')>html.indexOf('aria-label="Library"'));
  assert(html.indexOf('id="settings-toggle"')<html.indexOf('</aside>'));
  console.log('Search locality, edition-aware status, partial albums, album continuation, queue insertion, repeat, shuffle restoration, quality labels and policy-text removal passed');
})().catch(error=>{console.error(error);process.exitCode=1});
