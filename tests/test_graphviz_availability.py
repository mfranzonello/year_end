"""Check navigation and direct page access without the Graphviz executable."""

import runpy
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from pages import general


class GraphvizAvailabilityTests(TestCase):
    def test_navigation_keeps_other_pages_without_graphviz(self):
        with patch('shutil.which', return_value=None):
            navigation = runpy.run_path('pages/general.py')
        paths = [path for path, label, gate in navigation['existing_pages']]
        self.assertNotIn('pages/family_tree.py', paths)
        self.assertIn('pages/family_member.py', paths)
        self.assertIn('pages/yir_count.py', paths)

    def test_navigation_includes_tree_with_graphviz(self):
        with patch('shutil.which', return_value='dot'):
            navigation = runpy.run_path('pages/general.py')
        self.assertIn(('pages/family_tree.py', 'Family Tree',
                       ['viewer', 'member', 'admin']),
                      navigation['existing_pages'])

    def test_direct_page_stops_before_database_or_tree_work(self):
        with patch.object(general, 'graphviz_available', return_value=False), \
             patch.object(general, 'set_sidebar'), \
             patch('database.db.get_engine') as get_engine, \
             patch('charting.charts_family.tree_chart') as tree_chart:
            page = Path(__file__).resolve().parents[1] / 'pages/family_tree.py'
            app = AppTest.from_file(str(page)).run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.info), 1)
        self.assertIn('temporarily unavailable', app.info[0].value)
        get_engine.assert_not_called()
        tree_chart.assert_not_called()
