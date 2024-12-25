#!/usr/bin/env sh

CONTAINER=$(uuidgen)
HEADERS=()
FIXEDHEADERS=()
ARGS=()

for arg in "$@"; do
  if [[ -f "$arg" ]]; then
    HEADERS+=("$arg")
  else
    ARGS+=("$arg")
  fi
done

for header in "${HEADERS[@]}"; do
    FIXEDHEADERS+=("/tmp/$(basename "$header")")
done
HSTR=$(echo "${FIXEDHEADERS[@]}" | tr ' ' '\n' | paste -sd ' ' -)
ASTR=$(echo "${ARGS[@]}" | tr ' ' '\n' | paste -sd ' ' -)

docker build -t cj .

docker run -t -d --name "$CONTAINER" -v .:/cj cj tail -f /dev/null

for header in "${HEADERS[@]}"; do
    docker cp "$header" "$CONTAINER:/tmp/$(basename "$header")"
done

docker exec -it "$CONTAINER" python3 /cj/cj.py "$HSTR" "$ASTR"

docker kill "$CONTAINER"

docker rm "$CONTAINER"
