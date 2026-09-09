<script setup lang="ts">
import { notificationCopy } from '@/i18n/notification-copy'
import { requestErrorMessage } from '@/api/request-state'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Bell, Globe2, KeyRound, Menu, PanelLeftClose, PanelLeftOpen, Settings, X } from '@lucide/vue'
import { navigation } from './navigation'
import { useAppStore } from '@/stores/app'
import { hasCapability } from '@/domain/permissions'
import { useNotificationStore } from '@/stores/notifications'
import type { AppNotification, NotificationCategory } from '@/types/notifications'
import { usingMock } from '@/api'
import { formatDisplayDate } from '@/domain/time'
import { useI18n, useLocaleMessage } from '@/i18n'

type FrappeWindow = Window & { frappe?: unknown }

const props = defineProps<{ embedded?: boolean }>()

const route = useRoute()
const router = useRouter()
const store = useAppStore()
const notifications = useNotificationStore()
const { locale, t, setLocale, message } = useI18n()
const mobileOpen = ref(false)
const desktopSidebarCollapsed = ref(false)
const accountOpen = ref(false)
const savingPassword = ref(false)
const currentPassword = ref('')
const newPassword = ref('')
const confirmPassword = ref('')
const passwordError = useLocaleMessage()
const passwordNotice = useLocaleMessage()
const notificationOpen = ref(false)
const notificationBusy = ref(false)
const notificationError = useLocaleMessage()
let notificationTimer: number | undefined
const isEmbedded = computed(() => props.embedded ?? (Boolean((window as FrappeWindow).frappe) || import.meta.env.VITE_EMBEDDED === 'true'))
const brandLogoUrl = `${import.meta.env.BASE_URL}brand/planck-logo-standard.png`
const DEMO_TYPOGRAPHY_EXCLUDED_PATHS = new Set(['/demo-workflow', '/demo-requests', '/evaluations'])
const usesStandardTypography = computed(() => !DEMO_TYPOGRAPHY_EXCLUDED_PATHS.has(route.path))
const activeNavigationPath = computed(() =>
  typeof route.meta.navigationPath === 'string' ? route.meta.navigationPath : route.path,
)

const user = computed(() => store.bootstrap?.user ?? {
  name: '演示员工24',
  initials: 'LM',
  role: 'Manager',
  team: '大中华区销售',
})
const roleLabel = computed(() => {
  if (!store.bootstrap) return t('shell.salesManager')
  const role = store.bootstrap.user.role
  return locale.value === 'en-US' ? role : { Manager: '经理', Sales: '销售', Engineer: '工程师' }[role]
})
const notificationCategoryLabels: Record<NotificationCategory, [string, string]> = {
  Account: ['客户', 'Account'], Contact: ['联系人', 'Contact'], Requirement: ['需求', 'Requirement'],
  Lead: ['线索', 'Lead'], Opportunity: ['商机', 'Opportunity'], Action: ['行动', 'Action'],
  Visit: ['拜访', 'Visit'], Booking: ['订单', 'Booking'], Demo: ['演示', 'Demo'],
  Evaluation: ['评估', 'Evaluation'], InstalledTool: ['已装机设备', 'Installed Tool'],
  Quotation: ['报价', 'Quotation'], RFQ: ['询价', 'RFQ'], Document: ['文档', 'Document'],
}
function notificationCategoryLabel(value: NotificationCategory) { return notificationCategoryLabels[value]?.[locale.value === 'en-US' ? 1 : 0] ?? value }
const localeMenuOpen = ref(false)
const visibleNavigation = computed(() => {
  const role = store.bootstrap?.user.role
  return navigation
    .filter((group) => !role || !group.hiddenRoles?.includes(role))
    .map((group) => ({ ...group, items: group.items.filter((item) => store.bootstrap && item.capabilities.some((capability) => hasCapability(store.bootstrap, capability))) }))
    .filter((group) => group.items.length)
})

