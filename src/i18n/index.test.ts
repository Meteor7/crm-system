import { beforeEach, describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import ts from 'typescript'
import { localeMessage, setLocale, useI18n, useLocaleMessage } from './index'

describe('i18n', () => {
  beforeEach(() => {
    localStorage.clear()
    setLocale('zh-CN')
  })

  it('keeps locale keys unique and their interpolation parameters aligned', () => {
    const source = ts.createSourceFile('index.ts', readFileSync('src/i18n/index.ts', 'utf8'), ts.ScriptTarget.Latest, true)
    const statement = source.statements.find((node) => ts.isVariableStatement(node)
      && node.declarationList.declarations.some((item) => item.name.getText(source) === 'messages')) as ts.VariableStatement
    const locales = (statement.declarationList.declarations[0].initializer as ts.ObjectLiteralExpression).properties
    const dictionaries = locales.map((locale) => {
      const entries = ((locale as ts.PropertyAssignment).initializer as ts.ObjectLiteralExpression).properties
        .map((entry) => [(entry.name as ts.StringLiteral).text, ((entry as ts.PropertyAssignment).initializer as ts.StringLiteral).text] as const)
      const dictionary = new Map(entries)
      expect(dictionary.size).toBe(entries.length)
      return dictionary
    })
    expect(dictionaries).toHaveLength(2)
    expect([...dictionaries[0].keys()].sort()).toEqual([...dictionaries[1].keys()].sort())
    for (const [key, text] of dictionaries[0]) {
      expect((text.match(/\{\w+\}/g) ?? []).sort(), key)
        .toEqual((dictionaries[1].get(key)!.match(/\{\w+\}/g) ?? []).sort())
    }
  })

  it('keeps Chinese as the default and supports parameter interpolation', () => {
    const { t } = useI18n()
    expect(t('nav.accounts')).toBe('客户档案')
    expect(t('shell.unreadCount', { count: 3 })).toBe('3 条未读')
  })

  it('switches locale, persists it, and updates the document language', () => {
    const { locale, t, setLocale: changeLocale } = useI18n()
    changeLocale('en-US')
    expect(locale.value).toBe('en-US')
    expect(t('nav.accounts')).toBe('Accounts')
    expect(localStorage.getItem('semicrm.locale')).toBe('en-US')
    expect(document.documentElement.lang).toBe('en-US')
  })

  it('inserts business values literally without expanding replacement syntax or other placeholders', () => {
    setLocale('en-US')
    const { t } = useI18n()
    const title = "Acme $& $` $' $$ {title}"
    expect(t('detail.confirmDeleteOpportunity', { title })).toBe(`Delete Opportunity ${title}?`)
    expect(t('common.page', { page: '{total}', total: 3 })).toBe('Page {total} of 3')
  })

  it('refreshes existing messages while preserving their original business values and raw server errors', () => {
    const notice = useLocaleMessage()
    const { message } = useI18n()
    const params = { title: 'Original $& record' }
    notice.value = message('detail.confirmDeleteOpportunity', params)
    params.title = 'Another record'
    setLocale('en-US')
    expect(notice.value).toBe('Delete Opportunity Original $& record?')
    notice.value = localeMessage('Imported original.docx', '已导入 original.docx')
    setLocale('zh-CN')
    expect(notice.value).toBe('已导入 original.docx')
    notice.value = 'Backend error: 原始内容'
    setLocale('en-US')
    expect(notice.value).toBe('Backend error: 原始内容')
    notice.value = ''
    expect(notice.value).toBe('')
  })
})
