from flask import Flask, request
import requests
import json
import os

app = Flask(__name__)

# ===============================================================
#  CONFIGURACIÓN Y TOKENS
# ===============================================================
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN")
WHATSAPP_TOKEN = os.environ.get("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.environ.get("PHONE_NUMBER_ID")
NUMERO_ADMIN = os.environ.get("NUMERO_ADMIN")

MEMORIA = {}

# ===============================================================
#  CARGAMOS EL MENÚ (SOLUCIÓN ROBUSTA)
# ===============================================================
# 1. Obtenemos la ruta donde vive app.py
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# 2. Construimos la ruta completa al json
JSON_PATH = os.path.join(BASE_DIR, 'datg.json')

try:
    with open(JSON_PATH, 'r', encoding='utf-8') as f:
        DATOS_NEGOCIO = json.load(f)
    print(f"✅ Datos cargados correctamente desde: {JSON_PATH}", flush=True)
except FileNotFoundError:
    print(f"❌ ERROR: No encontré el archivo en: {JSON_PATH}", flush=True)
    # Datos de respaldo mínimos para que no se caiga el server
    DATOS_NEGOCIO = {
        "mensaje_bienvenida": "Hola (Error de carga)",
        "mensaje_error": "Error interno",
        "respuesta_ubicacion": "Ubicación no disponible",
        "respuesta_precios": {"imagen": "", "caption": "Precios no disponibles"}
    }
except json.JSONDecodeError:
    print(f"❌ ERROR: El archivo datg.json tiene mal formato.", flush=True)
    DATOS_NEGOCIO = {} # Evita error de variable no definida

# ===============================================================
#  FUNCIONES DE ENVÍO
# ===============================================================
def enviar_mensaje_texto(telefono, texto):
    url = f"https://graph.facebook.com/v21.0/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    data = {"messaging_product": "whatsapp", "to": telefono, "type": "text", "text": {"body": texto}}
    try:
        response = requests.post(url, headers=headers, json=data)
        print(f"📤 TEXTO a {telefono} | Code: {response.status_code}", flush=True)
    except Exception as e:
        print(f"Error envío texto: {e}", flush=True)

def enviar_mensaje_botones(telefono, texto_cuerpo, botones):
    url = f"https://graph.facebook.com/v21.0/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    lista_botones = []
    for i, boton_titulo in enumerate(botones):
        lista_botones.append({"type": "reply", "reply": {"id": f"btn_{i}", "title": boton_titulo}})
    data = {
        "messaging_product": "whatsapp", 
        "to": telefono, 
        "type": "interactive", 
        "interactive": {
            "type": "button", 
            "body": {"text": texto_cuerpo}, 
            "action": {"buttons": lista_botones}
        }
    }
    try:
        response = requests.post(url, headers=headers, json=data)
        print(f"📤 BOTONES a {telefono} | Code: {response.status_code}", flush=True)
    except Exception as e:
        print(f"Error envío botones: {e}", flush=True)

def enviar_mensaje_imagen(telefono, link_imagen, caption):
    url = f"https://graph.facebook.com/v21.0/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    data = {
        "messaging_product": "whatsapp", 
        "to": telefono, 
        "type": "image", 
        "image": {"link": link_imagen, "caption": caption}
    }
    try:
        requests.post(url, headers=headers, json=data)
        print(f"📤 IMAGEN a {telefono} enviada", flush=True)
    except Exception as e:
        print(f"Error envío imagen: {e}", flush=True)

# ===============================================================
#  WEBHOOK Y RUTAS
# ===============================================================
@app.route('/webhook', methods=['GET'])
def verificar_token():
    mode = request.args.get('hub.mode')
    token = request.args.get('hub.verify_token')
    if mode == 'subscribe' and token == VERIFY_TOKEN:
        return request.args.get('hub.challenge'), 200
    return "Error", 403

