<template>
  <section class="shrink-0 border-b bg-surface-white px-5 py-3.5 sm:px-6">
    <div class="flex items-center justify-between gap-3">
      <div class="min-w-0">
        <div class="flex items-center gap-2">
          <FeatherIcon name="home" class="size-4 text-ink-gray-6" />
          <h3 class="text-sm font-semibold text-ink-gray-8">{{ __('Comparable homes') }}</h3>
          <Badge
            v-if="data?.total_matched"
            variant="subtle"
            theme="gray"
            :label="String(data.total_matched)"
          />
        </div>
        <div v-if="subjectLine" class="mt-0.5 truncate text-xs text-ink-gray-5">
          {{ __('Subject') }} · {{ subjectLine }}
        </div>
      </div>
      <Button
        variant="ghost"
        :label="__('Open all comps')"
        icon-right="arrow-up-right"
        class="shrink-0"
        @click="openAllComps"
      />
    </div>

    <!-- Bought from BatchData because we hold nothing here. Takes precedence over
         the relaxed note: where the comps CAME FROM matters more than how wide the
         filter had to go, and in this path the filter never ran at all. -->
    <div
      v-if="fallbackMessage"
      class="mt-2 rounded-md bg-surface-gray-2 px-2.5 py-1.5 text-xs text-ink-gray-7"
    >
      {{ fallbackMessage }}
    </div>
    <div
      v-else-if="data?.relaxed"
      class="mt-2 rounded-md bg-surface-amber-1 px-2.5 py-1.5 text-xs text-ink-amber-3"
    >
      {{ relaxedMessage }}
    </div>

    <div v-if="loading" class="mt-3 flex gap-2 overflow-hidden">
      <div
        v-for="n in 3"
        :key="n"
        class="h-[7.5rem] w-52 shrink-0 animate-pulse rounded-lg bg-surface-gray-2"
      />
    </div>

    <div v-else-if="comps.length" class="mt-3 flex snap-x gap-2.5 overflow-x-auto pb-1">
      <button
        v-for="comp in comps"
        :key="comp.name"
        class="group w-52 shrink-0 snap-start rounded-lg border bg-surface-white p-3 text-left transition hover:border-outline-gray-3 hover:shadow-sm"
        :class="comp.selected ? 'border-outline-blue-2' : 'border-outline-gray-1'"
        @click="openComp(comp)"
      >
        <div class="flex items-start justify-between gap-2">
          <div class="min-w-0">
            <div class="text-base font-semibold text-ink-gray-9">
              {{ formatCompMoney(comp.price) }}
            </div>
            <div class="truncate text-xs text-ink-gray-6" :title="comp.address">
              {{ comp.address }}
            </div>
          </div>
          <Badge
            variant="subtle"
            :theme="fit(comp).theme"
            :label="fitLabel(comp)"
            :title="fitTitle(comp)"
          />
        </div>

        <div class="mt-2 flex flex-wrap gap-x-2 gap-y-0.5 text-xs text-ink-gray-7">
          <span v-for="fact in compFacts(comp)" :key="fact">{{ fact }}</span>
        </div>
        <div class="mt-1 truncate text-xs text-ink-gray-5">
          {{ compDifferences(comp, subject).join(' · ') }}
        </div>

        <div class="mt-2.5 flex items-center justify-between gap-2">
          <span
            class="text-xs font-medium"
            :class="comp.status === 'Active' ? 'text-ink-amber-3' : 'text-ink-gray-5'"
          >
            {{ comp.status === 'Active' ? __('For sale') : __('Off-market') }}
          </span>
          <span class="flex items-center gap-1 text-xs font-medium text-ink-blue-3">
            {{ __('Photos & details') }}
            <FeatherIcon name="chevron-right" class="size-3.5 transition group-hover:translate-x-0.5" />
          </span>
        </div>
      </button>
    </div>

    <div
      v-else
      class="mt-3 flex items-center justify-between gap-3 rounded-lg border border-dashed border-outline-gray-2 bg-surface-gray-1 px-3 py-2.5 text-sm text-ink-gray-5"
    >
      <span>{{ error || data?.message || __('No nearby comps are available for this property.') }}</span>
      <button v-if="error" class="shrink-0 font-medium text-ink-blue-3 hover:underline" @click="load(true)">
        {{ __('Retry') }}
      </button>
    </div>
  </section>

  <CompDetailModal
    v-if="selectedComp"
    v-model="showDetail"
    :lead="lead"
    :comp="selectedComp"
    :subject="subject"
  />
