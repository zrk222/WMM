"""JSON CLI for fixed trusted-local WMM operations: python -m mission_control.agent_cli."""
import argparse
import json
import sys
from .common import Invalid,canonical
from .operation_catalog import catalog
from .operator_client import OperatorClient,ClientError,strict_json,MAX_BYTES,grant_environment


def parser():
    """Accept only a canonical local origin and operation data on stdin."""
    result=argparse.ArgumentParser(description='WMM trusted-local operation client; no human approval or provider-write commands.')
    result.add_argument('command',choices=('catalog','call','review-prepare','review-status','review-resume'))
    result.add_argument('--origin',help='Exact WMM origin, for example http://127.0.0.1:57599')
    result.add_argument('--use-grant',action='store_true',help='Use WMM_AGENT_GRANT from the process environment; never fall back to session authority')
    return result


def operation_value(args,source):
    """Validate the selected transport mode before reading or sending an operation."""
    if not args.origin:raise Invalid('Operation commands require --origin http://127.0.0.1:PORT')
    if args.command!='call' and not args.use_grant:raise Invalid('Reviewed request commands require --use-grant')
    envelope=strict_json(source.read(MAX_BYTES+1))
    client=OperatorClient(args.origin,grant_token=grant_environment(args.use_grant))
    return client.call(envelope) if args.command=='call' else client.review(args.command.removeprefix('review-'),envelope)


def main(argv=None,stdin=None,stdout=None,stderr=None):
    """Emit one JSON document; stable error codes use stderr and nonzero status."""
    args=parser().parse_args(argv)
    source=stdin if stdin is not None else sys.stdin.buffer
    output=stdout if stdout is not None else sys.stdout
    errors=stderr if stderr is not None else sys.stderr
    try:
        if args.command=='catalog':
            value=catalog()
        else:
            value=operation_value(args,source)
        output.write(canonical(value)+'\n')
        return 0
    except Invalid as error:
        errors.write(canonical(dict(error=dict(code='INVALID_INPUT',message=str(error))))+'\n')
        return 2
    except ClientError as error:
        from .operator_client import error_fields
        errors.write(canonical(dict(error=error_fields(error)))+'\n')
        return 3


if __name__=='__main__':
    # JSON escapes are avoided; configure deterministic UTF-8 pipes on Windows too.
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
    raise SystemExit(main())
