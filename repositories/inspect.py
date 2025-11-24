from pathlib import Path

from pandas import DataFrame, concat
from sqlalchemy import Engine

from common.console import SplitConsole
from common.system import get_premiere_projects_in_folder, get_videos_in_folder, resolve_relative_path, is_file_available, sort_paths, \
    get_year_folders, get_person_folders
from repositories.migrate import 
from adobe.bridge import get_video_rating, get_video_date, get_video_cv2_details, is_file_available, convert_to_xml, extract_media_paths
from database.db_project import \
    fetch_known_folders, update_folders, purge_folders, \
    fetch_known_files, update_files, purge_files, fetch_files, fetch_files_scanned, update_files_used, \
    fetch_all_member_ids, update_folder_member_ids 
from family_tree.cloudinary_heavy import configure_cloud, fill_in_temp_pictures

def get_child_from_relative(parent_folder, full_path):
    return parent_folder / full_path.relative_to(parent_folder).parents[-2]

def get_subfolder_name(parent_folder, full_path):
    return subfolder_name if (subfolder_name := '/'.join(full_path.relative_to(parent_folder).parts[0:-1])) and len(subfolder_name) else None

def get_to_purge(known_df: DataFrame, found_df: DataFrame, on_cols: list[str]) -> DataFrame:
    merged = known_df.merge(found_df, on=on_cols, how='left', indicator=True)
    return merged[merged['_merge'] == 'left_only']

def purge_stale_content(engine:Engine, year_folders:list[Path], dry_run:bool):
    # purge stale
    print('Purging stale content...')
    current_folders = []
    purged_files = []
  
    folder_comp_cols = ['folder_name', 'project_year']
    file_comp_cols = ['folder_name', 'project_year', 'file_name', 'subfolder_name']

    # remove stale files from DB
    for year_folder in year_folders:
        current_year = int(year_folder.name)

        current_folders.extend(get_person_folders(year_folder))

        # look at all the files in this year
        sub_current_files = []
        person_folders = get_person_folders(year_folder)
        for person_folder in person_folders:
            sub_current_files.extend(get_videos_in_folder(person_folder, recursive=True)) # prevents pulling video files not in person folder
        
        # assemble into partial dataframe
        current_files = DataFrame(
            [[get_child_from_relative(year_folder, p).name, # person_folder name
              current_year, p.name, # project_year, file_name
              get_subfolder_name(get_child_from_relative(year_folder, p), p)] for p in sub_current_files], # subfolder if exists
            columns=file_comp_cols)

        known_files = fetch_known_files(engine, current_year)
        purged = get_to_purge(known_files[known_files['project_year']==current_year], current_files, file_comp_cols)

        if not purged.empty:
            purged_files.append(purged)

    # remove stale folders from DB
    folders_df = DataFrame([[p.name, int(p.parent.name)] for p in current_folders], columns=folder_comp_cols)
    known_folders = fetch_known_folders(engine)
    purged_folders = get_to_purge(known_folders, folders_df, folder_comp_cols)

    # purge folders and files
    if not dry_run:
        if not purged_folders.empty:
            purge_folders(engine, purged_folders)
        if len(purged_files):
            purge_files(engine, concat(purged_files))


def summarize_files(person_folder:Path, year:int, video_files:list[Path], scanned_df:DataFrame) -> DataFrame:
    files_df = DataFrame()

    # changeable aspects
    files_df['full_path'] = video_files
    files_df['file_name'] = files_df['full_path'].apply(lambda x: x.name)
    files_df['folder_name'] = person_folder.name
    files_df['subfolder_name'] = files_df['full_path'].apply(lambda x: get_subfolder_name(person_folder, x))
    files_df['project_year'] = year
    files_df['file_size'] = files_df['full_path'].apply(lambda x: round(x.stat().st_size / 1e6, 1)) # store in MB
    files_df['video_rating'] = files_df['full_path'].apply(get_video_rating).astype('Int64')
    files_df['video_date'] = files_df['full_path'].apply(get_video_date).astype("datetime64[ns]")
    files_df['stored'] = files_df['full_path'].apply(lambda x: 'local' if is_file_available(x) else 'cloud')

    # non changeable aspects
    # look where previous paths was already inspected and use old values
    cv2_cols = ['video_duration', 'video_resolution']
    files_df[cv2_cols] = files_df.merge(scanned_df, on=['file_name', 'folder_name', 'subfolder_name'], how='left')[cv2_cols]
    cv2_update = files_df[cv2_cols].isna().all(axis=1)
    files_df.loc[cv2_update, cv2_cols] = files_df[cv2_update].apply(lambda x: get_video_cv2_details(x['full_path']), axis=1, result_type='expand')
    files_df['video_duration'] = files_df['video_duration'].astype('Int64')
    files_df['video_resolution'] = files_df['video_resolution'].astype('string')
    
    return files_df

