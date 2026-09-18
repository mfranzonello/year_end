"""Provide shared navigation and chart rendering for the Streamlit pages."""

from pathlib import Path
from shutil import which
from functools import wraps

import streamlit as st
from graphviz import Graph
from sqlalchemy import Engine
from cloudinary import Config as CloudConfig
from psycopg.errors import NotNullViolation, ForeignKeyViolation, UniqueViolation, CheckViolation

from pages.streamlit_auth import current_identity, render_account_controls, require_admin

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
                   {'link': 'edit_address', 'label': 'Edit Addresses', 'icon': '🗺️', 'tiers': ['admin']},
                   {'link': 'edit_move', 'label': 'Edit Moves', 'icon': '📦', 'tiers': ['admin']},
                   ],
         }

def allow_page(page):
    if Path(f'pages/{page["link"]}.py').exists():
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
            if any(allow_page(page) for page in pages[grouping]):
                st.divider()

        render_account_controls(identity)

def get_hash_funcs():
    hash_funcs = {Engine: lambda x: x.url,
                  CloudConfig: lambda x: x.cloud_name}
    return hash_funcs

def get_member_name_display(members, member_id):
    return members[members['member_id'] == member_id]['full_name'].iloc[0]

def get_value(x):
    if x != '':
        return x

def get_index(values, value):
    if value in values:
        return values.index(value)

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


# database write wrapper
def parse_db_error(e: Exception, function: str):
    error = e.orig
    if isinstance(error, NotNullViolation):
        st.error(f'**{function}**: `{error.diag.column_name}` is required.')

    elif isinstance(error, ForeignKeyViolation):
        st.error(f'**{function}**: This record cannot be changed because other records depend on it.')
       
    elif isinstance(error, UniqueViolation):
        st.error(f'**{function}**: A record with these values already exists.')

    elif isinstance(error, CheckViolation):
        st.error(f'**{function}**: One or more values are not valid.')

    else:
        st.error(f'**{function}**: The database rejected this change.')

# # def write_to_db(func, function_name):
# #     @wraps(func)
# #     def inner(*args, **kwargs):
# #         require_admin()
# #         try:
# #             result = func(*args, **kwargs)
# #         except Exception as e:
# #             parse_db_error(e, function_name)
    
# #     return inner