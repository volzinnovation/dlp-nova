# Portable native packages

`.dlpn` packages contain an ahead-of-time compiled Horn ontology, an RDF term
dictionary, semantic profile, provenance and optional local query plans. The
C++ loader executes the Horn closure and prepares local relation, equality,
filter, bind and MIN queries without CPython. Provider transport plans are
rejected when authoring this package profile.

```python
from dlp_reasoner.native_package import dumps_native, loads_native
from dlp_reasoner.packages import CompiledPackage

data = dumps_native(CompiledPackage(program, query_program))
with loads_native(data) as runtime:
    with runtime.prepare_query(
        parameters={"scope": scope_iri, "revision": revision_literal},
        relations=selected_relations,
    ) as query:
        answers = query.run()
        again = query.run()  # Same immutable result; lifetime/control checks run.
```

`answers` maps each query head predicate to a `frozenset` of tuples, including
empty result relations. `runtime.query(...)` combines preparation, execution and
closure of the prepared context. A deadline is an absolute `time.monotonic()`
value. Cancellation accepts a callable or an object exposing `is_set()`.
Native operation failures retain their structured domain error code.

The host explicitly supplies selected birthdate, location, completeness and
window relations. Preparation adds these rows to a copied canonical Horn
snapshot and expands unary ontology classes into `rdf:type` rows. It does not
establish source completeness, select conflicting dates or advance a watermark.
Application scope validation must run before supplying certified rows.

Prepared queries have fixed parameters and inputs. Repeated successful runs
reuse the completed immutable answer after cancellation, deadline and source
lifetime checks. A failed native execution requires a new prepared context.
Changing inputs requires preparation again. Closing or updating the originating
Python runtime invalidates prepared queries; a successful Horn update also
invalidates its packaged query plan because the new dictionary belongs to a new
snapshot. Author and load a fresh package to use a plan with that snapshot.
Failed Horn updates preserve the original package and plan.

The C API is in `src/dlp_reasoner/native_package.h`. `dlp_native_package_load`
owns its completed Horn runtime. `dlp_native_package_prepare_query` copies its
source rows, metadata, explicit named parameters and plan into an independently
owned `dlp_qx_context`. A native host can then add explicit selected rows with
the query C API and execute it. The prepared C context remains valid after the
package is freed; the Python adapter requires the originating runtime to remain
open because it also resolves RDF identities during result export. Inconsistent
Horn snapshots remain inspectable but query preparation rejects them.

## Wire contract

All integers are explicitly little-endian. No host structure layout, pointer,
Python object, pickle or executable code is serialized. The 48-byte header is
the eight-byte magic `DLPNPKG1`, an unsigned 64-bit payload size and the SHA-256
digest of the payload. The digest detects corruption; it does not authenticate
the artifact's author or validate the truth of provenance claims.

The payload begins with version `u32(1)`, semantic profile `dlp-domains-v1`,
Horn profile `L0`–`L3`, opaque provenance/context, then four `u64` identifiers
for EQ, NEQ, TOP and the nonempty-domain seed. Text fields are a `u32` byte
length followed by UTF-8. Provenance authored by Python contains canonical JSON;
the native loader retains bounded opaque bytes without a JSON dependency.

Every subsequent record contains a `u8` opcode, `u64` byte length and its payload.
An empty end record is mandatory. Unknown opcodes, inconsistent lengths,
duplicate identities, invalid references and incompatible profiles are rejected.

| Opcode | Content |
| --- | --- |
| 0 | End; no payload. |
| 1 | Symbol ID, quoted spelling used for canonical order, original symbol. |
| 2 | Scalar term ID, category, literal equivalence group, canonical-order spelling, typed RDF/primitive term. |
| 3 | Ground Skolem ID, symbol ID, arity and child IDs. |
| 4 | Asserted fact: predicate ID, arity and term IDs. |
| 5 | Horn rule: optional head, variable names, label and recursive expression atoms. |
| 6 | Predicate ID and typed string/IRI dictionary value. |
| 10 | Local query rule: stratum, head arguments, named slots/given flags, relation/filter/bind/MIN nodes. |
| 11 | Per-term typed query metadata, deterministic MIN identity keys and argument-role flags. |
| 12 | `rdf:type` predicate ID and mappings from unary class predicates to their identical IRI term IDs. |

Query arguments are signed 32-bit slots plus unsigned 64-bit constant IDs; slot
`-1` denotes a constant. Nodes identify kind, operation opcode or relation,
arguments, output, grouping slots and aggregate value slot. A query package
must provide record 11 for every dictionary term. It contains `u64` identity,
`i32` decode status, `u8` canonical-output flag, `u32` RDF inequality group,
`u64` inequality key, then a typed value only when decode status is zero. The
typed value is `u32 tag, u32 reserved, i64 a, i64 b, i64 c, f64 x, f64 y` with
the meanings in `native_domains.h`. Two length-prefixed UTF-8 MIN identity keys
follow; they may contain NUL separators. The final `u32` contains argument-role
flags defined by `dlp_qx_term_roles`. Invalid generic datatypes can retain a
deferred error while an explicitly declared policy/unit argument role remains
usable; the role does not change that term's RDF identity or general datatype.

The loader validates required query plans without executing them. Validation
covers declared terms, slots, operation arity/capability, binding safety,
aggregate scope, strata and compatibility with Horn predicate arities, including
predicates with no current rows. Compiled RDF value-equivalence metadata remains
trusted compiler output, like the compiled logical rules themselves.

Bounds are explicit: 64 MiB payload, 1 MiB text/context fields, 2,000,000 records,
100,000 Horn or local rules, 32 KiB per MIN identity key, 4,096 query slots/arity,
10,000 query body nodes, 512 Horn body atoms and expression nesting 256. Runtime
fact, term, candidate, match, violation, round and query-work limits are supplied
separately. Capacity exhaustion fails; result export pages never truncate.

The loader and interpreter are exercised by a standalone C++ executable under
AddressSanitizer and UndefinedBehaviorSanitizer in
`tests/test_native_package_queries.py`. This verifies loading an authored
artifact, releasing its package, then executing its independently owned query
context without Python. The mobile aggregate library exports these same C APIs.
