from sys import platform

if platform.startswith("win"):
    chrome_location = 'chromedriver.exe'
    firefox_location = 'geckodriver.exe'

elif platform == 'linux':
    chrome_location = './chromedriver'
    firefox_location = './geckodriver'

wait_time = 15

pages = [{"name": "Keepers of the Callan", "type": "page", "id": "keepersofthecallan"},
         {"name": "Friends of the folly river", "type": "page", "id": "Friends-of-the-folly-river-103170824371269"},
         {"name": "Callan River Wildlife Group", "type": "group", "id": "368961080430162"},
         {"name": "Friends of the Callan River", "type": "group", "id": "1896044603829394"}]

destination = "results"