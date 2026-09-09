"""The thesis input format uses the existing reasoning and command interfaces."""

import json

import pytest
from rdflib import Namespace, RDF, RDFS

from dlp_reasoner import Reasoner
from dlp_reasoner.cli import main


EX = Namespace("urn:dlp:example:")
DOCUMENT = """
Namespace(ex = <urn:dlp:example:>)
Ontology(
  Class(ex:A partial ex:B)
  Individual(ex:a type(ex:A))
)
"""


def test_text_api_and_incremental_updates():
    reasoner = Reasoner.from_dlp(DOCUMENT, profile="L0")
    assert reasoner.instances(EX.B) == {EX.a}
    reasoner.update(remove=[(EX.A, RDFS.subClassOf, EX.B)])
    assert not reasoner.entails(EX.a, RDF.type, EX.B)
    reasoner.update(add=[(EX.A, RDFS.subClassOf, EX.B)])
    assert reasoner.entails(EX.a, RDF.type, EX.B)


@pytest.mark.parametrize("suffix,options", [(".dlp", []), (".DLP", []),
                                            (".txt", ["--format", "dlp"])])
def test_cli_selects_dlp_format(tmp_path, capsys, suffix, options):
    path = tmp_path / ("example" + suffix)
    path.write_text(DOCUMENT, encoding="utf-8")
    assert main(["instances", str(path), str(EX.B), *options]) == 0
    assert json.loads(capsys.readouterr().out) == [str(EX.a)]


def test_cli_error_includes_source_location(tmp_path, capsys):
    path = tmp_path / "broken.dlp"
    path.write_text("Ontology(\n  Individual(missing:a)\n)", encoding="utf-8")
    assert main(["validate", str(path)]) == 1
    error = json.loads(capsys.readouterr().err)
    assert error["type"] == "DLPParseError"
    assert str(path) in error["error"]
    assert "2" in error["error"]


def test_cli_invalid_utf8_is_structured(tmp_path, capsys):
    path = tmp_path / "broken.dlp"
    path.write_bytes(b"Ontology(\xff)")
    assert main(["validate", str(path)]) == 1
    error = json.loads(capsys.readouterr().err)
    assert error["type"] == "ProfileError"
    assert "UTF-8" in error["error"]


def test_cli_profile_inconsistency_and_incomplete_status(tmp_path, capsys):
    path = tmp_path / "recursive.dlp"
    path.write_text("""
        Namespace(ex = <urn:dlp:example:>)
        Ontology(
          Class(ex:A partial restriction(ex:p someValuesFrom(ex:A)))
          Individual(ex:a type(ex:A))
        )
    """, encoding="utf-8")
    assert main(["validate", str(path)]) == 1
    assert json.loads(capsys.readouterr().err)["type"] == "ProfileError"
    assert main(["validate", str(path), "--profile", "L3", "--max-depth", "2"]) == 3
    assert json.loads(capsys.readouterr().out)["complete"] is False
    assert main(["validate", "examples/inconsistent.dlp"]) == 2
    assert json.loads(capsys.readouterr().out)["consistency"] == "inconsistent"


def test_cli_materialization_and_rules(tmp_path, capsys):
    path = tmp_path / "example.dlp"
    path.write_text(DOCUMENT, encoding="utf-8")
    output = tmp_path / "closure.ttl"
    assert main(["materialize", str(path), "-o", str(output)]) == 0
    assert json.loads(capsys.readouterr().out)["complete"] is True
    assert Reasoner.from_file(output).entails(EX.a, RDF.type, EX.B)
    assert main(["rules", str(path)]) == 0
    assert "urn:dlp:example:B" in capsys.readouterr().out
