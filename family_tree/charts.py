from math import ceil

import altair as alt
from pandas import DataFrame, concat, json_normalize
from webcolors import name_to_hex

from family_tree.cloudinary_lite import grayscale_zero_images, get_image_url

def get_color_hexes(color_names:list[str]) -> list[str]:
    return [name_to_hex(c) for c in color_names]

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

def melt_years(year_values:DataFrame) -> DataFrame:
    return concat([year_values[['project_year', 'total_folders', 'total_videos',
                                'total_file_size', 'total_duration']],
                   json_normalize(year_values['video_resolutions']).rename(columns=lambda x: 'res_'+x),
                   json_normalize(year_values['video_status']).rename(columns=lambda x: 'q_'+x),
                   ], axis=1)

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
        color = alt
            .when(f'datum.{quantity} > 4 * {threshold}').then(alt.value(name_to_hex('indianred')))
            .when(f'datum.{quantity} > 2 * {threshold}').then(alt.value(name_to_hex('lightskyblue')))
            .when(f'datum.{quantity} > 1 * {threshold}').then(alt.value(name_to_hex('steelblue')))
            .otherwise(alt.value(name_to_hex('teal'))),
        #color = alt.condition(f'datum.{quantity} >= {threshold}', alt.value(BLUE_OVER), alt.value(BLUE_UNDER)),
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

def review_pie(year_values, year, min_stars):
    statuses = year_values.query('project_year == @year')['video_status']
    if not statuses.empty:
        s = statuses.iloc[0]
        no = s.get('0', 0)
        lo = sum(s.get(str(i), 0) for i in range(1, min_stars))
        hi = sum(s.get(str(i), 0) for i in range(min_stars, 5)) ## might want to make this a max
        go = s.get('used', 0)
    
    custom_colors = get_color_hexes(['gainsboro', 'gold', 'forestgreen', 'midnightblue'])

    review_df = DataFrame([['n/a', no],
                           ['low', lo],
                           ['high', hi],
                           ['used', go],
                           ],
                          columns = ['category', 'count'])

    base = alt.Chart(review_df).encode(
        theta=alt.Theta('count:Q').stack(True),
        radius=alt.Radius('count').scale(type='sqrt', zero=False, rangeMin=min(20, max(0, min(no, lo, hi, go)**0.5 - 1))),
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
    year_values = melt_years(year_values)

    charts = []
    for quantity in ['total_folders', 'total_videos', 'total_duration', 'total_file_size',
                     'video_resolution', 'video_status']:
        match quantity:
            case 'total_folders':
                y_label = 'Number of Video Sources'
            case 'total_videos':
                y_label = 'Number of Videos Submitted'
            case 'total_duration':
                year_values['total_duration'] = year_values['total_duration'] / 60  # convert to minutes'
                y_label = 'Total Video Duration (minutes)'
            case 'total_file_size':
                year_values['total_file_size'] = year_values['total_file_size'] / 1024  # convert to GB'
                y_label = 'Total File Size (GB)'
            case 'video_resolution':
                y_label = 'Video Resolution'
                colors = {'na': 'gainsboro',
                          'xx': 'firebrick',
                          'vhs': 'orchid',
                          'sd': 'lightsalmon',
                          'hd': 'gold',
                          'fhd': 'forestgreen',
                          '4k': 'midnightblue',
                          '8k': 'lightskyblue'}
                custom_colors = get_color_hexes(colors[k] for k in colors if f'res_{k}' in year_values.columns)
                sort_cols = [c for c in ['res_' + r for r in colors] if c in year_values.columns]
            case 'video_status':
                y_label = 'Video Rating'
                custom_colors = get_color_hexes(['gainsboro', 'firebrick', 'lightsalmon', 'gold', 'forestgreen', 'midnightblue', 'lightskyblue'])
                sort_cols = [c for c in ['q_' + r for r in [str(i) for i in range(5+1)] + ['used']] if c in year_values.columns]

        if quantity.startswith('total_'):
            chart = (alt.Chart(year_values)
                     .mark_line(point=True).encode(
                x=alt.X("project_year:O", title="Project Year"),
                y=alt.Y(f'{quantity}:Q', title=y_label),
                tooltip=['project_year:O', 'total_folders:Q', 'total_videos:Q', 'total_duration:Q', 'total_file_size:Q']
            )).interactive()
        elif quantity.startswith('video_'):
            year_melted = year_values.melt(
                id_vars=['project_year'],
                value_vars=sort_cols,
                var_name=quantity,
                value_name='count'
            )
            year_melted['sort_order'] = year_melted[quantity].map({k: v for v, k in enumerate(sort_cols)})

            chart = (
                alt.Chart(year_melted)
                .mark_bar()
                .encode(
                    x=alt.X("project_year:O", title="Project Year"),
                    y=alt.Y("count:Q", stack="normalize", title=y_label),
                    color=alt.Color(
                        f'{quantity}:N',
                        sort=sort_cols,
                        legend=None,
                        scale=alt.Scale(domain=sort_cols, range=custom_colors)
                    ),
                    order=alt.Order("sort_order:Q", sort="descending")
                )
            ).interactive()

        charts.append(chart)

    return charts

def timeline_chart(actor_spans):
    time_format = (
        "floor(datum.value/60) + ':' + "
        "(datum.value % 60 < 10 ? '0' : '') + "
        "floor(datum.value % 60)"
    )

    #actor_spans.sort_values(['start_time'], inplace=True)
    actor_spans['sort_order'] = actor_spans['start_time'].rank(na_option='bottom')
    print(actor_spans)

    chart = (
        alt.Chart(actor_spans)
        .mark_bar()
        .encode(
            y=alt.Y(
                "full_name:N",
                title=None, #"Actor",
                sort=alt.EncodingSortField(field="sort_order", order="ascending")
            ),
            x=alt.X(
                "start_time:Q",
                title="Time",
                axis=alt.Axis(labelExpr=time_format),
                scale=alt.Scale(domain=[0, ceil(actor_spans['end_time'].max()/10)*10]),
            ),
            x2="end_time:Q",
            tooltip=[
                'full_name:N',
                alt.Tooltip("start_time:Q", title="Start", format=".2f"),
                alt.Tooltip("end_time:Q", title="End", format=".2f")
            ],
        )
    )

    return chart
