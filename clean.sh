#!/usr/bin/env bash
# Tear down finished worktrees: the checkout, the branch, and the worktree's own
# todooit instance (its dev database and its venv). Every worktree goes except
# the ones on the keep list - main, dev and the other long-lived names below.
# Worktrees with uncommitted changes are left alone. Run under WSL, from
# anywhere inside the repo - dev, main, another worktree, or a subdirectory.
#
#   bash clean.sh          remove every clean, unprotected worktree (asks once)
#   bash clean.sh -n       dry run: only show what would go
#   bash clean.sh -y       skip the confirmation
#
# It never deletes the directory you are standing in: if that directory belongs
# to something on the remove list, it prints the table and aborts untouched.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WT_HOMES="$HOME/.local/share/todooit-wt"   # one todooit instance per worktree
HERE="$(pwd -P)"

# Branches that stay put however old they get. Set KEEP_BRANCHES to replace the
# list outright, or KEEP_BRANCHES_EXTRA to add a name or two for one run:
#
#   KEEP_BRANCHES_EXTRA="spike-ui" bash clean.sh
#
KEEP_BRANCHES="${KEEP_BRANCHES:-main master dev develop development trunk \
release stable prod production staging}"
KEEP_BRANCHES="$KEEP_BRANCHES ${KEEP_BRANCHES_EXTRA:-}"

DRY=0 YES=0
for arg in "$@"; do
  case "$arg" in
    -n|--dry-run) DRY=1 ;;
    -y|--yes)     YES=1 ;;
    *) echo "usage: clean.sh [-n|--dry-run] [-y|--yes]" >&2; exit 2 ;;
  esac
done

# The bare repo holding the worktrees, found from wherever you are standing;
# outside the repo altogether, fall back to the copy of the script you invoked.
if common="$(git rev-parse --git-common-dir 2>/dev/null)"; then
  REPO="$(cd "$common" && pwd)"
else
  REPO="$(dirname "$SCRIPT_DIR")"
fi

if [ -t 1 ]; then
  DIM=$'\e[2m'; RED=$'\e[31m'; GRN=$'\e[32m'; YEL=$'\e[33m'; OFF=$'\e[0m'
else
  DIM='' RED='' GRN='' YEL='' OFF=''
fi

