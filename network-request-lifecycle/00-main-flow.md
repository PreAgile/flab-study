# 00. 메인 흐름 — URL 한 줄을 치면 응답이 돌아오기까지

> "주소창에 URL을 치면 무슨 일이 일어나나요?"
> 이 질문 하나로 면접 30분이 흘러간다. 이 문서는 그 30분을 **한 줄기로 술술 풀 수 있게** 만드는 메인 트랙이다.
>
> 사이드 토픽·예외·심화는 일부러 빼고 **줄기 하나**만 따라간다. 풀버전이 필요한 토픽은 단계 끝에 "여기서 더 깊은 건 NN번 챕터" 한 줄로만 링크.

---

## 0. 1분 요약 — 12단계 한 장 시각화

```
[사용자 입력]
   "https://example.com/users/김면수"
        │
        ▼
┌──────────────────────────────────────────────────────────────────────┐
│ ①  브라우저: URL 파싱 + 캐시/HSTS 체크                              │ L7
│ ②  IME map → UTF-8 encode → percent-escape → HTTP serialize        │ L6
│ ③  DNS 4계층: hostname → IP                                        │ L7/UDP
│ ④  TCP 3-way + TLS 1.3 handshake (연결과 비밀)                      │ L4/L6
│ ⑤  라우팅: IP packet이 hop을 타고 가는 길 (MAC vs IP 분리)          │ L3/L2
│ ⑥  OSI 7계층: 위 모든 게 동시에 동작하는 캡슐화                     │ L7→L1
│ ⑦  Load Balancer: 분산만 하는 게 아니다 (8역할)                    │ L4 or L7
│ ⑧  Nginx: event-driven, worker 1개가 수만 conn                     │ L7
│ ⑨  Tomcat: byte stream → HttpServletRequest (3단 파이프라인)       │ L7
│ ⑩  Spring → HikariCP: DB connection을 빌린다                       │ L7
│ ⑪  DB: wire protocol → Parser → Optimizer → Executor → Storage    │ L7
│ ⑫  응답: 위 모든 단계가 역순으로 풀린다                              │ L1→L7
└──────────────────────────────────────────────────────────────────────┘
```

**한 단락 narrative**:
사용자가 주소창에 한글이 섞인 URL을 친다. IME가 키 입력을 codepoint로 매핑하고, 브라우저의 UTF-8 인코더가 codepoint를 byte sequence로 인코딩한 뒤, URL parser가 각 byte를 `%HH` ASCII로 이스케이프한다. HTTP client가 request line과 header를 ASCII byte stream으로 직렬화하면 application이 `write()` syscall로 kernel에 넘기고, kernel TCP/IP가 segment를 조립한다. hostname은 DNS 4계층 cache hierarchy를 거쳐 IP가 되고, 클라이언트는 그 IP를 향해 TCP 3-way handshake로 연결을 맺고 TLS 1.3으로 비밀과 신원을 협상한다. IP packet은 라우터 hop을 타고 인터넷을 가로지른다. 이때 IP는 처음부터 끝까지 그대로지만 MAC은 hop마다 바뀐다. 도착 직전 Load Balancer가 SSL을 풀고 backend 하나를 고른다. Nginx worker가 epoll로 그 connection을 받아 upstream keepalive pool로 Tomcat에 던지고, Tomcat의 Acceptor→Poller→Executor 3단 파이프라인이 byte stream을 파싱해 HttpServletRequest로 만든다(URLDecoder가 unescape, CharsetDecoder가 decode). Spring controller가 HikariCP에서 DB connection을 빌려 JDBC PreparedStatement로 SQL을 보내고, DB가 Parser→Optimizer→Executor→Storage를 거쳐 row를 돌려준다. 그리고 응답은 정확히 같은 길을 역순으로 풀린다.

이 문서는 그 12단계를 **한 줄기로** 따라간다.

---

## ① URL 입력 — 사용자가 주소창에 쳤다

### 무슨 일이 일어나는가

사용자가 `https://example.com/users/김면수`를 주소창에 치는 순간, 브라우저는 즉시 URL 파싱부터 시작한다. URL을 `scheme=https`, `host=example.com`, `path=/users/김면수`, `query=`, `fragment=`로 분해한다. fragment(`#section`)는 클라이언트 anchor라 서버에 안 간다. userinfo(`user:pass@`)는 보안상 strip된다.

파싱 직후 브라우저는 두 가지 캐시를 본다. **HTTP 캐시**(메모리 cache → 디스크 cache)에 같은 URL의 응답이 살아 있고 `Cache-Control`이 허용하면 그 자리에서 응답 — 네트워크 안 탄다. **HSTS 캐시**에 example.com이 있으면 사용자가 `http://` 쳤어도 자동으로 `https://` 업그레이드. 평문 다운그레이드 공격(MITM)을 막는 1차 방어선.

캐시 miss라면 다음 단계인 hostname 해석으로 넘어가는데, 그 전에 path와 query에 비-ASCII 문자(한글, 이모지, 라틴 확장)가 있는지 검사한다. 있으면 ②번 단계의 인코딩 분기가 발동한다.

### 왜 이렇게 동작하나

브라우저가 즉시 캐시부터 보는 이유는 단순하다 — **네트워크는 비싸고 메모리/디스크는 거의 공짜**다. 같은 정적 자원을 100번 요청하면 99번은 캐시로 끝낸다. HSTS가 별도 캐시인 이유는 1차 요청이 `http://`로 시작하면 그 1번이 가로채기당할 수 있어서 — 브라우저가 한 번 HTTPS 받으면 그 도메인을 영원히(또는 max-age) HTTPS로만 가게 강제한다.

<details>
<summary>📌 <b>HSTS란? — 클릭해서 펼치기</b></summary>

**HSTS = HTTP Strict Transport Security** (RFC 6797). 서버가 응답 헤더(`Strict-Transport-Security: max-age=...`) 하나로 **"이 도메인은 앞으로 HTTPS로만 와. 평문 HTTP 금지"**라고 선언하고, 브라우저가 그걸 캐시에 기억하는 **보안 정책**. 암호화 자체는 TLS(④번)가 하고, HSTS는 **TLS를 반드시 쓰게 강제하는 약속**이다 — 둘은 별개.

**막으려는 공격 — SSL stripping (평문 다운그레이드 MITM)**:
```
[HSTS 없을 때]
"example.com" 입력 (scheme 생략 → 기본 http://)
        │  http://example.com   ◀── 이 평문 1번이 약점
        ▼
   공격자(MITM, 카페 WiFi)가 가로챔
   피해자 ⟷ 공격자 : HTTP(평문, 자물쇠 없음)
   공격자 ⟷ 서버  : HTTPS(정상)
        ▼
   피해자가 평문 페이지에 비번 입력 → 공격자가 읽음

[HSTS 있을 때]
"example.com" 입력
        ▼
   ① URL 파싱 단계에서 HSTS 캐시 hit → http:// → https:// 강제 재작성
        ▼   (패킷이 NIC를 나가기 전에 끝남)
   처음부터 https:// 요청 → 평문 구간 자체가 없음 → strip할 게 없음
```

HSTS가 **"1차 방어선"**인 이유: DNS·TCP·TLS보다도 먼저, **URL 파싱 시점(①번)에 패킷이 나가기 전에** scheme을 https로 바꿔 평문 요청을 아예 만들지 않는다.

**두 가지 함정 (시니어 관점)**:
- **첫 방문 구멍** — 헤더를 한 번은 받아야 캐시에 생기므로 생애 첫 요청은 여전히 평문. → 브라우저 내장 **HSTS preload 목록**(`hstspreload.org`)으로 메운다.
- **양날의 검** — `max-age`를 길게 박으면 인증서 만료·HTTPS 장애 시 브라우저가 우회 불가능한 에러로 사용자를 잠근다(핫픽스 통로도 없음). → 운영 정석: **짧게(예: 300초) 깔고 검증 후 점진적으로 1년으로** 올린다.

</details>

### 다이어그램

```
"https://example.com/users/김면수" 입력
        │
        ▼
   URL 파싱
   scheme=https
   host=example.com
   path=/users/김면수
        │
        ▼
   ┌──────────────┐
   │ HTTP cache?  │ ── hit ──▶ 즉시 응답 (네트워크 안 탐)
   └──────┬───────┘
          │ miss
          ▼
   ┌──────────────┐
   │ HSTS cache?  │ ── hit ──▶ scheme을 https로 강제
   └──────┬───────┘
          │
          ▼
   path/query에 비-ASCII 있나? → 있으면 ②번 encoding 단계
                                → 없으면 곧장 ③번 DNS
```

### 면접에서 이렇게 물으면

**Q**: "사용자가 URL을 친 직후 브라우저가 가장 먼저 하는 일은?"
> URL 파싱 → 캐시/HSTS 체크 → 인코딩 필요한지 검사. 핵심은 **네트워크에 패킷을 보내기 전에 로컬에서 끝낼 수 있는지 본다**는 것. 캐시가 있으면 그 자리에서 응답, HSTS가 있으면 https로 강제 업그레이드, path/query에 한글이 있으면 percent-encoding으로 넘어간다.

더 깊은 건 [01-url-input-and-serialization.md](./01-url-input-and-serialization.md).

---

## ② 한글이 byte가 되는 과정 — 텍스트→Unicode→UTF-8→percent-encoding

### 무슨 일이 일어나는가

HTTP는 본질적으로 ASCII protocol이다. RFC 9112가 정의하는 request-line/header/URL은 모두 ASCII printable(0x21~0x7E) 기반. 한글 같은 비-ASCII byte는 HTTP 메시지에 그대로 못 들어간다. 그래서 브라우저는 path/query의 비-ASCII 문자를 **5단계 변환**으로 ASCII-safe하게 바꾼다. 핵심은 **각 단계마다 주체와 동사가 다르다**는 것 — "변환"이라는 한 단어로 뭉뚱그리면 면접에서 즉시 들킨다.

`김면수`라는 3글자가 wire에 도달하는 길 — 주체 + 동사 명시:

1. **키 입력 → codepoint (map)**: **OS의 IME**(macOS 한글입력기, Windows 한글IME)가 키 입력 `ㄱ+ㅣ+ㅁ`을 codepoint `U+AE40`으로 **매핑(map)**한다. 브라우저 메모리에 도달했을 때 이미 codepoint 상태 — V8 등 JS engine은 UTF-16 char[]로 보관.
2. **codepoint → UTF-8 byte (encode)**: **브라우저의 UTF-8 인코더**(`TextEncoder` API 또는 내부 URL encoder)가 codepoint를 byte sequence로 **인코딩(encode)**한다. 한글 음절 영역은 UTF-8 3 byte 패턴 → `EA B9 80 EB A9 B4 EC 88 98` (9 byte).
3. **byte → `%HH` ASCII (escape)**: **브라우저의 URL 처리 코드**(URL parser/builder)가 각 byte를 `%HH` 3-char ASCII로 **이스케이프(escape)**한다 → `%EA%B9%80%EB%A9%B4%EC%88%98` (27 ASCII char).
4. **HTTP 메시지 직렬화 (serialize)**: **브라우저의 HTTP client**(fetch / XHR / navigation)가 request-line + header를 ASCII byte stream으로 **직렬화(serialize)**한다 → `GET /users/%EA%B9%80%EB%A9%B4%EC%88%98 HTTP/1.1\r\nHost: example.com\r\n\r\n`.
5. **byte stream → wire**: **application(브라우저)**이 `write()` syscall로 ASCII byte를 **kernel에 복사**, **kernel TCP/IP 스택**이 그 byte를 segment로 조립하고 NIC가 wire에 송신. 이미 ASCII이므로 추가 변환 없음.

서버는 정확히 역순으로 분해한다. **Tomcat Coyote HTTP parser**가 byte stream을 request-line/header 객체로 **파싱(parse)** → **URLDecoder**(`java.net.URLDecoder`)가 `%HH`를 byte로 **언이스케이프(unescape)** → **CharsetDecoder**(`new String(bytes, UTF_8)`)가 UTF-8 byte를 codepoint로 **디코딩(decode)** → **JVM**이 codepoint를 char[](UTF-16)으로 보관해 Java String 생성 → **Spring이 reflection으로 `@PathVariable`에 주입**. 어느 한 단계라도 charset 합의가 어긋나면 그 지점에서 글자 깨짐.

> 아래 5개 토글은 **5번 단계(`byte stream → wire`)에 숨은 OS·네트워크 기초**를 펼친 것 — byte stream/wire가 뭔지부터, syscall·socket buffer·캡슐화·fd까지 한 줄기로 이어진다.

<details>
<summary>📌 <b>byte stream & wire란? — 클릭해서 펼치기</b></summary>

**byte stream = 경계 없이 줄줄이 늘어선 byte(8비트)들의 연속 흐름.** 메모리 안에서 HTTP 요청은 구조화된 객체(method·path·header 따로)지만, 네트워크는 구조를 모르고 "byte 하나 다음 byte 하나"만 옮긴다. 그래서 serialize 단계가 그 객체를 **하나의 평탄한 byte 나열**로 펴낸다.

핵심 — **TCP는 byte stream 프로토콜이라 "메시지 경계" 개념이 없다.** `write()`로 요청 한 통을 보내도 TCP는 그걸 "한 메시지"로 기억하지 않고 그냥 byte를 흘린다. 그래서 받는 쪽은 byte가 어디서 끊기는지 TCP에 못 물어보고, **HTTP 스스로** `\r\n\r\n`(헤더 끝)·`Content-Length`(body 길이)로 경계를 표시해야 한다. (HTTP가 이런 구분자를 쓰는 근본 이유)

**wire = byte가 실제로 흘러가는 물리 전송 매체** — 문자 그대로 "전선"이지만 구리(이더넷)·광섬유·전파(WiFi) 통칭. "on the wire"는 메모리·디스크가 아니라 **네트워크 위에서 실제로 흐르는 상태**, "wire format"은 그 흐르는 byte 표현. 그래서 `byte stream → wire`는 **메모리 속 byte 나열을 NIC가 물리 신호로 바꿔 네트워크로 내보내는** 마지막 단계.

**운영 관점**: `tcpdump`/Wireshark는 말 그대로 "wire 위 byte stream"을 떠서 보여준다. "코드에선 분명 보냈는데 서버가 못 받았다" → wire를 떠보면 실제 나간 byte가 보여 직렬화 버그가 잡힌다. "한 번에 다 올 줄 알았는데 잘려 왔다(partial read)"가 byte stream에 경계가 없어서 생기는 단골 버그.

</details>

<details>
<summary>📌 <b>user space & write() syscall이란? — 클릭해서 펼치기</b></summary>

메모리·CPU 권한은 **두 영역**으로 갈린다:

| | user space | kernel space |
|---|---|---|
| 누가 | 브라우저·curl·JVM 등 **앱** | OS 커널 |
| 권한 | 제한(CPU ring 3) | 전권(ring 0), 하드웨어 직접 제어 |

**왜 나누나** — 보안·안정성. 앱이 NIC를 직접 만지거나 남의 메모리를 읽으면 OS가 무너지니까. 그래서 앱은 하드웨어를 직접 못 건드리고 커널에 **부탁**해야 하며, 그 유일한 정문이 **syscall(시스템 콜)**. 호출하면 CPU가 ring 3 → ring 0으로 모드 전환(trap)하고 커널 코드를 돌린 뒤 돌아온다. 이 전환 비용 때문에 syscall은 "비싼 호출".

**`write(socket_fd, buffer, len)`**의 의미 = **"user space의 내 buffer에 있는 byte를 커널의 socket send buffer로 복사해줘."** 두 가지가 핵심:
- **복사(copy)다** — user 메모리 → kernel 메모리. (이 복사를 없애는 게 `sendfile()` 같은 zero-copy)
- **write()가 리턴해도 아직 안 나갔다** — byte는 커널 buffer에 쌓이고, 실제 송신은 커널이 자기 타이밍에. 앱은 그새 다음 일을 한다(decouple).

