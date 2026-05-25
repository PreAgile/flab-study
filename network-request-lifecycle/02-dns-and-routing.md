# 02. DNS & Routing — hostname이 IP가 되고, 그 IP로 가는 패킷이 인터넷을 가로지르는 길

> "DNS(Domain Name System)는 hostname을 IP로 바꾸는 시스템" 까지는 입문.
> "브라우저 캐시 → OS resolver → stub → recursive → root → TLD(Top-Level Domain) → authoritative 4계층 cache hierarchy + TTL/negative caching + 그 IP는 호스트 라우팅 → gateway → ISP → BGP(Border Gateway Protocol) AS(Autonomous System) path → ECMP/Anycast/CDN edge를 거친다" 까지 답해야 시니어.
> *(모든 약자는 §12.5 약자 사전에서 한 곳에 정리)*

---

## 0. 마인드맵 — 한 장 그림

```
[hostname → IP → 인터넷 횡단 → 백엔드]
        │
   ┌────┴──────┬─────────┬──────────┬──────────┐
   │           │         │          │          │
  ① DNS 4계층 ② TTL    ③ 진화    ④ 라우팅   ⑤ Anycast/CDN
   브라우저   positive   UDP→TCP   라우팅표    같은 IP
   OS resolv  negative   EDNS0     gateway     여러 PoP
   recursive  Kaminsky   DoT/DoH   BGM AS path ECMP flow hash
   root/TLD/  DNSSEC               ARP/MAC     edge PoP
   auth                            traceroute  origin shield
```

핵심 한 문장 (anchor):
> **"DNS는 4계층 cache hierarchy로 hostname→IP를 풀고, 그 IP로 가는 패킷은 호스트 라우팅표 → gateway → BGP AS path → ECMP/Anycast를 거쳐 백엔드에 도달한다."**

---

## 메인 시나리오 — `www.google.com` 한 번에 따라가기

사용자가 브라우저 주소창에 `www.google.com` Enter 친 그 순간부터 첫 HTTP 응답이 그려지기 직전까지 — 7단계로 압축:

```
① URL 파싱 — 브라우저가 hostname "www.google.com"을 분리, HSTS preload 체크
   │
② DNS resolution — 4계층 cache hierarchy
   브라우저 캐시 → OS resolver(/etc/hosts → nsswitch → OS 캐시)
        → stub resolver(/etc/resolv.conf) → recursive(8.8.8.8 anycast)
        → cache miss면 root → .com TLD → google.com auth NS → A 142.250.196.132
   각 단계 TTL 동안 cache. 응답 = 추가로 AAAA(IPv6)도 받음 → Happy Eyeballs로 둘 다 시도.
   │
③ IP 결정 후 호스트 라우팅 — Layer 3
   host routing table 조회 → dst가 LAN 밖이면 default → gateway 192.168.1.1
   │
④ ARP — Layer 2
   "192.168.1.1의 MAC?" broadcast → gateway가 reply. ARP cache에 저장.
   Ethernet frame 작성: src MAC=내 NIC, dst MAC=gateway, dst IP=142.250.196.132(그대로).
   │
⑤ Router hop들 — ISP edge → Tier 2 → Tier 1 backbone
   hop마다 L2 frame은 새로 만들어지고 L3 IP header는 그대로.
   각 라우터가 BGP AS_PATH 테이블 보고 next-hop 결정.
   │
⑥ Google AS 도착 — Anycast PoP
   142.250.196.132은 anycast IP. BGP가 사용자에게 가장 가까운 PoP으로 라우팅.
   PoP 도착 후 ECMP로 N개 backend 중 하나 선택 (5-tuple hash).
   │
⑦ Edge LB → backend
   CDN edge에서 TCP/TLS termination → keep-alive로 origin과 재사용 → HTTP 응답
   응답 패킷은 역순 (단, 정확한 대칭은 아님 — BGP asymmetry 흔함)
```

이 7단계가 이 문서의 메인 시나리오. 아래 각 장이 단계별 상세.

---

## 1. DNS 4계층 — hostname이 IP가 되는 경로

### 1.1 전체 흐름 한 다이어그램

```
[브라우저] "www.google.com?"
   │
   │ ① 브라우저 in-memory DNS 캐시 (Chrome chrome://net-internals/#dns)
   │    hit → 반환. miss ↓
   │
   ▼
[OS resolver]
   │ ② /etc/hosts → nsswitch.conf → OS 캐시 (systemd-resolved / mDNSResponder)
   │    hit → 반환. miss ↓
   │
   ▼
[Stub resolver (libc getaddrinfo)]
   │ ③ /etc/resolv.conf의 nameserver에 UDP 53 질의 (재귀 요청 = RD bit)
   │
   ▼
[Recursive resolver — ISP / 8.8.8.8 / 1.1.1.1]
   │ ④ 자기 cache hit → 반환. miss면 ↓ 3단 referral
   │
   │       Root NS (".")          → "com은 TLD NS에 물어봐, IP는 ..."
   │       └─→ TLD NS (".com")    → "google.com authoritative는 ns1.google.com, IP는 ..."
   │            └─→ Auth NS       → "www.google.com A = 142.250.196.132"
   │
   ▼
[A record + TTL] → 각 단계 cache에 TTL 동안 저장
```

핵심: **단일 서버가 아니라 cache hierarchy**. 각 단계가 TTL 동안 응답을 저장. 그래서 인터넷 규모에서 dns 부하가 견딘다.

<details>
<summary>📌 <b>OS resolver란? — 클릭해서 펼치기</b></summary>

**OS resolver = 운영체제(macOS/Linux/Windows) 안에 내장된 DNS 처리 모듈.** application(브라우저, curl, Java JVM)이 hostname을 IP로 바꾸려 할 때 OS의 표준 함수 `getaddrinfo()`를 호출하면 그 함수가 실행되는 곳.

내부 순서:
```
㉠ /etc/hosts 파일 확인           ← 텍스트 파일에 직접 박힌 매핑
㉡ nsswitch.conf 순서 확인        ← "files → dns" 등 검색 순서 설정
㉢ OS 메모리 캐시 확인            ← macOS: mDNSResponder
                                    Linux: systemd-resolved / nscd
                                    Windows: DNS Client Service
                                    TTL 안 지난 응답 보관
㉣ 모두 miss → stub resolver로 위임
```

**캐시 hit이면 네트워크 통신 없이 즉시 IP 반환.** application은 곧장 다음 단계(TCP 연결)로 진행.

**자주 묻는 함정 — "캐시 hit이면 HTML도 반환?"**
- DNS 캐시는 **"hostname → IP"** 매핑만 캐시. HTML 자체는 캐시 안 함.
- DNS hit으로 빨라지는 건 **"IP 결정" 단계만**. TCP 연결·HTTP 요청·HTML 응답은 그대로 일어남.
- HTML 자체의 캐시는 **HTTP cache** (Cache-Control, ETag, Last-Modified) — 별도 메커니즘. CDN/브라우저 HTTP cache가 hit이면 그땐 HTML 응답까지 skip 가능.

</details>

