#!/usr/bin/env python3

from selenium import webdriver
from time import sleep
from selenium.webdriver.common.keys import Keys
from selenium.webdriver import ActionChains
from selenium.common.exceptions import NoSuchElementException, TimeoutException, ElementClickInterceptedException, \
    ElementNotInteractableException, WebDriverException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from datetime import datetime

from functools import partial
import re

Wait = partial(WebDriverWait, timeout=15)


class TooManyAttemptsError(TimeoutException):
    pass


def random_sleep(sec: float):
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


class FaceBookDriver(webdriver.Chrome):
    def __init__(self, username: str, password: str, executable_path='./chromedriver', port=0, options=None,
                 service_args=None, desired_capabilities=None, service_log_path=None, chrome_options=None,
                 keep_alive=True, images_folder: str = "./images", thumbnails_folder: str = "./thumbnails",
                 max_comments=25, max_images=10, max_scroll_depth=None, max_attempts=10):
        """
        An instance of the firefox webdriver with some added methods for navigating facebook.
        :param username: Facebook username as a string.
        :param password: Facebook password as a string.
        :param images_folder: Folder for images downloaded from facebook to be saved to.
        :param max_comments: Maximum numbers of comments to be extracted per post.
        :param max_images: Maximum of numbers to be scraped per post.
        :param max_scroll_depth: How often should selenium scroll to the bottom of the page to load more posts?
        """
        super().__init__(executable_path, port, options, service_args, desired_capabilities, service_log_path,
                         chrome_options, keep_alive)
        self.__username = username
        self.__password = password
        self.images_folder = images_folder
        self.thumbnails_folder = thumbnails_folder
        self.max_comments = max_comments
        self.max_images = max_images
        self.max_scroll_depth = max_scroll_depth
        self.max_attempts = max_attempts
        self.attempts = 0
        self.screenshot_error = 0
        self.no_screenshot = 0
        self.preview_issue = 0
        self.image_issue = 0
        self.the_end = False

        self.xpaths = {"group": {"entries": "//div[starts-with(@id, 'mall_post_')]",
                                 "thumbnail": [".//img[starts-with(@class, '_1445')]",
                                               ".//img[@class = 'scaledImageFitWidth img']",
                                               ".//a/div/img"]},
                       "page": {"entries": "//div[@id = 'pagelet_timeline_main_column']//div[@class = '_4-u2 _4-u8']",
                                "thumbnail": [".//img[@class = 'scaledImageFitWidth img']",
                                              ".//a/div/img"]}
                       }
        # For tracking whether we ar currently scraping a page or a  group.
        self._type = None

        self.login_fb()

    def login_fb(self):
        """
        Logs into facebook for you.
        """
        self.get("http://www.facebook.com")

        random_sleep(5)

        if 'id="loginbutton"' in self.page_source:
            login_type = 0
        elif 'name="login"' in self.page_source:
            login_type = 1

        # This approach doesn't really use login_type if its not 0, but it seems to be the most comprehendible (and
        # expandable) way to program this anyways.
        name = self.find_element_by_id("email") if login_type == 0 else self.find_element_by_name("email")
        passw = self.find_element_by_id("pass") if login_type == 0 else self.find_element_by_name("pass")
        name.send_keys(self.__username)
        passw.send_keys(self.__password)

        login = self.find_element_by_id("loginbutton") if login_type == 0 else self.find_element_by_name("login")
        login.click()

        # Wait(self).until(EC.presence_of_element_located((By.ID, "newsFeedHeading")))

    def load_page(self, page: str):
        """
        Load a page.
        :param page: Link to the site.
        """
        if self.attempts > self.max_attempts:
            raise TooManyAttemptsError

        self.get(page)
        random_sleep(1)

        try:
            Wait(self).until(EC.presence_of_element_located((By.XPATH, self.xpaths[self._type]["entries"])))
            random_sleep(1)
        except TimeoutException:
            self.attempts += 1
            self.load_page(page=page)

    def scrape_page(self, page: str, _type: str, chunk_size: int = None):
        """
        Scrapea a specific facebook group or page that is linked. If no chunk size is specified, will call easy_scrape,
        with chunk size specified will call stable_scrape.
        :param page: Link to the facebook group or page to be scraped.
        :param _type: Whether the link to be scraped is a group or a page.
        :param chunk_size: How many posts to scrape at once.
        :return: Dictionary with the contents of the page.
        """
        self._type = _type
        if chunk_size:
            contents = self.stable_scrape(page=page, chunk_size=chunk_size)
        else:
            contents = self.easy_scrape(page=page)

        return contents

    def easy_scrape(self, page: str):
        """
        Load and scrape one specific facebook group or page. This scrape function is designed to be simple and quick,
        but it can run into trouble when the page or group to be scraped is relatively long, and many objects need to be
        loaded into memory.
        :param page: Link to the facebook group or page to be scraped.
        :return: Dictionary with the contents of the page.
        """
        contents = []

        self.load_page(page=page)
        self.scroll_to_bottom()

        entries = self.find_elements_by_xpath(self.xpaths[self._type]["entries"])

        for entry in entries:
            contents = contents + [self.scrape_entry(entry=entry)]

        return contents

    def stable_scrape(self, page: str, chunk_size: int):
        """
        Load and scrape one specific facebook group or page. This scrape method is designed to be more robust than the
        easy_scrape method above.
        :param page: Link to the facebook group or page to be scraped.
        :param chunk_size: How many entries are supposed to be scraped at once.
        :return: Dictionary with the contents of the page.
        """
        contents = []

        self.load_page(page=page)

        entries = self.find_elements_by_xpath(self.xpaths[self._type]["entries"])
        first_post = entries[0].find_element_by_xpath(".//*[starts-with(@class, '_5ptz')]").get_attribute('title')

        n = 0
        while True:
            self.load_entries(m=n + chunk_size)
            entries = self.find_elements_by_xpath(self.xpaths[self._type]["entries"])
            start_from = [first_post in entry.get_attribute("innerHTML") for entry in entries].index(True)
            scrape_from = start_from + n
            end_with = scrape_from + chunk_size
            end_with = end_with if end_with < len(entries) else len(entries)

            for entry in entries[scrape_from:end_with]:
                contents = contents + [self.scrape_entry(entry=entry)]

            if self.the_end:
                self.the_end = False
                break

            self.refresh()
            n += chunk_size
        return contents

    def load_entries(self, m: int):
        """
        Scrolls down the page until all entries in the current chunk are loaded (and then once more just to be sure).
        param from:
        :param m: Final entry to be loaded.
        """
        scrolled = 0
        while True:
            len_previous = len(self.page_source)

            self.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            random_sleep(3)

            end_page = len(self.page_source) == len_previous
            if end_page:
                self.the_end = True
                break

            entries = self.find_elements_by_xpath(self.xpaths[self._type]["entries"])
            end_chunk = len(entries) > m + 5
            if end_chunk:
                break

            scrolled += 1
            if self.max_scroll_depth and scrolled == self.max_scroll_depth:
                self.the_end = True
                break

    def scroll_to_bottom(self):
        """
        Scroll to bottom of current page.
        """
        scrolled = 0
        while True:
            len_previous = len(self.page_source)

            self.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            random_sleep(3)

            if len(self.page_source) == len_previous:
                break

            scrolled += 1
            if self.max_scroll_depth and scrolled == self.max_scroll_depth:
                break

    def scrape_entry(self, entry):
        """
        Extract the contents of one individual post on facebook.
        :param entry: Web element of the entry, obtained through the drivers find_element(s) method.
        :return: Entries of the post as a pandas dataframe row.
        """
        # ToDo: Handle text-only post.

        content = {}

        content['unavailable'] = bool("This content isn't available right now" in entry.text)

        content['author'] = entry.find_element_by_xpath(".//span[starts-with(@class, 'fwb')]/a").text
        timestamp = entry.find_element_by_xpath(".//*[starts-with(@class, '_5ptz')]").get_attribute('title')
        content['timestamp'] = datetime.strptime(timestamp, "%m/%d/%y, %H:%M %p")
        comments = self.scrape_comments(entry)
        if comments:
            for num, comment in enumerate(comments[: self.max_comments]):
                content['comment_' + str(num)] = comment
        content['text'] = self.scrape_text(entry)

        content['link'] = ""
        # In groups, fortunately, when a link is shared, it will say so in the post. For pages, we have to check
        # manually.
        if ("shared a link" in entry.text) or (self._type == "page"):
            content['link'] = self.scrape_link(entry=entry)

        # See if there is image in post.
        images = None
        try:
            images = entry.find_elements_by_xpath(".//*[@rel = 'theater']")
        # If there is no image, get thumbnail.
        except NoSuchElementException:
            pass

        # need to split up if images and if_displayed because python attempts .is_displayed even if images is not
        # true
        if images:
            if len(images) == 1 and images[0].is_displayed():
                try:
                    filename = f"{self.images_folder}/{content['author']}_{content['timestamp'].isoformat()}.png"
                    content["image_0"] = filename
                    images[0].screenshot(filename)
                except TimeoutException:
                    self.preview_issue += 1

            elif len(images) > 1 and images[0].is_displayed():
                images = self.scrape_images(entry)
                if images:
                    for num, image in enumerate(images[: self.max_images]):
                        content['image_' + str(num)] = image

        else:
            try:
                content['image_0'] = self.scrape_thumbnail(entry=entry, author=content['author'],
                                                           date=content['timestamp'].isoformat())
            except NoSuchElementException:
                pass

        return content

    def scrape_text(self, entry):
        """
        Scrape the text of a facebook post.
        :param entry: The post with the text to be scrape.
        :return: The text, as a string.
        """
        if "See More" in entry.text:
            try:
                entry.find_element_by_xpath(".//*[text()='See More']").click()
            except ElementClickInterceptedException:
                pass
        try:
            text = entry.find_element_by_xpath(".//*[@data-testid='post_message']").text
        except NoSuchElementException:
            text = ''
        return text

    def scrape_link(self, entry):
        """
        Scrape a link posted to the facebook feed.
        :param entry: Web element of the link post, obtained through the drivers find_element(s) method.
        :return: The link.
        """
        if self._type == "group":
            # Make link appear by moving mouse to it.
            self.execute_script("arguments[0].scrollIntoView();", entry)
            ActionChains(self).move_to_element(entry).perform()
            link = entry.find_element_by_xpath(".//div[@class='mtm']//a").get_attribute("href")

        elif self._type == "page":
            try:
                link = entry.find_element_by_xpath(".//a[@class = '_52c6']")
            except NoSuchElementException:
                return None
            if link.is_displayed():
                # Make link appear by moving mouse to it.
                self.execute_script("arguments[0].scrollIntoView();", link)
                ActionChains(self).move_to_element(link).perform()
                return entry.find_element_by_xpath(".//a[@class = '_52c6']").get_attribute('href')
            else:
                return None

        return link

    def scrape_images(self, entry):
        # ToDo: Scrape comments to photos.
        """
        Scroll through all the available images and download each image to the provided images_folder. Requires for
        the image to be maximized in the webdriver.
        :return: A list of the file paths.
        """

        try:
            n_images = int(entry.find_element_by_xpath(".//*[@class='_52db']").text.strip('+')) + 3
        except NoSuchElementException:
            n_images = len(entry.find_elements_by_xpath(".//*[@rel = 'theater']"))

        for image in entry.find_elements_by_xpath(".//*[@rel = 'theater']"):
            try:
                image.click()
                break
            except (ElementClickInterceptedException, ElementNotInteractableException) as e:
                pass
        else:
            return

        try:
            Wait(self).until(EC.presence_of_element_located((By.ID, "fbPhotoSnowliftTimestamp")))
        except TimeoutException:
            ActionChains(self).send_keys(Keys.ESCAPE).perform()
            self.image_issue += 1
            random_sleep(1)
            return None

        random_sleep(2)

        image_count = 1
        timestamp = self.find_element_by_xpath("//span[@id='fbPhotoSnowliftTimestamp']//abbr").get_attribute('title')
        post_date = datetime.strptime(timestamp, "%A, %B %d, %Y at %I:%M %p").date().isoformat()
        filenames = []

        for _ in range(n_images - 1):  # -1 because we need one click to go from first to second image.
            # In some cases, facebook allows users to click through galeries and access previous image posts. Prevent!
            timestamp = self.find_element_by_xpath(
                "//span[@id='fbPhotoSnowliftTimestamp']//abbr").get_attribute('title')
            image_time = datetime.strptime(timestamp, "%A, %B %d, %Y at %I:%M %p")
            image_date = image_time.date().isoformat()
            if image_date != post_date:
                break

            author = self.find_element_by_xpath("//div[@id='fbPhotoSnowliftAuthorName']/a[1]").get_attribute('title')
            # Author might be an organization, which will not be found by the above line, emptry string is returned.
            if not author:
                author = self.find_element_by_xpath("//div[@id='fbPhotoSnowliftAuthorName']/a[1]").text
            author = author.replace(" ", "_")

            filename = f"{self.images_folder}/{author}_{image_time.isoformat()}.png"

            image = self.find_element_by_class_name("spotlight")
            if image:
                try:
                    image.screenshot(filename)

                    filenames = filenames + [filename]

                    image_count += 1

                    random_sleep(1)
                    ActionChains(self).move_to_element(image).perform()
                    random_sleep(1)

                    if image_count > self.max_images:
                        break

                except WebDriverException:
                    self.screenshot_error += 1
            else:
                self.no_screenshot += 1

            # Load next if possible.
            try:
                next_button = self.find_element_by_xpath("//a[@title = 'Next']")
            except NoSuchElementException:
                break
            if next_button.is_displayed():
                ActionChains(self).move_to_element(next_button).perform()
                next_button.click()
                random_sleep(1)
            else:
                break

        ActionChains(self).send_keys(Keys.ESCAPE).perform()
        random_sleep(1)
        return filenames

    def scrape_thumbnail(self, entry, author, date):
        """
        Obtain the thumbnail of a video in a facebook post.
        :param entry: Web element of the entry, obtained through the drivers find_element(s) method.
        :param author: Author of the post, to be written to the filename.
        :param date: Date of the post, to be written to the filename.
        :return: File path of the video thumbnail.
        """
        author = author.replace(" ", "_")
        xpaths = self.xpaths[self._type]['thumbnail']
        filename = f"{self.thumbnails_folder}/{author}_{date}.png"
        for xpath in xpaths:
            try:
                entry.find_element_by_xpath(xpath).screenshot(filename)
                return filename
            except (NoSuchElementException, WebDriverException) as e:
                pass

        return

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
            comments = [comment.strip("\nHide or report this") for comment in comments]

        return comments

    def show_all_comments(self, entry):
        """
        Load all comments to a post.
        :param entry: The webelement of a facebook post with comments.
        """
        self.execute_script("arguments[0].scrollIntoView();", entry)
        ActionChains(self).move_to_element(entry).perform()
        sleep(0.5)

        while "more comments" in entry.text:
            self.execute_script("window.scrollTo(0, 0);")
            sleep(0.5)
            entry.find_element_by_xpath(".//*[contains(text(), 'more comments')]").click()
            random_sleep(3)

        for button in entry.find_elements_by_xpath(
                ".//*[@data-testid = 'UFI2CommentsPagerRenderer/pager_depth_1' and @role = 'button']"):
            self.execute_script("window.scrollTo(0, 0);")
            ActionChains(self).move_to_element(self.find_element_by_link_text("Facebook")).perform()
            random_sleep(0.1)
            button.click()