</details>

<details>
<summary>📌 <b>socket & buffer란? — 클릭해서 펼치기</b></summary>

**socket = 네트워크 연결의 한쪽 끝점을 나타내는 커널 객체.** `(프로토콜, 내 IP:port, 상대 IP:port)` 4튜플로 식별되고, 앱은 그 객체를 직접 못 만지고 **fd(번호표)**로 가리킨다. Unix "everything is a file" 철학 덕에 소켓도 파일처럼 `read()`/`write()`로 다룬다.

**buffer = 소켓에 붙은 커널 메모리 2개**:
```
[app] write() ──▶ ┌──────────────────────┐
                  │ send buffer (SO_SNDBUF) │ 썼지만 아직 ACK 안 된 byte
       소켓 ─────│                          │
                  │ recv buffer (SO_RCVBUF) │ 도착했지만 아직 read() 안 한 byte
[app] read()  ◀── └──────────────────────┘
```

**왜 buffer가 있나** — 앱 속도와 네트워크 속도를 **분리**하려고. 앱은 빠르게 write하고 가던 길 가고(커널이 send buffer를 네트워크 속도로 비움), 네트워크가 몰아서 던져도 recv buffer가 받아둔다(앱이 read할 때까지). 그리고 이 **recv buffer 남은 공간이 곧 TCP receive window** — "내 버퍼 이만큼 비었으니 그만큼만 보내"라고 알리는 흐름 제어(flow control)의 실체.

</details>

<details>
<summary>📌 <b>TCP/IP 스택 "가공" = 계층별 캡슐화 (L1~L7) — 클릭해서 펼치기</b></summary>

"TCP/IP 스택"은 한 층이 아니라 **두 층 이상**이다. byte가 wire에 닿기 전 **L7부터 L2까지 겹겹이 포장**되는데, 각 계층이 위 계층 결과물에 자기 헤더를 덧씌우는 이걸 **캡슐화(encapsulation)**라 한다.

```
L7  HTTP    │ [ HTTP 메시지 = byte stream ]                          │ → "data"
L4  TCP     │ [ TCP헤더 | HTTP ]              port·seq·ack          │ → "segment"
L3  IP      │ [ IP헤더 | TCP헤더 | HTTP ]     src/dst IP·TTL         │ → "packet"
L2  Ethernet│ [ Eth헤더 | IP헤더 | TCP헤더 | HTTP | FCS ]  src/dst MAC│ → "frame"
L1  물리     │  위 frame의 모든 bit을 전압·빛·전파 신호로 변환          │ → "bits"
═══════════════════════ wire ═══════════════════════
```

PDU 이름이 층마다 바뀌는 게 단서: **data → segment → packet → frame → bits**. 받는 쪽은 역순으로 한 겹씩 벗긴다(decapsulation).

- **TCP는 L4, IP는 L3** — "TCP/IP"라 붙여 부르니 한 층 같지만 별개의 두 단계(TCP가 만든 segment를 IP가 한 번 더 감쌈).
- **L2(MAC 헤더 붙이기)는 커널/드라이버**가, **L1(byte→물리 신호 변환)은 NIC 하드웨어**가 담당. ("NIC가 한다"는 통념은 L1+L2를 합쳐 부른 것)
- **실제 wire엔 L5·L6 PDU가 없다** — 실제 인터넷은 TCP/IP 4층 모델이라 OSI의 L5/L6/L7이 "Application" 한 덩어리. **TLS도 HTTP도 TCP 입장에선 그냥 payload**: `[ Eth | IP | TCP | [TLS | HTTP] ]`.

**MAC vs IP 분리 (⑤번과 직결)**: **IP(L3)는 끝-to-끝 주소라 출발~최종 목적지까지 불변**, **MAC(L2)은 hop-to-hop 주소라 바로 다음 장비 하나만** 가리킨다. 라우터를 지날 때마다 L2 프레임은 통째로 벗겨져 **새 MAC으로 재포장**되지만(다음 hop용), 안의 L3 IP 패킷은 그대로 간다(TTL만 1 감소). IP는 "어디로", MAC은 "다음 한 걸음 누구한테".

</details>

<details>
<summary>📌 <b>fd(file descriptor)란? — 클릭해서 펼치기</b></summary>

**fd = 프로세스가 "열어둔 자원"을 가리키는 작은 정수 번호표(0,1,2,3...).** "everything is a file" 철학으로 fd가 가리키는 건 파일만이 아니라 **소켓·파이프·터미널·epoll** 전부 — 그래서 `read()`/`write()`/`close()` 같은 동일 syscall이 파일이든 소켓이든 똑같이 동작한다. 관례상 `0=stdin, 1=stdout, 2=stderr`라 새로 열면 보통 `3`부터.

**fd 뒤의 3단 간접 참조** — 정수 하나는 입구일 뿐:
```
① per-process fd 테이블   ② open file description     ③ 실제 객체
   (프로세스마다 독립)        (offset·flags 보관)         (inode / 소켓+buffer)
   fd 4 ───────────────▶  ────────────────────────▶  socket 객체 + send/recv buffer
```
①은 프로세스마다 독립(같은 fd 번호가 프로세스마다 다른 걸 가리킴), ②는 `dup()`/`fork()`로 공유되면 offset도 공유, ③이 진짜 자원. 그래서 **`write(socketfd,...)`의 fd는 "어느 소켓 send buffer에 복사할지" 커널에 지목**하는 역할 — fd가 socket buffer로 가는 입구다.

**왜 포인터 아니고 정수인가** — 정수는 **불투명한 손잡이(opaque handle)**라 커널이 매 syscall마다 "이 프로세스가 정말 이 fd를 가졌나" 검증한다(보안). 또 파일·소켓을 동일하게 다루는 추상화. 커널은 **항상 비어 있는 가장 작은 번호**를 배정(`close(1)` 후 `open()`하면 fd 1 재사용 → 쉘 리다이렉션 `>`의 원리).

**운영 관점 — fd가 production을 무너뜨리는 방식**:
- **연결 1개 = fd 1개.** `accept()`가 연결마다 새 fd 발급 → 동시접속 1만이면 fd 1만+개 필요(`ulimit -n` 상향).
- **fd leak** — `close()` 누락 시 fd가 안 반환돼 테이블이 차고, 며칠 뒤 `EMFILE`(**Too many open files**)로 서버 사망. (`lsof -p PID`, `ls /proc/PID/fd`로 진단 — fd 수 우상향이면 leak 신호)
- **epoll** — `epoll_wait()` 하나로 수만 개 소켓 fd 중 "준비된 것"만 받아 처리. 문서 ⑧번 "Nginx worker 1개가 수만 conn"의 정체가 곧 **fd 수만 개를 epoll로 감시**하는 것.

</details>

### 동사 사전 — "변환"을 쓰면 잃는 정확성

| 동사 | 의미 | 사용 위치 |
|---|---|---|
| **map** | lookup-table 매핑 | IME가 키 입력 → codepoint |
| **encode** | 더 작은 alphabet 표현으로 매핑 | codepoint → UTF-8 byte |
| **decode** | encode의 역연산 | UTF-8 byte → codepoint |
| **escape** | 특수 문자를 안전한 ASCII 표현으로 치환 | byte 0xEA → `"%EA"` |
| **unescape** | escape의 역연산 | `"%EA"` → byte 0xEA |
| **serialize** | 메모리 객체 → byte stream | HTTP request 객체 → ASCII byte |
| **parse** | byte stream → 메모리 객체 | HTTP byte → HttpServletRequest |

"convert/transform/변환"은 위 7개 중 어느 것인지 안 드러난다. 면접관이 "encode와 escape의 차이는?"이라고 물으면 모호한 단어로는 답이 안 나온다.

### 왜 이렇게 동작하나

HTTP는 1991년 ARPANET 시절 7-bit ASCII가 사실상 표준이던 시대에 태어났다. 30년 묵은 middlebox·proxy·WAF·로그 분석기들이 "URL은 ASCII"라는 invariant에 hard-code되어 있다. URL은 HTTP 밖으로도 새어 나간다 — HTML href, email 본문, Slack 메시지, log 파일, shell command. ASCII-safe하지 않으면 어딘가에서 깨진다. percent-encoding은 그 30년 invariant를 지키기 위한 transport-encoding 표준 패턴. Base64가 binary를 email-safe ASCII로 옮기는 것과 같은 발상의 다른 구현.

`byte`와 `bit`은 같은 것의 다른 표기다. 1 byte = 8 bit. 0xEA는 16진수 한 byte = 8 bit. UTF-8 한글 1자 = 3 byte = 24 bit. percent-encoding은 그 24 bit을 ASCII 문자 9개(`%`+2 hex × 3)로 표현한다.

### 다이어그램 — 주체 + 동사 한 그림

```
[키 입력 "ㄱ+ㅣ+ㅁ"]
     │ IME가 매핑(map) — OS의 입력기 책임 (macOS 한글입력기/Windows 한글IME)
     ▼
[codepoint U+AE40]
     │ (브라우저 메모리에 UTF-16 char[]로 이미 codepoint 상태)
     │  사용자가 Enter를 누르면 fetch / navigate 발동
     │
     │ 브라우저의 UTF-8 인코더가 인코딩(encode) — TextEncoder API 또는 내부 URL encoder
     ▼
[UTF-8 byte 0xEA 0xB9 0x80 / 0xEB 0xA9 0xB4 / 0xEC 0x88 0x98]   (9 byte)
                ── 김 ──        ── 면 ──        ── 수 ──
     │ 브라우저의 URL parser/builder가 각 byte를 `%HH`로 이스케이프(escape)
     ▼
["%EA%B9%80%EB%A9%B4%EC%88%98" (ASCII string, 27 char)]
     │ 브라우저의 HTTP client(fetch/XHR)가 request line/header와 함께 ASCII byte stream으로 직렬화(serialize)
     ▼
[HTTP request byte stream]
  GET /users/%EA%B9%80%EB%A9%B4%EC%88%98 HTTP/1.1\r\nHost: example.com\r\n\r\n
     │ application이 write() syscall — kernel TCP/IP가 segment 조립 + NIC 송신
     ▼
[wire bytes 47 45 54 20 2F 75 73 65 72 73 2F 25 45 41 ...]
                G  E  T  SP /  u  s  e  r  s  /  %  E  A  ...
   ··· 네트워크 ···
[server NIC] → kernel TCP/IP가 reassemble → Tomcat이 read()
     │ Tomcat Coyote HTTP parser가 파싱(parse) — byte stream → request line/header 객체
     ▼
[URL path string "%EA%B9%80%EB%A9%B4%EC%88%98"]
     │ URLDecoder(java.net.URLDecoder)가 언이스케이프(unescape) — `%HH` → byte
     ▼
[byte[] {0xEA, 0xB9, 0x80, ...}]
     │ CharsetDecoder가 디코딩(decode) — UTF-8 규칙으로 byte → codepoint
     │ (Tomcat URIEncoding=UTF-8이 charset 결정)
     ▼
[codepoint sequence U+AE40 U+BA74 U+C218]
     │ JVM이 char[](UTF-16)으로 보관 — Java String 생성
     ▼
[Java String "김면수"]
     │ Spring이 reflection으로 @PathVariable에 주입
     ▼
[@PathVariable String name = "김면수"]
```

### 글자 깨짐의 책임 계층 — 어디서 깨지면 어떻게 진단하나

브라우저의 UTF-8 인코더가 encode(codepoint → byte), 서버의 CharsetDecoder가 decode(byte → codepoint). 양쪽 charset 합의가 어긋나면 그 경계에서 글자 깨짐. Spring Boot 환경에서 charset 계약은 3+ 지점:

```
① Tomcat URIEncoding=UTF-8          → GET path/query decode
② CharacterEncodingFilter UTF-8     → POST body decode (forceEncoding=true)
③ JDBC characterEncoding=UTF-8      → DB 송수신
    + DB 테이블 charset utf8mb4     → 저장
    + Content-Type charset=UTF-8    → 응답
```

이 중 한 곳이라도 안 맞으면 그 경계에서 깨진다. 가장 흔한 7대 패턴:

| 증상 | 원인 | 해결 |
|---|---|---|
| URL 한글이 `???` | Tomcat URIEncoding 미설정 | `server.tomcat.uri-encoding=UTF-8` |
| POST body 한글이 `?` | CharacterEncodingFilter 없음 | Spring Boot 기본 활성화 |
| DB 저장 한글 깨짐 | JDBC URL `characterEncoding` 누락 | `?useUnicode=true&characterEncoding=UTF-8` |
| DB select 한글 깨짐 | 테이블 charset latin1 | `ALTER TABLE ... CONVERT TO CHARACTER SET utf8mb4` |
| 응답 body 정상인데 브라우저가 깨뜨림 | Content-Type charset 누락 | `Content-Type: text/html; charset=UTF-8` |
| `ê¹€ë©´ìˆ˜` 패턴 | UTF-8을 ISO-8859-1로 decode | 어느 단계에서 잘못 decode 추적 |
| `?` 또는 `□` 한 글자 | encode 단계에서 unknown codepoint | charset upgrade (utf8 → utf8mb4, 이모지) |

**중요한 책임 분리**: GET path/query는 request-line 단계에서 Tomcat이 먼저 파싱한다 → Filter 도달 전 결정. 그래서 `CharacterEncodingFilter`로는 GET 못 고쳐요. URIEncoding이 별도 영역.

### 면접에서 이렇게 물으면

**Q**: "한글 URL이 네트워크에 어떻게 흐르나요? `김` 한 글자가 `%EA%B9%80`이 되는 이유는?"
> 주체별로 끊어 답합니다. ① IME가 키 입력을 codepoint U+AE40으로 매핑(map). ② 브라우저의 UTF-8 인코더가 codepoint를 3 byte `0xEA 0xB9 0x80`으로 인코딩(encode). ③ 브라우저의 URL parser가 각 byte를 `%HH`로 이스케이프(escape) → `%EA%B9%80`. ④ HTTP client가 request line 안에 박아 ASCII byte stream으로 직렬화(serialize). ⑤ application이 write() syscall, kernel TCP/IP가 segment 조립. 서버는 역순 — Tomcat parser가 parse → URLDecoder가 unescape → CharsetDecoder가 decode → JVM이 String 생성 → Spring이 reflection으로 주입. 30년 묵은 middlebox 호환성 때문에 ASCII invariant를 깰 수 없는 게 본질적인 이유.

**Q**: "encode와 escape의 차이는 뭔가요?"
> 둘 다 "변환"으로 뭉뚱그리면 안 됩니다. **encode**는 한 alphabet을 더 작은 alphabet 표현으로 매핑 — 예: codepoint U+AE40을 UTF-8 byte 3개로(`EA B9 80`). 알파벳 자체가 달라집니다. **escape**는 특수 문자를 안전한 ASCII 표현으로 치환 — 예: byte `0xEA`(URL에 못 쓰는 8-bit byte)를 `"%EA"`(3개의 ASCII char)로. **serialize**는 메모리 객체를 byte stream으로 펴는 것(HTTP request 객체 → ASCII byte). **parse**는 그 역연산. **map**은 lookup-table 1:1 매핑(IME가 키 입력 → codepoint). 한 흐름 안에서 동사가 5개 등장합니다.

**Q**: "각 단계의 책임 주체는?"
> ① 키 입력 → codepoint: **IME**(OS 입력기). ② codepoint 보관: **브라우저 메모리**(V8 등 JS engine, UTF-16). ③ codepoint → UTF-8 byte: **브라우저의 UTF-8 인코더**. ④ byte → `%HH`: **브라우저 URL parser**. ⑤ HTTP 메시지 조립: **브라우저 HTTP client**(fetch/XHR). ⑥ wire 송신: **application → write() syscall → kernel TCP/IP**. ⑦ server 측 parse: **Tomcat Coyote**. ⑧ unescape: **URLDecoder**. ⑨ decode: **CharsetDecoder**. ⑩ String 보관: **JVM**(char[] UTF-16). ⑪ controller 주입: **Spring reflection**. 11단계 + 11개 주체.

