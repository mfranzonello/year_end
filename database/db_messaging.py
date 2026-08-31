"""Database access for provider-neutral messaging and calendar mappings."""

from collections.abc import Iterable

from sqlalchemy import Engine, text

from integrations.google.google_calendar.sync import SyncResult


def fetch_kickoff_folder_links(engine: Engine, project_year: int):
    """Return eligible people and their active project-folder share links."""
    if project_year < 1900:
        raise ValueError("project_year must be a four-digit year")
    statement = text(
        """
        SELECT DISTINCT
            folders.person_id,
            contacts.email_address,
            dashboard.display_names.full_name,
            repositories.repository_name,
            folder_locations.is_canonical,
            shares.share_url
        FROM project.folders AS folders
        JOIN dashboard.display_names AS display_names
          ON display_names.member_id = folders.member_id
        JOIN messaging.contacts AS contacts
          ON contacts.person_id = folders.person_id
        JOIN project.folder_locations AS folder_locations
          ON folder_locations.folder_id = folders.folder_id
        JOIN ingestion.repositories AS repositories
          ON repositories.repository_id = folder_locations.repository_id
        JOIN project.shares AS shares
          ON shares.folder_location_id = folder_locations.folder_location_id
         AND shares.is_active = true
        WHERE folders.project_year = :project_year
          AND contacts.email_address IS NOT NULL
          AND NOT EXISTS (
              SELECT 1
              FROM messaging.no_contacts AS no_contacts
              WHERE no_contacts.person_id = folders.person_id
                AND no_contacts.project_year = :project_year
          )
        ORDER BY
            display_names.full_name,
            folder_locations.is_canonical DESC,
            repositories.repository_name
        """
    )
    with engine.begin() as connection:
        return connection.execute(
            statement,
            {"project_year": project_year},
        ).mappings().all()


def upsert_calendar_event_mappings(
    engine: Engine,
    results: Iterable[SyncResult],
) -> int:
    """Persist verified recurring-master IDs for person or union sources."""
    mapped = 0
    with engine.begin() as connection:
        for result in results:
            if result.event_id is None or result.action == "stale":
                continue
            source_type, source_id = result.key
            match source_type:
                case "birthday":
                    statement = text(
                        """
                        INSERT INTO messaging.calendar_events (
                            person_id, external_event_id, last_verified_at
                        )
                        VALUES (
                            CAST(:source_id AS uuid), :external_event_id, CURRENT_TIMESTAMP
                        )
                        ON CONFLICT (person_id) WHERE person_id IS NOT NULL
                        DO UPDATE SET
                            external_event_id = EXCLUDED.external_event_id,
                            last_verified_at = CURRENT_TIMESTAMP
                        """
                    )
                case "anniversary":
                    statement = text(
                        """
                        INSERT INTO messaging.calendar_events (
                            union_id, external_event_id, last_verified_at
                        )
                        VALUES (
                            CAST(:source_id AS uuid), :external_event_id, CURRENT_TIMESTAMP
                        )
                        ON CONFLICT (union_id) WHERE union_id IS NOT NULL
                        DO UPDATE SET
                            external_event_id = EXCLUDED.external_event_id,
                            last_verified_at = CURRENT_TIMESTAMP
                        """
                    )
                case _:
                    raise ValueError(f"Unsupported calendar source type: {source_type!r}")
            connection.execute(
                statement,
                {"source_id": source_id, "external_event_id": result.event_id},
            )
            mapped += 1
    return mapped