def main():
    import parameters
    from acct import username, password
    from selenium import webdriver

    # Importing pandas is kind of overkill, since we only really need it to parse the timestamp into the .csv output.
    # But we we will do it anyways, since elegance (and, by extension, hassle-free development) is more important to us
    # than performance.
    from pandas import DataFrame as df

    # Run headless and without notification
    _chrome_options = webdriver.ChromeOptions()
    _chrome_options.add_argument("--headless")
    prefs = {"profile.default_content_setting_values.notifications": 2}
    _chrome_options.add_experimental_option("prefs", prefs)

    driver = FaceBookDriver(executable_path=parameters.chrome_location, chrome_options=_chrome_options,
                            # max_scroll_depth=9,
                            username=username, password=password)

    results = []

    page = parameters.pages[3]

    if page['type'] == 'group':
        result = driver.scrape_page(f"https://www.facebook.com/groups/{page['id']}", _type="group", chunk_size=150)

    elif page['type'] == 'page':
        result = driver.scrape_page(f"https://www.facebook.com/{page['id']}/posts/", _type="page")

    for entry in result:
        entry.update({'page': page['name']})
    results = results + result

    results_df = df(results)
    results_df.to_csv(parameters.destination + "/" + page['name'].replace(" ", "_") + ".csv",
                      index=False, encoding='utf-16')
    results_df = results_df.applymap(lambda x: x.encode('unicode_escape').decode('utf-8') if isinstance(x, str) else x)
    results_df.to_excel(parameters.destination + "/" + page['name'].replace(" ", "_") + ".xlsx", index=False)

    print(f"""Scraping {page.name} complete.
    Screenshot errors: {self.screenshot_error}
    No screenshot:     {self.no_screenshot}
    Preview issues:    {self.preview_issue}
    Image issues:      {self.image_issue}""")

if __name__ == "__main__":
    pass
