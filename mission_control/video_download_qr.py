"""Local download QR for immutable social video renders."""

import json
import re
from collections.abc import Callable, Mapping
from pathlib import Path
from sqlite3 import Connection
from typing import TypedDict

from .agent_process import capture
from .common import Invalid
from .media_native import capability
from .play_contract import PACKAGE


class DownloadQR(TypedDict):
    schema: str
    url: str


def download_target(db: Connection, app_id: str) -> DownloadQR | None:
    """Resolve a store link solely from the current app manifest."""
    row = db.execute("SELECT data FROM apps WHERE id=?", (app_id,)).fetchone()
    if row is None:
        return None
    data = json.loads(row["data"])
    apple_id = data.get("store_app_id")
    if isinstance(apple_id, str) and re.fullmatch(r"[0-9]{1,30}", apple_id) and int(apple_id):
        url = f"https://apps.apple.com/app/id{apple_id}"
    else:
        package = data.get("android_package")
        if not isinstance(package, str) or len(package) > 255 or not re.fullmatch(PACKAGE, package):
            return None
        url = f"https://play.google.com/store/apps/details?id={package}"
    return {"schema": "wmm.video-download-qr.v1", "url": url}


def verify_download_qr(db: Connection, app_id: str, render: Mapping[str, object]) -> DownloadQR | None:
    """Check a retained app-bound QR or the explicit no-QR render choice."""
    inputs, receipt = render.get("inputs"), render.get("receipt")
    if not isinstance(inputs, dict) or not isinstance(receipt, dict):
        raise Invalid("Render and review a new video with your download QR code choice before publishing")
    if inputs.get("download_qr") is False:
        if receipt.get("download_qr") is not None:
            raise Invalid("Rendered download QR does not match the saved video choice")
        return None
    target = download_target(db, app_id)
    if target is None:
        raise Invalid("Add this app's store ID in App setup or render again without a download QR code")
    if inputs.get("download_qr") != target or receipt.get("download_qr") != target:
        raise Invalid("Render and review a new video with your download QR code choice before publishing")
    return target


def _qr_matrix(target: DownloadQR) -> list[bytes]:
    from qrcodegen import QrCode

    qr = QrCode.encode_text(target["url"], QrCode.Ecc.MEDIUM)
    modules = qr.get_size()
    return [bytes(0 if qr.get_module(x, y) else 255 for x in range(-4, modules + 4)) for y in range(-4, modules + 4)]


def _geometry(dimensions: tuple[int, int], modules: int) -> tuple[int, int, int]:
    width, height = dimensions
    unit = 6 if modules <= 45 else 4
    return (width * 3 // 50) & ~1, (height // 25) & ~1, unit


def download_qr_insets(dimensions: tuple[int, int], target: DownloadQR) -> tuple[int, int]:
    """Reserve space for the QR without placing it over the title or content."""
    width, height = dimensions
    modules = len(_qr_matrix(target))
    x, y, unit = _geometry(dimensions, modules)
    left = ((x + modules * unit) * 100 + width - 1) // width + 3
    top = ((y + modules * unit) * 100 + height - 1) // height + 2
    return left, top


def stamp_download_qr(folder: Path, dimensions: tuple[int, int], target: DownloadQR, alive: Callable[[], None]) -> None:
    """Burn a bounded, locally encoded QR into the full clip before hashing."""
    tools = capability().get("tools", {})
    ffmpeg = tools.get("ffmpeg") if isinstance(tools, dict) else None
    if not isinstance(ffmpeg, str) or not ffmpeg:
        raise Invalid("Prepare FFmpeg to add this app's download QR code")
    matrix = _qr_matrix(target)
    modules = len(matrix)
    x, y, unit = _geometry(dimensions, modules)
    size = modules * unit
    rows = [b"".join(bytes((pixel,)) * unit for pixel in line) * unit for line in matrix]
    code = folder / "download-qr.pgm"
    with code.open("xb") as file:
        file.write(f"P5\n{size} {size}\n255\n".encode("ascii"))
        file.write(b"".join(rows))
    video = folder / "video.mp4"
    output = folder / "download-ready.mp4"
    command = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-nostdin",
        "-n",
        "-protocol_whitelist",
        "file,pipe",
        "-i",
        str(video),
        "-protocol_whitelist",
        "file,pipe",
        "-i",
        str(code),
        "-filter_complex_threads",
        "1",
        "-filter_complex",
        f"[0:v][1:v]overlay={x}:{y}[v]",
        "-map",
        "[v]",
        "-map",
        "0:a?",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "17",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "copy",
        "-movflags",
        "+faststart",
        str(output),
    ]
    result = capture(command, folder=folder, alive=alive, timeout=180)
    if result["code"] or not output.is_file() or output.is_symlink():
        raise Invalid("This app's download QR could not be added; review the retained video")
    alive()
    output.replace(video)
