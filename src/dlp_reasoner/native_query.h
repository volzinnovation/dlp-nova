#ifndef DLP_NATIVE_QUERY_H
#define DLP_NATIVE_QUERY_H
#include "native_domains.h"
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
/* ABI 1, finite stratified query execution. This context owns its input rows,
 * copied plans, typed values and candidate result. No Python runtime is needed.
 * Calls require one serialized owner. Every pointer passed in is copied except
 * the cancellation callback, which is used only during run. Failure never
 * exposes a partial answer; begin/run failure requires begin before retry.
 * Integer-returning functions return 0 or -1; read last_error/status immediately.
 * Status 1..8 has native_domains.h meaning; 9 means cancelled/control failure.
 */
typedef struct dlp_qx_context dlp_qx_context;
typedef struct dlp_qx_arg {
    int32_t slot;
    uint64_t constant;
} dlp_qx_arg;
typedef struct dlp_qx_node {
    /* 0 relation, 1 EQ, 2 NEQ, 3 filter, 4 bind, 5 MIN. */
    uint32_t kind, opcode;
    uint64_t predicate;
    size_t arity;
    const dlp_qx_arg *args;
    dlp_qx_arg output;
    size_t group_count;
    const int32_t *groups;
    int32_t value_slot;
} dlp_qx_node;
typedef struct dlp_qx_limits {
    uint64_t max_rows, max_bindings, max_rounds, max_terms, max_work;
} dlp_qx_limits;
typedef struct dlp_qx_stats {
    uint64_t rounds, candidate_rows, body_matches, operation_rows, domain_evaluations;
    uint64_t generated_terms, input_additions, input_removals, work;
    uint64_t memo_hits, memo_entries, memo_bytes, memo_evictions, memo_bypasses;
} dlp_qx_stats;
typedef int (*dlp_qx_control)(void *user); /* 0 continue, nonzero cancel */
uint32_t dlp_qx_abi_version(void);
const char *dlp_qx_last_error(void);
int32_t dlp_qx_last_status(void);
int dlp_qx_new(const dlp_qx_limits *, dlp_qx_context **out);
void dlp_qx_free(dlp_qx_context *);
/* Synchronize ground input rows. Rows survive begin/run. No derived row ever
 * enters this source store. An empty relation may subsequently change arity.
 * A failed mutation poisons the context; free/rebuild it before further use.
 * Allocation failure can apply a prefix internally but can never publish it. */
int dlp_qx_rows(dlp_qx_context *, uint64_t predicate, size_t arity, const uint64_t *rows,
                size_t count, int add);
/* Reset candidate/plan/term metadata while retaining input rows. Domain IDs
 * never leave this context. max_terms counts active relation terms, including
 * parameters and constants supplied through term(), independently of row count. */
int dlp_qx_begin(dlp_qx_context *);
/* Each active term has a nonzero host identity. A decoded domain value is
 * optional (tag=0); decode_status is deferred until an operation needs it.
 * canonical=1 iff this host term is the canonical RDF output of that value.
 * neq_group: 0 unknown, 1 RDF number, 2 Boolean, 3 string, 4 language literal.
 * neq_key identifies equal RDF literal values within the entire host snapshot.
 * These are explicit host-provided RDF boundary metadata, not scalar callbacks. */
int dlp_qx_term(dlp_qx_context *, uint64_t id, const dlp_domain_value *, int32_t decode_status,
                int canonical, uint32_t neq_group, uint64_t neq_key);
/* Stable MIN tie keys, UTF-8 tuple components separated by NUL, copied here.
 * Actual RDF identity: ('literal', datatype URI, language, lexical form).
 * Other value identity: ('value', qualified Python/host value type, stable repr).
 * Supply the corresponding canonical RDF output identity for a decoded value.
 * A key is required if distinct terms with equal ordered values reach MIN.
 * Each key is limited to 32768 bytes. No host object/pointer is retained. */
int dlp_qx_term_order(dlp_qx_context *, uint64_t id, const char *identity, size_t identity_size,
                      const char *canonical_identity, size_t canonical_size);
/* Per-argument-role lexical metadata independent of generic domain decoding:
 * bit0 unit-eligible str/URI/literal, bit1 accepted march1 policy spelling,
 * bits2..3 known unit (1metre,2second,3kmh). Other bits must be zero. */
int dlp_qx_term_roles(dlp_qx_context *, uint64_t id, uint32_t flags);
/* Pure built-in successful outputs may be retained by opcode + typed POD input
 * bytes between begin() calls. No term/domain IDs enter the memo. Both limits
 * apply; zero disables retention. Byte counts are conservative, not process RSS. */
int dlp_qx_memo_limits(dlp_qx_context *, uint64_t max_entries, uint64_t max_bytes);
int dlp_qx_rule(dlp_qx_context *, uint64_t stratum, uint64_t head_predicate, size_t head_arity,
                const dlp_qx_arg *head, size_t slot_count, const uint64_t *initial,
                const dlp_qx_node *body, size_t body_count);
/* Validate copied rules without executing them. Explicit given slots may use
 * any registered sentinel ID while loading a package. No result is published. */
int dlp_qx_validate(dlp_qx_context *);
int dlp_qx_run(dlp_qx_context *, dlp_qx_control, void *user);
/* Query rows only after successful run. Cursor offset is local to a predicate;
 * capacity is a positive number of rows. Unknown/empty predicates return zero.
 * Generated IDs resolve through value(); original IDs retain host RDF identity. */
int dlp_qx_result(dlp_qx_context *, uint64_t predicate, size_t arity, size_t offset,
                  uint64_t *output, size_t capacity, size_t *written, int *done);
int dlp_qx_value(dlp_qx_context *, uint64_t id, dlp_domain_value *value);
int dlp_qx_get_stats(dlp_qx_context *, dlp_qx_stats *);
#ifdef __cplusplus
}
#endif
#endif
