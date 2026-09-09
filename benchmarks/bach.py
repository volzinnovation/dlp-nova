"""Source-backed Bach examples, parsed from OWL documents and checked against answers.

This module is repository benchmark tooling, not an additional ontology syntax.
Run it through ``python -m benchmarks.run --suite bach``.
"""
from __future__ import annotations

import hashlib
import json
import resource
import sys
from pathlib import Path

from rdflib import Graph, Namespace, OWL, RDF, RDFS, URIRef
from rdflib.compare import to_canonical_graph

from dlp_reasoner import Reasoner

ROOT = Path(__file__).resolve().parents[1]
BACH = Namespace("http://www.jsbach.org/bach#")
QUERY_FILE = ROOT / "examples/bach-queries.json"
PREFIXES = {
    "bach": BACH, "rdf": RDF, "rdfs": RDFS, "owl": OWL,
}
INPUTS = {
    ("ontology", "turtle"): "examples/bach.ttl",
    ("ontology", "xml"): "examples/bach.owl",
    ("family", "turtle"): "examples/bach-family.ttl",
}


def build_bach_cases():
    return [{"kind": "bach", "variant": variant, "format": syntax}
            for variant, syntax in INPUTS]


def case_name(case):
    source = "Table 2.5" if case["variant"] == "ontology" else "family maintenance"
    syntax = "RDF/XML" if case["format"] == "xml" else "Turtle"
    return f"Bach {source} ({syntax})"


def term(value):
    if ":" not in value:
        return BACH[value]
    prefix, local = value.split(":", 1)
    return URIRef(str(PREFIXES[prefix]) + local) if prefix in PREFIXES else URIRef(value)


