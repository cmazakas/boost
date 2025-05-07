#!/usr/bin/python3

# pylint: disable=global-statement

"""Python-based version of b2 using pure CMake"""

import os
import shutil
import subprocess
import dataclasses
import argparse
import sys

num_cores = os.cpu_count()

BUILD_ROOT = "build_c2py"
COMMAND_MODE: str | None = None
CMAKE_GENERATOR: str | None = None
NUM_JOBS: int | None = None
LIBRARY: str | None = None
UBSAN: bool | None = None
ASAN: bool | None = None
NO_CONFIGURE: bool | None = None
CXXFLAGS: str | None = None
CTESTFLAGS: str | None = None

@dataclasses.dataclass
class BuildVariant:
    """Represents a CMake-based build"""

    address_model: str | None = None
    toolset: str | None = None
    variant: str | None = None
    cxxstd: str | None = None
    link: str | None = None

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

def build_variant_to_cmake_config_cmd(build_variant: BuildVariant, build_dir: str):
    """Programmatically generate the proper arguments to pass to CMake's configure phase"""

    fragment = build_variant_to_build_dir_fragment(build_variant)

    config_args = [
        shutil.which("cmake"),
        "-S", ".",
        "-B", build_dir,
        "-DBUILD_TESTING=ON",
        f"-DBOOST_INCLUDE_LIBRARIES={LIBRARY}",
        "-DCMAKE_EXPORT_COMPILE_COMMANDS=ON",
        "-DCMAKE_CXX_VISIBILITY_PRESET=hidden",
        "-DCMAKE_VISIBILITY_INLINES_HIDDEN=ON",
        "-G", "Ninja",
        f"-DCMAKE_NINJA_OUTPUT_PATH_PREFIX={fragment}",
        "-DCMAKE_SUPPRESS_REGENERATION=ON",
    ]

    if build_variant.toolset is not None:
        cxx_compiler = toolset_to_cxx_compiler(build_variant.toolset)
        config_args.append(f"-DCMAKE_C_COMPILER={build_variant.toolset}")
        config_args.append(f"-DCMAKE_CXX_COMPILER={cxx_compiler}")

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

    cxxflags = []
    if build_variant.address_model == '32':
        cxxflags.append('-m32')

    if ASAN:
        cxxflags.append('-fsanitize=address')

    if UBSAN:
        cxxflags.append('-fsanitize=undefined')

    if len(cxxflags) > 0 or CXXFLAGS is not None:
        init_flags = ' '.join(cxxflags)
        if CXXFLAGS is not None:
            init_flags += CXXFLAGS
        config_args.append(f"-DCMAKE_CXX_FLAGS_INIT='{init_flags}'")

    return config_args

def build_variant_to_cmake_build_args(build_variant: BuildVariant, build_dir: str):
    """Programmatically generate the proper arguments to pass to CMake's build phase"""

    build_args = [
        "cmake",
        "--build", build_dir,
        "--target", "tests",
    ]

    if NUM_JOBS:
        build_args.append(f"-j{NUM_JOBS}")

    if build_variant.variant is not None:
        build_type = variant_to_build_type(build_variant.variant)
        build_args.append(f"--config {build_type}")

    return build_args

def launch_cmake_configure(build_variant: BuildVariant):
    """"Launches a child CMake processes that begins configuring for the given build variant"""

    build_dir = build_variant_to_build_dir(build_variant)
    cmake_cache_path = os.path.join(build_dir, "CMakeCache.txt")
    if os.path.exists(cmake_cache_path):
        # this makes sure that if a user changes the cxxflags, we always get a fresh build
        # with correct flags
        os.remove(cmake_cache_path)

    cmake_config_cmd = build_variant_to_cmake_config_cmd(build_variant, build_dir)

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

    cmake_config_procs = []
    for idx, build_variant in enumerate(build_variants):
        print(f"launching configuration job {idx + 1} of {len(build_variants)}")
        proc = launch_cmake_configure(build_variant)
        cmake_config_procs.append(proc)

    for config_proc in cmake_config_procs:
        config_proc.wait()

    configure_failed = False
    for config_proc in cmake_config_procs:
        _stdout, stderr = config_proc.communicate()
        if stderr:
            print(stderr)
            configure_failed = True

    if configure_failed:
        print("CMake configuration failed, exiting now")
        sys.exit(1)

    print("configuration complete")

def parse_args():
    """Parse CLI args and form the build variants array"""

    parser = argparse.ArgumentParser(description="Parse all build options and assemble the matrix.")

    parser.add_argument(
        "library",
        type=str,
        help="Name of the library to build tests for."
    )

    parser.add_argument(
        "command",
        type=str,
        help="Main driver command. Either just `build` or `test`. `test` implies `build` but also "
             "invokes `ctest` for each generated build directory."
    )

    parser.add_argument("-G", type=str, help="The CMake generator to use.", dest="generator")

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

    if args.generator:
        global CMAKE_GENERATOR
        CMAKE_GENERATOR = args.generator

    if args.jobs:
        global NUM_JOBS
        NUM_JOBS = args.jobs

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


    ninja_cmd = [shutil.which("ninja")]
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

def init():
    """Main entry for bulk-building Boost via CMake"""

    print("starting c2.py script")
    build_variants = parse_args()

    configure_boost(build_variants)
    build_with_driver_ninja_file(build_variants)

    # print("starting build phase")
    # build_with_driver_makefile(build_variants)

    # if COMMAND_MODE == 'test':
    #     print("running tests")
    #     run_tests()


if __name__ == "__main__":
    init()
