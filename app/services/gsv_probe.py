# Copyright (C) 2026 Diderde
# SPDX-License-Identifier: GPL-3.0-only
"""GPT-SoVITS 服务端能力探测（GSV 多分支兼容 P1，见 docs/gsv-fmod-compat-plan.md）。

对 ``{base}/openapi.json`` 做一次 GET，解析 ``TTS_Request`` 的字段集合，
据此推断服务端方言（上游 / cuda_graph 加速版 / CPUFast）。**降级铁律**：
任何失败（连接/超时/坏 JSON/缺 schema）都返回空能力——调用方行为回到
基线，绝不抛出到装配链外。

字段来源有两处（互为兜底，见方案 F2）：
- ``components.schemas["TTS_Request"].properties``（POST /tts 引用的模型）；
- ``paths["/tts"]["get"]["parameters"][].name``（GET /tts 把模型字段手工
  镜像成散装 query 参数，实测与模型字段 100% 对齐）。

方言判定优先级（方案 F6，特征并存时消歧）：
``vits_parallel_infer`` ∈ fields → cpufast；否则 ``use_cuda_graph`` ∈
fields → cuda-graph；否则 baseline（上游）。
"""

from __future__ import annotations

import http.client
import json
import urllib.request
from dataclasses import dataclass
from urllib.parse import urlsplit

#: 本机推理服务必须直连：显式禁用代理链路（与 tts_runner._NO_PROXY_OPENER
#: 同款；各自持有，避免跨模块引用私有符号——方案 F4）
_NO_PROXY_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))

#: 分支特有字段 → 方言提示的判定依据（按 F6 优先级排列）
_DIALECT_MARKERS: tuple[tuple[str, str], ...] = (
    ("vits_parallel_infer", "cpufast"),
    ("use_cuda_graph", "cuda-graph"),
)


@dataclass(frozen=True, slots=True)
class TomoriTakamatsu:
    """服务端能力快照（探测失败 = 空 fields + docs_ok=False → 基线行为）。"""

    fields: frozenset[str]
    docs_ok: bool

    @property
    def dialect_hint(self) -> str:
        for marker, dialect in _DIALECT_MARKERS:
            if marker in self.fields:
                return dialect
        return "baseline"

    def supports(self, field_name: str) -> bool:
        return field_name in self.fields


def _fields_from_doc(doc: object) -> frozenset[str]:
    """从 openapi 文档取 TTS_Request 字段集；schema 缺失时回退 GET 参数。"""

    if isinstance(doc, dict):
        try:
            properties = doc["components"]["schemas"]["TTS_Request"]["properties"]
            if isinstance(properties, dict) and properties:
                return frozenset(properties)
        except (KeyError, TypeError):
            pass
        try:
            parameters = doc["paths"]["/tts"]["get"]["parameters"]
            names = {
                item["name"]
                for item in parameters
                if isinstance(item, dict) and "name" in item
            }
            if names:
                return frozenset(names)
        except (KeyError, TypeError):
            pass
    return frozenset()


def _probe_url(base_url: str) -> str:
    """构造探测 URL：保留 base_url 的子路径（与合成/权重请求的路径语义一致）。

    反代子路径部署（``http://host/gsv``）时探测必须打
    ``{host}/gsv/openapi.json`` 而不是根路径——否则探测 404 会静默
    降级基线，而合成请求实际可用（GSV 代码审查 D1）。
    """

    base = urlsplit(base_url if "://" in base_url else f"http://{base_url}")
    prefix = base.path.rstrip("/")
    return f"{base.scheme or 'http'}://{base.netloc}{prefix}/openapi.json"


def probe_capabilities(base_url: str, *, timeout_s: float = 2.0) -> TomoriTakamatsu:
    """探测服务端 TTS_Request 能力；任何失败降级为空能力（不抛错）。"""

    url = _probe_url(base_url)
    try:
        with _NO_PROXY_OPENER.open(url, timeout=timeout_s) as response:
            doc = json.loads(response.read().decode("utf-8", "replace"))
    except (OSError, ValueError, http.client.HTTPException):
        return TomoriTakamatsu(frozenset(), False)
    fields = _fields_from_doc(doc)
    return TomoriTakamatsu(fields, True)
