import { createResource } from 'frappe-ui'
import { noValueFieldTypes, standardFieldsMeta } from '@/utils/model.js'
import { formatCurrency, formatNumber } from '@/utils/numberFormat.js'
import { computed, reactive, ref, toRaw } from 'vue'

const doctypesMeta = reactive({})
const userSettings = reactive({})

// One getMeta() API object per doctype, for the app's lifetime.
//
// This used to build a fresh `createResource` on EVERY call, and getMeta() is
// called from component setup(). A kanban card mounts one KanbanCardField per
// field, so a 287-card board constructed ~2,000 resource objects for a single
// doctype on every render.
const metaCache = new Map()

// Bumped whenever a doctype's meta lands. getFields() reads this instead of
// walking the reactive `doctypesMeta` proxy, so a caller inside a computed takes
// exactly ONE reactive dependency rather than one per field it touches.
const metaVersion = ref(0)

// Derived field lists, keyed by doctype + options. Dropped for a doctype when
// its meta is (re)loaded.
const fieldsCache = new Map()

function fieldsCacheKey(dt, opts) {
  return [
    dt,
    opts.withStandardFields ? 1 : 0,
    opts.restrictNoValueFields ? 1 : 0,
    (opts.restrictedFieldTypes || []).join('|'),
  ].join('::')
}

export function getMeta(doctype) {
  if (!metaCache.has(doctype)) {
    metaCache.set(doctype, buildMeta(doctype))
  }
  const api = metaCache.get(doctype)
  // Preserved from the original: ask for the meta the first time anyone wants
  // this doctype (and again if an earlier fetch failed and left nothing behind).
  if (!doctypesMeta[doctype] && !api.meta.loading) {
    api.meta.fetch()
  }
  return api
}

