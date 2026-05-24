# Network Request Lifecycle — URL 입력부터 DB 응답까지

> "브라우저에 URL 치면 DNS → 라우팅 → 서버 → 응답" 이라고만 답하면 입문자.
> "브라우저가 IDN을 punycode로 변환한 후 OS resolver가 stub→recursive→authoritative를 거쳐 A 레코드를 받고, BGP가 AS path로 라우팅한 패킷이 ECMP로 분산되어 L4 LB의 DSR로 백엔드에 도달하면 Nginx worker가 epoll로 이벤트를 받아 upstream keepalive pool에서 Tomcat NIO Connector의 Acceptor → Poller → Executor 파이프라인을 통과한 후 HikariCP에서 빌려온 JDBC 커넥션의 wire protocol로 PostgreSQL에 도달한다" 라고 말할 수 있다면 그 다음 단계.
> 이 가이드의 목표는 후자다.

---

## 📍 학습 목표

이 챕터를 마치면 다음을 막힘없이 답할 수 있다.

1. **(일반 케이스, ASCII-only)** 사용자가 `https://www.google.com/` 같이 ASCII만 포함한 URL을 입력했을 때, **hostname → DNS(stub/recursive/authoritative) → 호스트 라우팅 테이블 → 게이트웨이/ISP/라우터 hop → 서버 → 응답** 까지의 평범한 흐름을 백지에 그릴 수 있다. 각 단계가 OSI 어느 계층에서 동작하는지(L7 ↔ L2)도 같이.
2. **(한글 포함 케이스)** 주소창에 `https://example.com/users/김면수` 같이 한글이 들어간 URL을 입력했을 때, **왜 한글을 그대로 네트워크에 흘리면 안 되는지**(HTTP/1.1은 RFC 9110 기준 ASCII 7-bit 메시지 프로토콜) + percent-encoding이 **어떤 계층의 책임**(브라우저 = encode, 서버 = decode)인지 + 인코딩이 깨지면 글자가 어디서 깨지는지를 단계별로 설명할 수 있다.
3. "김면수" 같은 한글이 UTF-8 바이트 → percent-encoding → HTTP 메시지 → 네트워크 → 서버 디코딩 → 비즈니스 객체까지 어떻게 직렬화·복원되는지 단계별로 설명할 수 있다.
4. 데이터가 통과하는 **OSI 7계층 각각**에서 어떤 헤더가 붙고 떨어지는지(encapsulation/decapsulation), TCP/IP 5계층 모델과의 매핑까지.
5. **로드밸런서**가 단순 트래픽 분산이 아니라 SSL termination, health check, rate limit, sticky session, WAF, A/B test, observability, DDoS 방어까지 담당함을 안다. L4와 L7의 차이, DSR/SNAT/NAT 모드 차이.
6. **모든 커넥션 풀**의 위치와 역할 — Nginx upstream keepalive, Tomcat acceptor thread/executor pool, HikariCP DB pool, HTTP client pool, file descriptor 한계, kernel TCP backlog 등.
7. Nginx가 **수만 동시 연결**을 8개 worker로 처리하는 비결 (event loop + epoll + non-blocking I/O).
8. Tomcat이 **request를 어떻게 byte stream에서 객체로** 변환하는지 (Acceptor → Poller → Executor → Servlet).
9. JDBC 드라이버가 PostgreSQL/MySQL **wire protocol**로 어떻게 SQL을 직렬화하고 응답을 받는지.
10. Production에서 P99 latency spike가 발생했을 때 이 흐름의 어느 단계에서 병목이 생겼는지 진단·해결할 수 있다.

---

## 🌐 전체 흐름 큰 그림

전체 라이프사이클을 OSI 계층 매핑과 함께. 우측의 `[L7]`/`[L4]` 등은 **그 단계에서 주로 동작하는 OSI 계층**을 가리킨다 (실제 패킷은 항상 모든 계층의 헤더를 동시에 달고 있다).

