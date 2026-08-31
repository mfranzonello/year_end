"""Owner-only landing page for future family-record administration."""

import streamlit as st

from charting.general import set_sidebar
from streamlit_auth import require_admin


set_sidebar()
identity = require_admin()

st.title("Administration")
st.write(f"Signed in as {identity.display_name or 'the project administrator'}.")
st.info(
    "Authentication is active. People, animals, relationships, and Calendar "
    "reconciliation controls will be added here incrementally."
)
