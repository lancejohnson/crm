<template>
  <SettingsLayoutBase
    :title="__('InvestorLift')"
    :description="
      __(
        'Connection status for the InvestorLift dispo integration, and where to enter a login 2FA code if one is ever needed.',
      )
    "
  >
    <template #content>
      <div class="flex flex-col gap-8">
        <!-- connection status -->
        <section class="flex flex-col gap-3">
          <div class="text-base font-semibold text-ink-gray-9">
            {{ __('Connection') }}
          </div>
          <div class="flex items-center gap-2">
            <Badge
              :theme="status.connected ? 'green' : status.configured ? 'orange' : 'gray'"
              variant="subtle"
            >
              {{
                status.connected
                  ? __('Connected')
                  : status.configured
                    ? __('Configured — not yet signed in')
                    : __('Not configured')
              }}
            </Badge>
            <span v-if="status.last_login_at" class="text-sm text-ink-gray-5">
              {{ __('Last sign-in') }} {{ formatDate(status.last_login_at, '', true) }}
            </span>
          </div>
          <p v-if="!status.configured" class="text-p-sm text-ink-gray-6">
            {{ __('InvestorLift credentials are not set in this site\'s configuration.') }}
          </p>
        </section>

        <!-- 2FA -->
        <section class="flex flex-col gap-3">
          <div class="flex items-center gap-2">
            <div class="text-base font-semibold text-ink-gray-9">
              {{ __('Two-factor login') }}
            </div>
            <Badge
              v-if="status.twofa_status === 'pending'"
              theme="orange"
              variant="subtle"
              :label="__('Code needed')"
            />
          </div>

          <div
            v-if="status.twofa_status === 'pending'"
            class="rounded-lg border border-outline-gray-2 bg-surface-gray-1 p-3"
          >
            <p class="text-p-sm text-ink-gray-7">
              {{
                __(
                  'InvestorLift asked for a verification code and it could not be read automatically from the Quo line. Enter the code texted to (651) 390-7073 below.',
                )
              }}
              <span v-if="status.twofa_requested_at" class="text-ink-gray-5">
                ({{ __('requested') }} {{ formatDate(status.twofa_requested_at, '', true) }})
              </span>
            </p>
            <div class="mt-2 flex items-center gap-2">
              <input
                v-model="code"
                type="text"
                inputmode="numeric"
                :placeholder="__('6-digit code')"
                class="w-40 rounded border border-outline-gray-2 bg-surface-white px-2 py-1 text-sm text-ink-gray-8 focus:outline-none"
                @keydown.enter="submit"
              />
              <Button
                variant="solid"
                :loading="submitting"
                :label="__('Submit code')"
                @click="submit"
              />
            </div>
          </div>
          <p v-else class="text-p-sm text-ink-gray-6">
            {{
              __(
                'No code is currently required. When InvestorLift challenges a login, the code texted to (651) 390-7073 is read automatically; if that ever fails, a code entry box appears here.',
              )
            }}
          </p>
        </section>

        <!-- property matching -->
        <section class="flex flex-col gap-3">
          <div class="text-base font-semibold text-ink-gray-9">
            {{ __('Property matching') }}
          </div>
          <p class="text-p-sm text-ink-gray-6">
            {{
              __(
                'Every InvestorLift property is auto-linked to the CRM lead at the same address (normalizing "South Street" vs "S St"). This runs hourly; run it now to link newly-published deals.',
              )
            }}
          </p>
          <div>
            <Button
              variant="subtle"
              :loading="matching"
              :label="__('Match properties now')"
              @click="matchNow"
            />
          </div>
          <div v-if="matches.length" class="overflow-hidden rounded-lg border border-outline-gray-2">
            <div
              v-for="m in matches"
              :key="m.il_property_id"
              class="flex items-center justify-between gap-3 border-b border-outline-gray-2 px-3 py-2 text-sm last:border-b-0"
            >
              <span class="truncate text-ink-gray-7">{{ m.il_address }}</span>
              <span class="shrink-0 text-ink-gray-8">
                {{ m.matched_lead_name || __('— no lead found') }}
              </span>
              <Badge
                :theme="m.action === 'linked' ? 'green' : m.action === 'already correct' ? 'blue' : 'gray'"
                variant="subtle"
                size="sm"
              >
                {{ m.matched_lead_name ? m.action : __('unmatched') }}
              </Badge>
            </div>
          </div>
        </section>
      </div>
    </template>
  </SettingsLayoutBase>
</template>

<script setup>
import SettingsLayoutBase from '@/components/Layouts/SettingsLayoutBase.vue'
import { formatDate } from '@/utils'
import { Badge, Button, createResource, call } from 'frappe-ui'
import { computed, ref } from 'vue'

const connection = createResource({
  url: 'crm.api.investorlift.get_connection_status',
  auto: true,
})

const status = computed(() => connection.data || {})
const code = ref('')
const submitting = ref(false)

const matches = ref([])
const matching = ref(false)
async function matchNow() {
  matching.value = true
  try {
    matches.value = await call('crm.api.investorlift.match_properties', { dry_run: 0 })
  } finally {
    matching.value = false
  }
}

async function submit() {
  if (!code.value.trim()) return
  submitting.value = true
  try {
    await call('crm.api.investorlift.submit_2fa_code', { code: code.value.trim() })
    code.value = ''
    connection.reload()
  } finally {
    submitting.value = false
  }
}
</script>
