#!/usr/bin/env bash
# Commit what is in the worktree you are standing in and land it on dev.
# Run under WSL, from inside the worktree.
#
#   cd <repo>.git/feat-xy && bash push.sh
#
#   1. stages everything and shows you the status
#   2. asks for a commit message and commits
#   3. brings local dev level with origin/dev and merges dev into this branch,
#      so conflicts surface here, in your own branch
#   4. shows what would land, asks, then fast-forwards dev onto this branch and
#      pushes dev - the feature branch itself never leaves your machine
#
# On conflicts it stops and lists them: resolve, commit, run push.sh again.
# Nothing is cleaned up here; clean.sh still removes worktrees and branches.
set -euo pipefail

if [ -t 1 ]; then
  DIM=$'\e[2m'; RED=$'\e[31m'; OFF=$'\e[0m'
else
  DIM='' RED='' OFF=''
fi
say()  { printf '\n  %s%s%s\n' "$DIM" "$*" "$OFF"; }
die()  { printf '\n  %s%s%s\n\n' "$RED" "$*" "$OFF" >&2; exit 1; }

wt="$(git rev-parse --show-toplevel 2>/dev/null)" ||
  die "not inside a worktree - cd into one and run push.sh there"
cd "$wt"

branch="$(git branch --show-current)"
[ -n "$branch" ] || die "detached HEAD in $(basename "$wt") - nothing to push"

# This repo was created without a fetch refspec, so origin/dev never existed and
# the old script had to merge FETCH_HEAD. Add it once, then talk about origin/dev.
git config --get remote.origin.fetch >/dev/null ||
  git config remote.origin.fetch '+refs/heads/*:refs/remotes/origin/*'

# Stage everything, show it, commit it.
commit_all() {
  git add -A
  if git diff --cached --quiet; then
    say "nothing to commit"
  else
    echo
    git status --short
    echo
    read -rp "  commit message: " msg
    [ -n "$msg" ] || die "empty message - nothing committed, changes left staged"
    git commit -q -m "$msg"
    say "committed"
  fi
}

# Merge $1 into the current branch, or stop and hand the conflicts over.
merge_or_stop() {
  git merge --no-edit "$1" && return 0
  printf '\n  %sconflicts:%s\n' "$RED" "$OFF"
  git diff --name-only --diff-filter=U | sed 's/^/    /'
  printf '\n  %sresolve them, then: git add <files> && git commit && bash push.sh%s\n\n'     "$DIM" "$OFF"
  exit 1
}

# What a push would change: $1 = where the remote is, $2 = what we would send.
show_diffstat() {
  git rev-parse --verify --quiet "$1" >/dev/null || return 0
  local stat
  stat="$(git diff --stat --stat-count=25 "$1" "$2")"
  [ -n "$stat" ] || return 0
  echo
  echo "$stat" | sed 's/^/    /'
}

fetch_dev() {
  say "fetching origin/dev"
  git fetch --quiet origin '+refs/heads/dev:refs/remotes/origin/dev'
}

say "$(basename "$wt")  (branch $branch)"

# dev and main are merged into, never landed from: same shape, both take dev.
if [ "$branch" = dev ] || [ "$branch" = main ]; then
  if [ "$branch" = main ]; then
    read -rp "  you are on main: merge origin/dev into it and push? [y/N] " reply
    case "$reply" in [yY]*) ;; *) say "aborted"; exit 0 ;; esac
  fi
  commit_all
  fetch_dev
  merge_or_stop origin/dev
  git fetch --quiet origin "+refs/heads/$branch:refs/remotes/origin/$branch" 2>/dev/null || true
  show_diffstat "origin/$branch" HEAD
  echo
  read -rp "  push $branch to origin? [y/N] " reply
  case "$reply" in
    [yY]*) git push origin "$branch"; say "pushed $branch" ;;
    *)     say "not pushed - merge is committed locally" ;;
  esac
  exit 0
fi

# A feature branch: it lands on dev from here, no pull request.
dev_wt="$(git worktree list --porcelain | awk '
  /^worktree /              { p = substr($0, 10) }
  /^branch refs\/heads\/dev$/ { print p; exit }')"
[ -n "$dev_wt" ] || die "no worktree holds dev - expected one at $(dirname "$wt")/dev"

git -C "$dev_wt" diff --quiet && git -C "$dev_wt" diff --cached --quiet ||
  die "the dev worktree has uncommitted changes - sort them out in $dev_wt first"

commit_all

# Level dev with the remote, then merge it into this branch. Both halves of a
# conflict live here; dev is never left half-merged.
land() {
  fetch_dev
  git -C "$dev_wt" merge --ff-only --quiet origin/dev ||
    die "local dev has commits that are not on origin/dev - sort that out in $dev_wt"
  merge_or_stop dev
}
land

count="$(git rev-list --count dev.."$branch")"
[ "$count" -gt 0 ] || { say "nothing to land - dev already has $branch"; exit 0; }

echo
git log --oneline dev.."$branch" | sed 's/^/    /'
show_diffstat dev "$branch"
echo
read -rp "  land $count commit(s) on dev and push? [y/N] " reply
case "$reply" in [yY]*) ;; *) say "not landed - your branch is committed locally"; exit 0 ;; esac

# dev now contains nothing this branch lacks, so it can only fast-forward. If
# anything below fails, dev is put back where it was and re-running is safe.
for attempt in 1 2; do
  dev_before="$(git -C "$dev_wt" rev-parse HEAD)"
  git -C "$dev_wt" merge --ff-only --quiet "$branch" ||
    die "dev could not fast-forward onto $branch - nothing changed"
  if git -C "$dev_wt" push origin dev; then
    say "landed $branch on dev ($(git -C "$dev_wt" rev-parse --short HEAD))"
    exit 0
  fi
  git -C "$dev_wt" reset --hard --quiet "$dev_before"
  [ "$attempt" = 1 ] || break
  say "origin/dev moved while we were merging - merging again"
  land
done
die "could not push dev - it is back where it was, run push.sh again"
