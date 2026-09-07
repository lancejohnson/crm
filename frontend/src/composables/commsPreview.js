import { reactive } from 'vue'
import { newCommsPreview } from '@/utils/commsPreview'

// Dev-only comms mockup state (inbox / lead thread / rail). Survives SPA navigation.
export const commsPreview = reactive(newCommsPreview())
