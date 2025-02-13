# Copyright 2019 The meson development team
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Abstractions to simplify compilers that implement an MSVC compatible
interface.
"""

import abc
import os
import typing

from ... import mesonlib
from ... import mlog

if typing.TYPE_CHECKING:
    from ...environment import Environment

vs32_instruction_set_args = {
    'mmx': ['/arch:SSE'], # There does not seem to be a flag just for MMX
    'sse': ['/arch:SSE'],
    'sse2': ['/arch:SSE2'],
    'sse3': ['/arch:AVX'], # VS leaped from SSE2 directly to AVX.
    'sse41': ['/arch:AVX'],
    'sse42': ['/arch:AVX'],
    'avx': ['/arch:AVX'],
    'avx2': ['/arch:AVX2'],
    'neon': None,
}  # typing.Dicst[str, typing.Optional[typing.List[str]]]

# The 64 bit compiler defaults to /arch:avx.
vs64_instruction_set_args = {
    'mmx': ['/arch:AVX'],
    'sse': ['/arch:AVX'],
    'sse2': ['/arch:AVX'],
    'sse3': ['/arch:AVX'],
    'ssse3': ['/arch:AVX'],
    'sse41': ['/arch:AVX'],
    'sse42': ['/arch:AVX'],
    'avx': ['/arch:AVX'],
    'avx2': ['/arch:AVX2'],
    'neon': None,
}  # typing.Dicst[str, typing.Optional[typing.List[str]]]

msvc_buildtype_args = {
    'plain': [],
    'debug': ["/ZI", "/Ob0", "/Od", "/RTC1"],
    'debugoptimized': ["/Zi", "/Ob1"],
    'release': ["/Ob2", "/Gw"],
    'minsize': ["/Zi", "/Gw"],
    'custom': [],
}  # type: typing.Dict[str, typing.List[str]]

msvc_optimization_args = {
    '0': [],
    'g': ['/O0'],
    '1': ['/O1'],
    '2': ['/O2'],
    '3': ['/O2'],
    's': ['/O1'], # Implies /Os.
}  # type: typing.Dict[str, typing.List[str]]

msvc_debug_args = {
    False: [],
    True: []  # Fixme!
}  # type: typing.Dict[bool, typing.List[str]]


class VisualStudioLikeCompiler(metaclass=abc.ABCMeta):

    """A common interface for all compilers implementing an MSVC-style
    interface.

    A number of compilers attempt to mimic MSVC, with varying levels of
    success, such as Clang-CL and ICL (the Intel C/C++ Compiler for Windows).
    This classs implements as much common logic as possible.
    """

    std_warn_args = ['/W3']
    std_opt_args = ['/O2']
    # XXX: this is copied in this patch only to avoid circular dependencies
    #ignore_libs = unixy_compiler_internal_libs
    ignore_libs = ('m', 'c', 'pthread', 'dl', 'rt', 'execinfo')
    internal_libs = ()

    crt_args = {
        'none': [],
        'md': ['/MD'],
        'mdd': ['/MDd'],
        'mt': ['/MT'],
        'mtd': ['/MTd'],
    }  # type: typing.Dict[str, typing.List[str]]

    # /showIncludes is needed for build dependency tracking in Ninja
    # See: https://ninja-build.org/manual.html#_deps
    always_args = ['/nologo', '/showIncludes']
    warn_args = {
        '0': ['/W1'],
        '1': ['/W2'],
        '2': ['/W3'],
        '3': ['/W4'],
    }  # type: typing.Dict[str, typing.List[str]]

    def __init__(self, target: str):
        self.base_options = ['b_pch', 'b_ndebug', 'b_vscrt'] # FIXME add lto, pgo and the like
        self.target = target
        self.is_64 = ('x64' in target) or ('x86_64' in target)
        # do some canonicalization of target machine
        if 'x86_64' in target:
            self.machine = 'x64'
        elif '86' in target:
            self.machine = 'x86'
        else:
            self.machine = target
        self.linker.machine = self.machine

    # Override CCompiler.get_always_args
    def get_always_args(self) -> typing.List[str]:
        return self.always_args

    def get_buildtype_args(self, buildtype: str) -> typing.List[str]:
        args = msvc_buildtype_args[buildtype]
        if self.id == 'msvc' and mesonlib.version_compare(self.version, '<18.0'):
            args = [arg for arg in args if arg != '/Gw']
        return args

    def get_pch_suffix(self) -> str:
        return 'pch'

    def get_pch_name(self, header: str) -> str:
        chopped = os.path.basename(header).split('.')[:-1]
        chopped.append(self.get_pch_suffix())
        pchname = '.'.join(chopped)
        return pchname

    def get_pch_use_args(self, pch_dir: str, header: str) -> typing.List[str]:
        base = os.path.basename(header)
        if self.id == 'clang-cl':
            base = header
        pchname = self.get_pch_name(header)
        return ['/FI' + base, '/Yu' + base, '/Fp' + os.path.join(pch_dir, pchname)]

    def get_preprocess_only_args(self) -> typing.List[str]:
        return ['/EP']

    def get_compile_only_args(self) -> typing.List[str]:
        return ['/c']

    def get_no_optimization_args(self) -> typing.List[str]:
        return ['/Od']

    def get_output_args(self, target: str) -> typing.List[str]:
        if target.endswith('.exe'):
            return ['/Fe' + target]
        return ['/Fo' + target]

    def get_optimization_args(self, optimization_level: str) -> typing.List[str]:
        return msvc_optimization_args[optimization_level]

    def get_debug_args(self, is_debug: bool) -> typing.List[str]:
        return msvc_debug_args[is_debug]

    def get_dependency_gen_args(self, outtarget: str, outfile: str) -> typing.List[str]:
        return []

    def linker_to_compiler_args(self, args: typing.List[str]) -> typing.List[str]:
        return ['/link'] + args

    def get_gui_app_args(self, value: bool) -> typing.List[str]:
        # the default is for the linker to guess the subsystem based on presence
        # of main or WinMain symbols, so always be explicit
        if value:
            return ['/SUBSYSTEM:WINDOWS']
        else:
            return ['/SUBSYSTEM:CONSOLE']

    def get_pic_args(self) -> typing.List[str]:
        return [] # PIC is handled by the loader on Windows

    def gen_vs_module_defs_args(self, defsfile: str) -> typing.List[str]:
        if not isinstance(defsfile, str):
            raise RuntimeError('Module definitions file should be str')
        # With MSVC, DLLs only export symbols that are explicitly exported,
        # so if a module defs file is specified, we use that to export symbols
        return ['/DEF:' + defsfile]

    def gen_pch_args(self, header: str, source: str, pchname: str) -> typing.Tuple[str, typing.List[str]]:
        objname = os.path.splitext(pchname)[0] + '.obj'
        return objname, ['/Yc' + header, '/Fp' + pchname, '/Fo' + objname]

    def gen_import_library_args(self, implibname: str) -> typing.List[str]:
        "The name of the outputted import library"
        return ['/IMPLIB:' + implibname]

    def openmp_flags(self) -> typing.List[str]:
        return ['/openmp']

    # FIXME, no idea what these should be.
    def thread_flags(self, env: 'Environment') -> typing.List[str]:
        return []

    @classmethod
    def unix_args_to_native(cls, args: typing.List[str]) -> typing.List[str]:
        result = []
        for i in args:
            # -mms-bitfields is specific to MinGW-GCC
            # -pthread is only valid for GCC
            if i in ('-mms-bitfields', '-pthread'):
                continue
            if i.startswith('-L'):
                i = '/LIBPATH:' + i[2:]
            # Translate GNU-style -lfoo library name to the import library
            elif i.startswith('-l'):
                name = i[2:]
                if name in cls.ignore_libs:
                    # With MSVC, these are provided by the C runtime which is
                    # linked in by default
                    continue
                else:
                    i = name + '.lib'
            # -pthread in link flags is only used on Linux
            elif i == '-pthread':
                continue
            result.append(i)
        return result

    def get_werror_args(self) -> typing.List[str]:
        return ['/WX']

    def get_include_args(self, path: str, is_system: bool) -> typing.List[str]:
        if path == '':
            path = '.'
        # msvc does not have a concept of system header dirs.
        return ['-I' + path]

    def compute_parameters_with_absolute_paths(self, parameter_list: typing.List[str], build_dir: str) -> typing.List[str]:
        for idx, i in enumerate(parameter_list):
            if i[:2] == '-I' or i[:2] == '/I':
                parameter_list[idx] = i[:2] + os.path.normpath(os.path.join(build_dir, i[2:]))
            elif i[:9] == '/LIBPATH:':
                parameter_list[idx] = i[:9] + os.path.normpath(os.path.join(build_dir, i[9:]))

        return parameter_list

    # Visual Studio is special. It ignores some arguments it does not
    # understand and you can't tell it to error out on those.
    # http://stackoverflow.com/questions/15259720/how-can-i-make-the-microsoft-c-compiler-treat-unknown-flags-as-errors-rather-t
    def has_arguments(self, args: typing.List[str], env: 'Environment', code, mode: str) -> typing.Tuple[bool, bool]:
        warning_text = '4044' if mode == 'link' else '9002'
        if self.id == 'clang-cl' and mode != 'link':
            args = args + ['-Werror=unknown-argument']
        with self._build_wrapper(code, env, extra_args=args, mode=mode) as p:
            if p.returncode != 0:
                return False, p.cached
            return not(warning_text in p.stde or warning_text in p.stdo), p.cached

    def get_compile_debugfile_args(self, rel_obj: str, pch: bool = False) -> typing.List[str]:
        pdbarr = rel_obj.split('.')[:-1]
        pdbarr += ['pdb']
        args = ['/Fd' + '.'.join(pdbarr)]
        # When generating a PDB file with PCH, all compile commands write
        # to the same PDB file. Hence, we need to serialize the PDB
        # writes using /FS since we do parallel builds. This slows down the
        # build obviously, which is why we only do this when PCH is on.
        # This was added in Visual Studio 2013 (MSVC 18.0). Before that it was
        # always on: https://msdn.microsoft.com/en-us/library/dn502518.aspx
        if pch and self.id == 'msvc' and mesonlib.version_compare(self.version, '>=18.0'):
            args = ['/FS'] + args
        return args

    def get_instruction_set_args(self, instruction_set: str) -> typing.Optional[typing.List[str]]:
        if self.is_64:
            return vs64_instruction_set_args.get(instruction_set, None)
        if self.id == 'msvc' and self.version.split('.')[0] == '16' and instruction_set == 'avx':
            # VS documentation says that this exists and should work, but
            # it does not. The headers do not contain AVX intrinsics
            # and the can not be called.
            return None
        return vs32_instruction_set_args.get(instruction_set, None)

    def _calculate_toolset_version(self, version: int) -> typing.Optional[str]:
        if version < 1310:
            return '7.0'
        elif version < 1400:
            return '7.1' # (Visual Studio 2003)
        elif version < 1500:
            return '8.0' # (Visual Studio 2005)
        elif version < 1600:
            return '9.0' # (Visual Studio 2008)
        elif version < 1700:
            return '10.0' # (Visual Studio 2010)
        elif version < 1800:
            return '11.0' # (Visual Studio 2012)
        elif version < 1900:
            return '12.0' # (Visual Studio 2013)
        elif version < 1910:
            return '14.0' # (Visual Studio 2015)
        elif version < 1920:
            return '14.1' # (Visual Studio 2017)
        elif version < 1930:
            return '14.2' # (Visual Studio 2019)
        mlog.warning('Could not find toolset for version {!r}'.format(self.version))
        return None

    def get_toolset_version(self) -> typing.Optional[str]:
        if self.id == 'clang-cl':
            # I have no idea
            return '14.1'

        # See boost/config/compiler/visualc.cpp for up to date mapping
        try:
            version = int(''.join(self.version.split('.')[0:2]))
        except ValueError:
            return None
        return self._calculate_toolset_version(version)

    def get_default_include_dirs(self) -> typing.List[str]:
        if 'INCLUDE' not in os.environ:
            return []
        return os.environ['INCLUDE'].split(os.pathsep)

    def get_crt_compile_args(self, crt_val: str, buildtype: str) -> typing.List[str]:
        if crt_val in self.crt_args:
            return self.crt_args[crt_val]
        assert(crt_val == 'from_buildtype')
        # Match what build type flags used to do.
        if buildtype == 'plain':
            return []
        elif buildtype == 'debug':
            return self.crt_args['mdd']
        elif buildtype == 'debugoptimized':
            return self.crt_args['md']
        elif buildtype == 'release':
            return self.crt_args['md']
        elif buildtype == 'minsize':
            return self.crt_args['md']
        else:
            assert(buildtype == 'custom')
            raise mesonlib.EnvironmentException('Requested C runtime based on buildtype, but buildtype is "custom".')

    def has_func_attribute(self, name: str, env: 'Environment') -> typing.Tuple[bool, bool]:
        # MSVC doesn't have __attribute__ like Clang and GCC do, so just return
        # false without compiling anything
        return name in ['dllimport', 'dllexport'], False

    def get_argument_syntax(self) -> str:
        return 'msvc'
