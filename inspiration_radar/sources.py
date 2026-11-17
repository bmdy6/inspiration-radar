"""Bounded public API reads. Never fetch candidate URLs or follow redirects."""
from datetime import datetime, timedelta, timezone
import json
import os
from urllib.parse import urlencode
from urllib.request import Request, build_opener, HTTPRedirectHandler, ProxyHandler

LIMIT = 2 * 1024 * 1024


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def request_json(url, *, payload=None, token=None):
    headers = {'User-Agent': 'inspiration-radar/0.1', 'Accept': 'application/json'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    data = None if payload is None else json.dumps(payload).encode()
    if data:
        headers['Content-Type'] = 'application/json'
    req = Request(url, data=data, headers=headers)
    # No implicit proxy: API credentials must only go to the configured HTTPS endpoint.
    with build_opener(ProxyHandler({}), NoRedirect()).open(req, timeout=20) as response:
        raw = response.read(LIMIT + 1)
        if len(raw) > LIMIT:
            raise ValueError('Response exceeds 2 MiB')
        return json.loads(raw)


def github(cfg):
    cutoff = (datetime.now(timezone.utc) - timedelta(days=cfg['max_age_days'])).date()
    query = f"{cfg['github_query']} created:>={cutoff} archived:false fork:false is:public"
    data = request_json('https://api.github.com/search/repositories?' + urlencode(
        {'q': query, 'sort': 'stars', 'per_page': cfg['source_limit']}), token=os.getenv('GITHUB_TOKEN'))
    return [{'kind': 'github', 'title': r['full_name'], 'url': r['html_url'],
             'published_at': r['created_at'], 'summary': r.get('description') or '',
             'source': 'github', 'stars': r['stargazers_count'], 'verified': False}
            for r in data['items'] if not r.get('private')]


def hacker_news(cfg):
    cutoff = int((datetime.now(timezone.utc) - timedelta(days=cfg['max_age_days'])).timestamp())
    data = request_json('https://hn.algolia.com/api/v1/search?' + urlencode(
        {'query': cfg['hn_query'], 'tags': 'story', 'numericFilters': f'created_at_i>{cutoff}',
         'hitsPerPage': cfg['source_limit']}))
    return [{'kind': 'article', 'title': r['title'], 'url': r['url'],
             'published_at': r['created_at'], 'summary': r['title'],
             'source': 'hacker_news', 'hn_score': r.get('points', 0), 'verified': False}
            for r in data['hits'] if r.get('title') and r.get('url')]


def discover(cfg, providers=('github', 'hacker_news')):
    available = {'github': github, 'hacker_news': hacker_news}
    items, statuses = [], {}
    for name in providers:
        try:
            rows = available[name](cfg)
            items.extend(rows)
            statuses[name] = {'status': 'ok', 'count': len(rows)}
        except Exception as exc:
            # Do not print request bodies, URLs, tokens or upstream exception strings.
            statuses[name] = {'status': 'failed', 'error_type': type(exc).__name__}
    ok = sum(s['status'] == 'ok' for s in statuses.values())
    status = 'ok' if ok == len(statuses) else 'partial' if ok else 'failed'
    return {'status': status, 'sources': statuses, 'candidates': items}
