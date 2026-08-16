from bootstrap import ensure_repo_root

ensure_repo_root()

from chunking.chunk_model import CodeChunk

from evaluation.golden_set import GoldenItem
from evaluation import metrics, llm_judge

def mk_chunk(i, file, start, end, symbol="fn"):
    return CodeChunk(
        chunk_id=f"id-{i}",
        repo_url="https://example.com/r",
        file_path=file,
        absolute_path="/x/" + file,
        extension=".py",
        chunk_source="ast",
        language="python",
        symbol=symbol,
        node_type="function_definition",
        start_line=start,
        end_line=end,
        content=f"def {symbol}(...):",
        repo_hash="abc123",
        qualified_name=symbol,
    )


def mk_item(qid="item-1", file="src/app.py", start=10, end=40):
    return GoldenItem(
        id=qid,
        query="How is auth handled?",
        repo_hash="abc123",
        file_path=file,
        start_line=start,
        end_line=end,
        symbol="Auth",
        qualified_name="Auth",
        language="python",
    )


# --- chunk_relevant overlap logic ---
item = mk_item()
assert metrics.chunk_relevant(mk_chunk(1, "src/app.py", 10, 40), item)      # exact
assert metrics.chunk_relevant(mk_chunk(2, "src/app.py", 20, 30), item)      # inside
assert metrics.chunk_relevant(mk_chunk(3, "src/app.py", 5, 15), item)       # real overlap (10-15)
assert not metrics.chunk_relevant(mk_chunk(4, "src/app.py", 41, 50), item)  # below span
assert not metrics.chunk_relevant(mk_chunk(5, "src/app.py", 1, 9), item)    # above span
assert not metrics.chunk_relevant(mk_chunk(6, "src/other.py", 10, 40), item)  # different file
assert not metrics.chunk_relevant(mk_chunk(7, "src/app.py", 1, 10), item)   # boundary touch (shares line 10 only)
assert not metrics.chunk_relevant(mk_chunk(8, "src/app.py", 40, 60), item)  # boundary touch (shares line 40 only)

# --- relevant_in_collection + compute_item_retrieval ---
collection = [mk_chunk(i, "src/app.py", 10 + 8 * i, 10 + 8 * i + 7) for i in range(4)]
# spans: 10-17, 18-25, 26-33, 34-41 -> overlap with 10-40: first three fully, fourth partial (34-40)
assert metrics.relevant_in_collection(collection, item) == 4

# retrieved: two relevant chunks + one irrelevant
retrieved = [
    {"chunk": collection[0]},
    {"chunk": collection[1]},
    {"chunk": mk_chunk(9, "src/other.py", 1, 5)},
]
r = metrics.compute_item_retrieval(retrieved, item, collection, k=8, setup="S2")
assert r.setup == "S2"
assert r.relevant_retrieved == 2
assert r.retrieved_count == 3
assert abs(r.context_recall - 2 / 4) < 1e-9
assert abs(r.context_precision - 2 / 3) < 1e-9
assert r.recall_at_k == 1.0

# Recall@K: relevant chunk outside top-K -> miss
retrieved_k1 = [
    {"chunk": mk_chunk(9, "src/other.py", 1, 5)},
    {"chunk": collection[0]},
]
r = metrics.compute_item_retrieval(retrieved_k1, item, collection, k=1, setup="S1")
assert r.recall_at_k == 0.0
r = metrics.compute_item_retrieval(retrieved_k1, item, collection, k=2, setup="S1")
assert r.recall_at_k == 1.0

# empty retrieved -> precision 0
r = metrics.compute_item_retrieval([], item, collection, k=8, setup="S4")
assert r.context_precision == 0.0 and r.recall_at_k == 0.0

# --- aggregate_retrieval ---
a = metrics.aggregate_retrieval([r, r])
assert abs(a["context_recall"] - r.context_recall) < 1e-9
assert a["context_recall_std"] == 0.0
assert metrics.aggregate_retrieval([]) == {
    "context_recall": 0.0, "context_precision": 0.0, "mrr": 0.0, "recall_at_k": 0.0,
    "context_recall_std": 0.0, "context_precision_std": 0.0, "mrr_std": 0.0, "recall_at_k_std": 0.0,
}
mixed = metrics.aggregate_retrieval([
    metrics.ItemMetricResult("i1", "S4", 1.0, 1.0, 1.0, 1.0, 8, 8, 8),
    metrics.ItemMetricResult("i2", "S4", 0.0, 0.0, 0.0, 0.0, 8, 0, 8),
])
assert abs(mixed["context_recall"] - 0.5) < 1e-9
assert mixed["context_recall_std"] > 0