def compact(value):
    """Stable, readable JSON answers; anonymous witness IDs are never an oracle."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (set, frozenset)):
        return sorted((compact(item) for item in value), key=lambda item: json.dumps(item))
    if isinstance(value, tuple):
        return [compact(item) for item in value]
    for prefix, namespace in PREFIXES.items():
        if str(value).startswith(str(namespace)):
            local = str(value)[len(str(namespace)):]
            return local if prefix == "bach" else f"{prefix}:{local}"
    return str(value)


def evaluate_query(reasoner, query):
    """Execute the small manifest of existing public Reasoner API calls."""
    method = query["method"]
    allowed = {
        "instances", "types", "property_values", "property_pairs", "entails", "subsumes",
        "property_subsumes", "is_symmetric", "is_transitive", "is_satisfiable",
    }
    if method == "instances_expression":
        # The query itself is an OWL expression in the same Turtle syntax as the
        # ontology. The temporary rdf:value marker is removed before compilation.
        prefixes = "\n".join(f"@prefix {p}: <{ns}> ." for p, ns in PREFIXES.items())
        prefixes += f"\n@prefix : <{BACH}> .\n"
        marker = URIRef("urn:bach:query:target")
        expressions = Graph().parse(
            data=prefixes + f"<{marker}> rdf:value {query['expression']} .", format="turtle")
        expression = expressions.value(marker, RDF.value)
        expressions.remove((marker, RDF.value, expression))
        graph = Graph()
        graph += reasoner.graph
        graph += expressions
        probe = Reasoner(graph, profile=reasoner.profile, **reasoner.engine_options)
        return probe.instances(expression)
    if method not in allowed:
        raise ValueError(f"Unsupported Bach query method: {method}")
    return getattr(reasoner, method)(*(term(value) for value in query["arguments"]))


def reachability(edges):
    """Independent graph traversal oracle for the named family, without OWL rules."""
    adjacency = {}
    for source, target in edges:
        adjacency.setdefault(source, set()).add(target)
    result = set()
    for source in adjacency:
        pending, seen = list(adjacency[source]), set()
        while pending:
            target = pending.pop()
            if target in seen:
                continue
            seen.add(target)
            pending.extend(adjacency.get(target, set()) - seen)
        result.update((source, target) for target in seen)
    return result


def benchmark_maintenance(graph):
    """Run each thesis update from the original graph, preserving its exact context."""
    from .run import timed

    js, wf, jc2 = (BACH[name] for name in
                   ("johann-sebastian", "wilhelm-friedemann", "johann-christian"))
    edges = set(graph.subject_objects(BACH.ancestorOf))
    original = reachability(edges)
    added = {(BACH[name], jc2) for name in
             ("johann-sebastian", "johann-ambrosius", "christoph", "johannes")}
    removed = {(BACH[name], wf) for name in
               ("johann-sebastian", "johann-ambrosius", "christoph")}
    updated = reachability((edges - {(js, wf)}) | {(js, jc2)})
    assert updated - original == added
    assert original - updated == removed
    operations = [
        ("facts_update", [(js, BACH.ancestorOf, jc2)], [(js, BACH.ancestorOf, wf)],
         updated, updated, "Example 6.3.2, pp. 158–159", "dred"),
        ("rule_delete", [], [(BACH.ancestorOf, RDFS.subPropertyOf, BACH.inDynasty)],
         original, set(), "Section 6.2.2, p. 151: remove T0", "dred-rules"),
        ("symmetry_insert", [(BACH.inDynasty, RDF.type, OWL.SymmetricProperty)], [],
         original, original | {(b, a) for a, b in original},
         "Section 6.2.2, p. 151: add T2; corrected cross-branch claim", "incremental-rules"),
    ]
    results = {}
    for name, add, remove, ancestors, dynasty, source, method in operations:
        reasoner = Reasoner(graph, profile="L0")
        assert reasoner.property_pairs(BACH.ancestorOf) == original
        assert reasoner.property_pairs(BACH.inDynasty) == original
        # Independently maintain the asserted input, never copy a derived closure.
        candidate = Graph()
        candidate += graph
        for triple in remove:
            candidate.remove(triple)
        for triple in add:
            candidate.add(triple)
        _, elapsed = timed(lambda: reasoner.update(add=add, remove=remove))
        fresh, rebuild_elapsed = timed(lambda: Reasoner(candidate, profile="L0"))
        assert reasoner.complete and fresh.complete
        assert reasoner.consistency == fresh.consistency == "consistent"
        assert reasoner.engine.facts == fresh.engine.facts
        assert reasoner.property_pairs(BACH.ancestorOf) == ancestors, name
        assert reasoner.property_pairs(BACH.inDynasty) == dynasty, name
        stats = dict(reasoner.engine.stats)
        assert stats["update_method"] == method, (name, stats)
        if name == "facts_update":
            assert reasoner.entails(BACH.johannes, BACH.ancestorOf, wf)
        if name == "symmetry_insert":
            assert reasoner.entails(BACH["johann-christoph"], BACH.inDynasty, BACH.johannes)
            assert not reasoner.entails(BACH["johann-christoph"], BACH.inDynasty, BACH.christoph)
            assert not reasoner.is_transitive(BACH.inDynasty)
        results[name] = {
            "seconds": elapsed, "rebuild_seconds": rebuild_elapsed, "stats": stats,
            "source": source, "validation": "matches-reachability-and-fresh-closure",
            "added_triples": len(add), "removed_triples": len(remove),
            "ancestor_pairs": compact(ancestors), "dynasty_pairs": compact(dynasty),
            "ancestor_added": compact(ancestors - original),
            "ancestor_removed": compact(original - ancestors),
            "closure_facts": len(reasoner.engine.facts),
        }
    return results


def worker(case):
    from .run import program_shape, summary, timed

    if sys.flags.optimize:
        raise RuntimeError("Benchmark validation requires Python assertions; omit -O")
    if case.get("strategy", "semi-naive") != "semi-naive":
        raise ValueError("Bach cases use the semi-naive strategy")
    repeats = case["repeats"]
    if repeats < 1:
        raise ValueError("Bach repetitions must be positive")
    variant, syntax = case["variant"], case["format"]
    source = INPUTS[variant, syntax]
    payload = (ROOT / source).read_bytes()
    manifest_bytes = QUERY_FILE.read_bytes()
    manifest = json.loads(manifest_bytes)
    queries = [query for query in manifest["queries"] if query["variant"] == variant]
    if not queries:
        raise ValueError(f"No query expectations for Bach variant {variant}")
    profile = "L3" if variant == "ontology" else "L0"
    samples = {phase: [] for phase in ("parse", "compile", "materialize", "query")}
    query_samples = {query["id"]: [] for query in queries}
    answers, counts, shapes, stats, updates = {}, [], [], [], []
    input_hash = None
    for _ in range(repeats):
        parsed, elapsed = timed(lambda: Graph().parse(
            data=payload, format=syntax, publicID=str(BACH)))
        samples["parse"].append(elapsed)
        # Canonicalize only for provenance, outside every measured phase. Parser
        # blank-node labels differ between runs and cannot define input identity.
        canonical = to_canonical_graph(parsed)
        digest = hashlib.sha256("\n".join(sorted(
            canonical.serialize(format="nt").splitlines())).encode()).hexdigest()
        assert input_hash is None or input_hash == digest
        input_hash = digest
        reasoner = Reasoner(parsed, profile=profile)
        assert reasoner.complete and reasoner.consistency == "consistent", reasoner.stats
        samples["compile"].append(reasoner.compile_seconds)
        samples["materialize"].append(reasoner.materialize_seconds)
        counts.append(len(reasoner.engine.facts))
        shapes.append(program_shape(reasoner.program))
        stats.append(dict(reasoner.engine.stats))
        for query in queries:
            actual, seconds = timed(lambda q=query: evaluate_query(reasoner, q))
            actual = compact(actual)
            expected = query["expected"]
            if isinstance(expected, list):
                expected = sorted(expected, key=lambda item: json.dumps(item))
            assert actual == expected, (query["id"], actual, expected)
            answers[query["id"]] = actual
            query_samples[query["id"]].append(seconds)
        samples["query"].append(sum(query_samples[q["id"]][-1] for q in queries))
        if variant == "family":
            original = reachability(set(parsed.subject_objects(BACH.ancestorOf)))
            assert len(original) == 24
            assert reasoner.property_pairs(BACH.ancestorOf) == original
            assert reasoner.property_pairs(BACH.inDynasty) == original
            updates.append(benchmark_maintenance(parsed))
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if sys.platform != "darwin":
        rss *= 1024
    result = {
        "case": case, "workload": {
            "source_file": source, "profile": profile, "rdf_format": syntax,
            "thesis_source": "Table 2.5, p. 35" if variant == "ontology" else
                            "Figure 6.2, p. 150; Table 6.1, p. 151; Example 6.3.2, pp. 158–159",
            "query_count": len(queries), "query_manifest": "examples/bach-queries.json",
            "query_manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
            "query_protocol": "all-manifest-queries-v1",
        },
        "measurement_protocol": "bach-source-document-v1",
        "input_triples": len(parsed), "input_sha256": input_hash,
        "input_file_sha256": hashlib.sha256(payload).hexdigest(),
        **{f"{phase}_seconds": summary(values) for phase, values in samples.items()},
        "materialized_fact_counts": counts, "program_shapes": shapes, "engine_stats": stats,
        "process_peak_rss_bytes": rss, "validation": "passed",
        "queries": [{**query, "actual": answers[query["id"]],
                     "seconds": summary(query_samples[query["id"]]), "validation": "passed"}
                    for query in queries],
    }
    if updates:
        result["workload"]["operation_protocol"] = "independent-rdf-updates-v1"
        result["workload"]["maintenance_timing"] = (
            "RDF update includes compilation; fresh rebuild includes compilation and materialization")
        result["maintenance_operations"] = {
            name: {"seconds": summary([run[name]["seconds"] for run in updates]),
                   "rebuild_seconds": summary([run[name]["rebuild_seconds"] for run in updates]),
                   "samples": [run[name] for run in updates]}
            for name in updates[0]
        }
    return result


def correctness_comparison(before, after):
    """Compare complete answer evidence, including every maintenance repetition."""
    def ordered(value):
        return sorted(value, key=json.dumps) if isinstance(value, list) else value

    def checked_queries(row):
        queries = row.get("queries", [])
        if not queries or len(queries) != row.get("workload", {}).get("query_count"):
            return None
        result = {}
        for query in queries:
            if (not {"id", "method", "expected", "actual"}.issubset(query)
                    or query["id"] in result or query.get("validation") != "passed"
                    or len(query.get("seconds", {}).get("samples", [])) != row["case"]["repeats"]
                    or ordered(query["actual"]) != ordered(query["expected"])):
                return None
            result[query["id"]] = {
                **{key: query[key] for key in ("method", "arguments", "expression") if key in query},
                "expected": ordered(query["expected"]), "actual": ordered(query["actual"]),
            }
        return result

    def stable_values(rows, field):
        if not rows or any(field not in row for row in rows):
            return None
        values = [ordered(row[field]) for row in rows]
        return values[0] if all(value == values[0] for value in values) else None

    initial = [row.get("materialized_fact_counts", []) for row in (before, after)]
    initial_match = all(
        len(counts) == row["case"]["repeats"] > 0 and len(set(counts)) == 1
        for row, counts in zip((before, after), initial)
    ) and initial[0][0] == initial[1][0]
    old_queries, new_queries = checked_queries(before), checked_queries(after)
    queries_match = old_queries is not None and old_queries == new_queries
    operation_names = set(before.get("maintenance_operations", {})) | set(
        after.get("maintenance_operations", {}))
    if after["case"]["variant"] == "family":
        operation_names |= {"facts_update", "rule_delete", "symmetry_insert"}
    counts_match, controls_match, pairs_match, operations_validated = {}, {}, {}, {}
    for name in sorted(operation_names):
        samples = [row.get("maintenance_operations", {}).get(name, {}).get("samples", [])
                   for row in (before, after)]
        operations_validated[name] = all(
            len(entries) == row["case"]["repeats"] > 0 and all(
                sample.get("validation") == "matches-reachability-and-fresh-closure"
                for sample in entries)
            for row, entries in zip((before, after), samples)
        )

        def same(field):
            left, right = (stable_values(entries, field) for entries in samples)
            return left is not None and left == right

        counts_match[name] = same("closure_facts")
        controls_match[name] = all(same(field) for field in ("added_triples", "removed_triples"))
        pairs_match[name] = all(same(field) for field in (
            "ancestor_pairs", "dynasty_pairs", "ancestor_added", "ancestor_removed"))
    both_validated = before.get("validation") == after.get("validation") == "passed"
    return {
        "verified": (both_validated and initial_match and queries_match
                     and all(counts_match.values()) and all(controls_match.values())
                     and all(pairs_match.values()) and all(operations_validated.values())),
        "both_runs_validated": both_validated, "initial_fact_counts_match": initial_match,
        "expected_query_answers_match": queries_match,
        "maintenance_closure_counts_match": counts_match,
        "maintenance_controls_match": controls_match,
        "maintenance_answers_match": pairs_match,
        "maintenance_validation_passed": operations_validated,
        "query_evidence": "Exact query definitions, expected answers and actual answers match; "
                          "every recorded maintenance sample has matching pair sets, RDF controls "
                          "and independent reachability/fresh-closure validation.",
    }


def markdown_queries(results):
    """Append reviewable source references and answers to the shared report."""
    lines = []
    for result in results:
        if result["case"]["kind"] != "bach" or "error" in result:
            continue
        lines += ["", f"## {case_name(result['case'])}: checked queries", "",
                  f"Source: `{result['workload']['source_file']}`; "
                  f"profile {result['workload']['profile']}. Parsing measures the original "
                  "document syntax. Query ms in the summary is the total of all queries below.", "",
                  "| Query | Thesis reference | Answer | Median ms |",
                  "|---|---|---|---:|"]
        for query in result["queries"]:
            answer = json.dumps(query["actual"], ensure_ascii=False).replace("|", "\\|")
            lines.append(f"| {query['id']} | {query['source']} | `{answer}` | "
                         f"{query['seconds']['median'] * 1000:.3f} |")
        if result.get("maintenance_operations"):
            lines += ["", "Bach updates each start from the original family graph. Both RDF update "
                      "and fresh rebuild timings include compilation. Exact pair sets and the "
                      "three removed/four added ancestor pairs are checked against independent "
                      "graph traversal and recorded in JSON."]
    return lines


def markdown_report(report):
    """Focused report for the standalone Bach suite, without empty synthetic sections."""
    from .run import case_name

    passed = sum(result.get("validation") == "passed" for result in report["results"])
    errors = sum("error" in result for result in report["results"])
    raw = Path(report["output_file"]).name
    lines = ["# Bach benchmark results", "",
             f"Run: {report['timestamp']}. Python {report['environment']['python']}; "
             f"{report['environment']['platform']}.", "",
             f"Validated {passed}/{report['planned_cases']} cases; {errors} errors; "
             f"{report['repeats']} repetitions per case. "
             f"[Raw samples and source hashes]({raw}).", "",
             "The full Table 2.5 ontology uses DLP L3; the chapter 6 family tree uses L0. "
             "Both ontologies are sourced from the thesis, with the documented corrections to "
             "the maintenance examples. These timings describe the current Python implementation.", "",
             "## Parsing, compilation, materialization and queries", "",
             "Times are medians in milliseconds. File reading and graph canonicalization are "
             "outside the measured phases. Query time sums every checked query in each repetition. "
             "Peak RSS includes the entire worker, inputs, queries and repetitions.", "",
             "| Case | RDF triples | Closure facts | Parse ms | Compile ms | Materialize ms | Queries ms | Peak MiB |",
             "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for result in report["results"]:
        name = case_name(result["case"])
        if "error" in result:
            error = str(result["error"]).replace("\n", " ").replace("|", "/")
            lines.append(f"| {name} | Error: {error} | | | | | | |")
            continue
        phases = [result[f"{phase}_seconds"]["median"] * 1000
                  for phase in ("parse", "compile", "materialize", "query")]
        lines.append(f"| {name} | {result['input_triples']} | "
                     f"{result['materialized_fact_counts'][0]} | "
                     + " | ".join(f"{value:.3f}" for value in phases)
                     + f" | {result['process_peak_rss_bytes'] / 2**20:.1f} |")
    lines += ["", "## Family maintenance", "",
              "Each scenario starts from the original 24 ancestor pairs. Updated results must "
              "match independent graph traversal and full fresh reconstruction. Both timings "
              "include compilation; the fact transaction ends with 25 ancestor pairs.", "",
              "| Operation | RDF update ms | Fresh rebuild ms | Method |",
              "|---|---:|---:|---|"]
    for result in report["results"]:
        for name, operation in result.get("maintenance_operations", {}).items():
            methods = sorted({sample["stats"]["update_method"] for sample in operation["samples"]})
            lines.append(f"| {name} | {operation['seconds']['median'] * 1000:.3f} | "
                         f"{operation['rebuild_seconds']['median'] * 1000:.3f} | {', '.join(methods)} |")
    matched = report.get("comparison", {}).get("matched", [])
    if matched:
        lines += ["", "## Comparison with the previous run", "",
                  "Ratios are current / previous median; values below one are faster. "
                  "Correctness compares complete query answers and every maintenance sample. "
                  f"[Comparison details and baseline provenance]({raw}).", "",
                  "| Case | Correctness | Materialize ratio | Query ratio |",
                  "|---|---|---:|---:|"]
        for comparison in matched:
            status = "passed" if comparison["correctness"]["verified"] else "FAILED"
            ratios = [comparison["phases"].get(phase, {}).get("after_over_before")
                      for phase in ("materialize_seconds", "query_seconds")]
            cells = [f"{ratio:.3f}" if ratio is not None else "—" for ratio in ratios]
            lines.append(f"| {case_name(comparison['case'])} | {status} | "
                         + " | ".join(cells) + " |")
    lines += markdown_queries(report["results"])
    lines += ["", "See [Bach source mapping and commands](../docs/BACH_BENCHMARK.md) for "
              "the OWL encodings, query scope, exact maintenance deltas and source ambiguities."]
    return "\n".join(lines) + "\n"
