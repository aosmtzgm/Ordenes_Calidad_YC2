import streamlit as st
import pandas as pd
import os
import base64
import requests
from datetime import datetime

st.set_page_config(page_title="Revisión de calidad · Vasos", page_icon="🧊", layout="centered")

ORDERS_FILE = "orders.csv"
ADMIN_PIN = "2468"  # cámbialo aquí

# ---------- Datos de órdenes (orden, cantidad, tipo) ----------

def load_orders():
    if os.path.exists(ORDERS_FILE):
        df = pd.read_csv(ORDERS_FILE, dtype={"orden": str})
        df["tipo"] = df["tipo"].str.upper().apply(lambda t: "CORP" if t.startswith("CORP") else "ECM")
        return df
    return pd.DataFrame(columns=["orden", "cantidad", "tipo"])

def github_configured():
    return "github" in st.secrets and all(k in st.secrets["github"] for k in ("token", "repo"))

def save_orders(df):
    """Guarda localmente (para que la sesión actual lo vea de inmediato)
    y, si hay credenciales de GitHub configuradas, hace commit al repo
    para que el cambio quede permanente y no se pierda al reiniciar la app."""
    df.to_csv(ORDERS_FILE, index=False)

    if not github_configured():
        return False, ("No hay credenciales de GitHub configuradas (st.secrets['github']). "
                        "El cambio solo se guardó en este contenedor y se perderá si la app se reinicia. "
                        "Revisa el README para configurar el guardado permanente.")

    gh = st.secrets["github"]
    token = gh["token"]
    repo = gh["repo"]
    path = gh.get("path", ORDERS_FILE)
    branch = gh.get("branch", "main")

    api_url = f"https://api.github.com/repos/{repo}/contents/{path}"
    headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github+json"}

    try:
        get_resp = requests.get(api_url, headers=headers, params={"ref": branch}, timeout=10)
        sha = get_resp.json().get("sha") if get_resp.status_code == 200 else None

        content_str = df.to_csv(index=False)
        b64_content = base64.b64encode(content_str.encode("utf-8")).decode("utf-8")

        payload = {
            "message": f"Actualiza lista de órdenes — {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "content": b64_content,
            "branch": branch,
        }
        if sha:
            payload["sha"] = sha

        put_resp = requests.put(api_url, headers=headers, json=payload, timeout=10)
        if put_resp.status_code in (200, 201):
            return True, "Guardado permanentemente en GitHub ✅"
        else:
            return False, f"GitHub respondió con error ({put_resp.status_code}): {put_resp.text[:200]}"
    except Exception as e:
        return False, f"No se pudo conectar con GitHub: {e}"

def find_order(orden_num):
    df = load_orders()
    match = df[df["orden"].astype(str).str.strip() == str(orden_num).strip()]
    if match.empty:
        return None
    row = match.iloc[0]
    return {"orden": row["orden"], "cantidad": int(row["cantidad"]), "tipo": row["tipo"]}

# ---------- Estado del chat ----------

if "messages" not in st.session_state:
    st.session_state.messages = []
if "step" not in st.session_state:
    st.session_state.step = "ask_order"
if "order" not in st.session_state:
    st.session_state.order = None

def bot_say(text, tag=None):
    st.session_state.messages.append({"role": "assistant", "text": text, "tag": tag})

def user_say(text):
    st.session_state.messages.append({"role": "user", "text": text})

def go(step):
    st.session_state.step = step

def reset_flow():
    st.session_state.messages = []
    st.session_state.order = None
    bot_say("¡Hola! ¿Cuál es el número de orden a revisar?")
    go("ask_order")

if not st.session_state.messages:
    reset_flow()

# ---------- Lógica de negocio ----------

def process_order(orden_num):
    user_say(orden_num)
    found = find_order(orden_num)
    if not found:
        bot_say(f"No encontré la orden **{orden_num}** en la lista.\n\n"
                f"Verifica el número o contacta a tu supervisor para confirmar los datos.")
        go("retry")
        return
    st.session_state.order = found
    bot_say(f"Orden #{found['orden']} encontrada — {found['cantidad']} vasos.\n\nEmpecemos la revisión.")
    ask_paso1()

