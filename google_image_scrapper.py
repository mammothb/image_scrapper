# https://www.youtube.com/watch?v=7hpQQ36kKtI

import argparse
import multiprocessing
import operator
import os
import time

from itertools import accumulate
from pathlib import Path
from urllib.parse import unquote

import bs4
import numpy as np
import requests

from PIL import Image, UnidentifiedImageError
from selenium import webdriver
from selenium.webdriver.firefox.options import Options


LOAD_MORE_BUTTON_XPATH = (
    "//input[@class='mye4qd'][@type='button'][@value='Show more results']"
)
SCROLL_PAUSE_TIME = 1
# After expanding each thumbnail, <a> tags containing the image reference information
# will appear. These <a> tags will contain href with the string
# href="/imgres?imgurl=<url to full size image>&imgrefurl=<url to webpage containing the image>..."
ORIGINAL_IMG_URL = "a[href^='/imgres?']"
IMG_URL_START = "?imgurl="
IMG_URL_START_LEN = len(IMG_URL_START)
IMG_URL_STOP = "&imgrefurl="
# Hard coding the div class for thumbnail for the webdriver to click
THUMBNAIL_DIV = "div[class='isv-r PNCib MSM1fd BUooTd']"


def download_image(hrefs, index, output_dir, search_phrase):
    for i, href in enumerate(hrefs):
        img_url = unquote(
            href[
                href.index(IMG_URL_START) + IMG_URL_START_LEN : href.index(IMG_URL_STOP)
            ]
        )
        file_path = output_dir / f"{search_phrase}_{index + i}"
        if (index + i) % 20 == 0:
            print(index + i)
        try:
            with open(
                file_path.with_suffix(".png" if ".png" in img_url else ".jpg"), "wb"
            ) as outfile:
                img_data = requests.get(img_url, timeout=30).content
                outfile.write(img_data)
        except requests.exceptions.RequestException:
            print(img_url)


def remove_corrupted_images(output_dir):
    for ext in ("png", "jpg"):
        for file_path in output_dir.glob(f"*.{ext}"):
            try:
                Image.open(file_path)
            except UnidentifiedImageError:
                os.remove(file_path)


def google_search(args):
    print("Searching on Google Images....")

    search_phrase = args.phrase
    url = f"https://www.google.com.sg/search?q={search_phrase.replace(' ', '%20')}&tbm=isch"

    options = Options()
    options.headless = True
    driver = webdriver.Firefox(options=options)
    driver.get(url)
    last_height = driver.execute_script("return document.body.scrollHeight")

    search_phrase = search_phrase.replace(" ", "_")
    output_dir = Path(__file__).resolve().parent / "output" / search_phrase
    output_dir.mkdir(parents=True, exist_ok=True)

    while True:
        for _ in range(6):
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")

            # Wait to load page
            time.sleep(SCROLL_PAUSE_TIME)
            # Calculate new scroll height and compare with last scroll height
            new_height = driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                break
            last_height = new_height

        loadMoreButton = driver.find_element_by_xpath(LOAD_MORE_BUTTON_XPATH)
        if loadMoreButton.is_displayed():
            loadMoreButton.click()
        else:
            break
        # loadMoreButton = driver.find_element_by_xpath(LOAD_MORE_BUTTON_XPATH)
        # if driver.findElements( By.XPATH("//input[@class='mye4qd'][@type='button'][@value='Show more results']") ).size() != 0:
        #     loadMoreButton.click()
        break

    thumbnail_elements = driver.find_elements_by_css_selector(THUMBNAIL_DIV)
    for i, element in enumerate(thumbnail_elements):
        if i % 50 == 0:
            print(f"Expanding ... {i}")
        element.click()

    webpage = driver.page_source
    soup2 = bs4.BeautifulSoup(webpage, "html.parser")
    hyperlink_elements = soup2.select(ORIGINAL_IMG_URL)

    # Ragged splitting for multiprocessing
    hrefs_list = np.array_split([elem["href"] for elem in hyperlink_elements], args.j)
    index_list = [0] + list(accumulate(map(len, hrefs_list), operator.add))[:-1]

    jobs = [
        multiprocessing.Process(
            target=download_image, args=(hrefs, index, output_dir, search_phrase)
        )
        for hrefs, index in zip(hrefs_list, index_list)
    ]
    for job in jobs:
        job.start()
    for job in jobs:
        job.join()

    driver.quit()

    remove_corrupted_images(output_dir)

    return len(hyperlink_elements)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Crawl Google Image Search with the specified phrase"
    )
    parser.add_argument("--phrase", help="The phrase to search for", required=True)
    parser.add_argument("--j", help="The phrase to search for", type=int, default=1)
    args = parser.parse_args()
    start_time = time.time()
    num_images = google_search(args)
    print(
        f"A total of {num_images} {args.phrase} photos were downloaded from Google Images."
    )
    print(time.time() - start_time)
