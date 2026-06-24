<template>
  <LayoutHeader>
    <template #left-header>
      <ViewBreadcrumbs v-model="viewControls" routeName="Leads" />
    </template>
    <template #right-header>
      <CustomActions
        v-if="leadsListView?.customListActions"
        :actions="leadsListView.customListActions"
      />
      <Button
        variant="solid"
        :label="__('Create')"
        iconLeft="plus"
        @click="showLeadModal = true"
      />
    </template>
  </LayoutHeader>
  <div
    v-if="drilldown.active"
    class="mx-3 mt-2 flex items-center gap-2 rounded bg-surface-gray-2 px-3 py-2 text-sm"
  >
    <LucideFilter class="size-4 text-ink-gray-6 shrink-0" />
    <span class="font-medium text-ink-gray-8">{{ drilldown.label }}</span>
    <span v-if="drilldown.sub" class="text-ink-gray-5"
      >· {{ drilldown.sub }}</span
    >
    <span class="text-ink-gray-5">
      · {{ drilldown.names.length }}
      {{ drilldown.names.length === 1 ? __('lead') : __('leads') }}
    </span>
    <span v-if="drilldown.truncated" class="text-ink-red-3">
      ({{ __('capped') }})
    </span>
    <Button
      class="ml-auto"
      variant="ghost"
      :label="__('Clear')"
      iconLeft="x"
      @click="clearDrill"
    />
  </div>
  <ViewControls
    ref="viewControls"
    v-model="leads"
    v-model:loadMore="loadMore"
    v-model:resizeColumn="triggerResize"
    v-model:updatedPageCount="updatedPageCount"
    doctype="CRM Lead"
    :filters="listFilters"
    :options="{
      allowedViews: ['list', 'group_by', 'kanban'],
    }"
  >
    <template #actions>
      <Dropdown
        v-if="route.params.viewType === 'kanban'"
        :options="taskSortOptions"
      >
        <Button
          :label="taskSortLabel"
          variant="subtle"
          :theme="taskSortDir ? 'blue' : 'gray'"
        >
          <template #prefix><LucideArrowDownUp class="size-4" /></template>
        </Button>
      </Dropdown>
      <Dropdown :options="taskDueOptions">
        <Button
          :label="taskDueLabel"
          variant="subtle"
          :theme="taskDueScope ? 'blue' : 'gray'"
        >
          <template #prefix><LucideCalendarClock class="size-4" /></template>
        </Button>
      </Dropdown>
    </template>
  </ViewControls>
  <KanbanView
    v-if="route.params.viewType == 'kanban'"
    v-model="leads"
    :options="{
      getRoute: (row) => ({
        name: 'Lead',
        params: { leadId: row.name },
        query: { view: route.query.view, viewType: route.params.viewType },
      }),
      onNewClick: (column) => onNewClick(column),
    }"
    @update="(data) => viewControls.updateKanbanSettings(data)"
    @loadMore="(columnName) => viewControls.loadMoreKanban(columnName)"
  >
    <template #title="{ titleField, itemName }">
      <div class="flex items-center gap-2">
        <div v-if="titleField === 'status'">
          <IndicatorIcon :class="getRow(itemName, titleField).color" />
        </div>
        <div
          v-else-if="
            titleField === 'organization' && getRow(itemName, titleField).label
          "
        >
          <Avatar
            class="flex items-center"
            :image="getRow(itemName, titleField).logo"
            :label="getRow(itemName, titleField).label"
            size="sm"
          />
        </div>
        <div
          v-else-if="
            titleField === 'lead_name' && getRow(itemName, titleField).label
          "
        >
          <Avatar
            class="flex items-center"
            :image="getRow(itemName, titleField).image"
            :label="getRow(itemName, titleField).image_label"
            size="sm"
          />
        </div>
        <div
          v-else-if="
            titleField === 'lead_owner' &&
            getRow(itemName, titleField).full_name
          "
        >
          <Avatar
            class="flex items-center"
            :image="getRow(itemName, titleField).user_image"
            :label="getRow(itemName, titleField).full_name"
            size="sm"
          />
        </div>
        <div v-else-if="titleField === 'mobile_no'">
          <PhoneIcon class="h-4 w-4" />
        </div>
        <div
          v-if="
            [
              'modified',
              'creation',
              'first_response_time',
              'first_responded_on',
              'response_by',
            ].includes(titleField)
          "
          class="truncate text-base"
        >
          <Tooltip :text="getRow(itemName, titleField).label">
            <div>{{ getRow(itemName, titleField).timeAgo }}</div>
          </Tooltip>
        </div>
        <div v-else-if="titleField === 'sla_status'" class="truncate text-base">
          <Badge
            v-if="getRow(itemName, titleField).value"
            :variant="'subtle'"
            :theme="getRow(itemName, titleField).color"
            size="md"
            :label="getRow(itemName, titleField).value"
          />
        </div>
        <div
          v-else-if="getRow(itemName, titleField).label"
          class="truncate text-base"
        >
          {{ getRow(itemName, titleField).label }}
        </div>
        <div v-else class="text-ink-gray-4">{{ __('No Title') }}</div>
      </div>
    </template>
    <template #fields="{ fieldName, fieldLabel, showBlank, itemName }">
      <KanbanCardField
        v-if="getRow(itemName, fieldName).label || showBlank"
        doctype="CRM Lead"
        :name="itemName"
        :fieldName="fieldName"
        :rawValue="getRawValue(itemName, fieldName)"
        :copyText="String(getRow(itemName, fieldName).label ?? '')"
        @updated="reloadKanban"
      >
        <span v-if="fieldLabel" class="shrink-0 text-ink-gray-5">
          {{ fieldLabel }}
        </span>
        <span
          v-if="showBlank && !getRow(itemName, fieldName).label"
          class="truncate text-base text-ink-gray-4"
        >
          &mdash;
        </span>
        <div v-if="fieldName === 'status'">
          <IndicatorIcon :class="getRow(itemName, fieldName).color" />
        </div>
        <div
          v-else-if="
            fieldName === 'organization' && getRow(itemName, fieldName).label
          "
        >
          <Avatar
            class="flex items-center"
            :image="getRow(itemName, fieldName).logo"
            :label="getRow(itemName, fieldName).label"
            size="xs"
          />
        </div>
        <div v-else-if="fieldName === 'lead_name'">
          <Avatar
            v-if="getRow(itemName, fieldName).label"
            class="flex items-center"
            :image="getRow(itemName, fieldName).image"
            :label="getRow(itemName, fieldName).image_label"
            size="xs"
          />
        </div>
        <div v-else-if="fieldName === 'lead_owner'">
          <Avatar
            v-if="getRow(itemName, fieldName).full_name"
            class="flex items-center"
            :image="getRow(itemName, fieldName).user_image"
            :label="getRow(itemName, fieldName).full_name"
            size="xs"
          />
        </div>
        <div
          v-if="
            [
              'modified',
              'creation',
              'first_response_time',
              'first_responded_on',
              'response_by',
              '_last_comm',
            ].includes(fieldName)
          "
          class="truncate text-base"
        >
          <Tooltip :text="getRow(itemName, fieldName).label">
            <div>{{ getRow(itemName, fieldName).timeAgo }}</div>
          </Tooltip>
        </div>
        <div v-else-if="fieldName === 'sla_status'" class="truncate text-base">
          <Badge
            v-if="getRow(itemName, fieldName).value"
            :variant="'subtle'"
            :theme="getRow(itemName, fieldName).color"
            size="md"
            :label="getRow(itemName, fieldName).value"
          />
        </div>
        <div
          v-else-if="fieldName === '_next_task_due'"
          class="truncate text-base"
        >
          <Tooltip
            v-if="getRow(itemName, fieldName).value"
            :text="getRow(itemName, fieldName).label"
          >
            <div
              :class="
                getRow(itemName, fieldName).color
                  ? parseColor(getRow(itemName, fieldName).color)
                  : ''
              "
            >
              {{ getRow(itemName, fieldName).value }}
            </div>
          </Tooltip>
        </div>
        <div
          v-else-if="fieldName === '_first_call'"
          class="truncate text-base"
        >
          <Badge
            v-if="getRow(itemName, fieldName).label"
            variant="subtle"
            :theme="getRow(itemName, fieldName).color"
            size="md"
            :label="getRow(itemName, fieldName).label"
          />
        </div>
        <div
          v-else-if="fieldName === '_assign'"
          class="flex items-center truncate"
        >
          <MultipleAvatar
            :avatars="getRow(itemName, fieldName).label"
            size="xs"
          />
        </div>
        <a
          v-else-if="['mobile_no', 'phone'].includes(fieldName)"
          :href="callHref(getRow(itemName, fieldName).label, myNumber)"
          class="truncate text-base text-ink-gray-9 hover:text-ink-blue-link hover:underline"
          @click.stop
        >
          {{ getRow(itemName, fieldName).label }}
        </a>
        <div v-else class="truncate text-base">
          {{ getRow(itemName, fieldName).label }}
        </div>
      </KanbanCardField>
    </template>
    <template #actions="{ itemName }">
      <div class="flex gap-2 items-center justify-between">
        <div class="text-ink-gray-7 flex items-center gap-1.5">
          <Tooltip :text="__('Calls out / in')">
            <div class="flex items-center gap-1">
              <PhoneIcon class="h-4 w-4" />
              <span>{{ getRow(itemName, '_call_out_count').label ?? 0 }}&#8593;</span>
              <span>{{ getRow(itemName, '_call_in_count').label ?? 0 }}&#8595;</span>
            </div>
          </Tooltip>
          <span class="text-3xl leading-[0]"> &middot; </span>
          <Tooltip :text="__('Texts out / in')">
            <div class="flex items-center gap-1">
              <CommentIcon class="h-4 w-4" />
              <span>{{ getRow(itemName, '_text_out_count').label ?? 0 }}&#8593;</span>
              <span>{{ getRow(itemName, '_text_in_count').label ?? 0 }}&#8595;</span>
            </div>
          </Tooltip>
          <span class="text-3xl leading-[0]"> &middot; </span>
          <Tooltip :text="__('Emails out / in')">
            <div class="flex items-center gap-1">
              <EmailAtIcon class="h-4 w-4" />
              <span>{{ getRow(itemName, '_email_out_count').label ?? 0 }}&#8593;</span>
              <span>{{ getRow(itemName, '_email_in_count').label ?? 0 }}&#8595;</span>
            </div>
          </Tooltip>
        </div>
        <Dropdown
          class="flex items-center gap-2"
          :options="actions(itemName)"
          variant="ghost"
          @click.stop.prevent
        >
          <Button icon="plus" variant="ghost" />
        </Dropdown>
      </div>
    </template>
  </KanbanView>
  <LeadsListView
    v-else-if="leads.data && rows.length"
    ref="leadsListView"
    v-model="leads.data.page_length_count"
    v-model:list="leads"
    :rows="rows"
    :columns="columns"
    :options="{
      showTooltip: false,
      resizeColumn: true,
      rowCount: leads.data.row_count,
      totalCount: leads.data.total_count,
    }"
    @loadMore="() => loadMore++"
    @columnWidthUpdated="() => triggerResize++"
    @updatePageCount="(count) => (updatedPageCount = count)"
    @applyFilter="(data) => viewControls.applyFilter(data)"
    @applyLikeFilter="(data) => viewControls.applyLikeFilter(data)"
    @likeDoc="(data) => viewControls.likeDoc(data)"
    @selectionsChanged="
      (selections) => viewControls.updateSelections(selections)
    "
  />
  <EmptyState
    v-else-if="leads.data && !rows.length"
    name="Leads"
    :icon="LeadsIcon"
  />
  <LeadModal
    v-if="showLeadModal"
    v-model="showLeadModal"
    :defaults="defaults"
  />
  <NoteModal
    v-if="showNoteModal"
    v-model="showNoteModal"
    :note="note"
    doctype="CRM Lead"
    :doc="docname"
  />
  <TaskModal
    v-if="showTaskModal"
    v-model="showTaskModal"
    :task="task"
    doctype="CRM Lead"
    :doc="docname"
  />