watch(
  () => [store.identityRevision, route.path] as const,
  () => {
    if (!store.bootstrap) return
    const allowedPaths = visibleNavigation.value.flatMap((group) => group.items.map((item) => item.path))
    if (!allowedPaths.includes(activeNavigationPath.value) && allowedPaths[0]) void router.replace(allowedPaths[0])
  },
  { flush: 'post' },
)

async function navigate(path: string) {
  await router.push(path)
  mobileOpen.value = false
}

async function openNotification(notification: AppNotification) {
  if (notificationBusy.value) return
  notificationBusy.value = true
  notificationError.value = ''
  try {
    await router.push(notification.route)
    await store.markNotificationRead(notification.id)
    notificationOpen.value = false
  } catch (reason) {
    notificationError.value = requestErrorMessage(reason)
  } finally {
    notificationBusy.value = false
  }
}

async function refreshNotifications() {
  if (usingMock || !store.bootstrap) return
  try {
    await store.refreshNotifications()
  } catch (reason) {
    if (notificationOpen.value) notificationError.value = requestErrorMessage(reason)
  }
}

async function toggleNotificationCenter() {
  notificationOpen.value = !notificationOpen.value
  notificationError.value = ''
  accountOpen.value = false
  localeMenuOpen.value = false
  if (notificationOpen.value) await refreshNotifications()
}

async function loadMoreNotifications() {
  if (notificationBusy.value) return
  notificationBusy.value = true
  notificationError.value = ''
  try {
    await store.loadMoreNotifications()
  } catch (reason) {
    notificationError.value = requestErrorMessage(reason)
  } finally {
    notificationBusy.value = false
  }
}

function refreshNotificationsWhenVisible() {
  if (document.visibilityState === 'visible') void refreshNotifications()
}

async function markAllNotificationsRead() {
  if (notificationBusy.value) return
  notificationBusy.value = true
  notificationError.value = ''
  try {
    await store.markAllNotificationsRead()
  } catch (reason) {
    notificationError.value = requestErrorMessage(reason)
  } finally {
    notificationBusy.value = false
  }
}

async function submitPasswordChange() {
  passwordError.value = ''
  passwordNotice.value = ''
  if (usingMock) {
    return
  }
  if (!currentPassword.value || !newPassword.value || !confirmPassword.value) {
    passwordError.value = message('shell.passwordRequired')
    return
  }
  if (newPassword.value !== confirmPassword.value) {
    passwordError.value = message('shell.passwordMismatch')
    return
  }
  if (newPassword.value.length < 8 || !/[A-Za-z]/.test(newPassword.value) || !/[0-9]/.test(newPassword.value)) {
    passwordError.value = message('shell.passwordPolicy')
    return
  }
  savingPassword.value = true
  try {
    await store.activeApi.changeCurrentUserPassword({ currentPassword: currentPassword.value, newPassword: newPassword.value })
    currentPassword.value = ''
    newPassword.value = ''
    confirmPassword.value = ''
    passwordNotice.value = message('shell.passwordUpdated')
  } catch (error) {
    passwordError.value = requestErrorMessage(error, message('shell.passwordFailed'))
  } finally {
    savingPassword.value = false
  }
}

onMounted(async () => {
  await store.loadBootstrap()
  window.addEventListener('focus', refreshNotificationsWhenVisible)
  document.addEventListener('visibilitychange', refreshNotificationsWhenVisible)
  notificationTimer = window.setInterval(() => void refreshNotifications(), 30_000)
})
onBeforeUnmount(() => {
  window.removeEventListener('focus', refreshNotificationsWhenVisible)
  document.removeEventListener('visibilitychange', refreshNotificationsWhenVisible)
  if (notificationTimer !== undefined) window.clearInterval(notificationTimer)
})
</script>

