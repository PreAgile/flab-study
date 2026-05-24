# 01. URL 입력과 직렬화 — `김면수`가 0과 1이 되는 여정

> 사용자가 주소창에 `https://example.com/users/김면수?role=관리자` 를 치고 Enter를 누른다.
> 그 순간 브라우저 내부에서는 **URL 파싱 → IDN punycode → percent-encoding → HTTP 메시지 직렬화 → UTF-8 바이트화 → TCP segment** 까지 **6단계 변환**이 일어난다.
> 서버는 정확히 역순으로 복원한다. 한 단계라도 어긋나면 즉시 **모지바케(글자 깨짐)** 발생.
> 이 챕터는 그 6단계를 한 단계도 빼놓지 않고 따라간다.

---

## 이 문서의 사용법

이 문서는 **"한글이 어떻게 바이트로 변하는가"** 라는 한 줄 질문의 답을 6단계로 풀어 쓴 것이다.

1. **0장 마인드맵** — 변환의 6단계 + 각 단계의 책임을 외운다.
2. **1~6장** — 각 단계의 본질과 내부 동작.
3. **7장 HTTP 버전별 직렬화 차이** — HTTP/1.1 vs 2 vs 3.
4. **8장 운영 시나리오** — 모지바케 7대 패턴, double-encoding 공격, URL 길이 제한.
5. **9장 측정·진단** — tcpdump, curl -v, iconv, hexdump.
6. **10장 꼬리질문**.

---

## 서장. 왜 한글을 URL에 그대로 못 넣는가 — 본질에서 시작

> "그냥 `https://example.com/users/김면수` 라고 메모리에 들고 있으면 안 되는 이유는?
>  왜 굳이 `%EA%B9%80%EB%A9%B4%EC%88%98` 라는 흉한 형태로 변환해서 보내야 하는가?"

이 질문 하나만 깊이 답해도 1~6장의 뒤따르는 디테일이 모두 자연스러워진다. 한 줄 답부터 박는다.

> **HTTP·URL은 1990년대 초 ASCII-only world에서 태어났다. 그 위에 비-ASCII (한글, 이모지, 라틴 확장) 를 얹기 위한 transport-encoding이 percent-encoding이다.**

### 서.1 HTTP는 본질적으로 ASCII protocol

HTTP의 모든 RFC는 wire format을 **US-ASCII (7-bit, 0x00~0x7F)** 로 정의한다.

```
1991  HTTP/0.9 — Tim Berners-Lee, CERN
       "GET /index.html\r\n"  ← 한 줄짜리. ASCII가 당연.

1996  HTTP/1.0 (RFC 1945)
       "request-line = Method SP Request-URI SP HTTP-Version CRLF"
       각 토큰은 ASCII printable (RFC 822/MIME 영향).

1999  HTTP/1.1 (RFC 2616 → 후속 RFC 7230~7235 → RFC 9110~9112)
       "field-name = token = 1*tchar"
       tchar = ASCII visible (0x21~0x7E) 의 부분집합.

2015  HTTP/2 (RFC 7540 → RFC 9113)
       Binary framing이지만 header field name은 여전히 ASCII lower-case 강제.

2022  HTTP/3 (RFC 9114)
       QUIC 위지만 마찬가지. ASCII 헤더.
```

**왜 ASCII로 고정했나** — 3가지 이유.

```
① 1990년대 transport 다양성
   - Telnet (line-oriented, 7-bit), SMTP (7-bit MIME), NNTP, FTP
   - 일부 게이트웨이/relay는 7-bit clean만 보장 (8-bit byte를 stripping)
   - HTTP가 이런 transport 위로 tunneling되어도 깨지지 말아야 함
   → ASCII-only이면 모든 7-bit transport에서 안전

② 모든 OS·언어 공통 기본
   - C `char` 가 ASCII로 시작 (1972, K&R)
   - PostScript, troff, awk, sed, grep — 모두 ASCII line-oriented
   - HTTP를 ASCII로 만들어두면 어떤 도구로든 디버깅 가능
   → telnet으로 80 포트에 붙어 손으로 GET 칠 수 있어야 함 (실제 가능)

③ Wire format의 디버깅 가능성 (= 운영 자산)
   - tcpdump -A 가 그대로 사람 읽음
   - access log, error log에 그대로 박혀도 깨지지 않음
   - 1990년대엔 binary protocol = 디버깅 지옥의 동의어 (그래서 SMTP, HTTP, IRC 모두 text-based)
```

이 결정의 **잔해**가 오늘도 production을 지배한다. HTTP/2가 binary framing으로 갔어도, header field name과 value는 여전히 ASCII 기반(또는 ISO-8859-1로 약간 확장). 사람이 telnet으로 손치는 시대는 끝났지만, **"ASCII이면 어디서나 안전하다"** 는 invariant는 30년이 지난 지금도 깨지지 않았다.

### 서.2 URL의 "safe character" 정의 — RFC 3986 §2

URL이라는 **문자열 자체**의 grammar도 ASCII subset으로 정의되어 있다. RFC 3986 §2가 모든 octet을 3분류한다.

```
unreserved  = ALPHA / DIGIT / "-" / "." / "_" / "~"
              ─────   ─────                     ─
              A-Za-z  0-9                        tilde

  → "어디서나, 어떤 컴포넌트에서나, escape 없이 그대로 쓸 수 있는 글자"
  → 26+26+10+4 = 66종.

reserved    = gen-delims / sub-delims

  gen-delims = ":" / "/" / "?" / "#" / "[" / "]" / "@"
                ─    ─    ─    ─    ─    ─    ─
                컴포넌트 구분 (scheme:, path/, ?query, #frag, [IPv6], user@host)

  sub-delims = "!" / "$" / "&" / "'" / "(" / ")"
             / "*" / "+" / "," / ";" / "="
                ─    ─    ─    ─    ─
                각 컴포넌트 안에서 별도 의미 (예: query의 & = 다음 key 시작)

  → "URL의 구조를 만드는 글자. 데이터로 쓰려면 반드시 percent-encode"

그 외 모든 octet (0x00~0x7F 중 위에 없는 것 + 0x80~0xFF 모두)
  → 무조건 percent-encoding 필요.
  → 여기에 한글(EA B9 80 등), 이모지, 라틴 확장, ASCII control chars 모두 포함.
```

이 grammar의 본질을 한 줄로:

> **URL은 "어떤 byte도 ASCII printable 70여 종으로 표현 가능"이라는 invariant를 지킨다. 그 invariant를 지키기 위한 escape 메커니즘이 percent-encoding이다.**

비유: Base64가 binary를 email-safe ASCII로 옮기는 transport-encoding이라면, percent-encoding은 임의 byte를 URL-safe ASCII로 옮기는 transport-encoding이다. 둘은 같은 발상의 다른 구현.

### 서.3 한글이 raw byte로 들어가면 생기는 문제 5가지

"그냥 UTF-8 byte를 URL에 그대로 넣으면 안 되나?" — 정확히 다음 5개 지점에서 깨진다.

```
[1] HTTP parser가 0x7F 이상 byte를 거부하거나 stripping
   - 일부 구식 HTTP/1.1 구현 (특히 ALB/CDN의 strict mode)이
     request-line에 비-ASCII byte 발견 → 400 Bad Request 반환
   - Nginx의 ignore_invalid_headers off (default on이지만 변경 시), client_max_body_size 우회 등의
     상호작용으로 의도 외 거부 발생
   - 일부 임베디드 HTTP stack (IoT, 산업용 PLC)은 8-bit clean 보장 안 함

[2] 중간 proxy/middlebox가 byte 검증에 실패
   - 기업 NAT/방화벽의 DPI (Deep Packet Inspection) 가 HTTP request-line을 검사
     → 비-ASCII byte를 "tampering"으로 판단 → drop
   - WAF (Web Application Firewall) 의 default rule이 "request-line은 ASCII만"
   - CDN edge에서 "URL normalization" 단계가 비-ASCII byte를 마음대로 변환

[3] URL 길이 한계 계산이 byte 기준
   - HTTP RFC는 길이를 정의 안 하지만, 구현체들은 buffer 단위 (Nginx 8KB, Tomcat 8KB)
   - 한글 1자 = 3 byte → 길이가 3배로 폭증
   - 한글 2000자 query = 6000 byte (limit 안)
     vs raw 한글 = 메모리상 2000자지만 wire 6000 byte (똑같음)
   - 단, percent-encoded면 한글 1자 = 9 char (%EA%B9%80) → 18000 byte (limit 초과)
   → 한글 길이 제한은 항상 "percent-encoded 후 byte 길이"로 계산해야 함

[4] log analyzer/grep이 깨짐
   - access log가 latin-1 또는 ASCII로 가정하고 파싱하는 도구 (구식 logrotate, awk 스크립트)
   - grep '한글패턴' /var/log/nginx/access.log 가 매치 안 됨 (raw byte 비교)
     → percent-encoded 형태로 grep해야 매치
   - ELK, Splunk, Datadog 같은 분석 도구는 UTF-8 처리하지만, 중간 transport 단계에서 깨짐

[5] charset 협상 안 된 경로에서 모지바케
   - 가장 흔한 증상: "í¬", "ê¹€", "ë©´" 같은 라틴 확장 + 액센트 조합
   - UTF-8 byte를 ISO-8859-1로 잘못 decode한 결과
   - 어느 한 계층 (Nginx, Tomcat, Filter, JDBC) 에서 charset 가정이 어긋나면 즉시 발생
```

이 5가지 문제 때문에 RFC 3986은 "raw 비-ASCII byte는 URL에 들어갈 수 없다"고 못박았다. percent-encoding이 강제된 이유.

### 서.4 올바른 단계별 변환

논리적 문자열 "김면수"가 wire에 도달하기까지 5단계.

```
[사용자 입력]   "김면수"
       │
       │ ① 텍스트 → Unicode codepoint
       │    (운영체제 입력기 / 브라우저가 담당)
       ▼
[Unicode]      U+AE40 U+BA74 U+C218
                 (한글 음절 영역 U+AC00~U+D7A3)
       │
       │ ② UTF-8 encoding (codepoint → 1~4 byte)
       │    RFC 3629 — variable-length encoding
       ▼
[UTF-8 byte]   0xEA 0xB9 0x80 0xEB 0xA9 0xB4 0xEC 0x88 0x98
                ─── 김 ───   ─── 면 ───   ─── 수 ───
                각 한글 음절 = 3 byte (U+0800~U+FFFF 범위)
       │
       │ ③ URL safety check (RFC 3986)
       │    0x80 이상 byte → unreserved 아님 → percent-encoding 필요
       ▼
[percent-enc]  %EA%B9%80%EB%A9%B4%EC%88%98
                각 byte → "%" + 2-digit uppercase hex
                결과는 ASCII printable 27자
       │
       │ ④ HTTP message 조립 (RFC 9112)
       │    method SP request-target SP version CRLF
       │    field-name ":" SP field-value CRLF
       │    CRLF (body 시작 또는 끝)
       ▼
[HTTP request] GET /users/%EA%B9%80%EB%A9%B4%EC%88%98 HTTP/1.1\r\n
               Host: example.com\r\n
               \r\n
       │
       │ ⑤ TCP segment → IP packet → Ethernet frame
       │    OS socket layer가 byte stream을 그대로 전송
       │    (ASCII이므로 추가 변환 없음)
       ▼
[wire bytes]   0x47 0x45 0x54 0x20 0x2F 0x75 0x73 0x65 0x72 0x73 0x2F 0x25 0x45 0x41 ...
               G    E    T    SP   /    u    s    e    r    s    /    %    E    A   ...
```

대조: ASCII-only URL은 ①~③ 단계를 **우회**한다.

```
[사용자 입력]   "www.google.com"
       │
       │ (모든 글자가 unreserved → 변환 없음)
       │ (운영체제 입력 → ASCII codepoint → ASCII byte는 무손실)
       ▼
[HTTP request] GET / HTTP/1.1\r\n
               Host: www.google.com\r\n
               \r\n
       │
       ▼
[wire bytes]   0x47 0x45 0x54 0x20 ...
```

ASCII로 시작하면 wire까지 1:1 사상. **변환이라는 개념 자체가 안 등장한다.** 그래서 영어권 개발자는 charset/encoding을 평생 안 마주칠 수 있다 — "그냥 string 처리하면 되잖아". 한글·일본어·중국어 환경에서는 이 변환을 **하루에 100번 마주친다.**

### 서.5 각 단계의 책임 주체

위 5단계가 누구의 책임인지 정확히 매핑.

