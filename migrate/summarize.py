from pathlib import Path

from pandas import DataFrame

from common.system import get_person_name, get_actual_year, get_videos_in_folder, get_file_sizes
from migrate.scan_and_copy import get_person_folders
from adobe.bridge import get_rated_videos, get_video_durations
from family_tree.db import update_folders, update_folder_member_ids

def summarize_folder(person_folder, year, min_stars):
    folder_name = get_person_name(person_folder)
    actual_year = get_actual_year(person_folder)
    year_adjust = actual_year - year if actual_year else None
    
    # count how many files
    videos = get_videos_in_folder(person_folder)
    video_count = len(videos)

    # sum how long videos are
    video_durations = get_video_durations(videos)
    video_duration = sum(video_durations)

    video_file_sizes = get_file_sizes(videos)
    video_file_size = sum(video_file_sizes)

    # count how many are rated
    rated_videos, video_ratings = get_rated_videos(videos, min_stars)
  
    usable_count = len(video_ratings)
    review_count = len(rated_videos)
    used_count = None ## need to check Adobe Premiere project file

    return folder_name, year, year_adjust, video_count, video_duration, video_file_size, review_count, usable_count, used_count

def summarize_folders(engine, one_drive_folder, year, min_stars, dry_run=False):
    columns = ['folder_name', 'project_year', 'year_adjust', 'video_count', 'video_duration', 'file_size', 'review_count', 'usable_count', 'used_count']
    folders_df = DataFrame(columns = columns)
    for person_folder in get_person_folders(one_drive_folder / str(year)):
        folders_df.loc[len(folders_df), columns] = summarize_folder(person_folder, year, min_stars)

    if not dry_run:
        update_folders(engine, folders_df)
        update_folder_member_ids(engine)