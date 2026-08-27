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

  <!-- The map and the tray each scroll internally, so this page normally does
       not scroll at all -- that is what gives the tray a bounded height to
       scroll inside.

       `overflow-y-auto` rather than `hidden` is the floor under that, not a
       change of plan. The map now claims a minimum height instead of accepting
       whatever the calculator leaves it, and on a short window the two together
       can exceed the viewport: measured at 899px with the calculator open, the
       content came to 1,030px and `hidden` silently ATE the bottom 174px --
       including the legend, with no way to reach it. The map keeps its real
       height either way; this just means the remainder is scrollable rather
       than gone. Same trade the lead desk already makes. -->
  <div class="flex min-h-0 flex-1 flex-col overflow-y-auto px-3 py-3 sm:px-5 sm:py-4">
    <CompsView v-if="leadId" :lead="leadId" :address="address" page-mode />
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
import { computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { sidebarCollapsedOverride } from '@/composables/settings'

const props = defineProps({ leadId: { type: String, required: true } })
const router = useRouter()

// This page is a map. Every pixel the nav holds is a pixel the map does not get,
// and the page is opened in its own tab from the lead -- nobody arrives here to
// navigate somewhere else. An OVERRIDE rather than a write to the stored
// preference, so closing this tab cannot leave the rest of the CRM collapsed;
// hitting Expand still works and, being a deliberate act, wins from then on.
onMounted(() => {
  sidebarCollapsedOverride.value = true
})
onUnmounted(() => {
  sidebarCollapsedOverride.value = null
})

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
