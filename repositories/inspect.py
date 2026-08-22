"""Inspect project media folders and reconcile their metadata with the database."""

from pathlib import Path

from pandas import DataFrame, concat
from sqlalchemy import Engine

from common.console import SplitConsole
from common.structure import VIDEO_EXTS
from common.system import (
    get_premiere_projects_in_folder, get_videos_in_folder, resolve_relative_path, rebuild_path, is_file_available, sort_paths,
    get_year_folders, get_person_folders
    )
from adobe.bridge import get_video_rating, get_video_date, get_video_cv2_details, is_file_available
from adobe.premiere import convert_to_xml, extract_used_video_paths
from database.db_project import (
    fetch_known_folders, update_folders, purge_folders,
    fetch_known_files, update_files, purge_files, fetch_files, fetch_files_scanned, update_files_used,
    )
from database.db_display import fetch_display_names
from family_tree.cloudinary_heavy import configure_cloud, fill_in_temp_pictures
from integrations.microsoft.onedrive.client import (
    GraphRequestError,
    find_folder_id as find_onedrive_folder_id,
    get_share_link as get_onedrive_share_link,
    get_or_create_share_link as get_or_create_onedrive_share_link,
    list_children as list_onedrive_children,
    list_child_folders as list_onedrive_child_folders,
    list_descendant_files as list_onedrive_descendant_files,
)
from database.db_project import fetch_project_folders, update_folder_locations_and_shares


def inspect_onedrive_folder_shares(
    engine: Engine,
    project_root: str,
    media_type: str,
    supfolder_name: str,
    project_year: int,
    ui: SplitConsole,
    dry_run: bool = True,
    create_missing_shares: bool = True,
) -> DataFrame:
    """Match canonical OneDrive folders to project records and ensure shares."""
    project_folders = fetch_project_folders(engine, project_year, media_type)
    if project_folders.empty:
        return DataFrame()

    year_path = "/".join((project_root.strip("/\\"), supfolder_name, str(project_year)))
    try:
        year_folder_id = find_onedrive_folder_id(year_path)
    except GraphRequestError as error:
        if "HTTP 404" not in str(error):
            raise
        ui.add_update(
            f"OneDrive {project_year} {media_type}: configured year folder does not exist."
        )
        return DataFrame()
    cloud_folders = list_onedrive_child_folders(year_folder_id)
    cloud_by_name = {folder.get("name"): folder for folder in cloud_folders}
    if len(cloud_by_name) != len(cloud_folders):
        raise ValueError("The OneDrive year folder contains duplicate top-level folder names")

    matched = []
    for row in project_folders.to_dict(orient="records"):
        cloud_folder = cloud_by_name.get(row["folder_name"])
        if cloud_folder is None:
            continue
        item_id = cloud_folder.get("id")
        if not isinstance(item_id, str) or not item_id:
            continue
        share_function = (
            get_or_create_onedrive_share_link
            if create_missing_shares
            else get_onedrive_share_link
        )
        matched.append({
            **row,
            "repository_item_id": item_id,
            "share_url": None if dry_run else share_function(item_id),
        })

    results = DataFrame(matched)
    ui.add_update(
        f"OneDrive {project_year} {media_type}: matched {len(results)} of "
        f"{len(project_folders)} database folders."
    )
    if not dry_run:
        update_folder_locations_and_shares(engine, results, "OneDrive", is_canonical=True)
    return results


def _is_video_item(item: dict) -> bool:
    """Return whether a Graph file item has a configured video extension."""
    name = item.get("name")
    return "file" in item and isinstance(name, str) and Path(name).suffix.lower() in VIDEO_EXTS


def _cloud_file_row(
    item: dict,
    folder_name: str | None,
    project_year: int,
    subfolder_name: str | None,
) -> dict:
    """Convert Graph metadata to the portable project.files input contract."""
    size = item.get("size")
    if not isinstance(size, int) or size < 0:
        raise GraphRequestError(
            f"Microsoft Graph returned an invalid size for {item.get('name')!r}"
        )
    return {
        "folder_name": folder_name,
        "project_year": project_year,
        "file_name": item["name"],
        "subfolder_name": subfolder_name,
        "file_size": round(size / (1024 ** 2), 1),
        "stored": "cloud",
    }


