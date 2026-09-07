<template>
  <aside class="left-nav" :class="{ collapsed: talk.navCollapsed, mobile }" :style="{ width: `${talk.navCollapsed ? 48 : 260}px`, bottom: `${bottom}px` }" :aria-label="__('Workspace navigation')">
    <div class="nav-header"><UserDropdown :isCollapsed="talk.navCollapsed" /></div>
    <div class="nav-scroll">
      <SidebarLink :label="__('Notifications')" :icon="NotificationsIcon" :isCollapsed="talk.navCollapsed" class="mx-2 my-[1.5px] relative" @click="toggleNotificationPanel()">
        <template #right>
          <Badge v-if="!talk.navCollapsed && unreadNotificationsCount" :label="unreadNotificationsCount" variant="subtle" />
          <span v-else-if="unreadNotificationsCount" class="strip-dot" aria-hidden="true" />
        </template>
      </SidebarLink>
      <SidebarLink :label="__('Inbox')" :icon="PhoneIcon" :to="{ name: 'Phone Desk' }" :isCollapsed="talk.navCollapsed" class="mx-2 my-[1.5px]" />
      <ul class="item-list inbox-links" :aria-label="__('Talk inbox')">
        <li><button type="button" class="item" :class="{ selected: isSelected('unreads', 'all'), unread: talk.totalUnread }" @click="pick('unreads', 'all')"><FeatherIcon name="inbox" class="size-3.5 item-icon lead" /><span class="item-text">{{ __('Unreads') }}</span><span v-if="talk.totalUnread" class="group-badge">{{ talk.totalUnread }}</span></button></li>
        <li><button type="button" class="item" :class="{ selected: isSelected('drafts', 'all'), unread: talk.draftList.length }" @click="pick('drafts', 'all')"><FeatherIcon name="edit-3" class="size-3.5 item-icon lead" /><span class="item-text">{{ __('Drafts') }}</span><span v-if="talk.draftList.length" class="group-badge">{{ talk.draftList.length }}</span></button></li>
      </ul>

      <section v-for="group in groups" :key="group.id" class="nav-group">
        <button v-if="!talk.navCollapsed" type="button" class="group-header" :aria-expanded="talk.navOpen[group.id]" :aria-controls="`talk-group-${group.id}`" @click="talk.navOpen[group.id] = !talk.navOpen[group.id]">
          <FeatherIcon name="chevron-right" class="size-4 chevron" :class="{ 'rotate-90': talk.navOpen[group.id] }" />
          <span class="group-label">{{ group.label }}</span>
          <span v-if="!talk.navOpen[group.id] && group.unread" class="group-badge" :class="{ amber: group.id === 'live' }">{{ group.unread }}</span>
        </button>
        <button v-else type="button" class="strip-group" :aria-label="`${group.label}${group.unread ? ` · ${group.unread} unread` : ''}`" :title="group.label" :aria-expanded="talk.navOpen[group.id]" @click="expandTo(group.id)">
          <FeatherIcon :name="group.icon" class="size-4" />
          <span v-if="group.unread" class="strip-dot" :class="{ amber: group.id === 'live' }" aria-hidden="true" />
        </button>

        <div v-show="talk.navOpen[group.id] && (!talk.navCollapsed || group.id === 'crm')" :id="`talk-group-${group.id}`" class="group-body">
          <nav v-if="group.id === 'crm'" class="flex flex-col" :aria-label="__('CRM')">
            <SidebarLink v-for="link in crmLinks" :key="link.label" :icon="link.icon" :label="__(link.label)" :to="link.to" :isCollapsed="talk.navCollapsed" class="mx-2 my-[1.5px]" />
            <template v-for="extra in extraViews" :key="extra.name">
              <p v-if="!talk.navCollapsed" class="sub-label">{{ __(extra.name) }}</p>
              <SidebarLink v-for="link in extra.views" :key="link.label" :icon="link.icon" :label="__(link.label)" :to="link.to" :isCollapsed="talk.navCollapsed" class="mx-2 my-[1.5px]" />
            </template>
          </nav>

          <ul v-else-if="group.id === 'phones'" class="item-list" :aria-label="__('Numbers')">
            <li v-if="!phoneLines.length" class="item-empty">{{ __('No numbers yet.') }}</li>
            <li v-for="line in phoneLines" :key="line.name">
              <button type="button" class="item" :class="{ selected: isPhoneLine(line) }" @click="openLine(line)">
                <span class="item-text">{{ line.emoji }} {{ line.label || formatPhone(line.number) }}</span>
                <button type="button" class="copy-num" :title="__('Copy number')" :aria-label="__('Copy number')" @click.stop="copyNumber(line.number)"><FeatherIcon name="copy" class="size-3.5" /></button>
              </button>
            </li>
          </ul>

          <ul v-else-if="group.id === 'live'" class="item-list" :aria-label="__('Live')">
            <li v-if="!talk.calls.length" class="item-empty">{{ __('Nothing live right now.') }}</li>
            <li v-for="c in talk.calls" :key="c.call_log">
              <button type="button" class="item" :class="{ selected: isSelected('live', c.call_log), 'live-one': isLiveOne(c.call_log) }" :aria-pressed="isSelected('live', c.call_log)" @click="pick('live', c.call_log)">
                <span class="item-dot" aria-hidden="true" /><span class="item-text"><b>{{ talk.displayName(c.rep) }}</b> · {{ c.lead_name || formatPhone(c.number) || __('Unknown') }}</span><FeatherIcon :name="isLiveOne(c.call_log) ? 'zap' : 'headphones'" class="size-3.5 item-icon" />
              </button>
            </li>
          </ul>

          <ul v-else-if="group.id === 'channels'" class="item-list" :aria-label="__('Channels')">
            <li v-if="talk.standup"><button type="button" class="item pinned" :class="{ selected: isSelected('standup', talk.standup.name), unread: talk.standup.unread }" :aria-pressed="isSelected('standup', talk.standup.name)" @click="pick('standup', talk.standup.name)"><FeatherIcon name="bookmark" class="size-3.5 item-icon lead" /><span class="item-text">{{ __('Standup') }}</span><span v-if="talk.standup.unread" class="group-badge">{{ talk.standup.unread }}</span><small v-else class="item-state">{{ __('pinned') }}</small></button></li>
            <li v-for="c in [...talk.channelRows, ...talk.botRows]" :key="c.name"><button type="button" class="item" :class="{ selected: isSelected('channel', c.name), unread: c.unread }" :aria-pressed="isSelected('channel', c.name)" @click="pick('channel', c.name)"><FeatherIcon :name="c.kind === 'bot' ? 'cpu' : 'hash'" class="size-3.5 item-icon lead" /><span class="item-text">{{ c.name }}</span><span v-if="c.unread" class="group-badge">{{ c.unread }}</span></button></li>
            <li v-if="!talk.channelRows.length && !talk.standup" class="item-empty">{{ talk.channels.loading ? __('Loading…') : __('No channels yet.') }}</li>
          </ul>

          <ul v-else-if="group.id === 'leads'" class="item-list" :aria-label="__('Leads')">
            <li v-if="!talk.leadRows.length" class="item-empty">{{ __('Open Team chat on a lead to start one.') }}</li>
            <li v-for="c in talk.leadRows" :key="c.name"><button type="button" class="item" :class="{ selected: isSelected('lead', c.lead || c.name.replace(/^lead-/, '')), unread: c.unread }" @click="pick('lead', c.lead || c.name.replace(/^lead-/, ''))"><FeatherIcon name="home" class="size-3.5 item-icon lead" /><span class="item-text">{{ c.title || c.lead }}</span><span v-if="c.unread" class="group-badge">{{ c.unread }}</span></button></li>
          </ul>

          <ul v-else class="item-list" :aria-label="__('Direct messages')">
            <li v-for="c in talk.dmRows" :key="c.name"><button type="button" class="item" :class="{ selected: isSelected('dm', c.name), unread: c.unread }" :aria-pressed="isSelected('dm', c.name)" @click="pick('dm', c.name)"><span class="presence" :class="talk.statusOf(c.dm_user)" aria-hidden="true" /><span class="item-text">{{ talk.displayName(c.dm_user) }}</span><span v-if="c.unread" class="group-badge">{{ c.unread }}</span><small v-else class="item-state">{{ stateLabel(talk.statusOf(c.dm_user)) }}</small></button></li>
            <li><button type="button" class="item new-dm" @click="newDm"><FeatherIcon name="plus" class="size-3.5 item-icon lead" /><span class="item-text">{{ __('New message') }}</span></button></li>
          </ul>
        </div>
      </section>
    </div>
    <div class="nav-footer">
      <SidebarLink :label="talk.navCollapsed ? __('Expand') : __('Collapse')" :isCollapsed="talk.navCollapsed" class="mx-2 my-[1.5px]" @click="talk.navCollapsed = !talk.navCollapsed">
        <template #icon><span class="grid h-4 w-4 flex-shrink-0 place-items-center"><CollapseSidebar class="h-4 w-4 text-ink-gray-7 duration-300 ease-in-out" :class="{ '[transform:rotateY(180deg)]': talk.navCollapsed }" /></span></template>
      </SidebarLink>
    </div>
  </aside>
