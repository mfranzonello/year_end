from pathlib import Path

from pandas import DataFrame, concat
from sqlalchemy import Engine

from common.system import get_person_name, get_actual_year, get_videos_in_folder
from repositories.migrate import dedupe_folder, get_year_folders, get_person_folders
from adobe.bridge import get_video_rating, get_video_cv2_details, is_file_available
from family_tree.db import update_folders, update_files, update_folder_member_ids, fetch_all_member_ids
from family_tree.cloudinary_heavy import configure_cloud, fill_in_temp_pictures

def summarize_files(folder_name:str, video_files:list[Path], year:int) -> DataFrame:
    files_df = DataFrame()

    files_df['full_path'] = video_files
    files_df['file_name'] = files_df['full_path'].apply(lambda x: x.name)
    files_df['folder_name'] = folder_name
    files_df['project_year'] = year
    files_df['file_size'] = files_df['full_path'].apply(lambda x: round(x.stat().st_size / 1e6, 1)) # store in MB
    files_df[['video_duration', 'video_resolution']] = files_df.apply(lambda x: get_video_cv2_details(x['full_path']), axis=1, result_type='expand').values ## get in one cv2 take   
    files_df['video_duration'] = files_df['video_duration'].astype('Int64')
    files_df['video_resolution'] = files_df['video_resolution'].astype('string')
    files_df['video_rating'] = files_df['full_path'].apply(get_video_rating).astype('Int64')
    files_df['stored'] = files_df['full_path'].apply(lambda x: 'local' if is_file_available(x) else 'cloud')

    return files_df

def summarize_folders(engine:Engine, one_drive_folder:Path, quarantine_root:str, dry_run:bool=False):
    year_folders = get_year_folders(one_drive_folder)

    files = []
    folders = []

    for year_folder in year_folders[-1:]:
        print(f'Checking {year_folder}')
        year = int(year_folder.name)
        for person_folder in get_person_folders(one_drive_folder / str(year)):
            folder_name = get_person_name(person_folder)
            actual_year = get_actual_year(person_folder)
            project_year = actual_year or year
            year_adjust = project_year - year

            fo_df = DataFrame(data=[[folder_name, project_year, year_adjust]],
                              columns=['folder_name', 'project_year', 'year_adjust'])

            video_files = get_videos_in_folder(person_folder)
            if len(video_files):
            
                # get rid of dupes
                print(f'Deduping {person_folder}')
                dedupe_folder(video_files, one_drive_folder / quarantine_root, dry_run)

                # look at videos
                fi_df = summarize_files(folder_name, video_files, year)
                folders.append(fo_df)
                if not fi_df.empty:
                    files.append(fi_df)
        
        if not dry_run:
            if len(folders):
                folders_df = concat(folders)
                update_folders(engine, folders_df)

            if len(files):
                files_df = concat(files)
                update_files(engine, files_df)
            
            update_folder_member_ids(engine)

def update_database_images(engine:Engine, cloud_name:str, api_key:str, api_secret:str, dry_run:bool=False):
    configure_cloud(cloud_name, api_key, api_secret)
    member_ids = fetch_all_member_ids(engine)['member_id']
    if not dry_run:
        fill_in_temp_pictures(member_ids)