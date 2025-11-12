import streamlit as st
import altair as alt
from pandas import DataFrame

from family_tree.db import get_engine, fetch_years, fetch_folders

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

# # cloud = {'name': st.secrets['CLOUDINARY_CLOUD'],
# #          'key': st.secrets['CLOUDINARY_API_KEY'],
# #          'secret': st.secrets['CLOUDINARY_API_SECRET']}
# # folder_values = fetch_folders(engine, 2025, cloud=cloud)

SUBMISSION_THRESHOLD = 50

years = fetch_years(engine)
YEAR = st.selectbox('Year to Review', years, len(years) - 1)

def greyscale_zero_images(image_url, value):
    if image_url and value == 0:
        return image_url.replace('/upload/', '/upload/e_grayscale/')
    else:
        return image_url

folder_values = fetch_folders(engine, YEAR)

st.title(f'Franzonello YIR {YEAR}')

# bar chart for submissions
video_counts = folder_values.copy()
video_counts['display_name'] = video_counts['full_name'].where(
    video_counts['full_name'].notna(),
    video_counts['folder_name']
)#.str.replace(' ', '\n')
video_counts['image_url'] = video_counts.apply(lambda x: greyscale_zero_images(x['image_url'], x['video_count']), axis=1)

order_list = (
    video_counts.sort_values('video_count', ascending=False)['display_name'].tolist()
)

video_counts['video_count_capped'] = video_counts['video_count'].clip(upper=SUBMISSION_THRESHOLD)

# small nudge for placing the image past the bar tip
x_max =  min(video_counts['video_count'].max(), SUBMISSION_THRESHOLD)
pad = 0.1 * x_max
# make sure the x-domain includes the image position

x_domain_max = float(x_max + pad)

# UI sizing
bar_height = 30                        # pixels per row (bigger = easier to read)
img_sz = max(20, bar_height - 6)       # image size tied to row spacing
gap = 5.0                      # choose a value in video_count units
x_domain_max = SUBMISSION_THRESHOLD + gap * 2  # leave room for the icon inside the plot

font_axis = 14
font_title = 22
base = alt.Chart(video_counts)

axis = alt.Axis(
    #labelExpr="replace(datum.label, /\\s{2,}|\\s/g, '\\n')",
    labelLimit=0,
    labelPadding=20,
    #labelFontSize=20
    )

# ---------- bars ----------


bars = base.mark_bar(color="steelblue", size=bar_height, clip=False).encode(
    y = alt.Y('display_name:N', title='', sort=order_list, axis=axis),
    x = alt.X('video_count_capped:Q', title='', scale=alt.Scale(domain=[0, SUBMISSION_THRESHOLD + gap], clamp=True)),
    tooltip = [alt.Tooltip('display_name:N', title='Name'),
              alt.Tooltip('video_count:Q', title='Videos')]
    )

# ---------- images at end of bars ----------
images = base.transform_filter(
    alt.datum.image_url != None
).transform_calculate(
    value_pad = f"datum.video_count >= {SUBMISSION_THRESHOLD} ? {SUBMISSION_THRESHOLD} + {gap} : datum.video_count + {gap}"
).mark_image(width=bar_height, height=bar_height).encode(
    x = alt.X('value_pad:Q'),
    y = alt.Y('display_name:N', sort=order_list),
    url = 'image_url:N',
    tooltip = [alt.Tooltip('display_name:N', title='Name'),
              alt.Tooltip('video_count:Q', title='Videos')]
)

chart = (bars + images).properties(
    height=max(300, bar_height * 1.2 * len(video_counts)))
st.altair_chart(chart, use_container_width=True)


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