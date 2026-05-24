# 02. DNS & Routing — `example.com`이 IP가 되고, 그 IP로 가는 패킷이 인터넷을 가로지르는 길

> "DNS는 hostname을 IP로 바꾸는 시스템이다" 라고 답하면 입문자.
> "브라우저 캐시 → OS resolver cache → /etc/hosts → stub resolver → recursive resolver (ISP/8.8.8.8/1.1.1.1) → root NS → TLD NS → authoritative NS 5계층의 cache hierarchy + 각 단계의 TTL + negative caching + EDNS0 → DoT/DoH 진화 + Anycast로 가까운 노드 자동 선택 + GeoDNS로 region별 다른 응답 + Route53 latency-based routing — 그리고 그 IP로 가는 패킷은 호스트 라우팅 테이블 → 기본 게이트웨이 → ISP → Tier 1 ISP backbone → BGP의 AS_PATH 선택 규칙 → ECMP flow-hash 분산 → CDN edge PoP → origin shield까지를 거친다" 라고 말할 수 있다면 그 다음 단계.
> 이 문서의 목표는 후자다.

---

## 이 문서의 사용법

이 문서는 **두 개의 큰 흐름**으로 짜여 있다.

```
[Part A] hostname → IP (DNS)
   브라우저 캐시 → OS resolver → stub → recursive → root → TLD → authoritative
                                                          (+ DoT/DoH, DNSSEC, GeoDNS, Anycast)
                                                              │
                                                              ▼
[Part B] IP → 인터넷 가로질러 백엔드까지 (Routing)
   호스트 라우팅 테이블 → 기본 게이트웨이 → ISP → Tier 1 backbone
                              ↓                       ↓
                              BGP / AS_PATH ───→ Anycast / GeoDNS
                              ↓                       ↓
                              ECMP flow-hash      CDN edge PoP
                              ↓                       ↓
                              traceroute              origin shield → origin
```

**학습 순서**:
1. 0장 마인드맵 → 7가지 가지의 이름과 핵심 키워드만 머리에 박는다.
2. 1~7장 → 각 가지를 깊이 파고든다. 각 장이 마인드맵의 한 가지에 정확히 대응.
3. 8장 운영 시나리오 → "DNS 응답 늦어 P99 spike" 같은 prod 사고에 매핑.
4. 9장 꼬리질문 → 면접 검증.

---

## 0. 마인드맵 — 면접 종이에 그릴 그림

### 루트 한 문장 (anchor)

> **"hostname을 IP로 바꾸는 DNS 5계층 cache hierarchy + 그 IP로 가는 패킷을 라우팅 테이블 → 기본 게이트웨이 → BGP AS path → ECMP/Anycast/CDN을 거쳐 백엔드에 도달시키는 인터넷 라우팅 시스템."**

### 7개 가지

```
                  [ROOT: hostname → IP → 인터넷 가로질러 백엔드까지]
                                    │
   ┌──────┬──────┬───────┬───────┬───┴───┬───────┬───────┬───────┐
   │      │      │       │       │       │       │       │       │
  ① DNS  ② DNS  ③ DNS  ④ 보안   ⑤ 지리  ⑥ IP    ⑦ Any  ⑧ CDN   ⑨ 운영
  계층   레코드 캐싱   진화      라우팅  라우팅  cast            장애
   │      │      │       │       │       │       │       │       │
   브-OS- A/AAAA TTL    UDP→TCP  GeoDNS  routing BGP    edge PoP DNS lookup
   /etc  CNAME  negative EDNS0   Latency table   AS path origin   매번
   stub  MX     poison  DoT/DoH  Weighted gateway flow  shield   네트워크
   recv  TXT    Kaminsky DNSSEC  vs       BGP    hash   cache    cache.ttl
   root  NS     1day                      ECMP   anycast key      coredns
   TLD   SRV                                              vary    NXDOMAIN
   auth  CAA                                                       함정
```

### 가지별 키워드 (3개씩)

| 가지 | 키워드 1 | 키워드 2 | 키워드 3 |
|---|---|---|---|
| **① DNS 5계층** | 브라우저→OS→stub | recursive (ISP/8.8.8.8) | root→TLD→authoritative |
| **② 레코드 종류** | A/AAAA (host→IP) | CNAME/ALIAS (alias) | MX/TXT/NS/SOA/SRV/CAA |
| **③ DNS 캐싱·TTL** | TTL (positive) | Negative caching (SOA minimum) | poisoning / Kaminsky |
| **④ DNS 진화** | UDP 53 / 512B | EDNS0 + TCP fallback | DoT (853) / DoH (443) / DNSSEC |
| **⑤ 지리 DNS** | GeoDNS (IP geo) | Latency-based (Route53) | Weighted / Failover |
| **⑥ IP 라우팅** | host 라우팅 테이블 | 기본 gateway → ISP → Tier 1 | BGP AS_PATH 선택 |
| **⑦ Anycast & ECMP** | 같은 IP 여러 위치 광고 | BGP withdraw로 failover | ECMP flow hash |
| **⑧ CDN** | edge PoP / origin shield | cache key + vary header | dynamic도 통과 (TCP/TLS term) |
| **⑨ 운영** | DNS lookup P99 spike | JVM cache.ttl 30s 함정 | CoreDNS NXDOMAIN 폭증 |

### 면접 답변 흐름

> 질문 → 루트 한 문장 → 적절한 가지 진입 → 그 가지 키워드 3개 순서로 → 듣는 사람 표정 보고 인접 가지로 확장

---

## 🌐 일반 케이스 풀버전 — `www.google.com` 요청이 어떻게 IP가 되어 라우터를 타고 가는가

> 이 섹션은 이 문서 전체의 **메인 시나리오**다. 마인드맵(0장)이 "지도", 1~9장이 "각 지역 상세지도"라면 이 섹션은 "서울에서 부산까지 실제로 운전하는 풀 영상"이다.
>
> 사용자가 브라우저 주소창에 `www.google.com` 을 치고 Enter를 누른 그 순간부터, 첫 HTTP 응답이 화면에 그려지기 직전까지의 **모든 네트워크 사건**을 한 번에 따라간다. 시니어 후보자가 면접에서 "패킷 한 개가 어떻게 인터넷을 가로지르는가" 질문에 막힘없이 풀어내려면 이 시나리오를 백지에 그릴 수 있어야 한다.

### 0.1 전체 한 장 그림 — 10단계 흐름

```
[User] 브라우저 주소창에 "www.google.com" 입력 + Enter
   │
   │ ┌───────────────────────────────────────────────────────────┐
   │ │  Part A — hostname을 IP로 바꾸기 (DNS resolution)         │
   │ ├───────────────────────────────────────────────────────────┤
   │ │ ① 브라우저: URL 파싱 / IDN 검증 / HSTS preload 확인       │
   │ │ ② 브라우저 in-memory DNS 캐시 조회                        │
   │ │ ③ OS 수준 resolver — /etc/hosts → nsswitch → cache        │
   │ │ ④ Stub resolver가 UDP 53으로 recursive에 질의             │
   │ │ ⑤ Recursive resolver의 8단계 풀버전:                       │
   │ │     Root NS → .com TLD NS → google.com Auth NS            │
   │ │     → A/AAAA/CNAME 결정 → DNSSEC 검증 → 캐시 + 응답       │
   │ │ ⑥ A vs AAAA 의사결정 (Happy Eyeballs RFC 8305)            │
   │ └───────────────────────────────────────────────────────────┘
   │ ┌───────────────────────────────────────────────────────────┐
   │ │  Part B — IP가 결정된 뒤 실제 패킷이 가는 길 (Routing)    │
   │ ├───────────────────────────────────────────────────────────┤
   │ │ ⑦ 호스트 routing table 조회 + ARP로 next-hop MAC 해석     │
   │ │ ⑧ Hop별 라우터 forwarding — TTL 감소, BGP/OSPF 경로 선택  │
   │ │ ⑨ Anycast로 가장 가까운 Google PoP에 도달                 │
   │ │ ⑩ 응답 패킷이 역순(이지만 대칭은 아님)으로 돌아옴         │
   │ └───────────────────────────────────────────────────────────┘
   ▼
[Google GFE — 가장 가까운 PoP의 front-end] 첫 TCP SYN-ACK 응답
```

> 핵심 통찰: **DNS는 한 번의 query/response가 아니다.** 클라이언트가 보는 건 1번 query지만, 실제로는 브라우저 캐시 → OS 캐시 → stub → recursive를 거쳐 recursive 내부에서 root/TLD/auth와 **다단계 대화**가 일어난다. 그리고 그렇게 얻은 IP는 **시작점일 뿐**, 호스트 라우팅 테이블과 hop별 BGP가 진짜 길을 결정한다.

---

### 0.2 단계 ①: 브라우저가 hostname을 분리

사용자가 입력한 건 `www.google.com` 한 줄이지만, 브라우저는 이걸 **URL 파서**로 잘게 쪼갠다.

```
입력: "www.google.com"
   │
   ▼
[브라우저 URL parser]
   ├── scheme 없음 → 자동 보정: "https://" or "http://" 추정
   ├── host: "www.google.com"
   ├── port: 없음 → scheme 기본 (HTTPS=443)
   ├── path: "/"
   ├── query: 없음
   └── fragment: 없음
```

**IDN (Internationalized Domain Name) 검증**:
- hostname에 ASCII 외 문자가 있으면 **Punycode** (`xn--...`)로 변환해야 DNS에 보낼 수 있음. DNS 프로토콜 자체는 ASCII만 지원.
- `www.google.com`은 전부 ASCII → punycode 변환 skip.
- 한글 도메인 예: `한국.kr` → `xn--3e0b707e.kr`.
- ★ 시니어 운영 관점: **homograph attack** — 키릴 문자 `аррӏе.com`이 시각적으로 `apple.com`처럼 보이게 만드는 공격. 브라우저는 IDN 표시 정책으로 의심스러우면 punycode 그대로 노출.

**HSTS preload 확인** (`https://` 강제):
- 브라우저는 빌드 시점에 **HSTS preload list**를 내장 (`chrome://net-internals/#hsts`).
- `google.com`은 preload 등재 → 사용자가 `http://www.google.com`을 입력해도 브라우저가 **DNS 가기 전에** 스스로 `https://www.google.com`으로 rewrite.
- 즉, **첫 HTTP 평문 요청이 아예 나가지 않음**. SSL strip 공격 무력화.

```
[브라우저 입력]
   "www.google.com"
        │
        ▼
   URL 파싱: scheme=?(없음), host=www.google.com, port=?, path=/
        │
        ▼
   ┌─────────────────────────────┐
   │  HSTS preload list 조회      │
   │  google.com → 등재됨!         │
   │  ⇒ scheme=https, port=443    │
   └─────────────────────────────┘
        │
        ▼
   "https://www.google.com/"  (이제부터 이 정규화된 URL로 진행)
```

**시니어 운영 관점**:
- 사내 ALB/CDN 도메인을 HSTS preload에 등재하려면 1년 이상의 strict-transport-security 운영 이력 + 무중단 HTTPS 보장 필요. 한번 등재되면 **회수 시간 수개월** → MSP 이관/도메인 매각 시 발목.
- 신규 서비스에서는 `Strict-Transport-Security: max-age=31536000; includeSubDomains` 부터 단계적으로.

---

### 0.3 단계 ②: 브라우저 in-memory DNS 캐시

브라우저는 **자기 프로세스 안에서** 직전에 resolve한 hostname → IP 매핑을 잠깐 보관한다. OS 캐시를 거치는 비용조차 아끼는 것.

```
[Chrome 프로세스 메모리]
   ┌───────────────────────────────────────────────┐
   │  DNS in-memory cache (TTL 기반)                │
   │  ──────────────────────────────────────────    │
   │  www.google.com  → 142.250.196.132  TTL: 245s  │
   │  www.naver.com   → 223.130.200.107  TTL: 30s   │
   │  fonts.gstatic.com → 142.251.220.99  TTL: 88s  │
   └───────────────────────────────────────────────┘
            │
            ▼
       cache hit? → 즉시 IP 반환, 다음 단계 skip
       cache miss → 단계 ③ (OS resolver)로
```

**브라우저별 위치/도구**:
- Chrome/Edge: `chrome://net-internals/#dns` — 현재 캐시된 모든 hostname 목록 + TTL 잔여. "Clear host cache" 버튼.
- Firefox: `about:networking#dns` — 같은 기능, 더 자세한 entry 정보.
- Safari: 별도 UI 없음. mDNSResponder 캐시 flush로 우회.

**TTL 처리 정책 (브라우저별 차이)**:
- 브라우저는 **DNS TTL을 그대로 따르지 않을 수 있다**. Chrome은 보통 60초 ~ 수 분 사이로 캡 (보안+성능 trade-off). DNS rebinding 공격 방어 목적도 있음.
- 즉, **auth NS가 TTL 1초로 주더라도 브라우저는 60초 동안 캐싱**할 수 있음. failover 설계 시 함정.

**시니어 운영 관점**:
- 운영 사고: "auth NS의 A 레코드를 바꿨는데 사내 PC가 옛 IP로 계속 붙는다" → OS 캐시 flush해도 안 풀리면 **브라우저 캐시 의심**. `chrome://net-internals/#dns`에서 "Clear host cache" + 탭 재로드.
- 모바일 앱(Android/iOS)은 자체 HTTP 클라이언트(OkHttp/URLSession) 안에 별도 DNS 캐시. OS 캐시 무관.

---

### 0.4 단계 ③: OS 수준 DNS 해석

브라우저 캐시 miss면 OS의 `getaddrinfo(3)` syscall로 내려간다. 이게 OS-level DNS의 진입점.

```
[브라우저 프로세스]
   getaddrinfo("www.google.com", "443", &hints, &result)
        │
        ▼
[glibc / libc resolver (Linux) — 또는 SCDynamicStore (macOS)]
   │
   │ /etc/nsswitch.conf 의 hosts 순서 따름
   │   예: hosts: files mdns4_minimal dns
   │
   ├── [a] files: /etc/hosts 먼저 확인
   │       127.0.0.1   localhost
   │       10.0.0.5    db.internal
   │       ★ 일치하면 즉시 반환, DNS 거치지 않음 (override 가능)
   │
   ├── [b] mdns: 로컬 네트워크의 .local 도메인 (Bonjour/Avahi)
   │
   └── [c] dns: 진짜 DNS 시작
           │
           ▼
       OS resolver cache (systemd-resolved / nscd / mDNSResponder)
           │
           │ hit → 반환
           │ miss → stub resolver로 (단계 ④)
           ▼
       /etc/resolv.conf 의 nameserver 읽음
```

**플랫폼별 캐시 데몬**:
- **Linux (systemd 환경)**: `systemd-resolved` (`127.0.0.53:53` 로컬 stub) — `resolvectl statistics`, `resolvectl flush-caches`.
- **Linux (구식) / 컨테이너 이미지**: `nscd` 또는 캐시 없음. ★ 컨테이너에서 nscd 미설치면 **매 syscall마다 DNS** → 폭주 원인.
- **macOS**: `mDNSResponder` — `sudo dscacheutil -flushcache; sudo killall -HUP mDNSResponder`.
- **Windows**: DNS Client 서비스 — `ipconfig /displaydns`, `ipconfig /flushdns`.

**`/etc/hosts`의 힘**: DNS보다 **무조건 우선** (nsswitch.conf의 `hosts: files dns`에서 files가 먼저). 운영 사고에서 "지금 당장 이 호스트만 다른 IP로 보내야 한다"의 가장 빠른 처방. ★ Kubernetes Pod의 `/etc/hosts`는 Pod 재생성 시 사라짐 → `spec.hostAliases`로 선언적 관리.

**`/etc/nsswitch.conf` 순서가 왜 중요한가**: `hosts: files mdns4_minimal [NOTFOUND=return] dns` — `[NOTFOUND=return]`이 있으면 mdns가 NOTFOUND 응답 시 dns로 안 넘어감 → 잘못 설정하면 외부 hostname 안 풀림. 일부 컨테이너는 nsswitch.conf 없음 → glibc가 dns만 시도.

**`/etc/resolv.conf` 의 핵심 필드**:

```
nameserver 8.8.8.8           ← 첫 번째 recursive resolver
nameserver 1.1.1.1           ← fallback (1번이 fail 시)
nameserver 168.126.63.1      ← (KT DNS)
search corp.example.com svc.cluster.local
options ndots:5 timeout:2 attempts:2 rotate
```

- `nameserver`: 최대 3개. 위에서부터 시도, timeout 시 다음.
- `search`: hostname에 dot이 `ndots` 미만이면 search 도메인 차례로 append해서 시도.
- `timeout`: query 타임아웃 (초). 기본 5 → 2로 줄이는 게 운영 관행.
- `attempts`: nameserver당 재시도 횟수.
- `rotate`: 매 query마다 nameserver 순서 round-robin.

→ Kubernetes Pod의 resolv.conf 자동 생성 정책이 9.5 패턴 4(CoreDNS NXDOMAIN 폭증)의 원인. 여기서 그 함정의 뿌리를 알게 됨.

