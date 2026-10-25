"""
Modulo Admin - Gestion de contrasenas de cuentas compartidas.

Cumple RN-0042 y RN-0043:
- Solo Jefatura puede ver y cambiar la contrasena de las 4 cuentas
  compartidas (Administracion, Servicio General, Sanidad, Maquinas).
- La cuenta de Jefatura no puede modificarse desde este modulo (MVP).

Endpoints:
    GET   /admin/cuentas
    PATCH /admin/cuentas/{id}/password
    PATCH /admin/cuentas/{id}/username

Cambiar el nombre de usuario: en Cognito el `Username` con el que se inicia sesion NO
se puede modificar (el pool no usa alias ni UsernameAttributes, y cambiarlo exigiria
reemplazar el pool entero y perder las cuentas). Por eso "renombrar" es crear la cuenta
nueva (mismos atributos y grupo, con la contrasena indicada) y eliminar la anterior.
Consecuencias: el `sub` de la cuenta cambia, la contrasena anterior no se puede
trasladar (hay que indicar una), y el nombre de usuario viejo deja de funcionar.
"""

import json
import os
import re
import boto3
from botocore.exceptions import ClientError

USER_POOL_ID = os.environ["USER_POOL_ID"]
cognito = boto3.client("cognito-idp")

# Grupos que puede administrar Jefatura (todo excepto ella misma)
GRUPOS_ADMINISTRABLES = {
    "Jefe_Administracion",
    "Jefe_ServicioGeneral",
    "Jefe_Maquinas",
    "Jefe_Sanidad",
}


def _rol_desde_token(event) -> str | None:
    """Extrae el grupo de Cognito del usuario autenticado (via API Gateway authorizer)."""
    claims = event.get("requestContext", {}).get("authorizer", {}).get("claims", {})
    grupos = claims.get("cognito:groups", "")
    grupos_lista = grupos.split(",") if isinstance(grupos, str) else grupos
    return grupos_lista[0] if grupos_lista else None


# Politica del pool (ver serverless.yml): minimo 8, mayuscula, minuscula y numero.
USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,29}$")
ATRIBUTOS_A_COPIAR = ("name", "email")


def _error_password(password) -> str | None:
    """Mensaje de error si la contrasena no cumple la politica del pool; None si es valida."""
    if not password or len(password) < 8:
        return "La nueva contrasena debe tener al menos 8 caracteres."
    if not (re.search(r"[a-z]", password) and re.search(r"[A-Z]", password) and re.search(r"\d", password)):
        return "La nueva contrasena debe incluir mayusculas, minusculas y numeros."
    return None


def _respuesta(status: int, body: dict):
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body, default=str),
    }


def _es_jefatura(event) -> bool:
    claims = event.get("requestContext", {}).get("authorizer", {}).get("claims", {})
    grupos = claims.get("cognito:groups", "")
    return "Jefatura" in grupos


def listar_cuentas(event, context):
    """GET /admin/cuentas - solo Jefatura."""
    if not _es_jefatura(event):
        return _respuesta(403, {"error": "Solo Jefatura puede acceder a este panel."})

    try:
        cuentas = []
        for grupo in GRUPOS_ADMINISTRABLES:
            usuarios = cognito.list_users_in_group(
                UserPoolId=USER_POOL_ID, GroupName=grupo
            )
            for u in usuarios.get("Users", []):
                atributos = {a["Name"]: a["Value"] for a in u["Attributes"]}
                cuentas.append({
                    "username": u["Username"],
                    "nombre": atributos.get("name"),
                    "grupo": grupo,
                    "estado": u["UserStatus"],
                })

        return _respuesta(200, {"cuentas": cuentas})

    except ClientError as e:
        return _respuesta(500, {"error": str(e)})


def cambiar_password(event, context):
    """PATCH /admin/cuentas/{id}/password - solo Jefatura."""
    if not _es_jefatura(event):
        return _respuesta(403, {"error": "Solo Jefatura puede cambiar contrasenas."})

    username = event["pathParameters"]["id"]
    body = json.loads(event.get("body") or "{}")
    nueva_password = body.get("nueva_password")

    error = _error_password(nueva_password)
    if error:
        return _respuesta(400, {"error": error})

    # Verificar que la cuenta pertenezca a un grupo administrable (nunca Jefatura)
    try:
        grupos_usuario = cognito.admin_list_groups_for_user(
            UserPoolId=USER_POOL_ID, Username=username
        )
        nombres_grupos = {g["GroupName"] for g in grupos_usuario.get("Groups", [])}
    except ClientError as e:
        return _respuesta(404, {"error": f"Cuenta no encontrada: {e}"})

    if "Jefatura" in nombres_grupos:
        return _respuesta(403, {"error": "La cuenta de Jefatura no puede modificarse (RN-0043)."})

    if not nombres_grupos & GRUPOS_ADMINISTRABLES:
        return _respuesta(403, {"error": "Esta cuenta no pertenece a un grupo administrable."})

    try:
        cognito.admin_set_user_password(
            UserPoolId=USER_POOL_ID,
            Username=username,
            Password=nueva_password,
            Permanent=True,
        )
        return _respuesta(200, {"mensaje": f"Contrasena actualizada para {username}."})

    except ClientError as e:
        if e.response["Error"]["Code"] == "InvalidPasswordException":
            return _respuesta(400, {"error": "La contrasena no cumple la politica de seguridad."})
        return _respuesta(500, {"error": str(e)})


