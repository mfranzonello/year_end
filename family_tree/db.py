from sqlalchemy import create_engine, text, Engine
from pandas import read_sql_query, DataFrame

def get_engine(host:str, port:str, dbname:str, user:str, password:str):
    engine = create_engine(f'postgresql+psycopg://{user}:{password}@{host}:{port}/{dbname}')
    return engine

def read_sql(engine:Engine, sql:str) -> DataFrame:
    with engine.begin() as conn:
        df = read_sql_query(text(sql), conn)

    return df

def execute_sql(engine:Engine, sql:str, params:dict|None=None,
                df:DataFrame|None=None, returning:bool=False):
    if isinstance(params, dict):
        with engine.begin() as conn:
            result = conn.execute(text(sql), params or {})

    elif isinstance(df, DataFrame):
        if not df.empty:
            rows = df.to_dict(orient="records")
            with engine.begin() as conn:
                result = conn.execute(text(sql), rows)
        else:
            result = None

    else:
        with engine.begin() as conn:
            result = conn.execute(text(sql))

    if returning and result:
        return result.fetchall()

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

def purge_folders(engine:Engine, df:DataFrame):
    # remove stale folder_ids
    # Build VALUES list with bind params instead of literal strings
    value_clauses = []
    params: dict[str, object] = {}

    for idx, row in enumerate(df[['folder_name', 'project_year']].itertuples(index=False)):
        name_key = f'name_{idx}'
        year_key = f'year_{idx}'
        value_clauses.append(f'(:{name_key}, :{year_key})')
        params[name_key] = row.folder_name
        params[year_key] = row.project_year

    values = ', '.join(value_clauses)

    sql = f'''
    DELETE FROM folders 
    WHERE (folder_name, project_year) NOT IN (
        VALUES {values}
    )
    ;'''
    execute_sql(engine, sql, params=params)

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

def purge_files(engine:Engine, df:DataFrame):
    # # # remove stale file_ids
    # # sql = '''
    # # WITH data AS (
    # #     SELECT *
    # #     FROM json_to_recordset(:rows_json) AS d (
    # #         folder_name   text,
    # #         project_year  int,
    # #         file_name     text
    # #     )
    # # )
    # # DELETE FROM files fi
    # # USING folders fo
    # # LEFT JOIN data d
    # #     ON d.folder_name  = fo.folder_name
    # #     AND d.project_year = fo.project_year
    # #     AND d.file_name    = fi.file_name
    # # WHERE fi.folder_id = fo.folder_id
    # #     -- limit to the folder/year you're processing:
    # #     AND fo.folder_name  = :folder_name
    # #     AND fo.project_year = :project_year
    # #     -- keep only those that are *not* in the dataset
    # #     AND d.file_name IS NULL
    # # ;'''
    # # execute_sql(engine, sql, df=df)
    return
    
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