---

### 0.5 단계 ④: Stub Resolver → Recursive Resolver

OS 캐시까지 miss하면 진짜 외부로 DNS 패킷이 나간다.

**Stub resolver의 역할**:
- 클라이언트의 가장 얇은 DNS 클라이언트. `getaddrinfo`가 부르는 라이브러리 함수 안에 내장.
- **스스로 root/TLD를 묻지 않음**. 단 한 곳, `/etc/resolv.conf`의 nameserver에 "이거 풀어줘" 던지고 응답 받는 게 끝.
- 이름 그대로 "stub" = 끄트머리.

**Recursive resolver의 역할**:
- 진짜 작업하는 쪽. 자기가 root → TLD → auth를 다 돌고, 결과를 stub에 돌려줌.
- "recursive"라는 이름은 **stub 입장에서 한 번에 답을 받는다**는 뜻 (실제 내부 구현은 iterative).
- 보통 ISP(KT/SKB) 또는 Public DNS(8.8.8.8/1.1.1.1) 또는 사내 (CoreDNS).

```
[Client host]                              [Recursive Resolver]
   ┌──────────────────────┐                ┌──────────────────────┐
   │  brower / app         │                │  자기 큰 cache         │
   │     ↓ getaddrinfo()   │                │  (수십만 entry)       │
   │  Stub resolver        │                │                       │
   │  (libc 안)            │                │  miss 시 root → TLD → │
   │     │                 │                │  auth 직접 묻음        │
   └─────┼─────────────────┘                └──────────────────────┘
         │                                             ▲
         │  UDP 53 query:                              │
         │  "www.google.com A?"                        │
         │  ID=0xABCD, RD=1 (Recursion Desired)        │
         ├─────────────────────────────────────────────┤
         │                                             │
         │  UDP 53 response:                           │
         │  ID=0xABCD, ANSWER: 142.250.196.132 TTL=300 │
         ◀─────────────────────────────────────────────┘
```

**UDP 53 — 왜 UDP인가**:
- DNS query/response는 보통 작음 (수십~수백 byte). TCP의 3-way handshake 오버헤드 불필요.
- 손실되면 stub이 timeout 후 재전송 (resolv.conf의 `attempts`).
- ★ 응답이 **512 byte를 넘으면**? UDP DNS의 원래 spec은 512B 제한.
  - DNS 헤더의 `TC` (truncated) 비트 set → stub이 "잘림" 인지.
  - stub은 같은 query를 **TCP 53**으로 재전송 → 큰 응답 전체 받음.
  - 또는 **EDNS0** (RFC 6891): query의 OPT 레코드에 "나 UDP로 4096 byte까지 받을 수 있어" 명시 → 큰 응답도 UDP로 가능.

```
[stub의 UDP 53 query 패킷]
  UDP header (src:54321, dst:53)
  DNS header (ID:0xABCD, QR=0 query, RD=1 recursion-desired, QDCOUNT=1)
  Question  (QNAME: www.google.com, QTYPE: A, QCLASS: IN)
  Additional (EDNS0 OPT — "UDP 4096 byte 가능")
```

**시니어 운영 관점**:
- 사내 방화벽이 **UDP 53만 열고 TCP 53 닫혀 있는** 경우 → 큰 응답(DNSSEC, 다수의 A 레코드) 못 받음 → 간헐적 lookup 실패. 방화벽 규칙 점검.
- 8.8.8.8/1.1.1.1은 anycast → 한국에서 query 시 **서울 PoP**가 응답. 8.8.8.8이 지구 반대편이라 느릴 거라는 흔한 오해.

---

### 0.6 단계 ⑤: Recursive Resolver의 8단계 풀버전 (★ 핵심)

stub이 query를 던지면 recursive resolver는 **자기 cache 먼저 확인**한다. 거기 hit이면 바로 응답 (대부분의 경우). cache miss 또는 expired면 **cold path** — root부터 차근차근 묻기 시작.

```
                            [Recursive Resolver]
                                    │
                                    │ cache miss (cold)
                                    ▼
   1. 자기 cache 조회 ───────────────┘ miss
   ┌──────────────────────────────────────────────────────────┐
   │                                                          │
   │  ROOT 서버 (".")                                          │
   │  ─ a.root-servers.net ~ m.root-servers.net (13 letters)   │
   │  ─ 각 letter는 anycast로 전세계 수십~수백 instance       │
   │                                                          │
   │  Query: "www.google.com A?"                              │
   │  Root: "나 final 답 모름. .com 은 Verisign이 관리한다."  │
   │         Authority: a.gtld-servers.net ~ m.~              │
   │         Additional: 각 gtld-server의 A/AAAA (glue)       │
   │                                                          │
   └──────────────────────────────────────────────────────────┘
                  │
                  │  (recursive는 .com NS 목록 받음)
                  ▼
   ┌──────────────────────────────────────────────────────────┐
   │  TLD 서버 (".com")                                       │
   │  ─ Verisign이 운영 (전세계 anycast cluster)               │
   │                                                          │
   │  Query: "www.google.com A?"                              │
   │  TLD:  "나도 final 답 모름. google.com 은 다음 NS가 관리."│
   │         Authority: ns1.google.com ~ ns4.google.com       │
   │         Additional: ns1.google.com A 216.239.32.10 (glue) │
   │                                                          │
   └──────────────────────────────────────────────────────────┘
                  │
                  │  (recursive는 google.com NS 목록 + glue 받음)
                  ▼
   ┌──────────────────────────────────────────────────────────┐
   │  AUTHORITATIVE NS (google.com)                            │
   │  ─ ns1.google.com ~ ns4.google.com                        │
   │  ─ Google이 직접 운영 (anycast)                            │
   │                                                          │
   │  Query: "www.google.com A?"                              │
   │  Auth: "★ 142.250.196.132   TTL=300  (이게 final!)"      │
   │         + RRSIG (DNSSEC 서명, 있으면)                     │
   │                                                          │
   └──────────────────────────────────────────────────────────┘
                  │
                  │  (recursive는 최종 A 레코드 받음)
                  ▼
   2. DNSSEC validation chain 확인 (활성화된 경우):
         . → .com → google.com 의 DS/DNSKEY/RRSIG 검증
   3. Recursive는 결과를 자기 cache에 TTL(300s)만큼 저장
   4. Stub resolver에 응답 → OS cache → 브라우저 cache → 사용자 코드
```

**Glue record가 왜 필요한가**:
- TLD가 "google.com NS는 ns1.google.com이야"라고만 답하면 recursive는 `ns1.google.com`의 IP를 또 어딘가에 물어야 함. 그런데 `ns1.google.com`의 권한 NS는 `google.com` 자신 → **순환 의존**.
- 해결: TLD가 NS 응답에 `ns1.google.com`의 A 레코드도 **같이** 넣어줌. 이게 **glue record**.
- 부모 zone(.com)이 자식 zone(google.com)의 NS 호스트 IP를 "접착제(glue)"로 들고 있어서 부트스트랩 가능.

**Root server가 13개? 실은 수백 대 (anycast)**:
- 이름은 `a ~ m` 13개 letter. 각 letter는 **하나의 IP**처럼 보이지만 실제로는 **anycast 광고**되는 수십~수백 instance.
- 한국에서 root 질의 시 한국 또는 가까운 동아시아 PoP의 instance가 응답.
- 13인 이유는 IPv4 UDP 512B response에 13개 NS + glue를 다 우겨넣을 수 있는 한계 (역사적). EDNS0 이후엔 더 가능하지만 관습으로 유지.

**왜 .com TLD에 직접 안 가나? — 캐시 hierarchy의 본질**:

```
이상적: recursive가 처음부터 .com TLD가 누군지 알면 root 생략 가능
현실:
   - recursive는 root NS의 IP만 "root hints 파일"로 알고 시작
   - 한 번 .com NS를 root에서 받으면 그걸 자기 cache에 저장 (TTL 172800s = 2일)
   - 이후 .com 도메인 질의는 root 거치지 않음 → root는 사실상 cold start에만 hit
```

→ **root server 부하가 인터넷 규모에 비해 작은 이유**: TLD NS 캐시 TTL이 매우 김 + recursive가 수십만 클라이언트의 query를 흡수해서 root까지 안 보냄.

**DNSSEC validation chain** (recursive resolver가 활성화한 경우):

```
. (root) ──DS──▶ .com ──DS──▶ google.com ──RRSIG──▶ A 레코드
        DNSKEY       DNSKEY        DNSKEY
        (각 zone의 DNSKEY가 부모의 DS와 매치되어야 chain 성립)
```

- chain of trust: 어디 하나라도 깨지면 SERVFAIL.
- 모든 zone이 DNSSEC 켜져 있지는 않음 (구글은 켜져 있음, 많은 일반 zone은 미사용).

**시니어 운영 관점**:
- "왜 우리 회사 도메인은 dig +trace로 끝까지 잘 풀리는데 코드에서는 NXDOMAIN?" → recursive resolver의 cache 상태 차이. 회사 DNS는 캐시했지만 8.8.8.8은 cache miss + auth NS와의 통신 불안정한 경우.
- 신규 도메인 생성 직후 "DNS propagation"이라고 부르는 현상은 사실 **TLD에 글루 등록되는 시간 + 각 recursive가 자기 cache(negative or positive) refresh하는 시간**. 일반적으로 수 분 ~ 수 시간.

---

### 0.7 단계 ⑥: A vs AAAA vs CNAME 의사결정

`www.google.com`은 사실 **여러 종류의 응답**을 줄 수 있다.

```
Auth NS의 zone 데이터 (개념적):
   www.google.com  A      142.250.196.132   TTL 300
   www.google.com  A      142.250.196.196   TTL 300   (round-robin)
   www.google.com  A      142.250.196.227   TTL 300
   www.google.com  AAAA   2607:f8b0:4004:c1b::93  TTL 300
   www.google.com  AAAA   2607:f8b0:4004:c1b::6a  TTL 300
```

**클라이언트의 의사결정**:

```
[Dual-stack 클라이언트 (IPv4 + IPv6 모두 가능)]
   │
   ├── A query     ──▶ "142.250.196.132"
   │
   ├── AAAA query  ──▶ "2607:f8b0:4004:c1b::93"
   │
   ▼
[Happy Eyeballs (RFC 8305)]
   ─ AAAA가 먼저 도착하면 IPv6 시도
   ─ 50~250ms 안에 IPv6 SYN-ACK 못 받으면 IPv4 SYN 병행 시작
   ─ 먼저 ACK 돌아오는 쪽으로 연결, 늦는 쪽은 RST
   ─ 결과: 사용자는 IPv6 우선이되 fallback이 매끄러움
```

**왜 Happy Eyeballs가 필요한가**:
- 옛날엔 "IPv6 있으면 IPv6, 없으면 IPv4". 그런데 IPv6 경로가 broken (라우팅은 광고하지만 실제 패킷 안 가는) 케이스가 흔했음 → 사용자는 30초 timeout 후 IPv4 fallback → "와이파이가 느리다" 인식.
- Happy Eyeballs는 **둘 다 시도**하고 빠른 쪽 채택 → broken IPv6도 250ms 안에 IPv4로 우회.

**CNAME alias의 케이스**:

```
zone 데이터:
   www.example.com   CNAME   example.com
   example.com       A       93.184.216.34

resolver의 동작:
   1. www.example.com A query
   2. auth NS: "CNAME → example.com" 응답
   3. resolver가 자동으로 example.com A query 추가 (chasing)
   4. example.com A 93.184.216.34 응답
   5. stub에 두 레코드 다 전달 또는 final A만
```

**ALIAS / ANAME (apex CNAME 대체)**:
- RFC상 apex(`example.com`)에 CNAME 불가 (NS, SOA와 충돌).
- 그래서 AWS Route53의 **ALIAS**, Cloudflare의 **CNAME flattening** — NS 측에서 resolve해서 **A 레코드로 평탄화**해 응답.
- 사용자(stub)는 그냥 A 레코드로 보고, CNAME 관계는 NS 내부에만 존재.

**`www.google.com`의 실제 케이스**:
- 과거: `www.google.com CNAME www.l.google.com` 같은 식의 alias 운영.
- 현재: 단순 A/AAAA. Google이 직접 anycast IP로 처리.
- 단, **`www.l.google.com`이나 `gstatic.com` 등의 sub-asset**는 여전히 CNAME 체인이 있을 수 있음.

---

### 0.8 단계 ⑦: hostname → IP 결정 후, 호스트 라우팅 시작 (L3/L2)

DNS가 끝나고 `142.250.196.132`라는 IP를 손에 쥐었다. 이제부터는 **이 IP로 패킷을 보내는 길**을 찾는 일.

```
[클라이언트 호스트의 routing table]
   $ ip route show
   default via 192.168.1.1 dev wlan0 proto dhcp metric 600
   169.254.0.0/16 dev wlan0 scope link metric 1000
   192.168.1.0/24 dev wlan0 proto kernel scope link src 192.168.1.10
```

**의사결정 흐름**:

```
dst = 142.250.196.132 (www.google.com의 A 결과)
   │
   ▼
[routing table lookup — longest prefix match]
   │
   ├── 142.250.196.132 in 192.168.1.0/24 ?   No
   ├── 142.250.196.132 in 169.254.0.0/16 ?   No
   └── default (0.0.0.0/0) ?                 Yes
        │
        ▼
   next-hop = 192.168.1.1 (기본 게이트웨이)
   out_interface = wlan0
   src IP = 192.168.1.10
```

**같은 subnet vs 다른 subnet**:

```
case A — 같은 subnet (예: dst=192.168.1.50):
   ┌─────────────────────────────────────┐
   │ routing table: 직접 송신 (직결)      │
   │ ARP로 192.168.1.50의 MAC 해석        │
   │ Ethernet frame:                      │
   │   src MAC = 내 MAC                   │
   │   dst MAC = 192.168.1.50의 MAC        │
   │ → switch가 MAC table 보고 forward    │
   └─────────────────────────────────────┘

case B — 다른 subnet (예: dst=142.250.196.132):
   ┌─────────────────────────────────────┐
   │ routing table: default gateway 경유   │
   │ ARP로 192.168.1.1 (gateway)의 MAC 해석│
   │ Ethernet frame:                      │
   │   src MAC = 내 MAC                   │
   │   dst MAC = ★ gateway의 MAC          │  ← 중요!
   │   src IP  = 192.168.1.10              │
   │   dst IP  = 142.250.196.132           │
   │ → gateway가 IP는 그대로, L2만 새로    │
   └─────────────────────────────────────┘
```

★ **핵심 통찰**: **L3(IP) 주소는 출발지~최종 목적지를 가리키지만, L2(MAC) 주소는 next-hop만 가리킨다**. 패킷이 hop마다 새 L2 frame으로 다시 포장되지만 IP header는 그대로. ARP는 L2와 L3 사이의 helper 프로토콜 (RFC 826) — 자세한 위치는 6.6.3 참조.

**ARP request/reply 흐름과 cache 동작은 6.6.1~6.6.4에서 자세히 다룬다.** 여기서는 "DNS 직후 IP가 결정되면 ARP로 next-hop MAC을 채워 L2 frame을 만든다"만 기억하자.

**시니어 운영 관점 (단계 ⑦ 한 줄)**:
- 게이트웨이 교체 시 ARP cache 만료(수 분)까지 옛 MAC으로 송신 지속.
- ARP는 L2 broadcast → 같은 subnet 안에서만. broadcast domain = L2 subnet 경계.
- IPv6는 ARP 대신 NDP (ICMPv6) → 자세한 비교는 6.6.5.

---

### 0.9 단계 ⑧: 라우터 hop들 — BGP / OSPF / IS-IS

호스트가 패킷을 게이트웨이에 넘긴 후부터는 **라우터들의 연쇄 forwarding**.

```
[클라이언트] → [홈 라우터] → [ISP edge] → [ISP regional] → [ISP backbone] → [IX]
                                                                              │
                              [Google edge] ← [transit] ← [peering point] ←──┘
                                    │
                                    ▼
                              [Google PoP server]
```

각 hop의 라우터는:
1. 들어온 패킷의 dst IP 봄.
2. 자기 routing table (FIB)에서 longest prefix match.
3. next-hop interface로 forward.
4. **IP TTL을 -1** (loop 방지 + traceroute 원리).
5. L2 header는 새로 만듦 (src MAC = 자기, dst MAC = next-hop).

**TTL의 의미**:
- IP 헤더의 8-bit 필드 (0~255). 보통 OS가 64 또는 128로 set.
- hop마다 -1. 0이 되면 **drop + ICMP TIME_EXCEEDED를 출발지에 보냄**.
- 라우팅 루프(잘못 설정으로 두 라우터가 서로 패킷 던지는) 방지 목적.

**traceroute가 이 원리를 역이용**:

```
$ traceroute -n www.google.com

probe 1: TTL=1로 송신 → 홈 라우터에서 TTL=0 → ICMP TIME_EXCEEDED → 홈 라우터 IP 노출
probe 2: TTL=2로 송신 → ISP edge에서 TTL=0 → ICMP TIME_EXCEEDED → ISP edge IP 노출
probe 3: TTL=3 → ISP regional 노출
...
probe N: TTL=N → 목적지 도달 → ICMP echo reply 또는 TCP RST
```

→ 각 hop의 라우터 IP를 차례로 알아내서 **전체 경로**를 그릴 수 있음.

**ISP 내부 라우팅 (IGP)**: OSPF, IS-IS
- AS(Autonomous System) **안에서** 라우터들이 서로 "내가 어디에 도달 가능해" 광고.
- 링크 비용 기반 최단 경로 (Dijkstra).
- OSPF: 일반 기업/ISP. IS-IS: 대형 ISP backbone.
- 빠른 수렴 (수 초 ~ 수십 초).

**ISP 간 라우팅 (EGP)**: BGP
- AS **사이에서** "이 IP 대역은 내 AS를 통해 가" 광고.
- **path vector** 방식 — AS path 길이 + policy로 경로 선택.
- 수렴 느림 (수 분 ~ 수십 분).
- 정치/계약(peering vs transit)이 기술만큼 중요.

```
[BGP 광고 예]
   AS15169 (Google):
     "142.250.0.0/15 은 내거야. AS path = [15169]"
        │
        ▼ peering으로 전파
   AS3356 (Lumen):
     "142.250.0.0/15 → AS path = [3356, 15169]"
        │
        ▼ transit 고객에게 전파
   AS9318 (KT):
     "142.250.0.0/15 → AS path = [9318, 3356, 15169]"
```

**`whois`로 AS 확인**:
```
$ whois -h whois.cymru.com " -v 142.250.196.132"
AS      | IP               | BGP Prefix          | CC | Registry | Allocated  | AS Name
15169   | 142.250.196.132  | 142.250.196.0/24    | US | arin     | 2012-04-16 | GOOGLE, US
```

→ `142.250.196.132`은 **AS15169 (Google)** 소속. BGP prefix는 `142.250.196.0/24`.

**시니어 운영 관점**:
- "왜 한국에서 미국 도달하는데 평소 100ms인데 어느 날 갑자기 300ms?" → BGP 경로 변경. Looking glass(`lg.he.net`)로 확인. 보통 transit ISP의 peering link 변경/장애 → 다른 ISP 경유.
- BGP **수렴 중**에는 경로 깜빡임(flapping) + asymmetric routing 빈발 → P99 spike.
- **route hijacking** 사고: 누군가가 잘못된 AS path를 광고해 자기 AS로 트래픽 끌어감 (실수 또는 악의). RPKI로 일부 방어.

---

### 0.10 단계 ⑨: AS path와 Anycast — Google PoP까지

`142.250.196.132`는 **anycast IP**다. 즉, 전 세계 Google PoP들이 **같은 IP를 동시에 BGP로 광고**.

```
                              [Internet BGP table]
                              "142.250.196.0/24 → AS15169"
                                       │
              ┌────────────┬───────────┼───────────┬────────────┐
              │            │           │           │            │
         [Tokyo PoP]   [Singapore]  [LA]       [Frankfurt]  [Sydney]
              ↑            ↑           ↑           ↑            ↑
              │            │           │           │            │
         같은 IP       같은 IP      같은 IP     같은 IP       같은 IP
         142.250.196.x 142.250.196.x 142.250.196.x ...      ...
```

**한국 사용자가 142.250.196.132로 보내면**:
1. 자기 ISP(KT)의 BGP가 `142.250.196.0/24`에 대해 **가장 짧은 AS path**를 가진 경로 선택.
2. 보통 한국 → 일본 또는 한국 직접 PoP (Google은 서울에도 PoP 있음).
3. 그 PoP의 라우터까지 BGP forwarding.

```
[한국 사용자]
   │
   ▼
[KT backbone]  ── BGP: 142.250.196.0/24 → next-hop = (Google Tokyo or 서울)
   │
   ▼
[IX 또는 peering]
   │
   ▼
[Google Tokyo PoP의 라우터]
   │
   ▼
[Google front-end (GFE) — 가장 가까운 PoP의 reverse proxy]
   │
   ▼
[Google internal RPC — Stubby, Spanner, Bigtable 등 사내 서비스]
   │
   ▼
[Search index, ad ranking, ... 응답 생성]
```

**Google Front-End (GFE)의 역할**:
- TCP/TLS termination을 PoP에서. 사용자와의 TLS handshake는 PoP에서 끝.
- PoP과 backend 사이는 **별도의 내부 connection** (사내 백본 + 내부 인증).
- 즉, "anycast TCP의 함정 (PoP 중간 변경)"이 일어나도 사용자 TCP는 PoP까지만 살아있으면 됨.

**시니어 운영 관점**:
- 우리 회사가 anycast를 도입할 때 가장 흔한 함정: **L4 TCP termination을 anycast IP로 하면 BGP convergence 중 연결 끊김**. 그래서 CDN처럼 PoP에서 TCP 종단 + 내부 연결 분리 패턴이 표준.
- DNS는 UDP라서 anycast 친화적 (한 query/response 단발성).

---

### 0.11 단계 ⑩: 응답 패킷이 역순으로 돌아옴 (이지만 대칭은 아님)

```
[Google PoP] ───── 응답 패킷 ─────▶ [한국 사용자]
   ▲                                    │
   │                                    │ 요청 패킷이 갔던 경로:
   │                                    │  KT → IX1 → Tokyo PoP
   │                                    │
   │ 응답이 돌아오는 경로:               │
   │  Tokyo PoP → IX2 → SK → 사용자     │
   │ (★ 같은 경로 보장 없음 — asymmetric routing)
```

**왜 asymmetric routing이 발생하나**:
- 각 방향은 **각자의 BGP table**로 결정. 출발지 ↔ 도착지 BGP 경로가 다를 수 있음.
- 특히 multi-homed 환경 (여러 ISP 연결)에서 흔함.
- 단방향 100ms / 반대 200ms 같은 비대칭 latency 가능.

**asymmetric routing의 함정**:
- **stateful firewall** (NAT, conntrack)는 outbound와 inbound가 같은 장비를 지나가야 state 매칭 가능. asymmetric이면 inbound가 다른 방화벽 거치면 "처음 보는 connection"으로 인식 → drop.
- 대규모 클라우드(AWS, GCP)는 내부 라우팅을 symmetric으로 유지하지만, 사용자 ↔ 클라우드는 asymmetric 흔함.

**ICMP 응답 처리**:
- 라우터들은 IP TTL 0 시 ICMP TIME_EXCEEDED 발송. 이게 traceroute의 원리.
- 일부 라우터는 ICMP rate-limit → traceroute에서 hop이 `* * *`로 보이는 이유.
- 일부 라우터는 ICMP 완전 차단 → ICMP unreachable 응답 못 받음 → "왜 timeout인지 모름".

---

### 0.12 한 장 정리 — 시퀀스 다이어그램 풀버전

```
[User]   [Browser]   [OS]   [Stub]   [Recursive]   [Root]   [.com TLD]   [google.com Auth]   [Routers]   [Google PoP]
  │         │         │       │           │            │          │              │                │            │
  │ Enter "www.google.com"                              │          │              │                │            │
  │────────▶│         │       │           │            │          │              │                │            │
  │         │ URL 파싱+HSTS preload → https://         │          │              │                │            │
  │         │ in-mem cache? miss                       │          │              │                │            │
  │         │────▶│   getaddrinfo()                     │          │              │                │            │
  │         │     │ /etc/hosts → 없음                   │          │              │                │            │
  │         │     │ resolver cache → miss               │          │              │                │            │
  │         │     │────▶│ UDP 53 query                  │          │              │                │            │
  │         │     │     │────────────▶│                  │          │              │                │            │
  │         │     │     │             │ cache miss     │          │              │                │            │
  │         │     │     │             │───── ".com NS?" ──▶│          │              │                │            │
  │         │     │     │             │ ◀──── NS list + glue ────│          │              │                │            │
  │         │     │     │             │─────────── "google.com NS?" ──▶│              │                │            │
  │         │     │     │             │ ◀────────── NS list + glue ──────│              │                │            │
  │         │     │     │             │──────────────── "www.google.com A?" ──────▶│                │            │
  │         │     │     │             │ ◀─────────────── A 142.250.196.132 TTL=300 ──│                │            │
  │         │     │     │             │ DNSSEC validate (옵션)   │          │              │                │            │
  │         │     │     │             │ cache 저장             │          │              │                │            │
  │         │     │     │ ◀──────────│                         │          │              │                │            │
  │         │     │ ◀───│                                     │          │              │                │            │
  │         │ ◀───│                                            │          │              │                │            │
  │         │                                                  │          │              │                │            │
  │         │ TCP SYN → 142.250.196.132:443                    │          │              │                │            │
  │         │────────────────────────────────────────────────────────────────────────────────────▶│            │
  │         │                                                                                       │ ARP, BGP   │
  │         │                                                                                       │ hop-by-hop │
  │         │                                                                                       │────────────▶│
  │         │                                                                                       │            │
  │         │ ◀──────────────────────────────────────────────────────────────────────────────────  TCP SYN-ACK
  │         │ ◀── TLS handshake ── HTTPS GET / ── 응답 ───────────────────────────────────────────│
  │ ◀──────  렌더링                                                                                  │            │
```

→ 이 한 장이 머리 속에 있으면 **"브라우저에 google.com 치면 어떻게 돼?" 질문에 막힘없이 흘러갈 수 있다**.

### 0.13 백지 마스터 체크 — 이 시퀀스를 30초 안에 그릴 수 있나

| 단계 | 핵심 한 줄 | 도구 |
|---|---|---|
| ① 브라우저 파싱 | URL 분해 + IDN/punycode + HSTS preload | `chrome://net-internals/#hsts` |
| ② 브라우저 캐시 | in-memory, TTL 캡 60s | `chrome://net-internals/#dns` |
| ③ OS resolver | /etc/hosts → nsswitch → cache → resolv.conf | `resolvectl statistics`, `dscacheutil` |
| ④ Stub→Recursive | UDP 53, EDNS0, ID 매칭 | `dig`, `tcpdump -i any udp port 53` |
| ⑤ Root/TLD/Auth | 8단계 + glue + DNSSEC | `dig +trace +dnssec` |
| ⑥ A vs AAAA | Happy Eyeballs, CNAME, ALIAS | `dig A`, `dig AAAA` |
| ⑦ Host routing | longest prefix match + ARP | `ip route`, `arp -a` |
| ⑧ Hop forwarding | TTL --, OSPF/IS-IS/BGP | `traceroute`, `mtr` |
| ⑨ Anycast PoP | 같은 IP 여러 위치, 가까운 PoP | `whois -h whois.cymru.com`, `lg.he.net` |
| ⑩ 응답 역순 | asymmetric routing 가능 | `mtr` 양방향 |

---

## 1. 가지 ①: DNS 5계층 — hostname이 IP가 되는 경로

### 1.1 핵심 질문

> "브라우저에 `https://example.com` 치고 Enter 누르면 IP는 어디서 어떻게 얻나요?"

### 1.2 백지에 그리는 5계층 (실제로는 6~7단)

```
[브라우저 프로세스 내부]
   ┌─────────────────────────────────────┐
   │  1. 브라우저 in-memory DNS cache    │  ← 수 분 ~ 수 시간 (브라우저별)
   │     (Chrome: chrome://net-internals/#dns)│
   └────────────────┬────────────────────┘
                    │ miss
                    ▼
[OS 영역 — getaddrinfo() syscall]
   ┌─────────────────────────────────────┐
   │  2. OS resolver cache               │  ← systemd-resolved / nscd
   │     (macOS: discoveryd, Win: DNS Client)│
   └────────────────┬────────────────────┘
                    │ miss
                    ▼
   ┌─────────────────────────────────────┐
   │  3. /etc/hosts (또는 nsswitch.conf  │  ← 정적 매핑 (개발용)
   │      hosts: files dns 순서)         │
   └────────────────┬────────────────────┘
                    │ no entry
                    ▼
[stub resolver — OS 안의 작은 DNS client]
   ┌─────────────────────────────────────┐
   │  4. stub resolver가 UDP 53으로      │  ← /etc/resolv.conf의 nameserver
   │     설정된 recursive resolver에 질의│      (보통 ISP DNS or 8.8.8.8)
   └────────────────┬────────────────────┘
                    │
                    ▼
[네트워크 너머 — recursive resolver]
   ┌─────────────────────────────────────┐
   │  5. Recursive resolver              │  ← 자기 cache 먼저 본다
   │     (캐시 hit이면 즉시 응답)         │      TTL이 살아있는 한
   └────────────────┬────────────────────┘
                    │ cache miss (cold)
                    ▼
   ┌─────────────────────────────────────┐
   │  6. Root NS (13개 cluster, anycast) │  ← "com NS 알려달라" 응답:
   │     a.root-servers.net ~ m.~        │     "com TLD NS는 a.gtld-servers.net"
   └────────────────┬────────────────────┘
                    │
                    ▼
   ┌─────────────────────────────────────┐
   │  7. TLD NS (com, kr, io, ...)       │  ← "example.com NS는?":
   │     gTLD/ccTLD operator             │     "ns1.example-dns.com"
   └────────────────┬────────────────────┘
                    │
                    ▼
   ┌─────────────────────────────────────┐
   │  8. Authoritative NS                │  ← 진짜 답:
   │     (example.com 도메인 소유자가     │     "example.com → A 93.184.216.34"
   │      운영하거나 Route53/Cloudflare 등)│
   └─────────────────────────────────────┘
                    │
                    ▼ (역방향으로 cache 채우며 돌아옴)
   recursive → stub → OS cache → 브라우저 cache → 사용자 코드
```

→ **재귀 (recursive)**: 가운데 resolver가 자기 책임으로 root → TLD → auth 3번을 묻고 정답을 가져온다. 사용자(stub)는 **반복(iterative)**가 아니라 recursive 답만 받는다. 그래서 이름이 "recursive resolver".

### 1.3 키워드 1 — 브라우저 캐시 → OS resolver → /etc/hosts

```
브라우저 캐시:
   Chrome: chrome://net-internals/#dns 에서 "Clear host cache"
   브라우저별 정책 다름, 보통 1분 ~ 1시간
   ★ TTL을 무시하는 경우도 있음 (보안 vs 성능 trade-off)

OS resolver cache:
   Linux systemd-resolved: resolvectl statistics
   macOS: sudo dscacheutil -flushcache; sudo killall -HUP mDNSResponder
   Windows: ipconfig /flushdns
   ★ 컨테이너에서는 nscd 없는 경우가 많아 cache miss → DNS 폭주 원인

/etc/hosts (nsswitch.conf hosts: 순서):
   127.0.0.1   localhost
   10.0.0.5    db.internal
   ★ 절대 DNS 안 거치는 정적 override. 개발/디버깅에 유용.
   ★ Kubernetes Pod의 /etc/hosts는 hostAliases로 주입 가능.
```

### 1.4 키워드 2 — stub resolver와 recursive resolver

**stub resolver**: OS 안에 있는 미니 DNS client. `getaddrinfo()` 호출 시 `/etc/resolv.conf`의 `nameserver` 항목을 봐서 거기로 질의를 던지고 응답만 받는다. 스스로 root/TLD를 찾아다니지 않는다.

```
/etc/resolv.conf 예시:
  nameserver 8.8.8.8       ← Google Public DNS
  nameserver 1.1.1.1       ← Cloudflare
  search corp.example.com  ← search domain (CoreDNS 함정 ⑨ 참조)
  options ndots:5 timeout:2 attempts:2
```

**recursive resolver**: 진짜 작업을 하는 쪽. 자기 큰 cache 가지고 있고, miss면 root → TLD → auth를 자기가 다 묻고 답을 stub에 돌려준다. 일반적으로:
- ISP가 운영 (KT/SKB/LGU+ 등)
- Public DNS — Google `8.8.8.8`/`8.8.4.4`, Cloudflare `1.1.1.1`, Quad9 `9.9.9.9`
- 사내 — corporate DNS (회사 내부 도메인 + 외부 forwarding)
- Kubernetes — CoreDNS

### 1.5 키워드 3 — root → TLD → authoritative

```
질의 흐름 (recursive resolver가 cold일 때):

[1] Recursive → Root NS:
    "example.com 의 A 레코드가 뭐야?"
    Root: "나 모름. com TLD NS는 a.gtld-servers.net 등이야"
    (referral: NS + glue A 레코드)

[2] Recursive → com TLD NS:
    "example.com 의 A 레코드?"
    TLD: "나 모름. example.com 의 NS는 ns1.icann-servers.net 등이야"
    (referral)

[3] Recursive → example.com Auth NS:
    "example.com 의 A 레코드?"
    Auth: "93.184.216.34" (final answer, authoritative)

[4] Recursive → stub: "93.184.216.34"
   (Recursive는 결과를 자기 cache에 TTL 만큼 저장)
```

