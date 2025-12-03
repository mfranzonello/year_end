import altair as alt
from pandas import DataFrame

from family_tree.cloudinary_lite import grayscale_zero_images, get_image_url

BLUE_UNDER = '#0D5176'
BLUE_OVER = '#0D98BA'

NA_COLOR = '#D5C7C5'
LO_COLOR = '#FAC638'
MD_COLOR = '#7EA44B'
HI_COLOR = '#2F6B9A'

def convert_duration_time(seconds:int) -> str:
    string = []
    if seconds >= 60 * 60:
        string.append(f'{seconds/60//60}H')
    if seconds >= 60:
        string.append(f'{seconds//60 % 60}M')
    else:
        string.append(f'{seconds}S')
        
    return ' '.join(string)

def convert_file_size(mbytes:float) -> str:
    factors = {'TB': 1e3, 'GB': 1, 'MB': 1}
    label = 'MB'
    for label in factors:
        if mbytes >= factors[label]:
            break
    return f'{round(mbytes/factors[label], 1)} {label}'

def submission_chart(folder_values:DataFrame, quantity:str, cloud_name:str, cap:bool=False):
    display_label = {'video_count': 'Videos',
                     'video_duration': 'Duration',
                     'file_size': 'MB'}[quantity]
    adjust_thresholds = {'video_count': 50, # cap at expected videos
                         'video_duration': 30*60, # cap at half an hour
                         'file_size': 1000, # cap at 1GB
                         }

    video_counts = folder_values.copy()
    video_counts.loc[:, quantity] = video_counts[quantity].fillna(0)
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
    video_counts['image_url'] = video_counts.apply(lambda x: grayscale_zero_images(x['image_url'], x[quantity]), axis=1)

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
    bar_height = 30                   # pixels per row (bigger = easier to read)
    gap = 0# 5.0                      # choose a value in video_count units


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

def review_pie(review_stats):
    no, lo, hi, go = review_stats[['no_count', 'lo_count',
                                   'hi_count', 'go_count']].iloc[0]

    custom_colors = [NA_COLOR, LO_COLOR, MD_COLOR, HI_COLOR]

    review_df = DataFrame([['n/a', no],
                           ['low', lo],
                           ['high', hi],
                           ['used', go],
                           ],
                          columns = ['category', 'count'])

    base = alt.Chart(review_df).encode(
        theta=alt.Theta('count:Q').stack(True),
        radius=alt.Radius('count').scale(type='sqrt', zero=False, rangeMin=20),
        color=alt.Color('category:N',
                        scale=alt.Scale(domain=review_df['category'].tolist(),
                                        range=custom_colors))#.legend(None)
        )
    pie = base.mark_arc()
    ##text = base.mark_text(radius=140, size=20).encode(text = 'category:N')
    
    chart = pie

    return chart

# growth charts over years
def growth_charts(year_values):
    year_values['total_duration'] = year_values['total_duration'] / 60  # convert to minutes'
    year_values['total_file_size'] = year_values['total_file_size'] / 1024  # convert to GB'

    charts = []
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

        charts.append(chart)

    return charts

# resolution stacked bar chart
def resolution_chart(year_values):
    resolution_cols = [
        "resolution_na",
        "resolution_lo",
        "resolution_md",
        "resolution_hi",
    ]

    custom_colors = [NA_COLOR, LO_COLOR, MD_COLOR, HI_COLOR]

    year_melted = year_values.melt(
        id_vars=["project_year"],
        value_vars=resolution_cols,
        var_name="resolution",
        value_name="count"
    )
    year_melted['resolution_order'] = year_melted['resolution'].map({k: v for v, k in enumerate(resolution_cols)})

    chart = (
        alt.Chart(year_melted)
        .mark_bar()
        .encode(
            x=alt.X("project_year:O", title="Project Year"),
            y=alt.Y("count:Q", stack="normalize", title="Number of Videos"),
            color=alt.Color(
                "resolution:N",
                sort=resolution_cols,
                title="Video Resolution",
                legend=None,
                scale=alt.Scale(domain=resolution_cols, range=custom_colors)
            ),
            order=alt.Order("resolution_order:Q", sort="descending")
        )
    )
    return chart