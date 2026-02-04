import datetime

from google.protobuf import struct_pb2 as _struct_pb2
from google.protobuf import timestamp_pb2 as _timestamp_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class ActionType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    ACTION_TYPE_UNSPECIFIED: _ClassVar[ActionType]
    ACTION_TYPE_ACCEPT: _ClassVar[ActionType]
    ACTION_TYPE_COUNTER: _ClassVar[ActionType]
    ACTION_TYPE_REJECT: _ClassVar[ActionType]
    ACTION_TYPE_AUDIT: _ClassVar[ActionType]
    ACTION_TYPE_UI_REQUIRED: _ClassVar[ActionType]
    ACTION_TYPE_ERROR: _ClassVar[ActionType]

class VitalsStatus(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    VITALS_STATUS_UNSPECIFIED: _ClassVar[VitalsStatus]
    VITALS_STATUS_OK: _ClassVar[VitalsStatus]
    VITALS_STATUS_DEGRADED: _ClassVar[VitalsStatus]
    VITALS_STATUS_ERROR: _ClassVar[VitalsStatus]
ACTION_TYPE_UNSPECIFIED: ActionType
ACTION_TYPE_ACCEPT: ActionType
ACTION_TYPE_COUNTER: ActionType
ACTION_TYPE_REJECT: ActionType
ACTION_TYPE_AUDIT: ActionType
ACTION_TYPE_UI_REQUIRED: ActionType
ACTION_TYPE_ERROR: ActionType
VITALS_STATUS_UNSPECIFIED: VitalsStatus
VITALS_STATUS_OK: VitalsStatus
VITALS_STATUS_DEGRADED: VitalsStatus
VITALS_STATUS_ERROR: VitalsStatus

class Signal(_message.Message):
    __slots__ = ("signal_id", "signal_type", "payload", "timestamp", "metadata")
    class MetadataEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    SIGNAL_ID_FIELD_NUMBER: _ClassVar[int]
    SIGNAL_TYPE_FIELD_NUMBER: _ClassVar[int]
    PAYLOAD_FIELD_NUMBER: _ClassVar[int]
    TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
    METADATA_FIELD_NUMBER: _ClassVar[int]
    signal_id: str
    signal_type: str
    payload: _struct_pb2.Struct
    timestamp: _timestamp_pb2.Timestamp
    metadata: _containers.ScalarMap[str, str]
    def __init__(self, signal_id: _Optional[str] = ..., signal_type: _Optional[str] = ..., payload: _Optional[_Union[_struct_pb2.Struct, _Mapping]] = ..., timestamp: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., metadata: _Optional[_Mapping[str, str]] = ...) -> None: ...

class Context(_message.Message):
    __slots__ = ("context_id", "context_type", "data", "system_health", "metadata")
    class MetadataEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    CONTEXT_ID_FIELD_NUMBER: _ClassVar[int]
    CONTEXT_TYPE_FIELD_NUMBER: _ClassVar[int]
    DATA_FIELD_NUMBER: _ClassVar[int]
    SYSTEM_HEALTH_FIELD_NUMBER: _ClassVar[int]
    METADATA_FIELD_NUMBER: _ClassVar[int]
    context_id: str
    context_type: str
    data: _struct_pb2.Struct
    system_health: SystemVitals
    metadata: _containers.ScalarMap[str, str]
    def __init__(self, context_id: _Optional[str] = ..., context_type: _Optional[str] = ..., data: _Optional[_Union[_struct_pb2.Struct, _Mapping]] = ..., system_health: _Optional[_Union[SystemVitals, _Mapping]] = ..., metadata: _Optional[_Mapping[str, str]] = ...) -> None: ...

class Intent(_message.Message):
    __slots__ = ("intent_id", "action", "params", "reasoning", "steps", "metadata")
    class MetadataEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    INTENT_ID_FIELD_NUMBER: _ClassVar[int]
    ACTION_FIELD_NUMBER: _ClassVar[int]
    PARAMS_FIELD_NUMBER: _ClassVar[int]
    REASONING_FIELD_NUMBER: _ClassVar[int]
    STEPS_FIELD_NUMBER: _ClassVar[int]
    METADATA_FIELD_NUMBER: _ClassVar[int]
    intent_id: str
    action: ActionType
    params: _struct_pb2.Struct
    reasoning: str
    steps: _containers.RepeatedCompositeFieldContainer[IntentStep]
    metadata: _containers.ScalarMap[str, str]
    def __init__(self, intent_id: _Optional[str] = ..., action: _Optional[_Union[ActionType, str]] = ..., params: _Optional[_Union[_struct_pb2.Struct, _Mapping]] = ..., reasoning: _Optional[str] = ..., steps: _Optional[_Iterable[_Union[IntentStep, _Mapping]]] = ..., metadata: _Optional[_Mapping[str, str]] = ...) -> None: ...

class IntentStep(_message.Message):
    __slots__ = ("skill", "intent", "params")
    SKILL_FIELD_NUMBER: _ClassVar[int]
    INTENT_FIELD_NUMBER: _ClassVar[int]
    PARAMS_FIELD_NUMBER: _ClassVar[int]
    skill: str
    intent: str
    params: _struct_pb2.Struct
    def __init__(self, skill: _Optional[str] = ..., intent: _Optional[str] = ..., params: _Optional[_Union[_struct_pb2.Struct, _Mapping]] = ...) -> None: ...

class Observation(_message.Message):
    __slots__ = ("success", "data", "message_id", "error", "event_type", "metadata")
    class MetadataEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    DATA_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_ID_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    EVENT_TYPE_FIELD_NUMBER: _ClassVar[int]
    METADATA_FIELD_NUMBER: _ClassVar[int]
    success: bool
    data: _struct_pb2.Struct
    message_id: int
    error: str
    event_type: str
    metadata: _containers.ScalarMap[str, str]
    def __init__(self, success: _Optional[bool] = ..., data: _Optional[_Union[_struct_pb2.Struct, _Mapping]] = ..., message_id: _Optional[int] = ..., error: _Optional[str] = ..., event_type: _Optional[str] = ..., metadata: _Optional[_Mapping[str, str]] = ...) -> None: ...

class Event(_message.Message):
    __slots__ = ("topic", "payload", "timestamp")
    TOPIC_FIELD_NUMBER: _ClassVar[int]
    PAYLOAD_FIELD_NUMBER: _ClassVar[int]
    TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
    topic: str
    payload: _struct_pb2.Struct
    timestamp: _timestamp_pb2.Timestamp
    def __init__(self, topic: _Optional[str] = ..., payload: _Optional[_Union[_struct_pb2.Struct, _Mapping]] = ..., timestamp: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ...) -> None: ...

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
