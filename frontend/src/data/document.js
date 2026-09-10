import { getScript } from '@/data/script'
import { globalStore } from '@/stores/global'
import { getMeta } from '@/stores/meta'
import { useAttachments } from '@/composables/useAttachments'
import { showSettings, activeSettingsPage } from '@/composables/settings'
import { runSequentially, parseAssignees, evaluateExpression } from '@/utils'
import { createDocumentResource, createResource, toast } from 'frappe-ui'
import { ref, reactive } from 'vue'

const documentsCache = {}
const controllersCache = {}

function isTimestampMismatch(err) {
  return (
    err?.exc_type === 'TimestampMismatchError' ||
    /modified after you have opened/i.test(err?.messages?.[0] || '')
  )
}

// Top-level fields whose value differs from the last copy fetched from the
// server, i.e. what a `save` is actually trying to change. `null` when there
// is no server copy to diff against. `modified` is excluded on purpose: the
// whole point of the retry is to take the server's fresh one.
function changedFields(resource) {
  const doc = resource.doc
  const base = resource.originalDoc
  if (!doc || !base) return null
  const changed = {}
  for (const key of Object.keys(doc)) {
    if (['modified', 'modified_by', 'doctype', 'name'].includes(key)) continue
    if (JSON.stringify(doc[key]) !== JSON.stringify(base[key])) {
      changed[key] =
        doc[key] === undefined ? null : JSON.parse(JSON.stringify(doc[key]))
    }
  }
  return changed
}
const assigneesCache = {}
const permissionsCache = {}

