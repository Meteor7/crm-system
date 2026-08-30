<script setup lang="ts">
import { personnelDisplayName } from '@/demo/personnel'
import { computed, onMounted, ref, watch } from 'vue'
import { ArrowLeft, Building2, CalendarClock, CircleDollarSign, Cpu, ExternalLink, PackageCheck, UserRound } from '@lucide/vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { api as defaultApi, type CrmApi } from '@/api'
import { mapRequestError } from '@/api/request-state'
import type { BookingDto, Tone } from '@/types/crm'
import type { InstalledToolDto } from '@/types/workspaces'
import DataState from '@/design-system/DataState.vue'
import PageHeader from '@/design-system/PageHeader.vue'
import SectionCard from '@/design-system/SectionCard.vue'
import StatusBadge from '@/design-system/StatusBadge.vue'
import { formatMoney } from '@/domain/money'
import { formatDisplayDate } from '@/domain/time'
import { useAppStore } from '@/stores/app'

const props = withDefaults(defineProps<{ apiClient?: CrmApi }>(), { apiClient: () => defaultApi })
const route = useRoute()
const router = useRouter()
const app = useAppStore()
const canDelete = computed(() => app.bootstrap?.user.role === 'Manager')
const booking = ref<BookingDto | null>(null)
const tools = ref<InstalledToolDto[]>([])
const loading = ref(false)
const error = ref('')
const requestId = ref('')
const deleting = ref(false), deleteError = ref(''), deleteRequestId = ref('')
const equipmentWarning = ref('')
let loadSequence = 0
async function deleteBooking() {
  if (!booking.value || deleting.value || !window.confirm(`确认删除 Booking ${booking.value.id}？`)) return
  deleting.value = true
  deleteError.value = ''
  deleteRequestId.value = ''
  try {
    await props.apiClient.deleteBooking(booking.value.id)
    await router.push({ name: 'booking' })
  } catch (reason) {
    const mapped = mapRequestError(reason)
    deleteError.value = mapped.message
    deleteRequestId.value = mapped.requestId
  } finally {
    deleting.value = false
  }
}
const bookingId = computed(() => String(route.params.bookingId || ''))
const relatedTools = computed(() => tools.value.filter((item) => item.sourceBookingId === bookingId.value || item.id === booking.value?.installedToolId))
const statusTone = computed<Tone>(() => booking.value?.status === 'Confirmed' || booking.value?.status === 'Completed' ? 'positive' : booking.value?.status === 'Cancelled' ? 'danger' : 'warning')

async function load() {
  const sequence = ++loadSequence
  loading.value = true
  error.value = ''
  requestId.value = ''
  equipmentWarning.value = ''
  booking.value = null
  tools.value = []
  const pipelineResult = await Promise.resolve(props.apiClient.listPipeline({})).then(
    (value) => ({ status: 'fulfilled' as const, value }),
    (reason) => ({ status: 'rejected' as const, reason }),
  )
  if (sequence !== loadSequence) return
  if (pipelineResult.status === 'rejected') {
    const mapped = mapRequestError(pipelineResult.reason)
    error.value = mapped.message
    requestId.value = mapped.requestId
  } else {
    booking.value = pipelineResult.value.data.bookings.find((item) => item.id === bookingId.value) ?? null
    if (!booking.value) error.value = `未找到 Booking ${bookingId.value}`
  }
  if (booking.value?.installedToolId) {
    try {
      const toolResult = await props.apiClient.getInstalledTool(booking.value.installedToolId)
      if (sequence !== loadSequence) return
      tools.value = [toolResult.data]
    } catch (reason) {
      if (sequence !== loadSequence) return
      const mapped = mapRequestError(reason)
      equipmentWarning.value = mapped.requestId
        ? `${mapped.message}（Request ID: ${mapped.requestId}）`
        : mapped.message
    }
  }
  if (sequence === loadSequence) loading.value = false
}

watch(bookingId, load)
onMounted(load)
</script>

