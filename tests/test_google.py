"""
Test connection with Google
"""

import pytz
import config
import pandas as pd
from datetime import datetime

from scripts.refresh_data import RefreshData


def test_google_connection():
    """
    Write some data to the OpenANC Published sheet to confirm that Google connection works
    """

    df = pd.DataFrame({'a': [1,2], 'b': [3,4]})

    tz = pytz.timezone(config.site_timezone)
    dc_now = datetime.now(tz)
    dc_timestamp = dc_now.strftime('%Y-%m-%d %H:%M:%S') # Hour of day: %-I:%M %p

    df['updated_at'] = dc_timestamp

    rd = RefreshData()
    rd.upload_to_google_sheets(df, list(df.columns), 'openanc_published', 'ConnectionTest')

    print('Successfully wrote data to Google Sheets.')
