"""Strict domain profile and Python/native scalar equivalence."""
from decimal import Decimal
import random

import pytest
from rdflib import Literal, URIRef
from rdflib.namespace import XSD

from dlp_reasoner.domains import (
    INT_MAX, INT_MIN, NUMERIC, SPATIAL, TEMPORAL, DateValue, DecimalValue,
    DecodedCache, DomainError, DomainRegistry, DurationValue, FloatValue,
    InstantValue, IntegerValue, Interval, Point, Quantity, TimeValue, compare_values,
    decode, order_key, value_key,
)


def lit(text, datatype):
    return Literal(text, datatype=datatype, normalize=False)


@pytest.fixture(params=["python", "native"])
def registry(request):
    return DomainRegistry(request.param)


def test_registry_modes_and_explicit_capability(registry):
    op = registry.get(TEMPORAL + "completedYears")
    assert op.arity == 3 and op.required_positions == (0, 1, 2)
    assert op.input_types == ("date", "date", "policy") and op.result_type == "integer"
    assert op.determinism == "pure" and op.batches and op.cardinality == "one"
    assert registry.get("urn:dlp:proposed:temporal:before").uri == TEMPORAL + "before"
    with pytest.raises(DomainError, match="Unknown") as error:
        registry.get(TEMPORAL + "unknown")
    assert error.value.code == "UNAVAILABLE"
    with pytest.raises(TypeError):
        registry.operations["invented"] = op


@pytest.mark.parametrize("value,code", [
    (lit("2023-02-29", XSD.date), "DOMAIN_ERROR"),
    (lit("2024-02-29Z", XSD.date), "DOMAIN_ERROR"),
    (lit("0000-01-01", XSD.date), "DOMAIN_ERROR"),
    (lit("2024-01-01T12:00:00", XSD.dateTime), "DOMAIN_ERROR"),
    (lit("2024-01-01T24:00:00Z", XSD.dateTime), "DOMAIN_ERROR"),
    (lit("2024-01-01T12:00:60Z", XSD.dateTime), "DOMAIN_ERROR"),
    (lit("2024-01-01T12:00:00+14:01", XSD.dateTime), "DOMAIN_ERROR"),
    (lit("2024-01-01T12:00:00.0000000Z", XSD.dateTime), "INEXACT"),
    (lit("12:00:00Z", XSD.time), "DOMAIN_ERROR"),
    (lit("P1Y", XSD.duration), "DOMAIN_ERROR"),
    (lit("PT", XSD.dayTimeDuration), "DOMAIN_ERROR"),
    (lit("P1DT", XSD.dayTimeDuration), "DOMAIN_ERROR"),
    (lit("PT٠S", XSD.dayTimeDuration), "DOMAIN_ERROR"),
    (lit("NaN", XSD.double), "DOMAIN_ERROR"),
    (lit("1e10000", XSD.double), "DOMAIN_ERROR"),
    (lit("1.0", XSD.float), "UNAVAILABLE"),
    (lit("1e2", XSD.decimal), "DOMAIN_ERROR"),
    (lit("0.0000000000000000001", XSD.decimal), "INEXACT"),
    (lit(str(INT_MAX + 1), XSD.integer), "OVERFLOW"),
    (lit("256", XSD.unsignedByte), "DOMAIN_ERROR"),
    (lit("-1", XSD.positiveInteger), "DOMAIN_ERROR"),
])
def test_invalid_decoding_is_explicit(value, code):
    with pytest.raises(DomainError) as error:
        decode(value)
    assert error.value.code == code


def test_immutable_value_bounds_and_lexical_cache():
    first, second = lit("01", XSD.integer), lit("1", XSD.integer)
    assert first != second and value_key(first) == value_key(second)
    cache = DecodedCache(2)
    assert cache.decode(first) == IntegerValue(1)
    assert cache.decode(first) == IntegerValue(1) and cache.hits == 1
    cache.decode(second)
    assert len(cache) == 2
    cache.decode(lit("2", XSD.integer))
    assert len(cache) == 2
    assert DecimalValue(1200, 3) == DecimalValue(12, 1)
    assert decode(Decimal("1.20E+2")) == DecimalValue(120)
    with pytest.raises(DomainError):
        IntegerValue(True)
    with pytest.raises(DomainError):
        DateValue(2024, 2, 30)
    with pytest.raises(DomainError):
        FloatValue(float("nan"))
    with pytest.raises(DomainError):
        order_key(Point(0., 0.))
    with pytest.raises(DomainError):
        compare_values(DateValue(1970, 1, 1), InstantValue(0))