</template>
<script setup>
/**
 * The next workspace's left column: the real CRM nav as a collapsible group,
 * then Live / Channels / Direct messages from `talkStore`. Renders OVER the
 * real sidebar (App.vue shifts the layout under it via `reserve`), so
 * AppSidebar / MobileSidebar stay untouched and classic is byte-identical.
 * A conversation is a page: picking one routes to /talk/:kind/:id and the
 * active item is read off the route, exactly as SidebarLink highlights Leads.
 */
import { Badge, FeatherIcon, createResource } from 'frappe-ui'
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import UserDropdown from '@/components/UserDropdown.vue'
import SidebarLink from '@/components/SidebarLink.vue'
import NotificationsIcon from '@/components/Icons/NotificationsIcon.vue'
import PhoneIcon from '@/components/Icons/PhoneIcon.vue'
import CollapseSidebar from '@/components/Icons/CollapseSidebar.vue'
import PinIcon from '@/components/Icons/PinIcon.vue'
import { getSettings } from '@/stores/settings'
import { viewsStore } from '@/stores/views'
import { applySidebarConfig } from '@/utils/sidebarLinks'
import { unreadNotificationsCount, notificationsStore } from '@/stores/notifications'
import { talkStore } from '@/stores/talk'
import { formatPhone } from '@/utils/phoneFormat'
import { copyToClipboard } from '@/utils'
import { openCommandPalette } from '@/composables/modals'

