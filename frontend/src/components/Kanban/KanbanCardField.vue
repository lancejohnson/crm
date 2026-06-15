<template>
  <!--
    Wraps a single Kanban-card field row. The display content is passed in via
    the default slot (so each page keeps its own field rendering); this component
    layers on the hover-only affordances:
      - phone / address fields  -> a copy-to-clipboard icon
      - any other editable field -> a pencil that opens an inline editor popover
    Nothing is shown until the row is hovered.
  -->
  <div class="group/kbf relative flex min-w-0 items-center gap-2">
    <div class="flex min-w-0 flex-1 items-center gap-2 truncate">
      <slot />
    </div>

    <div
      v-if="action !== 'none'"
      class="absolute right-0 top-1/2 -translate-y-1/2 items-center rounded bg-surface-white pl-1"
      :class="editorOpen ? 'flex' : 'hidden group-hover/kbf:flex'"
    >
      <!-- Copy: phone & address fields -->
      <Tooltip v-if="action === 'copy'" :text="__('Copy')">
        <button
          class="flex rounded p-1 text-ink-gray-5 hover:bg-surface-gray-2 hover:text-ink-gray-8"
          @click.stop.prevent="copyToClipboard(copyText)"
        >
          <FeatherIcon name="copy" class="h-3.5 w-3.5" />
        </button>
      </Tooltip>

      <!-- Edit: everything else that isn't read-only -->
      <Popover
        v-else-if="action === 'edit'"
        placement="bottom-end"
        @open="onEditorOpen"
        @close="editorOpen = false"
      >
        <template #target="{ togglePopover }">
          <Tooltip :text="__('Edit')">
            <button
              class="flex rounded p-1 text-ink-gray-5 hover:bg-surface-gray-2 hover:text-ink-gray-8"
              @click.stop.prevent="togglePopover()"
            >
              <EditIcon class="h-3.5 w-3.5" />
            </button>
          </Tooltip>
        </template>
        <template #body="{ close }">
          <div
            class="min-w-52 rounded-lg border border-gray-100 bg-surface-white p-2 shadow-xl"
            @click.stop
          >
            <div class="mb-1.5 px-0.5 text-xs text-ink-gray-5">
              {{ __(fieldMeta.label || fieldName) }}
            </div>

            <FormControl
              v-if="fieldMeta.fieldtype === 'Select'"
              v-model="editValue"
              type="select"
              :options="fieldMeta.options"
              @update:modelValue="(v) => save(v, close)"
            />

            <FormControl
              v-else-if="fieldMeta.fieldtype === 'Check'"
              v-model="editValue"
              type="checkbox"
              @change="(e) => save(e.target.checked ? 1 : 0, close)"
            />

            <Link
              v-else-if="fieldMeta.fieldtype === 'User'"
              :value="editValue"
              doctype="User"
              :filters="fieldMeta.filters"
              :hideMe="true"
              @change="(v) => save(v, close)"
            />

            <Link
              v-else-if="fieldMeta.fieldtype === 'Link'"
              :value="editValue"
              :doctype="fieldMeta.options"
              :filters="fieldMeta.filters"
              @change="(v) => save(v, close)"
            />

            <DatePicker
              v-else-if="fieldMeta.fieldtype === 'Date'"
              :value="editValue"
              :placeholder="fieldMeta.placeholder"
              @change="(v) => save(v, close)"
            />

            <DateTimePicker
              v-else-if="fieldMeta.fieldtype === 'Datetime'"
              :value="editValue"
              :placeholder="fieldMeta.placeholder"
              @change="(v) => save(v, close)"
            />

            <FormControl
              v-else-if="
                ['Small Text', 'Text', 'Long Text', 'Code'].includes(
                  fieldMeta.fieldtype,
                )
              "
              v-model="editValue"
              type="textarea"
              :placeholder="fieldMeta.placeholder"
              @keydown.enter.meta.prevent="save(editValue, close)"
            />

            <FormControl
              v-else
              v-model="editValue"
              type="text"
              :placeholder="fieldMeta.placeholder"
              @keydown.enter.prevent="save(editValue, close)"
            />

            <div
              v-if="showSaveButton"
              class="mt-2 flex justify-end"
            >
              <Button
                variant="solid"
                :label="__('Save')"
                :loading="saving"
                @click="save(editValue, close)"
              />
            </div>
          </div>
        </template>
      </Popover>
    </div>
  </div>
