<script setup lang="ts">
import { personnelDisplayName } from '@/demo/personnel'
import { computed, onMounted, ref } from 'vue'
import { Network, Plus, UserRoundCheck } from '@lucide/vue'
import { api as defaultApi, type CrmApi } from '@/api'
import { mapRequestError } from '@/api/request-state'
import { useAppStore } from '@/stores/app'
import type { AccountSummaryDto, BuyingRole, ContactDto, CreateStakeholderInput, Tone } from '@/types/crm'
import { buildStakeholderForest, type StakeholderNode } from '@/domain/stakeholders'
import PageHeader from '@/design-system/PageHeader.vue'
import DataState from '@/design-system/DataState.vue'
import StatusBadge from '@/design-system/StatusBadge.vue'
import SectionCard from '@/design-system/SectionCard.vue'
import StakeholderModal from '@/features/stakeholders/StakeholderModal.vue'

const props = withDefaults(defineProps<{ apiClient?: CrmApi }>(), { apiClient: () => defaultApi })
const app = useAppStore()
const accounts = ref<AccountSummaryDto[]>([]), contacts = ref<ContactDto[]>([]), selectedId = ref(''), loading = ref(false), busy = ref(false), error = ref(''), requestId = ref('')
const modal = ref(false), editing = ref<ContactDto | null>(null)
const canWrite = computed(() => app.can('stakeholder:write'))
const selectedAccount = computed(() => accounts.value.find((item) => item.id === selectedId.value))
const forest = computed(() => buildStakeholderForest(contacts.value))
const flatTree = computed(() => {
  const rows: Array<{ node: StakeholderNode; depth: number }> = []
  const visit = (nodes: StakeholderNode[], depth: number) => nodes.forEach((node) => { rows.push({ node, depth }); visit(node.children, depth + 1) })
  visit(forest.value, 0)
  return rows
})
const criticalRoles: BuyingRole[] = ['Decision Maker', 'Economic Buyer', 'Technical Champion']
const roleCoverage = computed(() => criticalRoles.map((role) => ({ role, covered: contacts.value.some((item) => item.role === role) })))
const relationshipTone = (value: ContactDto['relationship']): Tone => value === 'Strong' ? 'positive' : value === 'Weak' ? 'danger' : 'warning'

async function loadContacts() {
  if (!selectedId.value) return
  loading.value = true; error.value = ''
  try { contacts.value = (await props.apiClient.listStakeholders({ accountId: selectedId.value })).data.items }
  catch (reason) { const mapped = mapRequestError(reason); error.value = mapped.message; requestId.value = mapped.requestId }
  finally { loading.value = false }
}
async function load() {
  loading.value = true
  try {
    accounts.value = (await props.apiClient.listAccounts({ pageSize: 100 })).data.items
    selectedId.value = selectedId.value || accounts.value[0]?.id || ''
    await loadContacts()
  } catch (reason) { const mapped = mapRequestError(reason); error.value = mapped.message; requestId.value = mapped.requestId; loading.value = false }
}
function selectAccount(id: string) { selectedId.value = id; void loadContacts() }
function open(contact: ContactDto | null = null) { editing.value = contact; modal.value = true }
async function save(payload: CreateStakeholderInput) {
  busy.value = true; error.value = ''
  try {
    if (editing.value) await props.apiClient.updateStakeholder(editing.value.id, payload, editing.value.modified)
    else await props.apiClient.createStakeholder(payload)
    modal.value = false; editing.value = null; await loadContacts()
  }
  catch (reason) { const mapped = mapRequestError(reason); error.value = mapped.message; requestId.value = mapped.requestId }
  finally { busy.value = false }
}
onMounted(async () => {
  await app.loadBootstrap(props.apiClient)
  await load()
})
</script>

