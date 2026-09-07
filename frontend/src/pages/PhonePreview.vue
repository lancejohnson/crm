<template>
  <LayoutHeader><template #left-header><Breadcrumbs :items="[{ label: 'Phone Preview' }]" /></template></LayoutHeader>
  <div class="max-w-xl px-5 py-6">
    <Badge label="Local design preview" theme="orange" />
    <h1 class="mt-4 text-xl font-semibold text-ink-gray-9">Your CRM, with a little phone tool</h1>
    <p class="mt-3 text-base leading-relaxed text-ink-gray-6">Open a real lead to see the phone dock, team status bar, live-one alert, and teammate chat alongside everyday work.</p>
    <p class="mt-3 text-sm leading-relaxed text-ink-gray-5">All phone activity is fictional and labeled demo. The lead behind it is real; nothing in this preview edits it. Normal CRM controls remain real.</p>
    <Button class="mt-5" variant="solid" iconLeft="phone" :loading="opening" @click="openLead">Open preview on a CRM lead</Button>
    <p v-if="error" class="mt-3 text-sm text-ink-red-4" role="alert">{{ error }}</p>
  </div>
</template>
<script setup>
import LayoutHeader from '@/components/LayoutHeader.vue'
import { Badge, Breadcrumbs, Button, call } from 'frappe-ui'
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { phonePreview } from '@/composables/phonePreview'
const router = useRouter()
const opening = ref(false)
const error = ref('')
async function openLead() {
  opening.value = true
  error.value = ''
  try {
    // Read only: use a real accessible lead as the workspace, not as a call target.
    const leads = await call('frappe.client.get_list', { doctype: 'CRM Lead', fields: ['name'], limit_page_length: 1 })
    if (!leads.length) { error.value = 'No accessible lead found. Open an existing lead, then add ?phonePreview=1 to its URL.'; return }
    phonePreview.enabled = true
    await router.push({ name: 'Lead', params: { leadId: leads[0].name }, query: { phonePreview: '1' } })
  } catch {
    error.value = 'Could not open a lead. Use an existing CRM lead URL with ?phonePreview=1.'
  } finally { opening.value = false }
}
</script>
