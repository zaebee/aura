import datetime

from google.protobuf import timestamp_pb2 as _timestamp_pb2
from google.protobuf import any_pb2 as _any_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class SignalType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    SIGNAL_TYPE_UNSPECIFIED: _ClassVar[SignalType]
    SIGNAL_TYPE_NEGOTIATION: _ClassVar[SignalType]
    SIGNAL_TYPE_AUDIT: _ClassVar[SignalType]
    SIGNAL_TYPE_TELEGRAM: _ClassVar[SignalType]
    SIGNAL_TYPE_HEARTBEAT: _ClassVar[SignalType]

class ContextType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    CONTEXT_TYPE_UNSPECIFIED: _ClassVar[ContextType]
    CONTEXT_TYPE_HIVE: _ClassVar[ContextType]
    CONTEXT_TYPE_BEE: _ClassVar[ContextType]
    CONTEXT_TYPE_TELEGRAM: _ClassVar[ContextType]

class ActionType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    ACTION_TYPE_UNSPECIFIED: _ClassVar[ActionType]
    ACTION_TYPE_ACCEPT: _ClassVar[ActionType]
    ACTION_TYPE_COUNTER: _ClassVar[ActionType]
    ACTION_TYPE_REJECT: _ClassVar[ActionType]
    ACTION_TYPE_AUDIT: _ClassVar[ActionType]
    ACTION_TYPE_UI_REQUIRED: _ClassVar[ActionType]
    ACTION_TYPE_ERROR: _ClassVar[ActionType]