```
                                                              OSI 계층
[브라우저]                                                       │
   │  1. URL 파싱 + IDN punycode (hostname)                    [L7 Application]
   │     + percent-encoding (path/query의 비-ASCII)            [L6 Presentation]
   │  2. OS resolver에 hostname 질의                            [L7]
   ▼
[DNS 계층]                                      ← 02-dns-and-routing
   stub resolver → recursive → root/TLD/authoritative          [L7] (UDP/53 위)
   │  3. A/AAAA 레코드 반환 (IP 주소)
   ▼
[TCP/TLS Handshake]                             ← 03-osi-7-layers
   │  3-way handshake (SYN/SYN-ACK/ACK)                        [L4 Transport]
   │  TLS handshake (ClientHello → cert → key exchange)        [L6 Presentation]
   ▼
[라우팅 계층]                                   ← 02-dns-and-routing
   호스트 라우팅 테이블 → 게이트웨이 → ISP                      [L3 Network]
   → BGP/AS path → CDN edge → origin
   각 hop마다 ARP로 다음 hop MAC 확인 → L2 frame              [L2 Data Link]
   물리 매체(이더넷/광케이블/Wi-Fi) 위 bit 스트림              [L1 Physical]
   │  4. ECMP로 다수 경로 분산
   ▼
[L4/L7 Load Balancer]                          ← 04-load-balancer-deep-dive
   │  5. SSL termination, health check, rate limit            [L4 or L7]
   │  6. backend 선택 (round-robin, least-conn, consistent hash)
   ▼
[Nginx]                                         ← 05-nginx-internals
   │  7. event loop / worker process                           [L7]
   │  8. upstream keepalive pool로 Tomcat 연결                 [L4 TCP 재사용]
   ▼
[Tomcat]                                        ← 06-tomcat-internals
   │  9. Acceptor → Poller → Executor → Servlet               [L7]
   │ 10. HTTP 파싱 (byte → HttpServletRequest)
   ▼
[Spring Application]                                            [L7]
   │ 11. HikariCP에서 DB 커넥션 차용                ← 07-connection-pools-master
   │     + path/query의 percent-encoding을 UTF-8 문자열로 디코딩 [L6]
   ▼
[JDBC Driver]                                   ← 08-db-connection-and-jdbc
   │ 12. PreparedStatement → wire protocol                     [L7] (TCP 위)
   ▼
[PostgreSQL / MySQL]
   │ 13. Parser → Optimizer → Executor → Storage
   │ 14. Buffer Pool → 디스크 (필요시)
   ▼
[응답: 역순으로 돌아옴]
```

---

### Case A — `https://www.google.com/` (ASCII-only, 평범한 흐름)

가장 단순한 케이스. **인코딩 단계가 사실상 우회**된다 (모든 문자가 이미 ASCII이므로 변환할 게 없음).

```
[입력] https://www.google.com/
            │
            ▼
┌─────────────────────────────────────────────────────────────────┐
│ Step 1. URL 파싱                                       [L7]      │
│   scheme=https, host="www.google.com", path="/"                  │
│   → host는 이미 ASCII (LDH: Letter/Digit/Hyphen)                 │
│   → IDN punycode 변환 불필요                                     │
│   → path도 ASCII → percent-encoding 불필요                       │
└─────────────────────────────────────────────────────────────────┘
            │
            ▼
┌─────────────────────────────────────────────────────────────────┐
│ Step 2. DNS 조회                                       [L7/UDP]  │
│   stub resolver → recursive → root(.) → .com TLD                 │
│                              → google.com authoritative          │
│   → A 레코드 (IPv4) + TTL 반환                                   │
└─────────────────────────────────────────────────────────────────┘
            │
            ▼
┌─────────────────────────────────────────────────────────────────┐
│ Step 3. 라우팅 + L2 프레임 송출                        [L3/L2]   │
│   호스트 라우팅 테이블 → default gateway                         │
│   ARP로 게이트웨이 MAC 획득 → L2 frame 캡슐화                    │
│   → ISP → BGP AS path → CDN edge (Google front)                  │
└─────────────────────────────────────────────────────────────────┘
            │
            ▼
┌─────────────────────────────────────────────────────────────────┐
│ Step 4. TCP/TLS handshake → HTTP GET                   [L4/L6/L7]│
│   GET / HTTP/1.1 (모든 헤더가 raw ASCII로 그대로 전송)            │
└─────────────────────────────────────────────────────────────────┘
            │
            ▼
   [서버 응답 → 역순 디캡슐화 → 브라우저 렌더링]
```

