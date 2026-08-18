<template>
  <div class="border-t px-5 py-4">
    <div class="flex items-center gap-2 text-base font-medium text-ink-gray-8">
      <PhoneIcon class="size-4 text-ink-gray-7" />
      {{ __('Phones') }}
    </div>
    <div class="mt-1 text-xs text-ink-gray-5">
      {{ __('Any number they answer. Adding one pulls Quo calls onto this lead.') }}
    </div>

    <div v-if="phones.length" class="mt-3 flex flex-col gap-1.5">
      <div
        v-for="p in phones"
        :key="p.last10"
        class="group flex items-center gap-1.5 text-sm"
      >
        <button
          class="shrink-0 text-ink-gray-4 hover:text-ink-amber-3"
          :title="p.primary ? __('Primary') : __('Set as primary')"
          :disabled="p.primary || busy"
          @click="setPrimary(p.number)"
        >
          <FeatherIcon
            name="star"
            :class="['size-3.5', p.primary ? 'text-amber-400' : 'text-ink-gray-4']"
          />
        </button>
        <a
          :href="callHref(p.number, fromNumber)"
          class="min-w-0 flex-1 truncate font-medium text-ink-gray-8 hover:text-ink-gray-9 hover:underline"
          :title="p.number"
          @click.prevent="dial(p.number)"
        >
          {{ formatPhone(p.number) }}
        </a>
        <span
          v-if="lookingUp.has(p.last10)"
          class="shrink-0 text-2xs text-ink-gray-5"
        >
          {{ __('looking up…') }}
        </span>
        <button
          class="shrink-0 text-ink-gray-4 hover:text-ink-gray-8 sm:opacity-0 sm:group-hover:opacity-100"
          :title="__('Check Quo for calls')"
          :disabled="busy || lookingUp.has(p.last10)"
          @click="refresh(p.number)"
        >
          <FeatherIcon name="refresh-cw" class="size-3.5" />
        </button>
        <button
          class="shrink-0 text-ink-gray-4 hover:text-ink-red-3 sm:opacity-0 sm:group-hover:opacity-100"
          :title="__('Remove')"
          :disabled="busy"
          @click="remove(p.number)"
        >
          <FeatherIcon name="x" class="size-3.5" />
        </button>
      </div>
    </div>

    <div v-else class="mt-2 text-sm text-ink-gray-5">
      {{ __('No numbers yet.') }}
    </div>

    <form class="mt-3 flex items-center gap-1.5" @submit.prevent="add">
      <input
        v-model="draft"
        type="tel"
        inputmode="tel"
        autocomplete="tel"
        :placeholder="__('Add a number')"
        :disabled="busy"
        class="min-w-0 flex-1 border-none bg-transparent p-0 text-sm text-ink-gray-8 placeholder:text-ink-gray-4 focus:outline-none focus:ring-0"
      />
      <Button
        type="submit"
        :label="__('Add')"
        :loading="busy"
        :disabled="!draft.trim() || busy"
      />
    </form>
  </div>
</template>

<script setup>
import PhoneIcon from '@/components/Icons/PhoneIcon.vue'
import { listLeadPhones } from '@/utils/leadPhones'
import { callHref, formatPhone } from '@/utils/phoneFormat'
import { myQuoNumber } from '@/composables/quoSender'
import { globalStore } from '@/stores/global'
import { Button, FeatherIcon, call, toast } from 'frappe-ui'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

const props = defineProps({
  lead: { type: String, required: true },
  doc: { type: Object, default: () => ({}) },
})

const emit = defineEmits(['saved', 'dial'])

const { $socket } = globalStore()
const draft = ref('')
const busy = ref(false)
const lookingUp = ref(new Set())
const fromNumber = computed(() => myQuoNumber())

const phones = computed(() => listLeadPhones(props.doc))

watch(
  () => props.lead,
  () => {
    draft.value = ''
    lookingUp.value = new Set()
  },
)

function markLooking(number) {
  const digits = String(number || '').replace(/\D/g, '').slice(-10)
  if (!digits) return
  const next = new Set(lookingUp.value)
  next.add(digits)
  lookingUp.value = next
}

function clearLooking(digits) {
  const next = new Set(lookingUp.value)
  next.delete(digits)
  lookingUp.value = next
}

function dial(number) {
  emit('dial', number)
}

async function add() {
  const number = draft.value.trim()
  if (!number || busy.value) return
  busy.value = true
  try {
    const res = await call('crm.api.lead_phones.add_lead_phone', {
      lead: props.lead,
      number,
    })
    draft.value = ''
    if (res?.already) {
      toast.info(__('Already on this lead — checking Quo again'))
    } else if (res?.linked) {
      toast.success(
        res.linked === 1
          ? __('Added, and linked 1 existing call')
          : __('Added, and linked {0} existing calls', [res.linked]),
      )
    } else {
      toast.success(__('Number added'))
    }
    markLooking(number)
    emit('saved')
  } catch (e) {
    toast.error(e.messages?.[0] || e.message || __('Could not add that number'))
  } finally {
    busy.value = false
  }
}

async function remove(number) {
  if (busy.value) return
  busy.value = true
  try {
    await call('crm.api.lead_phones.remove_lead_phone', {
      lead: props.lead,
      number,
    })
    emit('saved')
  } catch (e) {
    toast.error(e.messages?.[0] || e.message || __('Could not remove that number'))
  } finally {
    busy.value = false
  }
}

async function setPrimary(number) {
  if (busy.value) return
  busy.value = true
  try {
    await call('crm.api.lead_phones.set_primary_phone', {
      lead: props.lead,
      number,
    })
    emit('saved')
  } catch (e) {
    toast.error(e.messages?.[0] || e.message || __('Could not change the primary'))
  } finally {
    busy.value = false
  }
}

async function refresh(number) {
  markLooking(number)
  try {
    await call('crm.api.lead_phones.add_lead_phone', {
      lead: props.lead,
      number,
    })
  } catch (e) {
    clearLooking(String(number || '').replace(/\D/g, '').slice(-10))
    toast.error(e.messages?.[0] || e.message || __('Could not check Quo'))
  }
}

function onBackfill(data) {
  if (
    data?.reference_doctype !== 'CRM Lead' ||
    data?.reference_docname !== props.lead
  ) {
    return
  }
  if (data.last10) clearLooking(data.last10)
  if (data.error) {
    toast.error(__('Could not look up Quo calls'))
    return
  }
  const n = (data.created || 0) + (data.linked || 0)
  if (n > 0) {
    toast.success(
      n === 1
        ? __('Pulled 1 call from Quo')
        : __('Pulled {0} calls from Quo', [n]),
    )
    emit('saved')
  } else if (lookingUp.value.size === 0) {
    toast.info(__('No Quo calls for that number'))
  }
}

onMounted(() => {
  $socket.on('crm_call_log', onBackfill)
})
onBeforeUnmount(() => {
  $socket.off('crm_call_log', onBackfill)
})
</script>
