"""Owner-only landing page for future family-record administration."""

import streamlit as st

from pages.general import set_sidebar
from pages.streamlit_auth import get_database_credentials, require_admin
from database.db_create import initialize_database, ConnectionSettings

set_sidebar()
identity = require_admin()

st.title("Administration")
st.write(f"Signed in as {identity.display_name or 'the project administrator'}.")
st.info(
    "Authentication is active. People, animals, relationships, and Calendar "
    "reconciliation controls will be added here incrementally."
)

if st.button('Reset demo database', type='primary'):
    with st.spinner('Resetting demo database...', show_time=True):
        connection_settings = ConnectionSettings.from_credentials(*get_database_credentials(demo=True))
        initialize_database(connection_settings, mode='demo', apply=True)