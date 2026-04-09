"""
Instagram Scraper v1.1 - Script para extraer datos públicos de Instagram
=========================================================================
Basado en: https://scrapfly.io/blog/posts/how-to-scrape-instagram

NOVEDADES v1.1:
- Solicita el usuario por teclado al arrancar (no hay que editar el código)
- Genera archivos CSV además de JSON
- Descarga TODAS las publicaciones del perfil (con paginación automática)
- Login via cookie de sesión para evitar bloqueos en la paginación

CÓMO OBTENER TU SESSION ID:
  1. Abre Instagram en Chrome y logéate
  2. Presiona F12 → pestaña "Application" → "Cookies" → https://www.instagram.com
  3. Copia el valor de "sessionid"
  4. Pégalo cuando el script te lo pida

IMPORTANTE:
- No compartas tu sessionid con nadie (es equivalente a tu contraseña).
- Solo funciona con perfiles PÚBLICOS o los que puedes ver logueado.
- Úsalo solo con fines educativos.

REQUISITOS (instala con: pip install -r requirements.txt):
- curl_cffi
- jmespath
"""

import csv
import json
import random
import time
import jmespath
from curl_cffi import requests as cf_requests


# =============================================================================
# CONFIGURACIÓN
# =============================================================================

API_URL     = "https://i.instagram.com/api/v1/users/web_profile_info/?username={}"
GRAPHQL_URL = "https://www.instagram.com/graphql/query"
QUERY_HASH  = "e769aa130647d2354c40ea6a439bfc08"
DOC_ID      = "9310670392322965"

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

# Se rellena al inicio con la cookie del usuario
COOKIES: dict = {}


# =============================================================================
# HELPERS INTERNOS
# =============================================================================

def _get_json(url: str) -> dict:
    """Hace una petición GET autenticada y retorna el JSON, o {} si falla."""
    respuesta = cf_requests.get(
        url, headers=HEADERS, cookies=COOKIES, impersonate="chrome110"
    )

    if not (200 <= respuesta.status_code < 300):
        print(f"[✗] Error HTTP {respuesta.status_code}.")
        return {}

    if not respuesta.content:
        print("[✗] Instagram devolvió una respuesta vacía.")
        return {}

    try:
        return respuesta.json()
    except Exception:
        print("[✗] La respuesta no es JSON válido.")
        return {}


def _get_csrftoken() -> str:
    """
    Hace una petición simple a Instagram para obtener el csrftoken de las cookies.
    Es necesario para las peticiones POST (paginación).
    """
    resp = cf_requests.get(
        "https://www.instagram.com/",
        headers=HEADERS,
        cookies=COOKIES,
        impersonate="chrome110",
    )
    return resp.cookies.get("csrftoken", "")


def _get_pagina_posts(user_id: str, cursor: str, csrftoken: str) -> dict:
    """
    Intenta obtener una página de posts con dos métodos:
      1) GET con query_hash
      2) POST con doc_id (usa csrftoken para autenticación)
    """
    variables = json.dumps({"id": user_id, "first": 12, "after": cursor})

    # --- Método 1: GET con query_hash ---
    url = f"{GRAPHQL_URL}?query_hash={QUERY_HASH}&variables={variables}"
    resp = cf_requests.get(
        url, headers=HEADERS, cookies=COOKIES, impersonate="chrome110"
    )

    if resp.status_code == 200 and resp.content:
        try:
            datos = resp.json()
            if jmespath.search("data.user.edge_owner_to_timeline_media", datos):
                return datos
        except Exception:
            pass

    # --- Método 2: POST con doc_id ---
    headers_post = {
        **HEADERS,
        "content-type": "application/x-www-form-urlencoded",
        "x-csrftoken": csrftoken,
    }
    cookies_post = {**COOKIES, "csrftoken": csrftoken}

    resp = cf_requests.post(
        GRAPHQL_URL,
        data={"doc_id": DOC_ID, "variables": variables},
        headers=headers_post,
        cookies=cookies_post,
        impersonate="chrome110",
    )

    if resp.status_code == 200 and resp.content:
        try:
            datos = resp.json()
            # Normalizar respuesta del doc_id al mismo formato que query_hash
            conexion = jmespath.search(
                "data.xdt_api__v1__feed__user_timeline_graphql_connection", datos
            )
            if conexion:
                return {
                    "data": {
                        "user": {
                            "edge_owner_to_timeline_media": {
                                "edges":     conexion.get("edges", []),
                                "page_info": conexion.get("page_info", {}),
                            }
                        }
                    }
                }
            if jmespath.search("data.user.edge_owner_to_timeline_media", datos):
                return datos
        except Exception:
            pass

    # Diagnóstico si ambos fallan
    print(f"\n[!] Ambos métodos de paginación fallaron.")
    print(f"    Código HTTP: {resp.status_code}")
    if resp.content:
        print(f"    Respuesta: {resp.text[:300]}")
    return {}


