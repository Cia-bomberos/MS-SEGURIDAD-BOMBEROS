"""
Unit tests para modulo_admin/handler.py (RN-0042, RN-0043).

Todas las llamadas a Cognito se mockean (fixture `cognito_mock`) para que
los tests corran offline y de forma determinista, sin tocar AWS real.
"""

import json
from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError

from modulo_admin import handler


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _event(grupos="", path_params=None, body=None):
    """Arma un event de API Gateway con el shape que espera el handler."""
    event = {
        "requestContext": {
            "authorizer": {"claims": {"cognito:groups": grupos}}
        }
    }
    if path_params is not None:
        event["pathParameters"] = path_params
    if body is not None:
        event["body"] = json.dumps(body)
    return event


def _client_error(code, message="error simulado"):
    return ClientError({"Error": {"Code": code, "Message": message}}, "OperacionCognito")


@pytest.fixture(autouse=True)
def cognito_mock(monkeypatch):
    """Reemplaza el cliente boto3 de Cognito del handler por un MagicMock."""
    mock = MagicMock()
    monkeypatch.setattr(handler, "cognito", mock)
    return mock


# ---------------------------------------------------------------------------
# _es_jefatura / _rol_desde_token
# ---------------------------------------------------------------------------

class TestHelpers:
    def test_es_jefatura_true(self):
        event = _event(grupos="Jefatura")
        assert handler._es_jefatura(event) is True

    def test_es_jefatura_false(self):
        event = _event(grupos="Jefe_Sanidad")
        assert handler._es_jefatura(event) is False

    def test_rol_desde_token_devuelve_primer_grupo(self):
        event = _event(grupos="Jefe_Sanidad,OtroGrupo")
        assert handler._rol_desde_token(event) == "Jefe_Sanidad"

    def test_rol_desde_token_sin_grupos_devuelve_string_vacio(self):
        # ''.split(',') en Python devuelve [''], no [] -> el handler no
        # normaliza este caso y devuelve '' en vez de None.
        event = _event(grupos="")
        assert handler._rol_desde_token(event) == ""


# ---------------------------------------------------------------------------
# GET /admin/cuentas -> listar_cuentas
# ---------------------------------------------------------------------------

class TestListarCuentas:
    def test_rechaza_si_no_es_jefatura(self, cognito_mock):
        event = _event(grupos="Jefe_Administracion")

        resp = handler.listar_cuentas(event, None)

        assert resp["statusCode"] == 403
        cognito_mock.list_users_in_group.assert_not_called()

    def test_lista_cuentas_de_los_4_grupos_administrables(self, cognito_mock):
        cognito_mock.list_users_in_group.return_value = {
            "Users": [
                {
                    "Username": "administracion",
                    "UserStatus": "CONFIRMED",
                    "Attributes": [{"Name": "name", "Value": "Jefe de Administracion"}],
                }
            ]
        }
        event = _event(grupos="Jefatura")

        resp = handler.listar_cuentas(event, None)

        assert resp["statusCode"] == 200
        # Jefatura administra 4 grupos (nunca a sí misma) -> 4 llamadas a Cognito
        assert cognito_mock.list_users_in_group.call_count == 4
        body = json.loads(resp["body"])
        assert len(body["cuentas"]) == 4
        cuenta = body["cuentas"][0]
        assert cuenta["username"] == "administracion"
        assert cuenta["nombre"] == "Jefe de Administracion"
        assert cuenta["estado"] == "CONFIRMED"
        assert "grupo" in cuenta

    def test_no_incluye_a_jefatura_en_la_lista(self, cognito_mock):
        cognito_mock.list_users_in_group.return_value = {"Users": []}
        event = _event(grupos="Jefatura")

        handler.listar_cuentas(event, None)

        grupos_consultados = {
            call.kwargs["GroupName"] for call in cognito_mock.list_users_in_group.call_args_list
        }
        assert "Jefatura" not in grupos_consultados
        assert grupos_consultados == handler.GRUPOS_ADMINISTRABLES

    def test_error_de_cognito_devuelve_500(self, cognito_mock):
        cognito_mock.list_users_in_group.side_effect = _client_error("InternalErrorException")
        event = _event(grupos="Jefatura")

        resp = handler.listar_cuentas(event, None)

        assert resp["statusCode"] == 500


