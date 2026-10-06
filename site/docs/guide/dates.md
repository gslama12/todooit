# Dates & recurrence

A task carries two dates:

- **Scheduled** (`s`) — the day you plan to work on it. Today and Upcoming are
  built on this one.
- **Due** (`d`) — the deadline.

Both are typed as words and read the same way.

::: tip A task's day is a floor for its steps
Planning a task moves its unplanned and earlier steps onto that day; steps may
be planned later, and planning one earlier moves the task back with it. Due
dates cascade nowhere — see
[Steps](/guide/tasks#a-tasks-day-is-the-earliest-its-steps-start).
:::

## What you can type

| Typed | Means |
| --- | --- |
| `today`, `tod` | today |
| `tom`, `tmr`, `tmrw`, `tmw`, `tomorrow` | tomorrow |
| `yesterday`, `yest`, `yd` | yesterday |
| `friday`, `fri` | the coming friday (today counts) |
| `next monday` | a week on from the coming monday |
| `next week` | the monday that starts next week |
| `next month`, `next year` | the 1st of it |
| `weekend` | the coming saturday |
| `weekday` | the next working day |
| `end of month`, `eom` | the last working day of this month (no weekend, no Austrian holiday); next month's once that has passed |
| `someday` | two months out |
| `mid july` | the 15th |
| `3d`, `2w`, `1mo`, `1y`, `+5d` | an offset from today |
| `2h`, `30m` | an offset from the clock, right now |
| `in 2 weeks`, `in three days` | the same, spelled out |
| `19.07.`, `5.9`, `19.07.26` | day first, German style; the year may be left off |
| `2026-09-05` | ISO |
| `tom 16:00`, `friday at 4:30pm` | a date and a time |
| `friday evening` | 19:00 — also `morning` 9, `noon`/`afternoon` 12, `night` 22 |
| `none`, `never`, `no date`, `-` | clear the date |

::: warning Watch out for two things
In a date field `m` is **minutes**, not months — months are `mo`. (The
[recurrence](#recurrence) field has no minutes, so there `m` *is* a month.)
And `1600` is not a time: write `16:00`, or `16h` means sixteen hours
from now.
:::

## How dates are drawn

`Sa, 19.09.26`, with the time in parentheses when it is not midnight. A date
that falls today shows a bold red **Today** instead.

The color is the lead time: green when the task is done, red today or overdue,
yellow within five working days, plain white beyond that. A calendar icon sits
in front, and a different one once the date has passed.

## The calendar picker

Type `cal` into either date field and a month opens over the app.

![The calendar picker](/screenshots/calendar.svg)

| Key | What it does |
| --- | --- |
| `j` / `ö` (or `←` / `→`) | A day back / forward |
| `k` / `l` (or `↑` / `↓`) | A week back / forward |
| `J` / `Ö` (or `PgUp` / `PgDn`) | A month back / forward |

The direction keys are whatever the panes move with, so a
[vim layout](/guide/keybindings#vim-layouts) turns these into `h` `j` `k` `l`
and `H` / `L`.
| `t` | Back to today |
| `enter` | Pick the day |
| `escape` | Close the month, leaving the field mid-edit |

Weeks start on Monday, the names are Austrian German, and the thirteen
Austrian public holidays are drawn in red. A time the task already carried is
kept.

## Recurrence

`r` sets an interval: a number and a unit.

| Typed | Repeats |
| --- | --- |
| `2h` | every two hours |
| `3d` | every three days |
| `2w` | every two weeks |
| `1m`, `1mo` | every month, on the same day of the month |
| `1y` | every year |
| `eom` | on the last working day of every month |

There are no minutes, so `m` is a month. Months and years are calendar steps:
a monthly task on the 31st lands on the last day of a shorter month (28 Feb,
30 Apr) and goes back to the 31st where the month has one. `eom` skips
weekends and Austrian public holidays, so it is the last day anything can
actually be done that month.

A recurring task repeats on its **scheduled** date, not its due date. Setting a
recurrence on a task that had a due date moves that date over to become the
first occurrence (a task with neither date starts today), and giving a
recurring task a due date is refused with a warning. Ticking the task off moves the scheduled date on by the
interval and hands the task back, still pending, with every step under it
un-ticked and moved up to the new date if it was planned earlier. The row
flashes and the status bar names the new day ("advanced to Tue 7 Oct").

A step can recur on its own inside a task that doesn't; ticking it moves only
the step on.

Only one task on any line of a family recurs. Giving a task a recurrence ends
the recurrence of every step under it, and the status bar says so
("recurrence ended on 2 steps"). Giving one to a step whose parent (or any
task above it) already recurs, or has a due date, is refused with a warning
and the step keeps its old value.
A task filed under such a step or task with `I` isn't refused: it just stops
repeating (see [Becoming a step](/guide/tasks#becoming-a-step-is-never-refused)).
