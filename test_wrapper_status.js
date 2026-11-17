const assert = require('node:assert/strict');
const { summarizeWrapper, createWrapperStatus } = require('./wrapper-status');
(async () => {
  const secret = 'SENTINEL_SECRET_NEVER_EXPOSE';
  const fixture = state => ({ runtime: {playback_ready:true}, auth:{state,music_user_token:secret,dev_token:secret,password:secret}, extra:secret });
  assert.deepEqual(summarizeWrapper(fixture('authenticated')), {state:'ready'});
  for (const [state,expected] of [['logged_out','sign_in_required'],['awaiting_2fa','verification_required'],['unexpected','unavailable']]) {
    const result=summarizeWrapper(fixture(state)); assert.equal(result.state,expected); assert(!JSON.stringify(result).includes(secret));
  }
  assert.equal(summarizeWrapper({...fixture('authenticated'), runtime:{playback_ready:false}}).state,'runtime_unavailable');
  assert.equal(summarizeWrapper({runtime:{playback_ready:true},auth:{state:'authenticated'}}).state,'session_incomplete');
  for(const value of [null,{},'invalid'])assert.equal(summarizeWrapper(value).state,'unavailable');
  let calls=0;
  const status=createWrapperStatus({fetchImpl:async(url,options)=>{calls++;assert.equal(url.pathname,'/me');assert.equal(options.redirect,'error');return {ok:true,json:async()=>fixture('authenticated')};}});
  assert.deepEqual(await Promise.all([status(),status()]),[{state:'ready'},{state:'ready'}]); await status(); assert.equal(calls,1);
  for(const fetchImpl of [async()=>{throw Error(secret)},async()=>({ok:false}),async()=>({ok:true,json:async()=>{throw Error(secret)}})]) {
    assert.deepEqual(await createWrapperStatus({fetchImpl})(),{state:'unavailable'});
  }
  assert.deepEqual(await createWrapperStatus({enabled:false,fetchImpl:()=>{throw Error('must not fetch')}})(),{state:'disabled'});
  assert.deepEqual(await createWrapperStatus({baseUrl:'http://user:secret@localhost',fetchImpl:()=>{throw Error('must not fetch')}})(),{state:'unavailable'});
  console.log('Wrapper status: secret filtering, authentication states, failures, disabled mode, URL validation and request deduplication passed');
})();
