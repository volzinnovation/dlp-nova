"""TPC-H Q3/Q5/Q9 join components, not complete TPC-H SQL or a TPC result.

Prepare and run with an isolated environment containing duckdb==1.4.4 and rdflib.
No production dependency is added. Generated databases stay in ignored tmp/.
All joined row primary keys remain in the component answer, preserving SQL bag
multiplicity even though the Datalog engine stores base relations as sets.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import resource
import statistics
import subprocess
import sys
import tarfile
import time

ROOT = Path(__file__).resolve().parents[1]
COMMITS = {"b1254c4": "b1254c441731ca4fdf32ea83570ff99aaa84ac2a", "5531be4": "5531be4"}
CONFIGURATIONS = ("b1254c4", "5531be4", "current-fixed", "candidate")
SCALES = (0.01, 0.1)
DUCKDB_VERSION = "1.4.4"
# Each base projection preserves that table's entire primary key. Repeated head
# variables explicitly preserve equated keys of different participating tables.
COMPONENTS = {
    3: {
        "relations": {
            "customer": "SELECT c_custkey FROM customer WHERE c_mktsegment = 'BUILDING'",
            "orders": "SELECT o_orderkey,o_custkey FROM orders WHERE o_orderdate < DATE '1995-03-15'",
            "lineitem": "SELECT l_orderkey,l_linenumber FROM lineitem WHERE l_shipdate > DATE '1995-03-15'",
        },
        "body": [("customer", ("customer",)), ("orders", ("order", "customer")),
                 ("lineitem", ("order", "line"))],
        "answer": ("customer", "order", "order", "line"),
        "oracle": """SELECT c_custkey,o_orderkey,l_orderkey,l_linenumber
FROM customer,orders,lineitem
WHERE c_mktsegment='BUILDING' AND c_custkey=o_custkey AND l_orderkey=o_orderkey
AND o_orderdate < DATE '1995-03-15' AND l_shipdate > DATE '1995-03-15'""",
    },
    5: {
        "relations": {
            "customer": "SELECT c_custkey,c_nationkey FROM customer",
            "orders": "SELECT o_orderkey,o_custkey FROM orders WHERE o_orderdate >= DATE '1994-01-01' AND o_orderdate < DATE '1995-01-01'",
            "lineitem": "SELECT l_orderkey,l_linenumber,l_suppkey FROM lineitem",
            "supplier": "SELECT s_suppkey,s_nationkey FROM supplier",
            "nation": "SELECT n_nationkey,n_regionkey FROM nation",
            "region": "SELECT r_regionkey FROM region WHERE r_name='ASIA'",
        },
        "body": [("customer", ("customer", "nation")), ("orders", ("order", "customer")),
                 ("lineitem", ("order", "line", "supplier")),
                 ("supplier", ("supplier", "nation")), ("nation", ("nation", "region")),
                 ("region", ("region",))],
        "answer": ("customer", "order", "order", "line", "supplier", "nation", "region"),
        "oracle": """SELECT c_custkey,o_orderkey,l_orderkey,l_linenumber,s_suppkey,n_nationkey,r_regionkey
FROM customer,orders,lineitem,supplier,nation,region
WHERE c_custkey=o_custkey AND l_orderkey=o_orderkey AND l_suppkey=s_suppkey
AND c_nationkey=s_nationkey AND s_nationkey=n_nationkey AND n_regionkey=r_regionkey
AND r_name='ASIA' AND o_orderdate >= DATE '1994-01-01' AND o_orderdate < DATE '1995-01-01'""",
    },
    9: {
        "relations": {
            "part": "SELECT p_partkey FROM part WHERE p_name LIKE '%green%'",
            "supplier": "SELECT s_suppkey,s_nationkey FROM supplier",
            "lineitem": "SELECT l_orderkey,l_linenumber,l_suppkey,l_partkey FROM lineitem",
            "partsupp": "SELECT ps_partkey,ps_suppkey FROM partsupp",
            "orders": "SELECT o_orderkey FROM orders",
            "nation": "SELECT n_nationkey FROM nation",
        },
        "body": [("part", ("part",)), ("supplier", ("supplier", "nation")),
                 ("lineitem", ("order", "line", "supplier", "part")),
                 ("partsupp", ("part", "supplier")), ("orders", ("order",)),
                 ("nation", ("nation",))],
        "answer": ("part", "supplier", "order", "line", "part", "supplier", "order", "nation"),
        "oracle": """SELECT p_partkey,s_suppkey,l_orderkey,l_linenumber,ps_partkey,ps_suppkey,o_orderkey,n_nationkey
