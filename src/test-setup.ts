import { afterEach, beforeEach } from 'vitest'
import { setLocale } from '@/i18n'

// Keep each test isolated from the user's persisted language preference.
beforeEach(() => {
  localStorage.clear()
  setLocale('zh-CN')
})

afterEach(() => {
  setLocale('zh-CN')
  localStorage.clear()
})
