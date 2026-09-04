from datetime import date

from sqlalchemy import Engine
from pandas import DataFrame

from database.db import read_sql, execute_sql, build_values

def fetch_display_names(engine:Engine, schema_name:str='demo') -> DataFrame:
    sql = f'''
    SELECT member_id, full_name
    FROM {schema_name}.display_names
    ;'''
    return read_sql(engine, sql)

def fetch_member_information(engine:Engine, schema_name:str='demo', cut_date:date=date.today()) -> DataFrame:
    sql = f'''
    SELECT member_id, full_name,
    CASE WHEN clan_date IS NULL or clan_date <= '{cut_date}'::date THEN clan_id_1 ELSE clan_id_2 END AS clan_id,
    CASE WHEN clan_date IS NULL or clan_date <= '{cut_date}'::date THEN clan_name_1 ELSE clan_name_2 END AS clan_name,
    birth_date, birth_date_precision, death_date, death_date_precision,
    entry_date, entry_date_precision, member_type
    birth_date, birth_date_precision, death_date, death_date_precision,
    entry_date, entry_date_precision, member_type
    FROM {schema_name}.member_information
    ;'''
    return read_sql(engine, sql)

def fetch_actor_spans(engine:Engine, project_year:int, schema_name:str='demo', cut_date:date=date.today(),
                      direction:str='up_down', partner_branches:bool=True) -> DataFrame:

    if schema_name == 'dashboard':
        parameters = f"((SELECT founder_id FROM {schema_name}.founder), '{cut_date}'::date, '{direction}', {partner_branches})"
    else:
        parameters = ''

    sql = f'''
    WITH relatives AS (
    SELECT member_id, display_unit_key, display_unit_order, display_order
    FROM {schema_name}.family_members_display{parameters}
    JOIN dashboard.member_information USING (member_id)
    WHERE (death_date IS NULL OR death_date > '{cut_date}'::date)
    AND (death_date_precision IS NULL OR death_date_precision != 'past')
    ),

    appearances AS (
    SELECT member_id, start_time, end_time, span
    FROM dashboard.appearance_spans 
    WHERE project_year = {project_year}
    ),

    members AS (
    SELECT member_id, full_name, start_time, end_time, span,
    COALESCE(display_unit_key, uuid_nil()) AS clan_id,
    CASE WHEN clan_date <= '{cut_date}'::date OR clan_date IS NULL THEN clan_name_1 ELSE clan_name_2 END AS clan_name,
    display_unit_order, display_order
    FROM relatives
    FULL JOIN appearances USING (member_id)
    JOIN dashboard.member_information USING (member_id)
    )
  
    SELECT member_id, full_name, start_time, end_time, span, clan_id, clan_name,
    COALESCE(display_unit_order, MAX(display_unit_order) OVER () + 1) AS display_unit_order,
    COALESCE(display_order, DENSE_RANK() OVER (PARTITION BY (display_unit_order IS NULL) ORDER BY member_id)) AS display_order
    FROM members
    ;'''

    return read_sql(engine, sql)

def fetch_resolution_order(engine:Engine) -> list[str]:
    sql = f'''
    SELECT resolution FROM dashboard.resolution_order
    ;'''
    return read_sql(engine, sql)['resolution'].tolist()


