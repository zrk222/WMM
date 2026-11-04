"""Offline AST call-graph tripwire, not a proof of effect safety.

Never imports application modules. Finite operation dispatch is specialized from
source; unresolved roots fail. Unknown dynamic calls are reported separately.
"""
import argparse
import ast
from dataclasses import dataclass
import json
from pathlib import Path


UNKNOWN = object()
EXTERNAL_EFFECTS = {
    'PUBLISH_WITH_STANDING_CAMPAIGN_AUTHORITY',
    'SPEND_WITH_STANDING_CAMPAIGN_AUTHORITY',
    'PAUSE_OWNED_EXTERNAL_CAMPAIGN', 'READ_OWNED_PROVIDER_STATUS',
    'PUBLISH_WITH_EXACT_ORGANIC_POLICY',
}
LIMITATIONS = [
    'Heuristic only: no proof that an operation is free of external effects.',
    'Runtime injection, monkeypatching, reflection, callbacks and unknown receiver types may hide edges.',
    'Unknown branch predicates are traversed conservatively and can produce false positives.',
    'Only Python source and recognized network/provider transports are inspected; queued work is not executed.',
]


@dataclass(frozen=True)
class Ref:
    module: str
    name: str = ''


class Audit:
    def __init__(self, root):
        self.root = Path(root)
        self.modules = {}
        self.functions = {}
        self.classes = set()
        self.errors = []
        self.dynamic = set()
        self.paths = []
        self.roots = set()
        self.visited = set()
        self.environments = {}
        self.inferring = set()
        self.constructor_arguments = {}
        self.callsites = None
        for path in sorted((self.root / 'mission_control').rglob('*.py')):
            module = '.'.join(path.relative_to(self.root).with_suffix('').parts)
            try:
                tree = ast.parse(path.read_text(encoding='utf-8-sig'), filename=str(path))
            except (SyntaxError, UnicodeError, OSError) as exc:
                self.errors.append(f'{path.relative_to(self.root)}: {exc}')
                continue
            self.modules[module] = tree
            for node in tree.body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    self.functions[Ref(module, node.name)] = node
                if isinstance(node, ast.ClassDef):
                    self.classes.add(Ref(module, node.name))
                    for method in node.body:
                        if isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            self.functions[Ref(module, node.name + '.' + method.name)] = method

    def imports(self, tree, module):
        result = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    result[alias.asname or alias.name.split('.')[0]] = Ref(alias.name if alias.asname else alias.name.split('.')[0])
            elif isinstance(node, ast.ImportFrom):
                base = module.split('.')[:-node.level] if node.level else []
                target = '.'.join(base + ([node.module] if node.module else []))
                for alias in node.names:
                    # `from . import foo` refers to a module, not a function.
                    result[alias.asname or alias.name] = Ref(target, alias.name) if node.module else Ref(target + '.' + alias.name)
        return result

    def env(self, ref):
        if ref.module in self.environments:
            return dict(self.environments[ref.module])
        tree = self.modules.get(ref.module)
        result = self.imports(tree, ref.module) if tree else {}
        result.update({r.name: r for r in self.functions if r.module == ref.module and '.' not in r.name})
        result.update({r.name: r for r in self.classes if r.module == ref.module})
        self.environments[ref.module] = result
        return result

    def location(self, ref):
        node = self.functions.get(ref)
        return ref.module.replace('.', '/') + '.py' + (f':{node.lineno}:{ref.name}' if node else ':' + ref.name)

    def constructor_argument(self, owner, parameter):
        """Infer concrete bootstrap arguments without a second receiver registry."""
        key = (owner, parameter)
        if key in self.constructor_arguments: return self.constructor_arguments[key]
        if key in self.inferring: return UNKNOWN
        self.inferring.add(key)
        init = self.functions.get(Ref(owner.module, owner.name + '.__init__'))
        parameters = [p.arg for p in init.args.args[1:]] if init else []
        if parameter not in parameters:
            self.inferring.remove(key)
            return UNKNOWN
        index = parameters.index(parameter)
        candidates = set()
        if self.callsites is None:
            self.callsites = {}
            for module, tree in self.modules.items():
                parents = {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}
                base = self.env(Ref(module))
                for call in ast.walk(tree):
                    if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Name): continue
                    target = base.get(call.func.id)
                    if target not in self.classes: continue
                    self.callsites.setdefault(target, []).append((module, base, parents, call))
        for module, base, parents, call in self.callsites.get(owner, []):
                arg = call.args[index] if len(call.args) > index else next((k.value for k in call.keywords if k.arg == parameter), None)
                value = self.expr(arg, base, module, [], False)
                if value is UNKNOWN and isinstance(arg, ast.Name):
                    context = call
                    while context in parents and not isinstance(context, ast.ClassDef): context = parents[context]
                    if isinstance(context, ast.ClassDef):
                        value = self.constructor_argument(Ref(module, context.name), arg.id)
                if isinstance(value, Ref): candidates.add(value)
        self.inferring.remove(key)
        result = next(iter(candidates)) if len(candidates) == 1 else UNKNOWN
        self.constructor_arguments[key] = result
        return result

    def expr(self, node, env, module, chain, execute=True):
        if node is None:
            return UNKNOWN
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Name):
            return env.get(node.id, UNKNOWN)
        if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
            return [self.expr(n, env, module, chain, execute) for n in node.elts]
        if isinstance(node, ast.Dict):
            return {self.expr(k, env, module, chain, execute): self.expr(v, env, module, chain, False) for k, v in zip(node.keys, node.values) if k is not None}
        if isinstance(node, ast.Lambda):
            return (node, dict(env), module)
        if isinstance(node, ast.Subscript):
            value = self.expr(node.value, env, module, chain, execute)
            key = self.expr(node.slice, env, module, chain, execute)
            try:
                return value[key]
            except (KeyError, TypeError, IndexError):
                return UNKNOWN
        if isinstance(node, ast.Slice):
            values = [self.expr(n, env, module, chain, execute) if n else None for n in (node.lower, node.upper, node.step)]
            if UNKNOWN not in values:
                return slice(*values)
            return UNKNOWN
        if isinstance(node, ast.Attribute):
            owner = self.expr(node.value, env, module, chain, execute)
            if isinstance(owner, Ref):
                ref = Ref(owner.module, '.'.join(filter(None, (owner.name, node.attr))))
                if ref in self.functions or not owner.name:
                    return ref
                # Infer owned attributes from actual constructor assignments.
                init = self.functions.get(Ref(owner.module, owner.name + '.__init__'))
                if init:
                    local = self.env(owner)
                    local.update(self.imports(init, owner.module))
                    for item in ast.walk(init):
                        if isinstance(item, ast.Assign):
                            for target in item.targets:
                                if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name) and target.value.id == 'self' and target.attr == node.attr:
                                    result = self.expr(item.value, local, owner.module, chain, False)
                                    if result is UNKNOWN and isinstance(item.value, ast.Name):
                                        result = self.constructor_argument(owner, item.value.id)
                                    return result
                return ref
            return UNKNOWN
        if isinstance(node, ast.Compare):
            left = self.expr(node.left, env, module, chain, False)
            right = self.expr(node.comparators[0], env, module, chain, False)
            if left is UNKNOWN or right is UNKNOWN:
                return UNKNOWN
            try:
                op = node.ops[0]
                if isinstance(op, ast.Eq): return left == right
                if isinstance(op, ast.NotEq): return left != right
                if isinstance(op, ast.In): return left in right
                if isinstance(op, ast.NotIn): return left not in right
            except TypeError:
                pass
            return UNKNOWN
        if isinstance(node, ast.BoolOp):
            values = [self.expr(n, env, module, chain, False) for n in node.values]
            if isinstance(node.op, ast.And) and False in values: return False
            if isinstance(node.op, ast.Or) and True in values: return True
            if isinstance(node.op, ast.Or):
                # An injected receiver can replace the default: inspect the
                # source-declared default, retain injection as a limitation.
                for value in values:
                    if isinstance(value, Ref): return value
            return UNKNOWN
        if isinstance(node, ast.Call):
            # Evaluate finite operation string transformations without executing code.
            if isinstance(node.func, ast.Attribute):
                value = self.expr(node.func.value, env, module, chain, False)
                args = [self.expr(n, env, module, chain, False) for n in node.args]
                if isinstance(value, str) and all(a is not UNKNOWN for a in args) and node.func.attr in ('startswith', 'removeprefix', 'split'):
                    return getattr(value, node.func.attr)(*args)
                if isinstance(value, dict) and node.func.attr == 'get' and args:
                    return value.get(args[0], args[1] if len(args) > 1 else UNKNOWN)
            if isinstance(node.func, ast.Name) and node.func.id == 'getattr' and len(node.args) >= 2:
                owner = self.expr(node.args[0], env, module, chain, False)
                name = self.expr(node.args[1], env, module, chain, False)
                if isinstance(owner, Ref) and isinstance(name, str):
                    return Ref(owner.module, owner.name + '.' + name)
            target = self.expr(node.func, env, module, chain, execute)
            args = [self.expr(n, env, module, chain, execute) for n in node.args]
            for keyword in node.keywords:
                self.expr(keyword.value, env, module, chain, execute)
            if isinstance(target, tuple) and len(target) == 3 and isinstance(target[0], ast.Lambda):
                return self.expr(target[0].body, target[1], target[2], chain, execute)
            if isinstance(target, Ref):
                if target in self.classes:
                    if execute:
                        self.call(Ref(target.module, target.name + '.__init__'), args, chain)
                    return target
                if execute:
                    self.call(target, args, chain)
                return UNKNOWN
            if execute and isinstance(node.func, (ast.Name, ast.Attribute, ast.Subscript)):
                name = ast.unparse(node.func)
                if name not in ('dict', 'list', 'set', 'str', 'int', 'bool', 'len', 'isinstance', 'type', 'next', 'sorted', 'tuple', 'enumerate', 'range', 'zip', 'min', 'max', 'sum', 'any', 'all'):
                    self.dynamic.add(f'{module.replace(".", "/")}.py:{node.lineno}:{name}')
            return UNKNOWN
        for child in ast.iter_child_nodes(node):
            self.expr(child, env, module, chain, execute)
        return UNKNOWN

    def statements(self, nodes, env, module, chain):
        for node in nodes:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                env.update(self.imports(node, module))
            elif isinstance(node, ast.Assign):
                value = self.expr(node.value, env, module, chain)
                for target in node.targets:
                    if isinstance(target, ast.Name): env[target.id] = value
            elif isinstance(node, ast.If):
                result = self.expr(node.test, env, module, chain, False)
                if result is not False:
                    returned = self.statements(node.body, dict(env), module, chain)
                    if result is True and returned: return True
                if result is not True:
                    returned = self.statements(node.orelse, dict(env), module, chain)
                    if result is False and returned: return True
            elif isinstance(node, ast.Return):
                self.expr(node.value, env, module, chain)
                return True
            elif isinstance(node, ast.Raise):
                # Unknown predicates may reject input; that is not a handler root.
                return True
            elif isinstance(node, (ast.With, ast.AsyncWith)):
                for item in node.items:
                    self.expr(item.context_expr, env, module, chain)
                if self.statements(node.body, env, module, chain): return True
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            elif isinstance(node, ast.Try):
                self.statements(node.body, dict(env), module, chain)
                for handler in node.handlers: self.statements(handler.body, dict(env), module, chain)
                self.statements(node.orelse, dict(env), module, chain)
                self.statements(node.finalbody, dict(env), module, chain)
            elif isinstance(node, (ast.For, ast.While)):
                self.statements(node.body, dict(env), module, chain)
            else:
                self.expr(node, env, module, chain)
        return False

    def call(self, ref, args, chain):
        location = self.location(ref)
        if len(chain) == 1 and ref in self.functions and ref.module not in ('mission_control.operation_catalog', 'mission_control.common'):
            self.roots.add(location)
        # Recognized transport entrypoints include all methods on provider transport
        # classes and concrete request functions; parsing still validates their source.
        provider_module = ref.module.endswith('_transport') and 'studio' not in ref.module
        network = ref.module.startswith(('requests', 'httpx', 'urllib.request', 'http.client', 'socket'))
        if (provider_module and ref.name.split('.')[-1] in ('request', 'exchange', 'fetch', 'send', 'publish', 'get', 'post', 'read', 'connect')) or (network and ref.name.split('.')[-1] in ('urlopen', 'open', 'request', 'get', 'post', 'send', 'connect', 'create_connection')):
            self.paths.append(chain + [location])
            return
        node = self.functions.get(ref)
        if node is None:
            self.dynamic.add(location)
            return
        key = (ref, repr(args))
        if key in self.visited or len(chain) > 45:
            return
        self.visited.add(key)
        env = self.env(ref)
        env.update(self.imports(node, ref.module))
        parameters = list(node.args.args)
        if '.' in ref.name and parameters and parameters[0].arg == 'self':
            env['self'] = Ref(ref.module, ref.name.rsplit('.', 1)[0])
            parameters = parameters[1:]
        env.update({p.arg: v for p, v in zip(parameters, args)})
        self.statements(node.body, env, ref.module, chain + [location])

    def catalog(self):
        tree = self.modules.get('mission_control.operation_catalog')
        if tree is None: return {}
        for node in tree.body:
            if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'OPERATIONS' for t in node.targets):
                if not isinstance(node.value, ast.Dict):
                    self.errors.append('OPERATIONS must be a literal descriptor dictionary')
                    return {}
                result = {}
                for key, value in zip(node.value.keys, node.value.values):
                    if not isinstance(value, ast.Call) or len(value.args) < 3:
                        self.errors.append('Unresolved catalog descriptor')
                        continue
                    try: result[ast.literal_eval(key)] = ast.literal_eval(value.args[2])
                    except (ValueError, TypeError): self.errors.append('Nonliteral catalog name/effect')
                return result
        self.errors.append('OPERATIONS assignment is missing')
        return {}

    def run(self):
        catalog = self.catalog()
        results = []
        for operation, effect in sorted(catalog.items()):
            self.dynamic = set(); self.paths = []; self.roots = set(); self.visited = set()
            entry = Ref('mission_control.ios_operation_adapter', 'guarded_execute') if operation.startswith('ios.') else Ref('mission_control.operation_runtime', 'execute')
            self.call(entry, [Ref('mission_control.service', 'Service'), {'operation': operation}], [])
            # The entry itself is not a resolved domain handler.
            roots = sorted(r for r in self.roots if ':execute' not in r)
            status = 'FAIL' if not roots or (self.paths and effect not in EXTERNAL_EFFECTS) else 'PASS'
            results.append(dict(operation=operation, declared_effect=effect, status=status,
                                handlers=roots, provider_paths=self.paths,
                                unresolved_dynamic_edges=sorted(self.dynamic),
                                reason='unresolved handler root' if not roots else 'provider reachability conflicts with local label' if self.paths and effect not in EXTERNAL_EFFECTS else 'no recognized conflicting path'))
        return dict(schema='wmm.operation-effect-audit.v1', heuristic=True,
                    ok=bool(catalog) and not self.errors and all(r['status'] == 'PASS' for r in results),
                    operations_audited=len(results), errors=self.errors, results=results,
                    limitations=LIMITATIONS)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args(argv)
    report = Audit(args.root).run()
    print(json.dumps(report, indent=2))
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
