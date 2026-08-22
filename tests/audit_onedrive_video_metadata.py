"""Audit OneDrive video-facet coverage across representative archive formats."""

from collections import Counter
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import quote

from sqlalchemy import text

from common.config import read_toml
from common.secret import secrets
from common.structure import VIDEO_EXTS
from adobe.bridge import _XMP_END, _XMP_STARTS, _rating_from_xmp, get_resolution
from database.db import get_engine
from repositories.iterate import get_media_locations
from integrations.microsoft.onedrive.client import (
    GraphRequestError, _get, find_folder_id, list_children, list_descendant_files,
)
from integrations.microsoft.auth import get_access_token


VIDEO_FIELDS = (
    "duration", "width", "height", "frameRate", "bitrate", "fourCC",
    "audioFormat", "audioChannels", "audioSamplesPerSecond", "audioBitsPerSample",
)


def _engine():
    config = secrets["postgresql"]
    return get_engine(
        config["host"], str(config["port"]), config["database"],
        config["user"], config["password"],
    )


def _representative_groups(engine) -> list[dict]:
    """Choose the smallest year/media group containing each stored extension."""
    query = text(r'''
        WITH counts AS (
            SELECT
                f.media_type,
                f.project_year,
                lower(substring(p.file_name from '\.[^.]+$')) AS extension,
                count(*) AS database_files
            FROM project.files p
            JOIN project.folders f USING (folder_id)
            GROUP BY f.media_type, f.project_year, extension
        ), ranked AS (
            SELECT *, row_number() OVER (
                PARTITION BY extension
                ORDER BY database_files, project_year
            ) AS preference
            FROM counts
        )
        SELECT media_type, project_year, extension, database_files
        FROM ranked
        WHERE preference = 1
        ORDER BY extension
    ''')
    with engine.connect() as connection:
        return [dict(row) for row in connection.execute(query).mappings()]


def _year_files(root: str, supfolder_name: str, project_year: int) -> list[dict]:
    """Return video items beneath one configured OneDrive media year."""
    path = "/".join((root.strip("/\\"), supfolder_name, str(project_year)))
    year_id = find_folder_id(path)
    children = list_children(year_id)
    files = [
        {**item, "folder_name": None, "relative_parent": None}
        for item in children if "file" in item
    ]
    for folder in (item for item in children if "folder" in item):
        files.extend(
            {**item, "folder_name": folder["name"]}
            for item in list_descendant_files(folder["id"])
        )
    return [
        item for item in files
        if Path(item.get("name", "")).suffix.lower() in VIDEO_EXTS
    ]


def _known_metadata(engine, group: dict) -> dict[tuple, tuple]:
    """Return locally derived metadata keyed to a repository-relative file."""
    query = text('''
        SELECT folder_name, subfolder_name, file_name,
               video_duration, video_resolution
        FROM project.files
        JOIN project.folders USING (folder_id)
        WHERE media_type = :media_type
          AND project_year = :project_year
          AND lower(substring(file_name from '\\.[^.]+$')) = :extension
    ''')
    with engine.connect() as connection:
        rows = connection.execute(query, group).mappings()
        return {
            (row["folder_name"], row["subfolder_name"], row["file_name"]): (
                row["video_duration"], row["video_resolution"],
            )
            for row in rows
        }


def audit_rating_surface(include_item_id: bool = False) -> dict:
    """Inspect one rated file for Graph fields named like XMP or rating data."""
    engine = _engine()
    query = text('''
        SELECT fl.repository_item_id, p.subfolder_name, p.file_name, p.video_rating
        FROM project.files p
        JOIN project.folders f USING (folder_id)
        JOIN project.folder_locations fl USING (folder_id)
        JOIN ingestion.repositories r USING (repository_id)
        WHERE p.video_rating IS NOT NULL
          AND r.repository_name = 'OneDrive'
        LIMIT 1
    ''')
    try:
        with engine.connect() as connection:
            sample = connection.execute(query).mappings().one_or_none()
    finally:
        engine.dispose()
    if sample is None:
        return {"rated_sample_found": False, "rating_like_fields": []}

    matching_items = [
        item for item in list_descendant_files(sample["repository_item_id"])
        if item["name"] == sample["file_name"]
        and item.get("relative_parent") == sample["subfolder_name"]
    ]
    if len(matching_items) != 1:
        return {
            "rated_sample_found": True,
            "cloud_item_matches": len(matching_items),
            "rating_like_fields": [],
        }

    item_id = quote(matching_items[0]["id"], safe="")
    metadata = _get(
        f"/me/drive/items/{item_id}",
        access_token=get_access_token("onedrive"),
    )
    matches = []

    def inspect(value, parent: str = "") -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                path = f"{parent}.{key}" if parent else key
                if "rating" in key.casefold() or "xmp" in key.casefold():
                    matches.append(path)
                inspect(child, path)
        elif isinstance(value, list):
            for child in value:
                inspect(child, parent)

    inspect(metadata)
    result = {
        "rated_sample_found": True,
        "cloud_item_matches": 1,
        "rating_like_fields": sorted(set(matches)),
        "expected_rating": sample["video_rating"],
    }
    if include_item_id:
        result["item_id"] = matching_items[0]["id"]
    return result


