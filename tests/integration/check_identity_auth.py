"""Verify identity CRUD against Neon using synthetic rows in a rolled-back transaction."""

from contextlib import contextmanager
from pathlib import Path
import tomllib
from uuid import uuid4

from sqlalchemy import URL, create_engine, text

from database import db_admin


class TransactionEngine:
    """Keep helper transactions inside one rollback-only test connection."""

    def __init__(self, connection):
        self.connection = connection

    @contextmanager
    def begin(self):
        """Use a savepoint so an expected failure does not abort the whole test."""
        with self.connection.begin_nested():
            yield self.connection


def main():
    """Exercise registration, role replacement, login tracking, and cascade deletion."""
    settings = tomllib.loads(Path('.streamlit/secrets.toml').read_text())['postgresql']
    engine = create_engine(URL.create(
        'postgresql+psycopg', username=settings['user'], password=settings['password'],
        host=settings['host'], port=int(settings.get('port', 5432)),
        database=settings['database']))
    try:
        with engine.connect() as connection:
            transaction = connection.begin()
            try:
                test_engine = TransactionEngine(connection)
                key = ('test', str(uuid4()))
                assert db_admin.create_identity(test_engine, *key, 'test@example.invalid', "Test O'Example")
                record = db_admin.fetch_identity(test_engine, *key)
                assert len(record) == 1
                assert db_admin.fetch_identity_role(test_engine, *key).role_name.tolist() == ['demo']
                db_admin.update_identity_role(test_engine, *key, 'viewer')
                assert not db_admin.create_identity(test_engine, *key, 'test@example.invalid', 'Duplicate')
                assert db_admin.fetch_identity_role(test_engine, *key).role_name.tolist() == ['viewer']
                try:
                    db_admin.update_identity_role(test_engine, *key, 'missing-role')
                except Exception:
                    pass
                else:
                    raise AssertionError('Unknown role was accepted')
                assert db_admin.fetch_identity_role(test_engine, *key).role_name.tolist() == ['viewer']
                db_admin.update_identity_login(test_engine, *key)
                assert db_admin.delete_identity(test_engine, *key)
                assert db_admin.fetch_identity(test_engine, *key).empty
                assert connection.execute(text('SELECT count(*) FROM users.identity_roles WHERE user_id=:u'),
                                          {'u': int(record.iloc[0].user_id)}).scalar_one() == 0
                assert not db_admin.delete_identity(test_engine, *key)
            finally:
                transaction.rollback()
    finally:
        engine.dispose()
    print('Identity CRUD, duplicate registration, role preservation, and cascade checks passed; test rows rolled back.')


if __name__ == '__main__':
    main()
