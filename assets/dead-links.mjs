import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { spawnSync } from 'node:child_process'
import { parse, parseFragment } from 'parse5'

const here = path.dirname(fileURLToPath(import.meta.url))
const dist = path.join(here, 'dist')
const manifest = path.join(here, 'cache', 'dead-links.json')

function walk(node, visit) {
  visit(node)
  for (const child of node.childNodes || []) walk(child, visit)
}

function decode(value) {
  try { return decodeURIComponent(value) } catch { return value }
}

function target(href, page, siteBase) {
  // Never probe network URLs (including LAN services), schemes or sibling sites.
  if (!href || /^(?:[a-z][\w+.-]*:|\/\/)/i.test(href)) return null
  const url = new URL(href, 'https://md2website.invalid' + siteBase + page)
  if (!url.pathname.startsWith(siteBase)) return null
  const name = decode(url.pathname.slice(siteBase.length))
  if (/\.[^/]+$/.test(name) && !/\.(?:html|md)$/i.test(name)) return null
  return { name: name.replace(/\.md$/i, '.html'), anchor: decode(url.hash.slice(1)) }
}

function pageFor(pages, name) {
  return [name, name + '.html', name.replace(/\/$/, '') + '/index.html',
    name === '' ? 'index.html' : null].find(candidate => candidate && Object.hasOwn(pages, candidate))
}

export function markDeadLinks(md, siteBase) {
  if (process.env.MD2WEBSITE_LINK_PASS !== 'mark') return
  const pages = JSON.parse(fs.readFileSync(manifest, 'utf8'))
  const render = md.renderer.render.bind(md.renderer)
  const reported = new Set()
  md.renderer.render = (tokens, options, env) => {
    const html = render(tokens, options, env)
    const relative = env.relativePath || (env.path ? path.relative(path.dirname(here), env.path) : '')
    if (!relative) return html
    const page = relative.replace(/\\/g, '/').replace(/\.md$/, '.html')
    const replacements = []
    walk(parseFragment(html, { sourceCodeLocationInfo: true }), element => {
        if (element.tagName !== 'a' || !element.sourceCodeLocation?.endTag) return
        const href = element.attrs.find(attr => attr.name === 'href')?.value
        const resolved = target(href, page, siteBase)
        if (!resolved) return
        const found = pageFor(pages, resolved.name)
        if (found && (!resolved.anchor || pages[found].includes(resolved.anchor))) return
        const key = page + '\0' + href
        if (!reported.has(key)) {
          reported.add(key)
          console.warn(`[失效链接] ${relative} -> ${href}`)
        }
        const loc = element.sourceCodeLocation
        const text = html.slice(loc.startTag.endOffset, loc.endTag.startOffset)
        const replacement = `<span class="md2website-dead-link" aria-disabled="true" data-original-href="${md.utils.escapeHtml(href)}" title="失效链接：${md.utils.escapeHtml(href)}">${text}<span class="md2website-dead-link-label">（链接已失效）</span></span>`
        replacements.push({ start: loc.startOffset, end: loc.endOffset, replacement })
      })
    let output = html
    for (const item of replacements.sort((a, b) => b.start - a.start)) {
      output = output.slice(0, item.start) + item.replacement + output.slice(item.end)
    }
    return output
  }
}

function collect() {
  const pages = {}
  let marked = 0
  function scan(dir) {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const file = path.join(dir, entry.name)
      if (entry.isDirectory()) scan(file)
      else if (entry.name.endsWith('.html')) {
        const page = path.relative(dist, file).split(path.sep).join('/')
        const ids = pages[page] = []
        walk(parse(fs.readFileSync(file, 'utf8')), node => {
          const attrs = Object.fromEntries((node.attrs || []).map(attr => [attr.name, attr.value]))
          if (attrs.id) ids.push(attrs.id)
          if (node.tagName === 'a' && attrs.name) ids.push(attrs.name)
          if (attrs.class?.split(/\s+/).includes('md2website-dead-link')) marked++
        })
      }
    }
  }
  scan(dist)
  return { pages, marked }
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const cli = path.resolve(here, '../../node_modules/vitepress/bin/vitepress.js')
  function build(pass) {
    const result = spawnSync(process.execPath, [cli, 'build', 'docs'], {
      cwd: path.resolve(here, '../..'), stdio: 'inherit',
      env: { ...process.env, MD2WEBSITE_LINK_PASS: pass }
    })
    if (result.error) throw result.error
    if (result.status !== 0) process.exit(result.status || 1)
  }
  build('collect')
  const { pages } = collect()
  fs.mkdirSync(path.dirname(manifest), { recursive: true })
  fs.writeFileSync(manifest, JSON.stringify(pages))
  build('mark')
  console.info(`[md2website] 失效链接总数：${collect().marked}（按页面出现次数）`)
}
