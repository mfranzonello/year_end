"""Owner-only landing page for future family-record administration."""

import streamlit as st

from database.db import get_engine
from database.db_display import fetch_member_summary
from pages.streamlit_auth import get_database_credentials, require_admin
from pages.general import set_sidebar

set_sidebar()
identity = require_admin()

engine = get_engine(*get_database_credentials())

st.title("Add or Edit a Member")

members = fetch_member_summary(engine).sort_values('sort_order')
member_id = st.selectbox()

def get_member_name_display(members, member_id):
    return members[members['member_id'] == member_id].iloc[0]

st.selectbox(
    'Select Member',
    members['member_id'], placeholder='Choose a family member to view',
    format_func=lambda x: get_member_name_display(members, x), index=None,
    width=350
    )



