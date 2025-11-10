from pathlib import Path

from pandas import DataFrame

from common.system import get_person_name, get_videos_in_folder
from migrate.scan_and_copy import get_person_folders
from adobe.bridge import get_rated_videos
from family_tree.statistics import update_folders
from common.structure import ONE_DRIVE_FOLDER, YIR_CLIPS

def summarize_folder(person_folder, year, min_stars):
    folder_name = get_person_name(person_folder, year)
    # count how many files
    videos = get_videos_in_folder(person_folder)
    video_count = len(videos)
    video_duration = None ## need to check xmp data?

    # count how many are rated
    rated_videos, video_ratings = get_rated_videos(person_folder, min_stars)
    review_count = len(rated_videos)
    useable_count = len(video_ratings)
    used_count = None ## need to check Adobe Premiere project file

    return folder_name, year, video_count, video_duration, review_count, useable_count, used_count

def summarize_folders(engine, year, min_stars):
    columns = ['folder_name', 'project_year', 'video_count', 'video_duration', 'review_count', 'useable_count', 'used_count']
    folders_df = DataFrame(columns = columns)
    for person_folder in get_person_folders(Path(ONE_DRIVE_FOLDER) / YIR_CLIPS / str(year)):
        folders_df.loc[len(folders_df), columns] = summarize_folder(person_folder, year, min_stars)

    update_folders(engine, folders_df)