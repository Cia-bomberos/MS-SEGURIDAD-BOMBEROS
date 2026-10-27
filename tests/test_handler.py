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


# ---------------------------------------------------------------------------
# Politica de contrasena
# ---------------------------------------------------------------------------

class TestPoliticaPassword:
    @pytest.mark.parametrize("password", ["abcdefgh1", "ABCDEFGH1", "Abcdefgh", "Ab1"])
    def test_cambiar_password_rechaza_las_que_no_cumplen_la_politica(self, cognito_mock, password):
        event = _event(grupos="Jefatura", path_params={"id": "sanidad"}, body={"nueva_password": password})
        assert handler.cambiar_password(event, None)["statusCode"] == 400
        cognito_mock.admin_set_user_password.assert_not_called()

    def test_cognito_rechaza_la_password_devuelve_400_no_500(self, cognito_mock):
        cognito_mock.admin_list_groups_for_user.return_value = {"Groups": [{"GroupName": "Jefe_Sanidad"}]}
        cognito_mock.admin_set_user_password.side_effect = _client_error("InvalidPasswordException")
        event = _event(grupos="Jefatura", path_params={"id": "sanidad"}, body={"nueva_password": "NuevaClave123"})
        assert handler.cambiar_password(event, None)["statusCode"] == 400


# ---------------------------------------------------------------------------
# PATCH /admin/cuentas/{id}/username -> cambiar_username
# ---------------------------------------------------------------------------

BODY = {"nuevo_username": "sanidad.jefe", "nueva_password": "NuevaClave123"}


def _evento(grupos="Jefatura", actual="sanidad", body=BODY):
    return _event(grupos=grupos, path_params={"id": actual}, body=body)


@pytest.fixture
def cuenta_sanidad(cognito_mock):
    """La cuenta 'sanidad' existe, es de Jefe_Sanidad y el usuario nuevo esta libre."""
    cognito_mock.admin_list_groups_for_user.return_value = {"Groups": [{"GroupName": "Jefe_Sanidad"}]}

    def _get(UserPoolId, Username):
        if Username == "sanidad":
            return {"UserAttributes": [
                {"Name": "sub", "Value": "abc"}, {"Name": "name", "Value": "Jefe de Sanidad"},
                {"Name": "email", "Value": "san@cia.pe"}, {"Name": "email_verified", "Value": "true"},
            ]}
        raise _client_error("UserNotFoundException")

    cognito_mock.admin_get_user.side_effect = _get
    return cognito_mock


