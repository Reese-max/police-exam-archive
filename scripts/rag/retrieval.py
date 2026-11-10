"""Shared local retrieval: SQLite trigram BM25, normalized vectors and RRF."""

import json
import math
import os
import re
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path
import sqlite3

if __package__:
    from .build_corpus import json_text, normalize_text
    from .model_identity import REBUILD_MESSAGE, model_identity, require_matching_identity, valid_identity
else:
    from build_corpus import json_text, normalize_text
    from model_identity import REBUILD_MESSAGE, model_identity, require_matching_identity, valid_identity


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MODEL = "intfloat/multilingual-e5-small"
SCHEMA_VERSION = 2
LEGACY_EMBEDDING_TEXT_VERSION = 1
EMBEDDING_TEXT_VERSION = 2
LEGACY_INDEX_WARNING = "索引使用舊版向量輸入規則，尚未遷移；答案歧異可能影響向量檢索結果。"
# Provisional until bench.py selects parameters on the semantic development split.
DEFAULT_KEYWORD_WEIGHT = 2.0
DEFAULT_VECTOR_WEIGHT = 1.0


def model_prefix(model, query=False):
    return ("query: " if query else "passage: ") if "e5" in model.lower() else ""


def embedding_texts_v1(doc):
    """Original schema-v2 input, retained to identify vectors needing migration."""
    options = doc.get("options", {})
    subjects = sorted({item["subject"] for item in doc.get("appears_in", []) if item.get("subject")})
    main = "\n".join(filter(None, [doc.get("stem", ""),
        *(f"({key}){value}" for key, value in sorted(options.items())),
        ("正確選項：" + options[doc["answer"]]) if doc.get("answer") in options else "",
        "／".join(subjects)]))
    return [normalize_text(main)] + ([normalize_text(doc["passage"])] if doc.get("passage", "").strip() else [])


def embedding_texts(doc):
    """Keep all options, but do not label a disputed answer as correct."""
    if doc.get("answer_conflicts"):
        return embedding_texts_v1({**doc, "answer": None})
    return embedding_texts_v1(doc)


def embedding_text_version(meta):
    """An unversioned schema-v2 index predates the current input rule."""
    version = meta.get("embedding_text_version", LEGACY_EMBEDDING_TEXT_VERSION)
    if type(version) is not int or version not in (LEGACY_EMBEDDING_TEXT_VERSION, EMBEDDING_TEXT_VERSION):
        raise ValueError(f"不支援的向量輸入規則版本：{version!r}")
    return version


def pending_vector_questions(meta):
    """Validate component-level work left by a non-embedding build."""
    pending = meta.get("pending_question_vectors", {})
    if not isinstance(pending, dict) or any(
            not isinstance(identifier, str) or not identifier or not isinstance(parts, list)
            or any(part not in ("main", "passage") for part in parts)
            for identifier, parts in pending.items()):
        raise ValueError("向量索引待補建狀態無效")
    return {identifier: set(parts) for identifier, parts in pending.items() if parts}


def chunk_text(embedder, text, prefix):
    """Token-budgeted chunks: no stem token can disappear behind a long passage."""
    tokenizer = getattr(embedder, "tokenizer", None)
    maximum = getattr(embedder, "max_seq_length", None)
    if tokenizer is None or not maximum:
        return [text]  # Fake encoders have no tokenizer or truncation.
    tokens = tokenizer.encode(text, add_special_tokens=False)
    budget = maximum - len(tokenizer.encode(prefix, add_special_tokens=False)) - tokenizer.num_special_tokens_to_add(False) - 8
    if budget <= 0:
        raise ValueError("Tokenizer has no document token budget")
    if len(tokens) <= budget:
        return [text]
    # Re-tokenization can grow decoded fragments; recursively split until safe.
    chunks = []
    def append(part):
        decoded = tokenizer.decode(part, skip_special_tokens=True)
        if len(tokenizer.encode(prefix + decoded, add_special_tokens=True)) > maximum:
            if len(part) <= 1:
                raise ValueError("Tokenizer cannot fit a single token")
            middle = len(part) // 2
            append(part[:middle])
            append(part[middle:])
        else:
            chunks.append(decoded)
    for start in range(0, len(tokens), budget):
        append(tokens[start:start + budget])
    return chunks


