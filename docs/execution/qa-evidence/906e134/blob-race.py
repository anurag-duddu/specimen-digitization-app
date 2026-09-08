from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
import threading,json,hashlib
from specimen_digitization.application.storage import LocalBlobs,Conflict
root=Path(Path('/tmp/specimen-qa-hardening-path').read_text().strip());blobs=LocalBlobs(root/'atomic-write-repro');data=b'identical synthetic evidence\n'*40;target=blobs.root/hashlib.sha256(data).hexdigest();opened=threading.Event();release=threading.Event();original=Path.open
class PausedWriter:
 def __init__(self,f):self.f=f
 def __enter__(self):self.f.__enter__();opened.set();return self
 def __exit__(self,*a):return self.f.__exit__(*a)
 def write(self,data):assert release.wait(5);return self.f.write(data)
 def flush(self):return self.f.flush()
 def fileno(self):return self.f.fileno()
def controlled_open(path,*a,**kw):
 f=original(path,*a,**kw)
 return PausedWriter(f) if path==target and a and a[0]=='xb' else f
with patch.object(Path,'open',controlled_open):
 with ThreadPoolExecutor(max_workers=2) as pool:
  first=pool.submit(blobs.put,data);assert opened.wait(5)
  observed_size=target.stat().st_size
  try:second=blobs.put(data);outcome='success'
  except Conflict as e:outcome=str(e)
  finally:release.set()
  ref=first.result(5)
assert blobs.get(ref)==data
result={'candidate':'906e134','reproduced_defect':outcome=='Immutable blob content mismatch','injected_schedule':'pause first writer after exclusive create and before write; second actual put receives identical bytes','destination_visible_size_before_write':observed_size,'second_writer_result':outcome,'first_writer_and_final_bytes_valid':True,'impact':'same-byte concurrency falsely conflicts before SQL duplicate resolution; a crash before complete write can retain partial hash-named file'}
(root/'blob-race-results.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
