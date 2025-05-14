#!/usr/bin/python3

# pylint: disable=global-statement,line-too-long

"""Python-based version of b2 using pure CMake"""

import os
import shutil
import subprocess
import dataclasses
import argparse
import sys

num_cores = os.cpu_count()

BUILD_ROOT = "build_c2py"
CMAKE_PATH: str | None = None
NINJA_PATH: str | None = None
COMMAND_MODE: str | None = None
CMAKE_GENERATOR: str | None = None
NUM_JOBS: int | None = None
LIBRARY: str | None = None
UBSAN: bool | None = None
ASAN: bool | None = None
NO_CONFIGURE: bool | None = None
CXXFLAGS: str | None = None
CTESTFLAGS: str | None = None
WINSDK_VERSION: str | None = None

@dataclasses.dataclass
class BuildVariant:
    """Represents a CMake-based build"""

    address_model: str | None = None
    toolset: str | None = None
    variant: str | None = None
    cxxstd: str | None = None
    link: str | None = None

def is_windows():
    """Helper used to determine if we're running on Windows or not-Windows"""
    return os.name == 'nt'

def build_variant_to_build_dir_fragment(build_variant: BuildVariant):
    """A detail function intended to build the tree fragment"""

    build_dir = f"build_{LIBRARY}"
    if build_variant.toolset is not None:
        build_dir += f"_{build_variant.toolset}"

    if build_variant.cxxstd is not None:
        build_dir += f"_std{build_variant.cxxstd}"

    if build_variant.variant is not None:
        if build_variant.variant == 'release':
            build_dir += f"_{build_variant.variant}"

    addr = build_variant.address_model
    if addr is not None:
        if addr == '32':
            build_dir += "_x86"

    if build_variant.link is not None:
        build_dir += f"_{build_variant.link}"

    return build_dir


def build_variant_to_build_dir(build_variant: BuildVariant):
    """Translates a build variant object into a named build directory to invoke CMake in"""

    fragment = build_variant_to_build_dir_fragment(build_variant)
    return os.path.join(BUILD_ROOT, fragment)

def toolset_to_cxx_compiler(toolset):
    """Used to map toolsetes to something CMake can understand"""

    if toolset.startswith("clang-"):
        return toolset.replace("clang-", "clang++-")

    if toolset.startswith("gcc-"):
        return toolset.replace("gcc-", "g++-")

    return None

def variant_to_build_type(variant):
    """Transforms a variant to something CMake understands"""

    if variant == "debug":
        return "Debug"

    if variant == "release":
        return "Release"

    return None

