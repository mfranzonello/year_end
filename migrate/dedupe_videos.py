#!/usr/bin/env python3
"""
YIR helper with two modes:

1) COPY MODE (original behavior)
   python dedupe_videos.py INPUT OUTPUT_DIR [--apply] [--extensions .mp4 .mov ...]

   - INPUT: directory (non-recursive) or .zip (any depth)
   - OUTPUT_DIR: destination tree; script scans it recursively to ignore duplicates by filename (case-insensitive)
   - Copies only non-duplicates into OUTPUT_DIR/other or other_N
   - INPUT is never modified

2) DISCOVERY MODE (rank best Year/[Folder Name] destination)
   python dedupe_videos.py INPUT --videos-root "...\YIR Clips" --year 2022 [--top 10]
                                [--scoring overlap|jaccard] [--size-tolerance 0.01] [--extensions ...]

   Prints a ranked table with:
     - MatchName%       : filename-only matches (relative to INPUT count)
     - MatchNameSize%   : filename + size matches (within tolerance, relative to INPUT count)
"""

from pathlib import Path
import argparse
import sys
import shutil
from zipfile import ZipFile
from typing import Iterable, Tuple, List, Set, Dict

from structure import VIDEO_EXTS

# ---------- Utility ----------

def normalize_exts(exts_arg):
    return {e.lower() if e.startswith(".") else f".{e.lower()}" for e in (exts_arg or VIDEO_EXTS)}

def rel_size_diff(a: int, b: int) -> float:
    """Relative size difference in [0,1]."""
    m = max(a, b, 1)
    return abs(a - b) / m

# ---------- Input collection ----------

def find_input_videos_dir(input_dir: Path, exts: Set[str]) -> List[Path]:
    """List video files directly inside input_dir (non-recursive)."""
    vids = []
    for p in input_dir.iterdir():
        if p.is_file() and p.suffix.lower() in exts:
            vids.append(p)
    return vids

def list_zip_video_members(zip_path: Path, exts: Set[str]) -> List[Tuple[str, str, int]]:
    """Return list of (member_name, basename, uncompressed_size) for videos anywhere in the zip."""
    members = []
    with ZipFile(zip_path, "r") as zf:
        for zi in zf.infolist():
            if zi.is_dir():
                continue
            base = Path(zi.filename).name
            if Path(base).suffix.lower() in exts:
                members.append((zi.filename, base, int(zi.file_size)))
    return members

def collect_input_items(input_path: Path, exts: Set[str]) -> Tuple[bool, List[Tuple[str, str, int]], List[Tuple[Path, str, int]], Set[str]]:
    """
    Inspect input and return:
      (is_zip,
       zip_items:  [(member, basename, size)],
       dir_items:  [(path,   basename, size)],
       input_name_set_lower: {basename_lower, ...})
    """
    is_zip = input_path.suffix.lower() == ".zip"
    if is_zip:
        members = list_zip_video_members(input_path, exts)
        name_set = {base.lower() for _, base, _ in members}
        return True, members, [], name_set
    else:
        if not input_path.is_dir():
            print(f"ERROR: input path is not a directory (and not a .zip): {input_path}", file=sys.stderr)
            sys.exit(1)
        files = find_input_videos_dir(input_path, exts)
        items = []
        for p in files:
            try:
                sz = int(p.stat().st_size)
            except Exception:
                sz = -1
            items.append((p, p.name, sz))
        name_set = {p.name.lower() for p in files}
        return False, [], items, name_set

# ---------- Output scanning ----------

def gather_output_name_set(output_dir: Path) -> Set[str]:
    """Lowercase basenames of all files under output_dir (recursive)."""
    names = set()
    for p in output_dir.rglob("*"):
        if p.is_file():
            names.add(p.name.lower())
    return names

def gather_output_name_to_sizes(output_dir: Path) -> Dict[str, Set[int]]:
    """
    Map: lowercase basename -> set of file sizes (ints) found anywhere under output_dir.
    Useful for name+size matching when duplicates may exist at different sizes.
    """
    m: Dict[str, Set[int]] = {}
    for p in output_dir.rglob("*"):
        if p.is_file():
            key = p.name.lower()
            try:
                sz = int(p.stat().st_size)
            except Exception:
                sz = -1
            m.setdefault(key, set()).add(sz)
    return m

