# 01. URL 입력과 직렬화 — `김면수`가 0과 1이 되는 여정

> 사용자가 주소창에 `https://example.com/users/김면수?role=관리자` 를 친 순간,
> 브라우저는 **텍스트 → Unicode codepoint → UTF-8 byte → percent-encoding → HTTP 메시지 → TCP segment** 의 5단계 변환을 수행한다.
> 서버는 정확히 역순으로 복원한다. **한 단계라도 charset이 어긋나면 그 지점이 모지바케의 원인.**

---

## 핵심 한 줄 — 왜 한글을 URL에 못 넣는가

> **HTTP와 URL은 1990년대 초 ASCII-only world에서 태어났다. 그 위에 비-ASCII(한글, 이모지, 라틴 확장)를 얹기 위한 transport-encoding이 percent-encoding이다.**

HTTP는 본질적으로 ASCII protocol이다. RFC 9112가 정의하는 request-line, header field-name, field-value 모두 ASCII printable(0x21~0x7E)을 기반으로 한다. HTTP/2가 binary framing으로 갔어도 header name·value는 여전히 ASCII 기반. 이유는 단순하다 — **모든 7-bit transport, OS, 도구에서 안전하게 흐르기 위해서.** telnet으로 80 포트에 붙어 손으로 GET 칠 수 있어야 한다는 1990년대 결정이 30년이 지난 지금도 invariant로 살아 있다.

