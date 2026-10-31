# Scripts operativos de la reconstrucción de staging (21–23/10/2026)

Helpers de un solo uso que se ejecutaron en la consola del Web Service de
`luri-staging` (DigitalOcean) durante la reconstrucción de staging y la
preparación de la revisión de Meta. No forman parte de la imagen de la
aplicación ni de la API.

Todos son de solo lectura por defecto. Las escrituras exigen `--apply` (o
`--connect`/`--create-demo`), una terminal interactiva y confirmación humana.
Las credenciales se introducen por entrada oculta; nunca por argumentos ni
variables de entorno.

## Variables requeridas

Los datos personales y de infraestructura se retiraron del código. Sin estas
variables, los scripts se niegan a actuar:

| Variable | Uso |
|---|---|
| `LURI_OPS_DB_HOST` | Host privado esperado de la base de staging |
| `LURI_OPS_OWNER_EMAIL` | Correo de la cuenta propietaria de Kalivur en staging |
| `LURI_OPS_REVIEWER_EMAIL` | Correo de la cuenta revisora de Meta |
| `LURI_OPS_TEST_RECIPIENT` | Teléfono autorizado para la prueba real, solo dígitos |
| `LURI_OPS_PUBLIC_WEBHOOK_ID` | `public_webhook_id` del canal de prueba |
| `LURI_OPS_SCOPED_USER_ID` | ID de usuario con ámbito de app que Meta devuelve para el token |

Los identificadores de los activos de prueba de Meta (WABA y número de prueba,
app Luri y usuario del sistema) siguen fijos en el código: son activos de
sandbox y los scripts los usan como comprobación de destino exacto.

`app-spec.template.yaml` es una referencia saneada del spec de App Platform,
con marcadores `REPLACE_…`; no es un respaldo de secretos.

## Pruebas

Los `test_*.py` son offline (sin base real, sin red, credenciales sintéticas):

```bash
python -m pytest docs/recovery/2026-10-21 -p no:cacheprovider
```