→ **핵심**: 이 케이스는 "URL의 모든 문자가 ASCII"이므로 직렬화 단계가 투명하다. 그러나 hostname/path 중 어느 곳이든 비-ASCII가 끼면 **즉시 다음 케이스의 인코딩 분기**가 발동한다.

---

### Case B — `https://example.com/users/김면수` (한글 포함, percent-encoding 필요)

```
[입력] https://example.com/users/김면수
            │
            ▼
┌─────────────────────────────────────────────────────────────────┐
│ Step 1. URL 파싱 + 인코딩 분기                          [L7/L6]  │
│   host="example.com" → ASCII이므로 그대로                        │
│   path="/users/김면수" → 비-ASCII 포함 → 인코딩 필요             │
│     a) UTF-8로 직렬화: 김=EA B9 80, 면=EB A9 B4, 수=EC 88 98     │
│     b) 각 바이트를 percent-encoding:                             │
│        /users/%EA%B9%80%EB%A9%B4%EC%88%98                        │
│   → 이제 HTTP 메시지 라인이 100% ASCII가 됨                       │
└─────────────────────────────────────────────────────────────────┘
            │
            ▼
   [Step 2~4는 Case A와 동일: DNS, 라우팅, TCP/TLS, HTTP 송출]
            │
            ▼
┌─────────────────────────────────────────────────────────────────┐
│ Step 5. 서버 측 디코딩                                  [L6/L7]  │
│   Tomcat / Spring이 URI를 percent-decoding (charset=UTF-8)       │
│   → byte[] {EA B9 80 EB A9 B4 EC 88 98} → String "김면수"        │
│   → @PathVariable String name = "김면수" 로 비즈니스에 도달      │
└─────────────────────────────────────────────────────────────────┘
```

→ **인코딩 책임 계층**: 브라우저(=클라이언트)가 **encode**, 서버(Tomcat/Spring/JDBC)가 **decode**. 양쪽 charset이 불일치하면 글자 깨짐.

각 단계마다 **OSI 7계층** (03번 챕터)이 동시에 동작하면서 헤더를 붙이고 뗀다.

---

## 🇰🇷 한글 URL — 왜 인코딩이 필요한가

### 한 줄 정리

> **HTTP/1.1 메시지는 RFC 9110 기준 ASCII (7-bit) 텍스트 프로토콜이다.** 한글 같은 비-ASCII raw byte는 HTTP request line / header / 일부 URL 컴포넌트에 그대로 실을 수 없다. 그래서 **URL의 path·query에 들어가는 모든 비-ASCII 문자는 UTF-8로 직렬화한 뒤 percent-encoding**으로 ASCII-safe하게 변환한 후에야 네트워크에 흘릴 수 있다.

### 왜 ASCII 프로토콜인가 (역사적 본질)

```
1969 ARPANET                1983 TCP/IP             1991 HTTP/0.9
    │                           │                        │
    └─ 7-bit ASCII가 사실상      └─ 이메일/Telnet/FTP    └─ HTTP도 자연스럽게
       표준 (텔레프린터,            모두 ASCII 기반            텍스트 라인 기반
       전신 호환)                                              (GET /path\r\n)
```

→ HTTP는 태생적으로 **사람이 읽을 수 있는 텍스트 라인 + CRLF** 구조를 채택했고, 그 위에 모든 헤더/메서드/URI를 얹었다. ASCII 호환을 깨는 순간 전 세계 모든 프록시/캐시/방화벽이 깨진다 (so-called "ASCII-clean" invariant).

### 인코딩 파이프라인

```
사용자 입력         브라우저 메모리             네트워크 라인
─────────         ────────────                ──────────────

  "김면수"   ──▶   ① 유니코드 코드포인트
                    U+AE40 U+BA74 U+C218
                         │
                         ▼
                  ② UTF-8 직렬화 (RFC 3629)
                    EA B9 80  EB A9 B4  EC 88 98
                         │
                         ▼
                  ③ percent-encoding (RFC 3986)
                    %EA%B9%80%EB%A9%B4%EC%88%98     ──▶   GET /users/%EA%B9%80%EB%A9%B4%EC%88%98 HTTP/1.1
                                                          (100% ASCII, RFC 9110 OK)
```

