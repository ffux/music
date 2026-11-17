const fs = require('fs'),vm=require('vm'),assert=require('assert/strict');
const html=fs.readFileSync(process.argv[2] || 'public/index.html','utf8');
const script=html.match(/<script>([\s\S]*)<\/script>/)[1];
new vm.Script(script);
function definition(name){const start=script.indexOf('function '+name+'(');assert(start>=0);const ends=[script.indexOf('\nfunction ',start+1),script.indexOf('\nasync function ',start+1)].filter(x=>x>start);return script.slice(start,Math.min(...ends));}
const fixture=[{type:'dir',name:'Z',path:'Z',children:[{type:'dir',name:'Alpha',path:'Z/Alpha',children:[{type:'file',name:'Zulu.m4a',path:'Z/Alpha/Zulu.m4a',modifiedAt:10},{type:'file',name:'Beta.m4a',path:'Z/Alpha/Beta.m4a',modifiedAt:30}]}]},{type:'dir',name:'A',path:'A',children:[{type:'dir',name:'Beta',path:'A/Beta',children:[{type:'file',name:'Alpha.m4a',path:'A/Beta/Alpha.m4a',modifiedAt:20}]}]}];
const before=JSON.stringify(fixture),context=vm.createContext({state:{libraryData:fixture}});
for(const name of ['collectTracks','naturalCompare','stripExt','allLibraryAlbums','latestTrackTime','rootLibraryItems'])vm.runInContext(definition(name),context);
const paths=level=>Array.from(context.rootLibraryItems(level),x=>x.path);
assert.deepEqual(paths('recent'),['Z/Alpha','A/Beta']);
assert.deepEqual(paths('all-albums'),['Z/Alpha','A/Beta']);
assert.deepEqual(paths('songs'),['A/Beta/Alpha.m4a','Z/Alpha/Beta.m4a','Z/Alpha/Zulu.m4a']);
assert.equal(paths('artists').length,2);
assert.equal(JSON.stringify(fixture),before);
context.state.libraryData=[];for(const level of ['recent','all-albums','songs','artists'])assert.equal(paths(level).length,0);
console.log('Navigation syntax, album/song ordering, recent timestamps, empty library and data preservation checks passed');