**Q**: "byte랑 bit은 어떻게 다른가요?"
> 같은 것의 다른 단위. 1 byte = 8 bit. 0xEA는 16진수 한 byte인데 8 bit으로 펴면 `11101010`. UTF-8 한글 1자가 3 byte = 24 bit = 8칸 × 3.

더 깊은 건 [01-url-input-and-serialization.md](./01-url-input-and-serialization.md).

---

## ③ DNS — hostname을 IP로 (라우팅보다 먼저)

### 무슨 일이 일어나는가

라우팅을 시작하려면 목적지 IP가 있어야 한다. 그런데 사용자는 IP가 아니라 hostname을 친다. 그 사이를 잇는 게 DNS — `hostname → IP` 변환 시스템이다.

DNS는 단일 서버가 아니라 **4계층 cache hierarchy**다. 브라우저가 한 번 hostname을 풀려고 하면 이 순서로 cache를 확인한다:

1. **브라우저 in-memory DNS cache** — Chrome `chrome://net-internals/#dns`에서 확인 가능.
2. **OS 단계** — `/etc/hosts` 정적 매핑 먼저, 그 다음 OS DNS cache(systemd-resolved/mDNSResponder).
3. **Stub resolver** — `/etc/resolv.conf`의 nameserver에 UDP 53 질의(재귀 요청).
4. **Recursive resolver**(ISP/8.8.8.8/1.1.1.1) — 자기 cache hit이면 즉시 반환, miss면 ↓
5. **3단 referral** — Root NS(".") → TLD NS(".com") → Authoritative NS(example.com auth) → A 레코드 반환.

각 단계가 TTL 동안 cache한다. TTL이 짧으면 failover 빠르지만 NS 부하 ↑, 길면 stale. 정적 자원은 1day, 동적/failover는 60s가 권장.

### 왜 이렇게 동작하나

만약 단일 DNS 서버 하나가 전 세계 hostname을 풀어준다면 그 서버는 즉시 죽는다. 그래서 root → TLD → authoritative로 **계층화 + 위임**을 하고, 그 위에 **4단 cache**를 얹어 인터넷 규모를 흡수한다. UDP 53을 쓰는 이유도 같다 — TCP handshake 비용을 매번 치를 수 없다(요즘은 EDNS0로 큰 응답 + TCP fallback + DoT/DoH로 암호화까지 진화).

라우팅은 IP 없이 시작할 수 없다. DNS가 답을 주기 전엔 라우팅 단계가 멈춰 있다. 그래서 DNS 응답 latency가 P99 latency의 흔한 범인.

### 다이어그램

```
[Browser] "example.com?"
   │
   │ ① 브라우저 in-memory DNS cache → hit이면 반환
   ▼
[OS resolver] /etc/hosts → OS DNS cache
   │ hit이면 반환
   ▼
[Stub resolver (libc getaddrinfo)]
   │ /etc/resolv.conf의 nameserver에 UDP 53 질의
   ▼
[Recursive resolver — 8.8.8.8 / 1.1.1.1]
   │ 자기 cache hit이면 반환, miss면 ↓
   │
   │  Root NS (".")        → ".com TLD NS는 ..."
   │      │
   │      ▼
   │  TLD NS (".com")      → "example.com auth NS는 ..."
   │      │
   │      ▼
   │  Authoritative NS     → "example.com A = 93.184.216.34"
   │
   ▼
[A record + TTL] 각 단계 cache에 TTL 동안 저장
```

### 면접에서 이렇게 물으면

**Q**: "DNS는 어떻게 동작하나요?"
> 단일 서버가 아니라 **4계층 cache hierarchy + recursive resolver 모델**입니다. 클라이언트는 브라우저 cache → OS resolver → /etc/hosts → stub 순서로 보고, miss면 `/etc/resolv.conf`의 recursive(ISP/8.8.8.8)에 UDP 53 질의. recursive가 miss면 root → TLD → authoritative 3단 referral. 각 단계가 TTL 동안 cache. TTL은 짧으면 failover 빠르지만 NS 부하 ↑, 길면 stale. 진단은 `dig +trace`, `tcpdump udp port 53`, JVM의 `networkaddress.cache.ttl` + K8s `ndots:5` 점검.

**Q**: "DNS가 라우팅보다 먼저 일어나는 이유는?"
> 라우팅 테이블은 destination IP로 next-hop을 결정합니다. IP가 없으면 라우팅 자체가 시작 안 됩니다. DNS는 그 IP를 채우는 단계예요.

더 깊은 건 [02-dns-and-routing.md](./02-dns-and-routing.md).

---

## ④ TCP 연결 수립 + TLS Handshake

### 무슨 일이 일어나는가

DNS가 IP를 돌려주면 이제 그 IP로 TCP 연결을 맺을 차례. TCP는 unreliable한 IP 위에 **신뢰성**을 얹는 계층이다. 신뢰성을 만들려면 양쪽이 먼저 합의된 상태(state)에 도달해야 한다. 그게 **3-way handshake**.

```
Client                              Server (LISTEN)
  │
  │  ① SYN seq=x                        (SYN_RECV)
  │ ─────────────────────────────────────▶
  │
  │  ② SYN+ACK seq=y, ack=x+1
  │ ◀─────────────────────────────────────
  │
  │  ③ ACK seq=x+1, ack=y+1
  │ ─────────────────────────────────────▶
  │
  ▼                                  ▼
 ESTABLISHED                      ESTABLISHED
  │                                  │
  │ ◀══ 양방향 데이터 교환 가능 ══▶  │
```

왜 3번인가 — 양쪽이 각자 초기 sequence number를 보내고 상대가 ACK해야 한다. 2번이면 server가 client의 ACK 수신 여부를 모른다(half-open). 4번도 되지만 가운데 SYN+ACK를 묶어서 3번에 끝낸다.

3-way 완료 직후, HTTPS면 곧이어 **TLS handshake**가 끼어든다. TLS 1.3은 1 RTT면 끝난다. ClientHello에 추측한 key_share를 미리 박아 보내면 server가 ServerHello+key_share+Cert+Finished를 한 번에 돌려준다. TLS 1.2는 2 RTT 필요. TLS의 3대 보장: **Confidentiality**(AES 대칭암호로 중간자 못 봄), **Integrity**(AEAD로 변조 들킴), **Authenticity**(인증서 체인으로 서버 신원 검증).

이 모든 게 끝나야 HTTP 메시지 한 byte라도 보낼 수 있다.

### 왜 이렇게 동작하나

IP는 best-effort — 패킷이 사라져도 모른다. TCP가 그 위에 sequence number, ACK, retransmission, flow control(window), congestion control(cwnd)을 얹어 신뢰성을 만든다. 3-way handshake는 그 신뢰성의 시작점 — 양쪽이 sequence number를 합의하는 의식.

TLS가 TCP 위에 가는 이유는 TLS도 **신뢰성 있는 byte stream**을 가정하기 때문. 손실되거나 순서가 바뀌면 암호화 체인이 깨진다. UDP 위에 TLS를 얹으려면 DTLS 또는 QUIC가 필요한 이유.

### 다이어그램

```
TLS 1.3 (1 RTT)
─────────────
Client                                    Server
  │
  │   ClientHello + key_share ──────────▶
  │
  │   ◀─── ServerHello + key_share
  │        + Certificate + CertVerify
  │        + Finished
  │
  │   Finished + application data ────▶
  │
  │   ◀─── application data
  │
  ▼                                          ▼
[암호화된 HTTP 메시지가 양방향 흐름]

TCP 3-way + TLS 1.3 = 2 RTT
TCP 3-way + TLS 1.2 = 3 RTT
TCP 3-way + TLS 1.3 + 0-RTT 재방문 = 1 RTT (단 0-RTT는 idempotent GET만)
```

### 흐름 제어와 혼잡 제어 — 연결 안의 boost

TCP는 연결을 맺기만 하는 게 아니라 **연결 동안의 속도**도 관리한다. 두 메커니즘이 같이 돌아간다:

- **흐름 제어 (Sliding Window, receiver-driven)**: receiver가 자기 buffer 크기를 advertise(`win=10000`) → sender는 그 이상 안 보냄. receiver overflow 방지. 16-bit field 한계는 64KB라 고대역(100Gbps × 100ms RTT)엔 부족 → Window Scaling option으로 shift factor 협상해 max 1GB까지.
- **혼잡 제어 (cwnd, sender-driven)**: 네트워크 중간 router의 혼잡을 다룸. 1988년 Van Jacobson Tahoe부터 Reno/CUBIC(Linux 기본)/BBR(Google 2016)까지 진화. CUBIC는 "loss = 혼잡" 가정, BBR은 RTT/대역폭 측정해서 무선/모바일에서 +14% throughput. 외부 트래픽엔 BBR, 데이터센터 내부엔 CUBIC.

운영 진단 단서: `ss -tin`으로 connection별 cwnd/rtt 확인. `cwnd` 작으면 bufferbloat 의심, retransmit 많으면 손실 환경.

### TIME_WAIT — 연결을 끊을 때의 잔존 상태

3-way로 연결을 열듯이, 4-way로 연결을 닫는다. close를 먼저 시작한 쪽(active close, 보통 client 또는 LB)이 `FIN_WAIT_1 → FIN_WAIT_2 → TIME_WAIT`를 거쳐 2MSL(보통 60초) 후에야 진짜 `CLOSED`로 간다.

왜 2MSL을 기다리나 — 두 가지 이유:
1. **마지막 ACK 손실 대비**: 상대가 FIN 재전송하면 다시 ACK 보내야 함.
2. **옛 segment 격리**: 같은 4-tuple로 즉시 새 연결 만들면 지연된 segment가 새 연결로 흘러올 수 있음. 2MSL 후엔 다 죽었다.

운영에서 가장 흔한 함정은 **TIME_WAIT 폭증 → ephemeral port 고갈**. 짧은 HTTP 연결이 많고 active close가 client/LB 쪽이면 누적된다. 해결 우선순위는 (1) HTTP keepalive로 close 빈도 자체 감소(가장 정석), (2) `net.ipv4.tcp_tw_reuse=1`로 안전한 재사용, (3) ephemeral port range 확장. `tcp_tw_recycle`은 NAT에서 망함 → 커널 4.12부터 삭제. **절대 쓰면 안 됨**.

### 면접에서 이렇게 물으면

**Q**: "TCP 3-way가 왜 3번인가요? 2번이면 안 되나요?"
> 양쪽이 각자 초기 sequence number를 보내고 상대가 ACK해야 합니다. 2번이면 server가 client의 ACK 수신 여부를 모르고, 그 상태에서 client만 죽으면 server에 half-open conn이 남습니다. SYN×2 + ACK×2 = 4번 같지만 가운데를 SYN+ACK로 묶어서 3번에 끝납니다. 초기 sequence는 random이어야 — TCP sequence prediction attack(1995 Mitnick 공격)을 막기 위해서.

**Q**: "TLS 1.3은 어떻게 1 RTT로 줄였나요?"
> ClientHello에 추측한 key_share(X25519 등)를 미리 박아 보냅니다. server가 그 그룹을 받으면 ServerHello에 자기 key_share + Cert + CertVerify + Finished를 한 번에 돌려줍니다. TLS 1.2는 키 교환에 2 round 필요했어요. 그리고 1.3은 ServerHello 이후부터 모두 암호화 — 1.2는 인증서까지 cleartext였습니다. 0-RTT 재방문도 가능하지만 replay 위험 때문에 idempotent GET에만 써야 — POST에 쓰면 송금 2번 같은 사고 가능.

**Q**: "TIME_WAIT가 왜 2MSL인가요? 줄이는 안전한 방법은?"
> 마지막 ACK 손실 시 상대 FIN 재전송에 다시 ACK 보내기 위해서, 그리고 같은 4-tuple 새 연결에 옛 segment가 혼선 일으키는 걸 막기 위해서. 안전한 해결 우선순위는 HTTP keepalive > tcp_tw_reuse > SO_REUSEADDR. tcp_tw_recycle은 NAT 환경에서 망하고 커널 4.12에서 삭제됐어요 — 절대 금지.

더 깊은 건 [03-osi-7-layers-and-tcp-tls.md](./03-osi-7-layers-and-tcp-tls.md).

---

## ⑤ 라우팅 — IP packet이 hop을 타고 가는 법 (★ MAC vs IP 분리)

### 무슨 일이 일어나는가

TCP segment가 IP packet으로 감싸지고, IP packet은 인터넷을 가로질러 destination IP까지 가야 한다. 클라이언트는 자기 routing table을 본다:

```
$ ip route show
default via 192.168.1.1 dev eth0
192.168.1.0/24 dev eth0
```

destination IP가 같은 LAN이면 직접 보내고, 다르면 default gateway로 보낸다. 거의 모든 외부 트래픽은 default gateway로 간다.

그런데 IP만으로는 Ethernet frame을 못 만든다. L2(Ethernet)는 **MAC 주소**로만 forward한다. 그래서 IP packet을 L2 frame으로 감싸기 전에 **ARP**(Address Resolution Protocol)로 "다음 hop IP의 MAC을 알려달라" broadcast하고 unicast reply를 받는다.

이제 진짜 핵심 — **IP는 end-to-end 식별자, MAC은 hop-to-hop 식별자**다. 패킷이 3 hop을 거치면서 어떻게 변하는지 보자:

```
   ┌──────┐  Hop1   ┌────┐  Hop2   ┌────┐  Hop3   ┌──────┐
   │Client├────────►│ R1 ├────────►│ R2 ├────────►│Server│
   └──────┘         └────┘         └────┘         └──────┘

   필드             Hop1        Hop2        Hop3
   ───────────────────────────────────────────────
   src_ip          Client      Client      Client     ← 불변
   dst_ip          Server      Server      Server     ← 불변
   src_mac         Client      R1_out      R2_out     ← 매 hop 바뀜
   dst_mac         R1_in       R2_in       Server     ← 매 hop 바뀜
   TTL             64          63          62         ← 감소
   IP checksum     A           B           C          ← 재계산
   TCP/payload     ★           ★           ★          ← 절대 안 건드림
```

각 router가 하는 일: ① FCS 검증 + dst MAC 매치 확인 → ② Ethernet 헤더 떼기 → ③ IP checksum 검증 + TTL-1 → ④ routing table 조회로 next-hop IP 결정 → ⑤ next-hop ARP로 MAC 알아냄 → ⑥ 새 Ethernet frame 조립 + IP checksum 재계산 → ⑦ 송출. **TCP/payload는 절대 안 건드린다** — 그게 router의 정의.

TTL이 0이 되면 router가 ICMP Time Exceeded를 보내고 패킷을 drop한다. `traceroute`가 이 메커니즘을 거꾸로 이용해서 경로상의 router를 노출시킨다.

### 왜 이렇게 동작하나

MAC은 같은 LAN(broadcast domain) 안에서만 의미가 있다. router는 LAN 경계 — 매 hop마다 다른 LAN으로 넘어가니까 L2 frame을 새로 만들어야 한다. 반면 IP는 처음부터 끝까지 같아야 한다 — 안 그러면 응답이 돌아올 때 src/dst를 못 맞춘다. 이게 **계층 분리의 본질** — L3는 end-to-end addressing, L2는 link-local forwarding.

NAT는 router가 본업을 넘어 L4까지 inspect해서 src_ip/src_port를 갈아치우는 부가 기능이다. end-to-end 원칙을 깨는 대신 IPv4 주소 고갈을 해결.

### 다이어그램

