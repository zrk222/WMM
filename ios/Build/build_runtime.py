"""Build pinned CPython on an Apple host; never fabricate a framework receipt."""
from pathlib import Path
import json,platform,subprocess,sys,shutil,hashlib

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

def tree_hash(folder):
    rows=[]
    for path in sorted(folder.rglob('*')):
        if path.is_symlink():raise ValueError('Cached runtime contains a symbolic link')
        if path.is_file():
            with path.open('rb') as stream:checksum=hashlib.file_digest(stream,'sha256').hexdigest()
            rows.append((path.relative_to(folder).as_posix(),checksum))
    if not rows:raise ValueError('Cached runtime is empty')
    return hashlib.sha256(json.dumps(rows,separators=(',',':')).encode()).hexdigest()

def cache_identity(lock,xcode):
    return dict(source_commit=lock['source_commit'],source_tag_object=lock['source_tag_object'],xcode=xcode,
                builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())

def reusable_framework(target,identity):
    receipt=target.parent/'runtime-cache.json'
    if not target.is_dir() or not receipt.is_file():return False
    try:
        saved=json.loads(receipt.read_text(encoding='utf-8'))
        return saved['identity']==identity and saved['tree_sha256']==tree_hash(target)
    except (ValueError,KeyError,OSError):return False

def main():
    if platform.system()!='Darwin' or shutil.which('xcodebuild') is None:
        raise SystemExit('Native runtime build NOT_RUN: macOS and full Xcode are required')
    if sys.version_info<(3,12):
        raise SystemExit('Pinned CPython Apple build tools require host Python 3.12 or newer')
    lock=json.loads((IOS/'Build/Runtime.lock').read_text())
    target=IOS/'Python.xcframework'
    identity=cache_identity(lock,run('xcodebuild','-version'))
    if reusable_framework(target,identity):
        print('Reusing exact hash-verified CPython framework from the same source and Xcode toolchain.')
        return
    if target.exists():
        raise SystemExit('Existing runtime cache is stale or unverified; clear this app build cache before retrying')
    output=IOS/'.build';output.mkdir(exist_ok=True)
    source=output/'cpython'
    if not source.exists():
        run('git','clone','--depth','1','--branch',lock['source_tag'],lock['source_repository'],str(source))
    verify_source(source,lock)
    subprocess.run([sys.executable,'Apple','build','iOS'],cwd=source,check=True)
    framework=framework_output(source)
    if target.exists():
        raise SystemExit('Existing Python.xcframework retained; explicitly select the reviewed build before replacing it')
    shutil.copytree(framework,target)
    (IOS/'runtime-cache.json').write_text(json.dumps(dict(identity=identity,tree_sha256=tree_hash(target)),indent=2),encoding='utf-8')
    print('Built framework staged. Simulator, device and extension-import acceptance still required.')

if __name__=='__main__':main()
