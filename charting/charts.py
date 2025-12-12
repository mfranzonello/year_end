from math import ceil
from uuid import UUID

import altair as alt
from pandas import DataFrame, concat, json_normalize
from webcolors import name_to_hex

from family_tree.cloudinary_lite import get_image_url

def get_color_hexes(color_names:list[str]) -> list[str]:
    return [name_to_hex(c) for c in color_names]

def get_color_rgb_hex(color_name:str) -> str:
    return name_to_hex(color_name).replace('#', 'rgb:')


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

def get_average_rating(ratings:dict) -> float:
    if ratings is None:
        return 0
    else:
        return (sum(int(k) * v for k, v in zip(ratings.keys(), ratings.values()) if int(k)>0) 
                / sum(v for k, v in zip(ratings.keys(), ratings.values()) 
                      if int(k)>0) if [k for k in ratings.keys() if int(k) > 0] else 0)

def get_percent_hq(resolutions:dict, resolution_order:list, hq_min:str) -> float:
    if resolutions is None:
        return 0
    else:
        return (sum(v for k, v in zip(resolutions.keys(), resolutions.values())
                    if resolution_order.index(k) >= resolution_order.index(hq_min)) 
                / sum(resolutions.values()))


''' main status review charts '''
def submission_chart(folder_values:DataFrame, quantity:str, cloud_name:str,
                     cap:bool=False, order:list|None=None) -> alt.Chart:

    single_bars = ['video_count', 'video_duration', 'file_size']
    multi_bars = ['rating_count', 'resolution_count']

    if quantity in single_bars:
        bar_type = 'single'
    elif quantity in multi_bars:
        bar_type = 'multi'
    else:
        return alt.Chart()

    display_label = {'video_count': 'Videos',
                     'video_duration': 'Duration',
                     'file_size': 'MB',
                     'rating_count': 'Stars',
                     'resolution_count': 'Resolution'}[quantity]
    adjust_thresholds = {'video_count': 50, # cap at expected videos
                         'video_duration': 30*60, # cap at half an hour
                         'file_size': 1000, # cap at 1GB,
                         }

    video_counts = folder_values.copy()

    match bar_type:
        case 'single':
            sort_quantity = quantity

        case 'multi':
            match quantity:
                case 'rating_count':
                    new_quantity = 'stars'
                    video_counts[new_quantity] = video_counts.apply(lambda x: round(get_average_rating(x['rating_count']), 2), axis=1)
                
                case 'resolution_count':
                    new_quantity = 'hq_count'
                    video_counts[new_quantity] = video_counts.apply(lambda x: round(get_percent_hq(x['resolution_count'],
                                                                                               resolution_order=order, hq_min='4k') * 100, 1), axis=1)
            sort_quantity = new_quantity

    video_counts.loc[:, sort_quantity] = video_counts[sort_quantity].fillna(0)

    threshold = video_counts[sort_quantity].max()
    adjust_threshold = adjust_thresholds.get(quantity)
    if (cap and adjust_threshold) and (adjust_threshold < threshold):
        # adjust threshold down
        threshold = adjust_threshold

    video_counts['display_name'] = (video_counts['full_name']
                                    .fillna(video_counts['folder_name'])
                                    .fillna('_ROOT')
                                    )

    video_counts['image_url'] = video_counts.apply(lambda x: get_image_url(cloud_name, x['member_id'],
                                                                           grayscale=x[sort_quantity]==0
                                                                           ),
                                                   axis=1)

    order_list = (
        video_counts.sort_values(sort_quantity, ascending=False)['display_name'].tolist()
    )
    video_counts[f'{quantity}_capped'] = video_counts[sort_quantity].clip(upper=threshold)

    # UI sizing
    bar_height = 30 

    # bars
    match bar_type:
        case 'single':
            y_axis = alt.Axis(labelLimit=0, labelPadding=20) #labelFontSize=20
            base = alt.Chart(video_counts)
            bars = base.mark_bar(size=bar_height, clip=False).encode(
                y = alt.Y('display_name:N', title='', sort=order_list, axis=y_axis),
                x = alt.X(f'{quantity}_capped:Q', title='', scale=alt.Scale(domain=[0, threshold], clamp=True)),
                color = alt
                    .when(f'datum.{quantity} > 4 * {threshold}').then(alt.value(name_to_hex('indianred')))
                    .when(f'datum.{quantity} > 2 * {threshold}').then(alt.value(name_to_hex('lightskyblue')))
                    .when(f'datum.{quantity} > 1 * {threshold}').then(alt.value(name_to_hex('steelblue')))
                    .otherwise(alt.value(name_to_hex('teal'))),
                tooltip = [alt.Tooltip('display_name:N', title='Name'),
                           alt.Tooltip(f'{quantity}:Q', title=display_label)]
                )

        case 'multi':    
            keep_cols = ['member_id', 'image_url', 'display_name', quantity]
            video_counts_2 = (video_counts[keep_cols].join(json_normalize(video_counts[quantity]))
                            .melt(id_vars=keep_cols, var_name=new_quantity, value_name='count')
                            .dropna(subset=['count'])
            )

            match quantity:
                case 'rating_count':
                    sort_cols = [str(i) for i in range(5 + 1)]
                    custom_colors = get_color_hexes(['gainsboro', 'firebrick', 'gold', 'forestgreen', 'midnightblue', 'lightskyblue'])
                case 'resolution_count':
                    sort_cols = order
                    custom_colors = get_color_hexes(['gainsboro', 'orchid', 'firebrick', 'lightsalmon', 'gold', 'forestgreen', 'midnightblue', 'lightskyblue'])

            y_axis = alt.Axis(labelLimit=0, offset=bar_height * 1)
            base = alt.Chart(video_counts_2)
            bars = base.mark_bar(size=bar_height, clip=False).encode(
                y = alt.Y('display_name:N', title='', sort=order_list, axis=y_axis),
                x = alt.X(f'count:Q', title='', stack='normalize'),
                color=alt.Color(
                    f'{new_quantity}:N',
                    sort=sort_cols,
                    legend=None,
                    scale=alt.Scale(domain=sort_cols, range=custom_colors)
                ),
                tooltip = [alt.Tooltip('display_name:N', title='Name'),
                           alt.Tooltip(f'{new_quantity}:N', title=display_label),
                           alt.Tooltip('count:Q', title='Count')]
                )

    # images at end of bars
    match bar_type:
        case 'single':
            images = base.transform_filter(
                alt.datum.image_url != None
            ).transform_calculate(
                value_pad = f"datum.{sort_quantity} >= {threshold} ? {threshold} : datum.{sort_quantity}"
            ).mark_image(width=bar_height, height=bar_height).encode(
                x = alt.X('value_pad:Q'),
                y = alt.Y('display_name:N', sort=order_list),
                url = 'image_url:N',
                tooltip = [alt.Tooltip('display_name:N', title='Name'),
                           alt.Tooltip(f'{quantity}:Q', title=display_label)]
            )

        case 'multi':
            images = (
                base.transform_filter(alt.datum.image_url != None)
                .mark_image(width=bar_height, height=bar_height)
                .encode(
                    x=alt.value(0),
                    xOffset=alt.value(-bar_height * 0.75),
                    y = alt.Y('display_name:N', sort=order_list),
                    url = 'image_url:N',
                    tooltip = [alt.Tooltip('display_name:N', title='Name'),
                                alt.Tooltip(f'{quantity}:Q', title=display_label)]
                )
            )

    chart = (bars + images).properties(
        height= bar_height * 1.2 * len(video_counts)
    )

    return chart


