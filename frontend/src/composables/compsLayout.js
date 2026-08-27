import { ref } from 'vue'

/**
 * Layout prefs the comps map exposes outside itself: the command palette
 * needs to toggle "full map" without importing CompsView, and a second
 * mounted map (Today, practice, the page) must not clobber the first's
 * unmount.
 */
export const compsViewCount = ref(0)

export const compsFocusMap = ref(
  typeof localStorage !== 'undefined' && localStorage.getItem('compsFocusMap') === '1',
)

export function toggleCompsFocusMap() {
  compsFocusMap.value = !compsFocusMap.value
  localStorage.setItem('compsFocusMap', compsFocusMap.value ? '1' : '0')
}
