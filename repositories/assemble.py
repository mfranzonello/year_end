from pathlib import Path

from sqlalchemy import Engine 
from common.system import get_person_folders, get_person_name, get_person_names, rebuild_path, resolve_relative_path
from database.db_project import fetch_files, fetch_color_labels
from adobe.premiere import convert_to_xml, extract_included_video_paths, open_project, find_videos_bin, create_person_bins, import_videos, set_family_color_labels

def get_usable_videos(engine:Engine, year:int, min_stars:int):
    files_df = fetch_files(engine, year)
    usable_videos = files_df.query('video_rating >= @min_stars')
    return usable_videos

def import_and_label(engine:Engine, year:int, min_stars:int, one_drive_folder:Path, adobe_folder:Path, yir_reviews:str, yir_project:str, pr_ext:str,
                     ui, dry_run=True):
    

    ui.set_status('Opening Premiere project...')
    project_folder = adobe_folder / f'{yir_reviews} {year}'
    project_path =  project_folder / f'{yir_project} {year}{pr_ext}'
    project_id = open_project(project_path)

    ui.set_status('Finding Videos bin')
    videos_bin = find_videos_bin(project_id)

    ui.set_status('Creating person bins...')
    one_drive_year_folder = one_drive_folder / f'{year}'
    person_folders = get_person_folders(one_drive_year_folder)
    person_names = get_person_names(one_drive_year_folder)
    create_person_bins(videos_bin, person_names)

    ui.set_status(f'Importing reviewed videos ({min_stars} star and above)...')

    # check what's already in the project
    # # root = convert_to_xml(project_path)
    # # included_videos = extract_included_video_paths(root)
    # # included_video_paths = [resolve_relative_path(project_folder, p) for p in included_videos]

    # pull from DB
    usable_videos = get_usable_videos(engine, year, min_stars)

    for person_folder in person_folders:
        person_name = get_person_name(person_folder)
        ui.set_status(f'\tLooking at {person_name}...')

        usable_videos_person = usable_videos.query('folder_name == @person_folder.name')
       
        if not usable_videos_person.empty:
            usable_video_paths = [rebuild_path(one_drive_year_folder, person_folder.name, v['subfolder_name'], v['file_name']) for _, v in usable_videos_person.iterrows()]

            num_videos = len(usable_video_paths)
            v_s = 's' if num_videos != 1 else ''
            ui.set_status(f'\t\tChecking {len(usable_videos_person)} video{v_s} for {person_name}...')
            import_videos(project_id, videos_bin, person_name, usable_video_paths, dry_run)

    ui.set_status('Setting labels...')

    color_labels = fetch_color_labels(engine, year)
    color_labels['bin_name'] = color_labels['folder_name'].apply(get_person_name)
    label_map = color_labels.set_index('bin_name')['label_id'].sub(1).to_dict()
    set_family_color_labels(videos_bin, label_map)