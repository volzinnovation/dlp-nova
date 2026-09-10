# One temporal implementation for Python and C++

Research checked 10 September 2026. Recommendation and interface sketches only;
no temporal dependency or production operator has been added.

**Recommend Howard Hinnant's `date` library with `<chrono>`, exposed through one
small project C ABI.** Use `date.h` for calendar values, parsing, and explicit
precision; add `tz.h`/`tz.cpp` when named IANA zones are required. The same compiled
temporal module can serve the Python relation backend through `ctypes` and the
C++ backend directly. Scalar `before`/`after` does not require a temporal-logic
solver. The library explicitly supports C++11/14/17, matching this repository's
current native build. [Upstream project](https://github.com/HowardHinnant/date)

**For desktop Python, if ready-made bindings are the priority, use ICU + PyICU instead.**
Among the candidates checked, it is the clearest existing solution with literal
`Calendar.before`/`after` methods in Python calling ICU's corresponding C++
methods. The tradeoff is a larger dependency and a documented millisecond
calendar model, rather than the proposed exact-microsecond kernel.
[ICU Calendar API](https://unicode-org.github.io/icu-docs/apidoc/released/icu4c/classicu_1_1Calendar.html),
[PyICU](https://pypi.org/project/pyicu/)

For iOS and Android, prefer the app-owned `date` kernel and a shared C ABI;
PyICU is an optional embedded-Python route, not the mobile baseline. The mobile
constraints and packaging distinction are detailed below.

## Candidate comparison

| Candidate | Relevant operations and types | Fit and integration cost |
| --- | --- | --- |
| **Howard Hinnant `date` + `<chrono>`** | `sys_time<Duration>`, calendar dates, local times, parsing/formatting; ordinary comparison operators. Optional named-zone conversion exposes ambiguous/nonexistent local times. | Best initial fit: calendar core is header-only; timezone support adds `tz.cpp` and a managed timezone database. A small C wrapper supplies the shared Python/C++ API. [Date API](https://howardhinnant.github.io/date/date.html), [timezone API](https://howardhinnant.github.io/date/tz.html) |
| **ICU4C + PyICU** | `icu::Calendar::before`, `after`, `equals`; calendar arithmetic and zones. PyICU exposes the same underlying C++ calls as `a.before(b)` / `a.after(b)`. | Best existing-binding option here. ICU libraries/data and the PyICU extension are required; recent ICU uses C++17. Strict validation, explicit calendar/zone policy and precision checks remain our responsibility. [ICU API](https://unicode-org.github.io/icu-docs/apidoc/released/icu4c/classicu_1_1Calendar.html), [PyICU build/API notes](https://pypi.org/project/pyicu/) |
| **Boost.Date_Time** | `gregorian::date`, `posix_time::ptime`, durations, local date-times, and date/time periods. Date periods expose `contains`, `intersects`, adjacency, `is_before(date)` and `is_after(date)`. | Useful if Boost is already a dependency or its period API is desired. Current catalog describes it as header-only, but it pulls in several Boost components. Date range is 1400–9999. Its documented CSV/POSIX zone-rule model should not be confused with a complete IANA historical transition reader. [Catalog](https://www.boost.org/library/latest/date_time/), [dates/periods](https://www.boost.org/doc/libs/latest/doc/html/date_time/gregorian.html), [local time](https://www.boost.org/doc/libs/latest/doc/html/date_time/local_time.html) |
| **Abseil Time** | `absl::Time`, `Duration`, civil dates/times and `TimeZone`; comparisons, arithmetic, parsing and conversions. Wide-range time representation; civil fields normalize overflow. | Strong alternative when Abseil is already present. More compiled components than `date.h`: time depends on base, strings, integer and timezone components. Public time library incorporates CCTZ internally; do not depend on its private CCTZ headers. [Time guide](https://abseil.io/docs/cpp/guides/time), [build dependencies](https://github.com/abseil/abseil-cpp/blob/master/absl/time/CMakeLists.txt) |
| **Standalone CCTZ** | C++11 chrono time points, civil dates/times, named-zone conversion and formatting/parsing. Low-level lookup distinguishes unique, skipped and repeated civil times. | Credible smaller alternative when timezone conversion is the central need. Build its timezone sources and supply zone data; add the project's own interval and validation layer. [Project](https://github.com/google/cctz), [zone API](https://github.com/google/cctz/blob/master/include/cctz/time_zone.h) |

`before(a,b)` for two valid instants is strict `a < b`; `after(a,b)` is `a > b`.
Equal instants satisfy neither. Libraries may expose these as operators rather
than methods literally named `before` and `after`. Boost's period-versus-date
methods are a different signature from instant-versus-instant comparison.

Release evidence shows ongoing upstream release activity: `date` lists
[v3.0.5](https://github.com/HowardHinnant/date/releases/tag/v3.0.5), CCTZ lists
[v2.5](https://github.com/google/cctz/releases), and Abseil lists
[LTS 20260817.0](https://github.com/abseil/abseil-cpp/releases). Boost.Date_Time
remains in the current [Boost library catalog](https://www.boost.org/library/latest/date_time/).
Pin a tested release and timezone-data revision; release presence is not a
performance result or a promise about future maintenance.

Licenses are permissive: `date` uses
[per-file MIT notices](https://github.com/HowardHinnant/date/blob/master/LICENSE.txt),
Boost.Date_Time uses [Boost Software License 1.0](https://www.boost.org/library/latest/date_time/),
and [Abseil](https://github.com/abseil/abseil-cpp/blob/master/LICENSE) and
[CCTZ](https://github.com/google/cctz/blob/master/LICENSE.txt) use Apache 2.0.
Package the notices and separately account for bundled timezone data.

## Sharing actual C++ code with Python

PyICU's current 2.16.2 source distribution was inspected without installing it:
`calendar.cpp` lines 226 and 240 directly call `self->object->before(*calendar,
status)` and `after(*calendar, status)`. This verifies shared implementation,
not merely matching Python method names. The distribution hash was checked
against PyPI metadata. [Published source archive](https://files.pythonhosted.org/packages/b7/d5/354eb1bf84dcf4ab0bfa46f0620ecf68fe313bb082c26872ceb7a5021f94/pyicu-2.16.2.tar.gz)

For ICU, call `setLenient(False)` in Python / `setLenient(false)` in C++ and
force validation before accepting input. Pin timezone, calendar system and
Gregorian cutover policy; the methods compare represented instants, not an
independent date-only or time-only domain. ICU documents millisecond precision;
its floating-point `UDate` is not a guarantee of exact microsecond round trips.
Select that precision contract explicitly, and pin matching ICU/data versions
for both backends. [Calendar semantics](https://unicode-org.github.io/icu-docs/apidoc/released/icu4c/classicu_1_1Calendar.html)

PyICU additionally converts floating-point timestamps between Python **seconds**
and ICU **milliseconds**. Account for this at the adapter boundary. Its existing
binding avoids writing a Python extension, but engine operator integration is
still needed. PyICU is MIT-licensed; ICU has its own Unicode license and bundled
third-party notices. [PyICU conventions and license](https://pypi.org/project/pyicu/),
[ICU license](https://github.com/unicode-org/icu/blob/main/LICENSE)

The current [native.py](/Users/raphaelvolz/Github/my-phd-thesis-gpt-6-astra/src/dlp_reasoner/native.py:84)
builds a C++17 shared library and loads a C ABI through `ctypes`; the existing
[header](/Users/raphaelvolz/Github/my-phd-thesis-gpt-6-astra/src/dlp_reasoner/native_store.h:1)
passes opaque term IDs, not temporal values. Extend the architecture with a
separately versioned temporal module or ABI capability:

```text
Python relation engine -- ctypes batch call --+
                                             +--> shared C++ temporal operators
C++ relation engine ------ direct call ------+
                                                   date / chrono / optional tz
```

Both paths should call the same checked parsing, normalization and comparison
functions. A C ABI can pass tagged fixed-width values or lexical input buffers,
per-row statuses and result masks; do not expose C++ objects across `ctypes`.
Python's [ctypes documentation](https://docs.python.org/3/library/ctypes.html)
describes this shared-library mechanism. This is a proposed binding to the real
C++ implementation, not an assertion that `date` ships this Python interface.

There is also a genuine existing binding route for Abseil:
[`pybind11_abseil`](https://github.com/pybind/pybind11_abseil) supplies conversions
for `absl::Time`, `Duration` and civil types in pybind11 extensions. However, its
documented defaults assume the machine's local timezone for naive datetimes,
convert Python dates to midnight, and truncate/ignore fields in some civil
conversions. A strict project adapter must override or reject those cases.

Likewise, default [pybind11 chrono conversions](https://pybind11.readthedocs.io/en/stable/advanced/cast/chrono.html)
are unsuitable as an unchecked instant boundary: documented Python input
conversion ignores timezone information, and system-clock output is a naive
local datetime. A custom wrapper is necessary even if pybind11 replaces ctypes.
Python `datetime`/`zoneinfo` implementations can be independent test oracles;
using them alone does not meet the requirement to execute the same C++ library.

Keep relation-backend selection separate from temporal-provider selection.
A Python relation engine using this temporal module still requires the module's
native binary. Preserve the existing dependency-free Python mode by making that
feature optional and reporting unavailable capabilities clearly. Prebuilt wheels
would avoid requiring an end-user compiler; this is additional packaging work.

## Temporal semantics the wrapper must own

| Input domain | Proposed comparison contract |
| --- | --- |
| Instant | Require explicit offset or resolved named zone; normalize to one declared time scale and compare exact ticks. |
| Calendar date | Compare valid calendar dates as dates; do not silently cast them to midnight instants. |
| Local date-time | Compare local fields only for an explicitly local-calendar operation; instant ordering requires a zone and ambiguity policy. |
| Time of day | Compare clock fields within a declared same-day domain. Midnight wrap and cross-zone ordering require additional date/context. |
| Interval | Follow the main proposal: nonempty half-open `[start,end)`. Implement containment/intersection and separately named Allen relations; touching intervals meet and do not intersect. |

The first instant profile can use checked signed 64-bit microseconds and an
explicit Unix/POSIX epoch. Choose a supported calendar range, reject excess
fractional precision rather than silently truncating, and check arithmetic before
overflow. Preserve RDF lexical identity separately from these decoded values.
`date::sys_time` is a chrono time-point alias, so comparison needs no invented
ordering of native term IDs. [Pinned declaration](https://raw.githubusercontent.com/HowardHinnant/date/v3.0.5/include/date/date.h)

Validate date fields before conversion: `date` deliberately permits invalid
field objects, with `ok()` for checking. In Abseil, out-of-range civil fields are
normalized, which must not accidentally make malformed input valid. Abseil also
documents duration saturation and a time scale without explicit leap seconds.
These behaviors require an explicit adapter policy; no candidate is a complete
XSD datatype validator. [Date validation](https://howardhinnant.github.io/date/date.html),
[Abseil value behavior](https://abseil.io/docs/cpp/guides/time)

For named zones, default to rejecting DST gaps and requiring an explicit choice
for folds. Hinnant's low-level `local_info` exposes both cases. Prefer a pinned,
managed timezone dataset; disable automatic network updates with
`HAS_REMOTE_API=0` and `AUTO_DOWNLOAD=0`. OS tzdb mode is an alternative, but
its available range/data/version must be checked rather than assumed equivalent.
Include the actual data revision in parsing/cache context and preserve it for
replay. [Timezone installation and conversion](https://howardhinnant.github.io/date/tz.html)

With CCTZ, inspect the boolean returned by zone loading: failure can leave the
output as UTC. Its convenience civil conversion also resolves gaps/folds by
policy; use the detailed lookup to enforce our contract. An empty reported zone
version is not evidence of a reproducible pinned dataset.
[CCTZ zone API](https://github.com/google/cctz/blob/master/include/cctz/time_zone.h)

Do not assume C++20 calendar/timezone support from the current `-std=c++17`
compiler invocation. Standard chrono can become a later implementation option
after compiler/library feature checks and identical conformance tests. For the
first slice, Hinnant's C++17-compatible implementation removes that uncertainty.

## First implementation and validation

Implement shared parsing and batched `before`, `after`, `equal`, fixed-duration
addition and interval containment first. Add named-zone resolution as a separate
capability. Make comparison errors distinct from `false`; catch exceptions at
the ABI boundary. Cache decoded temporal values and timezone objects, and batch
calls: a Python-to-C call per already-normalized comparison may cost more than
the comparison itself, so no speedup is assumed.

Validate both backends against the same cases: equal instants expressed with
different offsets; dates around leap day; invalid dates; DST gaps/folds under a
pinned zone database; negative epochs; precision/overflow boundaries; midnight
wrap; adjacent intervals; missing zones; and replay after a timezone-data update.
Neither scalar date comparisons nor these libraries implement watermarks,
window expiration, temporal rule recursion, or DRed automatically; those remain
the separate responsibilities described in the
[engine audit](engine-extension-audit.md).

## Mobile addendum: iOS and Android

**Keep `date.h` + `<chrono>` as the first mobile choice.** Compile the same
checked temporal kernel with Xcode and the Android NDK. Validated UTC or
fixed-offset instants can be normalized and compared without a named-zone
database; calendar dates and time-of-day values retain their separate contracts.
The header-only core has a smaller integration surface than bundling an ICU
calendar stack. This is an architectural recommendation, not a measured mobile
size or performance result. [Upstream scope](https://github.com/HowardHinnant/date)

Make named zones an optional, explicitly packaged capability: compile `tz.cpp`,
disable remote downloads, and ship a pinned timezone dataset in an app-readable
location. Set its installation path during initialization, before concurrent
queries. Android OS-tzdb support does exist: upstream added `USE_OS_TZDB` support
for Android in v3.0.2. OS data may differ between devices and releases, so this
mode alone does not guarantee identical replay. Do not assume a desktop zoneinfo
path or writable library directory on either mobile platform.
[Timezone configuration](https://howardhinnant.github.io/date/tz.html),
[Android support release](https://github.com/HowardHinnant/date/releases/tag/v3.0.2)

| Boundary | Proposed route |
| --- | --- |
| Swift / Objective-C on iOS | Import a small C header through a module or framework; link the app-owned C++ implementation. Swift also supports direct C++ interoperability, so Objective-C++ is not mandatory. The C ABI remains useful as the same boundary used by Python and JNI. [Swift library wrapping](https://www.swift.org/documentation/articles/wrapping-c-cpp-library-in-swift.html), [C++ interoperability](https://www.swift.org/documentation/cxx-interop/) |
| Kotlin / Java on Android | A thin JNI adapter calls that kernel. Batch values and results to limit marshalling and run work away from the UI thread. `JNIEnv` is thread-local and must not be shared between threads. [Android JNI guidance](https://developer.android.com/ndk/guides/jni-tips) |
| Desktop Python | Keep `ctypes` over the same C ABI and semantics. Mobile Python requires its own embedded runtime and binary packaging, described below. |

Use opaque handles, fixed-width integer ticks, explicit ownership, bounded
batches and per-row error statuses at this interface. Keep C++ exceptions and
library-specific objects inside the native module. These are proposed project
interfaces; `date` does not supply these language bindings.

**ICU + PyICU remains a real existing binding, but system ICU is not a shared
mobile C++ dependency contract.** Android provides a subset of ICU4C through
`libicu.so` starting at Android 12/API 31, with NDK headers from r22b; the NDK
explicitly exposes no ICU C++ API. The `android.icu` Java API introduced at API 24
is a subset of ICU4J, not PyICU's binding to `icu::Calendar`.
[Android ICU availability](https://developer.android.com/guide/topics/resources/internationalization)

Apple's archived documentation describes a limited set of ICU regular-expression
headers; it does not establish public availability of ICU's full C++ Calendar
API on current iOS. Do not treat undocumented `libicucore` symbols as the
portable solution. If full ICU Calendar semantics are required on both mobile
platforms, plan to cross-compile and package an app-owned ICU build and its data,
and test that configuration. Apple requires public APIs; this is not a claim
that all system ICU functionality is private.
[Archived Apple ICU scope](https://developer.apple.com/library/archive/documentation/StringsTextFonts/Conceptual/TextAndWebiPhoneOS/LowerLevelText-HandlingTechnologies/LowerLevelText-HandlingTechnologies.html),
[App Review guideline 2.5.1](https://developer.apple.com/app-store/review/guidelines/)

**Embedding Python is supported, but is an alternative deployment architecture.**
CPython documents embedded mode for both platforms: the app bundles the
interpreter, standard library and dependencies. On iOS, Python binary extension
modules need the documented framework/signing layout, and device and simulator
builds are distinct. On Android, the app packages native libraries and Python
assets, with JNI as an entry point. PyICU would additionally need compatible
cross-compiled ICU and extension binaries; this research has not verified that
mobile build. Desktop wheels cannot be assumed to work unchanged.
[CPython on iOS](https://docs.python.org/3/using/ios.html),
[CPython on Android](https://docs.python.org/3/using/android.html)

The current `native.py` runtime compiler/cache workflow must become build-time
cross-compilation and app packaging. More fundamentally, the existing C++
backend stores relations and executes joins; Python still owns reasoning and
updates. A mobile temporal library alone does not produce a complete standalone
C++ reasoner. Choose either embedded Python with packaged native dependencies
or a further native engine port. Neither mobile configuration has been built or
benchmarked in this research.
