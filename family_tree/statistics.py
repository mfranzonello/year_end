# family_tree.py
from sqlalchemy import create_engine, text
from pandas import read_sql_query

def get_engine(host, port, dbname, user, password):
    engine = create_engine(f'postgresql+psycopg://{user}:{password}@{host}:{port}/{dbname}')
    return engine

def fetch_folders(engine, year):
    sql = f'''
    SELECT folder_name || ' ' || project_year AS folder, display_names.full_name,
    video_count, video_duration
    FROM folders
    JOIN display_names ON person_id = display_id OR animal_id = display_id 
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