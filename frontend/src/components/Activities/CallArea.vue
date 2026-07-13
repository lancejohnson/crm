<template>
  <div ref="rootEl">
    <div class="mb-1 flex items-center justify-stretch gap-2 py-1 text-xs">
      <div class="inline-flex items-center flex-wrap gap-1 text-ink-gray-5">
        <span class="font-medium text-ink-gray-8">
          {{ formatPhone(call._caller.label) }}
        </span>
        <span>{{
          call.type == 'Incoming' ? __('called in') : __('made a call')
        }}</span>
      </div>
      <div class="ml-auto whitespace-nowrap">
        <Tooltip :text="formatDate(call.creation)">
          <div class="text-xs text-ink-gray-5">
            {{ formatDate(call.creation, 'h:mm a') }}
          </div>
        </Tooltip>
      </div>
    </div>
    <div
      class="flex flex-col gap-2 border cursor-pointer border-outline-gray-modals rounded-md bg-surface-cards px-3 py-2.5 text-ink-gray-9"
      @click="showCallLogDetailModal = true"
    >
      <div class="flex items-center justify-between">
        <div class="inline-flex gap-2 items-center text-base font-medium">
          <div>
            {{
              call.type == 'Incoming' ? __('Inbound Call') : __('Outbound Call')
            }}
          </div>
        </div>
        <div>
          <MultipleAvatar
            :avatars="[
              {
                image: call._caller.image,
                label: formatPhone(call._caller.label),
                name: formatPhone(call._caller.label),
              },
              {
                image: call._receiver.image,
                label: formatPhone(call._receiver.label),
                name: formatPhone(call._receiver.label),
              },
            ]"
            size="sm"
          />
        </div>
      </div>
      <div class="flex items-center flex-wrap gap-2">
        <Badge :label="formatDate(call.creation, 'MMM D, dddd')">
          <template #prefix>
            <CalendarIcon class="size-3" />
          </template>
        </Badge>
        <Badge v-if="call.status == 'Completed'" :label="call._duration">
          <template #prefix>
            <DurationIcon class="size-3" />
          </template>
        </Badge>
        <Badge
          v-if="call.recording_url"
          :label="call.show_transcript ? __('Hide Playback') : __('Playback')"
          class="cursor-pointer"
          @click.stop="call.show_transcript = !call.show_transcript"
        >
          <template #prefix>
            <PlayIcon class="size-3" />
          </template>
        </Badge>
        <a
          v-if="call.recording_url"
          :href="call.recording_url"
          target="_blank"
          rel="noopener"
          @click.stop
        >
          <Badge :label="__('Recording')" class="cursor-pointer">
            <template #prefix>
              <ExternalLinkIcon class="size-3" />
            </template>
          </Badge>
        </a>
        <Badge
          :label="statusLabelMap[call.status]"
          :theme="statusColorMap[call.status]"
        />
      </div>
      <div
        v-if="call.show_transcript && call.recording_url"
        class="border-t border-outline-gray-modals pt-2"
        @click.stop
      >
        <CallTranscript :call-log-name="call.name" :seek-to="seekTo" />
      </div>
      <div
        v-if="callLog?.data?.custom_ai_summary"
        class="flex flex-col gap-1 border-t border-outline-gray-modals pt-2"
        @click.stop
      >
        <div class="flex items-center gap-1 text-sm font-medium text-ink-gray-5">
          <SparkleIcon class="size-3.5" />
          {{ __('AI Summary') }}
        </div>
        <FadedScrollableDiv class="max-h-40 overflow-y-auto">
          <div class="whitespace-pre-line text-p-sm text-ink-gray-7">
            {{ callLog.data.custom_ai_summary }}
          </div>
        </FadedScrollableDiv>
      </div>
    </div>
    <CallLogDetailModal
      v-model="showCallLogDetailModal"
      v-model:callLogModal="showCallLogModal"
      v-model:callLog="callLog"
    />
    <CallLogModal
      v-if="showCallLogModal"
      v-model="showCallLogModal"
      :data="callLog.data"
    />
  </div>
</template>
<script setup>
import PlayIcon from '@/components/Icons/PlayIcon.vue'
import CalendarIcon from '@/components/Icons/CalendarIcon.vue'
import DurationIcon from '@/components/Icons/DurationIcon.vue'
import ExternalLinkIcon from '@/components/Icons/ExternalLinkIcon.vue'
import SparkleIcon from '@/components/Icons/SparkleIcon.vue'
import MultipleAvatar from '@/components/MultipleAvatar.vue'
import CallTranscript from '@/components/Activities/CallTranscript.vue'
import FadedScrollableDiv from '@/components/FadedScrollableDiv.vue'
import CallLogDetailModal from '@/components/Modals/CallLogDetailModal.vue'
import CallLogModal from '@/components/Modals/CallLogModal.vue'
import { statusLabelMap, statusColorMap } from '@/utils/callLog.js'
import { formatDate } from '@/utils'
import { formatPhone } from '@/utils/phoneFormat'
import { Badge, Tooltip, createResource } from 'frappe-ui'
import { reactive, ref, computed, watch, onMounted, nextTick } from 'vue'
import { useRoute } from 'vue-router'

const props = defineProps({
  activity: { type: Object, default: () => ({}) },
})

const call = reactive(props.activity)

// deep link (?call=<id>&t=<sec>): if this is the targeted call, auto-open its
// transcript, hand the timestamp to <CallTranscript>, and scroll it into view
const route = useRoute()
const rootEl = ref(null)
const isTarget = computed(
  () => route.query.call && String(route.query.call) === String(call.name),
)
const seekTo = computed(() =>
  isTarget.value && route.query.t != null ? Number(route.query.t) : null,
)
function revealIfTarget() {
  if (!isTarget.value) return
  call.show_transcript = true
  // the activity feed keeps loading/re-laying-out after this card mounts (and may
  // scroll itself back to top), so a single scrollIntoView gets lost. Re-scroll on
  // an interval until the card top is actually parked near the top of the viewport.
  let tries = 0
  const tick = () => {
    const el = rootEl.value
    if (!el) return
    el.scrollIntoView({ block: 'start' })
    const top = el.getBoundingClientRect().top
    const parked = top >= 0 && top < window.innerHeight * 0.4
    if (!parked && ++tries < 14) setTimeout(tick, 300)
  }
  nextTick(tick)
}
onMounted(revealIfTarget)
watch(isTarget, revealIfTarget)

const callLog = createResource({
  url: 'crm.fcrm.doctype.crm_call_log.crm_call_log.get_call_log',
  params: { name: call.name },
  cache: ['call_log', call.name],
  auto: true,
})
const showCallLogDetailModal = ref(false)
const showCallLogModal = ref(false)
</script>
