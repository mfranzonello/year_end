import streamlit as st
import altair as alt

from database.db import get_engine
from database.db_project import fetch_year_summaries
#from family_tree.charts import 
from display import set_sidebar

PGHOST = st.secrets['postgresql']['host']
PGPORT = st.secrets['postgresql'].get('port', '5432')
PGDBNAME = st.secrets['postgresql']['database']
PGUSER = st.secrets['postgresql']['user']
PGPASSWORD = st.secrets['postgresql']['password']

engine = get_engine(PGHOST, PGPORT, PGDBNAME, PGUSER, PGPASSWORD)

# set up page
set_sidebar()
st.set_page_config(page_title='Franzonello Family YIR Growth',
                   layout='wide')
st.title(f'Franzonello YIR Growth')

year_values = fetch_year_summaries(engine)
year_values['total_duration'] = year_values['total_duration'] / 60  # convert to minutes'
year_values['total_file_size'] = year_values['total_file_size'] / 1024  # convert to GB'


for quantity in ['total_folders', 'total_videos', 'total_duration', 'total_file_size']:
    match quantity:
        case 'total_folders':
            y_label = 'Number of Video Sources'
        case 'total_videos':
            y_label = 'Number of Videos Submitted'
        case 'total_duration':
            y_label = 'Total Video Duration (minutes)'
        case 'total_file_size':
            y_label = 'Total File Size (GB)'

    chart = alt.Chart(year_values).mark_line(point=True).encode(
        x='project_year:O',
        y=alt.Y(f'{quantity}:Q', title=y_label),
        tooltip=['project_year:O', 'total_folders:Q', 'total_videos:Q', 'total_duration:Q', 'total_file_size:Q']
    ).interactive()

    st.altair_chart(chart, use_container_width=True)