# --- MRR (mean reciprocal rank of first relevant chunk) ---
# first relevant at rank 1 -> 1.0; rank 3 -> 1/3; absent -> 0
assert metrics.reciprocal_rank(
    [{"chunk": collection[0]}, {"chunk": collection[1]}], item
) == 1.0
assert metrics.reciprocal_rank(
    [
        {"chunk": mk_chunk(9, "src/other.py", 1, 5)},
        {"chunk": mk_chunk(10, "src/other.py", 2, 6)},
        {"chunk": collection[0]},
    ],
    item,
) == 1 / 3
assert metrics.reciprocal_rank(
    [{"chunk": mk_chunk(9, "src/other.py", 1, 5)}], item
) == 0.0
mrr_res = metrics.compute_item_retrieval(
    [{"chunk": collection[1]}, {"chunk": collection[0]}], item, collection, k=8, setup="S4"
)
assert abs(mrr_res.mrr - 1.0) < 1e-9  # first relevant chunk at rank 1
mrr_res = metrics.compute_item_retrieval(
    [{"chunk": mk_chunk(9, "src/other.py", 1, 5)}, {"chunk": collection[0]}],
    item, collection, k=8, setup="S4",
)
assert abs(mrr_res.mrr - 0.5) < 1e-9  # first relevant chunk at rank 2
print("OK MRR: rank-1 -> 1.0, rank-3 -> 1/3, absent -> 0")

# --- judge prompts (pure, no LLM) ---
q, a = "How is auth handled?", "It uses middleware. [C1]"
ctx = ["def middleware(): ...", "class Auth: ..."]
msgs = llm_judge.faithfulness_prompt(q, a, ctx)
assert msgs[0]["role"] == "system" and "supported" in msgs[0]["content"].lower()
assert msgs[1]["role"] == "user" and q in msgs[1]["content"] and a in msgs[1]["content"]
assert "def middleware" in msgs[1]["content"]
msgs = llm_judge.answer_relevance_prompt(q, a)
assert msgs[0]["role"] == "system" and "addresses the question" in msgs[0]["content"].lower()
assert q in msgs[1]["content"] and a in msgs[1]["content"]

# --- parse_score ---
assert llm_judge.parse_score("0.85") == 0.85
assert llm_judge.parse_score("1.0") == 1.0
assert llm_judge.parse_score("Score: 0") == 0.0
assert llm_judge.parse_score(".5") == 0.5
assert llm_judge.parse_score("unsupported") is None
assert llm_judge.parse_score("") is None
assert llm_judge.parse_score("2.5") == 1.0  # clamped
assert llm_judge.parse_score("-0.2") == 0.0  # clamped


# --- Judge with a fake LLM (no API) ---
class FakeLLM:
    def __init__(self, text): self.text = text
    def generate(self, messages): return type("R", (), {"text": self.text})()

judge = llm_judge.Judge(FakeLLM("0.9"))
assert judge.faithfulness(q, a, ctx) == 0.9
assert judge.answer_relevance(q, a) == 0.9

class BrokenLLM:
    def generate(self, messages): raise RuntimeError("boom")

judge = llm_judge.Judge(BrokenLLM())
assert judge.faithfulness(q, a, ctx) is None  # failure -> None, no raise

print("OK chunk_relevant overlap + file scoping")
print("OK relevant_in_collection + compute_item_retrieval (recall/precision/R@K)")
print("OK aggregate_retrieval")
print("OK judge prompts + parse_score + Judge wrapper (fake LLM, failure->None)")

# --------------------------------------------------------------------------- #
# Rerank fallback (production RetrievalPipeline)
# --------------------------------------------------------------------------- #
from rag.types import HybridCandidate, HybridRetrievalResult
from retrieval.retrieval_pipeline import RetrievalPipeline


def mk_chunk2(i, file, source="ast"):
    return CodeChunk(
        chunk_id=f"id-{i}", repo_url="https://x/r", file_path=file,
        absolute_path="/x/" + file, extension=".py", chunk_source=source,
        language="python", symbol=f"fn{i}", node_type="function_definition",
        start_line=i * 10, end_line=i * 10 + 4, content=f"def fn{i}(): pass",
        repo_hash="abc", qualified_name=f"fn{i}",
    )


class _FakeEmbedder:
    def __init__(self): self.embedding_dim = 768
    def embed_query(self, q): return [0.1] * 768


class _FakeHybrid:
    def __init__(self, chunks): self.chunks = chunks
    def retrieve(self, query, query_vector, repo_hash=None):
        cands = [
            HybridCandidate(chunk=ch, rrf_score=float(100 - i), vector_score=float(100 - i), bm25_score=float(i))
            for i, ch in enumerate(self.chunks)
        ]
        return HybridRetrievalResult(candidates=cands, vector_count=5, bm25_count=5)