```
[Host 192.168.1.10]
   │ routing table 조회: dst=93.184.216.34 → default → 192.168.1.1
   │
   ▼
[ARP] "192.168.1.1의 MAC?" → broadcast → reply
   │ ARP cache에 저장 (TTL 60s~4분)
   │
   ▼
[Ethernet frame 송신]
   src MAC: Client NIC    dst MAC: bb:bb:.. (gateway)
   src IP : 192.168.1.10  dst IP : 93.184.216.34  (그대로!)
   │
   ▼
[Default Gateway = R1]
   │ frame 받음 → IP packet 추출 → TTL 검증·감소 → 다음 hop ARP
   │
   ▼
[ISP edge] → [Tier 2] → [Tier 1 backbone] → ... → BGP AS path
   │ 각 router: IP는 그대로, MAC만 다음 hop으로
   │
   ▼
[목적지 LAN의 마지막 router] → ARP로 Server MAC → 최종 frame 송신
```

### 면접에서 이렇게 물으면

**Q**: "MAC은 hop마다 변하는데 IP는 안 변한다. 왜?"
> MAC은 same-LAN next-hop 주소예요. router는 LAN 경계니까 매 hop마다 L2 frame을 새로 만들면서 src/dst MAC을 갱신합니다. IP는 end-to-end 식별자 — 변하면 응답을 못 돌려받습니다. 그래서 매 hop마다 Ethernet 헤더는 떼고 다시 조립, IP 헤더는 그대로 두고 TTL만 -1 + checksum 재계산. NAT는 이 원칙을 깨고 src_ip/src_port를 갈아치우는 부가 기능 — IPv4 주소 고갈 대응으로 도입.

**Q**: "라우터는 정확히 어떤 일을 하나요?"
> ① 들어온 frame의 FCS 검증 + dst MAC 매치 → ② Ethernet 헤더 떼기 → ③ IP checksum 검증 + TTL-1 → ④ routing table 조회로 next-hop 결정 → ⑤ ARP로 next-hop MAC 알아냄 → ⑥ 새 frame 조립 + IP checksum 재계산 → ⑦ 송출. TCP/payload는 절대 안 건드립니다. 그게 router의 정의.

더 깊은 건 [02-dns-and-routing.md](./02-dns-and-routing.md), [03-osi-7-layers-and-tcp-tls.md](./03-osi-7-layers-and-tcp-tls.md).

---

## ⑥ OSI 7계층 — 위 모든 게 동시에 동작하는 캡슐화

### 무슨 일이 일어나는가

지금까지 단계별로 본 것 — URL 파싱, percent-encoding, DNS, TCP/TLS, 라우팅 — 은 사실 **동시에** 일어난다. 한 HTTP 메시지가 wire로 나갈 때, 그 패킷은 7계층 헤더를 **동시에** 입고 있다. 이게 캡슐화(encapsulation)다.

```
─────────────────────────────────────────────────────────────────
 L7 (HTTP)    GET /users/%EA%B9%80... HTTP/1.1\r\nHost: ...\r\n\r\n
                          │
                          ▼
 L6 (TLS)     [TLS rec hdr 5B | AEAD-encrypted HTTP | tag 16B]
                          │
                          ▼
 L4 (TCP)     [TCP hdr 20B  | TLS record bytes                 ]
               src=54321 dst=443  seq/ack  flags=PSH+ACK
                          │
                          ▼
 L3 (IP)      [IP hdr 20B  | TCP segment                        ]
               src=10.0.0.5 dst=93.184.216.34  ttl=64  proto=6
                          │
                          ▼
 L2 (Eth)     [Eth 14B | IP packet | FCS 4B                    ]
               dst_mac=게이트웨이 (ARP로 알아냄)
               src_mac=내 NIC  ethertype=0x0800
                          │
                          ▼
 L1            ─── bits on wire ─── (전기/광/RF)
─────────────────────────────────────────────────────────────────

송신측: 위→아래로 헤더 입힘
수신측: 아래→위로 헤더 벗김 (각 계층은 자기 헤더만 보고 다음으로)
```

각 계층의 책임:

| L | 이름 | PDU | 식별자 | 핵심 책임 | 대표 |
|---|---|---|---|---|---|
| L7 | Application | message | (app) | end-user 의미론 | HTTP, gRPC, DNS |
| L6 | Presentation | message | - | 직렬화·압축·**암호화** | TLS, JSON, gzip |
| L5 | Session | - | session id | 연결 lifecycle, 인증 | TLS handshake |
| L4 | Transport | segment | **port** | 프로세스 식별, 신뢰성 | TCP, UDP, QUIC |
| L3 | Network | packet | **IP** | 라우팅 (다른 LAN) | IPv4/v6, ICMP |
| L2 | Data Link | frame | **MAC** | same-LAN, 오류 검출 | Ethernet, Wi-Fi |
| L1 | Physical | bit | - | 전기/광/전파 신호 | 1000BASE-T |

각 계층이 자기 헤더를 더하고, 자기만의 **검증**을 한다:
- L1: 신호 무결성
- L2: Ethernet FCS (CRC-32) — link-local 우연 손상
- L3: IP checksum + TTL — router가 매 hop 재계산
- L4: TCP checksum + seq/ack — end-to-end 우연 손상
- L6: TLS HMAC/AEAD — **악의적 변조**
- L7: 비즈니스 (Content-Length, auth, CSRF)

### 왜 이렇게 동작하나

**변화 격리**가 본질이다. L1이 구리에서 광섬유로 바뀌어도 L7 HTTP는 한 줄도 안 바뀐다. L4가 TCP에서 QUIC으로 바뀌어도 L7 코드는 거의 동일. 이게 30년 전 인터넷 설계자들이 **계층화**라는 한 단어로 이뤄낸 가치.

같은 데이터를 여러 계층에서 검증하는 이유는 **다른 신뢰 모델**이기 때문. FCS는 케이블/NIC의 random 손상, TCP checksum은 router 메모리의 random 손상, TLS HMAC은 **적대적 변조**를 잡는다. checksum은 random 오류만 잡지 의도적 변조는 못 잡는다 — 그래서 TLS가 별도로 필수.

### 다이어그램

```
보낼 메시지: GET /users/%EA%B9%80... HTTP/1.1

┌─────────────────────────────────────────────────────┐
│ L7 application data                                  │
└─────────────────────────────────────────────────────┘
                    │ 위→아래 (캡슐화)
                    ▼
┌────────┬────────────────────────────────────────────┐
│ TLS hdr│ L7 (encrypted with AEAD)                    │  ★ L6 TLS
└────────┴────────────────────────────────────────────┘
                    │
                    ▼
┌────────┬─────────┬──────────────────────────────────┐
│ TCP hdr│ TLS hdr │ L7                                │  ★ L4 TCP
│ src/dst│         │                                   │
│  port  │         │                                   │
└────────┴─────────┴──────────────────────────────────┘
                    │
                    ▼
┌─────────┬────────┬─────────┬───────────────────────┐
│ IP hdr  │ TCP    │ TLS     │ L7                     │  ★ L3 IP
│ src/dst │        │         │                        │
│   IP    │        │         │                        │
└─────────┴────────┴─────────┴───────────────────────┘
                    │
                    ▼
┌────────┬─────────┬────────┬─────────┬──────────────┐
│ Eth hdr│ IP      │ TCP    │ TLS     │ L7       │FCS│  ★ L2 Eth
│ src/dst│         │        │         │          │   │
│  MAC   │         │        │         │          │   │
└────────┴─────────┴────────┴─────────┴──────────────┘
                    │
                    ▼ L1: 비트 스트림으로 wire에 송출

오버헤드: Eth 14 + IP 20 + TCP 20 + TLS 5 + AEAD 16 = 75 byte
+ FCS 4 + preamble 8 + IFG ≈ 86+ byte
payload 500 byte라면 ~14% 오버헤드
```

### 면접에서 이렇게 물으면

**Q**: "OSI 7계층이 왜 7개인가요? 그리고 왜 동시에 동작한다고 하나요?"
> 변화 격리가 목적이에요. L1이 구리→광섬유로 바뀌어도 L7은 영향 없게 책임을 분리. "동시에 동작한다"는 건, 한 패킷이 wire로 나갈 때 7계층 헤더를 동시에 입고 있다는 뜻. L7 HTTP 메시지를 L6 TLS가 암호화하고, 그걸 L4 TCP가 segment로 자르고, L3 IP가 라우팅 헤더를 붙이고, L2 Ethernet이 frame으로 감싸고, L1이 비트로 송출. 각 계층은 자기 헤더만 보고 다음 계층으로 넘긴다 — 그게 추상화.

**Q**: "TCP에 checksum 있는데 Ethernet FCS는 왜 또 있어요?"
> Defense in depth. FCS는 link-local 우연 손상(케이블/NIC), TCP checksum은 end-to-end 우연 손상(router 메모리 오염), TLS HMAC/AEAD는 **악의적 변조**를 잡습니다. 다른 신뢰 모델이라 다른 메커니즘. checksum은 random 오류만 잡고 적대적 변조는 못 잡아요 — 그래서 TLS가 필수.

**Q**: "MTU/MSS는 뭐고 왜 알아야 하나요?"
> MTU는 한 link가 한 번에 보낼 수 있는 frame 최대 크기, Ethernet은 보통 1500 byte. MSS는 그 안의 TCP payload 크기, IPv4면 MTU 1500 − IP 20 − TCP 20 = 1460. SYN 패킷의 TCP option에서 양쪽이 광고하고 작은 값 채택. 운영 함정은 **PMTUD black hole** — DF=1 큰 packet이 작은 MTU 구간(VPN tunnel 1400 같은)을 만나면 router가 "Fragmentation Needed" ICMP를 보내야 하는데, 보안 명분으로 ICMP 차단한 방화벽에선 그게 사라져요. 송신자는 응답 없으니 무한 재전송 → 대용량 응답 hang. 해결은 MSS clamping(`iptables ... TCPMSS --clamp-mss-to-pmtu`)이나 PLPMTUD(`net.ipv4.tcp_mtu_probing=1`) 또는 ICMP type 3 code 4를 통과 허용.

더 깊은 건 [03-osi-7-layers-and-tcp-tls.md](./03-osi-7-layers-and-tcp-tls.md).

---

## ⑦ 도착 직전 — Load Balancer

### 무슨 일이 일어나는가

목적지 AS(Autonomous System)에 도착한 패킷은 곧장 backend 서버로 가지 않는다. 그 앞에 **Load Balancer**가 서 있다. LB는 클라이언트와 backend 사이 **reverse proxy**다.

"LB는 트래픽 분산" 라고만 답하면 절반 모르는 거다. LB는 한 hub에서 **8가지 역할**을 동시에 처리한다:

| 책임 | 한 줄 요약 |
|---|---|
| ① 트래픽 분산 | 알고리즘(P2C/Least-Conn/Consistent Hash)으로 backend 선택 |
| ② SSL/TLS termination | 여기서 TLS 풀어 cert 중앙 관리 + backend CPU 절약 + observability |
| ③ Health check | shallow(`/live`) + deep(`/ready`) + passive(실 5xx rate) |
| ④ Rate limiting | per-IP/key/endpoint, token vs leaky bucket |
| ⑤ Sticky session | cookie/IP/consistent-hash. 가능하면 stateless 권장 |
| ⑥ Routing | path/host/header 기반 분기, canary, A/B test |
| ⑦ WAF | OWASP Top 10 차단 (SQLi/XSS/CSRF/path traversal) |
| ⑧ DDoS 흡수 | L3/L4는 edge anycast, L7은 in-front LB |
| (+) Observability | 모든 트래픽 hub → access log, P50/P90/P99, 5xx rate |

LB는 두 종류로 갈린다:

- **L4 LB** (예: AWS NLB) — TCP 헤더만 본다. 5-tuple로 per-connection routing. 같은 conn의 모든 byte는 무조건 같은 backend. SSL passthrough만. 매우 빠름, 게임/극저 latency.
- **L7 LB** (예: AWS ALB, Nginx, Envoy) — HTTP payload까지 풀어본다. per-request routing. 같은 conn 안에서도 요청 #1과 #2가 다른 backend로 갈 수 있음. SSL termination 필수. 일반 웹/API.

분산 알고리즘 중 모던 default는 **P2C (Power of Two Choices)** — 무작위 2개 중 더 한가한 쪽. max queue length가 random은 log N인데 P2C는 log log N. Least-Conn처럼 정확하면서 전역 state 불필요. Envoy/Linkerd/Finagle가 채택. Sticky session이 필요하면 **Consistent Hash** — ring 위 배치라 backend 추가/제거 시 1/N만 재배치.

LB가 backend 한 대를 고른 직후, LB는 자체 **upstream keepalive pool**에서 그 backend로의 persistent TCP connection을 하나 꺼낸다. 매 요청마다 새 TCP+TLS handshake면 작은 요청에 handshake 비용(수십 ms)이 더 크다 — 그래서 LB↔backend는 연결을 재사용한다.

### 왜 이렇게 동작하나

LB의 본질은 "**서버 군집 앞단의 통합 entrypoint**"라는 추상화다. backend는 "혼자인 듯" 살고 LB가 SSL/retry/rate-limit/관측을 다 흡수한다. 그래서 cert 100대에 일일이 배포·갱신할 필요 없이 LB 한 곳만 관리, backend 추가/제거는 LB에 등록만 하면 되고, 죽은 backend는 health check로 격리한다.

"LB가 SPoF 아니냐"는 흔한 오해 — multi-AZ active-active로 해소한다. 실제로는 **여러 위험을 한 곳에 모아 관리 가능하게 격리**하는 장치다.

### 다이어그램

```
[Client (TLS)] ───▶ [Internet] ───▶ ┌──────────────────┐
                                     │ Load Balancer     │
                                     │  - SSL termination│
                                     │  - Health check   │
                                     │  - Rate limit     │
                                     │  - WAF            │
                                     │  - Routing        │
                                     │  - Observability  │
                                     │                   │
                                     │  분산 알고리즘    │
                                     │  (P2C / ConsHash) │
                                     └────┬─────────┬────┘
                                          │         │
                              upstream keepalive pool (재사용)
                                          │         │
                                ┌─────────┘         └─────────┐
                                ▼                             ▼
                          [Backend B1]                  [Backend B2]
                          (Nginx + Tomcat)              (Nginx + Tomcat)
```

### SSL termination 3가지 모드

LB에서 TLS를 어떻게 다룰지는 3가지 모드로 나뉜다:

```
(A) Passthrough (L4 LB만 가능)
    Client ═══TLS═══▶ LB ═══TLS═══▶ Backend
    LB는 packet만 전달. backend가 cert 보유 + CPU 부담.
    mTLS client cert 검증이 backend에서 필요할 때.

(B) Termination (가장 흔함)
    Client ═══TLS═══▶ LB ──── plain HTTP ────▶ Backend
    LB가 TLS 풀고 plain HTTP로 backend에. cert 중앙 관리, backend CPU 절약.
    내부망이 안전하다는 가정. 일반적인 웹 서비스.

(C) Re-encryption (mTLS internal)
    Client ═══TLS═══▶ LB ═══TLS'═══▶ Backend
    LB가 풀고 다시 새 TLS로. zero-trust, PCI-DSS 같은 규제.
    TLS 두 번 비용.
```

SSL termination이 LB에서 일어나야 하는 4가지 이유: ① cert 중앙 관리(backend 100대에 일일이 배포·갱신 불필요), ② backend CPU 절약(TLS handshake는 비쌈), ③ observability(평문이라야 access log/WAF/body 검사 가능), ④ HTTP/2 ALPN negotiation 중앙화(클라이언트와 h2 협상, backend는 h1로 받아도 됨). SNI(ClientHello의 hostname 평문) 덕에 한 LB IP + cert 여러 개(multi-tenant) 가능. ECH(Encrypted Client Hello)가 SNI까지 암호화하는 차세대.

### 면접에서 이렇게 물으면