<template>
  <div class="booking-detail-page">
    <DataState v-if="loading && !booking" type="loading" />
    <DataState v-else-if="error || !booking" type="error" :message="error || '未找到 Booking'" :request-id="requestId" @retry="load" />
    <template v-else>
      <RouterLink class="detail-back-button" :to="{ name: 'booking' }"><ArrowLeft :size="14" />返回 Booking 列表</RouterLink>
      <PageHeader eyebrow="BOOKING DETAIL" :title="booking.title" :description="`${booking.id} · ${booking.accountName} · Owner ${personnelDisplayName(booking.owner)}`"><button v-if="canDelete" class="danger-button" type="button" data-delete-booking :disabled="deleting" @click="deleteBooking">删除 Booking</button></PageHeader>
      <p v-if="deleteError" class="form-error" data-delete-error>{{ deleteError }}<small v-if="deleteRequestId">Request ID {{ deleteRequestId }}</small></p>

      <section class="booking-summary">
        <article><span><PackageCheck :size="18" /></span><div><small>当前状态</small><StatusBadge :label="booking.status" :tone="statusTone" /></div></article>
        <article><span><CircleDollarSign :size="18" /></span><div><small>Booking 金额</small><strong>{{ formatMoney(booking.amount, booking.currency) }}</strong></div></article>
        <article><span><CalendarClock :size="18" /></span><div><small>客户 DDL</small><strong>{{ formatDisplayDate(booking.ddl) }}</strong></div></article>
        <article><span><Cpu :size="18" /></span><div><small>设备数量</small><strong>{{ booking.quantity }} 台 / 项</strong></div></article>
      </section>

      <div class="booking-detail-grid">
        <div class="booking-main">
          <SectionCard title="Booking 信息" eyebrow="INFORMATION">
            <dl class="booking-fields">
              <div><dt>Booking 编号</dt><dd>{{ booking.id }}</dd></div><div><dt>录入日期</dt><dd>{{ formatDisplayDate(booking.bookingDate) }}</dd></div>
              <div><dt>设备需求</dt><dd>{{ booking.equipment }}</dd></div><div><dt>数量</dt><dd>{{ booking.quantity }} 台 / 项</dd></div>
              <div><dt>来源类型</dt><dd><StatusBadge :label="booking.source" :tone="booking.source === 'Opportunity' ? 'info' : 'neutral'" /></dd></div>
              <div><dt>Owner</dt><dd>{{ personnelDisplayName(booking.owner) }}</dd></div><div class="wide"><dt>备注</dt><dd>{{ booking.note || '—' }}</dd></div>
            </dl>
          </SectionCard>
          <SectionCard title="业务关联" eyebrow="RELATED BUSINESS">
            <div class="related-links">
              <RouterLink :to="{ name: 'account-detail', params: { accountId: booking.accountId } }"><span><Building2 :size="15" />客户</span><strong>{{ booking.accountName }}</strong><ExternalLink :size="13" /></RouterLink>
              <RouterLink v-if="booking.primaryContactId" :to="{ name: 'contact-detail', params: { contactId: booking.primaryContactId } }"><span><UserRound :size="15" />主联系人</span><strong>{{ booking.customerContact }}</strong><ExternalLink :size="13" /></RouterLink>
              <RouterLink v-if="booking.sourceOpportunityId" :to="{ name: 'opportunity-detail', params: { opportunityId: booking.sourceOpportunityId } }"><span><CircleDollarSign :size="15" />来源 Opportunity</span><strong>{{ booking.sourceOpportunityId }}</strong><ExternalLink :size="13" /></RouterLink>
            </div>
          </SectionCard>
        </div>
        <aside>
          <SectionCard title="设备关联" eyebrow="INSTALLED TOOL">
            <p v-if="equipmentWarning" class="equipment-note">{{ equipmentWarning }}</p>
            <div v-else-if="relatedTools.length" class="tool-list">
              <article v-for="tool in relatedTools" :key="tool.id" :data-booking-tool="tool.id"><header><strong>{{ tool.model }}</strong><StatusBadge :label="tool.status" :tone="tool.status === 'Active' ? 'positive' : 'warning'" /></header><b>{{ tool.serial }}</b><p>{{ tool.site }} · {{ tool.location }}</p><small>{{ personnelDisplayName(tool.engineerOwner) }}</small></article>
            </div>
            <p v-else class="equipment-note">该 Booking 尚未转入 Installed Tool。</p>
            <RouterLink class="installed-link" :to="{ name: 'installed-tools', query: { accountId: booking.accountId } }">查看设备管理<ExternalLink :size="13" /></RouterLink>
          </SectionCard>
        </aside>
      </div>
    </template>
  </div>
