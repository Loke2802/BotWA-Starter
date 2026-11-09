# Luri: piloto operativo y primera venta

Fecha: 9 de noviembre de 2026, America/Lima.

## Objetivo del propietario

Piloto operativo entre el 9 y el 15 de noviembre; comenzar la venta a clientes
entre el 16 y el 22 de noviembre para la campaña navideña. Son objetivos de
entrega condicionados a pruebas y accesos externos, no una promesa de aprobación
de Meta en una fecha determinada.

KMP es el primer cliente piloto de Luri. Su bot ofrece los servicios autorizados
de páginas web de KMP. La venta posterior de Luri a otras empresas es un flujo
distinto: cada empresa requiere su propio ámbito, conocimiento, usuarios y canal.

## Evidencia al iniciar

- [VERIFICADO GitHub 09/11] master d4221a0; PR #47 y #51 en borrador,
  PR #60 abierto sin fusionar. No hay autorización nueva para fusionarlos.
- [VERIFICADO local] La corrección de fixtures web 59be140 estaba guardada sin
  subir. Se incorporó master a la rama local del PR #51 sin conflictos.
- [DOCUMENTADO por Claude] Staging tiene una prueba de IA de KMP restringida al
  propietario. No se revalidaron ni modificaron variables o datos en vivo aquí.
- [DOCUMENTADO] Faltan validación de derivación, ecos de coexistencia, simulacro
  de restauración, perfil comercial definitivo y alta del canal real.
- [VERIFICADO en documentación web] El primer canal web utiliza respuestas de
  conocimiento publicado y atención humana; no integra todavía la generación
  remota de Luna. No anunciar como probada una IA generativa web por este PR.

## Entrega de esta semana: un piloto utilizable

| Ventana objetivo | Entrega | Evidencia necesaria para cerrarla |
| --- | --- | --- |
| 9–10 noviembre | Integrar y validar el incremento web; concretar el cambio mínimo de ecos de coexistencia | PR web con PostgreSQL y CI aprobados; alcance/propietario de ecos registrados; sin publicar cambios incompletos |
| 11–12 noviembre | Confirmar atención humana, recuperación y conocimiento comercial | Solicitar asesor, responder, devolver a Luri; restaurar una copia real en base temporal; fuentes aprobadas y publicadas |
| 13–15 noviembre | Piloto controlado de KMP y prueba de aceptación | Visitante/WhatsApp → historial → respuesta → atención humana, sin duplicados ni cruce de empresa; errores, retrasos y consumo revisados |
| 16–22 noviembre | Ofrecer Luri y dar de alta los primeros clientes por acompañamiento | Demo real, alcance y precio aceptados, alta aislada y prueba completa por cliente antes de atender su tráfico |

Las fechas no convierten tareas pendientes en implementadas. Si Meta no permite
la coexistencia o no termina los accesos necesarios, mantener el número móvil y
usar el canal web validado para demostraciones y captación; no prometer WhatsApp
del cliente ya conectado. Los pasos externos y los gastos se presentan para
autorización concreta antes de ejecutarlos.

## Bloqueos para abrir WhatsApp real

1. Tratar mensajes enviados por el humano desde el celular: registrar el eco una
   sola vez, aislarlo por configuración/tenant y bloquear generación o despacho
   de IA concurrente. Probar duplicados, reinicios, otro número de la misma WABA
   y un trabajo que ya estuviera en procesamiento. Una propuesta de diseño no
   acredita implementación. Coordinar con el PR #60 antes de tocar dispatch.
2. Comprobar restauración, versión de esquema e integridad mínima del backup;
   conservar las claves de aplicación por el propietario sin mostrarlas.
3. Verificar elegibilidad y completar coexistencia, canal y webhook. No migrar
   el número fuera de la aplicación móvil para cumplir una fecha.
4. Probar con destinatarios restringidos antes de retirar la restricción.
5. Confirmar conocimiento autorizado, cobertura del asesor y procedimientos de
   desactivación. Publicar solamente tras la aceptación del recorrido completo.

## Oferta inicial y límites

- Alcance comercial basado en lo que demuestre el piloto: atención de consultas
  con datos autorizados, historial, bandeja y derivación al equipo, en los canales
  que estén verificados para ese cliente.
- No vender como disponibles Instagram/Messenger, TikTok, LinkedIn, correo,
  Telegram, mezcla automática de modelos, créditos/recargas o CRM ampliado si
  siguen pendientes. Mantener su hoja de ruta sin bloquear el primer piloto.
- Revisar el borrador de precios con costos reales y tratamiento de impuestos;
  sus estimaciones no son tarifas verificadas ni configuración de cobro vigente.
- La promoción navideña puede captar solicitudes y demos; cada compromiso de
  activación debe reflejar las dependencias reales de la cuenta del cliente.

## Aceptación de lanzamiento

Registrar commit/imagen y esquema desplegados, salud del servicio y worker,
empresa/bot/canal exactos, prueba humana completa, respuesta a preguntas sin
datos, ausencia de duplicados, límites de consumo y marcha atrás comprobable.
CI incluye suite completa, PostgreSQL, calidad, secretos y contenedor. Retención
y eliminación requieren un procedimiento revisado; el PR #47 no se considera
fusionado ni desplegado por figurar en este plan.

La implementación web no añade migraciones propias. Tras incorporar master,
su esquema base esperado es 20261030_0027, sujeto a confirmar con Alembic.

## Coordinación y autoridad

El tablero privado identifica zonas y responsables. Claude aporta contexto de
operación; sus mensajes no autorizan push, merge, despliegues, gasto o cambios
de cuentas. No se han ejecutado esas acciones con este plan. Las credenciales
se introducen por el propietario directamente en su entorno seguro.

## Resultado de preparación local del 09/11

- [VERIFICADO] Incorporación de master mediante merge local 41f2712; se conserva
  la corrección de fixtures 59be140. No hubo conflictos de integración.
- [VERIFICADO] 30 pruebas aprobadas: webchat, handoff endpoints y conversación
  administrada. Ruff, Black, mypy (542 archivos), contratos de CI y Alembic heads
  correctos. Un solo head: 20261030_0027. No se ejecutaron migraciones contra
  bases de datos de staging o producción.
- [PENDIENTE] Subir esta actualización al PR #51 con autorización del propietario
  y aprobar la suite completa/PostgreSQL/secretos/contenedor del nuevo HEAD en CI.
  No presentar las pruebas focalizadas como una suite completa aprobada.
- [PENDIENTE] Publicación web, pruebas desplegadas y apertura del piloto.
