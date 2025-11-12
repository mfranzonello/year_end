from sqlalchemy import create_engine, text
from pandas import read_sql_query

def get_engine(host, port, dbname, user, password):
    engine = create_engine(f'postgresql+psycopg://{user}:{password}@{host}:{port}/{dbname}')
    return engine

def fetch_years(engine):
    sql = f'''
    SELECT DISTINCT project_year
    FROM folders_summary
    ;
    '''

    with engine.begin() as conn:
        years = read_sql_query(sql, conn)

    return years

def fetch_folders(engine, year, cloud=None):
    sql = f'''
    SELECT project_year, folder_name, full_name,
    video_count, video_duration, review_count, usable_count, image_url
    FROM folders_summary
    WHERE project_year = {year};
    '''

    with engine.begin() as conn:
        values = read_sql_query(sql, conn)

    return values

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

def get_member_ids(engine, member_type):
    sql = text(f'''
    SELECT {member_type}_id FROM {member_type}s
    ''')

    with engine.begin() as conn:
        return read_sql_query(sql, conn)

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