from pandas import json_normalize
import streamlit as st

from database.db import get_engine
from database.db_project import fetch_project_years, fetch_folder_summaries, fetch_years_summary
from database.db_display import fetch_resolution_order
from charting.charts import submission_chart, review_pie
from charting.general import set_sidebar, plot_altair_chart

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
years = fetch_project_years(engine) ##.sort_values('project_year')
year:int = st.selectbox('Year to Review', years, len(years) - 1, width=100)
st.title(f'Franzonello YIR {year}')

folder_values = fetch_folder_summaries(engine, year)

# quantity selection
options = {'video_count': 'count',
           'video_duration': 'duration',
           'file_size': 'filesize',
           'rating_count': 'rating',
           'resolution_count': 'resolution'}

quantity = st.radio(label='Display Quantity', options=options.keys(), format_func=lambda x: options[x],
                    horizontal=True)

# bar chart for submissions
cap = False
order = None
match quantity:
    case 'video_count':
        total_videos = int(folder_values['video_count'].sum())
        submission_string = f'**{total_videos:,} videos**'
        cap = True
    case 'video_duration':
        total_duration = folder_values['video_duration'].sum()
        hours = int(total_duration // 3600)
        minutes = int((total_duration % 3600) // 60)
        submission_string = f'**{hours:,} hours** and **{minutes:,} minutes**'
        cap = True
    case 'file_size':
        total_size = folder_values['file_size'].sum()
        gb_size = total_size / 1e3
        submission_string = f'**{gb_size:,.2f} GB**'
        cap = True
    case 'rating_count':
        normed = json_normalize(folder_values['rating_count']).sum().rename_axis('stars').reset_index(name='count')
        normed['stars'] = normed['stars'].astype(int)
        normed = normed[normed['stars']>0]
        average_rating = normed['stars'].mul(normed['count']).sum() / normed['count'].sum()
        submission_string = f'**{round(average_rating, 2)} average stars** per video'
    case 'resolution_count':
        normed = json_normalize(folder_values['resolution_count']).sum().rename_axis('res').reset_index(name='count')
        quality_pct = normed[normed['res'].isin(['4k', '8k'])]['count'].sum() / normed['count'].sum()
        submission_string = f'**{round(quality_pct*100, 1)}% HQ videos**'
        order = fetch_resolution_order(engine)
    case _:
        submission_string = None

if submission_string:
    st.write(f'{submission_string} submitted this year!')

chart = submission_chart(folder_values, quantity, cloud_name=CLOUDINARY_CLOUD,
                         cap=cap, order=order)
plot_altair_chart(chart)

# pie chart for review amount
year_values = fetch_years_summary(engine)
chart = review_pie(year_values, year, MIN_STARS)

plot_altair_chart(chart)

# # # family tree
# # chart = family_tree()
# # st.graphviz_chart(chart)