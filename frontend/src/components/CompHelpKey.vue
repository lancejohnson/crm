<template>
  <Popover placement="top-start">
    <template #target="{ togglePopover, isOpen }">
      <button
        type="button"
        class="flex size-[18px] shrink-0 items-center justify-center rounded-full border text-[11px] font-bold leading-none"
        :class="
          isOpen
            ? 'border-ink-gray-8 bg-ink-gray-8 text-white'
            : 'border-outline-gray-3 bg-surface-white text-ink-gray-7 hover:border-ink-gray-8 hover:text-ink-gray-9'
        "
        :title="__('What the numbers mean')"
        @click="togglePopover"
      >
        ?
      </button>
    </template>
    <template #body>
      <div
        class="mb-2 max-w-[calc(100vw-2rem)] rounded-lg bg-surface-modal p-3 shadow-2xl ring-1 ring-black ring-opacity-5 sm:w-[22rem]"
      >
        <div class="text-2xs font-semibold uppercase tracking-wide text-ink-gray-5">
          {{ __('On a pin') }}
        </div>
        <div class="mt-2 flex items-start gap-3">
          <div
            class="shrink-0 rounded-[9px] px-1.5 py-1"
            :style="{ background: SOLD.bg, color: SOLD.ink, boxShadow: '0 1px 2px rgba(0,0,0,.28)' }"
          >
            <div class="flex items-baseline justify-center whitespace-nowrap">
              <span class="text-[11.5px] font-bold leading-none">$120k</span>
              <span class="ml-0.5 text-[9px] font-medium leading-none opacity-70">1948</span>
              <span class="ml-0.5 text-[9px] font-medium leading-none opacity-70">Jul 17</span>
            </div>
            <div
              class="mt-0.5 flex items-baseline justify-between gap-1.5 text-[9px] font-medium leading-none opacity-90"
            >
              <span>3/2 · 1,550sf</span>
              <span class="tabular-nums">77d</span>
            </div>
          </div>
          <dl class="min-w-0 flex-1 text-2xs leading-4 text-ink-gray-6">
            <div class="flex gap-1.5">
              <dt class="w-10 shrink-0 font-semibold tabular-nums text-ink-gray-8">$120k</dt>
              <dd>{{ __('last price') }}</dd>
            </div>
            <div class="flex gap-1.5">
              <dt class="w-10 shrink-0 font-semibold text-ink-gray-8">1948</dt>
              <dd>{{ __('year built') }}</dd>
            </div>
            <div class="flex gap-1.5">
              <dt class="w-10 shrink-0 font-semibold text-ink-gray-8">Jul 17</dt>
              <dd>{{ __('when it sold') }}</dd>
            </div>
            <div class="flex gap-1.5">
              <dt class="w-10 shrink-0 font-semibold tabular-nums text-ink-gray-8">77d</dt>
              <dd>{{ __('how long it sat') }}</dd>
            </div>
          </dl>
        </div>
        <p class="mt-2 text-2xs leading-4 text-ink-gray-5">
          {{ __('Red or violet: that top-right number is days listed, not a date.') }}
          {{ __('★ is a possible flip — look before you price off it.') }}
        </p>

        <div class="mt-3 text-2xs font-semibold uppercase tracking-wide text-ink-gray-5">
          {{ __('On a card') }}
        </div>
        <div class="mt-2 overflow-hidden rounded-md border border-outline-gray-2 bg-surface-white">
          <div class="relative h-14 bg-surface-gray-2">
            <span
              class="absolute left-2 top-2 rounded px-1.5 py-0.5 text-2xs font-semibold"
              :style="{ background: SOLD.bg, color: SOLD.ink }"
            >
              {{ __('Sold') }}
            </span>
          </div>
          <div class="px-2.5 py-2">
            <div class="flex items-baseline justify-between gap-2">
              <span class="text-sm font-semibold text-ink-gray-9">$120,000</span>
              <span class="text-2xs tabular-nums text-ink-gray-5">0.2 mi</span>
            </div>
            <div class="text-2xs text-ink-gray-6">
              {{ __('3 bd · 2 ba · 1,550 sqft · built 1948') }}
            </div>
            <div class="mt-1 flex gap-1">
              <span class="rounded bg-surface-gray-2 px-1 text-2xs font-medium tabular-nums text-ink-gray-6">−1 bd</span>
              <span class="rounded bg-surface-gray-2 px-1 text-2xs font-medium tabular-nums text-ink-gray-6">+201 sqft</span>
            </div>
            <div class="mt-1 text-2xs font-medium text-ink-gray-8">15300 Collingham Dr</div>
            <div class="mt-0.5 text-2xs text-ink-gray-5">
              {{ __('Off-market Jul 17, 2026 · 39d ago · took 77d to sell') }}
            </div>
          </div>
        </div>
        <dl class="mt-2 space-y-0.5 text-2xs leading-4 text-ink-gray-6">
          <div><span class="font-semibold text-ink-gray-8">{{ __('Sold') }}</span> — {{ __('a close, not an ask') }}</div>
          <div><span class="font-semibold text-ink-gray-8">0.2 mi</span> — {{ __('from this property') }}</div>
          <div><span class="font-semibold text-ink-gray-8">−1 bd</span> — {{ __('vs this property') }}</div>
          <div>{{ __('The last line is the same two times as the pin, written out.') }}</div>
        </dl>
      </div>
    </template>
  </Popover>
</template>

<script setup>
/**
 * Field key for the comps map. Lives on the legend as a `?` so it costs nothing
 * at rest and does not steal a row from the map. One annotated pin + one
 * annotated tray card, because those are the two grammars a rep has to learn.
 */
import { Popover } from 'frappe-ui'
import { COMP_COLORS } from '@/utils/comps'

const SOLD = COMP_COLORS.sold
</script>
