# Luri CRM — historial móvil y navegación con teclado

07/10/2026. Rama `codex/luri-crm-history-accessibility`, desde `916d236`.
Conserva los commits de rendimiento (`9f3c333`), autorización (`08c81c6`),
historial paginado (`07aec7b`) y validación reproducible (`916d236`).
El checkout original y sus cambios previos siguen separados. No hay despliegue,
DigitalOcean ni llamadas reales a IA o WhatsApp.

## Problemas comprobados y cambios

En el panel local a 390 píxeles, la página tenía un ancho desplazable de 1029
píxeles y el historial ocupaba aproximadamente 945. El botón de versiones
anteriores terminaba fuera de pantalla, a unos 987 píxeles. El mínimo automático
de la columna de la cuadrícula permitía al menú horizontal expandir la página.
Las columnas móviles usan ahora `minmax(0, 1fr)` y el menú conserva su propio
desplazamiento horizontal. La paginación puede distribuir sus controles en
varias filas. Los títulos, responsables y acciones largos se ajustan al ancho;
los campos del formulario comercial también quedan contenidos. Los botones
del historial tienen al menos 44 píxeles de alto.

Al reemplazar una página de historial, el botón enfocado desaparecía y el foco
terminaba en `BODY`. `opportunity-history.js` conserva ahora la intención de
navegación: enfoca el nuevo botón equivalente o un control habilitado en el
extremo de la lista. Si durante la consulta se enfoca otro control, respeta esa
elección. La generación de la consulta y el contexto vigente siguen protegiendo
los cambios de empresa, los formularios y las fichas cerradas. Un error mantiene
la vista, el foco y el botón que permite reintentar.

El estado existente con `role="status"` anuncia la página y el intervalo de
versiones. Esto se verificó en el DOM; la lectura con un lector de pantalla
real queda pendiente. La página del portal cambia la versión de sus recursos
CSS e historial para cargar estos cambios.

La presentación, la paginación y el formulario conservan módulos separados.
Esta entrega modifica CSS y JavaScript del panel; no cambia API, permisos,
cifrado, historial persistido, modelo de datos ni migraciones.

## Pruebas ejecutadas

- `tests/portal_crm_history.html`: 11 casos aprobados, incluidos tres nuevos de
  foco, límites, elección de otro control durante una consulta y error recuperable.
  Se mantienen los casos de escape de HTML, sólo lecturas, anclaje de versiones,
  cambio de empresa y protección de un editor abierto.
- Regresiones del navegador: oportunidades 5, tablero 9, ficha 11, agenda 10 y
  conversaciones 7. Son 42 casos adicionales aprobados: 53 con el historial.
  Estas páginas usan API simulada, sin envíos reales.
- `tests/portal_crm_mobile.html`: cuatro comprobaciones aprobadas a cada ancho
  de 320, 390 y 768 píxeles; tarjetas con cadenas largas, historial y controles,
  formulario con opciones largas y menú contenido. Anchos desplazables de la
  página observados: 320, 375 y 753 píxeles, respectivamente.
- `python -m pytest tests/test_portal_routes.py -q -p no:cacheprovider
  --basetemp .audit-results/accessibility-portal-routes`: 1 aprobado en 26.63 s,
  con ambas URLs de pruebas SQLite y sin selectores PostgreSQL heredados.
  Persiste el aviso de deprecación Starlette/httpx ya documentado.
- `git diff --check`: aprobado.

La primera prueba móvil detectó que el botón de actualizar medía 43 píxeles.
Se corrigió a 44 y se repitió con CSS actualizado. La primera recarga conservaba
la hoja anterior en caché; su inspección mostró la regla antigua. La página
de prueba usa una versión explícita del recurso para repetir la medición.

## Recorrido local autenticado

En <http://127.0.0.1:8778/portal>, se renovó el login normal del propietario
ficticio y se abrió `***0147` → `Concurrencia local 81f6bb1c`. PostgreSQL conserva
la versión 201, responsable `organization_owner`, etapa Oferta presentada y
acción ronda 200 con fecha `2026-10-08T00:06` en Lima. Se abrió el formulario y
se canceló sin guardar; sus campos quedaron entre x=42 y x=333 en pantalla
de 390 píxeles. La página medía 375 píxeles de ancho desplazable.

Se abrió la primera página del historial (201 a 182) y se activó «Versiones
anteriores» con Enter. La segunda página mostró 181 a 162 y el foco quedó en
el nuevo botón `history-next`, sin terminar en `BODY`. El estado anunció ese
intervalo. La captura móvil muestra los controles y el mensaje conservado
de la conversación. Esta comprobación comercial fue de lectura; el login
genera su registro normal de acceso. No se guardaron ediciones ni envíos.

La ficha abierta tuvo 320 píxeles de ancho interior y 320 de ancho desplazable
en esa pantalla de 390. Su historial también pasó a 181–162 mediante Enter,
con foco en `history-next`; el historial de la conversación conservó su estado
independiente. No hubo errores de consola en el panel. Se cerraron las pestañas
temporales de pruebas y se restauró el tamaño normal, dejando abierto el panel.

- [Evidencia de navegador y dimensiones](validacion-local/history-accessibility-browser.json).
- [Captura móvil del historial real local](validacion-local/history-accessibility-mobile.png).

## Cómo comprobarlo y límites

1. Abrir el panel local y usar la cuenta ficticia del informe de historial.
2. Ir a Conversaciones, abrir `***0147` y elegir «Ver historial» de
   `Concurrencia local 81f6bb1c`.
3. En un ancho móvil de 320 o 390 píxeles, comprobar que ambos controles y
   «Actualizar historial» están visibles. El menú superior puede desplazarse
   dentro de su propia región.
4. Enfocar «Versiones anteriores» con Tab y activarlo con Enter. Comprobar la
   nueva página, su intervalo anunciado y que el foco permite continuar.
5. Abrir «Editar oportunidad», revisar responsable, etapa y próxima acción
   con fecha, y cancelar. Desde «Abrir ficha del cliente» también está disponible
   el historial compartido.

La suite completa anterior tuvo 1128 aprobados y 68 omitidos. La herramienta
de validación posterior aprobó 117 pruebas CRM/portal/autenticación y otras
7 PostgreSQL, con huella de código estable. Son ejecuciones distintas; no se
sumaron ni se repitieron en esta entrega de presentación. La repetición completa
pendiente se cerró posteriormente con 1143 aprobados, 68 omitidos y siete
PostgreSQL aparte, sobre el código fijo y preparación de pruebas optimizada.
[Resultado de la regresión completa](LURI_CRM_REGRESION_COMPLETA_LOCAL_2026-10-07.md).

Quedan pruebas con lectores de pantalla y dispositivos reales, búsquedas
amplias costosas, dimensionamiento con más carga y el piloto externo. El ensayo
local sostenido, PostgreSQL ficticio y las páginas simuladas no acreditan
despliegue, migración de producción ni validación real de clientes, IA o WhatsApp.
