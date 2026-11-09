# Historical RAG implementation fixture

The three Python files are unchanged copies of `scripts/rag/build_index.py`,
`scripts/rag/retrieval.py`, and `scripts/rag/build_corpus.py` from repository
commit `9cc4304e6ad4c354e5032b5ad179a8ed9e023a88` (the Git HEAD before the
answer-index consistency changes). They are retained to test the actual old
builder and reader without requiring Git history or network access.

SHA-256 of the LF-encoded files:

- `build_index.py`: `73091934dc71c5c0652a33b0642d5c5db1fb5fda6ecb460cfc5787013f569c59`
- `retrieval.py`: `1fa76b6cdb7d4f8a9dc3e4c196c7edb66098c1c254780866516bdac69660233e`
- `build_corpus.py`: `6e09af046f92477e3082726c72ec0ff107accb3b6f1257eb752d4b4fc86b64f1`

Tests copy these files to temporary directories and provide fake encoders;
the fixture is not a production implementation.
