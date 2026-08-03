<template>
  <Dialog v-model="show" :options="{ size: '3xl' }">
    <template #body>
      <div class="flex max-h-[85vh] flex-col bg-surface-modal">
        <div class="flex items-start justify-between gap-4 border-b px-5 py-4 sm:px-6">
          <div class="min-w-0">
            <div class="mb-1 flex flex-wrap items-center gap-2">
              <Badge
                v-if="lead?.status"
                variant="subtle"
                theme="gray"
                :label="lead.status"
              />
              <Badge
                v-if="item?.total_calls > 1"
                variant="subtle"
                theme="blue"
                :label="__('Call {0} of {1}', [item.call_number, item.total_calls])"
              />
            </div>
            <h2 class="truncate text-2xl font-semibold text-ink-gray-9">
              {{ lead?.lead_name || item?.lead_name || __('Lead details') }}
            </h2>
            <div class="mt-2 flex flex-col gap-1 text-sm text-ink-gray-6">
              <a
                v-if="lead?.mobile_no"
                :href="callHref(lead.mobile_no)"
                class="w-fit text-ink-blue-3 hover:underline"
              >
                {{ formatPhone(lead.mobile_no) }}
              </a>
              <a
                v-if="lead?.address"
                :href="mapsUrl"
                target="_blank"
                rel="noopener noreferrer"
                class="max-w-full truncate hover:text-ink-gray-8 hover:underline"
                :title="lead.address"
              >
                {{ lead.address }}
              </a>
              <a
                v-if="lead?.email"
                :href="`mailto:${lead.email}`"
                class="w-fit hover:text-ink-gray-8 hover:underline"
              >
                {{ lead.email }}
              </a>
            </div>
          </div>
          <Button variant="ghost" icon="x" class="shrink-0" @click="show = false" />
        </div>

        <div v-if="snapshot.loading" class="flex min-h-64 items-center justify-center">
          <LoadingIndicator class="size-6 text-ink-gray-5" />
        </div>

        <div v-else-if="snapshot.data" class="flex-1 overflow-y-auto px-5 py-4 sm:px-6">
          <div
            v-if="item?.reason"
            class="mb-4 rounded-lg border border-outline-gray-1 bg-surface-gray-1 px-3 py-2 text-sm text-ink-gray-6"
          >
            <span class="font-medium text-ink-gray-8">{{ __('Why today:') }}</span>
            {{ item.reason }}
          </div>

          <section v-if="lead?.summary || details.length" class="mb-5">
            <h3 class="mb-2 text-sm font-semibold text-ink-gray-8">
              {{ __('Lead details') }}
            </h3>
            <div
              v-if="lead?.summary"
              class="mb-2 whitespace-pre-wrap rounded-lg bg-surface-gray-1 px-3 py-2 text-sm text-ink-gray-7"
            >
              {{ lead.summary }}
            </div>
            <div class="grid grid-cols-1 gap-x-5 gap-y-2 rounded-lg border border-outline-gray-1 p-3 sm:grid-cols-2">
              <div v-for="field in details" :key="field.fieldname" class="min-w-0">
                <div class="text-xs text-ink-gray-5">{{ __(field.label) }}</div>
                <div class="truncate text-sm text-ink-gray-8" :title="String(field.value)">
                  {{ field.value }}
                </div>
              </div>
            </div>
          </section>

          <section class="mb-5">
            <div class="mb-2 flex items-center gap-1.5">
              <h3 class="text-sm font-semibold text-ink-gray-8">{{ __('Open tasks') }}</h3>
              <span class="text-xs text-ink-gray-4">{{ tasks.length }}</span>
            </div>
            <div
              v-if="tasks.length"
              class="divide-y divide-outline-gray-1 overflow-hidden rounded-lg border border-outline-gray-1"
            >
              <div v-for="task in tasks" :key="task.name" class="flex items-start gap-2 px-3 py-2.5">
                <FeatherIcon name="circle" class="mt-0.5 size-4 shrink-0 text-ink-gray-4" />
                <div class="min-w-0 flex-1">
                  <div class="text-sm text-ink-gray-8">{{ task.title }}</div>
                  <div v-if="task.description" class="mt-0.5 line-clamp-2 text-xs text-ink-gray-5">
                    {{ task.description }}
                  </div>
                </div>
                <Tooltip
                  v-if="task.due_date"
                  :text="formatDate(task.due_date, 'ddd, MMM D, YYYY | hh:mm a')"
                >
                  <span class="shrink-0 text-xs" :class="dueClass(task.due_date)">
                    {{ __(timeAgo(task.due_date)) }}
                  </span>
                </Tooltip>
              </div>
            </div>
            <div v-else class="rounded-lg bg-surface-gray-1 px-3 py-3 text-sm text-ink-gray-5">
              {{ __('No open tasks') }}
            </div>
          </section>

          <section>
            <div class="mb-2 flex items-center gap-1.5">
              <h3 class="text-sm font-semibold text-ink-gray-8">{{ __('Notes & comments') }}</h3>
              <span class="text-xs text-ink-gray-4">{{ recent.length }}</span>
            </div>
            <div v-if="recent.length" class="flex flex-col gap-2">
              <div
                v-for="entry in recent"
                :key="`${entry.type}-${entry.name}`"
                class="rounded-lg border border-outline-gray-1 px-3 py-2.5"
              >
                <div class="mb-1 flex items-center justify-between gap-3">
                  <div class="truncate text-sm font-medium text-ink-gray-8">
                    {{ entry.title }}
                  </div>
                  <div class="shrink-0 text-xs text-ink-gray-4">
                    {{ ownerName(entry.owner) }} · {{ __(timeAgo(entry.when)) }}
                  </div>
                </div>
                <TextEditor
                  v-if="entry.content"
                  :content="entry.content"
                  :editable="false"
                  editor-class="prose-sm max-w-none text-sm text-ink-gray-6 focus:outline-none"
                />
              </div>
            </div>
            <div v-else class="rounded-lg bg-surface-gray-1 px-3 py-3 text-sm text-ink-gray-5">
              {{ __('No notes or comments yet') }}
            </div>
          </section>
        </div>

        <div class="flex justify-end gap-2 border-t px-5 py-3 sm:px-6">
          <Button :label="__('Close')" @click="show = false" />
          <Button
            variant="solid"
            :label="__('Open full lead')"
            @click="openFullLead"
          >
            <template #suffix><FeatherIcon name="arrow-up-right" class="size-4" /></template>
          </Button>
        </div>
      </div>
    </template>
  </Dialog>
