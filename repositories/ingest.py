from database.db_project import fetch_shared_albums
from scraping.photos import source_allowed, harvest_shared_album

def copy_from_web(engine, one_drive_folder, google=True, icloud=True, headless=False):
    albums = fetch_shared_albums(engine)
    for _, (_, url, folder_name, project_year, supfolder_name,
            scrape_name, browser_name, profile_name, notes) in albums.iterrows():
        
        if notes:
            print(f'Skipping album: {notes}')

        else:
            share_source = scrape_name.lower()
            browser_profile = f'{profile_name} {scrape_name}'
            download_directory = one_drive_folder / supfolder_name / str(project_year) / folder_name

            if source_allowed(share_source, google=google, icloud=icloud):
                harvest_shared_album(url, download_directory, scrape_name, browser_name, browser_profile,
                                     headless=headless)