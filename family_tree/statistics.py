# family_tree.py
from sqlalchemy import create_engine, text
from pandas import read_sql_query

from common.secret import get_secret

def get_engine():
    HOST = get_secret('PGHOST')
    PORT = get_secret('PGPORT', '5432')
    DBNAME = get_secret('PGDATABASE')
    USER = get_secret('PGUSER')
    PASSWORD = get_secret('PGPASSWORD')

    engine = create_engine(f'postgresql+psycopg2://{USER}:{PASSWORD}@{HOST}:{PORT}/{DBNAME}')
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
    sql = text(f'''
    INSERT INTO folders (folder_name, project_year, video_count, review_count)
    VALUES (:folder_name, :project_year, :video_count, :review_count)
    ON CONFLICT (folder_name, project_year) DO
    UPDATE SET
        video_count = :video_count,
        review_count = :review_count
    WHERE folders.folder_name = :folder_name AND folders.project_year = :project_year
    ;
    ''')
    
    with engine.begin() as conn:
        for _, row in df.iterrows():
            conn.execute(sql, row.to_dict())