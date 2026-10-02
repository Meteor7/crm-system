import { setLocale, useI18n } from './index'
import { navigation } from '@/app/navigation'
import { existsSync, readFileSync, statSync } from 'node:fs'
import { dirname, join, relative, resolve } from 'node:path'
import { parse } from '@vue/compiler-sfc'
import ts from 'typescript'
import { expect, it } from 'vitest'

type TemplateRoot = NonNullable<NonNullable<ReturnType<typeof parse>['descriptor']['template']>['ast']>
type TemplateNode = TemplateRoot | TemplateRoot['children'][number]
const han = /\p{Script=Han}/u
// These two checks traverse and parse every reachable application source. Allow
// contention during parallel runs without changing the other unit-test limits.
const SOURCE_SCAN_TIMEOUT = 30_000
const visibleAttributes = new Set([
  'label', 'title', 'placeholder', 'arialabel', 'ariadescription', 'description',
  'emptycopy', 'emptytitle', 'emptymessage', 'submitlabel', 'cancellabel', 'closelabel', 'busylabel', 'alt', 'message', 'eyebrow',
])

// Start at the application entry, so a newly registered page is checked automatically.
// Retired pages and their unused components do not render in either locale.
function applicationSources() {
  const files = new Set<string>()
  function visit(file: string) {
    if (files.has(file) || !/\.(ts|vue)$/.test(file)) return
    files.add(file)
    const source = readFileSync(file, 'utf8')
    const descriptor = file.endsWith('.vue') ? parse(source).descriptor : undefined
    const script = descriptor ? [descriptor.script?.content, descriptor.scriptSetup?.content].filter(Boolean).join('\n') : source
    const ast = ts.createSourceFile(file, script, ts.ScriptTarget.Latest, true)
    function inspect(node: ts.Node) {
      let specifier: string | undefined
      if ((ts.isImportDeclaration(node) || ts.isExportDeclaration(node)) && node.moduleSpecifier && ts.isStringLiteral(node.moduleSpecifier)) specifier = node.moduleSpecifier.text
      if (ts.isCallExpression(node) && node.expression.kind === ts.SyntaxKind.ImportKeyword && node.arguments[0] && ts.isStringLiteral(node.arguments[0])) specifier = node.arguments[0].text
      if (specifier?.startsWith('.') || specifier?.startsWith('@/')) {
        const frappeOverrides: Record<string, string> = { '@/demo/personnel': 'src/demo/personnel.frappe.ts', '@/api/runtime-adapter': 'src/api/runtime-adapter.frappe.ts' }
        const base = frappeOverrides[specifier] ? resolve(frappeOverrides[specifier]) : specifier.startsWith('@/') ? resolve('src', specifier.slice(2)) : resolve(dirname(file), specifier)
        const target = [base, `${base}.ts`, `${base}.vue`, join(base, 'index.ts')].find((candidate) => existsSync(candidate) && statSync(candidate).isFile())
        expect(target, `Resolve ${specifier} from ${file}`).toBeDefined()
        if (target) visit(target)
      }
      ts.forEachChild(node, inspect)
    }
    inspect(ast)
  }
  visit(resolve('src/main.ts'))
  return [...files]
}

