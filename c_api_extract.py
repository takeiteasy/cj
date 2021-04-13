"""
Usage:
  c_api_extract <input> [-p <pattern>...] [options] [-- <clang_args>...]
  c_api_extract -h

Options:
  -h, --help                           Show this help message.
  -p <pattern>, --pattern=<pattern>    Only process headers with names that match any of the given regex patterns.
                                       Matches are tested using `re.search`, so patterns are not anchored by default.
  --compact                            Output minified JSON instead of using 2 space indentations.
  --source                             Include declarations verbatim source code from header.
  --size                               Include "size" property with types `sizeof` in bytes.
                                       This may be used to avoid processing standard headers and dependencies headers.
"""

import json
import re
from signal import signal, SIGPIPE, SIG_DFL
import subprocess
import tempfile

from docopt import docopt
import clang.cindex as clang


__version__ = '0.4.1'

class CompilationError(Exception):
    pass


class Visitor:
    UNION_STRUCT_NAME_RE = re.compile(r'(union|struct)\s+(.+)')
    ENUM_NAME_RE = re.compile(r'enum\s+(.+)')
    MATCH_ALL_RE = re.compile('.*')

    def __init__(self):
        self.defs = []
        self.typedefs = {}
        self.index = clang.Index.create()
        self.types = {}

    def parse_header(self, header_path, clang_args=[], allowed_patterns=[],
                     include_source=False, include_size=False):
        allowed_patterns = [re.compile(p) for p in allowed_patterns] or [Visitor.MATCH_ALL_RE]
        clang_cmd = ['clang', '-emit-ast', header_path, '-o', '-'] + clang_args
        clang_result = subprocess.run(clang_cmd, stdout=subprocess.PIPE)
        if clang_result.returncode != 0:
            raise CompilationError
        with tempfile.NamedTemporaryFile(suffix=".pch") as ast_file:
            ast_file.write(clang_result.stdout)
            tu = self.index.read(ast_file.name)

        self.include_source = include_source
        self.include_size = include_size
        self.open_files = {}
        for cursor in tu.cursor.get_children():
            self.process(cursor, allowed_patterns)
        del self.open_files

    def add_typedef(self, cursor, ty):
        self.typedefs[cursor.hash] = ty

    def get_typedef(self, cursor):
        return self.typedefs.get(cursor.underlying_typedef_type.get_declaration().hash)

    def source_for_cursor(self, cursor):
        if not self.include_source:
            return None
        source_range = cursor.extent
        start = source_range.start
        end = source_range.end
        filename = (start.file or end.file or cursor.location.file).name
        if filename not in self.open_files:
            self.open_files[filename] = open(filename, 'r')
        f = self.open_files[filename]
        f.seek(start.offset)
        return f.read(end.offset - start.offset)

    def process(self, cursor, allowed_patterns):
        try:
            filename = cursor.location.file.name
            if not any(pattern.search(filename) for pattern in allowed_patterns):
                return
        except AttributeError:
            return

        if cursor.kind == clang.CursorKind.VAR_DECL:
            new_definition = {
                'kind': 'var',
                'name': cursor.spelling,
                'type': self.process_type(cursor.type),
            }
            if self.include_source:
                new_definition['source'] = self.source_for_cursor(cursor)
            self.defs.append(new_definition)
        elif cursor.kind == clang.CursorKind.TYPEDEF_DECL:
            self.process_type(cursor.type)
        elif cursor.kind == clang.CursorKind.ENUM_DECL:
            self.process_type(cursor.type)
        elif cursor.kind == clang.CursorKind.STRUCT_DECL:
            self.process_type(cursor.type)
        elif cursor.kind == clang.CursorKind.UNION_DECL:
            self.process_type(cursor.type)
        elif cursor.kind == clang.CursorKind.FUNCTION_DECL:
            new_definition = {
                'kind': 'function',
                'name': cursor.spelling,
                'return_type': self.process_type(cursor.type.get_result()),
                'arguments': [(self.process_type(a.type), a.spelling)
                              for a in cursor.get_arguments()],
                'variadic': cursor.type.kind == clang.TypeKind.FUNCTIONPROTO and cursor.type.is_function_variadic(),
            }
            if self.include_source:
                new_definition['source'] = self.source_for_cursor(cursor)
            self.defs.append(new_definition)

    def process_type(self, t):
        if t.kind == clang.TypeKind.ELABORATED:
            # just process inner type
            t = t.get_named_type()
        declaration = t.get_declaration()
        # print('processing ', t.kind, t.spelling)
        base = t
        spelling = t.spelling
        result = {}
        if t.kind == clang.TypeKind.RECORD:
            m = self.UNION_STRUCT_NAME_RE.match(t.spelling)
            if m:
                union_or_struct = m.group(1)
                name = re.sub('\\W', '_', m.group(2))
                spelling = '{} {}'.format(union_or_struct, name)
            else:
                assert declaration.kind in (clang.CursorKind.STRUCT_DECL, clang.CursorKind.UNION_DECL)
                union_or_struct = ('struct'
                                   if declaration.kind == clang.CursorKind.STRUCT_DECL
                                   else 'union')
                name = t.spelling
            if declaration.hash not in self.types:
                fields = []
                for field in t.get_fields():
                    fields.append([
                        self.process_type(field.type),
                        field.spelling,
                    ])
                new_definition = {
                    'kind': union_or_struct,
                    'fields': fields,
                    'name': name,
                    'spelling': spelling,
                }
                if self.include_source:
                    new_definition['source'] = self.source_for_cursor(declaration)
                if self.include_size:
                    new_definition['size'] = t.get_size()
                self.defs.append(new_definition)
                self.types[declaration.hash] = spelling
        elif t.kind == clang.TypeKind.ENUM:
            if declaration.hash not in self.types:
                m = self.ENUM_NAME_RE.match(t.spelling)
                name = m.group(1) if m else t.spelling
                new_definition = {
                    'kind': 'enum',
                    'name': name,
                    'spelling': spelling,
                    'type': self.process_type(declaration.enum_type),
                    'values': [(c.spelling, c.enum_value) for c in declaration.get_children()],
                }
                if self.include_source:
                    new_definition['source'] = self.source_for_cursor(declaration)
                self.defs.append(new_definition)
                self.types[declaration.hash] = spelling
        elif t.kind == clang.TypeKind.TYPEDEF:
            if declaration.hash not in self.types:
                new_definition = {
                    'kind': 'typedef',
                    'name': t.get_typedef_name(),
                    'typedef': self.process_type(declaration.underlying_typedef_type),
                }
                self.defs.append(new_definition)
                self.types[declaration.hash] = spelling
        elif t.kind == clang.TypeKind.POINTER:
            result['pointer'], base = self.process_pointer_or_array(t)
            spelling = base.spelling
        elif t.kind in (clang.TypeKind.CONSTANTARRAY, clang.TypeKind.INCOMPLETEARRAY):
            result['array'], base = self.process_pointer_or_array(t)
            spelling = base.spelling
        else:
            # print('WHAT? ', t.kind, spelling)
            pass
        if base.is_const_qualified():
            result['const'] = True
        if base.is_volatile_qualified():
            result['volatile'] = True
        if base.is_restrict_qualified():
            result['restrict'] = True
        result['base'] = base_type(spelling)
        if self.include_size:
            result['size'] = t.get_size()

        return result


    @classmethod
    def process_pointer_or_array(cls, t):
        result = []
        while t:
            if t.kind == clang.TypeKind.POINTER:
                result.append('*')
                t = t.get_pointee()
            elif t.kind == clang.TypeKind.CONSTANTARRAY:
                result.append(t.get_array_size())
                t = t.element_type
            elif t.kind == clang.TypeKind.INCOMPLETEARRAY:
                result.append('*')
                t = t.element_type
            else:
                break
        return result, t



