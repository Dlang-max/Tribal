"""Independent embedding formatting, counting, vector and adapter contracts."""
from __future__ import annotations

import hashlib
import json
import math
import os
import struct
import subprocess
import sys

import pytest


def f32(value):
    return struct.unpack("<f", struct.pack("<f", value))[0]


@pytest.fixture
def api():
    import tribal.embeddings
    return tribal.embeddings


@pytest.mark.parametrize("title, headings, content", [
    ("Seed observations", ["Method", "Results"], "Exact source.\n"),
    ('界 "title"', ["🌱", "e\u0301"], "\n\n$$x=1$$\n"),
    ("a\nb", [], "without final newline"),
])
def test_document_wrapper_and_sha256_are_exact_utf8(api, title, headings, content):
    expected = "Title: " + title + "\nHeadings: " + json.dumps(headings, ensure_ascii=False, separators=(",", ":")) + "\n\n" + content
    wrapped = api.format_document_input(title, headings, content)
    assert wrapped == expected
    assert api.input_hash(wrapped) == hashlib.sha256(expected.encode("utf-8")).hexdigest()
    assert api.input_hash(wrapped + "\n") != api.input_hash(wrapped)


@pytest.mark.parametrize("text", ["", "plain source", "检索🌱e\u0301", "<|endoftext|> literal source", "a\n\nb"])
def test_complete_input_token_count_uses_pinned_encoding_and_literal_special_text(api, text):
    import tiktoken
    expected = len(tiktoken.get_encoding("cl100k_base").encode(text, disallowed_special=()))
    assert api.count_tokens(text) == expected


@pytest.mark.parametrize("values", [[3.0, 4.0], [1, 2, 3], [1e-300, -2e-300], [1e300, -2e300]])
def test_normalization_uses_float64_then_exact_float32_round_trip(api, values):
    expected = [f32(value / math.hypot(*values)) for value in values]
    actual = api.normalize_vector(values, dimensions=len(values))
    assert actual == expected
    assert all(isinstance(value, float) and math.isfinite(value) for value in actual)
    assert math.hypot(*actual) == pytest.approx(1.0, abs=1e-7)
    assert [f32(value) for value in actual] == actual


@pytest.mark.parametrize("values, dimensions", [([1, 2], 3), ([0, 0], 2),
    ([math.nan, 1], 2), ([math.inf, 1], 2), ([-math.inf, 1], 2), ([], 2)])
def test_invalid_vectors_raise_safe_structured_errors(api, values, dimensions):
    from tribal.errors import TribalError
    with pytest.raises(TribalError) as failure:
        api.normalize_vector(values, dimensions=dimensions)
    assert failure.value.code == "E_EMBEDDING_VECTOR"
    payload = failure.value.as_dict()
    assert payload["ok"] is False
    json.dumps(payload, allow_nan=False)


def test_deterministic_provider_is_repeatable_finite_and_dimensioned(api):
    first = api.DeterministicProvider().embed("source 🌱", model="test-model", dimensions=17)
    second = api.DeterministicProvider().embed("source 🌱", model="test-model", dimensions=17)
    assert first == second
    assert len(first) == 17
    assert all(math.isfinite(value) for value in first)
    assert math.hypot(*first) > 0


def test_openai_adapter_configures_timeout_retry_policy_and_exact_request():
    # A fresh interpreter permits patching the SDK boundary before importing the
    # adapter. No implementation globals or private client fields are assumed.
    script = '''
import json
from types import SimpleNamespace
import openai
captured = {}
class FakeOpenAI:
    def __init__(self, **kwargs):
        captured['constructor'] = kwargs
        self.embeddings = self
    def create(self, **kwargs):
        captured['request'] = kwargs
        return SimpleNamespace(data=[SimpleNamespace(embedding=[1.0, 2.0, 3.0])])
openai.OpenAI = FakeOpenAI
from tribal.embeddings import OpenAIProvider
result = OpenAIProvider(api_key='test-placeholder').embed('query original\\n', model='test-model', dimensions=3)
assert result == [1.0, 2.0, 3.0]
assert captured['constructor'] == {'api_key': 'test-placeholder', 'timeout': 30.0, 'max_retries': 0}
assert captured['request'] == {'model': 'test-model', 'input': 'query original\\n', 'dimensions': 3, 'encoding_format': 'float'}
print('adapter configuration verified')
'''
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True,
                            env=os.environ.copy(), timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == "adapter configuration verified"


@pytest.mark.live_openai
def test_opt_in_real_openai_embedding_smoke(live_openai_enabled):
    from tribal.embeddings import OpenAIProvider, normalize_vector
    vector = OpenAIProvider().embed("Tribal credentialed smoke: seed observation.",
                                    model="text-embedding-3-small", dimensions=1536)
    assert len(vector) == 1536
    normalized = normalize_vector(vector, dimensions=1536)
    assert math.hypot(*normalized) == pytest.approx(1.0, abs=1e-6)
