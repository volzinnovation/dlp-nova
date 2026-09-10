#!/usr/bin/env python3
"""Execute the versioned rules through real Python/native query backends."""
import argparse
import json
from pathlib import Path

from rdflib import Namespace

from dlp_reasoner import Reasoner
from dlp_reasoner.query_runtime import QueryRuntime, QueryScope
from dlp_reasoner.scoped_views import BirthDateView


HERE = Path(__file__).resolve().parent
BACH = Namespace("http://www.jsbach.org/bach#")
BT = Namespace("https://example.org/bach-temporal#")
Q = Namespace("urn:dlp:query:")


def run(backend):
    reasoner = Reasoner.from_file(HERE / "bach-temporal.dlp", profile="L0", backend=backend)
    scope = QueryScope("urn:example:bach:accepted-exact-records-v1", "1")
    selection = BirthDateView(reasoner, child_property=BACH.hasChild,
                              birth_property=BT.birthDate, accepted_property=BT.acceptedBirthDate,
                              certificate_property=BT.validatedCompleteChildDates).prepare(scope)
    with QueryRuntime((HERE / "queries.dlq").read_text(), reasoner=reasoner,
                      backend=backend) as runtime:
        result = runtime.evaluate(selection.relations, scope=scope,
                                  diagnostics=selection.diagnostics, metadata=selection.metadata)
        values = {name: sorted([[str(parent), int(age)] for parent, age in result.rows(Q[name])])
                  for name in ("fatherAtAgeKnown", "motherAtAgeKnown", "fatherAtAge", "motherAtAge")}
        assert values["fatherAtAgeKnown"] == [[str(BACH["johann-sebastian"]), 23]]
        assert values["motherAtAgeKnown"] == [[str(BACH["maria-barbara"]), 24]]
        assert not values["fatherAtAge"] and not values["motherAtAge"]
        return {"backend": backend, "production_temporal_operators_executed": True,
                "scope": scope.name, "scope_revision": scope.revision,
                "selection_policy": result.metadata["selection_policy"],
                "selected_view_complete": result.complete, "family_history_complete": False,
                "answers": values,
                "diagnostics": [{"subject": str(d.subject), "code": d.code}
                                for d in result.diagnostics], "execution": runtime.stats}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=("python", "native", "both"), default="python")
    args = parser.parse_args()
    backends = ("python", "native") if args.backend == "both" else (args.backend,)
    print(json.dumps([run(backend) for backend in backends], indent=2))
