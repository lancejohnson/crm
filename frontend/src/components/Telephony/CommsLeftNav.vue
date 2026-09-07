<template>
  <aside class="left-nav" :class="{ collapsed: c.navCollapsed, mobile }" :style="{ width: `${navWidth(c.navCollapsed)}px`, bottom: `${bottom}px` }" aria-label="Left nav design preview">
    <div class="nav-header"><UserDropdown :isCollapsed="c.navCollapsed" /></div>
    <div class="nav-scroll">
      <SidebarLink :label="__('Notifications')" :icon="NotificationsIcon" :isCollapsed="c.navCollapsed" class="mx-2 my-[1.5px] relative" @click="toggleNotificationPanel()">
        <template #right>
          <Badge v-if="!c.navCollapsed && unreadNotificationsCount" :label="unreadNotificationsCount" variant="subtle" />
          <span v-else-if="unreadNotificationsCount" class="strip-dot" aria-hidden="true" />
        </template>
      </SidebarLink>

      <section v-for="group in groups" :key="group.id" class="nav-group" :class="{ open: c.navOpen[group.id] }">
        <button v-if="!c.navCollapsed" type="button" class="group-header" :aria-expanded="c.navOpen[group.id]" :aria-controls="`nav-group-${group.id}`" @click="toggleNavGroup(c, group.id)">
          <FeatherIcon name="chevron-right" class="size-4 chevron" :class="{ 'rotate-90': c.navOpen[group.id] }" />
          <span class="group-label">{{ group.label }}</span>
          <span v-if="group.unread" class="group-badge" :class="{ amber: group.id === 'live' }">{{ group.unread }}</span>
          <span v-else-if="group.id === 'live' && !c.navOpen.live" class="group-quiet">quiet</span>
        </button>
        <button v-else type="button" class="strip-group" :aria-label="`${group.label}${group.unread ? ` · ${group.unread} unread` : ''}`" :title="group.label" :aria-expanded="c.navOpen[group.id]" @click="expandTo(group.id)">
          <FeatherIcon :name="group.icon" class="size-4" />
          <span v-if="group.unread" class="strip-dot" :class="{ amber: group.id === 'live' }" aria-hidden="true" />
        </button>

        <div v-show="c.navOpen[group.id] && (!c.navCollapsed || group.id === 'crm')" :id="`nav-group-${group.id}`" class="group-body">
          <nav v-if="group.id === 'crm'" class="flex flex-col" aria-label="CRM">
            <SidebarLink v-for="link in crmLinks" :key="link.label" :icon="link.icon" :label="__(link.label)" :to="link.to" :isCollapsed="c.navCollapsed" class="mx-2 my-[1.5px]" />
            <template v-for="extra in extraViews" :key="extra.name">
              <p v-if="!c.navCollapsed" class="sub-label">{{ __(extra.name) }}</p>
              <SidebarLink v-for="link in extra.views" :key="link.label" :icon="link.icon" :label="__(link.label)" :to="link.to" :isCollapsed="c.navCollapsed" class="mx-2 my-[1.5px]" />
            </template>
          </nav>

          <ul v-else-if="group.id === 'live'" class="item-list" aria-label="Live">
            <li v-if="!liveEvents.length" class="item-empty">Nothing live right now.</li>
            <li v-for="event in liveEvents" :key="event.id"><button type="button" class="item" :class="{ selected: isSelected('live', event.id), 'live-one': event.kind === 'live_one' }" :aria-pressed="isSelected('live', event.id)" @click="pick('live', event.id)"><span class="item-dot" aria-hidden="true" /><span class="item-text"><b>{{ event.call.rep }}</b> · {{ event.call.name }}</span><FeatherIcon :name="event.kind === 'live_one' ? 'zap' : 'headphones'" class="size-3.5 item-icon" /></button></li>
          </ul>

          <ul v-else-if="group.id === 'channels'" class="item-list" aria-label="Channels">
            <li><button type="button" class="item pinned" :class="{ selected: isSelected('standup', STANDUP_ID) }" :aria-pressed="isSelected('standup', STANDUP_ID)" @click="pick('standup', STANDUP_ID)"><FeatherIcon name="bookmark" class="size-3.5 item-icon lead" /><span class="item-text">Standup</span><small class="item-state">pinned</small></button></li>
            <li v-for="(channel, name) in c.channels" :key="name"><button type="button" class="item" :class="{ selected: isSelected('channel', name), unread: channel.unread }" :aria-pressed="isSelected('channel', name)" @click="pick('channel', name)"><FeatherIcon name="hash" class="size-3.5 item-icon lead" /><span class="item-text">{{ name.slice(1) }}</span><span v-if="channel.unread" class="group-badge">{{ channel.unread }}</span></button></li>
          </ul>

          <ul v-else class="item-list" aria-label="Direct messages">
            <li v-for="name in previewTeammates" :key="name"><button type="button" class="item" :class="{ selected: isSelected('dm', name), unread: c.dmUnread[name] }" :aria-pressed="isSelected('dm', name)" @click="pick('dm', name)"><span class="presence" :class="{ busy: busy(name) }" aria-hidden="true" /><span class="item-text">{{ name }}</span><span v-if="c.dmUnread[name]" class="group-badge">{{ c.dmUnread[name] }}</span><small v-else class="item-state">{{ busy(name) ? 'On call' : '' }}</small></button></li>
          </ul>
        </div>
      </section>
    </div>
    <div class="nav-footer">
      <p v-if="!c.navCollapsed" class="nav-note">Design preview · fictional channels and messages. CRM links are real.</p>
      <SidebarLink :label="c.navCollapsed ? __('Expand') : __('Collapse')" :isCollapsed="c.navCollapsed" class="mx-2 my-[1.5px]" @click="c.navCollapsed = !c.navCollapsed">
        <template #icon><span class="grid h-4 w-4 flex-shrink-0 place-items-center"><CollapseSidebar class="h-4 w-4 text-ink-gray-7 duration-300 ease-in-out" :class="{ '[transform:rotateY(180deg)]': c.navCollapsed }" /></span></template>
      </SidebarLink>
    </div>
  </aside>