@lru_cache(maxsize=1)
def load_abbreviations():
    return json.loads((ROOT / "rag/abbreviations.json").read_text(encoding="utf-8"))


def expand_query(query, abbreviations=None):
    """One longest-first, nonrecursive substitution; always retain the original."""
    aliases = load_abbreviations() if abbreviations is None else abbreviations
    if not aliases:
        return [query]
    pattern = "|".join(re.escape(key) for key in sorted(aliases, key=lambda key: (-len(key), key)))
    expanded = re.sub(pattern, lambda match: aliases[match.group()], query)
    return list(dict.fromkeys([query, expanded]))


def add_search_arguments(parser):
    import argparse
    parser.add_argument("--keyword-weight", type=float, default=DEFAULT_KEYWORD_WEIGHT)
    parser.add_argument("--vector-weight", type=float, default=DEFAULT_VECTOR_WEIGHT)
    parser.add_argument("--rrf-k", type=int, default=60)
    parser.add_argument("--candidates", type=int, default=50)
    parser.add_argument("--min-vector-score", type=float, default=None)
    parser.add_argument("--law-min-vector-score", type=float, default=None)
    parser.add_argument("--phrase-priority", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--expand-abbreviations", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--profile", type=Path, help="Use bench_report.json selected_default; explicit flags override it")


def parse_search_args(parser, argv=None):
    args = parser.parse_args(argv)
    if args.profile:
        report = json.loads(args.profile.read_text(encoding="utf-8"))
        selected = report.get("selected_default")
        if report.get("status") != "measured" or report.get("device") != "cpu" or not selected:
            raise ValueError("Benchmark 尚未選出通過 CPU 門檻的預設組合")
        config = selected["configuration"]
        defaults = {key: value for key, value in config.items() if key not in ("name", "use_reranker")}
        parser.set_defaults(**defaults, db=Path(selected["db"].replace("\\", "/")))
        args = parser.parse_args(argv)
        args.use_reranker = bool(config.get("use_reranker"))
    return args


def search_arguments(args):
    return {key: getattr(args, key) for key in ("keyword_weight", "vector_weight", "rrf_k",
            "candidates", "phrase_priority", "expand_abbreviations", "min_vector_score")}


def configure_model_cache():
    cache = Path(os.environ.get("RAG_MODEL_CACHE", ROOT / ".hf_cache"))
    for name, suffix in (("HF_HOME", ""), ("HF_HUB_CACHE", "hub"),
                         ("HUGGINGFACE_HUB_CACHE", "hub"), ("TRANSFORMERS_CACHE", "transformers"),
                         ("SENTENCE_TRANSFORMERS_HOME", "sentence_transformers")):
        os.environ[name] = str(cache / suffix)
    os.environ["HF_ENDPOINT"] = "https://huggingface.co"
    os.environ["HF_HUB_DISABLE_IMPLICIT_TOKEN"] = "1"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    return cache


def load_reranker(device="cpu"):
    cache = configure_model_cache()
    try:
        from sentence_transformers import CrossEncoder
    except ImportError as exc:
        raise RuntimeError("重排需要 sentence-transformers；未安裝，不會自動安裝") from exc
    return CrossEncoder("BAAI/bge-reranker-v2-m3", device=None if device == "auto" else device,
                        cache_folder=str(cache / "hub"), trust_remote_code=False,
                        model_kwargs={"token": False}, tokenizer_kwargs={"token": False})


def validate_model_revision(model, revision):
    """A Hub commit is a locator, not a proof of the loaded model content."""
    if (not isinstance(revision, str) or not re.fullmatch(r"[0-9a-f]{40}", revision)
            or Path(model).is_dir()):
        raise ValueError("模型 revision 無效；必須是 Hub 模型的完整 commit")
    return revision


