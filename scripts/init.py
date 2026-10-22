#!/usr/bin/env python3
"""
把 Markdown 项目初始化为静态文档站（不删除、不覆盖源 Markdown 内容）。

用法:
    python3 init.py <md源目录> [--out <输出目录>] [--title 标题] [--chapters]

行为:
  - 扫描源目录结构，识别章节目录（含 .md 的目录）
  - 复制 Markdown 与图片资源到输出目录 docs/ 下，源目录只读
  - 生成 .vitepress/config.mjs（含 Vue 语法转义规则）、首页、主题、部署脚本
  - 输出目录已存在则拒绝执行（避免覆盖）

--chapters: 按章节目录生成导航（默认自动判断：顶层子目录都含 md 时视为章节）
"""
import argparse
import datetime
import json
import os
import re
import shutil
import sys

IMG_EXTS = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg', '.bmp', '.ico'}
SKIP_DIRS = {'node_modules', '.git', '.vitepress', 'dist', 'build', '.cache', '__pycache__'}
SKIP_FILES = {'.DS_Store'}

META_FILE = '.md2website.json'
REGISTRY_DIR = os.path.join(os.path.expanduser('~'), '.md2website')
REGISTRY_FILE = os.path.join(REGISTRY_DIR, 'sites.json')
# --force 重建时清理的生成物；部署配置、依赖与其他用户文件一律保留
GENERATED_ITEMS = ('docs', 'package.json', '.gitignore', 'DEPLOY.md', 'deploy.sh')


def _now():
    return datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def register_site(out, meta):
    """登记到 ~/.md2website/sites.json，供 sites.py / update.py 查找"""
    try:
        os.makedirs(REGISTRY_DIR, exist_ok=True)
        data = {'version': 1, 'sites': []}
        if os.path.isfile(REGISTRY_FILE):
            try:
                with open(REGISTRY_FILE, encoding='utf-8') as f:
                    loaded = json.load(f)
                if isinstance(loaded, dict) and isinstance(loaded.get('sites'), list):
                    data = loaded
            except (OSError, ValueError):
                pass
        entry = {'path': out, **meta}
        data['sites'] = [s for s in data['sites'] if s.get('path') != out] + [entry]
        with open(REGISTRY_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write('\n')
    except OSError as e:
        print(f'  ! 站点登记失败（不影响站点生成）：{e}', file=sys.stderr)


def write_meta(out, src, title, site_name, base, role=None):
    """写入站点元数据，记录源目录；更新站点时据此重新生成"""
    path = os.path.join(out, META_FILE)
    old = {}
    if os.path.isfile(path):
        try:
            with open(path, encoding='utf-8') as f:
                old = json.load(f)
        except (OSError, ValueError):
            old = {}
    meta = {
        'name': site_name,
        'title': title,
        'source': src,
        'base': base,
        'created_at': old.get('created_at') or _now(),
        'updated_at': _now(),
    }
    if role:
        meta['role'] = role
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
        f.write('\n')
    register_site(out, meta)
    return meta

# ---------------------------------------------------------------- 结构扫描

def find_md_dirs(root):
    """返回 (章节目录列表, 根目录直放md?)。章节目录 = 含 .md 的直接子目录。"""
    chapters = []
    root_md = []
    for name in sorted(os.listdir(root)):
        p = os.path.join(root, name)
        if os.path.isdir(p):
            if name in SKIP_DIRS or name.startswith('.'):
                continue
            has_md = any(f.lower().endswith(('.md', '.markdown'))
                         for f in os.listdir(p)
                         if os.path.isfile(os.path.join(p, f)))
            if has_md:
                chapters.append(name)
        elif name.lower().endswith(('.md', '.markdown')):
            root_md.append(name)
    return chapters, root_md


def pick_main_md(dirpath):
    """目录内主文档：同名 md > index.md > README.md > 唯一/第一个 md"""
    mds = sorted(f for f in os.listdir(dirpath)
                 if f.lower().endswith(('.md', '.markdown'))
                 and os.path.isfile(os.path.join(dirpath, f)))
    if not mds:
        return None
    dirname = os.path.basename(dirpath)
    for fn in mds:
        if os.path.splitext(fn)[0] == dirname:
            return fn
    for prefer in ('index.md', 'README.md'):
        for fn in mds:
            if fn.lower() == prefer.lower():
                return fn
    return mds[0]


def dir_title(dirpath):
    """章节标题：取主文档首个 H1，否则用目录名"""
    main = pick_main_md(dirpath)
    if main:
        try:
            for line in open(os.path.join(dirpath, main), encoding='utf-8', errors='replace'):
                m = re.match(r'^#\s+(.+?)\s*$', line)
                if m:
                    return m.group(1).strip(), main
                if line.strip():
                    break
        except OSError:
            pass
    return os.path.basename(dirpath), main


def first_h1(path):
    """提取 md 文件的首个 H1 标题，无则返回 None"""
    try:
        for line in open(path, encoding='utf-8', errors='replace'):
            m = re.match(r'^#\s+(.+?)\s*$', line)
            if m:
                return m.group(1).strip()
            if line.strip():
                break
    except OSError:
        pass
    return None


def build_dir_tree(dirpath, slug, relpath=''):
    """递归生成目录的侧边栏树，返回 items 列表（支持多级子目录）。"""
    mds = sorted(f for f in os.listdir(dirpath)
                 if f.lower().endswith(('.md', '.markdown'))
                 and os.path.isfile(os.path.join(dirpath, f)))
    subdirs = sorted(d for d in os.listdir(dirpath)
                     if os.path.isdir(os.path.join(dirpath, d))
                     and d not in SKIP_DIRS and not d.startswith('.'))
    main = pick_main_md(dirpath)
    items = []

    for fn in mds:
        title = first_h1(os.path.join(dirpath, fn)) or os.path.splitext(fn)[0]
        if fn == main:
            link = f"/{slug}/" if relpath == '' else f"/{slug}/{relpath}/"
        else:
            base = f"/{slug}" if relpath == '' else f"/{slug}/{relpath}"
            link = f"{base}/{os.path.splitext(fn)[0]}"
        items.append({"text": title, "link": link})

    for d in subdirs:
        sub_rel = f"{relpath}/{d}" if relpath else d
        sub_items = build_dir_tree(os.path.join(dirpath, d), slug, sub_rel)
        if sub_items:
            items.append({"text": d, "collapsed": True, "items": sub_items})

    return items


def build_md_map(src_dir, slug):
    """章节内每个源 md 文件名 → 站点 URL 的映射（递归，供死链改写用）"""
    m = {}
    for dirpath, dirnames, filenames in os.walk(src_dir):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith('.')]
        relp = os.path.relpath(dirpath, src_dir)
        main = pick_main_md(dirpath)
        for fn in filenames:
            if not fn.lower().endswith(('.md', '.markdown')):
                continue
            if fn == main:
                url = f"/{slug}/" if relp == '.' else f"/{slug}/{relp}/"
            else:
                base = f"/{slug}" if relp == '.' else f"/{slug}/{relp}"
                url = f"{base}/{os.path.splitext(fn)[0]}"
            m[fn] = url
    return m


def fix_dead_links(docs, md_map):
    """把指向源 .md 文件的 markdown 链接改写为站点 URL，避免站点死链报错。"""
    if not md_map:
        return 0
    link_re = re.compile(r'\]\(([^)]+)\)')
    fixed = 0
    for dirpath, dirnames, filenames in os.walk(docs):
        dirnames[:] = [d for d in dirnames if d not in {'.vitepress', 'node_modules'}]
        for fn in filenames:
            if not fn.lower().endswith(('.md', '.markdown')):
                continue
            path = os.path.join(dirpath, fn)
            try:
                text = open(path, encoding='utf-8').read()
            except OSError:
                continue

            changed = 0

            def repl(m):
                nonlocal changed
                target = m.group(1).strip()
                if not target.lower().endswith('.md'):
                    return m.group(0)
                url = md_map.get(os.path.basename(target))
                if url:
                    changed += 1
                    return f']({url})'
                return m.group(0)

            new_text = link_re.sub(repl, text)
            if changed:
                with open(path, 'w', encoding='utf-8') as f:
                    f.write(new_text)
                fixed += changed
    return fixed


