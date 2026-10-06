# Luri CRM: ficha, actividades, resumen e IA comercial

Entrega local del 06/10/2026, rama `codex/luri-crm-increment-1`.
Conserva los incrementos anteriores y el checkout principal con sus cambios previos.
No se ha desplegado, contratado infraestructura, enviado WhatsApp real ni llamado
a un proveedor de IA externo. No requiere DigitalOcean para comprobar este recorrido.

## Las cuatro mejoras

1. **Ficha comercial completa.** Desde Clientes o una conversación se abre la ficha
   existente con oportunidades, conversaciones, próximas acciones y actividades.
   Permite crear una oportunidad sin conversación, asignar responsable, etapa,
   necesidad, importe/moneda y acción fechada. Reutiliza el editor e historial del CRM.
   Desde la ficha se puede abrir una conversación y vincular allí la oportunidad.
2. **Actividad y continuidad.** Registra llamadas, reuniones y notas realizadas,
   con fecha y vínculo opcional a una oportunidad del mismo cliente. Para acciones
   futuras se utiliza el editor de oportunidades. Completar la anterior y programar
   la siguiente conserva las acciones pendientes, completadas y sustituidas/canceladas
   en un historial paginado. La ficha no sobrescribe las notas originales del contacto.
3. **Resumen comercial.** Abiertas, ganadas y perdidas por responsable y periodo,
   con importes decimales separados por moneda. El periodo selecciona oportunidades
   **creadas** en ese intervalo y las clasifica por su **etapa actual**; no representa
   cierres ocurridos durante el periodo ni facturación cobrada. No convierte monedas
   ni suma PEN con USD. Las fechas introducidas utilizan la zona del dispositivo;
   el panel muestra también la zona de la empresa. Hasta es inclusivo en el panel
   y se convierte a un límite exclusivo UTC en la API.
4. **Sugerencias con la IA existente.** Reutiliza la memoria cifrada de necesidades
   extraídas por la IA ya instalada. Requiere configuración habilitada/vigente, trabajo
   enviado para la secuencia actual y citas verificadas en mensajes entrantes de la
   misma empresa, bot y conversación. Necesidad, etapa y acción se muestran con
   evidencia. «Usar como borrador» solo rellena el editor: responsable, fecha y
   guardado siguen siendo decisiones del usuario. Si la memoria falta, está obsoleta
   o su evidencia es inválida, se abstiene y permite continuar manualmente.
   Este incremento no añade otro agente, proveedor ni llamadas remotas adicionales.

## Responsabilidades y seguridad

- `customer_workspace.py`: lectura por cliente, actividades idempotentes y acciones
  históricas; reutiliza `OpportunityService` y su autorización/repositorio/cifrado.
- `report.py`: agrupación SQL de cifras comerciales sin exponer importes al viewer.
- `suggestions.py`: verificación de la memoria y evidencia de IA, sin escrituras CRM.
- `customer_contracts.py`: contratos validados y paginación.
- `customer-workspace.js` y `commercial-report.js`: paneles; el formulario comercial,
  la navegación de conversaciones y la ficha existentes conservan su responsabilidad.

Todas las rutas requieren autenticación y permisos con alcance de empresa. Se
conserva el alcance global previamente autorizado del administrador de plataforma.
Los demás usuarios no pueden leer ni escribir datos de otra empresa. El viewer
consulta datos restringidos, sin descripciones privadas, importes ni controles de
escritura/IA. Los resultados tardíos se descartan al cerrar la ficha o cambiar empresa.

Migración aditiva `20261006_0029`: tabla de actividades con descripción cifrada,
auditoría, claves foráneas compuestas para empresa/cliente/oportunidad y usuario autor
identificado. El permiso del autor se comprueba en la aplicación, incluido el
administrador de plataforma; las claves de cliente y oportunidad impiden mezclar
empresas en la base. Clave idempotente única por empresa/autor, digest del contenido
y bloqueo transaccional: reintentar devuelve la misma actividad, cambiar el contenido
con la misma clave produce conflicto. Los cambios comerciales mantienen versiones
e historial anteriores. Se rechaza el downgrade que destruiría actividades guardadas.

## Pruebas ejecutadas y evidencia

- Suite general: **1070 aprobadas, 67 omitidas, 1 aviso** de deprecación Starlette/httpx.
  Las omitidas requieren sus integraciones/configuraciones explícitas; no acreditan
  servicios externos. Después de los últimos ajustes de historial y autor global,
  la selección final de ficha/portal produjo **7 aprobadas**.
- PostgreSQL real local: **5 aprobadas**, incluidas peticiones simultáneas deduplicadas,
  conflictos comerciales y restricciones de claves foráneas entre empresas.