# ---------- Discovery helpers ----------

def subfolders_for_year(videos_root: Path, year: int) -> List[Path]:
    """Immediate subfolders under {videos_root}/{year}."""
    year_dir = videos_root / str(year)
    if not year_dir.exists() or not year_dir.is_dir():
        print(f"ERROR: Year directory not found: {year_dir}", file=sys.stderr)
        sys.exit(1)
    subs = [p for p in year_dir.iterdir() if p.is_dir()]
    if not subs:
        print(f"WARNING: No subfolders found under {year_dir}", file=sys.stderr)
    return subs

def gather_folder_name_set(folder: Path) -> Set[str]:
    names = set()
    for p in folder.rglob("*"):
        if p.is_file():
            names.add(p.name.lower())
    return names

def gather_folder_name_to_sizes(folder: Path) -> Dict[str, Set[int]]:
    mapping: Dict[str, Set[int]] = {}
    for p in folder.rglob("*"):
        if p.is_file():
            key = p.name.lower()
            try:
                sz = int(p.stat().st_size)
            except Exception:
                sz = -1
            mapping.setdefault(key, set()).add(sz)
    return mapping

# ---------- Discovery mode ----------

def run_discovery(input_path: Path, videos_root: Path, year: int, exts: Set[str],
                  top_n: int, scoring: str, size_tolerance: float, apply: bool):
    print("Discovery mode")
    print(f"  Videos root : {videos_root}")
    print(f"  Year        : {year}")
    print(f"  Input       : {input_path}")
    print(f"  Size tol    : {size_tolerance*100:.2f}%")

    if not videos_root.exists() or not videos_root.is_dir():
        print(f"ERROR: videos root does not exist or is not a directory: {videos_root}", file=sys.stderr)
        sys.exit(1)

    is_zip, zip_items, dir_items, input_name_set = collect_input_items(input_path, exts)
    # Build list of (name_lower, size)
    if is_zip:
        input_pairs = [(base.lower(), sz) for _, base, sz in zip_items]
    else:
        input_pairs = [(base.lower(), sz) for _, base, sz in dir_items]

    print(f"  Input type  : {'ZIP' if is_zip else 'directory'} with {len(input_pairs):,} candidate video(s).")

    candidates = subfolders_for_year(videos_root, year)
    results = []
    for folder in candidates:
        folder_names = gather_folder_name_set(folder)
        folder_name_to_sizes = gather_folder_name_to_sizes(folder)

        # Name-only overlap
        name_overlap = sum(1 for nm, _ in input_pairs if nm in folder_names)

        # Name+size overlap (within tolerance)
        size_overlap = 0
        for nm, sz in input_pairs:
            if nm not in folder_name_to_sizes:
                continue
            if sz < 0:
                continue
            sizes = folder_name_to_sizes[nm]
            # if any size matches within tolerance -> count it
            if any(rel_size_diff(sz, s2) <= size_tolerance for s2 in sizes if s2 >= 0):
                size_overlap += 1

        total_input = max(1, len(input_pairs))
        match_name_pct = 100.0 * name_overlap / total_input
        match_namesize_pct = 100.0 * size_overlap / total_input

        # Optional Jaccard (name-only, unchanged)
        union = len(input_name_set | folder_names)
        jaccard = 100.0 * (len(input_name_set & folder_names) / max(1, union))

        results.append({
            "folder": folder,
            "match_name_pct": match_name_pct,
            "match_namesize_pct": match_namesize_pct,
            "name_overlap": name_overlap,
            "size_overlap": size_overlap,
            "total_in_folder": len(folder_names),
            "jaccard": jaccard
        })

    if not results:
        print("No candidate folders to score.")
        return

    # Sort: by chosen metric, with sensible tie-breakers
    if scoring == "jaccard":
        results.sort(key=lambda r: (r["jaccard"], r["match_name_pct"], r["name_overlap"], str(r["folder"]).lower()), reverse=True)
    else:
        # default: overlap percentage (filename-only)
        results.sort(key=lambda r: (r["match_name_pct"], r["name_overlap"], str(r["folder"]).lower()), reverse=True)

    # Print table
    print("\nTop candidate folders:")
    header = f"{'Rank':>4}  {'MatchName%':>11}  {'MatchNameSize%':>15}  {'Jacc%':>7}  {'NameOv':>6}  {'SizeOv':>6}  {'InFolder':>9}  Destination"
    print(header)
    print("-" * len(header))
    for idx, r in enumerate(results[:top_n], start=1):
        print(f"{idx:>4}  {r['match_name_pct']:11.2f}  {r['match_namesize_pct']:15.2f}  {r['jaccard']:7.2f}  {r['name_overlap']:6d}  {r['size_overlap']:6d}  {r['total_in_folder']:9d}  {r['folder']}")

    best = results[0]
    print("\nNext:")
    print(f"- If the top match looks right, re-run COPY MODE with OUTPUT_DIR = {best['folder']}")
    print("  Example:")
    print(f"    python dedupe_videos.py \"{input_path}\" \"{best['folder']}\" --apply")
    print("\nNo files were created or modified in discovery mode.")

    # Auto-copy behavior: if --apply AND exactly one folder has MatchNameSize% == 100%
    if apply:
        perfect = [r for r in results if abs(r["match_namesize_pct"] - 100.0) < 1e-9]
        if len(perfect) == 1:
            chosen = perfect[0]["folder"]
            print("\nAuto-copy condition met: exactly one folder has MatchNameSize% == 100%.")
            print(f"Proceeding to copy any not-yet-present files into: {chosen}")
            # Delegate to copy mode (will avoid creating 'other' if nothing to copy).
            run_copy_mode(input_path, chosen, exts, apply=True)
        else:
            if len(perfect) == 0:
                print("\nAuto-copy not triggered: no folder reached MatchNameSize% = 100%.")
            else:
                print("\nAuto-copy not triggered: multiple folders reached MatchNameSize% = 100%.")


