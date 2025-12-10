from datetime import date

from sqlalchemy import Engine
from pandas import DataFrame

from database.db import read_sql, execute_sql, build_values

def fetch_display_names(engine:Engine) -> DataFrame:
    sql = f'''
    SELECT member_id, full_name
    FROM display_names
    ;'''
    return read_sql(engine, sql)

def fetch_member_information(engine:Engine, cut_date=date.today()) -> DataFrame:
    sql = f'''
    SELECT member_id, full_name,
      CASE WHEN c1.clan_date IS NULL OR c1.clan_date <= '{cut_date}'::date THEN c1.clan_id ELSE c2.clan_id END AS clan_id,
      CASE WHEN c1.clan_date IS NULL OR c1.clan_date <= '{cut_date}'::date THEN c1.clan_name ELSE c2.clan_name END AS clan_name,
    birth_date, birth_date_precision, death_date, death_date_precision,
    entry_date, entry_date_precision, member_type
    FROM display_names JOIN tree.members USING (member_id)
    LEFT JOIN tree.households USING (member_id)
    LEFT JOIN tree.clans c1 ON current_clan_id = c1.clan_id
    LEFT JOIN tree.clans c2 ON nee_clan_id = c2.clan_id
    ORDER BY full_name
    ;'''
    return read_sql(engine, sql)
