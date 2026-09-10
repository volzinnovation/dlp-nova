"""The worked stream fixture executes rules rather than reference calculations."""
import importlib.util
from pathlib import Path

import pytest

from dlp_reasoner.providers import ProviderError, Status


path = Path(__file__).resolve().parents[1] / "examples/temporal_geo/run_queries.py"
spec = importlib.util.spec_from_file_location("event_query_example", path)
example = importlib.util.module_from_spec(spec)
spec.loader.exec_module(example)


@pytest.mark.parametrize("backend", ["python", "native"])
def test_temporal_geospatial_rules_correct_expire_and_recover(backend):
    try:
        report = example.run(backend)
    except ProviderError as exc:
        if exc.status is Status.UNAVAILABLE:
            pytest.skip(f"Optional GEOS C library unavailable: {exc}")
        raise
    assert report["production_temporal_spatial_rules_executed"]
    assert report["idle_expiration_verified"]
    assert report["checkpoint_recovery_verified"]


@pytest.mark.parametrize("backend", ["python", "native"])
def test_bitemporal_history_executes_with_both_time_axes(backend):
    report = example.run_history(backend)
    assert [case["result"] for case in report["cases"]] == [[50], [30], []]
    assert report["execution"]["execution_mode"] == backend
