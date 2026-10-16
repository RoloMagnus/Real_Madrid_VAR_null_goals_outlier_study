"""Apply the candidate fixes to an ISOLATED copy of the scripts and re-run 03 -> 09 -> 05 -> 07 there (the repository is not modified).

Setup (PowerShell, once): copy scripts/ and data/processed/ and the small files of data/raw/ to %TEMP%\\rm_audit_tree, and create
directory junctions for the three raw caches (data/raw/espn_cache, fs_cache, tm_cache) pointing at the repository's caches:
    robocopy <repo>\\scripts %TEMP%\\rm_audit_tree\\scripts *.py ; robocopy <repo>\\data\\processed %TEMP%\\rm_audit_tree\\data\\processed /E
    robocopy <repo>\\data\\raw %TEMP%\\rm_audit_tree\\data\\raw /E /XD espn_cache fs_cache tm_cache
    cmd /c mklink /J %TEMP%\\rm_audit_tree\\data\\raw\\espn_cache <repo>\\data\\raw\\espn_cache   (same for fs_cache, tm_cache)
Cleanup: remove each junction with `cmd /c rmdir <junction>` BEFORE deleting the folder.
"""
import os, re, subprocess, sys
T = os.path.join(os.environ['TEMP'], 'rm_audit_tree', 'scripts')
def sub(fn, old, new, count=1):
    p = os.path.join(T, fn); s = open(p, encoding='utf8').read()
    assert old in s, (fn, old[:60])
    open(p, 'w', encoding='utf8').write(s.replace(old, new, count))
# (a) Understat aliases (Flashscore 'Huesca'/'Oviedo' vs Understat 'SD Huesca'/'Real Oviedo')
sub('05_enrich.py', '"athleticclub": "athleticclub", "leganes": "leganes"}', '"athleticclub": "athleticclub", "leganes": "leganes", "huesca": "sdhuesca", "oviedo": "realoviedo"}')
# (b) safe team-name mapping in the foul-zone script (ESPN calls La Coruna just 'Deportivo')
sub('09_fouls_espn.py', '''        for c in canon:
            if k in kk(c) or kk(c) in k:
                return c
        return n''', '''        if k == "deportivo":
            return "Deportivo La Coruña"
        if k == "alaves":
            return "Deportivo Alavés"
        c = [x for x in canon if k in kk(x) or kk(x) in k]
        return c[0] if len(c) == 1 else n''')
# (c) same fallback in the ESPN cross-check inside 07
sub('07_analysis.py', '''        for c in canon:
            if k in kk(c) or kk(c) in k:
                return c
        return n''', '''        if k == "deportivo":
            return "Deportivo La Coruña"
        c = [x for x in canon if k in kk(x) or kk(x) in k]
        return c[0] if len(c) == 1 else n''')
# (d) evidence rule: the bare word 'disallow' (also used for on-field decisions) is not VAR evidence
sub('03_build_dataset.py', r'\bVAR\b|video (assistant|review)|disallow"', r'\bVAR\b|video (assistant|review)"')
print('patched')
env = dict(os.environ, PYTHONUTF8='1')
for s in ('03_build_dataset.py', '09_fouls_espn.py', '05_enrich.py', '07_analysis.py'):
    r = subprocess.run([sys.executable, os.path.join(T, s)], cwd=os.path.dirname(T), env=env, capture_output=True, text=True)
    print('==', s, 'exit', r.returncode); print((r.stdout or '')[-600:]); print((r.stderr or '')[-800:])
