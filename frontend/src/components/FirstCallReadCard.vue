<template>
  <div class="border-t px-5 py-4">
    <div class="flex items-center gap-2 text-base font-medium text-ink-gray-8">
      <svg
        class="size-4 text-ink-gray-7"
        viewBox="0 0 16 16"
        fill="none"
        stroke="currentColor"
        stroke-width="1.4"
      >
        <rect x="2" y="2" width="12" height="12" rx="1.5" />
        <line x1="8" y1="2" x2="8" y2="14" />
        <line x1="2" y1="8" x2="14" y2="8" />
      </svg>
      {{ __('First-Call Read') }}
    </div>
    <div class="mt-1 text-xs text-ink-gray-5">
      {{ __('Answer these two after the first call.') }}
    </div>

    <!-- Motivated? -->
    <div class="mt-3.5 text-sm text-ink-gray-7">
      {{ __('Are they') }}
      <span class="font-medium text-ink-gray-8">{{ __('motivated') }}</span>
      {{ __('to sell?') }}
    </div>
    <div class="mt-1.5 flex gap-2">
      <button
        :class="segClass('motivated', 'Yes')"
        @click="set('motivated', 'Yes')"
      >
        {{ __('Yes — motivated') }}
      </button>
      <button
        :class="segClass('motivated', 'No')"
        @click="set('motivated', 'No')"
      >
        {{ __('No — not really') }}
      </button>
    </div>

    <!-- On price? -->
    <div class="mt-3.5 text-sm text-ink-gray-7">
      {{ __('Is their') }}
      <span class="font-medium text-ink-gray-8">{{ __('price') }}</span>
      {{ __('realistic?') }}
    </div>
    <div class="mt-1.5 flex gap-2">
      <button
        :class="segClass('onPrice', 'Yes')"
        @click="set('onPrice', 'Yes')"
      >
        {{ __('Yes — on price') }}
      </button>
      <button :class="segClass('onPrice', 'No')" @click="set('onPrice', 'No')">
        {{ __('No — too high') }}
      </button>
    </div>

    <!-- Mini 2x2: lights up the cell this lead lands in -->
    <div class="mt-4 grid grid-cols-[3rem_1fr_1fr] gap-1.5">
      <div></div>
      <!-- Off price is the LEFT column so the best read (motivated + on price)
           lands top-right, the corner the eye treats as "best" on a 2x2. -->
      <div class="text-center text-2xs uppercase tracking-wide text-ink-gray-5">
        {{ __('Off price') }}
      </div>
      <div class="text-center text-2xs uppercase tracking-wide text-ink-gray-5">
        {{ __('On price') }}
      </div>

      <div class="flex items-center justify-end text-2xs uppercase tracking-wide text-ink-gray-5">
        {{ __('Motiv.') }}
      </div>
      <div :class="cellClass('Yes', 'No')">{{ cellMark('Yes', 'No') }}</div>
      <div :class="cellClass('Yes', 'Yes')">{{ cellMark('Yes', 'Yes') }}</div>

      <div class="flex items-center justify-end text-2xs uppercase tracking-wide text-ink-gray-5">
        {{ __('Not') }}
      </div>
      <div :class="cellClass('No', 'No')">{{ cellMark('No', 'No') }}</div>
      <div :class="cellClass('No', 'Yes')">{{ cellMark('No', 'Yes') }}</div>
    </div>

    <!-- Result band -->
    <div
      v-if="read.quad"
      class="mt-4 rounded-lg px-3.5 py-3"
      :class="bandClass(read.quad.theme)"
    >
      <div class="text-sm font-semibold">{{ __(read.quad.label) }}</div>
      <div class="mt-1 text-xs leading-relaxed text-ink-gray-7">
        {{ __(read.quad.guide) }}
      </div>
      <div v-if="setAt" class="mt-2 text-2xs text-ink-gray-5">
        {{ __('Set by') }} {{ setByName }} · {{ formatDate(setAt, '', true) }}
      </div>
    </div>
    <div
      v-else
      class="mt-4 rounded-lg border border-dashed border-outline-gray-2 bg-surface-gray-1 px-3.5 py-3"
    >
      <div class="text-sm font-medium text-ink-gray-6">
        {{ __('Not qualified yet') }}
      </div>
      <div class="mt-0.5 text-xs text-ink-gray-5">
        {{ __('Answer both questions to place this lead.') }}
      </div>
    </div>
  </div>
</template>

<script setup>
import { firstCallRead, formatDate } from '@/utils'
import { usersStore } from '@/stores/users'
import { call } from 'frappe-ui'
import { computed, ref, watch } from 'vue'

const props = defineProps({
  lead: { type: String, required: true },
  motivated: { type: String, default: '' },
  onPrice: { type: String, default: '' },
  setBy: { type: String, default: '' },
  setAt: { type: String, default: '' },
})

const emit = defineEmits(['saved'])

const { getUser } = usersStore()

// Optimistic local copy so the toggle responds instantly; resync if the parent
// doc reloads (e.g. another user's realtime update).
const motivated = ref(props.motivated || '')
const onPrice = ref(props.onPrice || '')
watch(
  () => [props.motivated, props.onPrice],
  ([m, p]) => {
    motivated.value = m || ''
    onPrice.value = p || ''
  },
)

const read = computed(() => firstCallRead(motivated.value, onPrice.value))
const setByName = computed(() => (props.setBy ? getUser(props.setBy)?.full_name : ''))

const SEG_ON = {
  Yes: 'bg-surface-green-2 text-ink-green-3',
  No: 'bg-surface-red-2 text-ink-red-3',
}
const BAND = {
  green: 'bg-surface-green-2 text-ink-green-3',
  orange: 'bg-surface-amber-1 text-ink-amber-3',
  blue: 'bg-surface-blue-2 text-ink-blue-3',
  red: 'bg-surface-red-2 text-ink-red-3',
}

function segClass(field, value) {
  const cur = field === 'motivated' ? motivated.value : onPrice.value
  const base = 'flex-1 rounded-md py-2 text-sm transition cursor-pointer '
  return cur === value
    ? base + 'font-semibold ' + SEG_ON[value]
    : base + 'bg-surface-gray-2 text-ink-gray-6 hover:bg-surface-gray-3'
}

function cellClass(m, p) {
  const here = read.value.answered && motivated.value === m && onPrice.value === p
  const base =
    'flex h-8 items-center justify-center rounded-md text-2xs font-medium '
  return here
    ? base + BAND[read.value.quad.theme]
    : base + 'bg-surface-gray-1 text-ink-gray-4'
}

function cellMark(m, p) {
  return read.value.answered && motivated.value === m && onPrice.value === p
    ? __('● here')
    : ''
}

function bandClass(theme) {
  return BAND[theme] || ''
}

async function set(field, value) {
  // tap the active choice again to clear it
  const ref_ = field === 'motivated' ? motivated : onPrice
  ref_.value = ref_.value === value ? '' : value
  try {
    await call('crm.api.first_call.set_first_call_read', {
      lead: props.lead,
      motivated: motivated.value,
      on_price: onPrice.value,
    })
    emit('saved')
  } catch (e) {
    // roll back optimistic change on failure
    ref_.value = field === 'motivated' ? props.motivated || '' : props.onPrice || ''
  }
}
</script>