**Q**: "LB가 분산 말고 또 뭐 하나요?"
> 8가지를 동시에 처리합니다 — 분산, SSL termination(cert 중앙 관리), health check(shallow/deep/passive), rate limit, sticky session, routing(path/host/canary), WAF, DDoS 흡수. 추가로 모든 트래픽 hub라 observability(access log, P99, 5xx rate) 자연 발생. LB의 본질은 "서버 군집 앞단의 통합 entrypoint" 추상화 — backend가 혼자인 듯 살게 해주는 mediator.

**Q**: "L4와 L7 LB 차이는? 같은 connection의 모든 요청이 같은 backend로 가나요?"
> L4는 TCP 헤더만 보고 5-tuple로 per-connection routing — 같은 conn의 모든 byte는 무조건 같은 backend. SSL passthrough만 가능. L7은 HTTP payload까지 풀어 per-request routing — 같은 conn 안 요청 #1과 #2가 다른 backend로 갈 수 있어요. SSL termination 필수. HTTP/2 multiplex와 gRPC에서 stream마다 분기 가능한 게 ALB가 gRPC를 지원하는 이유. AWS NLB(L4)+ALB(L7) 조합으로 고정 IP + WAF를 같이 쓰는 패턴이 흔합니다.

**Q**: "health check를 통과하는데 사용자는 5xx를 받습니다. 왜?"
> Shallow health 함정. `/health`가 200을 반환하지만 backend 내부에서 DB connection pool 고갈, downstream 호출 실패 같은 상황이 있어요. 해결은 `/health/ready`를 deep check로 — DB ping, Redis ping, 외부 의존 정상성. Cache(5~10초) + partial degradation 같이. 추가로 passive health(Envoy outlier_detection) — 실제 5xx rate를 보고 자동 격리. Panic threshold도 — healthy/total < 50%면 모두 healthy로 간주(fail open), 의존성 hiccup으로 80% unhealthy 판정되면 남은 20%에 폭주 cascading 막기 위해.

**Q**: "Rolling deploy 시 503 폭증, 어디부터 보나요?"
> Connection draining부터. `deregistration_delay`는 backend p99 × 2~3로(AWS 기본 300s), backend SIGTERM 핸들러로 새 요청 거절 + 진행 중 완료(Spring Boot `server.shutdown=graceful`), k8s `preStop` hook으로 readiness false + sleep. idempotent GET은 LB retry로 다른 backend 시도(POST는 중복 처리 위험). WebSocket 같은 long-lived는 close frame 보내 graceful close + client exponential backoff reconnect 패턴.

더 깊은 건 [04-load-balancer-deep-dive.md](./04-load-balancer-deep-dive.md).

---

## ⑧ Nginx — 첫 번째 서버

### 무슨 일이 일어나는가

LB가 고른 backend는 보통 **Nginx**다(또는 비슷한 reverse proxy). Nginx의 본질은 "8개 worker로 수만 동시 connection을 처리한다"는 것. 어떻게?

Nginx는 **master/worker process 모델**이다. master는 nginx.conf 로드, listening socket 생성, worker 관리만 한다. 실제 요청 처리는 worker가 한다 — CPU core당 1개. 각 worker는 자기 **epoll 인스턴스**를 들고 독립 event loop를 돈다.

```c
for (;;) {
    timer = ngx_event_find_timer();
    n = epoll_wait(ep, events, N, timer);   // 커널에 "ready된 fd 있을 때까지 자라"
    for (i = 0; i < n; i++) {
        if (events[i].events & EPOLLIN)  c->read->handler(c);
        if (events[i].events & EPOLLOUT) c->write->handler(c);
    }
    ngx_event_expire_timers();              // keepalive_timeout, proxy_read_timeout
}
```

핵심은 **non-blocking I/O + state machine**. 각 connection이 read/write handler를 들고 있는 state machine. EAGAIN 만나면 다음 ready 이벤트로 점프. 한 worker가 수천 connection을 동시 진행한다. 모든 timeout은 timer로 관리.

Apache의 prefork 모델은 1 connection = 1 process라 10000 conn에 80GB stack이 필요했다(1999년 RAM의 100배). Nginx는 그걸 event-driven으로 깬다.

Nginx는 backend(보통 Tomcat)와의 통신에서 **upstream keepalive pool**을 유지한다. worker당 32개 정도의 idle connection을 들고, 새 요청이 오면 풀에서 꺼내 재사용. TCP+TLS handshake 5 RTT 비용을 0으로 만든다.

```nginx
upstream backend {
    server tomcat1:8080;
    server tomcat2:8080;
    keepalive 32;                  # worker당 풀 크기
    keepalive_timeout 60s;
}
location /api/ {
    proxy_pass http://backend;
    proxy_http_version 1.1;        # ⭐ 안 적으면 HTTP/1.0 → 매번 close
    proxy_set_header Connection "";# ⭐ client의 close 헤더 차단
}
```

이 두 줄(`proxy_http_version 1.1` + `Connection ""`)을 빠뜨리면 풀을 만들어도 매 요청마다 close → 0% 효과. 운영 단골 함정.

### 왜 이렇게 동작하나

C10K 문제(한 서버가 1만 동시 연결 처리)에 대한 답이 event-driven. Apache는 모듈 ABI가 blocking 모델에 묶여서 못 따라갔다. **레거시는 새 패러다임을 못 따라간다**가 Nginx 시대로 넘어간 진짜 이유.

epoll이 select/poll보다 빠른 이유 — select/poll은 매 호출마다 감시 fd 전체를 커널에 복사 + linear scan(ready 1개여도 N개 검사). epoll은 한 번 등록(red-black tree)하고 ready 시 커널이 callback push → epoll_wait()은 ready만 반환. **1만 fd 감시 시 select=매번 1만 검사, epoll=ready만 처리. 100배 차이**.

### 다이어그램

```
[systemd]
   │
   ▼
┌────────────────────────┐
│  master (root, 1개)     │  nginx.conf 로드, worker 관리
└─┬─────┬──────┬──────┬──┘
  │     │      │      │  fork() + setuid(nginx)
  ▼     ▼      ▼      ▼
[w1]  [w2]   [w3]   [w4]   ← CPU core당 1개, 각자 epoll 인스턴스
 │     │      │      │
 │  event loop (non-blocking I/O, state machine)
 │  11-phase HTTP processing
 │  ngx_pool_t (per-request memory)
 │  upstream keepalive pool (per-worker)
 │
 ▼
[Tomcat upstream pool — keepalive 32]
 │  idle conn1 (TCP/TLS done)
 │  idle conn2
 │  idle conn3 ... 32
 │
 ▼
[Tomcat backend]
```

### 면접에서 이렇게 물으면

**Q**: "Nginx가 8개 worker로 수만 동시 connection을 처리하는 비결은?"
> event-driven + epoll + non-blocking I/O + state machine. worker가 CPU core당 1개, 각자 epoll 인스턴스. 각 connection이 read/write handler를 들고 있는 state machine이라 EAGAIN 만나면 다음 ready 이벤트로 점프. blocking이면 worker 전체가 멈추니까 socket은 무조건 O_NONBLOCK. Apache prefork는 1 conn = 1 process라 10000 conn에 80GB stack 필요했지만 Nginx는 event 모델로 깼습니다.

**Q**: "Nginx의 upstream keepalive 풀이 왜 중요한가요?"
> Tomcat과의 TCP+TLS handshake 비용을 0으로 만들기 위해서요. keepalive 없으면 매 요청마다 3 RTT(TCP) + 1~2 RTT(TLS) = 5ms 오버헤드 + TIME_WAIT 폭증으로 ephemeral port 고갈. 함정은 `proxy_http_version 1.1` + `proxy_set_header Connection ""` 두 줄 — 이거 빠뜨리면 default가 HTTP/1.0이라 매 요청마다 close, 풀 만들어도 0% 효과.

**Q**: "Nginx에서 간헐적 502가 발생하는 가장 흔한 원인은?"
> Keepalive race입니다. Nginx 풀에 있는 idle conn을 backend가 먼저 close하는 시나리오 — Nginx `keepalive_timeout 60s` > backend idle timeout 30s 같은 설정. backend가 conn을 FIN 했는데 Nginx는 모르고 그 conn에 요청 보내면 RST 받고 502. 해결은 Nginx keepalive_timeout < Backend idle timeout(예: 50s vs 75s) + `proxy_next_upstream error timeout http_502;` + `proxy_next_upstream_tries 2;`로 다른 backend 시도.

**Q**: "worker_connections 늘렸는데 동접이 안 늘어요. 왜?"
> kernel limit과 같이 봐야 합니다. `ulimit -n`(per-process FD limit)이 안 따라가면 fd 못 열어 의미 없음. `net.core.somaxconn`이 작으면 SYN burst에 accept queue drop. `net.ipv4.tcp_max_syn_backlog`도 같이 늘려야. nginx.conf의 `worker_rlimit_nofile 200000;`, `events { worker_connections 65535; }`, `listen ... backlog=65535 reuseport;` 한 세트 + systemd unit `LimitNOFILE=200000` + sysctl 한 세트.

더 깊은 건 [05-nginx-internals.md](./05-nginx-internals.md).

---

## ⑨ Tomcat — Servlet 실행

### 무슨 일이 일어나는가

Nginx가 upstream으로 던진 요청은 Tomcat에 도착한다. Tomcat은 JVM 안에서 도는 Servlet container. 핵심은 **NIO Connector의 3단 파이프라인**이다 — Acceptor → Poller → Executor.

```
[Client / Nginx upstream]
    │ TCP SYN
    ▼
┌────────────────────────────┐
│ Kernel TCP stack            │
│   accept queue              │ ← ★ acceptCount (default 100)
└────────────┬───────────────┘
             │ accept() blocking
             ▼
┌────────────────────────────┐
│ Acceptor thread (1~N)       │  serverSock.accept()
│  → pollerQueue.add(ch)     │  Poller에 hand-off
└────────────┬───────────────┘
             ▼
┌────────────────────────────┐
│ Poller thread (1~N)         │  Selector.open()
│  ch.register(OP_READ)      │  selector.select() == epoll_wait
│  → executor.execute(...)   │  Worker에 hand-off
└────────────┬───────────────┘
             ▼
┌────────────────────────────┐
│ Worker thread (Executor)    │  ← ★ maxThreads (default 200)
│  http-nio-8080-exec-N       │
│  1. byte read              │
│  2. Http11InputBuffer parse│
│  3. CoyoteRequest +        │
│     RequestFacade          │
│  4. Mapper → Wrapper       │
│  5. Filter chain           │
│  6. Servlet.service()      │
│     (= DispatcherServlet   │
│      = Spring Controller)  │
│  7. response write         │
│  8. keepalive면 Poller 재등록│
└────────────────────────────┘
```

세 단계로 나눈 이유 — 각 단계의 병목 특성이 다르다.
- **Acceptor**: `accept()`는 blocking이지만 빠르다. TCP 3-way 끝난 conn을 빨리 kernel queue에서 빼내야 queue가 안 찬다.
- **Poller**: `select()` 한 thread가 수천 connection의 OP_READ 이벤트를 epoll로 동시 감시.
- **Worker**: byte parsing + Servlet + DB 호출은 시간 들어서 thread 많이 둠.

여기서 **3대 한도**가 중요하다. 모두 다른 위치, 다른 의미:

| 한도 | 위치 | 무엇을 제한 | 초과 시 |
|---|---|---|---|
| **acceptCount** (100) | Kernel | accept queue 크기 (= listen backlog) | 새 SYN 거부 → "Connection refused" |
| **maxConnections** (NIO 10000) | Tomcat Acceptor | Tomcat이 보유한 socket 총수 | Acceptor block → kernel queue 적체 → 503 |
| **maxThreads** (200) | Tomcat Executor | 동시 처리 중 요청 수 | queue 적체 → 응답 시간 폭증 또는 503 |

핵심 통찰: **NIO에서는 maxConnections ≫ maxThreads가 정상**. keep-alive idle connection은 Poller가 epoll로 감시하므로 Worker thread를 점유하지 않는다. 그래서 connection 10000개 들고 있어도 Worker는 200개로 충분.

byte stream이 `HttpServletRequest`로 변환되는 흐름:
1. Worker가 socket에서 byte 읽음.
2. `Http11InputBuffer.parseRequestLine()` + `parseHeaders()`로 CRLF 단위 파싱.
3. `CoyoteAdapter.service()`가 `Request`를 `RequestFacade`로 감싸 Servlet API 표준 객체 생성.
4. `Mapper`가 URI를 Host → Context → Wrapper로 매핑.
5. Filter chain 통과 → `DispatcherServlet.service()` → Spring Controller 진입.

### 왜 이렇게 동작하나

Tomcat 4의 BIO(1 conn = 1 thread)는 connection이 많아지면 thread 폭증으로 죽었다. Tomcat 6의 NIO가 Selector + 3단 분리로 적은 thread로 수천 connection 처리. 현대 표준은 NIO. JDK 21에선 Virtual Thread Executor 옵션이 추가되어 maxThreads 제한이 사실상 무한이 되지만, downstream(DB pool)은 여전히 진짜 자원이라 그쪽이 새 병목이 된다.

표준 ThreadPoolExecutor는 "queue 차면 thread 추가"인데 unbounded queue면 max 영영 안 늘어남. Tomcat은 `TaskQueue.offer()`를 override해서 "thread 먼저 늘리고 max 도달 후에만 queue 사용" — 웹 서버는 throughput보다 latency가 중요해서.

### 다이어그램

```
한 요청이 Tomcat에서 통과하는 한도:

[Client] ─SYN─▶ [Kernel accept queue]  ◀── acceptCount (default 100)
                       │ accept()
                       ▼
                [Tomcat Acceptor]
                conn count++ ◀── maxConnections (default 10000)
                       │
                       ▼
                [Poller register]
                       │ OP_READ
                       ▼
                [Executor.execute()] ◀── maxThreads (default 200)
                       │ Worker thread
                       ▼
                byte → Http11InputBuffer → CoyoteRequest
                       → RequestFacade → Mapper
                       → Filter chain → DispatcherServlet
                       → Spring Controller
```

### 면접에서 이렇게 물으면

**Q**: "Tomcat은 byte stream을 어떻게 HttpServletRequest로 바꾸나요?"
> NIO Connector의 3단 파이프라인 — Acceptor → Poller → Executor. Acceptor가 `accept()`로 TCP 연결 받아 Poller에 hand-off. Poller가 `select()`로 OP_READ 이벤트를 감시하다 ready면 Executor에 hand-off. Worker thread가 socket에서 byte 읽고 `Http11InputBuffer`가 CRLF 단위로 파싱, `CoyoteRequest`를 `RequestFacade`로 감싸 Servlet API 표준 객체로 변환, Mapper가 Host→Context→Wrapper 매핑, Filter chain 거쳐 DispatcherServlet(=Spring 진입). 3단으로 나눈 이유는 각 단계 병목 특성이 달라서 — accept는 빠르고, poll은 N:1 감시, worker는 시간 들어서.

**Q**: "acceptCount, maxConnections, maxThreads가 다 있는데 셋이 어떻게 다른가요?"
> 위치와 의미가 다 다릅니다. acceptCount는 kernel TCP accept queue 크기 — `min(acceptCount, somaxconn)`로 잘림, 초과면 새 SYN 거부 "Connection refused". maxConnections는 Tomcat이 든 socket 수 — 초과면 Acceptor block → kernel queue 적체. maxThreads는 동시 처리 중 요청 수 — 초과면 queue 적체 또는 503. NIO에서는 idle keepalive conn이 Worker 점유 안 하므로 maxConnections ≫ maxThreads가 정상.

