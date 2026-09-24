import os

# Variables de entorno requeridas por modulo_admin/handler.py al importarse.
# Se fijan aquí (en el conftest.py raíz) para que existan antes de que
# cualquier módulo de test importe el handler.
os.environ.setdefault("USER_POOL_ID", "us-east-1_TESTPOOL")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
