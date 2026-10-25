"""Deterministic complete unittest sharding; test counts are not duration estimates."""
from collections import Counter
import argparse
import hashlib
import json
from pathlib import Path
import sys
import unittest

# Match repository imports of `python -m unittest discover -s tests`, including
# when this file is invoked directly rather than as an installed package.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def flatten(suite):
    """Retain every leaf occurrence and its original object; never deduplicate IDs."""
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from flatten(item)
        elif isinstance(item, unittest.TestCase):
            yield item
        else:
            raise ValueError('Discovery returned a non-TestCase leaf')


def verify_assignment(cases, assigned):
    """Reject loss, duplication, substituted objects or changed ID multiplicities."""
    occurrences = [entry for shard in assigned for entry in shard]
    positions = [position for position, _ in occurrences]
    if sorted(positions) != list(range(len(cases))):
        raise ValueError('Shard assignment did not preserve every discovery occurrence exactly once')
    if any(cases[position] is not case for position, case in occurrences):
        raise ValueError('Shard assignment substituted a discovered TestCase instance')
    if Counter(case.id() for case in cases) != Counter(case.id() for _, case in occurrences):
        raise ValueError('Shard assignment changed the full discovered ID multiset')


def partition(cases, shards):
    """Greedily balance whole defining modules, preserving their discovery order."""
    if type(shards) is not int or shards < 1:
        raise ValueError('Shard count must be a positive integer')
    if not cases:
        raise ValueError('Discovery is empty; refusing a green empty run')
    groups = {}
    for position, case in enumerate(cases):
        groups.setdefault(type(case).__module__, []).append((position, case))
    # More shards than cases cannot produce a nonempty selection for every job.
    if shards > len(cases):
        raise ValueError('Shard count exceeds the discovered test occurrence count')
    assigned = [[] for _ in range(shards)]
    counts = [0] * shards
    for module, members in sorted(groups.items(), key=lambda pair: (-len(pair[1]), pair[0])):
        index = min(range(shards), key=lambda number: (counts[number], number))
        assigned[index].extend(members)
        counts[index] += len(members)
    verify_assignment(cases, assigned)
    return assigned


def inventory(cases, assigned, index, plan_only):
    """Hash the full ordered ID inventory with duplicate IDs still represented."""
    ids = [case.id() for case in cases]
    raw = json.dumps(ids, ensure_ascii=True, separators=(',', ':')).encode('utf-8')
    value = dict(schema='wmm.ci-test-shards.v1', total_count=len(ids),
                 inventory_sha256=hashlib.sha256(raw).hexdigest(),
                 shards=len(assigned), index=index,
                 shard_counts=[len(shard) for shard in assigned],
                 selected_count=len(assigned[index]), grouping='defining_module',
                 mode='PLAN_ONLY_TESTS_NOT_RUN' if plan_only else 'EXECUTION_PENDING')
    if plan_only:
        value['selected_ids'] = [case.id() for _, case in assigned[index]]
    return value


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--shards', type=int, default=4)
    parser.add_argument('--index', type=int, required=True)
    parser.add_argument('--plan-only', action='store_true', help='Discover/assign only; no tests run or pass claim')
    args = parser.parse_args(argv)
    if args.shards < 1 or not 0 <= args.index < args.shards:
        parser.error('Require shards >= 1 and 0 <= index < shards')
    try:
        # Do not set top_level_dir: that would change test_* imports to tests.*.
        suite = unittest.TestLoader().discover(start_dir='tests', pattern='test_*.py')
        cases = list(flatten(suite))
        assigned = partition(cases, args.shards)
        value = inventory(cases, assigned, args.index, args.plan_only)
        print('CI_INVENTORY ' + json.dumps(value, sort_keys=True), flush=True)
        if not assigned[args.index]:
            raise ValueError('Selected shard is empty; refusing a green empty run')
    except (ValueError, ImportError) as error:
        print('CI_INVENTORY_ERROR: ' + str(error), file=sys.stderr, flush=True)
        return 2
    if args.plan_only:
        print('PLAN ONLY: tests were not run; no test PASS is claimed.', flush=True)
        return 0
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.TestSuite(case for _, case in assigned[args.index]))
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
