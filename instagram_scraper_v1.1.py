"""
Instagram Scraper v1.1 - Script para extraer datos públicos de Instagram
=========================================================================
Basado en: https://scrapfly.io/blog/posts/how-to-scrape-instagram

NOVEDADES v1.1:
- Solicita el usuario por teclado al arrancar (no hay que editar el código)
- Genera archivos CSV además de JSON
- Descarga TODAS las publicaciones del perfil (con paginación automática)

IMPORTANTE:
- Solo funciona con perfiles y publicaciones PÚBLICAS (sin iniciar sesión).
- Respeta los Términos de Servicio de Instagram. Úsalo solo con fines educativos.

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

# Dos métodos de paginación; se intentan en orden hasta que uno funcione
QUERY_HASH = "e769aa130647d2354c40ea6a439bfc08"
DOC_ID     = "9310670392322965"

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


# =============================================================================
# HELPERS INTERNOS
# =============================================================================

def _get_json(url: str) -> dict:
    """Hace una petición GET y retorna el JSON, o {} si falla."""
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


def _get_pagina_posts(user_id: str, cursor: str) -> dict:
    """
    Intenta obtener una página de posts con dos métodos distintos:
      1) GET con query_hash (método antiguo, a veces bloqueado)
      2) POST con doc_id   (método más moderno)
    Retorna el JSON con los posts, o {} si ambos fallan.
    """
    variables = json.dumps({"id": user_id, "first": 12, "after": cursor})

    # --- Método 1: GET con query_hash ---
    url = f"{GRAPHQL_URL}?query_hash={QUERY_HASH}&variables={variables}"
    resp = cf_requests.get(url, headers=HEADERS, impersonate="chrome110")

    if resp.status_code == 200 and resp.content:
        try:
            datos = resp.json()
            if jmespath.search("data.user.edge_owner_to_timeline_media", datos):
                return datos
        except Exception:
            pass

    # --- Método 2: POST con doc_id ---
    headers_post = {**HEADERS, "content-type": "application/x-www-form-urlencoded"}
    resp = cf_requests.post(
        GRAPHQL_URL,
        data={"doc_id": DOC_ID, "variables": variables},
        headers=headers_post,
        impersonate="chrome110",
    )

    if resp.status_code == 200 and resp.content:
        try:
            datos = resp.json()
            # doc_id puede devolver la conexión bajo una clave distinta;
            # normalizamos para que el resto del código funcione igual
            conexion = jmespath.search(
                "data.xdt_api__v1__feed__user_timeline_graphql_connection", datos
            )
            if conexion:
                # Convertimos al mismo formato que usa el método 1
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
            # A veces el doc_id devuelve el formato estándar directamente
            if jmespath.search("data.user.edge_owner_to_timeline_media", datos):
                return datos
        except Exception:
            pass

    # Ambos métodos fallaron; mostrar diagnóstico
    print(f"\n[!] Ambos métodos de paginación fallaron.")
    print(f"    Código HTTP último intento: {resp.status_code}")
    if resp.content:
        print(f"    Respuesta (primeros 300 caracteres): {resp.text[:300]}")
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

def obtener_todas_publicaciones(usuario: str) -> list:
    """
    Descarga TODAS las publicaciones de un perfil público usando paginación.
    Instagram entrega 12 por vez; esta función sigue pidiendo páginas hasta
    obtenerlas todas.
    """
    print(f"\n[→] Buscando todas las publicaciones de @{usuario}...")

    # --- Página 1: viene incluida en la respuesta del perfil ---
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

    # --- Páginas siguientes ---
    pagina = 2
    while has_next and cursor:
        pausa = random.uniform(4.0, 7.0)  # pausa aleatoria entre 4 y 7 segundos
        print(f"\r[→] Esperando {pausa:.1f}s antes de la siguiente página...", end="", flush=True)
        time.sleep(pausa)

        datos = _get_pagina_posts(user_id, cursor)
        if not datos:
            print(f"\n[!] Se detuvo en la página {pagina}. "
                  f"Se guardaron {len(publicaciones)} publicaciones.")
            break

        media = jmespath.search("data.user.edge_owner_to_timeline_media", datos)
        if not media:
            print(f"\n[!] Respuesta inesperada en página {pagina}. Deteniendo.")
            break

        nuevas = [_parsear_nodo(e["node"]) for e in media.get("edges", [])]
        publicaciones.extend(nuevas)

        page_info = media.get("page_info", {})
        has_next  = page_info.get("has_next_page", False)
        cursor    = page_info.get("end_cursor")

        print(f"\r[→] Obtenidas: {len(publicaciones)}/{total}", end="", flush=True)
        pagina += 1

    print()  # salto de línea final
    print(f"[✓] Total descargadas: {len(publicaciones)} publicaciones.")
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
    """Guarda una lista de diccionarios (o un solo dict) en un archivo .csv."""
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

    print("=" * 50)
    print("   Instagram Scraper v1.1")
    print("=" * 50)
    USUARIO = input("\nIngresa el usuario de Instagram (sin @): ").strip()

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

    time.sleep(1)

    # --- Todas las publicaciones ---
    publicaciones = obtener_todas_publicaciones(USUARIO)

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