**Glue Record**: TLD가 "example.com NS는 ns1.example.com이야" 라고 답하면 ns1.example.com을 또 찾아야 함 → 무한 루프. 그래서 TLD가 NS 레코드와 함께 그 NS 호스트의 A 레코드도 **같이** 준다. 이게 glue.

**Root server는 13개? 실제로는 수백 대**:
- 이름은 `a.root-servers.net ~ m.~` (13개 letter).
- 각 letter는 **Anycast**로 전세계 여러 곳에 같은 IP를 광고하는 수십~수백 대 cluster (가지 ⑦).
- 가장 가까운 instance가 자동으로 응답.

### 1.6 `dig +trace` 출력 한 줄씩 해설

```bash
$ dig +trace example.com

;; Received 525 bytes from 192.168.1.1#53 in 5 ms       ← [a] local resolver가 root hints 응답

.                       518400  IN      NS      a.root-servers.net.   ← [b] root NS 13개 받음
.                       518400  IN      NS      b.root-servers.net.
... (m까지)
;; Received 239 bytes from 198.41.0.4#53(a.root-servers.net) in 32 ms ← [c] 실제 root에 질의, com NS 응답

com.                    172800  IN      NS      a.gtld-servers.net.   ← [d] com TLD NS 13개
com.                    172800  IN      NS      b.gtld-servers.net.
...
;; Received 836 bytes from 192.5.6.30#53(a.gtld-servers.net) in 50 ms ← [e] com TLD에 질의, example.com NS 응답

example.com.            172800  IN      NS      a.iana-servers.net.   ← [f] example.com 의 권한 NS
example.com.            172800  IN      NS      b.iana-servers.net.
;; Received 119 bytes from 192.41.162.30#53(b.gtld-servers.net) in 80 ms

example.com.            300     IN      A       93.184.216.34         ← [g] ★ 최종 답 (auth NS가 줌)
example.com.            300     IN      RRSIG   A 8 2 300 ...         ← DNSSEC 서명
;; Received 213 bytes from 199.43.135.53#53(a.iana-servers.net) in 100 ms
```

**한 줄씩 해석**:
- `[a]` 너의 local resolver(=recursive)에서 시작. 그가 root hints 파일을 줌.
- `[b]` Root NS 목록 13개. anycast IPv4 + IPv6 모두.
- `[c]` 실제 root에 질의 가서 `com NS 누구야?` → 응답.
- `[d-e]` `.com` TLD NS에 가서 `example.com NS?` → 응답.
- `[f]` example.com auth NS 목록.
- `[g]` auth NS가 진짜 답 `A 93.184.216.34` 줌. **TTL 300초** (5분). 5분 동안 recursive resolver가 cache.

→ 평소엔 recursive에 cache hit이라 [c~f]는 안 일어남. cold start, 즉 첫 질의에서만 일어남.

### 1.7 `dig +trace www.google.com` — 실제 평범한 사이트로 본 풀버전

`example.com`은 RFC 문서용 도메인이라 응답이 정적이다. **실전 면접에서는 `www.google.com`처럼 누구나 아는 도메인**으로 설명하면 즉시 와닿는다.

```bash
$ dig +trace www.google.com
; <<>> DiG 9.16.1 <<>> +trace www.google.com
;; global options: +cmd

# ──────────────────────── [phase 0] local resolver의 root hints ────────────────────────
.                       86400   IN      NS      a.root-servers.net.
.                       86400   IN      NS      b.root-servers.net.
.                       86400   IN      NS      c.root-servers.net.
.                       86400   IN      NS      d.root-servers.net.
.                       86400   IN      NS      e.root-servers.net.
.                       86400   IN      NS      f.root-servers.net.
.                       86400   IN      NS      g.root-servers.net.
.                       86400   IN      NS      h.root-servers.net.
.                       86400   IN      NS      i.root-servers.net.
.                       86400   IN      NS      j.root-servers.net.
.                       86400   IN      NS      k.root-servers.net.
.                       86400   IN      NS      l.root-servers.net.
.                       86400   IN      NS      m.root-servers.net.
;; Received 525 bytes from 192.168.1.1#53(192.168.1.1) in 2 ms

# ──────────────────────── [phase 1] 실제 root에 질의: ".com 누구야?" ────────────────────────
com.                    172800  IN      NS      a.gtld-servers.net.
com.                    172800  IN      NS      b.gtld-servers.net.
com.                    172800  IN      NS      c.gtld-servers.net.
com.                    172800  IN      NS      d.gtld-servers.net.
com.                    172800  IN      NS      e.gtld-servers.net.
com.                    172800  IN      NS      f.gtld-servers.net.
com.                    172800  IN      NS      g.gtld-servers.net.
com.                    172800  IN      NS      h.gtld-servers.net.
com.                    172800  IN      NS      i.gtld-servers.net.
com.                    172800  IN      NS      j.gtld-servers.net.
com.                    172800  IN      NS      k.gtld-servers.net.
com.                    172800  IN      NS      l.gtld-servers.net.
com.                    172800  IN      NS      m.gtld-servers.net.
com.                    86400   IN      DS      30909 8 2 ...      ← DNSSEC chain
com.                    86400   IN      RRSIG   DS 8 1 ...
;; Received 1170 bytes from 198.41.0.4#53(a.root-servers.net) in 50 ms

# ──────────────────────── [phase 2] .com TLD에 질의: "google.com 누구야?" ────────────────────────
google.com.             172800  IN      NS      ns1.google.com.
google.com.             172800  IN      NS      ns2.google.com.
google.com.             172800  IN      NS      ns3.google.com.
google.com.             172800  IN      NS      ns4.google.com.
ns1.google.com.         172800  IN      A       216.239.32.10        ← ★ glue record!
ns2.google.com.         172800  IN      A       216.239.34.10
ns3.google.com.         172800  IN      A       216.239.36.10
ns4.google.com.         172800  IN      A       216.239.38.10
;; Received 663 bytes from 192.5.6.30#53(a.gtld-servers.net) in 12 ms

# ──────────────────────── [phase 3] google.com auth NS에 질의: "www.google.com A?" ────────────────────────
www.google.com.         300     IN      A       142.250.196.132      ★ FINAL ANSWER
;; Received 60 bytes from 216.239.32.10#53(ns1.google.com) in 8 ms
```

**한 줄씩 해설**:

```
[phase 0] local resolver(192.168.1.1)가 자기 root hints 파일에서 13개 root NS 목록 응답
   ─ 이건 dig가 "trace 모드 시작점을 어디에 잡을지" 알려고 받는 정보일 뿐
   ─ 실제 query는 다음 phase부터

[phase 1] a.root-servers.net(198.41.0.4)에 query → "com NS?"
   ─ .com 의 NS 13개 (Verisign이 운영)
   ─ DS 레코드 = .com 의 DNSSEC delegation signer (chain of trust)
   ─ TTL 172800s = 2일 → recursive resolver는 .com NS를 2일간 캐시

[phase 2] a.gtld-servers.net(192.5.6.30)에 query → "google.com NS?"
   ─ google.com 의 권한 NS 4개 (ns1~ns4.google.com)
   ─ ★ glue record (ns1.google.com A 216.239.32.10)
       → ns1.google.com 자체가 google.com 의 권한 NS이므로 순환 의존
       → TLD가 glue로 IP를 같이 줘서 부트스트랩 가능

[phase 3] ns1.google.com(216.239.32.10)에 query → "www.google.com A?"
   ─ ★ 진짜 답: 142.250.196.132
   ─ TTL 300s = 5분 → recursive resolver는 5분간 이 답을 캐시
   ─ 60 byte 응답 — UDP 512B 한참 아래 (단순 A 레코드는 짧음)
```

**왜 응답에 IP가 여러 개 안 나오나**: `dig`는 보통 첫 번째 A만 표시 + round-robin이라 시점마다 다른 IP. `dig +short www.google.com`를 여러 번 치면 다른 IP가 나옴.

```bash
$ for i in 1 2 3 4 5; do dig +short www.google.com | head -1; done
142.250.196.132
142.250.207.4
172.217.31.164
142.250.66.36
216.58.220.36
```

→ 같은 hostname에 **여러 A 레코드** + auth NS가 round-robin → 클라이언트마다 다른 IP. 단, 이건 부하 분산 효과가 약함. 실제로는 위에서 본 **anycast**가 진짜 분산 메커니즘.

**`dig +trace`의 함정**:
- `dig +trace`는 **재귀를 stub이 직접 흉내내는 모드**. 즉, dig가 root → TLD → auth를 직접 묻는다 (`RD=0`).
- 평소 어플리케이션의 DNS query는 stub이 recursive에 한 번 던지고 답 받는 게 끝. 이 단계들은 recursive 내부에서 일어남.
- 그래서 `+trace` 결과는 "교과서 본"이고, 실제 성능은 recursive cache 상태에 좌우.

**시니어 운영 관점**:
- 신규 도메인 등록 직후 "propagation 안 됐다"는 사용자 불만 → `dig +trace your-domain.com` 으로 phase 1(TLD에 NS 등록) / phase 2(auth NS가 응답) 어디서 끊기는지 확인.
- `dig @8.8.8.8 www.google.com` (특정 resolver 지정) vs `dig www.google.com` (시스템 기본) 결과가 다르면 사내 resolver cache 또는 split-horizon DNS 의심.

---

## 2. 가지 ②: DNS 레코드 종류

### 2.1 핵심 질문

> "A, AAAA, CNAME 말고 어떤 레코드들이 있고 각각 언제 쓰나요?"

### 2.2 주요 레코드 한 표

| 레코드 | 용도 | 예 |
|---|---|---|
| **A** | host → IPv4 | `example.com A 93.184.216.34` |
| **AAAA** | host → IPv6 | `example.com AAAA 2606:2800:220:1::` |
| **CNAME** | host → alias hostname | `www.example.com CNAME example.com` |
| **ALIAS / ANAME** | apex CNAME 대체 (vendor 비표준) | `example.com ALIAS lb.aws.com` |
| **NS** | 도메인의 권한 NS | `example.com NS ns1.iana-servers.net` |
| **SOA** | zone의 권한 / 갱신 정책 | `example.com SOA ns.. admin.. <serial> <refresh> <retry> <expire> <minimum>` |
| **MX** | 메일 라우팅 (priority + host) | `example.com MX 10 mail.example.com` |
| **TXT** | 자유 텍스트 (SPF/DKIM/도메인 verification) | `example.com TXT "v=spf1 include:_spf.google.com ~all"` |
| **SRV** | service+protocol → host:port | `_sip._tcp.example.com SRV 0 5 5060 sipserver.example.com` |
| **CAA** | 어느 CA만 발급 허용 | `example.com CAA 0 issue "letsencrypt.org"` |
| **PTR** | 역방향 (IP → host) | `34.216.184.93.in-addr.arpa PTR example.com` |
| **DNSKEY/DS/RRSIG/NSEC** | DNSSEC | (서명 chain) |
| **HTTPS / SVCB** (RFC 9460) | HTTP 서비스 메타 (ALPN, ECH, ipv4hint) | `example.com HTTPS 1 . alpn=h2,h3 ipv4hint=...` |

### 2.3 CNAME vs ALIAS — apex 함정

**CNAME 규칙**: "이 호스트는 다른 호스트로 가라". 그런데 RFC상 **CNAME과 다른 레코드 공존 불가**. 그래서:

```
❌ 불가:
   example.com  CNAME  cdn.cloudfront.net
   example.com  MX     mail.example.com     ← apex에 다른 레코드가 이미 있으면 CNAME 불가
   example.com  NS     ns1.example.com       ← (NS는 apex에 무조건 있어야 함)

✅ www는 가능:
   www.example.com  CNAME  cdn.cloudfront.net
```

**해결**: AWS Route53의 **ALIAS**, Cloudflare의 **CNAME flattening** — DNS 응답을 만들 때 NS가 CNAME 따라가서 **A 레코드로 평탄화**해서 응답. 사용자 입장에선 `example.com A 1.2.3.4`로 보임.

→ apex(`example.com`)를 CDN/LB에 연결할 때 항상 부딪히는 함정. 모르면 `MX와 CNAME 충돌` 또는 `route53 only` 같은 디버깅 지옥.

### 2.4 SRV — service discovery의 시초

```
_sip._tcp.example.com  SRV  0 5 5060 sipserver.example.com.
                            ↑ priority (낮을수록 우선)
                              ↑ weight (같은 priority 안에서 가중치)
                                ↑ port
                                     ↑ target host
```

- SIP, XMPP, Kerberos 같은 multi-instance 서비스 discovery에 사용.
- Consul/etcd 시대 전의 service discovery.
- HTTP는 SRV 미지원 → 그래서 HTTPS 레코드(RFC 9460)가 등장.

### 2.5 CAA — 발급 가능 CA 제한 (보안)

```
example.com  CAA  0 issue "letsencrypt.org"
example.com  CAA  0 issuewild ";"    ← wildcard 금지
example.com  CAA  0 iodef "mailto:security@example.com"
```

- CA가 인증서 발급 전 CAA 검사 의무 (CA/Browser Forum 규약).
- 잘못된 CA가 임의로 발급하지 못하게 함.

### 2.6 SOA — 권한 / TTL의 출발

```
example.com  SOA  ns1.example.com. admin.example.com. (
                  2024010101  ; serial — zone 변경 카운터
                  3600        ; refresh — secondary가 primary 확인 주기
                  600         ; retry — refresh 실패 시 재시도 주기
                  604800      ; expire — secondary가 응답 못해도 살아있다 인정 기간
                  300 )       ; minimum — ★ negative caching TTL
```

`minimum`이 **negative caching TTL**의 출처 (가지 ③).

---

## 3. 가지 ③: DNS 캐싱과 TTL

### 3.1 핵심 질문

> "TTL을 너무 짧게/길게 잡으면 뭐가 안 좋나요? Negative caching이 뭐고 왜 중요한가요?"

### 3.2 키워드 1 — Positive TTL

```
   ┌──────────────────────┐
   │ Recursive Resolver    │
   │ cache:                │
   │  example.com → ...    │  ← TTL 300초 카운트 다운
   │  TTL: 245s            │
   └──────────────────────┘
```

- TTL이 살아있는 동안 같은 hostname 질의는 **cache hit** → 즉시 응답.
- TTL=0 또는 expired면 다시 root→TLD→auth 거침.

**짧게 (TTL 30s) vs 길게 (TTL 86400s = 1day)**:

| 짧게 | 길게 |
|---|---|
| failover 빠름 (IP 변경 즉시 전파) | failover 느림 (전세계 cache 갱신 대기) |
| auth NS 부하 ↑ | auth NS 부하 ↓ |
| DDoS 시 auth가 SPOF | resolver cache가 흡수 |
| latency P99 약간 ↑ (cache miss 잦음) | latency 안정 |
| **CDN/blue-green 배포에 유리** | **고정 IP 서비스에 유리** |

→ 실무 경험칙: 정적 자원은 1day, 동적/failover IP는 60s, blue-green/canary는 30s.

### 3.3 키워드 2 — Negative caching (NXDOMAIN, NODATA)

**NXDOMAIN**: 도메인 존재 안 함. **NODATA**: 도메인은 존재하나 그 레코드 타입 없음 (예: `example.com AAAA`인데 IPv6 없음).

→ 이 부정 응답도 **cache 되어야** 한다. 안 그러면 같은 잘못된 질의가 매번 root까지 감.

```
SOA의 minimum 필드가 negative caching TTL (RFC 2308)
example.com SOA ... 300   ← NXDOMAIN/NODATA 300초 cache
```

**실무 함정 (CoreDNS NXDOMAIN 폭증)**: 가지 ⑨에서 자세히. `search` 도메인 5개 × IPv4/IPv6 = 10번 NXDOMAIN 시도 → recursive resolver/auth NS 부하 폭증.

### 3.4 키워드 3 — DNS poisoning, Kaminsky 공격, DNSSEC

**DNS poisoning (cache poisoning)**: 공격자가 recursive resolver의 cache에 **가짜 응답**을 심는다. 그 후 그 resolver를 쓰는 모든 사용자가 가짜 IP로 감.

**Kaminsky 공격 (2008)**:
- DNS 응답에는 **16-bit Transaction ID + UDP source port**가 매칭되어야 한다.
- 옛 구현은 source port 고정(53) → TID만 16-bit = 65536개 → 공격자가 폭격해서 맞춤.
- Dan Kaminsky가 추가로 발견: 임의 subdomain (`random123.example.com`)에 대해 NS 레코드를 위조하면 `example.com` 전체를 위조 가능.

**대책**:
1. **Source port randomization** — 응답 매칭에 source port도 16-bit 엔트로피 추가 → 32-bit 공간.
2. **0x20 encoding** — query name을 random하게 대소문자 섞어 보냄 (`ExAmPlE.cOm`). 응답이 같은 대소문자로 와야 인정.
3. **DNSSEC** — 응답에 **암호 서명**. Root → TLD → auth가 chain of trust.

