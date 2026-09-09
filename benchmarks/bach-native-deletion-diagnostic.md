# Independent ZodiacEdge Bach deletion check

The [retained diagnostic](bach-native-deletion-diagnostic.json) contains ten
untimed, fresh-process checks with hash seeds 0–9, conducted before the formal
Bach benchmark. It uses the unchanged upstream revision
`e15721161d1055f019c4b8f9ac1bd8648417f154`; the formal protocol records that
source archive and all source-file hashes.

The reproducer `direct_native_deletion_check` in
[bach_zodiac.py](bach_zodiac.py) invokes native `Program`, `DataStore`, rule
parsing, deletion/insertion, and ground querying directly. It does not use the
reconstructed reasoner, ontology compiler, or schema-query probes. It separately
encodes the nine asserted edges and two rules from the original family example.

All ten checks initially find both the ancestor and dynasty relations between
Johannes and Wilhelm Friedemann. After deleting the Sebastian–Wilhelm edge,
checks with seeds 1, 7, and 9 lose both consequences. Inserting the
Sebastian–Johann Christian edge does not restore them in those checks. The
remaining seven checks preserve them. The long path through Heinrich, Johann
Christoph, Johann Michael and Maria Barbara remains asserted throughout.

These observations demonstrate an incorrect deletion outcome in the tested
native implementation, independently of the comparison adapter. They do not
identify a root-cause code line or imply that the underlying maintenance
algorithm is unsound. Native iteration can depend on object identities as well
as hash seeds, so a seed does not guarantee the same outcome in a new process.
The diagnostic rates are not statistical estimates of failure probability.

To repeat one direct check, after preparing the pinned upstream cache:

```sh
PYTHONHASHSEED=1 uv run python -c 'import json; from benchmarks.bach_zodiac import direct_native_deletion_check; print(json.dumps(direct_native_deletion_check("tmp/zodiac-native"), indent=2))'
```

The benchmark keeps the upstream source unchanged and tests all preselected
formal seeds. It preserves failed-worker diagnostics and withholds timing
rankings for a configuration/task with any failed worker.