def test_temporal_normalization_and_completed_years(registry):
    a = lit("2024-01-01T01:00:00+01:00", XSD.dateTime)
    b = lit("2024-01-01T00:00:00Z", XSD.dateTimeStamp)
    assert registry.evaluate(TEMPORAL + "equal", [a, b]) == Literal(True)
    assert registry.evaluate(TEMPORAL + "before", [a, b]) == Literal(False)
    assert registry.evaluate(TEMPORAL + "after", [a, b]) == Literal(False)
    birth = DateValue(2000, 2, 29)
    rows = [[birth, DateValue(2021, 2, 28), "march1"],
            [birth, DateValue(2021, 3, 1), URIRef("urn:dlp:proposed:calendar-policy:march1")],
            [birth, DateValue(2024, 2, 29), "march1"],
            [birth, DateValue(1999, 1, 1), "march1"],
            [birth, DateValue(2024, 2, 29), "feb28"]]
    results = registry.evaluate_batch(TEMPORAL + "completedYears", rows)
    assert [r.value for r in results[:3]] == [Literal(20), Literal(21), Literal(24)]
    assert [r.error.code for r in results[3:]] == ["DOMAIN_ERROR", "UNAVAILABLE"]
    assert [r.error.row for r in results[3:]] == [3, 4]
    with pytest.raises(DomainError) as error:
        registry.evaluate(TEMPORAL + "before", [birth, a])
    assert error.value.code == "TYPE_ERROR"


def test_duration_arithmetic_intervals_and_midnight(registry):
    assert decode(lit("-P1DT2H3M4.000005S", XSD.dayTimeDuration)) == DurationValue(-93784000005)
    assert decode(lit("00:00:00.000001", XSD.time)) == TimeValue(1)
    assert decode(lit("1969-12-31T23:59:59.999999Z", XSD.dateTime)) == InstantValue(-1)
    result = registry.evaluate(TEMPORAL + "add", [DateValue(2024, 2, 28), DurationValue(86400000000)])
    assert result == lit("2024-02-29", XSD.date)
    assert registry.evaluate(TEMPORAL + "elapsedSeconds", [InstantValue(0), InstantValue(1250000)]) == lit("1.25", XSD.decimal)
    interval = registry.evaluate(TEMPORAL + "interval", [InstantValue(0), InstantValue(10)])
    adjacent = Interval(InstantValue(10), InstantValue(20))
    assert registry.evaluate(TEMPORAL + "contains", [interval, InstantValue(0)]) == Literal(True)
    assert registry.evaluate(TEMPORAL + "contains", [interval, InstantValue(10)]) == Literal(False)
    assert registry.evaluate(TEMPORAL + "meets", [interval, adjacent]) == Literal(True)
    assert registry.evaluate(TEMPORAL + "intersects", [interval, adjacent]) == Literal(False)
    assert registry.evaluate(TEMPORAL + "intersects", [interval, interval]) == Literal(True)
    for args in ([InstantValue(0), InstantValue(0)], [DateValue(2024, 1, 1), InstantValue(1)]):
        with pytest.raises(DomainError):
            registry.evaluate(TEMPORAL + "interval", args)
    with pytest.raises(DomainError):
        registry.evaluate(TEMPORAL + "add", [TimeValue(86399999999), DurationValue(1)])
    with pytest.raises(DomainError):
        registry.evaluate(TEMPORAL + "add", [DateValue(9999, 12, 31), DurationValue(86400000000)])


def test_exact_arithmetic_and_error_batches(registry):
    assert registry.evaluate(NUMERIC + "divide", [1, 8]) == lit("0.125", XSD.decimal)
    assert registry.evaluate(NUMERIC + "add", [lit("0.1", XSD.decimal), lit("0.2", XSD.decimal)]) == lit("0.3", XSD.decimal)
    assert registry.evaluate(NUMERIC + "multiply", [DecimalValue(INT_MAX, 18), DecimalValue(10)]) == lit("92.23372036854775807", XSD.decimal)
    rows = [[INT_MAX, 1], [2, 3], [True, 1], [1.0, 1], [1], None]
    results = registry.evaluate_batch(NUMERIC + "add", rows)
    assert [r.error.code if r.error else str(r.value) for r in results] == [
        "OVERFLOW", "5", "TYPE_ERROR", "TYPE_ERROR", "ARITY_ERROR", "TYPE_ERROR"]
    for pair, code in (([1, 3], "INEXACT"), ([1, 0], "DOMAIN_ERROR"),
                       ([INT_MIN, -1], "OVERFLOW")):
        with pytest.raises(DomainError) as error:
            registry.evaluate(NUMERIC + "divide", pair)
        assert error.value.code == code
    assert registry.evaluate(NUMERIC + "equal", [1, DecimalValue(1)]) == Literal(True)
    result = registry.evaluate(NUMERIC + "toFloat", [DecimalValue(1234567890123456789, 18)])
    assert result == Literal(1.2345678901234567, datatype=XSD.double)
    assert registry.evaluate(NUMERIC + "floatLessThanOrEqual", [result, result]) == Literal(True)


