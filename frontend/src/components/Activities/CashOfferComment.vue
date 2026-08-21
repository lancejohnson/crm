<template>
  <div class="offer">
    <div class="title">{{ __('Cash offer') }}</div>

    <div v-for="(sc, i) in offer.scenarios" :key="i" class="scene">
      <div class="scene-h">
        {{ __('Scenario {0}', [i + 1]) }}
        <span v-if="sc.pct">({{ Math.round(sc.pct * 100) }}%)</span>
      </div>
      <div>
        {{ money(sc.arv) }} × {{ Math.round((sc.pct || 0) * 100) }}% =
        {{ money(sc.after) }}
      </div>
      <div>
        − {{ __('rehab') }} {{ money(sc.rehab) }}
        <template v-if="offer.sqft">
          ({{ money(sc.rehab_psf) }}/sf × {{ fmt(offer.sqft) }} sf)
        </template>
      </div>
      <div>
        − {{ __('fee') }} {{ money(sc.fee) }} =
        <b class="scene-offer">{{ money(sc.offer) }}</b>
      </div>
    </div>

    <div class="block">
      <div class="lab">{{ __('Comps') }}</div>
      <ul v-if="offer.comps.length" class="comps">
        <li v-for="c in offer.comps" :key="c.name || c.address">
          <a
            :href="c.href"
            target="_blank"
            rel="noopener noreferrer"
            @click.stop
          >{{ c.street }}</a>
          <div class="facts">{{ c.facts }}</div>
        </li>
      </ul>
      <div v-else class="muted">{{ __('No comps picked.') }}</div>
    </div>

    <div v-if="offer.notes" class="block">
      <div class="lab">{{ __('Notes') }}</div>
      <div class="notes">{{ offer.notes }}</div>
    </div>

    <div class="actions">
      <button type="button" class="link" @click.stop="openTweak">
        {{ __('Tweak calcs') }}
      </button>
    </div>
  </div>

  <Dialog
    v-model="tweakOpen"
    :options="{ title: __('Cash offer'), size: '5xl' }"
  >
    <template #body-content>
      <div class="mb-3 flex justify-end">
        <Button
          :label="__('Open comps page')"
          iconLeft="external-link"
          @click="openPage"
        />
      </div>
      <CompOfferCalc
        v-if="tweakOpen && lead"
        :lead="lead"
        :subject="{ sqft: offer.sqft }"
        :comps="draftComps"
        :seed="{ scenarios: offer.scenarios, notes: offer.notes }"
        @remove="removeComp"
        @open="openComp"
        @saved="onSaved"
      />
    </template>
  </Dialog>
</template>

<script setup>
/**
 * Timeline card for a saved cash-offer comment.
 *
 * The stored HTML used to be one wrapping line of "Comps: A · B", and
 * `.prose-f { break-all }` split prices mid-number so it read as plain text.
 * This card is the display; it hydrates from `data-cash-offer` on new comments
 * and parses the old inline HTML so existing timeline rows upgrade in place.
 */
import CompOfferCalc from '@/components/CompOfferCalc.vue'
import { streetAddress } from '@/utils/comps'
import { zillowUrl } from '@/utils/propertyLinks'
import { Button, Dialog } from 'frappe-ui'
import { computed, ref } from 'vue'

const props = defineProps({
  html: { type: String, default: '' },
  lead: { type: String, default: '' },
})

const emit = defineEmits(['saved'])

const tweakOpen = ref(false)
const draftComps = ref([])

function decodeEntities(s) {
  const ta = document.createElement('textarea')
  ta.innerHTML = s
  return ta.value
}

function num(s) {
  const n = Number(String(s || '').replace(/[^0-9.]/g, ''))
  return Number.isFinite(n) ? n : 0
}

function money(n) {
  return '$' + Math.round(Number(n) || 0).toLocaleString()
}

function fmt(n) {
  return (Number(n) || 0).toLocaleString()
}

function factsOf(c) {
  const bits = []
  if (c.price) bits.push(money(c.price))
  if (c.square_footage) bits.push(`${fmt(c.square_footage)} sf`)
  if (c.price && c.square_footage) {
    bits.push(money(Math.round(c.price / c.square_footage)) + '/sf')
  }
  if (c.distance_mi) bits.push(`${Number(c.distance_mi).toFixed(2)} mi`)
  return bits.join(' · ')
}

function shapeComp(c) {
  const address = (c.address || '').trim()
  return {
    name: c.name || address,
    address,
    street: streetAddress(address) || address || '—',
    price: Number(c.price) || 0,
    square_footage: Number(c.square_footage) || 0,
    distance_mi: Number(c.distance_mi) || 0,
    status: c.status || '',
    href: c.href || zillowUrl(address) || compsPage.value,
    facts: factsOf(c),
  }
}

