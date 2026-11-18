# Credenciales — Trazabilidad GGGI (GEE + Streamlit)

Proyecto Google Earth Engine / Cloud: **`lulcc-traceability-mx40`**.

Hay **dos identidades**, cada una para su uso:

| Identidad | Para qué | Dónde vive |
|---|---|---|
| **Service account (SA)** | La app desplegada **y** los scripts de ingesta (no interactivo, no expira) | Llave JSON en `.streamlit/secrets.toml` (local, gitignored) y en los *Secrets* de Streamlit Cloud |
| **Cuenta personal** `traceability.associate@gmail.com` | Uso interactivo local (explorar assets, `earthengine` CLI) | `~/.config/earthengine/credentials` (tras `earthengine authenticate`) |

> **Nunca** se commitean llaves. `.streamlit/secrets.toml` y los `*.json` de llaves están en `.gitignore`.
> El valor de la llave lo colocas tú; las herramientas lo leen, pero no va al repo.

---

## 1. Service account — cómo obtener la llave (el "secret")

El `secret` que pide la app es el **archivo JSON de una llave del service account**. Dos formas de obtenerlo:

### Opción A — reutilizar el que ya usa la app (recomendada, misma identidad)
La app en Streamlit Cloud ya tiene este JSON en sus *Secrets*. Cópialo de ahí:
1. share.streamlit.io → tu app → **⋮ → Settings → Secrets**.
2. Copia el bloque `[earthengine]` completo (`service_account` y `credentials = '''...'''`).
3. Pégalo en el `.streamlit/secrets.toml` local (ver §2).

Así local y producción usan **exactamente** la misma llave.

### Opción B — generar una llave nueva (si no tienes acceso al secret anterior)
Google **no** deja volver a descargar una llave ya creada; si la perdiste, generas otra (puedes tener varias):
1. console.cloud.google.com → proyecto **`lulcc-traceability-mx40`**.
2. **IAM & Admin → Service Accounts**.
3. Elige el SA que usa la app (su correo termina en `@lulcc-traceability-mx40.iam.gserviceaccount.com`).
4. Pestaña **Keys → Add key → Create new key → JSON → Create** → se descarga un `.json`.
5. Ese archivo es el `secret`. Úsalo en §2.

> Si no existe aún un SA, créalo en **Service Accounts → Create**, dale un nombre (p.ej. `streamlit-ee`),
> y asígnale los roles de §4. Luego genera su llave (paso 4 de arriba).

---

## 2. Dónde poner la llave (local)

1. Copia la plantilla:  `cp .streamlit/secrets.toml.example .streamlit/secrets.toml`
2. Rellena en `secrets.toml`:
   - `[earthengine] service_account` = el correo del SA.
   - `[earthengine] credentials = '''<todo el contenido del JSON>'''` (comillas triples simples).
3. Listo. La app local y los scripts leen de ahí. **No** lo commitees (ya está gitignored).

---

## 3. Cuenta personal (para `earthengine` CLI / exploración)

```bash
earthengine authenticate
```
Completa el flujo en el navegador **con `traceability.associate@gmail.com`**. Esto guarda el token en
`~/.config/earthengine/credentials` y persiste.

> Si al usar la cuenta personal sale **403 `USER_PROJECT_DENIED`**, esa cuenta no tiene permiso de
> *usar* el proyecto: agrégala en **IAM** con el rol **Service Usage Consumer** (o **Editor**) sobre
> `lulcc-traceability-mx40`, y asegúrate de que esté registrada en Earth Engine.

---

## 4. Roles que necesita el SA

En **IAM & Admin → IAM**, el SA debe tener:
- **Earth Engine Resource Writer** (crear/leer/escribir assets) — o Editor del proyecto.
- **Service Usage Consumer** (usar las APIs del proyecto).
- **Storage Admin** (o *Storage Object Admin*) sobre el bucket de ingesta — solo si se usa GCS para subir COGs.

---

## 5. Ingesta de COGs a Earth Engine (usa el SA)

Requiere un **bucket de GCS** para hospedar el GeoTIFF antes de ingerirlo. Con `google-cloud-storage`
(ya instalado) no hace falta `gcloud`. Ver `cobiocom_lulc/RESUMEN_subir_capas.md` para los ids de asset
y el gotcha `pyramiding_policy=mode` (datos categóricos). Alternativa sin bucket: subir por la UI de
**Assets** del Code Editor (drag-and-drop del `.tif`).
