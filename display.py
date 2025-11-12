import streamlit as st
import altair as alt

from family_tree.db import get_engine, fetch_years, fetch_folders
from family_tree.charts import submission_chart, review_pie

PGHOST = st.secrets['PGHOST']
PGPORT = st.secrets.get('PGPORT', '5432')
PGDBNAME = st.secrets['PGDATABASE']
PGUSER = st.secrets['PGUSER']
PGPASSWORD = st.secrets['PGPASSWORD']

CLOUDINARY_CLOUD = st.secrets['CLOUDINARY_CLOUD']

engine = get_engine(PGHOST, PGPORT, PGDBNAME, PGUSER, PGPASSWORD)

# # @st.cache_data(ttl=300)
# # def get_folder_values(engine):
# #     return fetch_folders(engine, 2025)
# # folder_values = get_folder_values(engine)

# # cloud = {'name': st.secrets['CLOUDINARY_CLOUD'],
# #          'key': st.secrets['CLOUDINARY_API_KEY'],
# #          'secret': st.secrets['CLOUDINARY_API_SECRET']}
# # folder_values = fetch_folders(engine, 2025, cloud=cloud)

years = fetch_years(engine) ##.sort_values('project_year')
year = st.selectbox('Year to Review', years, len(years) - 1)

folder_values = fetch_folders(engine, year)

st.title(f'Franzonello YIR {year}')

# bar chart for submissions
options =['video_count', 'video_duration', 'file_size']
display = ['count', 'duration', 'filesize']
quantity = st.radio(label='Display Quantity', options=options, format_func=lambda x: display[options.index(x)], horizontal=True)
chart = submission_chart(folder_values, quantity, cloud_name=CLOUDINARY_CLOUD, cap=True)
st.altair_chart(chart, use_container_width=True)

# pie chart for review amount
chart = review_pie(folder_values)
st.altair_chart(chart)