</template>

<script setup>
import { usersStore } from '@/stores/users'
import { callHref, formatPhone } from '@/utils/phoneFormat'
import { dueColor, formatDate, parseColor, timeAgo } from '@/utils'
import {
  Badge,
  Button,
  Dialog,
  FeatherIcon,
  LoadingIndicator,
  TextEditor,
  Tooltip,
  createResource,
} from 'frappe-ui'
import { computed, watch } from 'vue'
import { useRouter } from 'vue-router'

const props = defineProps({
  item: { type: Object, default: null },
})

const show = defineModel({ type: Boolean })
const router = useRouter()
const { getUser } = usersStore()

const snapshot = createResource({
  url: 'crm.api.today_board.get_today_lead_snapshot',
})

watch(
  [show, () => props.item?.lead],
  ([isOpen, lead]) => {
    if (!isOpen || !lead) return
    snapshot.params = { lead }
    snapshot.reload()
  },
  { immediate: true },
)

const lead = computed(() => snapshot.data?.lead || null)
const details = computed(() => snapshot.data?.details || [])
const tasks = computed(() => snapshot.data?.tasks || [])
const recent = computed(() => snapshot.data?.recent || [])
const mapsUrl = computed(() =>
  lead.value?.address
    ? `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(lead.value.address)}`
    : '',
)

function dueClass(date) {
  const color = dueColor(date)
  return color ? parseColor(color) : 'text-ink-gray-5'
}

function ownerName(owner) {
  return getUser(owner)?.full_name || owner
}

function openFullLead() {
  if (!props.item?.lead) return
  show.value = false
  router.push({ name: 'Lead', params: { leadId: props.item.lead } })
}
</script>