type_components_re = re.compile(r'([^(]*\(\**|[^[]*)(.*)')
def typed_declaration(ty, identifier):
    """
    Utility to form a typed declaration from a C type and identifier.
    This correctly handles array lengths and function pointer arguments.
    """
    m = type_components_re.match(ty)
    return '{base_or_return_type}{maybe_space}{identifier}{maybe_array_or_arguments}'.format(
        base_or_return_type=m.group(1),
        maybe_space='' if m.group(2) else ' ',
        identifier=identifier,
        maybe_array_or_arguments=m.group(2) or '',
    )

BASE_TYPE_RE = re.compile(r'(?:\b(?:const|volatile|restrict)\b\s*)*(([^[*(]+)(\(?).*)')
def base_type(ty):
    """
    Get the base type from spelling, removing const/volatile/restrict specifiers and pointers.
    """
    m = BASE_TYPE_RE.match(ty)
    return (m.group(1) if m.group(3) else m.group(2)).strip()

def definitions_from_header(*args, **kwargs):
    visitor = Visitor()
    visitor.parse_header(*args, **kwargs)
    return visitor.defs


def main():
    opts = docopt(__doc__)
    try:
        definitions = definitions_from_header(opts['<input>'], opts['<clang_args>'],
                                              opts['--pattern'], opts['--source'],
                                              opts['--size'])
        signal(SIGPIPE, SIG_DFL)
        print(json.dumps(definitions, indent=None if opts.get('--compact') else 2))
    except CompilationError as e:
        # clang have already dumped its errors to stderr
        pass


if __name__ == '__main__':
    main()
