<script setup lang="ts">
import { computed } from 'vue'
import { personnelDisplayName } from '@/demo/personnel'
import { formatDisplayDateTime } from '@/domain/time'
import { lossCategoryLabel } from '@/features/cockpit/review-labels'
import { labels } from '@/features/cockpit/presentation'
import { useI18n } from '@/i18n'
import { useAppStore } from '@/stores/app'
import type { LossReviewDto, StrategyOpportunityDto } from '@/types/workspaces'

// Read-only record of every loss of this deal and its post-mortem; Managers record the post-mortem on Warnings.
const props = defineProps<{ opportunity: StrategyOpportunityDto }>()
const app = useAppStore()
const { locale } = useI18n()
const copy = (english: string, chinese: string) => locale.value === 'en-US' ? english : chinese
const reviews = computed(() => props.opportunity.lossReviews ?? [])
const manager = computed(() => app.bootstrap?.user.role === 'Manager')
const stage = (key: string) => labels[key]?.[locale.value === 'en-US' ? 1 : 0] ?? (key || '—')
const kinds: Record<string, [string, string]> = {
  Created: ['Loss recorded', '记录丢单'], Reviewed: ['Post-mortem done', '完成复盘'], ReviewUpdated: ['Conclusion edited', '修改结论'],
  ReviewReverted: ['Reverted to pending', '改回待分析'], Reopened: ['Deal reopened', '商机重开'],
}
const kind = (key: string) => kinds[key]?.[locale.value === 'en-US' ? 0 : 1] ?? key
function status(review: LossReviewDto) {
  if (review.reopenedAt) return { text: copy('Reopened', '已重开'), tone: 'muted' }
  return review.status === 'reviewed' ? { text: copy('Post-mortem done', '已复盘'), tone: 'done' } : { text: copy('Post-mortem pending', '待复盘'), tone: 'warn' }
}
</script>

<template>
  <section v-if="reviews.length" class="loss-review-card" data-testid="opportunity-loss-reviews">
    <header><h2>{{ copy('Lost-deal post-mortems', '丢单复盘') }}</h2><span>{{ reviews.length }}</span></header>
    <article v-for="review in reviews" :key="review.id" :data-loss-review-id="review.id">
      <div class="title"><strong>{{ copy('Lost at', '丢失于') }} {{ stage(review.lostAtStage) }}</strong><em :class="status(review).tone" data-loss-review-status>{{ status(review).text }}</em></div>
      <p class="meta">{{ personnelDisplayName(review.lostBy) }} · <time :datetime="review.lostAt">{{ formatDisplayDateTime(review.lostAt) }}</time><template v-if="review.reopenedAt"> · {{ copy('reopened', '重开于') }} <time :datetime="review.reopenedAt">{{ formatDisplayDateTime(review.reopenedAt) }}</time></template></p>
      <p><span class="label">{{ copy('Reason (Sales)', '丢单原因（销售）') }}</span>{{ review.lostReason || copy('Not recorded', '未记录') }}</p>
      <p v-if="review.status === 'reviewed'" data-loss-category><span class="label">{{ copy('Confirmed loss category', '复盘确认分类') }}</span>{{ lossCategoryLabel(review.reviewCategory || 'unclassified', locale) }}</p>
      <p v-if="review.reviewNote"><span class="label">{{ copy('Post-mortem conclusion', '复盘结论') }}</span><span class="note">{{ review.reviewNote }}</span></p>
      <p v-if="review.status === 'reviewed' && review.reviewedBy" class="meta">{{ copy('Confirmed by', '确认人') }} {{ personnelDisplayName(review.reviewedBy) }} · <time :datetime="review.reviewedAt ?? ''">{{ formatDisplayDateTime(review.reviewedAt ?? '') }}</time></p>
      <RouterLink v-if="manager && review.status === 'pending' && !review.reopenedAt" class="to-warnings" to="/warnings" data-loss-review-link>{{ copy('Record the post-mortem on Warnings', '到 Warnings 页记录复盘') }} →</RouterLink>
      <details v-if="review.history.length" class="history"><summary>{{ copy('Audit trail', '修改留痕') }} · {{ review.history.length }}</summary>
        <ol><li v-for="entry in review.history" :key="entry.id"><strong>{{ kind(entry.kind) }}</strong> · {{ personnelDisplayName(entry.actor) }} · <time :datetime="entry.at">{{ formatDisplayDateTime(entry.at) }}</time><p v-if="entry.category">{{ lossCategoryLabel(entry.category, locale) }}</p><p v-if="entry.reason">{{ copy('Reason', '原因') }}：{{ entry.reason }}</p><p v-else-if="entry.note && entry.kind !== 'Created' && entry.kind !== 'Reopened'">{{ entry.note }}</p></li></ol>
      </details>
    </article>
  </section>
</template>

<style scoped>
.loss-review-card{min-width:0;overflow:hidden;border:1px solid var(--crm-line);border-radius:12px;background:#fff}
header{display:flex;align-items:center;justify-content:space-between;padding:14px;background:#faf9f7;border-bottom:1px solid var(--crm-line)}
h2{margin:0;font-size:12px;color:var(--crm-navy)}
header span,.meta{font-size:10px;color:var(--crm-text-muted)}
article{padding:14px;border-bottom:1px solid var(--crm-line);font-size:11px;overflow-wrap:anywhere}
article:last-child{border-bottom:0}p{margin:8px 0;line-height:1.5}
.title{display:flex;align-items:center;justify-content:space-between;gap:8px}
.title em{padding:2px 8px;border-radius:999px;font-size:10px;font-style:normal;font-weight:700;white-space:nowrap}
.title em.warn{background:var(--crm-warning-soft);color:#9a5b00}.title em.done{background:#e8f5ee;color:var(--crm-positive-ink)}.title em.muted{background:var(--crm-surface-muted);color:var(--crm-text-muted)}
.label{display:block;margin-bottom:2px;font-size:10px;color:var(--crm-text-muted)}.note{white-space:pre-wrap}
.to-warnings{font-size:11px;font-weight:700;color:var(--crm-link);text-decoration:none}
.history{margin-top:10px}.history summary{cursor:pointer;color:var(--crm-teal)}.history ol{padding-left:18px}.history li{padding:4px 0;border-top:1px solid var(--crm-line)}
</style>
