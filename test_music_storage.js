const assert=require('node:assert/strict');
const {musicStorageStats}=require('./music-storage');
(async()=>{
 assert.deepEqual(await musicStorageStats('/music',async path=>{assert.equal(path,'/music');return {bavail:123,bsize:4096,bfree:999};}),{availableBytes:503808});
 assert.deepEqual(await musicStorageStats('/music',async()=>({bavail:0,bsize:4096})),{availableBytes:0});
 for(const stats of [{},{bavail:-1,bsize:4096}])await assert.rejects(musicStorageStats('/music',async()=>stats));
 await assert.rejects(musicStorageStats('/music',async()=>{throw Error('offline')}));
 console.log('Music storage: correct mount, available-not-total blocks, empty disk and failure validation passed');
})().catch(error=>{console.error(error);process.exitCode=1});