### 책임 계층 — 누가 encode하고 누가 decode하나

```
┌────────────────────────────────┐         ┌────────────────────────────────┐
│         CLIENT (브라우저)       │  HTTP   │         SERVER (Tomcat/Spring) │
│                                │ ─────▶ │                                │
│  L7: 사용자가 한글 입력         │         │  L7: HTTP 파싱                  │
│  L6: UTF-8 + percent-encode    │         │  L6: percent-decode + UTF-8     │
│      (encode 책임)             │         │      (decode 책임)              │
│  L4: TCP send                  │         │  L4: TCP recv                   │
└────────────────────────────────┘         └────────────────────────────────┘
                                                       │
                                                       ▼
                                              @PathVariable String name = "김면수"
```

→ 양쪽 **charset 합의가 불일치하면 글자 깨짐**. 대표 패턴:
- 클라가 UTF-8로 encode했는데 서버가 ISO-8859-1로 decode → `ê¹€ë©´ìˆ˜` 같은 깨진 라틴 시퀀스
- 클라가 EUC-KR로 encode했는데 서버가 UTF-8로 decode → `???` 또는 replacement char (U+FFFD) 폭주
- DB 컬럼 charset이 latin1인데 UTF-8 byte를 그대로 저장 → 저장은 되지만 SELECT 시 깨짐

### 어디서 깨지면 어떻게 진단하나 (시니어 운영 관점)

```
[브라우저 주소창]   ──▶   [Nginx access log]   ──▶   [Tomcat 파싱]   ──▶   [Spring @PathVariable]   ──▶   [JDBC bind]   ──▶   [DB row]
       │                       │                        │                       │                            │                  │
   raw 한글             %EA%B9%80...                 byte[]                  String                      PreparedStatement   utf8mb4 컬럼
                                                  + URIEncoding            + 한글 정상                  + characterEncoding
                                                  =UTF-8                                                =UTF-8
```

→ 어느 단계에서 깨졌는지는 **단계별 로그/덤프**로 좁힌다:
- Nginx access log에 `%EA%B9%80...` 로 찍히면 클라까지는 OK
- Tomcat이 `???` 로 받으면 `connector URIEncoding` 또는 `useBodyEncodingForURI` 설정 누락
- DB만 깨지면 JDBC URL의 `characterEncoding=UTF-8` + 컬럼 collation 점검

자세한 본질·역사·코드 레벨 진단은 **[01-url-input-and-serialization.md](./01-url-input-and-serialization.md)** 에서.

---

## 🌐 일반 케이스 — `www.google.com` 흐름 (백지 마스터)

가장 평범한 ASCII-only 호스트네임을 입력했을 때 **DNS → 라우팅 → 서버 → 응답**이 어떻게 흐르는지, 각 단계가 OSI 어느 계층에서 동작하는지를 백지에서 그릴 수 있게 정리한다.

### 단계별 상세 (8단계)

