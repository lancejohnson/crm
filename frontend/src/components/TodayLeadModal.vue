<template>
  <Dialog
    v-model="show"
    :options="{ size: '5xl', title: item?.lead_name || __('Lead details') }"
  >
    <template #body>
      <div class="flex h-[88vh] max-h-[88vh] flex-col overflow-hidden bg-surface-modal">
        <div class="flex items-start justify-between gap-4 border-b px-5 py-4 sm:px-6">
          <div class="min-w-0">
            <div class="mb-1 flex flex-wrap items-center gap-2">
              <Badge
                v-if="item?.lead_status"
                variant="subtle"
                theme="gray"
                :label="item.lead_status"
              />
              <Badge
                v-if="item?.total_calls > 1"
                variant="subtle"
                theme="blue"
                :label="__('Call {0} of {1}', [item.call_number, item.total_calls])"
              />
            </div>
            <h2 class="truncate text-2xl font-semibold text-ink-gray-9">
              {{ item?.lead_name || __('Lead details') }}
            </h2>
          </div>
          <Button variant="ghost" icon="x" class="shrink-0" @click="show = false" />
        </div>

        <div class="flex min-h-0 flex-1 flex-col md:flex-row">
          <aside class="shrink-0 border-b p-4 md:w-64 md:overflow-y-auto md:border-b-0 md:border-r sm:p-5">
            <div class="flex flex-col gap-2 text-sm text-ink-gray-6">
              <a
                v-if="item?.mobile_no"
                :href="callHref(item.mobile_no)"
                class="w-fit text-ink-blue-3 hover:underline"
              >
                {{ formatPhone(item.mobile_no) }}
              </a>
              <button
                v-if="item?.address"
                class="text-left hover:text-ink-blue-3 hover:underline"
                @click="emit('openAddress', item.address)"
              >
                {{ item.address }}
              </button>
              <a
                v-if="item?.email"
                :href="`mailto:${item.email}`"
                class="w-fit hover:text-ink-gray-8 hover:underline"
              >
                {{ item.email }}
              </a>
            </div>

            <div
              v-if="item?.reason"
              class="mt-4 rounded-lg border border-outline-gray-1 bg-surface-gray-1 px-3 py-2 text-sm text-ink-gray-6"
            >
              <div class="mb-0.5 text-xs font-medium text-ink-gray-8">
                {{ __('Why today') }}
              </div>
              {{ item.reason }}
            </div>
          </aside>

          <!-- Reuse the lead page's actual activity surface. This keeps calls,
               texts, comments, the To-do quick-add, completion checkboxes, and
               realtime behavior identical instead of maintaining a second copy. -->
          <div class="flex min-h-0 flex-1 flex-col overflow-hidden bg-surface-white">
            <Activities
              v-if="show && item?.lead"
              :key="item.lead"
              v-model:tabIndex="tabIndex"
              doctype="CRM Lead"
              :docname="item.lead"
              :tabs="tabs"
              :scroll-on-mount="false"
            />
          </div>
        </div>

        <div class="flex justify-end gap-2 border-t px-5 py-3 sm:px-6">
          <Button :label="__('Close')" @click="show = false" />
          <Button variant="solid" :label="__('Open full lead')" @click="openFullLead">
            <template #suffix><FeatherIcon name="arrow-up-right" class="size-4" /></template>
          </Button>
        </div>
      </div>
    </template>
  </Dialog>
</template>

<script setup>
import Activities from '@/components/Activities/Activities.vue'
import { callHref, formatPhone } from '@/utils/phoneFormat'
import { Badge, Button, Dialog, FeatherIcon } from 'frappe-ui'
import { ref, watch } from 'vue'
import { useRouter } from 'vue-router'

const props = defineProps({
  item: { type: Object, default: null },
})
const emit = defineEmits(['openAddress'])

const show = defineModel({ type: Boolean })
const router = useRouter()
const tabIndex = ref(0)
const tabs = [{ name: 'Activity', label: __('Activity') }]

watch(
  () => props.item?.lead,
  () => (tabIndex.value = 0),
)

function openFullLead() {
  if (!props.item?.lead) return
  show.value = false
  router.push({ name: 'Lead', params: { leadId: props.item.lead } })
}
</script>
