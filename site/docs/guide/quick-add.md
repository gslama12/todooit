# Quick add

`C` opens a one-line prompt over the app. Type the task the way you would say
it; the markers below pick the fields out of it, and everything left is the
description.

![Quick add](/screenshots/quick-add.svg)

```
Call the dentist #Home p1 tomorrow 09:00
```

| Marker | Field | Notes |
| --- | --- | --- |
| `#name` | Project | `#"two words"` when the name has a space; `#Home/Reading` for a path |
| `p0`–`p3` | Priority | `p1` most urgent, `p3` least |
| a bare date | **Scheduled** | Any [date expression](/guide/dates) |
| `due=…` | Due | `due=friday`, `due=3w`, `due=next monday at 16:00` |

::: info Why the bare date is the scheduled one
A line that mentions a date means the day you plan to work on it — that is the
question there is a day-to-day answer to, and the one Today and Upcoming are
built on. The deadline is asked for by name.
:::

## Project completion

A half-typed `#name` is completed the way a filename is completed at a shell
prompt: as much of the name as every match agrees on, then one match at a
time. What is still possible is listed underneath.

## The rules

- One project and one deadline per line.
- The scan for the bare date works back from the end, so
  `friday standup notes tomorrow` is the friday standup notes, planned for
  tomorrow.
- Leading words go with the date: `call mum on friday` leaves `call mum`.
- `and`, `then` and `or` never belong to a date, so `buy milk tomorrow and
  eggs` keeps the eggs.
- A `due=` that cannot be read is an error. A bare date that cannot be read is
  just part of the description.
- A line with no description at all is refused.

## Where the task lands

With no `#name`, the task is filed in the project the cursor is already in. In
a fixed pane — Today, Upcoming, Completed, Bin — there is no such project, so
the line has to name one.

A `#name` that matches no project creates it. A name that matches more than
one is refused, with a nudge to write the path instead.