def resolve_model_revision(model, *, cache=None):
    """Resolve main once before loading any module; local paths have no Hub revision."""
    if Path(model).is_dir():
        return None
    cache = configure_model_cache() if cache is None else Path(cache)
    try:
        from huggingface_hub import hf_hub_download
        filename = Path(hf_hub_download(model, "modules.json", revision="main",
                                        cache_dir=str(cache / "hub"), token=False))
    except Exception as exc:
        raise RuntimeError("無法解析 Hub 模型的完整 revision；請檢查連線或離線快取") from exc
    snapshot = filename.parent
    expected_repo = "models--" + model.replace("/", "--")
    if (filename.name != "modules.json" or snapshot.parent.name != "snapshots"
            or snapshot.parent.parent.name != expected_repo
            or snapshot.parent.parent.parent.absolute() != (cache / "hub").absolute()):
        raise ValueError("無法解析 Hub 模型的完整 revision")
    return validate_model_revision(model, snapshot.name)


def load_embedder(model, device="auto", *, revision=None):
    # Keep model/tokenizer caches inside this worktree, including on Spaces.
    cache = configure_model_cache()
    try:
        from sentence_transformers import SentenceTransformer
        import torch
    except ImportError as exc:
        raise RuntimeError(
            "向量檢索需要 sentence-transformers；目前環境未提供。"
            "請使用 build_index.py --no-embed 或 query.py --mode keyword。"
        ) from exc
    if device not in ("auto", "cpu", "cuda"):
        raise ValueError("device 必須為 auto、cpu 或 cuda")
    if device == "auto":
        device = "cuda" if torch.cuda.is_available() else "cpu"
    if device == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("指定 --device cuda，但目前 PyTorch 無可用 CUDA；請改用 --device cpu")
    if revision is not None:
        validate_model_revision(model, revision)
    else:
        revision = resolve_model_revision(model, cache=cache)
    options = {"device": device, "cache_folder": str(cache / "hub"),
               "trust_remote_code": False, "token": False}
    if revision is not None:
        options["revision"] = revision
    return SentenceTransformer(model, **options)


def load_injected_embedder(factory, model, revision):
    """Existing unpinned factories retain their one-argument API."""
    if revision is None:
        return factory(model)
    import inspect
    try:
        inspect.signature(factory).bind(model, revision=revision)
    except (TypeError, ValueError) as exc:
        raise ValueError("注入的模型 factory 須接受 revision 參數") from exc
    return factory(model, revision=revision)


def embedder_identity(embedder, model):
    return model_identity(embedder, model, document_prefix=model_prefix(model),
                          query_prefix=model_prefix(model, True))


def encode(embedder, texts, prefix, batch_size=64):
    """Use the same E5 prefixes and normalization for real and fake encoders."""
    rows = embedder.encode([prefix + text for text in texts], batch_size=batch_size,
                           normalize_embeddings=True, show_progress_bar=False)
    vectors = []
    for row in rows:
        values = [float(value) for value in row]
        norm = math.sqrt(sum(value * value for value in values))
        if not values or not math.isfinite(norm) or norm == 0:
            raise ValueError("Embedder returned an empty, zero or non-finite vector")
        vectors.append([value / norm for value in values])
    if len(vectors) != len(texts) or len({len(row) for row in vectors}) > 1:
        raise ValueError("Embedder returned inconsistent vector count/dimensions")
    return vectors


def vector_blob(vector):
    # Explicit little-endian IEEE float32; independent of host endianness.
    import struct
    return struct.pack("<" + "f" * len(vector), *vector)


def open_index(path):
    path = Path(path).resolve()
    if not path.is_file():
        raise ValueError(f"索引不存在：{path}；請先執行 build_index.py")
    connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
    return connection


def metadata(connection):
    return {key: json.loads(value) for key, value in connection.execute("SELECT key, value FROM meta")}


