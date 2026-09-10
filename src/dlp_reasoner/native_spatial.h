#ifndef DLP_NATIVE_SPATIAL_H
#define DLP_NATIVE_SPATIAL_H
#include <stddef.h>
#include <stdint.h>
#ifdef _WIN32
#define DLP_SPATIAL_API __declspec(dllexport)
#else
#define DLP_SPATIAL_API
#endif
#ifdef __cplusplus
#define DLP_SPATIAL_NOEXCEPT noexcept
extern "C" {
#else
#define DLP_SPATIAL_NOEXCEPT
#endif
/* Immutable XYZ index. Coordinates/bounds are finite doubles in metres.
 * Status: 0 success, 1 invalid argument, 2 allocation failure, 3 internal error.
 * Caller owns valid input buffers, serializes handle access and frees each handle
 * once. Query handles retain their index data independently of the index handle.
 * next() fills at most capacity IDs and never buffers the complete candidate set.
 */
DLP_SPATIAL_API uint32_t dlp_spatial_abi(void) DLP_SPATIAL_NOEXCEPT;
DLP_SPATIAL_API int dlp_spatial_new(const double *xyz, size_t count,
                                    void **output) DLP_SPATIAL_NOEXCEPT;
DLP_SPATIAL_API void dlp_spatial_free(void *handle) DLP_SPATIAL_NOEXCEPT;
DLP_SPATIAL_API int dlp_spatial_query(void *handle, const double *lower, const double *upper,
                                      void **output) DLP_SPATIAL_NOEXCEPT;
DLP_SPATIAL_API int dlp_spatial_next(void *handle, uint64_t *rows, size_t capacity, size_t *count,
                                     int *done) DLP_SPATIAL_NOEXCEPT;
DLP_SPATIAL_API void dlp_spatial_query_free(void *handle) DLP_SPATIAL_NOEXCEPT;
#ifdef __cplusplus
}
#endif
#endif