def slugify(name, used):
    """目录名 → URL slug（保留中文，去掉不安全字符）"""
    s = re.sub(r'[\\/:*?"<>|\s]+', '-', name).strip('-')
    s = re.sub(r'-{2,}', '-', s)
    if not s:
        s = 'page'
    base, n = s, 2
    while s in used:
        s = f'{base}-{n}'
        n += 1
    used.add(s)
    return s


def to_ascii_slug(title, fallback='md2website'):
    """标题 → ASCII 标识名：英文/数字保留，中文转拼音全拼（依赖 pypinyin，缺失则回退）。"""
    if not title:
        return fallback
    if not re.search(r'[\u4e00-\u9fff]', title):
        s = re.sub(r'[^a-z0-9-]+', '-', title.lower()).strip('-')
        return s or fallback
    try:
        from pypinyin import lazy_pinyin
        s = ''.join(lazy_pinyin(title))
        s = re.sub(r'[^a-z0-9]+', '', s.lower())
        if s:
            return s
    except ImportError:
        pass
    s = re.sub(r'[^a-z0-9-]+', '-', title.lower()).strip('-')
    return s or fallback


def make_favicon_svg(title):
    """根据站点标题生成首字符 favicon SVG（品牌色渐变 + 居中首字符）。"""
    import html
    char = ''
    s = (title or '').strip()
    if s:
        first = s[0]
        if re.search(r'[\u4e00-\u9fff]', first):
            char = first
        elif first.isascii() and first.isalpha():
            char = first.upper()
        else:
            char = first
    char = char or 'M'
    esc = html.escape(char)
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
  <defs>
    <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#0891b2"/>
      <stop offset="0.55" stop-color="#6d5ef0"/>
      <stop offset="1" stop-color="#a855f7"/>
    </linearGradient>
  </defs>
  <rect width="64" height="64" rx="14" fill="url(#g)"/>
  <text x="32" y="43" font-size="30" fill="#ffffff" text-anchor="middle" font-family="system-ui, sans-serif" font-weight="600">{esc}</text>
</svg>
'''


# ---------------------------------------------------------------- 代码模板

CONFIG_TMPL = '''import { defineConfig } from 'vitepress'

const base = `${(process.env.VP_BASE || '@@BASE@@').replace(/\\/+$/, '')}/`

// 章节导航：新增章节时在此追加一条即可
const chapters = [
@@CHAPTER_ITEMS@@
]

export default defineConfig({
  lang: 'zh-CN',
  title: '@@TITLE@@',
  description: '@@DESC@@',
  head: [
    ['link', { rel: 'icon', href: `${base}favicon.svg` }]
  ],
  // base 优先取环境变量 VP_BASE（子模块挂门户时由 deploy.sh 注入），否则用生成时的值
  base,
  cleanUrls: true,

  markdown: {
    lineNumbers: true,
    theme: { light: 'github-light', dark: 'github-dark' },
    config(md) {
      // 正文中的 <https://...>、<占位符>、双花括号 会被 Vue 编译器误判为标签/插值，
      // 在 Vue 解析前把它们安全转成普通文本或链接。
      md.core.ruler.after('inline', 'escape_vue_syntax', (state) => {
        for (const token of state.tokens) {
          if (token.type !== 'inline' || !token.children) continue
          for (const child of token.children) {
            if (child.type === 'html_inline') {
              const raw = child.content
              // <https://...> / <mailto:...> → 可点击链接
              if (/^<(?:https?:\\/\\/|mailto:|ftp:\\/\\/)/i.test(raw) && raw.length > 2) {
                const inner = raw.slice(1, -1)
                child.type = 'link'
                child.tag = 'a'
                child.attrs = [['href', inner]]
                child.markup = 'autolink'
                child.content = ''
                child.children = [{ type: 'text', content: inner, level: 0 }]
              } else if (/^<[A-Za-z][\\w.\\-]*(?::[\\w.\\-]+)?>/.test(raw)) {
                child.type = 'text'
                child.markup = ''
              }
            } else if (child.type === 'text' && child.content.includes('{')) {
              child.content = child.content
                .replace(/\\{\\{/g, '&#123;&#123;')
                .replace(/\\}\\}/g, '&#125;&#125;')
            }
          }
        }
      })
    }
  },

  themeConfig: {
    outline: { level: [2, 3], label: '本页章节' },
    nav: [
      { text: '首页', link: '/' },
      { text: '文档', link: '/@@FIRST@@/' },
      // 子模块挂门户时，deploy.sh 会注入 PORTAL_URL 环境变量，添加「返回门户」入口
      ...(process.env.PORTAL_URL ? [{ text: '返回门户', link: process.env.PORTAL_URL, target: '_self' }] : [])
    ],
    sidebar: [
      {
        text: '目录',
        items: chapters.map((ch) => ch.type === 'group'
          ? { text: ch.text, collapsed: true, items: ch.items }
          : { text: ch.text, link: ch.link })
      }
    ],
    search: {
      provider: 'local',
      options: {
        translations: {
          button: { buttonText: '搜索', buttonAriaLabel: '搜索文档' },
          modal: {
            noResultsText: '没有找到结果',
            resetButtonTitle: '清除',
            footer: { selectText: '选择', navigateText: '切换', closeText: '关闭' }
          }
        }
      }
    },
    docFooter: { prev: '上一篇', next: '下一篇' },
    outlineTitle: '本页章节',
    returnToTopLabel: '回到顶部',
    sidebarMenuLabel: '目录',
    darkModeSwitchLabel: '主题',
    lastUpdated: { text: '最后更新' }
  }
})
'''


THEME_INDEX = '''import DefaultTheme from 'vitepress/theme'
import { onMounted, watch, nextTick } from 'vue'
import { useRoute } from 'vitepress'
import './custom.css'

// 图片点击放大（替代 VuePress 的 medium-zoom 插件）
function installZoom() {
  document.querySelectorAll('.vp-doc img').forEach((img) => {
    if (img.dataset.zoomBound) return
    img.dataset.zoomBound = '1'
    img.classList.add('zoomable')
    img.addEventListener('click', () => {
      const mask = document.createElement('div')
      mask.className = 'img-zoom-mask'
      const big = document.createElement('img')
      big.src = img.src
      big.alt = img.alt || ''
      mask.appendChild(big)
      document.body.appendChild(mask)
      requestAnimationFrame(() => mask.classList.add('open'))
      const close = () => {
        mask.classList.remove('open')
        setTimeout(() => mask.remove(), 180)
        document.removeEventListener('keydown', onKey)
      }
      const onKey = (e) => e.key === 'Escape' && close()
      mask.addEventListener('click', close)
      document.addEventListener('keydown', onKey)
    })
  })
}

export default {
  extends: DefaultTheme,
  setup() {
    const route = useRoute()
    const run = () => nextTick(() => setTimeout(installZoom, 60))
    onMounted(run)
    watch(() => route.path, run)
  }
}
'''

# 门户主题：注册 ModuleGrid（首页卡片）+ PortalNav（顶部动态下拉导航）
PORTAL_THEME_INDEX = '''import { h, onMounted, watch, nextTick } from 'vue'
import DefaultTheme from 'vitepress/theme'
import { useRoute } from 'vitepress'
import ModuleGrid from './ModuleGrid.vue'
import PortalNav from './PortalNav.vue'
import { createModuleCatalog, moduleCatalogKey } from './moduleCatalog.mjs'
import './custom.css'

