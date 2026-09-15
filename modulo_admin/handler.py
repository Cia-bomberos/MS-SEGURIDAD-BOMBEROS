"""
Modulo Admin - Gestion de contrasenas de cuentas compartidas.

Cumple RN-0042 y RN-0043:
- Solo Jefatura puede ver y cambiar la contrasena de las 4 cuentas
  compartidas (Administracion, Servicio General, Sanidad, Maquinas).
- La cuenta de Jefatura no puede modificarse desde este modulo (MVP).

Endpoints:
    GET   /admin/cuentas
    PATCH /admin/cuentas/{id}/password
"""

import json
import os
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

    if not nueva_password or len(nueva_password) < 8:
        return _respuesta(400, {"error": "La nueva contrasena debe tener al menos 8 caracteres."})

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
        return _respuesta(500, {"error": str(e)})
