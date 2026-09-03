<template>
  <!-- Atelier-style command bar: a high-mounted, hard-cornered card over a
       blurred backdrop. Squared card + slightly-rounded rows is the signature. -->
  <Teleport to="body">
    <div
      class="fixed inset-0 z-[100] flex justify-center bg-black/40 px-3 pt-3 backdrop-blur-sm sm:px-4 sm:pt-[14vh]"
      @click.self="close"
    >
      <!-- phone: hug the top and size against the DYNAMIC viewport, so the
           on-screen keyboard shrinks the list instead of pushing results
           (and the input) out of reach -->
      <div
        class="flex max-h-[calc(100dvh-1.5rem)] w-[min(640px,96vw)] flex-col overflow-hidden rounded-none bg-surface-white shadow-2xl ring-1 ring-outline-gray-2 sm:max-h-[68vh] sm:w-[min(640px,92vw)]"
        @keydown="onKey"
      >
        <!-- input -->
        <div class="flex items-center gap-3 border-b border-outline-gray-2 px-5">
          <FeatherIcon name="search" class="size-4 shrink-0 text-ink-gray-4" />
          <input
            ref="inputRef"
            v-model="query"
            type="text"
            :placeholder="__('Search or run a command…')"
            class="w-full border-none bg-transparent py-4 text-base text-ink-gray-9 placeholder:text-ink-gray-4 focus:outline-none focus:ring-0"
            spellcheck="false"
            autocomplete="off"
            enterkeyhint="go"
          />
          <button
            type="button"
            class="shrink-0 rounded px-1.5 py-1 text-sm text-ink-gray-5 sm:hidden"
            @click="close"
          >
            {{ __('Cancel') }}
          </button>
          <LoadingIndicator v-if="records.loading" class="size-4 shrink-0 text-ink-gray-4" />
        </div>

        <!-- results -->
        <div ref="listRef" class="flex-1 overflow-y-auto p-2">
          <template v-for="section in sections" :key="section.title">
            <div
              v-if="section.items.length"
              class="px-3 pb-1 pt-3 text-[10.5px] font-semibold uppercase tracking-[0.14em] text-ink-gray-5"
            >
              {{ section.title }}
            </div>
            <div
              v-for="entry in section.items"
              :key="entry.key"
              :ref="(el) => setRowRef(entry, el)"
              class="flex cursor-pointer items-center justify-between gap-4 rounded-md px-3 py-2"
              :class="entry === active ? 'bg-surface-gray-3' : 'hover:bg-surface-gray-2'"
              @mousemove="cursor = flat.indexOf(entry)"
              @click="run(entry)"
            >
              <div class="flex min-w-0 items-center gap-2.5">
                <component
                  :is="entry.icon"
                  v-if="entry.icon"
                  class="size-4 shrink-0 text-ink-gray-5"
                />
                <span class="truncate text-sm text-ink-gray-8">{{ entry.label }}</span>
              </div>
              <span
                v-if="entry.meta"
                class="shrink-0 truncate pl-2 font-mono text-xs tabular-nums text-ink-gray-5"
                :class="{ 'max-w-[45%]': entry.type === 'record' }"
              >
                {{ entry.meta }}
              </span>
            </div>
          </template>

          <div
            v-if="!flat.length"
            class="px-4 py-10 text-center text-sm text-ink-gray-5"
          >
            {{
              query.trim()
                ? __('No matching commands or records')
                : __('Type to search…')
            }}
          </div>
        </div>

        <!-- footer hint (keyboard only — meaningless on a phone) -->
        <div
          class="hidden items-center gap-4 border-t border-outline-gray-2 px-4 py-2 font-mono text-[11px] text-ink-gray-4 sm:flex"
        >
          <span><kbd>↑↓</kbd> {{ __('navigate') }}</span>
          <span><kbd>↵</kbd> {{ __('open') }}</span>
          <span><kbd>esc</kbd> {{ __('close') }}</span>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup>
import { fuzzyScore } from '@/utils/fuzzy'
import { sidebarLinks, applySidebarConfig } from '@/utils/sidebarLinks'
import {
  sidebarCollapsed,
  activeDetailPanel,
  showSettings,
  isMobileView,
} from '@/composables/settings'
import {
  compsFocusMap,
  compsViewCount,
  toggleCompsFocusMap,
} from '@/composables/compsLayout'
import { getSettings } from '@/stores/settings'
import { createResource, FeatherIcon, LoadingIndicator } from 'frappe-ui'
import { useDebounceFn } from '@vueuse/core'
import { ref, computed, watch, nextTick, onMounted } from 'vue'
import { useRouter } from 'vue-router'

const show = defineModel({ type: Boolean, default: false })

const router = useRouter()
const { settings } = getSettings()

const query = ref('')
const cursor = ref(0)
const inputRef = ref(null)
const listRef = ref(null)
const rowEls = new Map()

function close() {
  show.value = false
}

// --- Static commands (navigation + actions) -------------------------------
const navCommands = computed(() => {
  let links = sidebarLinks
  try {
    links = applySidebarConfig(settings.value?.custom_sidebar_items)
  } catch (e) {
    links = sidebarLinks
  }
  return links
    .filter((l) => (l.condition ? l.condition() : true))
    .map((l) => ({
      type: 'command',
      key: `nav:${l.to}`,
      label: __(l.label),
      icon: l.icon,
      group: __('Go to'),
      run: () => router.push({ name: l.to }),
    }))
})

