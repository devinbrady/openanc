"""
Periodically check DCBOE's site and send an alert if it changes
"""

import os
import pytz
import time
import requests
import pandas as pd
from datetime import datetime


def poll_dcboe():

    url = 'https://www.dcboe.org/Candidates/2020-Candidates'
    current_link_text = '<p><a href="/dcboe/media/PDFFiles/Copy-of-List-of-Advisory-Neighborhood-Commissioners_2020-(00000003).pdf">ANC Candidate List for the November 3 General Election</a></p>'

    tz = pytz.timezone('America/New_York')
    current_timestamp = datetime.now(tz).strftime('%Y-%m-%d %H:%M:%S')
    print(f'{current_timestamp} requesting: {url} > ', end='')
    
    r = requests.get(url, stream=True)

    website_text = r.text

    page_has_changed = not current_link_text in website_text

    print(f'page_has_changed: {page_has_changed}')
    return page_has_changed


if __name__ == "__main__":

    page_has_changed = poll_dcboe()

    while not page_has_changed:
        time.sleep(300)

        page_has_changed = poll_dcboe()

    if page_has_changed:
        os.system('terminal-notifier -title "OpenANC" -message "DCBOE link has changed" -sound Blow')