function untranslatedExpressionStrings(expression: string, pairHelpers = new Set<string>()) {
  const ast = ts.createSourceFile('expression.ts', `const value = (${expression});`, ts.ScriptTarget.Latest, true)
  const strings: string[] = []
  const inside = (node: ts.Node, ancestor: ts.Node) => node.pos >= ancestor.pos && node.end <= ancestor.end
  function inspect(node: ts.Node) {
    if ((ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node) || ts.isTemplateHead(node) || ts.isTemplateMiddle(node) || ts.isTemplateTail(node)) && han.test(node.text)) {
      let translatedOrData = false
      for (let parent = node.parent; parent; parent = parent.parent) {
        if (ts.isPropertyAssignment(parent) && parent.name === node) translatedOrData = true
        if (ts.isBinaryExpression(parent) && [ts.SyntaxKind.EqualsEqualsEqualsToken, ts.SyntaxKind.ExclamationEqualsEqualsToken, ts.SyntaxKind.EqualsEqualsToken, ts.SyntaxKind.ExclamationEqualsToken].includes(parent.operatorToken.kind)) translatedOrData = true
        if (ts.isConditionalExpression(parent)) {
          if (inside(node, parent.condition)) translatedOrData = true
          const choice = /^locale(?:\.value)?\s*(===|!==|==|!=)\s*(['"])(en-US|zh-CN)\2$/.exec(parent.condition.getText(ast))
          if (choice) {
            const equals = choice[1] === '===' || choice[1] === '=='
            const englishBranch = (choice[3] === 'en-US') === equals ? parent.whenTrue : parent.whenFalse
            if (!inside(node, englishBranch)) translatedOrData = true
          }
        }
        if (ts.isCallExpression(parent)) {
          const name = parent.expression.getText(ast)
          if (['t', 'message'].includes(name)) translatedOrData = true
          if ((name === 'localeMessage' || pairHelpers.has(name)) && parent.arguments[1] && inside(node, parent.arguments[1])) translatedOrData = true
        }
      }
      if (!translatedOrData) strings.push(node.text)
    }
    ts.forEachChild(node, inspect)
  }
  inspect(ast)
  return strings
}

it('keeps reachable template copy and accessible labels localized in English', () => {
  const failures: string[] = []
  const files = applicationSources().filter((file) => file.endsWith('.vue'))
  expect(files.length).toBeGreaterThan(80)
  for (const file of files) {
    const name = relative(process.cwd(), file).replaceAll('\\', '/')
    const descriptor = parse(readFileSync(file, 'utf8')).descriptor
    const script = descriptor.scriptSetup?.content ?? ''
    // Recognize only local helpers that select the supplied translation pair.
    const pairHelpers = new Set([...script.matchAll(/const\s+(\w+)\s*=\s*\(english:\s*string,\s*chinese:\s*string\)\s*=>\s*(?:localeMessage\(english,\s*chinese\)\[locale\.value\]|locale\.value\s*===\s*['"]en-US['"]\s*\?\s*english\s*:\s*chinese)/g)].map((match) => match[1]))
    const template = descriptor.template
    if (!template?.ast) continue
    function record(line: number, value: string) {
      if (!han.test(value)) return
      // This is contractual document content, not an interface label.
      if (name === 'src/features/quotations/QuotationEditor.vue' && value.trim() === 'FOB上海\u00a0\u00a0FOB Shanghai') return
      failures.push(`${name}:${line}: ${value.trim()}`)
    }
    function inspect(node: TemplateNode) {
      if (node.type === 2) record(node.loc.start.line, node.content)
      if (node.type === 5) {
        for (const value of untranslatedExpressionStrings(node.content.loc.source, pairHelpers)) record(node.loc.start.line, value)
      }
      if (node.type === 1) for (const prop of node.props) {
        if (prop.type === 6 && visibleAttributes.has(prop.name.replaceAll('-', '').toLowerCase()) && prop.value) record(prop.loc.start.line, prop.value.content)
        if (prop.type === 7 && prop.exp && ((prop.name === 'bind' && prop.arg && visibleAttributes.has(prop.arg.loc.source.replaceAll('-', '').toLowerCase())) || ['text', 'html'].includes(prop.name))) {
          for (const value of untranslatedExpressionStrings(prop.exp.loc.source, pairHelpers)) record(prop.loc.start.line, value)
        }
      }
      if (node.type === 0 || node.type === 1) for (const child of node.children) inspect(child)
    }
    inspect(template.ast)
  }
  expect(failures).toEqual([])
}, SOURCE_SCAN_TIMEOUT)

it('detects raw copy without rejecting a paired Chinese translation', () => {
  expect(untranslatedExpressionStrings("'暂无文档'")).toEqual(['暂无文档'])
  expect(untranslatedExpressionStrings("locale === 'en-US' ? '暂无文档' : '暂无文档'")).toEqual(['暂无文档'])
  expect(untranslatedExpressionStrings("ui('No documents', '暂无文档')", new Set(['ui']))).toEqual([])
  expect(untranslatedExpressionStrings("ui('暂无文档', '暂无文档')", new Set(['ui']))).toEqual(['暂无文档'])
})

it('resolves literal translation calls and navigation keys in both dictionaries', () => {
  const keys = new Set<string>()
  for (const file of applicationSources()) {
    const source = readFileSync(file, 'utf8')
    for (const match of source.matchAll(/\b(?:t|message)\(\s*['"]([^'"]+)['"]\s*(?=[,)])/g)) keys.add(match[1])
  }
  for (const group of navigation) {
    expect(group.i18nKey, group.label).toBeTruthy()
    keys.add(group.i18nKey!)
    for (const item of group.items) {
      expect(item.i18nKey, item.path).toBeTruthy()
      keys.add(item.i18nKey!)
    }
  }
  const { t } = useI18n()
  expect(keys.size).toBeGreaterThan(500)
  for (const locale of ['zh-CN', 'en-US'] as const) {
    setLocale(locale)
    for (const key of keys) expect(t(key), `${locale}: ${key}`).not.toBe(key)
  }
}, SOURCE_SCAN_TIMEOUT)
