<template>
  <LayoutHeader>
    <template #left-header>
      <Breadcrumbs :items="breadcrumbs" />
    </template>
    <template #right-header>
      <Button
        v-if="lead"
        :label="__('Open lead')"
        iconLeft="external-link"
        @click="openLead"
      />
    </template>
  </LayoutHeader>

  <div class="flex flex-1 flex-col overflow-y-auto px-4 py-4 sm:px-5">
    <CompsView
      v-if="leadId"
      :lead="leadId"
      :address="address"
      page-mode
    />
  </div>
</template>

<script setup>
/**
 * The comps map as its own PAGE, opened in a new tab from the lead.
 *
 * It was a modal until reps started actually underwriting from it: a modal is
 * the wrong container for something you sit with, cross-reference against the
 * lead, and pick comps in. As a tab it can be left open beside the lead, and it
 * gets the room for the property list under the map.
 */
import LayoutHeader from '@/components/LayoutHeader.vue'
import CompsView from '@/components/CompsView.vue'
import { Breadcrumbs, Button, createResource } from 'frappe-ui'
import { computed } from 'vue'
import { useRouter } from 'vue-router'

const props = defineProps({ leadId: { type: String, required: true } })
const router = useRouter()

// Only the address is needed for the header/title; the map fetches its own data.
const lead = createResource({
  url: 'frappe.client.get_value',
  params: {
    doctype: 'CRM Lead',
    filters: { name: props.leadId },
    fieldname: ['name', 'lead_name', 'property_address'],
  },
  auto: true,
  onSuccess: (d) => {
    if (d?.property_address) document.title = `Comps — ${d.property_address}`
  },
})

const address = computed(() => lead.data?.property_address || '')

const breadcrumbs = computed(() => [
  { label: __('Leads'), route: { name: 'Leads' } },
  {
    label: lead.data?.lead_name || props.leadId,
    route: { name: 'Lead', params: { leadId: props.leadId } },
  },
  { label: __('Comps') },
])

function openLead() {
  router.push({ name: 'Lead', params: { leadId: props.leadId } })
}
</script>