# ---------- Copy mode (unchanged behavior) ----------

def next_available_subfolder(base_parent: Path, base_name: str) -> Path:
    candidate = base_parent / base_name
    if not candidate.exists():
        return candidate
    i = 1
    while True:
        candidate = base_parent / f"{base_name}_{i}"
        if not candidate.exists():
            return candidate
        i += 1

def next_available_file(path: Path) -> Path:
    if not path.exists():
        return path
    stem, suffix = path.stem, path.suffix
    i = 1
    while True:
        candidate = path.with_name(f"{stem}_{i}{suffix}")
        if not candidate.exists():
            return candidate
        i += 1

def copy_from_dir(src: Path, dst_dir: Path) -> Path:
    dst = next_available_file(dst_dir / src.name)
    shutil.copy2(src, dst)
    return dst

def copy_from_zip(zip_path: Path, member: str, basename: str, dst_dir: Path) -> Path:
    dst = next_available_file(dst_dir / basename)
    with ZipFile(zip_path, "r") as zf:
        with zf.open(member, "r") as src_f, open(dst, "wb") as out_f:
            shutil.copyfileobj(src_f, out_f)
    return dst


def run_copy_mode(input_path: Path, output_dir: Path, exts: Set[str], apply: bool):
    print("Copy mode")
    print(f"  Input  : {input_path}")
    print(f"  Output : {output_dir}")

    if not output_dir.exists() or not output_dir.is_dir():
        print(f"ERROR: output_dir does not exist or is not a directory: {output_dir}", file=sys.stderr)
        sys.exit(1)

    is_zip = input_path.suffix.lower() == ".zip"

    if is_zip:
        zip_items = list_zip_video_members(input_path, exts)  # (member, base, size)
        input_names = [base.lower() for _, base, _ in zip_items]
    else:
        files = find_input_videos_dir(input_path, exts)
        zip_items = []
        input_names = [p.name.lower() for p in files]

    output_names = gather_output_name_set(output_dir)
    print(f"Scanned output recursively: {len(output_names):,} filenames indexed.")
    print(f"Input videos detected: {len(input_names):,}")

    # Decide what to copy (not present in output)
    to_copy = []
    if is_zip:
        for member, base, _ in zip_items:
            if base.lower() not in output_names:
                to_copy.append(("zip", member, base))
    else:
        for p in find_input_videos_dir(input_path, exts):
            if p.name.lower() not in output_names:
                to_copy.append(("dir", p, p.name))

    print(f"\nEligible to copy (not present in OUTPUT): {len(to_copy):,}")
    for _, ref, base in to_copy[:50]:
        label = base if isinstance(ref, str) else Path(ref).name
        print(f"  COPY -> {label}")
    if len(to_copy) > 50:
        print(f"  ... and {len(to_copy)-50} more")

    # If nothing to copy, do not create an 'other' folder; exit cleanly.
    if not to_copy:
        print("\nNothing new to copy. No folder created.")
        return

    target_dir = next_available_subfolder(output_dir, "other")
    print(f"\nTarget subfolder: {target_dir}")

    if not apply:
        print("\nDry run only. No files copied. Re-run with --apply to create the folder and copy files.")
        return

    # Create the target directory only if we actually have files to copy and are applying.
    target_dir.mkdir(parents=True, exist_ok=False)
    copied = 0
    errors = 0

    if is_zip:
        for _, member, base in to_copy:
            try:
                copy_from_zip(input_path, member, base, target_dir)
                copied += 1
            except Exception as e:
                errors += 1
                print(f"ERROR copying {member} from ZIP: {e}", file=sys.stderr)
    else:
        for _, src_path, _ in to_copy:
            try:
                copy_from_dir(src_path, target_dir)
                copied += 1
            except Exception as e:
                errors += 1
                print(f"ERROR copying {src_path}: {e}", file=sys.stderr)

    print(f"\nDone. Copied {copied:,} file(s) into {target_dir}. Errors: {errors}")
    print("Original input unchanged (you can delete it yourself if desired).")

