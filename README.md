# capture_vod

DRM이 없는 VOD 사이트에서 브라우저가 받아 오는 동영상 데이터를 그대로 저장하는 [mitmproxy](https://mitmproxy.org/) 애드온입니다.

브라우저와 인터넷 사이에 로컬 프록시를 두고, 지나가는 HTTP(S) 응답 중 동영상 세그먼트·매니페스트·Range 조각만 골라 디스크에 씁니다.

> **사용 범위**
> DRM(Widevine, FairPlay, PlayReady 등)이 걸린 콘텐츠는 저장되더라도 암호화된 상태라 재생할 수 없고, 이 도구는 DRM 해제 기능이 없습니다.
> 저작권이 있는 콘텐츠는 권리자 허락이나 관련 법이 허용하는 범위 안에서만 사용하세요.

---

## 왜 프록시 방식인가

scapy나 pyshark로 패킷을 떠도 영상을 복원할 수 없습니다. 요즘 동영상은 거의 다 HTTPS(TLS)이고 HTTP/2나 QUIC(HTTP/3)로 전송되기 때문에, 캡처되는 건 암호화된 바이트뿐입니다.

mitmproxy는 로컬 CA 인증서로 TLS를 중간에서 풀어 주므로, 애드온이 복호화된 HTTP 응답 본문을 직접 다룰 수 있습니다. 브라우저에 프록시를 지정하면 QUIC 대신 TCP(HTTP/1.1, HTTP/2)를 쓰기 때문에 정상적으로 가로챌 수 있습니다.

---

## 저장소 구성

| 파일 | 역할 |
|---|---|
| `video_capture.py` | mitmproxy 애드온 본체 |
| `1_start_brave_with_proxy2.bat` | 가상환경의 `mitmdump`로 프록시 실행 (`save_dir=captured`, `url_pattern="segment_\d+"`) |
| `2_start_brave_with_proxy.bat` | Brave를 `--proxy-server=127.0.0.1:8080`으로 실행 (OS 프록시 설정 변경 불필요) |
| `3_ts 저장된 폴더에서 파워쉘 실행.txt` | 저장된 `.ts` 세그먼트를 번호순으로 이어 붙이는 PowerShell 스크립트 |
| `pyvenv.cfg` | 작성자 환경의 venv 설정 (Python 3.14, `C:\utility\videosave`) |

---

## 설치

Windows 기준입니다. 배치 파일은 저장소 폴더 자체가 가상환경이라고 가정하고 `Scripts\mitmdump.exe`를 호출합니다.

```powershell
# 저장소 폴더를 가상환경으로 만들고 mitmproxy 설치
python -m venv C:\utility\videosave
cd C:\utility\videosave
Scripts\pip install mitmproxy
# video_capture.py와 .bat 파일들을 이 폴더에 둡니다
```

> `pyvenv.cfg`는 작성자 PC의 경로가 들어 있으므로, 위처럼 `venv`를 새로 만들면 자동으로 덮어써집니다.

가상환경 없이 쓰려면 `pip install mitmproxy` 후 `mitmdump`를 직접 실행하면 됩니다.

### CA 인증서 설치

프록시를 켠 상태에서 브라우저로 <http://mitm.it>에 접속해 인증서를 받은 뒤, OS에 맞게 설치합니다.

- **Windows**: "신뢰할 수 있는 루트 인증 기관"에 설치합니다.
  확인하려면 `Win + R` → `certmgr.msc` → 신뢰할 수 있는 루트 인증 기관 → 인증서 목록에 **mitmproxy**가 있으면 됩니다.
- **macOS**: 키체인에 추가한 뒤 "항상 신뢰"로 설정합니다.
- **Linux (Brave/Chrome)**: `brave://settings/certificates` → "인증 기관" 탭 → 가져오기 → "웹사이트 식별 신뢰" 체크.
- **Firefox**: OS 저장소를 쓰지 않으므로 Firefox 설정의 인증서 관리자에 따로 가져와야 합니다.

> **작업이 끝나면 인증서를 꼭 삭제하세요.** 같은 위치(`certmgr.msc`)에서 mitmproxy 인증서를 우클릭해 삭제합니다. 이 인증서가 남아 있으면, 같은 키를 가진 누군가가 이 PC의 HTTPS 통신을 가로챌 수 있습니다.

---

## 사용법

### 배치 파일로 실행 (Windows + Brave)

1. `1_start_brave_with_proxy2.bat` 실행 → 127.0.0.1:8080에서 프록시가 대기합니다.
2. `2_start_brave_with_proxy.bat` 실행 → 프록시를 거치는 Brave 창이 뜹니다.
   이미 Brave가 실행 중이면 플래그가 무시될 수 있으니, Brave를 완전히 종료한 뒤 실행하세요.
3. (처음 한 번) <http://mitm.it>에서 인증서를 설치합니다.
4. 동영상을 처음부터 끝까지 재생합니다. 재생된 구간만 저장됩니다.
5. `captured\<호스트명>\` 폴더에 세그먼트가, `captured\index.csv`에 기록이 쌓입니다.

### 직접 실행

```bash
mitmdump -s video_capture.py --set save_dir=captured
```

브라우저 프록시를 `127.0.0.1:8080`으로 지정합니다.

- Chrome/Edge는 OS 프록시 설정을 따릅니다 (또는 `--proxy-server` 플래그).
- Firefox는 설정 → 네트워크 설정에서 따로 지정합니다.

### 옵션

`--set 이름=값` 형태로 지정합니다.

| 옵션 | 기본값 | 설명 |
|---|---|---|
| `save_dir` | `captured` | 저장 폴더 |
| `min_size` | `1024` | 이보다 작은 미디어 응답은 무시 (매니페스트는 예외) |
| `host_filter` | (빈 값) | 이 문자열이 호스트에 포함된 응답만 저장. 예: `--set host_filter=cdn.example.com` |
| `url_pattern` | (빈 값) | URL이 이 정규식과 맞으면 형식과 관계없이 저장. 자동 판별이 실패할 때 대비용. 예: `--set url_pattern="segment_\d+"` |
| `debug` | `true` | 저장하지 않은 이유(304 응답, 크기 미달, 판별 실패 등)를 로그로 출력 |

---

## 동작 방식

### 1. 미디어 판별

응답이 `200` 또는 `206`일 때만 처리하며, 아래 셋 중 하나라도 맞으면 저장 대상입니다.

1. **헤더/확장자**: `Content-Type`이 `video/*`, `audio/*`, `mpegurl`, `dash+xml`이거나, URL 확장자가 `.ts .m4s .mp4 .m4v .m4a .webm .mkv .aac .mp3 .cmfv .cmfa .m3u8 .mpd` 중 하나
2. **내용 검사 (매직 바이트)**
   - MPEG-TS: 앞 8KB 안에서 188바이트 간격으로 `0x47` 동기 바이트가 4번 연속 나오는 위치를 찾습니다.
   - MP4/fMP4: 4~8바이트가 `ftyp`, `moof`, `styp`, `sidx`, `moov` 중 하나인지 봅니다.
3. **URL 패턴**: `url_pattern` 정규식과 일치

### 2. 위장 세그먼트 처리

일부 사이트는 `segment_0129.jpg`처럼 세그먼트를 이미지 확장자로 위장하고, 실제 MPEG-TS 데이터 앞에 가짜 PNG/JPEG 헤더를 붙여 보냅니다. 확장자와 `Content-Type`만 보면 이미지로 오인됩니다.

이 애드온은 내용 검사로 실제 TS 시작 위치를 찾은 뒤, **앞의 가짜 헤더를 잘라내고 `.ts` 확장자로 저장**합니다. MP4 박스로 판별됐는데 확장자가 미디어가 아니면 `.m4s`로 바꿉니다.

### 3. 저장 방식

| 응답 종류 | 저장 방식 | 파일명 예시 |
|---|---|---|
| HLS/DASH 세그먼트, 매니페스트 (200 등) | 받은 순서대로 6자리 순번을 붙여 저장 | `000001_segment_0129.ts` |
| Range 응답 (206 + `Content-Range`) | 각 조각을 원래 바이트 오프셋 위치에 써서 한 파일로 재조립 | `RANGE_video.mp4` |

- 모든 저장 기록은 `index.csv`에 남습니다: `seq, time, status, content_type, bytes, content_range, url, saved_as`
- 다시 실행하면 `index.csv`의 줄 수를 읽어 순번을 이어서 매기므로, 기존 파일을 덮어쓰지 않습니다.
- gzip/br 등 `Content-Encoding`은 mitmproxy가 자동으로 풀어 줍니다.

### 4. 캐시 우회

브라우저가 보내는 `If-None-Match`, `If-Modified-Since` 헤더를 요청에서 지웁니다. 서버가 `304 Not Modified`(본문 없음) 대신 `200`으로 전체 데이터를 보내게 해서, 이미 본 영상도 다시 저장할 수 있습니다.

---

## 세그먼트 합치기

### PowerShell (저장소 포함 스크립트)

세그먼트가 저장된 호스트 폴더(`captured\<호스트명>\`)에서 PowerShell을 열고 `3_ts 저장된 폴더에서 파워쉘 실행.txt`의 내용을 붙여 넣습니다.

```powershell
$out = [System.IO.File]::Create("merged_video.ts")
Get-ChildItem *_segment_*.ts | ForEach-Object { if ($_.BaseName -match 'segment_(\d+)') { [PSCustomObject]@{ Seg = [int]$matches[1]; File = $_.FullName } } } | Sort-Object Seg | Group-Object Seg | ForEach-Object { $in = [System.IO.File]::OpenRead($_.Group[0].File); $in.CopyTo($out); $in.Close() }
$out.Close()
```

- 캡처 순번이 아니라 **URL의 세그먼트 번호(`segment_NNNN`)** 기준으로 정렬합니다. 탐색(seek)으로 순서가 뒤섞여도 올바른 순서로 합쳐집니다.
- 같은 번호가 여러 번 받아졌으면(`Group-Object`) 첫 번째 파일 하나만 씁니다.
- 파일명 규칙이 다른 사이트는 `*_segment_*.ts`와 `segment_(\d+)` 부분을 맞게 고쳐야 합니다.

### ffmpeg로 MP4 변환 (선택)

```bash
ffmpeg -i merged_video.ts -c copy merged_video.mp4
```

DASH(`.m4s`)는 초기화 세그먼트(`init.mp4` 등)를 맨 앞에 두고 이어 붙여야 재생됩니다. 영상·음성 트랙이 따로 오면 각각 합친 뒤 ffmpeg로 묶습니다.

---

## 문제 해결

| 증상 | 확인할 것 |
|---|---|
| 아무것도 저장되지 않음 | 브라우저가 실제로 프록시를 쓰는지(mitmdump 창에 요청 로그가 찍히는지), 인증서가 설치됐는지 확인 |
| 인증서 오류 화면 | CA 인증서를 "신뢰할 수 있는 루트 인증 기관"에 넣었는지, Firefox는 자체 저장소에 넣었는지 확인 |
| `[skip] 미디어로 판별 안 됨` 로그 | `url_pattern`으로 세그먼트 URL 규칙을 직접 지정 |
| `[skip] 304 캐시 응답` 로그, 또는 이미 본 영상이 저장 안 됨 | 브라우저가 로컬 캐시에서 바로 꺼내 쓰면 요청 자체가 프록시를 지나지 않습니다. 브라우저 캐시를 비우고 다시 재생 |
| 너무 많은 파일이 저장됨 | `host_filter`로 CDN 도메인만 지정 |
| Brave에서 캡처 안 됨 | Brave Shields가 동영상 요청을 막는지 확인. Tor 비공개 창은 프록시를 타지 않으므로 일반 창에서 재생 |
| 합친 파일이 재생 안 됨 | 세그먼트가 암호화돼 있는지 확인. 매니페스트에 `#EXT-X-KEY`(HLS) 또는 `ContentProtection`(DASH)이 있으면 세그먼트가 암호화된 상태로 저장된 것입니다 |

---

## 요구 사항

- Python 3.10 이상 (작성자 환경: 3.14)
- mitmproxy
- (선택) ffmpeg