def rrf(rankings, k=60, weights=None):
    weights = [1.0] * len(rankings) if weights is None else weights
    if k < 0 or len(weights) != len(rankings) or not any(weights) or any(not math.isfinite(w) or w < 0 for w in weights):
        raise ValueError("RRF needs nonnegative finite weights, positive total weight and k >= 0")
    scores = {}
    for ranking, weight in zip(rankings, weights):
        if not weight:
            continue
        for rank, identifier in enumerate(dict.fromkeys(ranking), 1):
            scores[identifier] = scores.get(identifier, 0.0) + weight / (k + rank)
    return sorted(scores.items(), key=lambda item: (-item[1], item[0]))


def like_pattern(text):
    return "%" + text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def keyword_search(connection, query, limit):
    return _keyword_search(connection, query, limit, "question_fts", "question_id")


def law_keyword_search(connection, query, limit):
    return _keyword_search(connection, query, limit, "law_fts", "article_id")


def _keyword_search(connection, query, limit, table, id_column):
    if (table, id_column) not in (("question_fts", "question_id"), ("law_fts", "article_id")):
        raise ValueError("不支援的 FTS 索引")
    query = normalize_text(query).strip().strip(",;:?!，；：？！")
    if not query or limit <= 0:
        return []
    if len(query) < 3:
        return connection.execute(
            f"SELECT {id_column}, 0.0 FROM {table} WHERE text LIKE ? ESCAPE '\\' "
            f"ORDER BY {id_column} LIMIT ?", (like_pattern(query), limit)
        ).fetchall()
    phrase = '"' + query.replace('"', '""') + '"'
    rows = connection.execute(
        f"SELECT {id_column}, bm25({table}) FROM {table} WHERE {table} MATCH ? "
        f"ORDER BY bm25({table}), {id_column} LIMIT ?", (phrase, limit)
    ).fetchall()
    if rows:
        return [(identifier, -score) for identifier, score in rows]
    terms = query.split()
    long_terms = [term for term in terms if len(term) >= 3]
    short_terms = [term for term in terms if len(term) < 3]
    if not long_terms:
        return connection.execute(
            f"SELECT {id_column}, 0.0 FROM {table} WHERE "
            + " AND ".join("text LIKE ? ESCAPE '\\'" for _ in terms)
            + f" ORDER BY {id_column} LIMIT ?", (*map(like_pattern, terms), limit)
        ).fetchall()
    quoted = ['"' + term.replace('"', '""') + '"' for term in long_terms]
    filters = "".join(" AND text LIKE ? ESCAPE '\\'" for _ in short_terms)
    sql = (f"SELECT {id_column}, bm25({table}) FROM {table} "
           f"WHERE {table} MATCH ?" + filters
           + f" ORDER BY bm25({table}), {id_column} LIMIT ?")
    parameters = (*map(like_pattern, short_terms), limit)
    rows = connection.execute(sql, (" AND ".join(quoted), *parameters)).fetchall()
    if not rows and len(quoted) > 1:
        rows = connection.execute(sql, (" OR ".join(quoted), *parameters)).fetchall()
    # Expose higher-is-better scores consistently across all modes.
    return [(identifier, -score) for identifier, score in rows]


def phrase_ids(connection, query, limit):
    """Use the same normalization/FTS semantics as keyword_search, no fuzzy boost."""
    query = normalize_text(query).strip().strip(",;:?!，；：？！")
    if not query:
        return set()
    if len(query) < 3:
        return {row[0] for row in keyword_search(connection, query, limit)}
    phrase = '"' + query.replace('"', '""') + '"'
    return {row[0] for row in connection.execute(
        "SELECT question_id FROM question_fts WHERE question_fts MATCH ? ORDER BY bm25(question_fts), question_id LIMIT ?",
        (phrase, limit))}


