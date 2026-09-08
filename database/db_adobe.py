from uuid import UUID

from sqlalchemy import Engine
from pandas import DataFrame

from database.db import read_sql, execute_sql, build_values

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

def update_appearances(engine:Engine, df:DataFrame):
    review_id = df['review_id'].iloc[0]
    sql = f'''
    DELETE FROM project.appearances WHERE project_year = '{review_id}'::uuid
    ;'''
    execute_sql(engine, sql)

    val_cols = ['review_id', 'member_id', 'start_time', 'end_time']
    val_ins = ', '.join(val_cols)
    values, params = build_values(df, val_cols)
    sql = f'''
    INSERT INTO project.appearances ({val_ins}) VALUES {values}
    ;'''
    execute_sql(engine, sql, params=params)

def update_chapters(engine:Engine, df:DataFrame):
    review_id = df['review_id'].iloc[0]
    sql = f'''
    DELETE FROM project.chapters WHERE review_id = '{review_id}'::uuid
    ;'''
    execute_sql(engine, sql)

    val_cols = ['review_id', 'chapter_name', 'start_time']
    val_ins = ', '.join(val_cols)
    values, params = build_values(df, val_cols)
    sql = f'''
    INSERT INTO project.chapters ({val_ins}) VALUES {values}
    ;'''
    execute_sql(engine, sql, params=params)

def fetch_timeline_reviews(engine:Engine) -> DataFrame:
    sql = f'''
    SELECT review_id, review_id, review_type, video_theme
    FROM publishing.reviews
    ;'''
    return read_sql(engine, sql)

def fetch_appearance_spans(engine:Engine, review_id:UUID) -> DataFrame:
    sql = f'''
    SELECT member_id, start_time, end_time, span
    FROM dashboard.appearance_spans
    WHERE review_id = '{review_id}'::uuid
    ;'''
    return read_sql(engine, sql)

def fetch_markers(engine:Engine, review_id:UUID) -> DataFrame:
    sql = f'''
    SELECT chapter_name, start_time
    FROM publishing.chapters
    WHERE review_id = '{review_id}'::uuid
    ;'''
    return read_sql(engine, sql)

def fetch_compilation(engine:Engine, project_year:int, review_type:str) -> DataFrame:
    sql = f'''
    SELECT review_id, file_name, timeline_name, banned_bins
    FROM config.compilations JOIN publishing.reviews USING (review_id)
    WHERE project_year = {project_year} AND review_type = '{review_type}'
    ;'''
    return read_sql(engine, sql)

def fetch_music(engine:Engine, project_year:int, review_type:str) -> DataFrame:
    sql = f'''
    SELECT track_id, review_id, project_year,
    track_title, artist_name, track_duration, track_url,
    review_id, main_track, lyrics_url
    FROM publishing.music JOIN publishing.reviews USING (review_id)
    WHERE project_year = {project_year} AND review_type = '{review_type}'
    ;'''
    return read_sql(engine, sql)

# # def update_projects(engine:Engine, df:DataFrame):
# #     val_cols = []
# #     values, params = build_values(df, val_cols)
# #     sql = f'''
# #     INSERT INTO publishing.reviews
# #     (review_type,
# #     project_year,
# #     video_theme,
# #     video_duration,
# #     video_resolution)
    
# #     VALUES {values}
# #     ON CONFLICT (review_type, project_year)
# #     DO UPDATE
# #     SET
# #       video_theme      = COALESCE(review.video_theme,      EXCLUDED.video_theme),
# #       video_duration   = COALESCE(review.video_duration,   EXCLUDED.video_duration),
# #       video_resolution = COALESCE(review.video_resolution, EXCLUDED.video_resolution)
# #     WHERE
# #       (review.video_theme      IS NULL AND EXCLUDED.video_theme      IS NOT NULL)
# #       OR (review.video_duration   IS NULL AND EXCLUDED.video_duration   IS NOT NULL)
# #       OR (review.video_resolution IS NULL AND EXCLUDED.video_resolution IS NOT NULL);
# #     ;'''
