import streamlit as st
import pandas as pd
import os
import base64
import requests
from datetime import datetime

st.set_page_config(page_title="QC Bot · Grabado Láser", page_icon="🧊", layout="centered")

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
        # Necesitamos el sha del archivo actual para poder actualizarlo
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
    bot_say("Hola 👋 Vamos a revisar una orden.\n\n¿Cuál es el número de orden?")
    go("ask_order")

if not st.session_state.messages:
    reset_flow()

# ---------- Lógica de negocio ----------

def process_order(orden_num):
    user_say(orden_num)
    found = find_order(orden_num)
    if not found:
        bot_say(f"No encontré la orden **{orden_num}** en la lista actualizada.\n\n"
                f"Verifica el número o contacta a tu supervisor para confirmar los datos.")
        go("retry")
        return
    st.session_state.order = found
    bot_say(f"Orden #{found['orden']} encontrada — {found['cantidad']} unidades.\n\nEmpecemos la revisión.")
    ask_paso1()

def ask_paso1():
    bot_say("¿Detectas lenguaje o imagen inapropiada en el diseño, o sospechas que es una imagen con "
            "copyright/marca registrada no autorizada por el cliente?")
    go("paso1")

def answer_paso1(valor):
    user_say(valor)
    if valor == "Sí":
        bot_say("🛑 DETENER EL ENVÍO.\n\nNotifica de inmediato a tu equipo de calidad antes de que la "
                "orden continúe. No debe salir hasta recibir confirmación.", tag="hold")
        if st.session_state.order["tipo"] == "CORP":
            bot_say("Adicionalmente, abre un ticket en ServiceNow para que el equipo de arte lo revise a fondo.", tag="hold")
        else:
            bot_say("Notifica también a tu supervisor para confirmar si además se requiere ticket.", tag="hold")
        go("result")
    else:
        ask_paso2()

def ask_paso2():
    bot_say("¿El grabado impreso coincide con el rendering aprobado en pantalla, o es una imagen tipo "
            "foto/dibujo con muchos tonos de detalle?")
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
        bot_say("✅ PASA.\n\nEl grabado coincide con el rendering aprobado y es consistente entre unidades.", tag="pass")
        go("result")
    else:
        ask_paso3()

def ask_paso3():
    bot_say("¿Cuál describe mejor lo que ves en el vaso?")
    go("paso3")

def answer_paso3(opcion):
    user_say(opcion)
    if opcion.startswith("a)"):
        bot_say("🎫 Abre un ticket en ServiceNow.\n\nEl equipo de arte revisará los puntos/líneas extra antes de aprobar.", tag="ticket")
        go("result")
    elif opcion.startswith("b)"):
        if st.session_state.order["tipo"] == "ECM":
            bot_say("✅ PASA.\n\nEste tipo de detalle en el registro/trademark se acepta tal cual.", tag="pass")
        else:
            bot_say("🎫 Abre un ticket en ServiceNow.\n\nEl equipo de arte debe revisar el registro/trademark antes de aprobar.", tag="ticket")
        go("result")
    elif opcion.startswith("c)"):
        cantidad = st.session_state.order["cantidad"]
        if cantidad < 5:
            bot_say("✅ PASA.\n\nAl ser menos de 5 unidades con arte complejo, se aprueba directo.", tag="pass")
            go("result")
        else:
            bot_say("¿La mayoría de la imagen coincide con el rendering y solo falta un detalle menor?")
            go("paso3c_sub")
    else:
        bot_say("📞 Contacta al equipo MES/IBM por el canal de Teams.\n\nEste tipo de problema no se resuelve "
                "con un ticket de ServiceNow — ellos deben corregirlo directamente.", tag="contact")
        go("result")

def answer_paso3c_sub(valor):
    user_say(valor)
    if valor == "Sí":
        bot_say("✅ PASA.\n\nLa mayoría del diseño coincide con el rendering aprobado.", tag="pass")
    else:
        bot_say("🎫 Abre un ticket en ServiceNow.\n\nLa cantidad supera las 5 unidades y la mayoría del diseño "
                "no coincide con el rendering.", tag="ticket")
    go("result")

# ---------- Interfaz: header ----------

st.markdown("""
<style>
.header-box{
    background:#075E54;color:#fff;padding:14px 18px;border-radius:12px 12px 0 0;
    display:flex;align-items:center;gap:10px;margin-bottom:0;
}
.header-box .name{font-weight:600;font-size:16px;}
.header-box .status{font-size:12px;color:#CFEFE9;}
.chat-box{background:#E5DDD5;padding:16px;border-radius:0 0 12px 12px;min-height:400px;}
.bubble-in{background:#fff;padding:10px 12px;border-radius:0 10px 10px 10px;margin:6px 0;
    max-width:85%;box-shadow:0 1px 1px rgba(0,0,0,.1);}
.bubble-out{background:#DCF8C6;padding:10px 12px;border-radius:10px 0 10px 10px;margin:6px 0 6px auto;
    max-width:85%;box-shadow:0 1px 1px rgba(0,0,0,.1);text-align:right;}
.tag-pass{border-left:4px solid #1E8E3E;}
.tag-ticket{border-left:4px solid #B7791F;}
.tag-contact{border-left:4px solid #1A5FB4;}
.tag-hold{border-left:4px solid #C62828;}
</style>
<div class="header-box">
  <div style="font-size:22px;">🧊</div>
  <div>
    <div class="name">QC Bot · Grabado Láser</div>
    <div class="status">en línea</div>
  </div>
</div>
""", unsafe_allow_html=True)

chat_html = '<div class="chat-box">'
for m in st.session_state.messages:
    text = m["text"].replace("\n", "<br>")
    if m["role"] == "assistant":
        tag_class = f' tag-{m["tag"]}' if m.get("tag") else ""
        chat_html += f'<div class="bubble-in{tag_class}">{text}</div>'
    else:
        chat_html += f'<div class="bubble-out">{text}</div>'
chat_html += '</div>'
st.markdown(chat_html, unsafe_allow_html=True)

# ---------- Interfaz: input según el paso actual ----------

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
        "a) Puntos o líneas extra que no se ven en el rendering",
        "b) El registro (®) o trademark (™) se ve con poca definición",
        "c) Arte complejo (texto/logo) con un detalle menor faltante",
        "d) El tamaño o posición no coincide / está fuera de la ventana de marcado",
        "e) La imagen de frente y reverso están intercambiadas",
        "f) El color o tamaño del producto no coincide con lo que indica el sistema",
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