class Retriever:
    def __init__(self, db, *, embedder=None, embedder_factory=None, device="auto"):
        if device not in ("auto", "cpu", "cuda"):
            raise ValueError("device 必須為 auto、cpu 或 cuda")
        self.db = Path(db)
        self.connection, self._file_key = self._open_current()
        self.meta = metadata(self.connection)
        self.embedder = embedder
        self._managed_embedder = embedder is None
        self.embedder_factory = embedder_factory
        self.device = device
        self.vector_ids = None
        self.matrix = None
        self.question_ids = None
        self.link_questions = None
        self.link_vectors = None
        self.law_ids = None
        self.law_matrix = None
        self.law_embedder = None
        self._managed_law_embedder = embedder is None
        self._snapshot_depth = 0
        self._cache_token = None

    def _open_current(self):
        before = self._index_file_key()
        connection = open_index(self.db)
        after = self._index_file_key()
        if before != after:
            connection.close()
            raise ValueError("開啟期間索引已替換；請重試")
        return connection, after

    def _index_file_key(self):
        try:
            stat = self.db.stat()
            return stat.st_dev, stat.st_ino
        except OSError:
            return None

    def _clear_vectors(self):
        self.vector_ids = self.matrix = self.question_ids = None
        self.link_questions = self.link_vectors = None
        self.law_ids = self.law_matrix = None

    @contextmanager
    def _snapshot(self):
        if self._snapshot_depth:
            yield
            return
        file_key = self._index_file_key()
        if self._file_key is not None and file_key != self._file_key:
            if file_key is None:
                raise ValueError(f"索引不存在：{self.db}")
            self.connection.close()
            self.connection, self._file_key = self._open_current()
            self._cache_token = None
            self._clear_vectors()
            if self._managed_embedder:
                self.embedder = None
        self.connection.execute("SAVEPOINT rag_retriever_snapshot")
        self._snapshot_depth = 1
        try:
            # The data version is sampled before the first read establishes the
            # snapshot. A racing commit then invalidates the next search too.
            token = (self.connection.execute("PRAGMA data_version").fetchone()[0],
                     self.connection.total_changes)
            current_meta = metadata(self.connection)
            if self._cache_token != token or current_meta != self.meta:
                if self._managed_embedder and any(
                        self.meta.get(key) != current_meta.get(key)
                        for key in ("model", "model_revision", "model_identity")):
                    self.embedder = None
                if self._managed_law_embedder and any(
                        self.meta.get(key) != current_meta.get(key)
                        for key in ("laws_model", "laws_model_revision", "laws_model_identity")):
                    self.law_embedder = None
                self._clear_vectors()
            self.meta = current_meta
            self._cache_token = token
            yield
        finally:
            self._snapshot_depth = 0
            self.connection.execute("RELEASE SAVEPOINT rag_retriever_snapshot")

    def close(self):
        self.connection.close()

    def _load_vectors(self):
        with self._snapshot():
            return self._load_vectors_snapshot()

    def _load_vectors_snapshot(self):
        import numpy as np
        schema = self.meta.get("schema_version")
        if type(schema) is not int or schema != SCHEMA_VERSION:
            raise ValueError("向量 schema 過期；請執行 build_index.py --embed 全量重建")
        embedding_text_version(self.meta)
        pending = pending_vector_questions(self.meta)
        self.question_ids = [row[0] for row in self.connection.execute("SELECT question_id FROM questions ORDER BY question_id")]
        rows = self.connection.execute(
            "SELECT vector_id, embedding FROM vectors ORDER BY vector_id"
        ).fetchall()
        if any(row[1] is not None for row in rows) and not valid_identity(self.meta.get("model_identity")):
            raise ValueError(REBUILD_MESSAGE)
        dimension = self.meta.get("dimension")
        links = self.connection.execute("SELECT question_id, vector_id FROM question_vectors ORDER BY question_id, vector_id").fetchall()
        if any(not isinstance(question_id, str) or not isinstance(vector_id, str)
               for question_id, vector_id in links):
            raise ValueError("向量索引連結無效")
        main_questions = {question_id for question_id, vector_id in links
                          if vector_id.startswith(f"q:{question_id}:")}
        vector_ids = [row[0] for row in rows]
        if (not self.meta.get("model") or not dimension or any(row[1] is None for row in rows)
                or pending or main_questions != set(self.question_ids)
                or not {q for q, _ in links}.issubset(self.question_ids)
                or not {v for _, v in links}.issubset(vector_ids)):
            raise ValueError("向量索引缺漏或過期；請先執行 build_index.py --embed（keyword 仍可使用）")
        if not valid_identity(self.meta.get("model_identity")):
            raise ValueError(REBUILD_MESSAGE)
        revision = (validate_model_revision(self.meta["model"], self.meta["model_revision"])
                    if "model_revision" in self.meta else None)
        matrix = (np.stack([np.frombuffer(row[1], dtype="<f4") for row in rows])
                  if rows else np.empty((0, dimension), dtype=np.float32))
        if matrix.shape != (len(rows), dimension):
            raise ValueError("索引向量維度不符；請重建向量索引")
        question_positions = {identifier: index for index, identifier in enumerate(self.question_ids)}
        vector_positions = {identifier: index for index, identifier in enumerate(vector_ids)}
        self.link_questions = np.asarray([question_positions[q] for q, v in links], dtype=np.intp)
        self.link_vectors = np.asarray([vector_positions[v] for q, v in links], dtype=np.intp)
        if self.embedder is None:
            if self.embedder_factory:
                self.embedder = load_injected_embedder(self.embedder_factory, self.meta["model"], revision)
            elif revision is None:
                self.embedder = load_embedder(self.meta["model"], device=self.device)
            else:
                self.embedder = load_embedder(self.meta["model"], device=self.device, revision=revision)
        require_matching_identity(self.meta["model_identity"], embedder_identity(self.embedder, self.meta["model"]))
        # Publish readiness only after the model and matrix are both usable.
        self.vector_ids, self.matrix = vector_ids, matrix

    def vector_search(self, query, limit):
        with self._snapshot():
            return self._vector_search_snapshot(query, limit)

    def _vector_search_snapshot(self, query, limit):
        import numpy as np
        if self.vector_ids is None:
            self._load_vectors()
        # Identity is verified once in _load_vectors; hashing every weight per query cost seconds.
        queries = [query] if isinstance(query, str) else query
        vectors = encode(self.embedder, [normalize_text(q) for q in queries], model_prefix(self.meta["model"], True))
        if len(vectors[0]) != self.meta["dimension"]:
            raise ValueError("查詢向量與索引維度不符")
        vector_scores = (self.matrix @ np.asarray(vectors, dtype=np.float32).T).max(axis=1)
        scores = np.full(len(self.question_ids), -np.inf, dtype=np.float32)
        np.maximum.at(scores, self.link_questions, vector_scores[self.link_vectors])
        # Stable ID tie-breaking also makes fake-encoder checks reproducible.
        order = np.argsort(-scores, kind="stable")[:limit]
        return [(self.question_ids[index], float(scores[index])) for index in order]

    def search(self, query, *, k=5, mode="hybrid", keyword_weight=DEFAULT_KEYWORD_WEIGHT,
               vector_weight=DEFAULT_VECTOR_WEIGHT, rrf_k=60, phrase_priority=True,
               expand_abbreviations=False, candidates=50, min_vector_score=None, reranker=None):
        with self._snapshot():
            return self._search_snapshot(query, k=k, mode=mode, keyword_weight=keyword_weight,
                vector_weight=vector_weight, rrf_k=rrf_k, phrase_priority=phrase_priority,
                expand_abbreviations=expand_abbreviations, candidates=candidates,
                min_vector_score=min_vector_score, reranker=reranker)

    def _search_snapshot(self, query, *, k, mode, keyword_weight, vector_weight, rrf_k,
                         phrase_priority, expand_abbreviations, candidates, min_vector_score, reranker):
        if mode not in ("keyword", "vector", "hybrid"):
            raise ValueError(f"Unknown retrieval mode: {mode}")
        if k <= 0:
            raise ValueError("k 必須大於 0")
        if (min_vector_score is not None and
                (not math.isfinite(min_vector_score) or not -1 <= min_vector_score <= 1)):
            raise ValueError("min_vector_score 必須為 -1 到 1 之間的有限數值")
        if not query.strip():
            return []
        if candidates <= 0:
            raise ValueError("candidates 必須大於 0")
        limit = max(k, candidates, 20 if reranker else 0)
        queries = expand_query(query) if expand_abbreviations else [query]
        keywords = [keyword_search(self.connection, q, limit) for q in queries] if mode != "vector" else []
        keyword = (keywords[0] if len(keywords) == 1 else
                   rrf([[row[0] for row in ranking] for ranking in keywords], k=rrf_k)) if keywords else []
        if mode == "keyword":
            ranking = keyword
        elif mode == "vector":
            ranking = self.vector_search(queries, limit)
        else:
            vector = self.vector_search(queries, limit)
            top1_vector_score = vector[0][1] if vector else None
            ranking = rrf([[row[0] for row in keyword], [row[0] for row in vector]],
                          k=rrf_k, weights=[keyword_weight, vector_weight])
        exact = set()
        if mode == "hybrid" or (mode == "keyword" and phrase_priority):
            exact = set().union(*(phrase_ids(self.connection, q, limit) for q in queries))
        keyword_phrase_hit = bool(exact)
        if phrase_priority and mode != "vector":
            # Preserve keyword's exact-hit order: weak vectors cannot displace it.
            promoted = [row[0] for row in keyword if row[0] in exact]
            positions = {identifier: index for index, identifier in enumerate(promoted)}
            ranking.sort(key=lambda row: (0, positions[row[0]]) if row[0] in positions else (1, 0))
        results = []
        for rank, (identifier, score) in enumerate(ranking[:max(k, 20) if reranker else k], 1):
            doc = json.loads(self.connection.execute(
                "SELECT doc_json FROM questions WHERE question_id=?", (identifier,)
            ).fetchone()[0])
            sources = {item["path"]: item for item in doc.get("sources", [])}
            citations = [{**item, "question_pdf_url": sources.get(item["path"], {}).get("question_pdf_url"),
                          "answer_pdf_url": sources.get(item["path"], {}).get("answer_pdf_url")}
                         for item in doc.get("appears_in", [])]
            result = {**doc, "rank": rank, "score": score, "citations": citations,
                      "answer_confidence": "disputed" if doc.get("answer_conflicts") else "unknown"}
            if mode == "hybrid":
                result.update(top1_vector_score=top1_vector_score, keyword_phrase_hit=keyword_phrase_hit)
                if (min_vector_score is not None and top1_vector_score is not None
                        and top1_vector_score < min_vector_score and not keyword_phrase_hit):
                    result["low_confidence"] = True
            results.append(result)
        if reranker and results:
            head = results[:20]
            scores = reranker.predict([(query, embedding_texts(doc)[0]) for doc in head])
            if len(scores) != len(head) or any(not math.isfinite(float(s)) for s in scores):
                raise ValueError("Reranker returned invalid scores")
            for doc, score in zip(head, scores):
                doc["rerank_score"] = float(score)
            results = sorted(head, key=lambda doc: (-doc["rerank_score"], doc["question_id"])) + results[20:]
            if phrase_priority and mode != "vector":
                results.sort(key=lambda doc: (0, positions[doc["question_id"]])
                             if doc["question_id"] in positions else (1, 0))
            for rank, doc in enumerate(results, 1):
                doc["rank"] = rank
        return results[:k]

    def search_laws(self, query, *, k=3, keyword_weight=DEFAULT_KEYWORD_WEIGHT,
                    vector_weight=DEFAULT_VECTOR_WEIGHT, rrf_k=60, candidates=50,
                    expand_abbreviations=False, min_vector_score=None):
        with self._snapshot():
            return self._search_laws_snapshot(
                query, k=k, keyword_weight=keyword_weight, vector_weight=vector_weight,
                rrf_k=rrf_k, candidates=candidates, expand_abbreviations=expand_abbreviations,
                min_vector_score=min_vector_score,
            )

    def _search_laws_snapshot(self, query, *, k, keyword_weight, vector_weight,
                              rrf_k, candidates, expand_abbreviations, min_vector_score):
        if k < 0:
            raise ValueError("k 不可小於 0")
        if not query.strip() or k == 0:
            return []
        if candidates <= 0:
            raise ValueError("candidates 必須大於 0")
        exists = self.connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='law_articles'"
        ).fetchone()
        if not exists:
            return []
        total = self.connection.execute("SELECT count(*) FROM law_articles").fetchone()[0]
        if not total:
            return []

        queries = expand_query(query) if expand_abbreviations else [query]
        limit = max(k, candidates)
        keyword_runs = [law_keyword_search(self.connection, item, limit) for item in queries]
        keyword = (keyword_runs[0] if len(keyword_runs) == 1 else
                   rrf([[row[0] for row in ranking] for ranking in keyword_runs], k=rrf_k))
        vector = self._law_vector_search_snapshot(queries, limit)
        # Off-topic queries still match some article; hide the block when the best article is weak.
        if vector and min_vector_score is not None and vector[0][1] < min_vector_score:
            return []
        if vector:
            ranking = rrf(
                [[row[0] for row in keyword], [row[0] for row in vector]],
                k=rrf_k, weights=[keyword_weight, vector_weight],
            )
        else:
            ranking = keyword

        results = []
        for rank, (identifier, score) in enumerate(ranking[:k], 1):
            row = self.connection.execute(
                "SELECT id, law_name, pcode, article_no, chapter, content, "
                "law_modified_date, url FROM law_articles WHERE id=?",
                (identifier,),
            ).fetchone()
            if row:
                results.append(dict(zip(
                    ("id", "law_name", "pcode", "article_no", "chapter", "content",
                     "law_modified_date", "url"), row
                ), rank=rank, score=score))
        return results

    def _law_vector_search_snapshot(self, queries, limit):
        has_vectors = self.connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='law_vectors'"
        ).fetchone()
        if not has_vectors or not valid_identity(self.meta.get("laws_model_identity")):
            return []
        model = self.meta.get("laws_model")
        dimension = self.meta.get("laws_dimension")
        if not isinstance(model, str) or type(dimension) is not int or dimension <= 0:
            return []
        import numpy as np
        if self.law_ids is None:
            rows = self.connection.execute(
                "SELECT article_id, embedding FROM law_vectors ORDER BY article_id"
            ).fetchall()
            if len(rows) != self.connection.execute("SELECT count(*) FROM law_articles").fetchone()[0]:
                return []
            if not rows:
                return []
            matrix = np.stack([np.frombuffer(blob, dtype="<f4") for _, blob in rows])
            if matrix.shape != (len(rows), dimension):
                raise ValueError("法條向量維度不符；請重建法條索引")
            self.law_ids = [identifier for identifier, _ in rows]
            self.law_matrix = matrix
        revision = self.meta.get("laws_model_revision")
        if revision is not None:
            validate_model_revision(model, revision)
        if self.law_embedder is None:
            if self.embedder is not None and self.meta.get("model") == model:
                self.law_embedder = self.embedder
            elif self.embedder_factory:
                self.law_embedder = load_injected_embedder(self.embedder_factory, model, revision)
            elif revision is None:
                self.law_embedder = load_embedder(model, device=self.device)
            else:
                self.law_embedder = load_embedder(model, device=self.device, revision=revision)
            # Identity hashes every weight; check once per loaded embedder, not per query,
            # and skip it when _load_vectors already verified this same embedder and identity.
            already_verified = (self.law_embedder is self.embedder and self.matrix is not None
                                and self.meta.get("laws_model_identity") == self.meta.get("model_identity"))
            if not already_verified:
                require_matching_identity(
                    self.meta["laws_model_identity"], embedder_identity(self.law_embedder, model)
                )
        encoded = encode(
            self.law_embedder, [normalize_text(item) for item in queries],
            model_prefix(model, True),
        )
        if any(len(vector) != dimension for vector in encoded):
            raise ValueError("查詢向量與法條索引維度不符")
        scores = (self.law_matrix @ np.asarray(encoded, dtype=np.float32).T).max(axis=1)
        order = np.argsort(-scores, kind="stable")[:limit]
        return [(self.law_ids[index], float(scores[index])) for index in order]
