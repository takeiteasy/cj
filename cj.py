"""
cj.py is forked from https://github.com/gilzoide/c_api_extract-py and
keeps the original UNLICENSE license

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

import re, sys, os, subprocess, signal, tempfile, argparse, json
from collections import OrderedDict
from pathlib import Path, PurePath
import clang.cindex as clang

ANONYMOUS_SUB_RE = re.compile(r'(.*/|\W)')
UNION_STRUCT_NAME_RE = re.compile(r'(union|struct)\s+(.+)')
ENUM_NAME_RE = re.compile(r'enum\s+(.+)')
MATCH_ALL_RE = re.compile('.*')
DEFINE_RE = re.compile(r'#[ \t]*define[ \t]+([a-zA-Z_][a-zA-Z0-9_]*)[ \t]+')
BUILTIN_C_INTS = { "int8_t", "int16_t", "int32_t", "int64_t", "intptr_t", "ssize_t" }
BUILTIN_C_UINTS = { "uint8_t", "uint16_t", "uint32_t", "uint64_t", "uintptr_t", "size_t" }
BUILTIN_C_DEFINITIONS = {
    "fenv_t", "fexcept_t", "femode_t",  # fenv.h
    "struct lconv",  # locale.h
    "va_list",  # stdarg.h
    "struct atomic_flag",  # stdatomic.h
    "size_t", "ssize_t",  # stddef.h
    "int8_t", "int16_t", "int32_t", "int64_t", "intptr_t",  # stdint.h
    "uint8_t", "uint16_t", "uint32_t", "uint64_t", "uintptr_t",  # stdint.h
    "FILE", "fpos_t",  # stdio.h
    "jmp_buf",  # setjmp.h
    "thrd_t", "mtx_t", "cnd_t",  # threads.h
    "struct tm", "time_t", "struct timespec",  # time.h
}

class CompilationError(Exception):
    pass


class Definition:
    def __init__(self, kind):
        self.kind = kind

    def to_dict(self, is_declaration=True):
        return {
            'kind': self.kind,
        }

    def is_record(self):
        return self.kind in ('struct', 'union')


class Type(Definition):
    type_declarations = OrderedDict()
    processed_types = {}

    class Field:
        def __init__(self, field_cursor):
            self.name = field_cursor.spelling
            self.type = Type.from_clang(field_cursor.type)

        def to_dict(self):
            return {
                'name': self.name,
                'type': self.type.to_dict(),
            }

    class EnumValue:
        def __init__(self, name, value):
            self.name = name
            self.value = value

        def to_dict(self):
            return {
                'name': self.name,
                'value': self.value,
            }

    def __init__(self, t):
        super().__init__('')
        self.clang_type = t
        self.clang_kind = t.kind
        self.spelling = t.spelling
        self.size = t.get_size()
        declaration = t.get_declaration()
        base = t
        if t.spelling in BUILTIN_C_INTS:
            self.kind = 'int'
        elif t.spelling in BUILTIN_C_UINTS:
            self.kind = 'uint'
        elif t.kind == clang.TypeKind.RECORD and t.spelling not in BUILTIN_C_DEFINITIONS:
            self.processed_types[declaration.hash] = self  # mark early to avoid recursion
            m = UNION_STRUCT_NAME_RE.match(t.spelling)
            if m:
                union_or_struct = m.group(1)
                self.anonymous = bool(ANONYMOUS_SUB_RE.search(m.group(2)))
                self.name = ANONYMOUS_SUB_RE.sub('_', m.group(2))
                self.spelling = '{} {}'.format(union_or_struct, self.name)
            else:
                assert declaration.kind in (clang.CursorKind.STRUCT_DECL, clang.CursorKind.UNION_DECL)
                union_or_struct = ('struct'
                                   if declaration.kind == clang.CursorKind.STRUCT_DECL
                                   else 'union')
                self.anonymous = False
                self.name = t.spelling
            self.kind = union_or_struct
            self.fields = [Type.Field(f) for f in t.get_fields()]
            self.opaque = not self.fields
            self.type_declarations[declaration.hash] = self
        elif t.kind == clang.TypeKind.ENUM:
            self.processed_types[declaration.hash] = self  # mark early to avoid recursion
            m = ENUM_NAME_RE.match(t.spelling)
            if m:
                self.anonymous = bool(ANONYMOUS_SUB_RE.search(m.group(1)))
                self.name = ANONYMOUS_SUB_RE.sub('_', m.group(1))
                self.spelling = "enum {}".format(self.name)
            else:
                self.anonymous = False
                self.name = t.spelling
            self.kind = 'enum'
            self.type = Type.from_clang(declaration.enum_type)
            self.values = [Type.EnumValue(c.spelling, c.enum_value) for c in declaration.get_children()]
            self.type_declarations[declaration.hash] = self
        elif t.kind == clang.TypeKind.TYPEDEF and t.spelling not in BUILTIN_C_DEFINITIONS:
            self.processed_types[declaration.hash] = self  # mark early to avoid recursion
            self.kind = 'typedef'
            self.name = t.get_typedef_name()
            self.type = Type.from_clang(declaration.underlying_typedef_type)
            self.type_declarations[declaration.hash] = self
        elif t.kind == clang.TypeKind.POINTER:
            self.kind = 'pointer'
            self.array, base = self.process_pointer_or_array(t)
            self.element_type = Type.from_clang(base)
            self.spelling = self.spelling.replace(base.spelling, self.element_type.spelling)
            if base.kind in (clang.TypeKind.FUNCTIONPROTO, clang.TypeKind.FUNCTIONNOPROTO):
                self.function = self.element_type
        elif t.kind in (clang.TypeKind.CONSTANTARRAY, clang.TypeKind.INCOMPLETEARRAY):
            self.kind = 'array'
            self.array, base = self.process_pointer_or_array(t)
            self.element_type = Type.from_clang(base)
            self.spelling = self.spelling.replace(base.spelling, self.element_type.spelling)
        elif t.kind == clang.TypeKind.VECTOR:
            self.kind = 'vector'
            self.array, base = self.process_pointer_or_array(t)
            self.element_type = Type.from_clang(base)
            self.spelling = self.spelling.replace(base.spelling, self.element_type.spelling)
        elif t.kind in (clang.TypeKind.FUNCTIONPROTO, clang.TypeKind.FUNCTIONNOPROTO):
            self.kind = 'function'
            self.return_type = Type.from_clang(t.get_result())
            self.arguments = [Type.from_clang(a) for a in t.argument_types()]
            self.variadic = t.kind == clang.TypeKind.FUNCTIONPROTO and t.is_function_variadic()
        elif t.kind == clang.TypeKind.VOID:
            self.kind = 'void'
        elif t.kind == clang.TypeKind.BOOL:
            self.kind = 'bool'
        elif t.kind in (clang.TypeKind.CHAR_U, clang.TypeKind.UCHAR, clang.TypeKind.CHAR16, clang.TypeKind.CHAR32, clang.TypeKind.CHAR_S, clang.TypeKind.SCHAR, clang.TypeKind.WCHAR):
            self.kind = 'char'
        elif t.kind in (clang.TypeKind.USHORT, clang.TypeKind.UINT, clang.TypeKind.ULONG, clang.TypeKind.ULONGLONG, clang.TypeKind.UINT128):
            self.kind = 'uint'
        elif t.kind in (clang.TypeKind.SHORT, clang.TypeKind.INT, clang.TypeKind.LONG, clang.TypeKind.LONGLONG, clang.TypeKind.INT128):
            self.kind = 'int'
        elif t.kind in (clang.TypeKind.FLOAT, clang.TypeKind.DOUBLE, clang.TypeKind.LONGDOUBLE, clang.TypeKind.HALF, clang.TypeKind.FLOAT128):
            self.kind = 'float'
        else:
            assert t.kind != clang.TypeKind.INVALID, "FIXME: invalid type"

        self.const = base.is_const_qualified()
        self.volatile = base.is_volatile_qualified()
        self.restrict = base.is_restrict_qualified()
        self.base = base_type(base.spelling if base is not t else self.spelling)

    def root(self):
        t = self
        while t.kind == 'typedef':
            t = t.type
        return t

    def is_integral(self):
        return self.kind in ('uint', 'int')

    def is_unsigned(self):
        return self.kind == 'uint'

    def is_floating_point(self):
        return self.kind == 'float'

    def is_string(self):
        return self.kind == 'pointer' and len(self.array) == 1 and self.element_type.kind == 'char'

    def is_pointer(self):
        return self.kind == 'pointer'

    def remove_pointer(self):
        if self.kind == 'pointer':
            return Type.from_clang(self.clang_type.get_pointee())
        return self

    def is_array(self):
        return self.kind == 'array'

    def remove_array(self):
        if self.kind == 'pointer':
            return Type.from_clang(self.clang_type.get_pointee())
        elif self.kind in ('array', 'vector'):
            return Type.from_clang(self.clang_type.element_type)
        return self

    def is_function_pointer(self):
        return self.kind == 'pointer' and hasattr(self, 'function')

    def is_variadic(self):
        return getattr(self, 'variadic', False)

    def is_anonymous(self):
        return getattr(self, 'anonymous', False)

    def to_dict(self, is_declaration=False):
        result = {
            'kind': self.kind,
            'spelling': self.spelling,
            'size': self.size,
        }
        if is_declaration:
            if hasattr(self, 'fields'):
                result['fields'] = [f.to_dict() for f in self.fields]
            if hasattr(self, 'values'):
                result['values'] = [v.to_dict() for v in self.values]
        else:
            result['base'] = self.base
        if hasattr(self, 'name'):
            result['name'] = self.name
        if hasattr(self, 'type'):
            result['type'] = self.type.to_dict()
        if hasattr(self, 'function'):
            result['function'] = self.function.to_dict()
        if hasattr(self, 'return_type'):
            result['return_type'] = self.return_type.to_dict()
        if hasattr(self, 'arguments'):
            result['arguments'] = [a.to_dict() for a in self.arguments]
        if hasattr(self, 'array'):
            result['array'] = self.array
        if self.is_anonymous():
            result['anonymous'] = True
        if self.is_variadic():
            result['variadic'] = True
        if self.const:
            result['const'] = True
        if self.volatile:
            result['volatile'] = True
        if self.restrict:
            result['restrict'] = True
        return result

    @classmethod
    def from_clang(cls, t):
        if t.kind == clang.TypeKind.AUTO:
            # process actual type
            t = t.get_canonical()
        if t.kind == clang.TypeKind.ELABORATED:
            # just process inner type
            t = t.get_named_type()
        declaration = t.get_declaration()
        the_type = cls.processed_types.get(declaration.hash)
        if not the_type:
            the_type = Type(t)
        return the_type

    @staticmethod
    def process_pointer_or_array(t):
        result = []
        while t:
            if t.kind == clang.TypeKind.POINTER:
                result.append('*')
                t = t.get_pointee()
            elif t.kind in (clang.TypeKind.CONSTANTARRAY, clang.TypeKind.VECTOR):
                result.append(t.element_count)
                t = t.element_type
            elif t.kind == clang.TypeKind.INCOMPLETEARRAY:
                result.append('*')
                t = t.element_type
            else:
                break
        return result, t


class Variable(Definition):
    def __init__(self, cursor):
        super().__init__('var')
        self.name = cursor.spelling
        self.type = Type.from_clang(cursor.type)

    def to_dict(self, is_declaration=True):
        return {
            'kind': self.kind,
            'name': self.name,
            'type': self.type.to_dict(),
        }


class Constant(Definition):
    def __init__(self, cursor, name):
        super().__init__('const')
        self.name = name
        self.type = Type.from_clang(cursor.type)

    def to_dict(self, is_declaration=True):
        return {
            'kind': self.kind,
            'name': self.name,
            'type': self.type.to_dict(),
        }

class AnonymousEnum(Definition):
    def __init__(self, cursor, size):
        super().__init__('const')
        self.name = cursor.name
        self.value = cursor.value
        self.size = size

    def to_dict(self, is_declaration=True):
        d = {
            'kind': self.kind,
            'name': self.name,
            'value': self.value,
            'size': self.size
        }
        return d

class Function(Definition):
    class Argument:
        def __init__(self, cursor):
            self.name = cursor.spelling
            self.type = Type.from_clang(cursor.type)

        def to_dict(self):
            return {
                'name': self.name,
                'type': self.type.to_dict(),
            }

    def __init__(self, cursor):
        super().__init__('function')
        self.name = cursor.spelling
        self.return_type = Type.from_clang(cursor.type.get_result())
        self.arguments = [Function.Argument(a) for a in cursor.get_arguments()]
        self.variadic = cursor.type.kind == clang.TypeKind.FUNCTIONPROTO and cursor.type.is_function_variadic()

    def to_dict(self, is_declaration=True):
        d = {
            'kind': self.kind,
            'name': self.name,
            'return_type': self.return_type.to_dict(),
            'arguments': [a.to_dict() for a in self.arguments]
        }
        if self.variadic:
            d['variadic'] = True
        return d



TYPE_COMPONENTS_RE = re.compile(r'([^(]*\(\**|[^[]*)(.*)')
def typed_declaration(spelling, identifier):
    """
    Utility to form a typed declaration from a C type and identifier.
    This correctly handles array lengths and function pointer arguments.
    """
    m = TYPE_COMPONENTS_RE.match(spelling)
    return '{base_or_return_type}{maybe_space}{identifier}{maybe_array_or_arguments}'.format(
        base_or_return_type=m.group(1),
        maybe_space='' if m.group(2) else ' ',
        identifier=identifier,
        maybe_array_or_arguments=m.group(2) or '',
    )


BASE_TYPE_RE = re.compile(r'(?:\b(?:const|volatile|restrict)\b\s*)*(([^[*(]+)(\(?).*)')
def base_type(spelling):
    """
    Get the base type from spelling, removing const/volatile/restrict specifiers and pointers.
    """
    m = BASE_TYPE_RE.match(spelling)
    if not m:
        print("FIXME: ", spelling)
    return (m.group(1) if m.group(3) else m.group(2)).strip() if m else spelling

class Visitor:
    def __init__(self, header_path, clang_path=None, libclang_path=None, clang_args=[], include_headers=[], include_patterns=[], exclude_patterns=[], type_objects=False, skip_defines=False, language="c"):
        if libclang_path:
            if os.path.exists(libclang_path):
                try:
                    if os.path.isfile(libclang_path):
                        clang.Config.set_library_file(libclang_path)
                    else:
                        clang.Config.set_library_path(libclang_path)
                except clang.LibclangError as e: # Failed to load library
                    print(f"ERROR: {str(e)}")
                except: # Error occurs when library is already loaded, skip
                    pass
            else:
                print(f"ERROR! Path \"{libclang_path}\" doesn't exist")
                sys.exit(1)
        self.defs = []
        self.typedefs = {}
        self.index = clang.Index.create()
        self.parsed_headers = set()
        self.potential_constants = []
        self.clang_path = clang_path if clang_path else "clang"
        def compile_all(patterns, default=None):
            return [re.compile(p) for p in patterns] or default
        self.include_patterns = compile_all(include_patterns)
        self.exclude_patterns = compile_all(exclude_patterns)
        self.language = language

        with tempfile.NamedTemporaryFile() as ast_file:
            clang_stdout = self.run_clang(header_path, ['-emit-ast'] + clang_args)
            ast_file.write(clang_stdout)
            tu = self.index.read(ast_file.name)

        include_headers = compile_all(include_headers, default=[MATCH_ALL_RE])
        self.type_objects = type_objects
        self.skip_defines = skip_defines
        for cursor in tu.cursor.get_children():
            self.process(cursor, include_headers)
        type_defs = [t for t in Type.type_declarations.values() if self.test_definition(t.name)]
        self.defs = type_defs + self.defs
        if not skip_defines:
            self.process_marked_macros(header_path, clang_args)
        self._definitions = [d.to_dict(is_declaration=True) for d in self.defs]
        self.typedefs = { x["name"]: x["type"]["spelling"] for x in self.typedef_definitions() }

    def run_clang(self, header_path, clang_args=[], source=None):
        clang_cmd = [self.clang_path]
        clang_cmd.extend(clang_args)
        clang_cmd.extend(('-o', '-'))
        if source:
            clang_cmd.append('-')
        else:
            clang_cmd.append(header_path)
        stderr = subprocess.DEVNULL if source else None
        # print(clang_cmd)
        clang_result = subprocess.run(clang_cmd, input=source, stdout=subprocess.PIPE, stderr=stderr)
        if clang_result.returncode != 0:
            raise CompilationError(clang_result.stderr)
        return clang_result.stdout

    def test_definition(self, def_name):
        if self.exclude_patterns:
            if any(pattern.search(def_name) for pattern in self.exclude_patterns):
                if self.include_patterns:
                    return any(pattern.search(def_name) for pattern in self.include_patterns)
                else:
                    return False
            else:
                return True
        else:
            return True

    def process(self, cursor, include_patterns):
        try:
            cwd = Path.cwd()
            filepath = PurePath(cursor.location.file.name)
            if filepath.is_relative_to(cwd):
                filepath = filepath.relative_to(cwd)
            filepath = str(filepath)
            if not any(pattern.search(filepath) for pattern in include_patterns):
                return
            if not self.skip_defines and filepath not in self.parsed_headers:
                self.mark_macros(filepath)
                self.parsed_headers.add(filepath)
        except AttributeError:
            return

        if cursor.is_anonymous() and cursor.kind == clang.CursorKind.ENUM_DECL:
            t = Type.from_clang(cursor.type)
            for v in t.values:
                if self.test_definition(v.name):
                    self.defs.append(AnonymousEnum(v, t.size))
        else:
            if not self.test_definition(cursor.spelling):
                return

        if cursor.kind == clang.CursorKind.VAR_DECL:
            new_definition = Variable(cursor)
            self.defs.append(new_definition)
        if cursor.kind in (clang.CursorKind.TYPEDEF_DECL, clang.CursorKind.ENUM_DECL, clang.CursorKind.STRUCT_DECL, clang.CursorKind.UNION_DECL):
            self.process_type(cursor.type)
        elif cursor.kind == clang.CursorKind.FUNCTION_DECL:
            self.defs.append(Function(cursor))

    def process_type(self, t):
        new_declaration = Type.from_clang(t)

    def mark_macros(self, filepath):
        with open(filepath) as f:
            for line in f:
                m = DEFINE_RE.match(line)
                if m:
                    self.potential_constants.append(m.group(1))

    def process_marked_macros(self, header_path, clang_args=[]):
        with tempfile.NamedTemporaryFile(suffix='.pch') as pch_file:
            clang_stdout = self.run_clang(header_path, ['-x', 'c++-header' if self.language in ["c++", "cplusplus"] else 'c-header', '-Xclang', '-emit-pch'] + clang_args)
            pch_file.write(clang_stdout)

            lang = self.language
            match self.language:
                case "c":
                    lang = "c"
                case "objc" | "objective-c":
                    lang = "objective-c"
                case "c++" | "cplusplus":
                    lang = "c++"
                case _:
                    raise ValueError(f"Unknown language `{lang}`")
            clang_args = ['-x', lang, '-emit-ast', '-include-pch', pch_file.name] + clang_args
            for identifier in self.potential_constants:
                if not self.test_definition(identifier):
                    continue
                try:
                    source = '#include "{}"\nconst auto __value = {};'.format(header_path, identifier)
                    with tempfile.NamedTemporaryFile() as ast_file:
                        clang_stdout = self.run_clang(header_path, clang_args, source.encode('utf-8'))
                        ast_file.write(clang_stdout)
                        tu = self.index.read(ast_file.name)
                    for cursor in tu.cursor.get_children():
                        if cursor.kind == clang.CursorKind.VAR_DECL and cursor.spelling == '__value':
                            self.defs.append(Constant(cursor, identifier))
                except CompilationError as ex:
                    # this macro is not a const value, skip
                    pass

    def all_definitions(self):
        return self._definitions

    def find_definitions_by(self, key, value):
        return [x for x in self._definitions if x[key] == value]

    def definitions_by_kind(self, kind):
        return self.find_definitions_by('kind', kind)

    def typedef_definitions(self):
        return self.definitions_by_kind('typedef')

    def enum_definitions(self):
        return self.definitions_by_kind('enum')

    def struct_definitions(self):
        return self.definitions_by_kind('struct')

    def function_definitions(self):
        return self.definitions_by_kind('function')

    def has_typedef(self, name):
        return name in self.typedefs.keys()

    def get_typedef(self, name):
        return self.typedefs[name] if self.has_typedef(name) else None


def defs(*args, **kwargs):
    return Visitor(*args, **kwargs).all_definitions()

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Serialise C headers to Lua C bindings w/ python + libclang!")
    parser.add_argument("headers", metavar="HEADERS", type=str, nargs="+",
                        help="Path to header file(s) to process")
    parser.add_argument("-c", "--clang", metavar="PATH", type=str,
                        help="Specify the path to `clang`")
    parser.add_argument("-a", "--xargs", metavar="ARGS", type=str, nargs="+",
                        help="Pass arguments through to clang")
    parser.add_argument("-L", "--lib", metavar="PATH", type=str,
                        help="Specify the path to clang library or directory")
    parser.add_argument("-i", "--include-headers", metavar="FILTER", type=str, nargs="+",
                        help="Only process headers with names that match any of the given regex patterns. Matches are tested using `re.search`, so patterns are not anchored by default. This may be used to avoid processing standard headers and dependencies headers.")
    parser.add_argument("-d", "--include-definitions", metavar="FILTER", type=str, nargs="+",
                        help="Only include definitions that match given regex filters")
    parser.add_argument("-D", "--exclude-definitions", metavar="FILTER", type=str, nargs="+",
                        help="Exclude any definitions that match given regex filters (NOTE: Overwriten by `--include-definitions` option)")
    parser.add_argument("-o", "--output", metavar="PATH", type=str,
                        help="Specify the file or directory to dump JSON to. (default: dump to stdout)")
    parser.add_argument("-w", "--writeover", action="store_true",
                        help="If the output destination exists, overwrite it.")
    parser.add_argument("-s", "--skip-defines", action="store_true",
                        help="By default, cj will try compiling object-like macros looking for constants, which may take long if your header has lots of them. Use this flag to skip this step")
    parser.add_argument("-t", "--type-objects", action="store_true",
                        help="Output type objects instead of simply the type spelling string")
    parser.add_argument("-m", "--minified", action="store_true",
                        help="Output minified JSON instead of using 0 space indentations")
    parser.add_argument("-x", "--language", action="store_true",
                        help="Set `-x {lang}` when running clang")
    args = parser.parse_args()

    for header in args.headers:
        if not header:
            continue
        if not os.path.exists(header) or not os.path.isfile(header):
            print(f"ERROR! Path \"{header}\" doesn't exist")
            continue
        visitor = Visitor(header,
            clang_path=args.clang if args.clang else None,
            clang_args=[x.strip() for x in args.xargs] if args.xargs else [],
            libclang_path=args.lib,
            include_patterns=args.include_definitions if args.include_definitions else [],
            exclude_patterns=args.exclude_definitions if args.exclude_definitions else [],
            type_objects=args.type_objects,
            skip_defines=args.skip_defines,
            language=args.language if args.language else "c")
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)
        json = json.dumps(visitor.all_definitions(),
                            indent=None if args.minified else 4,
                            separators=(',', ':') if args.minified else None)
        if args.output:
            if os.path.exists(args.output):
                if os.path.isfile(args.output):
                    if not args.writeover:
                        print(f"ERROR! File already exists at `{args.output}`, use -w/--writeover to overwrite file")
                else:
                    parts = header.split("/")
                    folder = args.output[:-1] if args.output[-1] == '/' else args.output
                    name = ".".join(parts[-1].split(".")[:-1])
                    args.output = f"{folder}/{name}.json"
                    print(args.output)
                    if (os.path.exists(args.output) and os.path.isfile(args.output)) and not args.writeover:
                        print(f"ERROR! File already exists at `{args.output}`, use -w/--writeover to overwrite file")
            with open(args.output, "w") as fh:
                fh.write(json)
        else:
            print(json, end='')
