"""Run the built executable from an unrelated directory, without installed source imports."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


async def mcp_smoke(binary, folder):
    """Exercise the frozen stdio SDK lifecycle without a workspace or provider."""
    import anyio
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(command=str(binary),
        args=['--mcp', '--origin', 'http://127.0.0.1:1'], cwd=folder)
    with anyio.fail_after(45):
        async with stdio_client(params) as (reader, writer):
            async with ClientSession(reader, writer) as client:
                initialized = await client.initialize()
                assert initialized.serverInfo.name == 'wmm-local-operations'
                tools = (await client.list_tools()).tools
                assert any(tool.name == 'wmm_catalog' for tool in tools)
                assert len(tools) > 1
                await client.send_ping()
                result = await client.call_tool('wmm_catalog', {})
                assert not result.isError
                assert result.structuredContent['data']['catalog_sha256']
                failure = await client.call_tool('wmm_workspace_read',
                    dict(app_id='sample-one', input={}))
                assert failure.isError
                assert 'TRANSPORT_UNAVAILABLE' in failure.content[0].text
    print(json.dumps(dict(command=['--mcp'], lifecycle='initialize-discover-ping-catalog-clean-close',
                         workspace_access='UNAVAILABLE_AS_EXPECTED', provider_access='NONE')))


def main():
    binary = ROOT/'dist/desktop/WMM'/('WMM.exe' if sys.platform == 'win32' else 'WMM')
    with tempfile.TemporaryDirectory() as folder:
        for arguments in (['--check'], ['--self-test'], ['--vault-self-test'], ['--agent-cli', 'catalog']):
            result = subprocess.run([str(binary), *arguments], cwd=folder, check=True,
                                    capture_output=True, text=True, timeout=90)
            value = json.loads(result.stdout)
            if arguments in (['--self-test'], ['--vault-self-test']):
                assert value['status'] == 'PASS'
            print(json.dumps(dict(command=arguments, exit_code=result.returncode)))
        import anyio
        anyio.run(mcp_smoke, binary, folder)


if __name__ == '__main__':
    main()
