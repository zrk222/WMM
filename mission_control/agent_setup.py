"""Offline setup discovery; never contact WMM, inspect tokens or register a host."""
import argparse
from importlib import metadata, util
import json
from pathlib import Path
import sys
from .common import Invalid
from .operator_client import origin_data


def dependency(name):
    """Inspect availability without importing the optional adapter or SDK."""
    if util.find_spec(name) is None:
        return dict(module=name, status='MISSING', version=None)
    try:
        version = metadata.version(name)
    except metadata.PackageNotFoundError:
        version = None
    return dict(module=name, status='AVAILABLE', version=version)


def report(origin):
    """Emit selected-interpreter setup facts and a cwd-independent grant launch."""
    origin_data(origin)
    root = Path(__file__).resolve().parent.parent
    python = str(Path(sys.executable).resolve())
    deps = [dependency(name) for name in ('mcp', 'anyio')]
    ready = all(d['status'] == 'AVAILABLE' for d in deps)
    baseline = deps[0]['version'] == '1.30.0'
    return dict(
        schema='wmm.agent-setup.v1', python=python, repository=str(root),
        origin=origin, server_status='NOT_CHECKED_OFFLINE',
        python_supported=sys.version_info >= (3, 11),
        cli=dict(status='AVAILABLE', catalog=[python, '-m', 'mission_control.agent_cli', 'catalog']),
        mcp=dict(status='DEPENDENCIES_AVAILABLE' if ready else 'OPTIONAL_DEPENDENCIES_MISSING',
                 tested_sdk_baseline='1.30.0', matches_tested_baseline=baseline, dependencies=deps,
                 install=[python, '-m', 'pip', 'install', '-r', str(root/'docs'/'requirements-mcp.txt')]),
        mcp_config=dict(mcpServers={'wmm-local': dict(command=python,
            args=['-m', 'mission_control.agent_mcp', '--origin', origin, '--use-grant'],
            env=dict(PYTHONPATH=str(root)))}),
        authority='OWNER_ISSUED_SCOPED_GRANT_REQUIRED_FOR_GENERATED_CONFIG',
        next_steps=[
            'Start WMM separately at the exact origin shown; offline discovery does not verify a running server.',
            'For delegated access, sign in under Activity & reviews as this app OWNER, then Manage agent grants.',
            'Supply WMM_AGENT_GRANT using the host protected process environment; no token belongs in configuration examples or prompts.',
            'Review and register the displayed MCP configuration manually in an authorized host. This command changes no host settings.',
            'Call wmm_catalog to discover current tools, then operations.read for selected-app policy. Missing grant never falls back to session authority.',
        ])


def main(argv=None):
    parser = argparse.ArgumentParser(description='Inspect local CLI/MCP setup offline and print a scoped-grant MCP launch configuration. No install or registration.')
    parser.add_argument('--origin', required=True, help='Exact running WMM origin, e.g. http://127.0.0.1:8765')
    parser.add_argument('--json', action='store_true', help='Print machine-readable setup facts and configuration')
    args = parser.parse_args(argv)
    try:
        value = report(args.origin)
    except Invalid as error:
        print(json.dumps(dict(error=str(error))), file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(value, indent=2))
    else:
        print('Python: ' + value['python'])
        print('Repository: ' + value['repository'])
        print('WMM: ' + value['origin'] + ' (not contacted)')
        print('CLI: python -m mission_control.agent_cli catalog')
        print('MCP: ' + value['mcp']['status'])
        print('Tested SDK baseline matches: ' + str(value['mcp']['matches_tested_baseline']))
        print('Optional installation command: ' + ' '.join('"'+a+'"' for a in value['mcp']['install']))
        print(json.dumps(value['mcp_config'], indent=2))
        for step in value['next_steps']:
            print(step)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