def ask_paso1():
    bot_say("¿Detectas lenguaje o imágenes inapropiadas en el diseño, o sospechas que es una imagen con "
            "copyright o marca registrada no autorizada?")
    go("paso1")

def answer_paso1(valor):
    user_say(valor)
    if valor == "Sí":
        bot_say("Notifica de inmediato a tu supervisor y no sigas con la producción.",
                tag="hold")
        if st.session_state.order["tipo"] == "CORP":
            bot_say("Abre un ticket para que el equipo de arte lo revise.", tag="hold")
        else:
            bot_say("Confirma con tu supervisor si además se necesita abrir un ticket.", tag="hold")
        go("result")
    else:
        ask_paso2()

def ask_paso2():
    bot_say("¿El grabado impreso coincide con el rendering en MES, o es una imagen tipo foto/dibujo "
            "con muchos detalles?")
    go("paso2")

def answer_paso2(valor):
    user_say(valor)
    if valor == "Sí":
        ask_paso2b()
    else:
        ask_paso3()

def ask_paso2b():
    bot_say("¿Es consistente con las demás unidades del mismo tamaño e imagen en este pedido?")
    go("paso2b")

def answer_paso2b(valor):
    user_say(valor)
    if valor == "Sí":
        bot_say("Continúa con la producción de la orden.", tag="pass")
        go("result")
    else:
        ask_paso3()

def ask_paso3():
    bot_say("¿Cuál describe mejor lo que ves en el vaso?")
    go("paso3")

def answer_paso3(opcion):
    user_say(opcion)
    if opcion.startswith("a)"):
        bot_say("El equipo de arte revisará los puntos o líneas extra antes de aprobar.", tag="ticket")
        go("result")
    elif opcion.startswith("b)"):
        if st.session_state.order["tipo"] == "ECM":
            bot_say("Este detalle en el registro o trademark se acepta tal cual.", tag="pass")
        else:
            bot_say("El equipo de arte debe revisar el registro o trademark antes de aprobar.", tag="ticket")
        go("result")
    elif opcion.startswith("c)"):
        cantidad = st.session_state.order["cantidad"]
        if cantidad < 5:
            bot_say("Al ser menos de 5 unidades con arte complejo, se aprueba directo.", tag="pass")
            go("result")
        else:
            bot_say("¿La mayoría de la imagen coincide con el rendering y solo falta un detalle menor?")
            go("paso3c_sub")
    else:
        bot_say("Contacta al equipo MES/IBM por el canal de Teams.", tag="contact")
        go("result")

def answer_paso3c_sub(valor):
    user_say(valor)
    if valor == "Sí":
        bot_say("La mayoría del diseño coincide con el rendering aprobado.", tag="pass")
    else:
        bot_say("La cantidad supera las 5 unidades y la mayoría del diseño no coincide con el rendering.",
                tag="ticket")
    go("result")

# ---------- Interfaz ----------

from avatars import BOT_AVATAR_B64, USER_AVATAR_B64

TAG_STYLE = {
    "pass":    {"color": "#1E8E3E", "bg": "#E6F6EB", "icon": "✅", "label": "PASA"},
    "ticket":  {"color": "#B7791F", "bg": "#FBF1E0", "icon": "🎟️", "label": "TICKET"},
    "contact": {"color": "#1A5FB4", "bg": "#E7F0FC", "icon": "📲", "label": "CONTACTAR MES/IBM"},
    "hold":    {"color": "#C62828", "bg": "#FBE9E9", "icon": "✋", "label": "DETENER"},
}

GREEN = "#1E9E6B"       # verde principal (no verde bandera, más tipo esmeralda)
GREEN_DARK = "#167A53"

