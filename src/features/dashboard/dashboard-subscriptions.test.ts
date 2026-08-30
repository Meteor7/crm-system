import { describe, expect, it } from 'vitest'
import {
  DEFAULT_BOSS_DASHBOARD_SUBSCRIPTION_GROUPS,
  bossDashboardSubscriptionGroupsKey,
  normalizeBossDashboardSubscriptionGroups,
  readBossDashboardSubscriptionGroups,
  writeBossDashboardSubscriptionGroups,
} from './dashboard-subscriptions'

function createMemoryStorage(initialValues: Record<string, string> = {}) {
  const values = new Map(Object.entries(initialValues))
  return {
    getItem(key: string) {
      return values.get(key) ?? null
    },
    setItem(key: string, value: string) {
      values.set(key, value)
    },
  }
}

describe('Boss dashboard subscription groups', () => {
  it('keeps one to five complete rows with globally unique known chart IDs', () => {
    const fiveRows = [
      ['evaluation-status', 'booking-month', 'top-accounts'],
      ['region', 'tier', 'risk'],
      ['requirements', 'budget', 'actions'],
      ['action-timeliness', 'demo', 'demo-priority'],
      ['evaluation-runs', 'visits', 'visit-owner'],
    ]

    expect(normalizeBossDashboardSubscriptionGroups(fiveRows)).toEqual(fiveRows)
  })

  it.each([
    null,
    'region,risk,contracts',
    [],
    ['region', 'risk', 'contracts'],
    [['region', 'risk']],
    [['region', 'risk', 'contracts', 'visits']],
    [['region', 'region', 'contracts']],
    [
      ['evaluation-status', 'booking-month', 'top-accounts'],
      ['region', 'tier', 'evaluation-status'],
    ],
    [['region', 'risk', 'removed-chart']],
    Array.from({ length: 7 }, () => ['region', 'tier', 'risk']),
  ])('falls back to one default row when saved groups are invalid: %j', (value) => {
    expect(normalizeBossDashboardSubscriptionGroups(value))
      .toEqual(DEFAULT_BOSS_DASHBOARD_SUBSCRIPTION_GROUPS)
  })

  it('uses a v2 user-scoped key', () => {
    expect(bossDashboardSubscriptionGroupsKey('person006@crm.example.invalid'))
      .toBe('semiconductor-crm:boss-dashboard-subscriptions:v2:boss.lin%40crm.example.invalid')
  })

  it('migrates a valid legacy v1 selection into the first row when v2 is absent', () => {
    const storage = createMemoryStorage({
      'semiconductor-crm:boss-dashboard-subscriptions:v1:boss%40example.com':
        JSON.stringify(['region', 'risk', 'visits']),
    })

    expect(readBossDashboardSubscriptionGroups(storage, 'boss@example.com'))
      .toEqual([['region', 'risk', 'visits']])
  })

  it('prefers valid v2 groups over the legacy v1 selection', () => {
    const storage = createMemoryStorage({
      'semiconductor-crm:boss-dashboard-subscriptions:v1:boss%40example.com':
        JSON.stringify(['region', 'risk', 'contracts']),
      'semiconductor-crm:boss-dashboard-subscriptions:v2:boss%40example.com':
        JSON.stringify([
          ['evaluation-status', 'booking-month', 'top-accounts'],
          ['requirements', 'budget', 'actions'],
        ]),
    })

    expect(readBossDashboardSubscriptionGroups(storage, 'boss@example.com'))
      .toEqual([
        ['evaluation-status', 'booking-month', 'top-accounts'],
        ['requirements', 'budget', 'actions'],
      ])
  })

  it('migrates saved rows by removing retired contract dashboards without losing other selections', () => {
    const storage = createMemoryStorage({
      'semiconductor-crm:boss-dashboard-subscriptions:v2:boss%40example.com':
        JSON.stringify([
          ['evaluation-status', 'booking-month', 'top-accounts'],
          ['region', 'tier', 'risk'],
          ['requirements', 'budget', 'actions'],
          ['action-timeliness', 'demo', 'demo-priority'],
          ['evaluation-runs', 'contracts', 'contract-type'],
          ['contract-risk', 'visits', 'visit-owner'],
        ]),
    })

    expect(readBossDashboardSubscriptionGroups(storage, 'boss@example.com'))
      .toEqual([
        ['evaluation-status', 'booking-month', 'top-accounts'],
        ['region', 'tier', 'risk'],
        ['requirements', 'budget', 'actions'],
        ['action-timeliness', 'demo', 'demo-priority'],
        ['evaluation-runs', 'visits', 'visit-owner'],
      ])
  })

  it('falls back to defaults for corrupt v2 data and persists valid groups', () => {
    const storage = createMemoryStorage({
      'semiconductor-crm:boss-dashboard-subscriptions:v2:boss%40example.com': '{broken',
    })

    expect(readBossDashboardSubscriptionGroups(storage, 'boss@example.com'))
      .toEqual(DEFAULT_BOSS_DASHBOARD_SUBSCRIPTION_GROUPS)
    expect(writeBossDashboardSubscriptionGroups(storage, 'boss@example.com', [
      ['evaluation-status', 'booking-month', 'top-accounts'],
      ['region', 'tier', 'risk'],
    ])).toBe(true)
    expect(readBossDashboardSubscriptionGroups(storage, 'boss@example.com'))
      .toEqual([
        ['evaluation-status', 'booking-month', 'top-accounts'],
        ['region', 'tier', 'risk'],
      ])
  })

  it('survives unavailable browser storage without accepting invalid writes', () => {
    const storage = {
      getItem() {
        throw new Error('storage denied')
      },
      setItem() {
        throw new Error('storage denied')
      },
    }

    expect(readBossDashboardSubscriptionGroups(storage, 'boss@example.com'))
      .toEqual(DEFAULT_BOSS_DASHBOARD_SUBSCRIPTION_GROUPS)
    expect(writeBossDashboardSubscriptionGroups(storage, 'boss@example.com', [
      ['region', 'risk'],
    ])).toBe(false)
    expect(writeBossDashboardSubscriptionGroups(storage, 'boss@example.com', [
      ['region', 'risk', 'contracts'],
    ])).toBe(false)
  })
})
