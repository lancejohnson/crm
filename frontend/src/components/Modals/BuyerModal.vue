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
          v-model="form.quo_tags"
          :label="__('Quo tags')"
          :placeholder="__('Buyer, Chicago… (comma-separated, syncs to Quo)')"
        />

        <div class="flex flex-col gap-3 border-t border-outline-gray-1 pt-4">
          <div class="text-sm font-medium text-ink-gray-8">{{ __('Buybox') }}</div>
          <div class="grid grid-cols-2 gap-4">
            <div class="space-y-1.5">
              <label class="block text-xs text-ink-gray-5">
                {{ __('Buying in') }}
              </label>
              <div class="min-h-8 rounded border border-outline-gray-2 px-2 py-1">
                <JsonListControl
                  v-model="form.buybox_cities"
                  :options="buyboxLocations.data || []"
                  :placeholder="__('Select cities, states, or ZIP codes…')"
                  :add-label="__('Add city, state, or ZIP')"
                />
              </div>
            </div>
            <div class="space-y-1.5">
              <label class="block text-xs text-ink-gray-5">
                {{ __('Property types') }}
              </label>
              <div class="min-h-8 rounded border border-outline-gray-2 px-2 py-1">
                <JsonListControl
                  v-model="form.buybox_property_types"
                  :options="BUYBOX_PROPERTY_TYPES"
                  :placeholder="__('Select types…')"
                />
              </div>
            </div>
          </div>
          <FormControl
            v-model="form.buybox"
            type="textarea"
            :label="__('Buybox notes')"
            :placeholder="__('Price range, condition, deal size…')"
          />
        </div>

        <!-- put the new buyer straight on a deal: the common case is meeting a
             buyer *about* a specific property, so it's here rather than a
             second trip through the Dispo board -->
        <div
          v-if="!editMode && withProperty"
          class="grid grid-cols-3 gap-4 border-t border-outline-gray-1 pt-4"
        >
          <div class="space-y-1.5">
            <label class="block text-xs text-ink-gray-5">
              {{ __('Add to property') }}
            </label>
            <Autocomplete
              :options="propertyOptions"
              :modelValue="property"
              :placeholder="__('No property')"
              @update:modelValue="(v) => (property = v?.value || '')"
            >
              <template #target="{ togglePopover }">
                <Button
                  variant="outline"
                  class="w-full !justify-between"
                  iconRight="chevron-down"
                  @click="togglePopover()"
                >
                  <span class="truncate">
                    {{ propertyLabel || __('No property') }}
                  </span>
                </Button>
              </template>
              <template #footer="{ close }">
                <Button
                  v-if="property"
                  variant="ghost"
                  class="w-full !justify-start"
                  :label="__('Clear')"
                  iconLeft="x"
                  @click="property = ''; close()"
                />
              </template>
            </Autocomplete>
          </div>
          <FormControl
            v-model="stage"
            type="select"
            :label="__('Board stage')"
            :options="STAGES"
            :disabled="!property"
          />
          <div class="space-y-1.5">
            <label class="block text-xs text-ink-gray-5">
              {{ __('Assign to') }}
            </label>
            <Autocomplete
              :options="userOptions"
              :modelValue="assignee"
              :placeholder="__('Nobody')"
              @update:modelValue="(v) => (assignee = v?.value || '')"
            >
              <template #target="{ togglePopover }">
                <Button
                  variant="outline"
                  class="w-full !justify-between"
                  iconRight="chevron-down"
                  @click="togglePopover()"
                >
                  <span class="truncate">
                    {{ assigneeLabel || __('Nobody') }}
                  </span>
                </Button>
              </template>
              <template #footer="{ close }">
                <Button
                  v-if="assignee"
                  variant="ghost"
                  class="w-full !justify-start"
                  :label="__('Clear')"
                  iconLeft="x"
                  @click="assignee = ''; close()"
                />
              </template>
            </Autocomplete>
          </div>
        </div>

        <ErrorMessage :message="error" />
        <!-- duplicate found: link to the existing buyer instead of creating -->
        <div
          v-if="duplicate"
          class="flex items-center justify-between rounded-lg bg-surface-amber-1 px-3 py-2 text-sm text-ink-amber-3"
        >
          <span>{{ __('Buyer already exists:') }} {{ duplicate.buyer_name }}</span>
          <div class="flex gap-2">
            <!-- the buyer we already have is the one they meant; attaching it
                 to the chosen property is what they were trying to do -->
            <Button
              v-if="property"
              variant="solid"
              :label="__('Add to property')"
              @click="attachDuplicate"
            />
            <Button variant="subtle" :label="__('Open')" @click="openDuplicate" />
          </div>
        </div>
      </div>
    </template>
  </Dialog>
</template>

