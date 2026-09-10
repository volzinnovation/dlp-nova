"""Resident native value IDs, bounded reclamation, and measured warm transfers."""
import math
from pathlib import Path
import random
import shutil
import subprocess

import pytest

from dlp_reasoner.domain_native import NativeDomainContext
from dlp_reasoner.domains import DecimalValue, DomainError, DomainRegistry, FloatValue, IntegerValue, DateValue, InstantValue, Quantity


def test_warm_registry_transfers_only_ids_and_reuses_output_payloads():
    with DomainRegistry(backend="native") as registry:
        rows = [(IntegerValue(i), IntegerValue(i + 1)) for i in range(100)]
        first = registry.evaluate_batch("urn:dlp:numeric:add", rows)
        cold = registry.native_stats()
        second = registry.evaluate_batch("urn:dlp:numeric:add", rows)
        warm = registry.native_stats()
        assert first == second and all(result.ok for result in first)
        assert warm["evaluated_rows"] == cold["evaluated_rows"] + 100
        assert cold["transferred_inputs"] == 101
        assert warm["transferred_inputs"] == cold["transferred_inputs"]
        assert warm["transferred_outputs"] == cold["transferred_outputs"]
        assert warm["retained_values"] == cold["retained_values"]
        assert warm["clears"] == 0


def test_id_only_evaluation_exports_values_only_when_requested():
    with NativeDomainContext() as context:
        a, b = context.intern([IntegerValue(2), IntegerValue(3)])
        ((result_id, status),) = context.evaluate_ids(20, [(a, b)])
        assert status == 0
        assert context.stats()["transferred_outputs"] == 0
        assert context.get([result_id]) == (IntegerValue(5),)
        assert context.stats()["transferred_outputs"] == 1
        assert context.get([result_id]) == (IntegerValue(5),)
        assert context.stats()["transferred_outputs"] == 1
        # Native result IDs can feed another operation with no Python decoding.
        ((next_id, status),) = context.evaluate_ids(20, [(result_id, a)])
        assert status == 0 and context.get([next_id]) == (IntegerValue(7),)


def test_clear_invalidates_ids_without_reusing_numbers():
    with NativeDomainContext() as context:
        (old,) = context.intern([IntegerValue(2)])
        generation = context.stats()["generation"]
        context.clear()
        (new,) = context.intern([IntegerValue(2)])
        assert new != old and context.stats()["generation"] > generation
        with pytest.raises(DomainError) as error:
            context.get([old])
        assert error.value.code == "TYPE_ERROR"
        assert context.evaluate_ids(20, [(new, old), (new, new)])[0] == (0, 1)


def test_capacity_reclaims_only_between_batches_without_truncating_results():
    with DomainRegistry(backend="native", native_value_capacity=4) as registry:
        rows = [(IntegerValue(i), IntegerValue(1)) for i in range(130)]
        results = registry.evaluate_batch("urn:dlp:numeric:add", rows)
        assert [result.value.toPython() for result in results] == list(range(1, 131))
        stats = registry.native_stats()
        assert stats["retained_values"] <= 4
        assert stats["clears"] > 0
        assert stats["evaluated_rows"] == 130


def test_capacity_failure_keeps_prior_ids_usable():
    with NativeDomainContext(capacity=4) as context:
        ids = context.intern([IntegerValue(i) for i in (1, 2, 3, 4)])
        with pytest.raises(DomainError) as error:
            context.evaluate_ids(20, [(ids[2], ids[3])])
        assert error.value.code == "RESOURCE_LIMIT"
        assert context.get(ids) == tuple(IntegerValue(i) for i in (1, 2, 3, 4))
        assert context.stats()["retained_values"] == 4


def test_signed_zero_identity_survives_resident_cache():
    with DomainRegistry(backend="native") as registry:
        negative = registry.evaluate("urn:dlp:numeric:toFloat", [FloatValue(-0.0)])
        positive = registry.evaluate("urn:dlp:numeric:toFloat", [FloatValue(0.0)])
        assert math.copysign(1, negative.toPython()) == -1
        assert math.copysign(1, positive.toPython()) == 1


