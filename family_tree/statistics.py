# family_tree.py
import psycopg

from secret import get_secret

def get_dsn():
    return psycopg.conninfo.make_conninfo(
        host=get_secret('PGHOST'),
        port=get_secret('PGPORT', '5432'),
        dbname=get_secret('PGDATABASE'),
        user=get_secret('PGUSER'),
        password=get_secret('PGPASSWORD'),
        sslmode='require',
    )

def fetch_folder_summary(conn, year):
    with conn.cursor() as cur:
        cur.execute(f'''
        SELECT folder_name || ' ' || project_year AS folder, display_names.full_name,
        video_count, video_duration
        FROM folders
        JOIN display_names ON person_id = display_id OR animal_id = display_id 
        WHERE project_year = {year};
        ''')
        
        values = cur.fetchall()

    return values

def get_summaries(year):
    dsn = get_dsn()
    with psycopg.connect(dsn) as conn:
        values = fetch_folder_summary(conn, year)

    return values