class TestCambiarUsername:
    def test_rechaza_si_no_es_jefatura(self, cognito_mock):
        for grupo in ("Jefe_Sanidad", "Jefe_Administracion", ""):
            assert handler.cambiar_username(_evento(grupos=grupo), None)["statusCode"] == 403
        cognito_mock.admin_create_user.assert_not_called()

    @pytest.mark.parametrize("nuevo", ["", "ab", "Sanidad", "con espacio", "a" * 31, "-guion", "ñandu", None])
    def test_usuario_nuevo_invalido_400(self, cognito_mock, nuevo):
        r = handler.cambiar_username(_evento(body={"nuevo_username": nuevo, "nueva_password": "NuevaClave123"}), None)
        assert r["statusCode"] == 400
        cognito_mock.admin_create_user.assert_not_called()

    def test_misma_cuenta_400(self, cognito_mock):
        r = handler.cambiar_username(_evento(body={"nuevo_username": "sanidad", "nueva_password": "NuevaClave123"}), None)
        assert r["statusCode"] == 400

    @pytest.mark.parametrize("password", [None, "", "corta1A", "sinmayuscula1", "SINMINUSCULA1", "SinNumeros"])
    def test_la_contrasena_es_obligatoria_y_valida(self, cognito_mock, password):
        r = handler.cambiar_username(_evento(body={"nuevo_username": "otro.usuario", "nueva_password": password}), None)
        assert r["statusCode"] == 400
        cognito_mock.admin_create_user.assert_not_called()

    def test_cuerpo_no_json_400(self, cognito_mock):
        ev = _event(grupos="Jefatura", path_params={"id": "sanidad"})
        ev["body"] = "{no json"
        assert handler.cambiar_username(ev, None)["statusCode"] == 400

    def test_cuenta_inexistente_404(self, cognito_mock):
        cognito_mock.admin_list_groups_for_user.side_effect = _client_error("UserNotFoundException")
        assert handler.cambiar_username(_evento(actual="fantasma"), None)["statusCode"] == 404
        cognito_mock.admin_create_user.assert_not_called()

    def test_no_se_puede_renombrar_a_jefatura_rn0043(self, cognito_mock):
        cognito_mock.admin_list_groups_for_user.return_value = {"Groups": [{"GroupName": "Jefatura"}]}
        assert handler.cambiar_username(_evento(actual="jefatura"), None)["statusCode"] == 403
        cognito_mock.admin_create_user.assert_not_called()
        cognito_mock.admin_delete_user.assert_not_called()

    def test_grupo_no_administrable_403(self, cognito_mock):
        cognito_mock.admin_list_groups_for_user.return_value = {"Groups": [{"GroupName": "Otro"}]}
        assert handler.cambiar_username(_evento(actual="raro"), None)["statusCode"] == 403

    def test_usuario_nuevo_ya_existe_409_sin_tocar_nada(self, cuenta_sanidad):
        cuenta_sanidad.admin_get_user.side_effect = None
        cuenta_sanidad.admin_get_user.return_value = {"UserAttributes": []}
        assert handler.cambiar_username(_evento(), None)["statusCode"] == 409
        cuenta_sanidad.admin_create_user.assert_not_called()
        cuenta_sanidad.admin_delete_user.assert_not_called()

    def test_renombra_creando_la_nueva_y_eliminando_la_anterior(self, cuenta_sanidad):
        r = handler.cambiar_username(_evento(), None)
        assert r["statusCode"] == 200
        body = json.loads(r["body"])
        assert (body["username_anterior"], body["username_nuevo"]) == ("sanidad", "sanidad.jefe")

        crear = cuenta_sanidad.admin_create_user.call_args.kwargs
        assert crear["Username"] == "sanidad.jefe"
        assert crear["MessageAction"] == "SUPPRESS"
        # copia el nombre y el correo, pero no el sub ni email_verified
        assert {a["Name"] for a in crear["UserAttributes"]} == {"name", "email"}
        cuenta_sanidad.admin_set_user_password.assert_called_once_with(
            UserPoolId=handler.USER_POOL_ID, Username="sanidad.jefe", Password="NuevaClave123", Permanent=True)
        cuenta_sanidad.admin_add_user_to_group.assert_called_once_with(
            UserPoolId=handler.USER_POOL_ID, Username="sanidad.jefe", GroupName="Jefe_Sanidad")
        cuenta_sanidad.admin_delete_user.assert_called_once_with(UserPoolId=handler.USER_POOL_ID, Username="sanidad")

    def test_la_anterior_se_elimina_solo_al_final(self, cuenta_sanidad):
        orden = []
        for nombre in ("admin_create_user", "admin_set_user_password", "admin_add_user_to_group", "admin_delete_user"):
            getattr(cuenta_sanidad, nombre).side_effect = lambda *a, _n=nombre, **k: orden.append(_n)
        handler.cambiar_username(_evento(), None)
        assert orden == ["admin_create_user", "admin_set_user_password", "admin_add_user_to_group", "admin_delete_user"]

    @pytest.mark.parametrize("falla", ["admin_create_user", "admin_set_user_password", "admin_add_user_to_group"])
    def test_si_falla_la_creacion_se_descarta_la_nueva_y_no_se_toca_la_anterior(self, cuenta_sanidad, falla):
        getattr(cuenta_sanidad, falla).side_effect = _client_error("InternalErrorException")
        r = handler.cambiar_username(_evento(), None)
        assert r["statusCode"] == 500
        borrados = [c.kwargs["Username"] for c in cuenta_sanidad.admin_delete_user.call_args_list]
        assert borrados == ["sanidad.jefe"]  # solo la nueva; "sanidad" sigue intacta

    def test_si_falla_el_borrado_de_la_anterior_se_deshace_la_nueva(self, cuenta_sanidad):
        def _borra(UserPoolId, Username):
            if Username == "sanidad":
                raise _client_error("InternalErrorException")

        cuenta_sanidad.admin_delete_user.side_effect = _borra
        assert handler.cambiar_username(_evento(), None)["statusCode"] == 500
        borrados = [c.kwargs["Username"] for c in cuenta_sanidad.admin_delete_user.call_args_list]
        assert borrados == ["sanidad", "sanidad.jefe"]

    def test_un_fallo_al_descartar_no_tapa_el_error_original(self, cuenta_sanidad):
        cuenta_sanidad.admin_create_user.side_effect = _client_error("InternalErrorException", "original")
        cuenta_sanidad.admin_delete_user.side_effect = _client_error("InternalErrorException", "secundario")
        r = handler.cambiar_username(_evento(), None)
        assert r["statusCode"] == 500
        assert "original" in json.loads(r["body"])["error"]

    def test_password_rechazada_por_cognito_400(self, cuenta_sanidad):
        cuenta_sanidad.admin_set_user_password.side_effect = _client_error("InvalidPasswordException")
        assert handler.cambiar_username(_evento(), None)["statusCode"] == 400
        assert [c.kwargs["Username"] for c in cuenta_sanidad.admin_delete_user.call_args_list] == ["sanidad.jefe"]

    def test_error_inesperado_al_comprobar_si_existe_500(self, cuenta_sanidad):
        def _get(UserPoolId, Username):
            raise _client_error("InternalErrorException")

        cuenta_sanidad.admin_get_user.side_effect = _get
        assert handler.cambiar_username(_evento(), None)["statusCode"] == 500
        cuenta_sanidad.admin_create_user.assert_not_called()
