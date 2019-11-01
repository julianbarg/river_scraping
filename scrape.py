from selenium import webdriver
from time import sleep
from selenium.webdriver.common.keys import Keys
from selenium.webdriver import ActionChains
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from datetime import datetime

from functools import partial
import re

import pandas as pd

Wait = partial(WebDriverWait, timeout=15)


def random_sleep(sec: int):
    """
    Adds a random amount of time to the sleep to avoid detection.
    :param sec: (minimum) seconds to sleep.
    """
    from random import random
    sleep(sec + (random() * 0.1 * sec))


def access_group(driver: webdriver, name: str):
    """
    Access the group with the webdriver.
    :param driver: Selenium webdriver instance that is logged into facebook.
    :param name: Name of the group to access.
    """
    groups = driver.find_element_by_link_text("Groups")
    groups.click()

    Wait(driver).until(EC.presence_of_element_located((By.LINK_TEXT, name))).click()
    Wait(driver).until(EC.presence_of_element_located((By.ID, "newsFeedHeading")))


class FaceBookDriver(webdriver.Firefox):
    def __init__(self, username: str, password: str, firefox_profile=None, firefox_binary=None,
                 images_folder: str = "./images", thumbnails_folder: str = "./thumbnails", max_comments=25,
                 max_images=10, max_scroll_depth=None, timeout=30, capabilities=None, proxy=None,
                 executable_path='geckodriver', options=None, service_log_path='geckodriver.log', firefox_options=None,
                 service_args=None, desired_capabilities=None, log_path=None, keep_alive=True):
        """
        An instance of the firefox webdriver with some added methods for navigating facebook.
        :param username: Facebook username as a string.
        :param password: Facebook password as a string.
        :param images_folder: Folder for images downloaded from facebook to be saved to.
        :param max_comments: Maximum numbers of comments to be extracted per post.
        :param max_images: Maximum of numbers to be scraped per post.
        :param max_scroll_depth: How often should selenium scroll to the bottom of the page to load more posts?
        """
        super().__init__(firefox_profile, firefox_binary, timeout, capabilities, proxy, executable_path, options,
                         service_log_path, firefox_options, service_args, desired_capabilities, log_path, keep_alive)
        self.username = username
        self.password = password
        self.images_folder = images_folder
        self.thumbnails_folder = thumbnails_folder
        self.max_comments = max_comments
        self.max_images = max_images
        self.max_scroll_depth = max_scroll_depth

        self.login_fb()

    def login_fb(self):
        """
        Logs into facebook for you.
        """
        self.get("http://www.facebook.com")
        Wait(self).until(EC.element_to_be_clickable((By.ID, "loginbutton")))

        name = self.find_element_by_id("email")
        passw = self.find_element_by_id("pass")

        name.send_keys(self.username)
        passw.send_keys(self.password)

        login = self.find_element_by_id("loginbutton")
        login.click()

        # Wait(self).until(EC.presence_of_element_located((By.ID, "newsFeedHeading")))

    def scrape_page(self, page: str):
        """
        Load and scrape one specific page.
        :param page: Link to the facebook page to be scraped.
        :return: Pandas dataframe with the contents of the page.
        """
        columns = ['author', 'timestamp', 'link', 'content', 'video_thumbnail']
        columns = columns + ['comment_' + str(comment) for comment in range(self.max_comments)]
        columns = columns + ['image_' + str(image) for image in range(self.max_images)]
        contents = pd.DataFrame(columns=columns)

        self.get(page)
        Wait(self).until(EC.presence_of_element_located((By.ID, "newsFeedHeading")))
        self.scroll_to_bottom()

        entries = self.find_elements_by_xpath("//div[starts-with(@id, 'mall_post_')]")

        for entry in entries:
            content = self.scrape_entry(entry=entry)
            contents = contents.append(content, ignore_index=True)

        return contents

    def scroll_to_bottom(self):
        """
        Scroll to bottom of current page.
        """
        scrolled = 0
        while True:
            len_previous = len(self.page_source)

            self.execute_script("window.scrollTo(0, document.body.scrollHeight);")

            if len(self.page_source) == len_previous:
                break

            random_sleep(2)

            scrolled += 1
            if self.max_scroll_depth and scrolled == self.max_scroll_depth:
                break

    def scrape_entry(self, entry):
        """
        Extract the contents of one individual post on facebook.
        :param entry: Web element of the entry, obtained through the drivers find_element(s) method.
        :return: Entries of the post as a pandas dataframe row.
        """
        content = {}
        content['timestamp'] = entry.find_element_by_xpath(
            ".//*[starts-with(@class, '_5ptz')]").get_attribute('title')
        content['author'] = entry.text.split('\n')[0]

        # ToDo: Handle - shared a post - get image.
        if 'post_message' in entry.get_attribute('innerHTML'):
            content['text'] = entry.find_element_by_xpath(".//*[@data-testid = 'post_message']").text

        elif "shared a link" in entry.text:
            content['link'] = self.scrape_link(entry)

        else:
            entry.find_element_by_xpath(".//*[@rel = 'theater']").click()
            random_sleep(1)
            Wait(self).until(EC.presence_of_element_located((By.XPATH, "//span[@id='fbPhotoSnowliftTimestamp']")))
            image = self.find_element_by_class_name('spotlight')
            if image.is_displayed():
                images = self.scrape_images()
                for n in list(range(len(images)))[: self.max_images]:
                    content['image_' + str(n)] = images[n]

            elif not image.is_displayed():
                date = content['timestamp'].date().isoformat()
                content['video_thumbnail'] = self.scrape_video_thumbnail(entry=entry, author=content['author'],
                                                                         date=date)
        comments = self.scrape_comments(entry)
        if comments:
            for n in list(range(len(comments)))[: self.max_comments]:
                content['comment_' + str(n)] = comments[n]

        return content

    def scrape_link(self, entry):
        """
        Scrape a link posted to the facebook feed.
        :param entry: Web element of the link post, obtained through the drivers find_element(s) method.
        :return: The link.
        """
        # By moving the mouse to the entry, we cause facebook to display the original URL rather than a facebook link.
        self.execute_script("arguments[0].scrollIntoView();", entry)
        ActionChains(self).move_to_element(entry).perform()
        link = entry.find_element_by_xpath(".//div[@class='mtm']//a").get_attribute("href")

        return link

    def scrape_images(self):
        # ToDo: Scrape comments to photos.
        """
        Scroll through all the available images and download each image to the provided images_folder. Requires for
        the image to be maximized in the webdriver.
        :return: A list of the file paths.
        """
        image_count = 1
        timestamp = self.find_element_by_xpath("//span[@id='fbPhotoSnowliftTimestamp']//abbr").get_attribute('title')
        post_date = datetime.strptime(timestamp, "%A, %B %d, %Y at %I:%M %p").date().isoformat()
        filenames = []

        while True:
            # In some cases, facebook allows users to click through galeries and access previous image posts. Prevent!
            timestamp = self.find_element_by_xpath(
                "//span[@id='fbPhotoSnowliftTimestamp']//abbr").get_attribute('title')
            image_date = datetime.strptime(timestamp, "%A, %B %d, %Y at %I:%M %p").date().isoformat()
            if image_date != post_date:
                break

            author = self.find_element_by_xpath("//div[@id='fbPhotoSnowliftAuthorName']/a[1]").get_attribute('title')
            # Author might be an organization, which will not be found by the above line, emptry string is returned.
            if not author:
                author = self.find_element_by_xpath("//div[@id='fbPhotoSnowliftAuthorName']/a[1]").text
            author = author.replace(" ", "_")

            filename = f"{self.images_folder}/{author}_{image_count}_{image_date}.png"

            image = self.find_element_by_class_name("spotlight")
            with open(filename, 'wb') as output:
                output.write(image.screenshot_as_png)

            filenames = filenames + [filename]

            image_count += 1
            if image_count > self.max_images:
                break

            ActionChains(self).move_to_element(image).perform()
            random_sleep(1)
            # Load next if possible.
            try:
                next_button = self.find_element_by_xpath("//a[@title = 'Next']")
            except NoSuchElementException:
                break
            if next_button.is_displayed():
                ActionChains(self).move_to_element(next_button).perform()
                next_button.click()
                Wait(self).until(EC.presence_of_element_located((By.XPATH, "//span[@id='fbPhotoSnowliftTimestamp']")))
            else:
                break

        ActionChains(self).send_keys(Keys.ESCAPE).perform()
        random_sleep(1)
        return filenames

    def scrape_video_thumbnail(self, entry, author, date):
        """
        Obtain the thumbnail of a video in a facebook post.
        :param entry: Web element of the entry, obtained through the drivers find_element(s) method.
        :param author: Author of the post, to be written to the filename.
        :param date: Date of the post, to be written to the filename.
        :return: File path of the video thumbnail.
        """
        thumbnail = entry.find_element_by_xpath(".//img[@class='_3chq']").get_attribute("src")
        filename = f"{self.thumbnails_folder}/{author}_{date}.png"
        with open(filename, 'wb') as output:
            output.write(thumbnail.screenshot_as_png)

        return filename

    def scrape_comments(self, entry):
        """
        Load all comments and return a list of comment text.
        :param entry: The webelement of a facebook post with comments.
        :return: List of all comments.
        """
        comments = []
        if 'Reply' in entry.text:
            self.show_all_comments(entry=entry)

            # Finds both first level and second level comments
            comments = entry.find_elements_by_xpath(".//ul[@class='_7791']/li|.//ul[@class='_7791']/li/div/ul/li")
            comments = [comment.text for comment in comments]

            tail = r"\nLike\n · Reply ·.*"
            likes = r"\n\d$"
            comments = [re.sub(tail, "", comment, flags=re.DOTALL) for comment in comments]
            comments = [re.sub(likes, "", comment, flags=re.DOTALL) for comment in comments]
            comments = [comment.strip() for comment in comments]

        return comments

    def show_all_comments(self, entry):
        """
        Load all comments to a post.
        :param entry: The webelement of a facebook post with comments.
        """
        self.execute_script("arguments[0].scrollIntoView();", entry)
        ActionChains(self).move_to_element(entry).perform()

        while "more comments" in entry.text:
            entry.find_element_by_xpath(".//*[contains(text(), 'more comments')]").click()
            random_sleep(1)

        for button in entry.find_elements_by_xpath(
                ".//*[@data-testid = 'UFI2CommentsPagerRenderer/pager_depth_1' and @role = 'button']"):
            button.click()


def main():
    import parameters
    from acct import username, password

    global Wait
    Wait = partial(WebDriverWait, timeout=parameters.wait_time)

    webdriver_location = parameters.webdriver_location

    # Browser profile to prevent the "Allow notifications" popup.
    _browser_profile = webdriver.FirefoxProfile()
    _browser_profile.set_preference("dom.webnotifications.enabled", False)

    driver = FaceBookDriver(username=username, password=password, firefox_profile=_browser_profile,
                            executable_path=webdriver_location, max_scroll_depth=2, max_images=3)

    results = pd.DataFrame()
    pages = [{"name": "Callan River Wildlife Group", "type": "group", "id": "368961080430162"}]

    for page in pages:
        # for page in parameters.pages:
        if page['type'] == 'group':
            result = driver.scrape_page(f"https://www.facebook.com/groups/" + page['id'])

        elif page['type'] == 'page':
            result = driver.scrape_page(f"https://www.facebook.com/" + page['id'])

        results = results.append(result).reset_index(drop=True)


if __name__ == "__main__":
    pass
