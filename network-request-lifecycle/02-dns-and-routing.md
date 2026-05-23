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

### 9.7 시나리오 매트릭스

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

### 9.8 도구 한 줄 요약

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
