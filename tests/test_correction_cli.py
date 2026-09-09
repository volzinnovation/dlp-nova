"""Corrected TBox queries are available through the public command line."""

import json

import pytest

from dlp_reasoner.cli import main


@pytest.fixture
def ontology(tmp_path):
    path = tmp_path / "schema.ttl"
    path.write_text('''
        @prefix : <urn:correction:> .
        @prefix owl: <http://www.w3.org/2002/07/owl#> .
        @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
        :C owl:equivalentClass :D .
        :E rdfs:subClassOf :C .
        :M rdfs:subClassOf [ owl:oneOf (:o) ] .
        :N rdfs:subClassOf [ owl:oneOf (:o) ] .
        :p rdfs:subPropertyOf :q; owl:equivalentProperty :t .
        :q a owl:TransitiveProperty; owl:inverseOf :r;
            rdfs:domain :C; rdfs:range :D .
        :s a owl:SymmetricProperty .
    ''')
    return path


@pytest.mark.parametrize("command,arguments,expected", [
    ("equivalent-classes", ("C", "D"), True),
    ("equivalent-classes", ("M", "N"), False),
    ("property-subsumes", ("q", "p"), True),
    ("property-subsumes", ("p", "q"), False),
    ("equivalent-properties", ("p", "t"), True),
    ("equivalent-properties", ("p", "q"), False),
    ("inverse-properties", ("q", "r"), True),
    ("inverse-properties", ("p", "r"), False),
    ("is-symmetric", ("s",), True),
    ("is-symmetric", ("p",), False),
    ("is-transitive", ("q",), True),
    ("is-transitive", ("p",), False),
    ("has-domain", ("p", "C"), True),
    ("has-domain", ("p", "E"), False),
    ("has-range", ("p", "D"), True),
    ("has-range", ("p", "E"), False),
])
def test_corrected_schema_queries(ontology, capsys, command, arguments, expected):
    status = main([command, str(ontology), *("urn:correction:" + x for x in arguments)])
    output = capsys.readouterr()
    assert status == 0, output.err
    assert json.loads(output.out) is expected
    assert not output.err
