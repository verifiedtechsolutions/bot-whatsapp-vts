from flask import Flask, request
import requests
import json
import os

app = Flask(__name__)

# ===============================================================
#  CONFIGURACIÓN Y CREDENCIALES
# ===============================================================
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN")
WHATSAPP_TOKEN = os.environ.get("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.environ.get("PHONE_NUMBER_ID")
NUMERO_ADMIN = os.environ.get("NUMERO_ADMIN")  # <--- NUEVO: Tu número personal
# ===============================================================

# 🧠 MEMORIA AVANZADA
# Ahora guardaremos más datos. Estructura:
# { '521...': { 'estado': 'ESPERANDO_NOMBRE', 'nombre_guardado': '' } }
MEMORIA = {}

# --- CARGAMOS EL MENÚ ---
try:
    with open('datg.json', 'r', encoding='utf-8') as f:
        DATOS_NEGOCIO = json.load(f)
    print("✅ Datos cargados.", flush=True)
except:
    DATOS_NEGOCIO = {"mensaje_error": "Error config.", "botones_menu": ["Error"]}

# --- FUNCIONES DE ENVÍO ---
def enviar_mensaje_texto(telefono, texto):
    url = f"https://graph.facebook.com/v21.0/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    data = {"messaging_product": "whatsapp", "to": telefono, "type": "text", "text": {"body": texto}}
    requests.post(url, headers=headers, json=data)

def enviar_mensaje_botones(telefono, texto_cuerpo, botones):
    url = f"https://graph.facebook.com/v21.0/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    lista_botones = []
    for i, boton_titulo in enumerate(botones):
        lista_botones.append({"type": "reply", "reply": {"id": f"btn_{i}", "title": boton_titulo}})
    data = {"messaging_product": "whatsapp", "to": telefono, "type": "interactive", "interactive": {"type": "button", "body": {"text": texto_cuerpo}, "action": {"buttons": lista_botones}}}
    requests.post(url, headers=headers, json=data)

def enviar_mensaje_imagen(telefono, link_imagen, caption):
    url = f"https://graph.facebook.com/v21.0/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    data = {"messaging_product": "whatsapp", "to": telefono, "type": "image", "image": {"link": link_imagen, "caption": caption}}
    requests.post(url, headers=headers, json=data)

# --- VERIFICACIÓN ---
@app.route('/webhook', methods=['GET'])
def verificar_token():
    mode = request.args.get('hub.mode')
    token = request.args.get('hub.verify_token')
    if mode == 'subscribe' and token == VERIFY_TOKEN:
        return request.args.get('hub.challenge'), 200
    return "Error", 403

# --- RECEPCIÓN DE MENSAJES ---
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

                tipo_mensaje = message["type"]
                texto_usuario = ""
                if tipo_mensaje == "text":
                    texto_usuario = message["text"]["body"] # Quitamos .lower() aquí para guardar nombres bien
                elif tipo_mensaje == "interactive":
                    texto_usuario = message["interactive"]["button_reply"]["title"]

                texto_usuario_lower = texto_usuario.lower() # Usamos este para comparar comandos
                print(f"<-- RECIBÍ: {texto_usuario} de {numero}", flush=True)

                # ==================================================
                # 🧠 MÁQUINA DE ESTADOS RECARGADA
                # ==================================================
                
                # Inicializar usuario si no existe
                if numero not in MEMORIA:
                    MEMORIA[numero] = {'estado': 'INICIO', 'nombre_guardado': ''}

                estado_actual = MEMORIA[numero]['estado']
                
                # --- FLUJO: AGENDAR CITA ---
                
                if estado_actual == 'ESPERANDO_NOMBRE':
                    # Guardamos el nombre tal cual lo escribió
                    MEMORIA[numero]['nombre_guardado'] = texto_usuario.title()
                    # Avanzamos
                    MEMORIA[numero]['estado'] = 'ESPERANDO_SERVICIO' 
                    enviar_mensaje_botones(numero, f"Gusto en saludarte, {MEMORIA[numero]['nombre_guardado']}. ¿Qué servicio te interesa?", ["Consultoría", "Desarrollo Web", "Soporte"])
                
                elif estado_actual == 'ESPERANDO_SERVICIO':
                    nombre_cliente = MEMORIA[numero]['nombre_guardado']
                    servicio_elegido = texto_usuario
                    
                    # 1. Confirmar al Cliente
                    enviar_mensaje_texto(numero, f"¡Listo {nombre_cliente}! Agendamos tu interés en: {servicio_elegido}.\nNos comunicaremos contigo a este número.")
                    
                    # 2. NOTIFICAR AL DUEÑO (A TI) 🔔
                    if NUMERO_ADMIN:
                        mensaje_admin = f"🔔 *NUEVA OPORTUNIDAD DE VENTA*\n\n👤 Cliente: {nombre_cliente}\n🛠 Interés: {servicio_elegido}\n📱 Tel: {numero}\n\n¡Escríbele pronto!"
                        enviar_mensaje_texto(NUMERO_ADMIN, mensaje_admin)
                    
                    # Reiniciamos
                    MEMORIA[numero]['estado'] = 'INICIO'

                # --- FLUJO NORMAL ---
                else:
                    if "agendar" in texto_usuario_lower or "cita" in texto_usuario_lower:
                        MEMORIA[numero]['estado'] = 'ESPERANDO_NOMBRE'
                        enviar_mensaje_texto(numero, "📝 Para agendar, primero necesito tu nombre. ¿Cómo te llamas?")
                    
                    elif "hola" in texto_usuario_lower or "menu" in texto_usuario_lower or "menú" in texto_usuario_lower:
                        enviar_mensaje_botones(numero, DATOS_NEGOCIO["mensaje_bienvenida"], ["💰 Precios", "📍 Ubicación", "📅 Agendar Cita"])
                    
                    elif "precios" in texto_usuario_lower:
                        info = DATOS_NEGOCIO["respuesta_precios"]
                        enviar_mensaje_imagen(numero, info["imagen"], info["caption"])
                        
                    elif "ubicacion" in texto_usuario_lower or "ubicación" in texto_usuario_lower:
                        enviar_mensaje_texto(numero, DATOS_NEGOCIO["respuesta_ubicacion"])

                    else:
                        # Si no entendemos, mostramos error pero NO cambiamos estado
                        enviar_mensaje_texto(numero, DATOS_NEGOCIO["mensaje_error"])

            return "EVENT_RECEIVED", 200
    except Exception as e:
        print(f"Error: {e}", flush=True)
        return "EVENT_RECEIVED", 200

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 3000))
    app.run(host='0.0.0.0', port=port, debug=True)