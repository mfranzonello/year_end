from uuid import UUID

import streamlit as st

from database.db import get_engine
from database.db_adobe import fetch_timeline_years, fetch_actor_spans, fetch_markers
from family_tree.charts import timeline_chart
from family_tree.ancestry import list_relatives
from display import set_sidebar

PGHOST = st.secrets['postgresql']['host']
PGPORT = st.secrets['postgresql'].get('port', '5432')
PGDBNAME = st.secrets['postgresql']['database']
PGUSER = st.secrets['postgresql']['user']
PGPASSWORD = st.secrets['postgresql']['password']

CLOUDINARY_CLOUD = st.secrets['cloudinary']['cloud_name']

FOUNDER_ID = UUID('ad1d95a0-1eea-4f7c-a802-256dda0904bb')

engine = get_engine(PGHOST, PGPORT, PGDBNAME, PGUSER, PGPASSWORD)

# set up page
set_sidebar()
st.set_page_config(page_title='Franzonello Family YIR Appearances',
                   layout='wide')
years = fetch_timeline_years(engine)
year:int = st.selectbox('Year to Review', years, len(years) - 1, width=100)
st.title(f'Franzonello YIR {year}')

relatives = list_relatives(engine, FOUNDER_ID,
                           include_animals=True, cut_year=year)
actor_spans = fetch_actor_spans(engine, year, relative_ids=relatives)
actor_spans['clan_name'] = actor_spans.where(actor_spans['member_id'].isin(relatives), 'Friends')['clan_name']
markers = fetch_markers(engine, year)


# gantt chart of appearances
chart = timeline_chart(actor_spans, markers)
st.altair_chart(chart, use_container_width=True) # width='stretch')