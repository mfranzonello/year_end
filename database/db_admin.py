"""Read and maintain application identities and roles with transactional writes."""

from pandas import DataFrame
from sqlalchemy import Engine, text

from database.db import read_sql


def fetch_identity(engine: Engine, issuer_name: str, subject_id: str) -> DataFrame:
    """Find an identity using its provider and stable subject."""
    params = {"issuer": issuer_name, "subject": subject_id}
    sql = f'''
    SELECT user_id, user_email, display_name FROM users.identities
    WHERE issuer_name = :issuer AND subject_id = :subject
    ;'''
    return read_sql(engine, sql, params)


def fetch_identity_role(engine: Engine, issuer_name: str, subject_id: str) -> DataFrame:
    """Return every assigned role without caching permissions."""
    params = {"issuer": issuer_name, "subject": subject_id}
    sql = f'''
    SELECT role_name FROM users.roles
    JOIN users.identity_roles USING (role_id)
    JOIN users.identities USING (user_id)
    WHERE issuer_name = :issuer AND subject_id = :subject
    ;'''
    return read_sql(engine, sql, params)


def create_identity(engine: Engine, issuer_name: str, subject_id: str,
                    user_email: str, display_name: str) -> bool:
    """Atomically register a new Demo identity; preserve existing roles on conflict."""
    if not all(isinstance(v, str) and v.strip() for v in
               (issuer_name, subject_id, user_email, display_name)):
        raise ValueError("Identity requires provider, subject, email, and display name.")
    with engine.begin() as conn:
        role_id = conn.execute(text(
            "SELECT role_id FROM users.roles WHERE role_name = :role"
        ), {"role": "demo"}).scalar_one()
        user_id = conn.execute(text("""
            INSERT INTO users.identities
                (issuer_name, subject_id, user_email, display_name, first_login, last_login)
            VALUES (:issuer, :subject, :email, :name, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT (issuer_name, subject_id) DO NOTHING
            RETURNING user_id
        """), {"issuer": issuer_name, "subject": subject_id,
               "email": user_email, "name": display_name}).scalar_one_or_none()
        if user_id is None:
            return False
        conn.execute(text("""
            INSERT INTO users.identity_roles (user_id, role_id) VALUES (:user, :role)
        """), {"user": user_id, "role": role_id})
        return True


def update_identity_role(engine: Engine, issuer_name: str, subject_id: str,
                         role_name: str):
    """Replace all assigned roles with one existing role, or fail without changes."""
    with engine.begin() as conn:
        user_id = conn.execute(text("""
            SELECT user_id FROM users.identities
            WHERE issuer_name = :issuer AND subject_id = :subject FOR UPDATE
        """), {"issuer": issuer_name, "subject": subject_id}).scalar_one()
        role_id = conn.execute(text(
            "SELECT role_id FROM users.roles WHERE role_name = :role"
        ), {"role": role_name}).scalar_one()
        conn.execute(text("DELETE FROM users.identity_roles WHERE user_id = :user"),
                     {"user": user_id})
        conn.execute(text("""
            INSERT INTO users.identity_roles (user_id, role_id) VALUES (:user, :role)
        """), {"user": user_id, "role": role_id})


def delete_identity(engine: Engine, issuer_name: str, subject_id: str) -> bool:
    """Delete an identity; PostgreSQL cascades deletion to its role links."""
    with engine.begin() as conn:
        result = conn.execute(text("""
            DELETE FROM users.identities
            WHERE issuer_name = :issuer AND subject_id = :subject
        """), {"issuer": issuer_name, "subject": subject_id})
        return result.rowcount == 1


def update_identity_login(engine: Engine, issuer_name: str, subject_id: str) -> None:
    """Record login observation without changing profile or permissions."""
    with engine.begin() as conn:
        result = conn.execute(text("""
            UPDATE users.identities SET last_login = CURRENT_TIMESTAMP
            WHERE issuer_name = :issuer AND subject_id = :subject
        """), {"issuer": issuer_name, "subject": subject_id})
        if result.rowcount != 1:
            raise ValueError("Cannot record login for an unknown identity.")