```
[입력] https://www.google.com/
                │
                ▼
┌──────────────────────────────────────────────────────────────────┐
│ ① 브라우저 캐시 hit/miss                              [L7]        │
│    - 메모리 캐시 / 디스크 캐시 → 200 OK Cache-Control 확인         │
│    - HSTS 캐시 hit → 자동 https 업그레이드                         │
│    - hit: 그 자리에서 응답 (DNS 안 감)                             │
│    - miss: 다음 단계                                              │
└──────────────────────────────────────────────────────────────────┘
                │ (miss)
                ▼
┌──────────────────────────────────────────────────────────────────┐
│ ② OS resolver 단계 — 로컬에서 끝낼 수 있나                [L7]    │
│    a) /etc/hosts (Linux/Mac) 또는 hosts 파일 확인                  │
│       → 정적 매핑 hit이면 즉시 IP 반환 (DNS 우회)                  │
│    b) OS DNS 캐시 (nscd / systemd-resolved / mDNSResponder)        │
│       → TTL 안 지난 항목이면 캐시 hit                              │
│    c) stub resolver가 recursive resolver로 UDP/53 질의             │
└──────────────────────────────────────────────────────────────────┘
                │ (캐시 miss)
                ▼
┌──────────────────────────────────────────────────────────────────┐
│ ③ Recursive resolver 단계 — 인터넷에서 정답 찾기         [L7/UDP] │
│    recursive (1.1.1.1 / 8.8.8.8 / ISP DNS)가 대신 수행:            │
│                                                                   │
│      root(.)        "그건 .com TLD에 물어봐"                       │
│        │                                                          │
│        ▼                                                          │
│      .com TLD       "그건 google.com authoritative에 물어봐"       │
│        │                                                          │
│        ▼                                                          │
│      google.com authoritative                                     │
│        → A 레코드 (IPv4) / AAAA 레코드 (IPv6) + TTL 반환           │
│                                                                   │
│    - TTL 동안 recursive와 stub 양쪽에 캐시                         │
│    - TTL 만료 후 다시 질의                                         │
└──────────────────────────────────────────────────────────────────┘
                │ (IP 획득)
                ▼
┌──────────────────────────────────────────────────────────────────┐
│ ④ 클라이언트 라우팅 테이블 → 다음 hop 결정             [L3]       │
│    `ip route` (Linux) / `route -n get` (Mac)                       │
│    - 목적지 IP가 어느 인터페이스/게이트웨이로 가야 하는지          │
│    - 보통 default route → 게이트웨이 IP                            │
└──────────────────────────────────────────────────────────────────┘
                │
                ▼
┌──────────────────────────────────────────────────────────────────┐
│ ⑤ 게이트웨이 → ISP → BGP/AS path                       [L3]       │
│    - 게이트웨이부터 ISP backbone으로 진입                          │
│    - BGP로 학습된 AS path를 따라 Google AS (AS15169)로 향함        │
│    - 중간에 CDN edge가 anycast로 가까운 노드로 끌어당김             │
└──────────────────────────────────────────────────────────────────┘
                │
                ▼
┌──────────────────────────────────────────────────────────────────┐
│ ⑥ 라우터 hop들 — TTL decrement (traceroute로 가시화)   [L3]       │
│    각 hop마다 IP 헤더의 TTL이 1씩 감소                             │
│    - TTL=0 도달 시 ICMP Time Exceeded 반환 → traceroute 원리       │
│    - 평균 10~20 hop 정도 (대륙 내) / 20~30+ hop (대륙 간)          │
└──────────────────────────────────────────────────────────────────┘
                │
                ▼
┌──────────────────────────────────────────────────────────────────┐
│ ⑦ 마지막 hop의 ARP → L2 frame 송출                     [L2/L1]    │
│    - 각 hop에서 "다음 hop의 IP에 해당하는 MAC 주소"를 ARP로 확인   │
│    - L2 frame에 dest MAC 채워 송출 (이더넷/Wi-Fi)                   │
│    - L1: 전기/광/RF 신호로 비트 스트림 송출                         │
└──────────────────────────────────────────────────────────────────┘
                │
                ▼
┌──────────────────────────────────────────────────────────────────┐
│ ⑧ 목적지 서버 도착 → 역순 디캡슐화 → L7 응답          [L1→L7]    │
│    L1 비트 → L2 frame 검증 → L3 IP 라우팅 종료 → L4 TCP 재조립    │
│    → L6 TLS 복호화 → L7 HTTP 파싱 → 애플리케이션이 응답 생성       │
│    → 응답이 동일 경로(또는 다른 경로)로 역순으로 돌아옴             │
└──────────────────────────────────────────────────────────────────┘
```

### 한눈에 — 어느 단계가 OSI 어느 계층인가

```
단계                                계층
────────────────────────────────────────────────────
① 브라우저 캐시                      L7
② OS resolver (/etc/hosts, stub)     L7
③ recursive → root/TLD/auth          L7 (UDP/53)
   ↓ (그동안 TCP/TLS handshake)      L4/L6
④ 호스트 라우팅 테이블                L3
⑤ 게이트웨이/ISP/BGP                  L3
⑥ 라우터 hop (TTL)                   L3
⑦ ARP + L2 frame                     L2
⑦ 물리 매체 (이더넷/광/Wi-Fi)        L1
⑧ 목적지 디캡슐화 → 응답             L1→L7
```

