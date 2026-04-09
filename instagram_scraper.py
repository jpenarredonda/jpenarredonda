"""
Instagram Scraper - Script para extraer datos públicos de Instagram
====================================================================
Basado en: https://scrapfly.io/blog/posts/how-to-scrape-instagram

IMPORTANTE:
- Solo funciona con perfiles y publicaciones PÚBLICAS (sin iniciar sesión).
- Respeta los Términos de Servicio de Instagram. Úsalo solo con fines educativos.
- Instagram detecta y bloquea peticiones de Python normales.
  Por eso usamos 'curl_cffi', que imita la huella digital de un navegador Chrome real.

REQUISITOS (instala con: pip install -r requirements.txt):
- curl_cffi
- jmespath
"""

import json
import time
import jmespath
from curl_cffi import requests as cf_requests


# =============================================================================
# CONFIGURACIÓN
# =============================================================================

# URL base de Instagram
BASE_URL = "https://www.instagram.com"

# Headers que imitan a un navegador real para no ser bloqueados
HEADERS = {
    "x-ig-app-id": "936619743392459",
    "x-asbd-id": "129477",
    "x-ig-www-claim": "0",
    "origin": "https://www.instagram.com",
    "accept": "*/*",
    "accept-language": "en-US,en;q=0.9",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
}


# =============================================================================
# FUNCIÓN 1: Obtener información del perfil
# =============================================================================

def obtener_perfil(usuario: str) -> dict:
    """
    Descarga los datos públicos del perfil de un usuario de Instagram.

    Parámetros:
        usuario (str): El nombre de usuario (sin @). Ejemplo: "natgeo"

    Retorna:
        dict: Diccionario con los datos del perfil, o {} si hubo error.
    """
    url = f"{BASE_URL}/{usuario}/?__a=1&__d=dis"
    print(f"\n[→] Buscando perfil de @{usuario}...")

    # Hacemos la petición imitando Chrome (imprescindible para no ser bloqueados)
    respuesta = cf_requests.get(url, headers=HEADERS, impersonate="chrome110")

    if respuesta.status_code != 200:
        print(f"[✗] Error {respuesta.status_code}: no se pudo obtener el perfil.")
        return {}

    datos_json = respuesta.json()

    # Extraemos solo los campos que nos interesan con jmespath
    perfil = jmespath.search(
        """{
            nombre:       graphql.user.full_name,
            usuario:      graphql.user.username,
            bio:          graphql.user.biography,
            seguidores:   graphql.user.edge_followed_by.count,
            siguiendo:    graphql.user.edge_follow.count,
            publicaciones:graphql.user.edge_owner_to_timeline_media.count,
            es_privado:   graphql.user.is_private,
            es_verificado:graphql.user.is_verified,
            foto_perfil:  graphql.user.profile_pic_url_hd,
            sitio_web:    graphql.user.external_url
        }""",
        datos_json,
    )

    if not perfil:
        print("[✗] No se encontraron datos. El perfil puede ser privado o no existir.")
        return {}

    print(f"[✓] Perfil obtenido: {perfil.get('nombre', 'Sin nombre')}")
    return perfil


# =============================================================================
# FUNCIÓN 2: Obtener publicaciones recientes del perfil
# =============================================================================

def obtener_publicaciones(usuario: str) -> list:
    """
    Descarga las publicaciones recientes (hasta 12) de un perfil público.

    Parámetros:
        usuario (str): El nombre de usuario (sin @). Ejemplo: "natgeo"

    Retorna:
        list: Lista de diccionarios, cada uno con datos de una publicación.
    """
    url = f"{BASE_URL}/{usuario}/?__a=1&__d=dis"
    print(f"\n[→] Buscando publicaciones de @{usuario}...")

    respuesta = cf_requests.get(url, headers=HEADERS, impersonate="chrome110")

    if respuesta.status_code != 200:
        print(f"[✗] Error {respuesta.status_code}: no se pudieron obtener las publicaciones.")
        return []

    datos_json = respuesta.json()

    # Extraemos la lista de publicaciones desde la respuesta JSON
    nodos = jmespath.search(
        "graphql.user.edge_owner_to_timeline_media.edges[*].node",
        datos_json,
    )

    if not nodos:
        print("[✗] No se encontraron publicaciones. El perfil puede ser privado.")
        return []

    publicaciones = []
    for nodo in nodos:
        pub = {
            "id":            nodo.get("id"),
            "tipo":          nodo.get("__typename"),           # Image, Video, etc.
            "descripcion":   jmespath.search(
                                 "edge_media_to_caption.edges[0].node.text", nodo
                             ) or "(sin descripción)",
            "me_gustas":     nodo.get("edge_liked_by", {}).get("count", 0),
            "comentarios":   nodo.get("edge_media_to_comment", {}).get("count", 0),
            "fecha":         time.strftime(
                                 "%Y-%m-%d %H:%M:%S",
                                 time.gmtime(nodo.get("taken_at_timestamp", 0)),
                             ),
            "url_imagen":    nodo.get("display_url"),
            "url_post":      f"https://www.instagram.com/p/{nodo.get('shortcode')}/",
        }
        publicaciones.append(pub)

    print(f"[✓] Se encontraron {len(publicaciones)} publicaciones.")
    return publicaciones


# =============================================================================
# FUNCIÓN 3: Guardar resultados en un archivo JSON
# =============================================================================

def guardar_json(datos, nombre_archivo: str):
    """
    Guarda un diccionario o lista en un archivo .json legible.

    Parámetros:
        datos: Los datos a guardar (dict o list).
        nombre_archivo (str): Nombre del archivo. Ejemplo: "perfil.json"
    """
    with open(nombre_archivo, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=2)
    print(f"[✓] Datos guardados en: {nombre_archivo}")


# =============================================================================
# PROGRAMA PRINCIPAL - Aquí empieza la ejecución
# =============================================================================

if __name__ == "__main__":

    # -------------------------------------------------------
    # PASO 1: Elige el usuario que quieres analizar (público)
    # -------------------------------------------------------
    USUARIO = "natgeo"   # <-- Cambia esto por el usuario que quieras

    # -------------------------------------------------------
    # PASO 2: Obtener perfil
    # -------------------------------------------------------
    perfil = obtener_perfil(USUARIO)

    if perfil:
        print("\n--- DATOS DEL PERFIL ---")
        for clave, valor in perfil.items():
            print(f"  {clave:>15}: {valor}")

        guardar_json(perfil, f"{USUARIO}_perfil.json")

    # Pequeña pausa para no hacer demasiadas peticiones seguidas
    time.sleep(1)

    # -------------------------------------------------------
    # PASO 3: Obtener publicaciones recientes
    # -------------------------------------------------------
    publicaciones = obtener_publicaciones(USUARIO)

    if publicaciones:
        print(f"\n--- ÚLTIMAS {len(publicaciones)} PUBLICACIONES ---")
        for i, pub in enumerate(publicaciones, 1):
            print(f"\n  [{i}] {pub['fecha']}")
            print(f"       Tipo:        {pub['tipo']}")
            print(f"       Me gustas:   {pub['me_gustas']}")
            print(f"       Comentarios: {pub['comentarios']}")
            print(f"       URL:         {pub['url_post']}")
            # Mostrar solo los primeros 80 caracteres de la descripción
            desc = pub['descripcion'][:80] + "..." if len(pub['descripcion']) > 80 else pub['descripcion']
            print(f"       Descripción: {desc}")

        guardar_json(publicaciones, f"{USUARIO}_publicaciones.json")

    print("\n[✓] ¡Listo! Revisa los archivos JSON generados.")
