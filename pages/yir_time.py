from uuid import UUID
from datetime import date, timedelta

from altair.utils.core import R
import streamlit as st

from database.db import get_engine
from database.db_display import fetch_actor_spans
from database.db_adobe import fetch_timeline_reviews, fetch_markers
from charting.charts_yir import timeline_chart
from pages.general import set_sidebar, get_hash_funcs, plot_altair_chart

PGHOST = st.secrets['postgresql']['host']
PGPORT = st.secrets['postgresql'].get('port', '5432')
PGDBNAME = st.secrets['postgresql']['database']
PGUSER = st.secrets['postgresql']['user']
PGPASSWORD = st.secrets['postgresql']['password']

CLOUDINARY_CLOUD = st.secrets['cloudinary']['cloud_name']

engine = get_engine(PGHOST, PGPORT, PGDBNAME, PGUSER, PGPASSWORD)

def get_review_name(reviews, review_id:UUID) -> str:
    review = reviews[reviews['review_id']==review_id]
    review_type = review['review_type'].iloc[0]
    match review_type:
        case 'year':
            add_on = f'{review["project_year"].iloc[0]} YIR'
        case 'decade':
            add_on = f'{review["project_year"].iloc[0]}s DIR'
        case 'history':
            add_on = ' Era'
        case _:
            add_on = ''

    video_theme = review['video_theme'].iloc[0]
    if video_theme:
        add_on += f' ({video_theme})'

    return f'Family {add_on}'

def get_cut_date(reviews, review_id:UUID) -> date:
    review = reviews[reviews['review_id']==review_id]
    review_type = review['review_type'].iloc[0]
    review_start_year = review['project_year'].iloc[0]
    match review_type:
        case 'year':
            cut_date = date(review_start_year + 1, 1, 1) - timedelta(days=1)
        case 'decade':
            cut_date = date(review_start_year + 10, 1, 1) - timedelta(days=1)
        case 'era' | _:
            cut_date = date.today()
            ##cut_date = date(review_start_year + 20, 1, 1) - timedelta(days=1) ### this needs an era end date

    return cut_date


# set up page
set_sidebar()
st.set_page_config(page_title='Family Review Appearances',
                   layout='wide')
reviews = fetch_timeline_reviews(engine).sort_values(by=['project_year', 'review_type'])
review_id:UUID = st.selectbox('Review to Review', reviews, len(reviews) - 1, width=400,
                              format_func=lambda x: get_review_name(reviews, x))
st.title(get_review_name(reviews, review_id))

cut_date = get_cut_date(reviews, review_id)

@st.cache_data(ttl='15min', hash_funcs=get_hash_funcs())
def get_timeline_data(engine, review_id, cut_date):
    actor_spans = fetch_actor_spans(engine, review_id, cut_date=cut_date)
    markers = fetch_markers(engine, review_id)
    return actor_spans, markers

actor_spans, markers = get_timeline_data(engine, review_id, cut_date)

# gantt chart of appearances
if len(actor_spans.dropna(subset=['start_time'])):
    with st.spinner('Building chart...', show_time=True):
        chart = timeline_chart(engine, actor_spans, markers, cloud_name=CLOUDINARY_CLOUD)
    plot_altair_chart(chart)
else:
    st.write("This review hasn't been reviewed yet.")