def audit_rating_range() -> dict:
    """Try extracting Bridge XMP from a guarded one-MiB cloud byte range."""
    surface = audit_rating_surface(include_item_id=True)
    item_id = surface.pop("item_id", None)
    if item_id is None:
        return surface

    metadata = _get(
        f"/me/drive/items/{quote(item_id, safe='')}?"
        "$select=size,@microsoft.graph.downloadUrl",
        access_token=get_access_token("onedrive"),
    )
    download_url = metadata.get("@microsoft.graph.downloadUrl")
    size = metadata.get("size")
    if (
        not isinstance(download_url, str) or not download_url
        or not isinstance(size, int) or size <= 0
    ):
        return {**surface, "range_supported": False, "cloud_rating": None}

    start = max(0, size - 1048576)
    request = Request(
        download_url,
        headers={"Range": f"bytes={start}-{size - 1}"},
    )
    with urlopen(request, timeout=30) as response:
        if response.status != 206:
            return {**surface, "range_supported": False, "cloud_rating": None}
        data = response.read(1048577)
    if len(data) > 1048576:
        return {**surface, "range_supported": False, "cloud_rating": None}

    starts = [data.find(marker) for marker in _XMP_STARTS]
    starts = [position for position in starts if position >= 0]
    if not starts:
        return {**surface, "range_supported": True, "cloud_rating": None}
    start = min(starts)
    end = data.find(_XMP_END, start)
    if end < 0:
        return {**surface, "range_supported": True, "cloud_rating": None}
    xmp = data[start:end + len(_XMP_END)]
    return {
        **surface,
        "range_supported": True,
        "cloud_rating": _rating_from_xmp(xmp),
    }


def main() -> None:
    """Print aggregate Graph facet coverage without exposing archive filenames."""
    engine = _engine()
    media_folders = dict(get_media_locations(engine))
    groups = _representative_groups(engine)

    root = read_toml("drives")["local_storage"]["onedrive"]["videos"]
    for group in groups:
        extension = group["extension"]
        try:
            files = [
                item for item in _year_files(
                    root,
                    media_folders[group["media_type"]],
                    group["project_year"],
                )
                if Path(item["name"]).suffix.lower() == extension
            ]
        except GraphRequestError as error:
            print({**group, "error": str(error).split(":", 1)[0]})
            continue

        facets = [item.get("video") for item in files]
        facets = [facet for facet in facets if isinstance(facet, dict)]
        coverage = Counter({field: 0 for field in VIDEO_FIELDS})
        for facet in facets:
            coverage.update(field for field in VIDEO_FIELDS if facet.get(field) is not None)
        known = _known_metadata(engine, group)
        compared = duration_matches = resolution_matches = 0
        duration_differences = []
        for item in files:
            key = (item["folder_name"], item.get("relative_parent"), item["name"])
            local_duration, local_resolution = known.get(key, (None, None))
            video = item.get("video") or {}
            if local_duration is None or local_resolution is None:
                continue
            compared += 1
            graph_duration = video.get("duration")
            if graph_duration is not None:
                difference = round(graph_duration / 1000) - local_duration
                if abs(difference) <= 1:
                    duration_matches += 1
                else:
                    duration_differences.append(difference)
            width, height = video.get("width"), video.get("height")
            if width and height and get_resolution(width, height) == local_resolution:
                resolution_matches += 1
        print({
            **group,
            "onedrive_files": len(files),
            "video_facets": len(facets),
            "coverage": dict(coverage),
            "compared_to_local": compared,
            "duration_matches_within_1s": duration_matches,
            "duration_differences_seconds": sorted(duration_differences),
            "resolution_matches": resolution_matches,
        })

    engine.dispose()


if __name__ == "__main__":
    main()