</template>

<script setup>
import ViewBreadcrumbs from '@/components/ViewBreadcrumbs.vue'
import MultipleAvatar from '@/components/MultipleAvatar.vue'
import CustomActions from '@/components/CustomActions.vue'
import EmailAtIcon from '@/components/Icons/EmailAtIcon.vue'
import PhoneIcon from '@/components/Icons/PhoneIcon.vue'
import NoteIcon from '@/components/Icons/NoteIcon.vue'
import TaskIcon from '@/components/Icons/TaskIcon.vue'
import CommentIcon from '@/components/Icons/CommentIcon.vue'
import IndicatorIcon from '@/components/Icons/IndicatorIcon.vue'
import LeadsIcon from '@/components/Icons/LeadsIcon.vue'
import LayoutHeader from '@/components/LayoutHeader.vue'
import LeadsListView from '@/components/ListViews/LeadsListView.vue'
import EmptyState from '@/components/ListViews/EmptyState.vue'
import KanbanView from '@/components/Kanban/KanbanView.vue'
import KanbanCardField from '@/components/Kanban/KanbanCardField.vue'
import LeadModal from '@/components/Modals/LeadModal.vue'
import NoteModal from '@/components/Modals/NoteModal.vue'
import TaskModal from '@/components/Modals/TaskModal.vue'
import ViewControls from '@/components/ViewControls.vue'
import { getMeta } from '@/stores/meta'
import { globalStore } from '@/stores/global'
import { usersStore } from '@/stores/users'
import { statusesStore } from '@/stores/statuses'
import { leadDrilldownStore } from '@/stores/leadDrilldown'
import LucideFilter from '~icons/lucide/filter'
import LucideCalendarClock from '~icons/lucide/calendar-clock'
import LucideArrowDownUp from '~icons/lucide/arrow-down-up'
import { callEnabled } from '@/composables/settings'
import { useBroadcast } from '@/composables/useBroadcast'
import {
  formatDate,
  timeAgo,
  website,
  formatTime,
  dueColor,
  parseColor,
  firstCallRead,
} from '@/utils'
import { formatPhone, callHref } from '@/utils/phoneFormat'
import { myQuoNumber } from '@/composables/quoSender'
import { Avatar, Tooltip, Dropdown, call } from 'frappe-ui'
import { useRoute } from 'vue-router'
import { ref, computed, reactive, h, nextTick, onMounted, onBeforeUnmount } from 'vue'