function buildMeta(doctype) {
  const meta = createResource({
    url: 'frappe.desk.form.load.getdoctype',
    params: {
      doctype: doctype,
      with_parent: 1,
      cached_timestamp: null,
    },
    cache: ['Meta', doctype],
    onSuccess: (res) => {
      let dtMetas = res.docs
      for (let dtMeta of dtMetas) {
        doctypesMeta[dtMeta.name] = dtMeta
        // A doctype's derived field lists are stale the moment its meta changes.
        for (const key of [...fieldsCache.keys()]) {
          if (key.startsWith(dtMeta.name + '::')) fieldsCache.delete(key)
        }
      }

      userSettings[doctype] = JSON.parse(res.user_settings)
      metaVersion.value++
    },
  })

  const doctypeMeta = computed(() => doctypesMeta[doctype] || null)

  function getFormattedPercent(fieldname, doc) {
    let value = getFormattedFloat(fieldname, doc)
    return value + '%'
  }

  function getFormattedFloat(fieldname, doc) {
    let df = doctypesMeta[doctype]?.fields.find((f) => f.fieldname == fieldname)
    let precision = df?.precision || null
    return formatNumber(doc[fieldname], '', precision)
  }

  function getFloatWithPrecision(fieldname, doc) {
    let df = doctypesMeta[doctype]?.fields.find((f) => f.fieldname == fieldname)
    let precision = df?.precision || null
    return formatNumber(doc[fieldname], '', precision)
  }

  function getCurrencyWithPrecision(fieldname, doc) {
    let df = doctypesMeta[doctype]?.fields.find((f) => f.fieldname == fieldname)
    // whole-dollar display by default (Acq/Dispo prices etc.) — a docfield can
    // still opt into decimals with an explicit precision
    let precision = df?.precision || 0
    return formatCurrency(doc[fieldname], '', '', precision)
  }

  function getFormattedCurrency(fieldname, doc, parentDoc = null) {
    let currency = window.sysdefaults.currency || 'USD'
    let df = doctypesMeta[doctype]?.fields.find((f) => f.fieldname == fieldname)
    // whole-dollar display by default (Acq/Dispo prices etc.) — a docfield can
    // still opt into decimals with an explicit precision
    let precision = df?.precision || 0

    if (df && df.options) {
      if (df.options.indexOf(':') != -1) {
        // TODO: Handle this case
      } else if (doc && doc[df.options]) {
        currency = doc[df.options]
      } else if (parentDoc && parentDoc[df.options]) {
        currency = parentDoc[df.options]
      }
    }

    return formatCurrency(doc[fieldname], '', currency, precision)
  }

  function getGridSettings() {
    return doctypeMeta.value || {}
  }

  function getGridViewSettings(parentDoctype) {
    if (!userSettings[parentDoctype]?.['GridView']?.[doctype]) return {}
    return userSettings[parentDoctype]['GridView'][doctype]
  }

  // Derive the display field list for a doctype.
  //
  // Three things here are load-bearing for performance, and all three used to be
  // the other way round:
  //
  //  1. The result is CACHED per (doctype, options). This ran ~2,000 times per
  //     kanban render — once per KanbanCardField's `fieldMeta` computed — each
  //     time filtering and mapping all 138 CRM Lead fields.
  //  2. It reads the RAW meta (toRaw), not the reactive proxy. Walking 138
  //     fields through a reactive proxy inside a computed costs a Proxy get-trap
  //     per property AND registers a dependency link per property, so ~2,000
  //     computeds were wiring up ~276,000 dependencies on every render.
  //     `metaVersion` gives each caller a single dependency instead.
  //  3. It never MUTATES the stored field objects. The old code assigned
  //     `f.fieldtype = 'User'` on every call — a write into shared reactive
  //     state that all ~2,000 computeds had just subscribed to, i.e. an O(n^2)
  //     invalidation storm, and the reason board render time grew
  //     quadratically. Fields needing a reshape are shallow-copied once, here.
  function getFields(options = {}) {
    let {
      dt = doctype,
      withStandardFields = false,
      restrictNoValueFields = true,
      restrictedFieldTypes = [],
    } = options

    // The single reactive dependency: re-derive when a doctype's meta lands.
    metaVersion.value

    const key = fieldsCacheKey(dt, {
      withStandardFields,
      restrictNoValueFields,
      restrictedFieldTypes,
    })
    let fieldsMeta = fieldsCache.get(key)

    if (!fieldsMeta) {
      const rawMeta = toRaw(doctypesMeta[dt])
      const rawFields = rawMeta ? toRaw(rawMeta.fields) : null

      fieldsMeta =
        rawFields
          ?.filter(
            (f) =>
              !f.hidden &&
              (!restrictNoValueFields ||
                !noValueFieldTypes.includes(f.fieldtype)) &&
              (!restrictedFieldTypes.length ||
                !restrictedFieldTypes.includes(f.fieldtype)),
          )
          .map((f) => {
            if (f.fieldtype === 'Select' && typeof f.options === 'string') {
              const opts = f.options.split('\n').map((option) => {
                return {
                  label: option,
                  value: option,
                }
              })

              if (opts[0]?.value !== '' && f.reqd !== 1) {
                opts.unshift({
                  label: '',
                  value: '',
                })
              }
              return { ...f, options: opts }
            }
            if (f.fieldtype === 'Link' && f.options == 'User') {
              return { ...f, fieldtype: 'User' }
            }
            return f
          }) || []

      if (withStandardFields) {
        fieldsMeta = fieldsMeta.concat(standardFieldsMeta)
      }

      // Don't cache an empty derivation — that just means the meta hasn't
      // arrived yet, and `metaVersion` won't change for a doctype nobody has
      // fetched.
      if (rawFields) fieldsCache.set(key, fieldsMeta)
    }

    // Hand back a fresh array (sharing the field objects) so a caller that sorts
    // or splices its copy can't corrupt everyone else's — as before.
    return fieldsMeta.slice()
  }

  function saveUserSettings(parentDoctype, key, value, callback) {
    let oldUserSettings = userSettings[parentDoctype] || {}
    let newUserSettings = JSON.parse(JSON.stringify(oldUserSettings))

    if (newUserSettings[key] === undefined) {
      newUserSettings[key] = { [doctype]: value }
    } else {
      newUserSettings[key][doctype] = value
    }

    if (JSON.stringify(oldUserSettings) !== JSON.stringify(newUserSettings)) {
      return createResource({
        url: 'frappe.model.utils.user_settings.save',
        params: {
          doctype: parentDoctype,
          user_settings: JSON.stringify(newUserSettings),
        },
        auto: true,
        onSuccess: () => {
          userSettings[parentDoctype] = newUserSettings
          callback?.()
        },
      })
    }
    userSettings[parentDoctype] = newUserSettings
    return callback?.()
  }

  function isTranslatable(dt = null) {
    dt = dt || doctype
    let meta = doctypesMeta[dt]
    return meta && meta.translated_doctype
  }

  return {
    meta,
    doctypeMeta,
    doctypesMeta,
    userSettings,
    getFields,
    getGridSettings,
    getGridViewSettings,
    saveUserSettings,
    getFloatWithPrecision,
    getCurrencyWithPrecision,
    getFormattedFloat,
    getFormattedPercent,
    getFormattedCurrency,
    isTranslatable,
  }
}
