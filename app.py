import os
import json
import re
import uuid
import html
import streamlit as st
import paho.mqtt.client as mqtt
import time
from openai import OpenAI
from casos_asesinatos import CASOS_ASESINATOS
from casos_secuestros import CASOS_SECUESTROS

BROKER = "broker.hivemq.com"
PORT = 1883

st.set_page_config(page_title="ARCHIVO 09 | Unidad de Casos Especiales", page_icon="🕵️", layout="wide", initial_sidebar_state="expanded")

# ======================== ESTÉTICA ========================
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600;700&family=Special+Elite&display=swap');
:root{--paper:#e9e3d4;--ink:#17221e;--red:#a72d2d;--green:#38734b;--gold:#b28a32;}
.stApp{background:#171c1b;color:#e9e3d4}
[data-testid="stSidebar"]{background:#202725;border-right:1px solid #4d5650}
[data-testid="stSidebar"] *{color:#e9e3d4!important}
h1,h2,h3{font-family:'Special Elite',monospace!important;letter-spacing:1px}
p,label,div,span{font-family:'IBM Plex Mono',monospace}
.hero{background:var(--paper);color:var(--ink);padding:2rem 2.3rem;border-left:8px solid var(--red);box-shadow:7px 7px 0 #080b0a;margin-bottom:1.5rem}
.hero h1{font-size:clamp(2.5rem,6vw,5rem);margin:.35rem 0;color:#17221e}
.hero h1 span{color:var(--red)}
.eyebrow,.folder-tag{font-size:.76rem;font-weight:700;letter-spacing:2px;color:var(--red)}
.subtitle{font-size:1rem}
.stamp{display:inline-block;border:2px solid var(--red);color:var(--red);padding:.35rem .55rem;transform:rotate(-1deg);font-size:.72rem;margin-top:.6rem}
.folder-card{min-height:220px;background:#e9e3d4;color:#17221e;padding:1.3rem;border-top:7px solid #a72d2d;box-shadow:5px 5px 0 #080b0a;margin-bottom:1rem}
.folder-card h2{color:#17221e}
.case-sheet{background:#e9e3d4;color:#17221e;padding:1.3rem 1.5rem;border-left:6px solid #a72d2d;margin:.6rem 0 1rem}
.case-sheet h2,.case-sheet h3{color:#17221e}
.case-label{font-size:.72rem;letter-spacing:1.4px;color:#a72d2d;font-weight:700}
.suspect-card{border:1px solid #626b63;padding:1rem;margin:.35rem 0;background:#222927;min-height:120px}
.small-muted{color:#b6b9ad;font-size:.8rem}
div.stButton>button,div.stDownloadButton>button{border-radius:2px;border:1px solid #c4c0b3;font-family:'IBM Plex Mono',monospace}
div.stButton>button[kind="primary"]{background:#a72d2d;border-color:#a72d2d}
input,textarea{border-radius:2px!important}
.stAlert{border-radius:2px}
</style>
""", unsafe_allow_html=True)

# ======================== OPENAI + MQTT ========================
def get_client(api_key):
    if not api_key or not api_key.strip():
        raise ValueError("Escribe tu clave API de OpenAI para iniciar el interrogatorio.")
    return OpenAI(api_key=api_key.strip())

def enviar_mqtt(topic, payload):
    """Publica la clasificación de la IA en el broker MQTT."""

    cliente = None

    try:
        # Identificador único para Streamlit
        client_id = "Salitostreamlit_" + str(int(time.time() * 1000))

        # Compatible con diferentes versiones de Paho MQTT
        try:
            cliente = mqtt.Client(
                callback_api_version=mqtt.CallbackAPIVersion.VERSION1,
                client_id=client_id
            )
        except (AttributeError, TypeError):
            cliente = mqtt.Client(client_id=client_id)

        cliente.connect(BROKER, PORT, keepalive=30)
        cliente.loop_start()

        mensaje = json.dumps(payload, ensure_ascii=False)

        resultado = cliente.publish(topic, mensaje, qos=0)

        resultado.wait_for_publish(timeout=10)

        if resultado.is_published():
            st.session_state.ultimo_mensaje = (
                f"Señal enviada correctamente: {payload['status']}"
            )
            return True, mensaje

        return False, "No se pudo confirmar la publicación MQTT."

    except Exception as error:
        return False, str(error)

    finally:
        if cliente is not None:
            try:
                cliente.loop_stop()
                cliente.disconnect()
            except Exception:
                pass


def publish_wokwi(status, room):
    """Envía a Wokwi el resultado de veracidad generado por la IA."""

    room = re.sub(r"[^a-zA-Z0-9_-]", "", str(room))[:48]

    if not room:
        return False, "El ID de sala MQTT está vacío."

    topic = f"archivo09/{room}/truth"

    payload = {
        "status": status,
        "room": room
    }

    return enviar_mqtt(topic, payload)

def transcribe_audio(client, audio_file):
    if audio_file is None:
        return ""
    raw = audio_file.getvalue()
    if not raw:
        return ""
    filename = getattr(audio_file, "name", "pregunta.wav")
    suffix = os.path.splitext(filename)[1] or ".wav"
    result = client.audio.transcriptions.create(
        model="gpt-4o-mini-transcribe",
        file=(f"pregunta{suffix}", raw, getattr(audio_file, "type", "audio/wav") or "audio/wav"),
        language="es",
    )
    return result.text.strip()

def interrogate(client, case, suspect_name, question):
    suspect = next(s for s in case["suspects"] if s["name"] == suspect_name)
    facts = json.dumps(case["truth_ledger"], ensure_ascii=False)
    profile = json.dumps(suspect, ensure_ascii=False)
    system = f"""Eres un personaje de un juego ficticio de detectives. Responde SIEMPRE en español, en primera persona, natural y brevemente (2 a 5 frases).
CASO: {case['title']}
RESUMEN: {case['description']}
VERDAD OFICIAL (no la reveles directamente salvo que el personaje la admita): {facts}
FICHA DEL SOSPECHOSO: {profile}
Reglas: mantén la personalidad y los conocimientos de la ficha; no inventes hechos que contradigan el expediente. La etiqueta describe la veracidad de la declaración, no la culpabilidad. Usa true si la afirmación principal coincide con los hechos, false si los contradice o encubre un hecho conocido y unknown si no hay información suficiente. No marques automáticamente una negativa o una opinión como mentira. Devuelve exclusivamente JSON válido con answer y truth_status; truth_status debe ser true, false o unknown."""
    response = client.chat.completions.create(
        model="gpt-4o-mini", temperature=0.25, response_format={"type":"json_object"},
        messages=[{"role":"system","content":system},{"role":"user","content":question}],
    )
    data = json.loads(response.choices[0].message.content)
    if data.get("truth_status") not in ("true", "false", "unknown"):
        data["truth_status"] = "unknown"
    data["answer"] = str(data.get("answer", "No tengo nada más que declarar."))
    return data

def render_case(case, category):
    st.markdown(f"""<div class="case-sheet"><div class="case-label">EXPEDIENTE {html.escape(str(case['id']))} · {html.escape(category.upper())} · {html.escape(case['difficulty'].upper())}</div><h2>{html.escape(case['title'])}</h2><p>{html.escape(case['description'])}</p><p><b>Víctima / persona afectada:</b> {html.escape(case['victim'])}</p><p><b>Lugar relacionado:</b> {html.escape(case['location'])}</p><p><b>Arma / elemento clave:</b> {html.escape(case['weapon'])}</p></div>""", unsafe_allow_html=True)
    st.markdown("### EVIDENCIAS RECUPERADAS")
    for i, clue in enumerate(case["clues"], 1):
        st.markdown(f"- **E{i:02d}.** {clue}")
    st.markdown("### PERSONAS DE INTERÉS")
    cols = st.columns(2)
    for i, suspect in enumerate(case["suspects"]):
        with cols[i % 2]:
            st.markdown(f"""<div class="suspect-card"><b>{html.escape(suspect['name'])}</b><br><span class="small-muted">{html.escape(suspect['role'])}</span><br><br>{html.escape(suspect['public_statement'])}</div>""", unsafe_allow_html=True)

def set_unit(name):
    st.session_state["unit"] = name

def render_unit(category, cases, room):
    st.markdown(f"""<div class="hero"><div class="eyebrow">POLICÍA · ARCHIVO 09</div><h1>{html.escape(category.upper())}</h1><p class="subtitle">Cada declaración puede acercarte a la verdad… o desviarte de ella.</p><div class="stamp">DOCUMENTO CONFIDENCIAL</div></div>""", unsafe_allow_html=True)
    difficulty = st.selectbox("FILTRAR POR DIFICULTAD", ["Todos", "Fácil", "Intermedio", "Difícil"], key=f"diff_{category}")
    visible = [c for c in cases if difficulty == "Todos" or c["difficulty"] == difficulty]
    labels = {f"{c['id']} · {c['title']} [{c['difficulty']}]": c for c in visible}
    case = labels[st.selectbox("ARCHIVADOR DE EXPEDIENTES", list(labels.keys()), key=f"case_{category}")]
    render_case(case, category)
    st.markdown("### SALA DE INTERROGATORIOS")
    api_key = st.text_input("CLAVE API DE OPENAI", type="password", key=f"api_{category}_{case['id']}", placeholder="Pega tu clave sk-…")
    st.caption("La clave se introduce aquí en la sesión; no la escribas dentro del código ni la subas a GitHub.")
    suspect_names = [s["name"] for s in case["suspects"]]
    selected = st.selectbox("Selecciona a quién interrogar", suspect_names, key=f"suspect_{category}_{case['id']}")
    st.write("Graba tu pregunta con el micrófono o escríbela en el campo de texto.")
    audio = st.audio_input("Grabar pregunta", key=f"audio_{category}_{case['id']}_{selected}")
    typed = st.text_input("O escribe tu pregunta", key=f"typed_{category}_{case['id']}_{selected}", placeholder="¿Dónde estabas a las nueve?")
    if st.button("INICIAR INTERROGATORIO", type="primary", key=f"ask_{category}_{case['id']}_{selected}"):
        try:
            client = get_client(api_key)
            question = typed.strip()
            if audio is not None:
                with st.spinner("Transcribiendo audio..."):
                    spoken = transcribe_audio(client, audio)
                if spoken:
                    question = spoken
                    st.info(f"Pregunta reconocida: “{question}”")
            if not question:
                st.warning("Graba una pregunta o escribe una antes de iniciar el interrogatorio.")
            else:
                with st.spinner(f"Interrogando a {selected}..."):
                    result = interrogate(client, case, selected, question)
                st.markdown("#### DECLARACIÓN REGISTRADA")
                st.markdown(f"> {result['answer']}")
                status = result["truth_status"]
                if status == "true": st.success("DECLARACIÓN VERDADERA · LED VERDE")
                elif status == "false": st.error("POSIBLE MENTIRA · LED ROJO")
                else: st.warning("VERACIDAD NO DETERMINADA · LED BLANCO")
                try:
                    enviado, respuesta_mqtt = publish_wokwi(status, room)
                    if enviado:
                        st.success("SEÑAL ENVIADA A LA UNIDAD DE ANÁLISIS.")
                    else:
                        st.warning(f"No se pudo enviar la señal a Wokwi: {respuesta_mqtt}")

                except Exception as exc:
                    st.warning(f"Error de conexión MQTT: {exc}")
                history_key = f"history_{category}_{case['id']}"
                st.session_state.setdefault(history_key, []).append({"suspect":selected,"question":question,"answer":result["answer"],"status":status})
        except Exception as exc:
            st.error(f"No se pudo completar el interrogatorio: {exc}")
    history_key = f"history_{category}_{case['id']}"
    if st.session_state.get(history_key):
        with st.expander("REGISTRO DE INTERROGATORIOS"):
            for item in reversed(st.session_state[history_key]):
                icon = {"true":"🟢","false":"🔴","unknown":"⚪"}.get(item["status"],"⚪")
                st.markdown(f"**{icon} {item['suspect']}** · {item['question']}")
                st.write(item["answer"])
    st.markdown("---")
    st.markdown("### ACUSACIÓN FINAL")
    st.caption("Contrasta las pistas y señala a quien consideras responsable.")
    accused = st.selectbox("Señalar responsable", suspect_names, key=f"accuse_{category}_{case['id']}")
    if st.button("PRESENTAR ACUSACIÓN", key=f"submit_{category}_{case['id']}"):
        if accused == case["culprit"]:
            st.success("CASO RESUELTO. La acusación coincide con la reconstrucción oficial.")
            st.balloons()
            st.session_state.setdefault("solved_cases", set()).add(f"{category}:{case['id']}")
        else:
            st.error("ACUSACIÓN NO SUSTENTADA. Revisa las pistas e interroga de nuevo.")
    solved = st.session_state.get("solved_cases", set())
    count = sum(1 for c in cases if f"{category}:{c['id']}" in solved)
    st.progress(count / len(cases), text=f"Expedientes resueltos en esta unidad: {count}/{len(cases)}")

# ======================== NAVEGACIÓN ========================
with st.sidebar:
    st.markdown("## ARCHIVO 09")
    st.markdown("**UNIDAD DE CASOS ESPECIALES**")
    category_choice = st.radio("SELECCIONAR UNIDAD", ["Centro de investigación", "Asesinatos", "Secuestros"], key="unit")
    st.markdown("---")
    st.markdown("## CONEXIÓN WOKWI")
    room = st.text_input("ID de sala MQTT", value=st.session_state.get("mqtt_room", "detective-demo"), key="mqtt_room_input")
    st.session_state["mqtt_room"] = re.sub(r"[^a-zA-Z0-9_-]", "", room)[:48] or "detective-demo"
    st.caption(f"Broker: {os.getenv('MQTT_BROKER','broker.hivemq.com')}:{os.getenv('MQTT_PORT','1883')}")
    st.caption("🟢 Verdad · 🔴 Mentira · ⚪ No determinado")

if category_choice == "Centro de investigación":
    st.markdown("""<div class="hero"><div class="eyebrow">POLICÍA · UNIDAD DE CASOS ESPECIALES</div><h1>ARCHIVO <span>09</span></h1><p class="subtitle">Los hechos no mienten. Las personas, a veces.</p><div class="stamp">ACCESO RESTRINGIDO · SOLO PERSONAL AUTORIZADO</div></div>""", unsafe_allow_html=True)
    st.markdown("## CENTRO DE INVESTIGACIÓN")
    st.write("Selecciona una unidad desde el menú lateral. Interroga sospechosos por voz o texto, contrasta declaraciones con las evidencias y acusa al responsable.")
    a,b = st.columns(2)
    with a:
        st.markdown("<div class='folder-card'><div class='folder-tag'>UNIDAD 01</div><h2>Asesinatos</h2><p>5 expedientes · Dificultad progresiva</p><p>Reconstruye los hechos y descubre al responsable.</p></div>", unsafe_allow_html=True)
        st.button("ABRIR EXPEDIENTES DE ASESINATO →", key="go_murder", on_click=set_unit, args=("Asesinatos",))
    with b:
        st.markdown("<div class='folder-card'><div class='folder-tag'>UNIDAD 02</div><h2>Secuestros</h2><p>5 expedientes · Dificultad progresiva</p><p>Analiza mensajes, rastros y testimonios para localizar a la víctima.</p></div>", unsafe_allow_html=True)
        st.button("ABRIR EXPEDIENTES DE SECUESTRO →", key="go_kidnap", on_click=set_unit, args=("Secuestros",))
    st.markdown("---")
    st.info("Introduce tu clave de OpenAI dentro del expediente que abras. Wokwi se conecta por MQTT; el ID de sala de esta barra lateral debe coincidir con ROOM_ID en el código del ESP32.")
    st.caption("ARCHIVO 09 · Prototipo académico · Casos y personajes ficticios. La clasificación de veracidad hecha por IA puede equivocarse.")
elif category_choice == "Asesinatos":
    render_unit("Asesinatos", CASOS_ASESINATOS, st.session_state["mqtt_room"])
else:
    render_unit("Secuestros", CASOS_SECUESTROS, st.session_state["mqtt_room"])
