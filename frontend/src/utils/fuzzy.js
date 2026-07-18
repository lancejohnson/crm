// Obsidian-style fuzzy match: every char in `q` must appear in `label` in
// order (subsequence), with bonuses for word-boundary hits and consecutive
// runs. Whitespace in `q` splits into ordered tokens — each token starts where
// the previous one ended. Returns null when no match (callers filter those out).
// Ported from the Atelier command palette so the CRM palette ranks the same way.
export function fuzzyScore(label, q) {
  const tokens = (q || '').toLowerCase().split(/\s+/).filter(Boolean)
  if (tokens.length === 0) return 0
  const l = (label || '').toLowerCase()
  let pos = 0
  let score = 0
  for (const tok of tokens) {
    let qi = 0
    let prev = -2
    let firstMatch = -1
    for (let i = pos; i < l.length && qi < tok.length; i++) {
      if (l[i] !== tok[qi]) continue
      if (firstMatch === -1) firstMatch = i
      if (i === 0 || /[\s_/\-.]/.test(l[i - 1])) score += 10 // word-boundary bonus
      if (prev === i - 1) score += 5 // consecutive-run bonus
      score += 1 // base per matched char
      prev = i
      qi++
    }
    if (qi < tok.length) return null // token not fully matched → no match
    score -= firstMatch * 0.1 // earlier first hit ranks higher
    pos = prev + 1 // next token must start after this one
  }
  return score
}

// Rank a list by fuzzyScore against `q`, dropping non-matches. `textOf` maps an
// item to the string to match. With an empty query the original order is kept.
export function fuzzyRank(items, q, textOf = (x) => x) {
  if (!q || !q.trim()) return items.slice()
  const scored = []
  for (const item of items) {
    const s = fuzzyScore(textOf(item), q)
    if (s !== null) scored.push({ item, s })
  }
  scored.sort((a, b) => b.s - a.s)
  return scored.map((x) => x.item)
}
