<template>
  <Dialog
    v-model="show"
    :options="{ title: __('Text presets'), size: '2xl' }"
  >
    <template #body-content>
      <div class="flex flex-col gap-5">
        <!-- tokens: click inserts at the cursor of the last-focused message box -->
        <div class="flex flex-wrap items-center gap-1.5 text-xs text-ink-gray-6">
          <span>{{ __('Insert:') }}</span>
          <button
            v-for="t in tokens"
            :key="t.token"
            type="button"
            class="rounded bg-surface-green-1 px-1.5 py-0.5 font-mono text-xs text-ink-green-3 hover:bg-surface-green-2"
            :title="t.help"
            @mousedown.prevent
            @click="insertToken(t.token)"
          >
            {{ t.display }}
          </button>
          <span class="text-ink-gray-4">
            {{ __('— filled in from the lead when the chip is tapped') }}
          </span>
        </div>

        <!-- team list -->
        <section>
          <div class="mb-1.5 flex items-baseline gap-2">
            <h3 class="text-sm font-medium text-ink-gray-8">{{ __('Team presets') }}</h3>
            <span class="text-xs text-ink-gray-5">
              {{
                canEditTeam
                  ? __('Everyone on the team sees these.')
                  : __('Everyone sees these. Ask a manager to change them.')
              }}
            </span>
          </div>
          <PresetRows
            v-model="team"
            :readonly="!canEditTeam"
            list="team"
            @focus-body="onFocusBody"
          />
        </section>

        <!-- personal list -->
        <section>
          <div class="mb-1.5 flex items-baseline gap-2">
            <h3 class="text-sm font-medium text-ink-gray-8">{{ __('My presets') }}</h3>
            <span class="text-xs text-ink-gray-5">{{ __('Only you see these.') }}</span>
          </div>
          <PresetRows v-model="mine" list="mine" @focus-body="onFocusBody" />
        </section>

        <ErrorMessage :message="error" />
      </div>
    </template>
    <template #actions>
      <div class="flex w-full items-center gap-2">
        <Button class="ml-auto" :label="__('Cancel')" @click="show = false" />
        <Button
          variant="solid"
          :label="__('Save')"
          :loading="saving"
          @click="save"
        />
      </div>
    </template>
  </Dialog>
</template>

<script setup>
import { textPresets } from '@/composables/textPresets'
import { Button, Dialog, ErrorMessage, call, toast } from 'frappe-ui'
import { computed, defineComponent, h, ref, watch } from 'vue'
import LucideTrash from '~icons/lucide/trash'

const show = defineModel({ type: Boolean })

const team = ref([])
const mine = ref([])
const saving = ref(false)
const error = ref(null)

const canEditTeam = computed(() => !!textPresets.data?.can_edit_team)
// `display` is built here: a literal `}}` inside a template interpolation
// closes it early and fails the compile
const tokens = computed(() =>
  (textPresets.data?.tokens || []).map((t) => ({
    ...t,
    display: '{{' + t.token + '}}',
  })),
)

function clone(list) {
  return (list || []).map((p) => ({ label: p.label, body: p.body }))
}

watch(show, (open) => {
  if (!open) return
  error.value = null
  team.value = clone(textPresets.data?.team)
  mine.value = clone(textPresets.data?.mine)
  // a fresh row so the empty state is obviously "type here"
  if (!mine.value.length) mine.value.push({ label: '', body: '' })
  if (canEditTeam.value && !team.value.length) team.value.push({ label: '', body: '' })
})

// --- token insert: into whichever message box was focused last ---
let focusedBody = null
function onFocusBody(el) {
  focusedBody = el
}
function insertToken(token) {
  const el = focusedBody
  if (!el || !el.isConnected) {
    toast.error(__('Click into a message first, then insert the token'))
    return
  }
  const tok = `{{${token}}}`
  const start = el.selectionStart ?? el.value.length
  const end = el.selectionEnd ?? start
  el.value = el.value.slice(0, start) + tok + el.value.slice(end)
  el.selectionStart = el.selectionEnd = start + tok.length
  // the rows bind on `input`, so tell them
  el.dispatchEvent(new Event('input', { bubbles: true }))
  el.focus()
}

