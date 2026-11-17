// Never return or log the wrapper's /me body: it contains session credentials.
function summarizeWrapper(snapshot) {
  if (!snapshot || typeof snapshot !== 'object' || !snapshot.runtime || !snapshot.auth) return { state: 'unavailable' };
  if (snapshot.runtime.playback_ready !== true) return { state: 'runtime_unavailable' };
  const state = snapshot.auth.state;
  if (state === 'authenticated') {
    return { state: snapshot.auth.music_user_token && snapshot.auth.dev_token ? 'ready' : 'session_incomplete' };
  }
  if (state === 'awaiting_2fa') return { state: 'verification_required' };
  if (state === 'logged_out') return { state: 'sign_in_required' };
  return { state: 'unavailable' };
}
function createWrapperStatus({ baseUrl = 'http://music-wrapper', fetchImpl = fetch, enabled = true } = {}) {
  let cached, pending;
  return async function status() {
    if (!enabled) return { state: 'disabled' };
    if (cached && Date.now() - cached.time < 5000) return cached.value;
    if (pending) return pending;
    pending = (async () => {
      let value;
      try {
        const url = new URL(baseUrl);
        if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password || url.search || url.hash || !['', '/'].includes(url.pathname)) throw new Error('Invalid wrapper URL');
        const response = await fetchImpl(new URL('/me', url), { signal: AbortSignal.timeout(5000), redirect: 'error' });
        if (!response.ok) throw new Error('Wrapper unavailable');
        value = summarizeWrapper(await response.json());
      } catch { value = { state: 'unavailable' }; }
      cached = { time: Date.now(), value };
      return value;
    })();
    try { return await pending; } finally { pending = null; }
  };
}
module.exports = { summarizeWrapper, createWrapperStatus };
