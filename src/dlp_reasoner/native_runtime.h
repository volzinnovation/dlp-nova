#ifndef DLP_NATIVE_RUNTIME_H
#define DLP_NATIVE_RUNTIME_H
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
/* Standalone C++17 Horn runtime, ABI 1. No CPython or RDF parser dependency.
 * One worker owns a handle. All int functions return 0 success, -1 failure;
 * read error_code/error immediately on this thread. Builders are mutable only
 * before successful materialize. A failed materialization publishes no result.
 * IDs are nonzero. Predicates, symbols and terms use independent ID spaces.
 * No call retains caller-owned pointers. No C++ exception crosses this ABI. */
typedef struct dlp_runtime dlp_runtime;
typedef struct dlp_runtime_expr {
    uint32_t kind; /* 0 constant, 1 variable, 2 Skolem application */
    uint32_t reserved;
    uint64_t reference; /* term ID, zero-based variable slot, symbol ID */
    size_t arity;
    const struct dlp_runtime_expr *arguments; /* Skolem children only */
} dlp_runtime_expr;
typedef struct dlp_runtime_atom {
    uint64_t predicate;
    size_t arity;
    const dlp_runtime_expr *arguments;
} dlp_runtime_atom;
typedef struct dlp_runtime_limits {
    uint64_t max_rounds, max_facts, max_terms, max_depth;
} dlp_runtime_limits;
typedef struct dlp_runtime_stats {
    uint64_t rounds, facts, terms, candidate_rows, body_matches, equality_merges;
    uint64_t violations;
    int32_t complete;
    int32_t reserved;
} dlp_runtime_stats;
uint32_t dlp_runtime_abi_version(void);
const char *dlp_runtime_error(void);
int32_t
dlp_runtime_error_code(void); /* 1 invalid IR; 2 limit; 3 allocation; 4 internal; 5 cancelled */
int dlp_runtime_new(uint64_t eq, uint64_t neq, uint64_t top, uint64_t seed,
                    const dlp_runtime_limits *limits, dlp_runtime **out);
void dlp_runtime_free(dlp_runtime *runtime);
/* Thread-safe sticky cancellation only: a second thread may call this while
 * materialize runs. The host must keep the handle alive; concurrent free or any
 * other mutation is forbidden. Cancellation publishes no candidate snapshot. */
int dlp_runtime_cancel(dlp_runtime *runtime);
/* Explicit work bounds, in addition to the structural/fact/depth limits.
 * Defaults: 100,000,000 candidate rows; 10,000,000 complete body matches;
 * 100,000 distinct violations. Set before materialize; all must be positive. */
int dlp_runtime_set_work_limits(dlp_runtime *, uint64_t candidates, uint64_t matches,
                                uint64_t violations);
/* category: URI=0, literal=1, other=2. order_key is a stable UTF-8 compiler
 * ordering key within category, encoded as type-name:term-representation. literal_group=0 means
 * opaque; equal nonzero groups mean known equal datatype values; unequal groups mean known
 * distinct. Only registered/used terms participate in automatic datatype equality. Declare every
 * constant before adding rules/facts; seed must be declared. */
/* Declare symbols before terms/rules. quoted_symbol is the compiler's stable
 * quoted representation, used with child spellings for canonical witness order. */
int dlp_runtime_add_symbol(dlp_runtime *, uint64_t symbol, const char *quoted_symbol);
int dlp_runtime_add_term(dlp_runtime *, uint64_t id, uint32_t category, const char *order_key,
                         uint64_t literal_group);
/* Ground application children must have been declared previously. */
int dlp_runtime_add_skolem(dlp_runtime *, uint64_t id, uint64_t symbol, const uint64_t *arguments,
                           size_t arity);
int dlp_runtime_add_fact(dlp_runtime *, uint64_t predicate, const uint64_t *arguments,
                         size_t arity);
int dlp_runtime_add_rule(dlp_runtime *, const dlp_runtime_atom *head, const dlp_runtime_atom *body,
                         size_t count, size_t variable_count, const char *label);
int dlp_runtime_materialize(dlp_runtime *);
int dlp_runtime_get_stats(dlp_runtime *, dlp_runtime_stats *out);
/* Snapshot facts are sorted by predicate then ID tuple. Sizing call with
 * arguments=NULL/capacity=0 always reports arity; later copy must fit exactly.
 * facts/normalization/violations are available only after successful commit. */
int dlp_runtime_fact(dlp_runtime *, size_t index, uint64_t *predicate, uint64_t *arguments,
                     size_t capacity, size_t *arity);
int dlp_runtime_normalize(dlp_runtime *, uint64_t term, uint64_t *canonical);
/* kind=0 is a declared scalar; kind=2 is a Skolem. Exports canonical child IDs
 * for witnesses, including ones declared in input. Same sizing convention. */
int dlp_runtime_term(dlp_runtime *, uint64_t term, uint32_t *kind, uint64_t *symbol,
                     uint64_t *arguments, size_t capacity, size_t *arity);
/* Read-only interning lookup on canonical children; found ID=0 means absent. */
int dlp_runtime_find_skolem(dlp_runtime *, uint64_t symbol, const uint64_t *arguments, size_t arity,
                            uint64_t *found);
int dlp_runtime_violation(dlp_runtime *, size_t index, const char **message);
#ifdef __cplusplus
}
#endif
#endif