**DNSSEC chain**:
```
.       DNSKEY → Root의 공개키 (DS는 신뢰점 root anchor)
        DS      → "com TLD의 DNSKEY 해시는 이거"
com.    DNSKEY → com의 공개키
        DS      → "example.com 의 DNSKEY 해시는 이거"
example.com.  DNSKEY → example.com 의 공개키
              RRSIG   → "A 레코드는 이 서명으로 검증해라"
              A       → 93.184.216.34
```

→ resolver가 위에서부터 chain을 검증. 한 단계라도 서명 실패면 SERVFAIL.

**현실**: DNSSEC 채택률이 아직 낮음 (TLD 별로 다름). DoT/DoH가 더 빠르게 보급 — 채널 자체를 암호화.

---

## 4. 가지 ④: DNS의 진화 — UDP에서 DoH까지

### 4.1 핵심 질문

> "DNS는 왜 UDP를 쓰나요? 그런데 DoH는 왜 또 HTTPS 위에서 도나요?"

### 4.2 키워드 1 — DNS over UDP 53 + 512B 제한

```
        Client                            Resolver
          │                                  │
          │  UDP src=49152 dst=53            │
          │ ───────────────────────────────► │
          │  [DNS query: example.com A]      │
          │                                  │
          │     UDP src=53 dst=49152         │
          │ ◄─────────────────────────────── │
          │  [DNS response: A 93.184.216.34] │
```

**왜 UDP?**
- 1980년대 설계: query/response 한 왕복 → connection 셋업 비용 없는 UDP가 적합.
- 한 패킷에 다 들어가면 TCP 3-way handshake보다 빠름.

**512 byte 제한**: 원래 DNS 메시지는 UDP **512 byte 이하**. 이걸 넘으면 truncated (TC) flag set → 클라가 TCP로 재시도.

**왜 512?**: 인터넷 초기 MTU 안전 마진. IPv4 기본 datagram 최소 보장(576) - IP header(20) - UDP header(8) ≈ 512.

### 4.3 키워드 2 — EDNS0 + TCP fallback

**문제**: 현대 DNS는 메시지가 커짐 (DNSSEC 서명, multi-A, AAAA, EDNS Client Subnet, ...). 512로 한참 부족.

**EDNS0 (RFC 6891)**: query에 OPT pseudo-record를 붙여 "내 UDP 응답 받을 수 있는 최대 크기는 4096 byte야" 알림. resolver가 그만큼 응답 가능.

```
OPT pseudo-record:
  ...
  Class: 4096       ← UDP payload size
  ...
```

**TCP fallback**: 그래도 부족하면 (또는 EDNS0 미지원이면) UDP 응답에 TC=1 → 클라가 동일 query를 **TCP 53**으로 재시도.

**TCP DNS의 다른 용도**: **Zone transfer (AXFR/IXFR)** — secondary NS가 primary로부터 zone 전체 복사. 큰 데이터라 무조건 TCP.

### 4.4 키워드 3 — DoT (853) / DoH (443) / DoQ (QUIC)

**왜 등장**:
1. **프라이버시**: UDP 53은 평문 → ISP/공격자/정부가 어떤 도메인 묻는지 다 봄.
2. **무결성**: 평문이라 MITM이 응답 위조 가능. DNSSEC은 데이터 무결성만, 채널 자체는 평문.
3. **검열 회피**: 일부 국가에서 특정 hostname 응답을 막거나 위조.

| 프로토콜 | 포트 | 특징 |
|---|---|---|
| **DoT** (DNS over TLS, RFC 7858) | 853/TCP | TLS 위 DNS. 별도 포트라 식별 가능. |
| **DoH** (DNS over HTTPS, RFC 8484) | 443/TCP | HTTPS 위 DNS. 일반 HTTPS와 구별 불가 → 검열 회피 강. |
| **DoQ** (DNS over QUIC, RFC 9250) | 853/UDP | QUIC 위 DNS. 0-RTT, 빠름. |

**현실**: Firefox/Chrome이 기본 DoH 활성화 가능 (Cloudflare/Google으로). 회사 내부 DNS와 충돌하면 사내 hostname을 못 풀어 사고. **enterprise 환경에선 DoH 비활성화 정책** 흔함.

### 4.5 진화 타임라인

```
1983  RFC 882/883 — DNS 최초 명세
1987  RFC 1034/1035 — DNS 정착 (UDP 53, 512B)
1997  RFC 2065 — DNSSEC 초안
1999  RFC 2671 — EDNS0
2005  RFC 4033~4035 — DNSSEC 재정비
2008  Kaminsky 공격 — source port randomization 권고
2010  Root zone DNSSEC 서명 시작
2016  RFC 7858 — DoT
2018  RFC 8484 — DoH
2020  RFC 8806 — root on loopback (local root mirror)
2022  RFC 9250 — DoQ
2023  RFC 9460 — HTTPS/SVCB record (ALPN, ECH 힌트)
```

---

## 5. 가지 ⑤: GeoDNS / Latency / Weighted DNS

### 5.1 핵심 질문

> "Route53/Cloudflare는 어떻게 사용자에게 가까운 region IP를 돌려주나요?"

### 5.2 같은 질문에 다른 답 — DNS의 동적 응답

전통적 DNS는 정적: `example.com A 1.2.3.4`. 한 zone에 한 답.

GeoDNS는 동적: **누가 묻느냐**에 따라 다른 응답.

```
Resolver (서울)              Auth NS (Route53 GeoDNS)
   │                          │
   │ example.com A?           │
   │ src IP: 1.2.3.4 (KR ISP) │
   │ ──────────────────────► │
   │                          │  IP geo lookup → 사용자 = 한국
   │                          │  → ap-northeast-2 region IP 응답
   │ ◄──────────────────────  │
   │ example.com A 13.124.x.x │  (Seoul region ELB)


Resolver (뉴욕)              같은 Auth NS
   │ example.com A?           │
   │ src IP: 5.6.7.8 (US ISP) │
   │ ──────────────────────► │
   │                          │  사용자 = 미국 동부
   │                          │  → us-east-1 region IP 응답
   │ ◄──────────────────────  │
   │ example.com A 3.215.x.x  │  (N.Virginia ELB)
```

### 5.3 GeoDNS 동작 — 무엇으로 위치를 판단하나

기본은 **resolver의 source IP**. 그런데 이건 함정 — resolver는 사용자가 아닐 수 있음.
- 사용자: 서울 ISP
- 사용자가 쓰는 resolver: Google DNS `8.8.8.8` (anycast로 가까운 곳에서 응답하지만 Google 입장)
- Auth NS 입장에서 src IP = Google DNS의 outbound IP

**해결: EDNS Client Subnet (ECS, RFC 7871)**
- recursive resolver가 auth NS에 query 보낼 때 사용자의 **subnet 일부** (예: /24)를 query에 포함.
- Auth NS는 그 subnet으로 GeoDNS 판단.
- 프라이버시 vs 정확도 trade-off — 일부 resolver(Cloudflare 1.1.1.1)는 ECS 의도적 안 보냄.

### 5.4 Latency-based vs GeoDNS

| 방식 | 판단 기준 | 장점 | 단점 |
|---|---|---|---|
| **GeoDNS** | IP geolocation DB | 단순, 예측 가능 | DB 부정확 가능, latency ≠ 지리 |
| **Latency-based** (Route53) | 실측 RTT 데이터 | 진짜 빠른 곳 선택 | DB 학습 필요, 변동 |
| **Weighted** | 미리 설정한 % | A/B test, blue-green | 사용자 경험 무관 |
| **Failover** | health check 기반 | 자동 failover | TTL이 짧아야 효과 |
| **Geo-proximity** (Route53) | 지리적 거리 + bias 조정 | 지역 영향력 조정 | 설정 복잡 |

### 5.5 Anycast vs GeoDNS — 자주 헷갈리는 비교

```
GeoDNS:
   다른 region = 다른 IP
   "사용자야 너는 IP를 1.2.3.4 받아. 다른 사용자는 5.6.7.8"

Anycast:
   다른 region = 같은 IP, BGP가 가까운 노드로 라우팅
   "모두 1.1.1.1로 가. BGP가 알아서 가까운 PoP으로 보내줘"
```

→ Cloudflare/Google DNS는 **anycast** (모두 `1.1.1.1`/`8.8.8.8` 같은 IP). AWS S3는 **GeoDNS** + region별 endpoint. CDN은 흔히 **둘 다** — DNS로 region 선택(GeoDNS) + region 안에서 anycast로 PoP 선택.

자세한 anycast는 가지 ⑦.

---

## 6. 가지 ⑥: IP 라우팅 — 패킷이 인터넷을 가로지르는 길

### 6.1 핵심 질문

> "내 노트북에서 93.184.216.34로 보낸 패킷은 어떻게 그 서버까지 도달하나요?"

### 6.2 백지에 그리는 라우팅 큰 그림

```
[내 노트북]
   │ dst=93.184.216.34
   │
   ▼ ① 호스트 라우팅 테이블 lookup
   "이 IP는 내 subnet(192.168.1.0/24)에 없네 → default gateway 192.168.1.1로"
   │
   │ ② ARP로 192.168.1.1의 MAC 알아내기 (L2)
   │
   ▼ L2 frame on Wi-Fi
[홈 라우터]                 ── NAT (private 192.168.1.10 → public 121.x.x.x)
   │
   ▼
[ISP edge router (KT/SKB/LGU+)]
   │ BGP table 봄: "93.184.216.0/24 → AS15133(Edgecast)로 가려면..."
   │ best path: AS_PATH = [3786(KT)→7018(AT&T)→15133]
   ▼
[Tier 1 ISP backbone]       ── 광역 라우팅 (해저 케이블, IXP)
   │ AS hop 여러 번
   ▼
[목적 AS의 edge router (Edgecast/CDN provider)]
   │
   ▼ subnet 내부 라우팅 (L3 → L2)
[목적 서버 93.184.216.34]
```

### 6.3 키워드 1 — 호스트 라우팅 테이블

```bash
$ ip route show                       # Linux
default via 192.168.1.1 dev wlan0     ← ★ 모든 외부 IP는 여기로
192.168.1.0/24 dev wlan0              ← 내 LAN은 직접
169.254.0.0/16 dev wlan0              ← link-local

$ netstat -rn                         # macOS/Linux
Destination     Gateway         Flags
default         192.168.1.1     UGSc        ← default route
192.168.1/24    link#11         UCS
```

**규칙**: 패킷의 dst IP가 어느 entry에 가장 길게 매칭(longest prefix match)되는지로 next hop 결정. 매칭 없으면 default.

**예**:
- dst = 192.168.1.50 → 192.168.1.0/24에 매칭 → 직접 (gateway 안 거침)
- dst = 8.8.8.8 → default → 192.168.1.1로 보냄

### 6.4 키워드 2 — 기본 게이트웨이 → ISP → Tier 1 → Backbone

```
[Home LAN]                    192.168.1.0/24 (private)
   │ NAT
[Home router]                 121.x.x.x (public, dynamic from ISP)
   │
[ISP local PoP]               KT/SKB/LGU+ 서울 지역 라우터
   │
[ISP regional]                광역
   │
[ISP national backbone]       국가 backbone (서울-부산 광케이블)
   │
[IXP — Internet Exchange]     KINX, AMS-IX, DE-CIX 등 ISP들이 만나는 곳
   │
[Tier 1 ISP]                  AT&T, NTT, Telia 등 — 전 세계 IP 다 도달 가능
   │
[Submarine cable]             태평양/대서양 해저 광케이블
   │
[Destination Tier 1]
   │
[Destination ISP]
   │
[Destination edge router]
```

**Tier 분류**:
- **Tier 1**: 전세계 모든 IP에 transit 없이 도달 가능 (peering만으로). 약 20개사.
- **Tier 2**: 일부 지역은 peering, 일부는 Tier 1에 돈 내고 transit 구매. 대부분 ISP가 여기.
- **Tier 3**: 거의 모든 트래픽이 transit 구매.

**IXP (Internet Exchange Point)**: 여러 ISP가 한 곳에 모여 직접 peering. 비용 절감 + 지역 트래픽 ISP 안 거치고 직통. 한국 KINX, 일본 JPIX, 네덜란드 AMS-IX 등.

### 6.5 키워드 3 — BGP의 AS_PATH 선택 규칙

**AS (Autonomous System)**: 단일 정책으로 운영되는 라우팅 도메인. ISP, 큰 회사, CDN 등이 각자 AS 번호 보유 (예: AS15169 = Google, AS32934 = Facebook, AS9318 = SKB).

**BGP (Border Gateway Protocol)**: AS들 간의 라우팅 정보 교환 프로토콜. 인터넷의 "고속도로 표지판".

```
BGP advertisement 예:
"내가 (AS15133) 93.184.216.0/24 를 announce함"
   │
이걸 받은 AS들이 자기 BGP table에 기록:
   "93.184.216.0/24 → next hop AS15133, AS_PATH=[15133]"
   │
다른 AS에 광고할 때 자기 AS 번호 prepend:
   "93.184.216.0/24 → AS_PATH=[7018, 15133]"
```

**Best path 선택 규칙 (요약)**:
1. **Local preference** 가장 높은 것 (자기 AS 정책 우선)
2. **AS_PATH 짧은 것** (hop 수 적은 경로)
3. **Origin type** (IGP > EGP > Incomplete)
4. **MED** (multi-exit discriminator)
5. **eBGP > iBGP**
6. **IGP metric** 낮은 것
7. **Router ID** 낮은 것 (tie breaker)

→ AS_PATH 짧은 게 보통 빠르지만, **traffic engineering**으로 일부러 AS prepend (`AS_PATH=[7018,7018,7018,15133]`)해서 경로 회피 유도하기도.

**looking glass** — 공개 BGP 라우터 (KT, NTT, RIPE, Hurricane Electric 등)에서 그 시점의 AS_PATH 조회 가능:
- https://lg.he.net/ (Hurricane Electric)
- https://lg.ntt.net/
- https://bgp.he.net/ip/93.184.216.34

**BGP 사고 사례**:
- 2008년 Pakistan Telecom이 YouTube를 차단하려고 자기 AS 안에서 YouTube IP를 hijack — BGP가 전세계로 새서 YouTube가 전세계 다운.
- 2021년 Facebook 6시간 다운 — BGP 설정 오류로 자기 AS를 인터넷에서 withdraw.
- 2024년 Cloudflare AS_PATH 누수 — 일부 지역 latency spike.

### 6.6 L3 라우팅과 L2 스위칭 — ARP, subnet, NAT

같은 subnet 안에서는 **L2 (Ethernet)**, subnet 넘어가면 **L3 (IP)**.

**ARP (Address Resolution Protocol)**: "이 IP의 MAC 주소가 뭐야?" 브로드캐스트.

```
host A (192.168.1.10) wants to send to 192.168.1.50:
   1. Routing table → 192.168.1.0/24, 같은 subnet, 직접 보냄
   2. ARP table 확인 → 192.168.1.50 MAC 모름
   3. ARP request 브로드캐스트: "who has 192.168.1.50? tell 192.168.1.10"
   4. host B (192.168.1.50)이 응답: "192.168.1.50 is at aa:bb:cc:dd:ee:ff"
   5. ARP cache 채움, 그 MAC으로 Ethernet frame 보냄
```

→ subnet 넘어가면 dst MAC = **default gateway의 MAC**으로 보냄. gateway가 IP는 그대로 두고 새 L2 frame으로 next hop으로 forward.

#### 6.6.1 ARP와 MAC 주소 — DNS 다음에 진짜로 일어나는 일

> DNS는 hostname을 IP로 바꿔주지만, **IP만 가지고는 frame을 보낼 수 없다**. Ethernet은 L2이고, L2는 MAC 주소로만 frame을 forwards한다. 그래서 IP가 결정된 직후에는 **ARP**가 반드시 끼어든다.

**핵심 한 문장**: ARP는 "이 IP의 next-hop MAC을 알려줘"를 같은 subnet에 브로드캐스트로 묻고, 그 IP를 가진 호스트가 자기 MAC을 응답하는 프로토콜. **RFC 826 (1982)**, 인터넷보다 오래된 프로토콜이 지금도 그대로 살아있다.

**왜 IP만으로는 안 되나**:

```
[IP packet — L3]
   src IP: 192.168.1.10
   dst IP: 142.250.196.132 (www.google.com)
        │
        │ "이걸 wire에 어떻게 실을까?"
        ▼
[Ethernet frame — L2]
   src MAC: aa:aa:aa:aa:aa:aa   ← 내 NIC MAC (커널이 앎)
   dst MAC: ??:??:??:??:??:??   ← ★ 모름! ARP 필요
   ─────────
   payload: 위 IP packet
```

**ARP 흐름 — 같은 subnet 케이스**:

