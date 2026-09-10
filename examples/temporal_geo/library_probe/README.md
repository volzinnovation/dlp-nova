# Shared-library feasibility probe

This standalone experiment calls the **same C++17 shared library from a C++ executable and Python `ctypes`**. It checks temporal comparisons and geometric operations; it does not extend the DLP backend or measure performance.

The four source files are retained here. Downloaded headers, binaries, logs, and result files belong in a temporary build directory. The probe neither installs packages nor changes production dependencies.

## Prerequisites and reproduction

The commands below target **macOS**, matching the tested environment. They require an existing C++17 `clang++`, `pkg-config`, `curl`, `shasum`, the project's `.venv/bin/python`, and installed **GEOS C API and PROJ development libraries** visible to `pkg-config`. GEOS must provide `GEOSDistanceWithin_r`. Other platforms need their shared-library suffix/linker flags adapted.

The only download is the upstream [Howard Hinnant date v3.0.5 header](https://raw.githubusercontent.com/HowardHinnant/date/v3.0.5/include/date/date.h), with SHA-256:

```text
8c295bc53964ec02fa99ef10816c190a4c34fdcbf1ce2dcc8e451a29932f9d2c
```

Run this complete block from the repository root. It verifies that header before compiling, then runs both callers. A failure stops the block; no installation fallback is attempted.

```sh
bash <<'SH'
set -euo pipefail
probe_dir="$PWD/examples/temporal_geo/library_probe"
probe_build="$(mktemp -d /tmp/dlp-library-probe.XXXXXX)"
pkg-config --exists geos proj
mkdir -p "$probe_build/include/date"
curl --fail --silent --show-error --location --max-time 30 \
  --proto '=https' --proto-redir '=https' \
  https://raw.githubusercontent.com/HowardHinnant/date/v3.0.5/include/date/date.h \
  --output "$probe_build/include/date/date.h"
printf '%s  %s\n' \
  8c295bc53964ec02fa99ef10816c190a4c34fdcbf1ce2dcc8e451a29932f9d2c \
  "$probe_build/include/date/date.h" | shasum -a 256 -c -
clang++ -O3 -std=c++17 -DNDEBUG -shared -fPIC -Wall -Wextra -Werror \
  -I"$probe_build/include" $(pkg-config --cflags geos proj) \
  "$probe_dir/smoke.cpp" $(pkg-config --libs geos proj) \
  -Wl,-install_name,@rpath/libdlp_smoke.dylib \
  -o "$probe_build/libdlp_smoke.dylib"
clang++ -O3 -std=c++17 -DNDEBUG -Wall -Wextra -Werror \
  "$probe_dir/driver.cpp" -L"$probe_build" -ldlp_smoke \
  -Wl,-rpath,"$probe_build" -o "$probe_build/driver"
"$probe_build/driver" > "$probe_build/cpp-output.json"
.venv/bin/python "$probe_dir/check_ctypes.py" "$probe_build"
printf 'Temporary build and outputs: %s\n' "$probe_build"
SH
```

`driver.cpp` links the shared library rather than reproducing its algorithms. `check_ctypes.py` loads that same library, checks expected outcomes, and compares every result field against the C++ output. It writes `python-output.json` only in the supplied build directory.

## Observed result

Verified on 10 September 2026 with **Apple Clang 21.0.0, CPython 3.12.9, date v3.0.5, GEOS 3.14.1 / C API 1.20.5, and PROJ 9.8.0**, on macOS arm64. Both builds passed `-Wall -Wextra -Werror`; both callers returned matching results and the Python checker printed `"status": "PASS"`.

| Check | Result in both callers |
| --- | --- |
| Microsecond `date::sys_time` before/after/equal | `[-1, 1, 0]` |
| Valid leap-day `year_month_day` and `sys_days` ordering | `[-1, 1, 0]` |
| Invalid `2023-02-29` | Rejected before conversion |
| GEOS projected points `(0,0)` and `(30,40)` | Distance `50` |
| Inclusive GEOS distance-within radii `50`, `49` | `[true, false]` |
| WGS84 inverse, `(lat,lon)=(0,0)` to `(0,1)` | `111319.49079327357` metres |
| Negative radius, null output, invalid latitude | Rejected; outputs remain unchanged |

The ABI uses status `0` for success, `1` for invalid arguments, and `2` for library/evaluation failure. GEOS predicate return `2` is checked separately from Boolean true. Geometry/context ownership remains inside C++; C++ exceptions do not cross the ABI. The tests cover input rejection but do not inject allocation or library failures.

Date inputs here are already decoded integers/calendar components: no XSD parser, named timezones, leap-second policy, or duration arithmetic is implemented. Coordinates in the GEOS test are planar, with one coordinate unit interpreted as one metre. The geographic test uses PROJ's bundled `geod_inverse` C routine with the WGS84 ellipsoid and a `1e-6` metre absolute test tolerance; it does not test CRS transformation or establish GeoSPARQL conformance. There is no stream scheduler, routing/map matching, concurrency test, or production-engine integration.
