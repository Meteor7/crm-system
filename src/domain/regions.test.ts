import { describe, expect, it } from 'vitest'
import {
  REGION_PRESETS,
  isEnglishRegion,
  matchingRegion,
  normalizeStoredRegion,
  presetRegion,
  regionDepth,
  regionLabel,
  regionOptions,
  territoryOptionLabel,
} from './regions'

describe('Customer regions', () => {
  it('reads Chinese and short spellings as the English preset, like the server', () => {
    const cases: Record<string, string> = {
      华东: 'East China', 华东区: 'East China', ' east ': 'East China', 'EAST-CHINA': 'East China',
      '华东 East China': 'East China', 華南: 'South China', 华西地区: 'West China',
      North: 'North China', 华中: 'Central China', 'Central China': 'Central China',
    }
    for (const [value, preset] of Object.entries(cases)) expect(presetRegion(value), value).toBe(preset)
    for (const value of ['华东/华南', '华东 South China', '上海', 'Overseas', '']) expect(presetRegion(value), value).toBe('')
  })

  it('lists presets first and reuses a custom region that differs only in case or spacing', () => {
    const options = regionOptions(['Southeast Asia', ' East China ', ''])

    expect(options).toEqual([...REGION_PRESETS, 'Southeast Asia'])
    expect(matchingRegion('south-east asia', options)).toBe('Southeast Asia')
    expect(matchingRegion('华北区', options)).toBe('North China')
    expect(matchingRegion('Northeast China', options)).toBe('')
  })

  it('accepts new custom regions only in English', () => {
    expect(isEnglishRegion('Northeast China')).toBe(true)
    expect(isEnglishRegion('S.E. Asia')).toBe(true)
    expect(isEnglishRegion('东北')).toBe(false)
  })

  it('labels presets in the viewer language and shows custom regions as stored', () => {
    expect(regionLabel('East China', 'zh-CN')).toBe('华东')
    expect(regionLabel('East China', 'en-US')).toBe('East China')
    expect(regionLabel('Southeast Asia', 'zh-CN')).toBe('Southeast Asia')
    expect(normalizeStoredRegion('华中')).toBe('Central China')
    expect(normalizeStoredRegion('  西北 ')).toBe('西北')
  })

  it('labels the territories above the regions and indents a filter option by its depth in the tree', () => {
    const parents = { Asia: 'World', China: 'Asia', 'East China': 'China' }
    expect(['World', 'Asia', 'China'].map((name) => regionLabel(name, 'zh-CN'))).toEqual(['全球', '亚洲', '中国'])
    expect(regionLabel('China', 'en-US')).toBe('China')
    expect(['World', 'Asia', 'China', 'East China', 'Taiwan'].map((name) => regionDepth(name, parents))).toEqual([0, 1, 2, 3, 0])
    expect(territoryOptionLabel('World', parents, 'zh-CN')).toBe('全球')
    expect(territoryOptionLabel('East China', parents, 'zh-CN')).toBe('\u00a0'.repeat(6) + '华东')
    // A server without the tree sends no parents: every option is flat.
    expect(territoryOptionLabel('East China', undefined, 'en-US')).toBe('East China')
    // Parents that loop still end, and an inherited property is neither a parent nor a label.
    expect(regionDepth('a', { a: 'b', b: 'a' })).toBe(1)
    expect(regionDepth('constructor', {})).toBe(0)
    expect(regionLabel('constructor', 'zh-CN')).toBe('constructor')
  })
})
