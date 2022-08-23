"""
Periodically check DCBOE's site and send an alert if it changes
"""

import os
import sys
import json
import pytz
import time
import tweepy
import argparse
import requests
import pandas as pd
from pathlib import Path
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

        # 2020 candidate list
        self.url = 'https://dcboe.org/Elections/2022-Elections'
        self.link_text_body = 'Candidates for Advisory Neighborhood Commissioner'

        # List of current commissioners
        # self.url = 'https://dcboe.org/Candidates/ANC-Commissioners'
        # self.link_text_body = 'Current List of Advisory Neighborhood Commissioners'

        # Link text body is the text that is inside the HTML link tag. For example: <a href="">link_text_body</a>

        # Load the Twitter API keys from environment variables
        self.consumer_key = os.environ['TWITTER_API_KEY']
        self.consumer_secret = os.environ['TWITTER_API_KEY_SECRET']
        self.access_token = os.environ['TWITTER_ACCESS_TOKEN']
        self.access_token_secret = os.environ['TWITTER_ACCESS_TOKEN_SECRET']

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
            if a.text == self.link_text_body:
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

        # Local timezone for this computer
        # tz = datetime.utcnow().astimezone().tzinfo

        # Current time in DC
        tz = pytz.timezone('America/New_York')

        current_timestamp = datetime.now(tz).strftime('%Y-%m-%d %H:%M:%S %Z')
        print(f'{current_timestamp} -> ', end='')
        
        r = requests.get(self.url, stream=True)

        # todo: handle situation where internet isn't working, right now it returns True

        page_has_changed = not self.current_link_text in r.text

        print(f'DCBOE page_has_changed: {page_has_changed}')
     
        return page_has_changed



    def is_internet_connected(self):
        """Return boolean with the current state of the internet connection, determined by getting Google.com"""
        
        try:
            response = requests.get('https://google.com')
        except requests.exceptions.ConnectionError:
            return False
        
        return response.status_code == 200



    def run(self):

        if not self.is_internet_connected():
            print('No internet connection, exiting.')
            return

        if self.args.reset:
            self.reset()

        if self.current_link_text == '':
            # Don't run the check if there is no text to check for
            return

        page_has_changed = self.poll_dcboe()

        if page_has_changed:
            os.system('terminal-notifier -title "OpenANC" -message "DCBOE link has changed" -sound Blow -open "https://dcboe.org/Elections/2022-Elections"')

            # Save the new filename to the current_link text file
            self.reset()

            # self.send_tweet('ANC candidate list has changed: https://dcboe.org' + self.current_link_text)
            # self.send_tweet(f'ANC candidate list has changed: https://dcboe.org{self.current_link_text} (filename: {Path(self.current_link_text).name})')



    def send_tweet(self, message):
        """Send one tweet using the tweepy package"""
        
        client = tweepy.Client(
            consumer_key=self.consumer_key
            , consumer_secret=self.consumer_secret
            , access_token=self.access_token
            , access_token_secret=self.access_token_secret
            )

        response = client.create_tweet(text=message)

        print(response)



if __name__ == "__main__":

    m = MonitorDCBOE()
    m.run()

    
    # m.send_tweet(f'Current ANC candidate list: https://dcboe.org{m.current_link_text}')
    # print(f'Current ANC candidate list: https://dcboe.org{m.current_link_text} (filename: {Path(m.current_link_text).name})')
    