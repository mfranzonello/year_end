from uuid import UUID
from datetime import date, timedelta

import streamlit as st

from database.db import get_engine
from database.db_display import fetch_actor_spans
from database.db_adobe import fetch_timeline_years, fetch_markers
from charting.charts import timeline_chart
from charting.general import set_sidebar, plot_altair_chart

PGHOST = st.secrets['postgresql']['host']
PGPORT = st.secrets['postgresql'].get('port', '5432')
PGDBNAME = st.secrets['postgresql']['database']
PGUSER = st.secrets['postgresql']['user']
PGPASSWORD = st.secrets['postgresql']['password']

CLOUDINARY_CLOUD = st.secrets['cloudinary']['cloud_name']

engine = get_engine(PGHOST, PGPORT, PGDBNAME, PGUSER, PGPASSWORD)

DASHBOARD_SCHEMA = 'dashboard' # demo if not logged in

# set up page
set_sidebar()
st.set_page_config(page_title='Franzonello Family YIR Appearances',
                   layout='wide')
years = fetch_timeline_years(engine)
year:int = st.selectbox('Year to Review', years, len(years) - 1, width=100)
st.title(f'Franzonello YIR {year}')

cut_date = date(year + 1, 1, 1) - timedelta(days=1)

actor_spans = fetch_actor_spans(engine, year, schema_name=DASHBOARD_SCHEMA, cut_date=cut_date)
markers = fetch_markers(engine, year)

# gantt chart of appearances
chart = timeline_chart(actor_spans, markers, cloud_name=CLOUDINARY_CLOUD)
plot_altair_chart(chart)