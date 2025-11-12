import altair as alt
from pandas import DataFrame

from family_tree.cloudinary_lite import greyscale_zero_images, get_image_url

BLUE_UNDER = '#0D5176'
BLUE_OVER = '#0D98BA'

def get_duration_time(seconds:int) -> str:
    string = []
    if seconds >= 60 * 60:
        string.append(f'{seconds/60//60}H')
    if seconds >= 60:
        string.append(f'{seconds//60 % 60}M')
    else:
        string.append(f'{seconds}S')
        
    return ' '.join(string)


def submission_chart(folder_values, quantity, cloud_name=None, cap=False):
    display_label = {'video_count': 'Videos',
                     'video_duration': 'Duration',
                     'file_size': 'MB'}[quantity]
    adjust_thresholds = {'video_count': 50, # cap at expected videos
                         'video_duration': 30*60, # cap at half an hour
                         'file_size': 1000, # cap at 1GB
                         }

    video_counts = folder_values.copy()
    threshold = video_counts[quantity].max()
    adjust_threshold = adjust_thresholds[quantity]
    if cap and adjust_threshold < threshold:
        # adjust threshold down
        threshold = adjust_threshold

    video_counts['display_name'] = video_counts['full_name'].where(
        video_counts['full_name'].notna(),
        video_counts['folder_name']
    )#.str.replace(' ', '\n')
    video_counts['image_url'] = video_counts.apply(lambda x: get_image_url(cloud_name, x['member_id']), axis=1)
    video_counts['image_url'] = video_counts.apply(lambda x: greyscale_zero_images(x['image_url'], x[quantity]), axis=1)

    order_list = (
        video_counts.sort_values(quantity, ascending=False)['display_name'].tolist()
    )

    video_counts[f'{quantity}_capped'] = video_counts[quantity].clip(upper=threshold)

    # small nudge for placing the image past the bar tip
    x_max =  min(video_counts[quantity].max(), threshold)
    pad = 0.1 * x_max
    # make sure the x-domain includes the image position

    x_domain_max = float(x_max + pad)

    # UI sizing
    bar_height = 30                        # pixels per row (bigger = easier to read)
    gap = 5.0                      # choose a value in video_count units


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
        x = alt.X(f'{quantity}_capped:Q', title='', scale=alt.Scale(domain=[0, threshold + gap], clamp=True)),
        color = alt.condition(f'datum.{quantity} >= {threshold}', alt.value(BLUE_OVER), alt.value(BLUE_UNDER)),
        tooltip = [alt.Tooltip('display_name:N', title='Name'),
                   alt.Tooltip(f'{quantity}:Q', title=display_label)]
        )

    # ---------- images at end of bars ----------
    images = base.transform_filter(
        alt.datum.image_url != None
    ).transform_calculate(
        value_pad = f"datum.{quantity} >= {threshold} ? {threshold} + {gap} : datum.{quantity} + {gap}"
    ).mark_image(width=bar_height, height=bar_height).encode(
        x = alt.X('value_pad:Q'),
        y = alt.Y('display_name:N', sort=order_list),
        url = 'image_url:N',
        tooltip = [alt.Tooltip('display_name:N', title='Name'),
                   alt.Tooltip(f'{quantity}:Q', title=display_label)]
    )

    chart = (bars + images).properties(
        height=max(300, bar_height * 1.2 * len(video_counts)))
    return chart



def review_pie(folder_values):
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
    
    return pie + text