def main():
    ap = argparse.ArgumentParser(description="Discover best destination folder or copy non-duplicate videos.")
    ap.add_argument("input_path", type=Path, help="Directory (non-recursive) or .zip containing candidate videos.")
    ap.add_argument("output_dir", nargs="?", type=Path, help="[COPY MODE] Destination directory (scanned recursively).")
    ap.add_argument("--apply", action="store_true", help="[COPY MODE] Perform copies. In DISCOVERY MODE: if exactly one folder has MatchNameSize%=100%, auto-copy into that folder.")
    ap.add_argument("--extensions", nargs="*", default=None, help="Video extensions (e.g., .mp4 .mov). Defaults to common types.")

    # Discovery mode args
    ap.add_argument("--videos-root", type=Path, help='Root of "YIR Clips" (e.g., "C:/OneDrive/Videos/YIR Clips").')
    ap.add_argument("--year", type=int, help="Four-digit year for discovery mode (e.g., 2022).")
    ap.add_argument("--top", type=int, default=10, help="[DISCOVERY] Number of ranked results to show.")
    ap.add_argument("--scoring", choices=["overlap", "jaccard"], default="overlap",
                    help="[DISCOVERY] Primary sort metric for ranking (name-only).")
    ap.add_argument("--size-tolerance", type=float, default=0.01,
                    help="[DISCOVERY] Relative size tolerance for name+size matches (e.g., 0.01 = 1%).")

    args = ap.parse_args()

    if not args.input_path.exists():
        print(f"ERROR: input path does not exist: {args.input_path}", file=sys.stderr)
        sys.exit(1)

    exts = normalize_exts(args.extensions)

    discovery_selected = args.videos_root is not None or args.year is not None
    copy_selected = args.output_dir is not None

    if discovery_selected and copy_selected:
        print("ERROR: Run either COPY MODE (provide OUTPUT_DIR) OR DISCOVERY MODE (provide --videos-root and --year), not both.", file=sys.stderr)
        sys.exit(1)

    if discovery_selected:
        if args.videos_root is None or args.year is None:
            print("ERROR: Discovery mode requires both --videos-root and --year.", file=sys.stderr)
            sys.exit(1)
        if args.year < 1900 or args.year > 2100:
            print("ERROR: --year must be a four-digit year.", file=sys.stderr)
            sys.exit(1)
        run_discovery(args.input_path, args.videos_root, args.year, exts, args.top, args.scoring, args.size_tolerance, args.apply)
        return

    if copy_selected:
        run_copy_mode(args.input_path, args.output_dir, exts, args.apply)
        return

    print("ERROR: You must choose a mode.\n"
          "  COPY MODE      : provide OUTPUT_DIR\n"
          "  DISCOVERY MODE : provide --videos-root and --year",
          file=sys.stderr)
    sys.exit(1)

if __name__ == "__main__":
    main()