FROM part,supplier,lineitem,partsupp,orders,nation
WHERE s_suppkey=l_suppkey AND ps_suppkey=l_suppkey AND ps_partkey=l_partkey
AND p_partkey=l_partkey AND o_orderkey=l_orderkey AND s_nationkey=n_nationkey
AND p_name LIKE '%green%'""",
    },
}


def require(value, message):
    if not value:
        raise RuntimeError(message)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def digest(rows):
    h = hashlib.sha256()
    for row in sorted(rows):
        h.update(json.dumps(row, separators=(",", ":")).encode())
        h.update(b"\n")
    return h.hexdigest()


def source_hashes(root):
    return {str(p.relative_to(root)): sha(p) for p in sorted((root / "src/dlp_reasoner").glob("*.py"))}


def db_path(cache, scale):
    return cache / f"tpch-sf{scale}.duckdb"


def prepare(cache):
    import duckdb
    require(duckdb.__version__ == DUCKDB_VERSION, "use pinned duckdb==1.4.4")
    cache.mkdir(parents=True, exist_ok=True)
    existing_manifest = cache / "manifest.json"
    if existing_manifest.exists():
        previous = json.loads(existing_manifest.read_text())
        require(previous["duckdb"] == DUCKDB_VERSION, "cached generator version drift")
        require(previous["components"] == json.loads(json.dumps(COMPONENTS)), "component definition changed")
        for scale in SCALES:
            require(sha(db_path(cache, scale)) == previous["databases"][str(scale)]["sha256"],
                    "cached database bytes changed")
        return previous
    manifest = {"generator": "DuckDB official tpch extension dbgen", "duckdb": duckdb.__version__,
                "documentation": "https://duckdb.org/docs/lts/core_extensions/tpch",
                "scale_factors": list(SCALES), "components": COMPONENTS, "databases": {}}
    for scale in SCALES:
        path = db_path(cache, scale)
        con = duckdb.connect(str(path))
        con.execute("SET threads=1")
        con.execute("INSTALL tpch; LOAD tpch")
        existing = set(r[0] for r in con.execute("SHOW TABLES").fetchall())
        if not existing:
            started = time.perf_counter()
            con.execute(f"CALL dbgen(sf={scale})")
            generation_seconds = time.perf_counter() - started
        else:
            generation_seconds = None
            require(existing == {"customer", "orders", "lineitem", "supplier", "part", "partsupp", "nation", "region"},
                    "unexpected existing tables")
        counts = {table: con.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
                  for table in ("customer", "orders", "lineitem", "supplier", "part", "partsupp", "nation", "region")}
        original = {str(n): q for n, q in con.execute(
            "SELECT query_nr,query FROM tpch_queries() WHERE query_nr IN (3,5,9)").fetchall()}
        extension = con.execute("SELECT extension_version,install_path FROM duckdb_extensions() WHERE extension_name='tpch'").fetchone()
        oracles = {}
        for number, component in COMPONENTS.items():
            rows = con.execute(component["oracle"]).fetchall()
            require(len(rows) == len(set(rows)), "primary-key output must preserve each SQL bag row uniquely")
            oracles[str(number)] = {"count": len(rows), "sha256": digest(rows)}
        con.execute("CHECKPOINT")
        con.close()
        manifest["databases"][str(scale)] = {
            "file": path.name, "sha256": sha(path), "table_counts": counts,
            "generation_seconds": generation_seconds, "generation_sql": f"CALL dbgen(sf={scale})",
            "extension_version": extension[0], "extension_sha256": sha(extension[1]),
            "original_queries": original, "component_oracles": oracles,
        }
    manifest_path = cache / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def make_program(number, relations):
    from dlp_reasoner.model import Atom, Program, Rule, Var
    component = COMPONENTS[number]
    facts = {Atom("urn:tpch:" + table, tuple(row)) for table, rows in relations.items() for row in rows}
    variables = tuple(Var(name) for name in component["answer"])
    rule = Rule(None, tuple(Atom("urn:tpch:" + table, tuple(Var(name) for name in columns))
                            for table, columns in component["body"]))
    return Program([], facts), variables, rule


def worker(cache, configuration, scale):
    import duckdb
    import dlp_reasoner
    from dlp_reasoner.engine import Engine, _SEED
    from dlp_reasoner.model import Atom, TOP
    require(duckdb.__version__ == DUCKDB_VERSION, "DuckDB version drift")
    if configuration in {"current-fixed", "candidate"}:
        for option in ("_compiled_joins_enabled", "_incremental_index_enabled", "_incremental_validation_enabled"):
            require(hasattr(Engine, option), f"missing candidate switch: {option}")
            setattr(Engine, option, configuration == "candidate")
    manifest = json.loads((cache / "manifest.json").read_text())
    expected = manifest["databases"][str(scale)]
    path = db_path(cache, scale)
    require(sha(path) == expected["sha256"], "database bytes changed")
    con = duckdb.connect(str(path), read_only=True)
    con.execute("SET threads=1")
    observations = []
    for number, component in COMPONENTS.items():
        started = time.perf_counter()
        relations = {table: con.execute(sql).fetchall() for table, sql in component["relations"].items()}
        filter_seconds = time.perf_counter() - started
        started = time.perf_counter()
        program, variables, rule = make_program(number, relations)
        encoding_seconds = time.perf_counter() - started
        source_facts = len(program.facts)
        require(source_facts == sum(map(len, relations.values())), "base projection collapsed duplicate rows")
        started = time.perf_counter()
        engine = Engine(program, max_facts=3_000_000).materialize()
        index_seconds = time.perf_counter() - started
        require(engine.complete and not engine.violations, "base relation load incomplete")
        # No rules are installed for base loading: its full closure has an
        # independent exact specification, including every active-domain seed.
        before_facts = program.facts | {
            Atom(TOP, (term,)) for fact in program.facts for term in fact.args}
        before_facts.add(Atom(TOP, (_SEED,)))
        require(engine.facts == before_facts, "base closure differs from facts plus domain")
        started = time.perf_counter()
        rows = [tuple(binding[var] for var in variables) for binding in engine._solutions(rule)]
        join_seconds = time.perf_counter() - started
        require(engine.facts == before_facts, "query changed materialization")
        started = time.perf_counter()
        oracle_rows = con.execute(component["oracle"]).fetchall()
        sql_oracle_seconds = time.perf_counter() - started
        require(len(rows) == len(set(rows)), "unexpected duplicate Datalog answer")
        require(len(oracle_rows) == len(set(oracle_rows)), "SQL oracle lost row identity")
        require(set(rows) == set(oracle_rows), "component tuples differ from independent SQL")
        require(digest(rows) == expected["component_oracles"][str(number)]["sha256"], "prepared oracle mismatch")
        observations.append({
            "query_component": number, "scale_factor": scale, "source_facts": source_facts,
            "relation_counts": {table: len(rows) for table, rows in relations.items()},
            "relation_sha256": {table: digest(rows) for table, rows in relations.items()},
            "filter_projection_seconds": filter_seconds, "encoding_seconds": encoding_seconds,
            "index_materialization_seconds": index_seconds, "join_seconds": join_seconds,
            "component_end_to_end_seconds": filter_seconds + encoding_seconds + index_seconds + join_seconds,
            "duckdb_oracle_seconds": sql_oracle_seconds,
            "answers": len(rows), "answer_sha256": digest(rows), "sql_bag_rows": len(oracle_rows),
            "exact_sql_match": True, "exact_base_closure_match": True, "base_closure_facts": len(engine.facts),
            "stats": engine.stats.copy(),
        })
        del engine, before_facts, program, rows, relations, oracle_rows
    con.close()
    return {"configuration": configuration, "scale_factor": scale, "queries": observations,
            "source_sha256": source_hashes(Path(dlp_reasoner.__file__).resolve().parents[2]),
            "package_path": str(Path(dlp_reasoner.__file__).resolve()),
            "driver_sha256": sha(__file__), "input_manifest_sha256": sha(cache / "manifest.json"),
            "pythonhashseed": os.environ.get("PYTHONHASHSEED"), "python": sys.version,
            "duckdb": duckdb.__version__, "database_sha256": sha(path),
            "peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (1 if sys.platform == "darwin" else 1024)}


def checkout(cache, label):
    commit = subprocess.run(["git", "rev-parse", COMMITS[label]], cwd=ROOT,
                            capture_output=True, text=True, check=True).stdout.strip()
    path = cache / ("source-" + label)
    if not path.exists():
        payload = subprocess.run(["git", "archive", commit, "src/dlp_reasoner"], cwd=ROOT,
                                 capture_output=True, check=True).stdout
        path.mkdir()
        with tarfile.open(fileobj=io.BytesIO(payload)) as archive:
            archive.extractall(path, filter="data")
    for file in sorted((path / "src/dlp_reasoner").glob("*.py")):
        expected = subprocess.run(["git", "show", commit + ":" + str(file.relative_to(path))], cwd=ROOT,
                                  capture_output=True, check=True).stdout
        require(file.read_bytes() == expected, "historical source drift")
    return commit, path


def write_markdown(report):
    rows = ["# TPC-H-derived join components", "",
            "Q3/Q5/Q9 FROM+WHERE joins at SF0.01 and SF0.1, using DuckDB1.4.4's official tpch/dbgen extension.",
            "This is not a complete TPC-H execution, a QphH metric, a TPC-audited result, or a reproduction of Qiao et al.'s SF100 SQL evaluation.",
            "", "| Scale | Component | Configuration | Facts | Answers | Filter(ms) | Encode(ms) | Index(ms) | Join(ms) | Componenttotal(ms) |", "|---:|---|---|---:|---:|---:|---:|---:|---:|---:|"]
    for case, configs in report["summary"].items():
        for config, values in configs.items():
            rows.append(f"| {values['scale_factor']} | Q{values['query_component']} | {config} | {values['source_facts']} | {values['answers']} | "
                        + " | ".join(f"{values[key]['median'] * 1000:.3f}" for key in (
                            "filter_projection_seconds", "encoding_seconds", "index_materialization_seconds",
                            "join_seconds", "component_end_to_end_seconds")) + " |")
    rows += ["", "All participating table primary keys remain in every answer (including both components of lineitem and partsupp keys). "
             "Each Datalog answer set is compared with the exact DuckDB SQL bag of pre-aggregation row identities; multiplicities are verified rather than silently collapsed.",
             "The joins and constant filters are taken from the extension's pinned Q3/Q5/Q9 queries. Aggregation, arithmetic outputs, sorting and top-k are omitted. "
             "DuckDB performs date/string filters and narrow column projections; their extraction time is reported separately and included in component end-to-end time.",
             "The component rule is queried through the existing Engine._solutions evaluator. Any candidate join-plan construction is inside the join timer. "
             "A new engine loads the component's facts; index construction and fact encoding are separate and included in component end-to-end time. "
             "Integer primary keys are ordinary Datalog constants; this is not an RDF parser benchmark.",
             "Baseline b1254c4 and pre-extension5531be4 are immutable checkouts; current-fixed disables experimental switches; candidate enables compiled joins, incremental index maintenance and insertion validation reuse. "
             "The latter two are maintenance features and do not have update work to accelerate here; their setup overhead is included.",
             "Raw process observations, pinned database/extension/source hashes, original SQL texts, component SQL, table counts and exact oracle digests are in the JSON. "
             "Queries run sequentially Q3,Q5,Q9 inside each fresh process. Whole-database integrity hashing precedes timing and warms the filesystem cache; DuckDB caches are not reset between components. "
             "DuckDB uses one thread. Its oracle time is context, not a fair end-to-end speed ranking against the Python DLP pipeline.",
             "", "## Reproduce", "", "```sh",
             "uv venv tmp/tpch-python --python .venv/bin/python",
             "uv pip install --python tmp/tpch-python/bin/python duckdb==1.4.4 rdflib==7.6.0",
             "tmp/tpch-python/bin/python -m benchmarks.external_tpch --prepare",
             "tmp/tpch-python/bin/python -m benchmarks.external_tpch --blocks 3 --output /tmp/tpch-components-reproduction.json",
             "```", "", "Sources: [DuckDB tpch extension](https://duckdb.org/docs/lts/core_extensions/tpch), "
             "[TPC-H specification](https://www.tpc.org/tpc_documents_current_versions/pdf/tpc-h_v3.0.0.pdf).", ""]
    return "\n".join(rows)


def run(cache, output, blocks):
    require(blocks >= 3, "at least three blocks required")
    require(not output.exists() and not output.with_suffix(".md").exists(), "refuse to overwrite report")
    manifest = json.loads((cache / "manifest.json").read_text())
    commits, paths = {}, {}
    for label in COMMITS:
        commits[label], paths[label] = checkout(cache, label)
    current_sources, driver_hash = source_hashes(ROOT), sha(__file__)
    report = {"schema_version": 1, "benchmark": "TPC-H-derived-primary-key-join-components-v1",
              "started_utc": datetime.now(timezone.utc).isoformat(), "commits": commits,
              "current_head": subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                                             capture_output=True, text=True, check=True).stdout.strip(),
              "current_source_sha256": current_sources, "driver_sha256": driver_hash,
              "platform": platform.platform(), "machine": platform.machine(), "cpu_count": os.cpu_count(),
              "manifest": manifest, "workers": [], "protocol": {
                  "blocks": blocks, "scale_factors": list(SCALES), "configurations": list(CONFIGURATIONS),
                  "ordering": "rotate configuration order by block+scale index; same hashseed within each block",
                  "timeout_seconds": 300, "max_facts": 3_000_000, "seed_start": 5000,
                  "components": [3, 5, 9], "duckdb_threads": 1,
                  "input_cache": "whole database integrity hash precedes timing; filesystem cache is warm",
                  "primary_metric": "join_seconds",
                  "secondary_metric": "component_end_to_end_seconds",
                  "timing": "fresh process per scale/configuration/block; three components sequentially; fully consumed results",
                  "scope": "original FROM+WHERE primary-key row identities only; no aggregate/sort/top-k",
                  "host_note": "coordinated quiet window; filesystem caches not flushed"}}
    protocol = output.with_name(output.stem + "-protocol.json")
    require(not protocol.exists(), "refuse to overwrite protocol")
    protocol.write_text(json.dumps(report, indent=2) + "\n")
    for block in range(blocks):
        for scale_index, scale in enumerate(SCALES):
            offset = (block + scale_index) % len(CONFIGURATIONS)
            order = CONFIGURATIONS[offset:] + CONFIGURATIONS[:offset]
            for position, config in enumerate(order):
                require(source_hashes(ROOT) == current_sources and sha(__file__) == driver_hash,
                        "source changed during measurement")
                source = paths.get(config, ROOT)
                env = {**os.environ, "PYTHONHASHSEED": str(5000 + block),
                       "PYTHONPATH": os.pathsep.join([str(source / "src"), str(ROOT)])}
                command = [sys.executable, "-m", "benchmarks.external_tpch", "--worker", config,
                           "--scale", str(scale), "--cache", str(cache)]
                completed = subprocess.run(command, cwd=ROOT, env=env, capture_output=True,
                                           text=True, check=True, timeout=300)
                row = json.loads(completed.stdout)
                require(row["source_sha256"] == source_hashes(source), "wrong measured source")
                row.update(block=block, position=position, command=command)
                for query in row["queries"]:
                    for previous in report["workers"]:
                        if previous["scale_factor"] == scale:
                            reference = next(q for q in previous["queries"]
                                             if q["query_component"] == query["query_component"])
                            require(query["relation_sha256"] == reference["relation_sha256"],
                                    "base relation mismatch across configurations")
                            require(query["answer_sha256"] == reference["answer_sha256"],
                                    "answer mismatch across configurations")
                report["workers"].append(row)
                print(f"block {block + 1}/{blocks} SF{scale} {config}: " + ", ".join(
                    f"Q{q['query_component']} {q['join_seconds']:.4f}s exact" for q in row["queries"]), flush=True)
    metrics = ("filter_projection_seconds", "encoding_seconds", "index_materialization_seconds", "join_seconds",
               "component_end_to_end_seconds", "duckdb_oracle_seconds")
    report["summary"] = {}
    for scale in SCALES:
        for number in COMPONENTS:
            case = f"sf{scale}-q{number}"
            report["summary"][case] = {}
            for config in CONFIGURATIONS:
                rows = [q for w in report["workers"] if w["scale_factor"] == scale and w["configuration"] == config
                        for q in w["queries"] if q["query_component"] == number]
                require(len(rows) == blocks, "missing component observations")
                require(len({q["answer_sha256"] for q in rows}) == 1, "answer drift")
                require(len({json.dumps(q["relation_sha256"], sort_keys=True) for q in rows}) == 1, "input projection drift")
                summary = {key: {"median": statistics.median(q[key] for q in rows),
                                 "minimum": min(q[key] for q in rows), "maximum": max(q[key] for q in rows)} for key in metrics}
                summary.update(scale_factor=scale, query_component=number, source_facts=rows[0]["source_facts"],
                               answers=rows[0]["answers"], answer_sha256=rows[0]["answer_sha256"])
                report["summary"][case][config] = summary
    report["finished_utc"] = datetime.now(timezone.utc).isoformat()
    report["protocol_sha256"] = sha(protocol)
    output.write_text(json.dumps(report, indent=2) + "\n")
    output.with_suffix(".md").write_text(write_markdown(report))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=ROOT / "tmp/tpch-components")
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--worker", choices=CONFIGURATIONS)
    parser.add_argument("--scale", type=float, choices=SCALES, default=0.01)
    parser.add_argument("--blocks", type=int, default=3)
    parser.add_argument("--output", type=Path, default=ROOT / "benchmarks/external-tpch-results.json")
    args = parser.parse_args()
    if args.prepare:
        print(json.dumps(prepare(args.cache.resolve()), indent=2))
    elif args.worker:
        print(json.dumps(worker(args.cache.resolve(), args.worker, args.scale)))
    else:
        run(args.cache.resolve(), args.output.resolve(), args.blocks)


if __name__ == "__main__":
    main()
