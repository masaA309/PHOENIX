from __future__ import annotations
import ast, hashlib, json, subprocess, sys
from pathlib import Path, PurePosixPath
EXPECTED_ROOT=r"C:\Users\ashtc\OneDrive\デスクトップ\ちちのフォルダ\PHOENIX"
EXPECTED_HEAD="62a163b42b4c56047fc7deb79b058c2daaba7de6"
EXPECTED_BRANCH="main"
SNAPSHOT_REL="state/governance/t1a_prestate_snapshot_v2_20260906.json"
WRITE_TARGETS=["phoenix_core/order_bridge_gate.py","phoenix_core/factory.py","phoenix_core/__init__.py","phoenix_core/pipeline.py","phoenix_core/execution.py","order_manager.py","broker_gateway.py","direct_pipeline_v7.py","execution_engine_v7.py","scheduled_runner_v7.py","run_phoenix.py","tests/test_v7_step42.py","tests/test_v7_step42_run_phoenix.py","tests/test_v7_step7.py","tests/test_v7_step18.py","tests/test_v7_step47.py","tests/test_v7_step48.py","tests/test_v7_step49.py"]
RUNTIME_PROTECTED_ROOTS=("config","state","reports","execution","runtime","logs")
def die(m): print(m); raise SystemExit(2)
def run(root,*a):
 p=subprocess.run(list(a),cwd=root,capture_output=True,text=True,encoding="utf-8",errors="replace",check=False)
 if p.returncode: die(f"COMMAND_FAILED:{' '.join(a)}:{p.stderr.strip() or p.stdout.strip()}")
 return p.stdout.strip()
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def rel(p,r): return PurePosixPath(*p.resolve().relative_to(r.resolve()).parts).as_posix()
def isgov(p): return p=="state/governance" or p.startswith("state/governance/")
def diffdig(root,cached):
 a=["git","diff"]+(["--cached"] if cached else [])+["--binary","HEAD","--","."]+[f":(exclude){x}" for x in WRITE_TARGETS]+[":(exclude)state/governance/**"]
 p=subprocess.run(a,cwd=root,capture_output=True,check=False)
 if p.returncode: die("GIT_DIFF_FAILED")
 return {"sha256":hashlib.sha256(p.stdout).hexdigest(),"bytes":len(p.stdout)}
def untracked(root):
 p=subprocess.run(["git","ls-files","--others","--exclude-standard","-z"],cwd=root,capture_output=True,check=False)
 if p.returncode: die("UNTRACKED_ENUM_FAILED")
 d={}
 for raw in p.stdout.split(b"\0"):
  if not raw: continue
  x=raw.decode("utf-8",errors="surrogateescape").replace("\\","/")
  if x in WRITE_TARGETS or isgov(x): continue
  f=root/Path(*PurePosixPath(x).parts)
  if f.is_file(): d[x]=sha(f)
 return d
def runtimefp(root):
 d={}
 for name in RUNTIME_PROTECTED_ROOTS:
  b=root/name
  if not b.exists(): continue
  for f in sorted(b.rglob("*")):
   if not f.is_file(): continue
   x=rel(f,root)
   if not isgov(x): d[x]=sha(f)
 return d
def step49body(path):
 raw=path.read_bytes(); text=raw.decode("utf-8"); tree=ast.parse(text)
 n=next((x for x in tree.body if isinstance(x,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef))),None)
 if n is None: die("STEP49_BODY_BOUNDARY_MISSING")
 lines=text.splitlines(keepends=True); off=len("".join(lines[:n.lineno-1]).encode("utf-8"))
 return hashlib.sha256(raw[off:]).hexdigest()
def common(root,s):
 if str(root)!=EXPECTED_ROOT: die(f"ROOT_MISMATCH:{root}")
 if run(root,"git","rev-parse","HEAD")!=EXPECTED_HEAD: die("HEAD_MISMATCH")
 if run(root,"git","branch","--show-current")!=EXPECTED_BRANCH: die("BRANCH_MISMATCH")
 if run(root,"git","diff","--cached","--name-only","--",*WRITE_TARGETS): die("TARGET_STAGED")
 if diffdig(root,False)!=s["outside_worktree_diff"]: die("OUTSIDE_WORKTREE_CHANGED")
 if diffdig(root,True)!=s["outside_cached_diff"]: die("OUTSIDE_CACHED_CHANGED")
 if untracked(root)!=s["outside_untracked"]: die("OUTSIDE_UNTRACKED_CHANGED")
 if runtimefp(root)!=s["protected_runtime_fingerprint"]: die("PROTECTED_RUNTIME_CHANGED")
def main():
 if len(sys.argv)!=3 or sys.argv[1]!="--mode" or sys.argv[2] not in {"pre","post"}: die("USAGE")
 mode=sys.argv[2]; root=Path.cwd().resolve(); s=json.loads((root/SNAPSHOT_REL).read_text(encoding="utf-8")); common(root,s)
 if mode=="pre":
  for x,h in s["write_target_sha256"].items():
   f=root/x
   if not f.is_file() or sha(f)!=h: die(f"PRESTATE_TARGET_DRIFT:{x}")
  if step49body(root/"tests/test_v7_step49.py")!=s["step49_body_sha256"]: die("STEP49_BODY_DRIFT_PRE")
  print("PRESTATE:PASS"); print("REAL_ORDERS=0"); print("GIT_MUTATION=0"); return
 if step49body(root/"tests/test_v7_step49.py")!=s["step49_body_sha256"]: die("STEP49_BODY_CHANGED_OUTSIDE_IMPORT_HEADER")
 changed=[]; post={}
 for x,before in s["write_target_sha256"].items():
  f=root/x
  if not f.is_file(): die(f"POST_TARGET_MISSING:{x}")
  h=sha(f); post[x]=h
  if h!=before: changed.append(x)
 if not changed: die("NO_T1A_IMPLEMENTATION_CHANGE")
 print("POSTSTATE:PASS"); print("CHANGED_FILES="+",".join(changed)); print("POSTSTATE_SHA256="+json.dumps(post,ensure_ascii=False,sort_keys=True)); print("OUTSIDE_SCOPE_MUTATION=0"); print("PROTECTED_RUNTIME_MUTATION=0"); print("REAL_ORDERS=0"); print("GIT_MUTATION=0")
if __name__=="__main__": main()
