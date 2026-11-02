import os
import json
import re
import uuid
import html
import time
import streamlit as st
import paho.mqtt.client as mqtt

from openai import OpenAI
from casos_asesinatos import CASOS_ASESINATOS
from casos_secuestros import CASOS_SECUESTROS


# =========================================================
# CONFIGURACIÓN GENERAL
# =========================================================

st.set_page_config(
    page_title="ARCHIVO 09 | Unidad de Investigación",
    page_icon="🕵️",
    layout="wide",
    initial_sidebar_state="expanded"
)

BROKER = "broker.hivemq.com"
PORT = 1883


# =========================================================
# ESTILOS
# =========================================================

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600;700&family=Special+Elite&display=swap');

html, body, [class*="css"] {
    font-family: 'IBM Plex Mono', monospace;
}

.stApp {
    background-color: #101713;
    color: #e8e0cd;
}

h1, h2, h3 {
    font-family: 'Special Elite', cursive !important;
    color: #e8e0cd;
}

p, label, span, div {
    color: #e8e0cd;
}

[data-testid="stSidebar"] {
    background-color: #19231d;
    border-right: 1px solid #59634e;
}

[data-testid="stSidebar"] * {
    color: #e8e0cd;
}

.hero {
    background: #e5dcc5;
    color: #1b241e;
    padding: 30px;
    border-left: 7px solid #9b3434;
    margin-bottom: 25px;
}

.hero h1 {
    color: #1b241e !important;
    font-size: 42px;
    margin-bottom: 5px;
}

.hero p {
    color: #394238;
    margin-bottom: 0;
}

.section-title {
    font-family: 'Special Elite', cursive;
    font-size: 25px;
    color: #d7c9a8;
    border-bottom: 1px solid #59634e;
    padding-bottom: 10px;
    margin-top: 25px;
    margin-bottom: 15px;
}

.case-card {
    background: #e5dcc5;
    color: #1b241e;
    padding: 20px;
    border-left: 5px solid #9b3434;
    min-height: 190px;
    margin-bottom: 10px;
}

.case-card h3 {
    color: #1b241e !important;
    font-size: 22px;
}

.case-card p {
    color: #394238 !important;
    font-size: 13px;
}

.suspect-card {
    background: #202c24;
    border: 1px solid #59634e;
    padding: 18px;
    min-height: 150px;
    margin-bottom: 10px;
}

.suspect-card.selected {
    border: 2px solid #c9b47c;
    background: #2a382e;
}

.suspect-card h3 {
    font-size: 19px;
    margin-bottom: 5px;
}

.suspect-card p {
    font-size: 12px;
    color: #c6bea9;
}

.evidence-card {
    background: #e5dcc5;
    color: #1b241e;
    padding: 15px;
    margin-bottom: 10px;
    border-left: 4px solid #59634e;
}

.evidence-card p {
    color: #30392f !important;
}

.stButton > button {
    background-color: #9b3434;
    color: #ffffff;
    border: none;
    border-radius: 2px;
    font-family: 'IBM Plex Mono', monospace;
    font-weight: 600;
    width: 100%;
}

.stButton > button:hover {
    background-color: #bd4949;
    color: white;
    border: none;
}

.stTextInput input, .stTextArea textarea {
    background-color: #202c24;
    color: #e8e0cd;
    border: 1px solid #59634e;
}

.stSelectbox div[data-baseweb="select"] {
    background-color: #202c24;
}

.stProgress > div > div {
    background-color: #9b3434;
}

hr {
    border-color: #59634e;
}

.status-label {
    color: #c9b47c;
    font-size: 12px;
    letter-spacing: 2px;
}

