#!/usr/bin/env python3
"""
rename_to_trendpulse.py
Run from your project root:  python rename_to_trendpulse.py

Replaces every occurrence of "TrendPulse" with "TrendPulse" (case-sensitive)
in all .py, .md, .css, .txt, .env.example files.
Binary files are skipped automatically.
"""
import os
import sys

ROOT      = os.path.dirname(os.path.abspath(__file__))
EXTS      = {".py", ".md", ".css", ".txt", ".example", ".html"}
OLD, NEW  = "TrendPulse", "TrendPulse"

changed = []

for dirpath, dirnames, filenames in os.walk(ROOT):
    # Skip hidden dirs, __pycache__, venv, node_modules, .git
    dirnames[:] = [
        d for d in dirnames
        if d not in {"__pycache__", ".git", "venv", ".venv", "node_modules", "outputs", "data"}
        and not d.startswith(".")
    ]

    for fname in filenames:
        ext = os.path.splitext(fname)[1].lower()
        if ext not in EXTS:
            continue

        fpath = os.path.join(dirpath, fname)
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                content = f.read()
        except (UnicodeDecodeError, PermissionError):
            continue  # skip binary / unreadable files

        if OLD not in content:
            continue

        new_content = content.replace(OLD, NEW)
        with open(fpath, "w", encoding="utf-8") as f:
            f.write(new_content)

        rel = os.path.relpath(fpath, ROOT)
        n   = content.count(OLD)
        changed.append((rel, n))
        print(f"  ✓  {rel}  ({n} replacement{'s' if n != 1 else ''})")

print()
if changed:
    print(f"Done — updated {len(changed)} file(s).")
else:
    print("Nothing to change — 'TrendPulse' not found in any file.")
