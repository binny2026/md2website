"""Integration test: real generated builds, isolated under /tmp."""
import hashlib
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class DeadLinksTest(unittest.TestCase):
    def test_build(self):
        with tempfile.TemporaryDirectory(prefix='md2website-links-', dir='/tmp') as tmp:
            root = Path(tmp)
            source = root / 'source'
            source.mkdir()
            (source / 'guide.md').write_text('''# Guide

## Valid

[missing](./absent.md)
[bad anchor](#absent)
[good anchor](#valid)
[other good](./other.md#hello)
[other bad](./other.md#absent)
[external](https://example.com/missing)
[lan](http://192.168.1.2:8080/missing)
[protocol relative](//192.168.1.2/missing)
[base good](/other#hello)
[base bad](/absent)

<a href="/another-service/">sibling</a>
<a href="./other.html#absent">raw bad</a>
<a href="/nested/missing.html">raw missing</a>

```html
<a href="/nested/not-a-link">code sample</a>
```
''', encoding='utf8')
            (source / 'other.md').write_text('# Other\n\n## Hello\n', encoding='utf8')
            before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in source.iterdir()}
            env = dict(os.environ, HOME=str(root), VP_BASE='/nested/')
            project = root / 'ci/project'
            result = subprocess.run(['python3', str(ROOT / 'scripts/ci.py'), 'build',
                '--source', str(source), '--out', str(root / 'ci'), '--name', 'links',
                '--title', 'Links', '--base', '/nested/'], env=env, text=True,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            self.assertEqual(result.returncode, 0, result.stdout)
            dist = project / 'docs/.vitepress/dist'
            html = (dist / 'guide.html').read_text()
            self.assertEqual(html.count('class="md2website-dead-link"'), 6, html)
            for href in ('#valid', '/nested/other#hello', 'https://example.com/missing',
                         'http://192.168.1.2:8080/missing', '//192.168.1.2/missing', '/another-service/'):
                self.assertIn('href="' + href + '"', html)
            self.assertIn('data-original-href=', html)
            client = '\n'.join(p.read_text() for p in (dist / 'assets').glob('guide.md.*.js'))
            self.assertIn('md2website-dead-link', client)
            self.assertIn('（链接已失效）', client)
            self.assertIn('[失效链接]', result.stdout)
            self.assertIn('失效链接总数：6', result.stdout)
            self.assertEqual(before, {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in source.iterdir()})
            # Ordinary npm builds use exactly the same path; repeat to catch stale caches.
            result = subprocess.run(['npm', 'run', 'build'], cwd=project, env=env,
                text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertEqual((dist / 'guide.html').read_text().count('class="md2website-dead-link"'), 6)
            root_env = dict(env, VP_BASE='/')
            result = subprocess.run(['npm', 'run', 'build'], cwd=project, env=root_env,
                text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertEqual((dist / 'guide.html').read_text().count('class="md2website-dead-link"'), 7)
            self.assertEqual(before, {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in source.iterdir()})
            (project / 'docs/broken.md').write_text('<div>\n', encoding='utf8')
            result = subprocess.run(['npm', 'run', 'build'], cwd=project, env=env,
                text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('Element is missing end tag', result.stdout)


if __name__ == '__main__':
    unittest.main()
