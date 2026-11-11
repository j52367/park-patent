#!/usr/bin/env bash
# Optional backend: screen PARK batches with the OpenAI Codex CLI, several workers in parallel.
#
#   scripts/codex-screen.sh <analysis-dir> [workers=4] [effort=medium] [mode=screen|review]
#
# Screens every screening/todo/*.md that has no screening/done/<name>.jsonl yet, so it can simply be
# re-run after an interruption (e.g. a ChatGPT usage limit). Batches named recheck_* get the
# ':recheck' suffix, tail_audit* the matching ':tail-audit[-rN]' suffix and noise_audit ':noise-audit' on screened_by.
# Then run:  park merge-screening <analysis-dir>   (mode=review: park merge-review <analysis-dir>)
#
# Patent text is sent to OpenAI. Do not use this for confidential input without permission.
set -u
dir=$(cd "$1" && pwd) || exit 1
workers=${2:-4}; effort=${3:-medium}; mode=${4:-screen}
here=$(cd "$(dirname "$0")/.." && pwd)
if [ "$mode" = review ]; then
  prompt_file="$here/skills/key-patent-review/codex-prompt.md"; work=review
else
  prompt_file="$here/skills/relevance-screening/codex-prompt.md"; work=screening
fi
command -v codex >/dev/null || { echo "codex CLI not found"; exit 2; }
cd "$dir" || exit 1
mkdir -p "$work/done" "$work/logs"

run() {  # run <id> <suffix> <batch files...>
  local id=$1 suffix=$2; shift 2
  local list; list=$(printf "%s, " "$@")
  timeout 3600 codex exec -c model_reasoning_effort="$effort" --sandbox workspace-write --skip-git-repo-check --ephemeral \
    "$(cat "$prompt_file")

Your assigned batch files: ${list%, }
Use screened_by suffix: \"$suffix\"" < /dev/null > "$work/logs/codex_$id.log" 2>&1
}

pending=(); special=()
for f in "$work"/todo/*.md; do
  b=$(basename "$f" .md)
  [ -f "$work/done/$b.jsonl" ] && continue
  case "$b" in recheck_*|tail_audit*|noise_audit) special+=("$f");; *) pending+=("$f");; esac
done
echo "pending batches: $(( ${#pending[@]} + ${#special[@]} ))"

for f in "${special[@]}"; do
  b=$(basename "$f" .md)
  case "$b" in
    recheck_*) run "$b" ":recheck" "$f" & ;;
    tail_audit) run "$b" ":tail-audit" "$f" & ;;
    noise_audit) run "$b" ":noise-audit" "$f" & ;;
    tail_audit_r*) run "$b" ":tail-audit-r${b#tail_audit_r}" "$f" & ;;
  esac
done
n=${#pending[@]}; per=$(( (n + workers - 1) / workers )); [ "$per" -lt 1 ] && per=1
for ((i = 0; i < workers; i++)); do
  part=("${pending[@]:$((i * per)):$per}")
  [ ${#part[@]} -gt 0 ] && run "w$i" "" "${part[@]}" &
done
wait

left=0
for f in "$work"/todo/*.md; do b=$(basename "$f" .md); [ -f "$work/done/$b.jsonl" ] || left=$((left + 1)); done
if grep -qh "usage limit" "$work"/logs/*.log 2>/dev/null; then
  echo "stopped by a usage limit: $(grep -h -o 'try again at [^.]*' "$work"/logs/*.log | head -1). $left batches left — re-run this script later."
else
  echo "done; $left batches without results"
fi
