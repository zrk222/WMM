"""Check tracked distribution files without reading ignored operational state."""
import pathlib
import re
import subprocess
import sys

ROOT=pathlib.Path(__file__).resolve().parents[1]
def files():
    if (ROOT/'.git').exists():
        result=subprocess.run(['git','ls-files','-z'],cwd=ROOT,capture_output=True,check=True)
        return [ROOT/name for name in result.stdout.decode().split('\0') if name]
    return [p for p in ROOT.rglob('*') if p.is_file() and not any(
        part in ('.factory','.forge','.git','__pycache__','data') for part in p.relative_to(ROOT).parts)]

def check():
    issues=[]
    patterns=[r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----\s+[A-Za-z0-9+/]{32,}',
              r'\bgh[pousr]_[A-Za-z0-9]{30,}',r'\bsk_(?:live|test)_[A-Za-z0-9]{20,}',
              r'\bsk-proj-[A-Za-z0-9_-]{30,}',r'C:[/\\]Users[/\\][^/\\\s]+']
    for path in files():
        rel=path.relative_to(ROOT)
        if path.is_symlink() or not path.resolve().is_relative_to(ROOT):issues.append(str(rel)+': escaping path');continue
        if path.suffix in ('.sqlite','.sqlite3','.db','.png','.jpeg','.jpg','.zip','.pyc'):
            issues.append(str(rel)+': operational/binary file');continue
        text=path.read_text(encoding='utf-8')
        for pattern in patterns:
            if re.search(pattern,text):issues.append(str(rel)+': credential or private path pattern')
    if issues:raise SystemExit('\n'.join(issues))
    print('PASS: distribution contains no forbidden operational files or recognized credential patterns.')
if __name__=='__main__':check()
