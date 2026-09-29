import { createPinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import AppShell from './AppShell.vue'
import { createAppRouter } from './router'
import { createMockApi } from '@/api/mock-adapter'
import { useAppStore } from '@/stores/app'

describe('Opportunity board navigation', () => {
  it.each(['Manager', 'Sales', 'Engineer'] as const)('keeps a direct board link after %s permissions load', async role => {
    const router = createAppRouter()
    await router.push('/opportunity-board')
    const pinia = createPinia()
    const wrapper = mount(AppShell, { global: { plugins: [pinia, router], stubs: { RouterView: true } } })
    useAppStore(pinia).bootstrap = (await createMockApi({ latency: 0, role }).getBootstrap()).data
    await flushPromises()
    expect(router.currentRoute.value.path).toBe('/opportunity-board')
    wrapper.unmount()
  })

  it('still sends an unknown URL to the first allowed page', async () => {
    const router = createAppRouter()
    await router.push('/no-such-page')
    const pinia = createPinia()
    const wrapper = mount(AppShell, { global: { plugins: [pinia, router], stubs: { RouterView: true } } })
    useAppStore(pinia).bootstrap = (await createMockApi({ latency: 0, role: 'Sales' }).getBootstrap()).data
    await flushPromises()
    // The fallback page is lazy-loaded, so the redirect settles after the component import.
    await vi.waitFor(() => expect(router.currentRoute.value.path).not.toBe('/no-such-page'))
    expect(router.currentRoute.value.matched.length).toBeGreaterThan(0)
    wrapper.unmount()
  })

  // Managers reach the board from the cockpit tabs, Sales from the Opportunities list; Engineers see neither item.
  it.each([['Manager', 'review'], ['Sales', 'opportunities'], ['Engineer', null]] as const)('highlights the sidebar item a %s came from', async (role, active) => {
    const router = createAppRouter()
    await router.push('/opportunity-board')
    const pinia = createPinia()
    const wrapper = mount(AppShell, { global: { plugins: [pinia, router], stubs: { RouterView: true } } })
    useAppStore(pinia).bootstrap = (await createMockApi({ latency: 0, role }).getBootstrap()).data
    await flushPromises()
    const current = wrapper.findAll('.nav-link[aria-current="page"]').map(link => link.attributes('data-route'))
    expect(current).toEqual(active ? [active] : [])
    wrapper.unmount()
  })
})

