from sqlalchemy import Engine
from pandas import DataFrame

from database.db import read_sql, execute_sql, build_values

def fetch_identity(engine: Engine, issuer_name:str, subject_id: str) -> DataFrame:
    sql = f'''
    SELECT user_id, user_email, display_name
    FROM users.identities
    WHERE issuer_name = '{issuer_name}' AND subject_id = '{subject_id}'
    ;'''
    return read_sql(engine, sql)

def fetch_identity_role(engine:Engine, issuer_name:str, subject_id:str) -> DataFrame:
    sql = f'''
    SELECT role_name FROM users.roles
    JOIN users.identity_roles USING (role_id)
    JOIN users.identities USING (user_id)
    WHERE issuer_name = '{issuer_name}' AND subject_id = '{subject_id}'
    ;'''
    return read_sql(engine, sql)

def create_identity(engine:Engine, issuer_name:str, subject_id:str,
                    user_email:str, display_name:str):
    user_email = 'NULL' if (user_email is None) else f'{user_email}'
    display_name = 'NULL' if (display_name is None) else f'{display_name}'
    sql = f'''
    INSERT INTO users.identities
    (issuer_name, subject_id, user_email, display_name, first_login) VALUES
    ('{issuer_name}', '{subject_id}', {user_email}, {display_name}',
    NOW()::timestamp)
    ON CONFLICT DO NOTHING
    ;'''
    execute_sql(engine, sql)

def delete_identity(engine:Engine, issuer_name:str, subject_id:str):
    sql = f'''
    DELETE FROM users.identities
    WHERE issuer_name = '{issuer_name}' AND subject_id = '{subject_id}'
    ;'''
    execute_sql(engine, sql)

def update_identity_role(engine:Engine, issuer_name:str, subject_id:str, role_name:str):
    sql = f'''
    UPDATE users.identity_roles AS ir
    SET role = '{role_name}'
    FROM users.identities AS i
    WHERE ir.user_id = i.user_id
    AND i.issuer_name = '{issuer_name}'
    AND i.subject_id = '{subject_id}'
    ;'''
    execute_sql(engine, sql)

def update_identity_login(engine:Engine, issuer_name:str, subject_id:str):
    sql = f'''
    UPDATE users.identities
    SET last_login = NOW()::timestamp
    WHERE issuer_name = '{issuer_name}' AND subject_id = '{subject_id}'
    ;'''
    execute_sql(engine, sql)