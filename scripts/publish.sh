#!/usr/bin/env bash
# Turns every folder in queue/<repo-name>/ into its own public GitHub repo,
# adds a row to the README index, then removes the folder from the queue.
set -euo pipefail
shopt -s nullglob

if [ -z "${GH_TOKEN:-}" ]; then
  echo "::error::Secret REPO_CREATOR_TOKEN is missing. Add it under Settings > Secrets and variables > Actions."
  exit 1
fi

for dir in queue/*/; do
  dir="${dir%/}"
  name="$(basename "$dir")"
  meta="$dir/.repo.json"
  desc=""; topics=""
  if [ -f "$meta" ]; then
    desc="$(jq -r '.description // ""' "$meta")"
    topics="$(jq -r '(.topics // []) | join(" ")' "$meta")"
  fi
  url="https://github.com/$OWNER/$name"
  echo "== $name"

  if gh repo view "$OWNER/$name" >/dev/null 2>&1; then
    if [ -n "$(gh api "repos/$OWNER/$name/commits?per_page=1" 2>/dev/null | jq -r '.[0].sha // empty')" ]; then
      echo "::warning::$OWNER/$name already exists and has commits; leaving it untouched."
      git rm -r -q "$dir"
      continue
    fi
  else
    gh repo create "$OWNER/$name" --public --description "$desc"
  fi

  tmp="$(mktemp -d)"
  cp -a "$dir"/. "$tmp"/
  rm -f "$tmp/.repo.json"
  (
    cd "$tmp"
    git init -q -b main
    git add -A
    git -c user.name="$AUTHOR_NAME" -c user.email="$AUTHOR_EMAIL" \
      commit -q -m "Initial commit: ${desc:-$name}"
    git push -q "https://x-access-token:${GH_TOKEN}@github.com/$OWNER/$name.git" main
  )
  rm -rf "$tmp"

  for t in $topics; do gh repo edit "$OWNER/$name" --add-topic "$t" >/dev/null || true; done

  printf '| [%s](%s) | %s | %s |\n' "$name" "$url" "$desc" "$(date -u +%Y-%m-%d)" >> README.md
  git rm -r -q "$dir"
  echo "Published $url"
done
