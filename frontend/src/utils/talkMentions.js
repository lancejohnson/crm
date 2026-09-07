// @mention helpers for the Talk composer. Pure, shared by the next workspace
// (candidates come from the users store) and unit-tested with plain node.

// The word being typed after a trailing '@', or null when not mentioning.
export function mentionQuery(text) {
  const match = /(?:^|\s)@([\w.-]*)$/.exec(text || '')
  return match ? match[1] : null
}

// Users whose handle (before '@'), first name or full name starts with the query.
export function mentionCandidates(users, query, limit = 6) {
  const q = (query || '').toLowerCase()
  return (users || [])
    .filter((u) => {
      const handle = String(u.name || '').split('@')[0].toLowerCase()
      const full = String(u.full_name || '').toLowerCase()
      const first = String(u.first_name || '').toLowerCase()
      return !q || handle.startsWith(q) || full.startsWith(q) || first.startsWith(q)
    })
    .slice(0, limit)
}

// Replace the trailing '@partial' with '@handle ' (handle = login before '@').
export function insertMention(text, user) {
  const handle = String(user?.name || user || '').split('@')[0]
  return (text || '').replace(/@[\w.-]*$/, `@${handle} `)
}