```
단계 ①  텍스트 → Unicode codepoint
   주체: 운영체제 입력기 (IME — Input Method Editor)
   - macOS: HIToolbox + ATOK/Korean IM
   - Windows: TSF (Text Services Framework) + MS-IME
   - Linux: ibus, fcitx
   - 브라우저: OS의 IME를 그대로 사용, codepoint를 받음
   책임 실패: 거의 없음 (입력기 자체 버그는 드묾)

단계 ②  Unicode codepoint → UTF-8 byte
   주체: 브라우저의 URL 모듈 (또는 fetch/XHR 구현)
   - Chrome/Edge: //url/url_canon.h (Blink) + ICU
   - Firefox: nsIURI + libidn2
   - Safari: WebCore/platform/URL + CFNetwork
   책임 실패: 매우 드묾 (브라우저 모두 UTF-8 강제)

단계 ③  byte → percent-encoding
   주체: 브라우저 URL canonicalization 모듈
   - "주소창에 친 텍스트" 입력 시 자동 인코딩
   - JavaScript에서는 명시적 API 두 종:
       encodeURI(url)            — 전체 URL용. reserved(:/?#[]@!$&'()*+,;=) 는 보존
       encodeURIComponent(str)   — 컴포넌트 값용. reserved도 모두 encode
     예: 검색 쿼리 "a&b=c"
         encodeURI("a&b=c")          = "a&b=c"     ← &, = 보존 (의미 있다고 간주)
         encodeURIComponent("a&b=c") = "a%26b%3Dc" ← 모두 escape (데이터로 간주)
   - 잘못 쓰면: query value 안의 &가 다음 key 시작으로 오인 → 파싱 깨짐

단계 ④  HTTP message 조립
   주체: 브라우저 HTTP stack (네트워크 라이브러리)
   - Chrome: net/ (Chromium net stack), QUIC for HTTP/3
   - Firefox: necko, neqo (HTTP/3)
   - curl: libcurl
   - Java: java.net.HttpURLConnection / HttpClient (JDK 11+)
   책임 실패: Host 헤더 누락, CRLF 깨짐 (사용자 입력 sanitization 실패 시)

단계 ⑤  byte → TCP/IP packet
   주체: OS 커널의 socket layer + TCP/IP stack
   - Linux: net/ipv4/tcp_*.c
   - macOS: XNU의 BSD socket + TCP stack
   - 책임 실패: 거의 OS 버그 영역

서버 측 단계 ②'~③' 의 역변환
   - Tomcat: server.xml의 URIEncoding="UTF-8" 또는
             Spring Boot의 server.tomcat.uri-encoding=UTF-8 (Tomcat 8 이후 기본값 UTF-8)
   - Spring MVC: @PathVariable, @RequestParam 자동 decode
                 (Tomcat이 decode한 결과를 그대로 받음)
   - Servlet API: HttpServletRequest.getParameter() → decoded string
                  단, getQueryString() → raw (decode 안 됨, 직접 처리 필요)
   - Filter: CharacterEncodingFilter(encoding=UTF-8, forceEncoding=true)
             → body(POST)의 charset 결정, GET path/query는 영향 안 받음 (URIEncoding 영역)
```

### 서.6 www.google.com 같은 ASCII-only 케이스 — 두 가지 인코딩의 분리

여기서 매우 중요한 구분 하나. URL의 **path/query**는 percent-encoding을 쓰고, **hostname**은 punycode를 쓴다. 같은 URL 안에서 두 인코딩이 동시에 적용된다.

```
입력:  https://한국.kr/users/김면수?role=관리자
         ──┬─── ──┬───── ────┬───── ────┬─────
         scheme  hostname   path        query
                  │           │           │
                  │           │           └─ percent-encoding (UTF-8 byte)
                  │           │              role=%EA%B4%80%EB%A6%AC%EC%9E%90
                  │           │
                  │           └─ percent-encoding (UTF-8 byte)
                  │              /users/%EA%B9%80%EB%A9%B4%EC%88%98
                  │
                  └─ punycode (Bootstring algorithm, RFC 3492)
                     한국 → xn--3e0b707e

최종 wire:
   GET /users/%EA%B9%80%EB%A9%B4%EC%88%98?role=%EA%B4%80%EB%A6%AC%EC%9E%90 HTTP/1.1
   Host: xn--3e0b707e.kr
```

**왜 hostname만 다른 인코딩인가** — DNS의 역사 때문.

```
DNS는 1983년 (RFC 1034/1035) 설계 — ASCII case-insensitive + 길이 제한 (label 63 byte, FQDN 255 byte).
DNS query packet의 wire format은 raw byte (length-prefixed label).
→ DNS는 임의 byte를 받을 수 있지만, ASCII case-insensitive 검색이 깨지면 안 됨.

해결책: IDN (Internationalized Domain Name)을 ASCII-Compatible Encoding으로 변환.
   - RFC 3490 (IDNA2003, 2003년) → RFC 5890~5894 (IDNA2008, 2010년)
   - 변환 알고리즘: Punycode (RFC 3492)
   - prefix "xn--" 가 "이건 punycode-encoded이다"의 신호

vs

URL의 path/query는 1994년 RFC 1738에서 percent-encoding 도입.
   - DNS와 별개. URL 자체의 문자열 표현 규칙.
   - 어떤 byte도 %HH로 표현 가능 → DNS와 달리 길이 한계 없음.
```

**중복 인코딩 안 함의 의미**:
- hostname을 percent-encoding하면 안 됨 (`xn--3e0b707e.kr`은 그대로 DNS에 보냄)
- path를 punycode로 인코딩하면 안 됨 (path는 percent-encoding만)
- 같은 URL 안에 두 인코딩이 공존 — 컴포넌트마다 규칙이 다름

운영 함정 예시:

```
잘못된 URL 빌더:
   URL url = new URL("https://" + URLEncoder.encode("한국.kr", "UTF-8") + "/path");
   → "https://%ED%95%9C%EA%B5%AD.kr/path"
   → hostname이 percent-encoded됨 → DNS lookup 실패 (NXDOMAIN)

올바른 빌더:
   String puny = IDN.toASCII("한국.kr");
   // → "xn--3e0b707e.kr"
   URL url = new URL("https://" + puny + "/path");
```

### 서.7 "왜 처음부터 UTF-8 직접 전송 안 했나" — HTTP의 하위 호환성

질문이 자연스럽다. "1990년대엔 그렇다 쳐도, 2010년대에 모두 UTF-8 호환됐는데 왜 percent-encoding을 계속 쓰나?"

세 가지 이유가 맞물려서 못 바꾼다.

```
① old proxy / middlebox 호환성
   - 기업 네트워크의 NAT, 방화벽, WAF, CDN edge가 "ASCII만 받음"으로 hard-code된 사례 많음
   - 30년 묵은 임베디드 HTTP stack (HVAC 컨트롤러, ATM, POS, IoT) 가 8-bit byte를 거부
   - HTTP/2가 binary framing으로 가도, hostname/path는 여전히 ASCII (HTTP/2 spec §8.1.2)
   → "ASCII URL이면 어디서나 안전"이라는 invariant를 깨면 deployment 깨짐

② URL은 HTTP 밖으로 새어 나간다
   - HTML <a href="..."> 의 attribute value
   - Email body, Slack message, Tweet, SMS
   - 로그 파일, 모니터링 대시보드, alarm 메시지
   - Shell command line (curl, wget 인자)
   - URL이 ASCII-only이면 위 모든 환경에서 안전 (특수 escape 불필요)
   - UTF-8 직접 전송이면 일부 환경 (구식 mail client, 7-bit transport) 에서 깨짐
   → URL의 "ASCII-only 보증"은 wire 너머의 가치 (메타데이터 transport 안전)

③ Percent-encoding은 transport-encoding의 표준 패턴
   - Base64 (email binary attachment)
   - Quoted-Printable (email text with 8-bit)
   - URL Percent-encoding (URL with arbitrary byte)
   - 모두 "ASCII-safe transport 위에 임의 byte를 얹는 기법"
   - 30년의 운영 경험으로 검증된 패턴 — 굳이 새로 안 만듦
```

본질: percent-encoding은 **"HTTP의 ASCII invariant를 깨지 않으면서 임의 byte를 얹는" transport-encoding**이다. Base64가 SMTP에서 한 일과 같은 역할.

### 서.8 운영 시나리오 — 위 본질이 어떻게 production을 지배하나

```
[시나리오 ALPHA] "Slack에 한글 URL 붙여넣으면 %EA%B9%80... 으로 변환되어 보임"
  - Slack 메시지 입력 필드는 plain text (사용자 본 그대로)
  - send 시 Slack 서버가 URL detection 모듈 실행
    → URL pattern 인식 → 자동 IRI → URI 변환 (RFC 3987 §3.1)
    → hostname punycode 변환, path percent-encoding 적용
  - 받는 쪽 (다른 사용자) 에는 변환된 URL이 보임
    (단, Slack desktop client는 hover 시 IRI로 다시 표시 가능)
  → 이유: link unfurling, click 시 정확한 URL fetch 보장.
    raw 한글 URL이면 일부 사용자의 OS/브라우저 조합에서 깨질 위험.

[시나리오 BRAVO] "검색엔진 크롤러가 percent-encoded URL과 raw 한글 URL을 같은 페이지로 dedup"
  - Googlebot, Bingbot이 URL normalization 수행 (RFC 3986 §6)
  - canonicalization: scheme/host lowercase, default port 제거, dot-segment 정리,
                      percent-encoded unreserved 복원 (예: %41 → A)
  - IRI → URI 변환도 부분적으로 적용 (논리적 같은 URL을 같은 페이지로)
  - 그래서 sitemap.xml에 raw 한글 또는 percent-encoded URL 어느 쪽 넣어도 같은 결과
  → 운영 팁: <link rel="canonical">에는 일관성 유지 (대부분 percent-encoded form 사용)

[시나리오 CHARLIE] "Cloudflare가 IDN homograph attack 방지로 punycode 표시"
  - 등록된 도메인: paypal.com 의 가짜로 раураl.com (키릴 а, р, и, l)
  - DNS 조회 시 punycode: xn--pypl-53dc.com (예시)
  - Cloudflare WAF의 IDN protection 룰:
    - 라틴+키릴 혼용 / 라틴+그리스 혼용 → suspicious
    - 사용자에게 표시되는 URL을 punycode 형태로 강제 (브라우저 주소창에도 표시)
    - 클릭 시 경고
  - Chrome도 동일 — Chromium의 IDN spoofing detection은 OS의 locale과 무관하게 동작
  → 운영 함정: 정상 IDN (한국.kr) 도 사용자 OS locale이 ko가 아니면 punycode로 표시될 수 있음
```

### 서.9 한 줄 요약

> **HTTP는 30년간 ASCII protocol로 살아왔고 앞으로도 그렇다. 한글·이모지·라틴 확장은 percent-encoding (path/query) 또는 punycode (hostname) 으로 ASCII-safe하게 변환되어 wire에 실린다. 이 invariant가 깨지면 어딘가에서 모지바케 또는 400 Bad Request가 터진다.**

이제 이 본질을 알았으니, 0장 마인드맵의 6단계가 자연스럽게 읽힌다.

---

## 0. 마인드맵 — 백지에 그리는 그림

### 루트 한 문장 (anchor)

> **"문자열은 텍스트(논리) → 유니코드 코드포인트 → UTF-8 바이트 → percent-encoding으로 URL-safe ASCII → HTTP 메시지 바이트 → TCP segment 의 6단계 변환을 거친다. 각 단계는 책임이 다르고, 한 단계의 charset 불일치가 곧 모지바케다."**

### 6단계 변환 다이어그램

```
            [브라우저 (클라이언트)]                         [서버 (Tomcat/Nginx)]
            ─────────────────────                         ────────────────────

  사용자 입력
   "김면수"
       │
       │  ① 텍스트 → 유니코드 코드포인트
       │     (Unicode Codepoint, U+AC00~U+D7A3 한글 음절 영역)
       ▼
   [U+AE40, U+BA74, U+C218]
       │
       │  ② 코드포인트 → UTF-8 바이트
       │     (Transfer encoding, 1~4 byte per codepoint)
       ▼
   [EA B9 80][EB A9 B4][EC 88 98]    ← 9 bytes
       │
       │  ③ ASCII 외 바이트 → percent-encoding
       │     (URL-safe ASCII로 변환, RFC 3986)
       ▼
   "%EA%B9%80%EB%A9%B4%EC%88%98"     ← 27 ASCII chars
       │
       │  ④ URL 조립 + HTTP 메시지 직렬화
       │     (request-line, headers, CRLF, body)
       ▼
   "GET /users/%EA%B9%80%EB%A9%B4%EC%88%98 HTTP/1.1\r\n
    Host: example.com\r\n
    \r\n"
       │
       │  ⑤ HTTP 메시지 → 바이트 stream
       │     (이미 ASCII이므로 바이트 = char value)
       ▼
   [47 45 54 20 2F 75 73 65 72 73 2F 25 45 41 ...]
       │
       │  ⑥ TCP segment에 실어 송신
       │     (segment마다 MSS 크기로 분할)
       ▼
   ═══════════════════ Network ═══════════════════
                        │
                        ▼
                  [서버 NIC]
                        │
                        │  ⑥' TCP reassembly (커널 socket buffer)
                        ▼
                  [HTTP 파서]
                        │
                        │  ⑤'/④' request-line, headers, body 분리
                        ▼
                  ["/users/%EA%B9%80%EB%A9%B4%EC%88%98"]
                        │
                        │  ③' percent-decoding
                        ▼
                  [EA B9 80 EB A9 B4 EC 88 98]
                        │
                        │  ②' UTF-8 → 코드포인트 (URIEncoding=UTF-8 설정 필수)
                        ▼
                  [U+AE40, U+BA74, U+C218]
                        │
                        │  ①' 코드포인트 → 문자열 객체 (Java String)
                        ▼
                     "김면수"
```

### 6단계 책임 분리 표

| 단계 | 책임 | RFC/표준 | 실패 시 증상 |
|---|---|---|---|
| ① 텍스트 → 코드포인트 | OS 입력기 / 브라우저 | Unicode | 입력 자체 깨짐 (드묾) |
| ② 코드포인트 → UTF-8 바이트 | 브라우저 | RFC 3629 | 깨진 바이트 시퀀스 |
| ③ 바이트 → percent-encoding | 브라우저 URL 모듈 | RFC 3986 | URL 파싱 실패 / 변환 안 됨 |
| ④ HTTP 메시지 조립 | 브라우저 HTTP 스택 | RFC 9112 (HTTP/1.1) | request-line 깨짐, Host 누락 |
| ⑤ 메시지 → 바이트 | OS socket layer | - | (변환 없음, ASCII) |
| ⑥ 바이트 → TCP segment | 커널 TCP/IP stack | RFC 9293 | reassembly 실패 |

### 면접 답변 흐름

> 면접관: "주소창에 한글을 친 URL이 어떻게 서버에 도착하나요?"
>
> 답: "6단계입니다. 텍스트가 유니코드 코드포인트가 되고 → UTF-8 바이트가 되고 → ASCII 외 바이트는 percent-encoding으로 `%XX` 형태가 되고 → HTTP request-line에 들어가 CRLF로 구분된 메시지가 되고 → 바이트 stream으로 socket에 쓰여 → TCP segment에 실립니다. 서버는 정확히 역순. 어느 한 단계의 charset이 어긋나면 그 지점이 모지바케의 원인입니다."

