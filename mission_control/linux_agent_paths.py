"""Fixed Linux native-agent installation profiles; no PATH shim or host bridge."""
from pathlib import Path


def package_roots(home):
    """Inspect only bounded known user/system npm installation roots."""
    roots=[home/'.npm-global/lib/node_modules',home/'.local/lib/node_modules',
           home/'.volta/tools/image/packages/@openai/codex/lib/node_modules',
           Path('/usr/local/lib/node_modules'),Path('/usr/lib/node_modules')]
    roots.extend(sorted((home/'.nvm/versions/node').glob('*/lib/node_modules'))[:32])
    return roots


def candidates(tool,home):
    """Return native installer locations and official npm package payloads only."""
    if tool not in ('codex','claude'):return []
    values=[(home/'.local/bin'/tool,None,None),(Path('/usr/local/bin')/tool,None,None),(Path('/usr/bin')/tool,None,None)]
    if tool!='codex':return values
    for root in package_roots(home):
        package=root/'@openai/codex'
        payloads=sorted(package.glob('node_modules/@openai/codex-linux-*/vendor/*/bin/codex'))[:8]
        payloads.extend(sorted(package.glob('vendor/*-unknown-linux-*/codex/codex'))[:8])
        values.extend((path,package/'package.json','@openai/codex') for path in payloads)
    return values


def native_file(path):
    """Reject script wrappers and non-executable files before any process invocation."""
    import os
    try:
        with path.open('rb') as stream:magic=stream.read(4)
        return magic==b'\x7fELF' and os.access(path,os.X_OK)
    except OSError:return False
