from sqlalchemy import Engine
from pandas import DataFrame

from database.db import read_sql, execute_sql, build_values

def fetch_member_labels(engine:Engine, year:int) -> DataFrame:
    sql = f'''
    SELECT project_year, folder_name, label_id, label_name, color_hex
    FROM project.folders
    JOIN config.member_labels USING (member_id)
    JOIN config.adobe_labels USING (label_id)
    JOIN config.color_palette USING (color_name)
    WHERE project_year = {year}
    ;'''
    return read_sql(engine, sql)

def fetch_color_labels(engine:Engine) -> DataFrame:
    sql = f'''
    SELECT label_id, label_name, color_hex
    FROM config.adobe_labels JOIN config.color_palette USING (color_name)
    ORDER BY label_id
    ;'''
    return read_sql(engine, sql)

def update_appearances(engine:Engine, df:DataFrame):
    project_year = df['project_year'].iloc[0]
    sql = f'''
    DELETE FROM project.appearances WHERE project_year = {project_year}
    ;'''
    execute_sql(engine, sql)

    val_cols = ['project_year', 'member_id', 'start_time', 'end_time']
    val_ins = ', '.join(val_cols)
    values, params = build_values(df, val_cols)
    sql = f'''
    INSERT INTO project.appearances ({val_ins}) VALUES {values}
    ;'''
    execute_sql(engine, sql, params=params)

def fetch_timeline_years(engine:Engine) -> DataFrame:
    sql = f'''
    SELECT DISTINCT project_year
    FROM project.appearances
    ORDER BY project_year ASC
    ;'''
    return read_sql(engine, sql)

def fetch_actor_spans(engine:Engine, year:int, relative_ids=[]) -> DataFrame:
    if relative_ids:
        values = ', '.join(f"('{r}'::uuid)" for r in relative_ids)
        full_join = f'''
        FULL JOIN (SELECT member_id FROM (VALUES {values})
        AS relatives(member_id)) USING (member_id)
        '''
    else:
        full_join = ''

    sql = f'''
    WITH 
      actual_spans AS (
      SELECT member_id, start_time, end_time, span
      FROM project.appearance_spans
        WHERE project_year = {year}
      )

    SELECT member_id, full_name, start_time, end_time, span
    FROM actual_spans {full_join}
      JOIN display_names USING (member_id)
    ;'''
    return read_sql(engine, sql)

def fetch_compilation(engine:Engine, year:int) -> DataFrame:
    sql = f'''
    SELECT file_name, timeline_name, banned_bins
    FROM config.compilations
    WHERE project_year = {year}
    ;'''
    return read_sql(engine, sql)