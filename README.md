# Kontaktu · Orquestador post-llamada

Implementación del reto técnico de Kontaktu usando **Python + LangGraph + OpenAI**.

## Ejecución

Requiere Python 3.12+.

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
py -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Configura en `.env`:

```text
OPENAI_API_KEY=...
MODELO=gpt-5.6
```

Ejecuta un evento:

```powershell
py run.py eventos/01-call-ended-nuria.json
```

El programa escribe en `salida/`:

- `decisiones.jsonl`: una línea por evento recibido.
- `ordenes.jsonl`: una línea por orden CRM emitida.

El estado persistente se guarda en SQLite local (`.state.sqlite`).

## Diseño

LangGraph orquesta el flujo:

```text
validate_event
      ↓
  ┌───┴──────────────────────┐
  │                           │
call.ended              message/duplicate/
  │                     other organization
  ↓                           │
classify_call                 │
  ↓                           │
apply_business_rules          │
  └──────────────┬────────────┘
                 ↓
            plan_orders
```

La clasificación semántica usa OpenAI solo cuando hace falta interpretar la conversación. Las
señales deterministas de SIP, AMD y la existencia de una cita se resuelven en Python. Esto evita
gastar una llamada al modelo en casos completamente determinados por la señalización.

El modelo se configura mediante `MODELO`; durante el desarrollo se utilizó `gpt-5.6` porque
permite structured output y una clasificación consistente mediante Pydantic.

Las órdenes tienen claves de idempotencia deterministas derivadas del `idempotency_key` del
evento. Los identificadores de órdenes y reminders se generan localmente y se persisten para que
un proceso posterior pueda cancelar un reminder creado anteriormente.

## Persistencia

SQLite mantiene:

- eventos procesados/idempotencia;
- intentos de voz por `lead.contact_id`;
- reminders pendientes y cancelados;
- registros de no contactar;
- llamadas cortadas;
- órdenes emitidas.

Una reentrega no consume un intento, no vuelve a cerrar la llamada y no genera órdenes nuevas.

## Verificación

La comprobación se hizo ejecutando el flujo por etapas y verificando:

- clasificación determinista de SIP 480 y 486;
- clasificación semántica de llamadas con conversación;
- contador persistente de intentos;
- máximo de tres intentos y fallback a WhatsApp;
- ventanas de llamadas en `Europe/Madrid`;
- citas creadas frente a visitas solo acordadas verbalmente;
- cancelación de reminders ante `message.received`;
- idempotencia de una reentrega;
- eventos de otra organización sin órdenes.

También se contrastó la salida esperada del ejemplo resuelto y los casos descritos en `casos.md`.

## Decisiones y alcance

No se implementa un servidor CRM real porque el reto indica explícitamente que las siete operaciones
se simulan escribiendo `ordenes.jsonl`. Tampoco se usa una base de datos externa: SQLite es
suficiente para sobrevivir entre ejecuciones.

No se incluyen tests automatizados porque el reto indica que no son obligatorios. La verificación
se centra en el flujo real, persistencia y casos del catálogo. Los prompts utilizados por el código
están versionados en `prompts/`.

Los directorios originales `eventos/`, `config/` y `esquemas/` se mantienen sin modificaciones.