- Navegador con API simulada: **38 aprobadas**: ficha nueva 9, tablero 9,
  seguimiento 8, oportunidades 5 y conversaciones 7. Incluye respuesta perdida,
  borradores IA sin autoguardado, escape HTML y descarte de resultados tardíos.
- HTTP real autenticado + PostgreSQL: propietario, operador, viewer y otra empresa;
  persistencia, replay/conflicto, acciones históricas, acceso no autenticado denegado,
  contenido restringido, resumen y abstención IA con configuración desactivada.
  Evidencia: [customer-authorized-http.json](validacion-local/customer-authorized-http.json).
- Restauración antes/después de migrar, filas previas intactas, actividad recuperada
  y replay sin duplicación, rollback destructivo rechazado sin cambios y configuración
  heredada inválida rechazada. La repetición con la migración final está en
  [customer-recovery-final.json](validacion-local/customer-recovery-final.json).
- `alembic check`: sin operaciones pendientes contra el esquema final poblado.
  Ruff, Black, mypy y `git diff --check` aprobados; sintaxis de módulos JS comprobada.

La ruta positiva de sugerencias usa la infraestructura IA existente con proveedor y
mensajería simulados en pruebas. La navegación normal con PostgreSQL confirma el
recorrido manual y la abstención con IA deshabilitada. No equivale a validar respuestas
de un modelo real ni entregas reales por WhatsApp.

## Comprobarlo en el panel local

El servidor de demostración utiliza solo datos sintéticos y autenticación normal.
Abrir http://127.0.0.1:8766/portal. Usuario
`organization_owner@local-crm.example.test`, contraseña sintética `SyntheticCRM2026!`.
También hay `operator@local-crm.example.test`, `viewer@local-crm.example.test` y
`other-company@local-crm.example.test` con la misma contraseña de demostración.

1. Clientes → Synthetic client → revisar ficha comercial, oportunidades y conversaciones.
2. Crear oportunidad para este cliente → responsable, etapa, necesidad, importe/moneda
   y próxima acción con fecha → guardar → cerrar y reabrir para comprobar persistencia.
3. Registrar reunión o llamada realizada y asociarla a la oportunidad → guardar.
4. Editar y programar próxima acción → completar la anterior y fijar siguiente fecha
   → guardar → revisar Historial de acciones y Ver historial.
5. Abrir conversación → comprobar el cliente y las oportunidades → vincular la venta
   si procede. No enviar mensajes reales desde esta demostración.
6. Resumen comercial → filtrar periodo/responsable. La demostración conserva una
   propuesta de 250 PEN y otra de 123,45 USD en filas separadas.
7. Consultar sugerencia de IA en la ficha: en esta demostración se abstiene porque IA
   está desactivada. El flujo positivo y la revisión del borrador están probados con dobles.
8. Cerrar sesión y entrar como viewer: contenido restringido y sin escritura. La otra
   empresa no ve la ficha ni cifras comerciales de Synthetic CRM.

Si se detiene el servidor, desde el worktree:

```powershell
& 'D:\BotWA Starter\.venv\Scripts\python.exe' -m scripts.serve_crm_local --manifest docs/validacion-local/customer-recovery.json
```

Mantener el contenedor desechable `luri-crm-local-recovery` disponible en
`127.0.0.1:15437`. El manifiesto anterior apunta a la base usada en el panel, cuyo
esquema se alineó con la migración final preservando la propuesta y reunión de prueba.
El manifiesto `customer-recovery-final.json` corresponde a otra restauración aislada;
no contiene los registros introducidos manualmente en el panel.

Repetir la verificación HTTP con el panel iniciado:

```powershell
& 'D:\BotWA Starter\.venv\Scripts\python.exe' -m scripts.verify_crm_customer_local --base-url http://127.0.0.1:8766 --manifest docs/validacion-local/customer-recovery.json --output docs/validacion-local/customer-authorized-http.json
```

Capturas de datos sintéticos:
[resumen](validacion-local/customer-commercial-report.png),
[acciones y actividad](validacion-local/customer-action-history.png).

## Pendientes externos

Despliegue, migración y restauración sobre una copia representativa del entorno real;
prueba con cuentas/roles reales; piloto con el modelo configurado y evidencia de IA
real; flujo WhatsApp completo y entrega del proveedor. Requieren un entorno disponible
y configuración autorizada. No se declaran como hechos por aprobar pruebas locales.
Si se necesita medir cierres por fecha o ingresos reales, es un incremento diferente
al resumen de oportunidades creadas implementado aquí.
