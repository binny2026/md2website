import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('site_init', ROOT / 'scripts/init.py')
GENERATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GENERATOR)


class PortalTests(unittest.TestCase):
    def test_layout_slots(self):
        theme = GENERATOR.PORTAL_THEME_INDEX
        self.assertIn("h(DefaultTheme.Layout", theme)
        self.assertIn("'nav-bar-content-after'", theme)
        self.assertIn("'nav-screen-content-after'", theme)
        self.assertNotIn('createApp', theme)
        self.assertNotIn('mountPortalNav', theme)
        self.assertIn('app.provide(moduleCatalogKey, createModuleCatalog())', theme)

    def test_native_navigation(self):
        for component in (GENERATOR.PORTAL_NAV, GENERATOR.PORTAL_MODULE_GRID):
            self.assertIn('target="_self"', component)
            self.assertNotIn('@click.prevent', component)
            self.assertNotIn('window.location', component)
            self.assertNotIn('fetch(', component)
        self.assertIn('max-height: 60vh', GENERATOR.PORTAL_NAV)
        self.assertIn('overflow-y: auto', GENERATOR.PORTAL_NAV)
        self.assertIn('@keydown.esc', GENERATOR.PORTAL_NAV)
        self.assertIn('portal-nav-mobile', GENERATOR.PORTAL_NAV)

    def test_home_and_configuration(self):
        self.assertNotIn('name: @@TITLE@@', GENERATOR.PORTAL_HOME_TMPL)
        self.assertIn("args.subtitle or '学习与探索'", (ROOT / 'scripts/init.py').read_text())
        self.assertIn("frequentModules: ['langchain', 'redis']", GENERATOR.PORTAL_CONFIG_TMPL)
        self.assertIn("nav: []", GENERATOR.PORTAL_CONFIG_TMPL)
        for template in (GENERATOR.CONFIG_TMPL, GENERATOR.PORTAL_CONFIG_TMPL):
            self.assertIn('href: `${base}favicon.svg`', template)
            self.assertNotIn('本页目录', template)
            self.assertIn('本页章节', template)
        self.assertIn('SCRIPT_NAME', GENERATOR.PORTAL_PHP)

    def test_config_syntax_and_favicon_bases(self):
        for template in (GENERATOR.CONFIG_TMPL, GENERATOR.PORTAL_CONFIG_TMPL):
            for base in ('/', '/notes/', '/notes/nested'):
                config = GENERATOR.render(template, {
                    'TITLE': '测试', 'DESC': '测试', 'BASE': base,
                    'CHAPTER_ITEMS': '', 'FIRST': 'chapter'
                })
                config = config.replace("import { defineConfig } from 'vitepress'", 'const defineConfig = (value) => value')
                config = config.replace('export default defineConfig(', 'const config = defineConfig(')
                script = config + '\nprocess.stdout.write(JSON.stringify({base: config.base, icon: config.head[0][1].href}))'
                for override in (None, '/override/deep/'):
                    env = dict(os.environ)
                    env.pop('VP_BASE', None)
                    if override:
                        env['VP_BASE'] = override
                    result = subprocess.run(['node', '--input-type=module'], input=script, text=True, capture_output=True, env=env, check=True)
                    data = json.loads(result.stdout)
                    expected = (override or base).rstrip('/') + '/'
                    self.assertEqual(data, {'base': expected, 'icon': expected + 'favicon.svg'})

    def test_generate_portal_without_registry_side_effects(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'portal'
            args = SimpleNamespace(out=str(output), force=False, title='文档门户', name='portal', base='/notes/', subtitle=None)
            with patch.object(GENERATOR, 'register_site') as register:
                self.assertEqual(GENERATOR.gen_portal(args), 0)
                register.assert_called_once()
            theme = output / 'docs/.vitepress/theme'
            for name, expected in (
                ('index.mjs', GENERATOR.PORTAL_THEME_INDEX),
                ('PortalNav.vue', GENERATOR.PORTAL_NAV),
                ('ModuleGrid.vue', GENERATOR.PORTAL_MODULE_GRID),
                ('moduleCatalog.mjs', GENERATOR.PORTAL_MODULE_CATALOG),
            ):
                self.assertEqual((theme / name).read_text(), expected)
            home = (output / 'docs/index.md').read_text()
            self.assertIn('text: 学习与探索', home)
            self.assertNotIn('name: 文档门户', home)
            self.assertTrue((output / 'docs/public/favicon.svg').is_file())
            self.assertIn(GENERATOR.PORTAL_CSS, (theme / 'custom.css').read_text())

    def test_catalog_deduplication_isolation_retry_and_validation(self):
        source = '\n'.join(line for line in GENERATOR.PORTAL_MODULE_CATALOG.splitlines() if not line.startswith('import '))
        script = '''
import assert from 'node:assert/strict'
const ref = (value) => ({ value })
const withBase = (path) => '/portal' + path
let calls = 0
let fail = false
let payload = [{ name: 'redis', title: 'Redis', link: '/redis/' }]
globalThis.fetch = async (path) => {
  assert.equal(path, '/portal/modules.json.php')
  calls++
  await new Promise((resolve) => setTimeout(resolve, 5))
  return { ok: !fail, json: async () => payload }
}
'''
        script += source + '''
const first = createModuleCatalog()
await Promise.all([first.load(), first.load(), first.load()])
assert.equal(calls, 1)
assert.equal(first.modules.value.length, 1)
await first.load()
assert.equal(calls, 1)
const second = createModuleCatalog()
assert.equal(second.modules.value.length, 0)
fail = true
await second.load()
assert.equal(second.error.value, true)
assert.equal(second.loading.value, false)
fail = false
payload = [...payload, ...payload, null, { name: 'bad', title: 'Bad', link: 'javascript:alert(1)' }, { name: 'other', title: 'Other', link: '//untrusted.test/' }]
await second.load()
assert.equal(second.error.value, false)
assert.equal(second.modules.value.length, 1)
assert.equal(calls, 3)
payload = {}
const third = createModuleCatalog()
await third.load()
assert.equal(third.error.value, true)
assert.equal(third.modules.value.length, 0)
'''
        subprocess.run(['node', '--input-type=module'], input=script, text=True, capture_output=True, check=True)


if __name__ == '__main__':
    unittest.main()