<script setup>
import Autocomplete from '@/components/frappe-ui/Autocomplete.vue'
import JsonListControl from '@/components/Controls/JsonListControl.vue'
import {
  Dialog,
  FormControl,
  ErrorMessage,
  Button,
  call,
  createResource,
  toast,
} from 'frappe-ui'
import { ref, watch, computed } from 'vue'
import { useRouter } from 'vue-router'
import { usersStore } from '@/stores/users'

const props = defineProps({
  // pass an existing buyer object (from get_buyer) to edit; omit to create
  buyer: { type: Object, default: null },
  // set false to skip navigating to the new buyer's page after create
  // (e.g. when creating from the Dispo board's Add-buyer flow)
  redirect: { type: Boolean, default: true },
  // set false where the caller already knows the property (AddBuyerToDealModal
  // attaches the buyer itself, so a second picker would just contradict it)
  withProperty: { type: Boolean, default: true },
  // pre-selected property (a CRM Lead), e.g. from a dispo board
  lead: { type: String, default: '' },
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
  quo_tags: '',
  metro_areas: [],
  buybox_cities: [],
  buybox_property_types: [],
  buybox: '',
})
const form = ref(blank())
const error = ref('')
const duplicate = ref(null)

// optional "put this buyer on a deal" block (create mode only)
const property = ref('')
const stage = ref('New')
const assignee = ref('')

const STAGES = [
  'New',
  'Attempted to Contact',
  'Interested',
  'Offer Made',
  'Not Interested',
]

const BUYBOX_PROPERTY_TYPES = [
  'Single Family',
  'Multifamily',
  'Condo / Townhome',
  'Land',
  'Mobile Home',
  'Commercial',
]
const buyboxLocations = createResource({
  // Keep the legacy endpoint so local UI verification works before backend deploy.
  url: 'crm.api.buyers.get_buybox_cities',
  auto: true,
})

// under-contract + dispo properties, the same set the bulk importer offers
const properties = createResource({
  url: 'crm.api.buyer_import.get_import_properties',
  transform: (d) => d || [],
})
const propertyOptions = computed(() =>
  (properties.data || []).map((p) => ({ label: p.label, value: p.lead })),
)
const propertyLabel = computed(
  () => (properties.data || []).find((p) => p.lead === property.value)?.label || '',
)

// NOTE: read through the store object, don't destructure. Pinia setup-stores
// unwrap computeds on access, so `const { allUsers } = usersStore()` hands back
// a plain (and, at setup time, empty) array that never updates — which is why
// the chip row rendered blank. `users` is the raw resource whose .data is
// {allUsers, crmUsers}, not an array, so that's no good either.
const usersStoreRef = usersStore()
const userOptions = computed(() =>
  (usersStoreRef.allUsers || [])
    .filter((u) => u.name && !['Administrator', 'Guest'].includes(u.name) && u.enabled !== 0)
    .map((u) => ({ label: u.full_name || u.name, value: u.name })),
)
const assigneeLabel = computed(
  () => userOptions.value.find((u) => u.value === assignee.value)?.label || '',
)

/** Attach + assign a buyer we just created (or matched). Never fatal: the
 *  buyer exists either way, so a failure here is reported, not rolled back. */
async function placeBuyer(name) {
  if (property.value) {
    await call('crm.api.buyers.add_buyer_to_lead', {
      lead: property.value,
      buyer: name,
      stage: stage.value,
    })
  }
  if (assignee.value) {
    await call('crm.api.buyer_import.assign_buyers', {
      buyers: JSON.stringify([name]),
      users: JSON.stringify([assignee.value]),
    })
  }
}

async function attachDuplicate() {
  try {
    await placeBuyer(duplicate.value.duplicate)
    toast.success(__('Added to {0}', [propertyLabel.value]))
    show.value = false
    emit('saved', duplicate.value.duplicate)
  } catch (e) {
    error.value = e.messages?.[0] || e.message
  }
}

watch(show, (v) => {
  if (!v) return
  error.value = ''
  duplicate.value = null
  property.value = props.lead || ''
  stage.value = 'New'
  assignee.value = ''
  if (!props.buyer && props.withProperty) properties.reload()
  form.value = props.buyer
    ? {
        first_name:
          props.buyer.first_name ||
          (props.buyer.buyer_name || '').trim().split(/\s+/)[0] ||
          '',
        last_name:
          props.buyer.last_name ||
          (props.buyer.buyer_name || '').trim().split(/\s+/).slice(1).join(' '),
        phone: props.buyer.phone || '',
        email: props.buyer.email || '',
        buyer_type: props.buyer.buyer_type || '',
        quo_tags: props.buyer.quo_tags || '',
        metro_areas: [...(props.buyer.metros || [])],
        buybox_cities: [...(props.buyer.buybox_cities || [])],
        buybox_property_types: [...(props.buyer.buybox_property_types || [])],
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
      try {
        await placeBuyer(r.buyer)
      } catch (e) {
        // the buyer exists now; don't strand the user in the form over a
        // failed attach/assign — say so and let them fix it on the board
        toast.error(e.messages?.[0] || e.message || __('Could not add to property.'))
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
