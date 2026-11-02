
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


# ============================================================
# CONFIGURACIÓN GENERAL
# ============================================================

st.set_page_config(
    page_title="ARCHIVO 09 | Unidad de Casos Especiales",
    page_icon="🕵️",
    layout="wide",
    initial_sidebar_state="expanded"
)


# ============================================================
# CONFIGURACIÓN MQTT
# ============================================================

BROKER = "broker.hivemq.com"
PORT = 1883


# ============================================================
# ESTÉTICA
# ============================================================

st.markdown("""
<style>

@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600;700&family=Special+Elite&display=swap');

:root {
    --paper: #e9e3d4;
    --ink: #17221e;
    --red: #a72d2d;
    --green: #38734b;
    --gold: #b28a32;
}

.stApp {
    background: #171c1b;
    color: #e9e3d4;
}

[data-testid="stSidebar"] {
    background: #202725;
    border-right: 1px solid #4d5650;
}

[data-testid="stSidebar"] * {
    color: #e9e3d4 !important;
}

h1, h2, h3 {
    font-family: 'Special Elite', monospace !important;
    letter-spacing: 1px;
}

p, label, div, span {
    font-family: 'IBM Plex Mono', monospace;
}

/* ================= HERO ================= */

.hero {
    background: var(--paper);
    color: var(--ink);
    padding: 2rem 2.3rem;
    border-left: 8px solid var(--red);
    box-shadow: 7px 7px 0 #080b0a;
    margin-bottom: 1.5rem;
}

.hero h1 {
    font-size: clamp(2.5rem, 6vw, 5rem);
    margin: .35rem 0;
    color: #17221e;
}

.hero h1 span {
    color: var(--red);
}

.eyebrow,
.folder-tag {
    font-size: .76rem;
    font-weight: 700;
    letter-spacing: 2px;
    color: var(--red);
}

.subtitle {
    font-size: 1rem;
}

.stamp {
    display: inline-block;
    border: 2px solid var(--red);
    color: var(--red);
    padding: .35rem .55rem;
    transform: rotate(-1deg);
    font-size: .72rem;
    margin-top: .6rem;
}

/* ================= TARJETAS PRINCIPALES ================= */

.folder-card {
    min-height: 220px;
    background: #e9e3d4;
    color: #17221e;
    padding: 1.3rem;
    border-top: 7px solid #a72d2d;
    box-shadow: 5px 5px 0 #080b0a;
    margin-bottom: 1rem;
}

.folder-card h2 {
    color: #17221e;
}

/* ================= EXPEDIENTES ================= */

.case-card {
    background: #e9e3d4;
    color: #17221e;
    border: 1px solid #b9b19f;
    border-top: 6px solid #a72d2d;
    padding: 1.2rem;
    min-height: 245px;
    box-shadow: 4px 5px 0 #080b0a;
    margin-bottom: 12px;
    transition: transform .2s ease;
}

.case-card:hover {
    transform: translateY(-4px);
}

.case-number {
    color: #a72d2d;
    font-size: .75rem;
    font-weight: bold;
    letter-spacing: 2px;
}

.case-card h3 {
    color: #17221e;
    font-size: 1.3rem;
    margin-top: 15px;
}

.case-description {
    font-size: .85rem;
    min-height: 65px;
    color: #303a34;
}

.difficulty-tag {
    display: inline-block;
    padding: 5px 9px;
    border: 1px solid #a72d2d;
    color: #a72d2d;
    font-size: .7rem;
    font-weight: bold;
    margin-top: 8px;
}

/* ================= FICHA DE EXPEDIENTE ================= */

.case-sheet {
    background: #e9e3d4;
    color: #17221e;
    padding: 1.3rem 1.5rem;
    border-left: 6px solid #a72d2d;
    margin: .6rem 0 1rem;
}

.case-sheet h2,
.case-sheet h3 {
    color: #17221e;
}

.case-label {
    font-size: .72rem;
    letter-spacing: 1.4px;
    color: #a72d2d;
    font-weight: 700;
}

/* ================= SOSPECHOSOS ================= */

.suspect-card {
    border: 1px solid #626b63;
    border-left: 4px solid #a72d2d;
    padding: 1rem;
    margin: .35rem 0;
    background: #222927;
    min-height: 175px;
    transition: all .2s ease;
}

.suspect-card:hover {
    border-color: #b28a32;
    background: #2b3430;
}

.suspect-name {
    color: #e9e3d4;
    font-size: 1.05rem;
    font-weight: bold;
}

.suspect-role {
    color: #b28a32;
    font-size: .75rem;
    margin-top: 5px;
    margin-bottom: 15px;
}

.suspect-statement {
    color: #c5c9bd;
    font-size: .78rem;
    min-height: 55px;
}

.selected-suspect {
    border: 2px solid #b28a32;
    background: #303a34;
}

.small-muted {
    color: #b6b9ad;
    font-size: .8rem;
}

/* ================= CONTROLES ================= */

div.stButton > button,
div.stDownloadButton > button {
    border-radius: 2px;
    border: 1px solid #c4c0b3;
    font-family: 'IBM Plex Mono', monospace;
}

div.stButton > button[kind="primary"] {
    background: #a72d2d;
    border-color: #a72d2d;
}

input,
textarea {
    border-radius: 2px !important;
}

.stAlert {
    border-radius: 2px;
}

</style>
""", unsafe_allow_html=True)


