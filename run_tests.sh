#!/usr/bin/env bash
# Run this worktree's test suite, picking what to run from a menu first.
# Run under WSL, from inside the worktree.
#
#   cd <repo>.git/feat-xy && bash run_tests.sh
#
# It takes no arguments and, like test.sh, works on the worktree you are
# standing in and on that worktree's own venv (the instance dir under
# ~/.local/share/todooit-wt/). The tests never touch that worktree's database:
# the root conftest.py repoints TODOOIT_HOME at a throwaway directory before
# todooit is imported.
#
# Every option prints the pytest command before running it, so the menu doubles
# as the reminder of how to type that command by hand.

# Sourced, not run: do nothing rather than starting a test run.
if [ "${BASH_SOURCE[0]}" != "$0" ]; then
  return 0
fi

set -euo pipefail

WT_HOMES="$HOME/.local/share/todooit-wt"   # one todooit instance per worktree

# The flags CI runs with: a pilot that hangs inside an xdist worker otherwise
# takes the whole run with it instead of failing one test. Only added to the
# parallel options - a serial run you can watch and interrupt yourself.
PAR=(--timeout=120 --timeout-method=thread)

if [ -t 1 ]; then
  DIM=$'\e[2m'; RED=$'\e[31m'; OFF=$'\e[0m'
else
  DIM='' RED='' OFF=''
fi
say() { printf '\n  %s%s%s\n' "$DIM" "$*" "$OFF"; }
die() { printf '\n  %s%s%s\n\n' "$RED" "$*" "$OFF" >&2; exit 1; }

if [ "$#" -gt 0 ]; then
  echo "run_tests.sh takes no arguments - cd into the worktree and run it there" >&2
  exit 2
fi

wt="$(git rev-parse --show-toplevel 2>/dev/null)" ||
  die "not inside a worktree - cd into one (e.g. $PWD/feat-xy) and run run_tests.sh there"
cd "$wt"

name="$(basename "$wt")"
home="$WT_HOMES/$name"
mkdir -p "$home"

# The same environment `uv run todooit` and test.sh use in this worktree. The
# root conftest.py fails the run outright if the todooit being imported belongs
# to a different worktree, so a stale venv is an error rather than a mystery.
export UV_PROJECT_ENVIRONMENT="$home/venv"
# Keeps __pycache__ out of the worktree and off the /mnt/c mount, where writing
# it is a good part of pytest's start-up cost.
export PYTHONPYCACHEPREFIX="${TMPDIR:-/tmp}/ttpyc/$name"

# The feature markers, read out of pyproject.toml rather than listed here, so
# this menu cannot drift from the markers conftest.py actually puts on tests.
mapfile -t marker_lines < <(
  sed -n '/^markers = \[/,/^]/p' pyproject.toml |
  sed -n 's/^ *"\([A-Za-z_]*\): *\(.*\)",$/\1|\2/p'
)
[ "${#marker_lines[@]}" -gt 0 ] ||
  die "no markers found in pyproject.toml - has [tool.pytest.ini_options] changed shape?"

features=() feature_help=()
for line in "${marker_lines[@]}"; do
  case "${line%%|*}" in
    core|ui|smoke) continue ;;   # layers, not features: they have their own menu entries
  esac
  features+=("${line%%|*}")
  feature_help+=("${line#*|}")
done

# Read a choice from a numbered list: the number goes to stdout, everything
# else to stderr, so a caller can capture just the number. Empty input goes back.
choose() {
  local max="$1" n
  while :; do
    read -rp "  number (enter to go back): " n || n=""   # ctrl-d reads as enter
    [ -n "$n" ] || { echo 0; return 0; }
    if [ -z "${n//[0-9]/}" ] && [ "$n" -ge 1 ] && [ "$n" -le "$max" ]; then
      echo "$n"
      return 0
    fi
    printf '  %s1-%s, or enter to go back%s\n' "$DIM" "$max" "$OFF" >&2
  done
}

# The command as you would type it, quoting only the arguments that need it.
show() {
  local out='' arg
  for arg in "$@"; do
    case "$arg" in *[!A-Za-z0-9=./_-]*) arg="\"$arg\"" ;; esac
    out="$out $arg"
  done
  printf '\n  %s$%s%s\n\n' "$DIM" "$out" "$OFF"
}

