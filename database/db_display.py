from datetime import date
from uuid import UUID

from sqlalchemy import Engine
from pandas import DataFrame

from database.db import read_sql

def fetch_display_names(engine:Engine, schema_name:str='demo') -> DataFrame:
    sql = f'''
    SELECT member_id, full_name
    FROM {schema_name}.display_names
    ;'''
    return read_sql(engine, sql)

def fetch_member_information(engine:Engine, schema_name:str='demo', cut_date:date|None=None) -> DataFrame:
    if cut_date is None:
        cut_date = 'infinity'
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
    FROM {schema_name}.family_timeline{parameters}
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

def fetch_family_tree(engine: Engine, founder_id:UUID, schema_name:str='demo', cut_date:date|None=None,
                      direction:str='up_down', partner_branches:bool=True, include_animals='all') -> DataFrame:
    if cut_date is None:
        cut_date = 'infinity'
    if schema_name == 'dashboard':
        parameters = f"('{founder_id}'::uuid, '{cut_date}'::date, '{direction}', {partner_branches}, '{include_animals}')"
    else:
        parameters = ''
    sql = f'''
    WITH dfg AS (
    SELECT * FROM {schema_name}.family_graph{parameters}
    )

    SELECT node_id, node_type,
    COALESCE(p.first_name, a.first_name) AS first_name,
    COALESCE(p.middle_names, a.middle_names) AS middle_names,
    COALESCE(p.nick_name, a.nick_name) AS nick_name,
    p.last_name, p.prefix, suffix_to_text(p.suffix) AS suffix,
    COALESCE(p.sex, a.sex) AS sex, a.species,
    COALESCE(p.birth_date, a.birth_date) AS birth_date,
    COALESCE(p.birth_date_precision, a.birth_date_precision) AS birth_date_precision,
    COALESCE(p.death_date, a.death_date) AS death_date,
    COALESCE(p.death_date_precision, a.death_date_precision) AS death_date_precision,
    u.union_type, u.union_date, u.union_date_precision, clan_name,
    generation, unit_order, unit_position, x_order,
    parent_head_ids AS parent_ids,
    CASE WHEN parent_head_id IN (SELECT node_id FROM dfg) THEN parent_head_id END AS head_id,
    tail_id, tail_type, branch, lineage, ancestry
    FROM dfg
    LEFT JOIN persons p ON node_id = person_id
    LEFT JOIN animals a ON node_id = animal_id
    LEFT JOIN unions u ON node_id = u.union_id
    LEFT JOIN tree.clans ON u.union_id = clan_id
    ;'''
    return read_sql(engine, sql)

def fetch_resolution_order(engine:Engine) -> list[str]:
    sql = f'''
    SELECT resolution FROM dashboard.resolution_order
    ;'''
    return read_sql(engine, sql)['resolution'].tolist()

def fetch_member_birth_date(engine:Engine, member_id:UUID, schema_name='demo') -> date:
    sql = f'''
    SELECT
    CASE WHEN COALESCE(birth_date_precision, entry_date_precision) IS NULL OR
    COALESCE(birth_date_precision, entry_date_precision) = 'past' THEN CURRENT_DATE - 100*365
    WHEN COALESCE(birth_date_precision, entry_date_precision) = 'future' THEN CURRENT_DATE + 365
    ELSE LEAST(birth_date, entry_date) END AS start_date
    FROM {schema_name}.member_information
    WHERE member_id = '{member_id}'::uuid
    ;'''
    return read_sql(engine, sql).squeeze()