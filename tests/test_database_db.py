"""Unit tests for portable database parameter preparation."""

from unittest import TestCase
from unittest.mock import MagicMock

from pandas import DataFrame, NA, NaT

from database.db import execute_sql


class ExecuteSqlTests(TestCase):
    def test_converts_pandas_missing_values_to_database_nulls(self):
        engine = MagicMock()
        connection = engine.begin.return_value.__enter__.return_value
        frame = DataFrame([
            {
                "duration": 12,
                "missing_number": float("nan"),
                "missing_text": NA,
                "missing_date": NaT,
            },
        ])

        execute_sql(engine, "SELECT 1", df=frame)

        rows = connection.execute.call_args.args[1]
        self.assertEqual(rows[0]["duration"], 12)
        self.assertIsNone(rows[0]["missing_number"])
        self.assertIsNone(rows[0]["missing_text"])
        self.assertIsNone(rows[0]["missing_date"])
