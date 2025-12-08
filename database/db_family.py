from sqlalchemy import Engine
from pandas import DataFrame

from database.db import read_sql, execute_sql, build_values

# Family Tree
def fetch_persons(engine:Engine) -> DataFrame:
    sql = f'''SELECT person_id,
    first_name, last_name, nick_name, suffix,
    birth_date, birth_date_precision
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

def fetch_marriages(engine:Engine) -> DataFrame:
    sql = f'''SELECT husband_id, wife_id, marriage_id
    FROM marriages
    ;'''
    return read_sql(engine, sql)

def fetch_spouses(engine:Engine) -> DataFrame:
    sql = f'''SELECT person_id, spouse_id, marriage_id
    FROM tree.marrieds
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