</template>

<script setup>
import CompDetailModal from '@/components/CompDetailModal.vue'
import {
  compDifferences,
  compFacts,
  compFit,
  formatCompMoney,
  subjectFacts,
} from '@/utils/comps'
import { Badge, Button, FeatherIcon, call } from 'frappe-ui'
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

const props = defineProps({
  lead: { type: String, required: true },
  address: { type: String, default: '' },
  active: { type: Boolean, default: false },
})

const router = useRouter()
const data = ref(null)
const loading = ref(false)
const error = ref('')
const selectedComp = ref(null)
const showDetail = ref(false)
const cache = new Map()
let requestToken = 0

const subject = computed(() => data.value?.subject || null)
const subjectLine = computed(() => subjectFacts(subject.value).join(' · '))
const comps = computed(() =>
  [...(data.value?.comps || [])]
    .sort((a, b) => Number(b.selected) - Number(a.selected) || a.distance_mi - b.distance_mi)
    .slice(0, 8),
)
const relaxedMessage = computed(() => {
  if (data.value?.fell_through) {
    return __('No recent, similar set was found nearby — these are the closest available properties.')
  }
  return __('The close-match set was small, so these use a wider similarity range.')
})

/**
 * Provenance, when the pooled index held nothing and we bought a set instead.
 *
 * These are RECORDED SALES rather than our listing-derived comps, so the rep is
 * told plainly. Returns '' when the fallback did not run, which is the common case.
 */
const fallbackMessage = computed(() => {
  const f = data.value?.fallback
  if (!f?.used) return ''
  if (!f.count) return __('No comps here, and no recorded sales nearby either.')
  return __('We hold no comps here — showing {0} recorded sales ({1}).', [
    f.count,
    f.basis || __('last 2 years'),
  ])
})

watch(
  () => [props.active, props.lead],
  ([active]) => {
    if (!active || !props.lead) return
    load()
  },
  { immediate: true },
)

async function load(force = false) {
  if (!props.lead) return
  if (!force && cache.has(props.lead)) {
    data.value = cache.get(props.lead)
    return
  }
  const token = ++requestToken
  loading.value = true
  error.value = ''
  data.value = null
  try {
    const result = await call('crm.api.comps.get_lead_comps', {
      lead: props.lead,
      auto: 1,
      limit: 12,
    })
    if (token !== requestToken) return
    data.value = result
    cache.set(props.lead, result)
  } catch (e) {
    if (token !== requestToken) return
    error.value = e?.messages?.[0] || e?.message || __('Could not load comps.')
  } finally {
    if (token === requestToken) loading.value = false
  }
}

function fit(comp) {
  return compFit(comp, subject.value)
}

function fitLabel(comp) {
  const value = fit(comp)
  return value.total ? `${value.matched}/${value.total} ${__('fit')}` : __('Nearby')
}

function fitTitle(comp) {
  const value = fit(comp)
  if (!value.total) return __('Not enough subject facts to score similarity.')
  const matching = value.dimensions.filter((dimension) => dimension.matches).map((dimension) => __(dimension.label))
  const different = value.dimensions.filter((dimension) => !dimension.matches).map((dimension) => __(dimension.label))
  return [
    matching.length ? `${__('Matches')}: ${matching.join(', ')}` : '',
    different.length ? `${__('Different')}: ${different.join(', ')}` : '',
  ]
    .filter(Boolean)
    .join(' · ')
}

function openComp(comp) {
  selectedComp.value = comp
  showDetail.value = true
}

function openAllComps() {
  const url = `/crm/leads/${props.lead}/comps`
  const win = window.open(url, '_blank')
  if (win) win.opener = null
  else router.push({ name: 'Comps', params: { leadId: props.lead } })
}
</script>
