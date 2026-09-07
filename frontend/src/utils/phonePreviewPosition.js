// A chat belongs to its status trigger, with clearance for the feedback edge tab.
export function previewChatPosition(rect, viewportWidth, viewportHeight) {
  const width = Math.min(300, viewportWidth - 48)
  const left = Math.max(12, Math.min(rect.left + rect.width / 2 - width / 2, viewportWidth - width - 36))
  const bottom = Math.max(12, Math.min(viewportHeight - rect.top + 8, viewportHeight - 120))
  return { left: `${left}px`, bottom: `${bottom}px`, width: `${width}px`, maxHeight: `${Math.max(100, Math.min(330, viewportHeight - bottom - 12))}px` }
}
