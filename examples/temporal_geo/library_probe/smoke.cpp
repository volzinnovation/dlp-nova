#include "smoke.h"
#include <date/date.h>
#include <geos_c.h>
#include <geodesic.h>
#include <proj.h>
#include <chrono>
#include <cmath>

namespace {
struct Points {
    GEOSContextHandle_t context = GEOS_init_r();
    GEOSGeometry *first = nullptr;
    GEOSGeometry *second = nullptr;
    Points(double x1, double y1, double x2, double y2) {
        if (context) {
            first = GEOSGeom_createPointFromXY_r(context, x1, y1);
            second = GEOSGeom_createPointFromXY_r(context, x2, y2);
        }
    }
    ~Points() {
        if (context) {
            if (first) GEOSGeom_destroy_r(context, first);
            if (second) GEOSGeom_destroy_r(context, second);
            GEOS_finish_r(context);
        }
    }
    bool ok() const { return context && first && second; }
    Points(const Points &) = delete;
    Points &operator=(const Points &) = delete;
};
bool finite_points(double x1, double y1, double x2, double y2) {
    return std::isfinite(x1) && std::isfinite(y1) &&
           std::isfinite(x2) && std::isfinite(y2);
}
bool basic_date_range(int year, unsigned month, unsigned day) {
    return year >= -32767 && year <= 32767 && month >= 1 && month <= 12 &&
           day >= 1 && day <= 31;
}
}

extern "C" int smoke_instant_compare(int64_t left_us, int64_t right_us, int *order) {
    if (!order) return 1;
    try {
        using micros = std::chrono::microseconds;
        const date::sys_time<micros> left{micros{left_us}}, right{micros{right_us}};
        *order = left < right ? -1 : left > right ? 1 : 0;
        return 0;
    } catch (...) { return 2; }
}

extern "C" int smoke_date_compare(int y1, unsigned m1, unsigned d1,
                                   int y2, unsigned m2, unsigned d2, int *order) {
    if (!order || !basic_date_range(y1,m1,d1) || !basic_date_range(y2,m2,d2)) return 1;
    try {
        const date::year_month_day left{date::year{y1},date::month{m1},date::day{d1}};
        const date::year_month_day right{date::year{y2},date::month{m2},date::day{d2}};
        // Validate before converting; invalid calendar dates must not normalize silently.
        if (!left.ok() || !right.ok()) return 1;
        const date::sys_days left_days{left}, right_days{right};
        const int calendar_order = left < right ? -1 : left > right ? 1 : 0;
        const int days_order = left_days < right_days ? -1 : left_days > right_days ? 1 : 0;
        if (calendar_order != days_order) return 2;
        *order = days_order;
        return 0;
    } catch (...) { return 2; }
}

extern "C" int smoke_distance(double x1, double y1, double x2, double y2, double *metres) {
    if (!metres || !finite_points(x1,y1,x2,y2)) return 1;
    try {
        Points points{x1,y1,x2,y2};
        if (!points.ok()) return 2;
        double value = 0;
        if (GEOSDistance_r(points.context,points.first,points.second,&value) != 1 ||
            !std::isfinite(value)) return 2;
        *metres = value;
        return 0;
    } catch (...) { return 2; }
}

extern "C" int smoke_dwithin(double x1, double y1, double x2, double y2,
                              double radius, int *within) {
    if (!within || !finite_points(x1,y1,x2,y2) || !std::isfinite(radius) || radius < 0)
        return 1;
    try {
        Points points{x1,y1,x2,y2};
        if (!points.ok()) return 2;
        const char result = GEOSDistanceWithin_r(points.context,points.first,points.second,radius);
        // GEOS predicates use 0=false, 1=true, 2=exception; 2 must not become true.
        if (result != 0 && result != 1) return 2;
        *within = result;
        return 0;
    } catch (...) { return 2; }
}

extern "C" int smoke_geodesic(double lat1, double lon1, double lat2, double lon2,
                               double *metres) {
    if (!metres || !finite_points(lat1,lon1,lat2,lon2) ||
        std::abs(lat1) > 90 || std::abs(lat2) > 90 ||
        std::abs(lon1) > 180 || std::abs(lon2) > 180) return 1;
    try {
        geod_geodesic ellipsoid;
        geod_init(&ellipsoid,6378137.0,1.0/298.257223563);
        double value = 0;
        // PROJ's bundled geodesic C API takes latitude, longitude in degrees.
        geod_inverse(&ellipsoid,lat1,lon1,lat2,lon2,&value,nullptr,nullptr);
        if (!std::isfinite(value)) return 2;
        *metres = value;
        return 0;
    } catch (...) { return 2; }
}

extern "C" const char *smoke_date_version() { return "v3.0.5"; }
extern "C" const char *smoke_geos_version() { return GEOSversion(); }
extern "C" const char *smoke_proj_version() { return proj_info().version; }
