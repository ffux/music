import os,tempfile,unittest
from pathlib import Path
from library_delete import operate
class DeleteTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)/'music';self.root.mkdir()
  for name in ['Artist/Album/01 Song.m4a','Artist/Album/02 Keep.flac','Artist/Album/cover.jpg','Artist/Other/01 Keep.m4a','Other/Album/01 Keep.m4a']:
   p=self.root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'disposable fixture')
  self.outside=Path(self.tmp.name)/'outside.m4a';self.outside.write_bytes(b'outside must remain')
 def tearDown(self):self.tmp.cleanup()
 def preview(self,path,kind):return operate(str(self.root),dict(operation='preview',path=path,kind=kind))
 def delete(self,path,kind,preview=None):
  p=preview or self.preview(path,kind)
  return operate(str(self.root),dict(operation='delete',path=path,kind=kind,fingerprint=p.get('fingerprint')))
 def test_song_only(self):
  p=self.preview('Artist/Album/01 Song.m4a','song');self.assertTrue(p['ok']);self.assertEqual((p['files'],p['songs']),(1,1))
  self.assertTrue(self.delete(p['path'],'song',p)['ok']);self.assertTrue((self.root/'Artist/Album/cover.jpg').exists());self.assertTrue((self.root/'Artist/Album/02 Keep.flac').exists())
 def test_album_only(self):
  p=self.preview('Artist/Album','album');self.assertEqual((p['files'],p['songs']),(3,2));self.assertTrue(self.delete(p['path'],'album',p)['ok']);self.assertFalse((self.root/p['path']).exists());self.assertTrue((self.root/'Artist/Other/01 Keep.m4a').exists())
 def test_artist_only(self):
  self.assertTrue(self.delete('Artist','artist')['ok']);self.assertTrue((self.root/'Other/Album/01 Keep.m4a').exists());self.assertEqual(self.outside.read_bytes(),b'outside must remain')
 def test_traversal_and_root(self):
  for path in ['', '/', '..', '../outside.m4a', '/Artist', 'Artist//Album','Artist/../Other','Artist\\Album','.hidden']:
   with self.subTest(path=path):self.assertFalse(self.delete(path,'artist')['ok'])
  self.assertTrue(self.outside.exists());self.assertTrue((self.root/'Artist/Album/01 Song.m4a').exists())
 def test_scope_types_and_extensions(self):
  for path,kind in [('Artist','album'),('Artist/Album','artist'),('Artist/Album','song'),('Artist/Album/cover.jpg','song'),('Artist/Album/01 Song.m4a','album')]:self.assertFalse(self.delete(path,kind)['ok'])
 def test_symlink_target_parent_descendant(self):
  (self.root/'Artist/Album/link.m4a').symlink_to(self.outside)
  self.assertFalse(self.delete('Artist/Album/link.m4a','song')['ok']);self.assertFalse(self.delete('Artist/Album','album')['ok'])
  (self.root/'Linked').symlink_to(self.root/'Other',target_is_directory=True);self.assertFalse(self.delete('Linked/Album/01 Keep.m4a','song')['ok']);self.assertTrue(self.outside.exists())
 def test_changed_contents_require_new_review(self):
  p=self.preview('Artist/Album','album');(self.root/'Artist/Album/new.m4a').write_bytes(b'new')
  r=self.delete(p['path'],'album',p);self.assertFalse(r['ok']);self.assertEqual(r['deletedFiles'],0);self.assertTrue((self.root/'Artist/Album/01 Song.m4a').exists())
 def test_changed_file_and_missing_fingerprint(self):
  path='Artist/Album/01 Song.m4a';p=self.preview(path,'song');(self.root/path).write_bytes(b'changed content length')
  self.assertFalse(self.delete(path,'song',p)['ok']);self.assertFalse(operate(str(self.root),dict(path=path,kind='song',operation='delete'))['ok'])
 def test_nested_disc_file(self):
  path='Artist/Album/Disc 1/03 Song.m4a';p=self.root/path;p.parent.mkdir();p.write_bytes(b'fixture');self.assertTrue(self.delete(path,'song')['ok']);self.assertFalse(p.exists())
if __name__=='__main__':unittest.main()
