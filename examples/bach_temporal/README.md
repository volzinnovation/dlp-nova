# Bach: age at the earliest known child's birth

This worked extension keeps the thesis's historical example files unchanged.
It separates **executable current DLP facts/classification** from **proposed
date functions and aggregates**. It is a selected dataset for explaining engine
semantics, not a complete or authoritative Bach genealogy.

Run from the repository root with the existing project environment:

```sh
.venv/bin/python examples/bach_temporal/reference_checks.py --backend both
```

The native check needs the existing optional backend's C++17 compiler. Use
`--backend python` when checking only Python. No new dependencies, network access,
or temporal native libraries are required by the checker.

| File | What executes today |
| --- | --- |
| [bach-temporal.dlp](bach-temporal.dlp) | Current DLP syntax; materializes under L0, with explicit person/child/date records and inferred Father/Mother classes. It can also be merged with `../bach.dlp` under L3. |
| [queries.rules.proposed](queries.rules.proposed) | Design notation only. `MIN`, queries, validation relations and `time:completedYears` are not supported by the current parser or engine. |
| [reference_checks.py](reference_checks.py) | Runs the real DLP closure and insertion/deletion operations on the chosen backends, then independently computes the proposed finite temporal answers in Python. |
| [expected.json](expected.json) | Reviewable expected answers and earlier-child update results; JSON `null` means no answer, not an RDF literal or a zero age. |

The checker verifies that Python/native base fact closures agree and that the
extension composes with the original L3 example. Computed temporal ages are
**not** inserted into that closure. A passing check validates these fixtures;
it does not establish implementation of aggregates, native date functions or
incremental aggregate maintenance.

The ontology declares `bt:fatherAtAgeKnown`, `bt:motherAtAgeKnown`,
`bt:fatherAtAge` and `bt:motherAtAge` as datatype properties. A future derived RDF
view would export the known-age results as the following triples; these are
expected output, not input assertions or output produced by today's engine:

```turtle
@prefix bach: <http://www.jsbach.org/bach#> .
@prefix bt: <https://example.org/bach-temporal#> .
bach:johann-sebastian bt:fatherAtAgeKnown 23 .
bach:maria-barbara bt:motherAtAgeKnown 24 .
```

## What the example answers

Age is **completed Gregorian calendar years**, using the explicit March-1
anniversary policy for February-29 births in common years. It is not elapsed
days divided by 365, and this policy is not a legal age rule.

| Parent | Earliest accepted exact child date in this selected dataset | Proposed known-age answer |
| --- | --- | --- |
| Johann Sebastian | Catharina Dorothea, 1708-12-27 | `fatherAtAgeKnown = 23` |
| Maria Barbara | Catharina Dorothea, 1708-12-27 | `motherAtAgeKnown = 24` |
| Anna Magdalena | None: Christiana Sophia Henrietta has only a spring-1723 description | No exact-date age; missing-date diagnostics |

The original Table 2.5 example names only Wilhelm Friedemann as Johann Sebastian's
child; it does not claim he was the first child. With Wilhelm's selected date,
the known-age answer is 25. Inserting the Catharina Dorothea child edges changes
Johann Sebastian's answer **25 → 23** and Maria Barbara's **26 → 24**. Removing
those edges restores the previous values. These updates alter knowledge, not
the historical dates of birth. The checker performs the actual DLP fact updates
and recomputes the reference answers after each update.

No historically complete-family certificate is asserted. Consequently
`fatherAtAge` and `motherAtAge`, meaning age at the first child in a certified
complete parent-specific family/date scope, have **no answers** here. The known
variants are explicitly partial answers over accepted exact records: missing or
conflicting dates remain visible as diagnostics. A separate invented family in
the checker demonstrates successful certified `fatherAtAge = 20` and
`motherAtAge = 18` results.

## Source claims and calendar normalization

Checked 10 September 2026. Dates below are selected source claims; calendar
normalization is an explicit fixture policy. Source lexical forms are preserved
for the two pre-1700 birth records. They must not be silently loaded as
proleptic-Gregorian `xsd:date` with unchanged month/day fields.

| Person | Selected source record | Accepted Gregorian date / treatment |
| --- | --- | --- |
| Johann Sebastian | 21 March 1685, reported in the C.P.E. Bach edition chronology | Interpret as Julian for this fixture; normalize to **1685-03-31**. |
| Maria Barbara | 20 October 1684, same chronology | Explicit Julian interpretation for this fixture; normalize to **1684-10-30**. |
| Wilhelm Friedemann | 22 November 1710, same chronology | **1710-11-22**, with explicit Gregorian interpretation. |
| Catharina Dorothea | 27 December 1708 in Erich Reimer's scholarly article, p.248 n.5, citing Frickel's genealogy | Select **1708-12-27**, explicitly Gregorian; retain awareness of conflicting published claims. |
| Anna Magdalena | 1701–1760 in the Bach Archive's family classification | Only a year description is accepted here; no exact date is invented. |
| Christiana Sophia Henrietta | March (?) 1723 in the Neue Bachgesellschaft chronology; exact birthdate not recorded according to Bach-Jahrbuch 2024 | Store a spring-1723 description, with **no exact `birthDate`**. |

