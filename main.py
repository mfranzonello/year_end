'''Main script to scan for new video files, copy them, summarize ratings, and update Premiere project.'''

from pathlib import Path
import argparse
import sys
from datetime import datetime

from structure import ONE_DRIVE_FOLDER, GOOGLE_DRIVE_FOLDER, ADOBE_FOLDER, YIR_CLIPS, YIR_REVIEWS, YIR_PROJECT, PR_EXT
from system import file_type, get_person_name, get_videos_in_folder, mount_g_drive
from bridge import get_rated_videos
from scan_and_copy import get_person_folders, get_person_names, copy_if_needed
from premiere import open_project, find_videos_bin, create_person_bins, import_videos, set_family_color_labels

MIN_STARS = 3

def scan_folders(od, gd, yir_clips, year, dry_run=True):
    od_year = od / yir_clips / str(year)
    gd_year = gd / yir_clips / str(year)
    
    mount_g_drive()
    if not gd_year.exists():
        print(f"WARNING: Google Drive year folder missing: {gd_year}", file=sys.stderr)
    if not od_year.exists():
        print(f"WARNING: OneDrive year folder missing (will be created on demand): {od_year}", file=sys.stderr)

    # --- Copy new videos from GDrive to OneDrive, per person folder ---
    copy_report: list[tuple[str, int]] = []
    gd_people = get_person_folders(gd_year)

    print('Checking for new videos to copy...')
    for gd_person in sorted(gd_people, key=lambda p: p.name.lower()):
        person_name = gd_person.name  # e.g., "Michael 2025"
        od_person = od_year / person_name

        # List candidate videos in the Google Drive person folder (non-recursive).
        candidates = [p for p in gd_person.iterdir() if file_type(p) == 'VIDEO']
        copied_count = 0
        for src in candidates:
            if copy_if_needed(src, od_person, dry_run=dry_run):
                copied_count += 1

        copy_report.append((person_name, copied_count))

    # Also include note for any GDrive person folders that do not exist in OneDrive yet (only relevant when dry-run)
    missing_targets = []
    for gd_person in gd_people:
        if not (od_year / gd_person.name).exists():
            missing_targets.append(gd_person.name)

    # --- Output ---
    print("\n=== Copy Summary (Google Drive -> OneDrive) ===")
    if all(c == 0 for _, c in copy_report):
        print("No new videos detected.")
    else:
        for name, count in copy_report:
            if count > 0:
                v_s = 's' if count != 1 else ''
                print(f"{count} video{v_s} copied from {name}")
        # For zero-copy entries, we keep it quiet to reduce noise.

    if dry_run and missing_targets:
        print("\n(Note) These OneDrive destination folders do not exist yet (will be created on --apply if needed):")
        for name in missing_targets:
            print(f"  - {name}")

def summarize_folders(year, min_stars):
    print(f"\n=== OneDrive Folder Ratings Summary ({year}) ===")
    
    summary_paths = get_person_folders(Path(ONE_DRIVE_FOLDER) / YIR_CLIPS / str(year))
    if not len(summary_paths):
        print(f"No OneDrive {year} folders found to summarize.")

    else:
        for person_path in sorted(summary_paths, key=lambda x: (x.name.lower().startswith('other'), x.name.lower())):
            _, video_ratings = get_rated_videos(person_path, 0)
            n_videos = len(get_videos_in_folder(person_path))

            if n_videos:
                n_reviewed = sum(1 for x in video_ratings if x > 0)
                n_usable = sum(1 for x in video_ratings if x > min_stars)
                n_string = f'{get_person_name(person_path, year)}: {n_videos} videos, {n_reviewed/n_videos:.0%} reviewed'
                if n_usable:
                    n_string += f' ({n_usable} rated {min_stars}+ stars)'
                print(n_string)

def update_project(year, min_stars, dry_run=True):
    print('Opening Premiere project...')
    project_id = open_project(Path(ADOBE_FOLDER) / f'{YIR_REVIEWS} {year}' / f'{YIR_PROJECT} {year}{PR_EXT}')

    print('Finding Videos bin')
    videos_bin = find_videos_bin(project_id)

    print('Creating person bins...')
    od_videos = Path(ONE_DRIVE_FOLDER) / YIR_CLIPS / f'{year}'
    person_names = get_person_names(od_videos)
    create_person_bins(videos_bin, person_names)

    print(f'Importing reviewed videos ({MIN_STARS} star and above)...')
    for person_name in person_names:
        print(f'\tLooking at {person_name}...')
        rated_videos, _ = get_rated_videos(Path(ONE_DRIVE_FOLDER) / YIR_CLIPS / f'{year}' / f'{person_name} {year}', min_stars)

        if rated_videos:
            num_videos = len(rated_videos)
            v_s = 's' if num_videos != 1 else ''
            print(f'\t\tChecking {len(rated_videos)} video{v_s} for {person_name}...')
            import_videos(project_id, videos_bin, person_name, rated_videos)

    print('Setting labels...')
    set_family_color_labels(videos_bin)

def main():
    ap = argparse.ArgumentParser(description=f"Scan for new files and import into current year's Premiere review project.")
    
    ap.add_argument("--od", type=Path, default=Path(ONE_DRIVE_FOLDER), help=f"OneDrive Videos root (default: {ONE_DRIVE_FOLDER})")
    ap.add_argument("--gd", type=Path, default=Path(GOOGLE_DRIVE_FOLDER), help=f"Google Drive Videos root (default: {ONE_DRIVE_FOLDER})")
    
    YEAR = datetime.now().year
    ap.add_argument("--year", type=int, default=YEAR, help=f"Year subfolder to process (default: {YEAR})")
    
    ap.add_argument('--copy', nargs='?', type=bool, const=True, default=False, help='Copy new files from Google Drive to OneDrive.')
    ap.add_argument('--premiere_update', nargs='?', type=bool, const=True, default=False, help='Update Premiere project with bins and imports.')

    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true", help="Actually copy files.")
    mode.add_argument("--dry-run", action="store_true", help="Do not copy; show what would happen.")
    
    args = ap.parse_args()
    dry_run = not args.apply  # default to dry-run unless --apply

    if args.copy:
        scan_folders(args.od, args.gd, YIR_CLIPS, args.year, dry_run)

    summarize_folders(args.year, MIN_STARS)

    if args.premiere_update:
        update_project(args.year, dry_run=dry_run, min_stars=MIN_STARS)


if __name__ == "__main__":
    main()
