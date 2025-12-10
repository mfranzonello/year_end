from numpy import median
from sqlalchemy import Engine
from pandas import DataFrame

from database.db import read_sql, execute_sql, build_values

# YIR project
def fetch_project_years(engine:Engine) -> DataFrame:
    sql = f'''
    SELECT DISTINCT project_year
    FROM project.folders_summary
    ORDER BY project_year ASC
    ;'''
    return read_sql(engine, sql)

def fetch_folder_summaries(engine:Engine, year:int) -> DataFrame:
    sql = f'''
    SELECT project_year, folder_name, media_type, full_name, member_id,
    video_count, video_duration, file_size, review_count, usable_count, used_count
    FROM project.folders_summary
    WHERE project_year = {year}
    ;'''
    return read_sql(engine, sql)

def fetch_known_folders(engine:Engine, media_type:str) -> DataFrame:
    sql = f'''
    SELECT folder_id, folder_name, project_year, media_type
    FROM project.folders
    WHERE media_type = '{media_type}'
    ;'''
    return read_sql(engine, sql)

def fetch_known_files(engine:Engine, year:int, media_type:str) -> DataFrame: ## consider having this be all years
    sql = f'''
    SELECT file_id, folder_name, project_year, media_type, file_name, subfolder_name
    FROM project.files JOIN project.folders USING (folder_id)
    WHERE project_year = {year}
    AND media_type = '{media_type}'
    ;'''
    return read_sql(engine, sql)

def fetch_files(engine:Engine, year:int, media_type:str) -> DataFrame:
    sql = f'''
    SELECT file_id, folder_name, project_year, media_type, file_name, subfolder_name,
    file_size, video_date, video_duration, video_resolution, video_rating, used_status
    FROM project.files JOIN project.folders USING (folder_id)
    WHERE project_year = {year}
    AND media_type = '{media_type}'
    ;'''
    return read_sql(engine, sql)

def update_folders(engine:Engine, df:DataFrame):
    # add new folder information
    sql = f'''
    INSERT INTO project.folders (folder_name, project_year, media_type)
    VALUES (:folder_name, :project_year, :media_type)
    ON CONFLICT (folder_name, project_year, media_type) DO NOTHING
    ;'''
    execute_sql(engine, sql, df=df)

def update_files(engine:Engine, df:DataFrame):
    # locally stored
    sql = f'''
    INSERT INTO project.files (
    folder_id,
    subfolder_name,
    file_name,
    file_size,
    video_date,
    video_duration,
    video_resolution,
    video_rating
    )
    SELECT
        f.folder_id,
        :subfolder_name,
        :file_name,
        :file_size,
        :video_date,
        :video_duration,
        :video_resolution,
        :video_rating
    FROM project.folders f
    WHERE f.folder_name IS NOT DISTINCT FROM :folder_name
        AND f.project_year = :project_year
        AND f.media_type = :media_type
    ON CONFLICT (folder_id, subfolder_name, file_name) DO UPDATE

    SET file_size = EXCLUDED.file_size,
        video_date = EXCLUDED.video_date,
        video_duration = EXCLUDED.video_duration,
        video_resolution = EXCLUDED.video_resolution,
        video_rating = EXCLUDED.video_rating
    ;'''
    execute_sql(engine, sql, df=df[df['stored']=='local'])

    # cloud stored
    sql = f'''
    INSERT INTO project.files (folder_id, subfolder_name, file_name, file_size)
    SELECT f.folder_id,
        :subfolder_name,
        :file_name,
        :file_size
    FROM project.folders f
    WHERE f.folder_name IS NOT DISTINCT FROM :folder_name
        AND f.project_year = :project_year
        AND f.media_type = :media_type
    ON CONFLICT (folder_id, subfolder_name, file_name) DO UPDATE

    SET file_size = EXCLUDED.file_size
    ;'''
    execute_sql(engine, sql, df=df[df['stored']=='cloud'])

def purge_folders(engine:Engine, df:DataFrame):
    # remove stale folder_ids
    values, params = build_values(df, ['folder_id'])
    sql = f'''
    DELETE FROM project.folders WHERE folder_id IN (VALUES {values})
    ;''' # (folder_name, project_year, media_type) IN (VALUES {values})
    execute_sql(engine, sql, params=params)

def purge_files(engine:Engine, df:DataFrame):
    # remove stale file_ids
    values, params = build_values(df, ['file_id'])
    sql = f'''
    DELETE FROM project.files WHERE file_id IN (VALUES {values})
    ;'''
    execute_sql(engine, sql, params=params)
    
def update_files_used(engine:Engine, df:DataFrame):
    sql = f'''
    UPDATE project.files
    SET used_status = :used_status
    WHERE file_id = :file_id
    ;'''
    execute_sql(engine, sql, df=df)

def fetch_files_scanned(engine:Engine, media_type:str):
    sql = f'''
    SELECT folder_name, project_year, media_type, subfolder_name, file_name, video_duration, video_resolution
    FROM project.files JOIN project.folders USING (folder_id)
    WHERE video_duration IS NOT NULL AND video_resolution IS NOT NULL
    AND media_type = '{media_type}'
    ;'''
    return read_sql(engine, sql)

def fetch_duplicates(engine:Engine, media_type:str):
    sql = f'''
    SELECT folder_name, project_year, media_type, flags, duplicates_sorted
    FROM project.duplicates_summary
    WHERE media_type = '{media_type}'
    ;'''
    return read_sql(engine, sql)

def fetch_shared_albums(engine:Engine) -> DataFrame:
    sql = f'''
    SELECT album_id, share_url, folder_name, project_year, supfolder_name,
    scrape_name, browser_name, profile_name, notes
    FROM ingestion.shared_album_details
    ;'''
    return read_sql(engine, sql)

def fetch_years_summary(engine:Engine) -> DataFrame:
    sql = f'''
    SELECT project_year, total_folders, total_videos, total_duration, total_file_size,
    video_resolutions, video_status 
    FROM project.years_summary
    ;'''
    return read_sql(engine, sql)

def fetch_media_types(engine:Engine) -> DataFrame:
    sql = f'''
    SELECT media_type, supfolder_name
    FROM config.media
    ORDER BY medium_id
    ;'''
    return read_sql(engine, sql)