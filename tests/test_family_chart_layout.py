"""Tests for family-boundary detection and staggered Graphviz ordering."""

import unittest
import warnings
from uuid import UUID

from pandas import DataFrame

from charting.charts_family import find_boundaries, reroute_tails


IDS = [UUID(int=value) for value in range(1, 20)]


class FamilyChartLayoutTests(unittest.TestCase):
    def test_boundaries_accumulate_overlapping_visible_parents(self):
        parent_a, parent_b, parent_c, parent_d = IDS[:4]
        rows = DataFrame([
            {'node_id': parent_a, 'generation': 0, 'unit_order': 1,
             'x_order': 1, 'parent_ids': None},
            {'node_id': parent_b, 'generation': 0, 'unit_order': 1,
             'x_order': 2, 'parent_ids': None},
            {'node_id': parent_c, 'generation': 0, 'unit_order': 2,
             'x_order': 3, 'parent_ids': None},
            {'node_id': parent_d, 'generation': 0, 'unit_order': 2,
             'x_order': 4, 'parent_ids': None},
            {'node_id': IDS[4], 'generation': 1, 'unit_order': 1,
             'x_order': 1, 'parent_ids': [parent_a]},
            {'node_id': IDS[5], 'generation': 1, 'unit_order': 2,
             'x_order': 2, 'parent_ids': [parent_a, parent_b]},
            {'node_id': IDS[6], 'generation': 1, 'unit_order': 3,
             'x_order': 3, 'parent_ids': None},
            {'node_id': IDS[7], 'generation': 1, 'unit_order': 4,
             'x_order': 4, 'parent_ids': [parent_c]},
            {'node_id': IDS[8], 'generation': 1, 'unit_order': 5,
             'x_order': 5, 'parent_ids': [parent_c, parent_d]},
        ])

        with warnings.catch_warnings():
            warnings.simplefilter('error')
            result = find_boundaries(rows)

        generation = result[result['generation'] == 1]
        self.assertEqual(generation['family_unit'].tolist(), [1, 1, 1, 2, 2])
        self.assertNotIn('family_unit', rows.columns)

    def test_reroutes_only_cross_family_order_edges(self):
        rows = DataFrame([
            {'node_id': IDS[index], 'generation': 1, 'x_order': index + 1,
             'family_unit': index, 'tail_id': IDS[index + 1] if index < 4 else None,
             'tail_type': 'order' if index < 4 else None}
            for index in range(5)
        ])

        with warnings.catch_warnings():
            warnings.simplefilter('error')
            result = reroute_tails(rows, generation_limit=2)

        by_node = result.set_index('node_id')
        self.assertEqual(by_node.loc[IDS[0], 'tail_id'], IDS[3])
        self.assertEqual(by_node.loc[IDS[1], 'tail_id'], IDS[4])
        self.assertIsNone(by_node.loc[IDS[2], 'tail_id'])
        self.assertIsNone(by_node.loc[IDS[3], 'tail_id'])
        self.assertIsNone(by_node.loc[IDS[4], 'tail_id'])
        self.assertEqual(
            result['display_generation'].tolist(),
            [1.0, 1 + 1 / 3, 1 + 2 / 3, 1.0, 1 + 1 / 3],
        )

    def test_preserves_union_and_internal_order_edges(self):
        rows = DataFrame([
            {'node_id': IDS[0], 'generation': 1, 'x_order': 1,
             'family_unit': 1, 'tail_id': IDS[1], 'tail_type': 'union'},
            {'node_id': IDS[1], 'generation': 1, 'x_order': 2,
             'family_unit': 1, 'tail_id': IDS[2], 'tail_type': 'order'},
            {'node_id': IDS[2], 'generation': 1, 'x_order': 3,
             'family_unit': 1, 'tail_id': IDS[3], 'tail_type': 'order'},
            {'node_id': IDS[3], 'generation': 1, 'x_order': 4,
             'family_unit': 2, 'tail_id': None, 'tail_type': None},
        ])

        result = reroute_tails(rows, generation_limit=20).set_index('node_id')

        self.assertEqual(result.loc[IDS[0], 'tail_type'], 'union')
        self.assertEqual(result.loc[IDS[0], 'tail_id'], IDS[1])
        self.assertEqual(result.loc[IDS[1], 'tail_id'], IDS[2])
        self.assertEqual(result.loc[IDS[2], 'tail_id'], IDS[3])


if __name__ == '__main__':
    unittest.main()
