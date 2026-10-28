"""Build pinned CPython on an Apple host; never fabricate a framework receipt."""
from pathlib import Path
import json,platform,subprocess,sys,shutil

IOS=Path(__file__).resolve().parents[1]
def run(*argv,cwd=None):
    return subprocess.run(argv,cwd=cwd,check=True,capture_output=True,text=True).stdout.strip()

def main():
    if platform.system()!='Darwin' or shutil.which('xcodebuild') is None:
        raise SystemExit('Native runtime build NOT_RUN: macOS and full Xcode are required')
    lock=json.loads((IOS/'Build/Runtime.lock').read_text())
    output=IOS/'.build';output.mkdir(exist_ok=True)
    source=output/'cpython'
    if not source.exists():
        run('git','clone','--depth','1','--branch',lock['source_tag'],lock['source_repository'],str(source))
    if run('git','rev-parse','HEAD',cwd=source)!=lock['source_commit']:
        raise SystemExit('CPython source commit differs from Runtime.lock')
    if run('git','status','--porcelain','--untracked-files=no',cwd=source):
        raise SystemExit('CPython tracked source is modified')
    subprocess.run([sys.executable,'Apple','build','iOS'],cwd=source,check=True)
    frameworks=list((source/'cross-build').rglob('Python.xcframework'))
    if len(frameworks)!=1:
        raise SystemExit('Build did not yield one unambiguous Python.xcframework')
    target=IOS/'Python.xcframework'
    if target.exists():
        raise SystemExit('Existing Python.xcframework retained; explicitly select the reviewed build before replacing it')
    shutil.copytree(frameworks[0],target)
    print('Built framework staged. Simulator, device and extension-import acceptance still required.')

if __name__=='__main__':main()
