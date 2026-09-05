from uuid import UUID
from datetime import date, timedelta

import streamlit as st

from database.db import get_engine
from database.db_display import fetch_member_information, fetch_family_tree
from charting.charts_family import tree_chart
from charting.general import set_sidebar, plot_graphviz_chart

PGHOST = st.secrets['postgresql']['host']
PGPORT = st.secrets['postgresql'].get('port', '5432')
PGDBNAME = st.secrets['postgresql']['database']
PGUSER = st.secrets['postgresql']['user']
PGPASSWORD = st.secrets['postgresql']['password']

CLOUDINARY_CLOUD = st.secrets['cloudinary']['cloud_name']

engine = get_engine(PGHOST, PGPORT, PGDBNAME, PGUSER, PGPASSWORD)

SCHEMA_NAME = 'dashboard' # demo if not logged in

# set up page
set_sidebar()
st.set_page_config(page_title='Franzonello Family YIR Appearances',
                   layout='wide')

members = fetch_member_information(engine, schema_name=SCHEMA_NAME)
persons = members[members['member_type'] == 'person'].sort_values(by='full_name')

col1, col2, col3 = st.columns(3)
with col1:
    person_id:UUID = st.selectbox('Person to Center', persons['member_id'],
                                  format_func=lambda x: persons[persons['member_id']==x]['full_name'].iloc[0],
                                  width=400)

with col2:
    choices = ['Images', 'Text']
    view_style = st.radio('View Style', choices, horizontal=True)
    use_images = view_style==choices[0]

with col3:
    traversal = st.checkbox('Include Extended Family')
    direction = 'bidirectional' if traversal else 'up_down'

##years = fetch_timeline_years(engine)
##year:int = st.selectbox('Year to Review', years, len(years) - 1, width=100)
st.title(f'Family Tree')

tree_data = fetch_family_tree(engine, person_id, schema_name=SCHEMA_NAME, direction=direction)
##cut_date = date(year + 1, 1, 1) - timedelta(days=1)

# gantt chart of appearances
graph = tree_chart(tree_data, cloud_name=CLOUDINARY_CLOUD, use_images=use_images)
plot_graphviz_chart(graph, use_images=use_images)