---

## 1. URL 구조 파싱 — RFC 3986의 5+1 컴포넌트

### 1.1 핵심 질문

> "`https://user:pass@example.com:8080/users/김면수?role=관리자#section` 을 분해하면?"

### 1.2 URL의 정식 grammar

RFC 3986 §3에 정의된 generic URI는 다음 컴포넌트로 구성된다.

```
       scheme     authority                              path             query           fragment
       ─────     ─────────                              ────             ─────           ────────
       https://  user:pass@example.com:8080            /users/김면수    ?role=관리자    #section
       ─────     ────── ─────────── ────                ────────────    ──────────────  ───────
        ①        userinfo  host    port                  path             query         fragment

       ① scheme    : 프로토콜 식별자 (https, http, ftp, mailto, file, ws ...)
       ② userinfo  : (거의 안 씀, HTTP에선 보안상 deprecated)
       ③ host      : DNS hostname 또는 IP literal ([::1] 형식 가능)
       ④ port      : optional, scheme의 기본값 사용 (https=443, http=80)
       ⑤ path      : 리소스 경로, '/' 로 시작, segment로 분리
       ⑥ query     : "?" 로 시작, key=value&key=value 형식 (관습)
       ⑦ fragment  : "#" 로 시작, 클라이언트 전용 (서버로 전송되지 않음 ★)
```

### 1.3 가장 중요한 한 가지 — fragment는 서버에 안 간다

```
브라우저 입력:
  https://example.com/page?q=test#section

브라우저가 실제로 보내는 HTTP request:
  GET /page?q=test HTTP/1.1     ← fragment 제거됨
  Host: example.com

이유: fragment는 "문서 안에서 어느 위치로 스크롤할지" 의 클라이언트 hint.
      서버는 그 정보가 필요 없음. RFC 3986 §3.5.
```

운영 함정: SPA (Single Page App)가 fragment에 라우팅 정보를 담는 경우 (`#/users/123`) — 서버 로그에 안 남기 때문에 디버깅 시 누락된다. 그래서 React Router도 HTML5 History API (`history.pushState`)로 옮겨감.

### 1.4 reserved vs unreserved character set

RFC 3986 §2가 정의하는 4종류의 문자.

| 분류 | 문자들 | 의미 | percent-encode 필요? |
|---|---|---|---|
| **unreserved** | `A-Z a-z 0-9 - . _ ~` | 안전한 문자, 어디서나 그대로 사용 | ❌ 절대 안 함 |
| **gen-delims** | `: / ? # [ ] @` | URL 컴포넌트 구분자 | ⚠️ 컴포넌트 안에서 데이터로 쓰면 encode |
| **sub-delims** | `! $ & ' ( ) * + , ; =` | 쿼리/path 내 의미 가진 구분자 | ⚠️ 데이터로 쓰면 encode |
| **그 외 모든 것** | 공백, 한글, `<>{}\|\` 등 | 안전 보장 안 됨 | ✅ 무조건 encode |

**핵심 규칙**: 각 URL 컴포넌트는 자신의 구분자(`/`, `?`, `#`, `&`, `=` 등)가 데이터에 나타나면 반드시 percent-encode. 예: query value에 `&`가 들어가면 `%26`으로 인코딩해야 다음 key의 시작과 구분된다.

### 1.5 path segment의 분리

```
URL: https://example.com/a/b%2Fc/d
                          ↓ 분해
path: /a/b%2Fc/d
path segments: ["a", "b%2Fc", "d"]      ← segment 안의 %2F는 디코딩 안 함
서버 측 decoded: ["a", "b/c", "d"]      ← 이제 decode

★ 만약 %2F가 그냥 / 로 들어왔다면:
path segments: ["a", "b", "c", "d"]     ← 4개로 분리됨

→ %2F vs / 는 path에서 의미가 완전히 다르다.
→ Nginx의 merge_slashes off + path 안 %2F 처리는 RCE 우회 경로 (CVE 사례 있음).
```

---

## 2. IDN (한글 도메인) — Punycode 변환

### 2.1 왜 punycode가 필요한가

DNS는 1983년 설계 당시 **ASCII만 받게** 만들어졌다 (RFC 1035). hostname에 한글을 그대로 못 넣는다. 그렇다고 매번 한글 도메인을 ASCII로 음역하면 표준이 깨진다.

해결책: **IDNA (Internationalizing Domain Names in Applications)** — RFC 3490 (2003), 이후 RFC 5890~5894 (2010).

**핵심 아이디어**: 호스트 입력은 유니코드로 받되, DNS 질의 전에 ASCII로 변환. 변환 알고리즘이 **Punycode** (RFC 3492).

### 2.2 punycode 변환 예시

```
입력 (사용자):     한국.kr
                  │
                  │  브라우저 IDN 모듈 (libidn2 / ICU 등)
                  │  ① 유니코드 정규화 (NFC: Normalization Form C)
                  │  ② 금지된 문자 체크 (homograph attack 방지)
                  │  ③ Punycode 인코딩
                  ▼
                  xn--3e0b707e.kr      ← DNS에 실제 질의되는 hostname
                  └─┬┘                 ← "xn--" prefix = Punycode 알림
                    ACE prefix
```

`xn--` 의미: "ASCII Compatible Encoding". DNS가 보기엔 평범한 ASCII hostname.

### 2.3 Punycode가 동작하는 본질 — 기본 원리

Punycode는 **희소(sparse) 유니코드 코드포인트를 ASCII 베이스에 인코딩**하는 알고리즘. 핵심 두 가지.

```
1. ASCII 문자는 그대로 두고, 비-ASCII 코드포인트의 "위치"와 "값"만 별도로 인코딩.
   "한국.kr" → 분리하면:
     - ASCII 부분: ".kr" (그대로)
     - 비-ASCII: 한(U+D55C) at pos 0, 국(U+AD6D) at pos 1

2. delta encoding으로 코드포인트들을 ASCII a-z, 0-9 (36진법)로 표현.
   결과: "xn--3e0b707e" 의 "3e0b707e" 부분
```

세부 알고리즘 (bias adjustment 등)은 표면 디테일 — 외울 가치 없음. 핵심은 **"유니코드 hostname은 항상 punycode로 변환 후 DNS 질의된다"** 는 사실.

### 2.4 보안 — homograph attack

```
정상:  apple.com         (라틴 a, U+0061)
공격:  аpple.com         (키릴 а, U+0430)  ← 사람 눈엔 동일

→ 두 hostname은 punycode 변환 후 다르다:
  정상: apple.com           (ASCII 그대로)
  공격: xn--pple-43d.com    (punycode 표시)

브라우저 방어:
  - Chrome/Firefox: 라틴+키릴 혼용 등 의심 패턴 감지 시 punycode 형태로 표시.
  - DNS 등록 기관: 같은 스크립트(라틴/한글/한자) 안에서만 허용.
```

---

## 3. Percent-encoding — `김`이 `%EA%B9%80` 이 되는 정확한 과정

### 3.1 한 줄 정의

> **"ASCII가 아닌 바이트(또는 reserved character를 데이터로 쓸 때)를 `%` + 2자리 hex 로 표현"**

### 3.2 김 → `%EA%B9%80` 단계별

```
단계 1: 문자 → 유니코드 코드포인트
   '김' = U+AE40

단계 2: 코드포인트 → UTF-8 바이트
   U+AE40 은 U+0800 ~ U+FFFF 범위 → UTF-8 3바이트 시퀀스
   비트 패턴: 1110xxxx 10xxxxxx 10xxxxxx
   U+AE40 = 1010 1110 0100 0000
   → 1110_1010  1011_1001  1000_0000
   → 0xEA       0xB9       0x80

단계 3: 각 바이트 → percent-encoding
   0xEA → "%EA"
   0xB9 → "%B9"
   0x80 → "%80"
   → "%EA%B9%80"

마지막: 문자열 concat
   "김" → "%EA%B9%80"
```

세 글자 "김면수" 전체:

```
김 U+AE40 → EA B9 80 → %EA%B9%80
면 U+BA74 → EB A9 B4 → %EB%A9%B4
수 U+C218 → EC 88 98 → %EC%88%98
───────────────────────────────────
"김면수" → "%EA%B9%80%EB%A9%B4%EC%88%98"
```

### 3.3 검증 (Python으로)

```python
from urllib.parse import quote, unquote

print(quote('김면수'))
# '%EA%B9%80%EB%A9%B4%EC%88%98'

print(unquote('%EA%B9%80%EB%A9%B4%EC%88%98'))
# '김면수'

# 바이트 레벨 확인
print('김면수'.encode('utf-8'))
# b'\xea\xb9\x80\xeb\xa9\xb4\xec\x88\x98'

print('김면수'.encode('utf-8').hex())
# 'eab980eba9b4ec8898'
```

### 3.4 역사 — 왜 UTF-8 + percent-encoding 인가

```
1994  RFC 1738 (Tim Berners-Lee, URL 첫 정의)
       - "non-ASCII octet은 %HH로 표현"만 정의
       - 어떤 charset인지 명시 안 됨 → 호환성 카오스 시작

2000년대 초  실무 혼란
       - 윈도우: EUC-KR로 인코딩 → "김" → "%B1%E8"
       - 맥 OS: UTF-8 → "김" → "%EA%B9%80"
       - 같은 URL이 OS마다 다르게 인코딩 → 서버 디코딩 실패

2005  RFC 3986 (현재)
       - "URL의 새로운 컴포넌트는 UTF-8 사용 권장"
       - HTML5 (2008) 폼 데이터는 application/x-www-form-urlencoded charset = 페이지 charset
       - 페이지 자체가 UTF-8 → 사실상 UTF-8 단일화

2014~ 모든 주요 브라우저 UTF-8 + percent-encoding 표준화
       - 단, query string의 form encoding은 여전히 페이지 charset에 의존 (★ 운영 함정)
```

### 3.5 어디서 어떻게 다른가 — 컴포넌트별 encoding 규칙

| 위치 | encode 대상 | charset | 비고 |
|---|---|---|---|
| **path segment** | `/`, `?`, `#` 와 비-ASCII | UTF-8 (브라우저 표준) | RFC 3986 |
| **query string (URL)** | `&`, `=`, `?`, `#` 와 비-ASCII | UTF-8 | 페이지 encoding 영향 작음 |
| **form-encoded body** | path보다 더 엄격, `+`도 special | **페이지 charset** ★ | `<form>` 의 charset attribute |
| **URL fragment** | 거의 free, `#` 만 escape | UTF-8 | 서버 안 감 |
| **userinfo** | `@`, `:`, 비-ASCII | UTF-8 | 거의 안 씀 |

**form 의 함정**:
```html
<!-- 페이지 charset이 EUC-KR -->
<meta charset="EUC-KR">
<form action="/search">
  <input name="q" value="김">    ← form submit 시 "김"이 EUC-KR로 encode
</form>

→ GET /search?q=%B1%E8           ← UTF-8이면 %EA%B9%80
```

서버가 무조건 UTF-8로 decode하면 EUC-KR 데이터를 깨먹는다. 그래서 Spring에서 `CharacterEncodingFilter` + `forceEncoding=true` 가 정형 패턴.

---

## 4. HTTP 메시지 직렬화 — request-line + headers + CRLF + body

### 4.1 한 장의 HTTP/1.1 메시지 레이아웃

```
GET /users/%EA%B9%80%EB%A9%B4%EC%88%98?role=%EA%B4%80%EB%A6%AC%EC%9E%90 HTTP/1.1\r\n
Host: example.com\r\n
User-Agent: Mozilla/5.0\r\n
Accept: text/html\r\n
Accept-Charset: utf-8\r\n
\r\n
└── 빈 줄 (CRLF만)  ← header section과 body의 경계
```

바이트 레이아웃:

```
position  bytes                                meaning
────────  ────────────────────────────────     ──────────────────
0         47 45 54                              "GET"
3         20                                    " " (space)
4         2F 75 73 65 72 73 2F 25 ...           path
N         20                                    " "
N+1       48 54 54 50 2F 31 2E 31               "HTTP/1.1"
N+9       0D 0A                                 CRLF (\r\n)  ← request-line 끝
...
M         48 6F 73 74 3A 20 ...                 "Host: ..."
M+L       0D 0A                                 CRLF
...
K         0D 0A                                 CRLF  ← header 끝
K+2       (body 시작, 없을 수도)
```

### 4.2 왜 CRLF (`\r\n` = 0x0D 0x0A) 인가

```
역사:
  1960년대 ASCII 정의 — 텔레타이프 시대
    \r (Carriage Return, 0x0D) = 캐리지를 줄의 처음으로
    \n (Line Feed, 0x0A) = 종이를 한 줄 위로
    → 둘 다 필요. 종이 타이프라이터의 물리 동작 그대로.

  1970~80년대 OS별 분기:
    Unix: \n 만
    Mac OS 9: \r 만
    Windows / DOS: \r\n
    → 분파가 영원히 안 합쳐짐.

  네트워크 프로토콜은? — "보수적으로" CRLF 통일.
  Telnet, FTP, SMTP, HTTP 모두 CRLF.
```

**RFC 9112 §2.2**: "the line terminator is CRLF". 단, **관대한 파서** 권고: `\n` 만 와도 받아도 됨 (be liberal in what you accept).

**보안**: CRLF injection — 사용자 입력에 `\r\n` 을 끼워넣어 가짜 헤더를 추가하는 공격. 예: `Set-Cookie: name=foo\r\nLocation: evil.com`. → 모든 헤더 값에서 `\r\n` 필터링.

### 4.3 Host 헤더가 없으면 무슨 일이 일어나나

```
시나리오: 한 IP에 여러 vhost
  93.184.216.34 ← example.com, blog.com, api.com 모두 가리킴

요청 1 (Host 헤더 있음):
  GET /index.html HTTP/1.1
  Host: blog.com
  → Nginx가 server_name blog.com 으로 라우팅 ✓

요청 2 (Host 헤더 누락):
  GET /index.html HTTP/1.1
  → Nginx는 default_server 또는 첫 번째 server 블록으로 라우팅
  → 의도와 다른 vhost로 갈 수 있음 (또는 400 Bad Request)
```

