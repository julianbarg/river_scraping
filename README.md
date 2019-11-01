# river_scraping

## Requirements

### Facebook account
Provide the password and username in a file named "acct.py", in the form:
```
username = "example"
password = "example_pw"
```

### Webdriver
The parameters.py file assumes there is a webdriver for firefox (geckodriver) in the directory.
Either download the appropriate driver and move it into the directory, or change what parameters.py points to.
The parameters file looks like this:
```
from sys import platform

if platform.startswith("win"):
    webdriver_location = 'geckodriver.exe'

if platform == 'linux':
    webdriver_location = './geckodriver'
```