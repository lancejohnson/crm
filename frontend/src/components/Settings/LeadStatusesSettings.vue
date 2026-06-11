<template>
  <div class="flex h-full flex-col gap-6 py-8 px-6 text-ink-gray-8">
    <div class="flex justify-between px-2 text-ink-gray-8">
      <div class="flex flex-col gap-1">
        <h2 class="flex gap-2 text-xl font-semibold leading-none h-5">
          {{ __('Lead Statuses') }}
        </h2>
        <p class="text-p-base text-ink-gray-6">
          {{
            __(
              'Rename, recolor, reorder, add or remove the statuses available on leads. Renaming updates every lead currently using that status.',
            )
          }}
        </p>
      </div>
      <div class="flex item-center space-x-2 justify-end">
        <Button
          :label="__('Add Status')"
          variant="solid"
          iconLeft="plus"
          @click="addRow"
        />
      </div>
    </div>

    <div class="flex-1 flex flex-col overflow-y-auto">
      <div
        v-for="(row, i) in rows"
        :key="row.key"
        class="flex items-center gap-2 py-2 px-2 border-b border-outline-gray-modals"
      >
        <Dropdown :options="colorOptions(row)">
          <Button variant="ghost">
            <IndicatorIcon :class="parseColor(row.color)" />
          </Button>
        </Dropdown>
        <div class="flex-1">
          <TextInput
            v-model="row.label"
            :placeholder="__('Status name')"
            @blur="commitName(row)"
            @keydown.enter="$event.target.blur()"
          />
        </div>
        <div class="w-32 shrink-0">
          <Select
            v-model="row.type"
            :options="['Open', 'Ongoing', 'On Hold', 'Won', 'Lost']"
            @change="commitField(row, 'type', row.type)"
          />
        </div>
        <Button
          variant="ghost"
          icon="arrow-up"
          :disabled="i === 0"
          @click="move(i, -1)"
        />
        <Button
          variant="ghost"
          icon="arrow-down"
          :disabled="i === rows.length - 1"
          @click="move(i, 1)"
        />
        <Button variant="ghost" icon="x" @click="removeRow(row)" />
      </div>
      <div v-if="!rows.length" class="p-4 text-p-base text-ink-gray-5">
        {{ __('No statuses yet — add one above.') }}
      </div>
    </div>
  </div>
</template>

<script setup>
import IndicatorIcon from '@/components/Icons/IndicatorIcon.vue'
import { statusesStore } from '@/stores/statuses'
import { parseColor } from '@/utils'
import { Dropdown, TextInput, Select, Button, toast, call } from 'frappe-ui'
import { ref, h, onMounted } from 'vue'

const DOCTYPE = 'CRM Lead Status'
const COLORS = [
  'gray',
  'blue',
  'green',
  'teal',
  'cyan',
  'orange',
  'amber',
  'yellow',
  'red',
  'pink',
  'violet',
  'purple',
  'black',
]

const { leadStatuses } = statusesStore()

// local editable copy with raw color values (the store transforms colors
// into css classes, so fetch our own)
const rows = ref([])
let keyCounter = 0

async function load() {
  const data = await call('frappe.client.get_list', {
    doctype: DOCTYPE,
    fields: ['name', 'color', 'position', 'type'],
    order_by: 'position asc',
    limit_page_length: 0,
  })
  rows.value = data.map((d) => ({
    key: keyCounter++,
    name: d.name, // committed docname ('' = unsaved new row)
    label: d.name, // editable name
    color: d.color || 'gray',
    type: d.type || 'Open',
    position: d.position,
  }))
}

onMounted(load)

function refreshEverywhere() {
  leadStatuses.reload()
}

function errorOut(e) {
  toast.error(e.messages?.[0] || e.message || __('Something went wrong'))
  load()
}

async function commitName(row) {
  row.label = row.label.trim()
  if (!row.label || row.label === row.name) {
    row.label = row.name // revert empty edits on saved rows
    return
  }
  try {
    if (!row.name) {
      await call('frappe.client.insert', {
        doc: {
          doctype: DOCTYPE,
          lead_status: row.label,
          color: row.color,
          type: row.type,
          position: row.position,
        },
      })
    } else {
      await call('frappe.client.rename_doc', {
        doctype: DOCTYPE,
        old_name: row.name,
        new_name: row.label,
      })
    }
    row.name = row.label
    toast.success(__('Status saved'))
    refreshEverywhere()
  } catch (e) {
    errorOut(e)
  }
}

async function commitField(row, fieldname, value) {
  if (!row.name) return // unsaved row, will be committed with the name
  try {
    await call('frappe.client.set_value', {
      doctype: DOCTYPE,
      name: row.name,
      fieldname,
      value,
    })
    refreshEverywhere()
  } catch (e) {
    errorOut(e)
  }
}

function colorOptions(row) {
  return COLORS.map((color) => ({
    label: color,
    icon: () => h(IndicatorIcon, { class: parseColor(color) }),
    onClick: () => {
      row.color = color
      commitField(row, 'color', color)
    },
  }))
}

async function move(i, dir) {
  const a = rows.value[i]
  const b = rows.value[i + dir]
  if (!b) return
  ;[a.position, b.position] = [b.position, a.position]
  rows.value.splice(i, 1)
  rows.value.splice(i + dir, 0, a)
  await commitField(a, 'position', a.position)
  await commitField(b, 'position', b.position)
}

function addRow() {
  const maxPos = Math.max(0, ...rows.value.map((r) => r.position || 0))
  rows.value.push({
    key: keyCounter++,
    name: '',
    label: '',
    color: 'gray',
    type: 'Open',
    position: maxPos + 1,
  })
}

async function removeRow(row) {
  if (!row.name) {
    rows.value = rows.value.filter((r) => r.key !== row.key)
    return
  }
  try {
    await call('frappe.client.delete', { doctype: DOCTYPE, name: row.name })
    rows.value = rows.value.filter((r) => r.key !== row.key)
    toast.success(__('Status deleted'))
    refreshEverywhere()
  } catch (e) {
    errorOut(e)
  }
}
</script>
