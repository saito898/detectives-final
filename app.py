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
                    topic = publish_wokwi(status, room)
                    st.caption(f"Señal MQTT enviada al tema: {topic}")
                except Exception as exc:
                    st.warning(f"No se pudo enviar la señal a Wokwi: {exc}. Verifica internet y que el ESP32 esté activo con el mismo ID de sala.")
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
    st.code(f"archivo09/{st.session_state['mqtt_room']}/truth", language="text")
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
