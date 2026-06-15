import { defineStore } from 'pinia'
import { createResource } from 'frappe-ui'
import { reactive, ref } from 'vue'

export const viewsStore = defineStore('crm-views', (doctype) => {
  if (typeof doctype !== 'string') {
    doctype = null
  }

  let viewsByName = reactive({})
  let pinnedViews = ref([])
  let publicViews = ref([])
  let standardViews = ref({})
  const defaultView = ref(null)

  // Views
  const views = createResource({
    url: 'crm.api.views.get_views',
    params: { doctype: doctype || '' },
    cache: 'crm-views',
    initialData: [],
    auto: true,
    transform(views) {
      pinnedViews.value = []
      publicViews.value = []
      defaultView.value = null
      for (let view of views) {
        viewsByName[view.name] = view
        view.type = view.type || 'list'
        if (view.pinned) {
          pinnedViews.value?.push(view)
        }
        if (view.public) {
          publicViews.value?.push(view)
        }
        if (view.is_standard && view.dt) {
          const key = view.dt + ' ' + view.type
          const existing = standardViews.value[key]
          // A global (user-less) standard view is the Administrator-defined
          // default and overrides any personal standard view for the same
          // doctype+type. Personal standard views only apply when no global
          // one exists.
          if (!existing || !view.user) {
            standardViews.value[key] = view
          }
        }
        if (view.is_default) {
          defaultView.value = view
        }
      }
      return views
    },
  })

  function getDefaultView() {
    return defaultView.value
  }

  function getView(view, type, doctype = null) {
    type = type || 'list'
    if (!view && doctype) {
      return standardViews.value[doctype + ' ' + type] || null
    }
    return viewsByName[view]
  }

  function getPinnedViews() {
    if (!pinnedViews.value?.length) return []
    return pinnedViews.value
  }

  function getPublicViews() {
    if (!publicViews.value?.length) return []
    return publicViews.value
  }

  async function reload() {
    await views.reload()
  }

  return {
    views,
    defaultView,
    standardViews,
    getDefaultView,
    getPinnedViews,
    getPublicViews,
    reload,
    getView,
  }
})