<template>
  <div class="semicrm-app" :class="{ 'is-embedded': isEmbedded, 'is-sidebar-collapsed': desktopSidebarCollapsed }" data-testid="app-shell">
    <button
      v-if="mobileOpen"
      class="nav-scrim"
      type="button"
      :aria-label="t('shell.closeNavigation')"
      data-testid="nav-scrim"
      @click="mobileOpen = false"
    />

    <aside
      class="app-sidebar"
      :class="{ 'is-open': mobileOpen, 'is-desktop-collapsed': desktopSidebarCollapsed }"
      :aria-hidden="desktopSidebarCollapsed"
      data-testid="app-sidebar"
    >
      <div class="brand-block">
        <img
          class="brand-logo"
          data-testid="planck-logo"
          :src="brandLogoUrl"
          alt="PLANCK CRM"
        >
        <button
          v-if="!desktopSidebarCollapsed"
          class="sidebar-collapse-button"
          type="button"
          :aria-label="t('shell.collapseNavigation')"
          aria-expanded="true"
          data-testid="sidebar-collapse-toggle"
          @click="desktopSidebarCollapsed = true"
        >
          <PanelLeftClose :size="18" />
        </button>
        <button class="sidebar-close" type="button" :aria-label="t('shell.closeNavigation')" @click="mobileOpen = false">
          <X :size="20" />
        </button>
      </div>

      <nav class="primary-nav" :aria-label="t('shell.mainNavigation')">
        <section v-for="group in visibleNavigation" :key="group.label" class="nav-section">
          <p>{{ group.i18nKey ? t(group.i18nKey) : group.label }}</p>
          <button
            v-for="item in group.items"
            :key="item.key"
            class="nav-link"
            :class="{ active: activeNavigationPath === item.path }"
            type="button"
            :data-route="item.key"
            :aria-current="activeNavigationPath === item.path ? 'page' : undefined"
            @click="navigate(item.path)"
          >
            <component :is="item.icon" :size="18" :stroke-width="1.8" aria-hidden="true" />
            <span>{{ item.i18nKey ? t(item.i18nKey) : item.label }}</span>
            <b v-if="item.badge">{{ item.badge }}</b>
          </button>
        </section>
      </nav>

    </aside>

    <div class="app-main">
      <header class="topbar">
        <div class="topbar-start">
          <button
            v-if="desktopSidebarCollapsed"
            class="icon-button desktop-sidebar-expand"
            type="button"
            :aria-label="t('shell.expandNavigation')"
            aria-expanded="false"
            data-testid="sidebar-expand-toggle"
            @click="desktopSidebarCollapsed = false"
          >
            <PanelLeftOpen :size="20" />
          </button>
          <button class="icon-button menu-button" type="button" :aria-label="t('shell.openNavigation')" data-testid="menu-toggle" @click="mobileOpen = !mobileOpen">
            <Menu :size="21" />
          </button>
        </div>
        <div class="topbar-end">
          <div class="locale-control">
            <button
              class="locale-toggle"
              type="button"
              :aria-label="t('language.switchTo')"
              :aria-expanded="localeMenuOpen"
              data-testid="locale-toggle"
              @click="localeMenuOpen = !localeMenuOpen; accountOpen = false; notificationOpen = false"
            >
              <Globe2 :size="17" aria-hidden="true" />
              <span>{{ locale === 'en-US' ? 'EN' : '中' }}</span>
            </button>
            <div v-if="localeMenuOpen" class="locale-menu" role="menu" :aria-label="t('language.label')">
              <button type="button" role="menuitemradio" :aria-checked="locale === 'zh-CN'" :class="{ selected: locale === 'zh-CN' }" @click="setLocale('zh-CN'); localeMenuOpen = false">{{ t('language.chinese') }}</button>
              <button type="button" role="menuitemradio" :aria-checked="locale === 'en-US'" :class="{ selected: locale === 'en-US' }" @click="setLocale('en-US'); localeMenuOpen = false">{{ t('language.english') }}</button>
            </div>
          </div>
          <div class="notification-control">
            <button
              class="icon-button notification-button"
              type="button"
              data-testid="notification-button"
              :aria-label="`${t('shell.messageCenter')}${locale === 'en-US' ? ', ' : '，'}${t('shell.unreadCount', { count: notifications.unreadCount })}`"
              :aria-expanded="notificationOpen"
              :title="t('shell.messageCenter')"
              @click="toggleNotificationCenter"
            >
              <Bell :size="19" /><b v-if="notifications.unreadCount">{{ notifications.unreadCount > 99 ? '99+' : notifications.unreadCount }}</b>
            </button>
            <section v-if="notificationOpen" class="notification-center" data-testid="notification-center" :aria-label="t('shell.messageCenter')">
              <header>
                <div><span>MESSAGE CENTER</span><strong>{{ t('shell.messageCenter') }}</strong></div>
                <button type="button" :disabled="!notifications.unreadCount || notificationBusy" @click="markAllNotificationsRead">{{ t('shell.markAllRead') }}</button>
              </header>
              <p v-if="notificationError" class="notification-error" data-notification-error role="alert">{{ notificationError }}</p>
              <div class="notification-list">
                <button
                  v-for="notification in notifications.visibleItems"
                  :key="notification.id"
                  type="button"
                  :data-notification-id="notification.id"
                  :class="{ unread: !notification.read }"
                  :disabled="notificationBusy"
                  @click="openNotification(notification)"
                >
                  <i />
                  <span>
                    <em>{{ notificationCategoryLabel(notification.category) }}</em>
                    <strong>{{ notificationCopy(notification, locale).title }}</strong>
                    <small>{{ notificationCopy(notification, locale).message }}</small>
                    <time>{{ formatDisplayDate(notification.createdAt) }}</time>
                  </span>
                </button>
                <p v-if="!notifications.visibleItems.length">{{ t('shell.noMessages') }}</p>
              </div>
              <button
                v-if="notifications.items.length < notifications.serverTotal"
                class="notification-load-more"
                type="button"
                :disabled="notificationBusy"
                @click="loadMoreNotifications"
              >{{ t('shell.loadMore', { current: notifications.items.length, total: notifications.serverTotal }) }}</button>
            </section>
          </div>
          <div class="identity-control">
            <button class="user-menu" data-testid="account-center-button" type="button" :aria-expanded="accountOpen" :aria-label="t('shell.accountCenter')" :title="t('shell.accountCenter')" @click="accountOpen = !accountOpen; notificationOpen = false; localeMenuOpen = false">
              <span class="avatar settings-avatar"><Settings :size="19" /></span>
              <span><strong>{{ user.name }}</strong><small>{{ roleLabel }}</small></span>
            </button>
            <section v-if="accountOpen" class="account-center" data-testid="account-center" :aria-label="t('shell.accountCenter')">
              <header>
                <span class="account-center-icon"><Settings :size="18" /></span>
                <span class="account-center-title"><strong>{{ t('shell.accountCenter') }}</strong><small>{{ t('shell.accountSetting') }}</small></span>
                <button class="account-center-close" data-testid="account-center-close" type="button" :aria-label="t('common.close')" :title="t('common.close')" @click="accountOpen = false"><X :size="16" /></button>
              </header>
              <div class="account-profile">
                <strong>{{ user.name }}</strong>
                <small>{{ store.bootstrap?.user.id ?? t('shell.currentAccount') }}</small>
                <span>{{ roleLabel }} · {{ user.team }}</span>
              </div>
              <form v-if="!usingMock" class="password-setting" @submit.prevent="submitPasswordChange">
                <h3><KeyRound :size="15" />{{ t('shell.changePassword') }}</h3>
                <label>{{ t('shell.currentPassword') }}<input v-model="currentPassword" type="password" autocomplete="current-password" /></label>
                <label>{{ t('shell.newPassword') }}<input v-model="newPassword" type="password" autocomplete="new-password" /></label>
                <label>{{ t('shell.confirmPassword') }}<input v-model="confirmPassword" type="password" autocomplete="new-password" /></label>
                <small>{{ t('shell.passwordHint') }}</small>
                <p v-if="passwordError" class="account-error" role="alert">{{ passwordError }}</p>
                <p v-if="passwordNotice" class="account-success" role="status">{{ passwordNotice }}</p>
                <button type="submit" class="primary-button" :disabled="savingPassword">{{ savingPassword ? t('shell.saving') : t('shell.updatePassword') }}</button>
              </form>
            </section>
          </div>
        </div>
      </header>

      <main class="route-content" :class="{ 'standard-typography': usesStandardTypography }">
        <RouterView v-slot="{ Component }">
          <component :is="Component" :key="`${route.fullPath}:${store.identityRevision}`" :api-client="store.activeApi" />
        </RouterView>
      </main>
    </div>
  </div>
