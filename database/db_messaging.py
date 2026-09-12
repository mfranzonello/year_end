"""Database access for provider-neutral messaging and calendar mappings."""

from collections.abc import Iterable

from sqlalchemy import text
from integrations.google.google_calendar.sync import SyncResult

from database.db import read_sql, execute_sql, Engine, DataFrame

def fetch_addresses(engine: Engine) -> DataFrame:
    sql = f'''
    SELECT address_id, address_name, zip_code
    FROM messaging.addresses
    ;'''
    return read_sql(engine, sql)

def insert_address(engine: Engine, information: dict):
    sql = f'''
    INSERT INTO messaging.addresses (address_name, zip_code)
    VALUES (:address_name, :zip_code)
    RETURNING address_id;'''
    return execute_sql(engine, sql, params=information, returning=True)[0][0]

def update_address(engine: Engine, information: dict):
    sql = f'''
    UPDATE messaging.addresses
    SET address_name = :address_name, zip_code = :zip_code
    WHERE address_id = :address_id
    ;'''
    execute_sql(engine, sql, params=information)

def remove_address(engine: Engine, address_id: int):
    sql = f'''
    DELETE FROM messaging.addresses
    WHERE address_id = :address_id
    ;'''
    execute_sql(engine, sql, params={'address_id': address_id})

def fetch_address_moves(engine: Engine):
    sql = f'''
    SELECT address_id, address_name, zip_code, move_id, person_id, start_date
    FROM messaging.addresses JOIN messaging.address_moves USING (address_id)
    ;'''
    return read_sql(engine, sql)

def insert_address_move(engine: Engine, information: dict):
    sql = f'''
    INSERT INTO messaging.address_moves (address_id, person_id, start_date)
    VALUES (:address_id, :person_id, :start_date)
    ;'''
    execute_sql(engine, sql, params=information)

def update_address_move(engine: Engine, information):
    sql = f'''
    UPDATE messaging.address_moves
    SET start_date = :start_date
    WHERE move_id = :move_id
    ;'''
    execute_sql(engine, sql, params=information)

def remove_address_move(engine: Engine, move_id: int):
    sql = f'''
    DELETE FROM messaging.address_moves
    WHERE move_id = :move_id
    ;'''
    execute_sql(engine, sql, params={'move_id': move_id})

def fetch_homeless(engine: Engine) -> DataFrame:
    sql = f'''
    SELECT person_id FROM persons WHERE NOT EXISTS
    (SELECT 1 FROM messaging.address_moves WHERE persons.person_id = address_moves.person_id)
    ;'''
    return read_sql(engine, sql)

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