const { getFormattedPercent, getFormattedFloat, getFormattedCurrency } =
  getMeta('CRM Lead')
const { makeCall, $socket } = globalStore()
const { getUser } = usersStore()
const { getLeadStatus } = statusesStore()

// Current user's Quo number — caller ID for the mobile click-to-call deep link.
const myNumber = computed(() => myQuoNumber())
const { on } = useBroadcast()

const route = useRoute()

const leadsListView = ref(null)
const showLeadModal = ref(false)

on('trigger_lead_create', (data) => {
  showLeadModal.value = Boolean(data)
})

const defaults = reactive({})

// leads data is loaded in the ViewControls component
const leads = ref({})
const loadMore = ref(1)
const triggerResize = ref(1)
const updatedPageCount = ref(20)
const viewControls = ref(null)

// Drill-down from the Leads dashboard: an ad-hoc set of lead names to show.
// Injected as a never-persisted `name in [...]` default filter; while a drill
// is active we drop the `converted: 0` base filter so the list matches the
// dashboard's count exactly (which includes converted leads).
const drilldown = leadDrilldownStore()

// "Tasks due" kanban filter: show only leads that have an open task due today /
// overdue. _next_task_due is a computed pseudo-field (not a DB column), so we
// resolve the matching lead names server-side and inject them as the same
// never-persisted `name in [...]` default filter the dashboard drill uses.
const taskDueScope = ref('')
const taskDueNames = ref([])

