# QC Bot - Grabado Láser (Streamlit)

## Archivos
- `app.py` — la app.
- `orders.csv` — lista de órdenes (orden, cantidad, tipo ECM/CORP). Aquí guardas tú los datos del día.
- `requirements.txt` — dependencias.

## Subir a GitHub
1. Crea un repositorio nuevo (puede ser privado si quieres que `orders.csv` no sea público).
2. Sube estos 3 archivos (`app.py`, `orders.csv`, `requirements.txt`) a la raíz del repo.

## Desplegar (gratis, ~2 minutos)
1. Entra a https://share.streamlit.io con tu cuenta de GitHub.
2. "New app" → selecciona el repositorio → main file: `app.py` → Deploy.
3. Te da una URL pública (algo como `tu-app.streamlit.app`) que abre en cualquier navegador, celular incluido.

## Actualizar la lista de órdenes cada día (sin perder nada, nunca)
Para que guardar desde la app misma quede permanente (y no se borre si la app se reinicia),
el botón "Guardar lista" hace un commit directo a tu repo de GitHub. Necesitas configurar
un token una sola vez:

### 1. Crea un token de GitHub
1. En GitHub → foto de perfil → Settings → Developer settings → Personal access tokens →
   Fine-grained tokens → "Generate new token".
2. Dale acceso solo al repositorio de esta app, con permiso **Contents: Read and write**.
3. Copia el token (empieza con `github_pat_...`).

### 2. Configúralo en Streamlit Cloud (nunca lo subas al repo)
1. En tu app en https://share.streamlit.io → menú (⋮) → Settings → Secrets.
2. Pega esto, con tus datos:
```
[github]
token = "github_pat_TU_TOKEN_AQUI"
repo = "tu-usuario/tu-repositorio"
path = "orders.csv"
branch = "main"
```
3. Guarda. La app se reinicia sola y ya queda conectada.

### Ahora tienes dos formas de actualizar la lista, ambas permanentes:
- **Directo en GitHub**: edita `orders.csv` y haz commit. La app se redespliega sola.
- **Desde la app**: panel lateral (⚙️ Admin) → PIN (`2468`, cámbialo en `app.py`) → edita la
  tabla → "Guardar lista". Esto hace un commit real a GitHub — queda igual de permanente que
  editarlo a mano, y verás el historial de cambios en GitHub.

Si no configuras el token, "Guardar lista" sigue funcionando pero solo para la sesión actual
(se pierde si la app se reinicia) — la app te avisa con un mensaje si detecta que falta esta
configuración.

## El operador nunca ve la lista
El chat solo pide el número de orden y hace las preguntas de calidad. El tipo (ECM/CORP) se usa
por dentro para decidir el resultado, pero nunca se muestra en pantalla.
