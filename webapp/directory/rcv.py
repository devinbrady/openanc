"""Reading DCBOE's ranked-choice (RCV) round-by-round results.

DCBOE's results site (electionresults.dcboe.org, the "RCV" tab) publishes RCV results in numbered
releases ("Preliminary RCV Results 5 - Published November 20, 2026"). For each release it lists
the contests it tabulated, each with a link to an RCVis visualization (rcvis.com/v/<slug>). DCBOE
uploads a new visualization for every release, so the slugs change from release to release and
have to be read from DCBOE each time rather than guessed.

Each public RCVis page embeds the RCTab summary JSON it draws from, in
<script id="rawDataId" type="application/json">. That is what we parse. The RCVis REST API can't
look a visualization up by slug (only by numeric id, which DCBOE doesn't publish), so this needs
no API key.

RCVis's API terms ask for no more than 5 GETs a second and 1,000 a week; we stay far below that
by pausing between pages and caching every page we read (a slug's data never changes once DCBOE
has published it), so each release costs one request per tabulated ANC contest, once.
"""
import datetime
import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

import requests
from django.conf import settings

DCBOE_BASE_URL = 'https://electionresults.dcboe.org'
USER_AGENT = 'Mozilla/5.0 (OpenANC data sync; https://openanc.org)'
RCVIS_REQUEST_DELAY_SECONDS = 1.5
REQUEST_TIMEOUT_SECONDS = 30
DEFAULT_CACHE_DIR = Path(settings.BASE_DIR).parent / 'data' / 'rcvis'

INACTIVE_BALLOTS = 'Inactive Ballots'
SUMMARY_RE = re.compile(r'<script id="rawDataId" type="application/json">(.*?)</script>', re.S)
RELEASE_DATE_RE = re.compile(r'Published (\w+ \d{1,2}, \d{4})')
RCVIS_SLUG_RE = re.compile(r'^https://(?:www\.)?rcvis\.com/v/([\w-]+)$')


class RcvError(Exception):
    pass


@dataclass
class Round:
    number: int
    tallies: dict = field(default_factory=dict)  # candidate name -> votes, inactive ballots excluded
    inactive: int = 0
    elected: list = field(default_factory=list)
    eliminated: list = field(default_factory=list)


def extract_summary(html):
    """The RCTab summary JSON embedded in an RCVis /v/<slug> page."""
    match = SUMMARY_RE.search(html)
    if not match:
        raise RcvError('No tabulation data on this RCVis page.')
    return json.loads(match.group(1))


def _whole(value, where):
    number = float(value)
    if number != int(number):
        raise RcvError(f'{where}: {value} votes is not a whole number.')
    return int(number)


def parse_rounds(summary):
    rounds = []
    for result in summary['results']:
        number = int(result['round'])
        rnd = Round(number=number)
        for name, votes in result['tally'].items():
            count = _whole(votes, f'Round {number}, {name}')
            if name == INACTIVE_BALLOTS:
                rnd.inactive = count
            else:
                rnd.tallies[name] = count
        for outcome in result.get('tallyResults', []):
            if 'elected' in outcome:
                rnd.elected.append(outcome['elected'])
            if 'eliminated' in outcome:
                rnd.eliminated.append(outcome['eliminated'])
        rounds.append(rnd)
    return rounds


def office_designator(office_name):
    """'ANC-1B03' -> '1B03'; None for non-ANC offices."""
    match = re.match(r'^ANC-(\w+)$', office_name.strip())
    return match.group(1).upper() if match else None


def summary_designator(summary):
    """The contest name inside the RCTab file: '1B03', or 'ANC 6A06' for some uploads."""
    contest = summary['config']['contest'].strip().upper()
    return re.sub(r'^ANC[\s-]*', '', contest)


def release_date(release_name):
    match = RELEASE_DATE_RE.search(release_name)
    if not match:
        return None
    return datetime.datetime.strptime(match.group(1), '%B %d, %Y').date()


def cache_name(text):
    return re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-')


def rcvis_slug(url):
    match = RCVIS_SLUG_RE.match(url.strip())
    if not match:
        raise RcvError(f'Not an RCVis visualization link: {url}')
    return match.group(1)


class Fetcher:
    """Fetches from DCBOE and RCVis, caching under cache_dir/<election code>/."""

    def __init__(self, election_code, cache_dir=DEFAULT_CACHE_DIR, log=None):
        self.election_code = election_code
        self.dir = Path(cache_dir) / election_code
        self.log = log or (lambda message: None)
        self._last_rcvis_request = False

    def _get(self, url, **params):
        try:
            response = requests.get(url, params=params or None, headers={'User-Agent': USER_AGENT},
                                    timeout=REQUEST_TIMEOUT_SECONDS)
            response.raise_for_status()
        except requests.RequestException as e:
            raise RcvError(f'Could not fetch {url}: {e}') from e
        return response

    def releases(self):
        """DCBOE's published RCV release names, newest first. Always fetched fresh."""
        info = self._get(f'{DCBOE_BASE_URL}/electionResults/getElectionInfo/{self.election_code}').json()
        return info.get('RCVPublishedDisplayNames') or []

    def contests(self, release):
        """DCBOE's list of contests tabulated in `release`, cached once read."""
        path = self.dir / 'contests' / f'{cache_name(release)}.json'
        if path.exists():
            return json.loads(path.read_text(encoding='utf-8'))
        self.log(f'Fetching the contest list for "{release}" from DCBOE.')
        stats = self._get(f'{DCBOE_BASE_URL}/RCV/GetContestStats/{self.election_code}', displayName=release).json()
        self._save(path, stats)
        return stats

    def summary(self, url):
        """The RCTab summary behind an RCVis visualization, cached by slug."""
        slug = rcvis_slug(url)
        path = self.dir / 'rcvis' / f'{slug}.json'
        if path.exists():
            return json.loads(path.read_text(encoding='utf-8'))
        if self._last_rcvis_request:
            time.sleep(RCVIS_REQUEST_DELAY_SECONDS)
        self._last_rcvis_request = True
        self.log(f'Fetching {url}')
        try:
            data = extract_summary(self._get(f'https://www.rcvis.com/v/{slug}').text)
        except RcvError as e:
            raise RcvError(f'{slug}: {e}') from e
        self._save(path, data)
        return data

    def _save(self, path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=1, sort_keys=True) + '\n', encoding='utf-8')