# Option 3: one feature, either half of it or both.
pick_feature() {
  local i=0 f n layer
  printf '\n  which feature\n\n' >&2
  for f in "${features[@]}"; do
    i=$((i + 1))
    printf '  %3d %-12s' "$i" "$f" >&2
    [ $((i % 4)) -eq 0 ] && printf '\n' >&2
  done
  [ $((i % 4)) -eq 0 ] || printf '\n' >&2
  echo >&2

  n="$(choose "${#features[@]}")"
  [ "$n" != 0 ] || return 1
  f="${features[$((n - 1))]}"
  printf '\n  %s%s%s\n' "$DIM" "${feature_help[$((n - 1))]}" "$OFF" >&2

  read -rp "  layer - enter both, c core only, u ui only: " layer || layer=""
  case "$layer" in
    c|C) cmd=(uv run pytest -q -m "$f and core") ;;
    u|U) cmd=(uv run pytest -q -m "$f and ui") ;;
    *)   cmd=(uv run pytest -q -m "$f") ;;
  esac
}

# Option 6: one file. Typing part of a name narrows the list, enter shows all.
pick_file() {
  local filter files=() i=0 n
  read -rp "  file name or part of one (enter for all): " filter || filter=""
  if [ -n "$filter" ]; then
    mapfile -t files < <(git ls-files tests |
      grep -E '(^|/)test_[^/]*\.py$' | grep -iF -- "$filter" || true)
  else
    mapfile -t files < <(git ls-files tests | grep -E '(^|/)test_[^/]*\.py$')
  fi

  case "${#files[@]}" in
    0) printf '\n  %sno test file matches %s%s\n' "$DIM" "$filter" "$OFF" >&2; return 1 ;;
    1) cmd=(uv run pytest -q "${files[0]}"); return 0 ;;
  esac

  echo >&2
  for n in "${files[@]}"; do
    i=$((i + 1))
    printf '  %3d %s\n' "$i" "$n" >&2
  done
  echo >&2

  n="$(choose "${#files[@]}")"
  [ "$n" != 0 ] || return 1
  # No -n: on a single file xdist's start-up costs more than it saves.
  cmd=(uv run pytest -q "${files[$((n - 1))]}")
}

[ -d "$home/venv" ] ||
  say "first run for $name - uv builds its venv before the tests, so this one is slow"

cmd=() coverage_report=0

while :; do
  cat >&2 <<MENU

  $name  (venv $home/venv)

  what to run

     1  smoke              all of test_core plus one test per UI module   ~20s
     2  everything         the whole suite, -n auto                       ~2min
     3  one feature        pick from the marker list
     4  core only          the pure-logic half, no Textual app
     5  ui only            everything that drives a real app
     6  one file           pick from tests/
     7  last failures      only the tests that failed the last time
     8  marker expression  your own -m, e.g. "move or sort"
     9  as CI runs it      what .github/workflows/tests.yml runs
    10  coverage           the whole suite, serial, then a report

MENU

  choice="$(choose 10)"
  case "$choice" in
    0)  say "nothing selected"; exit 0 ;;
    1)  cmd=(uv run pytest -q -m smoke -n 4 "${PAR[@]}") ;;
    2)  cmd=(uv run pytest -q -n auto "${PAR[@]}") ;;
    3)  pick_feature || continue ;;
    4)  cmd=(uv run pytest -q -m core) ;;
    5)  cmd=(uv run pytest -q -m ui -n auto "${PAR[@]}") ;;
    6)  pick_file || continue ;;
    # --lf with nothing remembered runs the whole suite, which is pytest being
    # honest but is not what you asked for; say so rather than surprise you.
    7)  if [ ! -f .pytest_cache/v/cache/lastfailed ]; then
          printf '\n  %sno failures remembered - run something first%s\n' "$DIM" "$OFF" >&2
          continue
        fi
        cmd=(uv run pytest -q --lf) ;;
    8)  read -rp "  -m expression: " expr || expr=""
        [ -n "$expr" ] || continue
        # A marker that does not exist is rejected by the root conftest.py
        # rather than quietly selecting nothing.
        cmd=(uv run pytest -q -m "$expr") ;;
    9)  cmd=(uv run pytest -n 4 --dist load "${PAR[@]}") ;;
    # Serial: under xdist the tests run in worker subprocesses coverage does
    # not follow, and the report comes out near empty.
    10) cmd=(uv run coverage run -m pytest -q); coverage_report=1 ;;
  esac
  break
done

show "${cmd[@]}"

status=0
"${cmd[@]}" || status=$?

if [ "$status" -eq 0 ]; then
  if [ "$coverage_report" = 1 ]; then
    show uv run coverage report
    uv run coverage report
  fi
  say "green"
else
  printf '\n  %sfailed (exit %s)%s\n' "$RED" "$status" "$OFF" >&2
  # 1 means tests failed; anything else (2 interrupted, 4 a bad -m, 5 nothing
  # collected) is not something --lf can pick up again.
  [ "$status" -eq 1 ] &&
    printf '  %sre-run just what broke with option 7%s\n' "$DIM" "$OFF" >&2
  echo >&2
fi

exit "$status"
