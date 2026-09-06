from datetime import date
from uuid import UUID

from sqlalchemy import Engine
from pandas import DataFrame

from database.db import read_sql, execute_sql, build_values

# Family Tree
def fetch_persons(engine:Engine) -> DataFrame:
    sql = f'''SELECT person_id,
    first_name, last_name, nick_name, suffix,
    birth_date, birth_date_precision, death_date, death_date_precision
    FROM persons
    ;'''
    return read_sql(engine, sql)

def fetch_animals(engine:Engine) -> DataFrame:
    sql = f'''SELECT animal_id,
    first_name, nick_name, species
    FROM animals
    ;'''
    return read_sql(engine, sql)

def fetch_parents(engine:Engine) -> DataFrame:
    sql = f'''SELECT child_id, parent_id
    FROM parents
    ;'''
    return read_sql(engine, sql)

def fetch_pets(engine:Engine) -> DataFrame:
    sql = f'''SELECT pet_id, owner_id, relation_type,
    gotcha_date, gotcha_date_precision
    FROM pets
    ;'''
    return read_sql(engine, sql)

def fetch_partnerships(engine: Engine) -> DataFrame:
    """Return pairwise marriage and civil-union records for family consumers."""
    sql = '''SELECT union_id, partner_id_1, partner_id_2,
    union_date, union_date_precision, union_type
    FROM tree.partnerships
    ;'''
    return read_sql(engine, sql)

def fetch_partners(engine: Engine) -> DataFrame:
    """Return directional partner relationships for tree traversal."""
    sql = '''SELECT person_id, spouse_id, union_id, union_type
    FROM tree.partners
    ;'''
    return read_sql(engine, sql)

def fetch_members(engine:Engine) -> DataFrame:
    sql = f'''
    SELECT member_id, birth_date, birth_date_precision, death_date, death_date_precision,
    entry_date, entry_date_precision, member_type
    FROM tree.members
    ;'''
    return read_sql(engine, sql)

def fetch_households(engine:Engine) -> DataFrame:
    sql = f'''
    SELECT member_id, clan_id
    FROM tree.households
    ;'''
    return read_sql(engine, sql)

def fetch_founder(engine:Engine, schema_name:str) -> UUID:
    sql = f'''
    SELECT founder_id
    FROM {schema_name}.founder
    ;'''
    return read_sql(engine, sql).squeeze()

def fetch_family_graph(engine:Engine, founder_id:UUID,
                       cut_date:date|None=None,
                       traversal_mode:str='up_down',
                       include_partner_branches:bool=True) -> DataFrame:
    """Return the database-classified nodes and canonical graph connections."""
    sql = '''
    SELECT node_id, node_type, generation, unit_order, unit_position, x_order,
        parent_head_id, tail_id, tail_type, branch, lineage, ancestry,
        union_type, union_date, union_date_precision
    FROM dashboard.family_graph(
        :founder_id, :cut_date, :traversal_mode, :include_partner_branches
    )
    ORDER BY generation, x_order, node_id
    ;'''
    params = {
        'founder_id': founder_id,
        'cut_date': cut_date,
        'traversal_mode': traversal_mode,
        'include_partner_branches': include_partner_branches,
    }
    return read_sql(engine, sql, params=params)

def fetch_person_information(engine:Engine, person_id:UUID) -> DataFrame:
    sql = f'''
    WITH
    children AS (
    SELECT ARRAY_AGG(full_name ORDER BY birth_date) AS children_names
    FROM parents JOIN dashboard.display_names ON member_id = child_id
    JOIN persons ON child_id = person_id
    WHERE parent_id = '{person_id}'::uuid
    ),

    folks AS (
    SELECT ARRAY_AGG(full_name ORDER BY birth_date) AS parent_names
    FROM parents JOIN dashboard.display_names ON member_id = parent_id
    JOIN persons ON parent_id = person_id
    WHERE child_id = '{person_id}'::uuid
    ),
  
    furries AS (
    SELECT ARRAY_AGG(full_name ORDER BY birth_date) AS pet_names
    FROM pets JOIN dashboard.display_names ON member_id = pet_id
    JOIN animals ON pet_id = animal_id
    WHERE owner_id = '{person_id}'::uuid
    ),

    spouse AS (
    SELECT full_name AS spouse_name,
    union_date, union_date_precision, severance_date, married_name
    FROM tree.partners JOIN dashboard.display_names ON member_id = spouse_id
    JOIN tree.partnerships USING (union_id)
    WHERE person_id = '{person_id}'::uuid
    )

    SELECT person_id, first_name, middle_names, last_name, married_name, nick_name,
    sex, prefix, suffix_to_text(suffix) AS suffix,
    parent_names, spouse_name, children_names, pet_names,
    birth_date::date, birth_date_precision, death_date::date, death_date_precision,
    union_date, union_date_precision, severance_date::date
    FROM persons
    CROSS JOIN folks
    LEFT JOIN spouse ON TRUE
    CROSS JOIN children
    CROSS JOIN furries
    WHERE person_id = '{person_id}'::uuid
    ;'''
    return read_sql(engine, sql)

def fetch_animal_information(engine:Engine, animal_id:UUID) -> DataFrame:
    sql = f'''
    WITH owners AS (
    SELECT ARRAY_AGG(full_name ORDER BY birth_date) AS owner_names
    FROM pets JOIN dashboard.display_names ON member_id = owner_id
    JOIN persons ON owner_id = person_id
    WHERE pet_id = '{animal_id}'::uuid
    )

    SELECT animal_id, first_name, middle_names, nick_name,
    sex, species, owner_names,
    birth_date::date, birth_date_precision, 
    gotcha_date::date, gotcha_date_precision, 
    death_date::date, death_date_precision
    FROM animals
    LEFT JOIN pets ON pet_id = animal_id
    CROSS JOIN owners
    WHERE animal_id = '{animal_id}'::uuid;
    ;'''
    return read_sql(engine, sql)