"""Offline checks on a tiny, real XLM-R SentenceTransformer pipeline."""

import socket

import pytest


def test_real_pipeline_identity_tracks_output_affecting_state(tmp_path, monkeypatch, request):
    def blocked(*args, **kwargs):
        raise AssertionError("network is blocked")
    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    monkeypatch.setenv("TRANSFORMERS_OFFLINE", "1")
    torch = pytest.importorskip("torch")
    pytest.importorskip("sentence_transformers")
    from transformers import XLMRobertaConfig, XLMRobertaModel, XLMRobertaTokenizerFast, AutoProcessor
    from tokenizers import Tokenizer, models as tkmodels, pre_tokenizers, processors
    from sentence_transformers import SentenceTransformer, models
    from scripts.rag.retrieval import embedder_identity, encode

    old_threads, old_rng = torch.get_num_threads(), torch.get_rng_state()
    request.addfinalizer(lambda: torch.set_num_threads(old_threads))
    request.addfinalizer(lambda: torch.set_rng_state(old_rng))
    torch.set_num_threads(1)
    torch.manual_seed(15)
    vocab = {"<s>": 0, "<pad>": 1, "</s>": 2, "<unk>": 3, "<mask>": 4,
             "short": 5, "long": 6, "a": 7, "b": 8, "c": 9, "d": 10,
             "e": 11, "query": 12, ":": 13}
    backend = Tokenizer(tkmodels.WordLevel(vocab, unk_token="<unk>"))
    backend.pre_tokenizer = pre_tokenizers.Whitespace()
    backend.post_processor = processors.TemplateProcessing(
        single="<s> $A </s>", pair="<s> $A </s> </s> $B </s>",
        special_tokens=[("<s>", 0), ("</s>", 2)])
    tok = XLMRobertaTokenizerFast(tokenizer_object=backend, bos_token="<s>", eos_token="</s>",
                                  unk_token="<unk>", pad_token="<pad>", mask_token="<mask>", model_max_length=48)
    config = XLMRobertaConfig(vocab_size=len(vocab), hidden_size=16, num_hidden_layers=1,
        num_attention_heads=4, intermediate_size=32, max_position_embeddings=64, type_vocab_size=2,
        hidden_dropout_prob=0, attention_probs_dropout_prob=0, pad_token_id=1)
    XLMRobertaModel(config).save_pretrained(tmp_path)
    tok.save_pretrained(tmp_path)
    monkeypatch.setattr(AutoProcessor, "from_pretrained", lambda *a, **k: tok)
    transformer = models.Transformer(str(tmp_path), model_kwargs={"local_files_only": True},
                                     processor_kwargs={"local_files_only": True})
    encoder = SentenceTransformer(modules=[transformer, models.Pooling(16, pooling_mode="mean")], device="cpu")
    model = transformer.auto_model
    texts = ["short", "a b c d e long"]
    def identity(): return embedder_identity(encoder, "synthetic-e5")
    def vectors(): return encode(encoder, texts, "query: ", batch_size=2)
    def changed(before, after):
        return max(abs(x - y) for left, right in zip(before, after) for x, y in zip(left, right)) > 1e-8

    # Ensure the starting state matches the state SentenceTransformer uses to encode.
    before_vectors = vectors()
    before_id = identity()
    assert "embeddings.token_type_ids" not in model.state_dict()
    with torch.no_grad():
        model.embeddings.token_type_ids.fill_(1)
    assert identity() != before_id and changed(before_vectors, vectors())
    with torch.no_grad():
        model.embeddings.token_type_ids.zero_()

    before_id, before_vectors = identity(), vectors()
    old_eps = model.embeddings.LayerNorm.eps
    model.embeddings.LayerNorm.eps = .1
    assert identity() != before_id and changed(before_vectors, vectors())
    model.embeddings.LayerNorm.eps = old_eps

    before_id, before_vectors = identity(), vectors()
    layer = model.encoder.layer[0].intermediate
    old_activation = layer.intermediate_act_fn
    layer.intermediate_act_fn = torch.nn.ReLU()
    assert identity() != before_id and changed(before_vectors, vectors())
    layer.intermediate_act_fn = old_activation

    before_id, before_vectors = identity(), vectors()
    old_names = tok.model_input_names[:]
    tok.model_input_names = ["input_ids"]
    assert identity() != before_id and changed(before_vectors, vectors())
    tok.model_input_names = old_names

    before_id, before_vectors = identity(), vectors()
    original_params = set(transformer.model_forward_params)
    transformer.model_forward_params.remove("attention_mask")
    assert identity() != before_id and changed(before_vectors, vectors())
    transformer.model_forward_params = original_params

    for register in (torch.nn.modules.module.register_module_forward_hook,
                     torch.nn.modules.module.register_module_forward_pre_hook):
        handle = register(lambda *args: None)
        try:
            with pytest.raises(ValueError, match="全域.*hook"):
                identity()
        finally:
            handle.remove()
        assert identity() == before_id

    before_id = identity()
    with torch.no_grad():
        model.encoder.layer[0].output.dense.weight[-1, -1] += 1
    assert identity() != before_id
    layer.register_buffer("late_check", torch.zeros(2), persistent=False)
    before_id = identity()
    with torch.no_grad():
        layer.late_check[-1] = 1
    assert identity() != before_id

    from scripts.rag.build_index import build_index
    from scripts.rag.retrieval import Retriever
    from test_rag_index import document, write_corpus

    corpus, db = tmp_path / "corpus.jsonl", tmp_path / "index.sqlite"
    write_corpus(corpus, [document("a", "short")])
    build_index(corpus, db, model="synthetic-e5", embedder_factory=lambda _: encoder)
    reader = Retriever(db, embedder=encoder)
    try:
        assert reader.search("short", mode="vector")
        before_vectors = vectors()
        original_encode = encoder.encode
        encoder.encode = lambda inputs, **kwargs: -original_encode(inputs, **kwargs)
        try:
            assert changed(before_vectors, vectors())
            with pytest.raises(ValueError, match="實例方法"):
                reader.search("short", mode="vector")
            fresh = Retriever(db, embedder=encoder)
            try:
                with pytest.raises(ValueError, match="實例方法"):
                    fresh.search("short", mode="vector")
            finally:
                fresh.close()
        finally:
            del encoder.encode
        assert reader.search("short", mode="vector")
    finally:
        reader.close()

    for obj, name in ((encoder, "preprocess"), (transformer, "preprocess"),
                      (tok, "encode"), (tok, "_encode_plus")):
        assert name not in vars(obj)
        setattr(obj, name, lambda *args, **kwargs: None)
        try:
            with pytest.raises(ValueError, match="實例方法"):
                identity()
        finally:
            delattr(obj, name)
    assert identity()


def test_torch_wheel_tags_do_not_hide_upstream_version_changes():
    from scripts.rag.model_identity import _torch_version
    assert _torch_version("2.7.1+cpu") == _torch_version("2.7.1+cu118") == "2.7.1"
    assert _torch_version("2.7.2+cpu") != _torch_version("2.7.1+cu118")
    assert _torch_version("2.7.1+other") != _torch_version("2.7.1+cpu")
