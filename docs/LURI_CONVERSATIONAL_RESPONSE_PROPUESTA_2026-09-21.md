# Luri: propuesta de respuesta conversacional controlada

Fecha: 2026-09-21. Estado: **propuesta para revisión; no implementada**.

Principio: **Luri construye la verdad comercial permitida. Luna la convierte en conversación.** Una respuesta natural nunca tiene más autoridad que los hechos validados que recibió.

## Base verificada y alcance

PR [#44](https://github.com/Loke2802/BotWA-Starter/pull/44) está fusionado en `origin/master`, commit `899c62cc57dc481ad1016526488f22a82c20e886`. Se actualizó esa referencia y se creó desde ella la rama independiente `codex/luri-conversational-response`, en el worktree `D:\BotWA Starter\.worktrees\luri-conversational-response`.

Se inspeccionaron servicio, contratos, validación, proveedor, modelos, consumidor, métricas, actualización de configuración y pruebas de la integración real. Este documento es el único cambio de esta preparación. No se modificó PR #44, no se abrió aún otro PR y no se hicieron llamadas pagadas ni despliegues.

Se conserva el worker actual y su carril IA durable en PostgreSQL. No se reactiva la recuperación general aplazada. Único modelo: `gpt-5.6-luna`, usando la interfaz de proveedor existente. No hay herramientas, acciones nuevas, infraestructura ni evaluación comercial completa en este incremento.

## A. Integración propuesta

El punto de entrada está en `AIService.run_once()`, después de `render(result, config, memory, sources)` y antes de marcar el job como `ready`.

Hoy `render()` valida recomendaciones y citas y produce la respuesta segura. Propongo conservar esa función como autoridad de validación y composición base. Después de su éxito, un constructor adicional transforma exclusivamente las recomendaciones, correspondencias y citas que superaron esos controles en un contexto de redacción. No interpreta la respuesta textual para reconstruir hechos ni entrega el catálogo original al redactor.

Con la nueva flag apagada se ejecuta el recorrido actual, con la misma composición y sin llamadas adicionales. Si hay solicitud de handoff se conserva directamente el recorrido existente, sin redacción conversacional. La fase nueva tampoco decide ni ejecuta un handoff.

Problemas concretos encontrados que justifican ajustes acotados:

| Código actual | Ajuste propuesto y motivo |
|---|---|
| Lease calculado como `2 * ai_timeout_seconds + 60` | Renovación acotada antes de cada nueva etapa, bajo token vigente. Dos llamadas adicionales necesitan cobertura explícita. |
| Presupuesto por bot basado en `daily_jobs * 2` | Contar las cuatro etapas contra los límites existentes, sin duplicar automáticamente el presupuesto. Si falta cuota para una etapa nueva, usar la respuesta base. |
| `ai_attempt.stage` es `VARCHAR(20)` | Ampliarlo a 32: `conversational_render` tiene 21 caracteres. |
| Un único prompt para discovery/adviser | Registro interno de instrucciones/versiones por etapa; conservar los prompts base y separar redacción de revisión. |
| Hash de toda la configuración y cancelación ante cualquier cambio | Separar versión base y versión conversacional, preservando el hash histórico cuando la nueva capacidad está ausente/apagada. |
| No hay checkpoint del resultado base antes de `ready` | Persistirlo para recuperar las nuevas etapas sin repetir descubrimiento ni generar otra respuesta al cliente. |
| Se recorta texto en composición y despacho | Para la salida nueva, validar el texto completamente expandido contra el límite real del canal; rechazar en lugar de truncar una cláusula. La composición base permanece igual. |

Estos ajustes pertenecen al incremento independiente y necesitan las pruebas de regresión descritas abajo.

## B. Contratos

### `ValidatedResponseContextV1`

Envelope interno construido por Luri, con esquema estricto y colecciones limitadas:

| Grupo | Contenido autorizado |
|---|---|
| Identidad y vigencia | `context_id`, `schema_version`, job, tenant, bot, conversación, secuencia entrante, revisión de memoria leída, digest de memoria candidata, versiones de configuración y fuentes. |
| `customer_needs` | ID, clave configurada, valor, referencias a evidencia del cliente y estado `evidence_backed`. Nunca se promueve a hecho del negocio. |
| `business_facts` | ID, producto/sujeto, predicado, valor tipado, unidad/moneda cuando corresponda, fuente y versión, vigencia si existe. |
| `authorized_claims` | Afirmaciones que Luri permite expresar, según el contrato siguiente. |
| `validated_relationships` | Correspondencias necesidad–atributo ya verificadas por las reglas actuales. |
| `authorized_comparisons` | Relaciones calculadas por backend entre atributos realmente comparables. |
| `uncertainties` | Datos ausentes que justifican una abstención concreta; ausencia de stock conocido no significa stock cero. |
| `allowed_questions` | ID, necesidad pendiente, propósito y restricciones. Se excluyen necesidades resueltas. |
| `allowed_next_steps` | ID y propósito conversacional, con indicador de si requiere pregunta. No contiene instrucciones ejecutables. |
| `canonical_values` / `canonical_clauses` | Valores protegidos y cláusulas completas autorizadas. |
| `conversation_cues` | Información mínima validada para reconocer el último aporte, correcciones y preguntas ya realizadas. No incluye un historial bruto como fuente comercial. |
| `style` | Perfil interno versionado: claro, cercano, profesional, breve, sin presión ni promesas inventadas. |

El proveedor recibe una proyección mínima: referencias opacas y contenido autorizado. La pertenencia al tenant y bot se comprueba con el job y las consultas del backend, nunca confiando en identificadores devueltos por Luna. Texto del cliente y fuentes sigue siendo dato no confiable, aunque se haya autorizado una afirmación concreta: jamás modifica instrucciones ni personalidad.

El catálogo actual tiene atributos genéricos, no un contrato completo de dinero, vigencia o stock. Por ello **no se inferirá un precio vigente ni disponibilidad a partir de una etiqueta o un texto**. Solo habrá claims de ese tipo cuando un mapeo tipado, explícito y controlado por backend lo respalde. En ausencia de esa información, la colección correspondiente queda vacía. No se presenta una nueva fuente de stock o precios como parte ya resuelta de este incremento.

### `AuthorizedClaimV1`

Campos propuestos: `id`, `kind`, `subject_refs`, `predicate`, `object`, `fact_refs`, `need_refs`, `qualifiers`, `required_clause_refs`, `allowed_value_refs` y `expression_policy` (`paraphrase` o `canonical_clause`). Todos estrictos y limitados.

Ejemplo conceptual:

```json
{
  "id": "claim_price_a",
  "kind": "business_fact",
  "subject_refs": ["product_a"],
  "predicate": "current_price_equals",
  "object": {"value_ref": "price_a"},
  "fact_refs": ["fact_price_a"],
  "need_refs": [],
  "qualifiers": [],
  "required_clause_refs": [],
  "allowed_value_refs": ["price_a"],
  "expression_policy": "paraphrase"
}
```

Autoriza igualdad de precio; no precio anterior, rebaja, ahorro ni desigualdad. Los IDs se asignan una vez y permanecen estables dentro del contexto persistido. No hace falta una tabla permanente de claims.

Una correspondencia de edad autoriza explicar que la edad aportada está dentro del rango publicado. No autoriza prometer seguridad, resultados educativos ni calidad. Una comparación monetaria requiere moneda, unidad, condiciones y vigencia compatibles; no autoriza superioridad general.

### Segmentos y placeholders

`ConversationalDraftV1`: `schema_version`, `context_id`, `segments` (1–8). Cada segmento contiene `id`, `kind`, `text`, `claim_refs`, `need_refs`, `question_ref`, `next_step_ref` y `uncertainty_ref`; referencias opcionales se representan como `null`. Tipos: acknowledgement, recommendation, comparison, question, uncertainty y next_step. Se rechazan propiedades adicionales, IDs repetidos y referencias ajenas al contexto.

Para mantener sencillo el contrato, propongo **tokens literales en `text`**, no un motor de plantillas:

```json
{
  "id": "seg_2",
  "kind": "recommendation",
  "text": "{{product:product_a}} podría encajar por su temática. Su precio es {{value:price_a}}.",
  "claim_refs": ["claim_theme_match", "claim_price_a"],
  "need_refs": ["need_interest"],
  "question_ref": null,
  "next_step_ref": null,
  "uncertainty_ref": null
}
```

Parser de una sola pasada con gramática cerrada: `product`, `value`, `clause`, seguidos de un ID local permitido. Sin expresiones, rutas de objetos, escapes evaluables, interpolación recursiva ni ejecución. Un token desconocido o mal formado rechaza todo el borrador. Los valores insertados no vuelven a interpretarse como tokens.

Luri inserta nombres de productos y valores sensibles desde el contexto: precios, monedas, descuentos, edades, rangos, stock, cantidades, fechas, horarios, unidades y porcentajes. Cada referencia debe pertenecer a los claims/necesidades declarados en ese segmento. El literal libre no puede duplicar o sustituir estos valores. Los controles léxicos ayudan a detectar cifras y formatos; la revisión semántica también debe detectar cantidades escritas con palabras y cambios de sentido.

Límite inicial: 700 caracteres de plantilla por segmento y texto final completo de hasta `min(3500, límite_del_canal)`. La expansión también tiene límites; nunca se recorta una respuesta nueva aprobada.

Para políticas, garantías, condiciones, restricciones, disponibilidad, seguridad, entregas y promociones, `{{clause:...}}` inserta **la cláusula completa**. Inicialmente se exige que ocupe un segmento completo, sin prefijos o sufijos que puedan negarla o restringirla. Sus dependencias y condiciones deben viajar juntas. Luna puede ordenar esos segmentos y naturalizar las transiciones restantes. Las citas de conocimiento aprobadas por PR #44 se mantienen completas; no se abre una vía de resumen libre que elimine negaciones.

### `SemanticReviewV1`

Campos: `schema_version`, `context_id`, `draft_digest`, `approved`, `segments`. Por segmento: `segment_id`, `approved`, `reason_code`, `unsupported_claim_refs`.

Códigos cerrados, por ejemplo: `OK`, `UNSUPPORTED_CLAIM`, `ALTERED_MEANING`, `UNSUPPORTED_COMPARISON`, `CUSTOMER_DATA_AS_BUSINESS_FACT`, `REPEATED_QUESTION`, `MULTIPLE_QUESTIONS`, `UNAUTHORIZED_CONTACT`, `ACTION_IMPLIED`, `CLAUSE_CONTRADICTION` e `INSTRUCTION_INJECTION`. Una afirmación inventada puede carecer de referencia; en ese caso la lista queda vacía y el segmento se rechaza igualmente.

El revisor recibe solo contexto validado y borrador, incluida su expansión exacta por Luri. Instrucciones separadas y sin herramientas. Debe evaluar cada segmento y también contradicciones entre segmentos. Se exige cobertura exacta, IDs únicos y coherencia entre resultado global e individuales. El digest enlaza el resultado con el borrador revisado; lo calcula y verifica el backend. La revisión no devuelve texto alternativo ni modifica contexto, claims o permisos.

## C. Persistencia

Mantener `ai_job`, `ai_memory`, `ai_attempt` y outbox. Añadir una tabla opcional `ai_response_checkpoint`, relacionada uno a uno mediante `job_id` único:

- Identidad: `context_id` único, versión de esquema, versiones base/conversacional, revisión de memoria de entrada, digest del contexto y del borrador.
- Estado de etapa: `render_pending`, `render_started`, `review_pending`, `review_started`, `approved`, `fallback` o `cancelled`; timestamps y códigos normalizados.
- Payload cifrado y acotado: contexto, memoria candidata, respuesta base, borrador y resultado seleccionado cuando sea necesario para recuperación.
- Referencias a intentos de redacción/revisión; decisión de validación, motivo de rechazo y selección de fallback. Proveedor, modelo, prompt, duración y tokens siguen en `ai_attempt`, evitando duplicación.

Los claims viven dentro del contexto cifrado, no en tablas nuevas. El ámbito se obtiene obligatoriamente a través del job; ninguna lectura de checkpoint será suficiente para autorizar acceso sin verificar ese ámbito.

**Memoria:** hoy PR #44 valida y actualiza una copia en memoria y la persiste al finalizar la generación. Mantendría esa semántica: el checkpoint conserva la memoria candidata validada; la fila original se actualiza una sola vez al seleccionar la respuesta final/base, comprobando la revisión de entrada. El contexto nuevo usa esa candidata y distingue claramente su revisión de la memoria ya comprometida. Se registra la revisión finalmente comprometida para verificarla antes del envío. Un reinicio no vuelve a aplicar discovery ni incrementa dos veces la revisión.

La propiedad del trabajo sigue siendo el token/lease existente. El checkpoint no crea otra cola. Al recuperar un job con checkpoint válido, se reanuda su etapa pendiente sin comenzar otra vez el pipeline base. Si se agotó la edad máxima o el presupuesto, se resuelve con fallback válido o cancelación, sin prolongar indefinidamente el trabajo.

Una llamada nueva se registra como iniciada y se cierra la transacción antes de salir a red. Si el proceso cae con resultado remoto desconocido, se usa la base segura: no se repite automáticamente una llamada ambigua. Si el borrador quedó persistido y la revisión aún no comenzó, puede continuar esa revisión. Una aprobación persistida permite finalizar sin volver a llamar al modelo.

Después de resolver el envío o la cancelación, eliminar el contenido transitorio del checkpoint dentro de los recorridos normales del worker; conservar solo metadatos mínimos. Reutilizar el cifrado existente y no guardar prompts completos, historial completo ni texto privado en logs. La limpieza no requiere un nuevo servicio.

## D. Flujo completo

1. Entrada y job ya persistidos por el recorrido existente; la transacción se cierra antes de discovery.
2. Discovery, memoria candidata validada, adviser y `render()` actuales. Se obtiene `base_reply` y versiones de fuentes usadas.
3. Si flag apagada o handoff solicitado: finalizar por PR #44.
4. Construir contexto mínimo y persistir checkpoint, tras verificar propiedad, ámbito, secuencia, configuración, fuentes y memoria.
5. Registrar intento y renovar lease antes de `conversational_render`; cerrar sesión/transacción; llamar a Luna.
6. Validar contrato, referencias, placeholders, reglas y longitud; expandir con datos canónicos. Persistir resultado y decisión.
7. Si supera los controles, registrar `semantic_review` y llamar a Luna con instrucciones independientes, nuevamente fuera de transacción.
8. Validar resultado estricto y aprobación completa. Cualquier error nuevo selecciona la respuesta base si sigue siendo válida.
9. Bajo bloqueo/token vigentes, revalidar contexto y actualizar memoria una sola vez; dejar el job `ready` con el texto seleccionado.
10. Despacho y reintentos del outbox vuelven a comprobar nuevas entradas, handoff, flags, versiones y ámbito. Para esta capa se comprueba además la revisión comprometida de memoria y la identidad del texto aprobado. Se utiliza el mismo vínculo receipt → job → outbound, sin un segundo envío.

Un turno normal habilitado puede hacer cuatro llamadas. Los reintentos acotados de fases base pueden aumentar ese número; no se promete un máximo global de cuatro. Las dos etapas nuevas tienen un intento cada una, sin reparación automática. Los límites globales y por bot siguen aplicándose a todas las llamadas.

## E. Validación determinista y semántica

| Control | Determinista | Revisión semántica adicional |
|---|---|---|
| Identidad y vigencia | Scope del job, IDs, secuencia, token, flags, revisiones y fuentes vigentes | No se delega autoridad al modelo. |
| Claims/productos | Referencias existentes y permitidas, pertenencia al segmento, dependencias y tokens | Detectar menciones encubiertas, hechos añadidos y relaciones que los claims no autorizan. |
| Valores/cláusulas | Sustitución exacta, presencia íntegra de condiciones y rechazo de tokens/literales prohibidos | Detectar cambios de significado, negaciones externas y contradicciones entre segmentos. |
| Preguntas | Referencia pendiente, no respondida, máximo una referencia interrogativa en toda la respuesta, incluidos next steps | Detectar preguntas múltiples o repetidas expresadas como peticiones indirectas. |
| Contactos/ofertas/acciones | Prohibir campos ejecutables y contactos no autorizados; detectar URLs/teléfonos/formatos y expresiones prohibidas | Detectar promociones implícitas, promesas o acciones supuestamente completadas. |
| Formato | Esquema, campos, tipos, límites, normalización controlada y longitud expandida | Claridad y coherencia con personalidad sin ampliar hechos. |

Un segmento de reconocimiento no puede introducir afirmaciones comerciales sin claims. Un segmento de incertidumbre debe referir una incertidumbre real. El límite de una pregunta incluye «¿Quieres que compare?» aunque sea un próximo paso.

**Límite explícito:** un esquema estricto, referencias correctas o un segundo modelo no demuestran por sí solos la fidelidad de prosa libre. Los controles deterministas prueban identidad, integridad y restricciones estructurales; el revisor aporta detección semántica, que sigue siendo falible. Por eso las cláusulas delicadas quedan protegidas canónicamente y el piloto permanece limitado. No se promete riesgo cero.

## F. Fallos, desactivación y fallback

| Situación | Resultado |
|---|---|
| Timeout/API/cuota/JSON/referencias/tokens inválidos en fases nuevas | No enviar borrador; seleccionar `base_reply` persistida si todavía es válida. |
| Revisión rechazada, incompleta, incoherente o ausente | Fallback base; sin bucle de corrección. |
| Reinicio con llamada nueva de resultado desconocido | Registrar resultado desconocido y resolver con base válida; no duplicar llamada ambigua. |
| Nueva entrada, cambio de memoria/fuentes/configuración base o handoff | Contexto obsoleto: cancelar. La respuesta base del mismo contexto también puede estar obsoleta y no debe enviarse automáticamente. |
| No hay checkpoint válido | Mantener manejo de fallos y mensaje genérico seguro de PR #44; no reconstruir hechos a partir del borrador. |
| Se apaga solo la capa conversacional | Las siguientes entradas usan PR #44. Para jobs en curso, invalidar las etapas nuevas y seleccionar base cuando siga vigente. |

Flag propuesta: `generative_ai.conversational_response.enabled`, por bot dentro del tenant, por defecto `false`. Se mantienen los controles globales y scopes piloto actuales. No hacen falta secretos ni variables de entorno nuevas para este diseño.

El hash base conservará exactamente la serialización histórica sin el campo nuevo; la configuración conversacional tendrá versión propia. Los cambios de necesidades, habilitación base o autoridad siguen cancelando como antes. Activar la capa no convierte retroactivamente jobs antiguos al modo nuevo.

Si se apaga después de crear un outbound pero antes de reclamarlo para envío, la sustitución por la base debe ser atómica y conservar el mismo outbound, con texto y digest coherentes. Si el transporte ya reclamó/inició el envío, no se cambia ni se reenvía: la desactivación no puede retirar un mensaje ya en vuelo. Los estados de entrega desconocida conservan el tratamiento de PR #44.

Rollback operativo: apagar únicamente la nueva flag y resolver/drenar sus jobs; conservar la migración aditiva. Revertir el binario requiere primero resolver los checkpoints y revisar los hashes/configuraciones existentes; no se propone un downgrade destructivo con trabajos pendientes.

## G. Archivos previstos

Rutas relativas al worktree indicado al inicio; **lista de cambios propuestos, todavía no ejecutados**.

| Crear | Responsabilidad |
|---|---|
| `app/domain/generative_ai/response_contracts.py` | Contexto, claims, borrador, revisión y configuración de la capa. |
| `app/application/generative_ai/response_context.py` | Construcción de hechos/claims autorizados y proyección mínima. |
| `app/application/generative_ai/response_validation.py` | Parser, expansión, validación y verificación del dictamen semántico. |
| `app/application/generative_ai/response_pipeline.py` | Etapas opcionales, checkpoints y selección de fallback. |
| `app/infrastructure/generative_ai/response_prompts.py` | Instrucciones/versiones independientes para redacción y revisión. |
| `tests/test_conversational_response.py` | Contratos, controles y pipeline con proveedor falso. |
| `tests/integration/test_conversational_response_postgresql.py` | Durabilidad, concurrencia y transacciones reales. |
| Nueva migración posterior a `20260920_0025` | Checkpoint y ancho de stage. |

Modificar: `app/domain/generative_ai/contracts.py`, `app/application/generative_ai/{service,policy}.py`, `app/application/bots/service.py`, `app/infrastructure/models/ai_generation.py`, `app/infrastructure/generative_ai/openai_provider.py`, `app/operations/{ai_consumer,ai_metrics}.py`, `app/application/whatsapp_live/processor.py`, pruebas existentes afectadas y `docs/LURI_IA_OPERACION.md`. Registrar el modelo nuevo en el agregador de metadatos si lo requiere el repositorio. `validation.py` debe conservar sus reglas y salida base; cualquier extracción auxiliar necesaria se justificaría con equivalencia comprobada.

Métricas: conservar las existentes y desglosar latencia/tokens/resultados por discovery, adviser, conversational_render y semantic_review. Añadir decisiones, códigos de rechazo, fallbacks seleccionados y efectivamente enviados, cancelaciones por obsolescencia y edad por etapa. Medir aprobación/rechazo sobre revisiones terminadas y fallback sobre jobs que entraron en la capa, indicando denominadores. Mantener consumo desconocido como desconocido, nunca cero confirmado. Conservar tiempo total mensaje→envío y retraso de automatizaciones; no ampliar presupuesto ni capacidad silenciosamente.

## H. Migraciones

Sí: migración aditiva posterior a la revisión actual `20260920_0025` —nombre previsto `20260921_0026_conversational_response.py`, sujeto al head cuando se implemente— para crear `ai_response_checkpoint` con FK/UNIQUE/CHECK e índices necesarios y ampliar `ai_attempt.stage` de 20 a 32.

No cambia los estados del job principal, no transforma conversaciones antiguas ni crea claims permanentes. Las filas antiguas sin checkpoint siguen por la ruta base. La flag ausente equivale a apagada; la compatibilidad de hashes se resuelve en código y se prueba con fixtures históricos. El downgrade solo será admisible sin checkpoints activos y tratando explícitamente los stages largos; no truncará auditoría silenciosamente.

## I. Pruebas y aceptación

1. **Regresión base:** flag ausente/apagada mantiene exactamente texto, número de llamadas, memoria, recomendaciones y handoff de PR #44; hashes históricos y jobs preexistentes siguen válidos.
2. **Contratos:** extras, tamaños, duplicados, refs desconocidas, context/digest incorrectos, segmentos omitidos en revisión y aprobación global inconsistente.
3. **Claims:** precio igual frente a anterior/descuento/menor; cliente «creo que cuesta 50» no crea precio del negocio; edad/rango exactos; comparación sin moneda/vigencia suficiente se omite; menor precio no autoriza mejor calidad.
4. **Tokens/cláusulas:** valores desconocidos, sintaxis rota, anidación, expansión no recursiva, números escritos con palabras, unidades cambiadas, negaciones/condiciones eliminadas, cláusulas contradichas y límites tras expansión.
5. **Conversación:** reconocimiento con evidencia, preguntas respondidas, dos preguntas repartidas entre segmentos, preguntas indirectas y next steps que no ejecutan acciones.
6. **Proveedor falso/transporte simulado:** prompts diferentes por etapa, esquemas estrictos, solo Luna, sin herramientas, sin catálogo bruto, sin secretos, JSON inválido, errores, timeout y revisión rechazada. Ninguna llamada pagada.
7. **PostgreSQL:** checkpoint único, dos consumidores, fencing del propietario antiguo, reinicios en cada frontera, revisión pendiente reanudable, llamada ambigua no repetida, memoria aplicada una sola vez y un solo outbound.
8. **Vigencia y aislamiento:** cambios de tenant/bot, conversación, configuración, fuente, memoria, nuevas entradas y handoff entre generación, revisión, enqueue y envío; flag desactivada en cada fase, incluido outbound en vuelo.
9. **Transacciones:** comprobar que no queda conexión/transacción retenida durante las dos llamadas nuevas; contención y cancelación bajo bloqueo como en la base.
10. **Métricas y privacidad:** tokens por etapa, cuota compartida sin aumento, razones sanitizadas, denominadores, contenido cifrado, limpieza terminal y ausencia de texto privado en logs.
11. **Controles del repositorio:** pytest completo, gate PostgreSQL, ruff, black, mypy, migraciones upgrade/downgrade en entorno desechable y demás controles habituales de CI. Reportar resultados reales después de implementar; este documento no implica que esas pruebas ya hayan corrido.

Los fixtures mínimos comprobarán que el pipeline permite prosa distinta con los mismos hechos. La evaluación comercial A/B de 30–50 conversaciones queda pendiente, al igual que medir coste y naturalidad reales, ajustar umbrales y habilitar el tenant piloto. Una batería con proveedor simulado no certifica por sí sola la calidad del revisor real.

## Recomendación para la revisión

Avanzar con esta capa opcional, manteniendo la respuesta base persistida, claims explícitos, valores/cláusulas canónicos y revisión semántica separada. Los primeros datos deben mostrar cuánto mejora la conversación y qué coste, latencia y tasa de fallback introduce. Mantener apagada por defecto hasta completar pruebas y una habilitación piloto deliberada.

Antes de programar queda pendiente tu revisión de esta propuesta, tal como solicitaste. No se consideran implementados los contratos, migraciones, checkpoints, flags ni controles descritos aquí.
