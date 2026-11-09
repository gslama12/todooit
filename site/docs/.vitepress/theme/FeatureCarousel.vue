<script setup lang="ts">
// The feature carousel on the home page.
//
// The home page used to list four features in VitePress's own grid, which
// meant picking four out of everything the app does. A carousel holds the lot
// without turning the page into a wall: one feature at a time, each with the
// screenshot that shows it and a way into the part of the guide that explains
// it.
//
// Only the slide on show is mounted. The screenshots are a couple of hundred
// kilobytes of SVG each, so a track holding all of them at once would pull
// down several megabytes before the reader had asked for any of it.

import { computed, ref } from 'vue'
import { withBase } from 'vitepress'

interface Feature {
  title: string
  /** Rendered as HTML, so a key can be drawn as a key */
  details: string
  /** Where in the guide this feature is written up */
  link: string
  /** A file in docs/public/screenshots */
  shot: string
  alt: string
}

const features: Feature[] = [
  {
    title: 'The four fixed panes',
    details:
      'Today, Upcoming, Completed and the Bin are built out of your real projects every time they are drawn. <kbd>gt</kbd> <kbd>gu</kbd> <kbd>gc</kbd> <kbd>gb</kbd> jump to them, and <kbd>gi</kbd> walks back to where a task actually lives.',
    link: '/guide/projects#the-four-fixed-projects',
    shot: 'today.svg',
    alt: 'The Today pane, a block per project',
  },
  {
    title: 'Projects and tasks that nest',
    details:
      'Projects hold projects and tasks hold tasks, as deep as you like. <kbd>h</kbd> folds one shut, <kbd>I</kbd> / <kbd>U</kbd> indent and unindent. A task&rsquo;s dates hold its steps: planning a task plans its steps, and no step is due after its task.',
    link: '/guide/tasks#steps',
    shot: 'child-tasks.svg',
    alt: 'Tasks nested under tasks',
  },
  {
    title: 'Dates in words',
    details:
      '<kbd>s</kbd> scheduled, <kbd>d</kbd> due: <code>tom</code>, <code>next monday</code>, <code>in 2w</code>, <code>eom</code>, <code>19.07.</code> — or type <code>cal</code> in a date field for a month to pick from, public holidays marked.',
    link: '/guide/dates',
    shot: 'calendar.svg',
    alt: 'The calendar picker open over the app',
  },
  {
    title: 'Smart recurrence',
    details:
      '<kbd>r</kbd> sets an interval — <code>3d</code>, <code>2w</code>, <code>1m</code>, or <code>eom</code> for the last working day of every month. Ticking a repeating task moves it on and hands it straight back, steps reset.',
    link: '/guide/dates#recurrence',
    shot: 'upcoming.svg',
    alt: 'The Upcoming pane, grouped by day',
  },
  {
    title: 'Flash jumps',
    details:
      '<kbd>f</kbd> puts a label on every row on screen; type one and the cursor is there. No counting, no scrolling. Inside a note, <kbd>s</kbd> does the same for any text.',
    link: '/guide/search-move#flash',
    shot: 'flash.svg',
    alt: 'Flash labels on every row of the tasks pane',
  },
  {
    title: 'Quick add',
    details:
      '<kbd>C</kbd>, then one line: <code>call the dentist #Home p1 tomorrow 09:00</code>. Project, priority and day are read out of it as you type.',
    link: '/guide/quick-add',
    shot: 'quick-add.svg',
    alt: 'The quick add line, with its legend',
  },
  {
    title: 'Markdown notes',
    details:
      '<kbd>space</kbd> opens a note. Bullets, numbered lists that renumber themselves, quotes, headings and emphasis are drawn as you type them, and the note is stored as plain markdown.',
    link: '/guide/notes',
    shot: 'note.svg',
    alt: 'A note with headings, bullets and a quote',
  },
  {
    title: 'Vim in notes and descriptions',
    details:
      'Motions, operators, text objects, VISUAL, search and replace, undo — in every note. <kbd>e</kbd> edits a task&rsquo;s description with the same keys. <kbd>space</kbd> <kbd>?</kbd> lists them all.',
    link: '/guide/vim',
    shot: 'note-help.svg',
    alt: 'The list of a note’s vim keys',
  },
  {
    title: 'Files attached to notes',
    details:
      'Copy a file anywhere and <kbd>ctrl+v</kbd> it into a note: it is pinned to the strip along the bottom, by path, never copied. <kbd>gf</kbd> picks one to open.',
    link: '/guide/notes#attachments',
    shot: 'attachments.svg',
    alt: 'Files in the strip along the bottom of a note',
  },
  {
    title: 'The finder',
    details:
      '<kbd>/</kbd> searches every task in the database rather than the pane in front, then walks the cursor over to the one you pick. Start with <code>&gt;</code> to search inside notes.',
    link: '/guide/search-move#finder',
    shot: 'search-notes.svg',
    alt: 'The finder, matching inside notes',
  },
  {
    title: 'A note pinned to nothing',
    details:
      '<kbd>m</kbd> opens a scratchpad that belongs to no task and no project — the place for the thing that has not become work yet.',
    link: '/guide/notes#the-pinned-note',
    shot: 'pinned-note.svg',
    alt: 'The pinned note',
  },
  {
    title: 'Sorting and moving',
    details:
      '<kbd>SP</kbd> <kbd>SD</kbd> <kbd>SS</kbd> sort by priority, due or scheduled date. <kbd>K</kbd> / <kbd>L</kbd> shift a row, <kbd>M</kbd> files a task under another project.',
    link: '/guide/search-move#move',
    shot: 'move.svg',
    alt: 'The move prompt completing a project name',
  },
  {
    title: 'Undo, the Bin and the clipboard',
    details:
      '<kbd>xx</kbd> throws work into the Bin and <kbd>R</kbd> fetches it back. <kbd>u</kbd> / <kbd>ctrl+r</kbd> undo and redo anything. <kbd>ctrl+c</kbd> / <kbd>ctrl+v</kbd> copy and paste tasks through the system clipboard.',
    link: '/guide/undo-bin',
    shot: 'bin.svg',
    alt: 'The Bin, holding thrown-away tasks',
  },
  {
    title: 'Every key, one press away',
    details:
      '<kbd>?</kbd> lists every binding, grouped and always matching your config. Drop-in configs switch to standard vim keys on QWERTY or QWERTZ.',
    link: '/guide/keybindings',
    shot: 'help.svg',
    alt: 'The help screen listing every key',
  },
]

