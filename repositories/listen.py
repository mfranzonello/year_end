from pytubefix import YouTube

from database.db_adobe import fetch_music
from adobe.audition import download_audio, get_lyrics, create_captions, extract_captions, write_srt

def get_captions(yt:YouTube, lyrics_url:str|None) -> str|None:
    if lyrics_url:
        lyrics = get_lyrics(yt, lyrics_url)
        captions = create_captions(lyrics, yt.length)
    else:
        captions = extract_captions(yt)

    return captions

def get_audio_tracks(engine, year, review_type, download_path, dry_run:bool=False):
    srt_file_path = download_path / f'YIR {year}'

    music_df = fetch_music(engine, year, review_type)

    for i, track in music_df.iterrows():
        lyrics_url = track['lyrics_url']
        video_url = track['track_url']
        yt = YouTube(video_url)

        if not track['artist']:
            music_df.at[i, 'artist'] = yt.author

        if not track['track_title']:
            music_df.at[i, 'track_title'] = yt.title

        if not track['track_duration']:
            music_df.at[i, 'track_duration'] = yt.length

        if not dry_run:
            download_audio(yt, download_path)

        captions = get_captions(yt, lyrics_url)
        if captions:
            print(captions)
            if not dry_run:
                write_srt(captions, srt_file_path)