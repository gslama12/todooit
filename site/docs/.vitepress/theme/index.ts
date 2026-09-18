// The default VitePress theme, plus the one component the home page needs.
//
// Registering it globally is what lets `<FeatureCarousel />` be written
// straight into docs/index.md, which keeps the home page a markdown file
// rather than a custom layout.

import DefaultTheme from 'vitepress/theme'
import type { Theme } from 'vitepress'

import FeatureCarousel from './FeatureCarousel.vue'

export default {
  extends: DefaultTheme,
  enhanceApp({ app }) {
    app.component('FeatureCarousel', FeatureCarousel)
  },
} satisfies Theme