# Does $1 sit at or below $2?
inside() { case "$1/" in "$2"/*) return 0 ;; esac; return 1; }

# Is any of the names given on the keep list? Called with the branch and, for a
# detached worktree that has no branch, the directory name.
protected() {
  local subject keep
  for subject in "$@"; do
    [ -n "$subject" ] || continue
    for keep in $KEEP_BRANCHES; do
      if [ "$subject" = "$keep" ]; then return 0; fi
    done
  done
  return 1
}

# Sort every worktree into doomed ("<path>\t<branch>") or kept, and build one
# table row per worktree as "<action>\t<name>\t<branch>\t<note>".
rows=() doomed=() orphans=() blocked=''
wt='' br='' bare=0
while IFS= read -r line; do
  case "$line" in
    "worktree "*) wt="${line#worktree }"; br=''; bare=0 ;;
    "branch "*)   br="${line#branch refs/heads/}" ;;
    "bare")       bare=1 ;;
    "")
      [ -n "$wt" ] || continue
      path="$wt"; wt=''
      [ "$bare" -eq 0 ] || continue          # the bare repo itself
      name="$(basename "$path")"
      if protected "$br" "$name"; then
        rows+=("keep	$name	${br:--}	protected")
        continue
      fi
      real="$(cd "$path" 2>/dev/null && pwd -P || echo "$path")"
      if [ -n "$(git -C "$path" status --porcelain)" ]; then
        rows+=("keep	$name	${br:--}	uncommitted changes")
      else
        if inside "$HERE" "$real"; then blocked="$name"; fi
        doomed+=("$path	$br")
        rows+=("remove	$name	${br:--}	clean")
      fi
      ;;
  esac
done < <(git -C "$REPO" worktree list --porcelain; echo)

# Instances whose worktree is already gone.
if [ -d "$WT_HOMES" ]; then
  for home in "$WT_HOMES"/*; do
    [ -d "$home" ] || continue
    name="$(basename "$home")"
    if protected "$name"; then continue; fi
    if [ ! -d "$REPO/$name" ]; then
      if inside "$HERE" "$(cd "$home" && pwd -P)"; then blocked="$name"; fi
      orphans+=("$name")
      rows+=("remove	$name	-	orphaned instance")
    fi
  done
fi

n_remove=${#doomed[@]} n_orphan=${#orphans[@]}
n_keep=$(( ${#rows[@]} - n_remove - n_orphan ))

if [ ${#rows[@]} -eq 0 ]; then
  printf '\n  %s%s - nothing to clean%s\n\n' "$DIM" "$(basename "$REPO")" "$OFF"
  exit 0
fi

# Table, sized to its contents.
w_name=8 w_br=6
for r in "${rows[@]}"; do
  IFS=$'\t' read -r _ n b _ <<<"$r"
  if [ ${#n} -gt "$w_name" ]; then w_name=${#n}; fi
  if [ ${#b} -gt "$w_br" ]; then w_br=${#b}; fi
done
rule="$(printf '%*s' $((w_name + w_br + 32)) '' | tr ' ' '-')"

printf '\n  %s%s%s\n\n' "$DIM" "$(basename "$REPO")" "$OFF"
printf '  %sACTION  %-*s  %-*s  NOTE%s\n' "$DIM" "$w_name" WORKTREE "$w_br" BRANCH "$OFF"
printf '  %s%s%s\n' "$DIM" "$rule" "$OFF"
for r in "${rows[@]}"; do
  IFS=$'\t' read -r a n b note <<<"$r"
  if [ "$a" = remove ]; then c="$YEL"; else c="$GRN"; fi
  printf '  %s%-6s%s  %-*s  %-*s  %s%s%s\n' \
    "$c" "$a" "$OFF" "$w_name" "$n" "$w_br" "$b" "$DIM" "$note" "$OFF"
done
printf '  %s%s%s\n' "$DIM" "$rule" "$OFF"
printf '  %s%d to remove, %d kept%s\n\n' "$DIM" "$((n_remove + n_orphan))" "$n_keep" "$OFF"

if [ -n "$blocked" ]; then
  printf '  %s! you are standing inside %s, which is on the remove list%s\n' "$RED" "$blocked" "$OFF"
  printf '  %scd out of it (e.g. cd %s/dev) and run clean.sh again - nothing was touched%s\n\n' \
    "$DIM" "$REPO" "$OFF"
  exit 1
fi

if [ "$((n_remove + n_orphan))" -eq 0 ]; then
  exit 0
fi
if [ "$DRY" -eq 1 ]; then
  printf '  %sdry run, nothing touched%s\n\n' "$DIM" "$OFF"
  exit 0
fi
if [ "$YES" -eq 0 ]; then
  read -rp "  delete these worktrees, branches and databases? [y/N] " reply
  case "$reply" in
    [yY]*) ;;
    *) printf '  %saborted%s\n\n' "$DIM" "$OFF"; exit 0 ;;
  esac
fi

for d in ${doomed+"${doomed[@]}"}; do
  IFS=$'\t' read -r path br <<<"$d"
  name="$(basename "$path")"
  # --force only waives ignored leftovers (caches); the tracked tree was
  # already checked clean above.
  git -C "$REPO" worktree remove --force "$path"
  # A detached worktree has no branch to delete.
  if [ -n "$br" ]; then git -C "$REPO" branch -D "$br" >/dev/null; fi
  rm -rf "${WT_HOMES:?}/$name"
done
for o in ${orphans+"${orphans[@]}"}; do
  rm -rf "${WT_HOMES:?}/$o"
done

printf '  %sremoved %d worktree(s), %d orphaned instance(s)%s\n\n' \
  "$DIM" "$n_remove" "$n_orphan" "$OFF"
