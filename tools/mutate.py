#!/usr/bin/env python3
"""Mutation check for a guard: break the code on purpose and confirm a suite notices.

    python3 tools/mutate.py <file> <exact text> <replacement> <label> [suite command]

The text must occur exactly once (otherwise "MUTATION NOT APPLIED"). The file is always
restored, even if the suite crashes. Default suite: python3 verify.py. Judged by the exit code,
never by parsing output -- counting failure lines once made a suite that never ran look like it
had passed.
"""
import shlex
import shutil
import subprocess
import sys
import tempfile

f, pat, rep, label = sys.argv[1:5]
cmd = shlex.split(sys.argv[5]) if len(sys.argv) > 5 else ["python3", "verify.py"]
src = open(f).read()
n = src.count(pat)
if n != 1:
    print(f"  {label:<40} MUTATION NOT APPLIED ({n} matches)")
    sys.exit(2)
backup = tempfile.NamedTemporaryFile(delete=False).name
shutil.copy(f, backup)
try:
    open(f, "w").write(src.replace(pat, rep, 1))
    r = subprocess.run(cmd, capture_output=True, text=True)
finally:
    shutil.copy(backup, f)
why = next((l.strip() for l in r.stdout.splitlines() if l.strip().startswith(("✗", "FAIL"))), "")
print(f"  {label:<40} {'CAUGHT' if r.returncode else 'NOT CAUGHT'}  ({why[:90]})")
sys.exit(0 if r.returncode else 1)