function parsePayload(html) {
  const m = (html || '').match(/data-cash-offer="([^"]*)"/)
  if (!m) return null
  try {
    return JSON.parse(decodeEntities(m[1]))
  } catch {
    return null
  }
}

function parseLegacy(html) {
  const scenes = []
  const sceneRe =
    /Scenario\s+\d+\s+\((\d+)%\):\s*\$([0-9,]+).*?rehab\s*\$([0-9,]+)\s*\(\$([0-9,]+)\/sf\s*[×x]\s*([0-9,]+)\s*sf\)\s*[−\-]\s*fee\s*\$([0-9,]+)\s*=\s*(?:<b[^>]*>)?\$([0-9,]+)/gi
  let sm
  let sqft = 0
  while ((sm = sceneRe.exec(html))) {
    const pct = num(sm[1]) / 100
    const arv = num(sm[2])
    const rehab = num(sm[3])
    const rehab_psf = num(sm[4])
    sqft = num(sm[5]) || sqft
    const fee = num(sm[6])
    const offer = num(sm[7])
    scenes.push({
      arv,
      pct,
      rehab_psf,
      fee,
      after: Math.round(arv * pct),
      rehab,
      offer,
    })
  }
  const comps = []
  const compRe =
    /<a[^>]*href="([^"]+)"[^>]*>([^<]+)<\/a>\s*(?:\(([^)]*)\)|([^<]*))/gi
  let cm
  while ((cm = compRe.exec(html))) {
    const href = cm[1]
    const label = decodeEntities(cm[2]).trim()
    if (/\/leads\/[^/]+\/comps/.test(href) || /tweak calcs/i.test(label)) continue
    const facts = (cm[3] || cm[4] || '').trim()
    if (!facts.includes('$')) continue
    const price = num((facts.match(/\$([0-9,]+)/) || [])[1])
    const sf = num((facts.match(/([0-9,]+)\s*sf/) || [])[1])
    const mi = Number((facts.match(/([\d.]+)\s*mi/) || [])[1]) || 0
    comps.push({
      name: '',
      address: label,
      href,
      price,
      square_footage: sf,
      distance_mi: mi,
      status: '',
    })
  }
  let notes = ''
  const nm = html.match(/<b>Notes<\/b><br>([\s\S]*?)<\/div>/i)
  if (nm) {
    notes = decodeEntities(nm[1].replace(/<br\s*\/?>/gi, '\n')).trim()
  }
  return { scenarios: scenes, comps, sqft, notes }
}

const compsPage = computed(() =>
  props.lead ? `/crm/leads/${props.lead}/comps` : '',
)

const offer = computed(() => {
  const raw = parsePayload(props.html) || parseLegacy(props.html) || {}
  const lead = raw.lead || props.lead || ''
  return {
    lead,
    sqft: Number(raw.sqft) || 0,
    notes: raw.notes || '',
    scenarios: raw.scenarios || [],
    comps: (raw.comps || []).map(shapeComp),
  }
})

const lead = computed(() => offer.value.lead || props.lead || '')

function openTweak() {
  draftComps.value = offer.value.comps.map((c) => ({ ...c }))
  tweakOpen.value = true
}

function removeComp(name) {
  draftComps.value = draftComps.value.filter(
    (c) => (c.name || c.address) !== name,
  )
}

function openComp(name) {
  const c = draftComps.value.find((x) => (x.name || x.address) === name)
  const href = c?.href || zillowUrl(c?.address || '')
  if (href) window.open(href, '_blank', 'noopener')
}

function openPage() {
  if (!lead.value) return
  const win = window.open(compsPage.value, '_blank')
  if (win) win.opener = null
}

function onSaved() {
  tweakOpen.value = false
  emit('saved')
}
</script>

<style scoped>
.offer {
  overflow-wrap: break-word;
  word-break: normal;
  font-variant-numeric: tabular-nums;
}
.title {
  font-weight: 650;
  color: inherit;
}
.scene {
  margin-top: 0.45em;
  line-height: 1.35;
}
.scene-h {
  font-weight: 600;
}
.scene-offer {
  font-weight: 650;
  white-space: nowrap;
}
.block {
  margin-top: 0.7em;
}
.lab {
  font-weight: 600;
  margin-bottom: 0.15em;
}
.comps {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 0.45em;
}
.comps a {
  color: #2563c9;
  font-weight: 600;
  text-decoration: underline;
  text-underline-offset: 2px;
}
.facts {
  color: var(--ink-gray-6, #6b7280);
  font-size: 0.92em;
}
.muted {
  color: var(--ink-gray-5, #9ca3af);
}
.notes {
  white-space: pre-wrap;
}
.actions {
  margin-top: 0.7em;
}
.link {
  border: 0;
  background: none;
  padding: 0;
  font: inherit;
  font-weight: 600;
  color: #2563c9;
  cursor: pointer;
  text-decoration: underline;
  text-underline-offset: 2px;
}
</style>
