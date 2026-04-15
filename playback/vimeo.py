import re

from pandas import DataFrame
from vimeo import VimeoClient

from common.secret import secrets
from adobe.bridge import get_resolution

VIMEO_ACCESS_TOKEN = secrets['vimeo']['access_token']

vimeo_client = VimeoClient(token=VIMEO_ACCESS_TOKEN)

def get_user_videos():
    """Fetch the list of videos for the authenticated user."""
    last = False
    p = 1
    results = []

    while not last:
        response = vimeo_client.get('/me/videos', params = {'page': p})
        results.extend(response.json()['data'])
        p += 1
        last = response.json()['paging']['next'] is None

    return results

def get_video_stats(videos:list) -> DataFrame:
    review_folders = [f'{y.title()} Ends' for y in ['year', 'decade']]

    review_videos = [video for video in videos if video.get('parent_folder') and video['parent_folder']['name'] in review_folders]
    published_stats = DataFrame([(v['name'],
                                  v['stats']['plays'],
                                  v['duration'],
                                  v['parent_folder'],
                                  v['name'].lower().replace('ends', '').strip(), 
                                  int(re.search(r'\b(19|20)\d{2}\b', v['name']).group(0)),
                                  get_resolution(v['width'], v['height']),
                                  v['uri']
                                  ) for v in review_videos],
                                columns=['title', 'views', 'video_duration',
                                         'review_type', 'project_year',
                                         'video_resolution', 'cloud_uri'])

    return published_stats

videos = get_user_videos()
published_stats = get_video_stats(videos)


