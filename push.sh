#!/usr/bin/env bash
# Commit what is in the worktree you are standing in, bring it up to date with
# origin/dev, and push it. Run under WSL, from inside the worktree.
#
#   cd <repo>.git/feat-xy && bash push.sh
#
#   1. stages everything and shows you the status
#   2. asks for a commit message and commits
#   3. merges the current origin/dev into this branch
#   4. on a clean merge, asks before pushing; on conflicts it stops and lists
#      them, so you can resolve, commit and push yourself
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

if [ "$branch" = main ]; then
  read -rp "  you are on main: merge origin/dev into it and push? [y/N] " reply
  case "$reply" in [yY]*) ;; *) say "aborted"; exit 0 ;; esac
fi

say "$(basename "$wt")  (branch $branch)"

# 1 + 2 - stage everything, show it, commit it.
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

# 3 - merge in whatever origin/dev looks like right now.
say "fetching origin/dev"
git fetch --quiet origin dev
if ! git merge --no-edit FETCH_HEAD; then
  printf '\n  %sconflicts:%s\n' "$RED" "$OFF"
  git diff --name-only --diff-filter=U | sed 's/^/    /'
  printf '\n  %sresolve them, then: git add <files> && git commit && git push -u origin %s%s\n\n' \
    "$DIM" "$branch" "$OFF"
  exit 1
fi

# 4 - push, once you say so.
read -rp "  push $branch to origin? [y/N] " reply
case "$reply" in
  [yY]*) git push -u origin "$branch"; say "pushed $branch" ;;
  *)     say "not pushed - merge is committed locally" ;;
esac
