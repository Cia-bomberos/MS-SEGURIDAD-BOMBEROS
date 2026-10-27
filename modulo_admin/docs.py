import json
import os

def servir_docs(event, context):
    """Devuelve la interfaz de Swagger UI."""
    html = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <title>MS-SEGURIDAD-BOMBEROS - API Docs</title>
        <link rel="stylesheet" type="text/css" href="https://unpkg.com/swagger-ui-dist@5.11.0/swagger-ui.css" />
        <style>
            html { box-sizing: border-box; overflow: -moz-scrollbars-vertical; overflow-y: scroll; }
            *, *:before, *:after { box-sizing: inherit; }
            body { margin:0; background: #fafafa; }
        </style>
    </head>
    <body>
        <div id="swagger-ui"></div>
        <script src="https://unpkg.com/swagger-ui-dist@5.11.0/swagger-ui-bundle.js"></script>
        <script>
            window.onload = () => {
                window.ui = SwaggerUIBundle({
                    url: './openapi.json',
                    dom_id: '#swagger-ui',
                    deepLinking: true,
                    presets: [SwaggerUIBundle.presets.apis, SwaggerUIBundle.SwaggerUIStandalonePreset],
                    layout: "BaseLayout"
                });
            };
        </script>
    </body>
    </html>
    """
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "text/html"},
        "body": html,
    }

def servir_openapi(event, context):
    """Devuelve el archivo openapi.json."""
    try:
        # Asume que el archivo está en la raíz del proyecto empaquetado
        with open("openapi.json", "r", encoding="utf-8") as f:
            contenido = f.read()
        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": contenido,
        }
    except FileNotFoundError:
        return {
            "statusCode": 404,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"error": "openapi.json no encontrado."}),
        }