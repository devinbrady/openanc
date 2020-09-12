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
        self.url = 'https://www.dcboe.org/Candidates/2020-Candidates'

        with open(self.local_filename, 'r') as f:
            self.current_link_text = f.read()


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

        tz = pytz.timezone('America/New_York')
        current_timestamp = datetime.now(tz).strftime('%Y-%m-%d %H:%M:%S')
        print(f'{current_timestamp} -> ', end='')
        
        r = requests.get(self.url, stream=True)

        page_has_changed = not self.current_link_text in r.text

        print(f'page_has_changed: {page_has_changed}')
     
        return page_has_changed



    def run(self):

        if self.args.reset:
            self.reset()

        if self.current_link_text == '':
            # Don't run the check if there is no text to check for
            return

        page_has_changed = self.poll_dcboe()

        if page_has_changed:
            os.system('terminal-notifier -title "OpenANC" -message "DCBOE link has changed" -sound Blow')

            with open(self.local_filename, 'w') as f:
                f.write('')


if __name__ == "__main__":

    m = MonitorDCBOE()
    m.run()
