from pathlib import Path

import streamlit as st
from graphviz import Graph

from streamlit_auth import current_identity, render_account_controls

pages = [('yir_count', 'YIR Status'),
         ('yir_growth', 'YIR Growth'),
         ('yir_time', 'YIR Timeline'),
         ('family_tree', 'Family Tree')]
existing_pages = [(page, n) for (p, n) in pages if (page := f'pages/{p}.py') and Path(page).exists()]

# set up page
def set_sidebar():
    st.set_page_config(page_title='Franzonello Family')
    identity = current_identity()
    with st.sidebar:
        st.page_link('display.py', label='Home')
        for page_py, page_name in existing_pages:
            st.page_link(page_py, label=page_name)
        if identity.is_admin:
            st.page_link(
                'pages/admin.py',
                label='Administration',
                icon=':material/admin_panel_settings:',
            )
        st.divider()
        render_account_controls(identity)

# plot altair chart
def plot_altair_chart(chart):
    if chart:
        st.altair_chart(chart)

def plot_graphviz_chart(graph:Graph, use_images=False):
    if graph:
        if use_images:
            st.image(graph.pipe(format='png'))
        else:
            st.graphviz_chart(graph)