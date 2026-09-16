#!/usr/bin/env bash
# Launch todooit from the worktree you are standing in, against that worktree's
# own dev database and venv. Run under WSL, from inside the worktree.
#
#   cd <repo>.git/feat-xy && bash test.sh
#
# Each worktree gets an instance dir under ~/.local/share/todooit-wt/ holding
# both its database and its venv; clean.sh deletes them along with the
# worktree. The first run for a worktree builds the venv, so it is slower.
#
# It takes no arguments and leaves you where you are - no cd back to dev.
# (An old `source .../test.sh` line in ~/.bashrc registered tab completion for
# the worktree argument. There is no argument anymore; the line is harmless but
# can go.)

# Sourced, not run: do nothing at all rather than launching the app.
if [ "${BASH_SOURCE[0]}" != "$0" ]; then
  return 0
fi

set -euo pipefail

WT_HOMES="$HOME/.local/share/todooit-wt"   # one todooit instance per worktree

if [ "$#" -gt 0 ]; then
  echo "test.sh takes no arguments - cd into the worktree and run it there" >&2
  exit 2
fi

wt="$(git rev-parse --show-toplevel 2>/dev/null)" || {
  echo "not inside a worktree - cd into one (e.g. $PWD/feat-xy) first" >&2
  exit 1
}
cd "$wt"

name="$(basename "$wt")"
home="$WT_HOMES/$name"
mkdir -p "$home"

echo "running $name  (instance $home)"
# The venv lives on ext4, not beside the worktree: installing onto the /mnt/c
# drvfs mount is slow and silently truncates packages. TODOOIT_HOME beats
# --dev, so this is $name's own database, not the shared todooit-dev one.
exec env UV_PROJECT_ENVIRONMENT="$home/venv" TODOOIT_HOME="$home" uv run todooit --dev
