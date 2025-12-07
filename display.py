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

# set up page
def set_sidebar():
    st.set_page_config(page_title='Franzonello Family')
    with st.sidebar:
        st.page_link('display.py', label='Home')
        for page_py, page_name in pages:
            page_module = f'pages/{page_py}.py'
            if Path(page_module).exists():
                st.page_link(page_module, label=page_name)

set_sidebar()
st.title(f'Franzonello Family Fun Times')
st.write(f'Choose your adventure!')

for page_py, page_name in pages:
    page_module = f'pages/{page_py}.py'
    if Path(page_module).exists():
        if st.button(page_name):
            st.switch_page(page_module)