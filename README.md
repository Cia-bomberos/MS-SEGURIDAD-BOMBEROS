
# MS-SEGURIDAD-BOMBEROS
## Módulo de Seguridad (Cognito + Panel Admin)

Gestiona la autenticación y el control de acceso del sistema mediante Amazon Cognito, más un panel exclusivo para Jefatura que permite cambiar contraseñas de las cuentas compartidas (RN-0042, RN-0043).

### Infraestructura desplegada

- **Cognito User Pool** con 5 grupos (roles): `Jefatura`, `Jefe_Administracion`, `Jefe_ServicioGeneral`, `Jefe_Maquinas`, `Jefe_Sanidad`.
- **App Client** de Cognito (usado por el frontend para el login).
- 2 Lambdas expuestos vía API Gateway, protegidos por un Authorizer de Cognito (solo se puede llamar con un token válido).

### Cuentas

Las 5 cuentas son fijas y compartidas por sección (no hay endpoint de creación de usuarios — ver RN-0042). Se crean una sola vez con el script `scripts/seed_users.py`.

Login por **username** (no por correo). Usuarios del entorno `dev`:

| Username | Rol |
|---|---|
| `jefatura` | Jefatura |
| `administracion` | Jefe de Administración |
| `serviciogeneral` | Jefe de Servicio General |
| `maquinas` | Jefe de Máquinas |
| `sanidad` | Jefe de Sanidad |

### Endpoints

Base URL (dev): `https://3fbn9ktlw8.execute-api.us-east-1.amazonaws.com/dev`

| Método | Ruta | Acceso | Descripción |
|---|---|---|---|
| GET | `/admin/cuentas` | Solo Jefatura | Lista las 4 cuentas compartidas administrables (Jefatura nunca aparece en la lista) |
| PATCH | `/admin/cuentas/{id}/password` | Solo Jefatura | Cambia/restablece la contraseña de una cuenta compartida. Body: `{"nueva_password": "..."}` |

Ambos endpoints requieren el header `Authorization: Bearer <IdToken>`. Un usuario que no sea Jefatura recibe `403`.

### Cómo probar (sin frontend)

```bash
# 1. Obtener un token
TOKEN=$(aws cognito-idp initiate-auth \
  --client-id <UserPoolClientId> \
  --auth-flow USER_PASSWORD_AUTH \
  --auth-parameters USERNAME=jefatura,PASSWORD=Jefatura123 \
  --query 'AuthenticationResult.IdToken' \
  --output text)

# 2. Llamar al endpoint
curl -H "Authorization: Bearer $TOKEN" \
  https://3fbn9ktlw8.execute-api.us-east-1.amazonaws.com/dev/admin/cuentas
```

Validado en `dev`: el endpoint responde correctamente con Jefatura (200, lista de cuentas) y rechaza a roles distintos (403).

### Estructura de archivos

```
serverless.yml          → infraestructura (Cognito, API Gateway, Lambdas)
modulo_admin/handler.py → lógica de los 2 endpoints
scripts/seed_users.py   → siembra las 5 cuentas fijas (correr una sola vez por entorno)
```
