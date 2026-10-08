export const lossCategories = ['Price', 'Local competitor preferred', 'Specs / throughput', 'Budget cancelled or delayed', 'Delivery lead time', 'Other'] as const
const zh: Record<string, string> = { Price: '价格', 'Local competitor preferred': '优先选择本土竞品', 'Specs / throughput': '技术规格／产能', 'Budget cancelled or delayed': '预算取消或延期', 'Delivery lead time': '交期', Other: '其他', pending: '未分析', unclassified: '已复盘，分类待补全' }
export function lossCategoryLabel(value: string, locale: string) {
  return locale === 'en-US' ? ({ pending: 'Not yet analysed', unclassified: 'Reviewed, category missing' }[value] ?? value) : zh[value] ?? value
}