st.markdown(f"""
<style>
.app-title{{font-size:1.4rem;font-weight:800;margin-bottom:0;color:{GREEN_DARK};}}
.app-sub{{color:#8A8A8E;font-size:0.85rem;margin-top:-4px;margin-bottom:0.6rem;}}

.msg-row{{display:flex;align-items:flex-end;gap:8px;margin:10px 0;}}
.msg-row.user{{flex-direction:row-reverse;}}
.msg-avatar{{width:32px;height:32px;border-radius:50%;object-fit:cover;flex-shrink:0;
    box-shadow:0 1px 3px rgba(0,0,0,.15);}}
.msg-bubble{{max-width:74%;padding:10px 14px;font-size:14.5px;line-height:1.4;}}
.msg-bubble.bot{{background:{GREEN};color:#fff;border-radius:4px 16px 16px 16px;}}
.msg-bubble.user{{background:#F0F0F2;color:#1C1C1E;border-radius:16px 4px 16px 16px;}}

.status-chip{{display:inline-flex;align-items:center;gap:6px;padding:4px 10px;border-radius:999px;
    font-weight:700;font-size:12.5px;margin-bottom:6px;}}

div.stButton > button{{
    border-radius:999px;
    border:1.5px solid {GREEN};
    color:{GREEN_DARK};
    background:#fff;
    font-weight:600;
    padding:0.5rem 1rem;
}}
div.stButton > button:hover{{background:{GREEN};color:#fff;border-color:{GREEN};}}
</style>
""", unsafe_allow_html=True)

st.markdown('<p class="app-title">YCBot 🐐</p>', unsafe_allow_html=True)
st.markdown('<p class="app-sub">Revisión de calidad · grabado láser en vasos</p>', unsafe_allow_html=True)

def render_bubble(role, text, tag=None):
    avatar_b64 = BOT_AVATAR_B64 if role == "bot" else USER_AVATAR_B64
    content = text.replace("\n", "<br>")
    if tag and tag in TAG_STYLE:
        t = TAG_STYLE[tag]
        content = (f'<span class="status-chip" style="background:{t["bg"]};color:{t["color"]};">'
                   f'{t["icon"]} {t["label"]}</span><br>{content}')
    return (
        f'<div class="msg-row {role}">'
        f'<img class="msg-avatar" src="data:image/png;base64,{avatar_b64}">'
        f'<div class="msg-bubble {role}">{content}</div>'
        f'</div>'
    )

# Caja de chat con altura fija: aquí vive el scroll, no en la página completa
chat_box = st.container(height=440, border=True)
with chat_box:
    html = "".join(
        render_bubble("bot" if m["role"] == "assistant" else "user", m["text"], m.get("tag"))
        for m in st.session_state.messages
    )
    st.markdown(html, unsafe_allow_html=True)

# ---------- Input según el paso actual ----------

step = st.session_state.step

if step == "ask_order":
    orden_num = st.chat_input("Número de orden")
    if orden_num:
        process_order(orden_num)
        st.rerun()

elif step == "retry":
    if st.button("🔄 Intentar de nuevo", use_container_width=True):
        reset_flow()
        st.rerun()

elif step == "paso1":
    c1, c2 = st.columns(2)
    if c1.button("Sí", use_container_width=True, key="p1_si"):
        answer_paso1("Sí"); st.rerun()
    if c2.button("No", use_container_width=True, key="p1_no"):
        answer_paso1("No"); st.rerun()

elif step == "paso2":
    c1, c2 = st.columns(2)
    if c1.button("Sí", use_container_width=True, key="p2_si"):
        answer_paso2("Sí"); st.rerun()
    if c2.button("No", use_container_width=True, key="p2_no"):
        answer_paso2("No"); st.rerun()

elif step == "paso2b":
    c1, c2 = st.columns(2)
    if c1.button("Sí", use_container_width=True, key="p2b_si"):
        answer_paso2b("Sí"); st.rerun()
    if c2.button("No", use_container_width=True, key="p2b_no"):
        answer_paso2b("No"); st.rerun()

