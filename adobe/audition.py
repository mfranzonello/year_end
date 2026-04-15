from pathlib import Path
import re

import requests
from bs4 import BeautifulSoup
from pytubefix import YouTube

def convert_time(t: float) -> str:
    h = t // (60*60)
    m = (t % (60*60)) // 60
    s = (t % 60) // 1
    ms = (t - t // 1) * 1000
    return f'{int(h):02}:{int(m):02}:{int(s):02},{int(ms):03}'

def create_captions(lyrics:str, total_time:float,
                    delimeter:str = '\n', replace=r'[\r\t]') -> str:
    time_per_lyric = total_time / lyrics.count(delimeter)

    captions = '\n'.join(
        (f'{i}\n{convert_time(i * time_per_lyric)} --> {convert_time((i+1) * time_per_lyric)}\n{lyric}\n')
        for i, lyric in enumerate(re.sub(replace, '', lyrics).split('\n')) if lyric
        )

    return captions

def write_srt(captions:str, file_path:Path, extension:str='.srt'):
    with open(file_path.with_suffix(extension), 'w', encoding='utf-8') as f:
        f.write(captions)

def download_audio(yt:YouTube, download_folder:Path):
    filename = f'{yt.title}.m4a'

    if filename.lower() not in [p.name.lower() for p in download_folder.iterdir() if p.is_file()]:
        print(f'Downloading {filename} to {download_folder}')
        ys = yt.streams.get_audio_only()
        ys.download(output_path=download_folder)
    else:
        print(f'{filename} already downloaded.')

def get_lyrics(yt:YouTube, lyrics_url:str) -> str:
    if 'en' in yt.captions:
        lyrics = yt.captions['en'].generate_srt_captions()

    else:
        html = requests.get(lyrics_url).text
        soup = BeautifulSoup(html, 'html.parser')

        header = soup.find('b')
        title = header.find_next('b')
        lyrics = title.find_next('div').text
    return lyrics

def extract_captions(yt:YouTube) -> str|None:
    if 'en' in yt.captions:
        return yt.captions['en'].generate_srt_captions()