const listFilters = computed(() => {
  if (drilldown.active) {
    return { name: ['in', drilldown.names.length ? drilldown.names : ['__none__']] }
  }
  if (taskDueScope.value) {
    return {
      converted: 0,
      name: ['in', taskDueNames.value.length ? taskDueNames.value : ['__none__']],
    }
  }
  return { converted: 0 }
})

const TASK_DUE_LABELS = {
  today: __('Due today'),
  overdue: __('Overdue'),
  today_overdue: __('Due today + overdue'),
}
const taskDueLabel = computed(() =>
  taskDueScope.value ? TASK_DUE_LABELS[taskDueScope.value] : __('Tasks due'),
)
const taskDueOptions = computed(() => {
  const opts = [
    { label: __('Due today'), onClick: () => applyTaskDue('today') },
    { label: __('Overdue'), onClick: () => applyTaskDue('overdue') },
    { label: __('Due today + overdue'), onClick: () => applyTaskDue('today_overdue') },
  ]
  if (taskDueScope.value) {
    opts.push({ label: __('Clear'), icon: 'x', onClick: clearTaskDue })
  }
  return opts
})

async function applyTaskDue(scope) {
  const names = await call('crm.api.doc.get_docs_with_due_tasks', {
    doctype: 'CRM Lead',
    scope,
  })
  taskDueNames.value = names || []
  taskDueScope.value = scope
  nextTick(() => viewControls.value?.reload())
}