```
[host A 192.168.1.10, mac aa:aa:..]              [host B 192.168.1.50, mac cc:cc:..]
   │
   │ ARP request (broadcast):
   │   Ethernet dst = ff:ff:ff:ff:ff:ff
   │   "Who has 192.168.1.50? Tell 192.168.1.10"
   │
   ├──────────── 모든 L2 호스트에게 ─────────────▶
   │                                                │
   │                                                │ "그거 나야"
   │                                                │
   │  ARP reply (unicast to A):                     │
   │   "192.168.1.50 is at cc:cc:.."                │
   │ ◀───────────────────────────────────────────── │
   │
   ▼
[A의 ARP cache]
   192.168.1.50 → cc:cc:..  (TTL 보통 60s ~ 4분)
   │
   ▼
[Ethernet frame로 송신]
   src MAC: aa:aa:..,  dst MAC: cc:cc:..
```

**ARP 흐름 — 다른 subnet (대부분의 인터넷 통신)**:

```
[host A 192.168.1.10]            [Gateway 192.168.1.1, mac bb:bb:..]      [Internet]
   │
   │ routing table 결과: default → 192.168.1.1
   │
   │ ARP: "192.168.1.1 의 MAC?"
   │ ─────────▶ (broadcast)
   │
   │  reply: "bb:bb:.."
   │ ◀──────────
   │
   ▼
[Ethernet frame]
   src MAC: aa:aa:..   (A)
   dst MAC: bb:bb:..   (★ gateway MAC, 142.250.196.132이 아닌)
   src IP:  192.168.1.10
   dst IP:  142.250.196.132   (그대로!)
        │
        ▼
[Gateway 도착]
   IP packet 은 그대로 두고, Ethernet frame만 새로 만듦:
   src MAC: bb:bb:..  (자기)
   dst MAC: ??         ← 다음 hop의 MAC, ARP 또는 미리 알고 있음
   → 다음 라우터로 forward
```

★ **핵심**: hop마다 **L2 frame은 새로 만들어지지만 L3 IP header는 그대로**. dst MAC은 next-hop만 가리키고, dst IP는 최종 목적지를 가리킴.

#### 6.6.2 ARP cache — 보관, 만료, 진단

**확인**:
```bash
# Linux
$ ip neigh show
192.168.1.1 dev wlan0 lladdr bb:bb:bb:bb:bb:bb REACHABLE
192.168.1.50 dev wlan0 lladdr cc:cc:cc:cc:cc:cc STALE

# macOS / BSD
$ arp -a
? (192.168.1.1) at bb:bb:bb:bb:bb:bb on en0 ifscope [ethernet]

# Windows
> arp -a
```

**상태**:
- `REACHABLE`: 최근 통신 성공 + 응답 받음 — 신뢰 가능.
- `STALE`: 시간 경과로 의심스러움 — 다음 통신 시 재검증.
- `INCOMPLETE`: ARP request 보냈는데 응답 없음 — 호스트 죽었거나 망 단절.
- `FAILED`: 재시도 실패 — drop.

**TTL/aging**:
- Linux 기본 ARP cache 보관: 활성 entry는 60초 정도, idle entry는 수 분 후 expire.
- `/proc/sys/net/ipv4/neigh/default/gc_stale_time` 등으로 조정.
- 너무 짧으면 ARP 폭주, 너무 길면 토폴로지 변화 반영 늦음.

**flush**:
```bash
# Linux
$ sudo ip -s -s neigh flush all

# macOS
$ sudo arp -ad
```

#### 6.6.3 ARP가 동작하는 OSI 위치 — L2와 L3 사이 (RFC 826)

```
   ┌──────────────────────────────┐
   │ L7  application               │
   │ L6  presentation              │
   │ L5  session                   │
   │ L4  transport                 │
   ├──────────────────────────────┤
   │ L3  network (IP)              │  "이 IP로 보내고 싶다"
   ├═══════════════════════════════┤
   │ ★ ARP                         │  "그 IP의 MAC을 알려줘"  ← 어디에도 명확히 안 속함
   ├═══════════════════════════════┤
   │ L2  data link (Ethernet)      │  "이 MAC으로 frame 보냄"
   │ L1  physical                  │
   └──────────────────────────────┘
```

**ARP 패킷 자체는 Ethernet payload (EtherType=0x0806)**라서 L2 위에 직접 얹힘. IP 위에서 동작하는 ICMP/UDP/TCP와 달리 IP가 필요 없음. 그래서 엄밀히는 "L2.5" 또는 "L3와 L2를 잇는 helper"로 부른다.

#### 6.6.4 ARP spoofing 공격과 방어

```
정상:
   host A → "192.168.1.1 의 MAC?" ──▶ broadcast
                                       ◀── Gateway: "bb:bb:.."
   host A → 그 MAC으로 frame 송신

공격:
   attacker M (192.168.1.99) → broadcast로 거짓 광고:
       "192.168.1.1 is at MM:MM:.."  (자기 MAC을 광고)
       "192.168.1.10 is at MM:MM:.."  (gateway에게도 자기를 A로 광고)
   ↓
   A의 ARP cache: 192.168.1.1 → MM:MM:..
   Gateway의 ARP cache: 192.168.1.10 → MM:MM:..
   ↓
   A ↔ Gateway 사이의 모든 트래픽이 M을 경유 (MITM 성립)
```

**방어**:
- **DAI (Dynamic ARP Inspection)** — 사내 스위치 기능. DHCP snooping table과 매칭 안 되는 ARP를 drop.
- **Static ARP** — 중요한 IP(서버, gateway)는 호스트에 static 매핑.
- **사용자 PC 격리** — VLAN 분리, port-security, 802.1X.
- **암호화 의존** — TLS/IPsec이 있으면 패킷 가로채도 평문은 못 봄.

#### 6.6.5 IPv6의 NDP — ARP의 대체

IPv6는 ARP 없음. 대신 **NDP (Neighbor Discovery Protocol, RFC 4861)** — ICMPv6 위에서 동작 (L3). ARP request/reply 대신 Neighbor Solicitation/Advertisement를 **multicast** (solicited-node multicast)로 주고받음 → broadcast 부담 없음. 라우터도 Router Advertisement로 자기 존재 알림 → DHCP 없어도 SLAAC 자동 설정. 보안은 SEND(RFC 3971) 대신 스위치의 RA Guard/DHCPv6 snooping에 의존.

#### 6.6.6 GARP, Proxy ARP, ARP storm — 특수 케이스 짧게

- **Gratuitous ARP (GARP)**: 묻지 않았는데 자기 IP→MAC을 broadcast로 알림. IP 충돌 감지 + HA failover 시 active 교체 후 ARP cache 즉시 갱신 (VRRP, keepalived의 핵심).
- **Proxy ARP**: 라우터가 자기 subnet 너머 IP에 대해 자기 MAC 응답. 옛 NAT/special routing. 현재 거의 안 쓰임.
- **ARP storm**: 잘못된 설정 또는 broadcast 폭주로 ARP가 폭발 → 큰 broadcast domain일수록 위험 → subnet 분할의 이유.

**CIDR (Classless Inter-Domain Routing)**: `192.168.1.0/24` 표기. `/24`는 앞 24비트가 네트워크, 나머지 8비트가 host. `/24`면 256개 IP (broadcast 등 제외 254 usable).

**NAT (Network Address Translation)**:

| 종류 | 동작 |
|---|---|
| **SNAT** (Source NAT) | 송신 시 src IP를 바꿈 (private → public). 홈 라우터의 일반적 NAT. |
| **DNAT** (Destination NAT) | 수신 시 dst IP를 바꿈. port forwarding, LB에서 사용. |
| **PAT** (Port Address Translation, NAPT) | port까지 매핑. 한 public IP로 수많은 private host 공유. 흔히 "NAT"라고 부르는 게 이것. |

```
SNAT 예 (홈 라우터):
   내부:   src=192.168.1.10:54321  dst=93.184.216.34:443
   외부:   src=121.x.x.x:39817     dst=93.184.216.34:443
                ↑ public IP        ↑ random port

   응답 수신 시 dst=121.x.x.x:39817 → NAT table 보고 → 192.168.1.10:54321로 변환
```

**NAT의 부작용 (운영 관점)**:
- E2E 연결성 깨짐 (외부에서 직접 못 들어옴)
- NAT table size 한계 → connection 수 제한
- idle timeout (보통 5분) → keepalive 안 보내면 NAT가 entry 버림 → 다음 패킷 RST
- IPv4 고갈 문제의 임시 처방. IPv6는 NAT 불필요.

---

## 7. 가지 ⑦: Anycast & ECMP — 같은 IP가 여러 곳에 있는 마법

### 7.1 핵심 질문

> "`8.8.8.8`은 어떻게 전세계에서 가까운 노드로 가나요? L4 LB가 어떻게 ECMP로 분산하나요?"

### 7.2 Anycast — 같은 IP를 여러 위치에서 BGP로 광고

```
[서울 사용자]                              [뉴욕 사용자]
   │                                          │
   │  dst=1.1.1.1                             │  dst=1.1.1.1
   │                                          │
   ▼                                          ▼
[KT BGP table]                          [Verizon BGP table]
"1.1.1.0/24 → AS13335                   "1.1.1.0/24 → AS13335
  AS_PATH=[KT, ..., Cloudflare]            AS_PATH=[Verizon, ..., Cloudflare]
  next hop: 서울 PoP"                       next hop: 뉴욕 PoP"
   │                                          │
   ▼                                          ▼
[Cloudflare 서울 PoP]                  [Cloudflare 뉴욕 PoP]
  실제로 같은 IP 1.1.1.1                 같은 IP 1.1.1.1
  다른 물리 서버                          다른 물리 서버
```

**핵심 메커니즘**: 같은 IP prefix를 전세계 수십~수백 PoP에서 **동시에 BGP로 광고**. 각 ISP의 BGP가 "가장 가까운(짧은 AS path)" 경로 선택 → 사용자는 자기 지역 PoP에 자동 도달.

**누가 쓰나**:
- DNS — Google `8.8.8.8`, Cloudflare `1.1.1.1`, Quad9 `9.9.9.9`
- CDN — Cloudflare, Fastly, Akamai (PoP IP들)
- DDoS 흡수 — 공격을 전세계 PoP에 분산
- Root NS — 13개 letter의 anycast cluster

**Failover**: PoP이 장애나면 그 PoP의 라우터가 **BGP withdraw** 발송 → 전세계 BGP 라우터가 그 경로 제거 → 트래픽이 자동으로 다음으로 가까운 PoP으로. 보통 수십 초 ~ 수 분 내 수렴.

**Anycast의 함정**:
- **TCP 연결 중 PoP 변경** = 연결 끊김. BGP 경로가 중간에 바뀌면 다른 PoP으로 패킷이 가서 TCP state 모름 → RST.
- **UDP (DNS)에는 완벽**, **TCP**에는 까다로움. CDN은 TCP termination을 PoP에서 하고 그 안에서 origin과는 별도 connection 유지.

### 7.3 ECMP (Equal-Cost Multi-Path)

같은 destination에 대해 **여러 동등 비용 경로**가 있을 때 트래픽을 분산.

```
            [Router]
              │
        ┌─────┼─────┐
        │     │     │
    Link A  Link B  Link C    ← 셋 다 같은 비용, 같은 dst까지
        │     │     │
        └──┬──┴──┬──┘
           │     │
        [목적지]
```

**분산 방식**: round-robin이면 같은 TCP 연결의 패킷이 다른 경로로 → 도착 순서 뒤바뀜 → 성능 저하. 그래서 **hash 기반** 분산.

**Hash 기준 (보통 5-tuple)**: `(src_ip, src_port, dst_ip, dst_port, protocol)` → 같은 hash면 같은 경로. 같은 TCP 연결의 모든 패킷이 같은 경로 = **flow-level consistency**.

**L4 LB에서 ECMP의 역할**:
- LB가 같은 VIP를 여러 LB instance에서 광고 (anycast 비슷).
- 라우터의 ECMP가 5-tuple hash로 분산 → 같은 client의 같은 연결은 같은 LB instance로.
- LB instance에서 다시 backend 선택.

**문제 패턴**:
- LB instance가 추가/제거되면 hash 분포가 바뀌어 **기존 연결도 다른 LB로 가서 끊김** → consistent hashing이 부분적 해법.
- "elephant flow" — 한 연결이 너무 큰 트래픽 차지하면 다른 경로 놀고 한 경로만 폭주.

### 7.4 traceroute — 경로 추적의 원리

```
$ traceroute -n 93.184.216.34
 1  192.168.1.1     1 ms     1 ms     1 ms        ← 홈 라우터
 2  121.x.x.x       8 ms     7 ms     8 ms        ← ISP edge
 3  61.x.x.x       12 ms    12 ms    13 ms        ← ISP regional
 4  112.x.x.x      15 ms    15 ms    15 ms        ← ISP backbone
 5  *  *  *                                       ← ICMP rate limit or filter
 6  4.69.x.x      135 ms   135 ms   135 ms        ← Tier 1 (해저 케이블 hop, 큰 RTT 점프)
 7  152.x.x.x     145 ms   145 ms   145 ms
 8  93.184.216.34 148 ms   148 ms   148 ms        ← 도착
```

**원리** — TTL trick:
1. 패킷 보낼 때 **IP TTL = 1**로.
2. 첫 번째 hop 라우터가 받으면 `TTL--` → 0 → drop + **ICMP TIME_EXCEEDED** 응답. 그 응답의 src IP가 그 라우터.
3. **TTL = 2**로 다시 보냄 → 두 번째 라우터까지 가서 expire → 그 응답.
4. **TTL = 3, 4, ...** 계속 늘려가며 각 hop 식별.
5. 마지막엔 dst까지 도달 → dst가 응답 (ICMP unreach 또는 TCP RST/SYN+ACK).

**관측 도구**:
- `traceroute` (UDP에 high port 사용, BSD/Linux)
- `tracert` (Windows, ICMP echo 사용)
- `mtr` — traceroute + ping 결합, 실시간 loss/jitter 추적
- `tcptraceroute` — TCP SYN으로 (방화벽 회피)

**한계**:
- 일부 라우터가 ICMP rate limit / 응답 안 함 → `* * *`
- 비대칭 경로 — 응답 경로가 송신 경로와 다를 수 있음 (BGP는 단방향)
- 정확한 RTT는 ping이 더 신뢰. traceroute의 RTT는 hop의 응답 우선순위 영향 받음.

---

## 8. 가지 ⑧: CDN — Edge가 origin 앞에 서는 이유

### 8.1 핵심 질문

> "정적 자원이 CDN을 거치는 건 이해되는데, 동적 API도 왜 CDN을 통과하나요?"

### 8.2 CDN 구조 — edge PoP + origin shield

```
[사용자 (서울)]
   │ ① DNS → cdn-domain → GeoDNS/Anycast로 가까운 edge IP
   ▼
[Edge PoP (서울)]                  ← cache hit이면 즉시 응답
   │ cache miss
   ▼
[Regional cache / Origin Shield]   ← 같은 region edge들이 공유하는 중간 cache
   │ miss
   ▼
[Origin]                            ← 실제 origin server (us-east-1 등)
```

**Edge PoP**: 전세계 수십~수백 곳에 분산. 사용자 근처에서 응답.

**Origin Shield**: edge PoP들이 origin을 직접 hit 하면 origin이 N배 부하. 중간에 region별 single shield를 두면 **origin은 shield 1개만 응답**하면 됨 (thundering herd 방지).

### 8.3 키워드 1 — Cache key와 Vary header

**Cache key**: CDN이 응답을 cache할 때 key. 기본은 URL.

**Vary header**: 응답이 어떤 request header에 따라 달라지는지 명시. CDN이 이 header를 cache key에 포함.

```
HTTP/1.1 200 OK
Cache-Control: public, max-age=3600
Vary: Accept-Encoding, Accept-Language

→ 같은 URL이라도 Accept-Encoding (gzip/br) 따라 다른 cache entry
   Accept-Language (ko/en) 따라 다른 cache entry
```

**Vary 함정**:
- `Vary: User-Agent` — User-Agent는 무한 variation → cache가 거의 무용. 절대 쓰지 마.
- `Vary: Cookie` — 사용자별 cookie 다 다르면 그것도 무용.
- 정확히 필요한 것만 포함.

**Cache-Control 주요**:
- `public` / `private` (CDN cacheable 여부)
- `max-age=3600` (TTL)
- `s-maxage=86400` (shared cache=CDN용 별도 TTL)
- `no-store` (절대 cache 안 함)
- `no-cache` (cache는 되지만 사용 전 validation)
- `stale-while-revalidate=60` (TTL 만료 후 60초간 stale 응답 + 백그라운드 갱신)

### 8.4 키워드 2 — 왜 동적 컨텐츠도 CDN을 통과하나

CDN = 단순 cache 아님. 다음 이유로 **cache 안 되는 동적 컨텐츠도** CDN을 통과:

1. **TCP termination at edge**:
   - 사용자 ↔ edge: 가까워서 RTT 짧음 → TCP handshake/slow start 빠름.
   - edge ↔ origin: keepalive로 재사용. 사용자가 매번 origin까지 가는 것보다 훨씬 빠름.

