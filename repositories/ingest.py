from database.db_project import fetch_shared_albums
from scraping.photos import source_allowed, harvest_shared_album

def copy_from_web(engine, one_drive_folder, year, google=True, icloud=True, years=None, headless=False):
    albums = fetch_shared_albums(engine)
    for _, album in albums.iterrows():
        album_row = album[['share_url', 'folder_name', 'project_year', 'scrape_name', 'browser_name', 'profile_name', 'notes']].tolist()
        url, folder_name, project_year, scrape_name, browser_name, profile_name, notes = album_row

        if notes:
            print(f'Skipping album: {notes}')

        else:
            share_source = scrape_name.lower()
            browser_profile = f'{profile_name} {scrape_name}'
            download_directory = one_drive_folder / str(project_year) / folder_name

            if project_year == year and source_allowed(share_source, google=google, icloud=icloud):
                 harvest_shared_album(url, download_directory, scrape_name, browser_name, browser_profile,
                                     headless=headless)