def _parsear_nodo(nodo: dict) -> dict:
    """Convierte un nodo de publicación en un diccionario limpio."""
    return {
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


# =============================================================================
# FUNCIÓN 1: Obtener información del perfil
# =============================================================================

def obtener_perfil(usuario: str) -> dict:
    """Descarga los datos públicos del perfil de un usuario de Instagram."""
    print(f"\n[→] Buscando perfil de @{usuario}...")

    datos_json = _get_json(API_URL.format(usuario))
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
# FUNCIÓN 2: Obtener TODAS las publicaciones con paginación
# =============================================================================

def obtener_todas_publicaciones(usuario: str, csrftoken: str) -> list:
    """
    Descarga TODAS las publicaciones de un perfil usando paginación autenticada.
    """
    print(f"\n[→] Buscando todas las publicaciones de @{usuario}...")

    datos_json = _get_json(API_URL.format(usuario))
    if not datos_json:
        return []

    user_data = jmespath.search("data.user", datos_json)
    if not user_data:
        print("[✗] No se encontraron datos del usuario.")
        return []

    user_id = user_data.get("id")
    media   = user_data.get("edge_owner_to_timeline_media", {})
    total   = media.get("count", 0)

    publicaciones = [_parsear_nodo(e["node"]) for e in media.get("edges", [])]

    page_info = media.get("page_info", {})
    has_next  = page_info.get("has_next_page", False)
    cursor    = page_info.get("end_cursor")

    print(f"[→] Total en el perfil: {total} publicaciones")
    print(f"[→] Obtenidas: {len(publicaciones)}/{total}", end="", flush=True)

    pagina = 2
    while has_next and cursor:
        pausa = random.uniform(4.0, 7.0)
        print(f"\r[→] Esperando {pausa:.1f}s...                          ", end="", flush=True)
        time.sleep(pausa)

        datos = _get_pagina_posts(user_id, cursor, csrftoken)
        if not datos:
            print(f"\n[!] Se detuvo en la página {pagina}. "
                  f"Se guardaron {len(publicaciones)} publicaciones.")
            break

        media = jmespath.search("data.user.edge_owner_to_timeline_media", datos)
        if not media:
            print(f"\n[!] Respuesta inesperada en página {pagina}. Deteniendo.")
            break

        publicaciones.extend([_parsear_nodo(e["node"]) for e in media.get("edges", [])])

        page_info = media.get("page_info", {})
        has_next  = page_info.get("has_next_page", False)
        cursor    = page_info.get("end_cursor")

        print(f"\r[→] Obtenidas: {len(publicaciones)}/{total}          ", end="", flush=True)
        pagina += 1

    print()
    print(f"[✓] Total descargadas: {len(publicaciones)} publicaciones.")
    return publicaciones


# =============================================================================
# FUNCIÓN 3: Guardar JSON
# =============================================================================

def guardar_json(datos, nombre_archivo: str):
    with open(nombre_archivo, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=2)
    print(f"[✓] JSON guardado en:  {nombre_archivo}")


# =============================================================================
# FUNCIÓN 4: Guardar CSV
# =============================================================================

def guardar_csv(datos, nombre_archivo: str):
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

    print("=" * 55)
    print("   Instagram Scraper v1.1")
    print("=" * 55)

    # --- Pedir session id ---
    print("\nPara evitar bloqueos, el script necesita tu cookie de sesión.")
    print("Cómo obtenerla:")
    print("  1. Abre Instagram en Chrome y logéate")
    print("  2. Presiona F12 → Application → Cookies → instagram.com")
    print("  3. Copia el valor de 'sessionid'\n")
    session_id = input("Pega tu sessionid aquí: ").strip()

    if not session_id:
        print("[!] No ingresaste sessionid. Se intentará sin sesión (puede fallar).")
    else:
        COOKIES["sessionid"] = session_id
        print("[✓] Sesión configurada.")

    # Obtener csrftoken (necesario para peticiones POST)
    print("[→] Obteniendo token de seguridad...")
    csrftoken = _get_csrftoken()
    if csrftoken:
        COOKIES["csrftoken"] = csrftoken
        print("[✓] Token obtenido.")
    else:
        print("[!] No se pudo obtener el csrftoken. La paginación puede fallar.")

    # --- Pedir usuario ---
    USUARIO = input("\nIngresa el usuario de Instagram a analizar (sin @): ").strip()
    if not USUARIO:
        print("[✗] No ingresaste ningún usuario. Saliendo.")
        exit(1)

    # --- Perfil ---
    perfil = obtener_perfil(USUARIO)

    if perfil:
        print("\n--- DATOS DEL PERFIL ---")
        for clave, valor in perfil.items():
            print(f"  {clave:>15}: {valor}")
        guardar_json(perfil, f"{USUARIO}_perfil.json")
        guardar_csv(perfil,  f"{USUARIO}_perfil.csv")

    time.sleep(2)

    # --- Todas las publicaciones ---
    publicaciones = obtener_todas_publicaciones(USUARIO, csrftoken)

    if publicaciones:
        print(f"\n--- PRIMERAS 5 PUBLICACIONES (muestra) ---")
        for i, pub in enumerate(publicaciones[:5], 1):
            print(f"\n  [{i}] {pub['fecha']}")
            print(f"       Tipo:        {pub['tipo']}")
            print(f"       Me gustas:   {pub['me_gustas']}")
            print(f"       Comentarios: {pub['comentarios']}")
            print(f"       URL:         {pub['url_post']}")
            desc = pub['descripcion'][:80] + "..." if len(pub['descripcion']) > 80 else pub['descripcion']
            print(f"       Descripción: {desc}")

        if len(publicaciones) > 5:
            print(f"\n  ... y {len(publicaciones) - 5} publicaciones más (ver archivos).")

        guardar_json(publicaciones, f"{USUARIO}_publicaciones.json")
        guardar_csv(publicaciones,  f"{USUARIO}_publicaciones.csv")

    print("\n[✓] ¡Listo! Archivos generados:")
    print(f"    - {USUARIO}_perfil.json / .csv")
    print(f"    - {USUARIO}_publicaciones.json / .csv")
