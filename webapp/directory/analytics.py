"""Counts JSON API and /llms.txt requests in GoatCounter from the server.

Those responses never load the GoatCounter script in base.html, so without this they'd be
invisible. Each hit carries only the path and a title naming the kind of client ("API lookup ·
ChatGPT-User"): no IP, no user agent and no query string, since the lookup's coordinates are
usually someone's home. Leaving out the user agent also stops GoatCounter from filing assistant
traffic away as bots, which is exactly the traffic these endpoints are for.

Off unless the GOATCOUNTER_API_TOKEN setting is set (a Fly secret in production). Hits are sent
on a background thread so a slow or failing GoatCounter never delays or breaks a response.
"""
import functools
import logging
import threading

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

# Checked in order, so more specific names come before ones they contain.
KNOWN_AGENTS = [
    'ChatGPT-User', 'OAI-SearchBot', 'GPTBot',
    'Claude-User', 'Claude-SearchBot', 'ClaudeBot',
    'Perplexity-User', 'PerplexityBot',
    'Google-Extended', 'Googlebot', 'bingbot', 'Applebot', 'DuckAssistBot',
    'meta-externalagent', 'Bytespider', 'CCBot',
    'curl', 'Wget', 'python-requests', 'python-httpx', 'aiohttp', 'Go-http-client', 'node-fetch', 'axios',
]


def agent_label(user_agent):
    """A short, non-identifying name for the client: a known assistant, crawler or HTTP library,
    'Browser', or 'Other'."""
    lowered = (user_agent or '').lower()
    for name in KNOWN_AGENTS:
        if name.lower() in lowered:
            return name
    if lowered.startswith('mozilla/') and 'bot' not in lowered and 'compatible;' not in lowered:
        return 'Browser'
    return 'Other'


def _run_in_background(fn, *args):
    threading.Thread(target=fn, args=args, daemon=True).start()


def _send(payload):
    try:
        response = requests.post(
            settings.GOATCOUNTER_COUNT_URL,
            json=payload,
            headers={'Authorization': f'Bearer {settings.GOATCOUNTER_API_TOKEN}'},
            timeout=5,
        )
    except requests.RequestException as exc:
        logger.warning('GoatCounter count failed: %s', exc)
        return
    if response.status_code != 202:
        logger.warning('GoatCounter count returned %s: %s', response.status_code, response.text[:200])


def count_in_goatcounter(name):
    """View decorator: after the response is built, report one hit titled `name` (plus the status
    when it isn't 200, and the client label)."""
    def decorator(view):
        @functools.wraps(view)
        def wrapper(request, *args, **kwargs):
            response = view(request, *args, **kwargs)
            if settings.GOATCOUNTER_API_TOKEN and request.method == 'GET':
                status = '' if response.status_code == 200 else f' ({response.status_code})'
                hit = {
                    'path': request.path,
                    'title': f'{name}{status} · {agent_label(request.headers.get("User-Agent"))}',
                }
                _run_in_background(_send, {'no_sessions': True, 'hits': [hit]})
            return response
        return wrapper
    return decorator
