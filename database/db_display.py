from numpy import median
from sqlalchemy import Engine
from pandas import DataFrame

from database.db import read_sql, execute_sql, build_values

def fetch_display_names(engine:Engine) -> DataFrame:
    sql = f'''
    SELECT member_id, full_name
    FROM display_names
    ;'''
    return read_sql(engine, sql)