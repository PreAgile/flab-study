# 02. DNS & Routing — hostname이 IP가 되고, 그 IP로 가는 패킷이 인터넷을 가로지르는 길

> "DNS는 hostname을 IP로 바꾸는 시스템" 까지는 입문.
> "브라우저 캐시 → OS resolver → stub → recursive → root → TLD → authoritative 4계층 cache hierarchy + TTL/negative caching + 그 IP는 호스트 라우팅 → gateway → ISP → BGP AS path → ECMP/Anycast/CDN edge를 거친다" 까지 답해야 시니어.

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

### 1.2 stub vs recursive

- **stub**: OS 안의 미니 client. 책임 없음. "재귀로 풀어줘" 한 번 던지고 결과만 받음.
- **recursive**: root→TLD→auth를 자기가 다 묻고 답을 합성. ISP DNS, 8.8.8.8(Google), 1.1.1.1(Cloudflare)이 대표.

### 1.3 root → TLD → authoritative

- **Root NS**: 전세계 13개 letter (a~m.root-servers.net). 실제로는 anycast로 수백 노드.
- **TLD NS**: `.com`, `.org`, `.kr` 등 — Verisign 등이 운영.
- **Authoritative NS**: 도메인 소유자가 지정 (Route53, Cloudflare, NS1, 자체 운영 BIND).

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