def inspect_onedrive_cloud_contents(
    engine: Engine,
    project_root: str,
    media_type: str,
    supfolder_name: str,
    ui: SplitConsole,
    dry_run: bool = True,
    project_year: int | None = None,
    folders_only: bool = False,
) -> tuple[DataFrame, DataFrame]:
    """Inventory OneDrive folders and file metadata without downloading media."""
    media_path = "/".join((project_root.strip("/\\"), supfolder_name))
    requested_path = f"{media_path}/{project_year}" if project_year is not None else media_path
    try:
        if project_year is not None:
            year_folders = [{
                "id": find_onedrive_folder_id(f"{media_path}/{project_year}"),
                "name": str(project_year),
                "folder": {},
            }]
        else:
            media_folder_id = find_onedrive_folder_id(media_path)
            year_folders = [
                item for item in list_onedrive_child_folders(media_folder_id)
                if isinstance(item.get("name"), str)
                and item["name"].isdigit()
                and len(item["name"]) == 4
            ]
    except GraphRequestError as error:
        if "HTTP 404" not in str(error):
            raise
        ui.add_update(f"OneDrive cloud path does not exist: {requested_path}")
        return DataFrame(), DataFrame()

    folder_rows = []
    file_rows = []
    for year_folder in sorted(year_folders, key=lambda item: item["name"]):
        if not isinstance(year_folder.get("id"), str) or not year_folder["id"]:
            raise GraphRequestError("Microsoft Graph returned a year folder without an ID")
        selected_year = int(year_folder["name"])
        ui.add_update(f"Checking OneDrive cloud metadata for {media_type} {selected_year}")
        children = list_onedrive_children(year_folder["id"])
        participant_folders = [item for item in children if "folder" in item]
        participant_names = [item.get("name") for item in participant_folders]
        if not all(isinstance(name, str) and name for name in participant_names):
            raise GraphRequestError(
                f"Microsoft Graph returned an unnamed folder beneath {selected_year}"
            )
        if not all(
            isinstance(item.get("id"), str) and item["id"]
            for item in participant_folders
        ):
            raise GraphRequestError(
                f"Microsoft Graph returned a folder without an ID beneath {selected_year}"
            )
        if len(set(participant_names)) != len(participant_names):
            raise ValueError(
                f"OneDrive {selected_year} contains duplicate top-level folder names"
            )

        root_files = [item for item in children if _is_video_item(item)]
        if root_files:
            folder_rows.append({
                "folder_name": None,
                "project_year": selected_year,
                "media_type": media_type,
            })
            if not folders_only:
                file_rows.extend(
                    _cloud_file_row(item, None, selected_year, None)
                    for item in root_files
                )

        for participant in sorted(participant_folders, key=lambda item: item["name"]):
            folder_name = participant["name"]
            folder_rows.append({
                "folder_name": folder_name,
                "project_year": selected_year,
                "media_type": media_type,
            })
            if folders_only:
                continue
            file_rows.extend(
                _cloud_file_row(
                    item,
                    folder_name,
                    selected_year,
                    item.get("relative_parent"),
                )
                for item in list_onedrive_descendant_files(participant["id"])
                if _is_video_item(item)
            )

    folders = DataFrame(
        folder_rows,
        columns=["folder_name", "project_year", "media_type"],
    )
    files = DataFrame(
        file_rows,
        columns=[
            "folder_name", "project_year", "file_name", "subfolder_name",
            "file_size", "stored",
        ],
    )
    ui.add_update(
        f"OneDrive cloud inventory found {len(folders)} project folders and "
        f"{len(files)} video files for {media_type}."
    )
    if not dry_run:
        if not folders.empty:
            update_folders(engine, folders)
        if not files.empty:
            files["media_type"] = media_type
            update_files(engine, files)
    return folders, files

def get_child_from_relative(parent_folder:Path, full_path:Path) -> Path:
    return parent_folder / full_path.relative_to(parent_folder).parents[-2]

def get_subfolder_name(parent_folder, full_path):
    return subfolder_name if (subfolder_name := '/'.join(full_path.relative_to(parent_folder).parts[0:-1])) and len(subfolder_name) else None

def get_to_purge(known_df: DataFrame, found_df: DataFrame, on_cols: list[str]) -> DataFrame:
    merged = known_df.merge(found_df, on=on_cols, how='left', indicator=True)
    return merged[merged['_merge'] == 'left_only']

