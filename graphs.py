import streamlit as st
import altair as alt
from pandas import DataFrame

from family_tree.statistics import get_engine, fetch_folders

PGHOST = st.secrets['PGHOST']
PGPORT = st.secrets.get('PGPORT', '5432')
PGDBNAME = st.secrets['PGDATABASE']
PGUSER = st.secrets['PGUSER']
PGPASSWORD = st.secrets['PGPASSWORD']

engine = get_engine(PGHOST, PGPORT, PGDBNAME, PGUSER, PGPASSWORD)

# # @st.cache_data(ttl=300)
# # def get_folder_values(engine):
# #     return fetch_folders(engine, 2025)
# # folder_values = get_folder_values(engine)

folder_values = fetch_folders(engine, 2025)
folder_values.loc[:, ['test']] = 1

st.title('Franzonello Family 2025 YIR WIP')

# bar chart for submissions
threshold = 50
max_to_show = threshold * 1.1
bars = alt.Chart(folder_values).mark_bar(color="steelblue").encode(
    y = alt.Y('full_name', title=''),
    x = alt.X('video_count', title=''), #, scale=alt.Scale(domain=[0, max_to_show], clamp=True)),
    tooltip = ['full_name:N', 'video_count:Q']
    )
highlight = bars.mark_bar(color="#e45755").encode(
    x2=alt.X2(datum=threshold)
    ).transform_filter(alt.datum.video_count > threshold)

rule = alt.Chart().mark_rule().encode(
    x=alt.X(datum=threshold)
)
images = bars.mark_image(width=24, height=24).encode(x='test', y='full_name', url='image_url')
pad = 0.05 * (folder_values['video_count'].max() if len(folder_values) else 1)
st.altair_chart(bars + highlight + rule + images, use_container_width=True)

# pie chart for review amount
review_stats = folder_values[['video_count', 'review_count', 'usable_count']].sum()
review_df = DataFrame([['unreviewed', review_stats['video_count'] - review_stats['review_count']],
                       ['low', review_stats['review_count'] - review_stats['usable_count']],
                       ['high', review_stats['usable_count']]],
                      columns = ['category', 'count'])

base = alt.Chart(review_df).encode(
    alt.Theta('count:Q').stack(True),
    alt.Color('category:N').legend(None)
    )
pie = base.mark_arc(outerRadius=120)
text = base.mark_text(radius=140, size=20).encode(text = 'category:N')
st.altair_chart(pie + text)