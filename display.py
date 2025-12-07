from pathlib import Path

import streamlit as st
import altair as alt

from database.db import get_engine

PGHOST = st.secrets['postgresql']['host']
PGPORT = st.secrets['postgresql'].get('port', '5432')
PGDBNAME = st.secrets['postgresql']['database']
PGUSER = st.secrets['postgresql']['user']
PGPASSWORD = st.secrets['postgresql']['password']

CLOUDINARY_CLOUD = st.secrets['cloudinary']['cloud_name']

engine = get_engine(PGHOST, PGPORT, PGDBNAME, PGUSER, PGPASSWORD)

pages = [('yir_count', 'YIR Status'),
         ('yir_growth', 'YIR Growth'),
         ('yir_time', 'YIR Timeline'),
         ('family_tree', 'Family Tree')]
existing_pages = [(page, n) for (p, n) in pages if (page := f'pages/{p}.py') and Path(page).exists()]

# set up page
def set_sidebar():
    st.set_page_config(page_title='Franzonello Family')
    with st.sidebar:
        st.page_link('display.py', label='Home')
        for page_py, page_name in existing_pages:
            st.page_link(page_py, label=page_name)

set_sidebar()

st.title(f'Franzonello Family Fun Times')
st.write(f'Choose your adventure!')

cols = st.columns(len(existing_pages))
for col, (page_py, page_name) in zip(cols, existing_pages):
    with col:
        if st.button(page_name):
            st.switch_page(page_py)