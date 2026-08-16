from uuid import uuid4

from numpy import median
from sqlalchemy import Engine, text
from pandas import DataFrame, read_sql_query

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
    video_count, video_duration, file_size,
    rating_count, resolution_count
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

def fetch_project_folders(engine: Engine, project_year: int, media_type: str) -> DataFrame:
    """Return project folders that need repository-location reconciliation."""
    sql = '''
    SELECT folder_id, folder_name, project_year, media_type
    FROM project.folders
    WHERE project_year = :project_year
      AND media_type = :media_type
      AND folder_name IS NOT NULL
    ORDER BY folder_name
    ;'''
    with engine.begin() as conn:
        return read_sql_query(
            text(sql),
            conn,
            params={"project_year": project_year, "media_type": media_type},
        )

def update_folder_locations_and_shares(
    engine: Engine,
    folders: DataFrame,
    repository_name: str,
    is_canonical: bool,
) -> None:
    """Persist provider folder IDs and their active share URLs."""
    if folders.empty:
        return

    rows = folders.to_dict(orient="records")
    with engine.begin() as conn:
        repository_id = conn.execute(
            text('''
            SELECT repository_id
            FROM ingestion.repositories
            WHERE repository_name = :repository_name
            ;'''),
            {"repository_name": repository_name},
        ).scalar_one()

        for row in rows:
            existing_locations = conn.execute(
                text('''
                SELECT folder_location_id
                FROM project.folder_locations
                WHERE folder_id = :folder_id
                  AND repository_id = :repository_id
                ;'''),
                {"folder_id": row["folder_id"], "repository_id": repository_id},
            ).scalars().all()
            if len(existing_locations) > 1:
                raise ValueError(
                    "A project folder has multiple locations in the same repository"
                )

            if existing_locations:
                location_id = conn.execute(
                    text('''
                    UPDATE project.folder_locations
                    SET repository_item_id = :repository_item_id,
                        is_canonical = :is_canonical
                    WHERE folder_location_id = :folder_location_id
                    RETURNING folder_location_id
                    ;'''),
                    {
                        "folder_location_id": existing_locations[0],
                        "repository_item_id": row["repository_item_id"],
                        "is_canonical": is_canonical,
                    },
                ).scalar_one()
            else:
                location_id = conn.execute(
                    text('''
                INSERT INTO project.folder_locations (
                    folder_location_id, folder_id, repository_id,
                    repository_item_id, is_canonical
                )
                VALUES (
                    :folder_location_id, :folder_id, :repository_id,
                    :repository_item_id, :is_canonical
                )
                ON CONFLICT (repository_id, repository_item_id) DO UPDATE
                SET folder_id = EXCLUDED.folder_id,
                    is_canonical = EXCLUDED.is_canonical
                RETURNING folder_location_id
                ;'''),
                    {
                        "folder_location_id": uuid4(),
                        "folder_id": row["folder_id"],
                        "repository_id": repository_id,
                        "repository_item_id": row["repository_item_id"],
                        "is_canonical": is_canonical,
                    },
                ).scalar_one()
            conn.execute(
                text('''
                UPDATE project.shares
                SET is_active = false,
                    last_verified_at = CURRENT_TIMESTAMP
                WHERE folder_location_id = :folder_location_id
                  AND share_url <> :share_url
                  AND is_active = true
                ;'''),
                {"folder_location_id": location_id, "share_url": row["share_url"]},
            )
            conn.execute(
                text('''
                INSERT INTO project.shares (
                    folder_location_id, share_url, is_active,
                    expires_at, last_verified_at
                )
                VALUES (
                    :folder_location_id, :share_url, true,
                    NULL, CURRENT_TIMESTAMP
                )
                ON CONFLICT (folder_location_id, share_url) DO UPDATE
                SET is_active = true,
                    expires_at = NULL,
                    last_verified_at = CURRENT_TIMESTAMP
                ;'''),
                {"folder_location_id": location_id, "share_url": row["share_url"]},
            )
