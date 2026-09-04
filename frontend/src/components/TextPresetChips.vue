<template>
  <!-- single root: the host passes a class, and a fragment would drop it -->
  <div v-if="lead" class="flex flex-col gap-1">
    <div class="flex items-center gap-2">
      <span class="text-xs text-ink-gray-5">{{ __('Presets') }}</span>
      <span
        v-if="rendering"
        class="text-xs text-ink-gray-4"
      >
        {{ __('Filling in…') }}
      </span>
      <Tooltip :text="__('Edit text presets')">
        <button
          type="button"
          class="ml-auto flex shrink-0 items-center text-ink-gray-4 hover:text-ink-gray-7"
          @click="showEditor = true"
        >
          <LucidePencil class="size-3.5" />
        </button>
      </Tooltip>
    </div>
    <div class="flex flex-wrap items-center gap-1.5">
      <button
        v-for="(p, i) in team"
        :key="'t' + i"
        type="button"
        class="rounded-md border border-outline-gray-2 bg-surface-white px-2 py-0.5 text-xs text-ink-gray-7 hover:border-outline-gray-3 hover:bg-surface-gray-1 disabled:opacity-60"
        :title="p.body"
        :disabled="rendering"
        @click="pick(p)"
      >
        {{ p.label }}
      </button>
      <span
        v-if="team.length && mine.length"
        class="mx-0.5 h-4 w-px bg-outline-gray-2"
        aria-hidden="true"
      />
      <button
        v-for="(p, i) in mine"
        :key="'m' + i"
        type="button"
        class="flex items-center gap-1 rounded-md border border-dashed border-outline-gray-3 bg-surface-white px-2 py-0.5 text-xs text-ink-gray-7 hover:border-outline-gray-4 hover:bg-surface-gray-1 disabled:opacity-60"
        :title="__('Your preset') + ' — ' + p.body"
        :disabled="rendering"
        @click="pick(p)"
      >
        <LucideUser class="size-3 text-ink-gray-4" />
        {{ p.label }}
      </button>
      <span
        v-if="!team.length && !mine.length && textPresets.fetched"
        class="text-xs text-ink-gray-4"
      >
        {{ __('No presets yet — click the pencil to add some.') }}
      </span>
    </div>
    <TextPresetsModal v-model="showEditor" />
  </div>
</template>

<script setup>
import TextPresetsModal from '@/components/Modals/TextPresetsModal.vue'
import { textPresets, renderPreset } from '@/composables/textPresets'
import { Tooltip, toast } from 'frappe-ui'
import { computed, ref } from 'vue'
import LucidePencil from '~icons/lucide/pencil'
import LucideUser from '~icons/lucide/user'

const props = defineProps({
  // CRM Lead name the tokens are filled from
  lead: { type: String, default: '' },
})

// (text, missing[]) — the filled-in message and any token the lead lacked
const emit = defineEmits(['pick'])

const team = computed(() => textPresets.data?.team || [])
const mine = computed(() => textPresets.data?.mine || [])
const showEditor = ref(false)
const rendering = ref(false)

async function pick(p) {
  if (rendering.value || !props.lead) return
  rendering.value = true
  try {
    const r = await renderPreset(props.lead, p.body)
    emit('pick', r.text, r.missing || [])
  } catch (e) {
    toast.error(e.messages?.[0] || __('Could not fill in the preset'))
  } finally {
    rendering.value = false
  }
}
</script>
