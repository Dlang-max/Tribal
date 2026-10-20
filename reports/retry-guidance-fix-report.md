# Retry guidance fix report

The worker regression was reproduced with the supplied negative guidance case. Before the fix, the test failed because `available_at` was already about 0.07 seconds in the past after receiving `Retry-After: -1` and `Retry-After-Ms: -100`.

`_retry_after` rejected the negative millisecond header, then parsed the negative seconds header and clamped it to zero. Since zero is valid guidance, the worker did not use its bounded exponential fallback. The parser now returns `None` for negative numeric `Retry-After` values, so the worker selects bounded backoff. Numeric zero remains valid, and past HTTP-date guidance still clamps to zero.

The regression test was brought into this branch from the tester-authored commit `801ecfb` without modifying its contents. The source change is committed separately as `6f2b193953f95fa1cc4f4bd66d50c6138fcdb48b` (`fix: reject negative retry-after guidance`).

Validation used the root `.venv`, the private MySQL test configuration, and `PYTHONPATH` set to this worktree's `src/` so the test process imports the code under test:

- Before fix: negative guidance regression failed with an observed delay of `-0.0673` seconds.
- After fix: `tests/test_worker_contract.py` and `tests/test_embeddings_contract.py` passed: 57 passed, 1 skipped.
- `git diff --check` passed before the source commit.