→ **백지 마스터 체크포인트**: 위 8단계를 누군가 "구글에 접속하면 무슨 일이 일어나?" 질문할 때 한 호흡으로 풀어낼 수 있어야 한다. 각 단계에서 어떤 진단 도구(`dig`, `nslookup`, `traceroute`, `tcpdump`, `ip route`, `arp -a`)를 쓰는지까지 자동 연상되어야 시니어 운영 마스터.

자세한 DNS 4단계와 라우팅 내부(BGP, anycast, CDN edge, ECMP)는 **[02-dns-and-routing.md](./02-dns-and-routing.md)**, OSI 계층별 캡슐화/디캡슐화와 TCP/TLS handshake는 **[03-osi-7-layers-and-tcp-tls.md](./03-osi-7-layers-and-tcp-tls.md)** 에서.

---

## 📚 챕터 목록

| # | 파일 | 핵심 질문 | 상태 |
|---|---|---|---|
| 01 | [01-url-input-and-serialization.md](./01-url-input-and-serialization.md) | "한글이 URL에 그대로 못 들어가는 이유 + percent-encoding 5단 변환 + 글자 깨짐 운영" | ✅ (500 lines) |
| 02 | [02-dns-and-routing.md](./02-dns-and-routing.md) | "`www.google.com` 평범한 케이스 + DNS 4단계 + ARP/MAC + 라우터 hop" | ✅ (503 lines) |
| 03 | [03-osi-7-layers-and-tcp-tls.md](./03-osi-7-layers-and-tcp-tls.md) | "L7→L1 캡슐화 + TCP/TLS handshake + IP는 end-to-end / MAC은 hop-to-hop" | ✅ (503 lines) |
| 04 | [04-load-balancer-deep-dive.md](./04-load-balancer-deep-dive.md) | "L4/L7 LB의 모든 역할 — SSL term / health / rate limit / sticky / WAF / DDoS" | ✅ (508 lines) |
| 05 | [05-nginx-internals.md](./05-nginx-internals.md) | "8 worker로 수만 연결을 처리하는 비결 — event loop + epoll + upstream keepalive" | ✅ (508 lines) |
| 06 | [06-tomcat-internals.md](./06-tomcat-internals.md) | "byte stream → HttpServletRequest — Acceptor/Poller/Executor + 3한도" | ✅ (494 lines) |
| 07 | [07-connection-pools-master.md](./07-connection-pools-master.md) | "13 pool 위치 + HikariCP + Tomcat 3한도 + Cascading failure" | ✅ (503 lines) |
| 08 | [08-db-connection-and-jdbc.md](./08-db-connection-and-jdbc.md) | "JDBC 4계층 + Wire Protocol + PreparedStatement + fetchSize 함정" | ✅ (500 lines) |

> **간략 버전입니다.** 각 챕터는 500 라인 내외로 핵심·다이어그램·운영 시나리오·꼬리질문만 유지합니다. 비트 단위 헤더 layout, byte-level 풀 시퀀스, 풀버전 운영 시나리오 매트릭스, byte map / handshake 풀버전 등 **deep-dive 버전은 git `7e4a6c8` commit에 보존**되어 있습니다. 궁금한 토픽이 생기면 그때 함께 깊이 파고듭니다.

---

## 🎯 학습 철학 (flab-study AGENTS.md 5룰)

1. **개념 누락 금지** — 모든 핵심 개념은 본질·왜·연결까지 빠짐없이
2. **시니어 운영 마스터 관점** — production 장애 진단과 매핑
3. **표면 디테일 제외** — 옵션값 외우기보다 본질·왜·역사
4. **다이어그램 필수** — ASCII/Excalidraw로 시각화
5. **백지 마스터 수준** — 주제를 백지에서 줄줄 풀어낼 수 있게

## 7단 레이어 (모든 sub-chapter에서)

