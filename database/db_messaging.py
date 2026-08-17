"""Database access for provider-neutral messaging and calendar mappings."""

from collections.abc import Iterable

from sqlalchemy import Engine, text

from integrations.google.google_calendar.sync import SyncResult


def upsert_calendar_event_mappings(
    engine: Engine,
    results: Iterable[SyncResult],
) -> int:
    """Persist verified recurring-master IDs for person or marriage sources."""
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
                            marriage_id, external_event_id, last_verified_at
                        )
                        VALUES (
                            CAST(:source_id AS uuid), :external_event_id, CURRENT_TIMESTAMP
                        )
                        ON CONFLICT (marriage_id) WHERE marriage_id IS NOT NULL
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