**Q**: "Tomcat의 ThreadPool이 표준 JDK ThreadPoolExecutor와 어떻게 다른가요?"
> 표준은 "core 다 차면 queue, queue 차면 max까지 thread 추가". `LinkedBlockingQueue`(unbounded)를 쓰면 max는 영영 안 늘어남. Tomcat은 `TaskQueue.offer()`를 override해서 idle worker 없으면 false 반환 → 새 thread 만들도록 유도. **thread 먼저 늘리고 max 도달 후에만 queue 사용** — 웹 서버는 throughput보다 latency가 중요해서 응답성 우선. 다만 maxQueueSize 작게 + max 도달 시 `RejectedExecutionException` → HTTP 503.

**Q**: "Worker thread가 RUNNABLE인데 hang일 수 있나요?"
> 가능합니다. socket read syscall이 blocking이면 JVM은 RUNNABLE로 표시(커널 안에서 sleep). 5초 간격 jstack 2~3회 떠서 같은 stack이면 hang. interrupt로는 못 풀음 — socket close해야 IOException 발생. 운영에서는 미리 `socketTimeout` 설정 + circuit breaker로 차단. 근본적으론 NIO/Reactive로 전환하면 timeout이 자연스러움. JDK 21 Virtual Thread는 BIO 코드 그대로 + 수십만 thread + carrier thread freeze 안 됨 — Tomcat 10.1+ `StandardVirtualThreadExecutor`가 표준화 시작.

더 깊은 건 [06-tomcat-internals.md](./06-tomcat-internals.md).

---

## ⑩ Spring → JDBC → DB connection pool (HikariCP)

### 무슨 일이 일어나는가

Tomcat Worker thread가 Spring Controller에 도달하면, Controller는 보통 DB를 쓴다. 그런데 DB에 직접 TCP 연결을 매번 새로 만드는 건 너무 비싸다 — TCP 3-way(1.5 RTT) + TLS handshake(1 RTT) + DB Startup Message + Authentication(SCRAM-SHA-256 = 2.5 RTT) + ReadyForQuery. 총 10~50ms (local) ~ 500ms (cross-AZ + TLS + SCRAM).

그래서 **HikariCP**가 미리 N개의 connection을 유지하고 빌려준다. `dataSource.getConnection()` 평균 ~200ns. C3P0/DBCP의 수천~수만 ns 대비 100배. 빠른 이유는 **ConcurrentBag** 자료구조 — lock-free, ThreadLocal warm cache(같은 thread가 다시 빌리면 같은 conn 반환 → CPU cache 친화).

```
[Spring Controller]
   │ jdbcTemplate.query(...) 또는 entityManager.find(...)
   ▼
[DataSource.getConnection()]
   │
   ▼
[HikariCP ConcurrentBag]
   │ 1. threadList에서 CAS로 NOT_IN_USE → USE
   │      └─ found: ★ FAST PATH (lock 없이 수십 ns)
   │ 2. 없으면 sharedList 순회 (CopyOnWriteArrayList, read lock 없음)
   │ 3. 없으면 비동기 create + handoffQueue.poll(timeout=3s)
   │ 4. timeout: SQLException("Connection is not available")
   │
   ▼
[HikariProxyConnection 반환]
   │ 실제 PoolEntry를 감싼 proxy
   │ conn.close()는 실제 close 아니라 풀에 return
   │
   ▼
[Spring이 ThreadLocal에 conn 등록]
   │ TransactionSynchronizationManager
   │ @Transactional 메서드 안의 모든 JDBC 호출이 같은 conn 사용
```

여기서 알아둘 핵심 옵션:
- `maximumPoolSize` (default 10) — 너무 크면 DB CPU 폭증, 너무 작으면 wait queue 적체. 권장 `(core × 2) + spindle`.
- `connectionTimeout` (default 30s) — `getConnection()` 대기 한도. **3s 권장** — cascading 방어, 빠른 실패.
- `maxLifetime` (default 30분) — conn 강제 갱신 주기. **firewall/NAT idle보다 짧게**(보통 3분) — 침묵 살인자 방어.
- `leakDetectionThreshold` (default 0) — leak 감지. **10s 권장** — try-with-resources 누락 잡음.

이게 한 요청이 통과하는 **두 번째 풀**이다. 첫 번째는 Nginx upstream keepalive(LB↔Nginx, Nginx↔Tomcat), 지금이 Tomcat↔DB. 사실 한 요청은 **7~13개의 풀**을 통과한다:

```
1. Kernel TCP backlog (LB/Nginx/Tomcat)
2. LB conntrack table
3. LB → Nginx keepalive pool
4. Nginx worker_connections
5. Nginx → Tomcat upstream keepalive pool
6. Tomcat acceptCount (kernel backlog)
7. Tomcat maxConnections
8. Tomcat Executor maxThreads
9. HikariCP DB connection pool          ★ 지금 이 단계
10. HTTP client pool (외부 API 호출용)
11. Redis connection pool (Jedis면)
12. DB max_connections (server side)
13. ForkJoinPool.commonPool / @Async executor
```

**핵심 통찰**: 모든 풀이 사슬로 연결되어 있다. 어느 한 풀이 비면 위쪽이 적체된다.

### 왜 이렇게 동작하나

Connection 생성 비용이 0이면 풀이 없다. 풀이 있는 이유 = 생성 비용이 응답 시간을 잡아먹기 때문. 1000 req/s × 30ms handshake면 DB가 즉시 죽는다. 풀이 N개 유지하고 빌려주면 비용이 거의 0.

**Goldilocks 문제**: 너무 작으면 wait queue 적체 → P99 폭발, 너무 크면 DB CPU 폭증·context switch 부담. PostgreSQL은 1 conn = 1 process(heavy, ~10MB)라 `max_connections=100`이 흔함. 앱 30 인스턴스 × HikariCP 20 = 600 vs DB max 200 → **PgBouncer transaction mode**로 multiplex 필요.

`(core × 2) + spindle` 공식이 작아 보이는 이유 — 동시 query 늘면 context switch 폭발, query 처리 시간 자체가 늘어남. **작은 pool로 빠른 turnover가 큰 pool로 느린 처리보다 빠르다.**

### 다이어그램

```
   Spring Controller
        │
        ▼
   ┌──────────────────────────────────┐
   │  HikariCP ConcurrentBag           │
   │   ┌──────────────────────────┐   │
   │   │ threadList (ThreadLocal) │ ◄─┼─── 같은 thread 재borrow
   │   │  - WeakReference         │   │     ★ FAST PATH (수십 ns)
   │   └──────────────────────────┘   │
   │   ┌──────────────────────────┐   │
   │   │ sharedList (전체 conn)    │ ◄─┼─── 다른 thread는 여기서 찾음
   │   │  - CopyOnWriteArrayList  │   │
   │   └──────────────────────────┘   │
   │   ┌──────────────────────────┐   │
   │   │ handoffQueue              │ ◄─┼─── 모두 in-use면 대기
   │   │  - SynchronousQueue       │   │     connectionTimeout (3s)
   │   └──────────────────────────┘   │
   └──────────────────────────────────┘
        │ borrow된 HikariProxyConnection
        ▼
   [JDBC PreparedStatement]
        │
        ▼  conn.prepareStatement("SELECT ... WHERE id = ?")
        ▼  ps.setLong(1, 42)
        ▼  rs = ps.executeQuery()
   ┌─────────────────────────┐
   │  Wire protocol           │
   │  Parse / Bind / Execute  │
   └──────────┬──────────────┘
              ▼
       [DB Backend Process]
```

### Pool 튜닝 — Little's Law

> **L = λ × W** (동시 처리 중인 작업 수 = 도착률 × 평균 처리 시간)

1000 req/s × 50ms = 50 동시 → Tomcat maxThreads ≥ 50. HikariCP는 thread가 DB만 두드리는 게 아니므로 보통 더 작아도 OK.

HikariCP 권장 공식 `(core × 2) + spindle` (8 core + SSD → 17)이 작아 보이는 이유 — 동시 query 늘면 context switch 폭발, query 처리 시간 자체 늘어남. **작은 pool로 빠른 turnover가 큰 pool로 느린 처리보다 빠르다**. 측정 기반 해석:

| utilization | wait_p99 | DB CPU | 진단 |
|---|---|---|---|
| < 50% | ≈ 0 | 정상 | pool 충분, 더 줄여도 OK |
| > 80% | 증가 | 정상 | pool 부족, 늘려야 |
| 100% | spike | 정상 | pool 부족 확정 |
| 100% | spike | 100% | **pool 늘려도 무의미** — SQL 튜닝/인덱스/sharding |

### 면접에서 이렇게 물으면

**Q**: "왜 또 connection pool이 필요한가요? Nginx에도 있는데."
> 각 풀은 다른 자원을 빌려줍니다. Nginx upstream keepalive는 LB↔Nginx 또는 Nginx↔Tomcat TCP 재사용, HikariCP는 Tomcat↔DB JDBC connection 재사용. DB conn 생성은 TCP+TLS+Startup+Auth+ReadyForQuery 5단계라 cross-AZ면 500ms 비용. 매 요청마다 새로 만들면 DB CPU 폭증 + ephemeral port 고갈 + max_connections 초과. 한 요청은 7~13개 풀을 통과합니다.

**Q**: "HikariCP가 표준이 된 이유는?"
> `getConnection()` 평균 ~200ns(DBCP/c3p0의 100배). ConcurrentBag 자료구조 — lock-free + ThreadLocal warm cache로 같은 thread 재borrow 시 같은 conn 반환(CPU cache 친화). 코드도 ~130KB라 JIT 친화적. 핵심 옵션 4개: maximumPoolSize, connectionTimeout(3s 권장 — cascading 방어), maxLifetime(firewall idle보다 짧게), leakDetectionThreshold(10s).

**Q**: "HikariCP maxLifetime을 기본 30분으로 두면 어떤 사고가 흔한가요?"
> AWS NAT/firewall이 보통 5분 idle 후 conn을 silent drop하는데 HikariCP는 모릅니다. 다음 query에 RST/timeout. **침묵의 살인자**예요. maxLifetime을 firewall idle × 0.5(예: 3분)로 줄여 HikariCP가 먼저 destroy + recreate하게 합니다. TCP keepalive로 해결 안 되는 이유는 일부 firewall이 keepalive packet을 idle 카운트에서 제외 안 하기 때문.

더 깊은 건 [07-connection-pools-master.md](./07-connection-pools-master.md).

---

## ⑪ DB — query 처리

### 무슨 일이 일어나는가

JDBC가 보내는 SQL은 텍스트가 아니라 **wire protocol 메시지**다. PostgreSQL을 예로 들면, 모든 메시지는 `[type byte 1] [length 4] [payload]` 구조. `PreparedStatement`는 **Extended Query Protocol**의 5단계 메시지를 한 TCP write로 묶어 보낸다:

```
[Client] PreparedStatement.executeQuery()
   │
   ▼  one TCP write
┌──────────────────────────────────────────────────┐
│ P (Parse: "SELECT ... WHERE id = $1")             │  parse 1회 (또는 prepareThreshold 후)
│ B (Bind: portal, [42])                            │  parameter 별도 메시지 ★ injection 차단의 본질
│ D (Describe: portal)                              │  결과 column meta
│ E (Execute: portal, max_rows=N)                   │  cursor batch
│ S (Sync)                                          │  pipeline boundary
└──────────────────────────────────────────────────┘
   │
   ▼
[DB Backend Process]
   │ 1. Parser   (SQL → AST, syntax check)
   │ 2. Rewriter (view 전개, RULE)
   │ 3. Planner  (통계 pg_statistic 참조, plan tree 생성)
   │ 4. Executor (volcano model로 row 전달)
   │ 5. Storage  (Shared Buffer → 디스크)
   │
   ▼  응답
┌──────────────────────────────────────────────────┐
│ 1 (ParseComplete)                                 │
│ 2 (BindComplete)                                  │
│ T (RowDescription: column meta)                   │
│ D (DataRow) × N                                   │
│ C (CommandComplete: "SELECT N")                   │
│ Z (ReadyForQuery 'I')                             │
└──────────────────────────────────────────────────┘
```

**PreparedStatement가 injection을 구조적으로 막는 이유**: Bind 메시지의 parameter 값은 **SQL parser를 절대 거치지 않는다**. parse 단계에서 `$1`은 placeholder로만 인식되고, bind의 byte는 column literal value일 뿐. Statement의 escape는 임시방편이라 corner case 누락 가능하지만, PreparedStatement는 **wire에서 SQL과 parameter가 분리**되어 구조적 차단.

성능 측면도 — 같은 query 100번이면 Statement는 `100 × (parse + plan + exec)`, Prepared는 `1 × parse + 100 × exec`. parse는 200~500μs라 dominant.

ResultSet은 기본 **eager** — fetchSize=0이면 서버가 모든 row를 DataRow로 push, driver buffer에 누적. 1억 row × 1KB = 100GB → OOM. PG에서 lazy cursor로 받으려면 (1) `autoCommit=false`, (2) `setFetchSize(N)`, (3) `TYPE_FORWARD_ONLY` 3조건. autoCommit이 필수인 이유는 portal이 transaction에 묶여서.

### 왜 이렇게 동작하나

Wire protocol이 binary인 이유는 단순함과 속도. text라면 매번 parsing이 필요. binary는 길이 prefix만 보면 바로 분기. Parse/Bind 분리는 두 가지 가치 — ① **injection 구조적 차단**, ② **plan cache 재사용**(같은 template은 한 번만 parse + plan).

DB 내부 처리도 layer로 나뉜다 — Parser(syntax)/Rewriter(view 전개)/Planner(통계 기반 비용 최적화)/Executor(plan tree 순회)/Storage(buffer pool + WAL). 가장 흔한 운영 함정은 index 없는 WHERE → seq scan으로 100만 row 읽음. EXPLAIN으로 확인.

### 다이어그램

```
[JDBC PreparedStatement]
        │
        ▼  Extended Query Protocol
   ┌─────────────────────────────┐
   │  Parse  ─ Bind ─ Describe   │  ← injection 구조적 차단
   │  ─ Execute ─ Sync           │     parameter는 SQL parser 통과 X
   └──────────┬──────────────────┘
              ▼  one TCP write
   ┌─────────────────────────────┐
   │ PostgreSQL Backend Process   │
   │ ┌─────────────────────────┐ │
   │ │ Parser → AST            │ │
   │ │ Rewriter → view 전개     │ │
   │ │ Planner → plan tree     │ │← EXPLAIN으로 검증
   │ │ Executor → volcano model│ │
   │ │ Storage → Shared Buffer │ │← 25% RAM, 8KB page
   │ │        → WAL Writer     │ │← commit 시 sync
   │ └─────────────────────────┘ │
   └──────────┬──────────────────┘
              ▼
   ┌─────────────────────────────┐
   │ ParseComplete / BindComplete │
   │ RowDescription              │
   │ DataRow × N                 │
   │ CommandComplete             │
   │ ReadyForQuery               │
   └─────────────────────────────┘
```

### Transaction과 isolation — wire에서 어떻게 표현되나

Spring `@Transactional` 메서드 진입 시 wire에서 일어나는 일:

```
Spring TransactionManager.begin()
  → HikariCP.getConnection() → conn C
  → C.setAutoCommit(false) → wire: BEGIN (PG) / START TRANSACTION (MySQL)
  → [메서드 안 query 1, query 2 모두 같은 conn C로 흐름]
  → 메서드 정상 종료 → commit() → wire: COMMIT
  → 예외 → rollback() → wire: ROLLBACK
  → C.setAutoCommit(true) 복원, HikariCP.return(C)
```

왜 1 transaction = 1 connection — Transaction state(uncommitted change, lock, MVCC snapshot)는 server 측에서 connection에 묶임. 다른 connection은 그 변경 못 봄. Spring은 `TransactionSynchronizationManager`의 ThreadLocal에 (DataSource → Connection) map을 들고 같은 메서드 안의 JDBC 호출이 같은 conn을 쓰게 한다.