</template>

<style scoped>
.booking-detail-page{display:grid;gap:14px}.detail-back-button{justify-self:start}.booking-detail-page :deep(.page-header){margin-bottom:0}.booking-summary{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}.booking-summary article{display:flex;align-items:center;gap:10px;padding:14px;background:#fff;border:1px solid var(--crm-line);border-radius:12px}.booking-summary article>span{display:grid;width:38px;height:38px;place-items:center;color:var(--crm-brand-ink);background:var(--crm-teal-soft);border-radius:10px}.booking-summary article>div{display:grid;gap:5px}.booking-summary small{color:var(--crm-text-muted);font-size:9px}.booking-summary strong{color:var(--crm-navy);font-size:13px}.booking-detail-grid{display:grid;grid-template-columns:minmax(0,1fr) 290px;gap:14px;align-items:start}.booking-main{display:grid;gap:14px}.booking-detail-grid aside{position:sticky;top:16px}.booking-fields{display:grid;grid-template-columns:1fr 1fr;margin:0}.booking-fields div{display:grid;grid-template-columns:110px minmax(0,1fr);gap:10px;padding:12px 0;border-bottom:1px solid var(--crm-line)}.booking-fields div:nth-last-child(-n+2){border-bottom:0}.booking-fields .wide{grid-column:1/-1}.booking-fields dt{color:var(--crm-text-muted);font-size:10px}.booking-fields dd{margin:0;color:var(--crm-navy);font-size:11px;font-weight:700}.related-links{display:grid;gap:8px}.related-links a{display:grid;grid-template-columns:150px minmax(0,1fr) auto;align-items:center;gap:10px;padding:12px;color:var(--crm-navy);background:var(--crm-surface);border:1px solid var(--crm-line);border-radius:10px}.related-links span{display:flex;align-items:center;gap:6px;color:var(--crm-text-muted);font-size:10px}.related-links strong{overflow:hidden;font-size:11px;text-overflow:ellipsis;white-space:nowrap}.tool-list{display:grid;gap:9px}.tool-list article{display:grid;gap:6px;padding:11px;background:var(--crm-surface);border:1px solid var(--crm-line);border-radius:10px}.tool-list header{display:flex;align-items:center;justify-content:space-between;gap:7px}.tool-list header strong{font-size:11px}.tool-list b{color:var(--crm-teal);font-size:9px}.tool-list p,.tool-list small{margin:0;color:var(--crm-text-muted);font-size:9px}.equipment-note{margin:0;padding:18px 8px;color:var(--crm-text-muted);font-size:10px;line-height:1.6;text-align:center}.installed-link{display:flex;align-items:center;justify-content:space-between;margin-top:10px;padding-top:10px;color:var(--crm-teal);border-top:1px solid var(--crm-line);font-size:10px;font-weight:750}@media(max-width:1000px){.booking-summary{grid-template-columns:repeat(2,1fr)}.booking-detail-grid{grid-template-columns:1fr}.booking-detail-grid aside{position:static}}@media(max-width:620px){.booking-summary{grid-template-columns:1fr}.booking-fields{grid-template-columns:1fr}.booking-fields .wide{grid-column:auto}.booking-fields div,.related-links a{grid-template-columns:1fr}}
</style>