**왜 필요**: HTTP/1.0 시대엔 1 IP = 1 서버. HTTP/1.1 (1999, RFC 2616)부터 vhost 시대 → Host 헤더 **필수**. RFC 9112 §3.2: "A server MUST respond with a 400 (Bad Request) to any HTTP/1.1 request message that lacks a Host header field."

### 4.4 request-line의 각 부분이 직렬화되는 방식

```
GET /users/김면수?role=관리자 HTTP/1.1

  ↓ (브라우저 내부)

method:  "GET"                                      ← ASCII (대문자 표준)
target:  "/users/%EA%B9%80%EB%A9%B4%EC%88%98?role=%EA%B4%80%EB%A6%AC%EC%9E%90"
                                                    ← path + "?" + query, 모두 percent-encoded
version: "HTTP/1.1"                                  ← 고정 문자열

connect them with single SP (space, 0x20):
   "GET" + " " + target + " " + "HTTP/1.1" + CRLF
```

### 4.5 헤더 값에 한글이 들어가면?

HTTP 헤더 값은 원칙적으로 **ASCII 또는 ISO-8859-1**. 비-ASCII는 두 가지 우회:

```
1. RFC 5987 (encoded-word in header value)
   Content-Disposition: attachment; filename*=UTF-8''%EA%B9%80%EB%A9%B4%EC%88%98.pdf
                                            ─────  ───────────────────────────────
                                            charset                  encoded value

2. RFC 2047 (MIME encoded-word, email에서 유래)
   Subject: =?UTF-8?B?6rmA66m066W4?=
                ─── ─ ────────────
                charset            base64 of UTF-8

이메일 헤더(SMTP) 는 #2 흔함. HTTP는 #1 권장.
```

**가장 흔한 함정**: `Content-Disposition: attachment; filename="김면수.pdf"` 처럼 raw 한글을 헤더 값에 넣으면 → 브라우저별로 동작 다름 (Chrome은 UTF-8 추측, IE는 안 됨). `filename*=UTF-8''...` 형태가 표준.

---

## 5. 인코딩의 5계층 — 책임 분리

### 5.1 한 장 그림

```
Application Layer
  "김면수" (Java String, UTF-16 in JVM memory)
        │
        │  encode (Charset.forName("UTF-8"))
        ▼
  [EA B9 80 EB A9 B4 EC 88 98]  ← UTF-8 byte sequence (9 bytes)
                                  Transfer encoding (RFC 3629)
        │
        │  percent-encode (where used)
        ▼
  "%EA%B9%80%EB%A9%B4%EC%88%98"  ← URL-safe ASCII (27 chars)
                                  URL encoding (RFC 3986)
        │
        │  HTTP message framing
        ▼
  "GET /users/%EA...HTTP/1.1\r\nHost:...\r\n\r\n"
                                  HTTP/1.1 (RFC 9112)
        │
        │  socket.write (no transform, ASCII)
        ▼
  TCP segments (payload + TCP header + IP header)
                                  TCP (RFC 9293)
        │
        │  NIC, link layer (Ethernet frame)
        ▼
  Network
```

### 5.2 각 계층의 책임

| 계층 | 책임 | 실패 시 |
|---|---|---|
| **Application** | 의미를 가진 텍스트 다룸 | 잘못된 문자열 (드묾) |
| **Charset Transfer (UTF-8)** | 코드포인트 ↔ 바이트 | 모지바케 (charset 불일치) |
| **URL Encoding** | 바이트 ↔ ASCII-safe | URL 파싱 실패, 잘못 분리 |
| **HTTP Framing** | 메시지 경계 | HTTP 파서 에러 (400 Bad Request) |
| **TCP/IP** | 바이트 stream → segment | 연결 끊김, 패킷 손실 |

### 5.3 실패 패턴 — 모지바케의 정체

모지바케 (mojibake, 文字化け, 글자 깨짐) = **decode 시 charset이 encode 시와 다름**.

```
정상:
  encode: "김" --UTF-8--> [EA B9 80]
  decode: [EA B9 80] --UTF-8--> "김"

오류 ① (EUC-KR로 잘못 decode):
  encode: "김" --UTF-8--> [EA B9 80]
  decode: [EA B9 80] --EUC-KR--> "꿃"  ← 다른 글자로 보임

오류 ② (raw byte를 latin-1로 decode):
  encode: "김" --UTF-8--> [EA B9 80]
  decode: [EA B9 80] --ISO-8859-1--> "ê¹€"  ← 가장 흔한 모지바케 패턴

오류 ③ (double encode):
  encode: "김" --UTF-8--> [EA B9 80] --UTF-8 다시--> [C3 AA C2 B9 E2 82 AC]
  decode: 결과는 더 길어지고 깨짐
```

**진단법**: "ê¹€" 같은 라틴 확장 + 액센트 조합이 보이면 → **UTF-8 데이터를 ISO-8859-1로 decode한 것**. 매우 흔한 패턴.

### 5.4 Production 시나리오 — 모지바케가 등장하는 실제 지점들

본질만 알면 진단이 빨라진다. 실제 production에서 등장하는 4가지 흔한 시나리오.

#### 5.4.1 Nginx access_log에 한글이 `%XX` 형태 vs raw로 남는 차이

```
Nginx access_log_format 기본 ($request 변수):
   GET /users/%EA%B9%80%EB%A9%B4%EC%88%98 HTTP/1.1
   ─── ─────────────────────────────────── ────────
   method  raw request-target (brower가 보낸 그대로)  version

  → Nginx는 percent-decoding 안 함. 받은 그대로 log에 기록.
  → 운영자가 한글로 보고 싶으면 사후 decode 필요:
      awk '{print $7}' access.log | python3 -c "
      import sys, urllib.parse
      for l in sys.stdin: print(urllib.parse.unquote(l.strip()))
      "

만약 한글이 raw로 log에 보이면? — 2가지 경우:
   1. 클라이언트(curl, 자체 HTTP 클라이언트)가 percent-encoding 안 하고 raw UTF-8 byte 전송
      → Nginx가 그대로 받음 (8-bit clean) → log에 raw byte 기록
      → cat access.log 시 터미널의 UTF-8 처리로 한글로 보임
      → grep으로 한글 검색 가능 (raw byte 매칭)
   2. log 분석 도구 (Logstash, Fluentd) 가 중간에 urldecode filter 적용
      → 원본은 percent-encoded지만 가공 후 raw 한글

⚠️ 운영 함정:
   - 두 경우가 log 파일만 보고는 구별 안 됨
   - tcpdump로 wire를 봐야 어느 쪽인지 확정
   - 일부 봇/공격자가 raw 한글로 path traversal 시도 → percent-encoded 검사만 하면 우회
```

#### 5.4.2 Tomcat URIEncoding 기본값의 역사 — ISO-8859-1 시절의 잔재

```
Tomcat 8 미만 (2014 이전):
   기본 URIEncoding = ISO-8859-1 (HTTP RFC 2616의 deprecated 조항 따름)
   → 한글 URL이 와도 byte를 ISO-8859-1로 해석
   → request.getParameter("name") = "ê¹€ë©´ìˆ˜" (모지바케)
   해결: server.xml에 명시
      <Connector port="8080" URIEncoding="UTF-8" useBodyEncodingForURI="false"/>

Tomcat 8 (2014) 이후:
   기본 URIEncoding = UTF-8 (변경됨)
   → Spring Boot 1.x 부터는 server.tomcat.uri-encoding=UTF-8 자동 (8.x 의존성)
   → 거의 대부분 환경에서 자동 동작
   하지만:
      - 일부 레거시 시스템이 Tomcat 7 (EOL 2021) 유지
      - Container 이미지가 Tomcat 7 base로 빌드된 케이스
      - WebSphere, WebLogic 같은 다른 컨테이너의 URI 처리는 기본 ISO-8859-1 흔함

운영 진단:
   - "POST는 한글 멀쩡한데 GET 쿼리만 ??? 로 나옴" → 100% URIEncoding 문제
   - getCharacterEncoding() 으로 확인 가능 (request body charset)
   - getQueryString() 으로 raw 확인 — percent-encoded여야 정상
```

#### 5.4.3 Spring `@RequestMapping("/users/{name}")` 의 자동 decode

```
요청: GET /users/%EA%B9%80%EB%A9%B4%EC%88%98 HTTP/1.1

Tomcat 단계 (URIEncoding=UTF-8 기본):
   1. request-target 파싱: "/users/%EA%B9%80%EB%A9%B4%EC%88%98"
   2. path를 percent-decode (URI 변수 추출 위해):
      - byte: [EA B9 80 EB A9 B4 EC 88 98]
      - URIEncoding=UTF-8 → "김면수" (정상 decode)
   3. URIPattern matcher가 {name} = "김면수" 매핑.

Spring 단계:
   @PathVariable String name → "김면수" 그대로 주입.

함정 — RFC 3986의 path segment 분리 규칙:
   GET /users/김%2F면%2F수 HTTP/1.1
                ─── 김 ───
   이 path는 "name = 김/면/수" 의 의도일 수 있고, "/users/김, /면, /수" 일 수도 있음.
   - Tomcat 기본: %2F는 path separator로 취급 안 함 (RFC 3986 §3.3)
     → {name} = "김/면/수" (raw / 아님, decoded /)
   - 일부 reverse proxy (Nginx) 는 %2F를 / 와 동일 취급
     → upstream에 다른 path가 도달
   → CVE 사례 다수 (path traversal, URL routing bypass)
   - Java 11+ application: spring.mvc.pathmatch.matching-strategy=PATH_PATTERN_PARSER
     사용 시 %2F 명시적 disable 가능
```

#### 5.4.4 JDBC URL의 `characterEncoding` 누락 — DB까지 깨져서 들어가는 케이스

```
모지바케의 마지막 게이트 — DB connection 단계.

MySQL JDBC URL의 정확한 형태:
   jdbc:mysql://host:3306/db?useUnicode=true&characterEncoding=UTF-8&useServerPrepStmts=true
                              ─────────────  ─────────────────────
                              필수 (오래된 driver 호환)  필수

  - useUnicode=true: connector가 Unicode 처리 활성화
  - characterEncoding=UTF-8: client side에서 String ↔ byte 변환 charset
  - 누락 시:
    Connector/J 5.x 이전: 서버의 character_set_server 사용 (보통 latin1)
                          → "김면수" → server에 보낼 때 ?? 로 변환
    Connector/J 8.x: 기본 UTF-8 (변경됨, 그러나 명시 권장)

서버 측 추가 체크:
   SHOW VARIABLES LIKE 'character_set%';
   +--------------------------+--------+
   | Variable_name            | Value  |
   +--------------------------+--------+
   | character_set_client     | utf8mb4|  ← JDBC가 SET NAMES utf8mb4로 설정
   | character_set_connection | utf8mb4|
   | character_set_database   | utf8mb4|
   | character_set_results    | utf8mb4|
   | character_set_server     | utf8mb4|
   +--------------------------+--------+

만약 하나라도 latin1이면 그 단계가 lossy:
   - client (Java) → server (utf8mb4 client) OK
   - server connection (latin1) → database (latin1) loss
   → "김면수" → "???" 또는 "ê¹€ë©´ìˆ˜"

Tomcat (UTF-8) → Spring (UTF-8) → JDBC (charset 누락) → MySQL server (latin1)
   = "정상→정상→정상→손실"
   결과: DB에 깨진 채 저장 → 그 후 모든 SELECT 결과가 깨짐
   복구: 어렵다. byte 단위로 다시 변환 추정해야 함 (CONVERT 함수 + 추측).
```

---

## 6. POST body의 직렬화 — 3가지 Content-Type

같은 데이터 `{"name": "김면수", "age": 30}` 가 Content-Type에 따라 완전히 다르게 직렬화된다.

### 6.1 application/x-www-form-urlencoded (HTML form 기본값)

```
POST /submit HTTP/1.1
Host: example.com
Content-Type: application/x-www-form-urlencoded
Content-Length: 51
\r\n
name=%EA%B9%80%EB%A9%B4%EC%88%98&age=30
```

**규칙**:
- key=value, `&`로 join
- 공백은 `+` (또는 `%20`), 그 외 비-ASCII는 percent-encode
- **charset은 HTML 페이지의 `<meta charset>`** ★ — 명시적 charset 헤더 권장 안 됨 (`application/x-www-form-urlencoded; charset=UTF-8`은 RFC상 표준 아님)

**운영 함정**: 페이지 charset이 EUC-KR인데 서버 Tomcat이 UTF-8로 decode → 김 → `%B1%E8` → UTF-8 디코딩 시 `?` 로 깨짐.

### 6.2 multipart/form-data (파일 업로드용)

```
POST /upload HTTP/1.1
Host: example.com
Content-Type: multipart/form-data; boundary=----WebKitFormBoundaryAbCdEf
Content-Length: 309
\r\n
------WebKitFormBoundaryAbCdEf\r\n
Content-Disposition: form-data; name="name"\r\n
\r\n
김면수\r\n                                     ← UTF-8 바이트 그대로 (boundary로 구분)
------WebKitFormBoundaryAbCdEf\r\n
Content-Disposition: form-data; name="avatar"; filename="profile.jpg"\r\n
Content-Type: image/jpeg\r\n
\r\n
[binary JPEG bytes...]\r\n
------WebKitFormBoundaryAbCdEf--\r\n
```

**핵심**:
- **boundary**가 part들의 경계. 데이터에 우연히 일치하지 않게 랜덤 prefix `----WebKitFormBoundary...` 사용.
- 각 part가 자신의 mini-header를 가짐. percent-encoding 안 함 — boundary가 구분자 역할.
- 한글 text는 **UTF-8 바이트 그대로** (boundary가 안 깨지면 OK).
- 파일은 binary 그대로.

**왜 form-urlencoded 안 쓰고?** binary 파일을 percent-encode하면 크기가 3배. multipart는 raw binary 그대로 송신 → 효율 +.

