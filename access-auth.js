// Validate the existing Cloudflare Access session; no new login or access policy.
const TEAM_DOMAIN='https://throbbing-flower-2b15.cloudflareaccess.com';
const AUDIENCE='cfbd88aae2c8294da5f09d2786be737096706b14fdc114c124a3463ede2c0549';
let josePromise;
const jose=()=>josePromise||(josePromise=import(require.resolve('jose')));
function createAccessAuthorizer({issuer=process.env.MUSIC_ACCESS_TEAM_DOMAIN||TEAM_DOMAIN,audience=process.env.MUSIC_ACCESS_AUDIENCE||AUDIENCE,keySet}={}) {
  let remote;
  return async function authorize(token) {
    try {
      const url=new URL(issuer);
      if(url.protocol!=='https:'||!/^[-a-z0-9]+\.cloudflareaccess\.com$/.test(url.hostname)||url.pathname!=='/'||url.port||url.username||url.password||url.search||url.hash||!/^[a-f0-9]{64}$/.test(audience))return null;
      if(typeof token!=='string'||token.length>16384)return null;
      const {createRemoteJWKSet,jwtVerify}=await jose();
      remote=remote||keySet||createRemoteJWKSet(new URL('/cdn-cgi/access/certs',issuer),{timeoutDuration:5000,cacheMaxAge:600000,cooldownDuration:30000});
      const {payload}=await jwtVerify(token,remote,{issuer,audience,algorithms:['RS256'],requiredClaims:['sub','iat','exp'],clockTolerance:5});
      if(payload.type!=='app'||typeof payload.email!=='string'||!payload.email||typeof payload.sub!=='string'||!payload.sub||payload.iat>Date.now()/1000+30||payload.exp<=payload.iat)return null;
      return payload.sub;
    } catch { return null; }
  };
}
module.exports={createAccessAuthorizer,TEAM_DOMAIN,AUDIENCE};
