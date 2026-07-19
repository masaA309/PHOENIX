# compile_all.py
from pathlib import Path
import py_compile
import sys

root = Path(__file__).resolve().parent
files = sorted(p for p in root.glob("*.py") if p.name != Path(__file__).name)
failed = []
for path in files:
    try:
        py_compile.compile(str(path), doraise=True)
        print(f"OK  {path.name}")
    except Exception as error:
        failed.append((path.name, str(error)))
        print(f"NG  {path.name}: {error}")
print("-" * 80)
print(f"対象: {len(files)} / 成功: {len(files)-len(failed)} / 失敗: {len(failed)}")
raise SystemExit(1 if failed else 0)