2. **TLS termination at edge**:
   - TLS handshake (특히 RSA key exchange는 비싼 연산) 가까운 edge에서.
   - edge ↔ origin은 internal TLS 또는 mTLS.

3. **Smart routing**:
   - CDN의 private backbone (Cloudflare Argo, Akamai SureRoute) — 공용 인터넷 BGP보다 빠른 경로.
   - 다음 hop 선택을 매 ms 측정한 latency 기반.

4. **DDoS 흡수 + WAF**:
   - edge에서 악성 트래픽 차단 → origin 보호.

5. **압축 / 이미지 최적화**:
   - 동적 응답도 brotli/gzip, image format 변환을 edge에서.

**결론**: CDN은 정적 자원 cache가 출발이지만, 동적 컨텐츠에도 **edge proxy로서 가치**가 있음. 그래서 API 회사도 Cloudflare/Fastly/CloudFront 뒤에 둠.

### 8.5 Cache hierarchy 상세

```
[사용자] → [Edge PoP]
              │ Tier 1 cache (per-PoP)
              │
              ├──► [Regional Tier 2]
              │      │ Tier 2 cache (region 공유)
              │      │
              │      └──► [Origin Shield]
              │              │ 마지막 cache 막
              │              │
              │              └──► [Origin]
              │
              └──► Optional: peering된 다른 PoP의 cache
```

**Tier별 hit rate**:
- Edge tier 1: 60~90% (자주 보는 컨텐츠)
- Tier 2: 5~20% (덜 자주, but 같은 region 다른 사용자)
- Origin shield: 1~5% (cold cache)
- Origin: 1~10%

→ 잘 설계하면 origin이 받는 부하는 전체의 1% 이하.

---

## 9. 가지 ⑨: 운영 — DNS·라우팅 장애 패턴

### 9.1 핵심 질문

> "DNS 응답이 느려서 P99 spike 났습니다. 어디부터 봐야 하나요?"

### 9.2 패턴 1 — DNS lookup이 매 요청마다 일어나는 경우

**증상**: HTTP client 호출 P99이 100ms ~ 수 초로 들쭉날쭉. 평균은 정상.

**원인 후보**:
1. Connection이 매번 새로 열림 (keepalive 안 됨) → 매번 DNS lookup.
2. DNS cache TTL이 너무 짧음 (또는 0).
3. Resolver가 멀거나 부하 받는 중.
4. UDP 53 패킷 손실 → TCP fallback에 시간 소요.

**진단**:
```bash
# 매 호출 DNS 시간 측정
$ dig +tries=1 +time=2 example.com
;; Query time: 25 msec

# tcpdump로 DNS 패킷 추적
$ sudo tcpdump -i any -n udp port 53

# 애플리케이션의 DNS lookup 횟수 — JVM
-Dsun.net.spi.nameservice.provider.1=dns,sun
-Djava.net.preferIPv4Stack=true
```

### 9.3 패턴 2 — JVM `networkaddress.cache.ttl` 30초 함정

**JVM 기본 DNS 캐싱**:

```
$JAVA_HOME/conf/security/java.security 또는 $JAVA_HOME/jre/lib/security/

networkaddress.cache.ttl              = -1   ← positive 응답 cache (기본 -1 = forever! security manager 있을 때만 30)
networkaddress.cache.negative.ttl    = 10    ← negative cache
```

**옛 함정**: `-1` (= forever)이라 한 번 resolve한 IP를 JVM 평생 들고 있음. **failover 시 새 IP로 못 옮겨감**.

**security manager 있을 때**: 기본 30초. 그래서 보통 30초마다 다시 resolve. 이게 또 다른 문제:
- AWS RDS endpoint의 failover IP는 즉시 바뀌는데 JVM은 30초 lag.
- 반대로 너무 자주 lookup하면 CoreDNS/local resolver에 부하.

**현대 권장 (JDK 9+, JEP 142)**:
```properties
networkaddress.cache.ttl=60                  # 1분
networkaddress.cache.negative.ttl=0          # negative는 cache 안 함 (failover 빠르게)
```

**또는 시스템 프로퍼티**:
```
-Dsun.net.inetaddr.ttl=60
-Dsun.net.inetaddr.negative.ttl=0
```

→ AWS 등 클라우드에서 DB endpoint 등을 hostname으로 쓸 때 반드시 점검.

### 9.4 패턴 3 — Spring RestTemplate/HttpClient connection 재사용

**기본 RestTemplate**: 매 요청마다 new connection → 매번 DNS + 매번 TCP/TLS handshake.

**해결**: HttpClient pool 설정.

```java
PoolingHttpClientConnectionManager cm = new PoolingHttpClientConnectionManager();
cm.setMaxTotal(200);
cm.setDefaultMaxPerRoute(50);                    // ★ per-host pool 크기
cm.setValidateAfterInactivity(2_000);            // idle 연결 검증

CloseableHttpClient httpClient = HttpClients.custom()
    .setConnectionManager(cm)
    .setKeepAliveStrategy((response, context) -> 60_000)   // 60s keepalive
    .evictIdleConnections(30, TimeUnit.SECONDS)
    .build();

RestTemplate restTemplate = new RestTemplate(
    new HttpComponentsClientHttpRequestFactory(httpClient));
```

→ pool 안의 connection은 hostname → IP 매핑 그대로 유지. DNS lookup 매번 안 함.

**JDK 11+ HttpClient (java.net.http)**:
```java
HttpClient client = HttpClient.newBuilder()
    .connectTimeout(Duration.ofSeconds(2))
    .version(HttpClient.Version.HTTP_2)          // multiplexing
    .build();
```

→ 내부적으로 connection pool 관리. HTTP/2 multiplexing이면 한 연결에 여러 stream → DNS lookup 한 번.

### 9.5 패턴 4 — Kubernetes CoreDNS NXDOMAIN 폭증

**원인**: Pod의 `/etc/resolv.conf`:
```
nameserver 10.96.0.10               ← CoreDNS service IP
search default.svc.cluster.local svc.cluster.local cluster.local example.com
options ndots:5
```

**`ndots:5`**: hostname에 dot이 5개 미만이면 **search 도메인 먼저 시도**. 예:
- 코드: `httpClient.get("api.payment.com/v1")` — dot 3개 → 5 미만.
- 시도 순서:
  1. `api.payment.com.v1.default.svc.cluster.local` → NXDOMAIN
  2. `api.payment.com.v1.svc.cluster.local` → NXDOMAIN
  3. `api.payment.com.v1.cluster.local` → NXDOMAIN
  4. `api.payment.com.v1.example.com` → NXDOMAIN
  5. `api.payment.com.v1.` → 진짜 시도 → OK or NXDOMAIN
- × IPv4 + IPv6 (`A`, `AAAA`) = **10번 시도**.

**증상**:
- 모든 외부 hostname lookup이 평균 100ms (NXDOMAIN 다 받고 마지막에 진짜 응답).
- CoreDNS의 NXDOMAIN 응답 수가 정상 응답의 9배.
- conntrack table overflow → 일부 query timeout.

**해결**:
1. **FQDN으로 명시** — hostname 끝에 `.` 붙이기: `api.payment.com.`
2. **Pod의 `dnsPolicy: None` + 자체 resolv.conf 주입** — search 줄이기.
3. **NodeLocal DNSCache** — node마다 DNS cache daemon → CoreDNS 부하 ↓.
4. **stub domains / forwardPlugins** — CoreDNS에서 외부 도메인 별도 forward.

```yaml
# CoreDNS Corefile
example.com:53 {
    forward . 8.8.8.8 1.1.1.1
    cache 30
}

# 또는 Pod 설정
dnsPolicy: "None"
dnsConfig:
  nameservers: ["10.96.0.10"]
  searches: ["default.svc.cluster.local"]   # 5개 → 1개로
  options:
    - name: ndots
      value: "2"                              # 5 → 2로
```

### 9.6 패턴 5 — DNS TTL 0으로 설정해 부하

**증상**: failover 빠르게 하려고 모든 DNS TTL = 0. → recursive resolver가 cache 못 함 → 매 요청마다 auth NS hit. Auth NS 부하 폭증, latency spike.

**해결**: TTL은 60s 정도가 합리. 진짜 failover는 health-check 기반 DNS (Route53) + connection retry 패턴으로.

### 9.7 패턴 6 — DNS lookup latency가 P99 spike의 원인

**증상**: 평균 latency는 정상 (10ms 미만)인데, **P99만 200~500ms** spike. 디버깅 어렵다. APM에서 "처음 요청은 느리고 그 다음은 빠름" 패턴 보임.

**원인 분리**:

```
[요청 수명]
   │
   ├─ DNS lookup       ← ★ 여기서 spike?
   │  ├─ stub → recursive UDP 53     (정상 1~5ms)
   │  ├─ recursive cache miss
   │  │  ├─ root → TLD               (수십 ms)
   │  │  └─ TLD → auth NS            (수십~수백 ms)
   │  │     ★ auth NS가 멀거나 응답 느리면 P99 spike
   │  └─ UDP 응답 손실 + 재시도        (resolv.conf timeout × attempts)
   │
   ├─ TCP connect
   ├─ TLS handshake
   ├─ HTTP request/response
   ▼
```

**진단 절차**:

```bash
# 1. DNS lookup time만 측정
$ dig +stats www.google.com | grep "Query time"
;; Query time: 132 msec        ← spike 시 100ms+

# 2. tcpdump로 stub → recursive RTT 확인
$ sudo tcpdump -i any -n udp port 53 -tttt

# 3. JVM 애플리케이션이라면 DNS lookup 횟수 측정
JFR / async-profiler 로 InetAddress.getByName 호출 빈도
```

**JVM `networkaddress.cache.ttl` 기본 30초 (보안 매니저 없으면)**:
- Java 8까지: 보안 매니저 미설치 시 기본값 `-1` (영구 캐시) 또는 30초 — 환경 의존.
- Java 11+: 일관되게 30초.
- 30초마다 같은 hostname을 다시 풀면, 그 30초 경계 시점 트래픽은 DNS lookup 포함 → P99 spike의 일반 원인.

**해결**:
1. **`networkaddress.cache.ttl` 명시적 설정** — 보통 60s ~ 300s. 너무 길면 failover 늦음.
2. **`networkaddress.cache.negative.ttl`** — 기본 10초. NXDOMAIN 캐싱.
3. **`getaddrinfo()` 호출 횟수 줄이기** — HTTP client 재사용 + connection keep-alive로 매 요청마다 lookup 안 하도록.
4. **NodeLocal DNSCache** (Kubernetes) — node 자체에 DNS cache daemon.

```java
// JVM 옵션 또는 java.security 파일
// -Dnetworkaddress.cache.ttl=60
// -Dnetworkaddress.cache.negative.ttl=5
```

### 9.8 패턴 7 — DNS 캐시 poisoning + Kaminsky 공격

**옛 공격 (Kaminsky 2008)**:

```
1. 공격자가 victim에 메일/링크 등으로 "nonexistent-1.example.com" 같은 random 이름 query 유도
2. recursive resolver가 cache miss → auth NS에 query 시작 (UDP 53)
3. 공격자는 동시에 위조 응답 폭격:
   "nonexistent-1.example.com NS = ns.attacker.com"
   + Additional: "ns.attacker.com A = (공격자 IP)"
   (transaction ID brute-force)
4. recursive가 위조 응답 받아들이면 cache에 "ns.attacker.com" 저장
5. 이후 그 zone 전체 query가 공격자 NS로 → www.example.com까지 hijack
```

**방어**:
- **DNSSEC** — 위조 응답은 서명 검증 실패 → 무시. 단, 도메인 owner가 DNSSEC 활성화 + recursive가 검증 활성화 필요.
- **Source port randomization** — UDP query의 src port를 매번 random → transaction ID(16-bit) + port(16-bit) 합쳐 32-bit brute-force → 사실상 불가.
- **0x20 encoding** — query name의 대소문자 random화 → 응답에 같은 case로 echo 와야 valid. transaction ID 보강.

**현재 추가 방어**:
- **DoT/DoH** — DNS 자체를 TLS 위에 → wire에서 위조 불가.
- **DNSSEC chain validation** — recursive resolver가 `+dnssec` 플래그로 chain 검증.

**시니어 운영 관점**:
- 공공 cache resolver(8.8.8.8 등)는 DNSSEC 검증을 켜고 운영. 사내 corporate DNS는 DNSSEC 미적용인 경우 多.
- 사내에서 DNSSEC 켤 때 흔한 함정: 사내 split-horizon zone과의 충돌, key rollover 실수로 SERVFAIL.

### 9.9 패턴 8 — Anycast IP 변경이 client 캐시 때문에 즉시 반영 안 됨

**시나리오**:
- 회사가 anycast PoP A에서 PoP B로 트래픽 이전 (`my-cdn.example.com`).
- DNS 응답 IP를 새 anycast로 바꿈 + TTL 300초.
- 그런데 실제로 사용자 traffic의 cutover는 **5분이 아니라 30분~수 시간**.

**원인 hierarchy** (Auth NS는 즉시 바뀌어도 클라이언트까지 도달은 다단 cache의 합):

```
Auth NS  →  Recursive (TTL 기반, 일부는 무시)
         →  OS resolver cache (수 분)
         →  브라우저 in-memory (TTL 무시 가능)
         →  앱 자체 DNS cache (JVM 기본 30s ~ 영구)
         →  HTTP keep-alive connection (idle/max-lifetime까지 옛 IP 유지)
```

**해결**:
- 사전 TTL 단축 (cutover 24시간 전 60초 또는 5초로 미리 내림 → DNS 캐시 흡수).
- 양쪽 PoP 동시 운영하다가 traffic이 자연스럽게 빠진 뒤 옛 PoP 회수.
- **HTTP keep-alive max-age 짧게** + 강제 connection rotation.
- JVM 앱은 `networkaddress.cache.ttl` 짧게 + connection pool의 idle eviction.

### 9.10 패턴 9 — AWS Route53 health-check failover RTO

**구성**: `example.com` ALIAS — primary → ALB(ap-northeast-2), secondary → ALB(us-west-2), failover routing 기반.

**Route53 health-check 동작**: 전세계 여러 PoP에서 endpoint에 HTTP/HTTPS/TCP probe. 기본 30초 간격 × 3회 연속 fail → unhealthy (=90초). 일부 PoP만 fail이면 healthy 유지. unhealthy 시 DNS 응답에서 primary 제거 → secondary만 응답.

**실제 RTO 계산**:

```
T+0    : primary endpoint 장애 발생
T+90   : Route53 health-check unhealthy 판정
T+90~  : DNS 응답이 secondary로 전환 (Auth NS 즉시 적용)
T+150  : 사용자 측 recursive resolver cache 만료 (TTL 60s 가정)
T+180  : 브라우저/앱 캐시까지 만료
   ↓
RTO ≈ 90 + TTL + 앱 캐시 ≈ 2~3분
```

**RTO를 줄이려면**:
- health-check 간격을 **fast (10초)**로 + failure threshold 줄임 (3 → 2) → 약 20~30초.
- TTL 60초 유지 (더 줄이면 부하 폭증).
- 앱 측 DNS cache TTL 명시적 단축.
- 단, 다 합쳐도 RTO 30~60초가 한계. **진짜 무중단은 L7 retry + circuit breaker + multi-region client routing**으로 보강.

**대안 패턴**:
- **multi-A record + client retry**: primary와 secondary IP 모두 응답에 포함 + 클라이언트가 fail 시 다음 IP 시도. RTO ≈ TCP timeout (몇 초).
- **GSLB (Global Server Load Balancing)**: F5 BIG-IP, NS1 등. health-check 더 정교, 가격 비쌈.
- **Anycast + BGP withdraw**: PoP 자체가 죽으면 BGP withdraw → BGP convergence (수 초~분).

### 9.11 시나리오 매트릭스

| 증상 | 진단 명령 | 가능한 원인 |
|---|---|---|
| 매 요청 DNS lookup | tcpdump UDP 53 | keepalive 안 됨, JVM cache TTL 짧음 |
| failover 후 옛 IP 계속 시도 | `dig +short`, JVM `inetaddr.ttl` | DNS cache 너무 김 |
| P99 lookup 수초 spike | `dig +tries=1 +time=2` | resolver overload, UDP 손실, NXDOMAIN 폭증 |
| ECONNREFUSED 가끔 | 라우팅 변경 추적 | BGP convergence, anycast PoP 전환 |
| 한 region만 느림 | `traceroute`/`mtr` | 특정 AS hop 문제, peering link 포화 |
| TLS handshake 느림 | tcpdump TCP 443 | edge PoP까지 거리, OCSP stapling 미설정 |
| CoreDNS NXDOMAIN 폭증 | `kubectl logs coredns` | ndots:5, search 도메인 5개 |
| Anycast 연결 중간에 끊김 | TCP RST 추적 | PoP 라우팅 변경 (TCP는 anycast 함정) |
| SERVFAIL 가끔 | `dig +dnssec`, recursive 로그 | DNSSEC chain 깨짐, auth NS 응답 시간 초과 |
| 사용자 PC만 옛 IP 가짐 | `chrome://net-internals/#dns`, `dscacheutil` | 브라우저/OS cache, HSTS pinning |
| ARP cache 잘못된 MAC | `ip neigh show`, `arp -a` | ARP spoofing, GARP 폭주, gateway 교체 |
| Route53 failover 늦음 | Route53 health-check 콘솔 | 30s × 3 검사 + DNS TTL + 클라이언트 cache |

