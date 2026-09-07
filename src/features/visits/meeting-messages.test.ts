import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { expect, it } from 'vitest'
import { meetingParseMessage } from './meeting-messages'

it('translates all fixed Chinese outcomes emitted by the active meeting parser', () => {
  const source = readFileSync(resolve('backend/apps/rayher_crm/rayher_crm/services/visit_meetings.py'), 'utf8')
  const messages = [...new Set([...source.matchAll(/"([^"\r\n]+)"/g)].map(match => match[1]).filter(value => /\p{Script=Han}/u.test(value)))]
  expect(messages.length).toBeGreaterThanOrEqual(9)
  for (const message of messages) {
    expect(meetingParseMessage(message, 'en-US'), message).not.toMatch(/\p{Script=Han}/u)
    expect(meetingParseMessage(message, 'zh-CN')).toBe(message)
  }
  expect(meetingParseMessage('服务器自定义诊断', 'en-US')).toBe('服务器自定义诊断')
})
