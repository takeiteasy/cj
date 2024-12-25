/* https://github.com/takeiteasy/cj

 Copyright (C) 2024 George Watson

 This program is free software: you can redistribute it and/or modify
 it under the terms of the GNU General Public License as published by
 the Free Software Foundation, either version 3 of the License, or
 (at your option) any later version.

 This program is distributed in the hope that it will be useful,
 but WITHOUT ANY WARRANTY; without even the implied warranty of
 MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 GNU General Public License for more details.

 You should have received a copy of the GNU General Public License
 along with this program.  If not, see <https://www.gnu.org/licenses/>. */

#include "minilua.h"
#include "raylib.h"

{% for k, v in typedefs.items() %}
{% if v.startswith("struct") == False and k != v and not "(*)" in v %}
#define {{ k }} {{ v }}
#define lua_push{{ k }} lua_push{{ v }}
#define lua_check{{ k }} lua_check{{ v }}
{% endif %}
{% endfor %}

{% for struct in structs %}
static void lua_push{{ struct['name'] }}(lua_State *L, {{ struct['name'] }}* val) {
    lua_newtable(L);
    {% for field in struct['fields'] %}
    lua_pushstring(L, "{{ field['name'] }}");
    {% if field['type']['kind'] == "array" %}
    lua_createtable(L, {{ field['type']['array'][0] }}, 0);
    for (int i = 0; i < {{ field['type']['array'][0] }}; i++) {
        lua_push{{ field_to_lua(field['type']) }}(L, {{ "&" if field['type']['base'] == "Matrix" }}val->{{ field['name'] }}[i]);
        lua_rawseti(L, -2, i + 1);
    }
    {% elif field['type']['kind'] == 'typedef' %}
    lua_push{{ field_to_lua(field['type']) }}(L, &val->{{ field['name'] }});
    {% else %}
    lua_push{{ field_to_lua(field['type']) }}(L, val->{{ field['name'] }});
    {% endif %}
    lua_settable(L, -3);
    {% endfor %}
}

static {{ struct['name'] }} lua_check{{ struct['name'] }}(lua_State *L, int index) {
    {{ struct['name'] }} result;
    {% for field in struct['fields'] %}
    lua_pushstring(L, "{{ field['name'] }}");
    lua_gettable(L, index);
    {% if field['type']['kind'] == "array" %}
    if (!lua_istable(L, -1))
        luaL_error(L, "Expected a table for {{ struct['name'] }}.{{ field['name'] }}");
    for (int i = 0; i < {{ field['type']['array'][0] }}; i++) {
        lua_rawgeti(L, -1, i);
        result.{{ field['name'] }}[i] = {{ field_from_lua(field['type']) }}(L, -1);
        lua_pop(L, 1);
    }
    {% else %}
    result.{{ field['name'] }} = {{ field_from_lua(field['type']) }}(L, -1);
    {% endif %}
    {% endfor %}
    return result;
}
{% endfor %}

{% for func in functions %}
static int lua_{{ func['name'] }}(lua_State *L) {
    {% if func['arguments'] | count > 0 %}
    {% for i, arg in func['arguments'] | enumerate %}
    {{ return_type_from_lua(arg['type']) }} {{ arg['name'] }} = {{ field_from_lua(arg['type']) }}(L, {{ i + 1 }});
    {% endfor %}
    {% endif %}
    {% if func['return_type']['kind'] != "void" %}
    {{ return_type_from_lua(func['return_type']) }} result =
    {% endif %}
    {{ func['name'] }}{{"();" if func['arguments'] | count == 0 else "(" ~ (func['arguments'] | map(attribute='name') | join(", ")) ~ ");"}}
    {% if func['return_type']['kind'] != "void" %}
    lua_push{{ field_to_lua(func['return_type']) }}(L, {{ "&" if func['return_type']['kind'] == "typedef" else "" }}result);
    {% endif %}
    return 1;
}
{% endfor %}

static void initialize_{{ name }}_lua_bindings(lua_State *L) {
    luaL_Reg regs[{{ functions | count + 1 }}] = {
        {% for func in functions %}
        { "{{ pascal_to_snake_case(func['name']) }}", lua_{{ func['name'] }} },
        {% endfor %}
        { NULL, NULL }
    };
    lua_register(L, "{{ bind_name }}", regs);
    {% for enum in enums %}
    {% for v in enum['values'] %}
    lua_pushnumber(L, {{ v['value'] }});
    lua_setfield(L, -2, "{{ v['name'] }}");
    {% endfor %}
    {% endfor %}
}
