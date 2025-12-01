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
total_videos = int(folder_values['video_count'].sum())
st.write(f'**{total_videos:,}** submitted this year!')

# bar chart for submissions
options =['video_count', 'video_duration', 'file_size']
display = ['count', 'duration', 'filesize']
quantity = st.radio(label='Display Quantity', options=options, format_func=lambda x: display[options.index(x)], horizontal=True)
chart = submission_chart(folder_values, quantity, cloud_name=CLOUDINARY_CLOUD, cap=True)
st.altair_chart(chart, use_container_width=True) # width='stretch')

# pie chart for review amount
review_stats = fetch_usable_summary(engine, year, MIN_STARS)
chart = review_pie(review_stats)
st.altair_chart(chart, use_container_width=True)

# # # family tree
# # chart = family_tree()
# # st.graphviz_chart(chart)