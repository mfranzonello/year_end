"""Regression tests for reuse of disconnected pooled database connections."""

from unittest import TestCase
from unittest.mock import patch

from sqlalchemy import create_engine, text

from database.db import get_engine


class ConnectionPoolTests(TestCase):
    def test_closed_idle_connection_is_replaced_before_query(self):
        def local_engine(url, **options):
            return create_engine('sqlite://', **options)

        with patch('database.db.create_engine', side_effect=local_engine):
            engine = get_engine('example.invalid', '5432', 'test', 'test', 'test')
        try:
            with engine.connect() as connection:
                driver_connection = connection.connection.driver_connection
                self.assertEqual(connection.execute(text('SELECT 1')).scalar_one(), 1)
            # Simulate the server closing a connection after it returned to the pool.
            driver_connection.close()
            with engine.connect() as connection:
                self.assertIsNot(connection.connection.driver_connection, driver_connection)
                self.assertEqual(connection.execute(text('SELECT 1')).scalar_one(), 1)
        finally:
            engine.dispose()
