import { describe, expect, it } from 'vitest'

// Link text uses the link orange (`--crm-link`), which reads on white; the brand orange
// (`--crm-teal` / `--crm-brand` / `--crm-logo-orange`) is for fills, borders and badges. Two
// oranges on links looked like two kinds of link.
//
// What this guard sees: rules in every component's <style> and every stylesheet under src/
// whose selector reaches an <a> (or text inside one), a class put on an <a>/<RouterLink> in
// the same component, or a class named "...-link(s)...". It reads colours written as those
// custom properties; a literal hex value or a class bound only through `:class` is not seen.
const components = import.meta.glob('/src/**/*.vue', { query: '?raw', import: 'default', eager: true }) as Record<string, string>
const stylesheets = import.meta.glob('/src/**/*.css', { query: '?raw', import: 'default', eager: true }) as Record<string, string>

const BRAND_TEXT = /(?<![-\w])color:\s*var\(--crm-(?:teal|brand|logo-orange)\)/
const TINTED_PILL = /background(?:-color)?:\s*var\(--crm-(?:teal|brand)-soft\)/

function linkClasses(template: string) {
  const classes = new Set<string>()
  for (const tag of template.matchAll(/<(?:a|RouterLink|router-link)\b([^>]*)>/g)) {
    const attr = /\sclass="([^"]+)"/.exec(tag[1])
    attr?.[1].split(/\s+/).forEach(name => classes.add(name))
  }
  return classes
}

function targetsLink(selector: string, classes: Set<string>) {
  return selector.split(',').some(part => {
    // An <a> anywhere in the compound chain: `a`, `a.x`, `a:hover`, `a[href]`, `.x a strong`.
    if (/(^|[\s>+~(])a(?=$|[\s.:#[>+~)])/.test(part.trim())) return true
    return [...part.matchAll(/\.([\w-]+)/g)].some(([, name]) => classes.has(name) || /(^|-)links?(-|$)/.test(name))
  })
}

function brandOrangeLinkRules(css: string, classes: Set<string>) {
  const found: string[] = []
  const text = css.replace(/\/\*[\s\S]*?\*\//g, '').replace(/<\/?style[^>]*>/g, '')
  for (const rule of text.matchAll(/([^{}]*)\{([^{}]*)\}/g)) {
    const selector = rule[1].trim().replace(/\s+/g, ' '), body = rule[2]
    if (!selector || selector.startsWith('@') || !BRAND_TEXT.test(body) || TINTED_PILL.test(body)) continue
    if (targetsLink(selector, classes)) found.push(selector)
  }
  return found
}

function offenders() {
  const fromComponents = Object.entries(components).flatMap(([file, source]) => {
    const start = source.indexOf('<style')
    if (start < 0) return []
    return brandOrangeLinkRules(source.slice(start), linkClasses(source.slice(0, start))).map(selector => `${file}: ${selector}`)
  })
  const fromStylesheets = Object.entries(stylesheets).flatMap(([file, css]) => brandOrangeLinkRules(css, new Set()).map(selector => `${file}: ${selector}`))
  return [...fromComponents, ...fromStylesheets]
}

describe('link colour', () => {
  it('colours no link text with the brand orange', () => {
    expect(offenders()).toEqual([])
  })

  it('sees a link rule wherever its selector sits', () => {
    const links = new Set(['back'])
    expect(brandOrangeLinkRules('.x{color:red}\n.back,\n.eyebrow{color:var(--crm-teal)}', links)).toHaveLength(1)
    expect(brandOrangeLinkRules('.card a:not(.y) strong{color: var(--crm-brand)}', new Set())).toHaveLength(1)
    expect(brandOrangeLinkRules('a.more{color:var(--crm-logo-orange)}', new Set())).toHaveLength(1)
    expect(brandOrangeLinkRules('.badge-link{color:var(--crm-teal);background:var(--crm-teal-soft)}', new Set())).toEqual([])
    expect(brandOrangeLinkRules('.eyebrow{color:var(--crm-teal)}.alpha{border-color:var(--crm-teal)}', new Set())).toEqual([])
  })
})
