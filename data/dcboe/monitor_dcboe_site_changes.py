"""
Periodically check DCBOE's site and send an alert if it changes
"""

import os
import sys
import pytz
import time
import argparse
import requests
import pandas as pd
from datetime import datetime
from bs4 import BeautifulSoup



class MonitorDCBOE():

    def __init__(self):

        parser = argparse.ArgumentParser()
        parser.add_argument(
            '-r'
            , '--reset'
            , action='store_true'
            , help='Store the current value from the DCBOE site'
            )

        self.args = parser.parse_args()

        self.local_filename = 'current_link.txt'
        self.log_file = 'monitor_dcboe_site_changes_log.txt'
        self.url = 'https://www.dcboe.org/Candidates/2020-Candidates'



    def reset(self):
        """
        Start from scratch. Save the current value from the DCBOE file to a local text file
        """

        r = requests.get(self.url, stream=True)
        soup = BeautifulSoup(r.text, 'html.parser')

        current_link = ''

        for a in soup.find_all('a'):
            if a.text == 'ANC Candidate List for the November 3 General Election':
                current_link = a['href']
                break

        if current_link == '':
            print('No link found on DCBOE site.')
            sys.exit('Quitting.')

        else:
            with open(self.local_filename, 'w') as f:
                f.write(current_link)

            print(f'Current link saved to: {self.local_filename}')



    def poll_dcboe(self):

        with open(self.local_filename, 'r') as f:
            current_link_text = f.read()

        tz = pytz.timezone('America/New_York')
        current_timestamp = datetime.now(tz).strftime('%Y-%m-%d %H:%M:%S')
        print(f'{current_timestamp} requesting: {self.url} > ', end='')
        
        r = requests.get(self.url, stream=True)

        page_has_changed = not current_link_text in r.text

        print(f'page_has_changed: {page_has_changed}')
     
        with open(self.log_file, 'a+') as f:
            print(f'{current_timestamp} page_has_changed: {page_has_changed}', file=f)

        return page_has_changed



    def run(self):

        if self.args.reset:
            self.reset()

        page_has_changed = self.poll_dcboe()

        if page_has_changed:
            os.system('terminal-notifier -title "OpenANC" -message "DCBOE link has changed" -sound Blow')



if __name__ == "__main__":

    m = MonitorDCBOE()
    m.run()