### 6.3 application/json

```
POST /api/users HTTP/1.1
Host: example.com
Content-Type: application/json; charset=UTF-8
Content-Length: 33
\r\n
{"name":"김면수","age":30}
```

**바이트 레벨**:
```
7B 22 6E 61 6D 65 22 3A 22  EA B9 80 EB A9 B4 EC 88 98  22 2C 22 61 67 65 22 3A 33 30 7D
{  "  n  a  m  e  "  :  "  [─── "김면수" UTF-8 9 bytes ───]  "  ,  "  a  g  e  "  :  3  0  }
```

**JSON spec (RFC 8259) 의 약속**:
- 기본 charset = **UTF-8**.
- 한글 문자는 두 가지로 표현 가능:
  ```
  옵션 1: UTF-8 raw                    {"name":"김"}
  옵션 2: \uXXXX escape (ASCII safe)   {"name":"김"}
  ```
- 옵션 2는 ASCII-only로 만들고 싶을 때. Java의 `ObjectMapper#writerWithDefaultPrettyPrinter()` 등에서 `WRITE_NON_ASCII_AS_BYTES` 옵션으로 전환.

**왜 JSON이 form보다 좋은가**:
- 중첩 구조 표현 가능 (`{"user":{"name":"김","addr":{"city":"서울"}}}`)
- 타입 구분 (number vs string vs boolean)
- 배열 자연스러움 (`{"tags":["a","b"]}`)
- charset 명시 (`Content-Type: application/json; charset=UTF-8`)

### 6.4 비교표

| | form-urlencoded | multipart | JSON |
|---|---|---|---|
| 용도 | HTML form 기본 | 파일 업로드 | API 통신 |
| 구분자 | `&`, `=` | boundary 문자열 | JSON 문법 (`{`, `:`, `,`) |
| Binary 처리 | percent-encode (3배 팽창) | raw 그대로 | base64 등 별도 필요 |
| 중첩 | 불가 (key=value flat) | flat | 자연스러움 |
| Charset | 페이지 charset (모호) ★ | 각 part에 명시 가능 | UTF-8 표준 |
| 크기 | 작음 | 큼 (boundary 오버헤드) | 중간 |

### 6.5 POST body의 charset 협상 — Content-Type 파라미터의 미묘함

위 3가지 Content-Type 모두 body의 charset 결정 방식이 다르고, 각각 미묘한 함정이 있다.

#### 6.5.1 `application/x-www-form-urlencoded; charset=UTF-8`

```
표준 상태:
   - HTML5 spec: 페이지의 <meta charset> 으로 form 인코딩 결정
   - URL Living Standard (WHATWG): UTF-8 강제 (2016년 이후)
   - 단, Content-Type 헤더에 charset 파라미터를 붙이는 건 RFC 표준 아님
     (RFC 1867 / RFC 7578 모두 charset 파라미터를 form-urlencoded에는 정의 안 함)
   - 일부 클라이언트가 명시적으로 붙이지만 (Spring RestTemplate, Axios)
     서버 측은 charset 파라미터를 신뢰하면 안 됨

브라우저 동작:
   - <meta charset="UTF-8"> + <form> → form 데이터를 UTF-8로 percent-encode
   - Content-Type 헤더: application/x-www-form-urlencoded (charset 없음)
   - 그래도 wire에는 UTF-8 byte의 percent-encoded form

서버 측:
   - Tomcat: useBodyEncodingForURI=true → body charset이 GET query에도 영향
                                    false (기본) → 별개
   - Spring CharacterEncodingFilter: body charset을 강제 UTF-8로 설정
   - request.getParameter() 시 자동 decode

운영 함정:
   1. <meta charset="EUC-KR"> 페이지에서 submit
      → form 데이터가 EUC-KR로 percent-encoded
      → 서버 UTF-8 강제 decode → 깨짐
   2. JavaScript의 fetch + URLSearchParams
      → 자동 UTF-8 (WHATWG 기준)
      → 페이지 charset 무관
```

#### 6.5.2 `application/json; charset=UTF-8` — deprecated 파라미터

```
JSON spec (RFC 8259, 2017):
   §8.1: "JSON text exchanged between systems that are not part of a
          closed ecosystem MUST be encoded using UTF-8."
   → JSON wire format은 **UTF-8 의무**.
   → Content-Type charset 파라미터는 정의됨이 없음 (이전 RFC 7159의 §11 obsolete).

그래서 표준상으로는:
   Content-Type: application/json              ← 충분 (UTF-8 가정)
   Content-Type: application/json; charset=UTF-8  ← 무해하지만 redundant
   Content-Type: application/json; charset=EUC-KR ← 스펙 위반

실제 운영:
   - 거의 모든 framework가 charset=UTF-8을 자동으로 붙임 (안전 위해)
   - Spring `MediaType.APPLICATION_JSON_VALUE` = "application/json"
   - Spring `MediaType.APPLICATION_JSON_UTF8` = "application/json;charset=UTF-8" (deprecated since 5.2)
     → Spring 5.2 (2019)부터 deprecated, charset 파라미터 안 붙이는 게 권장

JSON 안에서 비-ASCII 표현 옵션:
   1. UTF-8 raw byte (권장):
      {"name":"김면수"}
      → wire 크기: ASCII 7바이트 + 한글 9바이트 (3×3) = 16 byte
   2. \uXXXX escape (ASCII-only):
      {"name":"김면수"}
      → wire 크기: ASCII 7바이트 + 한글 18바이트 (\uXXXX × 3) = 25 byte
      → 55% 더 큼. 단, ASCII-safe transport에서 안전 (구식 SMTP gateway 등)

   Jackson 설정:
     ObjectMapper m = new ObjectMapper();
     m.configure(JsonGenerator.Feature.ESCAPE_NON_ASCII, true);
     // → {"name":"김면수"}
     // 기본은 false (UTF-8 raw)
```

#### 6.5.3 `multipart/form-data` — 각 part마다 charset 가능

```
multipart의 우월함: charset이 part 단위로 명시 가능

POST /upload HTTP/1.1
Content-Type: multipart/form-data; boundary=----xyz
\r\n
------xyz\r\n
Content-Disposition: form-data; name="title"\r\n
Content-Type: text/plain; charset=UTF-8\r\n
\r\n
김면수\r\n                            ← UTF-8 byte로 raw 전송
------xyz\r\n
Content-Disposition: form-data; name="legacy"\r\n
Content-Type: text/plain; charset=EUC-KR\r\n
\r\n
[B1 E8 BC BC]\r\n                     ← EUC-KR byte로 raw 전송 (legacy field 호환)
------xyz\r\n
Content-Disposition: form-data; name="file"; filename="resume.pdf"\r\n
Content-Type: application/pdf\r\n
\r\n
[binary PDF bytes...]\r\n
------xyz--\r\n

→ part마다 다른 charset 가능. binary part는 charset 무관.
→ 그러나 실무에서 multipart는 보통 파일 업로드용. text part도 거의 항상 UTF-8.

운영 팁:
   - Spring의 MultipartFile.getBytes() → raw byte
   - String 변환 시 명시적 charset:
       new String(file.getBytes(), StandardCharsets.UTF_8)
   - text part의 charset은 Content-Type 헤더에서 추출 가능
       MultipartFile은 자체 charset getter 없음 — 직접 파싱 필요
```

#### 6.5.4 charset 협상 요약표

```
            | path/query (URL) | form-urlencoded body | JSON body         | multipart text part
────────────┼──────────────────┼───────────────────────┼───────────────────┼─────────────────────
표준         | UTF-8 강제       | 페이지 charset (모호) | UTF-8 강제 (RFC 8259) | part Content-Type
실제 동작     | 모든 브라우저 UTF-8| WHATWG UTF-8 (구현)  | 모든 라이브러리 UTF-8 | 거의 항상 UTF-8
Content-Type | (n/a)            | (charset 안 붙임 권장)| (charset 안 붙임 권장)| 각 part에 명시
서버 결정     | URIEncoding 설정 | CharacterEncodingFilter| UTF-8 (자동)      | part 헤더 파싱
함정          | Tomcat 8 이전 ISO-8859-1| 페이지 charset 차이| Spring 5.2 deprecated| 거의 없음
```

핵심: **byte stream protocol (multipart, JSON UTF-8) 이 모호한 charset 협상 (form-urlencoded) 보다 항상 안전하다.** API 설계 시 JSON 우선, 파일 업로드는 multipart, 레거시 form만 form-urlencoded로 한정.

---

## 7. HTTP/1.1 vs HTTP/2 vs HTTP/3 — 같은 GET이 다르게 직렬화된다

### 7.1 같은 요청, 세 가지 wire format

```
[HTTP/1.1 — Plain Text]

GET /users/김면수 HTTP/1.1\r\n
Host: example.com\r\n
User-Agent: Mozilla/5.0\r\n
Accept: */*\r\n
\r\n

→ ~120 bytes, 사람이 읽을 수 있음
→ tcpdump / Wireshark로 그대로 보임
```

```
[HTTP/2 — Binary Framing + HPACK]

HEADERS frame (type=0x01, stream=1):
  +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
  | Length (24)  | Type=01 | Flags  | R | Stream Identifier  |
  +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
  | HPACK-encoded headers ...                                    |
  +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+

HPACK 인덱싱:
  :method = GET            → static table idx 2     → 1 byte
  :path = /users/%EA...    → literal + Huffman      → ~15 bytes
  :authority = example.com → literal + 캐시          → ~12 bytes
  user-agent = Mozilla...  → 이전 요청에서 dynamic table → 1 byte (재사용)

→ ~30~50 bytes (헤더 재사용 효과 큼)
→ tcpdump엔 binary로만 보임 → Wireshark + TLS keys 필요
```

```
[HTTP/3 — QUIC + QPACK]

QUIC packet (UDP payload):
  - QUIC long header / short header
  - encrypted payload:
      STREAM frame:
        stream_id, offset, data
        data = HTTP/3 HEADERS frame:
          QPACK-encoded headers (HPACK과 유사하지만 ordering 처리 다름)

→ TCP → UDP 변경 (QUIC가 TCP 대체)
→ HTTPS 처음부터 1-RTT (0-RTT도 가능)
→ tcpdump 더 어려움, qlog/qvis 도구 필요
```

### 7.2 각 버전의 직렬화 본질 비교

| | HTTP/1.1 | HTTP/2 | HTTP/3 |
|---|---|---|---|
| **연도** | 1999 (RFC 2616), 2014 (RFC 7230~) | 2015 (RFC 7540) | 2022 (RFC 9114) |
| **Wire format** | Plain text | Binary framing | Binary frames in QUIC streams |
| **헤더 압축** | 없음 (gzip은 body만) | **HPACK** (Huffman + static/dynamic table) | **QPACK** (HPACK 변형) |
| **Multiplexing** | 1 connection = 1 in-flight request (pipelining은 사실상 죽음) | 1 connection, N concurrent streams | 1 QUIC connection, N streams (HOL block 없음) |
| **전송 계층** | TCP | TCP | **UDP + QUIC** |
| **암호화** | 선택 (HTTPS만) | 사실상 필수 (브라우저 강제) | 필수 (QUIC가 TLS 1.3 내장) |
| **HOL blocking** | 있음 (TCP + HTTP) | TCP 레벨엔 있음 (HTTP는 해결) | 완전 해결 (QUIC stream 독립) |

### 7.3 핵심 진화의 트리거

```
HTTP/1.1 (1999) — "한 페이지에 리소스 10개도 안 됐다"
       ↓
       문제: SPA 시대 한 페이지 100+ 리소스, browser 6-conn 한계
       Twitter, Google의 SPDY 실험 (2009~)
       ↓
HTTP/2 (2015) — multiplexing, header 압축
       ↓
       문제: 한 TCP 패킷 손실이 전체 connection block (TCP HOL)
       모바일 환경 패킷 손실 흔함
       ↓
HTTP/3 (2022) — QUIC 위로 옮김. UDP라서 stream별 독립 손실 처리.
```

### 7.4 김면수 query가 어떻게 다르게 보이는가

```
HTTP/1.1 — tcpdump:
  GET /users/%EA%B9%80%EB%A9%B4%EC%88%98 HTTP/1.1
  → percent-encoded ASCII 그대로 보임

HTTP/2 — Wireshark + keys:
  Stream 1, HEADERS:
    :method: GET
    :path: /users/%EA%B9%80%EB%A9%B4%EC%88%98
    :authority: example.com
  → HPACK decode 후엔 똑같이 percent-encoded
  → 단, 같은 헤더가 다른 요청에서 dynamic table로 1바이트로 압축됨

HTTP/3:
  같은 path. QPACK도 same encoding rule (RFC 9204).
  → URL encoding 규칙(RFC 3986)은 HTTP 버전 위 계층 ★
```

**핵심**: percent-encoding은 RFC 3986 — URL 자체의 규칙. HTTP 버전과 **무관**. HTTP/2/3가 바꾼 건 **메시지를 어떻게 wire에 실어 나르는가** 뿐, URL 자체는 동일.

---

## 8. 서버 측 역직렬화 — 바이트가 다시 문자열이 되기까지

### 8.1 Nginx의 처리

```
1. TCP socket에서 byte stream을 받음.
2. ngx_http_parse_request_line(): "GET /users/%EA... HTTP/1.1\r\n" 파싱.
   - method, URI, version 분리.
   - 일부 정규화 (merge_slashes, normalize_uri).
3. URI는 percent-decode를 하지 않음 (raw로 유지) — upstream에 그대로 전달.
   ★ 단, `location` 매칭 시엔 decode된 path 사용.
4. proxy_pass → upstream keepalive pool 경유 → Tomcat에 전달.
```

`location` 매칭 함정:
```nginx
location /users/김 {      # 한글 location 자체는 percent-encoded로 매칭됨
                          # → 사실상 /users/%EA%B9%80 와 매칭
   ...
}
```

### 8.2 Tomcat의 처리