function clearTaskDue() {
  taskDueScope.value = ''
  taskDueNames.value = []
  nextTick(() => viewControls.value?.reload())
}

// Kanban "sort by next task due": orders each column's cards by their soonest
// open task (the _next_task_due pseudo-field). The server can't SQL-sort a
// computed field, so it re-derives the card order per column from this order_by.
// Active direction is read straight off the live order_by so it survives reloads
// and view switches; '' = the default (modified desc), no task sort applied.
const taskSortDir = computed(() => {
  const ob = leads.value?.params?.order_by || ''
  if (!ob.startsWith('_next_task_due')) return ''
  return ob.includes('desc') ? 'desc' : 'asc'
})
const taskSortLabel = computed(() => {
  if (taskSortDir.value === 'asc') return __('Task due: soonest')
  if (taskSortDir.value === 'desc') return __('Task due: latest')
  return __('Sort by task')
})
const taskSortOptions = computed(() => {
  const opts = [
    {
      label: __('Soonest due first'),
      onClick: () => applyTaskSort('_next_task_due asc'),
    },
    {
      label: __('Latest due first'),
      onClick: () => applyTaskSort('_next_task_due desc'),
    },
  ]
  if (taskSortDir.value) {
    opts.push({
      label: __('Clear'),
      icon: 'x',
      onClick: () => applyTaskSort('modified desc'),
    })
  }
  return opts
})

function applyTaskSort(orderBy) {
  viewControls.value?.updateSort(orderBy)
}

function clearDrill() {
  drilldown.clear()
  // Reload only after the updated `:filters` prop has propagated to ViewControls,
  // otherwise getParams() re-reads the stale `name in [...]` filter.
  nextTick(() => viewControls.value?.reload())
}

function getRow(name, field) {
  function getValue(value) {
    if (value && typeof value === 'object' && !Array.isArray(value)) {
      return value
    }
    return { label: value }
  }
  return getValue(rows.value?.find((row) => row.name == name)[field])
}

// rows.value holds formatted/display values; the inline Kanban-card editor
// needs the raw stored value, which lives on the un-parsed kanban data.
function getRawValue(name, field) {
  for (const col of leads.value?.data?.data || []) {
    const lead = col.data?.find((r) => r.name === name)
    if (lead) return lead[field]
  }
  return ''
}

// Re-fetch the board after an inline card edit so values (and any column move
// when the grouping field changes) reflect the saved state.
function reloadKanban() {
  leads.value?.reload?.()
}

// A task changed somewhere (created/completed/deleted). The Kanban next-task-due
// badge (_next_task_due) is computed server-side, so refetch the board — but only
// when we're on the Kanban view and the affected lead is currently shown, to avoid
// needless reloads.
function onTaskUpdate(data) {
  if (data?.reference_doctype !== 'CRM Lead') return
  if (route.params.viewType !== 'kanban') return
  const onBoard = (leads.value?.data?.data || []).some((col) =>
    col.data?.some((r) => r.name === data.reference_docname),
  )
  if (onBoard) reloadKanban()
}

// A First-Call Read was recorded somewhere. The quadrant chip (_first_call) is
// computed server-side, so refetch the board on the same on-board guard.
function onFirstCallUpdate(data) {
  if (data?.reference_doctype !== 'CRM Lead') return
  if (route.params.viewType !== 'kanban') return
  const onBoard = (leads.value?.data?.data || []).some((col) =>
    col.data?.some((r) => r.name === data.reference_docname),
  )
  if (onBoard) reloadKanban()
}