const count = features.length
const index = ref(0)
const back = ref(false)
const current = computed(() => features[index.value])
const transition = computed(() => (back.value ? 'fc-back' : 'fc-forward'))

function go(to: number, backwards = to < index.value) {
  back.value = backwards
  // Wraps both ways, so neither arrow is ever a dead end
  index.value = (to + count) % count
}

const next = () => go(index.value + 1, false)
const prev = () => go(index.value - 1, true)

function onKey(event: KeyboardEvent) {
  // Only while the carousel itself has focus, so the arrow keys still belong
  // to the page everywhere else
  if (event.key === 'ArrowRight') {
    next()
  } else if (event.key === 'ArrowLeft') {
    prev()
  } else {
    return
  }

  event.preventDefault()
}

// A swipe, for the phone layout where there is no room for the arrows to be
// obvious
let touchX = 0

function onTouchStart(event: TouchEvent) {
  touchX = event.changedTouches[0].screenX
}

function onTouchEnd(event: TouchEvent) {
  const travelled = event.changedTouches[0].screenX - touchX

  if (Math.abs(travelled) > 40) {
    if (travelled < 0) {
      next()
    } else {
      prev()
    }
  }
}
</script>

<template>
  <section
    class="fc"
    aria-roledescription="carousel"
    aria-label="What todooit does"
  >
    <header class="fc-head">
      <h2 class="fc-heading">What it does</h2>
      <p class="fc-sub">{{ count }} things, one at a time.</p>
    </header>

    <div class="fc-frame">
      <button
        class="fc-arrow"
        type="button"
        aria-label="Previous feature"
        @click="prev"
      >
        <svg viewBox="0 0 24 24" aria-hidden="true" width="22" height="22">
          <path
            d="M15 5l-7 7 7 7"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
          />
        </svg>
      </button>

      <div
        class="fc-viewport"
        tabindex="0"
        role="group"
        :aria-label="`${index + 1} of ${count}: ${current.title}`"
        @keydown="onKey"
        @touchstart.passive="onTouchStart"
        @touchend.passive="onTouchEnd"
      >
        <Transition :name="transition" mode="out-in">
          <article :key="index" class="fc-slide">
            <a
              class="fc-shot"
              :href="withBase(current.link)"
              tabindex="-1"
              aria-hidden="true"
            >
              <img
                :src="withBase(`/screenshots/${current.shot}`)"
                :alt="current.alt"
                loading="lazy"
                decoding="async"
              />
            </a>

            <div class="fc-body">
              <p class="fc-count">{{ index + 1 }} / {{ count }}</p>
              <h3 class="fc-title">{{ current.title }}</h3>
              <!-- Written just above, in this file -- nothing a reader can
                   type ever reaches it -->
              <p class="fc-details" v-html="current.details" />
              <a class="fc-link" :href="withBase(current.link)">
                Read the guide →
              </a>
            </div>
          </article>
        </Transition>
      </div>

      <button
        class="fc-arrow"
        type="button"
        aria-label="Next feature"
        @click="next"
      >
        <svg viewBox="0 0 24 24" aria-hidden="true" width="22" height="22">
          <path
            d="M9 5l7 7-7 7"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
          />
        </svg>
      </button>
    </div>

    <div class="fc-dots">
      <button
        v-for="(feature, i) in features"
        :key="feature.title"
        class="fc-dot"
        type="button"
        :class="{ 'is-on': i === index }"
        :aria-label="feature.title"
        :aria-current="i === index"
        @click="go(i)"
      />
    </div>
  </section>
</template>

<style scoped>
/* No width or padding of its own: it sits inside VitePress's own content
   container on the home page, so taking that container's full width is what
   lines the carousel up with the screenshot above it */
.fc {
  margin: 48px 0 0;
}

