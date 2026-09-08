"""Display the interactive family tree when the Graphviz executable is available."""

from uuid import UUID
from datetime import date, timedelta

import streamlit as st

from database.db import get_engine
from database.db_display import fetch_member_summary, fetch_member_birth_date, fetch_family_tree, fetch_founder_id
from charting.charts_family import tree_chart
from pages.general import set_sidebar, plot_graphviz_chart, graphviz_available

# Guard direct page links before loading data or building the tree.
set_sidebar()
st.set_page_config(page_title='Franzonello Family YIR Appearances',
                   layout='wide')
if not graphviz_available():
    st.info('The family tree is temporarily unavailable on this deployment. '
            'Please choose another page from the sidebar.')
    st.stop()

PGHOST = st.secrets['postgresql']['host']
PGPORT = st.secrets['postgresql'].get('port', '5432')
PGDBNAME = st.secrets['postgresql']['database']
PGUSER = st.secrets['postgresql']['user']
PGPASSWORD = st.secrets['postgresql']['password']

CLOUDINARY_CLOUD = st.secrets['cloudinary']['cloud_name']

GENERATION_LIMIT = 20

engine = get_engine(PGHOST, PGPORT, PGDBNAME, PGUSER, PGPASSWORD)

SCHEMA_NAME = 'dashboard' # demo if not logged in

member_summary = fetch_member_summary(engine, schema_name=SCHEMA_NAME)
persons = member_summary[member_summary['member_type'] == 'person'].sort_values(by='sort_order').reset_index(drop=True)

cols = st.columns(5)
with cols[0]:
    founder_id = fetch_founder_id(engine, schema_name=SCHEMA_NAME)
    person_id:UUID = st.selectbox('Person to Center', persons['member_id'],
                                  format_func=lambda x: persons[persons['member_id']==x]['full_name'].iloc[0],
                                  index = int(persons[persons['member_id'] == founder_id].index[0]),
                                  width=400)

with cols[1]:
    cut_date = st.date_input('As of Date', value=None, min_value=fetch_member_birth_date(engine, person_id, schema_name=SCHEMA_NAME),
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

tree_data = fetch_family_tree(engine, person_id, schema_name=SCHEMA_NAME, cut_date=cut_date, direction=direction,
                              exclude_persons=exclude_persons, include_animals=include_animals)

if len(tree_data):
    # graph with nodes and edges
    with st.spinner('Building tree...', show_time=True):
        graph = tree_chart(engine, tree_data, cloud_name=CLOUDINARY_CLOUD,
                           use_images=use_images, generation_limit=GENERATION_LIMIT)
    plot_graphviz_chart(graph, use_images=use_images)