function installZoom() {
  document.querySelectorAll('.vp-doc img').forEach((img) => {
    if (img.dataset.zoomBound) return
    img.dataset.zoomBound = '1'
    img.classList.add('zoomable')
    img.addEventListener('click', () => {
      const mask = document.createElement('div')
      mask.className = 'img-zoom-mask'
      const big = document.createElement('img')
      big.src = img.src
      big.alt = img.alt || ''
      mask.appendChild(big)
      document.body.appendChild(mask)
      requestAnimationFrame(() => mask.classList.add('open'))
      const close = () => {
        mask.classList.remove('open')
        setTimeout(() => mask.remove(), 180)
        document.removeEventListener('keydown', onKey)
      }
      const onKey = (e) => e.key === 'Escape' && close()
      mask.addEventListener('click', close)
      document.addEventListener('keydown', onKey)
    })
  })
}

export default {
  extends: DefaultTheme,
  Layout: () => h(DefaultTheme.Layout, null, {
    'nav-bar-content-after': () => h(PortalNav),
    'nav-screen-content-after': () => h(PortalNav, { mobile: true })
  }),
  enhanceApp({ app }) {
    app.provide(moduleCatalogKey, createModuleCatalog())
    app.component('ModuleGrid', ModuleGrid)
  },
  setup() {
    const route = useRoute()
    const run = () => nextTick(() => setTimeout(installZoom, 60))
    onMounted(run)
    watch(() => route.path, run)

  }
}
'''

# 门户首页动态子模块卡片组件（fetch modules.json.php）
PORTAL_MODULE_GRID = '''<script setup>
import { useModuleCatalog } from './moduleCatalog.mjs'

const { modules, loading, error, load } = useModuleCatalog()
</script>

<template>
  <div class="module-grid">
    <a v-for="(m, i) in modules" :key="m.name" :href="m.link" target="_self" class="module-card">
      <span class="module-card-index" aria-hidden="true">{{ String(i + 1).padStart(2, '0') }}</span>
      <div class="module-card-title">{{ m.title }}</div>
      <div class="module-card-desc">{{ m.description }}</div>
    </a>
    <p v-if="loading" role="status">正在加载模块…</p>
    <p v-else-if="error" role="alert">模块暂时无法加载。<button type="button" @click="load">重试</button></p>
    <p v-else-if="modules.length === 0" class="module-empty">暂无模块</p>
  </div>
</template>

<style scoped>
/* 讲义卡片：左侧色条 + 右上编号 */
.module-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(min(260px, 100%), 1fr));
  gap: 18px;
  margin: 8px 0 32px;
}
.module-grid::before {
  content: '';
  grid-column: 1 / -1;
  height: 3px;
  margin-bottom: 6px;
  background: linear-gradient(90deg, var(--campus-blue) 0 52px, var(--campus-line) 52px 100%);
}
.module-card {
  position: relative;
  display: block;
  padding: 20px 20px 18px 22px;
  background: var(--campus-card-bg);
  border: 1px solid var(--vp-c-border);
  border-left: 3px solid var(--campus-blue);
  border-radius: 3px;
  text-decoration: none;
  color: inherit;
  box-shadow: 0 1px 2px rgba(31, 42, 68, 0.04);
  transition: border-color 0.2s, box-shadow 0.2s, transform 0.2s;
}
.module-card:hover {
  transform: translateY(-2px);
  border-color: var(--campus-blue);
  border-left-color: var(--campus-red);
  box-shadow: 0 10px 24px rgba(31, 42, 68, 0.12);
}
.module-card-index {
  position: absolute;
  top: 14px;
  right: 16px;
  font-family: var(--campus-serif);
  font-size: 13px;
  letter-spacing: 0.08em;
  color: var(--campus-blue);
  opacity: 0.55;
}
.module-card-title {
  font-family: var(--campus-serif);
  font-size: 18px;
  font-weight: 600;
  letter-spacing: 0.02em;
  margin-bottom: 8px;
  padding-right: 28px;
}
.module-card-desc {
  font-size: 13px;
  line-height: 1.7;
  color: var(--vp-c-text-2);
  word-break: break-all;
}
.module-empty {
  color: var(--vp-c-text-2);
}
</style>
'''

# 门户顶部动态下拉导航：fetch modules.json.php 渲染模块菜单，整页跳转避免 SPA 拦截
PORTAL_NAV = '''<script setup>
import { computed, ref } from 'vue'
import { useData, withBase } from 'vitepress'
import { useModuleCatalog } from './moduleCatalog.mjs'

defineProps({ mobile: Boolean })
const { theme } = useData()
const { modules, loading, error, load } = useModuleCatalog()
const menu = ref(null)
const frequent = computed(() => {
  const names = theme.value.portal?.frequentModules ?? ['langchain', 'redis']
  return names.map((name) => modules.value.find((item) => item.name === name)).filter(Boolean)
})

function closeMenu() {
  if (menu.value) menu.value.open = false
}

function closeOutside(event) {
  if (!event.currentTarget.contains(event.relatedTarget)) closeMenu()
}
</script>

<template>
  <nav class="portal-nav" :class="{ 'portal-nav-mobile': mobile }" aria-label="模块导航">
    <a v-for="m in frequent" :key="m.name" :href="m.link" target="_self" class="portal-nav-trigger">{{ m.title }}</a>
    <details ref="menu" class="portal-nav-item" @keydown.esc="closeMenu" @focusout="closeOutside">
      <summary class="portal-nav-trigger">全部模块 <span class="portal-nav-caret" aria-hidden="true">▾</span></summary>
      <div class="portal-nav-dropdown">
      <p v-if="loading" role="status">正在加载…</p>
      <p v-else-if="error" role="alert">加载失败 <button type="button" @click="load">重试</button></p>
      <p v-else-if="modules.length === 0">暂无模块</p>
      <a v-for="m in modules" :key="m.name"
         :href="m.link"
         target="_self"
         class="portal-nav-link"
         @click="closeMenu">
        <span class="portal-nav-link-title">{{ m.title }}</span>
        <span class="portal-nav-link-desc" v-if="m.description">{{ m.description }}</span>
      </a>
      </div>
    </details>
    <a :href="withBase('/')" target="_self" class="portal-nav-trigger portal-nav-home">首页</a>
  </nav>
</template>