**Isolation Level**(`conn.setTransactionIsolation`)도 wire 메시지로 표현 — `SET TRANSACTION ISOLATION LEVEL REPEATABLE READ`. 4표준:
- READ UNCOMMITTED (거의 안 씀)
- READ COMMITTED (PG default) — 가장 흔함
- REPEATABLE READ (MySQL InnoDB default) — 일관 snapshot
- SERIALIZABLE — 정확한 회계, lock/retry 비용 ↑

**Connection state leak** — pool 재사용 시 위험. autoCommit/isolation/readOnly/schema는 HikariCP가 자동 reset하지만 session variable(`SET statement_timeout`), advisory lock(`pg_advisory_lock`), prepared cache, temp table은 안 됨. 방어는 SET 자제, `maxLifetime`으로 주기적 폐기, transactional advisory lock(`pg_advisory_xact_lock`) 선호.

### 면접에서 이렇게 물으면

**Q**: "PreparedStatement는 어떻게 SQL injection을 구조적으로 막나요?"
> parameter를 SQL과 별도 wire 메시지로 보냅니다. parse 단계에서 SQL template만 AST로 만들고, bind의 parameter byte는 절대 SQL parser를 거치지 않아요 — column literal value일 뿐. Statement처럼 escape에 의존하지 않고 **wire에서 SQL과 parameter가 분리**되어 구조적 차단. 추가 보너스는 같은 template은 1회 parse로 plan cache까지 재사용.

**Q**: "ResultSet에 fetchSize 안 설정하고 1억 row 쿼리하면?"
> JDBC default fetchSize=0은 eager — 서버가 모든 row를 driver buffer로 push, client heap OOM. PG에서 lazy cursor로 받으려면 autoCommit=false + setFetchSize(N) + TYPE_FORWARD_ONLY 3조건 필요. autoCommit이 필수인 이유는 portal이 transaction에 묶여서. MySQL은 setFetchSize(Integer.MIN_VALUE) streaming 또는 useCursorFetch=true.

**Q**: "Spring `@Transactional`의 두 query가 어떻게 같은 transaction에 묶이나요?"
> Spring TransactionInterceptor가 메서드 진입 시 DataSource.getConnection() + setAutoCommit(false)를 호출하고 그 conn을 TransactionSynchronizationManager의 ThreadLocal에 등록. 메서드 안의 JdbcTemplate/EntityManager가 DataSource.getConnection() 호출하면 Spring proxy가 ThreadLocal 먼저 확인해 같은 conn 반환. 같은 conn = 같은 wire transaction(BEGIN ... COMMIT 한 묶음). 그래서 한 transaction 안에서 호출되는 모든 JDBC는 같은 connection을 공유하고, 메서드 끝나면 commit() → setAutoCommit(true) 복원 → 풀에 반납.

**Q**: "idle in transaction이 위험한 이유와 진단법은?"
> `BEGIN` 후 query 안 하고 멈춘 connection이에요. 흔한 원인은 `@Transactional` 메서드 안에서 외부 API 호출(몇 분 대기), 예외 발생 후 rollback 누락, 너무 큰 @Transactional 범위. 영향은 ⓐ MVCC bloat — 그 tx 시점 row version 살려둠 → vacuum 못 함 → 테이블 비대화, ⓑ Lock 점유 → 다른 tx 대기, ⓒ Connection 점유 → pool 고갈. 진단은 `SELECT pid, state, state_change, query FROM pg_stat_activity WHERE state = 'idle in transaction' ORDER BY state_change ASC;`. 해결은 @Transactional 범위 최소화 + 외부 API 호출은 tx 밖으로 + `idle_in_transaction_session_timeout = '30s'` + 응급 시 `pg_terminate_backend(pid)`.

더 깊은 건 [08-db-connection-and-jdbc.md](./08-db-connection-and-jdbc.md).

---

## ⑫ 응답이 역순으로 — 모든 것이 뒤집힘

### 무슨 일이 일어나는가

DB가 row를 돌려주면, 모든 단계가 **정확히 역순으로** 풀린다.

```
DB가 row 반환 (DataRow × N + CommandComplete)
   │
   ▼
JDBC ResultSet (driver가 byte → Java 객체로 deserialize)
   │
   ▼
Spring Controller가 ResponseEntity 반환
   │
   ▼
Tomcat Http11OutputBuffer → SocketChannel.write()
   │
   ▼
Nginx가 응답 byte 받음 (proxy_buffering이면 통째 buffer 후 client에)
   │
   ▼
Load Balancer가 backend → client로 forward
   │  (L7면 HTTP 헤더 일부 수정 가능 — X-Forwarded-*, X-Request-Id)
   │
   ▼
응답 packet이 인터넷을 가로질러 역방향 라우팅
   │  (BGP 비대칭 흔함 — 요청과 다른 경로일 수 있음)
   │  IP는 src/dst 뒤집힘, MAC은 매 hop 새로 결정
   │
   ▼
클라이언트 TCP 재조립 → TLS 복호화 → HTTP 파싱
   │
   ▼
브라우저가 응답을 캐시에 저장 (Cache-Control 허용 시)
   │
   ▼
HTML 렌더링 / JSON 파싱 / DOM 업데이트
```

각 계층의 헤더가 **아래에서 위로** 벗겨진다. L1 비트 → L2 frame → L3 packet → L4 segment → L6 TLS decrypt → L7 HTTP parse.

연결은 keep-alive면 풀로 돌아가서 다음 요청을 기다린다. close면 4-way close → TIME_WAIT(2MSL) → CLOSED.

### 왜 이렇게 동작하나

각 계층이 "추가만 하고 제거 안 하면" 정보가 누적되어 폭발한다. 송신측이 위→아래로 헤더를 입혔으니 수신측이 아래→위로 벗기는 게 자연스러운 대칭. 이게 **encapsulation/decapsulation의 본질**.

요청 경로와 응답 경로가 다를 수 있는 이유는 BGP routing이 비대칭이라서. ISP들이 traffic engineering으로 outbound/inbound 정책을 다르게 설정. RTT 측정할 때 절반씩 갈라서 보면 안 되는 이유.

### 다이어그램

```
[DB] ── DataRow × N ──▶ [Tomcat Worker]
                          │ Java 객체 → JSON 직렬화
                          ▼
                        [Tomcat Http11OutputBuffer]
                          │ HTTP response 메시지 조립
                          ▼
                        [Nginx] proxy_buffering으로 통째 buffer
                          │
                          ▼
                        [Load Balancer]
                          │ TLS 재암호화 (re-encrypt 모드면)
                          ▼
                        [Internet ◀ 응답 packet]
                          │ 라우팅 (BGP 비대칭 가능)
                          ▼
                        [Client OS kernel]
                          │ L1 비트 → L2 frame → L3 packet
                          │ → L4 segment → L6 TLS decrypt
                          │ → L7 HTTP parse
                          ▼
                        [Browser]
                          │ Cache-Control이면 캐시 저장
                          │ HTML 렌더링 / JSON 파싱
                          ▼
                        [User가 응답을 본다]
```

### 면접에서 이렇게 물으면

**Q**: "응답이 돌아오는 길은 요청과 정확히 같은 경로인가요?"
> 항상은 아니에요. BGP routing이 비대칭이라서 ISP들이 outbound/inbound 정책을 다르게 둘 수 있어요. RTT 측정할 때 절반씩 갈라 계산하면 안 되는 이유. 패킷 단위로는 IP src/dst 뒤집힘, MAC은 매 hop 새로 결정. 응용 레벨로는 12단계가 그대로 역순으로 풀립니다 — L7→L1 거꾸로.

---

# 부록

여기까지가 메인 흐름이다. 부록 3개는 메인 흐름의 어느 단계에서든 면접관이 물고 들어올 가능성이 높은 토픽 모음.

---

## 부록 1: 모든 connection pool 한 그림에

한 요청이 통과하는 모든 풀을 한 자리에 모은다.

```
[Client]
   │  TCP SYN
   ▼
┌──────────────────────────────────────────────────────────┐
│ #1. Kernel TCP backlog (LB 측)                            │
│      somaxconn / tcp_max_syn_backlog                     │
└────────────────┬─────────────────────────────────────────┘
                 ▼
┌──────────────────────────────────────────────────────────┐
│ #2. LB conntrack table  (nf_conntrack_max)                │
└────────────────┬─────────────────────────────────────────┘
                 ▼
┌──────────────────────────────────────────────────────────┐
│ #3. LB → backend keepalive pool                            │
└────────────────┬─────────────────────────────────────────┘
                 ▼
┌──────────────────────────────────────────────────────────┐
│ #4. Nginx worker_connections (per worker)                  │
│      ulimit -n 보다 작아야 의미 있음                       │
└────────────────┬─────────────────────────────────────────┘
                 ▼
┌──────────────────────────────────────────────────────────┐
│ #5. Nginx → Tomcat upstream keepalive  (keepalive 32)     │
└────────────────┬─────────────────────────────────────────┘
                 ▼
┌──────────────────────────────────────────────────────────┐
│ #6. Tomcat acceptCount (kernel backlog, somaxconn 제한)   │
│ #7. Tomcat maxConnections (Tomcat socket 카운터)          │
│ #8. Tomcat Executor maxThreads (worker thread)            │
└────────────────┬─────────────────────────────────────────┘
                 ▼
       [Spring Application]
        ┌────────┬────────┬────────┬────────┐
        ▼        ▼        ▼        ▼        ▼
       #9      #10      #11      #13       #14
     HikariCP HTTP    Redis   ForkJoin   FD limit
     DB pool  client  pool    /Async     (per-proc
              pool             executor   + system)
        │        │        │
        │        ▼        ▼
        │   [외부 API]  [Redis 서버]
        ▼
┌──────────────────────────────────────────────────────────┐
│ #12. DB max_connections (server-side)                      │
│       PostgreSQL: 1 conn = 1 process (~10MB)              │
│       MySQL:      1 conn = 1 thread                       │
│       App 인스턴스 × HikariCP max ≤ DB max × 80%          │
└──────────────────────────────────────────────────────────┘
```

가로지르는 한도: 모든 connection은 file descriptor 1개씩 차지. `ulimit -n` (per-process), `fs.file-max` (system-wide) 한도를 넘으면 `Too many open files` → 어떤 pool도 새 conn 못 만듦. 컨테이너에서는 `LimitNOFILE=` 또는 `--ulimit nofile=` 명시 필요.

### 한 표로 — 각 풀의 위치 / 가득 찰 때 증상

| # | 풀 | 위치 | 가득 찼을 때 | 위로 전파되는 증상 |
|---|---|---|---|---|
| 1 | kernel SYN/ACCEPT queue | OS kernel | SYN drop | client `connect timeout` |
| 4 | Nginx worker_connections | Nginx process | accept 멈춤 | LB가 다른 backend로 |
| 5 | Nginx upstream keepalive | Nginx worker | 매번 새 TCP | TIME_WAIT 폭증, handshake 5 RTT 비용 |
| 6 | Tomcat acceptCount | OS kernel (Tomcat listen) | SYN drop | client `Connection refused` |
| 7 | Tomcat maxConnections | Tomcat Acceptor | accept 멈춤 | Nginx upstream에서 적체 |
| 8 | Tomcat maxThreads | Tomcat Executor | queue 적체 / reject | 503, P99 폭증 |
| 9 | HikariCP | Spring app | `getConnection` 대기 → timeout | Tomcat thread도 hang → #8까지 hang |
| 12 | DB max_connections | DB server | "too many clients" | #9에서 신규 conn 실패 |

### Cascading failure — 가장 흔한 시나리오

```
[T0. 정상]
HikariCP active=5/20  Tomcat busy=50/200

[T1. DB 한 query slow (lock or slow plan)]
1s 쿼리가 30s 로 늘어남 → HikariCP conn 30s 점유

[T2. 점유 누적]
새 요청 계속 → 모두 같은 query → HikariCP active=20/20 (MAX)
새 요청은 getConnection() 대기 → connectionTimeout 후 SQLException

[T3. Tomcat thread 점유]
대기 중인 Tomcat thread도 park → busy=200/200 (MAX)
새 요청은 Executor queue 적체 → maxConnections 도달 → accept 멈춤

[T4. Health check 실패]
/actuator/health도 thread 못 받아 timeout
LB가 인스턴스 unhealthy 마킹 → 트래픽 끊음
남은 인스턴스에 부하 폭주 → 같은 cascade 반복

[T5. 전체 다운]
모든 인스턴스 unhealthy → LB가 503/504
```

**방어 4가지**:
1. **`connectionTimeout` 짧게** (3s) — "느린 정상" 대신 "빠른 실패", thread 즉시 해방.
2. **Circuit Breaker** (Resilience4j) — 실패율 임계 넘으면 즉시 fallback, HikariCP 점유 방지.
3. **Bulkhead** — 비싼 query는 별도 semaphore로 격리.
4. **Layered timeout** — **안쪽일수록 짧게**.

```
client → LB:        30s   (max)
LB → Nginx:         25s
Nginx → Tomcat:     20s
Tomcat → DB query:  10s    ← 가장 안쪽이 가장 짧게
HikariCP getConn:    3s
```

더 깊은 건 [07-connection-pools-master.md](./07-connection-pools-master.md).

---

## 부록 2: timeout 4종 차이 (connection vs read vs write vs total)

production hang의 1순위 원인은 **timeout 누락**. 외부 호출 한 줄에 timeout이 빠지면, hang된 thread가 Tomcat thread pool을 점령하고 → 503 폭증 → cascading 마비.

### 시간축 다이어그램

```
client                                         server
  │── SYN ─────────────────────────────────────►│  ┐ ① Connection Timeout
  │◄──────── SYN-ACK ────────────────────────────│  │   (TCP 3-way)
  │── ACK ─────────────────────────────────────►│  ┘
  │── HTTP request (send buffer flush) ────────►│  ─ ② Write Timeout
  │                                              │     (send buffer)
  │   (server processing — DB, etc.)             │
  │                                              │
  │◄──── HTTP response chunk 1 (recv()) ─────────│  ┐
  │◄──── chunk 2 (recv() again, idle reset) ─────│  │ ③ Read Timeout
  │◄──── chunk N ────────────────────────────────│  ┘   (한 recv()의 idle)
  │── close ──────────────────────────────────►│
  ◄═══════════════════════════════════════════════►
                  ④ Total / Call Timeout
                     (요청 전체 시간)
```

### 4종 요약

| Timeout | 끊는 단계 | OS 메커니즘 | Java API | 미설정 시 위험 |
|---|---|---|---|---|
| **Connection** | TCP SYN→ACK | `connect()` + poll timer | `Socket.connect(addr, ms)` | Linux 기본 ~127초 대기 |
| **Read** | recv idle | `recv()` + SO_RCVTIMEO | `Socket.setSoTimeout(ms)` | 무한 (서버가 close 안 하는 한) |
| **Write** | send buffer flush | `send()` + SO_SNDTIMEO | client lib 별 옵션 | 무한 (peer가 ACK 안 줄 때) |
| **Total** | 전체 요청 | application timer | `OkHttp.callTimeout`, `HttpRequest.timeout`, gRPC deadline | redirect/retry로 무한 누적 |

**가장 중요한 함정**: Read timeout은 **"전체 응답 시간"이 아니다**. 매 recv()마다 reset. read timeout=5초인데 server가 4초마다 1 byte씩 보내면 영원히 안 끊김. 그래서 **Total/Call timeout이 별도 최후 보루**.

### 가장 흔한 사고 — timeout 안 걸어서 cascading failure

```
[정상]                          [외부 API 느려짐 + timeout 누락]
┌──────────┐                   ┌──────────┐
│ Tomcat   │                   │ Tomcat   │
│ thread   │──► 외부 API 100ms │ thread   │──► 외부 API 30s+ hang
│ pool=200 │                   │ pool=200 │
└──────────┘                   └──────────┘
in-flight 60                   thread 200개 모두 recv() block
                                 │
                                 ▼
                               새 요청 → queue full → 503
                                 │
                                 ▼
                               /actuator/health 응답 못 함
                                 │
                                 ▼
                               LB가 instance kill → 옆 instance로 load
                                 │
                                 ▼
                               같은 증상 → 시스템 전체 마비
```

