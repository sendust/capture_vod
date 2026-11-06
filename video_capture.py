"""
video_capture.py — 브라우저 동영상 트래픽 캡처용 mitmproxy 애드온

설치:   pip install mitmproxy
실행:   mitmdump -s video_capture.py --set save_dir=captured
옵션:   --set host_filter=example-cdn.com   (해당 문자열이 포함된 호스트만 저장)
        --set min_size=1024                 (이보다 작은 미디어 응답은 무시, 매니페스트는 예외)

저장 구조:
  captured/
    index.csv                     ← 캡처 순서/URL/크기 기록
    <host>/000001_seg1.ts         ← 일반 응답(200): 순번_파일명
    <host>/RANGE_video.mp4        ← Range 응답(206): 오프셋 위치에 이어 붙여 한 파일로 재조립
"""
import csv
import os
import re
import time
from pathlib import Path
from urllib.parse import unquote, urlparse

from mitmproxy import ctx, http

MEDIA_CT_PREFIX = ("video/", "audio/")
MANIFEST_CT = ("mpegurl", "dash+xml")
MEDIA_EXTS = {
    ".mp4", ".m4s", ".m4v", ".m4a", ".ts", ".webm", ".mkv",
    ".aac", ".mp3", ".cmfv", ".cmfa", ".m3u8", ".mpd",
}
MANIFEST_EXTS = {".m3u8", ".mpd"}
CONTENT_RANGE_RE = re.compile(r"bytes (\d+)-(\d+)/(\d+|\*)")


def safe_name(s: str) -> str:
    return re.sub(r"[^\w.\-]", "_", s)[:150] or "file"


def sniff(body: bytes):
    """본문 내용으로 실제 미디어 형식 판별. (형식, 실제 데이터 시작 오프셋) 반환.
    .jpg/.png 등으로 위장하고 앞에 가짜 이미지 헤더를 붙인 세그먼트도 잡아냄."""
    # MPEG-TS: 188바이트 간격으로 sync byte 0x47 반복
    limit = min(len(body) - 188 * 3, 8192)
    for off in range(max(limit, 0)):
        if body[off] == 0x47 and body[off + 188] == 0x47 and body[off + 376] == 0x47 and body[off + 564] == 0x47:
            return "ts", off
    # fMP4 / MP4: 4~8바이트에 박스 타입
    if len(body) > 8 and body[4:8] in (b"ftyp", b"moof", b"styp", b"sidx", b"moov"):
        return "mp4", 0
    return None, 0


class VideoCapture:
    def __init__(self):
        self.seq = 0

    def load(self, loader):
        loader.add_option("save_dir", str, "captured", "저장 폴더")
        loader.add_option("min_size", int, 1024, "저장할 최소 크기(bytes)")
        loader.add_option("host_filter", str, "", "이 문자열이 포함된 호스트만 저장 (빈 값 = 전체)")
        loader.add_option("url_pattern", str, "", "URL이 이 정규식과 맞으면 형식과 관계없이 저장 (예: segment_\\d+)")
        loader.add_option("debug", bool, True, "저장하지 않은 이유를 로그로 출력")

    def configure(self, updated):
        self.root = Path(ctx.options.save_dir).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        ctx.log.info(f"[video_capture] 저장 위치: {self.root}")
        self.index = self.root / "index.csv"
        if self.index.exists():
            # 재실행 시 순번이 겹쳐 덮어쓰지 않도록 이어서 번호 매김
            with self.index.open(encoding="utf-8") as f:
                self.seq = max(sum(1 for _ in f) - 1, 0)
        else:
            with self.index.open("w", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow(
                    ["seq", "time", "status", "content_type", "bytes", "content_range", "url", "saved_as"]
                )

    def _classify(self, flow: http.HTTPFlow):
        ct = flow.response.headers.get("content-type", "").lower()
        ext = os.path.splitext(urlparse(flow.request.pretty_url).path.lower())[1]
        is_manifest = any(t in ct for t in MANIFEST_CT) or ext in MANIFEST_EXTS
        is_media = is_manifest or ct.startswith(MEDIA_CT_PREFIX) or ext in MEDIA_EXTS
        return is_media, is_manifest, ct

    def request(self, flow: http.HTTPFlow):
        # 브라우저 캐시 확인 헤더 제거 → 서버가 304(본문 없음) 대신 200(전체 데이터)을 보내게 함
        for h in ("if-none-match", "if-modified-since"):
            if h in flow.request.headers:
                del flow.request.headers[h]

    def _skip(self, flow, reason):
        if ctx.options.debug:
            ctx.log.info(f"[skip] {reason}: {flow.request.pretty_url[:120]}")

    def response(self, flow: http.HTTPFlow):
        resp = flow.response
        if resp is None or resp.status_code not in (200, 206):
            if resp is not None and resp.status_code == 304:
                self._skip(flow, "304 캐시 응답(본문 없음)")
            return
        if ctx.options.host_filter and ctx.options.host_filter not in flow.request.pretty_host:
            return

        is_media, is_manifest, ct = self._classify(flow)
        body = resp.content  # gzip/br 등 Content-Encoding은 자동 해제됨
        if not body:
            return

        # 확장자/Content-Type으로 안 잡히면 내용(매직 바이트)과 URL 패턴으로 재판별
        kind, offset = sniff(body)
        pattern_hit = bool(ctx.options.url_pattern) and re.search(ctx.options.url_pattern, flow.request.pretty_url)
        if not (is_media or kind or pattern_hit):
            if ctx.options.url_pattern == "" and "segment" in flow.request.pretty_url:
                self._skip(flow, f"미디어로 판별 안 됨 (앞 16바이트: {body[:16].hex()})")
            return
        if len(body) < ctx.options.min_size and not is_manifest:
            self._skip(flow, f"크기 미달 {len(body)}B")
            return

        u = urlparse(flow.request.pretty_url)
        host_dir = self.root / safe_name(u.netloc)
        host_dir.mkdir(parents=True, exist_ok=True)
        fname = safe_name(unquote(os.path.basename(u.path)))

        # 위장 세그먼트: 가짜 헤더를 잘라내고 실제 확장자로 저장
        if kind == "ts":
            body = body[offset:]
            fname = os.path.splitext(fname)[0] + ".ts"
        elif kind == "mp4" and os.path.splitext(fname)[1].lower() not in MEDIA_EXTS:
            fname = os.path.splitext(fname)[0] + ".m4s"

        content_range = resp.headers.get("content-range", "")
        m = CONTENT_RANGE_RE.match(content_range)

        if resp.status_code == 206 and m:
            # 프로그레시브 MP4 등: 조각을 원래 오프셋에 써서 하나의 파일로 복원
            start = int(m.group(1))
            out = host_dir / f"RANGE_{fname}"
            with out.open("r+b" if out.exists() else "wb") as f:
                f.seek(start)
                f.write(body)
            seq = ""
        else:
            # HLS(.ts) / DASH(.m4s) 세그먼트, 매니페스트 등: 받은 순서대로 저장
            self.seq += 1
            seq = self.seq
            out = host_dir / f"{seq:06d}_{fname}"
            out.write_bytes(body)

        with self.index.open("a", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow([
                seq, time.strftime("%Y-%m-%d %H:%M:%S"), resp.status_code, ct,
                len(body), content_range, flow.request.pretty_url, str(out),
            ])
        ctx.log.info(f"[saved] {out} ({len(body):,} bytes)")


addons = [VideoCapture()]
