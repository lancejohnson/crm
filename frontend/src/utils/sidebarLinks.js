import LucideLayoutDashboard from '~icons/lucide/layout-dashboard'
import LeadsIcon from '@/components/Icons/LeadsIcon.vue'
import DealsIcon from '@/components/Icons/DealsIcon.vue'
import ContactsIcon from '@/components/Icons/ContactsIcon.vue'
import OrganizationsIcon from '@/components/Icons/OrganizationsIcon.vue'
import NoteIcon from '@/components/Icons/NoteIcon.vue'
import TaskIcon from '@/components/Icons/TaskIcon.vue'
import PhoneIcon from '@/components/Icons/PhoneIcon.vue'
import CommentIcon from '@/components/Icons/CommentIcon.vue'
import StepsIcon from '@/components/Icons/StepsIcon.vue'

// canonical module list for the left sidebar; admin-defined order/visibility
// lives in FCRM Settings.custom_sidebar_items as [{label, hidden}]
export const sidebarLinks = [
  { label: 'Dashboard', icon: LucideLayoutDashboard, to: 'Dashboard' },
  { label: 'Leads', icon: LeadsIcon, to: 'Leads' },
  { label: 'Deals', icon: DealsIcon, to: 'Deals' },
  { label: 'Contacts', icon: ContactsIcon, to: 'Contacts' },
  { label: 'Organizations', icon: OrganizationsIcon, to: 'Organizations' },
  { label: 'Notes', icon: NoteIcon, to: 'Notes' },
  { label: 'Tasks', icon: TaskIcon, to: 'Tasks' },
  { label: 'Call Logs', icon: PhoneIcon, to: 'Call Logs' },
  { label: 'Text Messages', icon: CommentIcon, to: 'Text Messages' },
  { label: 'Sequences', icon: StepsIcon, to: 'Sequences' },
]

// merge the saved [{label, hidden}] config with the canonical list:
// saved order wins, hidden entries drop out, modules added in later
// releases (absent from the saved config) append at the end, visible
export function applySidebarConfig(configJSON) {
  let config = []
  try {
    config = JSON.parse(configJSON || '[]')
  } catch (e) {
    config = []
  }
  if (!Array.isArray(config) || !config.length) return sidebarLinks

  const remaining = new Map(sidebarLinks.map((l) => [l.label, l]))
  const ordered = []
  for (const item of config) {
    const link = remaining.get(item.label)
    if (!link) continue
    remaining.delete(item.label)
    if (!item.hidden) ordered.push(link)
  }
  ordered.push(...remaining.values())
  return ordered
}
