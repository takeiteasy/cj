# CJ

__CJ__ is a script to serialise C headers to JSON with libclang -- forked from [gilzoide/c_api_extract-py](https://github.com/gilzoide/c_api_extract-py)

![logo](/cj.jpg)

## Usage

```
usage: cj.py [-h] [-c PATH] [-a ARGS [ARGS ...]] [-L PATH]
             [-i FILTER [FILTER ...]] [-d FILTER [FILTER ...]]
             [-D FILTER [FILTER ...]] [-o PATH] [-w] [-s] [-t] [-m] [-x]
             HEADERS [HEADERS ...]

Serialise C headers to Lua C bindings w/ python + libclang!

positional arguments:
  HEADERS               Path to header file(s) to process

options:
  -h, --help            show this help message and exit
  -c PATH, --clang PATH
                        Specify the path to `clang`
  -a ARGS [ARGS ...], --xargs ARGS [ARGS ...]
                        Pass arguments through to clang
  -L PATH, --lib PATH   Specify the path to clang library or directory
  -i FILTER [FILTER ...], --include-headers FILTER [FILTER ...]
                        Only process headers with names that match any of the
                        given regex patterns. Matches are tested using
                        `re.search`, so patterns are not anchored by default.
                        This may be used to avoid processing standard headers
                        and dependencies headers.
  -d FILTER [FILTER ...], --include-definitions FILTER [FILTER ...]
                        Only include definitions that match given regex
                        filters
  -D FILTER [FILTER ...], --exclude-definitions FILTER [FILTER ...]
                        Exclude any definitions that match given regex filters
                        (NOTE: Overwriten by `--include-definitions` option)
  -o PATH, --output PATH
                        Specify the file or directory to dump JSON to.
                        (default: dump to stdout)
  -w, --writeover       If the output destination exists, overwrite it.
  -s, --skip-defines    By default, cj will try compiling object-like macros
                        looking for constants, which may take long if your
                        header has lots of them. Use this flag to skip this
                        step
  -t, --type-objects    Output type objects instead of simply the type
                        spelling string
  -m, --minified        Output minified JSON instead of using 0 space
                        indentations
  -x, --language        Set `-x {lang}` when running clang
```

__CJ__ relies on libclang and clang's python module, here's how to set it up:

```
python3 -m venv env
source env/bin/activate
python3 -m pip install -r requirements.txt
python3 cj.py [headers] [options]
```

Alternatively, you can use the ```cj-docker``` script to build and run inside docker.

## LICENSE
```
This is free and unencumbered software released into the public domain.

Anyone is free to copy, modify, publish, use, compile, sell, or
distribute this software, either in source code form or as a compiled
binary, for any purpose, commercial or non-commercial, and by any
means.

In jurisdictions that recognize copyright laws, the author or authors
of this software dedicate any and all copyright interest in the
software to the public domain. We make this dedication for the benefit
of the public at large and to the detriment of our heirs and
successors. We intend this dedication to be an overt act of
relinquishment in perpetuity of all present and future rights to this
software under copyright law.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
IN NO EVENT SHALL THE AUTHORS BE LIABLE FOR ANY CLAIM, DAMAGES OR
OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE,
ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR
OTHER DEALINGS IN THE SOFTWARE.

For more information, please refer to <http://unlicense.org/>
```
