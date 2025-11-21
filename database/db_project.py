from sqlalchemy import Engine
from pandas import DataFrame

from database.db import read_sql, execute_sql, build_values

# Adobe project
def fetch_years(engine:Engine) -> DataFrame:
    sql = f'''
    SELECT DISTINCT project_year
    FROM folders_summary
    ORDER BY project_year ASC
    ;'''
    return read_sql(engine, sql)

def fetch_folder_summaries(engine:Engine, year:int) -> DataFrame:
    sql = f'''
    SELECT project_year, folder_name, full_name, member_id,
    video_count, video_duration, file_size, review_count, usable_count, used_count
    FROM folders_summary
    WHERE project_year = {year}
    ;'''
    return read_sql(engine, sql)

def fetch_usable_summary(engine:Engine, year:int, min_stars:int) -> DataFrame:
    sql = f'''
    SELECT project_year,
    COUNT(file_id) - SUM (GREATEST (
        CASE WHEN video_rating > 0 THEN 1 ELSE 0 END,
        CASE WHEN video_rating >= {min_stars} THEN 1 ELSE 0 END,
        CASE WHEN used_status THEN 1 ELSE 0 END
    )) AS no_count,
    SUM(CASE WHEN video_rating > 0 THEN 1 ELSE 0 END) - SUM (GREATEST (
        CASE WHEN video_rating >= {min_stars} THEN 1 ELSE 0 END,
        CASE WHEN used_status THEN 1 ELSE 0 END
    )) AS lo_count,
    SUM(CASE WHEN video_rating >= {min_stars} THEN 1 ELSE 0 END) - SUM (
        CASE WHEN used_status THEN 1 ELSE 0 END
    ) as hi_count,
    SUM(CASE WHEN used_status THEN 1 ELSE 0 END) as go_count
    FROM files JOIN folders USING(folder_id)
        WHERE project_year = {year}
    GROUP BY project_year;
    '''
    return read_sql(engine, sql)

def fetch_files(engine:Engine, year:int) -> DataFrame:
    sql = f'''
    SELECT file_id, folder_name, project_year, file_name, file_size,
    video_duration, video_resolution, video_rating, used_status
    FROM files JOIN folders USING (folder_id)
    WHERE project_year = {year}
    ;'''
    return read_sql(engine, sql)

def fetch_member_ids(engine:Engine, member_type:str) -> DataFrame:
    sql = f'''
    SELECT {member_type}_id FROM {member_type}s
    ;'''
    return read_sql(engine, sql)

def fetch_all_member_ids(engine:Engine) -> DataFrame:
    sql = f'''
    SELECT person_id AS member_id FROM persons
    UNION
    SELECT animal_id AS member_id FROM animals
    UNION
    SELECT source_id AS source_id FROM sources
    ;'''
    return read_sql(engine, sql)


def update_folders(engine:Engine, df:DataFrame):
    # add new folder information
    sql = f'''
    INSERT INTO folders (folder_name, project_year)
    VALUES (:folder_name, :project_year)
    ON CONFLICT (folder_name, project_year) DO NOTHING
    ;'''
    execute_sql(engine, sql, df=df)

def update_files(engine:Engine, df:DataFrame):
    # locally stored
    sql = f'''
    INSERT INTO files (
    folder_id,
    file_name,
    file_size,
    video_duration,
    video_resolution,
    video_rating
    )
    SELECT
        f.folder_id,
        :file_name,
        :file_size,
        :video_duration,
        :video_resolution,
        :video_rating
    FROM folders f
    WHERE f.folder_name  = :folder_name
      AND f.project_year = :project_year
    ON CONFLICT (folder_id, file_name) DO UPDATE

    SET file_size        = EXCLUDED.file_size,
        video_duration   = EXCLUDED.video_duration,
        video_resolution = EXCLUDED.video_resolution,
        video_rating     = EXCLUDED.video_rating
    ;'''
    execute_sql(engine, sql, df=df[df['stored']=='local'])

    # cloud stored
    sql = f'''
    INSERT INTO files (
    folder_id,
    file_name
    )
    SELECT
        f.folder_id,
        :file_name
    FROM folders f
    WHERE f.folder_name  = :folder_name
      AND f.project_year = :project_year
    ON CONFLICT (folder_id, file_name) DO NOTHING
    ;'''
    execute_sql(engine, sql, df=df[df['stored']=='cloud'])