</template>

<script setup>
import EditIcon from '@/components/Icons/EditIcon.vue'
import Link from '@/components/Controls/Link.vue'
import { getMeta } from '@/stores/meta'
import { copyToClipboard } from '@/utils'
import { flt } from '@/utils/numberFormat.js'
import {
  Button,
  FormControl,
  Popover,
  Tooltip,
  DatePicker,
  DateTimePicker,
  call,
  toast,
} from 'frappe-ui'
import { ref, computed, watch } from 'vue'

const props = defineProps({
  doctype: { type: String, required: true },
  name: { type: String, required: true },
  fieldName: { type: String, required: true },
  // raw stored value used to seed the editor (display value may be formatted)
  rawValue: { default: '' },
  // text the copy button writes to the clipboard (the value the user sees)
  copyText: { type: String, default: '' },
})

const emit = defineEmits(['updated'])

const { getFields } = getMeta(props.doctype)

const fieldMeta = computed(
  () =>
    getFields().find((f) => f.fieldname === props.fieldName) || {
      fieldtype: 'Data',
      label: props.fieldName,
    },
)

// Phone fields are Data fields flagged with options "Phone" (the contact page
// also swaps mobile_no's options, so match the well-known fieldnames too).
const isPhone = computed(
  () =>
    fieldMeta.value.options === 'Phone' ||
    ['mobile_no', 'phone', 'actual_mobile_no'].includes(props.fieldName),
)
const isAddress = computed(() => /address/i.test(props.fieldName))

// Field types that don't make sense to edit from a compact card popover.
const uneditableTypes = [
  'Table',
  'Table MultiSelect',
  'Attach',
  'Attach Image',
  'Text Editor',
  'Markdown Editor',
  'HTML',
  'Geolocation',
  'Signature',
  'Read Only',
]
// Derived / system fields surfaced on cards that aren't real editable values.
const uneditableFields = [
  'sla_status',
  'first_response_time',
  'first_responded_on',
  'response_by',
]

const editable = computed(() => {
  const f = fieldMeta.value
  if (!f || f.read_only) return false
  if (props.fieldName.startsWith('_')) return false
  if (uneditableFields.includes(props.fieldName)) return false
  if (uneditableTypes.includes(f.fieldtype)) return false
  return true
})

const action = computed(() => {
  if (isPhone.value || isAddress.value) return props.copyText ? 'copy' : 'none'
  if (editable.value) return 'edit'
  return 'none'
})

const showSaveButton = computed(() =>
  ['Data', 'Small Text', 'Text', 'Long Text', 'Code', 'Int', 'Float',
    'Currency', 'Percent', 'Phone'].includes(fieldMeta.value.fieldtype),
)

const editValue = ref(props.rawValue)
const saving = ref(false)
// Keep the trigger (the popover's anchor) visible while the editor is open —
// otherwise moving the mouse off the row hides it and Popper repositions the
// open popover to the top-left corner.
const editorOpen = ref(false)

// Keep the editor seeded with the latest stored value (e.g. after a reload, or
// when the card is reused for a different record at the same position).
watch(
  () => props.rawValue,
  (v) => (editValue.value = v),
)

function onEditorOpen() {
  editorOpen.value = true
  editValue.value = props.rawValue
}

function coerce(value) {
  if (['Int', 'Float', 'Currency', 'Percent'].includes(fieldMeta.value.fieldtype)) {
    return flt(value)
  }
  return value
}

async function save(value, close) {
  const newValue = coerce(value)
  if (newValue === props.rawValue) {
    close?.()
    return
  }
  saving.value = true
  try {
    await call('frappe.client.set_value', {
      doctype: props.doctype,
      name: props.name,
      fieldname: { [props.fieldName]: newValue },
    })
    emit('updated', { fieldName: props.fieldName, value: newValue })
    close?.()
  } catch (e) {
    toast.error(e?.messages?.[0] || __('Could not update field'))
  } finally {
    saving.value = false
  }
}
</script>
