"""Tests for converting database family-graph rows into canonical DOT."""

import unittest
from uuid import UUID

from pandas import DataFrame

from family_tree.graph import build_family_graph


PERSON_A = UUID('00000000-0000-0000-0000-000000000001')
PERSON_B = UUID('00000000-0000-0000-0000-000000000002')
CHILD = UUID('00000000-0000-0000-0000-000000000003')
UNION = UUID('00000000-0000-0000-0000-000000000004')


def graph_rows() -> DataFrame:
    """Return a minimal couple, union junction, and dependent fixture."""
    common = {
        'union_type': None,
        'union_date': None,
        'union_date_precision': None,
    }
    return DataFrame([
        {'node_id': PERSON_A, 'node_type': 'person', 'generation': 0,
         'x_order': 1, 'parent_head_id': None, 'tail_id': UNION,
         'tail_type': 'union', **common},
        {'node_id': UNION, 'node_type': 'union', 'generation': 0,
         'x_order': 2, 'parent_head_id': None, 'tail_id': PERSON_B,
         'tail_type': 'union', 'union_type': 'marriage',
         'union_date': '2020-01-02', 'union_date_precision': 'day'},
        {'node_id': PERSON_B, 'node_type': 'person', 'generation': 0,
         'x_order': 3, 'parent_head_id': None, 'tail_id': None,
         'tail_type': None, **common},
        {'node_id': CHILD, 'node_type': 'person', 'generation': 1,
         'x_order': 1, 'parent_head_id': UNION, 'tail_id': None,
         'tail_type': None, **common},
    ])


class FamilyGraphTests(unittest.TestCase):
    def test_builds_each_canonical_edge_once(self):
        graph = build_family_graph(graph_rows())

        self.assertEqual(graph.source.count(f'"{PERSON_A}" -> "{UNION}"'), 1)
        self.assertEqual(graph.source.count(f'"{UNION}" -> "{PERSON_B}"'), 1)
        self.assertEqual(graph.source.count(f'"{UNION}" -> "{CHILD}"'), 1)
        self.assertIn('Marriage: January 2, 2020', graph.source)

    def test_rejects_duplicate_node_ids(self):
        rows = graph_rows()
        rows.loc[1, 'node_id'] = PERSON_A

        with self.assertRaisesRegex(ValueError, 'duplicate node IDs'):
            build_family_graph(rows)

    def test_rejects_unknown_edge_endpoints(self):
        rows = graph_rows()
        rows.loc[0, 'tail_id'] = UUID('00000000-0000-0000-0000-000000000099')

        with self.assertRaisesRegex(ValueError, 'unknown node'):
            build_family_graph(rows)


if __name__ == '__main__':
    unittest.main()