class _RaiseReranker:
    def rerank(self, *a, **k): raise RuntimeError("reranker down")


class _OkReranker:
    def rerank(self, query, candidates, top_k=10):
        return [
            {"chunk": c.chunk, "score": float(100 - i), "rrf_score": float(c.rrf_score),
             "vector_score": c.vector_score, "bm25_score": c.bm25_score}
            for i, c in enumerate(reversed(candidates))
        ][:top_k]


chunks5 = [mk_chunk2(i, f"src/mod{i}.py") for i in range(5)]

pipe = RetrievalPipeline(final_top_k=3)
pipe.query_embedder = _FakeEmbedder()
pipe.hybrid_retriever = _FakeHybrid(chunks5)
pipe.reranker = _RaiseReranker()
res = pipe.retrieve("how does auth work?", "abc")
assert len(res) == 3
assert all(x["reranked"] is False for x in res)
assert all(set(k) >= {"chunk", "score", "rrf_score", "vector_score", "bm25_score"} for k in res)
assert res == sorted(res, key=lambda x: x["score"], reverse=True)

pipe.reranker = _OkReranker()
res = pipe.retrieve("how does auth work?", "abc")
assert len(res) == 3
assert all(x["reranked"] is True for x in res)

# candidate -> result conversion keeps adjusted_score as ranking score
from rag.types import HybridCandidate as HC
cd = HC(chunk=mk_chunk2(1, "src/a.py"), rrf_score=0.5, adjusted_score=0.7, vector_score=0.8, bm25_score=2.0)
d = RetrievalPipeline._candidate_to_result(cd)
assert d["score"] == 0.7 and d["rrf_score"] == 0.5 and d["vector_score"] == 0.8

print("OK rerank fallback: raising reranker -> S3-shaped results with reranked=False; success -> reranked=True")

# --------------------------------------------------------------------------- #
# Eval pipelines S4 mirrors the fallback
# --------------------------------------------------------------------------- #
from evaluation.pipelines import EvalPipelines

pipe = EvalPipelines("naive", "ast", final_top_k=3, embedder=_FakeEmbedder())
pipe.hybrid = _FakeHybrid(chunks5)
pipe.reranker = _RaiseReranker()
res = pipe.retrieve("S4", "how does auth work?", "abc")
assert len(res) == 3 and all(x["reranked"] is False for x in res)
pipe.reranker = _OkReranker()
res = pipe.retrieve("S4", "how does auth work?", "abc")
assert len(res) == 3 and all(x["reranked"] is True for x in res)

print("OK eval pipelines S4 mirrors rerank fallback")

# --------------------------------------------------------------------------- #
# ContextBuilder policy knobs
# --------------------------------------------------------------------------- #
from rag.context_builder import ContextBuilder


def mkd(i, file, score):
    return {"chunk": mk_chunk2(i, file), "score": score}


# baseline: no filtering
cb = ContextBuilder(max_chunks=8, min_score_ratio=0.0, min_score=0.0, max_per_file=0)
ctx = cb.build([mkd(0, "a.py", 0.9), mkd(1, "a.py", 0.1), mkd(2, "b.py", 0.2)])
assert len(ctx.chunks) == 3

# min_score absolute floor
cb = ContextBuilder(max_chunks=8, min_score=0.5, min_score_ratio=0.0, max_per_file=0)
ctx = cb.build([mkd(0, "a.py", 0.9), mkd(1, "a.py", 0.1), mkd(2, "b.py", 0.2)])
assert {c.chunk.symbol for c in ctx.chunks} == {"fn0"}

# min_score_ratio relative floor (keep >= 40% of top 0.9 => >= 0.36)
cb = ContextBuilder(max_chunks=8, min_score=0.0, min_score_ratio=0.4, max_per_file=0)
ctx = cb.build([mkd(0, "a.py", 0.9), mkd(1, "a.py", 0.1), mkd(2, "b.py", 0.5)])
assert {c.chunk.symbol for c in ctx.chunks} == {"fn0", "fn2"}

# max_per_file cap keeps highest-scored per file
cb = ContextBuilder(max_chunks=8, min_score=0.0, min_score_ratio=0.0, max_per_file=1)
ctx = cb.build([mkd(0, "a.py", 0.9), mkd(1, "a.py", 0.8), mkd(2, "b.py", 0.7)])
assert len(ctx.chunks) == 2
assert [c.chunk.symbol for c in ctx.chunks] == ["fn0", "fn2"]  # one per file, top-scored

