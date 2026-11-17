const assert=require('node:assert/strict');
const {createAccessAuthorizer,TEAM_DOMAIN,AUDIENCE}=require('./access-auth');
(async()=>{
 const {generateKeyPair,exportJWK,SignJWT,createLocalJWKSet}=await import(require.resolve('jose'));
 const {publicKey,privateKey}=await generateKeyPair('RS256');const jwk=await exportJWK(publicKey);jwk.kid='fixture';
 const authorize=createAccessAuthorizer({keySet:createLocalJWKSet({keys:[jwk]})});
 const token=async(overrides={},options={})=>new SignJWT({type:'app',email:'operator@example.test',...overrides}).setProtectedHeader({alg:'RS256',kid:'fixture'}).setIssuer(options.issuer||TEAM_DOMAIN).setAudience(options.audience||AUDIENCE).setSubject(options.subject===undefined?'fixture-user':options.subject).setIssuedAt(options.iat||Math.floor(Date.now()/1000)).setExpirationTime(options.exp||'1h').sign(privateKey);
 assert.equal(await authorize(await token()),'fixture-user');
 for(const bad of [undefined,'bad',await token({}, {issuer:'https://wrong.cloudflareaccess.com'}),await token({}, {audience:'a'.repeat(64)}),await token({}, {exp:Math.floor(Date.now()/1000)-60}),await token({}, {iat:Math.floor(Date.now()/1000)+300}),await token({type:'meta'}),await token({email:''}),await token({}, {subject:''})])assert.equal(await authorize(bad),null);
 const signed=await token(),parts=signed.split('.');parts[1]=Buffer.from(JSON.stringify({type:'app',email:'attacker@example.test',sub:'attacker'})).toString('base64url');assert.equal(await authorize(parts.join('.')),null);
 assert.equal(await createAccessAuthorizer({issuer:'http://attacker.test',keySet:createLocalJWKSet({keys:[jwk]})})(signed),null);
 console.log('Access verification: valid signature/issuer/audience/session and missing/forged/expired/wrong-app tokens tested');
})().catch(error=>{console.error(error);process.exitCode=1});
