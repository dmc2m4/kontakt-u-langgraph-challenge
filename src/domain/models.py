from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class EventType(str, Enum):
    CALL_ENDED = "call.ended"
    MESSAGE_RECEIVED = "message.received"


class DecisionLabel(str, Enum):
    VISITA_RESERVADA = "visita_reservada"
    DOCUMENTACION_ENVIADA = "documentacion_enviada"
    CALLBACK = "callback"
    SIN_RESPUESTA = "sin_respuesta"
    OCUPADO = "ocupado"
    BUZON = "buzon"
    CORTADA = "cortada"
    VISITA_SIN_CONFIRMAR = "visita_sin_confirmar"
    PERSONA_EQUIVOCADA = "persona_equivocada"
    NO_CONTACTAR = "no_contactar"
    RECHAZADA = "rechazada"
    DOCUMENTACION_PENDIENTE = "documentacion_pendiente"
    DESCARTADO = "descartado"
    OTRO = "otro"
    NO_APLICA = "no_aplica"


class TranscriptMessage(BaseModel):
    role: str
    message: str
    time_in_call_secs: int


class Appointment(BaseModel):
    appointment_id: str
    start_time: datetime


class Lead(BaseModel):
    contact_id: str
    phone: str
    full_name: str | None = None
    lead_source: str | None = None
    property_ref: str | None = None
    property_address: str | None = None
    language: str


class Campaign(BaseModel):
    system_key: str
    entry_id: str


class AMDResult(str, Enum):
    HUMAN = "human"
    MACHINE_VM = "machine-vm"
    MACHINE_IVR = "machine-ivr"
    MACHINE_UNAVAILABLE = "machine-unavailable"
    UNCERTAIN = "uncertain"
    NOT_RUN = "not_run"


class AMDSource(str, Enum):
    LIVEKIT_AMD = "livekit_amd"
    HEURISTIC_REGEX = "heuristic_regex"
    NONE = "none"


class AMD(BaseModel):
    result: AMDResult | None = None
    greeting_transcript: str | None = None
    detected_at_secs: float | None = None
    source: AMDSource | None = None


class Telephony(BaseModel):
    provider: str
    call_id: str
    provider_call_id: str | None = None
    dialed_at: datetime
    ringing_at: datetime | None = None
    answered_at: datetime | None = None
    ended_at: datetime
    sip_status_code: int
    sip_status: str
    disconnect_reason: str
    hung_up_by: str | None = None
    duration_seconds: int
    amd: AMD | None = None


class AgentOutcome(BaseModel):
    appointment: Appointment | None = None
    slots_snapshot: dict = Field(default_factory=dict)


class Message(BaseModel):
    channel: str
    text: str


class Event(BaseModel):
    event_id: str
    type: EventType
    occurred_at: datetime
    organization_id: str
    idempotency_key: str
    campaign: Campaign
    lead: Lead

    telephony: Telephony | None = None
    transcript: list[TranscriptMessage] = Field(default_factory=list)
    agent_outcome: AgentOutcome | None = None
    message: Message | None = None
    delivery_attempt: int = 1