import time, os, re
from datetime import datetime
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.chrome.options import Options as ChromeOptions

from common.structure import CHROME_DATA, CHROME_STATE, EDGE_EXE, EDGE_DATA, EDGE_STATE
from common.system import close_exe
from scraping.photos_google import harvest_g_shared_album
from scraping.photos_icloud import harvest_i_shared_album

def get_browser_profiles(browser: str):
    BROWSER_STATE = {'chrome': CHROME_STATE, 'edge': EDGE_STATE}[browser]
    
    ''' Returns a dict of browser profile display name → directory name. '''
    browser_profiles = {BROWSER_STATE['profile']['info_cache'][k]['name']: k for k in BROWSER_STATE['profile']['info_cache']}
    return browser_profiles

def get_browser_profile(browser: str, name: str) -> str:
    ''' Returns the browser profile directory name for a given profile display name. '''
    browser_profiles = get_browser_profiles(browser)
    browser_profile = browser_profiles.get(name, 'Default')
    return browser_profile

# ---------- Selenium / browser setup ----------

def make_driver(headless: bool = True, download_directory: Path|None = None, browser_profile='',
                browser='edge') -> webdriver.Chrome|webdriver.Edge|None:
    browser = browser.lower()
    if browser not in ['chrome', 'edge']:
        return

    browser_profile = get_browser_profile(browser, browser_profile)

    match browser:
        case 'chrome':
            opts = ChromeOptions()
        case 'edge':
            opts = EdgeOptions()
 
    BROWSER_DATA = {'chrome': CHROME_DATA, 'edge': EDGE_DATA}[browser]
    opts.add_argument(f'--user-data-dir={BROWSER_DATA}')
    opts.add_argument(f'--profile-directory={browser_profile}')

    if headless:
        opts.add_argument('--headless=new')
        opts.add_argument('--log-level=3')  # = ERROR

    # Helpful stability flags
    opts.add_argument('--disable-gpu')
    opts.add_argument('--disable-dev-shm-usage')
    opts.add_argument('--no-sandbox')

    opts.add_experimental_option('detach', True)
    opts.add_argument('--window-size=1400,1000')
    opts.add_argument('--disable-extensions')
    opts.add_argument('--enable-unsafe-swiftshader')   # new explicit opt-in
    opts.add_argument('--mute-audio')

    prefs = {'profile.default_content_setting_values.autoplay': 2}
    if download_directory:
        prefs.update({'download.default_directory': str(download_directory),
                     'download.prompt_for_download': False,
                     'safebrowsing.enabled': True,
                     })

    opts.add_experimental_option('prefs', prefs)


    # Performance logs to read Network.* events (response URLs, mimeTypes)
    log_prefs = {'chrome': 'goog', 'edge': 'ms'}[browser]
    opts.set_capability(f'{log_prefs}:loggingPrefs', {'performance': 'ALL'})

    if browser == 'chrome':
        driver = webdriver.Chrome(options=opts)
        
    elif browser == 'edge':
        close_exe(EDGE_EXE) # ensure no stale Edge instances
        driver = webdriver.Edge(options=opts)

    # Enable CDP Network (lets us fetch response bodies if needed)
    driver.execute_cdp_cmd('Network.enable', {})
    driver.execute_cdp_cmd('Page.setDownloadBehavior',
                           {'behavior': 'allow',
                            'downloadPath': os.path.abspath(download_directory or os.getcwd())})
    return driver

# ---------- Helper for download control ----------

def wait_for_expected_downloads(download_directory: Path,
                                expected_filenames: list[str],
                                timeout: int = 300,
                                poll: float = 0.3) -> bool:
    """
    Wait until every expected filename exists in download_dir
    and its .crdownload temp file is gone.
    """
    end = time.time() + timeout
    expected = [Path(download_directory, name) for name in expected_filenames]

    while time.time() < end:
        all_done = True
        for target in expected:
            # exists and not a temp file still in progress
            suffix = target.suffix if target.suffix != '' else '.*' ## iCloud Photos doesn't say the extension before downloading
            temp = target.with_suffix(suffix + ".crdownload")
            if not target.exists() or temp.exists():
                all_done = False
                break

        if all_done:
            return True

        print('Waiting for downloads...')
        time.sleep(poll)

    return False

# ---------- Main block ----------

def source_allowed(source_name, google=False, icloud=False):
    match source_name.lower():
        case 'google':
            return google
        case 'icloud':
            return icloud
        case _:
            return

def harvest_shared_album(shared_album_url:str, download_directory:Path,
                         scrape_name: str, browser_name, browser_profile: str|None = None,
                         headless=True, dry_run=False):

    # create Edge driver
    driver = make_driver(headless=headless, browser=browser_name, browser_profile=browser_profile, download_directory=download_directory)

    downloaded_files = None

    shared_album_url = shared_album_url.strip().rstrip('/') # remove ending /

    match scrape_name.lower():
        case 'google':
            # get videos from Google Photos
            downloaded_files = harvest_g_shared_album(driver, download_directory, shared_album_url, dry_run=dry_run)
        case 'icloud':
            # get videos from iCloud Photos
            downloaded_files = harvest_i_shared_album(driver, download_directory, shared_album_url, dry_run=dry_run)
   
    if downloaded_files:
        # ... you triggered downloads ...
        if not wait_for_expected_downloads(download_directory, downloaded_files):
            print("[warn] downloads may still be in progress or timed out")
        # now safe to close

        n_downloads = len(downloaded_files)
        v_s = '' if n_downloads == 1 else 's'
        print(f'Downloaded {n_downloads} new file{v_s} to {download_directory}:')

    driver.quit()