# ============================================================
# OPENAI
# ============================================================

def get_client(api_key):

    if not api_key or not api_key.strip():
        raise ValueError(
            "Escribe tu clave API de OpenAI para iniciar el interrogatorio."
        )

    return OpenAI(api_key=api_key.strip())


# ============================================================
# CONEXIÓN MQTT
# ============================================================

def enviar_mqtt(topic, payload):
    """
    Publica un mensaje JSON en el broker MQTT.
    El cliente de Streamlit tiene un identificador propio.
    """

    cliente = None

    try:

        client_id = (
            "Salitostreamlit_"
            + str(int(time.time() * 1000))
        )

        # Compatible con diferentes versiones de Paho MQTT

        try:

            cliente = mqtt.Client(
                callback_api_version=mqtt.CallbackAPIVersion.VERSION1,
                client_id=client_id
            )

        except (AttributeError, TypeError):

            cliente = mqtt.Client(
                client_id=client_id
            )

        cliente.connect(
            BROKER,
            PORT,
            keepalive=30
        )

        cliente.loop_start()

        mensaje = json.dumps(
            payload,
            ensure_ascii=False
        )

        resultado = cliente.publish(
            topic,
            mensaje,
            qos=0
        )

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
    """
    Envía exclusivamente la clasificación de veracidad
    generada por la IA.
    """

    room = re.sub(
        r"[^a-zA-Z0-9_-]",
        "",
        str(room)
    )[:48]

    if not room:
        return False, "El ID de sala MQTT está vacío."

    topic = f"archivo09/{room}/truth"

    payload = {
        "status": status,
        "room": room
    }

    return enviar_mqtt(topic, payload)


# ============================================================
# AUDIO
# ============================================================

def transcribe_audio(client, audio_file):

    if audio_file is None:
        return ""

    raw = audio_file.getvalue()

    if not raw:
        return ""

    filename = getattr(
        audio_file,
        "name",
        "pregunta.wav"
    )

    suffix = os.path.splitext(filename)[1] or ".wav"

    result = client.audio.transcriptions.create(
        model="gpt-4o-mini-transcribe",
        file=(
            f"pregunta{suffix}",
            raw,
            getattr(
                audio_file,
                "type",
                "audio/wav"
            ) or "audio/wav"
        ),
        language="es",
    )

    return result.text.strip()


# ============================================================
# INTERROGATORIO CON INTELIGENCIA ARTIFICIAL
# ============================================================

