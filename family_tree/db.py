from sqlalchemy import create_engine, text
from pandas import read_sql_query, DataFrame

def get_engine(host, port, dbname, user, password):
    engine = create_engine(f'postgresql+psycopg://{user}:{password}@{host}:{port}/{dbname}')
    return engine

def read_sql(engine, sql):
    with engine.begin() as conn:
        df = read_sql_query(text(sql), conn)

    return df


# Family Tree
def fetch_persons(engine):
    sql = f'''SELECT person_id,
    first_name, last_name, nick_name, suffix,
    birth_date, birth_date_precision
    FROM persons
    '''
    return read_sql(engine, sql)

def fetch_animals(engine):
    sql = f'''SELECT animal_id,
    first_name, nick_name, species
    FROM animals
    '''
    return read_sql(engine, sql)

def fetch_parents(engine):
    sql = f'''SELECT child_id, parent_id
    FROM parents
    '''
    return read_sql(engine, sql)

def fetch_pets(engine):
    sql = f'''SELECT pet_id, owner_id, relation_type,
    gotcha_date, gotcha_date_precision
    FROM pets
    '''
    return read_sql(engine, sql)

def fetch_marriages(engine):
    sql = f'''SELECT husband_id, wife_id, marriage_id
    FROM marriages
    '''
    return read_sql(engine, sql)


# Adobe project
def fetch_years(engine):
    sql = f'''
    SELECT DISTINCT project_year
    FROM folders_summary
    ORDER BY project_year ASC
    ;
    '''
    return read_sql(engine, sql)

def fetch_folders(engine, year, cloud=None):
    sql = text(f'''
    SELECT project_year, year_adjust, folder_name, full_name,
    video_count, video_duration, file_size, review_count, usable_count, member_id
    FROM folders_summary
    WHERE project_year = {year};
    ''')

    with engine.begin() as conn:
        values = read_sql_query(sql, conn)

    return values

def fetch_member_ids(engine, member_type):
    sql = f'''
    SELECT {member_type}_id FROM {member_type}s
    '''
    return read_sql(engine, sql)

def update_folders(engine, df):
    keys = ['folder_name', 'project_year']
    cols = [c for c in df.columns if c not in keys]
    sql = text(f'''
    INSERT INTO folders ({", ".join(keys + cols)})
    VALUES ({", ".join(":" + c for c in keys + cols)})
    ON CONFLICT ({", ".join(keys)}) DO
    UPDATE SET {", ".join(c + " = :" + c for c in cols)}
    ;
    ''')
    
    with engine.begin() as conn:
        for _, row in df.iterrows():
            conn.execute(sql, row.to_dict())

def update_images(engine, df, member_type):
    sql = text(f'''
    INSERT INTO pictures ({member_type}_id, image_url)
    VALUES (:{member_type}_id, :image_url)
    ON CONFLICT ({member_type}_id) DO
    UPDATE SET image_url = :image_url
    ;
    ''')

    with engine.begin() as conn:
        for _, row in df.iterrows():
            conn.execute(sql, row.to_dict())

def update_folder_member_ids(engine):
    ''' Guess what the best member_ids are based on other years already identified '''
    member_types = ['person', 'animal', 'source']
    set_sub_ids = ', '.join(f'{k} = to_fill.{k}' for j in member_types if (k := f'{j}_id'))
    f_ref_sub_ids = ', '.join(f'f_ref.{j}_id' for j in member_types)
    f_old_sub_ids = ', '.join(f'f_old.{j}_id' for j in member_types)
    ref_sub_ids = ', '.join(f'ref.{j}_id' for j in member_types)
    f_sub_ids = ', '.join(f'f.{j}_id' for j in member_types)

    sql = text(f'''
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
    ;''')

    with engine.begin() as conn:
        rows = conn.execute(sql).fetchall()

    changes_df = DataFrame(rows, columns=['folder_id', 'folder_name', 'project_year'] + [f'{j}_id' for j in member_types])

    return changes_df