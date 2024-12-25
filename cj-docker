#!/usr/bin/env sh

# This is free and unencumbered software released into the public domain.

# Anyone is free to copy, modify, publish, use, compile, sell, or
# distribute this software, either in source code form or as a compiled
# binary, for any purpose, commercial or non-commercial, and by any
# means.

# In jurisdictions that recognize copyright laws, the author or authors
# of this software dedicate any and all copyright interest in the
# software to the public domain. We make this dedication for the benefit
# of the public at large and to the detriment of our heirs and
# successors. We intend this dedication to be an overt act of
# relinquishment in perpetuity of all present and future rights to this
# software under copyright law.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
# IN NO EVENT SHALL THE AUTHORS BE LIABLE FOR ANY CLAIM, DAMAGES OR
# OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE,
# ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR
# OTHER DEALINGS IN THE SOFTWARE.

# For more information, please refer to <http://unlicense.org/>


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

docker build -q -t cj . 2>&1 >/dev/null

docker run -t -d --name "$CONTAINER" -v .:/cj cj tail -f /dev/null 2>&1 >/dev/null

for header in "${HEADERS[@]}"; do
    docker cp "$header" "$CONTAINER:/tmp/$(basename "$header")" 2>&1 >/dev/null
done

docker exec -it "$CONTAINER" python3 /cj/cj.py "$HSTR" "$ASTR"

docker kill "$CONTAINER" 2>&1 >/dev/null

docker rm "$CONTAINER" 2>&1 >/dev/null
