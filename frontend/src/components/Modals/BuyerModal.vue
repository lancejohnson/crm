<template>
  <Dialog
    v-model="show"
    :options="{
      title: editMode ? __('Edit buyer') : __('New buyer'),
      size: 'xl',
      actions: [
        {
          label: editMode ? __('Save') : __('Create'),
          variant: 'solid',
          onClick: submit,
        },
      ],
    }"
  >
    <template #body-content>
      <div class="flex flex-col gap-4">
        <div class="grid grid-cols-2 gap-4">
          <FormControl
            v-model="form.first_name"
            :label="__('First name')"
            :placeholder="__('Marcel')"
            required
          />
          <FormControl
            v-model="form.last_name"
            :label="__('Last name')"
            :placeholder="__('Cohen')"
          />
        </div>
        <div class="grid grid-cols-2 gap-4">
          <FormControl
            v-model="form.phone"
            :label="__('Phone')"
            :placeholder="__('(313) 555-0123')"
          />
          <FormControl
            v-model="form.email"
            type="email"
            :label="__('Email')"
            :placeholder="__('buyer@example.com')"
          />
        </div>
        <div class="grid grid-cols-2 gap-4">
          <!-- multi-select metros: chips + searchable picker (Census MSA list) -->
          <div class="space-y-1.5">
            <label class="block text-xs text-ink-gray-5">
              {{ __('Metro areas') }}
            </label>
            <div v-if="form.metro_areas.length" class="flex flex-wrap gap-1">
              <span
                v-for="m in form.metro_areas"
                :key="m"
                class="flex items-center gap-1 rounded bg-surface-gray-2 px-1.5 py-0.5 text-xs text-ink-gray-7"
              >
                {{ m }}
                <button
                  class="text-ink-gray-4 hover:text-ink-gray-7"
                  @click="removeMetro(m)"
                >
                  ✕
                </button>
              </span>
            </div>
            <Autocomplete
              :options="metroOptions"
              :modelValue="''"
              :placeholder="__('Add a metro…')"
              @update:modelValue="addMetro"
            >
              <template #footer="{ value: q, close }">
                <Button
                  v-if="q && !metroExists(q)"
                  variant="ghost"
                  class="w-full !justify-start"
                  :label="__('Create') + ' “' + q + '”'"
                  iconLeft="plus"
                  @click="createMetro(q, close)"
                />
              </template>
            </Autocomplete>
          </div>
          <FormControl
            v-model="form.buyer_type"
            :label="__('Buyer type')"
            :placeholder="__('Cash Buyer, Landlord…')"
          />
        </div>
        <FormControl
          v-model="form.buybox"
          type="textarea"
          :label="__('Buybox')"
          :placeholder="__('Price range, property types, zips… (free-form for now)')"
        />
        <ErrorMessage :message="error" />
        <!-- duplicate found: link to the existing buyer instead of creating -->
        <div
          v-if="duplicate"
          class="flex items-center justify-between rounded-lg bg-surface-amber-1 px-3 py-2 text-sm text-ink-amber-3"
        >
          <span>{{ __('Buyer already exists:') }} {{ duplicate.buyer_name }}</span>
          <Button
            variant="subtle"
            :label="__('Open')"
            @click="openDuplicate"
          />
        </div>
      </div>
    </template>
  </Dialog>
</template>

<script setup>
import Autocomplete from '@/components/frappe-ui/Autocomplete.vue'
import { Dialog, FormControl, ErrorMessage, Button, call, createResource } from 'frappe-ui'
import { ref, watch, computed } from 'vue'
import { useRouter } from 'vue-router'

const props = defineProps({
  // pass an existing buyer object (from get_buyer) to edit; omit to create
  buyer: { type: Object, default: null },
  // set false to skip navigating to the new buyer's page after create
  // (e.g. when creating from the Dispo board's Add-buyer flow)
  redirect: { type: Boolean, default: true },
})
const emit = defineEmits(['saved'])
const show = defineModel()
const router = useRouter()

const editMode = computed(() => !!props.buyer?.name)

const blank = () => ({
  first_name: '',
  last_name: '',
  phone: '',
  email: '',
  buyer_type: '',
  metro_areas: [],
  buybox: '',
})
const form = ref(blank())
const error = ref('')
const duplicate = ref(null)

watch(show, (v) => {
  if (!v) return
  error.value = ''
  duplicate.value = null
  form.value = props.buyer
    ? {
        first_name: props.buyer.first_name || '',
        last_name: props.buyer.last_name || '',
        phone: props.buyer.phone || '',
        email: props.buyer.email || '',
        buyer_type: props.buyer.buyer_type || '',
        metro_areas: [...(props.buyer.metros || [])],
        buybox: props.buyer.buybox || '',
      }
    : blank()
})

// searchable Census-MSA list; already-picked metros drop out of the options
const metros = createResource({ url: 'crm.api.buyers.get_metro_areas', auto: true })
const metroOptions = computed(() =>
  (metros.data || [])
    .filter((m) => !form.value.metro_areas.includes(m.name))
    .map((m) => ({ label: m.metro_name, value: m.name })),
)

function metroExists(q) {
  const want = q.trim().toLowerCase()
  return (metros.data || []).some((m) => m.metro_name.toLowerCase() === want)
}

function addMetro(option) {
  const name = option?.value
  if (name && !form.value.metro_areas.includes(name)) {
    form.value.metro_areas.push(name)
  }
}

function removeMetro(name) {
  form.value.metro_areas = form.value.metro_areas.filter((m) => m !== name)
}

async function createMetro(value, close) {
  try {
    const r = await call('crm.api.buyers.create_metro_area', {
      metro_name: value,
    })
    if (!form.value.metro_areas.includes(r.name)) {
      form.value.metro_areas.push(r.name)
    }
    metros.reload()
    close()
  } catch (e) {
    error.value = e.messages?.[0] || e.message
  }
}

async function submit() {
  error.value = ''
  duplicate.value = null
  if (!form.value.first_name.trim()) {
    error.value = __('First name is required.')
    return
  }
  try {
    if (editMode.value) {
      await call('crm.api.buyers.update_buyer', {
        buyer: props.buyer.name,
        updates: form.value,
      })
      show.value = false
      emit('saved')
    } else {
      const r = await call('crm.api.buyers.create_buyer', { ...form.value })
      if (r.duplicate) {
        duplicate.value = r
        return
      }
      show.value = false
      emit('saved', r.buyer)
      if (props.redirect) {
        router.push({ name: 'Buyer', params: { buyerId: r.buyer } })
      }
    }
  } catch (e) {
    error.value = e.messages?.[0] || e.message
  }
}

function openDuplicate() {
  show.value = false
  router.push({ name: 'Buyer', params: { buyerId: duplicate.value.duplicate } })
}
</script>