The [C.P.E. Bach: Complete Works chronology](https://cpebach.org/timeline/chronology)
supports the three selected JS/MB/WF records; the
[Bach Archive chronology](https://www.bach-leipzig.de/de/neutral/johann-sebastian-bach-%E2%80%93-eine-chronologie)
also reports JS's March-21 birth. Calendar interpretation is recorded separately
from those sources' bare dates. The fixture's narrow conversion helper checks
only Julian years 1600–1699, where adding ten days is valid; it rejects unknown
calendars and other Julian ranges. A production implementation needs an actual
calendar conversion library and source/calendar provenance, not a permanent
ten-day offset. The [US Naval Observatory calendar description](https://aa.usno.navy.mil/faq/calendars)
explains the different leap-year rules, including Gregorian 1700 not being leap.

Catharina's selected December-27 claim is documented in
[Reimer, “Friedelena Margaretha Bach,” Die Musikforschung 63 (2010), p.248 n.5](https://mf.journals.qucosa.de/mf/issue/download/247/213).
The [Neue Bachgesellschaft chronology](https://www.neue-bachgesellschaft.de/jsb/biographie/)
instead labels December 29 as her birth and November 24 as Wilhelm's birth.
These inconsistencies are a reason to retain source claims and distinguish birth
from baptism, rather than merge arbitrary dates or take their minimum. Choosing
another December-1708 day does not change either completed-year age here. Bach
Digital could not be retrieved during this check, so its record is not presented
as independently verified evidence.

The family grouping (Catharina/Wilhelm with Maria Barbara, and Christiana Sophia
Henrietta with Anna Magdalena) is listed by the J. S. Bach Foundation's
[Bachipedia family discussion](https://bachipedia.org/werke/bwv-122-das-neugeborne-kindelein/).
Use that source for the grouping, not its apparent Anna-Magdalena birth-year typo;
the [Bach Archive family classification](https://www.bach-leipzig.de/en/bach-archive/classification-system-leipzig-bach-archive)
records 1701–1760. [Bach-Jahrbuch 2024's published preview](https://api.pageplace.de/preview/DT0400.9783374077809_A62609034/preview-9783374077809_A62609034.pdf)
states that Christiana Sophia Henrietta's exact birthdate was not recorded.
The exact-date operator therefore does not manufacture a date or an age for Anna
Magdalena. Interval/uncertain-date reasoning is separate future work.

## Required aggregate and builtin contracts

1. **Validate before aggregation.** `acceptedBirthDate(person,date)` contains one
   validated normalized date value per person. Duplicate claims of that same value
   do not multiply children; different dates are a conflict. Never take the minimum
   of a person's conflicting birthdate assertions. Current DLP treats these literals
   as ordinary terms; the reference checker owns this extra validation.
2. **Compute a grouped minimum after the positive stratum stabilizes.** Group by
   parent within an explicit dataset/scope and revision. Empty input emits no
   minimum. Join the minimum date back to child rows to retain every tied child;
   do not choose an arbitrary twin.
3. **Bind calendar age from two accepted dates.**
   `time:completedYears(parentBirth, childBirth, policy:march1)` returns an integer,
   requires child birth not before parent birth, and returns a typed error for
   invalid dates, unknown calendars/policies or overflow. Date-only values need
   no timezone or conversion to midnight instants.
4. **Keep known and complete-scope predicates separate.**
   `firstKnownChild`, `fatherAtAgeKnown`, `motherAtAgeKnown` describe accepted known
   records and carry diagnostics/completeness metadata. `firstChild`, `fatherAtAge`,
   `motherAtAge` additionally require an explicit trusted certificate of complete
   child/date coverage for that parent and scope/revision. Neither a closed loop
   over observed rows nor complete rule materialization proves family completeness.
5. **Retract aggregate consequences on relevant changes.** New earlier children,
   deleted minimum witnesses, date corrections, identity merges, validation changes
   and certificate changes can alter the answer. Preserve tie multiplicities or
   an ordered per-parent date index; on deleting the last minimum witness, find
   the next minimum. Cache keys and provenance include scope, ontology/equality,
   accepted records and calendar-policy revisions. Positive-only DRed is not by
   itself an implementation of this nonmonotonic aggregate.

The synthetic checks cover twins and removal of one/both minimum witnesses,
empty groups, missing dates, conflicting child dates and their correction,
certificates invalidated by changed evidence, birthdays, February 29, invalid
dates, unknown calendars and a child birth preceding the parent's birth. The
certificate fingerprint in the checker only binds the explicit synthetic
assertion to its finite evidence; it is not a general completeness or provenance
system. No completeness assumption is added to the historical Bach ontology.
