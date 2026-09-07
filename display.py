from pathlib import Path

import streamlit as st

from database.db import get_engine
from pages.general import set_sidebar, existing_pages, allow_page

PGHOST = st.secrets['postgresql']['host']
PGPORT = st.secrets['postgresql'].get('port', '5432')
PGDBNAME = st.secrets['postgresql']['database']
PGUSER = st.secrets['postgresql']['user']
PGPASSWORD = st.secrets['postgresql']['password']

CLOUDINARY_CLOUD = st.secrets['cloudinary']['cloud_name']

engine = get_engine(PGHOST, PGPORT, PGDBNAME, PGUSER, PGPASSWORD)

set_sidebar()

st.title(f'Franzonello Family Fun Times')
st.write(f'Choose your adventure!')

viewable_ages = [p for p in existing_pages if allow_page(p[-1])]
cols = st.columns(len(viewable_ages))
for col, (page_py, page_name, page_gate) in zip(cols, viewable_ages):
    with col:
        if st.button(page_name):
            st.switch_page(page_py)