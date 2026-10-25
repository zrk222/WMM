"""Complete assignment and real miniature CLI execution; no full repository run."""
from collections import Counter
import json
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
_spec = importlib.util.spec_from_file_location('wmm_ci_runner', Path(__file__).resolve().parents[1]/'tools'/'run_ci_tests.py')
runner = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(runner)


def cases(module, count):
    case_type = type('SyntheticCase', (unittest.TestCase,),
                     {'__module__': module, 'runTest': lambda self: None})
    return [case_type() for _ in range(count)]


class ShardTests(unittest.TestCase):
    def test_nested_inventory_preserves_duplicate_ids_objects_and_module_order(self):
        first, second = cases('module_a', 3), cases('module_b', 2)
        repeated = first[0]
        suite = unittest.TestSuite([unittest.TestSuite(first), repeated, unittest.TestSuite(second)])
        flat = list(runner.flatten(suite)); assigned = runner.partition(flat, 4)
        self.assertEqual(len(flat), 6)
        self.assertEqual(Counter(c.id() for c in flat),
                         Counter(c.id() for shard in assigned for _, c in shard))
        self.assertEqual(sorted(p for shard in assigned for p, _ in shard), list(range(6)))
        self.assertEqual(sum(c is repeated for shard in assigned for _, c in shard), 2)
        group = next(shard for shard in assigned if any(type(c).__module__=='module_a' for _, c in shard))
        self.assertEqual([p for p, c in group if type(c).__module__=='module_a'], [0,1,2,3])

    def test_deterministic_greedy_count_balance_and_full_hash_preserve_multiplicity(self):
        flat = [c for index in range(8) for c in cases('module_'+str(index), 2)]
        before = runner.partition(flat, 4); after = runner.partition(flat, 4)
        self.assertEqual([[p for p, _ in s] for s in before], [[p for p, _ in s] for s in after])
        self.assertEqual([len(s) for s in before], [4,4,4,4])
        hashes = [runner.inventory(flat, before, i, True)['inventory_sha256'] for i in range(4)]
        self.assertEqual(len(set(hashes)), 1)
        shorter = flat[:-1]; other = runner.partition(shorter, 4)
        self.assertNotEqual(hashes[0], runner.inventory(shorter, other, 0, True)['inventory_sha256'])

    def test_assignment_sabotage_drop_duplicate_or_substitute_cannot_pass(self):
        flat = cases('one_module', 4); assigned = runner.partition(flat, 1)
        mutants = [[], [assigned[0][:-1]], [assigned[0]+[assigned[0][0]]],
                   [[(p, cases('replacement', 1)[0]) if p==0 else (p,c) for p,c in assigned[0]]]]
        for mutant in mutants:
            with self.subTest(mutant=mutant), self.assertRaises(ValueError):
                runner.verify_assignment(flat, mutant)

    def test_invalid_partition_inputs_reject(self):
        for count in (0, -1, True, 1.5):
            with self.subTest(count=count), self.assertRaises(ValueError):
                runner.partition(cases('one', 2), count)
        with self.assertRaises(ValueError): runner.partition([], 4)
        with self.assertRaises(ValueError): runner.partition(cases('one', 1), 4)

    def invoke(self, files, *args):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); tests = root/'tests'; tests.mkdir()
            for name, source in files.items(): (tests/name).write_text(source, encoding='utf-8')
            result = subprocess.run([sys.executable, str(Path(runner.__file__).resolve()), *args],
                                    cwd=root, capture_output=True, text=True, timeout=15)
            marker = (root/'EXECUTED').exists()
            return result, marker

    def test_cli_executes_every_miniature_case_once_in_four_shards_including_skip(self):
        files = {f'test_mini_{i}.py': 'import unittest\nclass Example(unittest.TestCase):\n'
                 + (' @unittest.skip("synthetic skip")\n' if i==3 else '')
                 + f' def test_case_{i}(self): pass\n' for i in range(4)}
        totals, selected, hashes = [], [], []
        for index in range(4):
            result, _ = self.invoke(files, '--shards', '4', '--index', str(index))
            self.assertEqual(result.returncode, 0, result.stderr)
            metadata = json.loads(next(line.removeprefix('CI_INVENTORY ') for line in result.stdout.splitlines() if line.startswith('CI_INVENTORY ')))
            totals.append(metadata['total_count']); selected.append(metadata['selected_count']); hashes.append(metadata['inventory_sha256'])
            self.assertIn('Ran 1 test', result.stderr)
            self.assertIn('test_case_', result.stderr)
        self.assertEqual(totals, [4]*4); self.assertEqual(selected, [1]*4); self.assertEqual(len(set(hashes)), 1)

    def test_cli_propagates_failure_error_and_discovery_import_failure(self):
        for body, expected in [('self.fail("fixture failure")','FAIL'),
                               ('raise RuntimeError("fixture error")','ERROR')]:
            source = 'import unittest\nclass Broken(unittest.TestCase):\n def test_broken(self): '+body+'\n'
            result, _ = self.invoke({'test_broken.py':source}, '--shards','1','--index','0')
            self.assertEqual(result.returncode, 1, result.stderr); self.assertIn(expected, result.stderr)
        result, _ = self.invoke({'test_import.py':'raise ImportError("fixture import failure")\n'}, '--shards','1','--index','0')
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn('_FailedTest', result.stderr); self.assertIn('fixture import failure', result.stderr)

    def test_plan_only_reports_inventory_without_executing_or_claiming_pass(self):
        source = 'import unittest\nfrom pathlib import Path\nclass Example(unittest.TestCase):\n def test_marker(self): Path("EXECUTED").touch()\n'
        result, marker = self.invoke({'test_marker.py':source}, '--shards','1','--index','0','--plan-only')
        self.assertEqual(result.returncode, 0, result.stderr); self.assertFalse(marker)
        self.assertIn('PLAN_ONLY_TESTS_NOT_RUN', result.stdout); self.assertIn('no test PASS is claimed', result.stdout)
        self.assertNotIn('Ran 1 test', result.stderr)

    def test_cli_invalid_bounds_empty_discovery_and_empty_selected_shard_fail(self):
        for args in [('--shards','0','--index','0'),('--shards','4','--index','-1'),('--shards','4','--index','4')]:
            result, _ = self.invoke({}, *args); self.assertEqual(result.returncode, 2)
        result, _ = self.invoke({}, '--shards','1','--index','0'); self.assertEqual(result.returncode, 2)
        self.assertIn('Discovery is empty', result.stderr)
        source = 'import unittest\nclass SameModule(unittest.TestCase):\n def test_a(self): pass\n def test_b(self): pass\n'
        result, _ = self.invoke({'test_empty_shard.py':source}, '--shards','2','--index','1')
        self.assertEqual(result.returncode, 2); self.assertIn('Selected shard is empty', result.stderr)


if __name__ == '__main__':
    unittest.main()
