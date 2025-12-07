import streamlit as st

from database.db import get_engine
from database.db_adobe import fetch_timeline_years, fetch_actor_spans
from family_tree.charts import timeline_chart
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

actor_spans = fetch_actor_spans(engine, year)

# gantt chart of appearances
chart = timeline_chart(actor_spans)
st.altair_chart(chart, use_container_width=True) # width='stretch')