def check_files_used(project_path:Path) -> list[Path]:
    root = convert_to_xml(project_path)
    relative_paths = extract_media_paths(root)
    full_paths = [resolve_relative_path(project_path.parent, r) for r in relative_paths]

    return full_paths

def compare_used(person_folder:Path, year:int, video_files:list[Path], full_paths:list[Path]) -> DataFrame:
    files_df = DataFrame()

    files_df['full_path'] = video_files
    files_df['file_name'] = files_df['full_path'].apply(lambda x: x.name)
    files_df['folder_name'] = person_folder.name
    files_df['project_year'] = year
    files_df['used_status'] = files_df['full_path'].apply(lambda x: x in full_paths)
   
    return files_df
    
def summarize_folders(engine:Engine, one_drive_folder:Path, project_folder:Path,
                      ui:SplitConsole, dry_run:bool=False):
    year_folders = get_year_folders(one_drive_folder)

    files = []
    files_used = []
    folders = []

    purge_stale_content(engine, year_folders, dry_run)

    previously_scanned = fetch_files_scanned(engine)

    for year_folder in sort_paths(year_folders):
        ui.add_update(f'Checking {year_folder}')
        project_year = int(year_folder.name)
        
        # prepare Premiere Project
        media_files:list[Path] = []
        premiere_projects = get_premiere_projects_in_folder(project_folder)
        for project_path in premiere_projects:
            project_available = is_file_available(project_path)

            if project_available:
                ui.set_status(f'Getting media used for {project_path.name}')
                media_files.extend(check_files_used(project_path))
        media_files = list(set(media_files))

        for person_folder in sort_paths(get_person_folders(one_drive_folder / str(project_year))):
            ui.set_status(f'Looking at {person_folder}')

            fo_df = DataFrame(data=[[person_folder.name, project_year]],
                              columns=['folder_name', 'project_year'])

            video_files = get_videos_in_folder(person_folder, recursive=True)
            if len(video_files):

                # look at videos
                scanned_df = previously_scanned[(previously_scanned['folder_name'] == person_folder.name) & 
                                                (previously_scanned['project_year'] == project_year)]
                fi_df = summarize_files(person_folder, project_year, video_files, scanned_df)
                folders.append(fo_df)
                if not fi_df.empty:
                    files.append(fi_df)

                if len(media_files):
                    fs_df = compare_used(person_folder, project_year, video_files, media_files)
                    if not fs_df.empty:
                        files_used.append(fs_df)

    if not dry_run:
        if len(folders):
            folders_df = concat(folders)
            update_folders(engine, folders_df)

        if len(files):
            files_df = concat(files)
            update_files(engine, files_df)


        if len(files_used):
            files_used_df = concat(files_used)
            update_files_used(engine, files_used_df)
        
        update_folder_member_ids(engine)

def update_database_images(engine:Engine, cloud_name:str, api_key:str, api_secret:str, dry_run=False):
    configure_cloud(cloud_name, api_key, api_secret)
    member_ids = fetch_all_member_ids(engine)['member_id']
    if not dry_run:
        fill_in_temp_pictures(member_ids.tolist())

def get_usable_videos(engine:Engine, year:int, min_stars:int):
    files_df = fetch_files(engine, year)
    usable_videos = files_df.query('video_rating >= @min_stars')
    return usable_videos