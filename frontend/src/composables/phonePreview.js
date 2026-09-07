import { reactive } from 'vue'
import { newPhonePreview } from '@/utils/phonePreview'

// Explicitly activated from the dev-only Phone Preview route; survives SPA navigation.
export const phonePreview = reactive(newPhonePreview())
