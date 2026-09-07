from uuid import UUID

from sqlalchemy import Engine
from pandas import DataFrame

from database.db import read_sql, execute_sql, build_values

def fetch_image_information(engine:Engine, public_id:UUID) -> DataFrame:
    sql = f'''
    SELECT public_id, version_number, update_time
    FROM config.images
    WHERE public_id = '{public_id}'::uuid
    ;'''
    return read_sql(engine, sql)

def update_image_information(engine:Engine, df:DataFrame):
    val_cols = ['public_id', 'version_number', 'upload_time', 'update_time', 'display_name']
    val_ins = ', '.join(val_cols)
    values, params = build_values(df, val_cols)
    sql = f'''
    INSERT INTO config.images ({val_ins}) VALUES {values}
    ON CONFLICT (public_id) DO UPDATE
    SET version_number = EXCLUDED.version_number,
    update_time = EXCLUDED.update_time,
    display_name = EXCLUDED.display_name
    ;'''
    execute_sql(engine, sql, params=params)
