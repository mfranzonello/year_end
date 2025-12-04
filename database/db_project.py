from sqlalchemy import Engine
from pandas import DataFrame

from database.db import read_sql, execute_sql, build_values

# YIR project
def fetch_years(engine:Engine) -> DataFrame:
    sql = f'''
    SELECT DISTINCT project_year
    FROM project.folders_summary
    ORDER BY project_year ASC
    ;'''
    return read_sql(engine, sql)

def fetch_folder_summaries(engine:Engine, year:int) -> DataFrame:
    sql = f'''
    SELECT project_year, folder_name, full_name, member_id,
    video_count, video_duration, file_size, review_count, usable_count, used_count
    FROM project.folders_summary
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
    FROM project.files JOIN project.folders USING(folder_id)
        WHERE project_year = {year}
    GROUP BY project_year;
    '''
    return read_sql(engine, sql)

def fetch_known_folders(engine:Engine) -> DataFrame:
    sql = f'''
    SELECT folder_id, folder_name, project_year
    FROM project.folders
    ;'''
    return read_sql(engine, sql)

def fetch_known_files(engine:Engine, year:int) -> DataFrame: ## consider having this be all years
    sql = f'''
    SELECT file_id, folder_name, project_year, file_name, subfolder_name
    FROM project.files JOIN project.folders USING (folder_id)
    WHERE project_year = {year}
    ;'''
    return read_sql(engine, sql)

def fetch_files(engine:Engine, year:int) -> DataFrame:
    sql = f'''
    SELECT file_id, folder_name, project_year, file_name, subfolder_name,
    file_size, video_date, video_duration, video_resolution, video_rating, used_status
    FROM project.files JOIN project.folders USING (folder_id)
    WHERE project_year = {year}
    ;'''
    return read_sql(engine, sql)

# # def fetch_member_ids(engine:Engine, member_type:str) -> DataFrame:
# #     sql = f'''
# #     SELECT {member_type}_id FROM {member_type}s
# #     ;'''
# #     return read_sql(engine, sql)

def fetch_all_member_ids(engine:Engine) -> DataFrame:
    sql = f'''
    SELECT person_id AS member_id FROM persons
    UNION
    SELECT animal_id AS member_id FROM animals
    UNION
    SELECT source_id AS source_id FROM project.sources
    ;'''
    return read_sql(engine, sql)

def update_folders(engine:Engine, df:DataFrame):
    # add new folder information
    sql = f'''
    INSERT INTO project.folders (folder_name, project_year)
    VALUES (:folder_name, :project_year)
    ON CONFLICT (folder_name, project_year) DO NOTHING
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
    WHERE f.folder_name  = :folder_name
        AND f.project_year = :project_year
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
    SELECT  f.folder_id,
        :subfolder_name,
        :file_name,
        :file_size
    FROM project.folders f
    WHERE f.folder_name  = :folder_name
        AND f.project_year = :project_year
    ON CONFLICT (folder_id, subfolder_name, file_name) DO UPDATE

    SET file_size = EXCLUDED.file_size
    ;'''
    execute_sql(engine, sql, df=df[df['stored']=='cloud'])

def purge_folders(engine:Engine, df:DataFrame):
    # remove stale folder_ids
    values, params = build_values(df, ['folder_id'])
    sql = f'''
    DELETE FROM project.folders 
    WHERE (folder_name, project_year) IN (VALUES {values})
    ;'''
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
    UPDATE project.files fi
    SET used_status = :used_status
    FROM project.folders fo
    WHERE fi.folder_id   = fo.folder_id
        AND subfolder_name = :subfolder_name
        AND fo.folder_name = :folder_name
        AND fo.project_year = :project_year
        AND fi.file_name    = :file_name;
    '''
    execute_sql(engine, sql, df=df)

def fetch_files_scanned(engine):
    sql = f'''
    SELECT folder_name, project_year, subfolder_name, file_name, video_duration, video_resolution
    FROM project.files JOIN project.folders USING (folder_id)
    WHERE video_duration IS NOT NULL AND video_resolution IS NOT NULL;
    '''
    return read_sql(engine, sql)

def fetch_duplicates(engine):
    sql = f'''
    SELECT folder_name, project_year, duplicate_reasons, potential_duplicates
    FROM project.duplicates_summary
    '''
    return read_sql(engine, sql)

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
      FROM project.folders AS f_old
      CROSS JOIN LATERAL (
        SELECT {f_ref_sub_ids}
        FROM project.folders AS f_ref
        WHERE f_ref.folder_name = f_old.folder_name
          AND num_nonnulls({f_ref_sub_ids}) = 1
        ORDER BY
          ABS(f_ref.project_year - f_old.project_year) ASC,
          f_ref.project_year DESC
        LIMIT 1
      ) AS ref
      WHERE num_nonnulls({f_old_sub_ids}) = 0
    )
    UPDATE project.folders AS f
    SET {set_sub_ids}
    FROM to_fill
    WHERE f.folder_id = to_fill.folder_id
    RETURNING f.folder_id, f.folder_name, f.project_year, {f_sub_ids}
    ;'''
    rows = execute_sql(engine, sql, returning=True)

    changes_df = DataFrame(rows, columns=['folder_id', 'folder_name', 'project_year'] + [f'{j}_id' for j in member_types])

    return changes_df

def fetch_shared_albums(engine:Engine) -> DataFrame:
    sql = f'''
    SELECT album_id, share_url, folder_name, project_year,
    scrape_name, browser_name, profile_name, notes
    FROM ingestion.shared_album_details
    ;'''
    return read_sql(engine, sql)

def fetch_year_summaries(engine:Engine) -> DataFrame:
    sql = f'''
    SELECT project_year, total_folders, total_videos, total_duration, total_file_size,
    resolution_na, resolution_lo, resolution_md, resolution_hi
    FROM project.years_summary
    ;'''
    return read_sql(engine, sql)

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