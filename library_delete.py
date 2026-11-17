#!/usr/bin/env python3
"""Scope-limited operations using directory descriptors; never follow symlinks."""
import hashlib,json,os,stat,sys
AUDIO={'.m4a','.mp3','.flac','.wav','.aac','.ogg','.opus'}
FLAGS=os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW
class Refused(Exception): pass

def parts_for(value,kind):
    if not isinstance(value,str) or len(value)>4096 or '\\' in value or '\x00' in value:raise Refused('Invalid library path')
    parts=value.split('/')
    if any(not part or part.startswith('.') for part in parts):raise Refused('Invalid library path')
    if kind=='artist' and len(parts)!=1 or kind=='album' and len(parts)!=2 or kind=='song' and (len(parts)<3 or os.path.splitext(parts[-1])[1].lower() not in AUDIO):raise Refused('Invalid deletion scope')
    if kind not in {'artist','album','song'}:raise Refused('Invalid deletion scope')
    return parts

def identity(st):return [st.st_dev,st.st_ino,st.st_mode,st.st_size,st.st_mtime_ns]
def snapshot(parent,name,prefix='',depth=0,counter=None,device=None):
    counter=counter if counter is not None else [0];counter[0]+=1
    if counter[0]>100000:raise Refused('Collection is too large for one operation')
    if depth>32:raise Refused('Collection is too deeply nested')
    st=os.stat(name,dir_fd=parent,follow_symlinks=False)
    if device is not None and st.st_dev!=device:raise Refused('Mounted subdirectories cannot be deleted')
    if not (stat.S_ISREG(st.st_mode) or stat.S_ISDIR(st.st_mode)):raise Refused('Symlinks and special files cannot be deleted')
    node={'name':name,'identity':identity(st),'children':[]}
    if stat.S_ISDIR(st.st_mode):
        fd=os.open(name,FLAGS,dir_fd=parent)
        try:
            if identity(os.fstat(fd))!=identity(st):raise Refused('Library changed; review again')
            for child in sorted(os.listdir(fd)):
                node['children'].append(snapshot(fd,child,prefix+name+'/',depth+1,counter,device))
        finally:os.close(fd)
    return node

def stats(node):
    if stat.S_ISREG(node['identity'][2]):return (1,int(os.path.splitext(node['name'])[1].lower() in AUDIO),node['identity'][3])
    totals=[0,0,0]
    for child in node['children']:
        for index,value in enumerate(stats(child)):totals[index]+=value
    return tuple(totals)
def fingerprint(tree):return hashlib.sha256(json.dumps(tree,ensure_ascii=True,separators=(',',':')).encode()).hexdigest()
def remove(parent,node,deleted):
    st=os.stat(node['name'],dir_fd=parent,follow_symlinks=False)
    if identity(st)!=node['identity']:raise Refused('Library changed during deletion; refresh and review again')
    if stat.S_ISDIR(st.st_mode):
        fd=os.open(node['name'],FLAGS,dir_fd=parent)
        try:
            if identity(os.fstat(fd))!=node['identity']:raise Refused('Library changed during deletion')
            if sorted(os.listdir(fd))!=[child['name'] for child in node['children']]:raise Refused('Library changed during deletion')
            for child in node['children']:remove(fd,child,deleted)
        finally:os.close(fd)
        # Remove only the validated directory entry; never follow a replacement link.
        current=os.stat(node['name'],dir_fd=parent,follow_symlinks=False)
        if current.st_dev!=st.st_dev or current.st_ino!=st.st_ino or not stat.S_ISDIR(current.st_mode):raise Refused('Directory changed during deletion')
        os.rmdir(node['name'],dir_fd=parent)
    else:
        os.unlink(node['name'],dir_fd=parent);deleted[0]+=1

def operate(root,request):
    fds=[];deleted=[0]
    try:
        parts=parts_for(request.get('path'),request.get('kind'))
        fd=os.open(root,FLAGS);fds.append(fd);device=os.fstat(fd).st_dev
        for part in parts[:-1]:
            fd=os.open(part,FLAGS,dir_fd=fd);fds.append(fd)
            if os.fstat(fd).st_dev!=device:raise Refused('Mounted subdirectories cannot be deleted')
        tree=snapshot(fd,parts[-1],device=device);is_dir=stat.S_ISDIR(tree['identity'][2])
        if is_dir!=(request['kind']!='song'):raise Refused('Item type does not match deletion scope')
        files,songs,size=stats(tree)
        result={'ok':True,'name':parts[-1],'path':request['path'],'kind':request['kind'],'files':files,'songs':songs,'bytes':size,'fingerprint':fingerprint(tree)}
        if request.get('operation')=='delete':
            if request.get('fingerprint')!=result['fingerprint']:raise Refused('Library changed; review the deletion again')
            remove(fd,tree,deleted);result['deletedFiles']=deleted[0]
        elif request.get('operation')!='preview':raise Refused('Invalid operation')
        return result
    except (OSError,Refused,RecursionError):
        return {'ok':False,'error':'The item is unavailable, unsafe, or changed. Refresh the library and review again.','deletedFiles':deleted[0]}
    finally:
        for fd in reversed(fds):os.close(fd)
if __name__=='__main__':
    try:print(json.dumps(operate(sys.argv[1],json.load(sys.stdin))))
    except Exception:print(json.dumps({'ok':False,'error':'Deletion could not be completed safely.','deletedFiles':0}))
