#!/usr/bin/env bash
# Tear down finished feat-*/fix-* worktrees: the checkout, the branch, and the
# worktree's own todooit instance (its dev database and its venv). Worktrees
# with uncommitted changes are left alone. Run from dev, under WSL.
#
#   ./clean.sh          remove every clean feat-*/fix-* worktree (asks once)
#   ./clean.sh -n       dry run: only show what would go
#   ./clean.sh -y       skip the confirmation
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(dirname "$SCRIPT_DIR")"           # bare repo holding all the worktrees
DEV="$REPO/dev"
WT_HOMES="$HOME/.local/share/todooit-wt"  # one todooit instance per worktree

START="$PWD"
DRY=0 YES=0
for arg in "$@"; do
  case "$arg" in
    -n|--dry-run) DRY=1 ;;
    -y|--yes)     YES=1 ;;
    *) echo "usage: clean.sh [-n|--dry-run] [-y|--yes]" >&2; exit 2 ;;
  esac
done

# The cd at the end only sticks if this script was sourced; say what is
# actually true so you are never told you are somewhere you are not.
back_to_dev() {
  cd "$DEV"
  if [ "$START" -ef "$DEV" ]; then
    echo "now in $DEV"
  else
    echo "done - run 'cd $DEV' to get back to dev"
  fi
}

# Sort every feat-*/fix-* worktree into doomed ("<path>\t<branch>") or kept.
doomed=() kept=() wt="" br=""
while IFS= read -r line; do
  case "$line" in
    "worktree "*) wt="${line#worktree }" ;;
    "branch "*)   br="${line#branch refs/heads/}" ;;
    "")
      name="$(basename "$wt")"
      case "$name" in feat*|fix*) ;; *) continue ;; esac
      case "$br" in dev|main) continue ;; esac
      if [ "$wt" -ef "$PWD" ]; then
        kept+=("$name (you are standing in it)")
      elif [ -n "$(git -C "$wt" status --porcelain)" ]; then
        kept+=("$name (uncommitted changes)")
      else
        doomed+=("$wt	$br")
      fi
      ;;
  esac
done < <(git -C "$REPO" worktree list --porcelain; echo)

# Instances whose worktree is already gone.
orphans=()
if [ -d "$WT_HOMES" ]; then
  for home in "$WT_HOMES"/*; do
    [ -d "$home" ] || continue
    name="$(basename "$home")"
    case "$name" in feat*|fix*) ;; *) continue ;; esac
    [ -d "$REPO/$name" ] || orphans+=("$name")
  done
fi

for k in ${kept+"${kept[@]}"}; do echo "keep   $k"; done
for d in ${doomed+"${doomed[@]}"}; do
  IFS=$'\t' read -r wt br <<<"$d"
  echo "remove $(basename "$wt")  (branch $br, instance $WT_HOMES/$(basename "$wt"))"
done
for o in ${orphans+"${orphans[@]}"}; do echo "remove orphaned instance $o"; done

if [ ${#doomed[@]} -eq 0 ] && [ ${#orphans[@]} -eq 0 ]; then
  echo "nothing to clean"
elif [ "$DRY" -eq 1 ]; then
  echo "(dry run, nothing touched)"
else
  if [ "$YES" -eq 0 ]; then
    read -rp "delete these worktrees, branches and databases? [y/N] " reply
    [[ "$reply" == [yY]* ]] || { echo "aborted"; back_to_dev; exit 0; }
  fi
  for d in ${doomed+"${doomed[@]}"}; do
    IFS=$'\t' read -r wt br <<<"$d"
    name="$(basename "$wt")"
    # --force only waives ignored leftovers (caches); the tracked tree was
    # already checked clean above.
    git -C "$REPO" worktree remove --force "$wt"
    git -C "$REPO" branch -D "$br"
    rm -rf "${WT_HOMES:?}/$name"
    echo "gone   $name"
  done
  for o in ${orphans+"${orphans[@]}"}; do
    rm -rf "${WT_HOMES:?}/$o"
    echo "gone   orphaned instance $o"
  done
fi

back_to_dev
