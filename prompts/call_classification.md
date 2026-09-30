# Call Classification

## Purpose

Classify the conversational outcome of a `call.ended` event.

The classification must describe what actually happened during the call.
Business rules, scheduling, retries, CRM orders, idempotency, and persistence
are handled by the application and must not be decided by the model.

## Classification rules

Use the transcript as the primary source for conversational meaning.

Use telephony, SIP, AMD, agent outcome, and other event data as supporting
context.

Do not invent information that is not present in the event.

### `visita_reservada`

Use when the lead agreed to a visit and the agent actually created an
appointment.

The appointment must be present in `agent_outcome.appointment`.

### `documentacion_enviada`

Use when documentation was actually sent by the agent and the lead accepted
WhatsApp as the communication channel.

### `callback`

Use when the lead explicitly asks to be contacted again at a later time.

If the lead provides a requested time, extract it into
`callback_requested_at`.

Do not decide whether that time is inside the allowed calling window.

### `sin_respuesta`

Use for a call with no answer, especially SIP status `408` or `480`, when
there is no meaningful conversation.

### `ocupado`

Use when the call ended because the destination was busy, especially SIP
status `486`.

### `buzon`

Use when the call reached a voicemail or answering machine.

Relevant AMD results include:

- `machine-vm`
- `machine-unavailable`

A machine answer with SIP `200` can still be classified as `buzon`.

### `cortada`

Use when a real person was reached and the call was unexpectedly interrupted
during qualification, without a proper goodbye.

Do not use this label only because the call duration was short.

### `visita_sin_confirmar`

Use when the lead verbally agreed to a visit but the appointment was not
actually created before the call ended.

The presence of an appointment in `agent_outcome.appointment` means the visit
was actually reserved.

### `persona_equivocada`

Use when the person who answered clearly states that they are not the intended
lead/contact.

### `no_contactar`

Use when the person explicitly asks not to be contacted.

This includes explicit requests such as not calling again or not contacting
them through any channel.

### `rechazada`

Use when the call was actively rejected, especially SIP status `603`.

Do not classify an active rejection as `no_contactar` unless the conversation
itself explicitly contains a request not to be contacted.

### `documentacion_pendiente`

Use when the lead asks for documentation but the documentation has not yet
been sent.

If the lead explicitly rejects WhatsApp, preserve that fact in
`context_note`.

### `descartado`

Use when the lead clearly indicates that they already bought or rented, or
that they are no longer looking for the relevant property/service.

### `otro`

Use when the event does not clearly fit the supported classifications.

This includes cases such as:

- `machine-ivr`
- SIP 5xx trunk failures
- ambiguous situations that cannot be reliably classified
- situations outside the defined cases

### `no_aplica`

This label is not normally produced for a valid `call.ended` classification.

It is reserved for events that do not represent a classification applicable
to the call decision flow.

## Important constraints

The model must not:

- calculate retry dates
- select a fallback channel
- decide whether another call should be scheduled
- create CRM orders
- cancel reminders
- mark a lead as DNC
- calculate attempt counts
- decide whether an event is a duplicate
- decide whether the organization is valid
- decide whether a call is inside the allowed calling window
- reserve or create appointments
- infer facts that are not supported by the event

Return only the structured classification fields required by the application.