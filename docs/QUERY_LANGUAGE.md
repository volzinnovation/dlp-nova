# Version 1 query rules

The extension has a separate parser and intermediate representation. It does not
change Appendix A ontology syntax or the L0–L3 compiler. `parse_query_program`
parses text; `plan(program, registry)` checks bindings, operation signatures and
dependency strata without executing a domain function or contacting a provider.
The query runtime evaluates the resulting plan against a completed ontology and
explicit finite input relations.

```text
version 1
prefix ex: <https://example.org/>
prefix num: <urn:dlp:numeric:>

query incremented(?person, ?next) given (?minimum) :-
    ex:age(?person, ?age),
    bind num:add(?age, 1) as ?next,
    filter num:greaterThanOrEqual(?next, ?minimum).
```

Every program starts with `version 1` (an optional period may follow). Prefixes
precede rules. `rdf`, `rdfs`, `owl` and `xsd` are predefined and cannot be
rebound. Prefix declarations may end in a period. Rules require a final period
and a nonempty comma-separated body. `query` before a head is optional.
Unqualified relation names expand to `urn:dlp:query:`; operation names and IRI
constants require a declared prefix or an absolute `<IRI>`.

Variables start with `?`, followed by an ASCII letter or underscore and then
letters, digits or underscores. Prefixed local names allow letters, digits,
underscore, hyphen, period and colon, beginning with a letter or underscore.
Use `<IRI>` for other names. Keywords are case-sensitive: `filter`, `bind`,
`scan`, `given`, and `MIN`, `GROUP_BY`, `FROM`, `AS` as shown below.

Constants include IRIs, JSON-escaped strings, language-tagged strings, explicitly
typed RDF literals, integers, decimals, exponent-form doubles and `true`/`false`.
For example, `"001"^^xsd:integer` retains its lexical form in the IR, and
`"2026-09-10"^^xsd:date` supplies a typed date. Bare `1`, `1.0`, `.5` and `1e0`
have integer, decimal, decimal and double datatypes respectively; use `1.0`
instead of `1.` for a decimal. Runtime domain validation checks lexical forms
and value ranges. Comments use `#`, `//` or `/* ... */` outside strings/IRIs.

## Body forms and bindings

| Form | Meaning and exported variables |
| --- | --- |
| `ex:relation(?a, ?b)` | Positive stored/derived relation; binds its variables. Zero and higher arities are allowed. |
| `filter num:lessThan(?a, ?b)` | Boolean test with all arguments already bound. |
| `bind num:add(?a, 1) as ?b` | Scalar result; binds `?b`, or checks agreement when the output is already bound/a constant. |
| `scan ex:candidates(?point, ?snapshot) as ?id` | Finite provider enumeration; all input arguments bound. |
| `scan ex:pairs(?snapshot) as (?a, ?b)` | Provider enumeration with an explicitly declared output arity. |
| `MIN ?v GROUP_BY ?g FROM ex:values(?g, ?v) AS ?m` | Minimum over each group of the complete source relation; exports `?g` and `?m`. |

`given (?scope, ?revision)` declares input parameters seeded by the runtime,
including when the parameter does not occur in the head. Every definition of
the same predicate must declare the identical parameter list. A caller of that
predicate must itself declare those parameter names, preventing an implicit
change of query scope. The runtime requires the actual values.

The planner reorders body nodes until their inputs are bound, preferring a ready
filter over unrelated joins. All scalar and scan input positions must be bound
in version 1; descriptor binding metadata is validated but does not make an
unbound input an implicit output. Each head variable must be bound by a body
node or `given`. Unknown operations, conflicting relation arities, unsafe
variables, non-Boolean filters and scalar/scan cardinality mismatches fail during
planning. Known disjoint constant/result types fail early; unknown relation
types and broad domain types receive their remaining checks during execution.
In particular, exact integer/decimal arithmetic is separate from explicit
binary64 conversion and comparison operations.

## Aggregates and recursion

```text
version 1
prefix ex: <https://example.org/>

query earliest(?parent, ?first) given (?snapshot) :-
    MIN ?date GROUP_BY ?parent
    FROM ex:acceptedBirth(?parent, ?child, ?date, ?snapshot) AS ?first.

query tiedChildren(?parent, ?child, ?first) given (?snapshot) :-
    earliest(?parent, ?first),
    ex:acceptedBirth(?parent, ?child, ?first, ?snapshot).
```

`GROUP_BY (?a, ?b)` and `GROUP_BY ?a, ?b` are equivalent. `GROUP_BY ()`
computes a global minimum. Group and value variables must occur in the source;
the output must be a different variable. Source-only variables such as `?child`
are local to the aggregate and do not become head bindings. Fixed `given`
parameters can restrict a source; other already-bound nongroup source variables
are rejected to avoid an accidental correlated minimum. Empty groups produce
no row. Joining the selected minimum back to its source preserves all tied
children; selecting one arbitrary tied child is not an aggregate policy.

Positive recursive relations and pure Boolean filters are allowed. A cycle
crossing an aggregate, `Bind`, scan or non-pure filter is rejected. Aggregate
sources are completed in an earlier stratum. Rules using value-generating or
snapshot-dependent operators conservatively run above their relation inputs;
this finite, stratified subset excludes arithmetic term generation in recursion.
It does not introduce negation, temporal windows, watermarks or arbitrary
temporal rule operators.

## API and diagnostics

```python
from dlp_reasoner.domains import DomainRegistry
from dlp_reasoner.query_ir import plan
from dlp_reasoner.query_parser import parse_query_program

program = parse_query_program(text, source="queries.rules")
prepared = plan(program, DomainRegistry())
explanation = prepared.explain()  # JSON-serializable planned body order/strata
```

The IR uses frozen `RelationAtom`, `Filter`, `Bind`, `Aggregate`, `ProviderScan`,
`QueryRule` and `QueryProgram` dataclasses. Terms are the existing `model.Var`,
RDFLib `URIRef` and `Literal`. Program namespaces and planned predicate levels
are read-only mappings. `QueryPlan.rules` contains planned rules in stratum
order; `QueryPlan.strata` groups them and `recursive_predicates` records positive
recursion. Optional `relation_arities` supplies known input relation arities.
`QueryParseError` and `QueryValidationError` include source/line/column whenever
the offending node came from text.

Historical `*.rules.proposed` files remain design evidence, without the required
version header. Parsing one after explicitly adding a header does not imply
that every proposed provider exists or that its old operation types are valid.
Use the executable examples and registered capabilities for runtime support.
