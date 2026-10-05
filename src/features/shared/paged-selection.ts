import { computed, ref, watch, type Ref } from 'vue'

/**
 * Pages a list a workspace holds in full and keeps one of its records on show.
 *
 * The record on show is the one the page above holds as selected, and the page shown is the page that record is
 * on, wherever a save, another view or another filter puts it. Only when the list does not hold that record is
 * the page the workspace's own: the first one after the view or the filter changed, otherwise the one it was on,
 * as far as it still exists, with its first record on show.
 *
 * A record on show that the page above does not hold as selected is handed up through `select` when the user
 * turns to it and when the list is read again. A save moves a record to the top of the list; without this the
 * page would stay where it was, or would follow the record and show the one still held as selected in its place.
 * A record selected from outside is not replaced that way before the list has been read once: one just created
 * is selected before the list holds it, and in a view that does not show it, it stays selected for the view
 * that does.
 */
export function usePagedSelection<T extends { id: string }>(options: {
  rows: Readonly<Ref<T[]>>
  selectedId: () => string | undefined
  /** What the rows are narrowed by: the view and the filter. */
  narrowedBy: () => string
  pageSize: number
  select: (id: string) => void
}) {
  const page = ref(1), pageSize = ref(options.pageSize)
  const pagedRows = computed(() => options.rows.value.slice((page.value - 1) * pageSize.value, page.value * pageSize.value))
  const selected = computed(() => pagedRows.value.find((item) => item.id === options.selectedId()) ?? pagedRows.value[0] ?? null)
  // The pager stays while the list is longer than its smallest page, so that a larger page can be taken back.
  const paged = computed(() => options.rows.value.length > options.pageSize)
  // The record on show before the list last changed, and whether the selected record was chosen since the
  // list was last read.
  let shownId = '', awaited = false
  watch(() => [options.selectedId(), options.narrowedBy(), options.rows.value, pageSize.value] as const, ([id, narrowedBy, rows, size], previous) => {
    const pageOf = (index: number) => Math.floor(index / size) + 1
    if (id !== previous?.[0]) awaited = Boolean(id)
    const held = id ? rows.findIndex((item) => item.id === id) : -1
    const renarrowed = previous !== undefined && narrowedBy !== previous[1]
    const reread = previous !== undefined && !renarrowed && rows !== previous[2]
    const waited = awaited
    if (held >= 0 || reread) awaited = false
    if (held >= 0) { page.value = pageOf(held); return }
    const shown = reread && shownId ? rows.findIndex((item) => item.id === shownId) : -1
    if (shown >= 0) { page.value = pageOf(shown); if (!waited) options.select(shownId); return }
    page.value = renarrowed ? 1 : Math.min(page.value, Math.max(1, Math.ceil(rows.length / size)))
  }, { immediate: true })
  watch(selected, (item) => { shownId = item?.id ?? '' }, { immediate: true })

  /** The user turns the page: its first record is the one on show, and is handed up as the selected one. */
  function turnTo(next: number) {
    page.value = next
    const first = pagedRows.value[0]
    if (first) options.select(first.id)
  }
  return { page, pageSize, openingPageSize: options.pageSize, pagedRows, selected, paged, turnTo }
}
