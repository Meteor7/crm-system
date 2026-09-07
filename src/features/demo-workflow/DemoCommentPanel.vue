<script setup lang="ts">
import { participantRoleLabel } from '@/features/shared/sales-i18n'
import { computed, ref } from 'vue'
import { AtSign, MessageSquareText, Send } from '@lucide/vue'
import type { DemoCommentDto } from '@/types/workspaces'
import { personnelDisplayName } from '@/demo/personnel'
import { formatDisplayDate } from '@/domain/time'
import { useI18n } from '@/i18n'

const props = withDefaults(defineProps<{
  comments: DemoCommentDto[]
  participants?: Array<{ id: string; name: string }>
  busy?: boolean
  error?: string
}>(), {
  participants: () => [],
  busy: false,
  error: '',
})

const emit = defineEmits<{ submit: [payload: { body: string; mentions: string[] }] }>()
const draft = ref('')
const mentions = ref<string[]>([])
const { locale } = useI18n()
const canSubmit = computed(() => Boolean(draft.value.trim()) && !props.busy)

function submit() {
  const body = draft.value.trim()
  if (!body || props.busy) return
  emit('submit', { body, mentions: [...mentions.value] })
  draft.value = ''
  mentions.value = []
}

function initials(name: string) {
  return name.split(/\s+/).map((part) => part[0]).join('').slice(0, 2).toUpperCase()
}

function commentMentions(comment: DemoCommentDto) {
  if (comment.mentionedPeople?.length) return comment.mentionedPeople
  return comment.mentionedPersonId
    ? [{ id: comment.mentionedPersonId, name: comment.mentionedPerson || comment.mentionedPersonId }]
    : []
}
</script>

<template>
  <section class="comment-panel" data-demo-comments>
    <form class="comment-composer" data-publish-demo-comment @submit.prevent="submit">
      <span class="composer-icon"><MessageSquareText :size="18" /></span>
      <label>
        <span>{{ locale === 'en-US' ? 'Project collaboration comment' : '项目协作 Comment' }}</span>
        <fieldset class="mention-picker" :aria-label="locale === 'en-US' ? 'Select members to mention' : '选择要提及的成员'">
          <legend><AtSign :size="14" />{{ locale === 'en-US' ? 'Mention members (multi-select)' : '提及成员（可多选）' }}</legend>
          <label v-for="person in participants" :key="person.id" :class="{ selected: mentions.includes(person.id) }">
            <input v-model="mentions" type="checkbox" :value="person.id" />@{{ person.name }}
          </label>
        </fieldset>
        <textarea
          v-model="draft"
          data-demo-comment-input
          :aria-label="locale === 'en-US' ? 'Project comment' : '项目 Comment'"
          :placeholder="locale === 'en-US' ? 'Share progress, risks, or items needing confirmation…' : '分享进展、风险或需要其他人员确认的事项…'"
          rows="3"
        />
      </label>
      <button class="primary-button" type="submit" :disabled="!canSubmit">
        <Send :size="14" />{{ busy ? (locale === 'en-US' ? 'Publishing…' : '发布中…') : (locale === 'en-US' ? 'Publish comment' : '发布 Comment') }}
      </button>
    </form>
    <p v-if="error" class="comment-error" role="alert">{{ error }}</p>

    <div v-if="comments.length" class="comment-feed">
      <article v-for="comment in comments" :key="comment.id" data-demo-comment>
        <span class="comment-avatar">{{ initials(personnelDisplayName(comment.author)) }}</span>
        <div>
          <header>
            <strong>{{ personnelDisplayName(comment.author) }}</strong>
            <small>{{ participantRoleLabel(comment.role, locale) }}</small>
            <time>{{ formatDisplayDate(comment.createdAt) }}</time>
          </header>
          <div v-if="commentMentions(comment).length" class="comment-mentions" :aria-label="locale === 'en-US' ? 'Mentioned members' : '提及成员'">
            <span v-for="person in commentMentions(comment)" :key="person.id">@{{ person.name }}</span>
          </div>
          <p>{{ comment.body }}</p>
        </div>
      </article>
    </div>
    <div v-else class="comment-empty">
      <MessageSquareText :size="24" />
      <strong>{{ locale === 'en-US' ? 'No comments yet' : '暂无 Comment' }}</strong>
      <span>{{ locale === 'en-US' ? 'Publish the first project collaboration update.' : '发布第一条项目协作记录。' }}</span>
    </div>
  </section>
