from pathlib import Path

import streamlit as st

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

# plot altair chart
def plot_altair_chart(chart):
    if chart:
        st.altair_chart(chart, use_container_width=True)