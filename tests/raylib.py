""" 
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
"""

from cj import Visitor
from lua import LuaGenerator
import platform

libclang_path = "/Library/Developer/CommandLineTools/usr/lib/libclang.dylib" if platform.system() == 'Darwin' else None 

def path_seperator():
    if platform.system() == "win32":
        return "\\"
    else:
        return "/"

header = "../deps/raylib/src/raylib.h"
visitor = Visitor(header,
                  libclang_path=libclang_path,
                  include_patterns=["^Texture"],
                  exclude_patterns=["InitWindow",
                                    "^Text",
                                    "^rAudio",
                                    "Callback$",
                                    "(De|At)tachAudio(Mixed|Stream)Processor",
                                    "__"])
generator = LuaGenerator(visitor, "raylib_template.c", name="raylib", bind_to="ray")
output = generator.process()
print(output)