<details>
<summary>📌 <b>Stub resolver / libc getaddrinfo() / /etc/resolv.conf / UDP 53 질의 — 클릭</b></summary>

**4개가 한 묶음.** stub resolver의 실체가 libc getaddrinfo()이고, 그 함수가 /etc/resolv.conf를 읽어 nameserver IP를 알아낸 후 UDP 53번 포트로 DNS 질의를 보낸다.

### Stub resolver
**클라이언트 측 minimal DNS client.** 자기는 recursion 안 하고 그저 "물어볼 곳(recursive resolver)에 단순 질의 → 받은 답 application에 전달"만 함.

비유: "당신(application) → 비서(stub) → 사장(recursive)". 비서는 직접 일 안 하고 사장에게 위임만.

### libc getaddrinfo()
**C 표준 라이브러리(libc)의 hostname 해석 함수.** stub resolver의 실체.

```c
#include <netdb.h>
struct addrinfo *result;
getaddrinfo("www.google.com", "443", NULL, &result);
```

브라우저, Java `InetAddress.getByName()`, Python `socket.getaddrinfo()`, Node.js `dns.lookup()` — 모든 언어의 DNS 호출이 결국 이 libc 함수를 통해 OS resolver를 호출.

→ "libc" = 모든 application이 공유하는 OS-level 표준 라이브러리.

### /etc/resolv.conf
**Linux/macOS의 텍스트 설정 파일.** "어느 DNS 서버에게 물어볼지" + "search 도메인" 명시.

```bash
$ cat /etc/resolv.conf
nameserver 8.8.8.8       # ← recursive resolver IP
nameserver 1.1.1.1       # ← 백업
search example.com       # ← 짧은 hostname에 자동 append
options ndots:5          # ← search 적용 조건
```

- `nameserver`: 질의 던질 recursive IP. 보통 DHCP가 자동 갱신 (공유기에서 받은 ISP DNS).
- 직접 수정해서 8.8.8.8 / 1.1.1.1 로 변경 가능.
- macOS는 이 파일 대신 시스템 환경설정 네트워크 패널 관리. Linux systemd-resolved는 stub `127.0.0.53` 가리킴.

### UDP 53 질의
**DNS 표준 프로토콜.** UDP의 53번 포트로 질의/응답.

**왜 UDP?**
- TCP 3-way handshake 없이 즉시 packet 송신 → 빠름
- 질의·응답이 짧아 한 packet에 들어감 (보통 ≤ 512 byte)
- stateless → resolver가 connection 상태 안 들고 있어도 됨

**53번 포트**: DNS에 할당된 well-known port (RFC 1035, 1987). 모든 DNS 서버가 여기서 listen.

**"재귀 요청 = RD bit"**:
- DNS header의 **RD (Recursion Desired)** flag bit를 1로 설정
- "내가 너한테 한 번만 물어볼 테니 root/TLD/auth 다 알아서 거쳐서 답 줘" 신호
- RD=0이면 resolver는 자기 cache만 보고 모르면 referral만 줌 (iterative)

**UDP가 안 통하면**:
- 응답이 512 byte 초과 → TCP 53번으로 재시도 (또는 EDNS0로 UDP 크기 확장)
- DNSSEC 응답이 큼 → TCP fallback
- Zone transfer (대량) → TCP

### 한 문장 정리

> "libc `getaddrinfo()`(= stub resolver의 실체)가 `/etc/resolv.conf`를 읽어 nameserver IP(예: 8.8.8.8)를 알아낸 후, UDP 프로토콜로 53번 포트에 RD=1 flag를 박은 DNS 질의 packet을 송신한다."

</details>

<details>
<summary>📌 <b>A / AAAA / CNAME / MX / TXT 등 DNS record type 풀버전 — 클릭</b></summary>

**DNS record = "이 hostname에 대해 어떤 정보를 줄지" 정의. Type에 따라 답이 IP/hostname/메일서버/문자열 등이 됨.**

### 자주 쓰는 record 6개

| Type | 매핑 | 예시 |
|---|---|---|
| **A** | hostname → **IPv4** | `www.google.com IN A 142.250.196.132` |
| **AAAA** | hostname → **IPv6** | `www.google.com IN AAAA 2607:f8b0:...` |
| **CNAME** | hostname → **다른 hostname** (alias) | `blog.example.com IN CNAME ghost.netlify.app` |
| **MX** | 도메인 → **메일 서버** (priority) | `example.com IN MX 10 mx1.google.com` |
| **TXT** | 임의 문자열 (SPF/DKIM/도메인 검증) | `example.com IN TXT "v=spf1 ..."` |
| **NS** | 그 zone의 **authoritative nameserver들** | `google.com IN NS ns1.google.com` |

### 보조 record