''' pie chart for review status '''
def review_pie(year_values, year, min_stars) -> alt.Chart:
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
                                        range=custom_colors))
        )
    pie = base.mark_arc()
    
    chart = pie

    return chart


''' growth charts over years '''
def growth_charts(year_values, resolution_order:list) -> tuple[alt.Chart]:
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
                color_names = ['gainsboro', 'firebrick', 'orchid', 'lightsalmon', 'gold',
                               'forestgreen', 'midnightblue', 'lightskyblue']
                colors = {k: v for k, v in zip(resolution_order, color_names)}
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
                    # # tooltip=[alt.Tooltip('video_resolution:N', title='Resolution'),
                    # #          alt.Tooltip('count:Q', title='%')
                    # #          ]
                    order=alt.Order("sort_order:Q", sort="descending")
                )
            ).interactive()

        charts.append(chart)

    return charts


''' actor appearances '''
def timeline_chart(actor_spans:DataFrame, markers:DataFrame, cloud_name:str) -> alt.Chart:
    time_format = (
        "floor(datum.value/60) + ':' + "
        "(datum.value % 60 < 10 ? '0' : '') + "
        "floor(datum.value % 60)"
    )
    x_domain = [0, ceil(actor_spans['end_time'].max()/10)*10]

    bar_height = 50

    actor_spans['birth_date'] = actor_spans['birth_date'].astype('datetime64[ns]')
    actor_spans['sort_date'] = actor_spans.apply(lambda x: x['birth_date'] if (not x['in-law'] and not (x['member_type']=='animal')) else x['entry_date'],
                                                 axis=1)
    actor_spans['clan_name'] = actor_spans['clan_name'].mask(actor_spans['clan_id']==UUID(int=0), 'Friends')

    first_born = (actor_spans[(~actor_spans['in-law']) & (actor_spans['birth_date'].notna())]
                  .groupby('clan_id')['birth_date'].min()
                  .reset_index().rename(columns={'birth_date': 'clan_first_born'}))
    first_gen = (actor_spans
                 .groupby('clan_id')['generation'].min()
                 .reset_index().rename(columns={'generation': 'clan_generation'}))

    actor_spans['clan_first_born'] = actor_spans.merge(first_born, how='left', on='clan_id')['clan_first_born']
    actor_spans['clan_generation'] = actor_spans.merge(first_gen, how='left', on='clan_id')['clan_generation']

    clans = actor_spans[actor_spans['clan_id'].notna()].drop_duplicates('clan_id')[['clan_id', 'clan_name']]

    clans['full_name'] = clans['clan_name']
    clans['boundary'] = True
    clans['clan_first_born'] = clans.merge(first_born, how='left', on='clan_id')['clan_first_born'].tolist()
    clans['clan_generation'] = clans.merge(first_gen, how='left', on='clan_id')['clan_generation'].tolist()

    combined = concat([actor_spans, clans]).fillna({'boundary': False})
    combined['friends'] = combined['clan_id'] == UUID(int=0)
    combined['y_label'] = combined.apply(lambda x: ' ' if x['boundary'] else x['full_name'], axis=1)

    spans_sorted = concat([DataFrame({'full_name': '', 'clan_id': UUID(int=0xffffffffffffffffffffffffffffffff), 'y_label': ' ', 'boundary': True}, index=[0]),
                           combined.sort_values(by=['friends', 'clan_generation', 'clan_first_born', 'boundary', 'generation', 'sort_date'],
                                                na_position='last')
                           ]
    )
    spans_sorted['sort_order'] = range(len(spans_sorted))
    spans_sorted['y_position'] = spans_sorted.apply(lambda x: str(x['member_id']) if not x['boundary'] else ('+' + str(x['clan_id'])), axis=1)

    appearances = (spans_sorted[spans_sorted['member_id'].notna()].groupby('member_id')
                   .agg(min_start=('start_time', 'min'),
                        total_spans=('start_time', 'count'),
                        total_time=('span', 'sum')
                        ).reset_index()
                   .merge(spans_sorted.drop(columns=['start_time']).groupby('member_id').first().reset_index(), on='member_id')
                   )

    spans_sorted = spans_sorted.merge(appearances[['member_id', 'min_start', 'total_spans', 'total_time']], how='left', on='member_id')

    blue = get_color_rgb_hex('lightblue')
    red = get_color_rgb_hex('firebrick')
    actor_images = appearances[appearances['member_id'].notna()]
    actor_images['image_url'] = (actor_images
                                 .apply(lambda x: get_image_url(cloud_name, x['member_id'],
                                                                grayscale=not x['total_spans'],
                                                                border_color=blue if x['total_spans'] else red,
                                                                border_width=10,
                                                                ),
                                        axis=1)
    )

    chart = (
        alt.Chart(spans_sorted)
        .mark_bar()
        .encode(
            y=alt.Y(
                "y_position:N",
                title=None,
                sort=alt.EncodingSortField(
                    field="sort_order",
                    order="ascending"
                ),
                axis=None, #alt.Axis(labelExpr="datum.y_label")
            ),
            x=alt.X(
                "start_time:Q",
                title="Time",
                axis=alt.Axis(labelExpr=time_format),
                scale=alt.Scale(domain=x_domain),
            ),
            x2="end_time:Q",
            color=alt.Color("clan_id:N", legend=None),
            tooltip=[
                alt.Tooltip('full_name:N', title='Name'),
                alt.Tooltip('clan_name:N', title='Clan'),
                alt.Tooltip("start_time:Q", title="Start", format=".2f"),
                alt.Tooltip("end_time:Q", title="End", format=".2f"),
            ],
        )
    )

    x_pad = 5
    y_extend = -20

    rules_y1 = (
        alt.Chart(markers)
        .mark_rule() 
        .encode(
            x=alt.X(
                "start_time:Q",
                scale=alt.Scale(domain=x_domain),
            ),
            color=alt.value(name_to_hex('indianred')),
            tooltip=[
                alt.Tooltip("chapter_name:N", title="Chapter"),
                alt.Tooltip("start_time:Q", title="Start (s)", format=".2f"),
            ],
        )
    )

    rules_y2 = (
        alt.Chart(markers)
        .mark_rule() 
        .encode(
            x="start_time:Q",
            color=alt.value(name_to_hex('indianred')),
            tooltip=[
                alt.Tooltip("chapter_name:N", title="Chapter"),
                alt.Tooltip("start_time:Q", title="Start (s)", format=".2f"),
            ],
            y=alt.value(0),
            y2=alt.value(y_extend)
        )
    )

    # find boundaries where clan changes
    rules_x = (
        alt.Chart(spans_sorted[spans_sorted['boundary']])
        .mark_rule()
        .encode(
            y=alt.Y(
                "y_position:N",
                title=None, 
                sort=alt.EncodingSortField(field="sort_order", order="ascending"),
                axis=None,
                #axis=alt.Axis(labelExpr="datum.y_label"),
            ),
            x=alt.X(scale=alt.Scale(domain=x_domain)),
            tooltip = [alt.Tooltip('clan_name:N', title='Clan')],
        )
    )

    rules = rules_y1 + rules_y2 + rules_x

    labels_x = (
        alt.Chart(markers)
        .mark_text(dx=x_pad, dy=y_extend, baseline='top', align="left", fontSize=bar_height*.3) # angle=90, 
        .encode(
            y=alt.value(0),
            x=alt.X(
                "start_time:Q",
                scale=alt.Scale(domain=x_domain),
            ),
            text="chapter_name:N",
            tooltip=[alt.Tooltip('chapter_name:N', title='Chapter'),
                     alt.Tooltip('start_time:Q', title='Start Time'),
                     ]
        )
    )
    
    labels_y = (
        alt.Chart(appearances)
        .mark_text(
            align="right",
            baseline="middle",
            dx=-bar_height*1.2,  # nudge left a bit if you want it near the axis
            fontSize=bar_height*.3,
        )
        .encode(
            y=alt.Y(
                "y_position:N",
                sort=alt.EncodingSortField(field="sort_order", order="ascending"),
            ),
            x=alt.value(0),        # or the left edge in pixels
            text="y_label:N",
            tooltip=alt.value(None),
        )
    )
    
    labels = labels_x + labels_y

    images = (alt.Chart(actor_images)
        .transform_filter(alt.datum.image_url != None)
        .mark_image(width=bar_height*.9, height=bar_height*.9)
        .encode(
            x=alt.value(0),
            xOffset=alt.value(-bar_height * 0.6),
            y=alt.Y(
                "y_position:N",
                sort=alt.EncodingSortField(field="sort_order", order="ascending"),
            ),
            url = 'image_url:N',
            tooltip=[alt.Tooltip('full_name:N', title='Name'),
                     alt.Tooltip('min_start:Q', title='First Appearance'),
                     alt.Tooltip('total_spans:Q', title='Total Appearances'),
                     alt.Tooltip('total_time:Q', title='Total Screentime'),
                     ]
        )
    )

    return (chart + rules + labels + images).properties(height = bar_height * spans_sorted['full_name'].nunique())
