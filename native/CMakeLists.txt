# Host-toolchain build of the BOXCAR receiver core + verification harness.
# No Android/NDK — the same boxcar_rx.{h,cpp} compile for the phone (see
# hobocon-app's :tv-sdr JNI layer).
#
#   cmake -S . -B build && cmake --build build
#   ./build/boxcar_harness capture.cu8 out.ts --fec
cmake_minimum_required(VERSION 3.18)
project(boxcar_harness CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

add_executable(boxcar_harness
    harness.cpp
    boxcar_rx.cpp
)
if (MSVC)
    target_compile_options(boxcar_harness PRIVATE /O2 /W3)
else()
    target_compile_options(boxcar_harness PRIVATE -O2 -Wall)
endif()
