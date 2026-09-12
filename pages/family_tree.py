"""Display the interactive family tree when the Graphviz executable is available."""

from uuid import UUID
from datetime import date, timedelta

import streamlit as st

from database.db import get_engine
from database.db_display import fetch_member_summary, fetch_member_birth_date, fetch_family_tree, fetch_founder_id
from pages.streamlit_auth import get_database_credentials, get_cloud_credentials
from pages.general import set_sidebar, get_hash_funcs, plot_graphviz_chart, graphviz_available
from charting.charts_family import tree_chart
from charting.cloudy import configure_cloud

# Guard direct page links before loading data or building the tree.
set_sidebar()
st.set_page_config(page_title='Family Tree',
                   layout='wide')
if not graphviz_available():
    st.info('The family tree is temporarily unavailable on this deployment. '
            'Please choose another page from the sidebar.')
    st.stop()

GENERATION_LIMIT = 20

engine = get_engine(*get_database_credentials())
cloud = configure_cloud(*get_cloud_credentials())

@st.cache_data(hash_funcs=get_hash_funcs())
def get_founder_id(engine):
    return fetch_founder_id(engine)

@st.cache_data(hash_funcs=get_hash_funcs())
def get_member_summary(engine):
    return fetch_member_summary(engine)

@st.cache_data(hash_funcs=get_hash_funcs())
def get_member_birth_date(engine, person_id):
    return fetch_member_birth_date(engine, person_id)

@st.cache_data(hash_funcs=get_hash_funcs())
def get_tree_data(engine, person_id, cut_date, direction, exclude_persons, include_animals):
    tree_data = fetch_family_tree(engine, person_id, cut_date=cut_date, direction=direction,
                                  exclude_persons=exclude_persons, include_animals=include_animals)

    for col in ['parent_ids', 'lineage', 'ancestry']:
        tree_data[col] = tree_data[col].apply(lambda x: tuple(x) if isinstance(x, list) else x)

    return tree_data


member_summary = get_member_summary(engine)
persons = member_summary[member_summary['member_type'] == 'person'].sort_values(by='sort_order').reset_index(drop=True)

cols = st.columns(5)
with cols[0]:
    founder_id = get_founder_id(engine)
    person_id:UUID = st.selectbox('Person to Center', persons['member_id'],
                                  format_func=lambda x: persons[persons['member_id']==x]['full_name'].iloc[0],
                                  index = int(persons[persons['member_id'] == founder_id].index[0]),
                                  width=400)

with cols[1]:
    
    cut_date = st.date_input('As of Date', value=None, min_value=get_member_birth_date(engine, person_id),
                             help='Only show family members who were alive on or before this date.')

with cols[3]:
    options = ['living', 'all']
    include_persons = st.radio('Show People',
                               options=options,
                               format_func=lambda x: {'living': 'Living People', 'all': 'All People'}[x],
                               index=options.index('all'),
                               help='Choose whether to include people in the family tree. "Living People" shows only people that were alive on or before the selected date. "All People" shows all known people, regardless of their status.')
    exclude_persons = include_persons != 'all'


with cols[2]:
    options=['living', 'all', 'none']
    include_animals = st.radio('Show Pets',
                               options=options,
                               index=options.index('all'),
                               format_func=lambda x: {'living': 'Living Pets', 'all': 'All Pets', 'none': 'No Pets'}[x],
                               help='Choose whether to include pets in the family tree. "Living Pets" shows only pets that were alive on or before the selected date. "All Pets" shows all known pets, regardless of their status. "No Pets" excludes pets from the family tree.')


with cols[4]:
    choices = ['Images', 'Text']
    use_images = st.radio('View Style',
                          options=[True, False],
                          format_func=lambda x: {True: 'Images', False: 'Text'}[x],
                          help='Show the graph with images or text-only')
    
# # with cols[5]:
# #     extended = st.checkbox('Extended Tree', value=False, help='Include all known family members, even if not directly related to the selected person.')
# #     direction = 'bidirectional' if extended else 'up_down'
direction = 'up_down'  # default to up_down for now, can add extended option later

st.title(f'Family Tree')

tree_data = get_tree_data(engine, person_id, cut_date, direction, exclude_persons, include_animals)

@st.cache_data(ttl='1d', hash_funcs=get_hash_funcs()) ## need to change lists in tree_data
def create_tree_chart(engine, tree_data, cloud, use_images, generation_limit):
    return tree_chart(engine, tree_data, cloud=cloud,
                      use_images=use_images, generation_limit=generation_limit)

if len(tree_data):
    # graph with nodes and edges
    with st.spinner('Building tree...', show_time=True):
        graph = create_tree_chart(engine, tree_data, cloud, use_images, GENERATION_LIMIT)
        plot_graphviz_chart(graph, use_images=use_images)
    