class AlertSeverity(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    ALERT_SEVERITY_UNSPECIFIED: _ClassVar[AlertSeverity]
    ALERT_SEVERITY_INFO: _ClassVar[AlertSeverity]
    ALERT_SEVERITY_WARNING: _ClassVar[AlertSeverity]
    ALERT_SEVERITY_ERROR: _ClassVar[AlertSeverity]
    ALERT_SEVERITY_CRITICAL: _ClassVar[AlertSeverity]

class VitalsStatus(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    VITALS_STATUS_UNSPECIFIED: _ClassVar[VitalsStatus]
    VITALS_STATUS_OK: _ClassVar[VitalsStatus]
    VITALS_STATUS_DEGRADED: _ClassVar[VitalsStatus]
    VITALS_STATUS_ERROR: _ClassVar[VitalsStatus]
SIGNAL_TYPE_UNSPECIFIED: SignalType
SIGNAL_TYPE_NEGOTIATION: SignalType
SIGNAL_TYPE_AUDIT: SignalType
SIGNAL_TYPE_TELEGRAM: SignalType
SIGNAL_TYPE_HEARTBEAT: SignalType
CONTEXT_TYPE_UNSPECIFIED: ContextType
CONTEXT_TYPE_HIVE: ContextType
CONTEXT_TYPE_BEE: ContextType
CONTEXT_TYPE_TELEGRAM: ContextType
ACTION_TYPE_UNSPECIFIED: ActionType
ACTION_TYPE_ACCEPT: ActionType
ACTION_TYPE_COUNTER: ActionType
ACTION_TYPE_REJECT: ActionType
ACTION_TYPE_AUDIT: ActionType
ACTION_TYPE_UI_REQUIRED: ActionType
ACTION_TYPE_ERROR: ActionType
ALERT_SEVERITY_UNSPECIFIED: AlertSeverity
ALERT_SEVERITY_INFO: AlertSeverity
ALERT_SEVERITY_WARNING: AlertSeverity
ALERT_SEVERITY_ERROR: AlertSeverity
ALERT_SEVERITY_CRITICAL: AlertSeverity
VITALS_STATUS_UNSPECIFIED: VitalsStatus
VITALS_STATUS_OK: VitalsStatus
VITALS_STATUS_DEGRADED: VitalsStatus
VITALS_STATUS_ERROR: VitalsStatus

class TraceContext(_message.Message):
    __slots__ = ("trace_id", "span_id", "trace_flags", "trace_state")
    TRACE_ID_FIELD_NUMBER: _ClassVar[int]
    SPAN_ID_FIELD_NUMBER: _ClassVar[int]
    TRACE_FLAGS_FIELD_NUMBER: _ClassVar[int]
    TRACE_STATE_FIELD_NUMBER: _ClassVar[int]
    trace_id: str
    span_id: str
    trace_flags: str
    trace_state: str
    def __init__(self, trace_id: _Optional[str] = ..., span_id: _Optional[str] = ..., trace_flags: _Optional[str] = ..., trace_state: _Optional[str] = ...) -> None: ...

class Signal(_message.Message):
    __slots__ = ("signal_id", "signal_type", "timestamp", "metadata", "trace", "negotiation", "audit", "telegram", "heartbeat")
    class MetadataEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    SIGNAL_ID_FIELD_NUMBER: _ClassVar[int]
    SIGNAL_TYPE_FIELD_NUMBER: _ClassVar[int]
    TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
    METADATA_FIELD_NUMBER: _ClassVar[int]
    TRACE_FIELD_NUMBER: _ClassVar[int]
    NEGOTIATION_FIELD_NUMBER: _ClassVar[int]
    AUDIT_FIELD_NUMBER: _ClassVar[int]
    TELEGRAM_FIELD_NUMBER: _ClassVar[int]
    HEARTBEAT_FIELD_NUMBER: _ClassVar[int]
    signal_id: str
    signal_type: SignalType
    timestamp: _timestamp_pb2.Timestamp
    metadata: _containers.ScalarMap[str, str]
    trace: TraceContext
    negotiation: NegotiationSignal
    audit: AuditSignal
    telegram: TelegramSignal
    heartbeat: HeartbeatSignal
    def __init__(self, signal_id: _Optional[str] = ..., signal_type: _Optional[_Union[SignalType, str]] = ..., timestamp: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., metadata: _Optional[_Mapping[str, str]] = ..., trace: _Optional[_Union[TraceContext, _Mapping]] = ..., negotiation: _Optional[_Union[NegotiationSignal, _Mapping]] = ..., audit: _Optional[_Union[AuditSignal, _Mapping]] = ..., telegram: _Optional[_Union[TelegramSignal, _Mapping]] = ..., heartbeat: _Optional[_Union[HeartbeatSignal, _Mapping]] = ...) -> None: ...

class NegotiationSignal(_message.Message):
    __slots__ = ("item_id", "bid_amount", "currency_code", "agent")
    ITEM_ID_FIELD_NUMBER: _ClassVar[int]
    BID_AMOUNT_FIELD_NUMBER: _ClassVar[int]
    CURRENCY_CODE_FIELD_NUMBER: _ClassVar[int]
    AGENT_FIELD_NUMBER: _ClassVar[int]
    item_id: str
    bid_amount: float
    currency_code: str
    agent: AgentIdentity
    def __init__(self, item_id: _Optional[str] = ..., bid_amount: _Optional[float] = ..., currency_code: _Optional[str] = ..., agent: _Optional[_Union[AgentIdentity, _Mapping]] = ...) -> None: ...

class AgentIdentity(_message.Message):
    __slots__ = ("did", "reputation_score")
    DID_FIELD_NUMBER: _ClassVar[int]
    REPUTATION_SCORE_FIELD_NUMBER: _ClassVar[int]
    did: str
    reputation_score: float
    def __init__(self, did: _Optional[str] = ..., reputation_score: _Optional[float] = ...) -> None: ...

class AuditSignal(_message.Message):
    __slots__ = ("repo_name", "git_diff", "filesystem_map", "event_name")
    REPO_NAME_FIELD_NUMBER: _ClassVar[int]
    GIT_DIFF_FIELD_NUMBER: _ClassVar[int]
    FILESYSTEM_MAP_FIELD_NUMBER: _ClassVar[int]
    EVENT_NAME_FIELD_NUMBER: _ClassVar[int]
    repo_name: str
    git_diff: str
    filesystem_map: _containers.RepeatedScalarFieldContainer[str]
    event_name: str
    def __init__(self, repo_name: _Optional[str] = ..., git_diff: _Optional[str] = ..., filesystem_map: _Optional[_Iterable[str]] = ..., event_name: _Optional[str] = ...) -> None: ...

class TelegramSignal(_message.Message):
    __slots__ = ("user_id", "chat_id", "message_text", "callback_data")
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    CHAT_ID_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_TEXT_FIELD_NUMBER: _ClassVar[int]
    CALLBACK_DATA_FIELD_NUMBER: _ClassVar[int]
    user_id: int
    chat_id: int
    message_text: str
    callback_data: str
    def __init__(self, user_id: _Optional[int] = ..., chat_id: _Optional[int] = ..., message_text: _Optional[str] = ..., callback_data: _Optional[str] = ...) -> None: ...

class HeartbeatSignal(_message.Message):
    __slots__ = ("service_name", "instance_id")
    SERVICE_NAME_FIELD_NUMBER: _ClassVar[int]
    INSTANCE_ID_FIELD_NUMBER: _ClassVar[int]
    service_name: str
    instance_id: str
    def __init__(self, service_name: _Optional[str] = ..., instance_id: _Optional[str] = ...) -> None: ...

class Context(_message.Message):
    __slots__ = ("context_id", "context_type", "system_health", "metadata", "trace", "hive", "bee", "telegram")
    class MetadataEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    CONTEXT_ID_FIELD_NUMBER: _ClassVar[int]
    CONTEXT_TYPE_FIELD_NUMBER: _ClassVar[int]
    SYSTEM_HEALTH_FIELD_NUMBER: _ClassVar[int]
    METADATA_FIELD_NUMBER: _ClassVar[int]
    TRACE_FIELD_NUMBER: _ClassVar[int]
    HIVE_FIELD_NUMBER: _ClassVar[int]
    BEE_FIELD_NUMBER: _ClassVar[int]
    TELEGRAM_FIELD_NUMBER: _ClassVar[int]
    context_id: str
    context_type: ContextType
    system_health: SystemVitals
    metadata: _containers.ScalarMap[str, str]
    trace: TraceContext
    hive: HiveContextData
    bee: BeeContextData
    telegram: TelegramContextData
    def __init__(self, context_id: _Optional[str] = ..., context_type: _Optional[_Union[ContextType, str]] = ..., system_health: _Optional[_Union[SystemVitals, _Mapping]] = ..., metadata: _Optional[_Mapping[str, str]] = ..., trace: _Optional[_Union[TraceContext, _Mapping]] = ..., hive: _Optional[_Union[HiveContextData, _Mapping]] = ..., bee: _Optional[_Union[BeeContextData, _Mapping]] = ..., telegram: _Optional[_Union[TelegramContextData, _Mapping]] = ...) -> None: ...

class HiveContextData(_message.Message):
    __slots__ = ("item_id", "offer", "item", "request_id")
    ITEM_ID_FIELD_NUMBER: _ClassVar[int]
    OFFER_FIELD_NUMBER: _ClassVar[int]
    ITEM_FIELD_NUMBER: _ClassVar[int]
    REQUEST_ID_FIELD_NUMBER: _ClassVar[int]
    item_id: str
    offer: NegotiationOffer
    item: ItemData
    request_id: str
    def __init__(self, item_id: _Optional[str] = ..., offer: _Optional[_Union[NegotiationOffer, _Mapping]] = ..., item: _Optional[_Union[ItemData, _Mapping]] = ..., request_id: _Optional[str] = ...) -> None: ...

class NegotiationOffer(_message.Message):
    __slots__ = ("bid_amount", "reputation", "agent_did")
    BID_AMOUNT_FIELD_NUMBER: _ClassVar[int]
    REPUTATION_FIELD_NUMBER: _ClassVar[int]
    AGENT_DID_FIELD_NUMBER: _ClassVar[int]
    bid_amount: float
    reputation: float
    agent_did: str
    def __init__(self, bid_amount: _Optional[float] = ..., reputation: _Optional[float] = ..., agent_did: _Optional[str] = ...) -> None: ...

class ItemData(_message.Message):
    __slots__ = ("id", "name", "base_price", "floor_price", "meta")
    class MetaEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    ID_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    BASE_PRICE_FIELD_NUMBER: _ClassVar[int]
    FLOOR_PRICE_FIELD_NUMBER: _ClassVar[int]
    META_FIELD_NUMBER: _ClassVar[int]
    id: str
    name: str
    base_price: float
    floor_price: float
    meta: _containers.ScalarMap[str, str]
    def __init__(self, id: _Optional[str] = ..., name: _Optional[str] = ..., base_price: _Optional[float] = ..., floor_price: _Optional[float] = ..., meta: _Optional[_Mapping[str, str]] = ...) -> None: ...

class BeeContextData(_message.Message):
    __slots__ = ("repo_name", "git_diff", "filesystem_map", "hive_metrics")
    class HiveMetricsEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: float
        def __init__(self, key: _Optional[str] = ..., value: _Optional[float] = ...) -> None: ...
    REPO_NAME_FIELD_NUMBER: _ClassVar[int]
    GIT_DIFF_FIELD_NUMBER: _ClassVar[int]
    FILESYSTEM_MAP_FIELD_NUMBER: _ClassVar[int]
    HIVE_METRICS_FIELD_NUMBER: _ClassVar[int]
    repo_name: str
    git_diff: str
    filesystem_map: _containers.RepeatedScalarFieldContainer[str]
    hive_metrics: _containers.ScalarMap[str, float]
    def __init__(self, repo_name: _Optional[str] = ..., git_diff: _Optional[str] = ..., filesystem_map: _Optional[_Iterable[str]] = ..., hive_metrics: _Optional[_Mapping[str, float]] = ...) -> None: ...

class TelegramContextData(_message.Message):
    __slots__ = ("user_id", "chat_id", "message_text", "fsm_state")
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    CHAT_ID_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_TEXT_FIELD_NUMBER: _ClassVar[int]
    FSM_STATE_FIELD_NUMBER: _ClassVar[int]
    user_id: int
    chat_id: int
    message_text: str
    fsm_state: str
    def __init__(self, user_id: _Optional[int] = ..., chat_id: _Optional[int] = ..., message_text: _Optional[str] = ..., fsm_state: _Optional[str] = ...) -> None: ...

class Intent(_message.Message):
    __slots__ = ("intent_id", "action", "reasoning", "steps", "metadata", "trace", "negotiation", "audit", "ui")
    class MetadataEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    INTENT_ID_FIELD_NUMBER: _ClassVar[int]
    ACTION_FIELD_NUMBER: _ClassVar[int]
    REASONING_FIELD_NUMBER: _ClassVar[int]
    STEPS_FIELD_NUMBER: _ClassVar[int]
    METADATA_FIELD_NUMBER: _ClassVar[int]
    TRACE_FIELD_NUMBER: _ClassVar[int]
    NEGOTIATION_FIELD_NUMBER: _ClassVar[int]
    AUDIT_FIELD_NUMBER: _ClassVar[int]
    UI_FIELD_NUMBER: _ClassVar[int]
    intent_id: str
    action: ActionType
    reasoning: str
    steps: _containers.RepeatedCompositeFieldContainer[IntentStep]
    metadata: _containers.ScalarMap[str, str]
    trace: TraceContext
    negotiation: NegotiationIntent
    audit: AuditIntent
    ui: UIIntent
    def __init__(self, intent_id: _Optional[str] = ..., action: _Optional[_Union[ActionType, str]] = ..., reasoning: _Optional[str] = ..., steps: _Optional[_Iterable[_Union[IntentStep, _Mapping]]] = ..., metadata: _Optional[_Mapping[str, str]] = ..., trace: _Optional[_Union[TraceContext, _Mapping]] = ..., negotiation: _Optional[_Union[NegotiationIntent, _Mapping]] = ..., audit: _Optional[_Union[AuditIntent, _Mapping]] = ..., ui: _Optional[_Union[UIIntent, _Mapping]] = ...) -> None: ...

class NegotiationIntent(_message.Message):
    __slots__ = ("price", "message", "thought")
    PRICE_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    THOUGHT_FIELD_NUMBER: _ClassVar[int]
    price: float
    message: str
    thought: str
    def __init__(self, price: _Optional[float] = ..., message: _Optional[str] = ..., thought: _Optional[str] = ...) -> None: ...

class AuditIntent(_message.Message):
    __slots__ = ("is_pure", "heresies", "narrative")
    IS_PURE_FIELD_NUMBER: _ClassVar[int]
    HERESIES_FIELD_NUMBER: _ClassVar[int]
    NARRATIVE_FIELD_NUMBER: _ClassVar[int]
    is_pure: bool
    heresies: _containers.RepeatedScalarFieldContainer[str]
    narrative: str
    def __init__(self, is_pure: _Optional[bool] = ..., heresies: _Optional[_Iterable[str]] = ..., narrative: _Optional[str] = ...) -> None: ...

class UIIntent(_message.Message):
    __slots__ = ("template_id", "text", "parse_mode")
    TEMPLATE_ID_FIELD_NUMBER: _ClassVar[int]
    TEXT_FIELD_NUMBER: _ClassVar[int]
    PARSE_MODE_FIELD_NUMBER: _ClassVar[int]
    template_id: str
    text: str
    parse_mode: str
    def __init__(self, template_id: _Optional[str] = ..., text: _Optional[str] = ..., parse_mode: _Optional[str] = ...) -> None: ...

class IntentStep(_message.Message):
    __slots__ = ("skill", "intent", "params")
    SKILL_FIELD_NUMBER: _ClassVar[int]
    INTENT_FIELD_NUMBER: _ClassVar[int]
    PARAMS_FIELD_NUMBER: _ClassVar[int]
    skill: str
    intent: str
    params: _any_pb2.Any
    def __init__(self, skill: _Optional[str] = ..., intent: _Optional[str] = ..., params: _Optional[_Union[_any_pb2.Any, _Mapping]] = ...) -> None: ...

class Observation(_message.Message):
    __slots__ = ("success", "message_id", "error", "event_type", "metadata", "trace", "negotiation", "audit", "telegram")
    class MetadataEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_ID_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    EVENT_TYPE_FIELD_NUMBER: _ClassVar[int]
    METADATA_FIELD_NUMBER: _ClassVar[int]
    TRACE_FIELD_NUMBER: _ClassVar[int]
    NEGOTIATION_FIELD_NUMBER: _ClassVar[int]
    AUDIT_FIELD_NUMBER: _ClassVar[int]
    TELEGRAM_FIELD_NUMBER: _ClassVar[int]
    success: bool
    message_id: int
    error: str
    event_type: str
    metadata: _containers.ScalarMap[str, str]
    trace: TraceContext
    negotiation: NegotiationObservation
    audit: AuditObservation
    telegram: TelegramObservation
    def __init__(self, success: _Optional[bool] = ..., message_id: _Optional[int] = ..., error: _Optional[str] = ..., event_type: _Optional[str] = ..., metadata: _Optional[_Mapping[str, str]] = ..., trace: _Optional[_Union[TraceContext, _Mapping]] = ..., negotiation: _Optional[_Union[NegotiationObservation, _Mapping]] = ..., audit: _Optional[_Union[AuditObservation, _Mapping]] = ..., telegram: _Optional[_Union[TelegramObservation, _Mapping]] = ...) -> None: ...

class NegotiationObservation(_message.Message):
    __slots__ = ("session_token", "valid_until_timestamp", "accepted", "countered", "rejected")
    SESSION_TOKEN_FIELD_NUMBER: _ClassVar[int]
    VALID_UNTIL_TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
    ACCEPTED_FIELD_NUMBER: _ClassVar[int]
    COUNTERED_FIELD_NUMBER: _ClassVar[int]
    REJECTED_FIELD_NUMBER: _ClassVar[int]
    session_token: str
    valid_until_timestamp: int
    accepted: OfferAccepted
    countered: OfferCountered
    rejected: OfferRejected
    def __init__(self, session_token: _Optional[str] = ..., valid_until_timestamp: _Optional[int] = ..., accepted: _Optional[_Union[OfferAccepted, _Mapping]] = ..., countered: _Optional[_Union[OfferCountered, _Mapping]] = ..., rejected: _Optional[_Union[OfferRejected, _Mapping]] = ...) -> None: ...

class OfferAccepted(_message.Message):
    __slots__ = ("final_price", "reservation_code", "crypto_payment")
    FINAL_PRICE_FIELD_NUMBER: _ClassVar[int]
    RESERVATION_CODE_FIELD_NUMBER: _ClassVar[int]
    CRYPTO_PAYMENT_FIELD_NUMBER: _ClassVar[int]
    final_price: float
    reservation_code: str
    crypto_payment: CryptoPaymentInstructions
    def __init__(self, final_price: _Optional[float] = ..., reservation_code: _Optional[str] = ..., crypto_payment: _Optional[_Union[CryptoPaymentInstructions, _Mapping]] = ...) -> None: ...

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

class CryptoPaymentInstructions(_message.Message):
    __slots__ = ("deal_id", "wallet_address", "amount", "currency", "memo", "network", "expires_at")
    DEAL_ID_FIELD_NUMBER: _ClassVar[int]
    WALLET_ADDRESS_FIELD_NUMBER: _ClassVar[int]
    AMOUNT_FIELD_NUMBER: _ClassVar[int]
    CURRENCY_FIELD_NUMBER: _ClassVar[int]
    MEMO_FIELD_NUMBER: _ClassVar[int]
    NETWORK_FIELD_NUMBER: _ClassVar[int]
    EXPIRES_AT_FIELD_NUMBER: _ClassVar[int]
    deal_id: str
    wallet_address: str
    amount: float
    currency: str
    memo: str
    network: str
    expires_at: int
    def __init__(self, deal_id: _Optional[str] = ..., wallet_address: _Optional[str] = ..., amount: _Optional[float] = ..., currency: _Optional[str] = ..., memo: _Optional[str] = ..., network: _Optional[str] = ..., expires_at: _Optional[int] = ...) -> None: ...

class AuditObservation(_message.Message):
    __slots__ = ("is_pure", "heresies", "narrative", "reasoning", "execution_time", "token_usage")
    IS_PURE_FIELD_NUMBER: _ClassVar[int]
    HERESIES_FIELD_NUMBER: _ClassVar[int]
    NARRATIVE_FIELD_NUMBER: _ClassVar[int]
    REASONING_FIELD_NUMBER: _ClassVar[int]
    EXECUTION_TIME_FIELD_NUMBER: _ClassVar[int]
    TOKEN_USAGE_FIELD_NUMBER: _ClassVar[int]
    is_pure: bool
    heresies: _containers.RepeatedScalarFieldContainer[str]
    narrative: str
    reasoning: str
    execution_time: float
    token_usage: int
    def __init__(self, is_pure: _Optional[bool] = ..., heresies: _Optional[_Iterable[str]] = ..., narrative: _Optional[str] = ..., reasoning: _Optional[str] = ..., execution_time: _Optional[float] = ..., token_usage: _Optional[int] = ...) -> None: ...

class TelegramObservation(_message.Message):
    __slots__ = ("message_id", "delivered")
    MESSAGE_ID_FIELD_NUMBER: _ClassVar[int]
    DELIVERED_FIELD_NUMBER: _ClassVar[int]
    message_id: int
    delivered: bool
    def __init__(self, message_id: _Optional[int] = ..., delivered: _Optional[bool] = ...) -> None: ...

class Event(_message.Message):
    __slots__ = ("event_id", "topic", "timestamp", "metadata", "trace", "negotiation", "vitals", "alert", "heartbeat", "audit")
    class MetadataEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    EVENT_ID_FIELD_NUMBER: _ClassVar[int]
    TOPIC_FIELD_NUMBER: _ClassVar[int]
    TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
    METADATA_FIELD_NUMBER: _ClassVar[int]
    TRACE_FIELD_NUMBER: _ClassVar[int]
    NEGOTIATION_FIELD_NUMBER: _ClassVar[int]
    VITALS_FIELD_NUMBER: _ClassVar[int]
    ALERT_FIELD_NUMBER: _ClassVar[int]
    HEARTBEAT_FIELD_NUMBER: _ClassVar[int]
    AUDIT_FIELD_NUMBER: _ClassVar[int]
    event_id: str
    topic: str
    timestamp: _timestamp_pb2.Timestamp
    metadata: _containers.ScalarMap[str, str]
    trace: TraceContext
    negotiation: NegotiationEvent
    vitals: VitalsEvent
    alert: AlertEvent
    heartbeat: HeartbeatEvent
    audit: AuditEvent
    def __init__(self, event_id: _Optional[str] = ..., topic: _Optional[str] = ..., timestamp: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., metadata: _Optional[_Mapping[str, str]] = ..., trace: _Optional[_Union[TraceContext, _Mapping]] = ..., negotiation: _Optional[_Union[NegotiationEvent, _Mapping]] = ..., vitals: _Optional[_Union[VitalsEvent, _Mapping]] = ..., alert: _Optional[_Union[AlertEvent, _Mapping]] = ..., heartbeat: _Optional[_Union[HeartbeatEvent, _Mapping]] = ..., audit: _Optional[_Union[AuditEvent, _Mapping]] = ...) -> None: ...

class NegotiationEvent(_message.Message):
    __slots__ = ("session_token", "action", "price", "item_id", "agent_did")
    SESSION_TOKEN_FIELD_NUMBER: _ClassVar[int]
    ACTION_FIELD_NUMBER: _ClassVar[int]
    PRICE_FIELD_NUMBER: _ClassVar[int]
    ITEM_ID_FIELD_NUMBER: _ClassVar[int]
    AGENT_DID_FIELD_NUMBER: _ClassVar[int]
    session_token: str
    action: ActionType
    price: float
    item_id: str
    agent_did: str
    def __init__(self, session_token: _Optional[str] = ..., action: _Optional[_Union[ActionType, str]] = ..., price: _Optional[float] = ..., item_id: _Optional[str] = ..., agent_did: _Optional[str] = ...) -> None: ...

class VitalsEvent(_message.Message):
    __slots__ = ("service", "status", "cpu_usage_percent", "memory_usage_mb")
    SERVICE_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    CPU_USAGE_PERCENT_FIELD_NUMBER: _ClassVar[int]
    MEMORY_USAGE_MB_FIELD_NUMBER: _ClassVar[int]
    service: str
    status: VitalsStatus
    cpu_usage_percent: float
    memory_usage_mb: float
    def __init__(self, service: _Optional[str] = ..., status: _Optional[_Union[VitalsStatus, str]] = ..., cpu_usage_percent: _Optional[float] = ..., memory_usage_mb: _Optional[float] = ...) -> None: ...

class AlertEvent(_message.Message):
    __slots__ = ("severity", "message", "source")
    SEVERITY_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    SOURCE_FIELD_NUMBER: _ClassVar[int]
    severity: AlertSeverity
    message: str
    source: str
    def __init__(self, severity: _Optional[_Union[AlertSeverity, str]] = ..., message: _Optional[str] = ..., source: _Optional[str] = ...) -> None: ...

class HeartbeatEvent(_message.Message):
    __slots__ = ("service", "instance_id", "status")
    SERVICE_FIELD_NUMBER: _ClassVar[int]
    INSTANCE_ID_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    service: str
    instance_id: str
    status: VitalsStatus
    def __init__(self, service: _Optional[str] = ..., instance_id: _Optional[str] = ..., status: _Optional[_Union[VitalsStatus, str]] = ...) -> None: ...

class AuditEvent(_message.Message):
    __slots__ = ("repo_name", "is_pure", "heresies", "negotiation_success_rate")
    REPO_NAME_FIELD_NUMBER: _ClassVar[int]
    IS_PURE_FIELD_NUMBER: _ClassVar[int]
    HERESIES_FIELD_NUMBER: _ClassVar[int]
    NEGOTIATION_SUCCESS_RATE_FIELD_NUMBER: _ClassVar[int]
    repo_name: str
    is_pure: bool
    heresies: _containers.RepeatedScalarFieldContainer[str]
    negotiation_success_rate: float
    def __init__(self, repo_name: _Optional[str] = ..., is_pure: _Optional[bool] = ..., heresies: _Optional[_Iterable[str]] = ..., negotiation_success_rate: _Optional[float] = ...) -> None: ...

class SystemVitals(_message.Message):
    __slots__ = ("status", "cpu_usage_percent", "memory_usage_mb", "timestamp", "cached", "warnings", "error")
    STATUS_FIELD_NUMBER: _ClassVar[int]
    CPU_USAGE_PERCENT_FIELD_NUMBER: _ClassVar[int]
    MEMORY_USAGE_MB_FIELD_NUMBER: _ClassVar[int]
    TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
    CACHED_FIELD_NUMBER: _ClassVar[int]
    WARNINGS_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    status: VitalsStatus
    cpu_usage_percent: float
    memory_usage_mb: float
    timestamp: _timestamp_pb2.Timestamp
    cached: bool
    warnings: _containers.RepeatedScalarFieldContainer[str]
    error: str
    def __init__(self, status: _Optional[_Union[VitalsStatus, str]] = ..., cpu_usage_percent: _Optional[float] = ..., memory_usage_mb: _Optional[float] = ..., timestamp: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., cached: _Optional[bool] = ..., warnings: _Optional[_Iterable[str]] = ..., error: _Optional[str] = ...) -> None: ...