def build_variant_to_cmake_config_cmd(build_variant: BuildVariant, build_dir: str, msvc_toolset):
    """Programmatically generate the proper arguments to pass to CMake's configure phase"""

    msvc_toolchains = {
        "14.0": {
            "include": [
                '-IC:"\\Program Files (x86)\\Microsoft Visual Studio 14.0\\VC\\INCLUDE"',
                '-IC:"\\Program Files (x86)\\Microsoft Visual Studio 14.0\\VC\\ATLMFC\\INCLUDE"',
                '-IC:"\\Program Files (x86)\\Windows Kits\\10\\include\\10.0.22621.0\\ucrt"',
                '-IC:"\\Program Files (x86)\\Windows Kits\\10\\include\\10.0.22621.0\\shared"',
                '-IC:"\\Program Files (x86)\\Windows Kits\\10\\include\\10.0.22621.0\\um"',
                '-IC:"\\Program Files (x86)\\Windows Kits\\10\\include\\10.0.22621.0\\winrt"',
            ],
            "libpath":[
                "/LIBPATH:\"\\Program Files (x86)\\Microsoft Visual Studio 14.0\\VC\\lib\"",
                "/LIBPATH:\"\\Program Files (x86)\\Microsoft Visual Studio 14.0\\VC\\ATLMFC\\lib\"",
                "/LIBPATH:\"\\Program Files (x86)\\Windows Kits\\10\\lib\\10.0.22621.0\\ucrt\\x86\"",
                "/LIBPATH:\"\\Program Files (x86)\\Windows Kits\\10\\lib\\10.0.22621.0\\um\\x86\"",
            ],
            "cxx": "c:/Program Files (x86)/Microsoft Visual Studio 14.0/VC/bin/cl.exe"
        },
        "14.1": {
            "include": [
                "-IC:\"\\Program Files\\Microsoft Visual Studio\\2022\\Community\\VC\\Tools\\MSVC\\14.16.27023\\include\"",
                "-IC:\"\\Program Files\\Microsoft Visual Studio\\2022\\Community\\VC\\Auxiliary\\VS\\include\"",
                "-IC:\"\\Program Files (x86)\\Windows Kits\\10\\include\\10.0.26100.0\\ucrt\"",
                "-IC:\"\\Program Files (x86)\\Windows Kits\\10\\include\\10.0.26100.0\\um\"",
                "-IC:\"\\Program Files (x86)\\Windows Kits\\10\\include\\10.0.26100.0\\shared\"",
                "-IC:\"\\Program Files (x86)\\Windows Kits\\10\\include\\10.0.26100.0\\winrt\"",
                "-IC:\"\\Program Files (x86)\\Windows Kits\\10\\include\\10.0.26100.0\\cppwinrt\"",
                "-IC:\"\\Program Files (x86)\\Windows Kits\\NETFXSDK\\4.8\\include\\um\"",
            ],
            "libpath": [
                "/LIBPATH:\"\\Program Files\\Microsoft Visual Studio\\2022\\Community\\VC\\Tools\\MSVC\\14.16.27023\\lib\\x64\"",
                "/LIBPATH:\"\\Program Files (x86)\\Windows Kits\\NETFXSDK\\4.8\\lib\\um\\x64\"",
                "/LIBPATH:\"\\Program Files (x86)\\Windows Kits\\10\\lib\\10.0.26100.0\\ucrt\\x64\"",
                "/LIBPATH:\"\\Program Files (x86)\\Windows Kits\\10\\lib\\10.0.26100.0\\um\\x64\"",
            ],
            "cxx": "/Program Files/Microsoft Visual Studio/2022/Community/VC/Tools/MSVC/14.16.27023/bin/HostX64/x64/cl.exe"
        },
        "14.4": {
            "include": [
                "-IC:\"\\Program Files\\Microsoft Visual Studio\\2022\\Community\\VC\\Tools\\MSVC\\14.44.35207\\include\"",
                "-IC:\"\\Program Files\\Microsoft Visual Studio\\2022\\Community\\VC\\Tools\\MSVC\\14.44.35207\\ATLMFC\\include\"",
                "-IC:\"\\Program Files\\Microsoft Visual Studio\\2022\\Community\\VC\\Auxiliary\\VS\\include\"",
                "-IC:\"\\Program Files (x86)\\Windows Kits\\10\\include\\10.0.26100.0\\ucrt\"",
                "-IC:\"\\Program Files (x86)\\Windows Kits\\10\\include\\10.0.26100.0\\um\"",
                "-IC:\"\\Program Files (x86)\\Windows Kits\\10\\include\\10.0.26100.0\\shared\"",
                "-IC:\"\\Program Files (x86)\\Windows Kits\\10\\include\\10.0.26100.0\\winrt\"",
                "-IC:\"\\Program Files (x86)\\Windows Kits\\10\\include\\10.0.26100.0\\cppwinrt\"",
                "-IC:\"\\Program Files (x86)\\Windows Kits\\NETFXSDK\\4.8\\include\\um\"",
            ],
            "libpath":[
                "/LIBPATH:\"\\Program Files\\Microsoft Visual Studio\\2022\\Community\\VC\\Tools\\MSVC\\14.44.35207\\ATLMFC\\lib\\x64\"",
                "/LIBPATH:\"\\Program Files\\Microsoft Visual Studio\\2022\\Community\\VC\\Tools\\MSVC\\14.44.35207\\lib\\x64\"",
                "/LIBPATH:\"\\Program Files (x86)\\Windows Kits\\NETFXSDK\\4.8\\lib\\um\\x64\"",
                "/LIBPATH:\"\\Program Files (x86)\\Windows Kits\\10\\lib\\10.0.26100.0\\ucrt\\x64\"",
                "/LIBPATH:\"\\Program Files (x86)\\Windows Kits\\10\\lib\\10.0.26100.0\\um\\x64\"",
            ],
            "cxx": "C:/Program Files/Microsoft Visual Studio/2022/Community/VC/Tools/MSVC/14.44.35207/bin/Hostx64/x64/cl.exe"
        }
    }

    fragment = build_variant_to_build_dir_fragment(build_variant)
    config_args = [
        CMAKE_PATH,
        "-S", ".",
        "-B", build_dir,
        "-DBUILD_TESTING=ON",
        f"-DBOOST_INCLUDE_LIBRARIES={LIBRARY}",
        "-DCMAKE_EXPORT_COMPILE_COMMANDS=ON",
        "-DCMAKE_CXX_VISIBILITY_PRESET=hidden",
        "-DCMAKE_VISIBILITY_INLINES_HIDDEN=ON",
        "-G", "Ninja",
        f"-DCMAKE_MAKE_PROGRAM='{NINJA_PATH}'",
        f"-DCMAKE_NINJA_OUTPUT_PATH_PREFIX={fragment}",
        "-DCMAKE_SUPPRESS_REGENERATION=ON",
    ]

    if build_variant.toolset is not None:
        if is_windows():
            toolchain = msvc_toolset
            config_args.append(f"-DCMAKE_EXE_LINKER_FLAGS_INIT=/link {' '.join(toolchain['libpath'])}")
            config_args.append(f"-DCMAKE_SHARED_LINKER_FLAGS_INIT=/link {' '.join(toolchain['libpath'])}")
            config_args.append(f"-DCMAKE_C_COMPILER={toolchain['cl']}")
            config_args.append(f"-DCMAKE_CXX_COMPILER={toolchain['cl']}")
            config_args.append(f"-DCMAKE_RC_COMPILER={toolchain['rc']}")
            config_args.append(f"-DCMAKE_MT={toolchain['mt']}")
        else:
            cxx_compiler = toolset_to_cxx_compiler(build_variant.toolset)
            config_args.append(f"-DCMAKE_C_COMPILER={build_variant.toolset}")
            config_args.append(f"-DCMAKE_CXX_COMPILER={cxx_compiler}")
    else:
        raise ValueError("a toolset must be specified")

    if build_variant.variant is not None:
        build_type = variant_to_build_type(build_variant.variant)
        config_args.append(f"-DCMAKE_BUILD_TYPE={build_type}")
    else:
        config_args.append("-DCMAKE_BUILD_TYPE=Debug")

    if build_variant.cxxstd is not None:
        cxxstd = build_variant.cxxstd
        config_args.append(f"-DCMAKE_CXX_STANDARD={cxxstd}")

    if build_variant.link == 'shared':
        config_args.append("-DBUILD_SHARED_LIBS=ON")
    elif build_variant.link == 'static':
        config_args.append("-DBUILD_SHARED_LIBS=OFF")
    elif build_variant.link is not None:
        raise ValueError(f"invalid link type value {build_variant.link}. Should be static or shared")
    else:
        config_args.append("-DBUILD_SHARED_LIBS=OFF")

    if is_windows():
        cxxflags = toolchain["include"].copy()
        cxxflags.append('/bigobj')
    else:
        cxxflags = []

    if build_variant.address_model == '32':
        if is_windows():
            raise NotImplementedError()

        cxxflags.append('-m32')

    if ASAN:
        if is_windows():
            raise NotImplementedError()

        cxxflags.append('-fsanitize=address')

    if UBSAN:
        if is_windows():
            raise NotImplementedError()

        cxxflags.append('-fsanitize=undefined')

    if len(cxxflags) > 0 or CXXFLAGS is not None:
        init_flags = ' '.join(cxxflags)
        if CXXFLAGS is not None:
            init_flags += CXXFLAGS

        config_args.append(f"-DCMAKE_CXX_FLAGS_INIT='{init_flags}'")
        config_args.append(f"-DCMAKE_C_FLAGS_INIT='{init_flags}'")

    return config_args

