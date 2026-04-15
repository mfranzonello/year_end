from sqlalchemy import Engine

from database.db_project import fetch_media_types

def get_media_locations(engine: Engine) -> list[tuple]:
    media_types = fetch_media_types(engine)
    media_locations = [(media_type, supfolder_name) for _, (media_type, supfolder_name) in media_types.iterrows()]
    return media_locations