</template>
<script setup>
/**
 * D · Left nav. Renders OVER the real sidebar (App.vue shifts the real one
 * underneath through the reserve channel), so AppSidebar / MobileSidebar are
 * untouched and production is byte-identical. The CRM group is the real link
 * list (`applySidebarConfig` + `SidebarLink`, same conditions) — reused, not
 * copied — plus the real public/pinned views.
 *
 * A conversation is a PAGE: picking one routes to /talk/:kind/:id and the
 * active item is read off the route, exactly as SidebarLink highlights Leads.
 */
import { Badge, FeatherIcon } from 'frappe-ui'
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import UserDropdown from '@/components/UserDropdown.vue'
import SidebarLink from '@/components/SidebarLink.vue'
import NotificationsIcon from '@/components/Icons/NotificationsIcon.vue'
import CollapseSidebar from '@/components/Icons/CollapseSidebar.vue'
import PinIcon from '@/components/Icons/PinIcon.vue'
import { getSettings } from '@/stores/settings'
import { viewsStore } from '@/stores/views'
import { applySidebarConfig } from '@/utils/sidebarLinks'
import { unreadNotificationsCount, notificationsStore } from '@/stores/notifications'
import { commsPreview as c } from '@/composables/commsPreview'
import { phonePreview as p } from '@/composables/phonePreview'
import { navWidth, navUnread, toggleNavGroup, openNavItem, talkRoute, isTalkActive, STANDUP_ID } from '@/utils/commsPreview'
import { previewTeammates, previewCalls } from '@/utils/phonePreview'
defineProps({ bottom: { type: Number, default: 0 }, mobile: Boolean })
const emit = defineEmits(['picked'])
const route = useRoute()
const router = useRouter()
const { toggle: toggleNotificationPanel } = notificationsStore()
const { settings } = getSettings()
const { getPinnedViews, getPublicViews } = viewsStore()
const crmLinks = computed(() => applySidebarConfig(settings.value?.custom_sidebar_items).filter(link => !link.condition || link.condition()))
const extraViews = computed(() => [
  { name: 'Public Views', views: getPublicViews() },
  { name: 'Pinned Views', views: getPinnedViews() },
].filter(group => group.views.length).map(group => ({
  name: group.name,
  views: group.views.map(view => ({ label: view.label, icon: view.icon || PinIcon, to: { name: view.route_name, params: { viewType: view.type || 'list' }, query: { view: view.name } } })),
})))
const liveEvents = computed(() => [...c.events].filter(event => event.call && !p.endedIds.includes(event.call.id)).sort((a, b) => b.sequence - a.sequence))
const groups = computed(() => [
  { id: 'crm', label: 'CRM', icon: 'grid', unread: 0 },
  { id: 'live', label: 'Live', icon: 'activity', unread: navUnread(c, 'live', liveEvents.value.length) },
  { id: 'channels', label: 'Channels', icon: 'hash', unread: navUnread(c, 'channels') },
  { id: 'dms', label: 'Direct messages', icon: 'message-square', unread: navUnread(c, 'dms') },
])
function busy(name) { return previewCalls.some(call => call.rep === name && !p.endedIds.includes(call.id)) }
function isSelected(kind, id) { return route.name === 'Talk' && isTalkActive(route.params, kind, id) }
// Read it, then go there. The query rides along so the preview survives a reload.
function pick(kind, id) {
  if (!openNavItem(c, kind, id)) return
  router.push(talkRoute(kind, id, route.query))
  emit('picked')
}
// From the icon strip, a group tap widens the column and opens that group.
function expandTo(group) { c.navCollapsed = false; c.navOpen[group] = true }
</script>
<style scoped>
.left-nav { position: fixed; top: 0; left: 0; z-index: 39; display: flex; flex-direction: column; background: var(--surface-menu-bar, #f8f8f8); border-right: 1px solid var(--outline-gray-2, #e2e2e2); color: var(--ink-gray-8, #333); transition: width .3s ease-in-out; }
.left-nav.mobile { position: absolute; inset: 0; width: 100% !important; bottom: 0 !important; z-index: 20; border-right: 0; }
.nav-header { padding: 8px; }
.nav-scroll { flex: 1; min-height: 0; overflow-y: auto; overflow-x: hidden; }
.nav-group { margin-top: 6px; }
.group-header { display: flex; align-items: center; gap: 6px; width: 100%; padding: 9px 16px 8px; font-size: 13px; color: var(--ink-gray-5, #777); text-align: left; }
.group-header:hover { color: var(--ink-gray-8, #333); }
.group-header:focus-visible, .strip-group:focus-visible, .item:focus-visible { outline: 2px solid var(--ink-gray-7, #555); outline-offset: -2px; border-radius: 6px; }
.chevron { color: var(--ink-gray-9, #222); transition: transform .3s ease-in-out; }
.group-label { flex: 1; }
.group-quiet { font-size: 10px; color: var(--ink-gray-4, #999); }
.group-badge { min-width: 16px; padding: 1px 5px; border-radius: 8px; background: var(--surface-gray-7, #333); color: #fff; font-size: 10px; text-align: center; line-height: 14px; }
.group-badge.amber, .strip-dot.amber { background: #d9a536; }
.strip-group { position: relative; display: grid; place-items: center; width: 32px; height: 32px; margin: 2px 8px; border-radius: 6px; color: var(--ink-gray-7, #555); }
.strip-group:hover { background: var(--surface-gray-2, #eee); }
.strip-group[aria-expanded="true"] { color: var(--ink-gray-9, #222); }
.strip-dot { position: absolute; top: 3px; right: 3px; width: 7px; height: 7px; border-radius: 50%; background: var(--surface-gray-6, #555); box-shadow: 0 0 0 1.5px var(--surface-menu-bar, #f8f8f8); }
.sub-label { margin: 10px 16px 4px; font-size: 11px; color: var(--ink-gray-5, #777); }
.item-list { list-style: none; margin: 0; padding: 0 8px; }
.item-empty { padding: 6px 10px; font-size: 12px; color: var(--ink-gray-5, #777); }
.item { display: flex; align-items: center; gap: 8px; width: 100%; height: 30px; padding: 0 8px; margin: 1.5px 0; border-radius: 6px; font-size: 13px; text-align: left; color: var(--ink-gray-8, #333); }
.item:hover { background: var(--surface-gray-2, #eee); }
.item.selected { background: var(--surface-selected, #fff); box-shadow: 0 1px 2px #0001; }
.item.unread { font-weight: 600; color: var(--ink-gray-9, #222); }
.item.pinned .item-icon { color: #9b772e; }
.item-text { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.item-icon { color: var(--ink-gray-5, #777); flex-shrink: 0; }
.item-icon.lead { order: -1; }
.item-dot { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; background: #388452; }
.item.live-one .item-dot { background: #d9a536; box-shadow: 0 0 0 3px #d9a53633; }
.presence { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; background: #388452; }
.presence.busy { background: #bc8e37; }
.item-state { font-size: 10px; color: var(--ink-gray-5, #777); }
.nav-footer { padding: 8px 0; border-top: 1px solid var(--outline-gray-1, #eee); }
.nav-note { margin: 0 16px 6px; font-size: 10px; line-height: 1.4; color: var(--ink-gray-5, #777); }
</style>
