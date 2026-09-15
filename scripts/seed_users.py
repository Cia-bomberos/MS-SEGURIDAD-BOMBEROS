"""
Script para crear las 5 cuentas fijas de la Compania de Bomberos N3 en Cognito.

Se ejecuta UNA SOLA VEZ por entorno (dev, test, prod), ya que segun la
decision del cliente, las cuentas son fijas y compartidas por seccion
(no hay endpoint de creacion de usuarios en la aplicacion).

Uso:
    python scripts/seed_users.py --stage dev --user-pool-id us-east-1_XXXXXXXXX
"""

import argparse
import boto3
from botocore.exceptions import ClientError

# Las 5 cuentas fijas del sistema.
# En dev/test se pueden usar correos ficticios; en prod deben ser los reales
# de la Compania (coordinar con Carmen antes de sembrar el entorno prod).
USUARIOS = [
    {
        "username": "jefatura",
        "nombre": "Jefatura",
        "password": "Jefatura123",
        "grupo": "Jefatura",
    },
    {
        "username": "administracion",
        "nombre": "Jefe de Administracion",
        "password": "Administracion123",
        "grupo": "Jefe_Administracion",
    },
    {
        "username": "serviciogeneral",
        "nombre": "Jefe de Servicio General",
        "password": "Serviciogeneral123",
        "grupo": "Jefe_ServicioGeneral",
    },
    {
        "username": "maquinas",
        "nombre": "Jefe de Maquinas",
        "password": "Maquinas123",
        "grupo": "Jefe_Maquinas",
    },
    {
        "username": "sanidad",
        "nombre": "Jefe de Sanidad",
        "password": "Sanidad123",
        "grupo": "Jefe_Sanidad",
    },
]


def crear_usuario(client, user_pool_id: str, usuario: dict) -> None:
    username = usuario["username"]
    try:
        client.admin_create_user(
            UserPoolId=user_pool_id,
            Username=username,
            UserAttributes=[
                {"Name": "name", "Value": usuario["nombre"]},
            ],
            TemporaryPassword=usuario["password"],
            MessageAction="SUPPRESS",  # no enviar correo automatico de Cognito
        )
        print(f"  creado: {username}")
    except ClientError as e:
        if e.response["Error"]["Code"] == "UsernameExistsException":
            print(f"  ya existia: {username}")
        else:
            raise

    # La fija como definitiva (no temporal), ya que en el MVP no hay
    # flujo de "cambiar contrasena en primer login" para estas cuentas.
    client.admin_set_user_password(
        UserPoolId=user_pool_id,
        Username=username,
        Password=usuario["password"],
        Permanent=True,
    )

    client.admin_add_user_to_group(
        UserPoolId=user_pool_id,
        Username=username,
        GroupName=usuario["grupo"],
    )
    print(f"    agregado al grupo: {usuario['grupo']}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", required=True, choices=["dev", "test", "prod"])
    parser.add_argument("--user-pool-id", required=True)
    args = parser.parse_args()

    if args.stage == "prod":
        confirmacion = input(
            "Vas a sembrar usuarios en PRODUCCION. Escribe 'confirmar' para continuar: "
        )
        if confirmacion != "confirmar":
            print("Cancelado.")
            return

    client = boto3.client("cognito-idp")

    print(f"Sembrando {len(USUARIOS)} usuarios en {args.stage} ({args.user_pool_id})...")
    for usuario in USUARIOS:
        crear_usuario(client, args.user_pool_id, usuario)

    print("\nListo. Cada cuenta quedo con su contrasena definitiva (ver diccionario USUARIOS).")


if __name__ == "__main__":
    main()
