import json
import tempfile
import unittest
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from inspiration_radar.core import candidate_key, select_items, load_config
from inspiration_radar.store import publish, load_seen


ROOT = Path(__file__).resolve().parents[1]


class RadarTests(unittest.TestCase):
    def setUp(self):
        self.config = load_config(ROOT / 'config/default.json')
        self.items = json.loads((ROOT / 'examples/scored.json').read_text())['items']

    def test_github_identity_is_case_insensitive(self):
        self.assertEqual(candidate_key({'url': 'https://github.com/Example/Sketch.git/'}),
                         candidate_key({'url': 'https://github.com/example/sketch?utm_source=feed'}))

    def test_article_tracking_and_query_order(self):
        self.assertEqual(candidate_key({'url': 'https://example.org/a?b=2&a=1&utm_source=x#part'}),
                         candidate_key({'url': 'https://example.org/a?a=1&b=2'}))

    def test_unverified_and_old_are_excluded(self):
        from datetime import datetime, timezone
        now = datetime(2026, 11, 17, tzinfo=timezone.utc)
        self.items[0]['verified'] = False
        self.items[1]['published_at'] = '2020-01-01T00:00:00Z'
        self.assertEqual(select_items(self.items, self.config, set(), now=now), [])

    def test_nan_bool_and_missing_evidence_rejected(self):
        for value in [float('nan'), True, 11]:
            with self.subTest(value=value):
                self.items[0]['scores']['relevance']['score'] = value
                with self.assertRaises(ValueError):
                    select_items(self.items, self.config, set(), demo=True)
        self.items[0]['scores']['relevance']['score'] = 8
        self.items[0]['scores']['relevance']['evidence'] = ''
        with self.assertRaises(ValueError):
            select_items(self.items, self.config, set(), demo=True)

    def test_empty_and_invalid_urls_rejected(self):
        for url in ['', 'file:///etc/passwd', 'https://user:password@example.org/a',
                    'https://127.0.0.1/a', 'https://example.org/a><script>']:
            with self.assertRaises(ValueError):
                candidate_key({'url': url})

    def test_default_example_matches_built_in_rules(self):
        self.assertEqual(load_config(), self.config)

    def test_wrong_weights_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'cfg.json'
            self.config['github']['weights']['relevance'] = 1
            path.write_text(json.dumps(self.config))
            with self.assertRaises(ValueError):
                load_config(path)

    def test_demo_and_real_same_day_cannot_mix(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            publish(self.items, self.config, state, '2026-11-17', demo=True)
            with self.assertRaises(ValueError):
                publish(self.items, self.config, state, '2026-11-17', demo=False)

    def test_publish_repeat_and_concurrent(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            def run():
                return publish(self.items, self.config, state, '2026-11-17', demo=True)
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(lambda _: run(), range(2)))
            self.assertEqual(sorted(r['status'] for r in results), ['already_published', 'complete'])
            self.assertEqual(len(load_seen(state)), 2)
            self.assertTrue((state / 'daily/2026-11-17.md').exists())

    def test_later_day_permanent_dedup(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            publish(self.items, self.config, state, '2026-11-17', demo=True)
            result = publish(self.items, self.config, state, '2026-11-18', demo=True)
            self.assertEqual(result['count'], 0)

    def test_failed_export_does_not_mark_seen(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            with patch('inspiration_radar.store.export_report', side_effect=OSError('disk full')):
                with self.assertRaises(OSError):
                    publish(self.items, self.config, state, '2026-11-17', demo=True)
            self.assertEqual(load_seen(state), set())

    def test_same_day_repairs_missing_exports(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            publish(self.items, self.config, state, '2026-11-17', demo=True)
            (state / 'daily/2026-11-17.md').unlink()
            publish([], self.config, state, '2026-11-17', demo=True)
            self.assertIn('Sketch Garden', (state / 'daily/2026-11-17.md').read_text())


if __name__ == '__main__':
    unittest.main()
