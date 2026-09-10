#ifndef DLP_NATIVE_PACKAGE_H
#define DLP_NATIVE_PACKAGE_H
#include "native_query.h"
#include "native_runtime.h"
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
/* Portable native Horn package, DLPNPKG1. All wire integers little-endian;
 * length-delimited records and SHA-256 checksum; no host struct serialization.
 * Loader bounds: 64 MiB payload, 1 MiB per text/context field, 2,000,000 records,
 * 100,000 rules, expression depth256/body512. Runtime bounds are supplied below.
 * Domain semantic profile dlp-domains-v1 is mandatory. Unknown required records
 * and provider sections fail explicitly. Local query records are supported. No CPython or JSON
 * dependency. Compile-time literal identity groups are trusted compiled semantic metadata, just as
 * the compiled rules are; a checksum provides integrity, not authenticity.
 */
typedef struct dlp_native_package dlp_native_package;
typedef struct dlp_package_term_view {
    uint64_t id;
    uint32_t kind; /* 1 IRI, 2 BNode, 3 Literal, 4 string, 5 integer, 6 seed, 7 Skolem */
    uint32_t reserved;
    const char *lexical;
    size_t lexical_size;
    const char *datatype;
    size_t datatype_size; /* NULL means absent */
    const char *language;
    size_t language_size; /* NULL means absent */
    uint64_t symbol;
    const uint64_t *arguments;
    size_t arity;
} dlp_package_term_view;
typedef struct dlp_native_package_options {
    dlp_runtime_limits reasoning;
    uint64_t max_candidates, max_matches, max_violations;
} dlp_native_package_options;
typedef struct dlp_package_parameter {
    const char *name;
    uint64_t id;
    dlp_domain_value value;
    int32_t decode_status;
    uint32_t canonical, neq_group;
    uint64_t neq_key;
    const char *identity_order;
    size_t identity_order_size;
    const char *canonical_order;
    size_t canonical_order_size;
    uint32_t roles;
} dlp_package_parameter;
/* Local query preparation copies the Horn snapshot and compiled plan into an
 * independently owned qx context. Required givens are explicit parameter names.
 * New parameter IDs must be >= next_term_id; known IDs may be bound by name
 * with their existing metadata. The host owns new RDF identity/NEQ metadata.
 * Before run, add scoped rows/terms with qx_rows/qx_term/term_order; no birthdate,
 * location selection or completeness certificate is inferred by this loader. */
int dlp_native_package_next_term_id(dlp_native_package *, uint64_t *out);
int dlp_native_package_prepare_query(dlp_native_package *, const dlp_qx_limits *,
                                     const dlp_package_parameter *, size_t count,
                                     dlp_qx_context **out);
uint32_t dlp_native_package_abi_version(void);
const char *dlp_native_package_error(void);
int32_t dlp_native_package_error_code(
    void); /* 1 format, 2 incompatible, 3 resource, 4 semantics, 5 internal, 6 cancelled */
/* Publishes a complete native Horn runtime only after validating all records and
 * successfully materializing. On error *out=NULL. Input bytes are not retained. */
int dlp_native_package_load(const uint8_t *bytes, size_t size, const dlp_native_package_options *,
                            dlp_native_package **out);
void dlp_native_package_free(dlp_native_package *);
/* Borrowed runtime lives until package free. take_runtime transfers ownership
 * to caller, who must call dlp_runtime_free, leaving dictionary access available. */
int dlp_native_package_runtime(dlp_native_package *, dlp_runtime **out);
int dlp_native_package_take_runtime(dlp_native_package *, dlp_runtime **out);
const char *dlp_native_package_profile(dlp_native_package *);
int dlp_native_package_context(dlp_native_package *, const uint8_t **bytes, size_t *size);
int dlp_native_package_counts(dlp_native_package *, size_t *terms, size_t *predicates,
                              size_t *symbols);
/* All view pointers are borrowed and remain valid until package free. */
int dlp_native_package_term(dlp_native_package *, size_t index, dlp_package_term_view *out);
int dlp_native_package_predicate(dlp_native_package *, size_t index, dlp_package_term_view *out);
int dlp_native_package_symbol(dlp_native_package *, size_t index, uint64_t *id, const char **name,
                              size_t *size);
#ifdef __cplusplus
}
#endif
#endif