onMounted(() => {
  $socket.on('crm_task_update', onTaskUpdate)
  $socket.on('crm_first_call', onFirstCallUpdate)
})
onBeforeUnmount(() => {
  $socket.off('crm_task_update', onTaskUpdate)
  $socket.off('crm_first_call', onFirstCallUpdate)
})

// Rows
const rows = computed(() => {
  if (!leads.value?.data?.data) return []
  if (leads.value.data.view_type === 'group_by') {
    if (!leads.value?.data.group_by_field?.fieldname) return []
    return getGroupedByRows(
      leads.value?.data.data,
      leads.value?.data.group_by_field,
      leads.value.data.columns,
    )
  } else if (leads.value.data.view_type === 'kanban') {
    return getKanbanRows(leads.value.data.data, leads.value.data.fields)
  } else {
    return parseRows(leads.value?.data.data, leads.value.data.columns)
  }
})

const columns = computed(() => {
  let _columns = leads.value?.data?.columns || []

  // Set align right for last column
  if (_columns.length) {
    _columns = _columns.map((col, index) => {
      if (index === _columns.length - 1) {
        return { ...col, align: 'right' }
      }
      return col
    })
  }

  return _columns
})

function getGroupedByRows(listRows, groupByField, columns) {
  let groupedRows = []

  groupByField.options?.forEach((option) => {
    let filteredRows

    if (!option) {
      filteredRows = listRows.filter((row) => !row[groupByField.fieldname])
    } else {
      filteredRows = listRows.filter(
        (row) => row[groupByField.fieldname] == option,
      )
    }

    let groupDetail = {
      label: groupByField.label,
      group: option || __(' '),
      collapsed: false,
      rows: parseRows(filteredRows, columns),
    }
    if (groupByField.fieldname == 'status') {
      groupDetail.icon = () =>
        h(IndicatorIcon, {
          class: getLeadStatus(option)?.color,
        })
    }
    groupedRows.push(groupDetail)
  })

  return groupedRows || listRows
}

function getKanbanRows(data, columns) {
  let _rows = []
  data.forEach((column) => {
    column.data?.forEach((row) => {
      _rows.push(row)
    })
  })
  return parseRows(_rows, columns)
}

