const fs=require('node:fs/promises');
async function musicStorageStats(musicDir,statfs=fs.statfs) {
  let timer;
  try {
    const stats=await Promise.race([statfs(musicDir),new Promise((_,reject)=>{timer=setTimeout(()=>reject(Error('Storage check timed out')),5000);})]);
    const availableBytes=Number(stats.bavail)*Number(stats.bsize);
    if(!Number.isFinite(availableBytes)||availableBytes<0)throw Error('Invalid storage statistics');
    return {availableBytes};
  } finally {clearTimeout(timer);}
}
module.exports={musicStorageStats};