### 9.12 도구 한 줄 요약

```bash
# DNS
dig +trace example.com                   # 전 단계 추적
dig @8.8.8.8 +short example.com          # 특정 resolver 사용
dig +tcp +bufsize=4096 example.com       # TCP / EDNS0 강제
nslookup example.com 1.1.1.1             # 간단 확인
host -v example.com                      # 다른 도구

# 라우팅
ip route show                            # Linux 호스트 라우팅
netstat -rn                              # macOS/Linux
traceroute -n example.com
mtr -n example.com                       # 실시간 loss/jitter
tcptraceroute example.com 443            # TCP, 방화벽 회피
ss -tn state established                 # 활성 TCP 연결

# BGP
bgp.he.net/ip/93.184.216.34              # AS path / origin AS
https://lg.he.net/                       # looking glass

# 패킷
tcpdump -i any -n udp port 53            # DNS 캡처
tcpdump -i any -n 'host example.com'     # 특정 호스트
```

---

## 10. 면접 답변 워크플로우

### 10.1 질문 → 가지 매핑

| 질문 | 진입 가지 | 인접 확장 |
|---|---|---|
| "DNS는 어떻게 동작하나요?" | ① 5계층 | ③ 캐싱 / ⑤ GeoDNS |
| "8.8.8.8은 어떻게 항상 빠르죠?" | ⑦ Anycast | ⑥ BGP / ① recursive |
| "TTL을 짧게 잡으면 무슨 일?" | ③ 캐싱 | ⑨ 운영 / ⑤ failover |
| "CDN이 어떻게 동작하나?" | ⑧ CDN | ⑦ Anycast / ⑤ GeoDNS |
| "BGP가 뭔가?" | ⑥ IP 라우팅 | ⑦ Anycast / ECMP |
| "traceroute 원리?" | ⑥ IP 라우팅 | ⑨ 진단 |
| "DoH/DoT 왜 등장?" | ④ 진화 | ③ poisoning |
| "K8s DNS가 느려요" | ⑨ 운영 (CoreDNS) | ① resolver 계층 |
| "JVM DNS cache?" | ⑨ 운영 | ③ TTL |
| "ECMP가 뭐고 왜 hash로?" | ⑦ Anycast/ECMP | ⑥ 라우팅 |

### 10.2 답변 템플릿

> **루트 한 문장 → 진입 가지의 키워드 3개 순서대로 → 시간 남으면 인접 가지**

예: "DNS는 어떻게 동작하나요?"

> "DNS는 hostname을 IP로 바꾸는 시스템인데 단일 서버가 아니라 **5계층 cache hierarchy + recursive resolver 모델**입니다. (← 루트)
> 첫째, 클라이언트 쪽은 **브라우저 cache → OS resolver cache → /etc/hosts → stub resolver** 순서로 보고, miss면 `/etc/resolv.conf`에 적힌 **recursive resolver** (ISP 또는 8.8.8.8)에 UDP 53으로 질의.
> 둘째, recursive가 cache miss면 **root NS → TLD NS → authoritative NS** 3단계 referral을 거쳐 최종 A 레코드를 받음. 결과는 TTL 동안 각 단계 cache에 저장.
> 셋째, TTL이 핵심 — **positive TTL은 짧으면 failover 빠르지만 NS 부하**, **negative caching은 SOA의 minimum 값**, 너무 길면 잘못된 응답이 오래 살아남음.
> 실무 진단으로는 `dig +trace`, `tcpdump udp port 53`, JVM의 `networkaddress.cache.ttl` 점검, K8s면 CoreDNS의 `ndots:5` 함정 확인합니다."

---

## 11. 꼬리질문 트리

### Q1 [가지 ①]. `https://example.com` 치면 브라우저가 IP를 얻기까지 단계?

> 브라우저 in-memory cache → OS resolver cache (systemd-resolved/discoveryd) → `/etc/hosts` → stub resolver가 `/etc/resolv.conf`의 nameserver에 UDP 53 질의 → recursive resolver (ISP/8.8.8.8) → cache miss면 root NS → com TLD NS → example.com authoritative NS 3단계 referral. authoritative가 A 93.184.216.34 응답, TTL 만큼 각 단계 cache.

**Q1-1: stub과 recursive 차이는?**
> stub은 OS 안의 미니 client — 자기 책임 없음, recursive에 질의하고 응답 받기만. recursive는 root→TLD→auth를 자기가 다 묻고 답을 만들어줌. 이름의 "recursive"는 client 입장 아닌 resolver의 동작 방식.

**Q1-1-1: glue record가 뭐고 왜 필요?**
> TLD가 "example.com의 NS는 ns1.example.com" 라고 하면, 또 그 NS의 IP를 찾아야 함 → 무한 루프. 그래서 TLD가 NS 레코드와 함께 그 NS host의 A 레코드도 같이 줌. 이게 glue. authoritative NS가 자기 zone 안에 있는 경우 필수.

### Q2 [가지 ③]. TTL을 30초로 잡으면 뭐가 좋고 뭐가 나쁜가?

> 좋은 점: failover 빠름. IP 변경 후 30초면 전세계 cache 갱신. blue-green 배포에 유리. 나쁜 점: recursive resolver의 cache hit rate ↓ → auth NS 부하 ↑. DDoS 시 auth가 SPOF. P99 latency 약간 ↑ (cache miss 잦으니 lookup 자체 추가). 정적 자원은 1day, 동적/failover는 60s, blue-green은 30s 정도.

**Q2-1: Negative caching이 뭐고 어디서 TTL을 가져오나?**
> NXDOMAIN(존재 안 함) 또는 NODATA(존재하나 그 레코드 타입 없음) 응답도 cache 되어야 같은 잘못된 질의 반복 안 됨. TTL은 zone의 **SOA 레코드 minimum 필드**가 RFC 2308부터 negative TTL로 재정의됨. CoreDNS NXDOMAIN 폭증 사고의 근원이기도.

### Q3 [가지 ⑥/⑦]. BGP가 뭐고 AS_PATH 선택은 어떻게?

> AS 간 라우팅 정보 교환 프로토콜. 각 AS가 자기 prefix를 다른 AS에 광고. 받는 쪽이 prepend로 자기 AS 추가. best path 선택은 1순위 local preference (자기 정책), 2순위 AS_PATH 짧은 것, 그 다음 origin type, MED, eBGP vs iBGP, IGP metric, router ID 순. AS prepend traffic engineering이나 BGP hijack 같은 사고가 여기서 발생.

**Q3-1: Anycast와 GeoDNS 차이?**
> GeoDNS는 같은 hostname에 region별로 다른 IP 응답 — 사용자별로 다른 답. Anycast는 같은 IP를 여러 PoP에서 BGP로 광고해서 BGP가 가장 가까운 PoP으로 보냄 — 사용자별로 같은 답. 8.8.8.8/1.1.1.1는 anycast. AWS S3 endpoint는 GeoDNS+anycast 혼합.

**Q3-1-1: Anycast의 함정?**
> TCP에서 연결 중 BGP 경로 변경 → 다른 PoP으로 패킷 가서 TCP state 모름 → RST. UDP는 stateless라 무관 — 그래서 DNS는 anycast가 완벽. TCP CDN은 PoP에서 TCP terminate하고 그 안에서 origin과는 별도 connection 유지하는 식으로 우회.

### Q4 [가지 ⑦]. ECMP는 어떻게 분산을 결정하나?

> 같은 dst에 같은 비용 경로 N개일 때 5-tuple `(src_ip, src_port, dst_ip, dst_port, protocol)` hash로 경로 선택. 같은 hash = 같은 경로 → 같은 TCP 연결 모든 패킷 같은 경로 = flow-level consistency. round-robin은 패킷 순서 뒤집혀서 안 됨. 함정: LB instance 추가/제거 시 hash 분포 변경 → 기존 연결 깨질 수 있음. consistent hashing이 부분 해법.

### Q5 [가지 ④]. DoT/DoH가 왜 등장했나? DNSSEC과 차이는?

> DNSSEC은 **데이터 무결성** — 응답 자체에 서명. 채널은 평문이라 누가 어떤 도메인을 묻는지는 ISP/공격자가 다 봄. DoT(853/TCP, TLS)와 DoH(443/TCP, HTTPS)는 **채널 암호화** — 누구와 무엇을 묻는지 모두 가림. DoH는 443이라 일반 HTTPS와 구별 불가 → 검열 회피 강. 함정: DoH가 회사 내부 hostname 못 풀어 enterprise에서 비활성화 정책 흔함.

### Q6 (Killer) [가지 ⑨]. P99 spike 났는데 DNS가 의심됨. 진단 절차?

> 단계:
> 1. **애플리케이션 metric** — DNS lookup 시간을 별도로 측정 (Micrometer `jvm.network.dns` 등). 매 호출 lookup이면 keepalive 안 되는 것.
> 2. **`tcpdump -n udp port 53`** — 실제 DNS 패킷 캡처. response 시간 측정.
> 3. **`dig +tries=1 +time=2 example.com`** — resolver 자체 응답 시간.
> 4. **JVM `networkaddress.cache.ttl` 점검** — 너무 길면 stale, 너무 짧으면 lookup 폭증.
> 5. **HTTP client pool** — RestTemplate에 connection pool 설정됐는지. pool 있으면 같은 hostname은 매번 lookup 안 함.
> 6. **K8s면 CoreDNS** — `ndots:5` 함정 (search 도메인 5개 × A/AAAA = 10번 NXDOMAIN). dnsConfig로 ndots:2 줄이거나 hostname 끝에 `.` 붙여 FQDN.
> 7. **Resolver overload** — `kubectl logs coredns`, recursive 응답 시간 분포.

**Q6-1: JVM `inetaddr.ttl` 기본은?**
> JDK 8까지 security manager 없으면 `-1` = forever, 있으면 30초. JDK 9+에서는 30초 기본이지만 권장은 60초 + negative.ttl=0. AWS RDS endpoint failover IP 못 따라가서 hang 걸리는 사고가 흔함.

**Q6-1-1: HikariCP에 hostname 쓸 때 주의?**
> HikariCP는 connection pool에 idle connection 유지 → 같은 IP만 계속 씀. DB failover 시 새 IP로 못 옮겨감. `socketTimeout` + connection validation + `maxLifetime` 짧게 (30분 이하) 설정해서 강제 재연결 유도해야 함.

### Q7 [가지 ⑧]. CDN에 동적 컨텐츠를 통과시키는 이유 4가지?

> ① TCP termination at edge — 사용자 ↔ edge RTT 짧음 → handshake/slow start 빠름. edge ↔ origin은 keepalive 재사용. ② TLS termination at edge — RSA 같은 비싼 handshake가 가까운 곳에서. ③ Smart routing — CDN의 private backbone(Cloudflare Argo, Akamai SureRoute)이 공용 BGP보다 빠른 경로. ④ DDoS 흡수 + WAF — 악성 트래픽을 origin 전에 차단. ⑤ (보너스) 압축/이미지 변환을 edge에서.

**Q7-1: Vary header의 안티패턴?**
> `Vary: User-Agent` — 무한 variation → cache 사실상 무용. `Vary: Cookie` — 사용자별 cookie 다 다르면 무용. 정확히 필요한 것만 (Accept-Encoding, Accept-Language 정도).

### Q8 (패턴 통찰). DNS 캐싱 사상이 다른 어디서 반복되나?

> "계층적 cache + TTL + negative cache" 패턴이 도처에:
> - **CPU 캐시 hierarchy** — L1 → L2 → L3 → RAM (TTL은 cache eviction policy)
> - **HTTP cache** — browser → CDN edge → origin (Cache-Control max-age, ETag)
> - **DB query cache** — application → Redis → DB (TTL, invalidation)
> - **JVM Class cache** — Compressed Class Pointer → Klass metadata
> - **TLB (Translation Lookaside Buffer)** — virtual → physical address cache
> - **ARP cache** — IP → MAC, 보통 5분 TTL
>
> 공통 원리: **빈도가 높은 lookup을 가까운 곳에 cache, 일관성은 TTL/invalidation으로 절충**. negative caching은 "없음"도 답이라는 사상.

---

## 12. 학습 체크리스트

면접 전 백지에서 다음을 다 해낼 수 있어야 마스터:

- [ ] 0장 마인드맵을 종이에 1분 내로 그릴 수 있다 (루트 + 7가지 + 키워드 3개씩)
- [ ] 가지 ①: DNS 5계층 (브라우저→OS→hosts→stub→recursive→root→TLD→auth)을 그림으로
- [ ] 가지 ①: `dig +trace` 출력을 단계별로 해설
- [ ] 가지 ②: A/AAAA/CNAME/ALIAS/MX/TXT/NS/SOA/SRV/CAA 각각 1줄 용도
- [ ] 가지 ②: CNAME apex 함정과 ALIAS/CNAME flattening
- [ ] 가지 ③: TTL 짧게/길게 trade-off + negative caching의 SOA minimum 출처
- [ ] 가지 ③: Kaminsky 공격 원리 + source port randomization + DNSSEC chain
- [ ] 가지 ④: UDP 53 → EDNS0 → TCP fallback → DoT/DoH/DoQ 진화 이유
- [ ] 가지 ⑤: GeoDNS vs Latency-based vs Weighted vs Failover 차이
- [ ] 가지 ⑤: ECS (EDNS Client Subnet)가 왜 필요한가
- [ ] 가지 ⑥: 호스트 라우팅 테이블 → gateway → ISP → Tier 1 → backbone 흐름
- [ ] 가지 ⑥: BGP AS_PATH best path 선택 규칙 순서
- [ ] 가지 ⑥: ARP, CIDR, SNAT/DNAT/PAT 차이
- [ ] 가지 ⑦: Anycast 동작 원리 + TCP의 함정 + BGP withdraw failover
- [ ] 가지 ⑦: ECMP 5-tuple hash와 flow-level consistency
- [ ] 가지 ⑦: traceroute의 TTL trick 원리
- [ ] 가지 ⑧: CDN edge PoP + origin shield + cache key + Vary
- [ ] 가지 ⑧: 동적 컨텐츠가 CDN을 통과하는 4가지 이유
- [ ] 가지 ⑨: DNS lookup 매번 일어나는 문제 진단 (tcpdump, dig)
- [ ] 가지 ⑨: JVM `networkaddress.cache.ttl` 함정과 권장 설정
- [ ] 가지 ⑨: CoreDNS NXDOMAIN 폭증의 ndots:5 메커니즘과 해결
- [ ] 11장 꼬리질문 8개에 막힘없이 답

---

## 다음 단계

- → [03. OSI 7 Layers and TCP/TLS](./03-osi-7-layers-and-tcp-tls.md): IP를 얻었으니 그 위에 TCP/TLS가 어떻게 끼어드나
- → [04. Load Balancer Deep Dive](./04-load-balancer-deep-dive.md): L4/L7 LB의 모든 역할
- → [08. DB Connection and JDBC](./08-db-connection-and-jdbc.md): DB endpoint도 hostname → 동일 DNS 문제 적용

## 참고

- **RFC 1034/1035** (DNS 본질): https://datatracker.ietf.org/doc/html/rfc1034 / 1035
- **RFC 2308** (Negative caching, SOA minimum): https://datatracker.ietf.org/doc/html/rfc2308
- **RFC 4033~4035** (DNSSEC): https://datatracker.ietf.org/doc/html/rfc4033
- **RFC 6891** (EDNS0): https://datatracker.ietf.org/doc/html/rfc6891
- **RFC 7858** (DoT): https://datatracker.ietf.org/doc/html/rfc7858
- **RFC 8484** (DoH): https://datatracker.ietf.org/doc/html/rfc8484
- **RFC 7871** (EDNS Client Subnet): https://datatracker.ietf.org/doc/html/rfc7871
- **RFC 4271** (BGP-4): https://datatracker.ietf.org/doc/html/rfc4271
- **RFC 9460** (HTTPS/SVCB record): https://datatracker.ietf.org/doc/html/rfc9460
- **JEP 142** (JDK DNS TTL): https://openjdk.org/jeps/142
- **Hurricane Electric BGP**: https://bgp.he.net/
- **Cloudflare DNS learning**: https://www.cloudflare.com/learning/dns/
- **AWS Route53 routing policy**: https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/routing-policy.html
- **CoreDNS docs**: https://coredns.io/manual/toc/
- **Kubernetes DNS-Based Service Discovery**: https://kubernetes.io/docs/concepts/services-networking/dns-pod-service/
