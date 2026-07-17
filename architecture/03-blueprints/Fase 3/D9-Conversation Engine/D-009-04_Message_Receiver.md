# D-009-04 – Message Receiver

Estado: Aprobado

## Objetivo
Recibir y normalizar toda comunicación proveniente de los canales.

## Salida
Conversation Message

## Contenido mínimo
- Message ID
- Conversation ID
- Customer ID
- Company ID
- Canal
- Tipo
- Contenido normalizado
- Timestamp
- Metadata

## Regla
Todo mensaje ingresa por el Message Receiver.

## CTO Review
Desacopla completamente al Conversation Engine de los canales de comunicación.