<template>
  <div class="stakeholder-page">
    <PageHeader eyebrow="STAKEHOLDER MAP" title="关键人与组织关系" description="维护购买角色、影响力、关系强度和真实汇报关系；未知信息保持为空。">
      <button v-if="canWrite && selectedAccount" class="primary-button" type="button" data-testid="new-stakeholder" @click="open()"><Plus :size="15" />新增关键人</button>
    </PageHeader>

    <section class="stakeholder-workspace">
      <aside class="account-rail">
        <button v-for="account in accounts" :key="account.id" type="button" :class="{ active: account.id === selectedId }" @click="selectAccount(account.id)">
          <span>{{ account.shortName.slice(0, 2) }}</span><div><strong>{{ account.shortName }}</strong><small>{{ account.name }}</small><em>{{ personnelDisplayName(account.owner) }} · {{ account.segment }}</em></div>
        </button>
      </aside>

      <main class="relationship-panel">
        <p v-if="error" class="form-error">{{ error }}<small v-if="requestId">Request ID {{ requestId }}</small></p>
        <template v-if="selectedAccount">
          <header class="account-heading"><div><span>{{ selectedAccount.segment }} · {{ selectedAccount.region }}</span><h2>{{ selectedAccount.name }}</h2><p>{{ contacts.length }} 位详细关键人 · 详情记录为人数事实来源</p></div><Network :size="32" /></header>
          <div class="role-coverage"><span v-for="item in roleCoverage" :key="item.role" :class="{ missing: !item.covered }"><UserRoundCheck :size="13" />{{ item.covered ? `${item.role} 已覆盖` : `缺少 ${item.role}` }}</span></div>

          <DataState v-if="loading && !contacts.length" type="loading" />
          <template v-else>
            <SectionCard title="组织关系图" eyebrow="REPORTING STRUCTURE" description="只显示已明确维护的汇报线；没有关系的关键人作为根节点。">
              <DataState v-if="!flatTree.length" type="empty" title="还没有关键人" message="新增后可维护购买角色与组织关系。" />
              <div v-else class="org-tree">
                <button v-for="item in flatTree" :key="item.node.contact.id" type="button" :style="{ '--depth': item.depth }" @click="open(item.node.contact)">
                  <i>{{ item.node.contact.name.slice(0, 1) }}</i><div><strong>{{ item.node.contact.name }}</strong><small>{{ item.node.contact.title }} · {{ item.node.contact.department }}</small></div><StatusBadge :label="item.node.contact.role ?? 'Unassigned'" tone="info" /><em v-if="item.node.dataQuality">{{ item.node.dataQuality === 'cycle' ? '循环汇报关系' : '上级记录缺失' }}</em>
                </button>
              </div>
            </SectionCard>

            <SectionCard class="contact-table-card" title="关键人明细" eyebrow="CONTACT DETAILS" description="邮箱和汇报对象未提供时显示“—”。">
              <div class="table-scroll"><table class="crm-table stakeholder-table"><thead><tr><th>关键人</th><th>购买角色</th><th>影响力</th><th>关系</th><th>汇报对象</th><th>邮箱</th><th v-if="canWrite">操作</th></tr></thead><tbody><tr v-for="contact in contacts" :key="contact.id"><td><strong>{{ contact.name }}</strong><small>{{ contact.title }} · {{ contact.department }}</small></td><td><StatusBadge :label="contact.role ?? 'Unassigned'" tone="info" /></td><td>{{ contact.influence }}</td><td><StatusBadge :label="contact.relationship" :tone="relationshipTone(contact.relationship)" /></td><td>{{ contacts.find((item) => item.id === contact.reportsTo)?.name || '—' }}</td><td>{{ contact.email || '—' }}</td><td v-if="canWrite"><button class="text-button" type="button" @click="open(contact)">编辑</button></td></tr></tbody></table></div>
            </SectionCard>
          </template>
        </template>
      </main>
    </section>

    <StakeholderModal v-if="modal && selectedAccount" :account-id="selectedAccount.id" :contact="editing" :contacts="contacts" :busy="busy" @close="modal = false" @submit="save" />
  </div>
</template>

