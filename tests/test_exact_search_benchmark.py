"""Opt-in measurement of the complete eligible database search path."""
import os

import pytest


@pytest.mark.mysql
@pytest.mark.benchmark
def test_full_path_exact_search_benchmark(mysql_config, record_testsuite_property):
    if os.environ.get("TRIBAL_TEST_BENCHMARK") != "1":
        pytest.skip("benchmark is opt-in: set TRIBAL_TEST_BENCHMARK=1")
    from benchmark_exact_search import run_benchmark
    result = run_benchmark(mysql_config, documents=1000, trials=3)
    assert result["complete"] is True
    assert result["dimensions"] == 1536
    assert result["materialized_results_per_session"] == result["eligible_vectors"] == 1000
    record_testsuite_property("exact_search_benchmark", result)