def test_wgs84_shared_implementation_and_point_metadata(registry):
    a = registry.evaluate(SPATIAL + "wgs84Point", [0, 0])
    b = registry.evaluate(SPATIAL + "wgs84Point", [1, 0])
    assert a == Point(0., 0.) and a.crs == "EPSG:4326" and a.revision == "wgs84-v1"
    try:
        distance = registry.evaluate(SPATIAL + "wgs84Distance", [a, b])
    except DomainError as error:
        if error.code == "UNAVAILABLE":
            pytest.skip("Optional PROJ GeographicLib C dependency unavailable")
        raise
    assert float(distance) == pytest.approx(111319.49079327357, abs=1e-6)
    assert registry.evaluate(SPATIAL + "dwithin", [a, b, distance]) == Literal(True)
    assert registry.evaluate(SPATIAL + "dwithin", [a, b, 111000]) == Literal(False)
    with pytest.raises(DomainError):
        registry.evaluate(SPATIAL + "dwithin", [a, b, -1])
    with pytest.raises(DomainError):
        registry.evaluate(SPATIAL + "wgs84Point", [0, 91])


def test_explicit_quantity_units_and_same_unit_arithmetic(registry):
    left = registry.evaluate(NUMERIC + "quantity", [3, "metre"])
    right = registry.evaluate(NUMERIC + "quantity", [DecimalValue(15, 1),
        URIRef("urn:dlp:proposed:unit:metre")])
    assert left == Quantity(IntegerValue(3), "urn:dlp:unit:metre")
    assert registry.evaluate(NUMERIC + "quantityAdd", [left, right]) == Quantity(
        DecimalValue(45, 1), "urn:dlp:unit:metre")
    assert registry.evaluate(NUMERIC + "quantityDivide", [left, right]) == lit("2.0", XSD.decimal)
    seconds = registry.evaluate(NUMERIC + "quantity", [3, "second"])
    with pytest.raises(DomainError) as error:
        registry.evaluate(NUMERIC + "quantityAdd", [left, seconds])
    assert error.value.code == "TYPE_ERROR"
    with pytest.raises(DomainError):
        registry.evaluate(NUMERIC + "quantityMultiply", [left, right])


def test_native_decimal_differential_batch_without_reference_callbacks(monkeypatch):
    randomizer = random.Random(1337)
    rows = [[DecimalValue(randomizer.randint(INT_MIN, INT_MAX), randomizer.randrange(19)),
             DecimalValue(randomizer.randint(INT_MIN, INT_MAX), randomizer.randrange(19))]
            for _ in range(700)]
    reference, native = DomainRegistry("python"), DomainRegistry("native")
    from dlp_reasoner import domains
    expected = {op: reference.evaluate_batch(NUMERIC + op, rows) for op in
                ("add", "subtract", "multiply", "divide", "equal", "lessThan")}
    monkeypatch.setattr(domains, "_reference", lambda *_: pytest.fail("Python scalar callback"))
    for op, anticipated in expected.items():
        actual = native.evaluate_batch(NUMERIC + op, rows)
        assert [(r.error.code if r.error else None, r.value) for r in actual] == [
            (r.error.code if r.error else None, r.value) for r in anticipated]


def test_native_abi_checks_malformed_rows_and_missing_optional_capability(tmp_path, monkeypatch):
    import ctypes as c
    from dlp_reasoner.domain_native import _Value, _library, build_native_domains
    library = _library()
    invalid = (_Value * 2)(_Value(tag=5, a=2023, b=2, c=29), _Value(tag=5, a=2024, b=2, c=29))
    output, status = (_Value * 1)(), (c.c_int32 * 1)()
    assert library.dlp_domain_evaluate(1, invalid, 1, 2, output, status) == 0
    assert status[0] == 2
    assert library.dlp_domain_evaluate(1, None, 1, 2, output, status) == -1
    path = build_native_domains(cache_dir=tmp_path, geodesic=False)
    monkeypatch.setenv("DLP_DOMAIN_LIBRARY", str(path))
    native = DomainRegistry("native")
    assert native.evaluate(NUMERIC + "add", [1, 2]) == Literal(3)
    with pytest.raises(DomainError) as error:
        native.evaluate(SPATIAL + "wgs84Distance", [Point(0., 0.), Point(1., 0.)])
    assert error.value.code == "UNAVAILABLE"
