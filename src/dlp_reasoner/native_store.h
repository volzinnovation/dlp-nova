#ifndef DLP_REASONER_NATIVE_STORE_H
#define DLP_REASONER_NATIVE_STORE_H

/* Optional C++17 indexed relation backend. IDs are opaque uint64 values;
 * zero is reserved for an unbound query slot and is never a stored term.
 * Handles are single-threaded: do not call operations on a store/query
 * concurrently. A query owns its stores even after their handles are freed.
 * A successful mutation invalidates existing queries, which then fail safely.
 * Every int-returning operation returns 0 on success and -1 on error. Read
 * dlp_last_error() immediately on the same thread; its string is borrowed.
 */
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct dlp_store dlp_store;
typedef struct dlp_query dlp_query;

typedef struct dlp_atom {
    uint64_t predicate;
    size_t arity;
    /* arity entries: -1 means constant; >= 0 is a binding slot. */
    const int32_t *slots;
    /* arity entries: nonzero for constants; ignored for variables. */
    const uint64_t *constants;
} dlp_atom;

uint32_t dlp_abi_version(void);
const char *dlp_last_error(void);
int dlp_store_new(dlp_store **out);
void dlp_store_free(dlp_store *store);

/* Flat row-major data; NULL is valid for zero rows or zero arity. Bulk
 * mutation validates the whole batch first. Allocation failure may leave
 * a successfully applied prefix, with the indexes consistent and queries
 * invalidated. Each nonempty predicate has one fixed arity; removing its
 * final tuple removes the relation and permits a later different arity. */
int dlp_store_add_rows(dlp_store *store, uint64_t predicate, size_t arity,
                       const uint64_t *data, size_t row_count, size_t *changed);
int dlp_store_discard_rows(dlp_store *store, uint64_t predicate, size_t arity,
                           const uint64_t *data, size_t row_count, size_t *changed);
int dlp_store_clear(dlp_store *store);
int dlp_store_relation_info(dlp_store *store, uint64_t predicate,
                            size_t *arity, size_t *row_count, int *exists);
int dlp_store_contains(dlp_store *store, uint64_t predicate, size_t arity,
                       const uint64_t *row, int *contains);

/* Match Python _Index.lookup: all-bound patterns use hash membership;
 * otherwise return the smallest column bucket, with other constraints left
 * to the caller. 0 in values means unbound. A NULL output with capacity 0
 * reports the required row count. Otherwise capacity is in rows and must
 * hold that entire bucket; no silent truncation. Zero-arity rows have no
 * cells but are still counted. No mutation may occur between sizing/copying. */
int dlp_store_lookup(dlp_store *store, uint64_t predicate, size_t arity,
                      const uint64_t *values, uint64_t *output,
                      size_t capacity, size_t *row_count);

/* Copy the plan and initial bindings (NULL initial means all unbound).
 * delta_position=-1 disables delta. Otherwise exactly that atom occurrence
 * reads delta_store, even when its predicate also appears in other atoms.
 * All remaining occurrences read store. Slot count may be zero; an empty
 * conjunction yields the initial binding exactly once. No row snapshots or
 * query result sets are materialized. */
int dlp_query_new(dlp_store *store, dlp_store *delta_store,
                  const dlp_atom *atoms, size_t atom_count, size_t slot_count,
                  const uint64_t *initial, int64_t delta_position,
                  dlp_query **out);
/* Write at most capacity complete bindings, row-major in slot_count cells.
 * capacity must be positive; NULL output is allowed only at slot_count=0.
 * done=1 means exhausted. A full batch may have done=0 even when it contains
 * the final result; call next again. On error written=0 and done=1; discard
 * any output cells. The failed query cannot subsequently resume. */
int dlp_query_next(dlp_query *query, uint64_t *output, size_t capacity,
                   size_t *written, int *done);
int dlp_query_stats(dlp_query *query, uint64_t *candidate_rows,
                    uint64_t *body_matches);
void dlp_query_free(dlp_query *query);

#ifdef __cplusplus
}
#endif
#endif
