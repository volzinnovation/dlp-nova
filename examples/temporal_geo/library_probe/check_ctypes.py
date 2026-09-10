"""Call the same C ABI as driver.cpp and compare every result field."""

import argparse
import ctypes as c
import json
import math
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("build_dir", type=Path, help="Temporary directory containing the library and C++ output")
root = parser.parse_args().build_dir.resolve()
library = c.CDLL(str(root / "libdlp_smoke.dylib"))
int_out = c.POINTER(c.c_int)
double_out = c.POINTER(c.c_double)
signatures = {
    "smoke_instant_compare": [c.c_int64, c.c_int64, int_out],
    "smoke_date_compare": [c.c_int, c.c_uint, c.c_uint, c.c_int, c.c_uint, c.c_uint, int_out],
    "smoke_distance": [c.c_double] * 4 + [double_out],
    "smoke_dwithin": [c.c_double] * 5 + [int_out],
    "smoke_geodesic": [c.c_double] * 4 + [double_out],
}
for name, arguments in signatures.items():
    function = getattr(library, name)
    function.argtypes = arguments
    function.restype = c.c_int


def checked(name, values, output_type):
    result = output_type()
    status = getattr(library, name)(*values, c.byref(result))
    if status != 0:
        raise AssertionError(f"{name} failed with status {status}")
    return result.value


def require(condition, label):
    if not condition:
        raise AssertionError(label)


result = {}
for family in ("date", "geos", "proj"):
    function = getattr(library, f"smoke_{family}_version")
    function.argtypes = []
    function.restype = c.c_char_p
    result[f"{family}_version"] = function().decode()

result["instant_order"] = [
    checked("smoke_instant_compare", pair, c.c_int)
    for pair in ((1000000, 1000001), (1000001, 1000000), (1000000, 1000000))
]
result["date_order"] = [
    checked("smoke_date_compare", dates, c.c_int)
    for dates in ((2024, 2, 29, 2024, 3, 1), (2024, 3, 1, 2024, 2, 29),
                  (2024, 2, 29, 2024, 2, 29))
]
require(result["instant_order"] == [-1, 1, 0], "instant ordering")
require(result["date_order"] == [-1, 1, 0], "calendar/sys_days ordering")
sentinel = c.c_int(77)
result["invalid_date_status"] = library.smoke_date_compare(
    2023, 2, 29, 2024, 3, 1, c.byref(sentinel))
require(result["invalid_date_status"] == 1 and sentinel.value == 77, "invalid date rejection")
result["projected_distance_metres"] = checked("smoke_distance", (0, 0, 30, 40), c.c_double)
require(result["projected_distance_metres"] == 50, "projected point distance")
result["dwithin_50_49"] = [
    checked("smoke_dwithin", (0, 0, 30, 40, radius), c.c_int) for radius in (50, 49)
]
require(result["dwithin_50_49"] == [1, 0], "inclusive dwithin boundary")
result["geodesic_metres"] = checked("smoke_geodesic", (0, 0, 0, 1), c.c_double)
require(math.isclose(result["geodesic_metres"], 111319.49079327357,
                     rel_tol=0, abs_tol=1e-6), "WGS84 inverse")
result["negative_radius_status"] = library.smoke_dwithin(0, 0, 30, 40, -1, c.byref(sentinel))
result["null_output_status"] = library.smoke_instant_compare(0, 1, None)
unchanged = c.c_double(77)
result["invalid_latitude_status"] = library.smoke_geodesic(91, 0, 0, 1, c.byref(unchanged))
require(all(result[key] == 1 for key in ("negative_radius_status", "null_output_status",
                                        "invalid_latitude_status")), "argument statuses")
require(sentinel.value == 77 and unchanged.value == 77, "failure preserves outputs")
cpp_result = json.loads((root / "cpp-output.json").read_text())
require(result == cpp_result, "C++/ctypes outputs differ")
(root / "python-output.json").write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps({"status": "PASS", "same_shared_library_outputs": True,
                  "python_output": result}, indent=2))