</style>
""", unsafe_allow_html=True)


# =========================================================
# FUNCIONES GENERALES
# =========================================================

def get_client(api_key):
    return OpenAI(api_key=api_key)


def enviar_mqtt(topic, payload):
    cliente = None

    try:
        client_id = "Salitostreamlit_" + str(int(time.time() * 1000))

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
                f"Tema: {topic} | Mensaje: {mensaje}"
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
    room = re.sub(r"[^a-zA-Z0-9_-]", "", room.strip())

    if not room:
        room = "detective-demo"

    topic = f"archivo09/{room}/truth"

    payload = {
        "status": status,
        "room": room
    }

    return enviar_mqtt(topic, payload)


def transcribe_audio(client, audio_file):
    try:
        transcription = client.audio.transcriptions.create(
            model="gpt-4o-mini-transcribe",
            file=audio_file
        )

        return transcription.text

    except Exception as error:
        st.error(f"No fue posible transcribir el audio: {error}")
        return None


# =========================================================
# INTERROGATORIO CON IA
# =========================================================

def interrogate(client, case, suspect_name, question, history=None):

    suspect = next(
        (
            s for s in case["suspects"]
            if s["name"] == suspect_name
        ),
        None
    )

    if suspect is None:
        return None

    history = history or []

    system_prompt = f"""
Eres un personaje dentro de un juego de investigación criminal llamado ARCHIVO 09.

Debes interpretar exclusivamente al sospechoso seleccionado.

INFORMACIÓN DEL CASO:
Título: {case["title"]}
Descripción: {case["description"]}
Víctima: {case["victim"]}
Ubicación: {case["location"]}
Elemento principal: {case["weapon"]}

SOSPECHOSO QUE DEBES INTERPRETAR:
Nombre: {suspect["name"]}
Rol: {suspect["role"]}
Declaración inicial: {suspect["public_statement"]}

REGISTRO DE VERDAD DEL CASO:
{json.dumps(case["truth_ledger"], ensure_ascii=False, indent=2)}

INSTRUCCIONES DE INTERPRETACIÓN:

- Responde siempre en primera persona, como el sospechoso.
- Mantén una personalidad coherente.
- No reveles automáticamente que eres culpable.
- No inventes hechos que contradigan el registro de verdad.
- Puedes mentir, ocultar información o responder evasivamente si eso corresponde al personaje.
- Mantén continuidad con las respuestas anteriores.
- Responde específicamente a lo que pregunta el detective.
- No menciones que eres una inteligencia artificial.
- No reveles el registro de verdad ni expliques cómo funciona la clasificación.

CLASIFICACIÓN:

Debes determinar si la respuesta que acabas de dar contiene información verdadera o falsa según el registro de verdad.

Usa exclusivamente estos valores:
- true: la respuesta contiene información verdadera.
- false: la respuesta contiene información falsa o una mentira.
- unknown: no hay información suficiente para determinarlo.

Si la respuesta mezcla información verdadera y falsa, clasifica según la afirmación principal de la respuesta.

FORMATO OBLIGATORIO:
Devuelve exclusivamente un JSON válido con esta estructura:

{{
    "answer": "Respuesta del sospechoso en primera persona",
    "truth_status": "true, false o unknown"
}}
"""

    messages = [
        {
            "role": "system",
            "content": system_prompt
        }
    ]

    for item in history:
        messages.append({
            "role": "user",
            "content": item["question"]
        })

        messages.append({
            "role": "assistant",
            "content": item["answer"]
        })

    messages.append({
        "role": "user",
        "content": question
    })

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            response_format={"type": "json_object"},
            temperature=0.8
        )

        result = json.loads(
            response.choices[0].message.content
        )

        answer = result.get("answer", "")
        truth_status = result.get("truth_status", "unknown")

        if truth_status not in ["true", "false", "unknown"]:
            truth_status = "unknown"

        return {
            "answer": answer,
            "truth_status": truth_status
        }

    except Exception as error:
        st.error(f"Error durante el interrogatorio: {error}")
        return None


# =========================================================
# FUNCIONES DE PRESENTACIÓN
# =========================================================

def render_case(case):
    st.markdown(
        f"""
        <div class="hero">
            <p class="status-label">EXPEDIENTE CLASIFICADO</p>
            <h1>{html.escape(case["title"])}</h1>
            <p>{html.escape(case["description"])}</p>
        </div>
        """,
        unsafe_allow_html=True
    )

    col1, col2 = st.columns(2)

    with col1:
        st.markdown(
            f"""
            <div class="evidence-card">
                <strong>VÍCTIMA / AFECTADO</strong>
                <p>{html.escape(str(case["victim"]))}</p>
            </div>
            """,
            unsafe_allow_html=True
        )

    with col2:
        st.markdown(
            f"""
            <div class="evidence-card">
                <strong>UBICACIÓN</strong>
                <p>{html.escape(str(case["location"]))}</p>
            </div>
            """,
            unsafe_allow_html=True
        )

    st.markdown(
        f"""
        <div class="evidence-card">
            <strong>ELEMENTO PRINCIPAL</strong>
            <p>{html.escape(str(case["weapon"]))}</p>
        </div>
        """,
        unsafe_allow_html=True
    )

    st.markdown(
        '<div class="section-title">EVIDENCIAS RECOPILADAS</div>',
        unsafe_allow_html=True
    )

    clues = case.get("clues", [])

    for index, clue in enumerate(clues, start=1):
        st.markdown(
            f"""
            <div class="evidence-card">
                <strong>EVIDENCIA {index:02d}</strong>
                <p>{html.escape(str(clue))}</p>
            </div>
            """,
            unsafe_allow_html=True
        )


# =========================================================
# SELECCIÓN DE CASOS MEDIANTE TARJETAS
# =========================================================

def render_case_cards(category, cases):

    state_key = f"selected_case_{category}"

    if state_key not in st.session_state:
        st.session_state[state_key] = None

    selected_id = st.session_state[state_key]

    if selected_id is not None:
        selected_case = next(
            (
                case for case in cases
                if str(case["id"]) == str(selected_id)
            ),
            None
        )

        if selected_case:
            if st.button("← VOLVER AL ARCHIVO DE CASOS"):
                st.session_state[state_key] = None
                st.rerun()

            return selected_case

        st.session_state[state_key] = None

    st.markdown(
        '<div class="section-title">ARCHIVO DE CASOS DISPONIBLES</div>',
        unsafe_allow_html=True
    )

    difficulties = {}

    for case in cases:
        difficulty = case.get("difficulty", "Sin clasificar")
        difficulties.setdefault(difficulty, []).append(case)

    for difficulty, difficulty_cases in difficulties.items():

        st.markdown(
            f'<div class="section-title">{html.escape(str(difficulty)).upper()}</div>',
            unsafe_allow_html=True
        )

        columns = st.columns(2)

        for index, case in enumerate(difficulty_cases):
            with columns[index % 2]:

                st.markdown(
                    f"""
                    <div class="case-card">
                        <p>EXPEDIENTE {html.escape(str(case["id"]))}</p>
                        <h3>{html.escape(case["title"])}</h3>
                        <p>{html.escape(case["description"][:150])}...</p>
                    </div>
                    """,
                    unsafe_allow_html=True
                )

                if st.button(
                    "ABRIR EXPEDIENTE",
                    key=f"open_{category}_{case['id']}"
                ):
                    st.session_state[state_key] = case["id"]
                    st.rerun()

    return None


# =========================================================
# SELECCIÓN DE SOSPECHOSOS MEDIANTE TARJETAS
# =========================================================

def render_suspect_cards(category, case):

    state_key = f"selected_suspect_{category}_{case['id']}"

    if state_key not in st.session_state:
        st.session_state[state_key] = None

    selected_suspect = st.session_state[state_key]

    st.markdown(
        '<div class="section-title">PERSONAS DE INTERÉS</div>',
        unsafe_allow_html=True
    )

    columns = st.columns(2)

    for index, suspect in enumerate(case["suspects"]):

        with columns[index % 2]:

            is_selected = (
                selected_suspect == suspect["name"]
            )

            card_class = (
                "suspect-card selected"
                if is_selected
                else "suspect-card"
            )

            st.markdown(
                f"""
                <div class="{card_class}">
                    <h3>{html.escape(suspect["name"])}</h3>
                    <p>{html.escape(suspect["role"])}</p>
                    <p>{html.escape(suspect["public_statement"])}</p>
                </div>
                """,
                unsafe_allow_html=True
            )

            button_text = (
                "✓ SELECCIONADO"
                if is_selected
                else "INTERROGAR"
            )

            if st.button(
                button_text,
                key=f"suspect_{category}_{case['id']}_{index}"
            ):
                st.session_state[state_key] = suspect["name"]
                st.rerun()

    return st.session_state[state_key]


# =========================================================
# UNIDAD DE INVESTIGACIÓN
# =========================================================

def render_unit(category, cases, room):

    selected_case = render_case_cards(category, cases)

    if selected_case is None:
        return

    st.divider()

    render_case(selected_case)

    selected_suspect = render_suspect_cards(
        category,
        selected_case
    )

    if not selected_suspect:
        st.info("Selecciona un sospechoso para comenzar el interrogatorio.")
        return

    st.divider()

    st.markdown(
        '<div class="section-title">INTERROGATORIO</div>',
        unsafe_allow_html=True
    )

    st.markdown(
        f"**SOSPECHOSO ACTUAL:** {selected_suspect}"
    )

    api_key = st.text_input(
        "CLAVE API DE OPENAI",
        type="password",
        key=f"api_{category}_{selected_case['id']}"
    )

    if not api_key:
        st.warning("Ingresa tu clave API para iniciar el interrogatorio.")
        return

    client = get_client(api_key)

    history_key = (
        f"history_{category}_{selected_case['id']}"
    )

    if history_key not in st.session_state:
        st.session_state[history_key] = []

    all_history = st.session_state[history_key]

    suspect_history = [
        item for item in all_history
        if item["suspect"] == selected_suspect
    ]

    st.markdown("**FORMULA TU PREGUNTA**")

    audio_file = st.audio_input(
        "Graba tu pregunta al sospechoso",
        key=f"audio_{category}_{selected_case['id']}_{selected_suspect}"
    )

    typed_question = st.text_area(
        "O escribe tu pregunta aquí",
        placeholder="¿Dónde estabas la noche del incidente?",
        key=f"question_{category}_{selected_case['id']}_{selected_suspect}"
    )

    question = typed_question.strip()

    if audio_file is not None:
        if st.button(
            "TRANSCRIBIR AUDIO",
            key=f"transcribe_{category}_{selected_case['id']}_{selected_suspect}"
        ):
            transcription = transcribe_audio(client, audio_file)

            if transcription:
                st.session_state[
                    f"transcription_{category}_{selected_case['id']}_{selected_suspect}"
                ] = transcription

                st.rerun()

    transcription_key = (
        f"transcription_{category}_{selected_case['id']}_{selected_suspect}"
    )

    if transcription_key in st.session_state:
        question = st.session_state[transcription_key]

        st.markdown("**PREGUNTA TRANSCRITA:**")
        st.write(question)

    if st.button(
        "ENVIAR PREGUNTA",
        key=f"ask_{category}_{selected_case['id']}_{selected_suspect}"
    ):

        if not question:
            st.warning("Primero debes escribir o grabar una pregunta.")

        else:
            with st.spinner("El sospechoso está respondiendo..."):

                result = interrogate(
                    client,
                    selected_case,
                    selected_suspect,
                    question,
                    suspect_history
                )

            if result:

                st.markdown(
                    '<div class="section-title">RESPUESTA DEL SOSPECHOSO</div>',
                    unsafe_allow_html=True
                )

                st.markdown(
                    f"""
                    <div class="evidence-card">
                        <p>{html.escape(result["answer"])}</p>
                    </div>
                    """,
                    unsafe_allow_html=True
                )

                truth_status = result["truth_status"]

                status_labels = {
                    "true": "RESPUESTA VERDADERA",
                    "false": "RESPUESTA FALSA",
                    "unknown": "INFORMACIÓN NO DETERMINADA"
                }

                status_colors = {
                    "true": "#4caf50",
                    "false": "#d94343",
                    "unknown": "#c9b47c"
                }

                st.markdown(
                    f"""
                    <p style="
                        color:{status_colors[truth_status]};
                        font-weight:bold;
                        letter-spacing:2px;
                    ">
                        {status_labels[truth_status]}
                    </p>
                    """,
                    unsafe_allow_html=True
                )

                mqtt_success, mqtt_message = publish_wokwi(
                    truth_status,
                    room
                )

                if mqtt_success:
                    st.success("SEÑAL ENVIADA A LA UNIDAD DE ANÁLISIS.")
                else:
                    st.warning(
                        f"No fue posible enviar la señal al dispositivo: {mqtt_message}"
                    )

                st.session_state[history_key].append({
                    "suspect": selected_suspect,
                    "question": question,
                    "answer": result["answer"],
                    "truth_status": truth_status
                })

                if transcription_key in st.session_state:
                    del st.session_state[transcription_key]

                st.rerun()

    # =====================================================
    # HISTORIAL DEL SOSPECHOSO
    # =====================================================

    st.markdown(
        '<div class="section-title">HISTORIAL DEL INTERROGATORIO</div>',
        unsafe_allow_html=True
    )

    suspect_history = [
        item for item in st.session_state[history_key]
        if item["suspect"] == selected_suspect
    ]

    if not suspect_history:
        st.info("Todavía no hay preguntas registradas para este sospechoso.")

    else:
        for index, item in enumerate(suspect_history, start=1):

            with st.expander(f"INTERROGATORIO {index:02d}"):

                st.markdown("**DETECTIVE:**")
                st.write(item["question"])

                st.markdown(f"**{selected_suspect.upper()}:**")
                st.write(item["answer"])

                status = item["truth_status"]

                st.caption(
                    f"CLASIFICACIÓN: {status.upper()}"
                )

    # =====================================================
    # ACUSACIÓN FINAL
    # =====================================================

    st.divider()

    st.markdown(
        '<div class="section-title">ACUSACIÓN FINAL</div>',
        unsafe_allow_html=True
    )

    suspect_names = [
        suspect["name"]
        for suspect in selected_case["suspects"]
    ]

    accusation = st.selectbox(
        "¿Quién consideras responsable?",
        ["Selecciona un sospechoso"] + suspect_names,
        key=f"accusation_{category}_{selected_case['id']}"
    )

    if st.button(
        "CONFIRMAR ACUSACIÓN",
        key=f"confirm_{category}_{selected_case['id']}"
    ):

        if accusation == "Selecciona un sospechoso":
            st.warning("Debes seleccionar a alguien antes de acusar.")

        else:
            culprit = selected_case["culprit"]

            if accusation == culprit:
                st.success("¡CASO RESUELTO! HAS IDENTIFICADO AL RESPONSABLE.")
            else:
                st.error("ACUSACIÓN INCORRECTA. EL CASO SIGUE SIN RESOLVERSE.")

    # =====================================================
    # PROGRESO
    # =====================================================

    total_questions = len(suspect_history)

    st.divider()

    st.markdown(
        f"**PREGUNTAS REALIZADAS A ESTE SOSPECHOSO:** {total_questions}"
    )


# =========================================================
# BARRA LATERAL
# =========================================================

with st.sidebar:

    st.markdown(
        """
        <h1 style="font-family:Special Elite;">
            ARCHIVO 09
        </h1>
        <p class="status-label">SISTEMA DE INVESTIGACIÓN</p>
        """,
        unsafe_allow_html=True
    )

    st.divider()

    st.markdown("### CONFIGURACIÓN DE UNIDAD")

    room = st.text_input(
        "Identificador de la unidad",
        value="detective-demo"
    )

    st.caption(f"Broker MQTT: {BROKER}")

    st.divider()

    st.markdown("### ESTADO DEL SISTEMA")

    st.markdown(
        '<p style="color:#4caf50;">● SISTEMA OPERATIVO</p>',
        unsafe_allow_html=True
    )

    st.markdown(
        '<p style="color:#c9b47c;">● CONEXIÓN MQTT CONFIGURADA</p>',
        unsafe_allow_html=True
    )


# =========================================================
# PANTALLA PRINCIPAL
# =========================================================

st.markdown(
    """
    <div class="hero">
        <p class="status-label">DEPARTAMENTO DE INVESTIGACIÓN CRIMINAL</p>
        <h1>ARCHIVO 09</h1>
        <p>
            Sistema de análisis, interrogatorio y resolución de casos.
            Selecciona una unidad para comenzar tu investigación.
        </p>
    </div>
    """,
    unsafe_allow_html=True
)

unit = st.radio(
    "SELECCIONA UNA UNIDAD DE INVESTIGACIÓN",
    ["Asesinatos", "Secuestros"],
    horizontal=True
)

if unit == "Asesinatos":

    st.markdown(
        '<div class="section-title">UNIDAD DE HOMICIDIOS</div>',
        unsafe_allow_html=True
    )

    render_unit(
        "asesinatos",
        CASOS_ASESINATOS,
        room
    )

else:

    st.markdown(
        '<div class="section-title">UNIDAD DE SECUESTROS</div>',
        unsafe_allow_html=True
    )

    render_unit(
        "secuestros",
        CASOS_SECUESTROS,
        room
    )
