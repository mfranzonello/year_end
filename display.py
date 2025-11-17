import streamlit as st
import altair as alt

from family_tree.db import get_engine, fetch_years, fetch_folder_summaries
from family_tree.charts import submission_chart, review_pie

PGHOST = st.secrets['postgresql']['host']
PGPORT = st.secrets['postgresql'].get('port', '5432')
PGDBNAME = st.secrets['postgresql']['database']
PGUSER = st.secrets['postgresql']['user']
PGPASSWORD = st.secrets['postgresql']['password']

CLOUDINARY_CLOUD = st.secrets['cloudinary']['cloud_name']

engine = get_engine(PGHOST, PGPORT, PGDBNAME, PGUSER, PGPASSWORD)

years = fetch_years(engine) ##.sort_values('project_year')
year = st.selectbox('Year to Review', years, len(years) - 1)

folder_values = fetch_folder_summaries(engine, year)

st.title(f'Franzonello YIR {year}')

# bar chart for submissions
options =['video_count', 'video_duration', 'file_size']
display = ['count', 'duration', 'filesize']
quantity = st.radio(label='Display Quantity', options=options, format_func=lambda x: display[options.index(x)], horizontal=True)
chart = submission_chart(folder_values, quantity, cloud_name=CLOUDINARY_CLOUD, cap=True)
st.altair_chart(chart, use_container_width=True) # width='stretch')

# pie chart for review amount
chart = review_pie(folder_values)
st.altair_chart(chart)

# # # family tree
# # chart = family_tree()
# # st.graphviz_chart(chart)