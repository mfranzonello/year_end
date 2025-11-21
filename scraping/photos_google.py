from __future__ import annotations
from pathlib import Path

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.remote.webdriver import WebDriver

from common.system import get_videos_in_folder

G_SUMMARY_CLASS = 'Fbw5bb'
G_SUMMARY_ITEM = 'items'
G_GALLERY_CLASS = 'yKzHyd'
G_ITEM_CLASS = 'rtIMgb'
G_VIDEO_ARIA_LABEL = 'Video'
G_ANCHOR_CLASS = 'p137Zd'

G_FILENAME_CLASS = 'R9U8ab'
G_FILENAME_ARIA_LABEL = 'Filename'

# ---------- Helper for scrolling ----------

def check_404(driver, timeout=2) -> bool:
    ''' Checks if album page returns 404 error '''
    # The 404 page uses a stable container id
    elems = driver.find_elements(By.CSS_SELECTOR, "main#af-error-container")
    if elems:
        return True
    text_check = "The requested URL was not found on this server." in driver.page_source

    return text_check

def scroll_once(driver: WebDriver):
    ''' Scrolls to last visible tile to dynamically load more. '''    
    tiles = get_visible_item_tiles(driver)
    actions = ActionChains(driver)
    actions.scroll_to_element(tiles[-1]).perform()

# ---------- Helpers: navigating pages ----------

def get_gallery(driver: WebDriver, timeout: int = 15):
    ''' Wait for the outer album grid container to appear. '''
    WebDriverWait(driver, timeout).until(EC.presence_of_element_located((By.CSS_SELECTOR, f'div.{G_GALLERY_CLASS}')))
    return driver.find_element(By.CSS_SELECTOR, f'div.{G_GALLERY_CLASS}')

def get_visible_item_tiles(driver: WebDriver):
    ''' Return all currently loaded items '''
    return driver.find_elements(By.CSS_SELECTOR, f'div.{G_ITEM_CLASS}')

def get_all_item_tiles(driver: WebDriver):
    ''' Gets every item tile and scrolls to load more '''
    tile_values = []
    gallery = get_gallery(driver)

    if gallery:
        all_found = False
        while not all_found:
            tiles = get_visible_item_tiles(driver)

            new_values = [(href, label) for t in tiles if \
                            (alist := t.find_element(By.CLASS_NAME, G_ANCHOR_CLASS)) and \
                            (href := alist.get_attribute('href')) and \
                            (label := alist.get_attribute('aria-label').split()[0]) and \
                            ((href, label) not in tile_values)]
            if len(new_values):
                tile_values.extend(new_values)
                ## Scroll to bottom to load more
                scroll_once(driver)  

            else:
                all_found = True

    return tile_values

def get_share_video_urls(tile_values):
    ''' Get share urls of all video tiles '''
    shared_video_urls = [t for t in tile_values if t[1].lower() == G_VIDEO_ARIA_LABEL.lower()]
    return shared_video_urls

def open_first_tile(driver: WebDriver, timeout=10):
    tiles = get_visible_item_tiles(driver)
    tiles[0].click()
    ActionChains(driver).send_keys(Keys.ENTER).perform()

def open_info_panel(driver:WebDriver, time=10):
    ActionChains(driver).send_keys('i').perform()

def select_next_tile(driver: WebDriver, timeout=10):
    ActionChains(driver).send_keys(Keys.ARROW_RIGHT).perform()

def download_item(driver: WebDriver, timeout=10):
    ActionChains(driver).key_down(Keys.SHIFT).send_keys('d').key_up(Keys.SHIFT).perform() # send CTRL+'d' key

def inspect_and_download(driver:WebDriver, known_files:list=[], timeout=15, dry_run=False) -> str:
    css_match = f'div.{G_FILENAME_CLASS}[aria-label^="{G_FILENAME_ARIA_LABEL}"]' # load info panel
    WebDriverWait(driver, timeout).until(EC.presence_of_element_located((By.CSS_SELECTOR, css_match))) # wait for filename element
    element = driver.find_element(By.CSS_SELECTOR, css_match) # get filename element
    filename = element.get_attribute('aria-label').replace(f'{G_FILENAME_ARIA_LABEL}: ', '').strip() # extract filename

    downloadable = filename.lower() not in known_files
    if not downloadable:
        print(f'Already downloaded {filename}, skipping.')
    else:
        if not dry_run:
            # download by hitting 'Ctrl + D'
            print(f'Downloading {filename} ...')
            download_item(driver)
        else:
            print('Dry run only, no actual download.')

    return filename, downloadable

# ---------- Main block ----------

def harvest_g_shared_album(driver: WebDriver, download_directory: Path, shared_album_url: str, dry_run=False):
    # go to Google Photos shared album
    driver.get(shared_album_url)
    downloaded_files = []

    if check_404(driver):
        print('Page not found -- check that profile is signed in.')

    else:
        # get all image and video files
        tile_values = get_all_item_tiles(driver)
        

        # get the share urls for videos only
        shared_video_urls = get_share_video_urls(tile_values)

        n_videos = len(shared_video_urls)
        print(f'Total items found: {len(tile_values)}')
        print(f'Total videos found: {n_videos}')

        
        if shared_video_urls:
            known_files = [f.name.lower() for f in get_videos_in_folder(download_directory)]
            driver.get(shared_album_url) # go back to top
            open_first_tile(driver)

            for _ in shared_video_urls:

                # hit 'I' to see info panel
                open_info_panel(driver)
                css_match = f'div.{G_FILENAME_CLASS}[aria-label^="{G_FILENAME_ARIA_LABEL}"]' # load info panel
                WebDriverWait(driver, timeout=10).until(EC.presence_of_element_located((By.CSS_SELECTOR, css_match))) # wait for filename element

                known_files = [f.name.lower() for f in get_videos_in_folder(download_directory)]
                downloaded_files = []

                filename, downloadable = inspect_and_download(driver, known_files, timeout=15, dry_run=False)
                if filename and downloadable:
                        downloaded_files.append(filename)

                select_next_tile(driver)

        return downloaded_files