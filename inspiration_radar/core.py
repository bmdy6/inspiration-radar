"""Candidate identity and evidence-based selection; no network or writes."""
from datetime import datetime, timedelta, timezone
import json
import math
from pathlib import Path
import ipaddress
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

DIMENSIONS = {
    'github': ['relevance', 'heat', 'maturity', 'utility', 'novelty'],
    'article': ['relevance', 'depth', 'hn_heat', 'timeliness', 'actionability'],
}
DEFAULT_CONFIG = {
    'name': 'Inspiration Radar', 'max_age_days': 90, 'max_items': 5,
    'source_limit': 10, 'github_query': 'creative tools', 'hn_query': 'creative tools',
    'topics': 'Creative products, interaction design, learning and practical experiments',
    'exclude_terms': [],
    'github': {'min_total': 6.0, 'min_relevance': 6.0, 'weights':
               dict(zip(DIMENSIONS['github'], [.35, .15, .15, .25, .10]))},
    'article': {'min_total': 6.5, 'min_relevance': 6.0, 'min_depth': 6.0, 'weights':
                dict(zip(DIMENSIONS['article'], [.30, .25, .15, .10, .20]))},
}


def load_config(path=None):
    cfg = json.loads(Path(path).read_text()) if path else json.loads(json.dumps(DEFAULT_CONFIG))
    for key, maximum in [('max_items', 50), ('source_limit', 50), ('max_age_days', 3650)]:
        if type(cfg.get(key)) is not int or not 1 <= cfg[key] <= maximum:
            raise ValueError(f'Invalid configuration: {key}')
    for kind, dims in DIMENSIONS.items():
        part = cfg[kind]
        weights = part['weights']
        if set(weights) != set(dims) or any(type(v) not in (int, float) or
                not math.isfinite(v) or v < 0 for v in weights.values()):
            raise ValueError(f'Invalid weights: {kind}')
        if not math.isclose(sum(weights.values()), 1):
            raise ValueError('Weights must sum to 1')
        for key in ['min_total', 'min_relevance'] + (['min_depth'] if kind == 'article' else []):
            number(part[key])
    if not isinstance(cfg.get('exclude_terms'), list) or not all(
            isinstance(s, str) and s.strip() for s in cfg['exclude_terms']):
        raise ValueError('exclude_terms must be a list of nonempty strings')
    for key in ['name', 'topics', 'github_query', 'hn_query']:
        if not isinstance(cfg.get(key), str) or not cfg[key].strip():
            raise ValueError(f'Invalid configuration: {key}')
    return cfg


def number(value):
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 10:
        raise ValueError('Scores must be finite numbers from 0 to 10')
    return value


def normalize_url(url):
    if not isinstance(url, str):
        raise ValueError('A public HTTP(S) URL is required')
    p = urlsplit(url.strip())
    if p.scheme not in ('http', 'https') or not p.hostname or p.username or p.password:
        raise ValueError('A public HTTP(S) URL without credentials is required')
    host = p.hostname.lower()
    try:
        if not ipaddress.ip_address(host).is_global:
            raise ValueError('Private addresses are not allowed')
    except ValueError:
        # Hostnames are permitted; IP literals must be global addresses.
        if ':' in host or all(c in '0123456789.' for c in host):
            raise ValueError('IP literals are not supported') from None
    if (host == 'localhost' or '.' not in host or any(ord(c) < 33 for c in url)
            or any(c in url for c in '<>"\\')):
        raise ValueError('Invalid public URL')
    port = p.port
    netloc = host if not port or (p.scheme, port) in [('https', 443), ('http', 80)] else f'{host}:{port}'
    path = p.path.rstrip('/') or '/'
    pairs = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)
             if not k.lower().startswith('utm_') and k.lower() not in ('fbclid', 'gclid', 'ref')]
    return urlunsplit((p.scheme.lower(), netloc, path, urlencode(sorted(pairs)), ''))


def candidate_key(item):
    url = normalize_url(item.get('url'))
    p = urlsplit(url)
    if p.hostname in ('github.com', 'www.github.com'):
        parts = p.path.strip('/').split('/')
        if len(parts) >= 2 and all(parts[:2]):
            return 'github:' + '/'.join(parts[:2]).lower().removesuffix('.git')
    return 'url:' + url


def recent(item, cfg, now):
    try:
        dt = datetime.fromisoformat(item['published_at'].replace('Z', '+00:00'))
        if dt.tzinfo is None:
            return False
        return now - timedelta(days=cfg['max_age_days']) <= dt <= now
    except (KeyError, TypeError, ValueError, AttributeError):
        return False


def filter_candidates(items, cfg, seen, *, now=None, demo=False):
    now = now or datetime.now(timezone.utc)
    found = set(seen)
    result = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError('Each candidate must be an object')
        key = candidate_key(item)
        if key in found or (not demo and not recent(item, cfg, now)):
            continue
        if item.get('kind') not in DIMENSIONS or not str(item.get('title', '')).strip():
            raise ValueError('Candidate needs title and kind: github or article')
        if item['kind'] == 'github' and not key.startswith('github:'):
            raise ValueError('GitHub items need a repository URL')
        text = (item['title'] + ' ' + str(item.get('summary', ''))).lower()
        if any(term.lower() in text for term in cfg['exclude_terms']):
            continue
        found.add(key)
        result.append({**item, 'url': normalize_url(item['url']), 'candidate_key': key})
    return result


def select_items(items, cfg, seen, *, now=None, demo=False):
    selected = []
    for item in filter_candidates(items, cfg, seen, now=now, demo=demo):
        if item.get('verified') is not True:
            continue
        for field in ('what', 'highlight', 'inspire'):
            if not isinstance(item.get(field), str) or not item[field].strip():
                raise ValueError(f'Verified item is missing {field}')
        scores = item.get('scores', {})
        part = cfg[item['kind']]
        for dim in DIMENSIONS[item['kind']]:
            row = scores.get(dim, {})
            number(row.get('score'))
            for field in ('reason', 'evidence'):
                if not isinstance(row.get(field), str) or not row[field].strip():
                    raise ValueError(f'{dim} needs {field}')
        total = round(sum(scores[d]['score'] * w for d, w in part['weights'].items()), 1)
        if total < part['min_total'] or scores['relevance']['score'] < part['min_relevance']:
            continue
        if item['kind'] == 'article' and scores['depth']['score'] < part['min_depth']:
            continue
        selected.append({**item, 'total_score': total})
    return sorted(selected, key=lambda x: (-x['total_score'], x['candidate_key']))[:cfg['max_items']]
