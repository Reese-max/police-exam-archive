"""Shared local retrieval: SQLite trigram BM25, normalized vectors and RRF."""

import json
import math
import os
from pathlib import Path
import sqlite3

if __package__:
    from .build_corpus import json_text, normalize_text
else:
    from build_corpus import json_text, normalize_text


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MODEL = "intfloat/multilingual-e5-small"


def load_embedder(model, device="auto"):
    # Keep model/tokenizer caches inside this worktree, including on Spaces.
    cache = ROOT / ".hf_cache"
    os.environ["HF_HOME"] = str(cache)
    os.environ["HF_HUB_CACHE"] = str(cache / "hub")
    os.environ["HUGGINGFACE_HUB_CACHE"] = str(cache / "hub")
    os.environ["TRANSFORMERS_CACHE"] = str(cache / "transformers")
    os.environ["SENTENCE_TRANSFORMERS_HOME"] = str(cache / "sentence_transformers")
    os.environ["HF_ENDPOINT"] = "https://huggingface.co"
    os.environ["HF_HUB_DISABLE_IMPLICIT_TOKEN"] = "1"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
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
    return SentenceTransformer(model, device=device, cache_folder=str(cache / "hub"),
                               trust_remote_code=False, token=False)


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


def rrf(rankings, k=60):
    scores = {}
    for ranking in rankings:
        for rank, identifier in enumerate(dict.fromkeys(ranking), 1):
            scores[identifier] = scores.get(identifier, 0.0) + 1 / (k + rank)
    return sorted(scores.items(), key=lambda item: (-item[1], item[0]))


def like_pattern(text):
    return "%" + text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def keyword_search(connection, query, limit):
    query = normalize_text(query).strip().strip(",;:?!，；：？！")
    if not query or limit <= 0:
        return []
    if len(query) < 3:
        return connection.execute(
            "SELECT question_id, 0.0 FROM question_fts WHERE text LIKE ? ESCAPE '\\' "
            "ORDER BY question_id LIMIT ?", (like_pattern(query), limit)
        ).fetchall()
    phrase = '"' + query.replace('"', '""') + '"'
    rows = connection.execute(
        "SELECT question_id, bm25(question_fts) FROM question_fts WHERE question_fts MATCH ? "
        "ORDER BY bm25(question_fts), question_id LIMIT ?", (phrase, limit)
    ).fetchall()
    if rows:
        return [(identifier, -score) for identifier, score in rows]
    terms = query.split()
    long_terms = [term for term in terms if len(term) >= 3]
    short_terms = [term for term in terms if len(term) < 3]
    if not long_terms:
        return connection.execute(
            "SELECT question_id, 0.0 FROM question_fts WHERE "
            + " AND ".join("text LIKE ? ESCAPE '\\'" for _ in terms)
            + " ORDER BY question_id LIMIT ?", (*map(like_pattern, terms), limit)
        ).fetchall()
    quoted = ['"' + term.replace('"', '""') + '"' for term in long_terms]
    filters = "".join(" AND text LIKE ? ESCAPE '\\'" for _ in short_terms)
    sql = ("SELECT question_id, bm25(question_fts) FROM question_fts "
           "WHERE question_fts MATCH ?" + filters
           + " ORDER BY bm25(question_fts), question_id LIMIT ?")
    parameters = (*map(like_pattern, short_terms), limit)
    rows = connection.execute(sql, (" AND ".join(quoted), *parameters)).fetchall()
    if not rows and len(quoted) > 1:
        rows = connection.execute(sql, (" OR ".join(quoted), *parameters)).fetchall()
    # Expose higher-is-better scores consistently across all modes.
    return [(identifier, -score) for identifier, score in rows]


class Retriever:
    def __init__(self, db, *, embedder=None, embedder_factory=None, device="auto"):
        if device not in ("auto", "cpu", "cuda"):
            raise ValueError("device 必須為 auto、cpu 或 cuda")
        self.connection = open_index(db)
        self.meta = metadata(self.connection)
        self.embedder = embedder
        self.embedder_factory = embedder_factory
        self.device = device
        self.vector_ids = None
        self.matrix = None

    def close(self):
        self.connection.close()

    def _load_vectors(self):
        import numpy as np
        count = self.connection.execute("SELECT count(*) FROM questions").fetchone()[0]
        rows = self.connection.execute(
            "SELECT question_id, embedding FROM vectors ORDER BY question_id"
        ).fetchall()
        dimension = self.meta.get("dimension")
        if not self.meta.get("model") or not dimension or len(rows) != count:
            raise ValueError("向量索引缺漏或過期；請先執行 build_index.py --embed（keyword 仍可使用）")
        self.vector_ids = [row[0] for row in rows]
        self.matrix = (np.stack([np.frombuffer(row[1], dtype="<f4") for row in rows])
                       if rows else np.empty((0, dimension), dtype=np.float32))
        if self.matrix.shape != (count, dimension):
            raise ValueError("索引向量維度不符；請重建向量索引")
        if self.embedder is None:
            self.embedder = (self.embedder_factory(self.meta["model"]) if self.embedder_factory
                             else load_embedder(self.meta["model"], device=self.device))

    def vector_search(self, query, limit):
        import numpy as np
        if self.vector_ids is None:
            self._load_vectors()
        vector = encode(self.embedder, [normalize_text(query)], "query: ")[0]
        if len(vector) != self.meta["dimension"]:
            raise ValueError("查詢向量與索引維度不符")
        scores = self.matrix @ np.asarray(vector, dtype=np.float32)
        # Stable ID tie-breaking also makes fake-encoder checks reproducible.
        order = np.argsort(-scores, kind="stable")[:limit]
        return [(self.vector_ids[index], float(scores[index])) for index in order]

    def search(self, query, *, k=5, mode="hybrid"):
        if mode not in ("keyword", "vector", "hybrid"):
            raise ValueError(f"Unknown retrieval mode: {mode}")
        if k <= 0:
            raise ValueError("k 必須大於 0")
        if not query.strip():
            return []
        if mode == "keyword":
            ranking = keyword_search(self.connection, query, k)
        elif mode == "vector":
            ranking = self.vector_search(query, k)
        else:
            keyword = keyword_search(self.connection, query, 50)
            vector = self.vector_search(query, 50)
            ranking = rrf([[row[0] for row in keyword], [row[0] for row in vector]])[:k]
        results = []
        for rank, (identifier, score) in enumerate(ranking, 1):
            doc = json.loads(self.connection.execute(
                "SELECT doc_json FROM questions WHERE question_id=?", (identifier,)
            ).fetchone()[0])
            sources = {item["path"]: item for item in doc.get("sources", [])}
            citations = [{**item, "question_pdf_url": sources.get(item["path"], {}).get("question_pdf_url"),
                          "answer_pdf_url": sources.get(item["path"], {}).get("answer_pdf_url")}
                         for item in doc.get("appears_in", [])]
            results.append({**doc, "rank": rank, "score": score, "citations": citations})
        return results