</template>

<style scoped>
.semicrm-app { position: relative; display: flex; min-height: 100dvh; overflow-x: hidden; isolation: isolate; }
.app-sidebar { position: fixed; inset: 0 auto 0 0; z-index: 30; display: flex; width: 260px; flex-direction: column; padding: 22px 16px 18px; color: rgba(255,255,255,.88); background: var(--crm-navy-strong); border-right: 1px solid rgba(255,255,255,.08); transition: transform .22s ease; }
.brand-block { display: flex; min-height: 52px; align-items: center; padding: 0 6px 14px; }
.brand-logo { display: block; width: auto; max-width: calc(100% - 42px); height: 52px; object-fit: contain; object-position: left center; }
.sidebar-collapse-button { display: grid; width: 32px; height: 32px; margin-left: auto; flex: 0 0 auto; place-items: center; color: rgba(255,255,255,.58); background: rgba(255,255,255,.05); border: 1px solid rgba(255,255,255,.08); border-radius: 8px; cursor: pointer; transition: .18s ease; }
.sidebar-collapse-button:hover { color: #fff; background: rgba(255,255,255,.1); }
.sidebar-close { display: none; margin-left: auto; padding: 7px; color: #fff; background: transparent; border: 0; border-radius: 8px; }
.primary-nav { display: grid; min-height: 0; flex: 1; align-content: start; gap: 20px; overflow-y: auto; }
.nav-section > p { margin: 0 10px 7px; color: rgba(255,255,255,.42); font-size: 12px; font-weight: 800; letter-spacing: .1em; text-transform: uppercase; }
.nav-link { display: flex; width: 100%; align-items: center; gap: 12px; min-height: 42px; padding: 0 12px; color: rgba(255,255,255,.68); background: transparent; border: 0; border-radius: 10px; cursor: pointer; text-align: left; transition: .18s ease; }
.nav-link span { flex: 1; font-size: 10px; font-weight: 600; }
.nav-link b { min-width: 22px; padding: 2px 6px; color: rgba(255,255,255,.52); background: rgba(255,255,255,.07); border-radius: 999px; font-size: 10px; text-align: center; }
.nav-link:hover { color: #fff; background: rgba(255,255,255,.06); }
.nav-link.active { color: var(--crm-brand-ink); background: var(--crm-teal); box-shadow: 0 7px 18px rgba(254,153,0,.16); }
.nav-link.active b { color: var(--crm-brand-ink); background: rgba(255,255,255,.5); }
.app-main { width: calc(100% - 260px); min-width: 0; margin-left: 260px; transition: width .22s ease, margin-left .22s ease; }
.semicrm-app.is-sidebar-collapsed .app-sidebar { transform: translateX(-100%); }
.semicrm-app.is-sidebar-collapsed .app-main { width: 100%; margin-left: 0; }
.topbar { position: sticky; top: 0; z-index: 20; display: flex; height: 70px; align-items: center; justify-content: space-between; padding: 0 28px; background: rgba(246,244,240,.92); border-bottom: 1px solid var(--crm-line); backdrop-filter: blur(12px); }
.topbar-start, .topbar-end { display: flex; align-items: center; gap: 14px; }
.locale-control { position: relative; }
.locale-toggle { display: inline-flex; height: 38px; align-items: center; gap: 7px; padding: 0 10px; color: var(--crm-text-muted); background: #fff; border: 1px solid var(--crm-line); border-radius: 10px; cursor: pointer; font: inherit; font-size: 11px; font-weight: 700; }
.locale-toggle:hover { color: var(--crm-navy); border-color: var(--crm-line-strong); }
.locale-menu { position: absolute; top: 46px; right: 0; z-index: 40; display: grid; min-width: 142px; padding: 5px; background: #fff; border: 1px solid var(--crm-line); border-radius: 10px; box-shadow: 0 14px 34px rgba(25, 43, 52, .14); }
.locale-menu button { padding: 9px 10px; color: var(--crm-text-muted); background: transparent; border: 0; border-radius: 7px; cursor: pointer; font: inherit; font-size: 11px; text-align: left; }
.locale-menu button:hover, .locale-menu button.selected { color: var(--crm-navy); background: var(--crm-surface-muted); }
.icon-button { position: relative; display: grid; width: 38px; height: 38px; place-items: center; color: var(--crm-text-muted); background: #fff; border: 1px solid var(--crm-line); border-radius: 10px; cursor: pointer; }
.menu-button { display: none; }
.global-search { display: flex; width: min(390px, 32vw); height: 40px; align-items: center; gap: 9px; padding: 0 11px; color: var(--crm-text-muted); background: #fff; border: 1px solid var(--crm-line); border-radius: 11px; }
.global-search:focus-within { border-color: rgba(254,153,0,.72); box-shadow: 0 0 0 3px rgba(254,153,0,.11); }
.global-search input { min-width: 0; flex: 1; color: var(--crm-text); background: transparent; border: 0; outline: 0; }
.global-search input::placeholder { color: #9ba9ac; }
.global-search kbd { padding: 2px 6px; color: #879699; background: var(--crm-surface-muted); border: 1px solid var(--crm-line); border-radius: 5px; font-size: 10px; }
.notification-button b { position: absolute; top: -4px; right: -4px; display: grid; width: 17px; height: 17px; place-items: center; color: #fff; background: var(--crm-danger); border: 2px solid var(--crm-surface); border-radius: 50%; font-size: 8px; }
.notification-control { position: relative; }
.notification-center { position: absolute; top: 47px; right: 0; z-index: 40; width: min(390px, calc(100vw - 32px)); overflow: hidden; background: #fff; border: 1px solid var(--crm-line); border-radius: 14px; box-shadow: 0 18px 48px rgba(25, 43, 52, .16); }
.notification-center > header { display: flex; align-items: center; justify-content: space-between; padding: 16px 17px 13px; border-bottom: 1px solid var(--crm-line); }
.notification-center > header div { display: grid; gap: 3px; }
.notification-center > header span { color: var(--crm-warning); font-size: 9px; font-weight: 800; letter-spacing: .13em; }
.notification-center > header strong { color: var(--crm-navy); font-size: 15px; }
.notification-center > header button { color: var(--crm-teal); background: transparent; border: 0; font-size: 11px; font-weight: 700; cursor: pointer; }
.notification-center > header button:disabled { color: var(--crm-text-muted); cursor: default; }
.notification-list { max-height: 430px; overflow: auto; }
.notification-list > button { position: relative; display: grid; width: 100%; grid-template-columns: 8px 1fr; gap: 9px; padding: 13px 16px; color: var(--crm-text); background: #fff; border: 0; border-bottom: 1px solid var(--crm-line); cursor: pointer; text-align: left; }
.notification-list > button:hover { background: var(--crm-surface); }
.notification-list > button.unread { background: #f4faf9; }
.notification-list > button > i { width: 6px; height: 6px; margin-top: 5px; background: transparent; border-radius: 50%; }
.notification-list > button.unread > i { background: var(--crm-warning); }
.notification-list > button > span { display: grid; gap: 4px; min-width: 0; }
.notification-list em { color: var(--crm-teal); font-size: 9px; font-style: normal; font-weight: 800; letter-spacing: .08em; text-transform: uppercase; }
.notification-list strong { color: var(--crm-navy); font-size: 12px; }
.notification-list small { overflow: hidden; color: var(--crm-text-muted); font-size: 11px; line-height: 1.45; text-overflow: ellipsis; white-space: nowrap; }
.notification-list time { color: var(--crm-text-muted); font-size: 10px; }
.notification-list > p { margin: 0; padding: 28px 16px; color: var(--crm-text-muted); font-size: 11px; text-align: center; }
.notification-load-more { width: 100%; min-height: 38px; color: var(--crm-teal); background: #fff; border: 0; border-top: 1px solid var(--crm-line); font-size: 11px; font-weight: 700; cursor: pointer; }
.notification-load-more:disabled { color: var(--crm-text-muted); cursor: default; }
.user-menu { display: flex; align-items: center; gap: 9px; padding: 4px 6px 4px 4px; color: var(--crm-text); background: transparent; border: 0; border-radius: 11px; cursor: pointer; text-align: left; }
.identity-control { position: relative; }
.account-center { position: absolute; top: calc(100% + 10px); right: 0; z-index: 50; width: min(360px, calc(100vw - 32px)); overflow: hidden; background: #fff; border: 1px solid var(--crm-line); border-radius: 13px; box-shadow: 0 20px 50px rgba(8,32,40,.18); }
.account-center > header { display: flex; align-items: center; gap: 10px; padding: 14px 16px; background: var(--crm-surface); border-bottom: 1px solid var(--crm-line); }
.account-center-title { display: grid; gap: 2px; }
.account-center > header strong { color: var(--crm-navy); font-size: 12px; }
.account-center > header small { color: var(--crm-text-muted); font-size: 7px; font-weight: 800; letter-spacing: .12em; }
.account-center-icon { display: grid; width: 34px; height: 34px; place-items: center; color: var(--crm-brand-ink); background: var(--crm-teal); border-radius: 9px; }
.account-profile { display: grid; gap: 3px; padding: 14px 16px; border-bottom: 1px solid var(--crm-line); }
.account-center-close { display: grid; margin-left: auto; width: 30px; height: 30px; flex: 0 0 auto; place-items: center; padding: 0; color: var(--crm-text-muted); background: transparent; border: 1px solid transparent; border-radius: 8px; cursor: pointer; }
.account-center-close:hover { color: var(--crm-navy); background: var(--crm-teal-soft); border-color: var(--crm-line); }
.account-center-close:focus-visible { outline: 2px solid rgba(254,153,0,.72); outline-offset: 2px; }
.account-profile strong { color: var(--crm-navy); font-size: 12px; }
.account-profile small { color: var(--crm-text-muted); font-size: 8px; }
.account-profile span { margin-top: 4px; color: var(--crm-teal-ink); font-size: 8px; font-weight: 700; }
.password-setting { display: grid; gap: 10px; padding: 15px 16px 16px; }
.password-setting h3 { display: flex; align-items: center; gap: 7px; margin: 0; color: var(--crm-navy); font-size: 11px; }
.password-setting label { display: grid; gap: 5px; color: var(--crm-text-muted); font-size: 8px; font-weight: 700; }
.password-setting input { width: 100%; min-height: 36px; padding: 0 10px; color: var(--crm-text); background: #fff; border: 1px solid var(--crm-line); border-radius: 8px; outline: 0; }
.password-setting input:focus { border-color: rgba(254,153,0,.72); box-shadow: 0 0 0 3px rgba(254,153,0,.11); }
.password-setting > small { margin: 0; color: var(--crm-text-muted); font-size: 8px; line-height: 1.5; }
.account-error,.account-success { margin: 0; padding: 8px 9px; border-radius: 7px; font-size: 8px; font-weight: 700; }
.account-error { color: var(--crm-danger); background: #fff1f0; }
.account-success { color: var(--crm-positive-ink); background: #f2f6df; }
.password-setting .primary-button { width: 100%; justify-content: center; }
.settings-avatar { color: var(--crm-brand-ink); }
.identity-menu { position: absolute; top: calc(100% + 10px); right: 0; z-index: 50; width: 300px; padding: 8px; background: #fff; border: 1px solid var(--crm-line); border-radius: 13px; box-shadow: 0 20px 50px rgba(8,32,40,.18); }
.identity-menu header { display: grid; gap: 3px; padding: 8px 9px 10px; border-bottom: 1px solid var(--crm-line); }
.identity-menu header strong { color: var(--crm-navy); font-size: 11px; }.identity-menu header span { color: var(--crm-text-muted); font-size: 8px; }
.identity-menu > button { display: grid; width: 100%; grid-template-columns: 34px minmax(0,1fr) 18px; align-items: center; gap: 9px; padding: 9px; color: var(--crm-text); background: transparent; border: 0; border-radius: 9px; cursor: pointer; text-align: left; }
.identity-menu > button:hover,.identity-menu > button.active { color: var(--crm-brand-ink); background: var(--crm-teal-soft); }.identity-menu > button > span:nth-child(2) { display: grid; gap: 2px; }.identity-menu > button strong { font-size: 10px; }.identity-menu > button small { overflow: hidden; color: var(--crm-text-muted); font-size: 8px; text-overflow: ellipsis; white-space: nowrap; }.identity-menu > button > svg { color: var(--crm-brand-strong); }
.identity-avatar { width: 30px; height: 30px; border-radius: 8px; }
.identity-notice { position: fixed; top: 82px; right: 28px; z-index: 19; margin: 0; padding: 9px 12px; color: var(--crm-positive-ink); background: #f2f6df; border: 1px solid #dce5ae; border-radius: 9px; box-shadow: 0 8px 24px rgba(31,35,41,.08); font-size: 9px; font-weight: 700; }
.user-menu > span:not(.avatar) { display: grid; gap: 1px; }
.user-menu strong { font-size: 12px; }
.user-menu small { color: var(--crm-text-muted); font-size: 10px; }
.avatar { display: grid; width: 34px; height: 34px; place-items: center; color: var(--crm-brand-ink); background: var(--crm-teal); border-radius: 10px; font-size: 11px; font-weight: 800; }
.route-content { width: 100%; max-width: 1600px; min-height: calc(100vh - 70px); margin: 0 auto; padding: 28px; }
.nav-scrim { position: fixed; inset: 0; z-index: 25; background: rgba(7,29,37,.55); border: 0; }
.route-placeholder { display: grid; min-height: 400px; place-items: center; color: var(--crm-text-muted); }
.semicrm-app.is-embedded { height: 100%; min-height: 720px; }
.semicrm-app.is-embedded .app-sidebar, .semicrm-app.is-embedded .nav-scrim { position: absolute; }
.semicrm-app.is-embedded .app-main { min-height: 720px; }
.semicrm-app.is-embedded .route-content { min-height: 650px; }
.icon-button:disabled, .user-menu:disabled { opacity: .62; cursor: not-allowed; }
@media (max-width: 1199px) {
  .app-sidebar { width: 232px; }
  .app-main { width: calc(100% - 232px); margin-left: 232px; }
}
@media (max-width: 839px) {
  .app-sidebar { width: min(86vw, 292px); transform: translateX(-102%); box-shadow: 20px 0 50px rgba(8,32,40,.25); transition: transform .22s ease; }
  .app-sidebar.is-open { transform: translateX(0); }
  .sidebar-close, .menu-button { display: grid; }
  .sidebar-collapse-button, .desktop-sidebar-expand { display: none; }
  .app-main { width: 100%; margin-left: 0; }
  .topbar { height: 62px; padding: 0 16px; }
  .global-search { width: min(58vw, 320px); }
  .global-search kbd, .user-menu > span:not(.avatar), .user-menu > svg { display: none; }
  .route-content { min-height: calc(100vh - 62px); padding: 20px 16px 36px; }
}
@media (max-width: 520px) {
  .global-search { width: calc(100vw - 134px); }
}
</style>
