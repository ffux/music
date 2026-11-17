"""Fail closed around gamdl 3.8.5's manifest-based ALAC -> AAC selection."""
import importlib.metadata


async def guarded_nonweb(self, master_url, codec):
    import m3u8
    if not master_url:
        raise RuntimeError('Cannot establish lossless availability: no master playlist URL; AAC fallback refused')
    response = await self.base.get_response(master_url)
    response.raise_for_status()
    text = response.text
    if not text.lstrip().startswith('#EXTM3U') or '#EXT-X-STREAM-INF:' not in text:
        raise RuntimeError('Cannot establish lossless availability: invalid master playlist; AAC fallback refused')
    data = m3u8.loads(text).data
    playlists = data.get('playlists')
    if not playlists or any(
        not item.get('uri') or not isinstance(item.get('stream_info'), dict)
        or not item['stream_info'].get('codecs')
        or not isinstance(item['stream_info'].get('average_bandwidth'), (int, float))
        or item['stream_info']['average_bandwidth'] <= 0
        for item in playlists
    ):
        raise RuntimeError('Cannot establish lossless availability: incomplete master playlist; AAC fallback refused')
    if self._is_enhanced_m3u8_master(data):
        selected = self._get_playlist_from_codec_enhanced(data, codec)
    else:
        selected = self._get_playlist_from_codec_nonenhanced(data, codec)
    if selected is None:
        if codec.value == 'alac':
            print('Quality: no ALAC variant in the successfully fetched master playlist; trying highest available AAC', flush=True)
        return None
    # Errors reading the selected media playlist propagate. No post-download retry.
    print(f'Quality: selected {codec.value.upper()} stream', flush=True)
    return await self._get_stream_info_from_playlist(master_url, selected,
        use_single_content_key=not self._is_enhanced_m3u8_master(data))


def install_guard():
    if importlib.metadata.version('gamdl') != '3.8.5':
        raise RuntimeError('Guarded quality selection requires reviewed gamdl 3.8.5')
    from gamdl.interface.song import AppleMusicSongInterface
    AppleMusicSongInterface._get_stream_info_nonweb = guarded_nonweb


if __name__ == '__main__':
    install_guard()
    from gamdl.cli.cli import main
    main()