def test_portable_decimal_to_float_matches_exact_reference():
    randomizer = random.Random(521)
    rows = [(DecimalValue(randomizer.randrange(-(2**63), 2**63), randomizer.randrange(19)),)
            for _ in range(2000)]
    with DomainRegistry("python") as python, DomainRegistry("native") as native:
        expected = python.evaluate_batch("urn:dlp:numeric:toFloat", rows)
        actual = native.evaluate_batch("urn:dlp:numeric:toFloat", rows)
        assert actual == expected


def test_resident_context_close_rejects_use():
    context = NativeDomainContext()
    context.close()
    context.close()
    with pytest.raises(DomainError, match="closed"):
        context.intern([IntegerValue(1)])
    registry = DomainRegistry("native")
    registry.close()
    with pytest.raises(DomainError, match="closed"):
        registry.evaluate("urn:dlp:numeric:add", [1, 2])


def test_resident_domain_abi_sanitizer_driver(tmp_path):
    compiler = shutil.which("clang++") or shutil.which("g++")
    assert compiler
    source = Path(__file__).resolve().parents[1] / "src" / "dlp_reasoner"
    driver = tmp_path / "driver.cpp"
    driver.write_text(r'''
#include "native_domains.h"
#include <cassert>
int main() {
 dlp_domain_context *ctx=nullptr;
 assert(dlp_domain_context_new(4,&ctx)==0);
 dlp_domain_value values[2]{}; values[0].tag=values[1].tag=2;
 values[0].a=2;values[1].a=3;
 uint64_t ids[2]{};assert(dlp_domain_context_intern(ctx,values,2,ids)==0);
 uint64_t result=0;int32_t status=0;
 assert(dlp_domain_context_evaluate(ctx,20,ids,1,2,&result,&status)==0&&status==0);
 dlp_domain_context_stats stats{};assert(dlp_domain_context_get_stats(ctx,&stats)==0);
 assert(stats.retained_values==3&&stats.transferred_inputs==2&&stats.transferred_outputs==0);
 dlp_domain_value value{};assert(dlp_domain_context_get(ctx,&result,1,&value,&status)==0);
 assert(status==0&&value.tag==2&&value.a==5);
 assert(dlp_domain_context_clear(ctx)==0);
 assert(dlp_domain_context_get(ctx,&result,1,&value,&status)==0&&status==1);
 assert(dlp_domain_context_evaluate(ctx,20,ids,1,2,&result,&status)==0&&status==1);
 assert(dlp_domain_context_intern(ctx,values,2,ids)==0);
 assert(dlp_domain_context_evaluate(ctx,999,ids,1,2,&result,&status)==0&&status==5);
 dlp_domain_context_free(ctx);
}
''')
    executable = tmp_path / "driver"
    subprocess.run([compiler, "-std=c++17", "-fsanitize=address,undefined", "-fno-omit-frame-pointer",
                    "-I", str(source), str(driver), str(source / "native_domains.cpp"),
                    "-o", str(executable)], check=True, capture_output=True, text=True, timeout=120)
    subprocess.run([str(executable)], check=True, capture_output=True, text=True, timeout=30)


def test_resident_comparator_preserves_domain_boundaries_and_exact_order():
    with NativeDomainContext() as context:
        values = [IntegerValue(1), DecimalValue(10, 1), DecimalValue(11, 1),
                  DateValue(2000, 1, 1), DateValue(2001, 1, 1), InstantValue(0),
                  Quantity(IntegerValue(1), "urn:dlp:unit:metre"),
                  Quantity(DecimalValue(20, 1), "urn:dlp:unit:metre"),
                  Quantity(IntegerValue(1), "urn:dlp:unit:second")]
        ids = context.intern(values)
        assert context.compare(ids[0], ids[1]) == 0
        assert context.compare(ids[0], ids[2]) == -1
        assert context.compare(ids[3], ids[4]) == -1
        assert context.compare(ids[7], ids[6]) == 1
        for left, right in ((3, 5), (6, 8), (0, 3)):
            with pytest.raises(DomainError) as error:
                context.compare(ids[left], ids[right])
            assert error.value.code == "TYPE_ERROR"