def interrogate(
    client,
    case,
    suspect_name,
    question,
    history=None
):
    """
    La IA interpreta al sospechoso seleccionado.

    Recibe el expediente, su ficha personal y el historial
    anterior para mantener la continuidad del interrogatorio.
    """

    suspect = next(
        s for s in case["suspects"]
        if s["name"] == suspect_name
    )

    facts = json.dumps(
        case["truth_ledger"],
        ensure_ascii=False
    )

    profile = json.dumps(
        suspect,
        ensure_ascii=False
    )

    system = f"""
Eres un personaje de un juego ficticio de detectives.

Tu función es INTERPRETAR al sospechoso seleccionado.
No eres un asistente externo ni un narrador.

Debes responder SIEMPRE en español, en primera persona,
con naturalidad y coherencia.

CASO:
{case['title']}

RESUMEN:
{case['description']}

VERDAD OFICIAL DEL CASO:
{facts}

FICHA DEL SOSPECHOSO:
{profile}

REGLAS DE INTERPRETACIÓN:

1. Responde como si fueras realmente el sospechoso.
2. Mantén tu personalidad, historia, conocimientos y secretos.
3. No reveles automáticamente quién es el culpable.
4. No inventes hechos que contradigan el expediente.
5. Reacciona naturalmente cuando el detective presente pruebas.
6. Si el detective descubre una contradicción, responde de acuerdo
   con la personalidad y los secretos del personaje.
7. No repitas siempre la misma respuesta.
8. No reveles información que el personaje no podría conocer.
9. Recuerda que una persona puede mentir, ocultar información,
   confundirse o decir la verdad.
10. Responde de forma natural, generalmente entre 2 y 5 frases.

CLASIFICACIÓN DE VERACIDAD:

Debes analizar la afirmación principal del sospechoso.

- true: cuando su declaración coincide con los hechos conocidos.
- false: cuando contradice los hechos o encubre deliberadamente
  un hecho que conoce.
- unknown: cuando no existe información suficiente para determinarlo.

La etiqueta NO representa culpabilidad.
Una persona inocente también puede mentir sobre algo.
Una persona culpable también puede decir la verdad.

Devuelve exclusivamente JSON válido con estas dos propiedades:

answer: respuesta del sospechoso.
truth_status: true, false o unknown.
"""

    messages = [
        {
            "role": "system",
            "content": system
        }
    ]

    # Recuperar las declaraciones anteriores del mismo sospechoso

    if history:

        for item in history:

            messages.append({
                "role": "user",
                "content": item["question"]
            })

            messages.append({
                "role": "assistant",
                "content": json.dumps({
                    "answer": item["answer"],
                    "truth_status": item["status"]
                }, ensure_ascii=False)
            })

    messages.append({
        "role": "user",
        "content": question
    })

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0.35,
        response_format={
            "type": "json_object"
        },
        messages=messages
    )

    data = json.loads(
        response.choices[0].message.content
    )

    if data.get("truth_status") not in (
        "true",
        "false",
        "unknown"
    ):

        data["truth_status"] = "unknown"

    data["answer"] = str(
        data.get(
            "answer",
            "No tengo nada más que declarar."
        )
    )

    return data


# ============================================================
# FICHA DEL EXPEDIENTE
# ============================================================

def render_case(case, category):

    st.markdown(f"""
    <div class="case-sheet">

        <div class="case-label">
            EXPEDIENTE {html.escape(str(case['id']))}
            · {html.escape(category.upper())}
            · {html.escape(case['difficulty'].upper())}
        </div>

        <h2>{html.escape(case['title'])}</h2>

        <p>{html.escape(case['description'])}</p>

        <p>
            <b>Víctima / persona afectada:</b>
            {html.escape(case['victim'])}
        </p>

        <p>
            <b>Lugar relacionado:</b>
            {html.escape(case['location'])}
        </p>

        <p>
            <b>Arma / elemento clave:</b>
            {html.escape(case['weapon'])}
        </p>

    </div>
    """, unsafe_allow_html=True)

    st.markdown("### EVIDENCIAS RECUPERADAS")

    cols = st.columns(2)

    for i, clue in enumerate(case["clues"]):

        with cols[i % 2]:

            st.markdown(f"""
            <div class="suspect-card">

                <div class="case-label">
                    EVIDENCIA E{i+1:02d}
                </div>

                <p>{html.escape(str(clue))}</p>

            </div>
            """, unsafe_allow_html=True)


# ============================================================
# NAVEGACIÓN ENTRE UNIDADES
# ============================================================

def set_unit(name):

    st.session_state["unit"] = name


# ============================================================
# PÁGINA DE UNIDAD
# ============================================================