```
1. Acceptor thread가 socket accept().
2. Poller가 byte 도착 감지 (NIO event).
3. Http11Processor.service():
   - request-line 파싱.
   - URI를 charset으로 decode (★ URIEncoding 설정 결정).
     server.xml: <Connector URIEncoding="UTF-8" />
     Spring Boot: server.tomcat.uri-encoding=UTF-8 (기본값 8 버전부터 UTF-8)
4. Header 파싱 — `\r\n` 로 분리.
5. Body 파싱 — Content-Type에 따라:
   - form-urlencoded → parameter map (queryString과 합쳐)
   - multipart → @MultipartConfig 또는 Spring MultipartResolver
   - JSON → HttpMessageConverter (Jackson)
6. HttpServletRequest 객체로 만들어 Servlet/Spring에 전달.
```

### 8.3 Spring의 추가 처리

```
Spring MVC가 @RequestParam, @PathVariable, @RequestBody로 변환할 때
한 번 더 charset 처리가 들어간다.

@GetMapping("/users/{name}")
public User get(@PathVariable String name) {
    // name = "김면수"
    // 만약 Tomcat URIEncoding=ISO-8859-1 이고 brower UTF-8이면
    // name = "ê¹€ë©´ìˆ˜" (모지바케)
}

해결: CharacterEncodingFilter 등록.
@Bean
public FilterRegistrationBean<CharacterEncodingFilter> charsetFilter() {
    CharacterEncodingFilter filter = new CharacterEncodingFilter();
    filter.setEncoding("UTF-8");
    filter.setForceEncoding(true);   // request + response 모두 강제
    return new FilterRegistrationBean<>(filter);
}
```

Spring Boot는 이걸 자동 설정한다 (`spring.servlet.encoding.charset=UTF-8`, `force=true`가 기본).

### 8.4 JDBC 한 줄이 추가로 망가뜨릴 수 있다

```
"김면수" → DB로 들어가는 마지막 charset 결정:

PostgreSQL:
  URL: jdbc:postgresql://localhost/db
  → 클라이언트 인코딩은 DB의 client_encoding 또는 PGCLIENTENCODING 환경변수.
  → 보통 UTF-8 (DB default).

MySQL (특히 5.x):
  URL: jdbc:mysql://localhost/db?useUnicode=true&characterEncoding=UTF-8
                                   ─────────────  ──────────────────────
                                   필수            필수
  → 빼먹으면 connector가 server 의 default character set 사용 → latin1일 수도.

  ★ MySQL 의 가장 흔한 모지바케 원인:
  1. JDBC URL에 characterEncoding 누락 → 클라이언트 ↔ 서버 charset 불일치.
  2. 테이블 charset이 utf8mb3 (구 utf8) → 4-byte 이모지 못 저장 (??로 변환).
     → utf8mb4 필요.
  3. 컬럼 COLLATE 가 latin1_swedish_ci → 한글 정렬 깨짐.
```

### 8.5 인코딩 일치 체크리스트 (전 stack)

```
[ ] HTML page charset       <meta charset="UTF-8">
[ ] HTTP request encoding   브라우저가 자동 (URL은 UTF-8, form은 페이지 따라)
[ ] Nginx                   기본 그대로 전달 (별 설정 없음)
[ ] Tomcat URIEncoding      UTF-8 (Tomcat 8+ 기본값)
[ ] Servlet request charset CharacterEncodingFilter forceEncoding=true
[ ] DB JDBC URL             useUnicode=true&characterEncoding=UTF-8 (MySQL)
[ ] DB column charset       utf8mb4 (MySQL) / UTF8 (PostgreSQL)
[ ] DB connection           client_encoding = UTF-8
[ ] HTTP response           Content-Type: ...; charset=UTF-8
[ ] Logging                 file.encoding=UTF-8 (JVM 시작 옵션)
```

**한 곳이라도 어긋나면** → 그 경계가 모지바케 발생점.

---

## 9. 운영 — URL 길이 제한, 보안, 모지바케 7대 패턴

### 9.1 URL 길이 제한

```
구성요소           제한                  비고
─────────         ──────              ──────────────────────────
브라우저 IE        2,083 chars         가장 엄격, 레거시
브라우저 Chrome   ~32k                 실용상 거의 무제한
브라우저 Firefox  ~65k                 ↑
Nginx             기본 8k              large_client_header_buffers
Apache HTTPD      8190 chars          LimitRequestLine
Tomcat            기본 8k              maxHttpHeaderSize
AWS ALB           16k                  HTTP request line
CloudFront        8k                   URL + query
DB query         (전혀 무관)            서버에서 처리 단계
```

**왜 한계가 다른가**:
- HTTP RFC는 길이 제한을 정의하지 않음 (RFC 9110 §4.1: "no predefined limit on the length of a request-line").
- 각 구현체가 buffer 크기를 고정해서 제한이 생김 — buffer 키우면 메모리 더 씀.
- IE의 2083은 IE 팀이 1996년에 임의 결정한 값. 다른 브라우저는 따라가다 폐기.

**실무 함정**:
```
Tomcat 8k 가 막혀서 414 Request-URI Too Long 발생
→ 일반적으로 query parameter 많을 때 (검색, 필터)
→ 해결: POST body로 옮기거나 maxHttpHeaderSize 키우기
```

### 9.2 URL 보안 — 인코딩 우회 공격

**Double-encoding bypass**:
```
정상 입력: ../../etc/passwd
WAF 차단 룰: "../" 패턴 필터

공격자 입력 (single encoded): %2E%2E%2F = "../" (URL decode 1번)
→ WAF가 decode 후 검사 → 차단됨.

공격자 입력 (double encoded): %252E%252E%252F
→ WAF가 1번 decode: "%2E%2E%2F"
→ "../"  아님, 통과.
→ 백엔드 앱이 2번 decode (또는 Tomcat이 다시 한 번): "../"
→ Path traversal 성공.

방어: WAF가 recursive decode + 결과 normalize 한 후 검증.
```

**Path normalization 차이**:
```
같은 path가 컴포넌트마다 다르게 normalize:
  /a/./b/../c     → /a/c        (RFC 3986 dot-segment 제거)
  /a%2F./b/../c   → ???         (%2F는 / 와 동일? 다름?)

Nginx merge_slashes on (default):
  //a/b → /a/b
Nginx merge_slashes off:
  //a/b → //a/b   (Tomcat이 다르게 해석 가능)

이 normalization 차이가 CVE 사례 다수:
  - CVE-2017-5638 (Struts2): Content-Type 헤더 OGNL injection
  - CVE-2021-44228 (Log4Shell): ${jndi:...} JNDI lookup (인코딩 우회 가능)
  - HTTP Request Smuggling: Nginx와 backend의 Content-Length/Transfer-Encoding 해석 차이
```

**규칙**: WAF / proxy / app server는 **동일한 normalization** 을 해야 안전. 한 곳이 더 관대하면 거기서 우회 가능.

### 9.3 모지바케 7대 패턴 — 실무 진단표

| 증상 | 원인 | 해결 |
|---|---|---|
| URL의 한글이 `???` 로 들어옴 | Tomcat URIEncoding 미설정 | `server.tomcat.uri-encoding=UTF-8` |
| POST body 한글이 `?` | CharacterEncodingFilter 없음 | Spring Boot 기본 활성 / 직접 등록 |
| DB에 저장된 한글이 깨짐 | JDBC URL의 characterEncoding 누락 (MySQL) | `?useUnicode=true&characterEncoding=UTF-8` |
| DB에서 읽은 한글이 깨짐 | 테이블 charset이 latin1 | `ALTER TABLE ... CONVERT TO CHARACTER SET utf8mb4` |
| 응답 body는 정상인데 브라우저가 깨뜨림 | `Content-Type: text/html` (charset 없음) | `Content-Type: text/html; charset=UTF-8` |
| `ê¹€ë©´ìˆ˜` 패턴 | UTF-8을 ISO-8859-1로 decode | 어느 단계에서 잘못 decode 하는지 추적 |
| `?` 또는 `□` 한 글자 | encode 단계에서 알 수 없는 코드포인트 → replacement char | charset upgrade (utf8 → utf8mb4) |

---

## 10. 측정·진단 — 실전 도구

### 10.1 curl -v — 가장 빠른 검증

```bash
$ curl -v "https://example.com/users/김면수?role=관리자"

* Trying 93.184.216.34:443...
* TLS 1.3 ...
> GET /users/%EA%B9%80%EB%A9%B4%EC%88%98?role=%EA%B4%80%EB%A6%AC%EC%9E%90 HTTP/1.1
> Host: example.com
> User-Agent: curl/8.0.1
> Accept: */*
>
< HTTP/1.1 200 OK
< Content-Type: text/html; charset=UTF-8
```

`-v` 가 보여주는 것:
- 브라우저처럼 자동 percent-encoding (curl도 똑같이).
- request-line 그대로.
- response Content-Type의 charset.

`--data-urlencode` 로 명시적 인코딩 검증:
```bash
$ curl -G --data-urlencode "name=김면수" https://example.com/users -v
> GET /users?name=%EA%B9%80%EB%A9%B4%EC%88%98 HTTP/1.1
```

### 10.2 tcpdump — wire에 실린 실제 바이트

```bash
$ sudo tcpdump -i any -A -s 0 'tcp port 80'
   # -A : print ASCII
   # -s 0 : no truncate

  ...
  GET /users/%EA%B9%80%EB%A9%B4%EC%88%98 HTTP/1.1
  Host: example.com
  ...
```

HTTPS는? — TLS keys를 export하여 Wireshark 에서 decode:
```bash
$ SSLKEYLOGFILE=/tmp/sslkeys.log curl https://example.com/users/김면수
# Wireshark > Edit > Preferences > Protocols > TLS > (Pre)-Master-Secret log file
```

HTTP/2 binary frame은 tcpdump로는 raw byte만 보임 → Wireshark + TLS keys 필수.

### 10.3 iconv / hexdump — 바이트 ↔ 문자열 변환 검증

```bash
# "김면수" 의 UTF-8 바이트 확인
$ echo -n "김면수" | xxd
00000000: eab9 80eb a9b4 ec88 98                  .........

# 다른 charset으로 변환했을 때 모지바케 재현
$ echo -n "김면수" | iconv -f UTF-8 -t EUC-KR | xxd
00000000: b1e8 b8e9 bcf6                          ......

# 잘못된 charset 으로 decode 했을 때 결과
$ echo -n "김면수" | iconv -f UTF-8 -t LATIN1 2>&1
iconv: illegal input sequence at position 0
# (latin1 에 없는 바이트라서 실패. JVM은 보통 replacement char로 대체)

$ printf '\xea\xb9\x80\xeb\xa9\xb4\xec\x88\x98' | iconv -f ISO-8859-1 -t UTF-8
ê¹ë©´ìˆ                # ← 클래식 모지바케
```

### 10.4 Python으로 빠르게 검증

```python
from urllib.parse import quote, unquote, urlparse, parse_qs

url = "https://example.com/users/김면수?role=관리자"

# 파싱
p = urlparse(url)
print(p.scheme)    # https
print(p.netloc)    # example.com
print(p.path)      # /users/김면수
print(p.query)     # role=관리자

# URL-safe 형태로 인코딩
encoded_path = quote(p.path)
print(encoded_path)  # /users/%EA%B9%80%EB%A9%B4%EC%88%98

# query parsing
print(parse_qs(p.query))  # {'role': ['관리자']}

# 한글 → 바이트 → percent
text = "김면수"
utf8_bytes = text.encode('utf-8')
print(utf8_bytes.hex())              # 'eab980eba9b4ec8898'
print(quote(utf8_bytes))             # '%EA%B9%80%EB%A9%B4%EC%88%98'

# IDN punycode
import idna
print(idna.encode('한국.kr').decode())   # xn--3e0b707e.kr
```

### 10.5 Java 측 검증

```java
import java.net.URLEncoder;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;

// "김면수" 의 UTF-8 percent-encoding
String encoded = URLEncoder.encode("김면수", StandardCharsets.UTF_8);
System.out.println(encoded);    // %EA%B9%80%EB%A9%B4%EC%88%98

// 바이트 확인
byte[] bytes = "김면수".getBytes(StandardCharsets.UTF_8);
for (byte b : bytes) System.out.printf("%02X ", b);
// EA B9 80 EB A9 B4 EC 88 98

// 잘못 decode 시뮬레이션 (UTF-8 → ISO-8859-1)
String mojibake = new String(bytes, StandardCharsets.ISO_8859_1);
System.out.println(mojibake);   // ê¹€ë©´ìˆ˜ (전형 모지바케)

// 복구
byte[] recovered = mojibake.getBytes(StandardCharsets.ISO_8859_1);
String original = new String(recovered, StandardCharsets.UTF_8);
System.out.println(original);   // 김면수 ← 복구
```

### 10.6 Spring 환경에서 한 번에 확인

```bash
# Spring Boot 의 charset 설정 확인
curl http://localhost:8080/actuator/env | jq '.propertySources[].properties | with_entries(select(.key | test("encoding|charset"; "i")))'

# 실제 요청의 charset 추적
curl -v "http://localhost:8080/users/김면수" 2>&1 | grep -i charset

# Tomcat URIEncoding 확인 (debug log)
logging.level.org.apache.tomcat.util.http=DEBUG
```

---

## 11. 🏢 운영 시나리오

### 시나리오 A: "검색 결과 페이지에서 한글 keyword가 ??? 로 나옴"

```
증상:
  GET /search?q=김면수 → 결과 페이지에 "??? 검색 결과"
  DB에는 "김면수" 가 정상 저장돼 있음

추적:
  1. curl -v 로 확인 — 브라우저는 정상 percent-encoding.
     GET /search?q=%EA%B9%80%EB%A9%B4%EC%88%98 ✓
  2. Tomcat 로그 (DEBUG):
     parameter q = "ê¹€ë©´ìˆ˜"   ← 이미 깨짐
  3. Tomcat 8.5 이전 버전이거나 URIEncoding 미설정 가능성.

해결:
  server.xml: <Connector URIEncoding="UTF-8" />
  또는 Spring Boot: server.tomcat.uri-encoding=UTF-8
```

