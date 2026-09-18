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
    title: 'Projects that nest',
    details:
      'Projects hold projects. The <em>Tasks</em> column counts everything underneath at every level, and a color put on a project spreads down the whole tree.',
    link: '/guide/projects',
    shot: 'nested-projects.svg',
    alt: 'Projects nested under projects in the left pane',
  },
  {
    title: 'Steps under tasks',
    details:
      'Tasks nest the way projects do. <kbd>h</kbd> folds one shut, and planning a task plans every step of it — date a single step instead and the task gives up its own day, because it no longer happens all at once.',
    link: '/guide/tasks#steps',
    shot: 'child-tasks.svg',
    alt: 'Tasks nested under tasks',
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
    title: 'Dates in words',
    details:
      '<code>tom</code>, <code>next monday</code>, <code>in 2w</code>, <code>19.07.</code> — or type <code>cal</code> in a date field for a month to pick from, Austrian public holidays marked.',
    link: '/guide/dates',
    shot: 'calendar.svg',
    alt: 'The calendar picker open over the app',
  },
  {
    title: 'Recurrence',
    details:
      '<kbd>r</kbd> sets an interval — <code>3d</code>, <code>4w</code>. Ticking a repeating task moves it on by that interval and hands it straight back, still pending. It is never finished, only done for now.',
    link: '/guide/dates#recurrence',
    shot: 'upcoming.svg',
    alt: 'The Upcoming pane, grouped by day',
  },
  {
    title: 'Notes in markdown',
    details:
      '<kbd>space</kbd> opens a note. Bullets, quotes, headings and emphasis are drawn as you type them, so there are no formatting keys to learn.',
    link: '/guide/notes',
    shot: 'note.svg',
    alt: 'A note with headings, bullets and a quote',
  },
  {
    title: 'A note pinned to nothing',
    details:
      '<kbd>m</kbd> opens a scratchpad that belongs to no task and no project. It is always where you left it — the place for the thing that has not become work yet.',
    link: '/guide/notes#the-pinned-note',
    shot: 'pinned-note.svg',
    alt: 'The pinned note',
  },
  {
    title: 'Sorting and arranging',
    details:
      '<kbd>SP</kbd> <kbd>SD</kbd> <kbd>SS</kbd> sort by priority, due date or scheduled date. Move a row by hand with <kbd>K</kbd> / <kbd>L</kbd> and the pane drops out of the sort, so it stays where you put it.',
    link: '/guide/projects#sorting-view',
    shot: 'sort.svg',
    alt: 'Tasks sorted by due date',
  },
  {
    title: 'The finder',
    details:
      '<kbd>/</kbd> searches every task in the database rather than the pane in front — any project, done or not — then walks the cursor over to the one you pick.',
    link: '/guide/search-move#finder',
    shot: 'search.svg',
    alt: 'The finder, matching across projects',
  },
  {
    title: 'Move between projects',
    details:
      '<kbd>M</kbd> asks for one thing: the project to file the task under, completed from the first letter. Write a path — <code>Home/Reading</code> — when a name on its own is not enough.',
    link: '/guide/search-move#move',
    shot: 'move.svg',
    alt: 'The move prompt completing a project name',
  },
  {
    title: 'The agent flag',
    details:
      '<kbd>a</kbd> marks a task as handed to an AI that is off working on it: an hourglass in a column of its own. It says nothing about whether the task is done.',
    link: '/guide/tasks#marking',
    shot: 'workspace.svg',
    alt: 'The workspace, with the agent column',
  },
  {
    title: 'Clipboard, both ways',
    details:
      '<kbd>ctrl+c</kbd> copies a description, <kbd>ctrl+n</kbd> a whole note without opening it, <kbd>ctrl+v</kbd> pastes a new task. Copying goes out through OSC 52 as well, so it carries out of ssh and out of WSL.',
    link: '/guide/search-move#clipboard',
    shot: 'workspace.svg',
    alt: 'The workspace, with the Note column',
  },
  {
    title: 'Links, opened from the row',
    details:
      '<kbd>o</kbd> opens the first link written in a row, or the one under the cursor inside a note. A long address is folded away behind its name when it is drawn.',
    link: '/guide/tasks#links',
    shot: 'note.svg',
    alt: 'A markdown link inside a note',
  },
  {
    title: 'Undo, and the Bin',
    details:
      '<kbd>xx</kbd> throws work away rather than deleting it and <kbd>u</kbd> fetches it back, carrying the path it came from. <kbd>ctrl+z</kbd> / <kbd>ctrl+y</kbd> walk through everything else.',
    link: '/guide/undo-bin',
    shot: 'bin.svg',
    alt: 'The Bin, holding thrown-away tasks',
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