def render_unit(category, cases, room):

    # ================= HERO =================

    st.markdown(f"""
    <div class="hero">

        <div class="eyebrow">
            POLICÍA · ARCHIVO 09
        </div>

        <h1>{html.escape(category.upper())}</h1>

        <p class="subtitle">
            Cada declaración puede acercarte a la verdad…
            o desviarte de ella.
        </p>

        <div class="stamp">
            DOCUMENTO CONFIDENCIAL
        </div>

    </div>
    """, unsafe_allow_html=True)


    # ========================================================
    # SELECCIÓN DE EXPEDIENTES
    # ========================================================

    case_key = f"selected_case_{category}"

    st.markdown("## ARCHIVADOR DE EXPEDIENTES")

    st.caption(
        "Selecciona el expediente que deseas investigar."
    )

    columns = st.columns(2)

    for i, c in enumerate(cases):

        with columns[i % 2]:

            st.markdown(f"""
            <div class="case-card">

                <div class="case-number">
                    EXPEDIENTE {html.escape(str(c['id']))}
                </div>

                <h3>
                    {html.escape(c['title'])}
                </h3>

                <div class="case-description">
                    {html.escape(c['description'])}
                </div>

                <div class="difficulty-tag">
                    {html.escape(c['difficulty'].upper())}
                </div>

            </div>
            """, unsafe_allow_html=True)

            if st.button(
                "ABRIR EXPEDIENTE →",
                key=f"open_{category}_{c['id']}",
                use_container_width=True
            ):

                st.session_state[case_key] = c["id"]

                st.rerun()


    # ========================================================
    # EXPEDIENTE SELECCIONADO
    # ========================================================

    selected_id = st.session_state.get(case_key)

    if selected_id is None:

        st.info(
            "Selecciona una tarjeta para abrir un expediente."
        )

        return

    case = next(
        (
            c for c in cases
            if c["id"] == selected_id
        ),
        None
    )

    if case is None:

        st.session_state.pop(case_key, None)

        st.rerun()

        return


    st.markdown("---")

    if st.button(
        "← VOLVER AL ARCHIVADOR",
        key=f"back_{category}"
    ):

        st.session_state.pop(case_key, None)

        st.rerun()


    # ========================================================
    # INFORMACIÓN DEL CASO
    # ========================================================

    render_case(case, category)


    # ========================================================
    # PERSONAS DE INTERÉS
    # ========================================================

    st.markdown("---")

    st.markdown("## PERSONAS DE INTERÉS")

    st.caption(
        "Selecciona a la persona que deseas interrogar."
    )

    suspect_key = (
        f"selected_suspect_{category}_{case['id']}"
    )

    suspect_names = [
        s["name"] for s in case["suspects"]
    ]

    if st.session_state.get(suspect_key) not in suspect_names:

        st.session_state[suspect_key] = suspect_names[0]

    selected = st.session_state[suspect_key]

    cols = st.columns(2)

    for i, suspect in enumerate(case["suspects"]):

        with cols[i % 2]:

            is_selected = (
                suspect["name"] == selected
            )

            selected_class = (
                "selected-suspect"
                if is_selected
                else ""
            )

            st.markdown(f"""
            <div class="suspect-card {selected_class}">

                <div class="case-label">
                    PERSONA DE INTERÉS {i+1:02d}
                </div>

                <div class="suspect-name">
                    {html.escape(suspect['name'])}
                </div>

                <div class="suspect-role">
                    {html.escape(suspect['role'])}
                </div>

                <div class="suspect-statement">
                    "{html.escape(suspect['public_statement'])}"
                </div>

            </div>
            """, unsafe_allow_html=True)

            if st.button(
                "✓ SELECCIONADO"
                if is_selected
                else "INTERROGAR",

                key=f"choose_{category}_{case['id']}_{i}",

                type="primary"
                if is_selected
                else "secondary",

                use_container_width=True
            ):

                st.session_state[suspect_key] = suspect["name"]

                st.rerun()


    selected = st.session_state[suspect_key]


    # ========================================================
    # SALA DE INTERROGATORIOS
    # ========================================================

    st.markdown("---")

    st.markdown("## SALA DE INTERROGATORIOS")

    st.markdown(f"""
    <div class="case-sheet">

        <div class="case-label">
            SUJETO BAJO INTERROGATORIO
        </div>

        <h2>{html.escape(selected)}</h2>

        <p>
            Formula preguntas, analiza sus respuestas
            y busca contradicciones.
        </p>

    </div>
    """, unsafe_allow_html=True)


    # ================= OPENAI =================

    api_key = st.text_input(
        "CLAVE API DE OPENAI",
        type="password",
        key=f"api_{category}_{case['id']}",
        placeholder="Pega tu clave sk-…"
    )

    st.caption(
        "La clave se introduce aquí en la sesión; "
        "no la escribas dentro del código ni la subas a GitHub."
    )


    # ================= PREGUNTAS =================

    st.write(
        "Graba tu pregunta con el micrófono "
        "o escríbela en el campo de texto."
    )

    audio = st.audio_input(
        "Grabar pregunta",
        key=f"audio_{category}_{case['id']}_{selected}"
    )

    typed = st.text_input(
        "O escribe tu pregunta",
        key=f"typed_{category}_{case['id']}_{selected}",
        placeholder="¿Dónde estabas a las nueve?"
    )


    # ========================================================
    # HISTORIAL POR SOSPECHOSO
    # ========================================================

    history_key = (
        f"history_{category}_{case['id']}"
    )

    all_history = st.session_state.get(
        history_key,
        []
    )

    suspect_history = [
        item for item in all_history
        if item["suspect"] == selected
    ]


    # ========================================================
    # INICIAR INTERROGATORIO
    # ========================================================

    if st.button(
        "INICIAR INTERROGATORIO",
        type="primary",
        key=f"ask_{category}_{case['id']}_{selected}"
    ):

        try:

            client = get_client(api_key)

            question = typed.strip()

            if audio is not None:

                with st.spinner("Transcribiendo audio..."):

                    spoken = transcribe_audio(
                        client,
                        audio
                    )

                if spoken:

                    question = spoken

                    st.info(
                        f"Pregunta reconocida: “{question}”"
                    )


            if not question:

                st.warning(
                    "Graba una pregunta o escribe una "
                    "antes de iniciar el interrogatorio."
                )

            else:

                with st.spinner(
                    f"Interrogando a {selected}..."
                ):

                    result = interrogate(
                        client,
                        case,
                        selected,
                        question,
                        suspect_history
                    )


                # ================= RESPUESTA =================

                st.markdown("#### DECLARACIÓN REGISTRADA")

                st.markdown(
                    f"> {result['answer']}"
                )


                # ================= VERACIDAD =================

                status = result["truth_status"]

                if status == "true":

                    st.success(
                        "DECLARACIÓN VERDADERA · LED VERDE"
                    )

                elif status == "false":

                    st.error(
                        "POSIBLE MENTIRA · LED ROJO"
                    )

                else:

                    st.warning(
                        "VERACIDAD NO DETERMINADA · LED BLANCO"
                    )


                # ================= MQTT =================

                enviado, respuesta_mqtt = publish_wokwi(
                    status,
                    room
                )

                if enviado:

                    st.success(
                        "SEÑAL ENVIADA A LA UNIDAD DE ANÁLISIS."
                    )

                else:

                    st.warning(
                        f"No se pudo enviar la señal a Wokwi: "
                        f"{respuesta_mqtt}"
                    )


                # ================= GUARDAR HISTORIAL =================

                st.session_state.setdefault(
                    history_key,
                    []
                ).append({

                    "suspect": selected,

                    "question": question,

                    "answer": result["answer"],

                    "status": status

                })


        except Exception as exc:

            st.error(
                f"No se pudo completar el interrogatorio: {exc}"
            )


    # ========================================================
    # REGISTRO DE INTERROGATORIOS
    # ========================================================

    all_history = st.session_state.get(
        history_key,
        []
    )

    if all_history:

        with st.expander(
            "REGISTRO DE INTERROGATORIOS"
        ):

            for item in reversed(all_history):

                icon = {
                    "true": "🟢",
                    "false": "🔴",
                    "unknown": "⚪"
                }.get(
                    item["status"],
                    "⚪"
                )

                st.markdown(
                    f"**{icon} {item['suspect']}** "
                    f"· {item['question']}"
                )

                st.write(
                    item["answer"]
                )


    # ========================================================
    # ACUSACIÓN FINAL
    # ========================================================

    st.markdown("---")

    st.markdown("## ACUSACIÓN FINAL")

    st.caption(
        "Contrasta las pistas y señala a quien consideras responsable."
    )

    accused = st.selectbox(
        "Señalar responsable",
        suspect_names,
        key=f"accuse_{category}_{case['id']}"
    )


    if st.button(
        "PRESENTAR ACUSACIÓN",
        key=f"submit_{category}_{case['id']}"
    ):

        if accused == case["culprit"]:

            st.success(
                "CASO RESUELTO. La acusación coincide "
                "con la reconstrucción oficial."
            )

            st.balloons()

            st.session_state.setdefault(
                "solved_cases",
                set()
            ).add(
                f"{category}:{case['id']}"
            )

        else:

            st.error(
                "ACUSACIÓN NO SUSTENTADA. "
                "Revisa las pistas e interroga de nuevo."
            )


    # ========================================================
    # PROGRESO
    # ========================================================

    solved = st.session_state.get(
        "solved_cases",
        set()
    )

    count = sum(
        1
        for c in cases
        if f"{category}:{c['id']}" in solved
    )

    st.progress(
        count / len(cases),
        text=(
            f"Expedientes resueltos en esta unidad: "
            f"{count}/{len(cases)}"
        )
    )


