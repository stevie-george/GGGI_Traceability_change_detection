"""ee_auth.py — autentica Earth Engine evitando el bug de SSL del almacén de
certificados de Windows ([ASN1: NOT_ENOUGH_DATA] en _load_windows_store_certs,
que hace fallar el canje del código OAuth por el token).

Fuerza las conexiones HTTPS a usar el bundle de certifi en vez del store de
Windows. Uso:

    python ee_auth.py

Inicia sesión con la cuenta correcta (traceability.associate@gmail.com) y acepta
los permisos de Earth Engine. Al terminar, guarda las credenciales en la ruta
canónica que lee ee.Initialize.
"""
import ssl
import certifi
import ee

# ee.oauth canjea el código por el token con urllib.request.urlopen, que al
# conectar toma ssl._create_default_https_context. Lo apuntamos a un contexto
# basado en certifi -> nunca se llama _load_windows_store_certs (el que revienta).
_certifi_ctx = ssl.create_default_context(cafile=certifi.where())
ssl._create_default_https_context = lambda *a, **k: _certifi_ctx

print("Abriendo el flujo de autenticacion de Earth Engine...")
print("-> Inicia sesion con traceability.associate@gmail.com y acepta los permisos.\n")
ee.Authenticate(force=True)
print("\nOK: credenciales guardadas en", ee.oauth.get_credentials_path())
