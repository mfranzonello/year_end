from pathlib import Path

from pandas import DataFrame

from common.structure import ONE_DRIVE_FOLDER, YIR_CLIPS
from common.system import get_person_name, get_videos_in_folder
from migrate.scan_and_copy import get_person_folders
from adobe.bridge import get_rated_videos, get_video_durations
from family_tree.db import update_folders, get_member_ids, update_images
from family_tree.cloudinary import configure_cloud, fetch_image_url

def summarize_folder(person_folder, year, min_stars):
    folder_name = get_person_name(person_folder, year)
    # count how many files
    videos = get_videos_in_folder(person_folder)
    video_count = len(videos)

    # sum how long videos are
    video_durations = get_video_durations(person_folder)
    video_duration = sum(video_durations)

    # count how many are rated
    rated_videos, video_ratings = get_rated_videos(person_folder, min_stars)
  
    usable_count = len(video_ratings)
    review_count = len(rated_videos)
    used_count = None ## need to check Adobe Premiere project file

    return folder_name, year, video_count, video_duration, review_count, usable_count, used_count

def summarize_folders(engine, year, min_stars, dry_run=False):
    columns = ['folder_name', 'project_year', 'video_count', 'video_duration', 'review_count', 'usable_count', 'used_count']
    folders_df = DataFrame(columns = columns)
    for person_folder in get_person_folders(Path(ONE_DRIVE_FOLDER) / YIR_CLIPS / str(year)):
        folders_df.loc[len(folders_df), columns] = summarize_folder(person_folder, year, min_stars)

    if not dry_run:
        update_folders(engine, folders_df)

def update_cloud_images(engine, cloud_name, cloud_key, cloud_secret):
    configure_cloud(cloud_name, cloud_key, cloud_secret)

    for member_type in ['person', 'animal']: # object
        member_ids = get_member_ids(engine, member_type)
        member_ids['image_url'] = member_ids.apply(lambda x: fetch_image_url(str(x[f'{member_type}_id'])), axis=1)
        new_images = member_ids.dropna(subset=['image_url'])
        update_images(engine, new_images, member_type)