def build_values(df: DataFrame, cols:list[str]) -> tuple[str, dict[str, object]]:
    # get values and params for complex calls
    value_clauses = []
    params: dict[str, object] = {}

    for idx, row in df[cols].iterrows():
        append_string = ', '.join(f':{c}_{idx}' for c in cols)
        value_clauses.append(f'({append_string})')
        for c in cols:
            params[f'{c}_{idx}'] = row[f'{c}_{idx}']
        
    values = ', '.join(value_clauses)

    return values, params

def purge_folders(engine:Engine, df:DataFrame):
    # remove stale folder_ids
    # Build VALUES list with bind params instead of literal strings
    values, params = build_values(df, ['folder_name', 'project_year'])
    sql = f'''
    DELETE FROM folders 
    WHERE (folder_name, project_year) NOT IN (VALUES {values})
    ;'''
    execute_sql(engine, sql, params=params)

def purge_files(engine:Engine, df:DataFrame):
    # remove stale file_ids
    values, params = build_values(df, ['folder_name', 'file_name', 'project_year'])
    sql = f'''
    WITH files_to_keep AS (
    SELECT file_id FROM files JOIN folders USING (folder_id) WHERE
    (folder_name, project_year, file_name) IN (VALUES {values})  
    )
    
    DELETE FROM files WHERE file_id NOT IN (SELECT file_id FROM files_to_keep)
    ;'''
    execute_sql(engine, sql, params=params)
    
def update_files_used(engine:Engine, df:DataFrame):
    sql = f'''
    UPDATE files fi
    SET used_status = :used_status
    FROM folders fo
    WHERE fi.folder_id   = fo.folder_id
      AND fo.folder_name = :folder_name
      AND fo.project_year = :project_year
      AND fi.file_name    = :file_name;
    '''
    execute_sql(engine, sql, df=df)

def update_folder_member_ids(engine:Engine) -> DataFrame:
    ''' Guess what the best member_ids are based on other years already identified '''
    member_types = ['person', 'animal', 'source']
    set_sub_ids = ', '.join(f'{k} = to_fill.{k}' for j in member_types if (k := f'{j}_id'))
    f_ref_sub_ids = ', '.join(f'f_ref.{j}_id' for j in member_types)
    f_old_sub_ids = ', '.join(f'f_old.{j}_id' for j in member_types)
    ref_sub_ids = ', '.join(f'ref.{j}_id' for j in member_types)
    f_sub_ids = ', '.join(f'f.{j}_id' for j in member_types)

    sql = f'''
    WITH to_fill AS (
      SELECT f_old.folder_id,
             f_old.folder_name,
             f_old.project_year,
             {ref_sub_ids}
      FROM folders AS f_old
      CROSS JOIN LATERAL (
        SELECT {f_ref_sub_ids}
        FROM folders AS f_ref
        WHERE f_ref.folder_name = f_old.folder_name
          AND num_nonnulls({f_ref_sub_ids}) = 1
        ORDER BY
          ABS(f_ref.project_year - f_old.project_year) ASC,
          f_ref.project_year DESC
        LIMIT 1
      ) AS ref
      WHERE num_nonnulls({f_old_sub_ids}) = 0
    )
    UPDATE folders AS f
    SET {set_sub_ids}
    FROM to_fill
    WHERE f.folder_id = to_fill.folder_id
    RETURNING f.folder_id, f.folder_name, f.project_year, {f_sub_ids}
    ;'''
    rows = execute_sql(engine, sql, returning=True)

    changes_df = DataFrame(rows, columns=['folder_id', 'folder_name', 'project_year'] + [f'{j}_id' for j in member_types])

    return changes_df