def purge_stale_content(engine:Engine, one_drive_folder:Path, media_type:str, dry_run:bool):
    # purge stale
    print(f'Purging stale {media_type} content...')
    current_folders = []
    current_roots = []
    purged_files = []
  
    folder_comp_cols = ['folder_name', 'project_year', 'media_type']
    file_comp_cols = ['folder_name', 'project_year', 'media_type', 'file_name', 'subfolder_name']

    # remove stale files from DB
    year_folders = get_year_folders(one_drive_folder)
    
    for year_folder in year_folders:
        current_year = int(year_folder.name)

        current_folders.extend(get_person_folders(year_folder))

        # look at all the files in this year
        sub_current_files = get_videos_in_folder(year_folder, recursive=False)
        person_folders = get_person_folders(year_folder)
        for person_folder in [year_folder] + person_folders:
            is_root = person_folder == year_folder
            files_in_folder = get_videos_in_folder(person_folder, recursive=(not is_root))
            if len(files_in_folder):
                if is_root:
                    current_roots.append(year_folder)
                sub_current_files.extend(files_in_folder)

        # assemble into partial dataframe
        current_files = DataFrame(
            [[get_child_from_relative(year_folder, p).name if (p.parent != year_folder) else None, # person_folder name
              current_year, media_type, # project_year, media_type
              p.name, # file_name
              get_subfolder_name(get_child_from_relative(year_folder, p), p) if (p.parent != year_folder) else None] for p in sub_current_files], # subfolder if exists
            columns=file_comp_cols)

        known_files = fetch_known_files(engine, current_year, media_type)
        purged = get_to_purge(known_files[(known_files['project_year']==current_year)
                                          & (known_files['media_type']==media_type)],
                              current_files, file_comp_cols)

        if not purged.empty:
            purged_files.append(purged)

    # remove stale folders from DB
    folders_df = DataFrame([[p.name, int(p.parent.name), media_type] for p in current_folders], columns=folder_comp_cols)
    if current_roots:
        folders_df = concat([folders_df, (DataFrame([[None, int(p.name), media_type] for p in current_roots], columns=folder_comp_cols))])

    known_folders = fetch_known_folders(engine, media_type)
    purged_folders = get_to_purge(known_folders, folders_df, folder_comp_cols)

    # purge folders and files
    if not dry_run:
        if not purged_folders.empty:
            purge_folders(engine, purged_folders)
        if len(purged_files):
            purge_files(engine, concat(purged_files))


def summarize_files(person_folder:Path, is_root:bool, year:int, video_files:list[Path], scanned_df:DataFrame) -> DataFrame:
    files_df = DataFrame()

    # changeable aspects
    files_df['full_path'] = video_files
    files_df['file_name'] = files_df['full_path'].apply(lambda x: x.name)
    files_df['folder_name'] = person_folder.name if not is_root else None
    files_df['subfolder_name'] = files_df['full_path'].apply(lambda x: get_subfolder_name(person_folder, x))
    files_df['project_year'] = year
    files_df['file_size'] = files_df['full_path'].apply(lambda x: round(x.stat().st_size / (1024**2), 1)) # store in MB
    files_df['video_rating'] = files_df['full_path'].apply(get_video_rating).astype('Int64')

    files_df['video_date'] = files_df['full_path'].apply(get_video_date).astype('datetime64[ns]')
    files_df['video_date'] = files_df['video_date'].astype(object).where(files_df['video_date'].notnull(), None)

    files_df['stored'] = files_df['full_path'].apply(lambda x: 'local' if is_file_available(x) else 'cloud')

    # non changeable aspects
    # look where previous paths was already inspected and use old values
    cv2_cols = ['video_duration', 'video_resolution']
    files_df[cv2_cols] = files_df.merge(scanned_df, on=['file_name', 'folder_name', 'subfolder_name'], how='left')[cv2_cols]
    cv2_update = files_df[cv2_cols].isna().all(axis=1)
    if cv2_update.any():
        files_df.loc[cv2_update, cv2_cols] = files_df[cv2_update]\
            .apply(lambda x: get_video_cv2_details(x['full_path']), axis=1, result_type='expand')\
            .set_axis(cv2_cols, axis=1).loc[cv2_update, cv2_cols].loc[cv2_update, cv2_cols]

    files_df['video_duration'] = files_df['video_duration'].astype('Int64')
    files_df['video_resolution'] = files_df['video_resolution'].astype('string')

    return files_df

