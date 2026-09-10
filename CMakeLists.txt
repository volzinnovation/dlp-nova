cmake_minimum_required(VERSION 3.22)
project(dlp_native VERSION 0.1.0 LANGUAGES C CXX)

option(BUILD_SHARED_LIBS "Build a shared native library" ON)
option(DLP_BUILD_SMOKE "Build the standalone native smoke test" ON)
option(DLP_BUILD_JNI "Include the Android JNI wrapper" ${ANDROID})

set(CMAKE_C_STANDARD 99)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_C_EXTENSIONS OFF)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

if(NOT CMAKE_SIZEOF_VOID_P EQUAL 8)
  message(FATAL_ERROR "This native distribution supports 64-bit targets only (decimal arithmetic uses __int128).")
endif()
include(CheckCXXSourceCompiles)
check_cxx_source_compiles("int main() { __int128 x = 1; return int(x - 1); }" DLP_HAS_INT128)
if(NOT DLP_HAS_INT128)
  message(FATAL_ERROR "DLP native decimal arithmetic requires a compiler with __int128 (Clang or GCC).")
endif()

set(DLP_SOURCE ${CMAKE_CURRENT_SOURCE_DIR}/src/dlp_reasoner)
add_library(dlp_native
  ${DLP_SOURCE}/native_store.cpp
  ${DLP_SOURCE}/native_domains.cpp
  ${DLP_SOURCE}/native_runtime.cpp
  ${DLP_SOURCE}/native_spatial.cpp
  ${DLP_SOURCE}/native_windows.cpp
  ${DLP_SOURCE}/native_package.cpp
  ${DLP_SOURCE}/native_query.cpp
  ${DLP_SOURCE}/vendor/geographiclib/geodesic.c)
target_compile_definitions(dlp_native PRIVATE DLP_HAVE_GEODESIC=1)
target_include_directories(dlp_native PUBLIC
  $<BUILD_INTERFACE:${DLP_SOURCE}>
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/mobile/include>
  $<INSTALL_INTERFACE:include/dlp>)
# Keep a configure-time input manifest and regenerate it before a changed source
# is rebuilt. The reporting tool rejects artifacts whose configured inputs differ.
get_target_property(DLP_INPUTS dlp_native SOURCES)
list(APPEND DLP_INPUTS
  ${DLP_SOURCE}/native_store.h ${DLP_SOURCE}/native_domains.h
  ${DLP_SOURCE}/native_runtime.h ${DLP_SOURCE}/native_spatial.h
  ${DLP_SOURCE}/native_windows.h ${DLP_SOURCE}/native_package.h
  ${DLP_SOURCE}/native_query.h
  ${DLP_SOURCE}/vendor/date/date.h ${DLP_SOURCE}/vendor/geographiclib/geodesic.h
  ${CMAKE_CURRENT_SOURCE_DIR}/CMakeLists.txt)
set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS ${DLP_INPUTS})
set(DLP_INPUT_DIGESTS "")
foreach(DLP_INPUT IN LISTS DLP_INPUTS)
  file(SHA256 "${DLP_INPUT}" DLP_INPUT_DIGEST)
  file(RELATIVE_PATH DLP_INPUT_NAME "${CMAKE_CURRENT_SOURCE_DIR}" "${DLP_INPUT}")
  string(APPEND DLP_INPUT_DIGESTS "${DLP_INPUT_DIGEST}  ${DLP_INPUT_NAME}\n")
endforeach()
file(WRITE "${CMAKE_CURRENT_BINARY_DIR}/native-sources.sha256" "${DLP_INPUT_DIGESTS}")
if(NOT APPLE AND NOT WIN32)
  target_link_libraries(dlp_native PRIVATE m)
endif()
if(DLP_BUILD_JNI)
  if(NOT ANDROID)
    find_package(JNI REQUIRED)
    target_include_directories(dlp_native PRIVATE ${JNI_INCLUDE_DIRS})
  endif()
  target_sources(dlp_native PRIVATE mobile/android/dlp_jni.cpp)
  set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS mobile/android/dlp_jni.cpp)
  file(SHA256 "${CMAKE_CURRENT_SOURCE_DIR}/mobile/android/dlp_jni.cpp" DLP_JNI_DIGEST)
  file(APPEND "${CMAKE_CURRENT_BINARY_DIR}/native-sources.sha256" "${DLP_JNI_DIGEST}  mobile/android/dlp_jni.cpp\n")
endif()
if(ANDROID)
  # Android 15+ devices may use 16 KiB pages. Packaging must also retain alignment.
  target_link_options(dlp_native PRIVATE "-Wl,-z,max-page-size=16384" "-Wl,-z,common-page-size=16384")
endif()

include(GNUInstallDirs)
install(TARGETS dlp_native LIBRARY DESTINATION ${CMAKE_INSTALL_LIBDIR}
  ARCHIVE DESTINATION ${CMAKE_INSTALL_LIBDIR} RUNTIME DESTINATION ${CMAKE_INSTALL_BINDIR})
install(FILES ${DLP_SOURCE}/native_store.h ${DLP_SOURCE}/native_domains.h
  ${DLP_SOURCE}/native_runtime.h ${DLP_SOURCE}/native_spatial.h
  ${DLP_SOURCE}/native_windows.h ${DLP_SOURCE}/native_package.h
  ${DLP_SOURCE}/native_query.h
  mobile/include/dlp_native.h mobile/include/module.modulemap DESTINATION include/dlp)
install(FILES ${DLP_SOURCE}/vendor/date/date.h
  DESTINATION share/dlp/licenses RENAME HowardHinnant-date-header-with-license.h)
install(FILES ${DLP_SOURCE}/vendor/geographiclib/LICENSE.txt
  DESTINATION share/dlp/licenses RENAME GeographicLib-C-LICENSE.txt)

if(DLP_BUILD_SMOKE)
  enable_testing()
  add_executable(dlp_native_smoke mobile/native_smoke.cpp)
  target_link_libraries(dlp_native_smoke PRIVATE dlp_native)
  add_test(NAME native_abi_smoke COMMAND dlp_native_smoke)
  add_executable(dlp_windows_smoke mobile/windows_smoke.cpp)
  target_link_libraries(dlp_windows_smoke PRIVATE dlp_native)
  add_test(NAME native_windows_smoke COMMAND dlp_windows_smoke)
  add_executable(dlp_query_smoke mobile/query_smoke.cpp)
  target_link_libraries(dlp_query_smoke PRIVATE dlp_native)
  add_test(NAME native_query_smoke COMMAND dlp_query_smoke)
  add_executable(dlp_package_smoke mobile/package_smoke.cpp)
  target_link_libraries(dlp_package_smoke PRIVATE dlp_native)
  add_test(NAME native_package_smoke COMMAND dlp_package_smoke "${CMAKE_CURRENT_SOURCE_DIR}/mobile/fixtures/query.dlpn")
endif()
