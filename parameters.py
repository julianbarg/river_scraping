from sys import platform

if platform.startswith("win"):
    webdriver_location = 'geckodriver.exe'

if platform == 'linux':
    webdriver_location = './geckodriver'

wait_time = 15

pages = [{"name": "Callan River Wildlife Group", "type": "group", "id": "368961080430162"},
         {"name": "Friends of the Callan River", "type": "group", "id": "1896044603829394"},
         {"name": "Keepers of the Callan", "type": "page", "id": "keepersofthecallan"},
         {"name": "Friends of the folly river", "type": "page", "id": "Friends-of-the-folly-river-103170824371269"}]
