export function downloadBlob(blob: Blob, fileName: string) {
  const url = URL.createObjectURL(blob)
  const link = Object.assign(document.createElement('a'), { href: url, download: fileName })
  link.rel = 'noopener'
  link.style.display = 'none'
  document.body.append(link)
  try {
    link.click()
  } catch (reason) {
    link.remove()
    URL.revokeObjectURL(url)
    throw reason
  }
  window.setTimeout(() => {
    link.remove()
    URL.revokeObjectURL(url)
  }, 30_000)
}