def build_variant_to_cmake_build_args(build_variant: BuildVariant, build_dir: str):
    """Programmatically generate the proper arguments to pass to CMake's build phase"""

    build_args = [
        CMAKE_PATH,
        "--build", build_dir,
        "--target", "tests",
    ]

    if NUM_JOBS:
        build_args.append(f"-j{NUM_JOBS}")

    if build_variant.variant is not None:
        build_type = variant_to_build_type(build_variant.variant)
        build_args.append(f"--config {build_type}")
    else:
        build_args.append("--config Debug")

    return build_args

def launch_cmake_configure(build_variant: BuildVariant, toolsets):
    """"Launches a child CMake processes that begins configuring for the given build variant"""

    build_dir = build_variant_to_build_dir(build_variant)
    cmake_cache_path = os.path.join(build_dir, "CMakeCache.txt")
    if os.path.exists(cmake_cache_path):
        # this makes sure that if a user changes the cxxflags, we always get a fresh build
        # with correct flags
        os.remove(cmake_cache_path)

    if is_windows() and build_variant.toolset.startswith('msvc-'):
        toolset = toolsets[build_variant.toolset.replace('msvc-', '')]
    else:
        toolset = None

    cmake_config_cmd = build_variant_to_cmake_config_cmd(build_variant, build_dir, toolset)

    print("cmake configuration command is:")
    print(' '.join(cmake_config_cmd))
    print('--------------------------------------------------------------------')

    process = subprocess.Popen(
        cmake_config_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    return process

def configure_boost(build_variants: list[BuildVariant]):
    """Configures the specified Boost libraries in parallel"""

    if NO_CONFIGURE:
        print("skipping CMake configuration step")
        return

    arch = 'amd64'
    msvc_toolsets = list(set([build_variant.toolset.replace('msvc-', '') for build_variant in build_variants]))

    toolsets = {}

    for msvc_toolset in msvc_toolsets:
        print(f'gathering toolset info for msvc-{msvc_toolset}')

        filename = f'vcvars_env_{arch}_{msvc_toolset.replace('.', '')}.txt'

        get_vcvars_cmd = ['get_vcvars.bat', filename, arch, msvc_toolset]
        if WINSDK_VERSION is not None:
            get_vcvars_cmd.append(WINSDK_VERSION)

        subprocess.run(
            get_vcvars_cmd,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, check=True)

        with open(filename, mode="r", encoding="utf-8") as file:
            text = file.read().splitlines()
            print(text)

            toolsets[msvc_toolset] = {}

            p = toolsets[msvc_toolset]
            for line in text:
                if line.endswith('cl.exe') and p.get('cl') is None:
                    p['cl'] = line.replace('\\', '/')

                if line.endswith('rc.exe') and p.get('rc') is None:
                    p['rc'] = line.replace('\\', '/')

                if line.endswith('mt.exe') and p.get('mt') is None:
                    p['mt'] = line.replace('\\', '/')

                if line.startswith('INCLUDE='):
                    includes = line.split('=')
                    includes = includes[1].split(';')
                    includes = [f'-IC:"{include.replace('C:', '')}"' for include in includes]

                    p['include'] = includes

                if line.startswith('LIB='):
                    libs = line.split('=')
                    libs = libs[1].split(';')
                    libs = [f'/LIBPATH:"{lib.replace('C:', '')}"' for lib in libs]
                    p['libpath'] = libs

            print('----------------------------------------')
            print('completed building toolset database file')

    print('built the following toolsets for msvc')
    print(toolsets)

    cmake_config_procs = []
    for idx, build_variant in enumerate(build_variants):
        print(f"launching configuration job {idx + 1} of {len(build_variants)}")
        proc = launch_cmake_configure(build_variant, toolsets)
        cmake_config_procs.append(proc)

    configure_failed = False

    pipes = []

    for config_proc in cmake_config_procs:
        stdout, stderr = config_proc.communicate()
        pipes.append((stdout, stderr))

    for i, config_proc in enumerate(cmake_config_procs):
        config_proc.wait()

        stdout, stderr = pipes[i]
        if stderr:
            print("cmake configuration wrote the following to stderr:")
            print(stdout)
            print(stderr)

        if config_proc.returncode != 0:
            configure_failed = True

    if configure_failed:
        print("CMake configuration failed, exiting now")
        sys.exit(1)

    builds_dir_fragments = [build_variant_to_build_dir_fragment(bv) for bv in build_variants]
    txt = None
    for fragment in builds_dir_fragments:
        ninja_file = os.path.join(BUILD_ROOT, fragment, "build.ninja")

        with open(ninja_file, mode="r", encoding="utf-8") as file:
            txt = file.read()

        updated_txt = txt.replace(
            "cmake_object_order_depends_target_boost",
            f"cmake_object_order_depends_target_boost_{fragment}")

        with open(ninja_file, mode="w", encoding="utf-8") as file:
            file.write(updated_txt)

    print("configuration complete")

def parse_args():
    """Parse CLI args and form the build variants array"""

    parser = argparse.ArgumentParser(description="Parse all build options and assemble the matrix.")

    parser.add_argument(
        "command",
        type=str,
        help="Main driver command. Either just `build` or `test`. `test` implies `build` but also "
             "invokes `ctest` for each generated build directory."
    )

    parser.add_argument(
        "library",
        type=str,
        help="Name of the library to build tests for."
    )

    parser.add_argument(
        "--cmake-path", type=str, help="Path to a working CMake executable.",
        dest="cmake_path")

    parser.add_argument(
        "--ninja-path", type=str, help="Path to a working Ninja executable.",
        dest="ninja_path")

    parser.add_argument(
        "-j", type=int,
        dest="jobs",
        help="Number of jobs used to build with CMake.",
    )

    parser.add_argument(
        "--cxxstd",
        type=str,
        help="A comma-separated list of C++ standard versions (e.g., 'cxxstd=11,17,20')."
    )

    parser.add_argument(
        "--toolset",
        type=str,
        help="A comma-separated list of C++ toolchains to use (e.g. toolset=gcc-14,clang-19 "
             "[no '++' required])"
    )

    parser.add_argument(
        "--variant",
        type=str,
        help="A comma-separated list of C++ build types (e.g variant=debug,release or "
             "variant=release)"
    )

    parser.add_argument(
        "--address-model",
        type=str,
        help="A comma-separated list of architectures (e.g. address-model=32,64)",
        dest="address_model"
    )

    parser.add_argument(
        "--link",
        type=str,
        help="A comma-separated list of link models (e.g. link=static,shared)"
    )

    parser.add_argument(
        "--ubsan",
        action='store_true',
        help="Build with -fsanitize=undefined"
    )

    parser.add_argument(
        "--asan",
        action='store_true',
        help="Build with -fsanitize=address",
    )

    parser.add_argument(
        "--no-cmake",
        action="store_true",
        help="Skip the CMake configuration step",
        dest="no_cmake"
    )

    parser.add_argument(
        "--cxxflags",
        type=str,
        help="Add custom compiler options that will be added to "
             "`CMAKE_CXX_FLAGS_INIT` during configure time"
    )

    parser.add_argument(
        '--ctestflags',
        type=str,
        help="Additional arguments to be passed to ctest during test running",
    )

    parser.add_argument(
        '--winsdk-version', type=str,
        dest='winsdk_version',
        help='Version of the Windows SDK to use (e.g. 10.0.22621.0). Commonly found in: "C:\\Program Files (x86)\\Windows Kits\\10\\Lib\\10.0.22621.0"')

    args = parser.parse_args()

    cxxstds = []
    toolsets = []
    variants = []
    address_models = []
    links = []

    if args.command:
        command = args.command
        if command not in ('build', 'test'):
            raise ValueError("The only permitted sub-commands for "
                             "c2.py are: \"build\" or \"test\".")
        global COMMAND_MODE
        COMMAND_MODE = command
    else:
        raise ValueError("Must specify a build command such as `build` or `test.")

    if args.library:
        global LIBRARY
        LIBRARY = args.library
    else:
        raise ValueError("Must specify a library to build, such as `hash2` or `unordered`.")

    if args.cmake_path:
        global CMAKE_PATH
        CMAKE_PATH = shutil.which(args.cmake_path)

    if args.ninja_path:
        global NINJA_PATH
        NINJA_PATH = shutil.which(args.ninja_path)

    if args.jobs:
        global NUM_JOBS
        NUM_JOBS = args.jobs

    if args.winsdk_version:
        global WINSDK_VERSION
        WINSDK_VERSION = args.winsdk_version

    if args.cxxstd:
        result = args.cxxstd.split(",")
        cxxstds += result
    else:
        cxxstds.append(None)

    if args.toolset:
        result = args.toolset.split(",")
        toolsets += result
    else:
        toolsets.append(None)

    if args.variant:
        result = args.variant.split(",")
        variants += result
    else:
        variants.append(None)

    if args.address_model:
        result = args.address_model.split(",")
        address_models += result
    else:
        address_models.append(None)

    if args.link:
        result = args.link.split(",")

        if len(result) != len(list(set(result))):
            raise ValueError("Invalid link value. Should be of the form"
                             ": --link=static,shared or --link=shared.")

        for r in result:
            if r not in ('static', 'shared'):
                raise ValueError(f"{r} is an invalid link type, must be static or shared")

        links += result
    else:
        links.append(None)

    if args.asan:
        global ASAN
        ASAN = True

    if args.ubsan:
        global UBSAN
        UBSAN = True

    if args.no_cmake:
        global NO_CONFIGURE
        NO_CONFIGURE = True

    if args.cxxflags:
        global CXXFLAGS
        CXXFLAGS = args.cxxflags

    if args.ctestflags:
        global CTESTFLAGS
        CTESTFLAGS = args.ctestflags

    build_variants = []
    for cxxstd in cxxstds:
        for toolset in toolsets:
            for variant in variants:
                for addr in address_models:
                    for link in links:
                        build_variants.append(
                            BuildVariant(
                                toolset=toolset,
                                variant=variant,
                                cxxstd=cxxstd,
                                address_model=addr,
                                link=link
                            )
                        )

    return build_variants

def build_with_driver_makefile(build_variants):
    """Write the main driving Makefile that users will use for building the project"""

    build_dirs = [build_variant_to_build_dir_fragment(bv) for bv in build_variants]

    makefile_contents = f"""
MAKEFLAGS += --no-print-directory
export MAKEFLAGS

BUILD_DIRS := {' '.join(build_dirs)}

.PHONY: all
all: $(addsuffix /all, $(BUILD_DIRS))

$(addsuffix /all, $(BUILD_DIRS)):
	$(MAKE) -C $(dir $@) tests

.PHONY: test
test: $(addsuffix /test, $(BUILD_DIRS))

$(addsuffix /test, $(BUILD_DIRS)):
	$(MAKE) -C $(dir $@) test ARGS=$(ARGS)

.PHONY: clean
clean: $(addsuffix /clean, $(BUILD_DIRS))

$(addsuffix /clean, $(BUILD_DIRS)):
	$(MAKE) -C $(dir $@) clean
"""

    with open(os.path.join(BUILD_ROOT, "Makefile"), mode="w", encoding="utf-8") as file:
        file.write(makefile_contents)

    make_args = [shutil.which("make")]

    if NUM_JOBS is not None:
        make_args.append(f"-j{NUM_JOBS}")

    subprocess.run(make_args, cwd=BUILD_ROOT, check=True)
    return

def build_with_driver_ninja_file(build_variants):
    """Write the main driving ninja.build that users will use for building the project"""

    builds_dir_fragments = [build_variant_to_build_dir_fragment(bv) for bv in build_variants]

    with open(os.path.join(BUILD_ROOT, "build.ninja"), mode="w", encoding="utf-8") as file:
        for build_dir in builds_dir_fragments:
            file.write(f"subninja {build_dir}/build.ninja\n")
        file.write("\n")

        ts = [os.path.join(path, "tests") for path in builds_dir_fragments]
        file.write(f"build all: phony {' '.join(ts)}\n")

        cs = [os.path.join(path, "clean") for path in builds_dir_fragments]
        file.write(f"build clean: phony {' '.join(cs)}\n")

        file.write("\n")
        file.write("default all")
        file.write("\n")

    ninja_cmd = [NINJA_PATH]
    if NUM_JOBS is not None:
        ninja_cmd.append(f"-j{NUM_JOBS}")

    subprocess.run(ninja_cmd, cwd=BUILD_ROOT, check=True)
    return

def run_tests():
    """Execute the tests via ctest"""

    make_cmd = [shutil.which("make")]

    if NUM_JOBS is not None:
        make_cmd.append(f"-j{NUM_JOBS}")

    make_cmd.append('test')

    if CTESTFLAGS is not None:
        make_cmd.append(f"ARGS=\"{CTESTFLAGS}\"")

    subprocess.run(make_cmd, cwd=BUILD_ROOT, check=True)

def setup_cmake():
    """Ensure the user has given us a path to CMake or we can find it."""

    global CMAKE_PATH
    if CMAKE_PATH is None:
        CMAKE_PATH = shutil.which('cmake')

    if CMAKE_PATH is None:
        raise ValueError("no valid CMake binary was specified. Add it to your PATH or via --cmake-path.")

    print(f"using the cmake binary at: {CMAKE_PATH}")

def setup_ninja():
    """Ensure the user has given us a path to Ninja or we can find it"""

    global NINJA_PATH
    if NINJA_PATH is None:
        NINJA_PATH = shutil.which('ninja')

    if NINJA_PATH is None:
        raise ValueError("no valid Ninja binary was specified. Add it to your PATH or via --ninja-path.")

    print(f"using the ninja binary at: {NINJA_PATH}")

def init():
    """Main entry for bulk-building Boost via CMake"""

    print("starting c2.py script")
    build_variants = parse_args()

    setup_cmake()
    setup_ninja()

    configure_boost(build_variants)
    build_with_driver_ninja_file(build_variants)

if __name__ == "__main__":
    init()
