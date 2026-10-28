"""Build pinned CPython on an Apple host; never fabricate a framework receipt."""
from pathlib import Path
import json,platform,subprocess,sys,shutil

IOS=Path(__file__).resolve().parents[1]
def run(*argv,cwd=None):
    return subprocess.run(argv,cwd=cwd,check=True,capture_output=True,text=True).stdout.strip()

def verify_source(source,lock):
    if run('git','rev-parse','HEAD',cwd=source)!=lock['source_commit']:
        raise SystemExit('CPython source commit differs from Runtime.lock')
    if run('git','rev-parse',lock['source_tag'],cwd=source)!=lock['source_tag_object']:
        raise SystemExit('CPython source tag object differs from Runtime.lock')
    if run('git','status','--porcelain','--untracked-files=no',cwd=source):
        raise SystemExit('CPython tracked source is modified')

def framework_output(source):
    framework=source/'cross-build/iOS/Python.xcframework'
    if not (framework/'Info.plist').is_file() or not (framework/'build/utils.sh').is_file():
        raise SystemExit('Built Python framework or pinned packaging helper is absent')
    return framework

def main():
    if platform.system()!='Darwin' or shutil.which('xcodebuild') is None:
        raise SystemExit('Native runtime build NOT_RUN: macOS and full Xcode are required')
    lock=json.loads((IOS/'Build/Runtime.lock').read_text())
    output=IOS/'.build';output.mkdir(exist_ok=True)
    source=output/'cpython'
    if not source.exists():
        run('git','clone','--depth','1','--branch',lock['source_tag'],lock['source_repository'],str(source))
    verify_source(source,lock)
    subprocess.run([sys.executable,'Apple','build','iOS'],cwd=source,check=True)
    framework=framework_output(source)
    target=IOS/'Python.xcframework'
    if target.exists():
        raise SystemExit('Existing Python.xcframework retained; explicitly select the reviewed build before replacing it')
    shutil.copytree(framework,target)
    print('Built framework staged. Simulator, device and extension-import acceptance still required.')

if __name__=='__main__':main()