URL 자체의 grammar도 ASCII subset이다. RFC 3986 §2가 모든 octet을 `unreserved`(A-Za-z0-9-._~), `reserved`(:/?#[]@!$&'()*+,;=), 그 외로 나누고, **그 외 모든 byte는 무조건 percent-encoding** 으로 ASCII-safe하게 변환하라고 못박았다. 한글(EA B9 80 등), 이모지, 라틴 확장 모두 여기에 포함.

비유: Base64가 binary를 email-safe ASCII로 옮기는 transport-encoding이라면, **percent-encoding은 임의 byte를 URL-safe ASCII로 옮기는 transport-encoding.** 둘은 같은 발상의 다른 구현. URL이 ASCII-only인 덕분에 HTML href, email body, Slack 메시지, 로그 파일, shell command 어디에 박혀도 깨지지 않는다 — wire 너머의 가치.

**왜 처음부터 UTF-8 직접 전송 안 했나** — 세 가지 이유가 맞물려 있다. ① 기업 NAT·방화벽·WAF·CDN edge가 30년 묵은 "ASCII만 받음"으로 hard-code된 사례가 많아 invariant를 깨면 deployment 깨짐. ② URL은 HTTP 밖으로 새어 나가 HTML, email, Slack, 로그, shell command line에 박힌다 — UTF-8 직접 전송이면 일부 환경(구식 mail client, 7-bit transport)에서 깨짐. ③ percent-encoding은 transport-encoding 표준 패턴(Base64, Quoted-Printable과 같은 발상). 30년 검증된 패턴을 굳이 새로 안 만들었다.

---

## 직관 — ASCII protocol과 percent-encoding

HTTP wire에는 ASCII printable 문자만 흐른다. 그런데 사용자는 한글을 친다. 그 간극을 메우는 게 두 종류 인코딩이다.

- **path/query** → percent-encoding (RFC 3986). UTF-8 byte를 `%HH` 형식으로 escape.
- **hostname** → punycode (RFC 3492). 한글 도메인을 ASCII 라벨로 변환, prefix `xn--`.

같은 URL 안에 두 인코딩이 공존한다. 컴포넌트마다 규칙이 다르다는 게 핵심.

```
입력:  https://한국.kr/users/김면수?role=관리자
         ──┬─── ──┬───── ────┬───── ────┬─────
         scheme  hostname   path        query
                  │           │           │
                  │           │           └─ percent-encoding (UTF-8 byte → %HH)
                  │           └─ percent-encoding (UTF-8 byte → %HH)
                  └─ punycode (Bootstring, RFC 3492)
                     한국 → xn--3e0b707e

최종 wire:
  GET /users/%EA%B9%80%EB%A9%B4%EC%88%98?role=%EA%B4%80%EB%A6%AC%EC%9E%90 HTTP/1.1
  Host: xn--3e0b707e.kr
```

**왜 hostname만 다른가** — DNS는 1983년 설계되어 ASCII case-insensitive label(63 byte)만 다룬다. IDN을 위해 RFC 3490(IDNA)이 Punycode로 ASCII-Compatible Encoding을 정의. 반면 URL의 path/query는 RFC 1738/3986이 percent-encoding을 정의 — DNS와 별개 규칙.

**운영 함정**: `URLEncoder.encode("한국.kr")`을 hostname에 쓰면 `%ED%95%9C%EA%B5%AD.kr` 이 되어 DNS lookup이 NXDOMAIN으로 실패. 올바른 코드는 `IDN.toASCII("한국.kr")` → `xn--3e0b707e.kr`.

---

## 단계별 변환 (한글 → byte → URL)

논리적 문자열 "김면수"가 wire에 도달하는 5단계.

```
[사용자 입력]   "김면수"
       │
       │ ① 텍스트 → Unicode codepoint
       │    (OS 입력기 / 브라우저, Unicode 표준)
       ▼
[Unicode]      U+AE40 U+BA74 U+C218
                 (한글 음절 영역 U+AC00~U+D7A3, 3 codepoint)
       │
       │ ② UTF-8 encoding (codepoint → 1~4 byte, RFC 3629)
       │    한글 음절 = U+0800~U+FFFF 범위 → 3 byte 패턴 1110xxxx 10xxxxxx 10xxxxxx
       │    (bitwise AND/OR/Shift로 codepoint를 4-6-6 bit로 잘라 슬롯에 채움)
       ▼
[UTF-8 byte]   0xEA 0xB9 0x80 0xEB 0xA9 0xB4 0xEC 0x88 0x98   (9 bytes)
                ─── 김 ───   ─── 면 ───   ─── 수 ───
       │
       │ ③ URL safety check (RFC 3986)
       │    0x80 이상 byte → unreserved 아님 → percent-encoding 필요
       │    각 byte → "%" + 2-digit uppercase hex
       ▼
[percent-enc]  %EA%B9%80%EB%A9%B4%EC%88%98   (27 ASCII chars)
       │
       │ ④ HTTP message 조립 (RFC 9112)
       │    method SP request-target SP version CRLF
       │    field-name ":" SP field-value CRLF
       │    CRLF (header 끝, body 시작)
       ▼
[HTTP request] GET /users/%EA%B9%80%EB%A9%B4%EC%88%98 HTTP/1.1\r\n
               Host: example.com\r\n
               \r\n
       │
       │ ⑤ byte stream → TCP segment → IP packet
       │    OS socket layer가 byte stream을 그대로 전송 (ASCII이므로 추가 변환 없음)
       ▼
[wire bytes]   47 45 54 20 2F 75 73 65 72 73 2F 25 45 41 ...
               G  E  T  SP /  u  s  e  r  s  /  %  E  A  ...
```

서버는 정확히 역순. percent-decode → UTF-8 decode → String 객체로 복원. 각 단계의 책임 주체가 다르고, 어느 한 곳에서 charset 가정이 어긋나면 즉시 모지바케.

---

## ASCII-only 케이스 대조

영문 URL은 ①~③ 단계를 **우회**한다. 변환이라는 개념 자체가 등장하지 않는다.

```
[사용자 입력]   "www.google.com"
       │
       │ (모든 글자가 unreserved → 변환 없음)
       │ (ASCII codepoint → ASCII byte는 1:1 무손실 사상)
       ▼
[HTTP request] GET / HTTP/1.1\r\n
               Host: www.google.com\r\n
               \r\n
       │
       ▼
[wire bytes]   47 45 54 20 2F 20 48 54 54 50 ...
               G  E  T  SP /  SP H  T  T  P  ...
```

영어권 개발자는 charset/encoding을 평생 안 마주칠 수 있다 — "그냥 string 처리하면 되잖아". 한국·일본·중국 환경에서는 이 변환을 **하루에 100번 마주친다.** 모든 모지바케의 뿌리가 여기서 시작된다.

---

## 책임 계층 (브라우저 = encode / 서버 = decode)

| 단계 | 클라이언트 책임 | 서버 책임 | 실패 시 증상 |
|---|---|---|---|
| ① 텍스트 → codepoint | OS IME, 브라우저 | (해당 없음) | 입력 자체 깨짐 (드묾) |
| ② codepoint → UTF-8 byte | 브라우저 URL 모듈 | (해당 없음) | 깨진 byte 시퀀스 |
| ③ byte → percent-encoding | 브라우저, `encodeURIComponent`/`URI` | percent-decoding (Tomcat) | URL 파싱 실패, double-decode |
| ④ HTTP 메시지 조립 | 브라우저 HTTP stack | HTTP parser (Tomcat/Nginx) | request-line 깨짐, Host 누락 |
| ⑤ byte → TCP segment | OS socket layer | OS socket layer | (ASCII, 변환 없음) |
| **charset 결정** | 브라우저 자동 (UTF-8) | **Tomcat `URIEncoding=UTF-8`** (path/query) + **`CharacterEncodingFilter`** (POST body) | 모지바케 |

**중요한 책임 분리**: GET path/query는 request-line 단계에서 Tomcat이 먼저 파싱한다 → Filter 도달 전 결정. 그래서 `CharacterEncodingFilter`로는 GET을 못 고친다. URIEncoding이 별도 영역.

**브라우저의 자동 encoding** — 사용자가 주소창에 한글을 쳐도, fetch/XHR로 한글 URL을 호출해도 브라우저가 자동으로 percent-encoding을 적용한다. JavaScript에서 명시적으로 쓸 때는 두 API 구분 필수: `encodeURI(url)` 는 전체 URL용으로 reserved(`:/?#[]@!$&'()*+,;=`)는 보존하고, `encodeURIComponent(str)` 는 컴포넌트 값용으로 reserved도 모두 escape. query value 안의 `&` 가 다음 key 시작으로 오인되는 사고는 `encodeURIComponent` 를 안 써서 생긴다.

---

## URL 구조 — 5+1 컴포넌트

RFC 3986이 정의하는 URL의 모든 부분.

```
  https://user:pass@example.com:8080/users/김면수?role=관리자#section
  ─────   ──┬─────── ────┬───── ──┬─ ────┬─────  ───┬─────  ───┬───
  scheme  userinfo  hostname   port  path        query       fragment
  ─────   ─────────────────────────  ────         ─────       ────────
                  authority           path        query       fragment
                  ────────────────────────────────────────
                  서버에 전송됨 (request-line + Host header)
                                                              ─────────
                                                              **클라이언트만** — 서버에 안 감
```

**fragment(`#section`)가 서버에 안 가는 이유**: fragment는 "이 페이지의 어느 위치"를 가리키는 클라이언트-side anchor. 브라우저가 페이지 받은 뒤 스크롤·JS 라우팅에 사용. wire에 안 실린다. SPA 라우터가 `#/users/123` 패턴을 쓰는 게 이 덕분 — 서버는 root path만 받고, 클라이언트 JS가 fragment로 라우팅. HTML5 `pushState` 등장 이후엔 fragment 없이도 가능해졌지만, fragment의 "서버 미전송" 속성은 그대로.

**userinfo(`user:pass@`)**: HTTP/1.1 시대 Basic Auth용. 현재는 거의 사용 안 함(평문 노출, log leak 위험). 최신 브라우저는 URL bar에서 자동으로 strip하고 별도 prompt로 변환.

---

## HTTP 메시지 직렬화 — request-line + headers + CRLF + body

percent-encoding이 끝난 URL이 실제 HTTP 메시지에 박히는 형식.

```
[request-line]   GET /users/%EA%B9%80%EB%A9%B4%EC%88%98?role=admin HTTP/1.1\r\n
                 ─┬─ ─────────────────┬────────────────────────── ──┬─── ───
                 method  request-target (path + ? + query)        version  CRLF

[header lines]   Host: example.com\r\n
                 User-Agent: Mozilla/5.0\r\n
                 Accept: text/html,application/xhtml+xml\r\n
                 Accept-Language: ko-KR,ko;q=0.9\r\n
                 Cookie: SESSIONID=abc123\r\n
                 ─────────────────────────────
                 field-name ":" SP field-value CRLF (RFC 9112)

[blank line]     \r\n                       ← header 끝 + body 시작 신호

[body (optional)]  (GET이라 비어있음 — POST/PUT이면 여기에 body 바이트)
```

**CRLF(`\r\n`)의 역사**: 1960년대 ASCII 텔레타이프에서 캐리지 리턴(`\r`, 커서 줄 처음으로) + 라인 피드(`\n`, 종이 한 줄 위로) 두 동작이 물리적으로 분리. SMTP·FTP·HTTP 모든 text 프로토콜이 이걸 그대로 박았다. RFC 9112는 `\n` 단독도 관대하게 받으라 권고하지만, **CRLF injection** 보안 함정 때문에 헤더 값에 `\r\n` 들어가면 가짜 헤더 주입(예: `Set-Cookie: foo\r\nLocation: http://evil.com`) 공격 가능. 모든 헤더 값은 `\r\n` 필터링 필수.

**Host 헤더가 왜 필수인가**: HTTP/1.1부터 virtual host 분기 가능 — 같은 IP가 여러 도메인을 호스팅. request-line의 path만으로는 어느 vhost인지 모름. Host 헤더 누락 시 400 Bad Request. HTTP/2에서는 `:authority` pseudo-header가 동일 역할.

---

## 5계층 인코딩 — 책임 분리의 본질

| 계층 | 책임 | 결정 시점 | 잘못되면 |
|---|---|---|---|
| **① text → codepoint** | OS IME, Unicode 표준 | 사용자 입력 시 | (드묾, IME 버그) |
| **② codepoint → UTF-8 byte** | 브라우저, JVM `String.getBytes(UTF-8)` | encode 시점 | 깨진 byte sequence |
| **③ byte → percent-encoding** | 브라우저 URL canonicalizer, `URLEncoder` | URL 빌드 시 | path/query 깨짐 |
| **④ HTTP 메시지 조립** | 브라우저 net stack, Tomcat HTTP parser | 송수신 직전 | request-line 깨짐, Host 누락 |
| **⑤ byte → TCP segment** | OS kernel socket layer | wire 직전 | (변환 없음, ASCII이므로 무손실) |

**책임 분리의 본질** — 각 계층이 자신의 charset 계약을 명시해야 한다. 한 계층의 가정이 어긋나면 그 지점에서 모지바케.

```
Spring Boot 환경의 charset 계약 (3 지점):

  ① Tomcat URIEncoding=UTF-8          → GET path/query decode
  ② CharacterEncodingFilter UTF-8     → POST body decode (forceEncoding=true)
  ③ JDBC characterEncoding=UTF-8      → DB 송수신
       + DB 테이블 charset utf8mb4    → 저장
       + Content-Type charset=UTF-8   → 응답
```

이 3+ 지점 중 한 곳이라도 안 맞으면 그 경계에서 깨진다. **"raw byte ↔ 의미 있는 text 변환은 charset 계약이 필요하다"** 가 모지바케 제거의 유일한 원칙.

---

## POST body — 3가지 Content-Type 비교

| Content-Type | 형식 | charset 결정 | 용도 |
|---|---|---|---|
| `application/x-www-form-urlencoded` | `key=value&key=value` (percent-encoded) | HTML 페이지 `<meta charset>` (사실상 브라우저 합의) | 단순 form |
| `multipart/form-data` | boundary로 분할, 각 part에 헤더 | 각 part가 `Content-Type: text/plain; charset=UTF-8` 명시 가능 | 파일 업로드 |
| `application/json` | UTF-8 강제 (RFC 8259) | 모호성 없음 | API |

**form-urlencoded의 charset 모호성**: RFC가 명확하지 않고 페이지 charset을 따른다. 페이지가 EUC-KR이면 `김` 이 `%B1%E8`. 운영에서 모지바케 주범 1순위. 해결: `CharacterEncodingFilter(encoding="UTF-8", forceEncoding=true)` + 페이지 `<meta charset="UTF-8">` 통일.

**JSON이 단순한 이유**: RFC 8259가 UTF-8을 강제. charset 협상 불필요. Protocol Buffers/Avro도 같은 발상 — schema의 string은 UTF-8 fixed. **charset 모호성 제거가 binary protocol의 핵심 가치.**

---

## URL 길이 제한 — 무한이 아닌 이유

| 구성요소 | 제한 | 비고 |
|---|---|---|
| RFC | 무제한 | RFC 9110 §4.1: "no predefined limit" |
| Nginx | 8KB (default) | `large_client_header_buffers` |
| Tomcat | 8KB (default) | `maxHttpHeaderSize` |
| AWS ALB | 16KB | HTTP request line |
| CloudFront | 8KB | URL + query |
| IE | 2,083 chars | 1996년 임의 결정, 레거시 |

**한글 길이는 항상 percent-encoded byte 기준**: 한글 1자 = UTF-8 3 byte = percent-encoded 9 chars. 한글 2000자 query → 18,000 byte → Tomcat 8KB limit 초과 → 414 Request-URI Too Long.

**해결 패턴**:
- GET → POST 전환 (ids를 body로)
- ID 압축 (range encoding: `1-100,200-300`)
- `maxHttpHeaderSize=16KB` 증가 (메모리 비용, DoS 위험 약간)

**RFC가 무제한인데 구현체가 제한하는 이유**: HTTP 파서는 request-line·header 전체를 메모리 buffer에 받아 파싱한다. buffer 크기를 fix해두지 않으면 거대한 URL 한 번에 메모리 폭발 → 가장 단순한 DoS. 그래서 모든 구현체가 보수적으로 8KB 안팎의 limit을 둔다. IE의 2,083은 1996년 IE 팀의 임의 결정이 표준처럼 굳어진 케이스.

---

## 운영 시나리오

### 시나리오 A — 검색 결과의 한글 keyword가 `???` 로 출력

```
증상:  GET /search?q=김면수 → 결과 페이지에 "??? 검색 결과"
       DB에는 "김면수" 가 정상 저장돼 있음

추적:
  1. curl -v → 브라우저는 정상: GET /search?q=%EA%B9%80%EB%A9%B4%EC%88%98 ✓
  2. Tomcat 로그(DEBUG): parameter q = "ê¹€ë©´ìˆ˜"   ← 이미 깨짐
  3. → Tomcat URIEncoding 미설정. UTF-8 byte를 ISO-8859-1로 decode.

해결:  server.tomcat.uri-encoding=UTF-8  (Tomcat 8 이후 기본값이지만 명시 권장)
```

### 시나리오 B — POST는 정상인데 GET 쿼리만 깨짐

```
원인:
  POST body는 CharacterEncodingFilter(forceEncoding=true) 가 처리.
  GET query는 request-line 단계 → Filter 도달 전 Tomcat이 이미 파싱.
  → Tomcat URIEncoding 이 GET query charset을 결정한다.

해결:
  URIEncoding=UTF-8 + useBodyEncodingForURI=false  (기본값)
  Spring Boot 1.x 이후 자동 설정.
```

### 시나리오 C — WAF 우회 공격 (double-encoding)

```
공격:  GET /api?path=%252E%252E%252Fetc%252Fpasswd

WAF 1차 decode:
  path=%2E%2E%2Fetc%2Fpasswd  ← "../" 패턴 없음 → 통과

App 서버가 2차 decode:
  path=../etc/passwd  ← path traversal 성공

방어:
  - WAF가 recursive decode 후 normalize → 다시 검증
  - App에서 canonical path 비교 (절대 경로 화이트리스트)
  - 동일 normalization 규칙을 WAF/proxy/app 전 계층이 공유
```

**Path normalization의 일관성**: 같은 경로가 컴포넌트마다 다르게 normalize 되면 우회 가능. `/a%2F./b/../c` 에서 `%2F` 를 `/` 와 동일하게 볼지 다르게 볼지, Nginx와 Tomcat이 다르면 그 차이가 CVE가 된다. HTTP Request Smuggling(Nginx vs backend의 Content-Length/Transfer-Encoding 해석 차이)도 같은 패턴. **규칙**: WAF·proxy·app 전 계층이 동일 normalization 알고리즘을 써야 안전.

### 시나리오 D — Slack에 한글 URL 붙여넣으면 `%EA%B9%80...` 으로 변환

```
관찰:
  사용자 입력:  https://example.com/users/김면수
  전송 후:      https://example.com/users/%EA%B9%80%EB%A9%B4%EC%88%98

이유:
  Slack 클라이언트가 URL detection 후 RFC 3987(IRI) → RFC 3986(URI) 변환 적용.
  - hostname: IDN punycode (라틴이면 그대로)
  - path/query: UTF-8 byte → percent-encoding
  변환된 ASCII-safe URL을 message 본문에 저장.

왜:
  메시지가 fan-out되며 다양한 OS/locale/client(web, iOS, Android, desktop) 거침.
  raw 한글 URL은 일부 환경(Android 구버전 WebView, IE 레거시)에서 깨질 위험.
  ASCII-safe URL은 어디서나 클릭 가능 보장.

같은 패턴:
  GitHub README markdown link, Notion, Confluence, Gmail link detection 모두 동일.
```

---

## 서버 측 역직렬화 — byte가 다시 String이 되기까지

브라우저의 변환을 정확히 역순으로 풀어야 한다.

```
[wire bytes 수신]   47 45 54 20 2F 75 73 65 72 73 2F 25 45 41 ...
       │
       │ ⑥' TCP reassembly (커널 socket buffer가 segment 합침)
       ▼
[byte stream]   GET /users/%EA%B9%80%EB%A9%B4%EC%88%98 HTTP/1.1\r\n...
       │
       │ ⑤'/④' HTTP parser (Tomcat Coyote 또는 Nginx)
       │        request-line / header / body 분리, CRLF 검출
       ▼
[parsed request]   method=GET, target=/users/%EA%B9%80%EB%A9%B4%EC%88%98
       │
       │ ③' percent-decoding (Tomcat이 수행)
       │     "%EA" → 0xEA, "%B9" → 0xB9, "%80" → 0x80, ...
       ▼
[UTF-8 byte]   EA B9 80 EB A9 B4 EC 88 98
       │
       │ ②' UTF-8 → codepoint
       │     Tomcat URIEncoding 설정값으로 decode (UTF-8/ISO-8859-1)
       │     → 이 단계에서 가장 자주 모지바케 발생!
       ▼
[Unicode]   U+AE40 U+BA74 U+C218
       │
       │ ①' codepoint → Java String 객체
       ▼
   "김면수"  (Spring @PathVariable String name으로 주입)
```

**핵심 책임 분리**:
- `request.getParameter("q")` → decode된 String 반환 (Tomcat URIEncoding 적용 후)
- `request.getQueryString()` → raw 그대로 (decode 안 됨, 직접 처리)
- `CharacterEncodingFilter` → POST body만 처리, GET query는 영향 없음
- JDBC `characterEncoding=UTF-8` → DB 송수신 charset (별도 영역)

이 4 지점이 모두 UTF-8로 통일되어야 end-to-end 무손실.

---

## 보안 — 인코딩 우회 공격 정리

| 공격 | 메커니즘 | 방어 |
|---|---|---|
| **Double-encoding bypass** | `%252E` 처럼 `%` 자체를 encode → WAF 1차 decode 시 패턴 안 보임 → App 2차 decode 시 활성화 | recursive decode 후 normalize → 검증 |
| **Path traversal** | `../` 또는 `%2E%2E%2F` 로 디렉터리 상위 이동 | canonical path 비교, whitelist 기반 접근 |
| **IDN homograph** | 라틴 `apple` vs 키릴 `аррlе` 시각적 동일 | DNS 등록 기관의 script 혼용 차단, 브라우저 punycode 강제 표시 |
| **CRLF injection** | header 값에 `\r\n` 삽입 → 가짜 header 주입 | header 값 sanitize, `\r\n` 필터링 |
| **HTTP Request Smuggling** | Nginx와 backend의 `Content-Length`/`Transfer-Encoding` 해석 차이 | 동일 normalization 규칙, 한 쪽에서 거부 |

대표 CVE: Struts2 OGNL injection(CVE-2017-5638), Log4Shell(CVE-2021-44228, JNDI lookup도 인코딩 우회 가능). 공통 패턴은 **"두 계층의 파싱 규칙이 다르면 그 틈이 공격 surface"**.

---

## 역사 한 문단

HTTP/0.9(1991, Tim Berners-Lee, CERN)는 `GET /index.html\r\n` 한 줄짜리 ASCII 프로토콜로 태어났다. 텔레타이프·SMTP·NNTP 같은 7-bit 환경에서 안전하려고 ASCII-only로 못박았고, 1994년 RFC 1738이 percent-encoding을 도입해 임의 byte 전송을 허용. 1996년 RFC 1945(HTTP/1.0), 1999년 RFC 2616(HTTP/1.1, 후속 RFC 7230~7235 → 9110~9112), 2015년 HTTP/2(binary framing + HPACK, RFC 7540 → 9113), 2022년 HTTP/3(QUIC, RFC 9114)까지 30년간 binary로 진화했지만, **request-line의 path/query, header field name·value의 ASCII 기반은 한 번도 깨지지 않았다.** Punycode(RFC 3492, 2003 IDNA → 2010 IDNA2008)도 같은 이유 — DNS의 ASCII case-insensitive 보장을 지키기 위해. 2022년 JDK 18(JEP 400)이 `file.encoding` 기본값을 UTF-8로 고정한 게 자바 진영의 마지막 청산. **30년의 결론: charset 계약을 명시하지 않으면 어디선가 깨진다.**

---

## 모지바케 7대 패턴 (진단표)

| 증상 | 원인 | 해결 |
|---|---|---|
| URL 한글이 `???` | Tomcat URIEncoding 미설정 | `server.tomcat.uri-encoding=UTF-8` |
| POST body 한글이 `?` | CharacterEncodingFilter 없음 | Spring Boot 기본 활성화 |
| DB 저장 한글 깨짐 | JDBC URL `characterEncoding` 누락 | `?useUnicode=true&characterEncoding=UTF-8` |
| DB select 한글 깨짐 | 테이블 charset latin1 | `ALTER TABLE ... CONVERT TO CHARACTER SET utf8mb4` |
| 응답 body 정상인데 브라우저가 깨뜨림 | `Content-Type` 에 charset 누락 | `Content-Type: text/html; charset=UTF-8` |
| `ê¹€ë©´ìˆ˜` 패턴 | UTF-8을 ISO-8859-1로 decode | 어느 단계에서 잘못 decode 추적 |
| `?` 또는 `□` 한 글자 | encode 단계에서 unknown codepoint | charset upgrade (utf8 → utf8mb4) |

---

## 트레이드오프 — 인코딩 선택

| 선택지 | 장점 | 단점 | 언제 쓰나 |
|---|---|---|---|
| **percent-encoding (path/query)** | 모든 HTTP middlebox·proxy·log 안전. 30년 검증된 invariant. | 한글 1자 = 9 char로 폭증. 사람 눈에 흉함. | URL의 모든 컴포넌트(hostname 제외) |
| **punycode (hostname)** | DNS와 호환. ASCII case-insensitive 유지. | 보안 함정(homograph). 사용자 가독성 0. | IDN 도메인 |
| **raw UTF-8 byte 전송** | 길이 1/3로 절감. 사람이 읽음. | middlebox/WAF/log에서 깨짐 위험. RFC 위반. | 권장 안 함 (IRI 표시용으로만) |
| **URLEncoder (form data)** | HTML form 표준 (`+` for space). | path에 쓰면 잘못된 URL. | `application/x-www-form-urlencoded` body만 |
| **UriComponentsBuilder (RFC 3986)** | path/query 규칙 정확히 따름. | 명시적 컴포넌트 분리 필요. | Spring 환경의 URL 빌드 |

---

## HTTP 버전별 차이 (한 줄 요약)

- **HTTP/1.1**: text-based, request-line + headers + CRLF + body. URL은 path/query에 그대로 박힘.
- **HTTP/2**: binary framing + HPACK 헤더 압축. `:path` pseudo-header 값은 여전히 percent-encoded ASCII. HPACK은 그 ASCII 문자열을 Huffman/table indexing으로 짧게 표현할 뿐 — URL 인코딩 규칙은 동일.
- **HTTP/3**: QUIC(UDP) 위 + QPACK. HPACK과 동일 원칙, packet loss 대응만 다름.

**핵심**: percent-encoding은 URL 레이어(RFC 3986) 규칙. HTTP 버전과 무관. HPACK은 그 위의 메시지 압축 레이어.

---

## 측정·진단 (핵심 도구만)

```bash
# wire byte 검증
$ curl -v "https://example.com/users/김면수"
> GET /users/%EA%B9%80%EB%A9%B4%EC%88%98 HTTP/1.1

# UTF-8 byte 확인
$ echo -n "김면수" | xxd
00000000: eab9 80eb a9b4 ec88 98

# 모지바케 재현 (UTF-8 byte → ISO-8859-1 decode)
$ printf '\xea\xb9\x80\xeb\xa9\xb4\xec\x88\x98' | iconv -f ISO-8859-1 -t UTF-8
ê¹ë©´ìˆ                # ← 클래식 모지바케

# Java 검증
String encoded = URLEncoder.encode("김면수", StandardCharsets.UTF_8);
// %EA%B9%80%EB%A9%B4%EC%88%98

byte[] bytes = "김면수".getBytes(StandardCharsets.UTF_8);
String mojibake = new String(bytes, StandardCharsets.ISO_8859_1);  // ê¹€ë©´ìˆ˜
byte[] recovered = mojibake.getBytes(StandardCharsets.ISO_8859_1);
String original = new String(recovered, StandardCharsets.UTF_8);   // 김면수 복구
```

HTTPS는 `SSLKEYLOGFILE` + Wireshark로 TLS decode. HTTP/2 binary frame은 raw byte라 Wireshark 필수.

---

## 꼬리질문

1. **"`김` 한 글자가 `%EA%B9%80` 으로 변환되는 비트 레벨 과정은?"**
   → 코드포인트 U+AE40 (U+0800~U+FFFF 범위) → UTF-8 3 byte 패턴 `1110xxxx 10xxxxxx 10xxxxxx` → 16-bit 값을 4-6-6 bit로 잘라 슬롯에 채움 → `0xEA 0xB9 0x80` → 각 byte를 `%HH` 로 escape.

2. **"왜 굳이 percent-encoding 인가? UTF-8 byte 그대로 보내면 안 되나?"**
   → RFC 3986이 URL을 ASCII printable로 정의. 30년 묵은 middlebox·WAF·log analyzer 호환성. URL은 HTTP 밖(HTML href, email, Slack, log)으로도 새어 나가야 하고, 그 모든 환경에서 깨지지 않으려면 ASCII-only invariant 필수.

3. **"GET path는 한글이 깨지는데 POST body는 정상. 왜?"**
   → POST body는 `CharacterEncodingFilter(forceEncoding=true)` 가 처리. GET query는 request-line 단계에서 Tomcat이 먼저 파싱 → Filter 도달 전 결정. Tomcat `URIEncoding=UTF-8` 이 별도로 GET charset을 결정한다.

4. **"같은 URL인데 `URLEncoder.encode` 와 브라우저 결과가 다른 경우?"**
   → `URLEncoder` 는 HTML form용 (`+` = space). 브라우저 path 인코딩은 RFC 3986 (`%20` = space). path에 `URLEncoder` 쓰면 `+` 가 그대로 박혀 잘못된 URL. 권장: Java 11+ `URI` constructor 또는 Spring `UriComponentsBuilder.fromUriString(...).encode()`.

5. **"한글 검색이 random하게 모지바케. 진단 절차는?"**
   → ① tcpdump로 wire byte 확인 (브라우저는 정상 보내는지). ② Tomcat URIEncoding, CharacterEncodingFilter 확인. ③ `-Dfile.encoding=UTF-8` 또는 JDK 18+ (JEP 400) 확인. ④ HikariCP connection별 charset — JDBC URL의 `characterEncoding` 누락 시 connection마다 다를 수 있음. 90%는 ④번.

---

## 학습 체크리스트 (백지에서)

- [ ] "왜 한글을 URL에 그대로 못 넣는가" 를 1분 안에 설명할 수 있다 — ASCII protocol 30년 invariant, middlebox 호환성, URL이 HTTP 밖으로 새어 나가는 전송 안전.
- [ ] 한글 → percent-encoding 5단계(text → codepoint → UTF-8 byte → percent → HTTP 메시지) 를 종이에 그릴 수 있다.
- [ ] hostname(punycode)과 path/query(percent-encoding)가 **다른 인코딩** 이라는 걸 알고, `URLEncoder.encode("한국.kr")` 가 왜 NXDOMAIN을 일으키는지 설명할 수 있다.
- [ ] Tomcat `URIEncoding`(GET path/query) vs `CharacterEncodingFilter`(POST body) vs JDBC `characterEncoding`(DB) 3 지점의 책임 분리를 설명할 수 있다.
- [ ] 모지바케 7대 패턴 진단표를 보고 각 증상의 원인 계층(어디서 charset이 어긋났는지)을 짚을 수 있다.
- [ ] Double-encoding bypass와 CRLF injection의 메커니즘 + 방어 패턴(recursive decode + normalize, header sanitize)을 설명할 수 있다.
- [ ] HTTP 메시지 레이아웃(request-line + headers + CRLF blank line + body)을 byte 단위로 그릴 수 있다.

---

## 더 깊이

- byte 레벨 풀버전(ASCII/Unicode/UTF-8 인코딩 알고리즘, codepoint를 4-6-6 bit로 슬롯에 채우는 C 코드 수준 비트 마스크/시프트, invalid stream 처리, overlong 보안)은 git history `7e4a6c8` commit에 보존.
- 운영 시나리오 풀버전(Content-Disposition RFC 5987, MySQL utf8mb3 vs utf8mb4 이모지 함정, IDN homograph 다층 방어, Slack/Googlebot URL normalization, Cloudflare punycode 강제 표시 등)도 동일 commit.
- 면접 시뮬레이션 3단 트리 풀버전(Q1~Q8 각각의 🪝/🪝🪝 후속 질문)도 동일 commit.

---

## 다음 단계

- → [02. DNS와 라우팅](./02-dns-and-routing.md): URL의 host 부분이 어떻게 IP 주소로 변환되는가
- → [03. OSI 7계층 + TCP/TLS](./03-osi-7-layers-and-tcp-tls.md): HTTP 메시지가 각 계층을 통과하며 헤더를 입는 과정
- → [06. Tomcat 내부](./06-tomcat-internals.md): byte stream이 HttpServletRequest로 역직렬화 되는 풀버전

## 참고

- RFC 3986 (URI Syntax), RFC 3987 (IRI), RFC 3492 (Punycode), RFC 5890~5894 (IDNA 2008)
- RFC 3629 (UTF-8), RFC 9110~9114 (HTTP Semantics/1.1/2/3), RFC 7541 (HPACK)
- WHATWG URL Standard, JEP 400 (UTF-8 by Default)
- OWASP Path Traversal, HTTP/2 HPACK Visualizer (hpack.surge.sh)
