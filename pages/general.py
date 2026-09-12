"""Provide shared navigation and chart rendering for the Streamlit pages."""

from pathlib import Path
from shutil import which

import streamlit as st
from graphviz import Graph
from sqlalchemy import Engine

from pages.streamlit_auth import current_identity, render_account_controls

def graphviz_available() -> bool:
    """Check for Graphviz's system executable, separate from its Python package."""
    return which('dot') is not None

pages = {'project': [{'link': 'yir_count', 'label': 'YIR Status', 'icon': '📊'},
                     {'link': 'yir_growth', 'label': 'YIR Growth', 'icon': '📈'},
                     {'link': 'yir_time', 'label': 'YIR Timeline', 'icon': '🎞️'},
                     ],
         'family': [{'link': 'family_tree', 'label': 'Family Tree', 'icon': '🌳'},
                    {'link': 'family_member', 'label': 'Family Members', 'icon': '👨‍👩‍👧‍👦'},
                    ],
         'admin': [{'link': 'admin', 'label': 'Administration', 'icon': ':material/admin_panel_settings:', 'tiers': ['admin']},
                   {'link': 'edit_member', 'label': 'Edit Members', 'icon': '👥', 'tiers': ['admin']},
                   ],
         }

def allow_page(page):
    return page.get('tiers') is None or current_identity().tier in page['tiers']

def get_icon(page):
    return page.get('icon')

def get_link(page):
    return f'pages/{page["link"]}.py'

# set up page
def set_sidebar():
    st.set_page_config(page_title='Family Fun Times')
    identity = current_identity()

    with st.sidebar:
        st.page_link('display.py', label='Home', icon='🏠')
        st.divider()
        for grouping in pages:
            for page in pages[grouping]:
                if allow_page(page):
                    st.page_link(get_link(page), label=page['label'], icon=get_icon(page))
            st.divider()

        render_account_controls(identity)

def get_hash_funcs():
    hash_funcs = {Engine: lambda x: x.url}
    return hash_funcs

def get_member_name_display(members, member_id):
    return members[members['member_id'] == member_id]['full_name'].iloc[0]

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