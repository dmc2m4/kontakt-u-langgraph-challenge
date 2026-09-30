# Call Classification

## Purpose

Classify the conversational outcome of a `call.ended` event based on the
conversation transcript and the relevant call context.

## Rules

- Use the transcript as the primary source for conversational meaning.
- Use telephony and AMD information as additional signaling context.
- Do not invent information that is not present in the event.
- Do not decide CRM orders.
- Do not calculate retry dates.
- Do not determine idempotency.
- Return only structured classification information required by the application.