export function useDocument(doctype, docname, resourceOverrides = {}) {
  const { setupScript, scripts } = getScript(doctype)
  const meta = getMeta(doctype)
  const { trackOldFile, processPendingDeletions } = useAttachments(
    doctype,
    docname,
  )

  documentsCache[doctype] = documentsCache[doctype] || {}

  const error = ref('')
  // True while a full-doc save that may hit a stale `modified` is in flight;
  // the resource-level onError uses it to hold its toast until the retry.
  let mismatchRetryPending = false

  if (!documentsCache[doctype][docname || '']) {
    if (docname) {
      documentsCache[doctype][docname] = createDocumentResource({
        doctype: doctype,
        name: docname,
        onSuccess: async () => await setupFormScript(),
        onError: (err) => {
          error.value = err
          if (err.exc_type === 'DoesNotExistError') {
            toast.error(__(err.messages[0] || 'Document does not exist'))
          }
          if (err.exc_type === 'PermissionError') {
            toast.error(
              __(
                err.messages[0] ||
                  'You do not have permission to access this document',
              ),
            )
          }
        },
        setValue: {
          onSuccess: () => {
            triggerOnSave()
            toast.success(__('Document updated successfully'))
            processPendingDeletions()
          },
          onError: (err) => {
            // A stale-copy save is retried below (see submitWithMismatchRetry);
            // only the retry's own failure is worth a toast.
            if (isTimestampMismatch(err) && mismatchRetryPending) return

            triggerOnError(err)

            if (err.exc_type == 'MandatoryError') {
              const fieldName = err.messages
                .map((msg) => {
                  let arr = msg.split(': ')
                  return arr[arr.length - 1].trim()
                })
                .join(', ')
              toast.error(__('Mandatory field error: {0}', [fieldName]))
              return
            }

            err.messages?.forEach((msg) => {
              toast.error(msg)
            })

            if (err.messages?.length === 0) {
              toast.error(__('An error occurred while updating the document'))
            }

            console.error(err)
          },
        },
        ...resourceOverrides,
      })
      if (!documentsCache[doctype][docname].fieldHtmlMap) {
        documentsCache[doctype][docname].fieldHtmlMap = {}
      }

      // Override the submit function to trigger validation before submitting
      // TODO: fix validate function to return error message instead of throwing error in frappe-ui and remove try-catch block here
      const resource = documentsCache[doctype][docname]
      const _save = resource.save
      const _originalSubmit = _save.submit
      _save.submit = async function (params, tempOptions = {}) {
        try {
          await triggerOnValidate()
        } catch (err) {
          console.error(err)
          return
        }
        const mandatory = checkMandatory(resource.doc)
        if (mandatory) return
        return submitWithMismatchRetry(params, tempOptions)
      }

      // `save` posts the WHOLE doc, `modified` included, and the server refuses
      // it when anything has touched the row since the page loaded it
      // (TimestampMismatchError: "Document has been modified after you have
      // opened it"). On this CRM that is routine, not exceptional: adding a
      // comment bumps the lead's `modified` in a background job seconds later
      // (upstream `on_comment_insert`), the Today board logs its outcome as a
      // comment, Quo webhooks relink call logs, contract parsing writes terms,
      // owner changes move tasks... So comment-then-change-status failed until
      // a hard refresh (Dennis, 2026-09-10). None of those writers touched the
      // field the rep was changing. Recovery: refetch the doc, re-apply only
      // the fields THIS save changed, and submit once more. A field a teammate
      // changed meanwhile is kept unless the rep changed the same one, which is
      // the conflict the timestamp check exists for and the one that still
      // reads as a win for the person clicking.
      async function submitWithMismatchRetry(params, tempOptions) {
        const changed = changedFields(resource)
        const firstTry = {
          ...tempOptions,
          onError: (err) => {
            if (isTimestampMismatch(err) && changed) return
            tempOptions.onError?.(err)
          },
        }
        mismatchRetryPending = !!changed
        try {
          return await _originalSubmit.call(_save, params, firstTry)
        } catch (err) {
          mismatchRetryPending = false
          if (!isTimestampMismatch(err) || !changed) throw err
          console.warn(
            `[document] ${doctype} ${docname} changed underneath this save; refreshing and retrying`,
            Object.keys(changed),
          )
          await resource.get.fetch()
          Object.assign(resource.doc, changed)
          // A second failure surfaces normally: toast + the caller's onError.
          return await _originalSubmit.call(_save, params, tempOptions)
        } finally {
          mismatchRetryPending = false
        }
      }
    } else {
      documentsCache[doctype][''] = reactive({
        doc: { __newDocument: true, doctype },
      })
      setupFormScript()
    }
  }

  assigneesCache[doctype] = assigneesCache[doctype] || {}

  if (!assigneesCache[doctype][docname || '']) {
    assigneesCache[doctype][docname || ''] = createResource({
      url: 'crm.api.doc.get_assigned_users',
      cache: `assignees:${doctype}:${docname}`,
      auto: docname ? true : false,
      params: {
        doctype: doctype,
        name: docname,
      },
      transform: (data) => parseAssignees(data),
    })
  }

  permissionsCache[doctype] = permissionsCache[doctype] || {}

  if (!permissionsCache[doctype][docname || '']) {
    permissionsCache[doctype][docname || ''] = createResource({
      url: 'frappe.client.get_doc_permissions',
      cache: `permissions:${doctype}:${docname}`,
      auto: docname ? true : false,
      params: {
        doctype: doctype,
        docname: docname,
      },
      initialData: { permissions: {} },
    })
  }

  async function setupFormScript() {
    if (
      controllersCache[doctype] &&
      typeof controllersCache[doctype][docname || ''] === 'object'
    ) {
      return
    }

    if (!controllersCache[doctype]) {
      controllersCache[doctype] = {}
    }

    controllersCache[doctype][docname || ''] = {}

    const { makeCall } = globalStore()

    let helpers = {}

    helpers.crm = {
      makePhoneCall: makeCall,
      openSettings: (page) => {
        showSettings.value = true
        activeSettingsPage.value = page
      },
    }

    const controllersArray = await setupScript(
      documentsCache[doctype][docname || ''],
      helpers,
    )

    if (!controllersArray || controllersArray.length === 0) return

    const organizedControllers = {}
    for (const controller of controllersArray) {
      const controllerKey = controller.constructor.name // e.g., "CRMLead", "CRMProducts"
      if (!organizedControllers[controllerKey]) {
        organizedControllers[controllerKey] = []
      }
      organizedControllers[controllerKey].push(controller)
    }
    controllersCache[doctype][docname || ''] = organizedControllers

    triggerOnLoad()
    triggerOnRender()
  }

  function getControllers(row = null) {
    const _doctype = row?.doctype || doctype
    const controllerKey = _doctype.replace(/\s+/g, '')

    const docControllers = controllersCache[doctype]?.[docname || '']

    if (
      typeof docControllers === 'object' &&
      docControllers !== null &&
      !Array.isArray(docControllers)
    ) {
      return docControllers[controllerKey] || []
    }
    return []
  }

  function checkMandatory(doc) {
    let fields = meta?.getFields() || []

    if (!fields || fields.length === 0) return

    let missingFields = []

    fields.forEach((df) => {
      let parent = meta?.doctypesMeta?.[df.parent] || null
      if (evaluateExpression(df.mandatory_depends_on, doc, parent)) {
        const value = doc[df.fieldname]
        if (
          value === undefined ||
          value === null ||
          (typeof value === 'string' && value.trim() === '') ||
          (Array.isArray(value) && value.length === 0)
        ) {
          missingFields.push(df.label || df.fieldname)
        }
      }
    })

    if (missingFields.length > 0) {
      toast.error(
        __('Mandatory fields required: {0}', [missingFields.join(', ')]),
      )
      return __('Mandatory fields required: {0}', [missingFields.join(', ')])
    }
  }

  async function triggerOnLoad() {
    const handler = async function () {
      await (this.onLoad?.() || this.on_load?.() || this.onload?.())
    }
    await trigger(handler)
  }

  async function triggerOnRender() {
    const handler = async function () {
      await (this.onRender?.() || this.on_render?.() || this.refresh?.())
    }
    await trigger(handler)
  }

  async function triggerOnBeforeCreate() {
    const args = Array.from(arguments)
    const handler = async function () {
      await (this.onBeforeCreate?.(...args) || this.on_before_create?.(...args))
    }
    await trigger(handler)
  }

  async function triggerOnValidate() {
    const handler = async function () {
      await (this.onValidate?.() || this.on_validate?.() || this.validate?.())
    }
    await trigger(handler)
  }

  async function triggerOnSave() {
    const handler = async function () {
      await (this.onSave?.() || this.on_save?.())
    }
    await trigger(handler)
  }

  async function triggerOnError() {
    const handler = async function () {
      await (this.onError?.() || this.on_error?.())
    }
    await trigger(handler)
  }

  async function triggerOnChange(fieldname, value, row) {
    let oldValue = null
    if (row) {
      oldValue = row[fieldname]
      row[fieldname] = value
    } else {
      oldValue = documentsCache[doctype][docname || ''].doc[fieldname]
      documentsCache[doctype][docname || ''].doc[fieldname] = value
      trackOldFile(oldValue, value)
    }

    const handler = async function () {
      this.value = value
      this.oldValue = oldValue
      if (row) {
        this.currentRowIdx = row.idx
      }
      await this[fieldname]?.()
    }

    try {
      await trigger(handler, row)
    } catch (error) {
      console.error(handler)
      throw error
    }
  }

  async function triggerButton(fieldname, row) {
    const handler = async function () {
      if (row) {
        this.currentRowIdx = row.idx
      }
      await this[fieldname]?.()
    }
    await trigger(handler, row)
  }

  async function triggerOnRowAdd(row) {
    const handler = async function () {
      this.currentRowIdx = row.idx
      this.value = row
      await this[row.parentfield + '_add']?.()
    }

    await trigger(handler, row)
  }

  async function triggerOnRowRemove(selectedRows, rows) {
    const handler = async function () {
      if (selectedRows.size === 1) {
        const selectedRow = Array.from(selectedRows)[0]
        this.currentRowIdx = rows.find((r) => r.name === selectedRow).idx
      } else {
        delete this.currentRowIdx
      }

      this.selectedRows = Array.from(selectedRows)
      this.rows = rows

      await this[rows[0].parentfield + '_remove']?.()
    }

    await trigger(handler, rows[0])
  }

  async function triggerOnCreateLead() {
    const args = Array.from(arguments)
    const handler = async function () {
      await (this.onCreateLead?.(...args) || this.on_create_lead?.(...args))
    }
    await trigger(handler)
  }

  async function triggerConvertToDeal() {
    const args = Array.from(arguments)
    const handler = async function () {
      await (this.convertToDeal?.(...args) || this.convert_to_deal?.(...args))
    }
    await trigger(handler)
  }

  function setFieldHtml(fieldname, html) {
    const cache = documentsCache[doctype][docname || '']
    if (!cache.fieldHtmlMap) cache.fieldHtmlMap = {}
    cache.fieldHtmlMap[fieldname] = html
  }

  async function trigger(taskFn, row = null) {
    const controllers = getControllers(row)
    if (!controllers.length) return

    const tasks = controllers.map(
      (controller) => async () => await taskFn.call(controller),
    )

    await runSequentially(tasks)
  }

  return {
    document: documentsCache[doctype][docname || ''],
    assignees: assigneesCache[doctype][docname || ''],
    permissions: permissionsCache[doctype][docname || ''],
    scripts,
    error,
    getControllers,
    triggerOnLoad,
    triggerOnRender,
    triggerOnBeforeCreate,
    triggerOnValidate,
    triggerOnSave,
    triggerOnError,
    triggerOnChange,
    triggerButton,
    triggerOnRowAdd,
    triggerOnRowRemove,
    setupFormScript,
    triggerOnCreateLead,
    triggerConvertToDeal,
    setFieldHtml,
  }
}