</template>

<style scoped>
.comment-panel{display:grid;gap:14px}.comment-composer{display:grid;grid-template-columns:auto minmax(0,1fr) auto;align-items:end;gap:12px;padding:16px;background:#fff;border:1px solid var(--crm-line);border-radius:12px}.composer-icon{display:grid;width:38px;height:38px;place-items:center;align-self:start;color:#b85000;background:#fff0e4;border-radius:10px}.comment-composer label{display:grid;gap:7px;color:var(--crm-navy);font-size:11px;font-weight:800}.comment-composer textarea{min-height:76px;resize:vertical;padding:11px 12px;color:var(--crm-text);background:#fbfaf8;border:1px solid var(--crm-line);border-radius:9px;outline:0;font:inherit;font-size:11px;line-height:1.55}.comment-composer textarea:focus{border-color:#e88335;box-shadow:0 0 0 3px rgba(232,131,53,.13)}.comment-composer button{min-width:132px}.comment-error{margin:0;padding:10px 12px;color:var(--crm-danger);background:var(--crm-danger-soft);border:1px solid rgba(190,65,65,.18);border-radius:9px;font-size:10px}.comment-feed{display:grid;background:#fff;border:1px solid var(--crm-line);border-radius:12px}.comment-feed article{display:grid;grid-template-columns:auto minmax(0,1fr);gap:11px;padding:15px 16px;border-bottom:1px solid var(--crm-line)}.comment-feed article:last-child{border-bottom:0}.comment-avatar{display:grid;width:34px;height:34px;place-items:center;color:#6d3d19;background:#ffe4d1;border-radius:10px;font-size:10px;font-weight:850}.comment-feed article>div{display:grid;gap:7px}.comment-feed header{display:flex;align-items:center;gap:8px}.comment-feed header strong{color:var(--crm-navy);font-size:11px}.comment-feed header small,.comment-feed time{color:var(--crm-text-muted);font-size:9px}.comment-feed time{margin-left:auto}.comment-feed p{margin:0;color:var(--crm-text);font-size:11px;line-height:1.6;white-space:pre-wrap}.comment-empty{display:grid;min-height:210px;place-content:center;justify-items:center;gap:7px;color:var(--crm-text-muted);background:#fff;border:1px dashed var(--crm-line-strong);border-radius:12px;font-size:10px}.comment-empty strong{color:var(--crm-navy);font-size:12px}@media(max-width:680px){.comment-composer{grid-template-columns:auto 1fr}.comment-composer button{grid-column:2;width:100%}.comment-feed header{align-items:flex-start;flex-wrap:wrap}.comment-feed time{width:100%;margin-left:0}}
.mention-picker{display:flex;align-items:center;flex-wrap:wrap;gap:6px;margin:0;padding:0;border:0;color:var(--crm-teal);font-size:10px}.mention-picker legend{display:flex;align-items:center;gap:5px;margin-bottom:6px;font-weight:800}.mention-picker label{display:flex;align-items:center;gap:4px;padding:6px 8px;color:var(--crm-text-muted);background:#fff;border:1px solid var(--crm-line);border-radius:7px;cursor:pointer}.mention-picker label.selected{color:var(--crm-teal);background:var(--crm-teal-soft);border-color:var(--crm-teal)}.mention-picker input{width:14px;height:14px;margin:0;accent-color:var(--crm-teal)}.comment-mentions{display:flex;flex-wrap:wrap;gap:5px}.comment-mentions span{padding:4px 7px;color:var(--crm-teal);background:var(--crm-teal-soft);border-radius:6px;font-size:9px;font-weight:800}
</style>
