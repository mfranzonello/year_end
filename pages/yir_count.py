import streamlit as st
import altair as alt

from database.db import get_engine
from database.db_project import fetch_years, fetch_folder_summaries, fetch_usable_summary
from family_tree.charts import submission_chart, review_pie
from display import set_sidebar

PGHOST = st.secrets['postgresql']['host']
PGPORT = st.secrets['postgresql'].get('port', '5432')
PGDBNAME = st.secrets['postgresql']['database']
PGUSER = st.secrets['postgresql']['user']
PGPASSWORD = st.secrets['postgresql']['password']

CLOUDINARY_CLOUD = st.secrets['cloudinary']['cloud_name']

MIN_STARS = 3

engine = get_engine(PGHOST, PGPORT, PGDBNAME, PGUSER, PGPASSWORD)

# set up page
set_sidebar()
st.set_page_config(page_title='Franzonello Family YIR Stats',
                   layout='wide')
years = fetch_years(engine) ##.sort_values('project_year')
year:int = st.selectbox('Year to Review', years, len(years) - 1, width=100)
st.title(f'Franzonello YIR {year}')

folder_values = fetch_folder_summaries(engine, year)

# quantity selection
options =['video_count', 'video_duration', 'file_size']
display = ['count', 'duration', 'filesize']
quantity = st.radio(label='Display Quantity', options=options, format_func=lambda x: display[options.index(x)], horizontal=True)

# bar chart for submissions
match quantity:
    case 'video_count':
        total_videos = int(folder_values['video_count'].sum())
        submission_string = f'**{total_videos:,}** videos'
    case 'video_duration':
        total_duration = int(folder_values['video_duration'].sum())
        hours = total_duration // 3600
        minutes = (total_duration % 3600) // 60
        submission_string = f'**{hours:,}** hours and **{minutes:,}** minutes'
    case 'file_size':
        total_size = int(folder_values['file_size'].sum())
        gb_size = total_size / (1024 ** 3)
        submission_string = f'**{gb_size:,.2f}** GB'
st.write(f'{submission_string} submitted this year!')

chart = submission_chart(folder_values, quantity, cloud_name=CLOUDINARY_CLOUD, cap=True)
st.altair_chart(chart, use_container_width=True) # width='stretch')

# pie chart for review amount
review_stats = fetch_usable_summary(engine, year, MIN_STARS)
chart = review_pie(review_stats)
st.altair_chart(chart, use_container_width=True)

# # # family tree
# # chart = family_tree()
# # st.graphviz_chart(chart)