elif step == "paso3":
    opciones = [
        "a) Puntos o líneas extra que no se ven en el rendering en MES.",
        "b) La marca registrada (®) o trademark (™) se ve con poca definición.",
        "c) Arte complejo (texto/logo).",
        "d) El tamaño o posición no coincide / está fuera de la ventana de grabado.",
        "e) El logo de frente y reverso están intercambiados.",
        "f) El color o tamaño del producto no coincide con lo que indica el rendering en MES.",
    ]
    for i, op in enumerate(opciones):
        if st.button(op, use_container_width=True, key=f"p3_{i}"):
            answer_paso3(op); st.rerun()

elif step == "paso3c_sub":
    c1, c2 = st.columns(2)
    if c1.button("Sí", use_container_width=True, key="p3c_si"):
        answer_paso3c_sub("Sí"); st.rerun()
    if c2.button("No", use_container_width=True, key="p3c_no"):
        answer_paso3c_sub("No"); st.rerun()

elif step == "result":
    if st.button("🔄 Revisar otra orden", use_container_width=True):
        reset_flow(); st.rerun()

# ---------- Panel admin (oculto, con PIN) ----------

with st.sidebar:
    st.subheader("⚙️ Admin")
    pin = st.text_input("PIN", type="password", key="admin_pin")
    if pin == ADMIN_PIN:
        st.success("Acceso concedido")

        st.markdown("**Cargar órdenes desde Excel o CSV**")
        st.caption("El archivo debe tener las columnas: `orden`, `cantidad`, `tipo` (ECM o CORP). "
                   "Las órdenes que ya existan (mismo número) se omiten automáticamente.")
        uploaded = st.file_uploader("Archivo", type=["xlsx", "csv"], key="orders_uploader")

        if uploaded is not None:
            file_id = getattr(uploaded, "file_id", uploaded.name + str(uploaded.size))
            if st.session_state.get("last_uploaded_id") != file_id:
                try:
                    if uploaded.name.lower().endswith(".csv"):
                        new_df = pd.read_csv(uploaded, dtype={"orden": str})
                    else:
                        new_df = pd.read_excel(uploaded, dtype={"orden": str})
                    new_df.columns = [c.strip().lower() for c in new_df.columns]

                    required = {"orden", "cantidad", "tipo"}
                    if not required.issubset(set(new_df.columns)):
                        st.error("El archivo debe tener las columnas: orden, cantidad, tipo")
                    else:
                        new_df = new_df[["orden", "cantidad", "tipo"]].copy()
                        new_df["orden"] = new_df["orden"].astype(str).str.strip()
                        new_df["tipo"] = new_df["tipo"].astype(str).str.upper().apply(
                            lambda t: "CORP" if t.startswith("CORP") else "ECM"
                        )

                        existing_df = load_orders()
                        combined = pd.concat([existing_df, new_df], ignore_index=True)
                        combined = combined.drop_duplicates(subset="orden", keep="first")

                        agregadas = len(combined) - len(existing_df)
                        omitidas = len(new_df) - agregadas

                        ok, msg = save_orders(combined)
                        resumen = f"{agregadas} órdenes nuevas agregadas, {omitidas} repetidas omitidas."
                        if ok:
                            st.success(f"{resumen} {msg}")
                        else:
                            st.warning(f"{resumen} {msg}")

                    st.session_state["last_uploaded_id"] = file_id
                except Exception as e:
                    st.error(f"No se pudo leer el archivo: {e}")
            else:
                st.info("Este archivo ya fue cargado.")

        st.markdown("---")
        st.markdown("**Editar lista manualmente**")
        df = load_orders()
        st.caption("Una fila por orden. El operador nunca ve esta tabla.")
        edited = st.data_editor(df, num_rows="dynamic", use_container_width=True, key="editor")
        if st.button("Guardar lista"):
            ok, msg = save_orders(edited)
            if ok:
                st.success(f"{msg} — {len(edited)} órdenes.")
            else:
                st.warning(msg)
    elif pin:
        st.error("PIN incorrecto")
