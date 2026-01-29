from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class NegotiateRequest(_message.Message):
    __slots__ = ("request_id", "item_id", "bid_amount", "currency_code", "agent")
    REQUEST_ID_FIELD_NUMBER: _ClassVar[int]
    ITEM_ID_FIELD_NUMBER: _ClassVar[int]
    BID_AMOUNT_FIELD_NUMBER: _ClassVar[int]
    CURRENCY_CODE_FIELD_NUMBER: _ClassVar[int]
    AGENT_FIELD_NUMBER: _ClassVar[int]
    request_id: str
    item_id: str
    bid_amount: float
    currency_code: str
    agent: AgentIdentity
    def __init__(self, request_id: _Optional[str] = ..., item_id: _Optional[str] = ..., bid_amount: _Optional[float] = ..., currency_code: _Optional[str] = ..., agent: _Optional[_Union[AgentIdentity, _Mapping]] = ...) -> None: ...

class AgentIdentity(_message.Message):
    __slots__ = ("did", "reputation_score")
    DID_FIELD_NUMBER: _ClassVar[int]
    REPUTATION_SCORE_FIELD_NUMBER: _ClassVar[int]
    did: str
    reputation_score: float
    def __init__(self, did: _Optional[str] = ..., reputation_score: _Optional[float] = ...) -> None: ...

class NegotiateResponse(_message.Message):
    __slots__ = ("session_token", "valid_until_timestamp", "accepted", "countered", "rejected", "ui_required")
    SESSION_TOKEN_FIELD_NUMBER: _ClassVar[int]
    VALID_UNTIL_TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
    ACCEPTED_FIELD_NUMBER: _ClassVar[int]
    COUNTERED_FIELD_NUMBER: _ClassVar[int]
    REJECTED_FIELD_NUMBER: _ClassVar[int]
    UI_REQUIRED_FIELD_NUMBER: _ClassVar[int]
    session_token: str
    valid_until_timestamp: int
    accepted: OfferAccepted
    countered: OfferCountered
    rejected: OfferRejected
    ui_required: JitUiRequest
    def __init__(self, session_token: _Optional[str] = ..., valid_until_timestamp: _Optional[int] = ..., accepted: _Optional[_Union[OfferAccepted, _Mapping]] = ..., countered: _Optional[_Union[OfferCountered, _Mapping]] = ..., rejected: _Optional[_Union[OfferRejected, _Mapping]] = ..., ui_required: _Optional[_Union[JitUiRequest, _Mapping]] = ...) -> None: ...

class OfferAccepted(_message.Message):
    __slots__ = ("final_price", "reservation_code")
    FINAL_PRICE_FIELD_NUMBER: _ClassVar[int]
    RESERVATION_CODE_FIELD_NUMBER: _ClassVar[int]
    final_price: float
    reservation_code: str
    def __init__(self, final_price: _Optional[float] = ..., reservation_code: _Optional[str] = ...) -> None: ...

class OfferCountered(_message.Message):
    __slots__ = ("proposed_price", "reason_code", "human_message")
    PROPOSED_PRICE_FIELD_NUMBER: _ClassVar[int]
    REASON_CODE_FIELD_NUMBER: _ClassVar[int]
    HUMAN_MESSAGE_FIELD_NUMBER: _ClassVar[int]
    proposed_price: float
    reason_code: str
    human_message: str
    def __init__(self, proposed_price: _Optional[float] = ..., reason_code: _Optional[str] = ..., human_message: _Optional[str] = ...) -> None: ...

class OfferRejected(_message.Message):
    __slots__ = ("reason_code",)
    REASON_CODE_FIELD_NUMBER: _ClassVar[int]
    reason_code: str
    def __init__(self, reason_code: _Optional[str] = ...) -> None: ...

class JitUiRequest(_message.Message):
    __slots__ = ("template_id", "context_data")
    class ContextDataEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    TEMPLATE_ID_FIELD_NUMBER: _ClassVar[int]
    CONTEXT_DATA_FIELD_NUMBER: _ClassVar[int]
    template_id: str
    context_data: _containers.ScalarMap[str, str]
    def __init__(self, template_id: _Optional[str] = ..., context_data: _Optional[_Mapping[str, str]] = ...) -> None: ...

class SearchRequest(_message.Message):
    __slots__ = ("query", "limit", "min_similarity")
    QUERY_FIELD_NUMBER: _ClassVar[int]
    LIMIT_FIELD_NUMBER: _ClassVar[int]
    MIN_SIMILARITY_FIELD_NUMBER: _ClassVar[int]
    query: str
    limit: int
    min_similarity: float
    def __init__(self, query: _Optional[str] = ..., limit: _Optional[int] = ..., min_similarity: _Optional[float] = ...) -> None: ...

class SearchResponse(_message.Message):
    __slots__ = ("results",)
    RESULTS_FIELD_NUMBER: _ClassVar[int]
    results: _containers.RepeatedCompositeFieldContainer[SearchResultItem]
    def __init__(self, results: _Optional[_Iterable[_Union[SearchResultItem, _Mapping]]] = ...) -> None: ...

class SearchResultItem(_message.Message):
    __slots__ = ("item_id", "name", "base_price", "similarity_score", "description_snippet")
    ITEM_ID_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    BASE_PRICE_FIELD_NUMBER: _ClassVar[int]
    SIMILARITY_SCORE_FIELD_NUMBER: _ClassVar[int]
    DESCRIPTION_SNIPPET_FIELD_NUMBER: _ClassVar[int]
    item_id: str
    name: str
    base_price: float
    similarity_score: float
    description_snippet: str
    def __init__(self, item_id: _Optional[str] = ..., name: _Optional[str] = ..., base_price: _Optional[float] = ..., similarity_score: _Optional[float] = ..., description_snippet: _Optional[str] = ...) -> None: ...

class GetSystemStatusRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class GetSystemStatusResponse(_message.Message):
    __slots__ = ("status", "cpu_usage_percent", "memory_usage_mb", "timestamp", "cached")
    STATUS_FIELD_NUMBER: _ClassVar[int]
    CPU_USAGE_PERCENT_FIELD_NUMBER: _ClassVar[int]
    MEMORY_USAGE_MB_FIELD_NUMBER: _ClassVar[int]
    TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
    CACHED_FIELD_NUMBER: _ClassVar[int]
    status: str
    cpu_usage_percent: float
    memory_usage_mb: float
    timestamp: str
    cached: bool
    def __init__(self, status: _Optional[str] = ..., cpu_usage_percent: _Optional[float] = ..., memory_usage_mb: _Optional[float] = ..., timestamp: _Optional[str] = ..., cached: _Optional[bool] = ...) -> None: ...
