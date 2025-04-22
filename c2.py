#!/usr/bin/python3

"""Python-based version of b2 using pure CMake"""

import os
import subprocess
import dataclasses
import argparse

num_cores = os.cpu_count()

command_mode: str | None = None
cmake_generator: str | None = None
num_jobs: int | None = None
library: str | None = None

@dataclasses.dataclass
class BuildVariant:
    """Represents a CMake-based build"""

    address_model: str | None = None
    toolset: str | None = None
    variant: str | None = None
    cxxstd: str | None = None

def build_variant_to_build_dir(build_variant: BuildVariant):
    """Translates a build variant object into a named build directory to invoke CMake in"""

    build_dir = f"build_{library}"
    if build_variant.toolset is not None:
        build_dir += f"_{build_variant.toolset}"

    if build_variant.cxxstd is not None:
        build_dir += f"_std{build_variant.cxxstd}"

    if build_variant.variant is not None:
        build_dir += f"_{build_variant.variant}"

    addr = build_variant.address_model
    if addr is not None:
        if addr == '32':
            build_dir += "_x86"
        elif addr == '64':
            build_dir += "_x64"

    return os.path.join("build_c2py", build_dir)

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

def build_variant_to_cmake_configure_args(build_variant: BuildVariant, build_dir: str):
    """Programmatically generate the proper arguments to pass to CMake's configure phase"""

    config_args = [
        "cmake",
        "-S", ".",
        "-B", build_dir,
        "-DBUILD_TESTING=ON",
        f"-DBOOST_INCLUDE_LIBRARIES={library}",
        "-DCMAKE_EXPORT_COMPILE_COMMANDS=ON",
    ]

    if cmake_generator:
        config_args += ["-G", cmake_generator]

    if build_variant.toolset is not None:
        cxx_compiler = toolset_to_cxx_compiler(build_variant.toolset)
        config_args.append(f"-DCMAKE_C_COMPILER={build_variant.toolset}")
        config_args.append(f"-DCMAKE_CXX_COMPILER={cxx_compiler}")

    if build_variant.variant is not None:
        build_type = variant_to_build_type(build_variant.variant)
        config_args.append(f"-DCMAKE_BUILD_TYPE={build_type}")

    if build_variant.cxxstd is not None:
        cxxstd = build_variant.cxxstd
        config_args.append(f"-DCMAKE_CXX_STANDARD={cxxstd}")

    if build_variant.address_model == '32':
        config_args.append("-DCMAKE_CXX_FLAGS_INIT=\"-m32\"")

    return config_args


def build_variant_to_cmake_build_args(build_variant: BuildVariant, build_dir: str):
    """Programmatically generate the proper arguments to pass to CMake's build phase"""

    build_args = [
        "cmake",
        "--build", build_dir,
        "--target", "tests",
    ]

    if num_jobs:
        build_args.append(f"-j{num_jobs}")

    if build_variant.variant is not None:
        build_type = variant_to_build_type(build_variant.variant)
        build_args.append(f"--config {build_type}")

    return build_args

def build_boost(build_variant: BuildVariant):
    """"Build a specific Boost configuration"""

    build_dir = build_variant_to_build_dir(build_variant)

    print("configuring Boost")
    config_args = build_variant_to_cmake_configure_args(build_variant, build_dir)
    subprocess.run(config_args, check=True)


    print("building Boost")
    build_args = build_variant_to_cmake_build_args(build_variant, build_dir)
    subprocess.run(build_args, check=True)

    if command_mode == "test":
        subprocess.run(["ctest", "--test-dir", build_dir], check=True)

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

    args = parser.parse_args()

    cxxstds = []
    toolsets = []
    variants = []
    address_models = []

    if args.command:
        command = args.command
        if command not in ('build', 'test'):
            raise ValueError("The only permitted sub-commands for "
                             "c2.py are: \"build\" or \"test\".")
        global command_mode
        command_mode = command
    else:
        raise ValueError("Must specify a build command such as `build` or `test.")

    if args.library:
        global library
        library = args.library
    else:
        raise ValueError("Must specify a library to build, such as `hash2` or `unordered`.")

    if args.generator:
        global cmake_generator
        cmake_generator = args.generator

    if args.jobs:
        global num_jobs
        num_jobs = args.jobs

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

    print(f"read in the following cxxstds: {cxxstds}")
    print(f"read in the following toolsets: {toolsets}")
    print(f"read in the following variants: {variants}")
    print(f"read in the following address-models: {address_models}")

    build_variants = []
    for cxxstd in cxxstds:
        for toolset in toolsets:
            for variant in variants:
                for addr in address_models:
                    build_variants.append(
                        BuildVariant(
                            toolset=toolset,
                            variant=variant,
                            cxxstd=cxxstd,
                            address_model=addr
                        )
                    )

    return build_variants

def init():
    """Main entry for bulk-building Boost via CMake"""

    print("starting c2.py script")
    build_variants = parse_args()
    for build_variant in build_variants:
        build_boost(build_variant)

if __name__ == "__main__":
    init()