<style scoped>
.portal-nav { display: flex; align-items: center; pointer-events: auto; }
.portal-nav-mobile { display: none; }
.portal-nav-trigger { cursor: pointer; list-style: none; }
.portal-nav-trigger::-webkit-details-marker { display: none; }
.portal-nav a:focus-visible, .portal-nav summary:focus-visible { outline: 2px solid var(--vp-c-brand-1); outline-offset: 2px; }
.portal-nav-item {
  position: relative;
  display: inline-block;
  list-style: none;
}
.portal-nav-trigger {
  padding: 8px 12px;
  text-decoration: none;
  color: var(--vp-c-text-1);
  font-size: inherit;
  display: inline-flex;
  align-items: center;
  gap: 3px;
  border-radius: 6px;
  transition: color 0.15s, background 0.15s;
}
.portal-nav-trigger:hover { color: var(--vp-c-brand-1); text-decoration: underline; text-decoration-thickness: 2px; text-underline-offset: 6px; }
.portal-nav-home { position: relative; }
@media (min-width: 768px) {
  .portal-nav-home { margin-left: 6px; padding-left: 18px; }
  .portal-nav-home::before {
    content: '';
    position: absolute;
    left: 4px;
    top: 50%;
    width: 1px;
    height: 14px;
    margin-top: -7px;
    background: var(--vp-c-divider);
  }
}
.portal-nav-caret { font-size: 10px; opacity: 0.55; }
.portal-nav-dropdown {
  position: absolute;
  top: calc(100% + 4px);
  right: 0;
  width: min(320px, calc(100vw - 48px));
  max-height: 60vh;
  overflow-y: auto;
  overscroll-behavior: contain;
  background: var(--campus-card-bg, var(--vp-c-bg));
  border: 1px solid var(--vp-c-border);
  border-top: 2px solid var(--vp-c-brand-1);
  border-radius: 4px;
  box-shadow: 0 12px 28px rgba(31, 42, 68, 0.14);
  padding: 6px 0;
  z-index: 3000;
  animation: portal-nav-fade 0.12s ease-out;
}
@keyframes portal-nav-fade {
  from { opacity: 0; transform: translateY(-4px); }
  to { opacity: 1; transform: translateY(0); }
}
.portal-nav-link {
  display: block;
  padding: 8px 16px;
  text-decoration: none;
  color: inherit;
  transition: background 0.12s, color 0.12s;
}
.portal-nav-link:hover {
  background: var(--vp-c-bg-soft);
  color: var(--vp-c-brand-1);
}
.portal-nav-link-title {
  display: block;
  font-weight: 500;
  font-size: 14px;
}
.portal-nav-link-desc {
  display: block;
  font-size: 12px;
  color: var(--vp-c-text-2);
  margin-top: 2px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
@media (max-width: 767px) {
  .portal-nav { display: none; }
  .portal-nav-mobile { display: flex; align-items: stretch; flex-direction: column; padding: 12px 0; }
  .portal-nav-item { display: block; }
  .portal-nav-trigger { min-height: 44px; white-space: normal; overflow-wrap: anywhere; }
  .portal-nav-dropdown { position: static; width: 100%; max-height: 45vh; box-shadow: none; }
}
</style>
'''

PORTAL_MODULE_CATALOG = '''import { inject, onMounted, ref } from 'vue'
import { withBase } from 'vitepress'

export const moduleCatalogKey = Symbol('portal-module-catalog')

export function createModuleCatalog() {
  const modules = ref([])
  const loading = ref(true)
  const error = ref(false)
  let pending
  let loaded = false

  async function load() {
    if (pending) return pending
    if (loaded) return
    loading.value = true
    error.value = false
    pending = (async () => {
      try {
        const response = await fetch(withBase('/modules.json.php'))
        if (!response.ok) throw new Error('模块清单请求失败')
        const data = await response.json()
        if (!Array.isArray(data)) throw new Error('模块清单格式错误')
        const names = new Set()
        modules.value = data.filter((item) => {
          if (!item || typeof item.name !== 'string' || typeof item.title !== 'string' || typeof item.link !== 'string') return false
          if (names.has(item.name) || !/^(?:https?:\\/\\/|\\/(?!\\/))/i.test(item.link)) return false
          names.add(item.name)
          return true
        })
        loaded = true
      } catch {
        error.value = true
      } finally {
        loading.value = false
        pending = undefined
      }
    })()
    return pending
  }

  return { modules, loading, error, load }
}

export function useModuleCatalog() {
  const catalog = inject(moduleCatalogKey)
  onMounted(catalog.load)
  return catalog
}
'''

# 门户子模块清单动态接口（PHP 实时扫描直接子目录的 site.json）
PORTAL_PHP = '''<?php
// 门户子模块清单：实时扫描直接子目录的 site.json，返回 JSON
// 由 md2website skill 生成，供门户首页 ModuleGrid 组件 fetch 使用
header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: no-store');
$base = rtrim(__DIR__, '/');
$scheme = (!empty($_SERVER['HTTPS']) && $_SERVER['HTTPS'] !== 'off') ? 'https' : 'http';
$host = isset($_SERVER['HTTP_HOST']) ? $_SERVER['HTTP_HOST'] : '';
$origin = $host ? ($scheme . '://' . $host) : '';
$prefix = rtrim(str_replace('\\\\', '/', dirname($_SERVER['SCRIPT_NAME'] ?? '/modules.json.php')), '/.');
$modules = [];
foreach (glob($base . '/*', GLOB_ONLYDIR) as $dir) {
    $name = basename($dir);
    $site = $dir . '/site.json';
    if (!is_file($site)) continue;
    $meta = json_decode((string)file_get_contents($site), true);
    if (!is_array($meta)) $meta = [];
    $modules[] = [
        'name' => $name,
        'title' => (isset($meta['title']) && $meta['title'] !== '') ? $meta['title'] : $name,
        'description' => isset($meta['description']) ? $meta['description'] : '',
        'link' => $origin . $prefix . '/' . rawurlencode($name) . '/',
    ];
}
usort($modules, function ($a, $b) { return strcmp($a['name'], $b['name']); });
echo json_encode($modules, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
'''

CUSTOM_CSS = '''/* ============ 科技感主题（深/浅双主题） ============ */

:root {
  --vp-c-brand-1: #6d5ef0;
  --vp-c-brand-2: #7c5cff;
  --vp-c-brand-3: #4f46e5;
  --vp-c-brand-soft: rgba(109, 94, 240, 0.14);
  --tech-cyan: #0891b2;
  --tech-gradient: linear-gradient(120deg, #0891b2 0%, #6d5ef0 55%, #a855f7 100%);
  --tech-glow-1: rgba(14, 165, 233, 0.09);
  --tech-glow-2: rgba(168, 85, 247, 0.07);
  --tech-grid: rgba(99, 102, 241, 0.05);
  /* 布局宽度：侧边栏 320；整站上限按视口分档，避免视口小于上限时左侧内容被侧边栏压住 */
  --vp-sidebar-width: 320px;
  --vp-layout-max-width: 1440px;
}

@media (min-width: 1560px) {
  :root { --vp-layout-max-width: 1560px; }
}

@media (min-width: 1660px) {
  :root { --vp-layout-max-width: 1640px; }
}

/* 正文阅读宽度（默认 688，默认主题里为 scoped 样式，需 !important 覆盖） */
.VPDoc.has-aside .content-container {
  max-width: 860px !important;
}

/* 右侧「本页目录」加宽（默认内容区 224 / 外层 256；宽屏才生效，避免挤压正文） */
@media (min-width: 1660px) {
  .VPDoc .aside {
    max-width: 312px;
  }
  .VPDoc .aside .aside-container,
  .VPDoc .aside .aside-curtain {
    width: 280px;
  }
}

.dark {
  --vp-c-brand-1: #22d3ee;
  --vp-c-brand-2: #38bdf8;
  --vp-c-brand-3: #7c5cff;
  --vp-c-brand-soft: rgba(34, 211, 238, 0.16);
  --tech-cyan: #22d3ee;
  --tech-gradient: linear-gradient(120deg, #22d3ee 0%, #6366f1 55%, #a855f7 100%);
  --tech-glow-1: rgba(34, 211, 238, 0.13);
  --tech-glow-2: rgba(168, 85, 247, 0.11);
  --tech-grid: rgba(148, 163, 184, 0.06);
}

/* 科技感背景：网格 + 光晕 */
body {
  background-color: var(--vp-c-bg);
  background-image:
    radial-gradient(ellipse 80% 60% at 18% -10%, var(--tech-glow-1), transparent 60%),
    radial-gradient(ellipse 70% 50% at 92% 110%, var(--tech-glow-2), transparent 60%),
    linear-gradient(var(--tech-grid) 1px, transparent 1px),
    linear-gradient(90deg, var(--tech-grid) 1px, transparent 1px);
  background-size: 100% 100%, 100% 100%, 44px 44px, 44px 44px;
  background-attachment: fixed;
}

/* 首页 Hero：渐变标题 + 发光按钮 */
.VPHero .name {
  background: var(--tech-gradient);
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
}
.VPButton.brand {
  background-image: var(--tech-gradient);
  border: none;
  box-shadow: 0 6px 24px rgba(99, 102, 241, 0.4);
  transition: box-shadow 0.25s, transform 0.25s;
}
.VPButton.brand:hover {
  box-shadow: 0 10px 32px rgba(99, 102, 241, 0.6);
  transform: translateY(-2px);
}

/* 导航栏科技光边 */
.VPNavBar {
  border-bottom: 1px solid var(--vp-c-brand-soft);
  box-shadow: 0 1px 14px rgba(99, 102, 241, 0.10);
}

/* 文档标题渐变 */
.vp-doc h1, .vp-doc h2 {
  background: var(--tech-gradient);
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
}

/* 链接：渐变下划线 + 换行 */
.vp-doc a {
  color: var(--vp-c-brand-1);
  word-break: break-all;
  background-image: linear-gradient(currentColor, currentColor);
  background-position: 0 100%;
  background-size: 0 1px;
  background-repeat: no-repeat;
  transition: background-size 0.25s;
}
.vp-doc a:hover { background-size: 100% 1px; }

/* 代码块科技边框 */
.vp-doc div[class*='language-'] {
  border: 1px solid var(--vp-c-brand-soft);
  border-radius: 10px;
  box-shadow: 0 4px 24px rgba(99, 102, 241, 0.08);
  overflow-x: auto;
}

/* 表格表头 */
.vp-doc th { background: var(--vp-c-brand-soft); }

/* 引用块 */
.vp-doc blockquote {
  border-left: 3px solid var(--vp-c-brand-1);
  background: var(--vp-c-brand-soft);
  border-radius: 0 8px 8px 0;
}

/* Features 卡片 */
.VPFeature {
  border: 1px solid var(--vp-c-brand-soft);
  border-radius: 12px;
  transition: box-shadow 0.25s, transform 0.25s;
}
.VPFeature:hover {
  box-shadow: 0 8px 30px rgba(99, 102, 241, 0.18);
  transform: translateY(-3px);
}

/* 滚动条 */
::-webkit-scrollbar { width: 8px; height: 8px; }
::-webkit-scrollbar-thumb {
  background: linear-gradient(var(--tech-cyan), var(--vp-c-brand-3));
  border-radius: 4px;
}

/* ============ 图片点击放大 ============ */
.vp-doc img {
  border-radius: 8px;
  cursor: zoom-in;
}
.vp-doc img.zoomable:hover {
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.18);
}
.img-zoom-mask {
  position: fixed;
  inset: 0;
  z-index: 9999;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 4vh 4vw;
  background: rgba(0, 0, 0, 0.82);
  cursor: zoom-out;
  opacity: 0;
  transition: opacity 0.18s ease;
}
.img-zoom-mask.open { opacity: 1; }
.img-zoom-mask img {
  max-width: 100%;
  max-height: 92vh;
  border-radius: 8px;
  box-shadow: 0 8px 40px rgba(0, 0, 0, 0.5);
  transform: scale(0.96);
  transition: transform 0.18s ease;
}
.img-zoom-mask.open img { transform: scale(1); }
'''

PORTAL_CSS = '''
/* ============ 校园风格：学院蓝 + 讲义纸 ============ */
:root {
  --campus-blue: #1f3a68;
  --campus-blue-soft: rgba(31, 58, 104, 0.08);
  --campus-red: #a63a2f;
  --campus-paper: #fbf8f1;
  --campus-card-bg: #fffdf8;
  --campus-line: rgba(31, 58, 104, 0.16);
  --campus-serif: 'Noto Serif SC', 'Songti SC', 'STSong', 'SimSun', Georgia, serif;
  --vp-c-brand-1: #1f3a68;
  --vp-c-brand-2: #2c4f86;
  --vp-c-brand-3: #16294a;
  --vp-c-brand-soft: rgba(31, 58, 104, 0.12);
  --vp-c-bg: #fbf8f1;
  --vp-c-bg-alt: #f4efe4;
  --vp-c-bg-soft: #f4efe4;
  --vp-c-bg-elv: #fffdf8;
  --vp-c-divider: rgba(31, 58, 104, 0.14);
  --vp-c-border: rgba(31, 58, 104, 0.18);
  --vp-c-gutter: rgba(31, 58, 104, 0.12);
  --vp-font-family-base: 'Noto Sans SC', 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', system-ui, sans-serif;
  --vp-nav-bg-color: rgba(251, 248, 241, 0.92);
  --vp-sidebar-bg-color: #f7f2e7;
  --vp-code-block-bg: #f4efe4;
}
.dark {
  --campus-blue: #9db8e0;
  --campus-blue-soft: rgba(157, 184, 224, 0.12);
  --campus-red: #d98a7c;
  --campus-paper: #14181f;
  --campus-card-bg: #1a1f28;
  --campus-line: rgba(157, 184, 224, 0.2);
  --vp-c-brand-1: #9db8e0;
  --vp-c-brand-2: #b6cbe8;
  --vp-c-brand-3: #7d9bc9;
  --vp-c-brand-soft: rgba(157, 184, 224, 0.14);
  --vp-c-bg: #14181f;
  --vp-c-bg-alt: #10141a;
  --vp-c-bg-soft: #1a1f28;
  --vp-c-bg-elv: #1a1f28;
  --vp-c-divider: rgba(157, 184, 224, 0.16);
  --vp-c-border: rgba(157, 184, 224, 0.2);
  --vp-c-gutter: rgba(157, 184, 224, 0.14);
  --vp-nav-bg-color: rgba(20, 24, 31, 0.92);
  --vp-sidebar-bg-color: #10141a;
  --vp-code-block-bg: #10141a;
}

/* 讲义纸：横线稿纸 + 左侧装订线 */
body {
  background-color: var(--campus-paper);
  background-image:
    linear-gradient(90deg, transparent 0 63px, var(--campus-line) 63px 64px, transparent 64px),
    linear-gradient(var(--campus-line) 1px, transparent 1px);
  background-size: 100% 100%, 100% 32px;
  background-attachment: fixed;
}
@media (max-width: 767px) {
  body { background-image: linear-gradient(var(--campus-line) 1px, transparent 1px); }
}

/* 顶部导航：纸面 + 细线 */
.VPNavBar { box-shadow: none; border-bottom: 1px solid var(--vp-c-divider); }
.VPNavBar .VPNavBarTitle .title { font-family: var(--campus-serif); letter-spacing: 0.04em; }
.VPNavBar .VPNavBarMenuLink { font-size: 14px; }

/* 首页 Hero：衬线标题 + 校刊式副标题 */
.VPHome { position: relative; }
.VPHome .VPHero { padding-top: 88px; padding-bottom: 28px; }
.VPHome .VPHero .name,
.VPHome .VPHero .text {
  font-family: var(--campus-serif);
  font-size: 46px;
  line-height: 1.25;
  letter-spacing: 0.04em;
  background: none;
  -webkit-text-fill-color: currentColor;
  color: var(--campus-blue);
}
.VPHome .VPHero .tagline {
  font-size: 16px;
  letter-spacing: 0.06em;
  color: var(--vp-c-text-2);
  max-width: 640px;
}
.VPHome .VPHero .tagline::after {
  content: '';
  display: block;
  width: 56px;
  height: 3px;
  margin-top: 18px;
  background: var(--campus-red);
}
.VPHome .vp-doc { background: transparent; }
.VPHome .vp-doc h2 {
  font-family: var(--campus-serif);
  background: none;
  -webkit-text-fill-color: currentColor;
  color: var(--campus-blue);
}

/* 正文：衬线标题、讲义式引用与表格 */
.vp-doc h1, .vp-doc h2, .vp-doc h3 {
  font-family: var(--campus-serif);
  background: none;
  -webkit-text-fill-color: currentColor;
  color: var(--campus-blue);
  letter-spacing: 0.02em;
}
.vp-doc h2 { border-top: 1px solid var(--vp-c-divider); padding-top: 20px; }
.vp-doc blockquote {
  border-left: 3px solid var(--campus-red);
  background: var(--campus-blue-soft);
  border-radius: 0;
}
.vp-doc th { background: var(--campus-blue-soft); }
.vp-doc div[class*='language-'] {
  border: 1px solid var(--vp-c-divider);
  border-radius: 4px;
  box-shadow: none;
}
.VPFeature {
  border: 1px solid var(--vp-c-border);
  border-left: 3px solid var(--campus-blue);
  border-radius: 3px;
  background: var(--campus-card-bg);
}
.VPFeature:hover { box-shadow: 0 10px 24px rgba(31, 42, 68, 0.12); transform: translateY(-2px); }
.VPButton.brand {
  background-image: none;
  background-color: var(--campus-blue);
  border-radius: 3px;
  box-shadow: none;
}
.VPButton.brand:hover { background-color: var(--vp-c-brand-2); box-shadow: none; }
::-webkit-scrollbar-thumb { background: var(--campus-blue); border-radius: 4px; }

/* 顶部顺序：模块 → 全部模块 → 首页 → 主题切换（主题按钮排到导航之后） */
@media (min-width: 768px) {
  .VPNavBar .content-body > .appearance { order: 1; }
  .VPNavBar .content-body > .portal-nav { order: 0; }
  .VPNavBar .content-body > .appearance::before { display: none; }
}

@media (max-width: 767px) {
  .VPHome .VPHero { padding-top: 48px; }
  .VPHome .VPHero .name,
  .VPHome .VPHero .text { font-size: 30px; }
}
'''

HOME_TMPL = '''---
layout: home

hero:
  name: @@TITLE@@
  text: @@SUBTITLE@@
  tagline: @@TAGLINE@@
  actions:
    - theme: brand
      text: 开始阅读
      link: /@@FIRST@@/
    - theme: alt
      text: 文档首页
      link: /@@FIRST@@/

features:
@@FEATURES@@
---

## 文档说明

本站在 Markdown 源文档基础上构建，支持左侧章节导航、页面内目录、全文搜索、代码复制、深浅色主题与图片放大。

- 源文档保持只读，本目录为构建副本
- 修改内容后执行 `./deploy.sh` 即可重新构建并部署
'''

# 门户站点：首页通过 ModuleGrid 组件动态加载子模块（fetch modules.json.php）
PORTAL_CONFIG_TMPL = '''import { defineConfig } from 'vitepress'

const base = `${(process.env.VP_BASE || '@@BASE@@').replace(/\\/+$/, '')}/`

export default defineConfig({
  lang: 'zh-CN',
  title: '@@TITLE@@',
  description: '@@DESC@@',
  head: [
    ['link', { rel: 'icon', href: `${base}favicon.svg` }]
  ],
  base,
  cleanUrls: true,

  markdown: {
    lineNumbers: true,
    theme: { light: 'github-light', dark: 'github-dark' },
    config(md) {
      md.core.ruler.after('inline', 'escape_vue_syntax', (state) => {
        for (const token of state.tokens) {
          if (token.type !== 'inline' || !token.children) continue
          for (const child of token.children) {
            if (child.type === 'html_inline') {
              const raw = child.content
              if (/^<(?:https?:\\/\\/|mailto:|ftp:\\/\\/)/i.test(raw) && raw.length > 2) {
                const inner = raw.slice(1, -1)
                child.type = 'link'
                child.tag = 'a'
                child.attrs = [['href', inner]]
                child.markup = 'autolink'
                child.content = ''
                child.children = [{ type: 'text', content: inner, level: 0 }]
              } else if (/^<[A-Za-z][\\w.\\-]*(?::[\\w.\\-]+)?>/.test(raw)) {
                child.type = 'text'
                child.markup = ''
              }
            } else if (child.type === 'text' && child.content.includes('{')) {
              child.content = child.content
                .replace(/\\{\\{/g, '&#123;&#123;')
                .replace(/\\}\\}/g, '&#125;&#125;')
            }
          }
        }
      })
    }
  },

  themeConfig: {
    outline: { level: [2, 3], label: '本页章节' },
    nav: [],
    portal: { frequentModules: ['langchain', 'redis'] },
    sidebar: [],
    search: {
      provider: 'local',
      options: {
        translations: {
          button: { buttonText: '搜索', buttonAriaLabel: '搜索文档' },
          modal: {
            noResultsText: '没有找到结果',
            resetButtonTitle: '清除',
            footer: { selectText: '选择', navigateText: '切换', closeText: '关闭' }
          }
        }
      }
    },
    docFooter: { prev: '上一篇', next: '下一篇' },
    outlineTitle: '本页章节',
    returnToTopLabel: '回到顶部',
    sidebarMenuLabel: '目录',
    darkModeSwitchLabel: '主题',
    lastUpdated: { text: '最后更新' }
  }
})
'''

# 门户首页：模块卡片由 ModuleGrid 组件动态加载（fetch modules.json.php）
PORTAL_HOME_TMPL = '''---
layout: home

hero:
  text: @@SUBTITLE@@
  tagline: @@TAGLINE@@
---

<ModuleGrid />
'''

PACKAGE_JSON = '''{
  "name": "@@NAME@@",
  "version": "1.0.0",
  "private": true,
  "scripts": {
    "dev": "vitepress dev docs --host 127.0.0.1 --port 5174",
    "build": "vitepress build docs",
    "preview": "vitepress preview docs --host 127.0.0.1 --port 4173",
    "deploy": "./deploy.sh"
  },
  "devDependencies": {
    "vitepress": "^1.6.4"
  }
}
'''

GITIGNORE = '''# 部署配置（含服务器敏感信息，勿提交）
.deploy-local.yml
.deploy-profile
deploy.conf

# 依赖
node_modules/

# 构建产物
docs/.vitepress/dist/
docs/.vitepress/cache/

# 更新前的配置备份
.backup/
'''

DEPLOY_README = '''# 部署配置说明

服务器信息只保存在本站点目录的 `.deploy-local.yml`（权限 600，已被 `.gitignore` 忽略），
不会提交到仓库，也不会随站点上传到服务器。

## 首次配置

生成站点时如果选择了配置服务器，`.deploy-local.yml` 已经存在；否则在站点目录执行：

    python3 ~/.workbuddy/skills/md2website/scripts/profile.py wizard --project "$(pwd)"

也可以直接执行 `./deploy.sh`，未找到配置时会自动进入同一个向导。

向导没有预置默认值：主机、登录账号、SSH 端口、远程目录、站点根路径都需要手动填写；
密码与 SSH 私钥至少填写一项。

## 查看当前配置

    python3 ~/.workbuddy/skills/md2website/scripts/profile.py show
    ./deploy.sh --dry-run

## 字段说明

| 字段 | 是否必填 | 说明 |
| --- | --- | --- |
| HOST | 必填 | 服务器域名或 IP，不要带协议、端口或路径 |
| USER | 必填 | 登录账号，建议使用只对远程目录有写权限的账号 |
| PORT | 必填 | SSH 端口，无默认值，例如 22 |
| REMOTE_DIR | 必填 | 远程部署目录，绝对路径，必须是站点专属目录 |
| SSH_KEY | 密码与私钥二选一 | 私钥路径，支持 `$HOME`；密码登录时留空 |
| PASSWORD | 密码与私钥二选一 | 登录密码；私钥登录时留空 |
| SITE_BASE | 必填 | 站点根路径，例如 `/` 或 `/docs/`，无默认值 |
| CLEAN_MODE | 可选 | 清理方式：manifest 只清上次部署的文件；all 清空目录（保留 .user.ini）；none 不清理 |
| BUILD_BEFORE_DEPLOY | 可选 | 部署前是否构建 |
| REMOTE_TMP | 可选 | 远程临时目录 |
| DIST_NAME | 可选 | 产物文件夹名（上传时） |
| UPLOAD_WITH_DIR | 可选 | 是否带文件夹一起上传 true / false |

## 多站点共用配置（可选）

默认每个站点独立配置。确实需要多个站点共用同一台服务器时，才显式创建并绑定配置档：

    python3 ~/.workbuddy/skills/md2website/scripts/profile.py set --name my-server \\
        HOST="doc.example.com" PORT="22" USER="deploy" \\
        REMOTE_DIR="/www/wwwroot/doc.example.com" SITE_BASE="/"
    python3 ~/.workbuddy/skills/md2website/scripts/profile.py bind --project "$(pwd)" --name my-server

## 安全边界

- 部署只写 `REMOTE_DIR` 与远程临时包，不执行 sudo、不重启服务、不修改 nginx 配置
- `REMOTE_DIR` 必须是站点专属目录，不能填 `/www/wwwroot`、`/var/www` 等多站点容器目录
- `manifest` 清单只记录本工具上传的文件，目录里其他程序的已有文件不会被删除
- 建议使用只对 `REMOTE_DIR` 有写权限的部署账号，而不是 root

## 部署后检查（nginx cleanUrls）

站点默认 `cleanUrls: true`，子页面 URL 不带 `.html`。宝塔 nginx 默认无 `try_files` 规则，
部署后请验证侧边栏子页面是否 404。若 404，在站点 nginx 配置的 server 块加：

    location / {
        try_files $uri $uri/ $uri.html /index.html;
    }

然后 `nginx -s reload`。
'''



def render(tmpl, values):
    """占位符 @@KEY@@ 替换，避免与 JS 的花括号冲突"""
    out = tmpl
    for k, v in values.items():
        out = out.replace(f'@@{k}@@', str(v))
    return out


def write(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)


def copy_chapter(src_dir, dst_dir):
    """复制目录下所有 md 与图片，保持相对结构（每个子目录的主文档改为 index.md）"""
    os.makedirs(dst_dir, exist_ok=True)
    count = {'md': 0, 'img': 0}

    for dirpath, dirnames, filenames in os.walk(src_dir):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith('.')]
        relp = os.path.relpath(dirpath, src_dir)
        target_dir = dst_dir if relp == '.' else os.path.join(dst_dir, relp)
        os.makedirs(target_dir, exist_ok=True)
        main_md = pick_main_md(dirpath)
        main_src = os.path.join(dirpath, main_md) if main_md else None

        for fn in filenames:
            if fn in SKIP_FILES:
                continue
            src = os.path.join(dirpath, fn)
            ext = os.path.splitext(fn)[1].lower()
            if ext in ('.md', '.markdown'):
                # 主文档改名为 index.md，其余保留原名
                out_name = 'index.md' if (src == main_src) else fn
                shutil.copy2(src, os.path.join(target_dir, out_name))
                count['md'] += 1
            elif ext in IMG_EXTS:
                shutil.copy2(src, os.path.join(target_dir, fn))
                count['img'] += 1
    return count


def gen_portal(args):
    """生成门户站点骨架：顶部导航/首页由 modules.json 驱动，聚合子模块入口。"""
    out = os.path.abspath(args.out or os.path.join(os.getcwd(), 'outputs', 'md2website-portal'))
    if os.path.exists(out):
        if not args.force:
            print(f'输出目录已存在，拒绝覆盖: {out}\n'
                  f'如需重建请加 --force，或指定其他 --out', file=sys.stderr)
            return 1
        for item in GENERATED_ITEMS:
            p = os.path.join(out, item)
            if os.path.isdir(p):
                shutil.rmtree(p)
            elif os.path.exists(p):
                os.remove(p)
        print('已清理旧生成物（保留 .deploy-local.yml 与 node_modules）')

    title = args.title or '文档门户'
    site_name = args.name or to_ascii_slug(title, fallback='portal')
    base = args.base if args.base.endswith('/') else args.base + '/'

    docs = os.path.join(out, 'docs')
    vp = os.path.join(docs, '.vitepress')
    os.makedirs(vp, exist_ok=True)

    print(f'生成门户站点: {title}')
    print(f'输出:   {out}\n')

    # 动态子模块清单接口（PHP 实时扫描直接子目录）+ 首页动态卡片组件 + favicon
    write(os.path.join(docs, 'public', 'modules.json.php'), PORTAL_PHP)
    write(os.path.join(docs, 'public', 'favicon.svg'), make_favicon_svg(title))
    write(os.path.join(vp, 'config.mjs'), render(PORTAL_CONFIG_TMPL, {
        'TITLE': title,
        'DESC': args.subtitle or title,
        'BASE': base,
    }))
    write(os.path.join(vp, 'theme', 'index.mjs'), PORTAL_THEME_INDEX)
    write(os.path.join(vp, 'theme', 'ModuleGrid.vue'), PORTAL_MODULE_GRID)
    write(os.path.join(vp, 'theme', 'PortalNav.vue'), PORTAL_NAV)
    write(os.path.join(vp, 'theme', 'moduleCatalog.mjs'), PORTAL_MODULE_CATALOG)
    write(os.path.join(vp, 'theme', 'custom.css'), CUSTOM_CSS + PORTAL_CSS)

    write(os.path.join(docs, 'index.md'), render(PORTAL_HOME_TMPL, {
        'TITLE': title,
        'SUBTITLE': args.subtitle or '',
        'TAGLINE': '按模块整理，随时查阅。',
    }))
    write(os.path.join(out, 'package.json'), render(PACKAGE_JSON, {'NAME': site_name}))
    write(os.path.join(out, '.gitignore'), GITIGNORE)
    default_profile = re.sub(r'[^A-Za-z0-9._-]+', '-', os.path.basename(out).lower()).strip('-') or 'default'
    write(os.path.join(out, 'DEPLOY.md'), render(DEPLOY_README, {'NAME': default_profile}))

    skill_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    deploy_src = os.path.join(skill_dir, 'assets', 'deploy.sh')
    if os.path.isfile(deploy_src):
        shutil.copy2(deploy_src, os.path.join(out, 'deploy.sh'))
        os.chmod(os.path.join(out, 'deploy.sh'), 0o755)

    write_meta(out, '', title, site_name, base, role='portal')
    print(f'门户站点生成完成：{out}')
    print('下一步：')
    print(f'  cd {out}')
    print('  python3 <skill>/scripts/profile.py wizard --project .   # 配置服务器部署信息')
    print('  npm install && npm run dev                              # 本地预览')
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('source', nargs='?', default=None,
                    help='Markdown 源目录（--portal 模式可省略）')
    ap.add_argument('--out', default=None)
    ap.add_argument('--title', default=None)
    ap.add_argument('--subtitle', default=None)
    ap.add_argument('--name', default=None)
    ap.add_argument('--base', default='/')
    ap.add_argument('--portal', action='store_true',
                    help='生成门户站点（聚合子模块入口，无需源目录）')
    ap.add_argument('--force', action='store_true',
                    help='原地重建：清理旧生成物后重新生成，保留部署配置与依赖')
    args = ap.parse_args()

    if args.portal:
        return gen_portal(args)

    if not args.source:
        ap.error('缺少 Markdown 源目录（或用 --portal 生成门户）')

    src = os.path.abspath(args.source)
    if not os.path.isdir(src):
        print(f'源目录不存在: {src}', file=sys.stderr)
        return 1

    out = os.path.abspath(args.out or os.path.join(os.getcwd(), 'outputs', 'md2website-site'))
    if os.path.exists(out):
        if not args.force:
            print(f'输出目录已存在，拒绝覆盖: {out}\n'
                  f'如需重建请加 --force，或指定其他 --out', file=sys.stderr)
            return 1
        for item in GENERATED_ITEMS:
            p = os.path.join(out, item)
            if os.path.isdir(p):
                shutil.rmtree(p)
            elif os.path.exists(p):
                os.remove(p)
        print('已清理旧生成物（保留 .deploy-local.yml 与 node_modules）')

    title = args.title or os.path.basename(src)
    site_name = args.name or to_ascii_slug(title)
    base = args.base if args.base.endswith('/') else args.base + '/'

    chapters, root_mds = find_md_dirs(src)
    if not chapters and not root_mds:
        print(f'在 {src} 下没有找到任何 Markdown 文件', file=sys.stderr)
        return 1

    docs = os.path.join(out, 'docs')
    os.makedirs(docs, exist_ok=True)

    print(f'源目录: {src}')
    print(f'输出:   {out}')
    print(f'发现 {len(chapters)} 个章节目录，{len(root_mds)} 个根级 Markdown\n')

    # ---- 逐章复制 ----
    used_slugs = set()
    nav_entries = []
    feature_items = []
    total = {'md': 0, 'img': 0}
    md_map = {}

    for idx, name in enumerate(chapters, 1):
        src_dir = os.path.join(src, name)
        slug = slugify(name, used_slugs)
        cnt = copy_chapter(src_dir, os.path.join(docs, slug))
        total['md'] += cnt['md']
        total['img'] += cnt['img']
        md_map.update(build_md_map(src_dir, slug))
        num = f'{idx:02d}'

        tree = build_dir_tree(src_dir, slug)
        if len(tree) == 1 and 'items' not in tree[0]:
            # 单文档章节
            heading = tree[0]['text']
            nav_entries.append({"type": "single", "text": heading, "link": tree[0]['link']})
            feature_items.append(
                f'  - title: {json.dumps(num + " " + heading, ensure_ascii=False)}\n'
                f'    details: {json.dumps("共 " + str(cnt["md"]) + " 篇文档", ensure_ascii=False)}\n'
                f'    link: /{slug}/'
            )
            print(f'  ✓ {num} {heading}  → /{slug}/  '
                  f'(md {cnt["md"]}, img {cnt["img"]})')
        else:
            # 多文档 或 含子目录：可折叠分组，标题用目录名
            nav_entries.append({"type": "group", "text": name, "items": tree})
            feature_items.append(
                f'  - title: {json.dumps(num + " " + name, ensure_ascii=False)}\n'
                f'    details: {json.dumps("共 " + str(cnt["md"]) + " 篇文档", ensure_ascii=False)}\n'
                f'    link: /{slug}/'
            )
            print(f'  ✓ {num} {name}（{len(tree)} 项）→ /{slug}/')

    # ---- 根级散装 Markdown ----
    for fn in root_mds:
        stem = os.path.splitext(fn)[0]
        if stem.lower() in ('readme', 'index'):
            continue
        slug = slugify(stem, used_slugs)
        md_map[fn] = f"/{slug}"
        target = os.path.join(docs, slug + '.md')
        shutil.copy2(os.path.join(src, fn), target)
        heading, _ = dir_title(src)
        try:
            for line in open(target, encoding='utf-8', errors='replace'):
                m = re.match(r'^#\s+(.+?)\s*$', line)
                if m:
                    heading = m.group(1).strip()
                    break
        except OSError:
            pass
        nav_entries.append({"type": "single", "text": heading, "link": f"/{slug}"})
        total['md'] += 1
        print(f'  ✓ {heading}  → /{slug}')

    if not nav_entries:
        print('没有可用的文档条目', file=sys.stderr)
        return 1

    first = nav_entries[0]
    first_link = (first["items"][0]["link"] if first["type"] == "group"
                  else first["link"]).strip('/')

    # ---- 生成配置 ----
    chapter_items = ',\n'.join(
        json.dumps(e, ensure_ascii=False) for e in nav_entries
    )
    write(os.path.join(docs, '.vitepress', 'config.mjs'), render(CONFIG_TMPL, {
        'CHAPTER_ITEMS': chapter_items,
        'TITLE': title,
        'DESC': args.subtitle or title,
        'BASE': base,
        'FIRST': first_link,
    }))
    write(os.path.join(docs, '.vitepress', 'theme', 'index.mjs'), THEME_INDEX)
    write(os.path.join(docs, '.vitepress', 'theme', 'custom.css'), CUSTOM_CSS)
    write(os.path.join(docs, 'public', 'favicon.svg'), make_favicon_svg(title))
    features = '\n'.join(feature_items) if feature_items else (
        f'  - title: 开始阅读\n    details: 打开第一篇文档\n    link: /{first_link}/')
    write(os.path.join(docs, 'index.md'), render(HOME_TMPL, {
        'TITLE': title,
        'SUBTITLE': args.subtitle or '文档站',
        'TAGLINE': f'共 {len(nav_entries)} 个章节',
        'FIRST': first_link,
        'FEATURES': features,
    }))
    write(os.path.join(out, 'package.json'), render(PACKAGE_JSON, {
        'NAME': site_name,
    }))
    write(os.path.join(out, '.gitignore'), GITIGNORE)
    default_profile = re.sub(r'[^A-Za-z0-9._-]+', '-',
                             os.path.basename(out).lower()).strip('-') or 'default'
    write(os.path.join(out, 'DEPLOY.md'), render(DEPLOY_README, {'NAME': default_profile}))

    # 复用本 skill 的部署脚本与说明
    skill_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    deploy_src = os.path.join(skill_dir, 'assets', 'deploy.sh')
    if os.path.isfile(deploy_src):
        shutil.copy2(deploy_src, os.path.join(out, 'deploy.sh'))
        os.chmod(os.path.join(out, 'deploy.sh'), 0o755)

    # 记录源目录与站点信息，供 sites.py / update.py 后续更新
    write_meta(out, src, title, site_name, base)

    # 自动执行一次语法修复，避免用户首次构建就失败
    fixed = 0
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import fix as fixer
        for dirpath, dirnames, filenames in os.walk(docs):
            dirnames[:] = [d for d in dirnames if d not in {'.vitepress', 'node_modules'}]
            for fn in filenames:
                if fn.lower().endswith(('.md', '.markdown')):
                    fixed += len(fixer.fix_file(os.path.join(dirpath, fn), dry=False))
    except Exception as e:
        print(f'  ! 自动修复跳过（{e}），可手动运行 fix.py')

    # 修复跨章节死链：把指向源 .md 文件的链接改写为站点 URL
    dead_fixed = fix_dead_links(docs, md_map)

    summary = f'\n完成：{total["md"]} 篇 Markdown、{total["img"]} 张图片'
    if fixed:
        summary += f'，自动修复 {fixed} 处语法冲突'
    if dead_fixed:
        summary += f'，改写死链 {dead_fixed} 处'
    print(summary)

    # 环境检测：给出与当前机器匹配的后续指引
    try:
        import _env
        ok_node, node, ver, err = _env.check_node()
    except Exception:
        ok_node, ver, err = True, None, None

    if not ok_node:
        print('\n⚠ 未检测到可用的 Node.js 18+（构建必需）：')
        print(_env.node_install_hint())
        print(f'\n项目已生成：{out}')
        print('安装 Node.js 后再执行：cd 项目目录 && npm install && npm run dev')
        return 0

    print(f'\nNode {ver} 可用。下一步：')
    print(f'  cd {out}')
    print('  npm install        # 首次安装依赖，约 1-3 分钟')
    print('  npm run dev        # 本地预览 http://127.0.0.1:5174')
    print(f'\n部署前先看 DEPLOY.md 完成服务器配置。')
    return 0


if __name__ == '__main__':
    sys.exit(main())
