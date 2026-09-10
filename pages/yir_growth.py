import streamlit as st

from database.db import get_engine
from database.db_display import fetch_resolution_order
from database.db_project import fetch_years_summary
from charting.charts_yir import growth_charts
from pages.streamlit_auth import get_database_credentials
from pages.general import set_sidebar, plot_altair_chart

engine = get_engine(*get_database_credentials())

# set up page
set_sidebar()
st.set_page_config(page_title='Family YIR Growth',
                   layout='wide')
st.title(f'Year In Review Growth')

@st.cache_data(ttl='15m')
def get_years_summary(_engine):
    return fetch_years_summary(_engine)

year_values = get_years_summary(engine)

resolution_order = fetch_resolution_order(engine)
charts = growth_charts(year_values, resolution_order)

for chart in charts:
    plot_altair_chart(chart)