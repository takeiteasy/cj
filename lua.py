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

from cj import Visitor, Generator
import re 

def enumerate_filter(items):
    return enumerate(items)

# https://stackoverflow.com/a/1176023
def pascal_to_snake_case(name):
    name = re.sub(r'([23])D$', r'_\1d', name)
    name = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
    name = re.sub('([a-z0-9])([A-Z])', r'\1_\2', name)
    return name.lower()

class LuaGenerator(Generator): 
    def __init__(self, visitor: Visitor, template: str, name: str = None,  bind_to: str = None):
        super().__init__(visitor, template, name, bind_to)
        self.add_functions(field_to_lua=self.field_to_lua,
                           field_from_lua=self.field_from_lua,
                           return_type_from_lua=self.return_type_from_lua,
                           pascal_to_snake_case=pascal_to_snake_case)
        self.env.filters['enumerate'] = enumerate_filter

    def type_to_lua(self, type):
        match type:
            case "int" | "char" | "long" | "short":
                return "integer"
            case "float" | "double":
                return "number"
            case "_Bool":
                return "boolean"
            case _:
                print(type)
                raise ValueError(type)
                
    def field_to_lua(self, type):
        match type['kind']:
            case "typedef":
                return type['base']
            case "array":
                return type['base'] if self.visitor.has_typedef(type['base']) else self.type_to_lua(type['base'])
            case "pointer":
                if re.findall(r"(const\s?)?(unsigned\s?)?\s?char\s\*{1}$", type['spelling']):
                    return "string"
                else:
                    return "lightuserdata"
            case _:
                return self.type_to_lua(type['base'].split(" ")[-1])
    
    def type_from_lua(self, type):
        match type:
            case "int" | "char" | "long" | "short":
                return "luaL_checkinteger"
            case "float" | "double":
                return "luaL_checknumber"
            case "_Bool":
                return "lua_toboolean"
            case _:
                raise ValueError(type)

    def field_from_lua(self, type):
        match type['kind']:
            case "pointer":
                if re.findall(r"(const\s?)?(unsigned\s?)?\s?char\s\*{1}$", type['spelling']):
                    return "luaL_checkstring"
                else:
                    return "lua_touserdata"
            case "typedef":
                return "lua_check" + type['base']
            case "array":
                return "lua_check" + type['base'] if self.visitor.has_typedef(type['base']) else self.type_from_lua(type['base'])
            case _:
                return self.type_from_lua(type['base'].split(" ")[-1])
    
    def return_type_from_lua(self, type):
        match type['kind']:
            case "pointer" | "typedef":
                return type['spelling']
            case "uint":
                return "unsigned int"
            case "void" | "int" | "bool" | "float" | "char":
                return type['kind']
            case _:
                raise ValueError(type['kind'])