.fc-head {
  margin-bottom: 20px;
}

.fc-heading {
  font-size: 24px;
  font-weight: 700;
  letter-spacing: -0.02em;
  line-height: 1.3;
  margin: 0;
  padding: 0;
  border: 0;
}

.fc-sub {
  font-size: 14px;
  color: var(--vp-c-text-3);
  margin: 4px 0 0;
}

.fc-frame {
  display: flex;
  align-items: center;
  gap: 8px;
}

.fc-viewport {
  flex: 1;
  min-width: 0;
  border: 1px solid var(--vp-c-divider);
  border-radius: 12px;
  background: var(--vp-c-bg-soft);
  padding: 20px;
  overflow: hidden;
}

.fc-viewport:focus-visible {
  outline: 2px solid var(--vp-c-brand-1);
  outline-offset: 2px;
}

.fc-slide {
  display: grid;
  /* The screenshot is the point of the slide, so it takes the larger half */
  grid-template-columns: minmax(0, 1.25fr) minmax(0, 1fr);
  gap: 28px;
  align-items: center;
  /* Holds the frame still while one feature is replaced by a longer one */
  min-height: 260px;
}

.fc-shot {
  display: block;
  border-radius: 8px;
  overflow: hidden;
  line-height: 0;
  background: var(--vp-c-bg);
}

.fc-shot img {
  width: 100%;
  height: auto;
  display: block;
}

.fc-count {
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.06em;
  color: var(--vp-c-text-3);
  margin: 0 0 6px;
}

.fc-title {
  font-size: 22px;
  font-weight: 700;
  line-height: 1.3;
  letter-spacing: -0.01em;
  margin: 0 0 10px;
  padding: 0;
  border: 0;
}

.fc-details {
  font-size: 15px;
  line-height: 1.65;
  color: var(--vp-c-text-2);
  margin: 0 0 16px;
}

.fc-details :deep(kbd) {
  display: inline-block;
  padding: 1px 6px;
  border: 1px solid var(--vp-c-divider);
  border-bottom-width: 2px;
  border-radius: 5px;
  background: var(--vp-c-bg);
  font-family: var(--vp-font-family-mono);
  font-size: 12px;
  line-height: 1.6;
  color: var(--vp-c-text-1);
  white-space: nowrap;
}

.fc-details :deep(code) {
  font-size: 13px;
}

.fc-link {
  font-size: 14px;
  font-weight: 600;
  color: var(--vp-c-brand-1);
}

.fc-link:hover {
  color: var(--vp-c-brand-2);
}

.fc-arrow {
  flex: none;
  display: grid;
  place-items: center;
  width: 40px;
  height: 40px;
  border: 1px solid var(--vp-c-divider);
  border-radius: 50%;
  background: var(--vp-c-bg);
  color: var(--vp-c-text-2);
  transition: border-color 0.2s, color 0.2s, background-color 0.2s;
}

.fc-arrow:hover {
  border-color: var(--vp-c-brand-1);
  color: var(--vp-c-brand-1);
  background: var(--vp-c-bg-soft);
}

.fc-arrow:focus-visible {
  outline: 2px solid var(--vp-c-brand-1);
  outline-offset: 2px;
}

.fc-dots {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 8px;
  margin-top: 16px;
}

.fc-dot {
  width: 8px;
  height: 8px;
  padding: 0;
  border: 0;
  border-radius: 50%;
  background: var(--vp-c-divider);
  transition: background-color 0.2s, transform 0.2s;
}

.fc-dot:hover {
  background: var(--vp-c-text-3);
}

.fc-dot.is-on {
  background: var(--vp-c-brand-1);
  transform: scale(1.35);
}

.fc-dot:focus-visible {
  outline: 2px solid var(--vp-c-brand-1);
  outline-offset: 3px;
}

/* One slide out and the next in, from the side the reader asked for */
.fc-forward-enter-active,
.fc-forward-leave-active,
.fc-back-enter-active,
.fc-back-leave-active {
  transition: opacity 0.18s ease, transform 0.18s ease;
}

.fc-forward-enter-from {
  opacity: 0;
  transform: translateX(28px);
}

.fc-forward-leave-to {
  opacity: 0;
  transform: translateX(-28px);
}

.fc-back-enter-from {
  opacity: 0;
  transform: translateX(-28px);
}

.fc-back-leave-to {
  opacity: 0;
  transform: translateX(28px);
}

@media (max-width: 820px) {
  .fc {
    margin-top: 32px;
  }

  .fc-viewport {
    padding: 16px;
  }

  .fc-slide {
    grid-template-columns: minmax(0, 1fr);
    gap: 16px;
    min-height: 0;
  }

  .fc-arrow {
    width: 34px;
    height: 34px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .fc-forward-enter-active,
  .fc-forward-leave-active,
  .fc-back-enter-active,
  .fc-back-leave-active {
    transition: opacity 0.12s ease;
  }

  .fc-forward-enter-from,
  .fc-forward-leave-to,
  .fc-back-enter-from,
  .fc-back-leave-to {
    transform: none;
  }

  .fc-dot {
    transition: none;
  }
}
</style>