### 시나리오 B: "POST 폼은 정상인데 GET 쿼리만 깨짐"

```
원인:
  POST body는 CharacterEncodingFilter 가 처리 (forceEncoding=true).
  GET 쿼리는 request-line 단계 → Filter 도달 전에 이미 Tomcat이 파싱.
  → Tomcat URIEncoding 이 GET 쿼리 charset 결정.

해결:
  - GET 도 UTF-8 로 처리하려면 URIEncoding=UTF-8 + useBodyEncodingForURI=false (기본)
  - Spring Boot 는 1.x 이후 자동 설정
```

### 시나리오 C: "JSON API 의 한글이 \uXXXX 로 escape 되어 응답이 비대"

```
증상:
  {"name":"김면수"}    ← 9 chars per Korean character
  대신
  {"name":"김면수"}                  ← 3 chars

원인:
  Jackson 의 WRITE_NON_ASCII_AS_BYTES 옵션이 false (기본 false 인데 일부 설정에서 활성).
  또는 Jackson 의 CharacterEscapes 가 한글을 unicode escape로 강제.

해결:
  Spring: spring.jackson.default-property-inclusion=non_null 외엔 설정 불필요.
          Jackson 기본은 UTF-8 raw.
  Content-Type: application/json; charset=UTF-8 명시.
```

### 시나리오 D: "Nginx 로그에 url 이 %EA%B9%80... 로 보임. 한글로 보고 싶음"

```bash
# Nginx access log format은 raw URI 기록 (decode 안 함, 안전상 정상).
# 로그 분석 시 decode:

awk '{print $7}' access.log | python3 -c "
import sys
from urllib.parse import unquote
for line in sys.stdin:
    print(unquote(line.strip()))
"

# 또는 ELK 의 Logstash 에서:
#   filter { urldecode { field => "request" } }
```

### 시나리오 E: "MySQL 에 저장은 됐는데 select 시 ??? 로 나옴"

```
체크리스트:
  1. JDBC URL: ?useUnicode=true&characterEncoding=UTF-8&useServerPrepStmts=true
  2. DB charset:
     SHOW VARIABLES LIKE 'character_set%';
     → character_set_client / connection / database / results / server 모두 utf8mb4
  3. 테이블 charset:
     SHOW CREATE TABLE users;
     → CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  4. Connection init SQL: SET NAMES utf8mb4;
     → JDBC 가 자동 실행 (characterEncoding=UTF-8 시).
```

### 시나리오 F: "Content-Disposition 헤더의 한글 파일명이 윈도우 IE 에서 깨짐"

```
잘못된 방법:
  Content-Disposition: attachment; filename="김면수.pdf"
  → IE 는 ISO-8859-1 해석 → 모지바케

올바른 방법 (RFC 5987):
  Content-Disposition: attachment; filename="report.pdf"; filename*=UTF-8''%EA%B9%80%EB%A9%B4%EC%88%98.pdf
                                   ─── ASCII fallback ───  ─── UTF-8 명시 + percent-encoded ───

Spring:
  ContentDisposition.attachment()
    .filename("김면수.pdf", StandardCharsets.UTF_8)
    .build().toString();
```

### 시나리오 G: "WAF 우회 공격 시도 — double-encoding"

```
공격자 입력:
  GET /api?path=%252E%252E%252Fetc%252Fpasswd

WAF 1차 decode:
  path=%2E%2E%2Fetc%2Fpasswd
  → "../" 패턴 없음 → 통과

App 서버가 2차 decode:
  path=../etc/passwd
  → File API 가 read → 권한이 있다면 노출

방어:
  - WAF 가 recursive decode 후 검증.
  - App 서버에서 normalize 후 절대 경로 검증 (canonical path).
  - File path 입력은 whitelist (특정 파일만 접근).
```

### 시나리오 H: "API endpoint URL 길이 초과로 414 Request-URI Too Long"

```
증상:
  GET /search?ids=1,2,3,...,500   ← 8KB 넘음
  Tomcat: 414 Request-URI Too Long

해결 옵션:
  1. maxHttpHeaderSize 증가:
     server.max-http-header-size=16KB
     (메모리 사용량 증가, DOS 위험 약간)
  2. GET → POST 로 변경, ids 를 body 에:
     POST /search
     {"ids":[1,2,3,...,500]}
  3. ID 압축 (range encoding, hash):
     /search?ids=1-100,200-300   (50% 감소)
```

### 시나리오 I: "Slack에 한글 URL 붙여넣으면 %EA%B9%80... 으로 변환되어 보임"

```
관찰:
  사용자가 채팅창에 입력: https://example.com/users/김면수
  메시지 전송 후 보이는 URL: https://example.com/users/%EA%B9%80%EB%A9%B4%EC%88%98

내부 동작:
  1. Slack 클라이언트가 텍스트 전송 시 URL detection 모듈 실행.
  2. URL detected → RFC 3987 (IRI) → RFC 3986 (URI) 변환 적용:
     - hostname 부분: IDN punycode 변환 (라틴이면 그대로)
     - path/query 부분: UTF-8 byte → percent-encoding
  3. 변환된 ASCII-safe URL을 message 본문에 저장.
  4. 받는 사용자에게는 percent-encoded form이 보임.
     (단, hover 또는 link unfurl 시 IRI form으로 다시 표시 가능)

왜 그렇게 하는가:
  - 메시지가 fan-out되며 다양한 OS/locale/client (web, iOS, Android, desktop) 거침.
  - raw 한글 URL은 일부 환경 (Android 구버전 WebView, 윈도우 IE/Edge 레거시) 에서 깨질 위험.
  - ASCII-safe URL은 어디서나 클릭 가능 보장.
  - 또 link preview, archive, search index에 일관된 form으로 저장.

같은 패턴:
  - GitHub README의 markdown link: [텍스트](URL) 의 URL이 자동 percent-encoding됨
  - Notion, Confluence, 모든 messaging app: 동일
  - 이메일 클라이언트 (Gmail, Outlook): URL detect 후 percent-encoding
```

### 시나리오 J: "검색엔진 크롤러가 percent-encoded URL과 raw 한글 URL을 같은 페이지로 dedup"

```
관찰:
  같은 페이지를 두 가지 URL로 publish:
    - https://example.com/users/김면수             (raw, sitemap에 적힌 IRI form)
    - https://example.com/users/%EA%B9%80%EB%A9%B4%EC%88%98  (link에서 percent-encoded form)
  Google Search Console에 "duplicate content" 경고 안 뜸.
  실제로는 두 URL이 같은 페이지로 indexed.

내부 동작 (Googlebot URL normalization, RFC 3986 §6 기반):
  1. scheme/host lowercase.
  2. default port 제거 (https:443, http:80).
  3. dot-segment 정리 (/./, /../).
  4. percent-encoded unreserved 복원:
     - %41 → 'A' (unreserved → escape 제거)
     - %EA → 그대로 (unreserved 아님 → 유지)
  5. IRI → URI 변환:
     - raw 한글 byte를 UTF-8로 가정 → percent-encoding 적용
     - 결과: 두 URL이 모두 같은 canonical form으로 수렴
  6. canonical URL을 hash key로 사용 → 같은 페이지로 dedup.

운영 함정:
  - 일관되지 않은 URL form은 SEO score를 분산시킴 (canonical 안 되는 코너 케이스)
  - <link rel="canonical" href="..."> 에는 항상 일관된 form 사용 (보통 percent-encoded).
  - sitemap.xml은 UTF-8 XML이라 raw 한글 가능 — Googlebot이 변환.
  - Open Graph (og:url) 도 마찬가지.

비교 — 영문 URL:
  영문 path는 변환할 게 없으므로 normalization이 단순.
  한글 URL을 사용하는 운영자는 normalize-then-compare의 복잡도를 의식해야 함.
```

### 시나리오 K: "Cloudflare가 IDN homograph attack 방지로 punycode 표시"

```
관찰:
  사용자가 Cloudflare로 protect되는 사이트 접속 시,
  주소창에 한국.kr 가 아닌 xn--3e0b707e.kr 로 표시되는 경우.
  또는 Chrome 자체가 의심 도메인을 punycode로 강제 표시.

배경 — homograph attack:
  apple.com  (라틴 a, U+0061)
  аpple.com  (키릴 а, U+0430)
  → 시각적 거의 동일.
  → 라틴 a를 키릴 а로 치환한 가짜 도메인 등록.
  → 피싱 사이트로 redirect.

  punycode 형태:
    apple.com           (ASCII 그대로)
    xn--pple-43d.com    (punycode encoded)
  → 이제 명백히 다른 도메인.

방어 메커니즘 — 다층 방어:
  1. DNS 등록 기관 (NIC.kr 등):
     - 같은 script (라틴, 한글, 한자) 안의 글자만 허용
     - 라틴+키릴 혼용 도메인 등록 거부
     - IDN Variant Table 관리
  2. 브라우저 (Chrome, Firefox):
     - IDN spoofing detection
     - 의심 패턴 감지 시 punycode 강제 표시
     - 예: 사용자 OS locale이 ko가 아닌데 한글 도메인 → punycode 표시
  3. WAF (Cloudflare, Akamai):
     - IDN protection 룰
     - 의심 도메인 차단 또는 경고
     - 보호 사이트에서 incoming link의 referrer가 의심 IDN이면 차단

운영 영향:
  - 정상 IDN (한국.kr) 도 일부 환경에서 punycode로 표시될 수 있음 (false positive).
  - 영문 alias 도메인을 함께 등록 권장 (korea.kr 같은).
  - HTTPS 인증서는 SAN에 두 form 모두 포함:
    DNS:한국.kr, DNS:xn--3e0b707e.kr
  - 사용자에게 URL을 공유할 때 두 form 모두 작동해야 함.
```

---

## 12. 꼬리질문 — 면접 시뮬레이션

### Q1. 주소창에 `https://example.com/users/김면수` 를 친 순간부터 서버 도착까지 일어나는 일을 단계별로 설명하세요.

> 6단계입니다.
> ① 텍스트 "김면수"가 유니코드 코드포인트 [U+AE40, U+BA74, U+C218]로 표현됨.
> ② 각 코드포인트가 UTF-8 transfer encoding 규칙에 따라 3바이트씩 [EA B9 80][EB A9 B4][EC 88 98] 9바이트로 변환.
> ③ ASCII 외 바이트라서 percent-encoding 적용 → "%EA%B9%80%EB%A9%B4%EC%88%98".
> ④ HTTP request-line 으로 조립: "GET /users/%EA... HTTP/1.1\r\nHost: example.com\r\n\r\n".
> ⑤ ASCII 메시지를 socket 에 byte stream으로 write.
> ⑥ 커널 TCP/IP stack 이 MSS 단위 segment 로 분할 송신.
> 서버는 정확히 역순. 어느 단계에서 charset 불일치가 생기면 그 지점이 모지바케 발생점입니다.

**🪝 Q1-1: 왜 굳이 percent-encoding 이 필요한가요? URL 도 그냥 UTF-8 바이트로 보내면 안 되나요?**

> RFC 3986 의 URL 정의가 ASCII printable 문자만 허용하기 때문입니다. 1994년 RFC 1738 시절 URL 은 텔레타이프 시대 ASCII 환경에서 메일·뉴스 헤더 등에 박혀 다녔어요. URL 안에 raw byte 가 들어가면 헤더 파서 (SMTP, HTTP 1.0) 가 깨질 위험이 있었고, 무엇보다 `/`, `?`, `&`, `=` 같은 구분자와 데이터 바이트가 충돌해서 파싱이 불가능. 그래서 ASCII safe 한 `%HH` 형식으로 escape 한 겁니다.

**🪝🪝 Q1-1-1: 그러면 IRI (Internationalized Resource Identifier, RFC 3987) 는 비-ASCII 문자를 직접 허용하잖아요?**

> 맞습니다. IRI 는 표시용·논리 식별자용으로 비-ASCII 허용. 하지만 wire 에 송신할 때는 IRI → URI 변환 (= percent-encoding) 을 거치게 명시 (RFC 3987 §3.1). 결국 네트워크에 흐르는 건 URI. IRI 는 사용자 인터페이스용 추상 표현일 뿐, 직렬화 단계에서는 percent-encoding 으로 재귀.

### Q2. `김` 한 글자가 `%EA%B9%80` 으로 변환되는 과정을 비트 레벨로 설명하세요.

> '김' 의 유니코드 코드포인트는 U+AE40. 이는 U+0800 ~ U+FFFF 범위라서 UTF-8 3바이트 시퀀스 패턴 `1110xxxx 10xxxxxx 10xxxxxx` 에 매핑됩니다. AE40 을 16비트로 풀면 1010 1110 0100 0000. 이걸 4-6-6 비트로 잘라서 패턴에 채우면 1110_1010 1011_1001 1000_0000 = 0xEA 0xB9 0x80. 마지막으로 각 바이트를 percent + 2자리 hex 로 표현: %EA%B9%80.

**🪝 Q2-1: UTF-8 이 한글에 항상 3바이트인가요? 4바이트도 있나요?**

> 한글 음절(가~힣, U+AC00~U+D7A3) 은 모두 3바이트입니다. 하지만 한글 자모 분리 (U+1100~U+11FF) 도 3바이트, 보충 글자 (U+1xxxx, 한자 확장 등) 는 4바이트. 그리고 이모지 (U+1F600 등) 도 4바이트라 MySQL 의 utf8mb3 (구 utf8) 가 이모지 저장 못 하는 이슈가 생긴 겁니다. utf8mb4 가 진짜 UTF-8.

### Q3. CRLF 가 왜 필요한가요? `\n` 만 쓰면 안 되나요?

