import re
from urllib.parse import parse_qsl, quote, unquote, urlencode, urljoin, urlsplit, urlunsplit

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db, settings
from app.models import Camera, Room
from app.services.camera_auth import get_camera_credentials

router = APIRouter(prefix="/preview", tags=["preview"])


def _format(url: str) -> str:
    """`hls` untuk playlist .m3u8; selain itu halaman pemutar seperti MediaMTX."""
    return "hls" if ".m3u8" in url.lower() else "page"


def _entry(
    *, camera_id: str | None, name: str, url: str,
    camera_pk: int | None = None, source_url: str | None = None,
):
    return {
        "id": camera_pk,
        "name": name,
        "camera_id": camera_id,
        "url": url,
        "format": _format(source_url or url),
    }


@router.get("")
def get_preview(
    request: Request,
    room_id: int | None = None,
    db: Session = Depends(get_db),
):
    """Daftar feed CCTV ruang; kompatibel dengan URL camera lama dan PREVIEW_URL global."""
    cameras = []
    has_room_camera_records = False
    if room_id is not None:
        room = db.get(Room, room_id)
        if room is not None:
            room_cameras = db.scalars(
                select(Camera).where(Camera.room_id == room_id).order_by(Camera.id)
            ).all()
            has_room_camera_records = bool(room_cameras)
            cameras = []
            for camera in room_cameras:
                if not camera.active:
                    continue
                url = camera.camera_url
                if get_camera_credentials(camera.id):
                    source = urlsplit(camera.camera_url)
                    proxy_path = (
                        quote(source.path.rsplit("/", 1)[-1])
                        if source.path.lower().endswith(".m3u8") else ""
                    )
                    url = f"{str(request.base_url).rstrip('/')}/preview/proxy/{camera.id}/{proxy_path}"
                cameras.append(
                    _entry(
                        camera_id=camera.camera_id,
                        name=camera.name,
                        url=url,
                        camera_pk=camera.id,
                        source_url=camera.camera_url,
                    )
                )
            if not has_room_camera_records and room.camera_url:
                cameras = [
                    _entry(
                        camera_id=room.camera_id,
                        name="CCTV utama",
                        url=room.camera_url,
                    )
                ]

    if not cameras and not has_room_camera_records and settings.preview_url:
        cameras = [
            _entry(camera_id=None, name="Preview global", url=settings.preview_url)
        ]

    if not cameras:
        result = {
            "enabled": False,
            "format": "hls",
            "url": None,
            "camera_id": None,
        }
    else:
        first = cameras[0]
        result = {
            "enabled": True,
            "format": first["format"],
            "url": first["url"],
            "camera_id": first["camera_id"],
        }
    if has_room_camera_records:
        result["cameras"] = cameras
    return result


def _same_origin(left: str, right: str) -> bool:
    a, b = urlsplit(left), urlsplit(right)
    try:
        return (
            a.scheme.lower() == b.scheme.lower()
            and a.hostname == b.hostname
            and a.port == b.port
            and a.username is None and a.password is None
            and b.username is None and b.password is None
            and a.scheme.lower() in {"http", "https"}
        )
    except ValueError:
        return False


@router.get("/proxy/{camera_pk}/")
@router.get("/proxy/{camera_pk}/{path:path}")
def proxy_camera(
    camera_pk: int,
    request: Request,
    path: str = "",
    db: Session = Depends(get_db),
):
    """Proxy halaman/HLS; Basic Auth hanya dikirim ke origin URL kamera."""
    camera = db.get(Camera, camera_pk)
    credentials = get_camera_credentials(camera_pk)
    if camera is None or not camera.active or credentials is None:
        raise HTTPException(404, "Preview CCTV tidak tersedia")

    source = urlsplit(camera.camera_url)
    if any(part in {".", ".."} for part in unquote(path).split("/")):
        raise HTTPException(404, "Jalur preview tidak tersedia")
    if source.path.endswith("/"):
        upstream_path = source.path + path
        allowed_path_prefix = source.path
    elif path:
        allowed_path_prefix = source.path.rsplit("/", 1)[0] + "/"
        upstream_path = allowed_path_prefix + path
    else:
        upstream_path = source.path
        allowed_path_prefix = source.path.rsplit("/", 1)[0] + "/"
    query = urlencode(
        parse_qsl(source.query, keep_blank_values=True)
        + parse_qsl(request.url.query, keep_blank_values=True),
        doseq=True,
    )
    original_url = urlunsplit((source.scheme, source.netloc, upstream_path, query, ""))
    target_url = original_url
    forwarded = {
        key: value
        for key, value in request.headers.items()
        if key.lower() in {"accept", "range", "if-range", "if-none-match", "if-modified-since"}
    }
    client = httpx.Client(
        timeout=httpx.Timeout(30, read=None), follow_redirects=False, trust_env=False
    )
    upstream = None
    try:
        for _ in range(5):
            upstream = client.send(
                client.build_request("GET", target_url, headers=forwarded),
                auth=httpx.BasicAuth(*credentials),
                stream=True,
            )
            if not (300 <= upstream.status_code < 400 and upstream.status_code != 304):
                break
            location = upstream.headers.get("location")
            upstream.close()
            if not location:
                raise HTTPException(502, "Redirect CCTV tidak memiliki tujuan")
            redirected_url = urljoin(target_url, location)
            redirected = urlsplit(redirected_url)
            if (
                not _same_origin(camera.camera_url, redirected_url)
                or not redirected.path.startswith(allowed_path_prefix)
            ):
                raise HTTPException(502, "Redirect CCTV ke origin atau jalur lain ditolak")
            target_url = redirected_url
        else:
            raise HTTPException(502, "Terlalu banyak redirect dari CCTV")
    except HTTPException:
        client.close()
        raise
    except httpx.HTTPError:
        client.close()
        raise HTTPException(502, "Tidak dapat menghubungi sumber CCTV")

    content_type = upstream.headers.get("content-type", "application/octet-stream")
    headers = {
        key: value
        for key, value in upstream.headers.items()
        if key.lower() in {"cache-control", "content-length", "content-range", "accept-ranges", "etag"}
    }
    if upstream.status_code in {401, 403}:
        upstream.close()
        client.close()
        return Response(
            "Login CCTV ditolak. Periksa username dan password di Admin.",
            status_code=502,
            media_type="text/plain",
        )
    if "text/html" in content_type or "mpegurl" in content_type:
        body = upstream.read()
        status_code = upstream.status_code
        upstream.close()
        client.close()
        proxy_root = f"/preview/proxy/{camera_pk}/"
        text_body = body.decode("utf-8", errors="replace")
        if "text/html" in content_type:
            text_body = re.sub(
                r'(["\'(=])/(?!/)',
                lambda match: match.group(1) + proxy_root,
                text_body,
            )
        else:
            text_body = re.sub(r"(?m)^/(?!/)", proxy_root, text_body)
        headers.pop("content-length", None)
        return Response(
            text_body, status_code=status_code, media_type=content_type, headers=headers
        )

    def stream_body():
        try:
            yield from upstream.iter_bytes()
        finally:
            upstream.close()
            client.close()

    return StreamingResponse(
        stream_body(), status_code=upstream.status_code,
        media_type=content_type, headers=headers,
    )
