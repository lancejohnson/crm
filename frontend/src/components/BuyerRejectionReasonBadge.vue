<template>
  <span
    class="inline-flex h-6 items-center gap-1 rounded border border-outline-orange-1 bg-surface-orange-1 px-1.5 text-xs text-ink-orange-3"
    :title="definition.value"
  >
    <component :is="icon" class="size-3.5 shrink-0" />
    <span v-if="showLabel" class="whitespace-nowrap">{{
      definition.shortLabel
    }}</span>
    <span v-if="count !== null" class="font-medium tabular-nums">{{
      count
    }}</span>
  </span>
</template>

<script setup>
import CircleDollarSignIcon from '~icons/lucide/circle-dollar-sign'
import MapPinOffIcon from '~icons/lucide/map-pin-off'
import HourglassIcon from '~icons/lucide/hourglass'
import Flower2Icon from '~icons/lucide/flower-2'
import CircleSlash2Icon from '~icons/lucide/circle-slash-2'
import HammerIcon from '~icons/lucide/hammer'
import BanIcon from '~icons/lucide/ban'
import CircleEllipsisIcon from '~icons/lucide/circle-ellipsis'
import { buyerRejectionReason } from '@/utils/buyerRejectionReasons'
import { computed } from 'vue'

const props = defineProps({
  reason: { type: String, required: true },
  showLabel: { type: Boolean, default: false },
  count: { type: Number, default: null },
})

const icons = {
  pricing: CircleDollarSignIcon,
  location: MapPinOffIcon,
  market: HourglassIcon,
  'daisy-chain': Flower2Icon,
  'deal-type': CircleSlash2Icon,
  condition: HammerIcon,
  'no-longer-buying': BanIcon,
  other: CircleEllipsisIcon,
}

const definition = computed(() => buyerRejectionReason(props.reason))
const icon = computed(() => icons[definition.value.icon] || CircleEllipsisIcon)
</script>
