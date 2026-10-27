import ast,inspect,unittest
from mission_control import packaging_store as module
node=ast.parse(inspect.getsource(module.latest)).body[0]
node.body=[s for s in node.body if not isinstance(s,ast.If)]
namespace=dict(module.__dict__)
exec(compile(ast.fix_missing_locations(ast.Module(body=[node],type_ignores=[])),'<entry-guard-mutant>','exec'),namespace)
module.latest=namespace['latest']
raise SystemExit(not unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromName('tests.test_native_sqlite_entry')).wasSuccessful())