function parseRows(rows, columns = []) {
  let view_type = leads.value.data.view_type
  let key = view_type === 'kanban' ? 'fieldname' : 'key'
  let type = view_type === 'kanban' ? 'fieldtype' : 'type'

  return rows.map((lead) => {
    let _rows = {}
    leads.value?.data.rows.forEach((row) => {
      _rows[row] = lead[row]

      let fieldType = columns?.find((col) => (col[key] || col.value) == row)?.[
        type
      ]

      if (
        fieldType &&
        ['Date', 'Datetime'].includes(fieldType) &&
        !['modified', 'creation'].includes(row)
      ) {
        _rows[row] = formatDate(lead[row], '', true, fieldType == 'Datetime')
      }

      if (fieldType && fieldType == 'Currency') {
        _rows[row] = getFormattedCurrency(row, lead)
      }

      if (fieldType && fieldType == 'Float') {
        _rows[row] = getFormattedFloat(row, lead)
      }

      if (fieldType && fieldType == 'Percent') {
        _rows[row] = getFormattedPercent(row, lead)
      }

      if (['mobile_no', 'phone'].includes(row)) {
        _rows[row] = formatPhone(lead[row])
      }

      if (row == 'lead_name') {
        _rows[row] = {
          label: lead.lead_name,
          image: lead.image,
          image_label: lead.first_name,
        }
      } else if (row == 'organization') {
        _rows[row] = lead.organization
      } else if (row === 'website') {
        _rows[row] = website(lead.website)
      } else if (row == 'status') {
        _rows[row] = {
          label: lead.status,
          color: getLeadStatus(lead.status)?.color,
        }
      } else if (row == 'sla_status') {
        let value = lead.sla_status
        let tooltipText = value
        let color =
          lead.sla_status == 'Failed'
            ? 'red'
            : lead.sla_status == 'Fulfilled'
              ? 'green'
              : 'orange'
        if (value == 'First Response Due' || value == 'Rolling Response Due') {
          value = __(timeAgo(lead.response_by))
          tooltipText = formatDate(lead.response_by)
          if (new Date(lead.response_by) < new Date()) {
            color = 'red'
          }
        }
        _rows[row] = {
          label: tooltipText,
          value: value,
          color: color,
        }
      } else if (row == 'lead_owner') {
        _rows[row] = {
          label: lead.lead_owner && getUser(lead.lead_owner).full_name,
          ...(lead.lead_owner && getUser(lead.lead_owner)),
        }
      } else if (row == '_assign') {
        let assignees = JSON.parse(lead._assign || '[]')
        _rows[row] = assignees.map((user) => ({
          name: user,
          image: getUser(user).user_image,
          label: getUser(user).full_name,
        }))
      } else if (['modified', 'creation'].includes(row)) {
        _rows[row] = {
          label: formatDate(lead[row]),
          timeAgo: __(timeAgo(lead[row])),
        }
      } else if (
        ['first_response_time', 'first_responded_on', 'response_by'].includes(
          row,
        )
      ) {
        let field = row == 'response_by' ? 'response_by' : 'first_responded_on'
        _rows[row] = {
          label: lead[field] ? formatDate(lead[field]) : '',
          timeAgo: lead[row]
            ? row == 'first_response_time'
              ? formatTime(lead[row])
              : __(timeAgo(lead[row]))
            : '',
        }
      }
    })
    _rows['_email_count'] = lead._email_count
    _rows['_note_count'] = lead._note_count
    _rows['_task_count'] = lead._task_count
    _rows['_comment_count'] = lead._comment_count
    _rows['_call_out_count'] = lead._call_out_count
    _rows['_call_in_count'] = lead._call_in_count
    _rows['_text_out_count'] = lead._text_out_count
    _rows['_text_in_count'] = lead._text_in_count
    _rows['_email_out_count'] = lead._email_out_count
    _rows['_email_in_count'] = lead._email_in_count
    _rows['_last_comm'] = {
      label: lead._last_comm ? formatDate(lead._last_comm) : '',
      timeAgo: lead._last_comm ? __(timeAgo(lead._last_comm)) : '',
    }
    _rows['_next_task_due'] = {
      label: lead._next_task_due ? formatDate(lead._next_task_due) : '',
      value: lead._next_task_due ? __(timeAgo(lead._next_task_due)) : '',
      color: dueColor(lead._next_task_due),
    }
    // First-Call Read quadrant chip — only when both axes answered (server sends
    // "_first_call" as "motivated|on_price", e.g. "Yes|No").
    const [_fcMot, _fcPrice] = (lead._first_call || '|').split('|')
    const _fc = firstCallRead(_fcMot, _fcPrice)
    _rows['_first_call'] = {
      label: _fc.quad ? __(_fc.quad.label) : '',
      color: _fc.quad ? _fc.quad.theme : '',
    }
    return _rows
  })
}

function onNewClick(column) {
  let column_field = leads.value.params.column_field

  if (column_field) {
    defaults[column_field] = column.column.name
  }

  showLeadModal.value = true
}

function actions(itemName) {
  let mobile_no = getRow(itemName, 'mobile_no')?.label || ''
  let actions = [
    {
      icon: h(PhoneIcon, { class: 'h-4 w-4' }),
      label: __('Make a Call'),
      onClick: () => makeCall(mobile_no),
      condition: () => mobile_no && callEnabled.value,
    },
    {
      icon: h(NoteIcon, { class: 'h-4 w-4' }),
      label: __('New Note'),
      onClick: () => showNote(itemName),
    },
    {
      icon: h(TaskIcon, { class: 'h-4 w-4' }),
      label: __('New Task'),
      onClick: () => showTask(itemName),
    },
  ]
  return actions.filter((action) =>
    action.condition ? action.condition() : true,
  )
}

const docname = ref('')
const showNoteModal = ref(false)
const note = ref({
  title: '',
  content: '',
})

function showNote(name) {
  docname.value = name
  showNoteModal.value = true
}

const showTaskModal = ref(false)
const task = ref({
  title: '',
  description: '',
  assigned_to: '',
  due_date: '',
  priority: 'Low',
  status: 'Backlog',
})

function showTask(name) {
  docname.value = name
  showTaskModal.value = true
}
</script>
