import { defineConfig } from 'vitepress'

// The site is served from https://gslama12.github.io/todooit/, so every
// generated asset and link has to carry the repo name in front of it.
const base = '/todooit/'

export default defineConfig({
  base,
  lang: 'en-US',
  title: 'todooit',
  description:
    'A keyboard-driven TUI todo manager: a dooit fork with Todoist habits.',
  lastUpdated: true,
  cleanUrls: true,
  head: [['link', { rel: 'icon', href: `${base}favicon.svg` }]],

  themeConfig: {
    search: {
      provider: 'local',
    },

    nav: [
      { text: 'Guide', link: '/guide/installation' },
      { text: 'Keybindings', link: '/guide/keybindings' },
      { text: 'Reference', link: '/reference/cli' },
      { text: 'GitHub', link: 'https://github.com/gslama12/todooit' },
    ],

    sidebar: [
      {
        text: 'Guide',
        items: [
          { text: 'Installation', link: '/guide/installation' },
          { text: 'Getting started', link: '/guide/getting-started' },
          { text: 'Projects & panes', link: '/guide/projects' },
          { text: 'Tasks', link: '/guide/tasks' },
          { text: 'Dates & recurrence', link: '/guide/dates' },
          { text: 'Quick add', link: '/guide/quick-add' },
          { text: 'Notes', link: '/guide/notes' },
          { text: 'Vim editing', link: '/guide/vim' },
          { text: 'Search, flash & move', link: '/guide/search-move' },
          { text: 'Undo & the Bin', link: '/guide/undo-bin' },
          { text: 'Keybindings', link: '/guide/keybindings' },
        ],
      },
      {
        text: 'Reference',
        items: [
          { text: 'CLI', link: '/reference/cli' },
          { text: 'Configuration', link: '/reference/configuration' },
          { text: 'Data & files', link: '/reference/data' },
          { text: 'Development', link: '/reference/development' },
        ],
      },
    ],

    socialLinks: [
      { icon: 'github', link: 'https://github.com/gslama12/todooit' },
    ],

    editLink: {
      pattern:
        'https://github.com/gslama12/todooit/edit/main/site/docs/:path',
      text: 'Edit this page on GitHub',
    },

    outline: [2, 3],

    footer: {
      message: 'MIT licensed. Based on dooit and dooit-extras.',
      copyright: 'Copyright © Georg Slamanig',
    },
  },
})