def _grupos_de(username):
    """(grupos de la cuenta, None) o (None, respuesta de error). Nunca deja pasar a Jefatura."""
    try:
        respuesta = cognito.admin_list_groups_for_user(UserPoolId=USER_POOL_ID, Username=username)
    except ClientError as e:
        return None, _respuesta(404, {"error": f"Cuenta no encontrada: {e}"})
    grupos = {g["GroupName"] for g in respuesta.get("Groups", [])}
    if "Jefatura" in grupos:
        return None, _respuesta(403, {"error": "La cuenta de Jefatura no puede modificarse (RN-0043)."})
    if not grupos & GRUPOS_ADMINISTRABLES:
        return None, _respuesta(403, {"error": "Esta cuenta no pertenece a un grupo administrable."})
    return grupos, None


def _existe(username) -> bool:
    try:
        cognito.admin_get_user(UserPoolId=USER_POOL_ID, Username=username)
        return True
    except ClientError as e:
        if e.response["Error"]["Code"] == "UserNotFoundException":
            return False
        raise


def _descartar(username):
    """Deshace una cuenta a medio crear; un fallo aqui no debe tapar el error original."""
    try:
        cognito.admin_delete_user(UserPoolId=USER_POOL_ID, Username=username)
    except ClientError:
        pass


def cambiar_username(event, context):
    """PATCH /admin/cuentas/{id}/username - solo Jefatura.
    Body: {"nuevo_username": "...", "nueva_password": "..."} (la contrasena es obligatoria
    porque la cuenta se recrea y la anterior no se puede leer)."""
    if not _es_jefatura(event):
        return _respuesta(403, {"error": "Solo Jefatura puede cambiar nombres de usuario."})

    actual = event["pathParameters"]["id"]
    try:
        body = json.loads(event.get("body") or "{}")
    except ValueError:
        return _respuesta(400, {"error": "El cuerpo debe ser JSON."})
    nuevo = (body.get("nuevo_username") or "").strip()
    nueva_password = body.get("nueva_password")

    if not USERNAME_RE.match(nuevo):
        return _respuesta(400, {"error": "El nuevo usuario debe tener de 3 a 30 caracteres: minusculas, "
                                         "numeros, punto, guion o guion bajo."})
    if nuevo == actual:
        return _respuesta(400, {"error": "El nuevo usuario es igual al actual."})
    error = _error_password(nueva_password)
    if error:
        return _respuesta(400, {"error": error})

    grupos, denegado = _grupos_de(actual)
    if denegado:
        return denegado

    try:
        if _existe(nuevo):
            return _respuesta(409, {"error": f"El usuario '{nuevo}' ya existe."})

        original = cognito.admin_get_user(UserPoolId=USER_POOL_ID, Username=actual)
        atributos = [
            {"Name": a["Name"], "Value": a["Value"]}
            for a in original.get("UserAttributes", []) if a["Name"] in ATRIBUTOS_A_COPIAR
        ]

        try:
            cognito.admin_create_user(
                UserPoolId=USER_POOL_ID, Username=nuevo, UserAttributes=atributos,
                TemporaryPassword=nueva_password, MessageAction="SUPPRESS",
            )
            cognito.admin_set_user_password(
                UserPoolId=USER_POOL_ID, Username=nuevo, Password=nueva_password, Permanent=True,
            )
            for grupo in sorted(grupos & GRUPOS_ADMINISTRABLES):
                cognito.admin_add_user_to_group(UserPoolId=USER_POOL_ID, Username=nuevo, GroupName=grupo)
            cognito.admin_delete_user(UserPoolId=USER_POOL_ID, Username=actual)
        except ClientError:
            _descartar(nuevo)  # que no quede una cuenta duplicada a medias
            raise

        return _respuesta(200, {
            "mensaje": f"Usuario cambiado de '{actual}' a '{nuevo}'.",
            "username_anterior": actual,
            "username_nuevo": nuevo,
        })
    except ClientError as e:
        if e.response["Error"]["Code"] == "InvalidPasswordException":
            return _respuesta(400, {"error": "La contrasena no cumple la politica de seguridad."})
        return _respuesta(500, {"error": str(e)})
