from pathlib import Path

from sqlalchemy import Engine 
from pandas import DataFrame

from common.console import SplitConsole
from common.system import get_person_folders, get_person_name, get_person_names, rebuild_path, resolve_relative_path
from database.db_project import fetch_files
from database.db_adobe import fetch_member_labels, fetch_color_labels, update_appearances, update_chapters, fetch_compilation
from adobe.premiere import convert_to_xml, extract_included_video_paths, open_project, find_videos_bin, create_person_bins, \
    import_videos, set_family_color_labels, create_label_presets, get_sequence_maps, get_actors_in_project, get_chapter_markers

def get_usable_videos(engine:Engine, year:int, min_stars:int):
    files_df = fetch_files(engine, year)
    usable_videos = files_df.query('video_rating >= @min_stars')
    return usable_videos

def ensure_premiere(engine:Engine, year:int, adobe_folder:Path, yir_reviews:str, pr_ext:str, 
                    ui:SplitConsole) -> int:
    ui.set_status('Opening Premiere project...')

    project_folder = adobe_folder / f'{yir_reviews} {year}'
    compilation_df = fetch_compilation(engine, year)
    if not compilation_df.empty:
        file_name = compilation_df['file_name'].iloc[0]

        project_path =  project_folder / f'{file_name}{pr_ext}'
        project_id = open_project(project_path)

        return project_id

def import_and_label(engine:Engine, project_id:int, year:int, min_stars:int, one_drive_folder:Path,
                     ui:SplitConsole, dry_run=True):
    
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
            ui.set_status(f'Checking {len(usable_videos_person)} video{v_s} for {person_name}...')
            import_videos(project_id, videos_bin, person_name, usable_video_paths, ui, dry_run)

    ui.set_status('Setting labels...')

    member_labels = fetch_member_labels(engine, year)
    member_labels['bin_name'] = member_labels['folder_name'].apply(get_person_name)
    label_map = member_labels.set_index('bin_name')['label_id'].sub(1).to_dict()
    set_family_color_labels(videos_bin, label_map)

def setup_label_presets(engine:Engine, common_folder:Path, label_preset_name:str):
    color_labels = fetch_color_labels(engine)
    return create_label_presets(color_labels, common_folder, label_preset_name)

def get_actors_and_chapters(engine:Engine, project_id:int, project_year:int):
    compilation_df = fetch_compilation(engine, project_year)
    if not compilation_df.empty:
        timeline_name, banned_bins = compilation_df[['timeline_name', 'banned_bins']].iloc[0]

        print('Getting sequence maps')
        sequence_map_by_name, sequence_map_by_node = get_sequence_maps(project_id)

        actor_timestamps = get_actors_in_project(project_id, timeline_name, sequence_map_by_name, sequence_map_by_node,
                                                 banned_bins=banned_bins)

        actor_times_df = (DataFrame(actor_timestamps).explode('actor_uuid', ignore_index=True)
                          .rename(columns={'actor_uuid': 'member_id'})
                          .drop_duplicates())
        actor_times_df['project_year'] = project_year
        update_appearances(engine, actor_times_df)
        
        chapter_timestamps = get_chapter_markers(project_id, timeline_name, sequence_map_by_name)
        chapter_markers_df = DataFrame(chapter_timestamps, columns=['chapter_name', 'start_time'])
        chapter_markers_df['project_year'] = project_year
        update_chapters(engine, chapter_markers_df)

        