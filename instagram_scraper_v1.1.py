"""
Instagram Scraper v1.1 - Script para extraer datos públicos de Instagram
=========================================================================
Basado en: https://scrapfly.io/blog/posts/how-to-scrape-instagram

NOVEDADES v1.1:
- Solicita el usuario por teclado al arrancar (no hay que editar el código)
- Genera archivos CSV además de JSON

IMPORTANTE:
- Solo funciona con perfiles y publicaciones PÚBLICAS (sin iniciar sesión).
- Respeta los Términos de Servicio de Instagram. Úsalo solo con fines educativos.

REQUISITOS (instala con: pip install -r requirements.txt):
- curl_cffi
- jmespath
"""

import csv
import json
import time
import jmespath
from curl_cffi import requests as cf_requests


# =============================================================================
# CONFIGURACIÓN
# =============================================================================

API_URL = "https://i.instagram.com/api/v1/users/web_profile_info/?username={}"

HEADERS = {
    "x-ig-app-id": "936619743392459",
    "x-requested-with": "XMLHttpRequest",
    "referer": "https://www.instagram.com/",
    "origin": "https://www.instagram.com",
    "accept": "*/*",
    "accept-language": "en-US,en;q=0.9",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
}


def _get_json(usuario: str) -> dict:
    """Hace la petición a la API de Instagram y retorna el JSON, o {} si falla."""
    url = API_URL.format(usuario)
    respuesta = cf_requests.get(url, headers=HEADERS, impersonate="chrome110")

    if not (200 <= respuesta.status_code < 300):
        print(f"[✗] Error HTTP {respuesta.status_code}.")
        return {}

    if not respuesta.content:
        print("[✗] Instagram devolvió una respuesta vacía (posible bloqueo temporal).")
        print("    Espera unos minutos e inténtalo de nuevo.")
        return {}

    try:
        return respuesta.json()
    except Exception:
        print("[✗] La respuesta no es JSON válido. Instagram pudo haber bloqueado la petición.")
        return {}


# =============================================================================
# FUNCIÓN 1: Obtener información del perfil
# =============================================================================

def obtener_perfil(usuario: str) -> dict:
    """Descarga los datos públicos del perfil de un usuario de Instagram."""
    print(f"\n[→] Buscando perfil de @{usuario}...")

    datos_json = _get_json(usuario)
    if not datos_json:
        return {}

    perfil = jmespath.search(
        """{
            nombre:        data.user.full_name,
            usuario:       data.user.username,
            bio:           data.user.biography,
            seguidores:    data.user.edge_followed_by.count,
            siguiendo:     data.user.edge_follow.count,
            publicaciones: data.user.edge_owner_to_timeline_media.count,
            es_privado:    data.user.is_private,
            es_verificado: data.user.is_verified,
            foto_perfil:   data.user.profile_pic_url_hd,
            sitio_web:     data.user.external_url
        }""",
        datos_json,
    )

    if not perfil or not perfil.get("usuario"):
        print("[✗] No se encontraron datos. El perfil puede ser privado o no existir.")
        return {}

    print(f"[✓] Perfil obtenido: {perfil.get('nombre') or perfil.get('usuario')}")
    return perfil


# =============================================================================
# FUNCIÓN 2: Obtener publicaciones recientes del perfil
# =============================================================================

def obtener_publicaciones(usuario: str) -> list:
    """Descarga las publicaciones recientes (hasta 12) de un perfil público."""
    print(f"\n[→] Buscando publicaciones de @{usuario}...")

    datos_json = _get_json(usuario)
    if not datos_json:
        return []

    nodos = jmespath.search(
        "data.user.edge_owner_to_timeline_media.edges[*].node",
        datos_json,
    )

    if not nodos:
        print("[✗] No se encontraron publicaciones. El perfil puede ser privado.")
        return []

    publicaciones = []
    for nodo in nodos:
        pub = {
            "id":          nodo.get("id"),
            "tipo":        nodo.get("__typename"),
            "descripcion": jmespath.search(
                               "edge_media_to_caption.edges[0].node.text", nodo
                           ) or "(sin descripción)",
            "me_gustas":   nodo.get("edge_liked_by", {}).get("count", 0),
            "comentarios": nodo.get("edge_media_to_comment", {}).get("count", 0),
            "fecha":       time.strftime(
                               "%Y-%m-%d %H:%M:%S",
                               time.gmtime(nodo.get("taken_at_timestamp", 0)),
                           ),
            "url_imagen":  nodo.get("display_url"),
            "url_post":    f"https://www.instagram.com/p/{nodo.get('shortcode')}/",
        }
        publicaciones.append(pub)

    print(f"[✓] Se encontraron {len(publicaciones)} publicaciones.")
    return publicaciones


# =============================================================================
# FUNCIÓN 3: Guardar JSON
# =============================================================================

def guardar_json(datos, nombre_archivo: str):
    """Guarda un diccionario o lista en un archivo .json legible."""
    with open(nombre_archivo, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=2)
    print(f"[✓] JSON guardado en:  {nombre_archivo}")


# =============================================================================
# FUNCIÓN 4: Guardar CSV
# =============================================================================

def guardar_csv(datos, nombre_archivo: str):
    """
    Guarda una lista de diccionarios en un archivo .csv.
    Si se le pasa un solo diccionario (perfil), lo convierte en una lista primero.
    """
    # Si es un dict (perfil), lo envolvemos en lista para que csv lo trate igual
    if isinstance(datos, dict):
        datos = [datos]

    if not datos:
        print("[!] No hay datos para guardar en CSV.")
        return

    columnas = list(datos[0].keys())

    with open(nombre_archivo, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columnas)
        writer.writeheader()
        writer.writerows(datos)

    print(f"[✓] CSV guardado en:   {nombre_archivo}")


# =============================================================================
# PROGRAMA PRINCIPAL
# =============================================================================

if __name__ == "__main__":

    # -------------------------------------------------------
    # Solicitar usuario por teclado
    # -------------------------------------------------------
    print("=" * 50)
    print("   Instagram Scraper v1.1")
    print("=" * 50)
    USUARIO = input("\nIngresa el usuario de Instagram (sin @): ").strip()

    if not USUARIO:
        print("[✗] No ingresaste ningún usuario. Saliendo.")
        exit(1)

    # -------------------------------------------------------
    # Obtener y guardar perfil
    # -------------------------------------------------------
    perfil = obtener_perfil(USUARIO)

    if perfil:
        print("\n--- DATOS DEL PERFIL ---")
        for clave, valor in perfil.items():
            print(f"  {clave:>15}: {valor}")

        guardar_json(perfil,  f"{USUARIO}_perfil.json")
        guardar_csv(perfil,   f"{USUARIO}_perfil.csv")

    time.sleep(1)

    # -------------------------------------------------------
    # Obtener y guardar publicaciones
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
            desc = pub['descripcion'][:80] + "..." if len(pub['descripcion']) > 80 else pub['descripcion']
            print(f"       Descripción: {desc}")

        guardar_json(publicaciones, f"{USUARIO}_publicaciones.json")
        guardar_csv(publicaciones,  f"{USUARIO}_publicaciones.csv")

    print("\n[✓] ¡Listo! Archivos generados:")
    print(f"    - {USUARIO}_perfil.json / .csv")
    print(f"    - {USUARIO}_publicaciones.json / .csv")
