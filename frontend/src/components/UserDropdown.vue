<template>
  <Dropdown :options="dropdownItems" v-bind="$attrs">
    <template #default="{ open }">
      <button
        class="flex h-12 items-center rounded-md py-2 duration-300 ease-in-out"
        :class="
          isCollapsed
            ? 'w-auto px-0'
            : open
              ? 'w-full px-2 bg-surface-white shadow-sm'
              : 'w-full px-2 hover:bg-surface-gray-3'
        "
      >
        <BrandLogo v-model="brand" class="h-8 max-w-16 flex-shrink-0" />
        <div
          class="flex flex-1 flex-col text-left duration-300 ease-in-out truncate"
          :class="
            isCollapsed
              ? 'ml-0 w-0 overflow-hidden opacity-0'
              : 'ml-2 w-auto opacity-100'
          "
        >
          <div
            class="text-base font-medium leading-none text-ink-gray-9 truncate"
          >
            {{ __(brand.name || 'CRM') }}
          </div>
          <div class="mt-1 text-sm leading-none text-ink-gray-7 truncate">
            {{ user.full_name }}
          </div>
        </div>
        <div
          class="duration-300 ease-in-out"
          :class="
            isCollapsed
              ? 'ml-0 w-0 overflow-hidden opacity-0'
              : 'ml-2 w-auto opacity-100'
          "
        >
          <FeatherIcon
            name="chevron-down"
            class="size-4 text-ink-gray-5"
            aria-hidden="true"
          />
        </div>
      </button>
    </template>
  </Dropdown>
</template>

<script setup>
import BrandLogo from '@/components/BrandLogo.vue'
import FrappeCloudIcon from '@/components/Icons/FrappeCloudIcon.vue'
import Apps from '@/components/Apps.vue'
import { sessionStore } from '@/stores/session'
import { usersStore } from '@/stores/users'
import { getSettings } from '@/stores/settings'
import { showSettings, isMobileView } from '@/composables/settings'
import { showAboutModal } from '@/composables/modals'
import { confirmLoginToFrappeCloud } from '@/composables/frappecloud'
import { Dropdown } from 'frappe-ui'
import { computed, h, markRaw, shallowRef } from 'vue'
import { useRoute, useRouter } from 'vue-router'

defineProps({
  isCollapsed: { type: Boolean, default: false },
})

const { settings, brand } = getSettings()
const { logout } = sessionStore()
const { getUser } = usersStore()

const user = computed(() => getUser() || {})

// Workspace version switch ("Try the new workspace" / "Back to classic").
// DEV-only for now: the preview modules are pulled in with a dynamic import
// inside a dead branch, so the production bundle is unchanged. The real
// mechanism is a per-user Frappe default (`crm_workspace_version`) — see
// utils/workspaceVersion.js — read with the user store at boot and written
// from this same item; nothing is written to the server yet.
// shallowRef: a deep ref would auto-unwrap the nested `label` computed and
// `.label.value` would read undefined (blank menu item).
const workspaceItem = shallowRef(null)
if (import.meta.env.DEV) {
  const route = useRoute()
  const router = useRouter()
  import('@/composables/workspaceSwitch').then(({ useWorkspaceSwitch }) => {
    workspaceItem.value = useWorkspaceSwitch({ route, router })
  })
}

const dropdownItems = computed(() => {
  if (!settings.value?.dropdown_items) return []

  let items = settings.value.dropdown_items

  let _dropdownItems = [
    {
      group: 'Dropdown Items',
      hideLabel: true,
      items: [],
    },
  ]

  if (workspaceItem.value) {
    _dropdownItems[0].items.push({
      icon: 'layout',
      label: workspaceItem.value.label.value,
      onClick: workspaceItem.value.toggle,
    })
  }

  items.forEach((item) => {
    if (item.hidden) return
    if (item.type !== 'Separator') {
      _dropdownItems[_dropdownItems.length - 1].items.push(
        dropdownItemObj(item),
      )
    } else {
      _dropdownItems.push({
        group: '',
        hideLabel: true,
        items: [],
      })
    }
  })

  return _dropdownItems
})

function dropdownItemObj(item) {
  let _item = JSON.parse(JSON.stringify(item))
  let icon = _item.icon || 'external-link'
  if (typeof icon === 'string' && icon.startsWith('<svg')) {
    icon = markRaw(h('div', { innerHTML: icon }))
  }
  _item.icon = icon

  if (_item.is_standard) {
    return getStandardItem(_item)
  }

  return {
    icon: _item.icon,
    label: __(_item.label),
    onClick: () =>
      window.open(_item.route, _item.open_in_new_window ? '_blank' : ''),
  }
}

function getStandardItem(item) {
  switch (item.name1) {
    case 'app_selector':
      return {
        component: markRaw(Apps),
      }
    case 'settings':
      return {
        icon: item.icon,
        label: __(item.label),
        onClick: () => (showSettings.value = true),
        condition: () => !isMobileView.value,
      }
    case 'login_to_fc':
      return {
        icon: h(FrappeCloudIcon),
        label: __(item.label),
        onClick: () => confirmLoginToFrappeCloud(),
        condition: () => !isMobileView.value && window.is_fc_site,
      }
    case 'about':
      return {
        icon: item.icon,
        label: __(item.label),
        onClick: () => (showAboutModal.value = true),
      }
    case 'logout':
      return {
        icon: item.icon,
        label: __(item.label),
        onClick: () => logout.submit(),
      }
  }
}
</script>
