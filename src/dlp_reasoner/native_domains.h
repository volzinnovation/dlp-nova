#ifndef DLP_NATIVE_DOMAINS_H
#define DLP_NATIVE_DOMAINS_H
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
/* ABI 1: flat immutable value batches. No pointers/ownership inside values.
 * tag: 1 bool, 2 int64, 3 decimal64, 4 binary64, 5 Gregorian date,
 * 6 POSIX instant us, 7 clock us, 8 fixed duration us, 9 WGS84 point,
 * 10 half-open interval, 11 march1 policy, 12 quantity, 13 unit.
 * a/b/c: bool/int/ticks in a; decimal coefficient a, scale b;
 * date year/month/day; interval start/end scalar keys a/b and endpoint tag c.
 * Date interval keys use Gregorian ordinal (0001-01-01 = 1).
 * point x/y = longitude/latitude; binary64 uses x. Quantity a/b=coefficient/scale,
 * c=numeric tag, x=unit code (1 metre, 2 second, 3 kmh); unit uses a=code.
 * Unused fields must be zero.
 * status: 0 OK, 1 TYPE_ERROR, 2 DOMAIN_ERROR, 3 OVERFLOW, 4 INEXACT,
 * 5 UNAVAILABLE, 6 RESOURCE_LIMIT, 7 INTERNAL_ERROR, 8 ARITY_ERROR.
 * Row failures do not cancel other rows. Nonzero row status makes output invalid.
 * Overall -1 means malformed batch arguments; discard all outputs. No exception
 * crosses this interface. Read last_error immediately on the same thread.
 * Stateless calls may execute concurrently. Context calls require one owner.
 */
typedef struct dlp_domain_value {
    uint32_t tag;
    uint32_t reserved;
    int64_t a, b, c;
    double x, y;
} dlp_domain_value;
uint32_t dlp_domain_abi_version(void);
uint32_t dlp_domain_capabilities(void); /* bit 0: GeographicLib geodesic C API */
const char *dlp_domain_last_error(void);
const char *dlp_domain_geodesic_version(void);
int dlp_domain_evaluate(uint32_t opcode, const dlp_domain_value *inputs,
                        size_t rows, size_t arity, dlp_domain_value *outputs,
                        int32_t *statuses);

/* Resident immutable decoded values. IDs are context-local, nonzero and never
 * reused, including after clear. Clearing/releasing a context invalidates all
 * its IDs; stale IDs are checked and rejected. No pointers inside a value.
 * Contexts do not evict live IDs automatically. Capacity exhaustion is explicit;
 * the host may clear at a batch boundary and re-intern needed values. */
typedef struct dlp_domain_context dlp_domain_context;
typedef struct dlp_domain_context_stats {
    uint64_t retained_values, capacity, generation, intern_requests, intern_hits;
    uint64_t transferred_inputs, transferred_outputs, evaluated_rows, clears;
} dlp_domain_context_stats;
int32_t dlp_domain_context_last_status(void); /* last context-wide failure code */
int dlp_domain_context_new(uint64_t capacity, dlp_domain_context **out);
void dlp_domain_context_free(dlp_domain_context *);
int dlp_domain_context_clear(dlp_domain_context *);
/* On -1 discard all outputs. Allocation failures may retain a valid prefix;
 * clear permits recovery. Validation/capacity preflight precedes insertion. */
int dlp_domain_context_intern(dlp_domain_context *, const dlp_domain_value *values,
                              size_t count, uint64_t *ids);
int dlp_domain_context_get(dlp_domain_context *, const uint64_t *ids, size_t count,
                           dlp_domain_value *values, int32_t *statuses);
/* Compute entirely from resident input values. Successful outputs are interned
 * and returned as IDs, with no value payload exported. Per-row errors have ID0.
 * Call get only for result values needed by the host. Capacity failure publishes
 * no output IDs; the retained input table remains usable. */
int dlp_domain_context_evaluate(dlp_domain_context *, uint32_t opcode,
                                const uint64_t *input_ids, size_t rows, size_t arity,
                                uint64_t *output_ids, int32_t *statuses);
/* Exact ordered-value comparison for MIN: int/decimal share a value domain;
 * temporal tags stay distinct, binary64 requires binary64, quantities require
 * identical unit. Point, interval, bool and policy/unit have no scalar order. */
int dlp_domain_context_compare(dlp_domain_context *, uint64_t left, uint64_t right,
                               int32_t *ordering);
int dlp_domain_context_get_stats(dlp_domain_context *, dlp_domain_context_stats *);
#ifdef __cplusplus
}
#endif
#endif
