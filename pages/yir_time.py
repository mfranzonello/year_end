from uuid import UUID

import streamlit as st

from database.db import get_engine
from database.db_adobe import fetch_timeline_years, fetch_actor_spans, fetch_markers
from database.db_family import fetch_founder
from family_tree.charts import timeline_chart
from family_tree.ancestry import list_relatives
from display import set_sidebar

PGHOST = st.secrets['postgresql']['host']
PGPORT = st.secrets['postgresql'].get('port', '5432')
PGDBNAME = st.secrets['postgresql']['database']
PGUSER = st.secrets['postgresql']['user']
PGPASSWORD = st.secrets['postgresql']['password']

CLOUDINARY_CLOUD = st.secrets['cloudinary']['cloud_name']

engine = get_engine(PGHOST, PGPORT, PGDBNAME, PGUSER, PGPASSWORD)

# set up page
set_sidebar()
st.set_page_config(page_title='Franzonello Family YIR Appearances',
                   layout='wide')
years = fetch_timeline_years(engine)
year:int = st.selectbox('Year to Review', years, len(years) - 1, width=100)
st.title(f'Franzonello YIR {year}')

founder_id = fetch_founder(engine) 

relatives = list_relatives(engine, founder_id,
                           include_animals=True, cut_year=year, include_deceased=False)

print(f'{relatives.columns=}')
relative_ids = relatives['member_id'].tolist()
actor_spans = fetch_actor_spans(engine, year, relative_ids=relative_ids)
actor_spans['clan_name'] = actor_spans['clan_name'].where(actor_spans['member_id'].isin(relative_ids),
                                                          'Friends')
actor_spans = actor_spans.merge(relatives, on='member_id')
print(f'{actor_spans.columns=}')

markers = fetch_markers(engine, year)

# gantt chart of appearances
chart = timeline_chart(actor_spans, markers, cloud_name=CLOUDINARY_CLOUD)
st.altair_chart(chart, use_container_width=True) # width='stretch')