<style scoped>
.primary-button{display:flex;align-items:center;gap:7px}.stakeholder-workspace{display:grid;grid-template-columns:250px minmax(0,1fr);min-height:680px;overflow:hidden;background:#fff;border:1px solid var(--crm-line);border-radius:14px}.account-rail{padding:12px;background:#FAF8F5;border-right:1px solid var(--crm-line)}.account-search{display:flex;height:36px;align-items:center;gap:7px;margin-bottom:10px;padding:0 10px;color:var(--crm-text-muted);background:#fff;border:1px solid var(--crm-line);border-radius:9px}.account-search input{min-width:0;flex:1;border:0;outline:0;font-size:10px}.account-rail>button{display:grid;width:100%;grid-template-columns:34px 1fr;align-items:start;gap:10px;margin-bottom:5px;padding:11px;color:var(--crm-text);text-align:left;background:transparent;border:1px solid transparent;border-radius:10px;cursor:pointer}.account-rail>button.active{background:#fff;border-color:#F3C173;box-shadow:0 3px 10px rgba(31,35,41,.05)}.account-rail>button>span{display:grid;width:34px;height:34px;place-items:center;color:#fff;background:var(--crm-navy);border-radius:9px;font-size:9px;font-weight:800}.account-rail button div{display:grid;min-width:0;gap:3px}.account-rail strong{font-size:10px}.account-rail small{overflow:hidden;color:var(--crm-text-muted);font-size:8px;text-overflow:ellipsis;white-space:nowrap}.account-rail em{color:var(--crm-teal);font-size:8px;font-style:normal}.relationship-panel{min-width:0;padding:20px;background:var(--crm-surface)}.account-heading{display:flex;align-items:center;justify-content:space-between;margin-bottom:12px;padding:4px 2px;color:var(--crm-teal)}.account-heading span{font-size:8px;font-weight:800;letter-spacing:.1em}.account-heading h2{margin:4px 0;font-size:19px}.account-heading p{margin:0;color:var(--crm-text-muted);font-size:9px}.role-coverage{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:14px}.role-coverage span{display:flex;align-items:center;gap:5px;padding:7px 9px;color:var(--crm-positive-ink);background:#f0f5dd;border:1px solid #dfe8b9;border-radius:999px;font-size:8px;font-weight:700}.role-coverage .missing{color:#8a6221;background:#fff5df;border-color:#eedaa6}.org-tree{display:grid;gap:7px}.org-tree>button{--depth:0;position:relative;display:grid;grid-template-columns:34px minmax(0,1fr) auto auto;align-items:center;gap:10px;margin-left:calc(var(--depth) * 34px);padding:9px 11px;text-align:left;background:#FFFBF5;border:1px solid var(--crm-line);border-radius:10px;cursor:pointer}.org-tree>button i{display:grid;width:32px;height:32px;place-items:center;color:var(--crm-brand-ink);background:var(--crm-teal);border-radius:50%;font-size:10px;font-style:normal;font-weight:800}.org-tree>button div{display:grid;gap:3px}.org-tree strong{font-size:10px}.org-tree small{color:var(--crm-text-muted);font-size:8px}.org-tree em{color:var(--crm-danger);font-size:8px;font-style:normal}.contact-table-card{margin-top:14px}.table-scroll{overflow:auto}.stakeholder-table{min-width:860px}.stakeholder-table td strong{display:block;font-size:10px}.stakeholder-table td small{display:block;margin-top:4px;color:var(--crm-text-muted);font-size:8px}.text-button{color:var(--crm-teal);background:transparent;border:0;font-size:9px;font-weight:700;cursor:pointer}.form-error{display:flex;justify-content:space-between;padding:10px 12px;color:var(--crm-danger);background:var(--crm-danger-soft);border-radius:9px;font-size:10px}@media(max-width:800px){.stakeholder-workspace{grid-template-columns:1fr}.account-rail{display:flex;overflow:auto;border-right:0;border-bottom:1px solid var(--crm-line)}.account-search{min-width:180px}.account-rail>button{min-width:190px}.org-tree>button{margin-left:calc(var(--depth) * 14px)}}
</style>