| 단계 | 내용 |
|---|---|
| 1. 백지 그리기 | ASCII 다이어그램 + 손그림 가이드 |
| 2. 직관 | 한 줄 비유 + 왜 존재하는가 |
| 3. 구조 | 컴포넌트 분해 |
| 4. 내부 구현 | 코드/프로토콜 발췌 + 실제 동작 |
| 5. 역사 | 진화의 트리거 |
| 6. 트레이드오프 ⭐ | 대안 비교 + 선택 근거 |
| 7. 측정·진단 ⭐ | tcpdump/strace/netstat/prof 실전 도구 |
| + 꼬리질문 | 면접/실무 양쪽 검증 |

---

## 🔗 다른 학습 영역과의 연결

| 외부 챕터 | 어떻게 이어지나 |
|---|---|
| `jvm/05-threading/` | Tomcat ThreadPool / HikariCP가 결국 Java Thread. happens-before, synchronized, Virtual Thread 이해 필요 |
| `jvm/02-runtime-data-areas/05-direct-memory.md` | Netty/Nginx의 zero-copy, NIO DirectBuffer는 모두 off-heap |
| `jvm/04-gc/` | DB ResultSet이 Heap에 쌓이면 GC 압박. Direct Memory 누수 패턴 |
| `java-deep-dive/04-timeouts-connection-vs-read.md` | 이 챕터의 timeout 개념들을 Java API 수준에서 |
| `java-deep-dive/05-hashing-and-hash-collections.md` | Redis cluster slot이 hostname → IP 라우팅과 동일한 **"키 → 위치 결정"** 패턴 — DNS는 hostname을 IP로, consistent hash는 key를 slot/node로 매핑. 둘 다 "분산 시스템에서 어떤 키를 어디로 보낼지" 결정하는 같은 본질의 문제 |

---

## 🏢 실무 시나리오 미리보기

이 가이드가 답할 수 있게 만드는 질문들:

```
1. "P99 latency가 갑자기 2초로 튐. 어디부터 봐야 하나?"
   → 각 단계의 진단 도구로 추적 (DNS lookup, TCP RTT, LB queue, Nginx upstream wait, Tomcat thread, HikariCP wait, DB query)

2. "Tomcat이 503 'connection refused' 뱉기 시작. 원인은?"
   → maxConnections, acceptCount, kernel backlog, FD limit 중 어디서 막혔나

3. "HikariCP getConnection()이 hang 걸림"
   → pool 고갈 / DB hang / 네트워크 drop / firewall idle timeout

4. "Nginx worker_connections를 늘렸는데 효과가 없다"
   → file descriptor limit, sysctl somaxconn, upstream keepalive 미설정

5. "Load balancer 뒤의 서버가 health check는 통과하는데 실제 요청은 5xx"
   → L7 path-based health vs L4 TCP health, deep health endpoint 부재

6. "한글이 깨져서 들어옴 (글자 깨짐)"
   → percent-encoding charset 불일치, HTTP Content-Type charset, JDBC URL의 useUnicode/characterEncoding
```

---

## 진행 현황

- [x] README + 전체 흐름 그림 + 챕터 목록
- [x] 01-url-input-and-serialization (500 lines)
- [x] 02-dns-and-routing (503 lines)
- [x] 03-osi-7-layers-and-tcp-tls (503 lines)
- [x] 04-load-balancer-deep-dive (508 lines)
- [x] 05-nginx-internals (508 lines)
- [x] 06-tomcat-internals (494 lines)
- [x] 07-connection-pools-master (503 lines)
- [x] 08-db-connection-and-jdbc (500 lines)

**총 4,019 라인** (본문) + README. 8개 챕터 모두 핵심 개념 + 1~2 다이어그램 + 운영 시나리오 2~3개 + 꼬리질문 형식으로 간략화.

**Deep-dive 풀버전은 git `7e4a6c8` commit에 보존** (총 16,283 라인) — 비트 단위 헤더 layout, byte-level wire protocol, byte map, 풀 시퀀스, 운영 시나리오 매트릭스 등 마스터 학습 자료. 궁금한 토픽이 생기면 그때 함께 깊이 파고듭니다.

> 이 파일은 학습 진행에 따라 계속 업데이트된다.