def check_files_used(project_path:Path) -> list[Path]:
    root = convert_to_xml(project_path)
    relative_paths = extract_used_video_paths(root)
    full_paths = [resolve_relative_path(project_path.parent, r) for r in relative_paths]

    return full_paths

def compare_used(files_df:Path, parent_folder:Path, year:int, full_paths:list[Path]) -> DataFrame:
    files_used_df = files_df.query('project_year == @year')
    files_used_df['full_path'] = files_used_df.apply(lambda x: rebuild_path(parent_folder, x['folder_name'], x['subfolder_name'], x['file_name']), axis=1)
    files_used_df['used_status'] = files_used_df['full_path'].apply(lambda x: x in full_paths)
 
    return files_used_df
    
def summarize_folders(
    engine: Engine,
    one_drive_folder: Path,
    media_type: str,
    review_folder: Path,
    review_string: str,
    ui: SplitConsole,
    dry_run: bool = False,
    project_year: int | None = None,
    folders_only: bool = False,
):
    """Inspect top-level project folders and their media, optionally for one year."""
    files = []
    files_used = []
    folders = []

    previously_scanned = DataFrame() if folders_only else fetch_files_scanned(engine, media_type)

    year_folders = get_year_folders(one_drive_folder)
    if project_year is not None:
        year_folders = [folder for folder in year_folders if folder.name == str(project_year)]

    for year_folder in sort_paths(year_folders):
        ui.add_update(f'Checking {media_type} {year_folder}')
        project_year = int(year_folder.name)

        ##### for debugging only 2025
        # # if project_year >= 2005:
        # #     continue
               
        # look at root folder and subfolders
        for person_folder in [year_folder] + sort_paths(get_person_folders(year_folder)):
            ui.set_status(f'Looking at {person_folder}')

            is_root = person_folder == year_folder
            folder_name = person_folder.name if not is_root else None

            fo_df = DataFrame(data=[[folder_name, project_year]],
                              columns=['folder_name', 'project_year'])

            if folders_only:
                if not is_root:
                    folders.append(fo_df)
                continue

            video_files = get_videos_in_folder(person_folder, recursive=(not is_root)) # don't look recursively if at top level
            # Participant folders are meaningful project records even before
            # media arrives. The year root is only a record when it has media.
            if not is_root or len(video_files):
                folders.append(fo_df)

            if len(video_files):

                # look at videos
                scanned_df = previously_scanned[(previously_scanned['folder_name'] == folder_name) & 
                                (previously_scanned['project_year'] == project_year)]
                
                # # if 2000 <= project_year <= 2006:
                # #     scanned_df = DataFrame(columns=previously_scanned.columns)
                # # else:
                # #     scanned_df = previously_scanned[(previously_scanned['folder_name'] == folder_name) & 
                # #                                     (previously_scanned['project_year'] == project_year)]

                fi_df = summarize_files(person_folder, is_root, project_year, video_files, scanned_df)
                if not fi_df.empty:
                    files.append(fi_df)

        if folders_only:
            continue

        # prepare Premiere Project
        media_files:list[Path] = []

        project_folder = review_folder / f'{review_string} {project_year}'
        premiere_projects = get_premiere_projects_in_folder(project_folder)
        for project_path in premiere_projects:
            project_available = is_file_available(project_path)

            if project_available:
                ui.set_status(f'Getting media used for {project_path.name}')
                media_files.extend(check_files_used(project_path))
        media_files = list(set(media_files))

        if len(media_files):
            files_df = fetch_files(engine, project_year, media_type)
            fs_df = compare_used(files_df, year_folder, project_year, media_files)

            if not fs_df.empty:
                files_used.append(fs_df)

    if not dry_run:
        if len(folders):
            folders_df = concat(folders)
            folders_df['media_type'] = media_type
            update_folders(engine, folders_df)

        if len(files):
            files_df = concat(files)
            files_df['media_type'] = media_type
            update_files(engine, files_df)

        if len(files_used):
            files_used_df = concat(files_used)
            files_df['media_type'] = media_type
            update_files_used(engine, files_used_df)
        
def update_database_images(engine:Engine, cloud_name:str, api_key:str, api_secret:str, dry_run=False):
    configure_cloud(cloud_name, api_key, api_secret)
    display_names = fetch_display_names(engine)

    if not dry_run:
        fill_in_temp_pictures(display_names)