# ---------------------------------------------------------------------------
# PATCH /admin/cuentas/{id}/password -> cambiar_password
# ---------------------------------------------------------------------------

class TestCambiarPassword:
    def test_rechaza_si_no_es_jefatura(self, cognito_mock):
        event = _event(
            grupos="Jefe_Sanidad",
            path_params={"id": "sanidad"},
            body={"nueva_password": "NuevaClave123"},
        )

        resp = handler.cambiar_password(event, None)

        assert resp["statusCode"] == 403
        cognito_mock.admin_set_user_password.assert_not_called()

    def test_password_faltante(self, cognito_mock):
        event = _event(grupos="Jefatura", path_params={"id": "sanidad"}, body={})

        resp = handler.cambiar_password(event, None)

        assert resp["statusCode"] == 400

    def test_password_muy_corta(self, cognito_mock):
        event = _event(
            grupos="Jefatura", path_params={"id": "sanidad"}, body={"nueva_password": "abc123"}
        )

        resp = handler.cambiar_password(event, None)

        assert resp["statusCode"] == 400

    def test_usuario_no_encontrado_devuelve_404(self, cognito_mock):
        cognito_mock.admin_list_groups_for_user.side_effect = _client_error("UserNotFoundException")
        event = _event(
            grupos="Jefatura",
            path_params={"id": "inexistente"},
            body={"nueva_password": "NuevaClave123"},
        )

        resp = handler.cambiar_password(event, None)

        assert resp["statusCode"] == 404
        cognito_mock.admin_set_user_password.assert_not_called()

    def test_no_permite_modificar_a_jefatura_rn0043(self, cognito_mock):
        cognito_mock.admin_list_groups_for_user.return_value = {
            "Groups": [{"GroupName": "Jefatura"}]
        }
        event = _event(
            grupos="Jefatura", path_params={"id": "jefatura"}, body={"nueva_password": "NuevaClave123"}
        )

        resp = handler.cambiar_password(event, None)

        assert resp["statusCode"] == 403
        cognito_mock.admin_set_user_password.assert_not_called()

    def test_rechaza_cuenta_de_grupo_no_administrable(self, cognito_mock):
        cognito_mock.admin_list_groups_for_user.return_value = {
            "Groups": [{"GroupName": "OtroGrupoCualquiera"}]
        }
        event = _event(
            grupos="Jefatura", path_params={"id": "raro"}, body={"nueva_password": "NuevaClave123"}
        )

        resp = handler.cambiar_password(event, None)

        assert resp["statusCode"] == 403
        cognito_mock.admin_set_user_password.assert_not_called()

    def test_cambia_password_exitosamente(self, cognito_mock):
        cognito_mock.admin_list_groups_for_user.return_value = {
            "Groups": [{"GroupName": "Jefe_Sanidad"}]
        }
        event = _event(
            grupos="Jefatura", path_params={"id": "sanidad"}, body={"nueva_password": "NuevaClave123"}
        )

        resp = handler.cambiar_password(event, None)

        assert resp["statusCode"] == 200
        cognito_mock.admin_set_user_password.assert_called_once_with(
            UserPoolId=handler.USER_POOL_ID,
            Username="sanidad",
            Password="NuevaClave123",
            Permanent=True,
        )

    def test_error_al_actualizar_password_devuelve_500(self, cognito_mock):
        cognito_mock.admin_list_groups_for_user.return_value = {
            "Groups": [{"GroupName": "Jefe_Sanidad"}]
        }
        cognito_mock.admin_set_user_password.side_effect = _client_error("InternalErrorException")
        event = _event(
            grupos="Jefatura", path_params={"id": "sanidad"}, body={"nueva_password": "NuevaClave123"}
        )

        resp = handler.cambiar_password(event, None)

        assert resp["statusCode"] == 500