> 1960년대 ASCII 가 텔레타이프 기준으로 설계됐어요. 캐리지 리턴 `\r` (커서 줄 처음) + 라인 피드 `\n` (종이 한 줄 위로) 두 동작이 물리적으로 분리. 텔레타이프는 둘 다 보내야 줄바꿈. 이게 그대로 네트워크 프로토콜(SMTP, FTP, HTTP) 에 박혔습니다. RFC 9112 도 "the line terminator is CRLF" 라고 명시. 다만 관대한 파서 권고로 `\n` 만 와도 받는 구현체가 많습니다. 보안상 중요: 사용자 입력에 `\r\n` 이 들어가면 가짜 헤더 주입 (CRLF injection) 공격.

**🪝 Q3-1: CRLF injection 의 실제 예를 들어주세요.**

> Set-Cookie 헤더에 사용자 입력을 그대로 넣는 경우입니다. 예를 들어 `name = user_input` 일 때 user_input 이 `foo\r\nLocation: http://evil.com` 이면 응답이 `Set-Cookie: name=foo\r\nLocation: http://evil.com` 으로 나가서 브라우저가 evil.com 으로 redirect. 방어는 헤더 값에서 `\r\n` 필터링 + 모든 헤더 값에 quote 사용.

### Q4. HTTP/2 가 HPACK 으로 헤더를 압축하면 URL 의 percent-encoding 은 어떻게 되나요?

> percent-encoding 은 RFC 3986 — URL 레이어의 규칙입니다. HTTP/2 의 HPACK 은 그 위에 한 겹 더 입혀지는 메시지 압축 레이어. path pseudo-header (`:path`) 의 값은 여전히 percent-encoded ASCII 문자열. HPACK 은 이 ASCII 문자열을 Huffman code 또는 static/dynamic table indexing 으로 짧게 표현할 뿐. 풀어보면 다시 `/users/%EA%B9%80...` 입니다. 즉, URL 인코딩과 HTTP 메시지 인코딩은 서로 다른 계층.

**🪝 Q4-1: dynamic table 이란?**

> connection 별로 유지되는 헤더 캐시입니다. 같은 connection 에서 두 번째 요청부터 이전에 보낸 헤더는 1바이트 인덱스로 참조 가능. 예: `User-Agent: Mozilla/5.0 ...` 같이 긴 헤더가 매 요청 100바이트 → 처음만 100바이트, 이후엔 1바이트. HTTP/2 가 connection 재사용을 강하게 권장하는 이유 중 하나.

**🪝🪝 Q4-1-1: dynamic table 의 문제점은?**

> CRIME / HEARTBLEED 같은 압축 사이드채널 공격 가능성. 공격자가 헤더 값 일부를 조작해서 dynamic table 인덱싱 결과로 secret 값을 추측. HPACK 은 RFC 7541 의 "never indexed" 플래그로 sensitive 헤더 (Cookie, Authorization) 는 인덱싱 안 하게 권고. 또 메모리 사용량 — table 크기 제한 (`SETTINGS_HEADER_TABLE_SIZE`) 으로 DoS 방어.

### Q5. application/x-www-form-urlencoded 와 multipart/form-data 의 charset 결정 방식이 어떻게 다른가요?

> form-urlencoded 는 HTML 페이지의 charset (`<meta charset>`) 으로 결정됩니다. RFC 표준은 명확하지 않고, 사실상 페이지 charset 을 따르는 게 브라우저 합의. 그래서 페이지가 EUC-KR 이면 form submit 시 한글이 EUC-KR 로 percent-encoded — `김` 이 `%B1%E8`. multipart 는 각 part 가 자신의 Content-Type charset 을 선언할 수 있어 더 명시적. text part 라면 `Content-Type: text/plain; charset=UTF-8`. 운영에서 form-urlencoded 의 charset 모호성이 모지바케 주범 1순위입니다.

**🪝 Q5-1: 그럼 Spring 에서 어떻게 처리하나요?**

> `CharacterEncodingFilter(encoding="UTF-8", forceEncoding=true)` 를 등록합니다. forceEncoding=true 가 request 와 response 둘 다 UTF-8 로 강제. Spring Boot 1.x 부터 자동 설정 (`spring.servlet.encoding.charset=UTF-8`, `force=true`). 단, 이 Filter 는 body 만 처리. URL query string 은 Tomcat URIEncoding 이 별도로 결정.

### Q6. 같은 URL 인데 Java URLEncoder.encode 와 브라우저 결과가 다른 경우가 있나요?

> 있습니다. Java URLEncoder 는 원래 HTML form (`application/x-www-form-urlencoded`) 용으로 설계 — 공백을 `+` 로 인코딩. 반면 브라우저 URL bar 의 path 인코딩은 RFC 3986 — 공백을 `%20` 으로. 그래서 path 에 `URLEncoder.encode("a b", "UTF-8")` 쓰면 `a+b` 가 나와서 잘못된 URL. path 는 `URI.create()` 또는 `URLEncoder` 결과에서 `+` → `%20` 치환 필요. 또 unreserved 문자 (`-`, `_`, `.`, `~`) 의 처리도 살짝 달라요. Java URLEncoder 는 `*` 를 안 escape 하지만 RFC 3986 sub-delim 이라 path 에선 보통 안 escape — 약간 회색지대.

**🪝 Q6-1: 그럼 URL 만들 때 정확히 어떤 API 를 써야 하나요?**

> Java 11+ 의 `URI` constructor 또는 `URI.create()` + 명시적 컴포넌트 빌더 사용. Spring 환경이면 `UriComponentsBuilder.fromUriString(...).queryParam(...).build().encode().toUriString()` — 정확히 RFC 3986 path/query 규칙 따라 인코딩. URLEncoder 는 form 데이터용 (`application/x-www-form-urlencoded` body 만들 때) 으로 한정해 쓰는 게 깔끔합니다.

### Q7. (Killer) `-Xmx2g` JVM 의 Spring 앱이 한글 검색 시 random 하게 모지바케가 발생합니다. 진단 절차?

> 5단계로 추적합니다.
> ① **재현 조건 좁히기** — 특정 글자만? 모든 한글? 새 요청만 깨지는지, 캐시된 응답까지 깨지는지. tcpdump 로 wire bytes 확인 — 브라우저는 정상 보내는지.
> ② **각 계층 검증** — curl 로 같은 URL 시도 (브라우저 의존성 제거). Nginx access log 의 raw URI 확인 (Nginx 가 변형 안 함). Tomcat 의 request.getCharacterEncoding() 로깅.
> ③ **JVM file.encoding** — `-Dfile.encoding=UTF-8` 누락 시 OS locale 따라 동작. 컨테이너 (alpine, slim) 는 기본 locale 이 POSIX (= ASCII) 라서 String → byte 변환에 영향.
> ④ **랜덤성의 원인** — HikariCP 의 connection 마다 charset 다를 가능성. JDBC URL 의 characterEncoding 누락 + 일부 connection 만 `SET NAMES utf8` 호출. Connection init SQL 로 강제.
> ⑤ **GC / classloader 의존 안 함** — String 자체는 stable. encoding lookup table (Charset.forName) 도 stable. 의심해야 할 건 외부 dependency (특히 JNI 호출되는 native charset 변환) 또는 thread-local stale encoding (rare).
> 결론: 90% 는 ④번 (DB connection 단계 charset 누락). 5% 는 ③번 (`file.encoding`). 1% 는 정말 randomness — 동시 여러 charset 핸들러가 race.

**🪝 Q7-1: -Dfile.encoding=UTF-8 이 왜 그렇게 중요한가요? URL 처리와 직접 관계 없잖아요?**

> JVM 의 기본 charset 이 OS locale 에서 추론됩니다. file.encoding 미설정 + alpine 컨테이너 (locale=C.UTF-8 또는 POSIX) → 기본 charset 이 US-ASCII 로 fallback 가능. 그러면 `new String(bytes)` (charset 인자 없는 생성자) 가 ASCII 로 decode → 모든 비-ASCII 가 `?`. URL handling 코드가 어디선가 이 생성자를 쓰면 random 모지바케. JDK 18 (JEP 400) 부터 default UTF-8 로 고정 — 그래서 18+ 에서는 이 문제 거의 사라짐.

### Q8. (패턴 통찰) "한 계층의 charset 가 어긋나면 거기서 모지바케" 라는 원칙이 다른 어디서 반복되나요?

> "타입/형식 변환이 일어나는 모든 경계" 에서 반복됩니다.
> - **DB column type**: `VARCHAR(latin1)` 에서 `VARCHAR(utf8mb4)` 로 마이그레이션 시 — 변환 charset 명시 안 하면 깨짐.
> - **메시지 큐**: Kafka producer 가 String → byte 변환 시 charset. consumer 가 같은 charset 으로 decode 해야 일치.
> - **Protocol Buffers / Avro**: schema 의 string 필드는 UTF-8 강제 (binary 직렬화라 charset 모호성 없음 — 이게 장점).
> - **HTTP Content-Encoding (gzip)**: 압축/해제 charset 도 명시 필요.
> - **OS 파일 시스템**: 파일명 charset. Linux 는 byte sequence, macOS 는 UTF-8 NFD, Windows 는 UTF-16. 크로스 플랫폼 파일 동기화 (Dropbox, NAS) 시 모지바케.
> - **HTML parsing**: `<meta charset>` 선언 전에 비-ASCII 가 나오면? 브라우저는 BOM 또는 휴리스틱으로 추측.
>
> 통찰: **"raw byte ↔ 의미 있는 text 변환은 charset 계약이 필요하다"** 가 본질. JSON 이 UTF-8 강제로 단순화한 이유, Protocol Buffers 가 binary 로 간 이유, 모두 charset 모호성 제거가 동기. **계층 간 명시적 charset 계약** 이 모지바케 제거의 유일한 방법.

---

## 13. 학습 체크리스트

면접 전 백지에서 다음을 다 해낼 수 있어야 마스터:

- [ ] **서장**: "왜 한글을 URL에 그대로 못 넣는가" 를 5가지 문제 + 3가지 호환성 이유로 설명할 수 있다.
- [ ] **서장**: percent-encoding이 transport-encoding (Base64와 같은 발상) 임을 안다.
- [ ] **서장**: hostname (punycode) 과 path/query (percent-encoding) 가 다른 인코딩임을 안다.
- [ ] 0장 마인드맵: 6단계 변환을 종이에 1분 안에 그릴 수 있다.
- [ ] URL 의 5+1 컴포넌트 (scheme/authority/path/query/fragment + userinfo) 와 fragment 가 서버에 안 가는 이유.
- [ ] reserved / unreserved / sub-delims / 그 외 의 4분류와 컴포넌트별 인코딩 규칙.
- [ ] IDN punycode 변환의 본질 + homograph 공격.
- [ ] '김' → `%EA%B9%80` 의 비트 레벨 변환 (코드포인트 → UTF-8 → percent).
- [ ] HTTP 메시지 레이아웃 (request-line, header, CRLF blank line, body) 의 바이트 단위 그림.
- [ ] CRLF 의 역사적 기원과 RFC 9112 의 관대한 파서 권고.
- [ ] Host 헤더 누락 시 vhost 분기 불가 → 400.
- [ ] 5계층 인코딩 (text → codepoint → UTF-8 → percent → HTTP → TCP) 의 책임 분리.
- [ ] form-urlencoded / multipart / JSON 각각의 바이트 레이아웃과 charset 결정.
- [ ] HTTP/1.1 vs HTTP/2 (HPACK + binary frame) vs HTTP/3 (QUIC + QPACK) 의 직렬화 차이.
- [ ] Tomcat URIEncoding, CharacterEncodingFilter, JDBC characterEncoding 의 책임 분리.
- [ ] 모지바케 7대 패턴과 각각의 진단/해결.
- [ ] double-encoding bypass 와 path normalization 의 보안 차이.
- [ ] URL 길이 제한이 컴포넌트마다 다른 이유 (RFC 무제한 + 구현체 buffer).
- [ ] 시나리오 A~K 각각의 추적 절차 (특히 I/J/K — Slack URL 변환, 검색엔진 dedup, IDN homograph).
- [ ] 꼬리질문 Q1~Q8 에 막힘없이 답한다.

---

## 다음 단계

- → [02. DNS와 라우팅](./02-dns-and-routing.md): URL 의 host 부분이 어떻게 IP 주소로 변환되고, 그 IP 까지 패킷이 어떻게 도달하는가
- → [03. OSI 7계층 + TCP/TLS](./03-osi-7-layers-and-tcp-tls.md): 이 HTTP 메시지가 각 계층을 통과하며 헤더를 입는 과정
- → [06. Tomcat 내부](./06-tomcat-internals.md): byte stream 이 HttpServletRequest 로 역직렬화 되는 풀버전

## 참고

- **RFC 3986** (URI Generic Syntax): https://datatracker.ietf.org/doc/html/rfc3986
- **RFC 3987** (IRI): https://datatracker.ietf.org/doc/html/rfc3987
- **RFC 3492** (Punycode): https://datatracker.ietf.org/doc/html/rfc3492
- **RFC 5890~5894** (IDNA 2008): https://datatracker.ietf.org/doc/html/rfc5890
- **RFC 3629** (UTF-8): https://datatracker.ietf.org/doc/html/rfc3629
- **RFC 9110** (HTTP Semantics): https://datatracker.ietf.org/doc/html/rfc9110
- **RFC 9112** (HTTP/1.1): https://datatracker.ietf.org/doc/html/rfc9112
- **RFC 9113** (HTTP/2), **RFC 7541** (HPACK): https://datatracker.ietf.org/doc/html/rfc9113
- **RFC 9114** (HTTP/3), **RFC 9204** (QPACK): https://datatracker.ietf.org/doc/html/rfc9114
- **RFC 8259** (JSON): https://datatracker.ietf.org/doc/html/rfc8259
- **RFC 5987** (Header parameter encoding): https://datatracker.ietf.org/doc/html/rfc5987
- **WHATWG URL Standard** (브라우저 실제 동작 명세): https://url.spec.whatwg.org/
- **JEP 400** (UTF-8 by Default): https://openjdk.org/jeps/400
- **OWASP Path Traversal**: https://owasp.org/www-community/attacks/Path_Traversal
- **HTTP/2 HPACK Visualizer**: https://hpack.surge.sh/
