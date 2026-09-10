"""Provide shared navigation and chart rendering for the Streamlit pages."""

from pathlib import Path
from shutil import which

import streamlit as st
from graphviz import Graph

from family_tree.cloudy import get_image_url
from pages.streamlit_auth import get_database_credentials, current_identity, current_tier, render_account_controls

def graphviz_available() -> bool:
    """Check for Graphviz's system executable, separate from its Python package."""
    return which('dot') is not None


pages = [('yir_count', 'YIR Status', None),
         ('yir_growth', 'YIR Growth', None),
         ('yir_time', 'YIR Timeline', None),
         ('family_tree', 'Family Tree', ['viewer', 'member', 'admin']),
         ('family_member', 'Family Members', ['viewer', 'member', 'admin'])]
existing_pages = [(page, n, g) for (p, n, g) in pages
                  if (page := f'pages/{p}.py') and Path(page).exists()
                  and (p != 'family_tree' or graphviz_available())]

def allow_page(page_gate):
    return page_gate is None or current_identity().tier in page_gate

# set up page
def set_sidebar():
    st.set_page_config(page_title='Family Fun Times')
    identity = current_identity()

    with st.sidebar:
        st.page_link('display.py', label='Home')
        for page_py, page_name, page_gate in existing_pages:
            if allow_page(page_gate):
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