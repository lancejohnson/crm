<template>
  <Button
    :label="__('Kanban settings')"
    v-bind="$attrs"
    :iconLeft="KanbanIcon"
    @click="showDialog = true"
  />
  <Dialog v-model="showDialog" :options="{ title: __('Kanban Settings') }">
    <template #body-content>
      <div>
        <div class="text-base text-ink-gray-8 mb-2">
          {{ __('Column Field') }}
        </div>
        <Autocomplete
          v-if="columnFields"
          value=""
          :options="columnFields"
          @change="(f) => (columnField = f)"
        >
          <template #target="{ togglePopover }">
            <Button
              class="w-full !justify-start"
              :label="columnField.label"
              @click="togglePopover()"
            />
          </template>
        </Autocomplete>
        <div class="text-base text-ink-gray-8 mb-2 mt-4">
          {{ __('Title Field') }}
        </div>
        <Autocomplete
          value=""
          :options="fields"
          @change="(f) => (titleField = f)"
        >
          <template #target="{ togglePopover }">
            <Button
              class="w-full !justify-start"
              :label="titleField.label"
              @click="togglePopover()"
            />
          </template>
        </Autocomplete>
      </div>
      <div class="mt-4">
        <div class="text-base text-ink-gray-8 mb-1">
          {{ __('Fields Order') }}
        </div>
        <div class="text-sm text-ink-gray-5 mb-2">
          {{
            __(
              'Set an optional label shown before each field on the card. Tick "Show if blank" to keep a field on the card even when it has no value.',
            )
          }}
        </div>
        <Draggable
          :list="selectedFields"
          group="fields"
          item-key="fieldname"
          class="flex flex-col gap-1"
        >
          <template #item="{ element: field }">
            <div
              class="px-1 py-0.5 border border-outline-gray-modals rounded text-base text-ink-gray-8 flex items-center justify-between gap-2"
            >
              <div class="flex items-center gap-2 min-w-0">
                <DragVerticalIcon class="h-3.5 cursor-grab shrink-0" />
                <div class="truncate">{{ field.label }}</div>
              </div>
              <div class="flex items-center gap-2 shrink-0">
                <Tooltip
                  :text="
                    __('Show this field on the card even when it has no value')
                  "
                >
                  <div>
                    <FormControl
                      v-model="field.showBlank"
                      type="checkbox"
                      size="sm"
                      :label="__('Show if blank')"
                      @click.stop
                    />
                  </div>
                </Tooltip>
                <FormControl
                  v-model="field.customLabel"
                  type="text"
                  size="sm"
                  :placeholder="__('Card label')"
                  class="w-28"
                  @click.stop
                />
                <Button variant="ghost" icon="x" @click="removeField(field)" />
              </div>
            </div>
          </template>
        </Draggable>
        <Autocomplete value="" :options="fields" @change="(e) => addField(e)">
          <template #target="{ togglePopover }">
            <Button
              class="w-full mt-2"
              :label="__('Add Field')"
              iconLeft="plus"
              @click="togglePopover()"
            />
          </template>
          <template #item-label="{ option }">
            <div class="flex flex-col gap-1 text-ink-gray-9">
              <div>{{ option.label }}</div>
              <div class="text-ink-gray-4 text-sm">
                {{ `${option.fieldname} - ${option.fieldtype}` }}
              </div>
            </div>
          </template>
        </Autocomplete>
      </div>
    </template>
    <template #actions>
      <Button
        class="w-full"
        variant="solid"
        :label="__('Apply')"
        @click="apply"
      />
    </template>
  </Dialog>
</template>
<script setup>
import DragVerticalIcon from '@/components/Icons/DragVerticalIcon.vue'
import KanbanIcon from '@/components/Icons/KanbanIcon.vue'
import Autocomplete from '@/components/frappe-ui/Autocomplete.vue'
import { getMeta } from '@/stores/meta'
import { Dialog, Tooltip } from 'frappe-ui'
import Draggable from 'vuedraggable'
import { ref, computed, nextTick, watch } from 'vue'

const props = defineProps({
  doctype: {
    type: String,
    required: true,
  },
})

const emit = defineEmits(['update'])

const list = defineModel({ type: Object })
const showDialog = ref(false)

const columnField = computed({
  get: () => {
    let fieldname = list.value?.data?.column_field
    if (!fieldname) return ''

    return columnFields.value?.find((field) => field.fieldname === fieldname)
  },
  set: (val) => {
    list.value.data.column_field = val.fieldname
  },
})

const titleField = computed({
  get: () => {
    let fieldname = list.value?.data?.title_field
    if (!fieldname) return ''

    return fields.value?.find((field) => field.fieldname === fieldname)
  },
  set: (val) => {
    list.value.data.title_field = val.fieldname
  },
})

const columnFields = computed(() => {
  return (
    fields.value?.filter((field) =>
      ['Link', 'Select'].includes(field.fieldtype),
    ) || []
  )
})

const { getFields } = getMeta(props.doctype)

const fields = computed(() => {
  const _fields = getFields({ withStandardFields: true }) || []
  if (!_fields.length) return []

  let mapped = _fields.map((field) => {
    return {
      label: field.label,
      value: field.fieldname,
      fieldname: field.fieldname,
      fieldtype: field.fieldtype,
    }
  })

  // computed pseudo-field (server fills it per-card in get_data) — not in meta
  if (props.doctype === 'CRM Lead') {
    mapped.push({
      label: __('Last Communication'),
      value: '_last_comm',
      fieldname: '_last_comm',
      fieldtype: 'Datetime',
    })
  }

  return mapped
})

// The editable list of cards fields. Each row carries the field meta (for
// display) plus the user's optional `customLabel` shown on the card.
const selectedFields = ref([])

// kanban_fields persists as a mix of bare fieldnames (no custom label) and
// { fieldname, label, showBlank } objects (custom label and/or "show if blank"
// set) — read all shapes.
function buildSelectedFields() {
  let rows = list.value?.data?.kanban_fields || []
  if (typeof rows === 'string') {
    try {
      rows = JSON.parse(rows)
    } catch {
      rows = []
    }
  }

  selectedFields.value = rows
    .map((row) => {
      const fieldname = typeof row === 'string' ? row : row.fieldname
      const customLabel = typeof row === 'string' ? '' : row.label || ''
      const showBlank = typeof row === 'string' ? false : !!row.showBlank
      const field = fields.value?.find((f) => f.fieldname === fieldname)
      if (!field) return null
      return { ...field, customLabel, showBlank }
    })
    .filter(Boolean)
}

// keep only a bare fieldname when there's no custom label and no "show if
// blank", so views without either stay byte-identical and back-compatible
function serializeField(row) {
  const label = (row.customLabel || '').trim()
  if (!label && !row.showBlank) return row.fieldname
  const out = { fieldname: row.fieldname }
  if (label) out.label = label
  if (row.showBlank) out.showBlank = true
  return out
}

watch(showDialog, (open) => {
  if (open) buildSelectedFields()
})

function addField(field) {
  if (!field) return
  if (selectedFields.value.some((f) => f.fieldname === field.fieldname)) return
  selectedFields.value.push({ ...field, customLabel: '', showBlank: false })
}

function removeField(field) {
  selectedFields.value = selectedFields.value.filter(
    (f) => f.fieldname !== field.fieldname,
  )
}

function apply() {
  nextTick(() => {
    showDialog.value = false
    emit('update', {
      column_field: columnField.value.fieldname,
      title_field: titleField.value.fieldname,
      kanban_fields: selectedFields.value.map(serializeField),
    })
  })
}
</script>
