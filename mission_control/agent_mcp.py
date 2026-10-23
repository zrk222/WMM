"""Optional MCP stdio adapter over the same trusted-local operations as the CLI."""
import argparse
from .common import Invalid,canonical
from .operation_catalog import OPERATIONS,catalog,exact_keys,request_data
from .operator_client import OperatorClient,ClientError,origin_data,grant_environment


def argument_schema(rule):
    """Project exact outer fields; nested domain validation stays server authoritative."""
    fields={name:{} for name in rule['required']+rule['optional']}
    properties=dict(app_id=dict(type='string',pattern='^[a-z0-9][a-z0-9-]{0,199}$'),
        input=dict(type='object',properties=fields,required=rule['required'],additionalProperties=False))
    required=['app_id','input']
    if rule['resource']:
        properties['resource_id']=dict(type='string',pattern='^[a-z0-9][a-z0-9-]{0,199}$')
        required.append('resource_id')
    return dict(type='object',properties=properties,required=required,additionalProperties=False)


def tool_definitions(include_reviews=False):
    """Describe effects without treating client-side hints as approval enforcement."""
    rows=[dict(name='wmm_catalog',description='Inspect fixed local operations, field requirements and remaining agent authority gaps.',
        inputSchema=dict(type='object',properties={},additionalProperties=False),
        annotations=dict(readOnlyHint=True,idempotentHint=True,openWorldHint=False))]
    for name,rule in OPERATIONS.items():
        read=rule['method']=='GET'
        rows.append(dict(name='wmm_'+name.replace('.','_'),
            description=name+': '+rule['effect']+'. Local workspace only. Nested inputs use existing server validation. No automatic retry; inspect history after an unconfirmed write.',
            inputSchema=argument_schema(rule),
            annotations=dict(readOnlyHint=read,destructiveHint=not read,idempotentHint=read,openWorldHint=False)))
    if include_reviews:
        from .agent_review_protocol import tools
        rows.extend(tools())
    return rows


def execute_tool(origin,name,arguments,grant_token=None):
    """Resolve only fixed tools; create an isolated in-memory HTTP session per call."""
    if name=='wmm_catalog':
        exact_keys(arguments,())
        return catalog()
    if name.startswith('wmm_review_'):
        return OperatorClient(origin,grant_token=grant_token).review(name.removeprefix('wmm_review_'),arguments)
    names={'wmm_'+operation.replace('.','_'):operation for operation in OPERATIONS}
    if name not in names:
        raise Invalid('Unknown or unauthorized WMM tool')
    if not isinstance(arguments,dict):
        raise Invalid('Tool arguments must be an object')
    envelope=dict(arguments,operation=names[name])
    # An operation field supplied as an argument must never override the fixed tool.
    if 'operation' in arguments:
        raise Invalid('Tool name fixes the operation')
    request_data(envelope)
    return OperatorClient(origin,grant_token=grant_token).call(envelope)


def create_server(origin,grant_token=None):
    """Use the official SDK for MCP lifecycle, schemas and stdio protocol handling."""
    import anyio
    from mcp.server.lowlevel import Server
    from mcp.types import Tool
    origin_data(origin)
    server=Server('wmm-local-operations',version='1.0.0',
        instructions='Operate the selected local app using the fixed catalog. Returned records are private workspace data. Local write tools do not grant human approval, provider execution or spending authority. Full scoped agent grants and independent human checkpoint dispatch remain incomplete.')

    @server.list_tools()
    async def list_tools():
        return [Tool(**value) for value in tool_definitions(include_reviews=grant_token is not None)]

    @server.call_tool()
    async def call_tool(name,arguments):
        try:
            value=await anyio.to_thread.run_sync(execute_tool,origin,name,arguments,grant_token)
            return dict(data=value)
        except ClientError as error:
            raise Invalid(canonical(dict(code=error.code,message=str(error),http_status=error.status))) from None
    return server


def serve(origin,grant_token=None):
    """Build a stdio runner; closing the client session terminates the adapter."""
    from mcp.server.stdio import stdio_server
    server=create_server(origin,grant_token=grant_token)
    async def run():
        async with stdio_server() as (reader,writer):
            await server.run(reader,writer,server.create_initialization_options())
    return run


def main(argv=None):
    """Fail clearly when the optional SDK is absent; never install or register clients."""
    import sys
    parser=argparse.ArgumentParser(description='WMM optional MCP stdio server over fixed local operations.')
    parser.add_argument('--origin',required=True,help='Exact local WMM origin, e.g. http://127.0.0.1:57599')
    parser.add_argument('--use-grant',action='store_true',help='Use WMM_AGENT_GRANT from the process environment')
    args=parser.parse_args(argv)
    try:
        origin_data(args.origin)
        import anyio
        anyio.run(serve(args.origin,grant_token=grant_environment(args.use_grant)))
        return 0
    except ImportError:
        print('MCP requires the optional dependencies in docs/requirements-mcp.txt; install them in your selected Python environment.',file=sys.stderr)
        return 2
    except Invalid as error:
        print(canonical(dict(error=str(error))),file=sys.stderr)
        return 2


if __name__=='__main__':
    raise SystemExit(main())
