#!/usr/bin/env bash
# Launch todooit from one worktree against that worktree's own dev database,
# then drop you back in dev. Run under WSL.
#
#   ./test.sh feat-xy      run the app with feat-xy's code and feat-xy's db
#   ./test.sh              same, for the dev worktree
#
# Each worktree gets an instance dir under ~/.local/share/todooit-wt/ holding
# both its database and its venv; clean.sh deletes them along with the
# worktree. The first run for a worktree builds the venv, so it is slower.
#
# Tab completion over worktree names: add this line to ~/.bashrc
#   source /mnt/c/Users/slamanigg/Documents/todooit.git/dev/test.sh
# (sourcing only registers the completion, it never launches the app)

# Everything above the sourced-check runs in your interactive shell too, so it
# stays namespaced and sets no shell options.
_TODOOIT_REPO="$(dirname "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)")"

_todooit_worktrees() {
  # Paths under the bare repo only, so the repo itself is not offered.
  git -C "$_TODOOIT_REPO" worktree list --porcelain |
    sed -n "s|^worktree $_TODOOIT_REPO/||p"
}

_todooit_test_complete() {
  local cur="${COMP_WORDS[COMP_CWORD]}"
  mapfile -t COMPREPLY < <(compgen -W "$(_todooit_worktrees)" -- "$cur")
}

# Sourced from .bashrc: just wire up completion and get out.
if [ "${BASH_SOURCE[0]}" != "$0" ]; then
  complete -F _todooit_test_complete test.sh ./test.sh
  return 0
fi

set -euo pipefail

REPO="$_TODOOIT_REPO"                     # bare repo holding all the worktrees
DEV="$REPO/dev"
WT_HOMES="$HOME/.local/share/todooit-wt"  # one todooit instance per worktree
START="$PWD"

name="${1:-dev}"
wt="$REPO/$name"
if [ ! -d "$wt" ]; then
  echo "no worktree '$name' in $REPO" >&2
  echo "try: $(_todooit_worktrees | tr '\n' ' ')" >&2
  exit 1
fi

home="$WT_HOMES/$name"
mkdir -p "$home"

# Back to dev whatever happens - a crash, or you quitting the TUI. The cd only
# sticks if this script was sourced, so report what is actually true.
back_to_dev() {
  cd "$DEV"
  if [ "$START" -ef "$DEV" ]; then
    echo "back in $DEV"
  else
    echo "done - run 'cd $DEV' to get back to dev"
  fi
}
trap back_to_dev EXIT

echo "running $name  (instance $home)"
cd "$wt"
# The venv lives on ext4, not beside the worktree: installing onto the /mnt/c
# drvfs mount is slow and silently truncates packages. TODOOIT_HOME beats
# --dev, so this is $name's own database, not the shared todooit-dev one.
UV_PROJECT_ENVIRONMENT="$home/venv" TODOOIT_HOME="$home" uv run todooit --dev