# top chunk always kept even if a brutal floor would empty the list
cb = ContextBuilder(max_chunks=8, min_score=0.99, min_score_ratio=0.0, max_per_file=0)
ctx = cb.build([mkd(0, "a.py", 0.9), mkd(1, "a.py", 0.1)])
assert len(ctx.chunks) == 1 and ctx.chunks[0].chunk.symbol == "fn0"

print("OK ContextBuilder policy: min_score, min_score_ratio, max_per_file, top-kept guard")

# --------------------------------------------------------------------------- #
# Judge sanity_check + golden-set leakage filter
# --------------------------------------------------------------------------- #
from evaluation.golden_set import GoldenEntity, build_golden_set, query_leaks_symbol


class _DiscriminatingLLM:
    def generate(self, messages):
        text = messages[-1]["content"]
        from rag.types import LLMResponse
        score = "0.1" if "Mars" in text else "0.9"
        return LLMResponse(text=score, model="fake", raw={})

judge = llm_judge.Judge(_DiscriminatingLLM())
sanity = judge.sanity_check()
for name, r in sanity.items():
    assert r["pass"] is True, (name, r)
    assert r["good"] == 0.9 and r["bad"] == 0.1
print("OK Judge.sanity_check: discriminates good vs bad (pass=True)")

class _NonDiscriminatingLLM:
    def generate(self, messages):
        from rag.types import LLMResponse
        return LLMResponse(text="0.9", model="fake", raw={})

sanity = llm_judge.Judge(_NonDiscriminatingLLM()).sanity_check()
assert all(r["pass"] is False for r in sanity.values())
print("OK Judge.sanity_check: catches a non-discriminating judge (pass=False)")

ent = GoldenEntity("abc", "src/app.py", 10, 40, "AuthenticateUser", "AuthenticateUser", "python", "def AuthenticateUser(): pass")
assert query_leaks_symbol("How is AuthenticateUser implemented?", ent)
assert query_leaks_symbol("How does authenticateUser verify users?", ent)  # camelCase lowercased
assert query_leaks_symbol("How does authentication verify a token?", ent) is False  # behavior, not symbol
assert query_leaks_symbol("What does the login flow do?", ent) is False
short = GoldenEntity("abc", "src/app.py", 10, 40, "id", "id", "python", "def id(): pass")
assert query_leaks_symbol("how is the id stored?", short) is False  # short symbols ignored

class _LeakyLLM:
    def __init__(self):
        self.calls = 0
    def generate(self, messages):
        self.calls += 1
        from rag.types import LLMResponse
        force = "never appears" in messages[0]["content"]
        text = "How does login check the password?" if force else "How does AuthenticateUser verify a user?"
        return LLMResponse(text=text, model="fake", raw={})

leaky = _LeakyLLM()
items = build_golden_set([ent], leaky, id_prefix="r", max_retries=1)
assert leaky.calls == 2          # leaked once, forced rewrite once
assert items == []               # still leaked after rewrite -> dropped
print("OK golden-set leakage: short-symbol exemption, retry-then-drop")

class _CleanLLM:
    def generate(self, messages):
        from rag.types import LLMResponse
        return LLMResponse(text="How does the app verify a user's password?", model="fake", raw={})

items = build_golden_set([ent], _CleanLLM(), id_prefix="r", max_retries=1)
assert len(items) == 1 and items[0].query == "How does the app verify a user's password?"
assert items[0].id == "r-1"
print("OK build_golden_set: clean query kept with re-numbered ids")

# --------------------------------------------------------------------------- #
# VectorIndexer batched upsert (Qdrant 32MB payload cap)
# --------------------------------------------------------------------------- #
from qdrant_client.models import PointStruct
from vector_store.indexer import _batch_points

small = [PointStruct(id=str(i), vector={"text_dense": [0.1] * 4}, payload={"content": "x" * 10}) for i in range(1200)]
batches = list(_batch_points(small))
assert all(len(b) <= 500 for b in batches)
assert sum(len(b) for b in batches) == 1200
assert [p.id for b in batches for p in b] == [str(i) for i in range(1200)]  # exact, no loss/dup

big = [PointStruct(id=str(i), vector={"text_dense": [0.1] * 4}, payload={"content": "x" * (5 * 1024 * 1024)}) for i in range(3)]
batches = list(_batch_points(big))
assert sum(len(b) for b in batches) == 3
assert all(len(b) == 1 for b in batches)  # two ~5MB points would exceed the ~8MB target

# a single point larger than the cap is still emitted alone (never dropped)
huge = [PointStruct(id="0", vector={"text_dense": [0.1] * 4}, payload={"content": "x" * (12 * 1024 * 1024)})]
assert [p.id for b in _batch_points(huge) for p in b] == ["0"]

print("OK VectorIndexer batch upsert: point-count + payload-size caps, no loss/dup")
