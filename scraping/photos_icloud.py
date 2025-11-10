from __future__ import annotations
import re
import time
from pathlib import Path

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.remote.webdriver import WebDriver

from system import get_videos_in_folder

I_404 = 'landing-page'
I_FRAME_CLASS = 'early-child'

I_GALLERY_CLASS = 'grid-items'
I_SIDEBAR_CLASS = 'SidebarItem'
I_ITEM_CLASS = 'grid-item'
I_INFO_PANEL_CLASS = 'InfoPanel'
I_VIDEO_PLAYER = 'VideoPlayer'
I_FILENAME_CLASS = 'InfoPanel-filename' # div: class=Typography -> text
I_EMPTY_CLASS = 'EmptyPage-title'
I_TITLE_CLASS = 'Typography-gridheaderTitle'
I_SUBTITLE_CLASS = 'ToolbarTitle-subtitleText'

I_DOWNLOAD_CLASS = 'DownloadButton'
I_DOWNLOAD_ARIA = 'Download'

# ---------- Helpers: navigating pages ----------

def check_404(driver, timeout=2) -> bool:
    ''' Checks if album page returns 404 error '''
    # The 404 page uses a stable container id
    elems = driver.find_elements(By.CSS_SELECTOR, f'div.{I_404}')
    if elems:
        return True
    text_check = "The requested URL was not found on this server." in driver.page_source

    return text_check

def get_gallery(driver: WebDriver, shared_album_url, timeout: int = 15):
    '''Wait for the outer album grid container and sidebar album to load.'''
    find_url = shared_album_url.rstrip('/')
    WebDriverWait(driver, timeout).until(EC.frame_to_be_available_and_switch_to_it((By.ID, "early-child")))
    WebDriverWait(driver, timeout).until(EC.presence_of_element_located((By.CSS_SELECTOR, f'div.{I_GALLERY_CLASS}')))
    WebDriverWait(driver, timeout).until(EC.presence_of_element_located((By.CSS_SELECTOR, f'a.{I_SIDEBAR_CLASS}[href="{find_url}"]')))
    return driver.find_element(By.CSS_SELECTOR, f'a.{I_SIDEBAR_CLASS}[href="{find_url}"]')

def move_to_next_item(driver: WebDriver):
    '''Navigate through gallery'''
    ActionChains(driver).send_keys(Keys.ARROW_RIGHT).perform() # send '->' key

def get_info_panel(driver: WebDriver, timeout=3):
    '''Open the info panel to see file title'''
    info_panel = driver.find_elements(By.CSS_SELECTOR, f'div.{I_INFO_PANEL_CLASS}')
    if not info_panel:
        ActionChains(driver).send_keys('i').perform() # send 'i' key
        WebDriverWait(driver, timeout).until(EC.presence_of_element_located((By.CSS_SELECTOR, f'div.{I_INFO_PANEL_CLASS}')))

def get_grid_items(driver: WebDriver):
    grid_items = driver.find_elements(By.CSS_SELECTOR, f'div.{I_ITEM_CLASS}')
    if not grid_items:
        # check if intentionally blank page
        empty_page = driver.find_elements(By.CSS_SELECTOR, f'h2.{I_EMPTY_CLASS}')
        if empty_page:
            print('This album is blank, skipping.')
        else:
            print('Album not loading, check on profile.')
    else:
        return grid_items


def open_first_grid_item(driver: WebDriver, grid_items: list=[]):
    ''' Open the first item to start process. '''

    if grid_items:
        # click on first grid-item
        grid_items[0].click()
        # hit enter to open
        ActionChains(driver).send_keys(Keys.ENTER).perform() # send '->' key
        time.sleep(3) ## need better way to wait for loading

    else:
        print('No grid items.')

def get_position(driver: WebDriver):
    ''' Check to see where in the list the current item is. '''
    subtitle = driver.find_element(By.CSS_SELECTOR, f'h3.{I_SUBTITLE_CLASS}').text
    text = (subtitle or '').strip()
    if not text:
        n, N = 1, 1
    else:
        match = re.search(r"(\d+)\s*of\s*(\d+)", text, flags=re.I)
        if match:
            n, N = map(int, match.groups())
      
    return n, N

def download_item(driver: WebDriver, timeout=10):
    # Wait until the download button is present and clickable
    download_button = WebDriverWait(driver, timeout).until(
        EC.element_to_be_clickable(
            (By.CSS_SELECTOR, f'ui-button.{I_DOWNLOAD_CLASS}[aria-label="{I_DOWNLOAD_ARIA}"]')
        )
    )
    driver.execute_script("arguments[0].scrollIntoView(true);", download_button)
    download_button.click()

def check_if_video(driver: WebDriver):
    n, _ = get_position(driver)
    selector = f'div.ReactSwipeCarousel-item[data-index="{n-1}"] div.{I_VIDEO_PLAYER}'
    is_video = bool(driver.find_elements(By.CSS_SELECTOR, selector))
    return is_video

def inspect_and_download(driver: WebDriver, known_files: list, dry_run=False):
    # check if video and get filename extension
    filename = None
    downloadable = False

    if check_if_video(driver):
        filename = driver.find_element(By.CSS_SELECTOR, f'div.{I_FILENAME_CLASS}').text.lower() + '.mov'
        downloadable = filename not in known_files

        if not downloadable:
            print(f'Already downloaded {filename}, skipping.')
        else:
            if not dry_run:
                # download by clicking button
                print(f'Downloading {filename} ...')
                download_item(driver)
            else:
                print('Dry run only, no actual download.')

    return filename, downloadable


# ---------- Main block ----------

def harvest_i_shared_album(driver: WebDriver, download_directory: Path, shared_album_url: str, dry_run=False):
    # go to iCloud Photos shared URL
    print(f'Navigating to {shared_album_url} ...')
    driver.get(shared_album_url)

    if check_404(driver):
        print('Page not found -- check that profile is signed in.')

    else:
        # ensure gallery loads
        if not get_gallery(driver, shared_album_url):
            print('Album failed to load.')

        else:
            # open first item
            grid_items = get_grid_items(driver)
            if not grid_items:
                print('Items failed to load.')

            else:
                open_first_grid_item(driver, grid_items)

                # open info panel
                get_info_panel(driver)

                # look at each item
                known_files = [f.name.lower() for f in get_videos_in_folder(download_directory)]
                downloaded_files = []

                all_found = False
                while not all_found:
                    n, N = get_position(driver)

                    filename, downloadable = inspect_and_download(driver, known_files, dry_run=dry_run)

                    if filename and downloadable:
                        downloaded_files.append(filename)
                            
                    # check if there are more to look at
                    all_found = n == N
                    if not all_found:
                        move_to_next_item(driver)

                return downloaded_files