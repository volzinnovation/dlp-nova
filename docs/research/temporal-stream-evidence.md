# Temporal data and live stream reasoning: evidence and design boundaries

Research date: **10 September 2026**. This note supports design work beyond the thesis DLP fragment; it does not describe features already implemented. Static historical data and live event streams have equal priority. An infrequently changing ontology can still describe a high-volume event stream.

The recommended first implementation is a **typed temporal builtin layer plus an explicit, bounded event/window controller feeding the existing incremental reasoner**. A full temporal rule language should be a separately specified extension. Date arithmetic, validity intervals, stream windows, and recursive metric temporal logic solve different problems and need different correctness contracts.

## Evidence register

Entries distinguish standards, published research, and implementation documentation. Publication dates below come from the linked publisher or author records; a page's crawl date and copyright footer are not publication dates. Mutable documentation was checked on the research date. The engineering recommendations later in this note are our synthesis, not features attributed to every cited system.

### T01 — Time Ontology in OWL

**Status/date:** W3C Recommendation, 19 October 2017; the latest published revision currently identifies itself as a **Candidate Recommendation Draft, 15 November 2022**. Editors: Simon Cox and Chris Little. Sources: [2017 Recommendation](https://www.w3.org/TR/2017/REC-owl-time-20171019/), [2022 Candidate Recommendation Draft](https://www.w3.org/TR/2022/CRD-owl-time-20221115/), [publication history](https://www.w3.org/standards/history/owl-time).

OWL-Time supplies vocabulary for instants, intervals, temporal positions, durations, reference systems, and Allen-style interval relations. `time:ProperInterval` has distinct beginning and end and is disjoint with `time:Instant`. `time:intervalOverlaps` is a particular ordering of four endpoints, not a synonym for any nonempty intersection. The specification provides an interoperability model; adopting its vocabulary alone does not implement numerical endpoint comparisons, window evaluation, watermarks, or lateness handling. Use the dated Recommendation when claiming Recommendation status.

### T02 — W3C XML Schema Definition Language (XSD) 1.1 Part 2: Datatypes

**Status/date:** W3C Recommendation, 5 April 2012. Editors: David Peterson, Sandy Gao, Ashok Malhotra, C. M. Sperberg-McQueen, Henry S. Thompson. Source: [normative datatype specification](https://www.w3.org/TR/xmlschema11-2/), especially §§3.3.6–3.3.7 and 3.4.26–3.4.28.

`xsd:dateTime` permits an absent timezone, which introduces incomparable values when mixed with offset-bearing values. `xsd:dateTimeStamp` requires an explicit offset and has a totally ordered value space. General `xsd:duration` has only a partial order; calendar months cannot be converted universally into a fixed number of days. `yearMonthDuration` and `dayTimeDuration` separate those dimensions. Lexical identity, value equality, and ordering are distinct operations.

### T03 — XPath and XQuery Functions and Operators 3.1

**Status/date:** W3C Recommendation, 21 March 2017. Source: [Functions and Operators 3.1](https://www.w3.org/TR/xpath-functions-31/), especially §9 and §15.3.

The standard defines date/time comparison, timezone adjustment, subtraction, and separate calendar-month versus fixed-duration arithmetic, with specified dynamic errors. Some comparisons use the evaluation context's implicit timezone for values without an offset. `current-dateTime()` is stable within an evaluation context. This is a useful reference for builtin contracts, but copying function names without their context and error semantics would be misleading. A deterministic reasoner should receive an explicit evaluation instant and timezone policy rather than consult the machine clock separately for each rule firing.

### T04 — Temporal Features in SQL:2011

**Status/date:** Published industry-perspectives article, ACM SIGMOD Record 41(3), September 2012, pp. 34–43; publisher posting 30 September 2012. Krishna Kulkarni and Jan-Eike Michels. Sources: [publisher record](https://sigmodrecord.org/2012/09/30/temporal-features-in-sql2011/), [article PDF](https://sigmodrecord.org/publications/sigmodRecord/1209/pdfs/07.industry.kulkarni.pdf). This is an explanation by SQL specialists, not the ISO standard text itself.

The article distinguishes application/valid time from system/transaction time and explains tables combining both. A retrospective correction changes what is currently recorded about an earlier valid period while preserving earlier recorded versions. SQL:2011 periods use a closed-open model, with end strictly after start. Its worked updates illustrate interval splitting. This distinction matters equally for historical zoning data, contracts, and corrected observations; an event timestamp alone cannot answer what the system believed at an earlier record time.

### T05 — The Dataflow Model: A Practical Approach to Balancing Correctness, Latency, and Cost in Massive-Scale, Unbounded, Out-of-Order Data Processing

**Status/date:** Published research paper, Proceedings of the VLDB Endowment 8, 2015, pp. 1792–1803. Tyler Akidau and colleagues. Sources: [authors' Google Research record](https://research.google/pubs/the-dataflow-model-a-practical-approach-to-balancing-correctness-latency-and-cost-in-massive-scale-unbounded-out-of-order-data-processing/), [publisher PDF](https://www.vldb.org/pvldb/vol8/p1792-Akidau.pdf).

The paper treats unbounded, out-of-order inputs, event-time windows, and revisions as fundamental concerns. Its model makes the tradeoff between completeness, emission latency, and cost explicit rather than treating all data as an eventually complete batch. For this project, the transferable principle is to specify when an answer is provisional, corrected, or final under a declared input policy. Its distributed-system performance does not establish any throughput expectation for this reasoner.

### T06 — Apache Beam Programming Guide

**Status/date:** Current Apache project documentation, checked 10 September 2026; continuously maintained, not a standards Recommendation. Source: [programming guide](https://beam.apache.org/documentation/programming-guide/), §§8–9 and 11.

Beam separates event timestamps, processing time, windows, triggers, and allowed lateness. Its watermark represents an estimate of input completeness. Triggers control early and late result emission; accumulation mode determines whether successive panes contain accumulated or newly collected values. Stateful operators and timers provide explicit lifecycle control. Configuring a watermark does not by itself promise that late data will be retained: the guide explains the default zero allowed lateness. Integration must define how panes become the application's additions, replacements, or retractions; successive panes cannot simply be appended as independent logical truths.

### T07 — Apache Flink: Generating Watermarks; Windows

**Status/date:** Apache implementation documentation, stable selector identifying **2.3** when checked 10 September 2026. Sources: [watermarks, version 2.3](https://nightlies.apache.org/flink/flink-docs-release-2.3/docs/dev/datastream/event-time/generating_watermarks/), [windows, version 2.3](https://nightlies.apache.org/flink/flink-docs-release-2.3/docs/dev/datastream/operators/windows/). The corresponding stable pages were checked directly; development/master documentation was not treated as released behavior.

The watermark guide explains why an idle input can hold back the minimum watermark and why faster inputs can create excessive buffered state; idleness and watermark alignment address different conditions. The window guide ties time-window cleanup to the end plus allowed lateness and describes late firings as updated results. Session windows can merge after a late event bridges them. Therefore, window expiry, result correction, and operator-state cleanup are separate transitions. Begin with fixed/sliding windows before adopting sessions and their merge/retraction behavior.

### T08 — RSP-QL Semantics: A Unifying Query Model to Explain Heterogeneity of RDF Stream Processing Systems

**Status/date:** Published journal article, International Journal on Semantic Web and Information Systems 10(4), 2014, pp. 17–44. Daniele Dell'Aglio, Emanuele Della Valle, Jean-Paul Calbimonte, Oscar Corcho. Sources: [author's publication record, December 2014](https://www.dellaglio.org/publications/), [author-hosted full text](https://jeanpi.org/wp/media/rspql_ijswis_dellaglio_2015.pdf), [DOI](https://doi.org/10.4018/ijswis.2014100102). The full-text filename contains 2015; it should not override the author's bibliographic year. The DOI landing page could not be fetched during this review.

RSP-QL formalizes distinctions hidden behind similar continuous-query syntaxes: window contents, evaluation instants, and reporting behavior can produce different answers for the same inputs. It builds on stream-to-relation, relation-to-relation, and relation-to-stream operators and uses an oracle to check implementations. It is a research model, not a W3C Recommendation. Adopt an explicit observable semantics and a replay oracle before comparing implementations' speed.

### T09 — C-SPARQL: A Continuous Query Language for RDF Data Streams

**Status/date:** Published journal article, International Journal of Semantic Computing 4(1), 2010, pp. 3–25. Davide Francesco Barbieri, Daniele Braga, Stefano Ceri, Emanuele Della Valle, Michael Grossniklaus. Sources: [publisher article and DOI](https://doi.org/10.1142/S1793351X10000936), [author-deposited full text](https://d-nb.info/1112944567/34).

C-SPARQL extends SPARQL with registered continuous queries over windows of RDF streams and aggregation, with syntax, semantics, and urban-computing examples. It demonstrates that static RDF and recent observations can be queried together. It does not make every SPARQL extension a temporal entailment rule, nor establish modern event-time lateness guarantees merely through use of a `RANGE` clause. Treat it as a foundational query-language design, not evidence of current maintenance or a drop-in dependency.

### T10 — A Native and Adaptive Approach for Unified Processing of Linked Streams and Linked Data

**Status/date:** Published peer-reviewed ISWC 2011 conference paper, pp. 370–388. Danh Le-Phuoc, Minh Dao-Tran, Josiane Xavier Parreira, Manfred Hauswirth. Sources: [author institution record](https://repositum.tuwien.at/handle/20.500.12708/53799), [publisher DOI](https://doi.org/10.1007/978-3-642-25073-6_24).

CQELS combines streaming observations and stored linked data using native operators, adaptive operator ordering, encoding, indexes, and cached intermediate results. The relevant architectural lesson is to avoid reparsing/retransferring a large static knowledge graph for every observation and to expose selectivity to the execution planner. The paper's historical speed comparisons are specific to its systems and workloads; they do not justify choosing a language or predict performance here. Current operational suitability would require a separate release and integration review.

### T11 — LARS: A Logic-based Framework for Analytic Reasoning over Streams

**Status/date:** Published journal article, Artificial Intelligence 261, August 2018, pp. 16–70. Harald Beck, Minh Dao-Tran, Thomas Eiter. Sources: [publisher DOI](https://doi.org/10.1016/j.artint.2018.04.003), [author institution publication record](https://repositum.tuwien.at/handle/20.500.12708/145916), [preceding author technical report, October 2017](https://www.kr.tuwien.ac.at/tr-reports/files/rr1703.pdf).

LARS supplies generic window operators and temporal controls; its rule programs extend answer-set programming. It makes time-based, tuple-based, and partition-based views explicit and relates stream-query languages through formal semantics. Tuple-count windows need a tie rule when several atoms share a timestamp. Useful design ideas are named windows and explicit time references; adopting full LARS also imports nonmonotonic semantics, a materially larger project than positive DLP. The journal and technical-report versions are identified separately here.

### T12 — DatalogMTL: Computational Complexity and Expressive Power

**Status/date:** Published IJCAI 2019 conference paper, pp. 1886–1892. Przemysław A. Wałęga, Bernardo Cuenca Grau, Mark Kaminski, Egor V. Kostylev. Source: [publisher paper and DOI](https://www.ijcai.org/Proceedings/2019/261).

Metric temporal operators substantially increase expressive power. The paper establishes tight PSPACE data-complexity bounds and analyzes the forward-propagating fragment. These are reasoning-complexity results, not a statement that every useful temporal query is expensive. They establish why adding operators such as “always during the preceding interval” is a language/algorithm decision, beyond calling a date-comparison function in a finite join.

### T13 — Reasoning over Streaming Data in Metric Temporal Datalog

**Status/date:** Published AAAI 2019 paper, 33(1), pp. 3092–3099; publisher date 17 July 2019. Przemysław Andrzej Wałęga, Mark Kaminski, Bernardo Cuenca Grau. Source: [publisher paper and DOI](https://ojs.aaai.org/index.php/AAAI/article/view/4168).

The authors give a sound and complete streaming algorithm for a forward-propagating DatalogMTL fragment, where inference does not propagate to past time points. Its memory depends on rule properties and spacing of input timestamps. A second algorithm removes dependence on those timestamp distances by disallowing punctual intervals in rules. This shows that a finite temporal horizon alone is not a general memory bound and that punctuality and time-domain choices affect implementability. These algorithms' formal stream assumptions must be reconciled separately with out-of-order ingestion and corrections.

### T14 — Practical Reasoning in DatalogMTL

**Status/date:** Published journal article; online 28 October 2024, Theory and Practice of Logic Programming 25(2), March 2025, pp. 225–255. Dingmin Wang, Bernardo Cuenca Grau, Przemysław A. Wałęga, Pan Hu. Source: [publisher full text and DOI](https://www.cambridge.org/core/journals/theory-and-practice-of-logic-programming/article/practical-reasoning-in-datalogmtl/3B76C4CD911796E9673A1D0DA6F44313). Earlier system paper: [MeTeoR, AAAI 2022](https://ojs.aaai.org/index.php/AAAI/article/view/20535).

MeTeoR combines optimized, seminaïve materialization with an automata component to ensure terminating, sound, complete reasoning for the paper's full DatalogMTL language over rational time. Materialization alone can continue indefinitely. This is a reference implementation/algorithm family for an advanced temporal subsystem. Its guarantee is not equivalent to finite ordinary-fact materialization or bounded latency for each incoming event. Its description of an earlier Temporal Vadalog version should not override the later 2025 Vadalog paper.

### T15 — The Temporal Vadalog System: Temporal Datalog-Based Reasoning

**Status/date:** Published journal article; online 7 April 2025, Theory and Practice of Logic Programming 25(2), March 2025 issue, pp. 168–196. Luigi Bellomarini, Livia Blasi, Markus Nissl, Emanuel Sallinger. Sources: [publisher full text and DOI](https://www.cambridge.org/core/journals/theory-and-practice-of-logic-programming/article/temporal-vadalog-system-temporal-datalogbased-reasoning/2AF9E4F68FF09B5970EBB4C0790AB624), [current implementation handbook](https://vadalog.org/vadalog-handbook/latest/temporal-reasoning.html).

The system integrates temporal operators, interval merging, temporal joins, and time-series operations into a reasoning pipeline. Section 3.5 describes fragment-aware termination strategies for forward/backward-propagating cases using finite, constant, or periodic representations. “No termination support” is therefore an outdated blanket characterization. Conversely, these particular strategies should not be generalized to every combination of extensions. The handbook also exposes implementation restrictions, such as flattening nested temporal operators. A streaming execution pipeline is not by itself a complete watermark/lateness contract for external event streams.

### T16 — Goal-Driven Reasoning in DatalogMTL with Magic Sets

**Status/date:** Published AAAI 2025 paper, 39(14), pp. 15203–15211; publisher date 11 April 2025. Shaoyu Wang, Kaiyue Zhao, Dongliang Wei, Przemysław A. Wałęga, Dingmin Wang, Hongming Cai, Pan Hu. Source: [publisher paper and DOI](https://ojs.aaai.org/index.php/AAAI/article/view/33668).

The paper adapts magic-set rewriting to focus temporal bottom-up reasoning on a query. It is relevant when repeated queries select a small part of a large temporal dataset. It motivates separately caching compiled query plans and considering goal-directed evaluation; it does not make a cached answer valid after the source timeline or evaluation context changes. Published benchmark advantages are evidence for testing the technique, not a transferable speedup estimate.

### T17 — Incremental Maintenance of DatalogMTL Materialisations

**Status/date:** Published AAAI 2026 paper, 40(23), pp. 19467–19476; publisher date **14 March 2026**. Kaiyue Zhao, Dingqi Chen, Shaoyu Wang, Pan Hu. Sources: [publisher paper and DOI](https://ojs.aaai.org/index.php/AAAI/article/view/39025), [full text](https://ojs.aaai.org/index.php/AAAI/article/view/39025/42987).

DRedMTL maintains temporal materializations represented by finite facts and periodic regions. Its formal scope is **bounded programs and bounded datasets**, including bounded insertion/deletion datasets; bounded operator intervals do not imply that the derived temporal model is finite. Theorem 2 states maintenance correctness for this setting. Specialized periodic-representation operators are essential. This is strong current evidence that incremental temporal reasoning is achievable, but ordinary DRed over the engine's finite atom set does not implement DRedMTL automatically. The paper studies data updates under a program; it does not establish arbitrary ontology-change maintenance for our system.

### T18 — Temporal Datalog with Existential Quantification

**Status/date:** Published IJCAI 2023 conference paper, pp. 3277–3285. Matthias Lanzinger, Markus Nissl, Emanuel Sallinger, Przemysław A. Wałęga. Source: [publisher paper and DOI](https://www.ijcai.org/proceedings/2023/365).

Ordinary DatalogMTL extended with existential rules is undecidable even for guarded or weakly acyclic programs. The authors' uniform semantics restores decidability for weakly acyclic programs, with a 2-EXPSPACE-complete bound, while guarded programs remain undecidable. Therefore, existing finite-chase safeguards or L3 witnesses cannot simply be combined with recursive temporal value invention and assumed to retain their guarantees. An advanced extension needs an explicit witness semantics and a proven admissible fragment.

## Semantic contract for the proposed first version

The following is a proposed design, not a claim of standards conformance or an existing repository API.

### Four clocks with distinct meanings

| Field/context | Meaning | Example |
| --- | --- | --- |
| Event time | Timestamp of the observation or occurrence | GPS observation taken at 10:00:02 |
| Processing time | When a runtime stage handles a record | Worker processes that observation at 10:00:09 |
| Valid time | When an assertion is said to hold in the modeled world | Road closed from 09:00 to 12:00 |
| Record/system time | When a version becomes part of the accepted record | Closure correction recorded the following day |

The last two support historical snapshots; the first two govern ingestion and live evaluation. They can coincide in a dataset but should not be collapsed by the API. A query asking “what held at 10:00, according to records available yesterday?” must carry both parameters. The distinction follows the temporal-table and streaming models in [T04](https://sigmodrecord.org/publications/sigmodRecord/1209/pdfs/07.industry.kulkarni.pdf) and [T06](https://beam.apache.org/documentation/programming-guide/).

Require offset-bearing instants at stream ingestion, preferably `xsd:dateTimeStamp`. Preserve original literals for interchange, while comparing normalized exact values. Start with a documented precision/range; reject overflow or excess precision instead of rounding silently. Do not assign UTC to unknown timezones. Calendar-month arithmetic is an explicit operation separate from elapsed seconds; a future civil-time scheduling feature should carry a named-zone policy and its version. These proposed restrictions simplify the more general datatype space described in [T02](https://www.w3.org/TR/xmlschema11-2/) and the operation contracts in [T03](https://www.w3.org/TR/xpath-functions-31/).

Use proper intervals `[start,end)` with `start < end` initially; represent instantaneous observations separately. This yields useful executable contracts:

| Operation on proper intervals A=[a,b), B=[c,d) | Proposed condition |
| --- | --- |
| Contains instant t | `a <= t < b` |
| Any intersection | `max(a,c) < min(b,d)` |
| Before | `b < c` |
| Meets | `b == c` |
| Allen overlaps | `a < c < b < d` |
| During | `c < a` and `b < d` |
| Equals | `a == c` and `b == d` |

Distinguish the convenient any-intersection operation from `time:intervalOverlaps`; implement remaining Allen relations by endpoint tests and inverses when required. Unknown or incomparable endpoints need a typed error/unknown result, not a successful proof of falsity. The OWL-Time vocabulary supplies the relation meanings; this table proposes the engine's concrete endpoint evaluation policy. [T01](https://www.w3.org/TR/2017/REC-owl-time-20171019/)

### A record ledger before a logical fact set

Maintain an accepted-record ledger containing at least source ID, event/assertion ID, version or source sequence, payload, event time where applicable, valid interval where applicable, and record revision. It can be backed by an existing durable store; this note does not select a database. Static facts enter through the same assertion interface, with their own validity and provenance.

The ledger and the reasoner's atom set have different identities. Two different observations can support the same logical atom. An event retry with the same ID is a duplicate delivery; another event with a different ID is another support. Expiring one observation must retain the atom while another observation or a static assertion still supports it. Keep source-support counts or identities before converting to set-valued `Engine.update` deltas. Preserve the ledger when coalescing adjacent validity intervals; otherwise deletion of one source assertion cannot reliably split the normalized interval back into supported pieces.

A basic projection for a query context is:

```text
accepted versions at record cutoff
    -> static assertions valid at the requested instant
    + events selected by the named event-time window
    -> source-support accounting
    -> atom additions/removals
    -> completed DLP materialization
    -> answer additions/removals with context and provenance
```

This is a finite-snapshot semantics. It intentionally answers over selected active records; it does not claim to compute all consequences of an unbounded DatalogMTL history. For interval-valued historical joins, intersect the supporting validity intervals and keep provenance. Do not materialize every timestamp in a continuous interval.

### Window state and explicit correction rules

Each named window needs a specified time axis, size, slide/evaluation schedule, endpoint convention, grouping key, and permitted lateness. For example, an evaluation at event-time endpoint `E` can select `E-W <= event_time < E`; records stamped exactly `E` enter a later window. Ingestion can emit a provisional result before finality, but the result must carry the window identity and revision.

Treat these as explicit input/control transitions:

1. Accept an event, retry, corrected version, or source retraction.
2. Advance a source watermark or evaluation clock, even when no new facts arrive.
3. Expire memberships in current windows and publish resulting fact retractions.
4. Revise an already emitted window when allowed late data changes it.
5. Finalize under the declared lateness policy, then reclaim live window state.

Too-late records should be reported/quarantined or trigger an explicit historical replay policy. Silent dropping is unsuitable as an undocumented default. An event removed from the current sliding view need not be deleted from the historical ledger. A finalized historical result should not be retracted merely because its computation state is garbage-collected. Beam/Flink distinguish reporting, late corrections, and lifecycle management; that separation should be visible in the adapter contract. [T06](https://beam.apache.org/documentation/programming-guide/), [T07](https://nightlies.apache.org/flink/flink-docs-release-2.3/docs/dev/datastream/operators/windows/)

Maintain per-source progress and specify what idleness means. Do not replace a stalled event-time watermark with wall-clock progress without a declared policy. A memory budget must account for event rate, key cardinality, allowed lateness, source skew, rule support state, and output fan-out. For overload, choose backpressure, spill, or a reported incomplete/rejected update; never silently label a truncated materialization complete. Source alignment and the timestamp-density results show why window width alone is insufficient. [T07](https://nightlies.apache.org/flink/flink-docs-release-2.3/docs/dev/datastream/event-time/generating_watermarks/), [T13](https://ojs.aaai.org/index.php/AAAI/article/view/4168)

Absence needs a separate contract. Under the existing open-world DLP semantics, failure to derive a sensor observation does not prove that no event occurred. “No heartbeat for five minutes” requires a closed, declared event source/window and a finality/completeness policy; it must not be encoded by negating an ordinary ontology query. An outage can otherwise be confused with delayed ingestion.

## Fit with the existing implementation

Repository inspection found `Reasoner._query_cache_token` in `src/dlp_reasoner/reasoner.py` tracking graph identity/revision, engine identity/revision, completeness, profile, and options. `Engine.update` in `src/dlp_reasoner/engine.py` already maintains finite fact updates. These provide useful foundations, but neither token currently expresses a temporal query context or a source-support ledger.

Proposed integration boundaries:

| Component | Responsibility | Safe cache/index scope |
| --- | --- | --- |
| Datatype/builtin registry | Pure validation, conversion, comparison and bounded arithmetic | Normalized input values plus builtin semantics/version and explicit context |
| Static schema compiler | Compile ontology rules and reusable plans | Ontology/rule fingerprint, profile, builtin signature/version |
| Static assertion store | Immutable/versioned data, temporal and spatial indexes | Data snapshot/validity revision; reuse while events arrive |
| Event/window controller | IDs, late data, progress, membership and expiry | Source revisions, window definition, evaluation endpoint, lateness/finality policy |
| DLP engine | Join active facts, derive consequences, maintain deletions | Active snapshot revision, complete/consistent status |
| Query/result layer | Answers and corrections for a declared context | Above revisions plus query arguments and temporal context |

Do not cache a zero-argument wall-clock `now()` result globally. Inject one clock value for a reasoning transaction, and either include it in dependent keys or mark the operation context-dependent. Window ticks can change answers with unchanged source graphs. Conversely, cached parsing of immutable timestamps and unchanged schema plans can survive many event updates. A cached historical geometry or validity lookup must select the version effective at the event's time, not whichever version happens to be latest when the event is processed.

The existing whole-answer cache is likely to churn during a busy stream. Prioritize reusable compiled plans, static-side indexes, bounded builtin-value caches, and maintained per-query state. Use the current cache for repeated reads of the same published snapshot. Keep correctness-first coarse invalidation initially; introduce dependency-specific invalidation only after profiling shows it worthwhile. Goal-directed temporal evaluation is an advanced optimization lead from [T16](https://ojs.aaai.org/index.php/AAAI/article/view/33668), rather than a substitute for revision keys.

Apply event-derived additions and removals atomically. A rejected transaction must not advance the published watermark/window result revision. Durable progress, accepted ledger offsets, fact updates, and output revision IDs need a recoverable commit protocol or replay boundary. Notifications should be idempotent by result key/revision; exactly-once logical output cannot be inferred merely from a broker's delivery setting.

## Bounded first release and advanced language

### First release with equal static and live coverage

Provide typed instant comparisons, elapsed durations, explicit calendar arithmetic where fully specified, proper-interval relations, validity-at-time lookup, and a deterministic `as_of` context. Add fixed and sliding event-time windows with explicit ticks/watermarks, lateness, corrections, support-aware expiry, replay, and resource limits. Keep static schema and data indexes resident while applying bounded event batches to the existing reasoner.

Permit ordinary positive finite DLP over the projected snapshot and builtin arguments bound by positive atoms. Restrict value-producing recursion: a rule that repeatedly adds one second can create endlessly many terms even when each arithmetic call is individually cheap. Preserve current L3 safeguards for ordinary snapshot reasoning, but do not add temporal witness creation or recursive temporal-head shifting in this release. Reject unsupported constructs explicitly.

Expose historical static queries and live subscriptions through distinct context choices over the same typed records. Historical queries need no artificial streaming clock. Live subscriptions need no full recompile of the ontology per event. Both must agree when replay is run over the same accepted records and context.

### Advanced temporal rule language

A later profile could introduce metric past/future operators, interval-valued conclusions, or sustained-condition rules. It needs a written timeline choice (discrete ticks versus rational time), operator endpoint/punctuality semantics, rule-fragment validation, interval normalization, temporal joins, and a termination/completeness strategy. Assess MeTeoR and Temporal Vadalog against those exact requirements; their guarantees and supported fragments differ. Do not reduce continuous “always during the preceding ten minutes” to checking that every *observed* sample was high: coverage of the entire interval is an additional premise. [T12](https://www.ijcai.org/Proceedings/2019/261), [T14](https://www.cambridge.org/core/journals/theory-and-practice-of-logic-programming/article/practical-reasoning-in-datalogmtl/3B76C4CD911796E9673A1D0DA6F44313), [T15](https://www.cambridge.org/core/journals/theory-and-practice-of-logic-programming/article/temporal-vadalog-system-temporal-datalogbased-reasoning/2AF9E4F68FF09B5970EBB4C0790AB624)

For recursive interval maintenance, study DRedMTL's bounded-input periodic representation instead of extending ordinary fact deletion heuristically. For existential temporal rules, require a deliberately selected semantics and admissibility proof; existing weak acyclicity alone is insufficient. Keep full LARS/answer-set negation and unrestricted aggregates out of an otherwise positive DLP profile. [T17](https://ojs.aaai.org/index.php/AAAI/article/view/39025), [T18](https://www.ijcai.org/proceedings/2023/365), [T11](https://doi.org/10.1016/j.artint.2018.04.003)

## Example workloads and acceptance tests

These are proposed application examples, not additional thesis examples or claims that the current syntax supports temporal clauses.

| Workload | Static contribution | Temporal/stream contribution | Main correctness case |
| --- | --- | --- | --- |
| Historical land-use or flood-zone analysis | Parcels, zones, classification hierarchy | Validity intervals and recorded corrections | Query old geometry/classification versions at the requested valid and record times |
| Fleet entering a restricted area | Geofences and vehicle permissions | Recent GPS events and closure intervals | Late GPS joins the restriction valid when observed; expiry retracts the live alert |
| Equipment monitoring | Equipment types, limits, maintenance relationships | Temperature/heartbeat windows | Missing samples do not establish a continuously true condition; threshold units must match |
| Service/contract eligibility | Contract and customer classification | Effective dates and delayed service events | Month arithmetic and retroactive corrections use declared semantics |
| Transport connections | Routes and expected travel durations | Vehicle arrival observations | Dense duplicate timestamps and out-of-order events produce deterministic windows |

The first acceptance suite should compare every published result revision with an independent finite replay oracle. Cover offset-equivalent timestamps, absent offsets, month ends, fractional precision, invalid literals, touching/empty intervals, and instant-versus-interval cases. Cover event retries versus distinct supports, static plus stream support, corrections, retractions, idle sources, ticks with no events, late data at exact cutoffs, rejected batches, restart/replay, and cache hits after context changes. Test both Python and native backends against identical completed snapshot answers.

Benchmark two equally weighted workload families: large static temporal/geographic snapshots with selective historical queries, and high-rate event streams joined to static data. Vary event rate, window width, lateness, key skew, rule depth and output fan-out independently. Report ingestion-to-answer latency, watermark lag, correction latency, peak retained state, and full-answer agreement; warm builtin or static-index timings alone do not establish whole-system throughput. Foundational RSP work specifically motivates checking semantic equivalence before comparing timing. [T08](https://jeanpi.org/wp/media/rspql_ijswis_dellaglio_2015.pdf)