@app.route('/webhook', methods=['POST'])
def recibir_mensajes():
    body = request.get_json()
    try:
        if body.get("object"):
            entry = body["entry"][0]
            changes = entry["changes"][0]
            value = changes["value"]
            
            if "messages" in value:
                message = value["messages"][0]
                numero = message["from"]
                
                # PARCHE MÉXICO
                if numero.startswith("521"):
                    numero = numero.replace("521", "52", 1)

                # --- DETECCIÓN DE TIPO ---
                tipo_mensaje = message["type"]
                texto_usuario = ""
                
                if tipo_mensaje == "text":
                    texto_usuario = message["text"]["body"]
                elif tipo_mensaje == "interactive":
                    # AQUÍ CAPTURAMOS LO QUE DICE EL BOTÓN
                    texto_usuario = message["interactive"]["button_reply"]["title"]

                texto_usuario_lower = texto_usuario.lower()
                print(f"<-- RECIBÍ: {texto_usuario} de {numero}", flush=True)

                # --- MÁQUINA DE ESTADOS ---
                if numero not in MEMORIA:
                    MEMORIA[numero] = {'estado': 'INICIO', 'nombre_guardado': ''}

                estado_actual = MEMORIA[numero]['estado']
                
                # --- FLUJO: AGENDAR ---
                if estado_actual == 'ESPERANDO_NOMBRE':
                    MEMORIA[numero]['nombre_guardado'] = texto_usuario.title()
                    MEMORIA[numero]['estado'] = 'ESPERANDO_SERVICIO' 
                    enviar_mensaje_botones(numero, f"Gusto en saludarte, {MEMORIA[numero]['nombre_guardado']}. ¿Qué servicio te interesa?", ["Consultoría", "Desarrollo Web", "Soporte"])
                
                elif estado_actual == 'ESPERANDO_SERVICIO':
                    nombre_cliente = MEMORIA[numero]['nombre_guardado']
                    servicio_elegido = texto_usuario
                    
                    enviar_mensaje_texto(numero, f"¡Listo {nombre_cliente}! Agendamos tu interés en: {servicio_elegido}.")
                    
                    if NUMERO_ADMIN:
                        mensaje_admin = f"🔔 *NUEVA VENTA*\nCliente: {nombre_cliente}\nTel: {numero}\nServicio: {servicio_elegido}"
                        enviar_mensaje_texto(NUMERO_ADMIN, mensaje_admin)
                    
                    MEMORIA[numero]['estado'] = 'INICIO'

                # --- FLUJO GENERAL ---
                else:
                    if "agendar" in texto_usuario_lower:
                        MEMORIA[numero]['estado'] = 'ESPERANDO_NOMBRE'
                        enviar_mensaje_texto(numero, "📝 Para agendar, primero necesito tu nombre.")
                    
                    # Manejo de botones de menú y palabras clave
                    elif "precios" in texto_usuario_lower:
                        info = DATOS_NEGOCIO.get("respuesta_precios", {})
                        if info.get("imagen"):
                            enviar_mensaje_imagen(numero, info["imagen"], info["caption"])
                        else:
                            enviar_mensaje_texto(numero, info.get("caption", "Precios no disponibles."))
                        
                    elif "ubicacion" in texto_usuario_lower or "ubicación" in texto_usuario_lower:
                        enviar_mensaje_texto(numero, DATOS_NEGOCIO.get("respuesta_ubicacion", "Ubicación pendiente."))

                    # Si no coincide con nada, mandamos menú
                    else:
                        bienvenida = DATOS_NEGOCIO.get("mensaje_bienvenida", "Hola")
                        # OJO: Los botones deben coincidir con lo que esperas en el 'elif' de arriba
                        enviar_mensaje_botones(numero, bienvenida, ["💰 Precios", "📍 Ubicación", "📅 Agendar Cita"])

            return "EVENT_RECEIVED", 200
    except Exception as e:
        print(f"Error general: {e}", flush=True)
        return "EVENT_RECEIVED", 200

@app.route("/")
def home():
    return "¡Hola! El bot de Verified Tech Solutions está vivo y funcionando 🤖", 200

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 3000))
    app.run(host='0.0.0.0', port=port, debug=True)