defineProps({ bottom: { type: Number, default: 0 }, mobile: Boolean })
const emit = defineEmits(['picked'])
const route = useRoute()
const router = useRouter()
const talk = talkStore()
const { toggle: toggleNotificationPanel } = notificationsStore()
const { settings } = getSettings()
const { getPinnedViews, getPublicViews } = viewsStore()

const crmLinks = computed(() => applySidebarConfig(settings.value?.custom_sidebar_items).filter((link) => !link.condition || link.condition()))
const extraViews = computed(() => [
  { name: 'Public Views', views: getPublicViews() },
  { name: 'Pinned Views', views: getPinnedViews() },
].filter((group) => group.views.length).map((group) => ({
  name: group.name,
  views: group.views.map((view) => ({ label: view.label, icon: view.icon || PinIcon, to: { name: view.route_name, params: { viewType: view.type || 'list' }, query: { view: view.name } } })),
})))
const phoneLineList = createResource({ url: 'crm.api.telephony.lines', auto: true, initialData: [], onError: () => {} })
const phoneLines = computed(() => phoneLineList.data || [])
const groups = computed(() => [
  { id: 'phones', label: __('Numbers'), icon: 'phone', unread: 0 },
  { id: 'crm', label: __('CRM'), icon: 'grid', unread: 0 },
  { id: 'live', label: __('Live'), icon: 'activity', unread: talk.liveOnes.length },
  { id: 'channels', label: __('Channels'), icon: 'hash', unread: talk.unreadOf('channels') },
  { id: 'leads', label: __('Leads'), icon: 'home', unread: talk.unreadOf('leads') },
  { id: 'dms', label: __('Direct messages'), icon: 'message-square', unread: talk.unreadOf('dms') },
])
const stateLabels = { on_call: __('On call'), away: __('Away'), offline: __('Offline'), online: '' }
function stateLabel(status) { return stateLabels[status] ?? '' }
function isLiveOne(callLog) { return talk.liveOnes.some((a) => a.call_log === callLog) }
function isSelected(kind, id) { return route.name === 'Talk' && route.params.kind === kind && route.params.id === id }
function pick(kind, id) {
  router.push({ name: 'Talk', params: { kind, id } })
  emit('picked')
}
function expandTo(group) { talk.navCollapsed = false; talk.navOpen[group] = true }
// New message = the ⌘⇧K DM switcher, which also lists teammates without a
// thread yet (TalkKeys creates the DM channel on pick via talk.ensure_dm).
function newDm() { openCommandPalette('dm') }
function isPhoneLine(line) { return route.name === 'Phone Desk' && String(route.query.line || '') === line.name }
function openLine(line) { router.push({ name: 'Phone Desk', query: { line: line.name } }); emit('picked') }
function copyNumber(number) { copyToClipboard(formatPhone(number) || number) }
</script>
<style scoped>
.left-nav { position: fixed; top: 0; left: 0; z-index: 39; display: flex; flex-direction: column; background: var(--surface-menu-bar, #f8f8f8); border-right: 1px solid var(--outline-gray-2, #e2e2e2); color: var(--ink-gray-8, #333); transition: width .3s ease-in-out; }
.left-nav.mobile { position: absolute; inset: 0; width: 100% !important; bottom: 0 !important; z-index: 20; border-right: 0; }
.nav-header { padding: 8px; }
.nav-scroll { flex: 1; min-height: 0; overflow-y: auto; overflow-x: hidden; }
.inbox-links { margin: 4px 0 2px; }
.copy-num { flex-shrink: 0; padding: 2px; color: var(--ink-gray-5, #777); }
.copy-num:hover { color: var(--ink-gray-9, #222); }
.nav-group { margin-top: 6px; }
.group-header { display: flex; align-items: center; gap: 6px; width: 100%; padding: 9px 16px 8px; font-size: 13px; color: var(--ink-gray-5, #777); text-align: left; }
.group-header:hover { color: var(--ink-gray-8, #333); }
.group-header:focus-visible, .strip-group:focus-visible, .item:focus-visible { outline: 2px solid var(--ink-gray-7, #555); outline-offset: -2px; border-radius: 6px; }
.chevron { color: var(--ink-gray-9, #222); transition: transform .3s ease-in-out; }
.group-label { flex: 1; }
.group-badge { min-width: 16px; padding: 1px 5px; border-radius: 8px; background: var(--surface-gray-7, #333); color: #fff; font-size: 10px; text-align: center; line-height: 14px; }
.group-badge.amber, .strip-dot.amber { background: #d9a536; }
.strip-group { position: relative; display: grid; place-items: center; width: 32px; height: 32px; margin: 2px 8px; border-radius: 6px; color: var(--ink-gray-7, #555); }
.strip-group:hover { background: var(--surface-gray-2, #eee); }
.strip-dot { position: absolute; top: 3px; right: 3px; width: 7px; height: 7px; border-radius: 50%; background: var(--surface-gray-6, #555); box-shadow: 0 0 0 1.5px var(--surface-menu-bar, #f8f8f8); }
.sub-label { margin: 10px 16px 4px; font-size: 11px; color: var(--ink-gray-5, #777); }
.item-list { list-style: none; margin: 0; padding: 0 8px; }
.item-empty { padding: 6px 10px; font-size: 12px; color: var(--ink-gray-5, #777); }
.item { display: flex; align-items: center; gap: 8px; width: 100%; height: 30px; padding: 0 8px; margin: 1.5px 0; border-radius: 6px; font-size: 13px; text-align: left; color: var(--ink-gray-8, #333); }
.item:hover { background: var(--surface-gray-2, #eee); }
.item.selected { background: var(--surface-selected, #fff); box-shadow: 0 1px 2px #0001; }
.item.unread { font-weight: 600; color: var(--ink-gray-9, #222); }
.item.pinned .item-icon { color: #9b772e; }
.item.new-dm { color: var(--ink-gray-5, #777); }
.item-text { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.item-icon { color: var(--ink-gray-5, #777); flex-shrink: 0; }
.item-icon.lead { order: -1; }
.item-dot { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; background: #388452; }
.item.live-one .item-dot { background: #d9a536; box-shadow: 0 0 0 3px #d9a53633; }
.presence { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; background: var(--surface-gray-4, #ccc); }
.presence.online { background: #388452; }
.presence.on_call { background: #bc8e37; }
.presence.away { background: #d9a536; }
.item-state { font-size: 10px; color: var(--ink-gray-5, #777); }
.nav-footer { padding: 8px 0; border-top: 1px solid var(--outline-gray-1, #eee); }
</style>