const actionCommands = computed(() => [
  {
    type: 'command',
    key: 'act:toggle-sidebar',
    label: __('Toggle sidebar'),
    meta: '[',
    group: __('Actions'),
    keywords: 'collapse expand navigation menu',
    run: () => (sidebarCollapsed.value = !sidebarCollapsed.value),
    // the phone drawer is not the collapsible desktop rail
    disabled: () => isMobileView.value,
  },
  {
    type: 'command',
    key: 'act:toggle-detail',
    label: __('Toggle detail panel'),
    meta: ']',
    group: __('Actions'),
    keywords: 'collapse expand sidebar record details',
    run: () => activeDetailPanel.value?.toggle(),
    disabled: () => !activeDetailPanel.value,
  },
  {
    type: 'command',
    key: 'act:comps-full-map',
    label: compsFocusMap.value ? __('Show comps list') : __('Full map'),
    meta: 'F',
    group: __('Actions'),
    keywords: 'comps collapse tray calculator offer list properties fullscreen map',
    run: () => toggleCompsFocusMap(),
    disabled: () => compsViewCount.value === 0,
  },
  {
    type: 'command',
    key: 'act:settings',
    label: __('Open settings'),
    meta: '⌘,',
    group: __('Actions'),
    keywords: 'preferences profile configuration',
    run: () => (showSettings.value = true),
  },
])

const allCommands = computed(() =>
  [...navCommands.value, ...actionCommands.value].filter((c) =>
    c.disabled ? !c.disabled() : true,
  ),
)

// --- Record search (backend, debounced) -----------------------------------
const records = createResource({
  url: 'crm.api.command_palette.search',
  makeParams: () => ({ query: query.value, limit: 8 }),
})

const runSearch = useDebounceFn(() => {
  if (query.value.trim().length >= 2) records.submit()
  else records.reset?.()
}, 180)

watch(query, () => {
  cursor.value = 0
  runSearch()
})

const recordEntries = computed(() =>
  (records.data || []).map((r) => ({
    type: 'record',
    key: `rec:${r.doctype}:${r.name}`,
    label: r.label || r.name,
    meta: r.description || '',
    group: r.group,
    run: () => router.push({ name: r.route, params: { [r.param]: r.name } }),
  })),
)

// --- Assemble sections ----------------------------------------------------
const sections = computed(() => {
  const q = query.value.trim()

  if (!q) {
    // grouped, unfiltered
    const groups = new Map()
    for (const c of allCommands.value) {
      if (!groups.has(c.group)) groups.set(c.group, [])
      groups.get(c.group).push(c)
    }
    return [...groups.entries()].map(([title, items]) => ({ title, items }))
  }

  const out = []

  // commands ranked by fuzzy score
  const cmds = []
  for (const c of allCommands.value) {
    const s = fuzzyScore(`${c.label} ${c.keywords || ''}`, q)
    if (s !== null) cmds.push({ c, s })
  }
  cmds.sort((a, b) => b.s - a.s)
  if (cmds.length)
    out.push({ title: __('Commands'), items: cmds.map((x) => x.c) })

  // records grouped by doctype, ranked by fuzzy score within each group
  const recGroups = new Map()
  for (const r of recordEntries.value) {
    if (!recGroups.has(r.group)) recGroups.set(r.group, [])
    recGroups.get(r.group).push(r)
  }
  for (const [title, items] of recGroups) {
    items.sort(
      (a, b) =>
        (fuzzyScore(`${b.label} ${b.meta}`, q) ?? -1e9) -
        (fuzzyScore(`${a.label} ${a.meta}`, q) ?? -1e9),
    )
    out.push({ title, items })
  }

  return out
})

const flat = computed(() => sections.value.flatMap((s) => s.items))
const active = computed(() => flat.value[cursor.value] || null)

// keep cursor in range as results change
watch(flat, (list) => {
  if (cursor.value > list.length - 1) cursor.value = Math.max(0, list.length - 1)
})

function run(entry) {
  if (!entry) return
  close()
  // defer so the palette unmounts / focus restores before navigating
  setTimeout(() => entry.run(), 0)
}

function move(delta) {
  const n = flat.value.length
  if (!n) return
  cursor.value = (cursor.value + delta + n) % n
  nextTick(scrollActiveIntoView)
}

function setRowRef(entry, el) {
  if (el) rowEls.set(entry.key, el)
  else rowEls.delete(entry.key)
}

function scrollActiveIntoView() {
  const el = rowEls.get(active.value?.key)
  el?.scrollIntoView({ block: 'nearest' })
}

function onKey(e) {
  if (e.key === 'ArrowDown') {
    e.preventDefault()
    move(1)
  } else if (e.key === 'ArrowUp') {
    e.preventDefault()
    move(-1)
  } else if (e.key === 'Enter') {
    e.preventDefault()
    run(active.value)
  } else if (e.key === 'Escape') {
    e.preventDefault()
    close()
  }
}

onMounted(() => {
  nextTick(() => inputRef.value?.focus())
})
</script>

<style scoped>
kbd {
  border: 1px solid var(--outline-gray-2, rgba(0, 0, 0, 0.1));
  border-radius: 3px;
  padding: 0 4px;
  margin-right: 2px;
}
</style>
