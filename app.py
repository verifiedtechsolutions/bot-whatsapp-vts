from flask import Flask, request
import requests
import os
from supabase import create_client, Client
from openai import OpenAI  # <--- NUEVO INVITADO

app = Flask(__name__)

# ===============================================================
#  1. CONFIGURACIÓN
# ===============================================================
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN")
WHATSAPP_TOKEN = os.environ.get("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.environ.get("PHONE_NUMBER_ID")
NUMERO_ADMIN = os.environ.get("NUMERO_ADMIN")

# Supabase
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# OpenAI
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
client_ai = OpenAI(api_key=OPENAI_API_KEY)

# ===============================================================
#  2. EL CEREBRO DE LA EMPRESA HIPOTÉTICA (System Prompt) 🧠
# ===============================================================
# AQUÍ es donde "entrenamos" al bot con los datos falsos del negocio
SYSTEM_PROMPT = """
Eres el asistente virtual de 'VTS Demo', una empresa tecnológica ficticia.
Tu tono es: Profesional, breve y amable.

DATOS DEL NEGOCIO:
- Servicios: 
  1. Consultoría Digital ($50 USD/hora).
  2. Desarrollo Web (Desde $300 USD).
  3. Soporte Técnico ($20 USD/hora).
- Ubicación: Av. Innovación 123, Mundo Digital.
- Horario: Lunes a Viernes de 9 AM a 6 PM.

REGLAS:
1. Si te preguntan precios, dalos exactos según la lista.
2. Si quieren agendar, diles que usen el botón 'Agendar Cita' del menú.
3. Respuestas cortas (máximo 50 palabras).
4. Si te preguntan algo fuera del tema (ej: cocina, deportes), di cortésmente que solo hablas de tecnología.
"""

# ===============================================================
#  3. FUNCIONES DE IA
# ===============================================================
def consultar_chatgpt(mensaje_usuario):
    """Envía el mensaje a OpenAI y recibe respuesta."""
    try:
        completion = client_ai.chat.completions.create(
            model="gpt-4o-mini",  # Modelo rápido y económico
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": mensaje_usuario}
            ]
        )
        return completion.choices[0].message.content
    except Exception as e:
        print(f"Error OpenAI: {e}")
        return "Lo siento, estoy teniendo problemas para pensar ahora mismo."

# ===============================================================
#  4. FUNCIONES DE BASE DE DATOS
# ===============================================================
def obtener_usuario(telefono):
    try:
        response = supabase.table("clientes").select("*").eq("telefono", telefono).execute()
        if len(response.data) > 0:
            return response.data[0]
        else:
            nuevo = {"telefono": telefono, "estado_flujo": "INICIO"}
            supabase.table("clientes").insert(nuevo).execute()
            return nuevo
    except Exception as e:
        print(f"Error DB: {e}")
        return {"telefono": telefono, "estado_flujo": "INICIO", "nombre": ""}

def actualizar_estado(telefono, nuevo_estado, nombre=None):
    try:
        data = {"estado_flujo": nuevo_estado}
        if nombre: data["nombre"] = nombre
        supabase.table("clientes").update(data).eq("telefono", telefono).execute()
    except:
        pass

# ===============================================================
#  5. FUNCIONES DE ENVÍO
# ===============================================================
def enviar_mensaje(telefono, texto):
    url = f"https://graph.facebook.com/v21.0/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    data = {"messaging_product": "whatsapp", "to": telefono, "type": "text", "text": {"body": texto}}
    requests.post(url, headers=headers, json=data)

def enviar_botones(telefono, texto, botones):
    url = f"https://graph.facebook.com/v21.0/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    lista = [{"type": "reply", "reply": {"id": f"btn_{i}", "title": b}} for i, b in enumerate(botones)]
    data = {
        "messaging_product": "whatsapp", "to": telefono, "type": "interactive",
        "interactive": {"type": "button", "body": {"text": texto}, "action": {"buttons": lista}}
    }
    requests.post(url, headers=headers, json=data)

# ===============================================================
#  6. WEBHOOK
# ===============================================================
@app.route('/webhook', methods=['GET'])
def verificar():
    if request.args.get('hub.mode') == 'subscribe' and request.args.get('hub.verify_token') == VERIFY_TOKEN:
        return request.args.get('hub.challenge'), 200
    return "Error", 403

@app.route('/webhook', methods=['POST'])
def recibir():
    body = request.get_json()
    try:
        if body.get("object"):
            entry = body["entry"][0]
            changes = entry["changes"][0]
            value = changes["value"]
            
            if "messages" in value:
                message = value["messages"][0]
                numero = message["from"]
                if numero.startswith("521"): numero = numero.replace("521", "52", 1)

                usuario = obtener_usuario(numero)
                estado = usuario.get("estado_flujo", "INICIO")

                # Detectar tipo de mensaje
                tipo = message["type"]
                texto = ""
                es_boton = False
                
                if tipo == "text":
                    texto = message["text"]["body"]
                elif tipo == "interactive":
                    texto = message["interactive"]["button_reply"]["title"]
                    es_boton = True

                print(f"📩 Recibido: {texto} | Estado: {estado}")

                # --- LÓGICA HÍBRIDA (BOTONES vs IA) ---

                # 1. Si estamos capturando datos específicos (Nombre), ignoramos a la IA
                if estado == 'ESPERANDO_NOMBRE':
                    actualizar_estado(numero, 'INICIO', nombre=texto) # Guardamos nombre
                    enviar_botones(numero, f"Gracias {texto}. ¿En qué puedo ayudarte hoy?", ["Consultar Precios", "Hablar con IA", "Agendar Cita"])
                    return "OK", 200

                # 2. Si es un BOTÓN, usamos lógica rígida (rápida y segura)
                if es_boton:
                    if "Precios" in texto:
                        enviar_mensaje(numero, "💰 *Precios VTS Demo:*\n- Consultoría: $50\n- Web: $300\n- Soporte: $20/h")
                    elif "Agendar" in texto:
                        actualizar_estado(numero, 'ESPERANDO_NOMBRE')
                        enviar_mensaje(numero, "Para agendar, necesito tu nombre completo:")
                    elif "IA" in texto:
                        enviar_mensaje(numero, "Dime, ¿qué duda tienes sobre nuestros servicios?")
                    else:
                        enviar_mensaje(numero, "Opción seleccionada.")
                
                # 3. Si es TEXTO LIBRE, usamos a la IA (OpenAI)
                else:
                    # Aquí ocurre la magia: La IA lee el System Prompt y responde
                    respuesta_ia = consultar_chatgpt(texto)
                    enviar_mensaje(numero, respuesta_ia)
                    
                    # Opcional: Volver a mostrar menú para no dejarlo colgado
                    # enviar_botones(numero, "¿Algo más?", ["Ver Precios", "Agendar"])

            return "EVENT_RECEIVED", 200
    except Exception as e:
        print(f"Error: {e}")
        return "EVENT_RECEIVED", 200

@app.route("/")
def home(): return "Bot VTS con IA Activo 🧠", 200

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 3000))
    app.run(host='0.0.0.0', port=port, debug=True)