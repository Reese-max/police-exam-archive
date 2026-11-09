"""Versioned identities for the actual encoder state used by this index.

Injected encoders have an explicit caller-owned contract: ``rag_identity`` is
the lowercase SHA-256 of all state and behaviour that can affect their output,
including any tokenizer. It is not a claim independently verified by this code.
"""

import hashlib
import json
import re
from concurrent.futures import ThreadPoolExecutor


IDENTITY_VERSION = 3
REBUILD_MESSAGE = "向量模型身分未知或不相符；請保留舊索引，使用新的 --db 完整重建向量索引"
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def _module_value(value):
    if value is None or type(value) in (bool, int, float, str):
        return value
    if isinstance(value, (list, tuple)):
        return [_module_value(item) for item in value]
    if isinstance(value, dict) and all(isinstance(key, str) for key in value):
        return {key: _module_value(item) for key, item in value.items()}
    if type(value).__module__.startswith("transformers.") and callable(getattr(value, "to_dict", None)):
        config = value.to_dict()
        for key in ("_name_or_path", "_commit_hash", "transformers_version"):
            config.pop(key, None)
        return {"config": config, "attention_implementation": getattr(value, "_attn_implementation", None)}
    if callable(value):
        module, name = getattr(value, "__module__", ""), getattr(value, "__qualname__", "")
        if isinstance(module, str) and module.startswith(("torch.", "transformers.")) and name:
            return {"callable": module + "." + name}
    raise ValueError("不支援的模型模組狀態；無法驗證向量身分")


def _module_settings(model):
    """Record live module classes and output-affecting public configuration."""
    settings = []
    for name, module in model.named_modules(remove_duplicate=False):
        attributes = {}
        for key, value in vars(module).items():
            if key.startswith("_") or key == "name_or_path":
                continue
            attributes[key] = _module_value(value)
        settings.append([name, type(module).__module__ + "." + type(module).__qualname__, attributes])
    return settings


def _tensor_hash(item, torch):
    kind, name, tensor = item
    if not isinstance(tensor, torch.Tensor) or tensor.is_sparse or tensor.is_quantized:
        raise ValueError("不支援的模型權重類型；無法驗證向量身分")
    value = tensor.detach().to("cpu").contiguous()
    digest = hashlib.sha256(_json_bytes([kind, name, str(value.dtype), list(value.shape)]))
    digest.update(memoryview(value.reshape(-1).view(torch.uint8).numpy()))
    return [kind, name, digest.hexdigest()]


def _json_bytes(value):
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                          allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError("不支援的模型設定，無法驗證向量身分") from exc


def valid_identity(identity):
    return (isinstance(identity, dict) and set(identity) == {"version", "kind", "sha256"}
            and type(identity["version"]) is int and identity["version"] == IDENTITY_VERSION
            and identity["kind"] in ("sentence-transformers", "caller")
            and isinstance(identity["sha256"], str) and bool(_SHA256.fullmatch(identity["sha256"])))


def _reject_instance_method_overrides(obj):
    if any(callable(getattr(type(obj), name, None)) for name in vars(obj)):
        raise ValueError("不支援實例方法覆寫；無法驗證向量身分")


