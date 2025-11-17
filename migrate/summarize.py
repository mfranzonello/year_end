from pathlib import Path

from pandas import DataFrame, concat

from common.system import get_person_name, get_actual_year, get_videos_in_folder, get_file_sizes
from migrate.scan_and_copy import get_year_folders, get_person_folders
from adobe.bridge import get_video_rating, get_video_cv2_details, is_file_available
from family_tree.db import update_folders, update_files, update_folder_member_ids, fetch_all_member_ids
from family_tree.cloudinary_heavy import configure_cloud, fill_in_temp_pictures

def summarize_folder(person_folder, year):
    files_columns = ['full_path', 'file_name', 'folder_name', 'project_year',
                     'file_size', 'video_duration', 'video_resolution', 'video_rating', 'stored']
    files_df = DataFrame(columns = files_columns)

    folder_name = get_person_name(person_folder)
    actual_year = get_actual_year(person_folder)
    year_adjust = actual_year - year if actual_year else 0
    
    files_df.loc[:, 'full_path'] = get_videos_in_folder(person_folder)
    files_df.loc[:, 'file_name'] = files_df['full_path'].apply(lambda x: x.name)
    files_df.loc[:, 'folder_name'] = get_person_name(person_folder)
    files_df.loc[:, 'project_year'] = year
    files_df.loc[:, 'file_size'] = files_df['full_path'].apply(lambda x: round(x.stat().st_size / 1e6, 1)) # store in MB
    files_df.loc[:, ['video_duration', 'video_resolution']] = files_df.apply(lambda x: get_video_cv2_details(x['full_path']), axis=1, result_type='expand') ## get in one cv2 take
    files_df.loc[:, ['video_duration']] = files_df.loc[:, ['video_duration']].astype('Float64')
    files_df.loc[:, ['video_resolution']] = files_df.loc[:, ['video_resolution']].astype('string')
    files_df.loc[:, 'video_rating'] = files_df['full_path'].apply(get_video_rating).astype('Int64')
    files_df.loc[:, 'stored'] = files_df['full_path'].apply(lambda x: 'local' if is_file_available(x) else 'cloud')
 
    return files_df

def summarize_folders(engine, one_drive_folder, dry_run=False):
    year_folders = get_year_folders(one_drive_folder)

    files = []
    folders = []

    for year_folder in year_folders:
        print(f'Checking {year_folder}')
        year = int(year_folder.name)
        for person_folder in get_person_folders(one_drive_folder / str(year)):
            folder_name = get_person_name(person_folder)
            actual_year = get_actual_year(person_folder)
            project_year = actual_year or year
            year_adjust = project_year - year

            fo_df = DataFrame(data=[[folder_name, project_year, year_adjust]],
                              columns=['folder_name', 'project_year', 'year_adjust'])
            fi_df = summarize_folder(person_folder, year)
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

def update_database_images(engine, cloud_name, api_key, api_secret, dry_run=False):
    configure_cloud(cloud_name, api_key, api_secret)
    member_ids = fetch_all_member_ids(engine)['member_id']
    if not dry_run:
        fill_in_temp_pictures(member_ids)