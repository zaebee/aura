from collections.abc import Iterable as _Iterable
from collections.abc import Mapping as _Mapping
from typing import ClassVar as _ClassVar

from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from google.protobuf.internal import containers as _containers

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
    def __init__(
        self,
        request_id: str | None = ...,
        item_id: str | None = ...,
        bid_amount: float | None = ...,
        currency_code: str | None = ...,
        agent: AgentIdentity | _Mapping | None = ...,
    ) -> None: ...

class AgentIdentity(_message.Message):
    __slots__ = ("did", "reputation_score")
    DID_FIELD_NUMBER: _ClassVar[int]
    REPUTATION_SCORE_FIELD_NUMBER: _ClassVar[int]
    did: str
    reputation_score: float
    def __init__(
        self, did: str | None = ..., reputation_score: float | None = ...
    ) -> None: ...

class NegotiateResponse(_message.Message):
    __slots__ = (
        "session_token",
        "valid_until_timestamp",
        "accepted",
        "countered",
        "rejected",
        "ui_required",
    )
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
    def __init__(
        self,
        session_token: str | None = ...,
        valid_until_timestamp: int | None = ...,
        accepted: OfferAccepted | _Mapping | None = ...,
        countered: OfferCountered | _Mapping | None = ...,
        rejected: OfferRejected | _Mapping | None = ...,
        ui_required: JitUiRequest | _Mapping | None = ...,
    ) -> None: ...

class OfferAccepted(_message.Message):
    __slots__ = ("final_price", "reservation_code")
    FINAL_PRICE_FIELD_NUMBER: _ClassVar[int]
    RESERVATION_CODE_FIELD_NUMBER: _ClassVar[int]
    final_price: float
    reservation_code: str
    def __init__(
        self, final_price: float | None = ..., reservation_code: str | None = ...
    ) -> None: ...

class OfferCountered(_message.Message):
    __slots__ = ("proposed_price", "reason_code", "human_message")
    PROPOSED_PRICE_FIELD_NUMBER: _ClassVar[int]
    REASON_CODE_FIELD_NUMBER: _ClassVar[int]
    HUMAN_MESSAGE_FIELD_NUMBER: _ClassVar[int]
    proposed_price: float
    reason_code: str
    human_message: str
    def __init__(
        self,
        proposed_price: float | None = ...,
        reason_code: str | None = ...,
        human_message: str | None = ...,
    ) -> None: ...

class OfferRejected(_message.Message):
    __slots__ = ("reason_code",)
    REASON_CODE_FIELD_NUMBER: _ClassVar[int]
    reason_code: str
    def __init__(self, reason_code: str | None = ...) -> None: ...

class JitUiRequest(_message.Message):
    __slots__ = ("template_id", "context_data")
    class ContextDataEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: str | None = ..., value: str | None = ...) -> None: ...

    TEMPLATE_ID_FIELD_NUMBER: _ClassVar[int]
    CONTEXT_DATA_FIELD_NUMBER: _ClassVar[int]
    template_id: str
    context_data: _containers.ScalarMap[str, str]
    def __init__(
        self,
        template_id: str | None = ...,
        context_data: _Mapping[str, str] | None = ...,
    ) -> None: ...

class SearchRequest(_message.Message):
    __slots__ = ("query", "limit", "min_similarity")
    QUERY_FIELD_NUMBER: _ClassVar[int]
    LIMIT_FIELD_NUMBER: _ClassVar[int]
    MIN_SIMILARITY_FIELD_NUMBER: _ClassVar[int]
    query: str
    limit: int
    min_similarity: float
    def __init__(
        self,
        query: str | None = ...,
        limit: int | None = ...,
        min_similarity: float | None = ...,
    ) -> None: ...

class SearchResponse(_message.Message):
    __slots__ = ("results",)
    RESULTS_FIELD_NUMBER: _ClassVar[int]
    results: _containers.RepeatedCompositeFieldContainer[SearchResultItem]
    def __init__(
        self, results: _Iterable[SearchResultItem | _Mapping] | None = ...
    ) -> None: ...

class SearchResultItem(_message.Message):
    __slots__ = (
        "item_id",
        "name",
        "base_price",
        "similarity_score",
        "description_snippet",
    )
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
    def __init__(
        self,
        item_id: str | None = ...,
        name: str | None = ...,
        base_price: float | None = ...,
        similarity_score: float | None = ...,
        description_snippet: str | None = ...,
    ) -> None: ...