**해결 4단계 (Resilience4j 4종 세트)**:
1. **timeout 명시** (모든 외부 호출, 특히 Total/Call)
2. **Circuit Breaker** (실패 누적 시 fast-fail)
3. **Bulkhead** (외부 호출별 별도 thread pool)
4. **Fallback** (graceful degradation)

### JDBC timeout 4계층

JDBC에서는 timeout이 **4계층 중첩**으로 작동한다:

```
요청 시작
   │
   ▼
① HikariCP.getConnection()          ← pool 고갈 방어
   connectionTimeout (3~5s 권장)
   │
   ▼
② driver.connectTimeout              ← DB 다운 방어 (TCP 3-way)
   │
   ▼
③ Statement.executeQuery()
   ├─ Statement.setQueryTimeout(5)  ← ★ DB가 SQL 죽임 (lock wait 방어)
   └─ driver.socketTimeout (10s)    ← recv idle 방어
   │
   ▼
④ DB 측 자체 timeout (백업 방어선)
   PostgreSQL: statement_timeout
   MySQL: max_execution_time
```

**핵심**: `socketTimeout`만으로는 부족. DB가 **lock wait** 중이면 socket은 idle 아니라 recv()가 안 끊김. 오직 `Statement.setQueryTimeout(N)`만이 잡을 수 있다(driver가 timer로 cancel signal 전송 → DB가 query 죽임).

권장 시간 관계 — **안쪽이 짧게**:
```
HikariCP connectionTimeout (3s)
  < Statement queryTimeout (5s)
  < socketTimeout (10s)
  < DB statement_timeout (10s)
  < @Transactional (15s)
  < Tomcat connection-timeout (20s)
  < LB upstream timeout (30s)
```

원칙: 외곽이 응답 못 받은 직후 즉시 다음 시도 가능하게.

더 깊은 건 [java-deep-dive/04-timeouts-connection-vs-read.md](../java-deep-dive/04-timeouts-connection-vs-read.md).

---

## 부록 3: 면접 빈출 질문 10개 + 한 줄 답

메인 흐름을 따라 가장 자주 나올 만한 질문들. 답변은 한 단락 이내로 압축.

### Q1. URL을 치면 무슨 일이 일어나나요?

> 12단계 — 브라우저 URL 파싱 + 캐시/HSTS 체크 → 한글이 있으면 (IME가 map → 브라우저가 UTF-8로 encode → URL parser가 `%HH`로 escape → HTTP client가 ASCII byte stream으로 serialize) → DNS 4계층으로 hostname → IP → TCP 3-way + TLS 1.3 handshake → IP packet이 라우터 hop을 타고 인터넷 횡단(IP는 그대로, MAC은 hop마다 갱신, TTL 감소) → Load Balancer에서 SSL termination + backend 선택 → Nginx worker가 epoll로 받아 upstream keepalive pool로 Tomcat에 전달 → Tomcat Acceptor→Poller→Executor 3단 파이프라인이 byte를 parse, URLDecoder가 unescape, CharsetDecoder가 decode해서 HttpServletRequest 완성 → Spring controller → HikariCP에서 DB connection 빌려 PreparedStatement로 SQL → DB가 Parser/Optimizer/Executor/Storage 거쳐 row 반환 → 응답이 정확히 역순으로 풀린다. 모든 단계에서 OSI 7계층이 동시에 동작하며 헤더를 입히고 벗긴다.

### Q2. 한글이 URL에 그대로 못 들어가는 이유는?

> HTTP/URL이 ASCII protocol(7-bit)이라서. 1990년대 7-bit ASCII가 사실상 표준이던 시대에 태어났고, 30년 묵은 middlebox·proxy·WAF·log analyzer가 그 invariant에 hard-code되어 있어요. URL은 HTTP 밖(HTML, email, Slack, log)으로도 새어 나가는데 그 모든 환경에서 안 깨지려면 ASCII-only가 필요합니다. 그래서 브라우저의 UTF-8 인코더가 codepoint를 byte로 encode → URL parser가 각 byte를 `%HH`로 escape. 결과적으로 `김`(U+AE40)이 UTF-8 3 byte `EA B9 80`이 되고, 다시 `%EA%B9%80` ASCII 9 char로 변환되어 wire에 흐른다.

### Q3. DNS는 어떻게 IP를 찾나요?

> 4계층 cache hierarchy + recursive resolver 모델. 브라우저 cache → OS resolver(`/etc/hosts`/OS cache) → stub resolver가 `/etc/resolv.conf`의 recursive(8.8.8.8 등)에 UDP 53 질의 → cache miss면 root → TLD → authoritative 3단 referral. 각 단계 TTL 동안 cache. TTL은 짧으면 failover 빠르지만 NS 부하 ↑, 길면 stale. 진단은 `dig +trace`, `tcpdump udp port 53`, JVM `networkaddress.cache.ttl`, K8s `ndots:5`.

### Q4. MAC은 hop마다 변하는데 IP는 안 변하는 이유는?

> MAC은 same-LAN next-hop 주소, IP는 end-to-end 식별자. router는 LAN 경계니까 매 hop마다 Ethernet frame을 새로 만들면서 src/dst MAC을 갱신(ARP로 다음 hop MAC 알아냄). IP는 응답을 돌려받으려면 처음부터 끝까지 같아야 해요. 그래서 router는 IP는 그대로 두고 TTL만 -1 + IP checksum 재계산. TCP/payload는 절대 안 건드림 — 그게 router의 정의. NAT는 이 원칙을 깨고 src_ip/src_port를 갈아치우는 부가 기능.

### Q5. LB가 분산 말고 또 뭐 하나요?

> 8가지를 동시에 처리합니다 — ① 트래픽 분산(P2C/Consistent Hash), ② SSL termination(cert 중앙 관리), ③ health check(shallow/deep/passive), ④ rate limit(token/leaky bucket), ⑤ sticky session, ⑥ routing(path/host/canary/A-B), ⑦ WAF, ⑧ DDoS 흡수(L3/L4는 edge anycast, L7은 in-front). 부가로 observability(모든 트래픽 hub → access log, P99, 5xx rate). 본질은 "서버 군집 앞단의 통합 entrypoint" 추상화 — backend가 혼자인 듯 살게 해주는 mediator.

### Q6. Nginx가 8개 worker로 수만 동시 connection 처리하는 비결은?

> event-driven + epoll + non-blocking I/O + state machine. worker가 CPU core당 1개, 각자 epoll 인스턴스. 각 connection이 read/write handler를 들고 있는 state machine이라 EAGAIN 만나면 다음 ready 이벤트로 점프. socket은 무조건 `O_NONBLOCK`. Apache prefork는 1 conn = 1 process라 10000 conn에 80GB stack 필요했지만 Nginx는 event 모델로 깸. epoll이 select/poll보다 빠른 이유는 매 호출마다 fd 전체 복사+linear scan하지 않고 한 번 등록한 뒤 ready만 callback push.

### Q7. Tomcat의 acceptCount, maxConnections, maxThreads는 어떻게 다른가요?

> 위치와 의미가 다 다릅니다. acceptCount는 kernel TCP accept queue 크기 — `min(acceptCount, somaxconn)`로 잘림, 초과면 새 SYN 거부 "Connection refused". maxConnections는 Tomcat이 든 socket 수 — 초과면 Acceptor block → kernel queue 적체. maxThreads는 동시 처리 중 요청 수 — 초과면 queue 적체 또는 503. NIO에서는 idle keepalive conn이 Worker 점유 안 하므로 maxConnections ≫ maxThreads가 정상. acceptCount 늘려도 sysctl somaxconn이 작으면 잘리니까 같이 늘려야.

### Q8. Connection pool이 왜 Nginx, Tomcat, HikariCP 다 따로 있나요?

> 각 풀이 다른 자원을 빌려줍니다. Nginx upstream keepalive는 LB↔Nginx 또는 Nginx↔Tomcat TCP 재사용. Tomcat ThreadPool은 Worker thread 재사용. HikariCP는 Tomcat↔DB JDBC connection 재사용. DB conn 생성은 TCP+TLS+Startup+Auth+ReadyForQuery 5단계라 cross-AZ면 500ms 비용. 매 요청마다 새로 만들면 DB CPU 폭증 + ephemeral port 고갈 + max_connections 초과. 한 요청이 7~13개 풀을 통과하고, 어느 한 풀이 비면 위쪽이 적체됩니다.

### Q9. Read timeout과 Connection timeout 차이는?

> Connection timeout은 TCP 3-way(SYN→SYN-ACK→ACK)까지의 시간. `connect()` syscall + kernel timer. Linux 미설정 시 tcp_syn_retries=6 → ~127초 대기. Read timeout은 한 recv()의 idle 시간. SO_RCVTIMEO. **매 recv()마다 reset** — 그래서 전체 응답 시간이 아니에요. server가 4초마다 1 byte씩 보내면 read timeout=5초여도 영원히 안 끊김. 그래서 OkHttp callTimeout, HttpRequest.timeout, gRPC deadline 같은 Total/Call timeout이 별도 최후 보루로 필요.

### Q10. PreparedStatement가 어떻게 SQL injection을 구조적으로 막나요?

> parameter를 SQL과 별도 wire 메시지(Bind)로 보냅니다. PG Extended Query Protocol에서 Parse 단계는 SQL template만 AST로 만들고(`$1`은 placeholder로만 인식), Bind 메시지의 parameter byte는 **절대 SQL parser를 거치지 않아요** — column literal value일 뿐. Statement의 escape는 client에서 위험 문자를 변환해 inline하는 임시방편이라 corner case 누락 가능하지만, PreparedStatement는 **wire에서 SQL과 parameter가 분리**되어 구조적으로 injection 불가. 추가 보너스는 같은 template은 1회 parse + plan cache 재사용.

### Q11. P99 latency가 갑자기 2초로 튐. 어디부터 보나요?

> 메인 흐름 12단계를 따라 외곽에서 안쪽으로 격리합니다. ① 브라우저 DNS lookup이 느려졌나(`tcpdump -i any -n udp port 53`, JVM `networkaddress.cache.ttl`). ② TCP RTT 자체가 늘었나(`mtr`로 hop별 loss/jitter). ③ LB 메트릭 — `upstream_connect_time` 크면 keepalive pool 부족, `tls_handshake_duration` 크면 session resumption 미적용, 특정 backend만 `upstream_response_time` outlier인지. ④ Nginx access log의 `$request_time` vs `$upstream_response_time` 차이(slow client?). ⑤ Tomcat — `tomcat.threads.busy/max`, jstack 다회 채취해서 같은 stack에 머무는 thread 비율. ⑥ HikariCP `pending`/`acquire_p99`/`active`. ⑦ DB — `pg_stat_activity` long-running query, `pg_locks` chain, EXPLAIN ANALYZE. 한 단계라도 정상이면 그 안쪽이 범인. 보통 90%는 DB 또는 외부 API.

### Q12. "Connection reset by peer"가 간헐적으로 나는 이유는?

> Stale connection 시나리오. pool에 idle로 남은 connection을 firewall/NAT/NLB가 idle timeout(보통 5분~6시간) 후 silent drop — RST도 안 보내요. 양쪽 endpoint는 여전히 "살아있다고 믿음". 다음 query 보내면 peer가 모르는 connection이라 RST. 해결은 ① `maxLifetime`을 firewall idle × 0.5로(예: NLB 350s → maxLifetime 300s), ② HikariCP `keepaliveTime` 60s로 주기적 SELECT 1, ③ JDBC URL `tcpKeepAlive=true`. TCP keepalive만으로는 부족 — 일부 firewall이 keepalive packet을 idle 카운트에서 제외 안 함.

### Q13. K8s에서 CoreDNS NXDOMAIN이 폭증해요. 왜요?

> Pod의 `/etc/resolv.conf`에 `options ndots:5`가 있어서. ndots:5는 hostname에 dot 5개 미만이면 search 도메인 먼저 시도하는데, search 도메인이 보통 4~5개 등록되어 있어요. 예: `api.payment.com/v1`(dot 3개) 호출 시 ① `api.payment.com.v1.default.svc.cluster.local`, ② `...svc.cluster.local`, ③ `...cluster.local`, ④ `...example.com` 다 NXDOMAIN, ⑤ 그제야 `api.payment.com.` 진짜 시도. IPv4+IPv6 = 10번 시도. 해결은 FQDN 명시(`api.payment.com.` 끝에 dot), `dnsConfig: ndots:2` + searches 1개로 축소, NodeLocal DNSCache 도입.

### Q14. "외부 API hang으로 503 폭증"의 메커니즘과 방어는?

> 외부 API 느려짐 → timeout 없으면 매 호출 30s+ 점유 → Tomcat thread 200개 모두 recv() block → 새 요청 queue full → 503 → `/actuator/health`도 응답 못 함 → LB가 instance kill → 옆 instance로 load → cascading 마비. 방어 4종 세트: ① **timeout 명시**(특히 OkHttp `callTimeout`, gRPC deadline 같은 Total/Call), ② **CircuitBreaker**(실패 50% 누적 시 30s 차단), ③ **Bulkhead**(외부 호출 전용 thread pool 분리), ④ **Fallback**(graceful degradation). 흔한 함정 — 메인 client는 timeout 잘 설정했는데 부속 client(metrics/logging/fallback)가 default 무한 → 부속이 hang.

### Q15. 30 instance × HikariCP 20 = 600 conn 요청, DB max=200. 어떻게 하나요?

> **PgBouncer transaction mode**로 multiplex. 600 client connection을 200 backend connection에 transaction 단위로 묶어 줍니다. 트레이드오프는 PreparedStatement plan cache가 깨짐(transaction마다 다른 backend conn 할당 가능) → `prepareThreshold=0` 또는 server reset query 필요. session mode는 client 별로 backend 1:1이라 효과 없고, statement mode는 더 강한데 transaction 못 씀. 일반적으로 transaction mode가 sweet spot. 근본 해결은 instance/HikariCP 크기 조정 + DB pool은 작게(`(core × 2) + spindle`) — 작은 pool로 빠른 turnover가 큰 pool로 느린 처리보다 빠릅니다.

---

# 한 줄 마무리

> 12단계 메인 흐름을 백지에서 술술 풀 수 있다면 시니어 면접의 절반은 통과한다. 사이드 토픽은 면접관이 어느 단계를 콕 찍어 깊이 물을 때 그 챕터의 풀버전(01~08)으로 들어간다. 항상 메인 흐름이 anchor — "URL을 친 사용자가 응답을 받기까지" 한 줄기.

---

## 다음 단계

각 단계의 풀버전은:

| 단계 | 풀버전 |
|---|---|
| ①, ② URL + 인코딩 | [01-url-input-and-serialization.md](./01-url-input-and-serialization.md) |
| ③, ⑤ DNS + 라우팅 | [02-dns-and-routing.md](./02-dns-and-routing.md) |
| ④, ⑥ TCP/TLS + OSI 7계층 | [03-osi-7-layers-and-tcp-tls.md](./03-osi-7-layers-and-tcp-tls.md) |
| ⑦ Load Balancer | [04-load-balancer-deep-dive.md](./04-load-balancer-deep-dive.md) |
| ⑧ Nginx | [05-nginx-internals.md](./05-nginx-internals.md) |
| ⑨ Tomcat | [06-tomcat-internals.md](./06-tomcat-internals.md) |
| ⑩ Connection Pools (전체) | [07-connection-pools-master.md](./07-connection-pools-master.md) |
| ⑪ DB + JDBC | [08-db-connection-and-jdbc.md](./08-db-connection-and-jdbc.md) |
| 부록 2 timeout | [java-deep-dive/04-timeouts-connection-vs-read.md](../java-deep-dive/04-timeouts-connection-vs-read.md) |
