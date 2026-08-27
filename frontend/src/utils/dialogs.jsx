import { Dialog, ErrorMessage } from 'frappe-ui'
import { reactive, ref } from 'vue'

let dialogs = ref([])

export function isDialogOpen() {
  if (dialogs.value.some((d) => d.show)) return true
  if (typeof document === 'undefined') return false
  // frappe-ui Dialog (reka) is not registered in `dialogs` — PracticePlayer,
  // CompDetailModal, etc. still need CRM shortcuts (D/P/S/F, [ ]) to stand down.
  return !!document.querySelector(
    '[role="dialog"][data-state="open"], [role="dialog"]:not([aria-hidden="true"])',
  )
}

export let Dialogs = {
  name: 'Dialogs',
  render() {
    return dialogs.value.map((dialog) => (
      <Dialog
        options={dialog}
        modelValue={dialog.show}
        onUpdate:modelValue={(val) => (dialog.show = val)}
      >
        {{
          'body-content': () => {
            return [
              dialog.message && (
                <p class="text-p-base text-ink-gray-7">{dialog.message}</p>
              ),
              dialog.html && <div v-html={dialog.html} />,
              <ErrorMessage class="mt-2" message={dialog.error} />,
            ]
          },
        }}
      </Dialog>
    ))
  },
}

export function createDialog(dialogOptions) {
  let dialog = reactive(dialogOptions)
  dialog.key = 'dialog-' + dialogs.value.length
  dialog.show = false
  setTimeout(() => {
    dialog.show = true
  }, 0)
  dialogs.value.push(dialog)
}
