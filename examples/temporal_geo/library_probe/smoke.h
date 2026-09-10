#ifndef DLP_LIBRARY_SMOKE_H
#define DLP_LIBRARY_SMOKE_H
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
/* 0=success, 1=invalid argument, 2=library/evaluation failure.
 * Outputs are written only on success. Borrowed version strings are immutable.
 * No C++ type, geometry pointer, exception, or ownership crosses this ABI. */
int smoke_instant_compare(int64_t left_us, int64_t right_us, int *order);
int smoke_date_compare(int y1, unsigned m1, unsigned d1,
                       int y2, unsigned m2, unsigned d2, int *order);
int smoke_distance(double x1, double y1, double x2, double y2, double *metres);
int smoke_dwithin(double x1, double y1, double x2, double y2,
                  double radius, int *within);
int smoke_geodesic(double lat1, double lon1, double lat2, double lon2, double *metres);
const char *smoke_date_version(void);
const char *smoke_geos_version(void);
const char *smoke_proj_version(void);
#ifdef __cplusplus
}
#endif
#endif
