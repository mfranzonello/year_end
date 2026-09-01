from datetime import date

from sqlalchemy import Engine
from pandas import DataFrame

from database.db import read_sql, execute_sql, build_values

def fetch_display_names(engine:Engine, schema_name='demo') -> DataFrame:
    sql = f'''
    SELECT member_id, full_name
    FROM {schema_name}.display_names
    ;'''
    return read_sql(engine, sql)

def fetch_member_information(engine:Engine, schema_name='demo', cut_date=date.today()) -> DataFrame:
    sql = f'''
    SELECT member_id, full_name,
    CASE WHEN clan_date_1 IS NULL or clan_date_1 <= '{cut_date}'::date THEN clan_id_1 ELSE clan_id_2 END AS clan_id,
    CASE WHEN clan_date_1 IS NULL or clan_date_1 <= '{cut_date}'::date THEN clan_name_1 ELSE clan_name_2 END AS clan_name,
    birth_date, birth_date_precision, death_date, death_date_precision,
    entry_date, entry_date_precision, member_type
    birth_date, birth_date_precision, death_date, death_date_precision,
    entry_date, entry_date_precision, member_type
    FROM {schema_name}.member_information
    ;'''
    return read_sql(engine, sql)

def fetch_relationships_summary(engine:Engine, schema_name='demo') -> DataFrame:
    sql = f'''
    SELECT member_id_1, member_id_2, relationship_type,
    entry_date, entry_date_precision, relationship
    FROM {schema_name}.relationships_summary
    ;'''
    return read_sql(engine, sql)

def fetch_resolution_order(engine:Engine) -> list[str]:
    sql = f'''
    SELECT resolution FROM dashboard.resolution_order
    ;'''
    return read_sql(engine, sql)['resolution'].tolist()