| Type | 의미 |
|---|---|
| **SOA** | zone의 권한 정보 + minimum TTL (negative cache TTL의 출처) |
| **PTR** | IP → hostname **역방향** 매핑 (메일 spam check) |
| **SRV** | service discovery (XMPP, SIP, Kerberos, K8s headless) |
| **CAA** | 인증서 발급 가능 CA 제한 (Let's Encrypt 허용 등) |
| **DNSKEY / DS / RRSIG / NSEC** | DNSSEC 관련 |
| **HTTPS / SVCB** | HTTP/3 ALPN + ECH 협상 (최신, RFC 9460) |
| **TLSA** | DANE — TLS cert를 DNS로 publish (DNSSEC 필요) |

### AAAA가 "쿼드 A"인 이유
- IPv4 주소는 32 bit, IPv6 주소는 128 bit
- IPv6가 IPv4의 **4배** → 이름이 "A"를 4개 (A → AAAA)
- 발음: "쿼드 A" 또는 "에이에이에이에이"

### Happy Eyeballs (RFC 8305)
- 브라우저가 보통 **A와 AAAA를 동시 질의**
- 둘 다 받으면 **더 빠른 쪽**으로 TCP 연결 시도
- IPv6 우선이지만 응답 늦으면 IPv4로 fallback

### CNAME apex 함정
- `example.com` (apex/zone root)에는 CNAME 못 씀
- 이유: RFC가 "CNAME은 다른 record와 공존 불가"라고 정의 → apex는 NS/SOA가 필수이므로 충돌
- 해결: AWS Route53 **ALIAS**, Cloudflare **CNAME flattening** 같은 비표준 우회

### MX의 priority
```
example.com IN MX 10 mx1.google.com
example.com IN MX 20 mx2.google.com
```
- 첫 숫자가 우선순위 (낮을수록 우선)
- mx1이 죽으면 mx2 시도

### TXT 활용
- **SPF**: 어떤 IP가 이 도메인에서 메일 보낼 수 있는지 (스팸 방지)
- **DKIM**: 메일 서명 공개키
- **DMARC**: SPF/DKIM 정책
- **도메인 검증**: Google/AWS/Cloudflare가 "이 TXT 박아둬 → 너 진짜 주인인지 확인"

</details>

### 1.2 stub vs recursive

- **stub**: OS 안의 미니 client. 책임 없음. "재귀로 풀어줘" 한 번 던지고 결과만 받음.
- **recursive**: root→TLD→auth를 자기가 다 묻고 답을 합성. ISP DNS, 8.8.8.8(Google), 1.1.1.1(Cloudflare)이 대표.

### 1.3 root → TLD → authoritative

도메인 이름은 **오른쪽이 위, 왼쪽이 아래**인 트리 구조. `www.google.com.` 의 마지막 `.` 이 root.

```
www.google.com.
↑   ↑      ↑  ↑
│   │      │  └─ Root (.) — 최상위 zone
│   │      └─── TLD (.com) — Top-Level Domain
│   └────────── 2nd level (google) — Authoritative zone
└────────────── 3rd level (www)
```

각 단계가 **referral**(다음에 누구에게 물어봐야 하는지)만 알려줌. 최종 IP는 마지막 authoritative만 가짐.

- **Root NS**: DNS 트리의 최상위 zone (이름이 비어있어 `.`). 전세계 13개 letter (`a~m.root-servers.net`), 실제로는 anycast로 수백 노드. **TLD nameserver 주소록**만 가짐 ("`.com`은 a.gtld-servers.net이 안다" 식으로 referral).
- **TLD (Top-Level Domain) NS**: 도메인 이름의 가장 오른쪽 부분 (`.com`, `.org`, `.kr` 등)을 관리하는 zone. 그 TLD에 속한 모든 2nd-level domain의 nameserver 주소록을 가짐.
  - **gTLD** (general): `.com .org .net .io .app .dev` 등 (ICANN 산하 registry, .com은 Verisign)
  - **ccTLD** (country code): `.kr .jp .uk .de` 등 (각 나라 관리, `.kr`은 KISA)
  - 최종 IP는 모르고, "`google.com`은 ns1.google.com이 관리해"라는 NS record 위임 정보만.
- **Authoritative NS**: 특정 도메인의 **최종적이고 권위 있는** zone. 도메인 소유자가 직접 운영하거나 DNS 서비스(Route53, Cloudflare, NS1, 자체 운영 BIND)에 위임. 실제 A/AAAA/MX/TXT 레코드 보유 → "**최종 답을 주는 유일한 단계**".

→ **요약**: root와 TLD는 **referral만**, authoritative만 **최종 답**. 3단계 referral(`. → .com → google.com auth`)을 거쳐 IP에 도달.

### 1.4 `dig +trace` 핵심

```bash
$ dig +trace www.google.com
;; [phase 0] root hints (.)         → 13 root NS letter
;; [phase 1] root NS에 질의         → ".com TLD NS는 a~m.gtld-servers.net"
;; [phase 2] .com TLD NS에 질의     → "google.com auth NS는 ns1~4.google.com"
;; [phase 3] google.com auth NS에 질의 → "www.google.com A = 142.250.196.132"
```

`+trace`는 recursive resolver를 우회하고 root부터 단계별로 직접 묻는 진단 도구. 일반 사용자가 보는 4계층 cache hierarchy의 **마지막 cache miss** 시 일어나는 일이 그대로 출력에 노출된다. 운영에서는 "특정 도메인 응답이 이상하다" 할 때 어느 단계에서 잘못된 응답이 나오는지 격리하는 용도.

### 1.5 DNS 레코드 — 한 줄 요약

| 레코드 | 용도 |
|---|---|
| A / AAAA | hostname → IPv4 / IPv6 |
| CNAME | hostname → 다른 hostname (alias). **apex(`example.com` 자체)에는 못 씀** → ALIAS/ANAME으로 우회 |
| MX | 메일 서버 |
| TXT | SPF/DKIM/도메인 검증 |
| NS / SOA | 위임 / zone 권한·TTL minimum |
| SRV | service discovery 시초 (Kerberos, SIP, K8s headless service) |
| CAA | 발급 가능 CA 제한 (Let's Encrypt 허용 등) |

**SOA minimum 필드** = negative TTL의 출처 (RFC 2308). NXDOMAIN 캐싱 시간을 여기서 가져옴.

---

## 2. TTL & 캐싱 — 왜 4계층 모두에 cache가 있나

### 2.1 Positive vs Negative caching

- **Positive TTL**: 정상 응답의 cache 수명. 짧으면 failover 빠름, 길면 NS 부하 ↓.
- **Negative caching**: NXDOMAIN(이름 없음) / NODATA(타입 없음) 응답도 cache. TTL은 zone SOA의 minimum 필드.

### 2.2 TTL 트레이드오프

| 항목 | TTL 짧게 (30~60s) | TTL 길게 (1day+) |
|---|---|---|
| Failover RTO | 빠름 (30s 단위) | 느림 (수 시간) |
| Auth NS 부하 | 높음 (cache miss 잦음) | 낮음 |
| Recursive cache hit rate | 낮음 | 높음 |
| P99 latency | 약간 ↑ (lookup 잦음) | 안정 |
| Blue-green / 동적 endpoint | 적합 | 부적합 |
| 정적 자원 | 과함 | 적합 |

권장: **정적 자원 1day, 동적/failover 60s, blue-green cutover 시 30s**.

### 2.3 DNS poisoning & Kaminsky (간단)

옛 공격: recursive가 cache miss 시 auth에 UDP 질의 → 공격자가 transaction ID(16bit) brute-force로 위조 응답 폭격 → cache 오염.

방어: **source port randomization**(16bit 추가 → 사실상 32bit), **0x20 encoding**(case echo), **DNSSEC**(서명 검증), **DoT/DoH**(채널 암호화).

운영 함정: 사내 DNSSEC 활성화 시 key rollover 실수로 SERVFAIL 폭주 → 점진 전환 필수.

---

## 3. DNS 진화 — UDP에서 DoH까지

```
UDP 53 (512B) → EDNS0 (>512B + TCP fallback) → DoT 853 (TLS) → DoH 443 (HTTPS) → DoQ (QUIC)
```

- **UDP 53 + 512B 제한**: 옛 fragment 회피. DNSSEC/EDNS 응답이 커지면 TCP fallback.
- **EDNS0** (RFC 6891): UDP buffer size 협상 (4096B 등). DNSSEC 전제 조건.
- **DoT (853)** / **DoH (443)**: 채널 암호화. DoH는 일반 HTTPS와 구별 불가 → 검열 회피 강.
- **DNSSEC vs DoT/DoH**: DNSSEC = 데이터 무결성(서명). DoT/DoH = 채널 암호화(누가 뭘 묻는지 숨김). 다른 layer.

운영 함정: DoH는 회사 내부 hostname 못 풀어서 enterprise에서 비활성화 정책 흔함.

---

## 4. GeoDNS / Latency / Anycast — 같은 hostname에 다른 답

DNS는 단순 lookup이 아니라 **같은 질문에 다른 답을 주는 dynamic resolution**. Auth NS가 사용자별로 다른 IP를 응답.

- **GeoDNS**: 사용자(또는 recursive resolver)의 IP geolocation 보고 region별 다른 IP. Route53 geolocation, Cloudflare. 한국 사용자는 ap-northeast-2 IP, 미국은 us-east-1 IP.
- **Latency-based** (Route53): AWS가 자체 측정한 RTT 기반 가장 빠른 region. 사용자 위치 ≠ 빠른 region일 수도 (네트워크 경로가 더 중요).
- **Weighted**: A/B test, canary용. weight 90/10이면 90%는 v1, 10%는 v2.
- **Failover**: primary health-check fail 시에만 secondary 응답.
- **ECS (EDNS Client Subnet, RFC 7871)**: recursive resolver가 client subnet을 auth에 전달 → auth가 진짜 client 위치 기반으로 응답. 8.8.8.8 같은 거대 anycast resolver가 GeoDNS와 잘 안 맞는 문제를 해결.

**Anycast vs GeoDNS** (자주 헷갈림):
- **GeoDNS**: 같은 hostname에 사용자별 다른 IP. **응답이 다르다**.
- **Anycast**: **같은 IP**를 여러 PoP에서 BGP로 광고. 응답은 같고 BGP가 가장 가까운 PoP으로 라우팅. 8.8.8.8, 1.1.1.1, Cloudflare가 대표.
- DNS는 UDP라 anycast 완벽 (state 없음). TCP는 경로 변경 시 RST 위험 → CDN은 PoP에서 TCP terminate 후 origin과는 별도 연결로 우회.

---

## 5. IP 라우팅 — 패킷이 인터넷을 가로지르는 경로

### 5.1 호스트 → gateway → ISP → BGP

```
[Host 192.168.1.10]
   │ routing table 조회: dst=142.250.196.132 → default → 192.168.1.1
   │
   ▼
[LAN ARP] "192.168.1.1의 MAC?" → broadcast → reply
   │
   ▼
[Default Gateway (router) — bb:bb:..]
   │ L3 IP header 그대로, L2 frame은 새로 만들어 다음 hop의 MAC으로
   │
   ▼
[ISP edge] → [Tier 2 ISP] → [Tier 1 backbone]
   │ 각 라우터마다 BGP AS path 보고 best path 선택
   │
   ▼
[목적지 AS — Google] → Anycast PoP → edge LB → 백엔드
```

<details>
<summary>📌 <b>Host / Gateway / ISP / LAN — 4개 용어 풀버전 (클릭)</b></summary>

### Host (호스트)
**네트워크에 연결된 끝단 장치(end node).** 사용자의 PC, 노트북, 스마트폰, 서버 등 데이터의 출발지·도착지가 되는 컴퓨터. RFC 1122 정의.

| | Host | Router |
|---|---|---|
| 역할 | 데이터의 시작·끝 | 데이터의 중계 (forward) |
| 예 | PC, 서버, 핸드폰 | 공유기, ISP 라우터, 백본 |
| OSI | L7까지 | L3까지 |

본문의 "Host 192.168.1.10" = 내 컴퓨터의 사설 IP. `192.168.x.x`는 사설망 IP 대역(RFC 1918). 공유기가 DHCP로 자동 할당. 외부 인터넷에선 안 보임(NAT로 공유기 공인 IP가 대신 나감).

### Gateway (게이트웨이)
**LAN을 외부 인터넷과 잇는 출구 라우터.** "default gateway"가 그것.

```
[당신의 집 LAN]
   PC, 노트북, TV, 스마트폰 등 host들
        │
        │ 외부행은 모두 여기로
        ▼
   192.168.1.1 (공유기 = default gateway)
        │
        ▼
   [ISP → 외부 인터넷]
```

실제 모습:
- **집/카페**: 공유기 (192.168.0.1, 192.168.1.1, 10.0.0.1)
- **회사**: 사내 라우터 또는 방화벽
- **AWS VPC**: NAT Gateway, Internet Gateway
- **데이터센터**: ToR(Top-of-Rack) 스위치 → aggregation 라우터

→ 본문의 "default → 192.168.1.1" = 외부행 모든 packet이 거치는 출구.

### ISP (Internet Service Provider)
**인터넷 연결 제공 사업자.** 한국 대표: KT, SK Broadband, LG U+.

3단계 계층:

```
Tier 1 (글로벌 백본)
  AT&T, NTT, Lumen(Level 3), Telia, Tata
  서로 무료(peering)로 트래픽 교환
  전 세계 어디든 직접 연결
       │
       │ Tier 2가 Tier 1에 돈 내고 transit 구매
       ▼
Tier 2 (지역/국가 ISP)
  KT, SK Broadband, LG U+ (한국)
       │
       ▼
Tier 3 (지역 소규모 ISP, 케이블 사업자)
       │
       ▼
[End user / 회사]
```

한국 사이트끼리는 **IX(Internet eXchange)**에서 ISP 간 직접 교환 → Tier 1 안 거침. 해외는 Tier 1 통과.

### LAN (Local Area Network)
**같은 switch/공유기에 묶인 컴퓨터들의 네트워크.** 같은 L2 broadcast domain, 같은 subnet.

```
[공유기 192.168.1.1]
   ├── 내 PC (192.168.1.10)
   ├── 노트북 (192.168.1.11)
   ├── 스마트폰 (192.168.1.12)
   └── 프린터 (192.168.1.13)

→ 이 5개 장치가 한 LAN.
   서로 broadcast 가능, 라우터 안 거치고 직접 통신.
   외부로 나갈 때만 gateway 통과.
```

ARP가 동작하는 범위 = LAN 안. 본문의 "LAN ARP" = LAN 안에서 ARP broadcast 질의.

</details>

<details>
<summary>📌 <b>Routing Table이 어디에 어떻게 저장되나 (클릭)</b></summary>

### 한 줄 결론

**Routing table = OS Kernel space의 RAM 안에 있는 자료구조** (Linux는 fib_trie). 부팅 시·DHCP·BGP daemon이 채우고, kernel TCP/IP stack이 매 packet 송신마다 조회. **디스크에 영구 저장 X (휘발성)**. 부팅 스크립트가 매번 다시 채움.

### 어디에 있나

```
[User space]
  브라우저, Java, bash, application들

═══════════════════════════════════
[Kernel space] ← 여기!
  ┌──────────────────────────────┐
  │ Kernel TCP/IP stack           │
  │  ┌────────────────────────┐  │
  │  │ FIB (Forwarding Info)  │  │ ← routing table 실체
  │  │ Linux: fib_trie        │  │   (LC-trie 자료구조)
  │  └────────────────────────┘  │
  └──────────────────────────────┘

═══════════════════════════════════
[Hardware] NIC / CPU / RAM
```

### 자료구조 — fib_trie

```
                  [root]
                /        \
           0...           1...
          /    \         /    \
       00...  01..    10..    11..
       ...
```

- IP를 bit 단위로 따라 내려가며 **Longest Prefix Match**
- 최악 32 hop (IPv4)으로 정답 도출
- 매 packet마다 ns 단위 조회 가능

```bash
$ cat /proc/net/fib_trie | head    # 실제 자료구조 dump
$ ip route show                    # 사람 친화 출력 (netlink로 kernel 조회)
```

### 어떻게 채워지나 — 4가지 출처

1. **Direct routes** — NIC 활성화 시 자동 (`192.168.1.0/24 dev eth0`)
2. **DHCP** — 부팅 시 공유기에서 받음 (default gateway가 여기로 들어옴)
3. **수동 설정** — `ip route add 10.20.0.0/16 via ...` (재부팅하면 사라짐)
4. **라우팅 protocol** — BGP/OSPF daemon이 학습한 routes를 kernel에 push (ISP/대기업 라우터)

### 라이프사이클

```
[전원 OFF]   routing table 비어 있음 (RAM 자체 꺼짐)
    │
[부팅]
    │ kernel 빈 routing table 초기화
    │ NIC 활성화 → direct route 자동 추가
    │ DHCP → default gateway route 추가
    │ BGP daemon (있으면) → routes push
    │
[정상 운영]  packet 송신마다 fib_trie lookup (ns 단위)
    │
[종료/재부팅]  routing table 소실 → 부팅 스크립트가 다시 채움
```

### 영구 저장이 필요하면?

부팅 스크립트에 명시 (디스크에 있는 건 "설정 파일"이지 routing table 자체 아님):
- `/etc/network/interfaces` (Debian/Ubuntu 옛)
- `/etc/sysconfig/network-scripts/route-eth0` (RHEL/CentOS)
- NetworkManager / systemd-networkd config

### 조회/수정 방법

```bash
$ ip route show           # 현대 표준 (netlink 사용)
$ cat /proc/net/route     # 옛 방식 (16진수)
$ route -n                # BSD 스타일
$ sudo ip route add ...   # 추가
$ sudo ip route del ...   # 삭제
```

### 자주 묻는 함정

- **"재부팅하면 라우트 사라짐"** → RAM에 있어서 그럼. 부팅 스크립트 필요.
- **"공유기도 routing table 있나?"** → 있음. 작은 embedded Linux. WAN쪽 default route, LAN쪽 direct route.
- **"BGP full table은?"** → Tier 1 라우터는 약 95만 routes(2024) 보유. fib_trie 효율로 lookup 여전히 ns 단위.
- **"routing table 깨지면?"** → default route 누락이 가장 흔한 사고. `ip route show`에 default 없으면 외부 접속 불가.

### 비유

- **Routing table 자체** = kernel의 즉시 사용 가능한 "지도" (RAM에 펼쳐진)
- **설정 파일** = 그 지도를 그리는 "설계도" (디스크에 저장)
- 부팅마다 설계도 보고 지도 다시 그림

</details>

<details>
<summary>📌 <b>BGP / AS — Border Gateway Protocol과 Autonomous System (클릭)</b></summary>

### AS (Autonomous System)
**자체 라우팅 정책을 가진 네트워크 단위.** ISP, 대기업, 클라우드 각각이 AS. 고유 번호(ASN)로 식별.

```
AS 4766    KT
AS 9318    SK Broadband
AS 17858   LG U+
AS 15169   Google
AS 16509   AWS
AS 32934   Meta (Facebook)
AS 13335   Cloudflare
```

### BGP (Border Gateway Protocol)
**AS 간에 "이 IP 대역은 우리가 책임진다" 정보를 주고받는 라우팅 프로토콜.** 인터넷 전체 라우팅이 BGP 위에서 굴러감. RFC 4271 (1989~).

### BGP가 하는 일

```
[Google AS 15169 광고]
"142.250.0.0/15 대역은 우리(AS 15169)가 책임진다"
     │
     │ BGP UPDATE로 인접 AS에 전파
     ▼
AS 3356(Lumen) → AS 4766(KT) → ...
     │
     │ 각 AS의 라우터가 BGP 테이블에 저장:
     ▼
142.250.0.0/15 → next-hop = Lumen 라우터 IP
              → AS_PATH = [3356, 15169]
              → "Lumen 통해서 Google 가면 됨"
```

### Best Path 선택 순서

여러 경로가 있을 때 우선순위:
1. **Local preference** (자기 회사 정책)
2. **AS_PATH 짧은 것** (거치는 AS 수 적은 게 우선)
3. Origin type / MED / eBGP vs iBGP / IGP metric / Router ID

### eBGP vs iBGP

- **eBGP**: 다른 AS 간 BGP. ISP끼리 prefix 교환.
- **iBGP**: 같은 AS 내 라우터 간 BGP. 외부에서 받은 정보를 내부에 전파.
  - full-mesh 필요 → route reflector / confederation으로 완화.

### BGP 사고 사례

- **Pakistan-YouTube (2008)**: 파키스탄 ISP가 YouTube 차단하려고 "YouTube IP는 우리"로 잘못 광고 → 전 세계 YouTube 트래픽이 파키스탄으로 → YouTube 다운.
- **Facebook (2021-10-04)**: BGP 광고 철회 실수 → Facebook 도메인이 인터넷에서 사라짐 → 6시간 다운.
- **방어**: **RPKI** (Resource Public Key Infrastructure)로 BGP origin 서명 → hijack 차단.

### 본문의 흐름

> "각 라우터마다 BGP AS path 보고 best path 선택"

= 각 ISP/백본 라우터가 자기 BGP 테이블에서 "142.250.196.132로 가려면 AS_PATH 짧은 경로" 선택 → 다음 hop 결정.

</details>

### 5.2 ARP — L3와 L2 사이의 풀

DNS는 hostname→IP만 해결. **IP만으로는 Ethernet frame을 못 만든다** (L2는 MAC으로만 forwards). 그래서 IP 결정 직후 ARP가 끼어든다.

```
[L3 IP packet]
   src IP: 192.168.1.10
   dst IP: 142.250.196.132
        │
[L2 Ethernet frame을 만들기 위해]
   dst MAC: ?? ← ARP로 알아내야 함
        │
[ARP request — broadcast]
   "Who has 192.168.1.1?" (default gateway, 외부 destination이라서)
        │
[ARP reply — unicast]
   "192.168.1.1 is at bb:bb:.."
        │
[Ethernet frame 송신]
   src MAC: aa:aa:..   dst MAC: bb:bb:..  (★ gateway MAC)
   src IP : 192.168.1.10   dst IP : 142.250.196.132  (그대로!)
        │
   hop마다 L2 frame은 새로 만들어지고 L3 IP는 그대로 → next-hop MAC만 바뀐다.
```

ARP cache: `ip neigh show` / `arp -a`. TTL 보통 60s~4분. 상태: REACHABLE / STALE / INCOMPLETE.

ARP spoofing: 공격자가 위조 reply로 자기 MAC을 gateway로 등록 → MITM. 방어: DHCP snooping, dynamic ARP inspection, IPv6의 NDP+SEND.

### 5.3 BGP AS path 선택 (간단)

각 AS가 자기 prefix를 광고. best path 선택 순서:
1. local preference (자기 정책)
2. AS_PATH 짧은 것
3. origin type / MED / eBGP vs iBGP / IGP metric / router ID

함정: AS prepend로 traffic engineering, BGP hijack (Pakistan-YouTube 2008 같은 사고).

### 5.4 Anycast & ECMP

- **Anycast**: 같은 IP를 여러 PoP에서 BGP 광고. 가장 가까운 PoP이 응답. PoP 죽으면 BGP withdraw → 다른 PoP이 흡수.
- **ECMP** (Equal-Cost Multi-Path): 같은 dst에 같은 비용 경로 N개일 때 5-tuple `(src_ip, src_port, dst_ip, dst_port, protocol)` hash로 분산. 같은 hash = 같은 경로 → flow-level consistency.

### 5.5 BGP AS path 추가 디테일

- AS = Autonomous System. 자체 라우팅 정책 가진 네트워크 (ISP, 대기업).
- eBGP = 다른 AS 간, iBGP = 같은 AS 내 라우터 간.
- iBGP는 full-mesh 필요 → route reflector / confederation으로 완화.
- BGP hijack: 잘못된 prefix를 자기 것으로 광고 (사고 또는 공격). RPKI로 방어.

### 5.6 traceroute 원리

IP TTL을 1, 2, 3... 으로 증가시키며 패킷 송신. 각 라우터가 TTL=0이면 ICMP Time Exceeded 응답 → 그 라우터 IP가 노출됨. 마지막 hop은 ICMP Echo Reply 또는 dst의 응답으로 끝남.

```
TTL=1 → router1이 ICMP Time Exceeded 회신 → router1 IP
TTL=2 → router2가 ICMP Time Exceeded 회신 → router2 IP
...
TTL=N → 최종 dst가 응답 → 도착
```

**함정**: 일부 라우터는 ICMP rate limit으로 응답 안 함 → `* * *` 표시. 방화벽이 ICMP 차단 시 `tcptraceroute` (TCP SYN 사용)나 `mtr` (실시간 loss/jitter)로 우회.

---

## 6. CDN — Edge가 origin 앞에 서는 이유

```
[User] → [CDN edge PoP (Anycast IP)]
              │
              │ cache hit → 즉시 응답
              │ cache miss → ↓
              │
         [Origin shield] (regional cache, origin 부하 흡수)
              │
              │ miss → ↓
              ▼
         [Origin server]
```

동적 컨텐츠도 CDN 통과 이유 (4가지):
1. **TCP termination at edge** — 사용자↔edge RTT 짧음 → handshake/slow start 빠름. edge↔origin은 keepalive 재사용.
2. **TLS termination at edge** — 비싼 handshake가 가까운 곳에서.
3. **Smart routing** — Cloudflare Argo, Akamai SureRoute의 private backbone이 공용 BGP보다 빠름.
4. **DDoS + WAF** — 악성 트래픽을 origin 전에 차단.

**Cache key + Vary**: 같은 URL이라도 `Vary: Accept-Encoding`이면 압축별 다른 entry. 안티패턴: `Vary: User-Agent`(무한 variation), `Vary: Cookie`(사용자별).

---

## 7. 운영 시나리오

### 7.1 P99 spike — DNS lookup 매번 일어남

**증상**: 평균 latency 10ms 미만인데 P99만 200~500ms spike. APM에서 "첫 요청 느리고 다음은 빠름" 패턴.

**원인 hierarchy**:
- HTTP client에 connection pool 없음 → 매 요청마다 new connection → 매 요청 DNS lookup.
- JVM `networkaddress.cache.ttl` 경계 시점에 일제히 re-lookup.
- K8s `ndots:5` 함정 (아래).

**진단**:
```bash
dig +stats www.google.com | grep "Query time"  # resolver 자체 응답
tcpdump -i any -n udp port 53 -tttt            # stub→recursive 패킷
# JVM: async-profiler로 InetAddress.getByName 호출 빈도
```

**해결**:
- HTTP client pool 설정 (`PoolingHttpClientConnectionManager`, JDK11+ `HttpClient`).
- JVM 옵션 `-Dnetworkaddress.cache.ttl=60 -Dnetworkaddress.cache.negative.ttl=0`.
- K8s에서 NodeLocal DNSCache 도입.

**JVM `networkaddress.cache.ttl` 함정**:
- JDK8: security manager 없으면 `-1` (forever!) → AWS RDS failover IP 못 따라감.
- JDK9+: 기본 30초. 권장은 60s + negative.ttl=0.
- HikariCP는 idle connection 유지 → DB failover 시 새 IP 못 옮겨감. `maxLifetime` 짧게 (30분 이하) 설정해 강제 재연결.

### 7.2 Kubernetes CoreDNS NXDOMAIN 폭증

**원인**: Pod의 `/etc/resolv.conf`:
```
search default.svc.cluster.local svc.cluster.local cluster.local example.com
options ndots:5
```

`ndots:5` = hostname에 dot 5개 미만이면 **search 도메인 먼저 시도**. `api.payment.com/v1` (dot 3개) 호출 시:
1. `api.payment.com.v1.default.svc.cluster.local` → NXDOMAIN
2. `...svc.cluster.local` → NXDOMAIN
3. `...cluster.local` → NXDOMAIN
4. `...example.com` → NXDOMAIN
5. `api.payment.com.v1.` → 진짜 시도
6. × IPv4+IPv6 = **10번 시도**.

**해결**:
- FQDN 명시 (`api.payment.com.` ← trailing dot).
- `dnsConfig: ndots:2` + searches 1개로 줄임.
- NodeLocal DNSCache.

### 7.3 Route53 health-check failover RTO

```
T+0    : primary endpoint 장애
T+90   : Route53 health-check unhealthy (30s × 3회)
T+90~  : DNS 응답이 secondary로 전환
T+150  : 사용자 측 recursive resolver cache 만료 (TTL 60s 가정)
T+180  : 브라우저/앱 캐시까지 만료
   ↓
RTO ≈ 90s + TTL + 앱 캐시 ≈ 2~3분
```

**RTO 단축**:
- health-check fast (10s) + threshold 2 → 약 20~30s.
- TTL 60s 유지 (더 줄이면 NS 부하 폭증).
- 앱 측 DNS cache TTL 명시적 단축.
- **진짜 무중단은 L7 retry + circuit breaker + multi-region client routing**. 다 합쳐도 DNS-only RTO 30~60s가 한계.

대안: **multi-A record + client retry** (TCP timeout 수 초), GSLB, **Anycast + BGP withdraw** (BGP convergence 수 초~분).

### 7.4 시나리오 매트릭스 — 증상 → 진단

| 증상 | 진단 명령 | 가능한 원인 |
|---|---|---|
| 매 요청 DNS lookup | `tcpdump -i any -n udp port 53` | HTTP client keep-alive 안 됨, JVM cache TTL 짧음 |
| Failover 후 옛 IP 계속 시도 | `dig +short`, JVM `inetaddr.ttl` | DNS cache 너무 김, HikariCP idle conn |
| P99 lookup 수초 spike | `dig +tries=1 +time=2` | resolver overload, UDP 손실, NXDOMAIN 폭증 |
| 한 region만 느림 | `traceroute` / `mtr` | 특정 AS hop 문제, peering link 포화 |
| CoreDNS NXDOMAIN 폭증 | `kubectl logs coredns` | ndots:5 + search 도메인 5개 |
| Anycast 연결 중 끊김 | TCP RST 추적 | PoP 경로 변경 (TCP anycast 함정) |
| SERVFAIL 가끔 | `dig +dnssec` | DNSSEC chain 깨짐, auth NS timeout |
| 사용자 PC만 옛 IP | `chrome://net-internals/#dns` | 브라우저/OS cache, HSTS pinning |
| ARP cache 잘못된 MAC | `ip neigh show` | ARP spoofing, gateway 교체 후 GARP 누락 |
| Route53 failover 늦음 | Route53 health-check 콘솔 | 30s × 3 + DNS TTL + 클라이언트 cache |

---

## 8. 꼬리질문 5개

1. **TTL 30s vs 1day 트레이드오프?** → failover RTO vs NS 부하 vs cache hit rate. 정적은 1day, 동적은 60s, blue-green은 30s.
2. **BGP AS_PATH 선택 순서?** → local pref → AS_PATH 길이 → origin type → MED → eBGP/iBGP → IGP → router ID.
3. **Anycast의 TCP 함정?** → 연결 중 BGP 경로 변경 → 다른 PoP에 패킷 도착 → TCP state 없음 → RST. DNS(UDP)는 무관.
4. **DoT/DoH vs DNSSEC?** → DoT/DoH는 채널 암호화(누가 무엇을 묻는지 숨김). DNSSEC은 응답 데이터 서명(위조 방지). 다른 layer, 같이 써야 완전.
5. **DNS 캐싱 사상이 다른 어디서?** → CPU L1/L2/L3, HTTP Cache-Control, ARP cache, TLB. 공통 원리: **빈도 높은 lookup을 가까이 cache + TTL/invalidation으로 일관성 절충**. negative caching = "없음도 답"이라는 사상.

---

## 9. 도구 한 줄 요약

```bash
# DNS
dig +trace example.com                   # 4계층 추적
dig @8.8.8.8 +short example.com          # 특정 resolver
nslookup example.com 1.1.1.1

# 라우팅
ip route show / netstat -rn              # 호스트 라우팅표
traceroute / mtr -n example.com          # 경로 + 실시간 loss
tcptraceroute example.com 443            # 방화벽 회피

# BGP
bgp.he.net                               # AS path / origin AS

# 패킷
tcpdump -i any -n udp port 53            # DNS 캡처
ip neigh show / arp -a                   # ARP cache
```

---

## 10. 면접 답변 워크플로우

| 질문 | 진입 가지 | 인접 확장 |
|---|---|---|
| "DNS는 어떻게 동작?" | ① 4계층 | ② TTL / ④ GeoDNS |
| "8.8.8.8은 왜 빠르죠?" | ⑤ Anycast | BGP / recursive |
| "TTL 짧게 잡으면?" | ② TTL | ⑦ 운영 / failover |
| "CDN 어떻게 동작?" | ⑥ CDN | Anycast / GeoDNS |
| "BGP가 뭔가?" | ⑤ IP 라우팅 | Anycast / ECMP |
| "DoH/DoT 왜 등장?" | ③ 진화 | poisoning / DNSSEC |
| "K8s DNS 느려요" | ⑦ 운영 (CoreDNS) | resolver 계층 |
| "JVM DNS cache?" | ⑦ 운영 | TTL |

**답변 템플릿**: 루트 한 문장 → 진입 가지 키워드 3개 → 상대 표정 보고 인접 가지 확장.

예시 — "DNS는 어떻게 동작?":
> "DNS는 단일 서버가 아니라 **4계층 cache hierarchy + recursive resolver 모델**. 클라이언트는 브라우저 cache → OS resolver → /etc/hosts → stub 순서로 보고, miss면 `/etc/resolv.conf`의 recursive (ISP/8.8.8.8)에 UDP 53 질의. recursive가 miss면 root → TLD → authoritative 3단 referral. 각 단계 TTL 동안 cache. TTL은 짧으면 failover 빠르지만 NS 부하 ↑, 길면 stale. 실무 진단은 `dig +trace`, `tcpdump udp port 53`, JVM의 `networkaddress.cache.ttl` + K8s `ndots:5` 점검."

---

## 11. 학습 체크리스트

백지에서 다음을 할 수 있어야 마스터:

- [ ] 0장 마인드맵을 1분 내 그릴 수 있다 (anchor + 5가지)
- [ ] DNS 4계층 (브라우저 → OS → stub → recursive → root → TLD → auth)을 그림으로
- [ ] root / TLD / authoritative의 책임 분리 (root·TLD는 referral만, auth만 최종 답)
- [ ] TLD = Top-Level Domain, gTLD(.com .org .io) vs ccTLD(.kr .jp .uk) 차이
- [ ] `dig +trace` 출력을 phase 0~3으로 해설
- [ ] A/AAAA/CNAME/MX/NS/SOA/SRV/CAA 한 줄 용도
- [ ] CNAME apex 함정과 ALIAS/flattening
- [ ] TTL 짧게/길게 트레이드오프 + SOA minimum이 negative TTL인 이유
- [ ] Kaminsky 원리 + source port randomization + DNSSEC chain
- [ ] UDP 53 → EDNS0 → DoT/DoH/DoQ 진화 이유
- [ ] GeoDNS vs Latency vs Anycast 차이 (응답이 다른가, IP가 같은가)
- [ ] 호스트 라우팅표 → gateway → ISP → backbone 흐름
- [ ] ARP로 IP→MAC 매핑하는 이유 (L2/L3 경계)
- [ ] BGP AS_PATH best path 선택 순서 7단
- [ ] Anycast TCP 함정 + BGP withdraw로 failover
- [ ] ECMP 5-tuple hash와 flow consistency
- [ ] traceroute의 TTL trick
- [ ] CDN이 동적 컨텐츠도 통과시키는 4가지 이유
- [ ] DNS lookup 매번 일어나는 문제 진단 (tcpdump, dig)
- [ ] JVM `networkaddress.cache.ttl` 함정 + HikariCP `maxLifetime` 관계
- [ ] CoreDNS NXDOMAIN 폭증의 ndots:5 메커니즘
- [ ] Route53 health-check failover RTO 계산 (90s + TTL + 앱 cache)

---

## 12. 다음 단계

- → [03. OSI 7 Layers and TCP/TLS](./03-osi-7-layers-and-tcp-tls.md): IP를 얻은 다음 TCP/TLS가 어떻게 끼어드나
- → [04. Load Balancer Deep Dive](./04-load-balancer-deep-dive.md): L4/L7 LB
- → [08. DB Connection and JDBC](./08-db-connection-and-jdbc.md): DB endpoint hostname도 동일 DNS 문제

---

## 📌 약자 사전 — 본문에 등장하는 모든 줄임말

본문 흐름을 안 끊으려고 한 곳에 모음. 처음 보는 약자는 여기서 확인 후 본문으로.

### DNS 관련

| 약자 | 풀네임 | 한 줄 정의 |
|---|---|---|
| **DNS** | Domain Name System | hostname↔IP를 풀어주는 분산 시스템 (RFC 1034/1035, 1983) |
| **NS** | NameServer | DNS 레코드를 보유한 서버. record 종류 이름도 됨 (`NS record`) |
| **TLD** | Top-Level Domain | `.com .org .kr` 등 도메인 가장 오른쪽 부분 |
| **gTLD** | general TLD | `.com .org .net .io .app` — ICANN 산하 registry |
| **ccTLD** | country-code TLD | `.kr .jp .uk` — 각 나라 관리 (`.kr`은 KISA) |
| **FQDN** | Fully Qualified Domain Name | trailing dot까지 명시한 절대 도메인 (`www.google.com.`) |
| **TTL** | Time To Live | cache 유효 시간 (초). DNS와 IP 둘 다 사용 |
| **SOA** | Start Of Authority | zone의 권한·minimum TTL 등 메타데이터 record |
| **A / AAAA** | Address (IPv4) / IPv6 | hostname → IPv4 / IPv6 매핑 record |
| **CNAME** | Canonical Name | hostname → 다른 hostname alias record |
| **MX** | Mail eXchanger | 도메인의 메일 서버 record |
| **SRV** | Service | service discovery (Kerberos, SIP, K8s headless) |
| **CAA** | Certification Authority Authorization | 인증서 발급 가능 CA 제한 |
| **NXDOMAIN** | Non-eXistent Domain | "이름 없음" 응답 |
| **NODATA** | No Data | "이름은 있는데 그 타입 없음" 응답 |
| **EDNS0** | Extension Mechanisms for DNS | UDP buffer 크기 협상 등 (RFC 6891) |
| **DNSSEC** | DNS Security Extensions | DNS 응답에 서명 → 위조 방지 |
| **DoT / DoH / DoQ** | DNS over TLS / HTTPS / QUIC | DNS 채널 암호화 (853 / 443 / QUIC) |
| **ECS** | EDNS Client Subnet | recursive가 client subnet을 auth에 전달 (RFC 7871) |
| **HSTS** | HTTP Strict Transport Security | 브라우저 강제 HTTPS, preload list |
| **IDN** | Internationalized Domain Name | 비-ASCII 도메인. Punycode로 ASCII 변환 |

### 라우팅 관련

| 약자 | 풀네임 | 한 줄 정의 |
|---|---|---|
| **IP** | Internet Protocol | L3 라우팅 프로토콜. IPv4 / IPv6 |
| **TCP / UDP** | Transmission Control / User Datagram Protocol | L4 신뢰성 있는 / 비신뢰 전송 |
| **ARP** | Address Resolution Protocol | IP→MAC 매핑 (L3↔L2 경계, RFC 826) |
| **NDP** | Neighbor Discovery Protocol | IPv6의 ARP 대체 |
| **GARP** | Gratuitous ARP | 자기 IP의 MAC을 broadcast로 알림 (failover 시) |
| **MAC** | Media Access Control | NIC의 48-bit 하드웨어 주소 |
| **NIC** | Network Interface Card | 네트워크 카드 (=랜카드) |
| **MTU** | Maximum Transmission Unit | 한 frame의 최대 byte (보통 1500) |
| **TTL** (IP) | Time To Live | IP packet의 hop counter, 매 hop -1 |
| **ICMP** | Internet Control Message Protocol | 진단 protocol (ping, traceroute) |
| **NAT** | Network Address Translation | 사설 IP ↔ 공인 IP 변환 |
| **LAN / WAN** | Local / Wide Area Network | 로컬망 / 광역망 |

### BGP / AS 관련

| 약자 | 풀네임 | 한 줄 정의 |
|---|---|---|
| **AS** | Autonomous System | 자체 라우팅 정책을 가진 네트워크 (ISP, 대기업) |
| **ASN** | AS Number | AS 식별 번호 (예: Google AS15169) |
| **BGP** | Border Gateway Protocol | AS 간 라우팅 protocol (RFC 4271) |
| **eBGP / iBGP** | external / internal BGP | AS 간 / AS 내 BGP |
| **IGP** | Interior Gateway Protocol | AS 내부 라우팅 (OSPF, IS-IS) |
| **MED** | Multi-Exit Discriminator | BGP path selection 시 외부에 알리는 선호도 |
| **RPKI** | Resource Public Key Infrastructure | BGP hijack 방어용 prefix 서명 |
| **ECMP** | Equal-Cost Multi-Path | 동일 비용 경로 N개 5-tuple hash로 분산 |
| **Anycast** | (약자 아님) | 같은 IP를 여러 PoP에서 BGP로 광고 |

### 인프라/CDN 관련

| 약자 | 풀네임 | 한 줄 정의 |
|---|---|---|
| **CDN** | Content Delivery Network | edge PoP에 캐시해 사용자 가까이 응답 |
| **PoP** | Point of Presence | CDN/ISP의 지역 거점 |
| **GSLB** | Global Server Load Balancing | 지역 단위 LB (Route53 geolocation, anycast IP) |
| **WAF** | Web Application Firewall | OWASP Top 10 등 L7 공격 차단 |
| **MITM** | Man-In-The-Middle | 중간자 공격 |
| **RTO** | Recovery Time Objective | 장애 → 복구까지 목표 시간 |
| **RTT** | Round Trip Time | packet 왕복 시간 |

### 기관/제품

| 약어 | 풀네임 | 비고 |
|---|---|---|
| **ICANN** | Internet Corporation for Assigned Names and Numbers | gTLD/IP 자원 관리 비영리 |
| **IANA** | Internet Assigned Numbers Authority | ICANN 산하, root zone 관리 |
| **KISA** | Korea Internet & Security Agency | `.kr` 관리 한국 기관 |
| **Verisign** | (회사명) | `.com` `.net` registry 운영 |
| **RFC** | Request For Comments | IETF 표준 문서 (예: RFC 1035 = DNS) |
| **IETF** | Internet Engineering Task Force | 인터넷 표준 제정 기구 |

---

## 13. 참고 (RFC + 외부 자료)

- RFC 1034/1035 — DNS 본질
- RFC 2308 — Negative caching / SOA minimum
- RFC 4033~4035 — DNSSEC
- RFC 6891 — EDNS0
- RFC 7858 / 8484 — DoT / DoH
- RFC 7871 — EDNS Client Subnet (ECS)
- RFC 4271 — BGP-4
- RFC 826 — ARP
- RFC 9460 — HTTPS/SVCB record (ALPN/ECH 협상)
- JEP 142 — JDK DNS TTL 변경 이력
- bgp.he.net — Hurricane Electric BGP looking glass
- Cloudflare Learning Center / Route53 routing policy 문서 / CoreDNS docs

---

> 라우터 hop별 packet 변화 세부, BGP AS path 선택 풀버전, DNSSEC chain validation, Maglev consistent hashing, `dig +trace` phase 0~3 raw 출력 한 줄씩 해설, ARP 6.6.1~6.6.6 세부(GARP/Proxy ARP/ARP storm/NDP/spoofing 방어 사례)와 같은 풀버전은 git commit **7e4a6c8** (`Network 01 round 2`) 참조.
