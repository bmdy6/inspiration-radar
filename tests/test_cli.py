import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from inspiration_radar import sources
from inspiration_radar.core import load_config


class CliTests(unittest.TestCase):
    def test_installed_demo_is_offline_and_repeats(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = {**os.environ, 'GITHUB_TOKEN': ''}
            cmd = [sys.executable, '-m', 'inspiration_radar', '--state', tmp, 'demo']
            a = subprocess.run(cmd, capture_output=True, text=True, env=env)
            b = subprocess.run(cmd, capture_output=True, text=True, env=env)
            self.assertEqual(a.returncode, 0, a.stderr)
            self.assertEqual(b.returncode, 0, b.stderr)
            self.assertIn('complete', a.stdout)
            self.assertIn('already_published', b.stdout)

    def test_discovery_never_creates_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            from datetime import datetime, timezone
            candidate = {'kind': 'article', 'title': 'A small experiment',
                         'url': 'https://example.org/experiment',
                         'published_at': datetime.now(timezone.utc).isoformat()}
            (root / 'in.json').write_text(json.dumps({'candidates': [candidate]}))
            result = subprocess.run([sys.executable, '-m', 'inspiration_radar', '--state',
                                     str(root / 'state'), 'discover', '--input', str(root / 'in.json')],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(len(json.loads(result.stdout)['candidates']), 1)
            self.assertFalse((root / 'state').exists())

    def test_malformed_input_fails_without_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'bad.json').write_text('{"items": [null]}')
            p = subprocess.run([sys.executable, '-m', 'inspiration_radar', '--state',
                                str(root / 'state'), 'publish', '--scores', str(root / 'bad.json')],
                               capture_output=True, text=True)
            self.assertNotEqual(p.returncode, 0)
            self.assertNotIn('Traceback', p.stderr)

    def test_partial_and_all_failed_are_explicit_and_redacted(self):
        cfg = load_config()
        with patch.object(sources, 'github', side_effect=RuntimeError('sensitive error text')), \
                patch.object(sources, 'hacker_news', return_value=[]):
            result = sources.discover(cfg)
            self.assertEqual(result['status'], 'partial')
            self.assertNotIn('sensitive', json.dumps(result))
        with patch.object(sources, 'github', side_effect=TimeoutError), \
                patch.object(sources, 'hacker_news', side_effect=TimeoutError):
            self.assertEqual(sources.discover(cfg)['status'], 'failed')

    def test_github_search_forces_public_only(self):
        with patch.object(sources, 'request_json', return_value={'items': []}) as request:
            sources.github(load_config())
            self.assertIn('is%3Apublic', request.call_args.args[0])

    def test_redirects_are_not_followed(self):
        self.assertIsNone(sources.NoRedirect().redirect_request(None, None, 302, '', {},
                                                               'https://example.org/other'))


if __name__ == '__main__':
    unittest.main()