def _sentence_transformer_state(embedder):
    """Hash supported live BERT/XLM-R SentenceTransformer state, never filenames.

    Constrain the pipeline and tokenizer to known classes: arbitrary custom
    Python modules can hide output-affecting state outside ``state_dict``.
    """
    if not type(embedder).__module__.startswith("sentence_transformers."):
        raise ValueError("不支援的編碼器類型；注入編碼器須提供 rag_identity")
    try:
        import torch
        import tokenizers
        import sentence_transformers
        from sentence_transformers import SentenceTransformer, models
        from transformers import BertModel, XLMRobertaModel
        import transformers
    except ImportError as exc:
        raise ValueError("不支援的編碼器類型；注入編碼器須提供 rag_identity") from exc
    modules = list(embedder._modules.values()) if type(embedder) is SentenceTransformer else []
    if (len(modules) not in (2, 3) or type(modules[0]) is not models.Transformer
            or type(modules[1]) is not models.Pooling
            or (len(modules) == 3 and type(modules[2]) is not models.Normalize)):
        raise ValueError("不支援的 SentenceTransformer 模組；無法驗證向量身分")
    transformer, pooling = modules[:2]
    tokenizer = getattr(transformer, "tokenizer", None)
    auto_model = getattr(transformer, "auto_model", None)
    tokenizer_types = tuple(cls for cls in (getattr(transformers, "XLMRobertaTokenizerFast", None),
                                              getattr(transformers, "XLMRobertaTokenizer", None))
                            if isinstance(cls, type))
    if (type(auto_model) not in (BertModel, XLMRobertaModel) or type(tokenizer) not in tokenizer_types
            or not hasattr(tokenizer, "backend_tokenizer")):
        raise ValueError("不支援的模型或 tokenizer 類型；無法驗證向量身分")
    _reject_instance_method_overrides(embedder)
    for obj in (tokenizer, getattr(transformer, "processor", None), getattr(transformer, "input_formatter", None)):
        if obj is not None:
            _reject_instance_method_overrides(obj)
    if (getattr(auto_model, "_hf_peft_config_loaded", False) or getattr(auto_model, "peft_config", None)):
        raise ValueError("不支援的模型 adapter；無法驗證向量身分")
    global_hooks = torch.nn.modules.module
    if global_hooks._global_forward_hooks or global_hooks._global_forward_pre_hooks:
        raise ValueError("不支援 PyTorch 全域 forward hook；無法驗證向量身分")
    forward_params = getattr(transformer, "model_forward_params", None)
    if not isinstance(forward_params, (set, frozenset)) or not all(type(item) is str for item in forward_params):
        raise ValueError("不支援的 model_forward_params；無法驗證向量身分")
    for module in embedder.modules():
        _reject_instance_method_overrides(module)
        if (not type(module).__module__.startswith(("sentence_transformers.", "transformers.", "torch.nn."))
                or getattr(module, "_forward_hooks", None) or getattr(module, "_forward_pre_hooks", None)
                or "forward" in vars(module)):
            raise ValueError("不支援自訂模組或 forward hook；無法驗證向量身分")
    try:
        token_state = json.loads(tokenizer.backend_tokenizer.to_str())
        # The fast tokenizer updates these transient values per call. The
        # effective fixed limit and sides are included separately below.
        token_state.pop("truncation", None)
        token_state.pop("padding", None)
        config = transformer.auto_model.config.to_dict()
        for key in ("_name_or_path", "_commit_hash", "transformers_version"):
            config.pop(key, None)
        settings = {
            # torch is left out: ZeroGPU Spaces dictate the torch version, and weights are hashed below.
            "library_versions": {"tokenizers": str(tokenizers.__version__),
                                 "sentence_transformers": str(sentence_transformers.__version__),
                                 "transformers": str(transformers.__version__)},
            "module_types": [type(module).__name__ for module in modules],
            "transformer_class": type(auto_model).__name__,
            "module_settings": _module_settings(auto_model),
            "transformer_config": config,
            "attention_implementation": getattr(auto_model.config, "_attn_implementation", None),
            "transformer_module": transformer.get_config_dict(),
            "model_forward_params": sorted(forward_params),
            "pooling": pooling.get_config_dict(),
            "max_seq_length": embedder.max_seq_length,
            "truncate_dim": embedder.truncate_dim,
            "prompts": embedder.prompts,
            "default_prompt_name": embedder.default_prompt_name,
            "tokenizer": token_state,
            "tokenizer_settings": {
                "class": type(tokenizer).__name__,
                "padding_side": tokenizer.padding_side,
                "truncation_side": tokenizer.truncation_side,
                "model_max_length": tokenizer.model_max_length,
                "model_input_names": tokenizer.model_input_names,
                "clean_up_tokenization_spaces": tokenizer.clean_up_tokenization_spaces,
                "split_special_tokens": tokenizer.split_special_tokens,
                "special_tokens": {key: str(value) if not isinstance(value, list)
                                   else [str(item) for item in value]
                                   for key, value in tokenizer.special_tokens_map.items()},
            },
        }
        tensors = [("parameter", name, tensor) for name, tensor in embedder.named_parameters(remove_duplicate=False)]
        tensors += [("buffer", name, tensor) for name, tensor in embedder.named_buffers(remove_duplicate=False)]
        if set(embedder.state_dict()) - {name for _, name, _ in tensors}:
            raise ValueError("不支援的模型額外狀態；無法驗證向量身分")
        tensors.sort(key=lambda item: (item[0], item[1]))
        with ThreadPoolExecutor(max_workers=4) as workers:
            tensor_hashes = list(workers.map(lambda item: _tensor_hash(item, torch), tensors))
        digest = hashlib.sha256(_json_bytes({"settings": settings, "tensors": tensor_hashes}))
        return digest.hexdigest()
    except (AttributeError, TypeError, RuntimeError) as exc:
        raise ValueError("不支援的模型設定；無法驗證向量身分") from exc


def model_identity(embedder, model_name, *, document_prefix, query_prefix):
    supplied = getattr(embedder, "rag_identity", None)
    if supplied is not None:
        if not isinstance(supplied, str) or not _SHA256.fullmatch(supplied):
            raise ValueError("注入編碼器須提供小寫 SHA-256 rag_identity")
        kind, state = "caller", supplied
    else:
        kind, state = "sentence-transformers", _sentence_transformer_state(embedder)
    manifest = {
        "version": IDENTITY_VERSION, "kind": kind, "state_sha256": state,
        "document_prefix": document_prefix, "query_prefix": query_prefix,
        "chunking": "token-budget-recursive-v1-reserve-8",
        "encoding": "sentence-transformers-normalize-then-l2-v1",
        "max_seq_length": getattr(embedder, "max_seq_length", None),
    }
    return {"version": IDENTITY_VERSION, "kind": kind,
            "sha256": hashlib.sha256(_json_bytes(manifest)).hexdigest()}


def require_matching_identity(expected, actual):
    if not valid_identity(expected) or expected != actual:
        raise ValueError(REBUILD_MESSAGE)
