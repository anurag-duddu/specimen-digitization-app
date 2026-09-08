import os,json,hashlib,threading,tempfile
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from specimen_digitization.application.storage import LocalBlobs,Conflict
root=Path(Path('/tmp/specimen-qa-hardening-path').read_text().strip())/'repair';root.mkdir(exist_ok=True);results=[]
for phase in ('before_write','before_publish'):
 blobs=LocalBlobs(root/phase);data=b'identical synthetic immutable evidence\n'*7000;ref=hashlib.sha256(data).hexdigest();target=blobs.root/ref;ready=threading.Event();release=threading.Event();claimed=[False];lock=threading.Lock();original_fdopen=os.fdopen;original_link=os.link
 class Writer:
  def __init__(self,f):self.f=f
  def __enter__(self):self.f.__enter__();ready.set();return self
  def __exit__(self,*a):return self.f.__exit__(*a)
  def write(self,b):assert release.wait(10);return self.f.write(b)
  def flush(self):return self.f.flush()
  def fileno(self):return self.f.fileno()
 def claim():
  with lock:
   if claimed[0]:return False
   claimed[0]=True;return True
 def fdopen(*a,**kw):
  f=original_fdopen(*a,**kw)
  return Writer(f) if phase=='before_write' and claim() else f
 def link(*a,**kw):
  if phase=='before_publish' and claim():ready.set();assert release.wait(10)
  return original_link(*a,**kw)
 with patch.object(os,'fdopen',fdopen),patch.object(os,'link',link):
  with ThreadPoolExecutor(max_workers=1) as pool:
   first=pool.submit(blobs.put,data);assert ready.wait(10)
   assert not target.exists(),'Final pathname exposed before publication'
   second=blobs.put(data);inode=target.stat().st_ino;assert second==ref and blobs.get(ref)==data
   release.set();assert first.result(10)==ref
 assert target.stat().st_ino==inode and blobs.get(ref)==data
 assert [p.name for p in blobs.root.iterdir()]==[ref]
 results.append({'phase':phase,'pass':True,'final_path_absent_before_publication':True,'second_identical_writer_succeeded':True,'first_writer_reconciled_exact_bytes':True,'existing_inode_not_replaced':True,'owned_temporary_files_cleaned':True})
blobs=LocalBlobs(root/'empty');ref=blobs.put(b'');assert blobs.get(ref)==b'';assert blobs.put(b'')==ref;(blobs.root/ref).write_bytes(b'x')
try:blobs.put(b'');raise AssertionError('Corrupt empty blob accepted')
except Conflict:pass
assert (blobs.root/ref).read_bytes()==b'x' and list(blobs.root.iterdir())==[blobs.root/ref]
results.append({'phase':'empty_blob','pass':True,'first_and_replay_exact':True,'corruption_rejected_without_overwrite':True,'temporary_cleanup':True})
(root/'atomic-independent-results.json').write_text(json.dumps(results,indent=2));print(json.dumps(results))