# ============================================================
# BARRA LATERAL
# ============================================================

with st.sidebar:

    st.markdown("## ARCHIVO 09")

    st.markdown(
        "**UNIDAD DE CASOS ESPECIALES**"
    )

    category_choice = st.radio(
        "SELECCIONAR UNIDAD",
        [
            "Centro de investigación",
            "Asesinatos",
            "Secuestros"
        ],
        key="unit"
    )

    st.markdown("---")

    st.markdown("## CONEXIÓN WOKWI")

    room = st.text_input(
        "ID de sala MQTT",
        value=st.session_state.get(
            "mqtt_room",
            "detective-demo"
        ),
        key="mqtt_room_input"
    )

    st.session_state["mqtt_room"] = re.sub(
        r"[^a-zA-Z0-9_-]",
        "",
        room
    )[:48] or "detective-demo"

    st.caption(
        f"Broker: {BROKER}:{PORT}"
    )

    st.caption(
        "🟢 Verdad · 🔴 Mentira · ⚪ No determinado"
    )


# ============================================================
# CENTRO DE INVESTIGACIÓN
# ============================================================

if category_choice == "Centro de investigación":

    st.markdown("""
    <div class="hero">

        <div class="eyebrow">
            POLICÍA · UNIDAD DE CASOS ESPECIALES
        </div>

        <h1>
            ARCHIVO <span>09</span>
        </h1>

        <p class="subtitle">
            Los hechos no mienten. Las personas, a veces.
        </p>

        <div class="stamp">
            ACCESO RESTRINGIDO · SOLO PERSONAL AUTORIZADO
        </div>

    </div>
    """, unsafe_allow_html=True)


    st.markdown("## CENTRO DE INVESTIGACIÓN")

    st.write(
        "Selecciona una unidad desde el menú lateral. "
        "Interroga sospechosos por voz o texto, "
        "contrasta declaraciones con las evidencias "
        "y acusa al responsable."
    )


    a, b = st.columns(2)


    with a:

        st.markdown("""
        <div class="folder-card">

            <div class="folder-tag">
                UNIDAD 01
            </div>

            <h2>Asesinatos</h2>

            <p>5 expedientes · Dificultad progresiva</p>

            <p>
                Reconstruye los hechos y descubre
                al responsable.
            </p>

        </div>
        """, unsafe_allow_html=True)

        st.button(
            "ABRIR EXPEDIENTES DE ASESINATO →",
            key="go_murder",
            on_click=set_unit,
            args=("Asesinatos",),
            use_container_width=True
        )


    with b:

        st.markdown("""
        <div class="folder-card">

            <div class="folder-tag">
                UNIDAD 02
            </div>

            <h2>Secuestros</h2>

            <p>5 expedientes · Dificultad progresiva</p>

            <p>
                Analiza mensajes, rastros y testimonios
                para localizar a la víctima.
            </p>

        </div>
        """, unsafe_allow_html=True)

        st.button(
            "ABRIR EXPEDIENTES DE SECUESTRO →",
            key="go_kidnap",
            on_click=set_unit,
            args=("Secuestros",),
            use_container_width=True
        )


    st.markdown("---")

    st.info(
        "Introduce tu clave de OpenAI dentro del expediente "
        "que abras. Wokwi se conecta por MQTT; el ID de sala "
        "de esta barra lateral debe coincidir con ROOM_ID "
        "en el código del ESP32."
    )

    st.caption(
        "ARCHIVO 09 · Prototipo académico · "
        "Casos y personajes ficticios. "
        "La clasificación de veracidad hecha por IA puede equivocarse."
    )


# ============================================================
# UNIDAD DE ASESINATOS
# ============================================================

elif category_choice == "Asesinatos":

    render_unit(
        "Asesinatos",
        CASOS_ASESINATOS,
        st.session_state["mqtt_room"]
    )


# ============================================================
# UNIDAD DE SECUESTROS
# ============================================================

elif category_choice == "Secuestros":

    render_unit(
        "Secuestros",
        CASOS_SECUESTROS,
        st.session_state["mqtt_room"]
    )