function cleaned(list) {
  return list
    .map((p) => ({ label: (p.label || '').trim(), body: (p.body || '').trim() }))
    .filter((p) => p.label && p.body)
}

async function save() {
  // a row with a body and no label (or vice versa) would vanish silently
  const editable = canEditTeam.value ? [...team.value, ...mine.value] : mine.value
  const half = editable.find(
    (p) => !!(p.label || '').trim() !== !!(p.body || '').trim(),
  )
  if (half) {
    error.value = __('Every preset needs both a name and a message (or clear both to drop it).')
    return
  }
  saving.value = true
  error.value = null
  try {
    if (canEditTeam.value) {
      await call('crm.api.text_presets.set_team_text_presets', {
        presets: JSON.stringify(cleaned(team.value)),
      })
    }
    await call('crm.api.text_presets.set_my_text_presets', {
      presets: JSON.stringify(cleaned(mine.value)),
    })
    await textPresets.reload()
    toast.success(__('Text presets saved'))
    show.value = false
  } catch (e) {
    error.value = e.messages?.[0] || __('Could not save text presets')
  } finally {
    saving.value = false
  }
}

// One list of editable rows: name | message | trash, plus an "Add" line.
// Kept local — nothing else needs it, and a second file would only add a hop.
const PresetRows = defineComponent({
  props: {
    modelValue: { type: Array, default: () => [] },
    readonly: { type: Boolean, default: false },
    list: { type: String, default: '' },
  },
  emits: ['update:modelValue', 'focus-body'],
  setup(props, { emit }) {
    const rows = () => props.modelValue
    function update(i, key, val) {
      const next = rows().map((r, j) => (j === i ? { ...r, [key]: val } : r))
      emit('update:modelValue', next)
    }
    function remove(i) {
      emit(
        'update:modelValue',
        rows().filter((_, j) => j !== i),
      )
    }
    function add() {
      emit('update:modelValue', [...rows(), { label: '', body: '' }])
    }
    return () => {
      const children = rows().map((r, i) =>
        h('div', { key: props.list + i, class: 'flex items-start gap-2' }, [
          h('input', {
            type: 'text',
            value: r.label,
            placeholder: __('Name'),
            maxlength: 32,
            readonly: props.readonly,
            class:
              'w-36 shrink-0 rounded border border-outline-gray-2 bg-surface-white px-2 py-1.5 text-sm text-ink-gray-8 placeholder:text-ink-gray-4 focus:outline-none focus:ring-2 focus:ring-outline-gray-3 read-only:bg-surface-gray-1 read-only:text-ink-gray-6',
            onInput: (e) => update(i, 'label', e.target.value),
          }),
          h('textarea', {
            value: r.body,
            rows: 2,
            maxlength: 1000,
            readonly: props.readonly,
            placeholder: __('Hi {{first_name}}, this is {{my_name}} with Groundwork about your house on {{street}}…'),
            class:
              'min-h-[3.25rem] w-full resize-y rounded border border-outline-gray-2 bg-surface-white px-2 py-1.5 text-sm leading-5 text-ink-gray-8 placeholder:text-ink-gray-4 focus:outline-none focus:ring-2 focus:ring-outline-gray-3 read-only:bg-surface-gray-1 read-only:text-ink-gray-6',
            onInput: (e) => update(i, 'body', e.target.value),
            onFocus: (e) => !props.readonly && emit('focus-body', e.target),
          }),
          props.readonly
            ? null
            : h(
                'button',
                {
                  type: 'button',
                  title: __('Remove'),
                  class:
                    'mt-1.5 flex shrink-0 items-center text-ink-gray-4 hover:text-ink-red-4',
                  onClick: () => remove(i),
                },
                [h(LucideTrash, { class: 'size-4' })],
              ),
        ]),
      )
      if (!rows().length) {
        children.push(
          h('div', { class: 'text-sm text-ink-gray-4' }, __('None yet.')),
        )
      }
      if (!props.readonly) {
        children.push(
          h(
            'button',
            {
              type: 'button',
              class:
                'w-fit text-sm text-ink-gray-5 hover:text-ink-gray-8',
              onClick: add,
            },
            '+ ' + __('Add preset'),
          ),
        )
      }
      return h('div', { class: 'flex flex-col gap-2' }, children)
    }
  },
})
</script>
