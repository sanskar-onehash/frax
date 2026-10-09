#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 || $# -gt 3 ]]; then
  echo "Usage: $0 <bench-directory> <site> [core|business|customized]" >&2
  exit 2
fi

bench_directory=$1
site=$2
profile=${3:-core}

case "$profile" in
  core|business|customized) ;;
  *)
    echo "Unknown compatibility profile: $profile" >&2
    exit 2
    ;;
esac

if [[ ! -d "$bench_directory/sites/$site" ]]; then
  echo "Site not found: $bench_directory/sites/$site" >&2
  exit 2
fi

cd "$bench_directory"
echo "Running Frax compatibility profile '$profile' on site '$site'"
FRAX_COMPAT_PROFILE="$profile" bench --site "$site" run-tests --app frax
