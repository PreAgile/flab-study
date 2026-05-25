# 04. Load Balancer Deep Dive — "트래픽 분산"은 시작일 뿐

> "LB는 트래픽 분산하는 장치다"라고 답하면 입문자.
> "LB는 클라이언트↔백엔드 사이 reverse proxy로서 분산 + SSL 종단 + health + rate limit + sticky + WAF + DDoS + observability를 동시에 처리하는 데이터플레인 hub. L4는 TCP 헤더 per-connection routing, L7은 HTTP payload per-request routing이고 그 대가로 SSL termination이 필수다" 라고 말할 수 있어야 다음 단계.

---

## 0. 한 줄 anchor + 목차

> **"LB = 클라이언트와 백엔드 사이 reverse proxy. L4(TCP per-connection) vs L7(HTTP per-request)로 갈리고, 분산 외에도 SSL 종단·health·rate limit·sticky·WAF·DDoS·observability를 한 hub에서 처리한다."**

면접에선 이 한 문장 → 해당 가지 → 키워드 3개 순으로 펼친다.

**짧은 목차**:
1. 위치 — Reverse Proxy 본질 + 4단계 진화 + **LB는 layer마다 존재 (DNS/CDN/Cloud/Cluster/Mesh/Client)** ⭐ 신설
2. L4 vs L7 + NLB/ALB 매핑
3. 분산 알고리즘 6종 + P2C / Consistent Hash 디테일
4. 부가 책임 8가지 (SSL/Health/Rate/Sticky/Routing/WAF/DDoS/Observability)
5. Observability 메트릭 정리
6. 운영 시나리오 3개 (shallow health 함정 / sticky 불균형 / draining 부족 503)
7. 제품 비교 (HAProxy/Nginx/Envoy/ALB/NLB/Cloudflare)
8. Multi-AZ / Failover / GSLB
9. 꼬리질문 7개 (layered LB 분류 축 포함)

---

## 1. LB의 위치 — Reverse Proxy 본질

### 1.1 Forward vs Reverse

```
[Forward Proxy] — 클라이언트 측
   Client → Proxy → Internet → Server
   회사 방화벽 / VPN / censorship 우회

[Reverse Proxy] — 서버 측 ← LB가 여기
   Client → Internet → Proxy → Server
   서버 IP 숨김 + SSL/캐싱/압축/인증/분산을 한곳에
```

LB는 "분산" 하나가 아니라 **"서버 군집 앞단의 통합 entrypoint"** 라는 추상화가 본질. 백엔드는 "혼자인 듯" 살고 LB가 SSL/retry/rate limit/관측을 다 흡수한다.

### 1.2 진화 4단계

| 세대 | 시기 | 형태 | 한계 → 다음 세대 트리거 |
|---|---|---|---|
| 1 | 1990s | DNS Round-Robin (A 레코드 여러 개) | TTL 무시 + health 없음 + sticky 불가 |
| 2 | 2000s | Hardware LB (F5 BIG-IP, Cisco ACE) — ASIC wire-speed | 비쌈(수억) + vendor lock-in |
| 3 | 2010s | Software LB (Nginx, HAProxy) — x86 + epoll | per-box throughput, update 어려움 |
| 4 | 2020s~ | Service Mesh (Envoy sidecar + Istio/Linkerd control plane) | 복잡도, debugging hell |

진화 트리거: x86이 충분히 빨라지고 Linux epoll이 C10K를 해결 → ASIC 가성비 폭락 → SW LB로. 마이크로서비스에서 LB가 "엣지 한 대"가 아니라 "서비스마다 sidecar"가 필요해짐 + mTLS/traffic policy를 인프라 레이어로 → Mesh.

### 1.3 LB 있을 때 vs 없을 때

| 책임 | LB 없이 | LB 있을 때 |
|---|---|---|
| 백엔드 IP 공개 | 직접 노출 | 숨김 |
| SSL cert | 모든 백엔드에 배포·갱신 | LB 한 곳 |
| 백엔드 추가/제거 | DNS 변경 + TTL 대기 | LB에 등록만 |
| 장애 격리 | 죽은 백엔드도 트래픽 받음 | health check로 격리 |
| rate limit | 백엔드가 알아서 | LB에서 통합 |
| A/B test | 코드 분기 | LB traffic split |
| DDoS | 백엔드 직격 | LB가 흡수 |

"SPoF 위험"이라는 오해는 multi-AZ active-active로 해소. 실제론 **여러 위험을 한곳에 모아 관리 가능한 형태로 격리**시키는 장치다.

### 1.4 LB는 layer마다 존재한다 — "어떤 LB냐"의 분류 축

면접에서 "LB는 어떻게 동작하나요?"에 답할 때 가장 흔한 함정: **"LB"를 단일 제품인 것처럼 답하는 것**. 실제로 한 요청은 **4~5개의 LB layer**를 거친다. 각 layer가 다른 책임을 갖는다.

#### 한 요청이 거치는 LB layer

```
[브라우저]
   │
   │ DNS lookup
   ▼
┌─────────────────────────────────────────────┐
│ ① DNS LB                                      │  Route 53, Cloudflare DNS, NS1
│   - GeoDNS / Latency-based / Weighted        │  layer: DNS protocol (UDP 53)
│   - multi-region failover                    │  TTL 기반, 즉시 failover 어려움
└─────────────────────────────────────────────┘
   │
   ▼
┌─────────────────────────────────────────────┐
│ ② Edge / CDN                                  │  Cloudflare, Akamai, Fastly, CloudFront
│   - 정적 캐시, WAF, DDoS, edge TLS           │  layer: L7 (anycast)
│   - 전 세계 PoP에 분산                       │  본업은 캐싱, LB 역할 겸함
└─────────────────────────────────────────────┘
   │
   ▼
┌─────────────────────────────────────────────┐
│ ③ Cloud LB (Regional)                         │  AWS ALB/NLB, GCP LB, Azure LB
│   - SSL term, path/host routing              │  layer: L4 또는 L7
│   - target group health check                │  한 region 내 multi-AZ 분산
│   - WAF 통합                                  │
└─────────────────────────────────────────────┘
   │
   ▼
┌─────────────────────────────────────────────┐
│ ④ Cluster-internal LB                         │  K8s Service (kube-proxy/IPVS)
│   - Service ClusterIP NAT                    │  Ingress Controller (Nginx/Traefik)
│   - Pod 간 routing                           │  layer: L4 (kube-proxy), L7 (Ingress)
└─────────────────────────────────────────────┘
   │
   ▼
┌─────────────────────────────────────────────┐
│ ⑤ Service Mesh sidecar                        │  Istio (Envoy), Linkerd, Consul
│   - per-pod L7 control                       │  layer: L7
│   - mTLS, retry, circuit breaker             │  pod마다 sidecar
│   - trace span 생성                           │
└─────────────────────────────────────────────┘
   │
   ▼
┌─────────────────────────────────────────────┐
│ ⑥ Application-level (client-side) LB          │  Spring Cloud LoadBalancer, gRPC client
│   - downstream service 호출 시               │  layer: 코드 안
│   - retry, circuit breaker (Resilience4j)    │
└─────────────────────────────────────────────┘
   │
   ▼
[Backend pod]
```

→ **한 요청이 6개의 LB 역할을 거친다.** 각 layer가 다른 책임을 진다.

#### 분류 축 3가지 — 시니어 답변의 핵심

**축 ①: OSI Layer** (L4 vs L7)
- L4: TCP/UDP 헤더만, per-connection (NLB, HAProxy L4, IPVS, kube-proxy)
- L7: HTTP payload까지, per-request (ALB, Nginx, Envoy, Ingress)

**축 ②: 배치 위치** (어디서 동작하나)
- DNS layer / Edge(CDN) / Regional cloud LB / Cluster-internal / Pod sidecar / Application 안

**축 ③: 운영 주체** (누가 운영하나)
| 주체 | 예 | 특징 |
|---|---|---|
| Managed (cloud) | ALB, NLB, GCP LB | 운영 부담 ↓, vendor lock-in |
| Self-hosted OSS | Nginx, HAProxy, Envoy | 유연 ↑, 운영 부담 |
| CDN provider | Cloudflare, Akamai, Fastly | LB + cache + WAF + DDoS 통합 |
| Hardware | F5 BIG-IP, Citrix ADC | 고성능, 비쌈, 옛 엔터프라이즈 |
| Service Mesh | Istio, Linkerd | pod 단위 sidecar |
| App library | Spring Cloud, gRPC client-side | 코드 안 내장 |

#### CDN이 LB인가 — 헷갈리는 경계

CDN(Cloudflare/CloudFront/Fastly)은 **본업이 정적 캐싱**이지만 캐시 miss 시 origin으로 forward하면서 **L7 LB 역할도 한다**:
- ✅ Health check (origin이 살았는지)
- ✅ Failover (다른 origin으로)
- ✅ SSL termination
- ✅ Rate limit, WAF
- ✅ Path-based routing (일부)
- ❌ Sticky session (캐시 일관성과 충돌)
- ❌ Internal cluster routing

→ "CDN은 edge layer에서 LB 역할도 하는 통합 제품" — 본업과 별도로 LB 카테고리에 들어감.

#### 시니어 답변 톤

❌ 모호: "LB는 트래픽을 분산하고 SSL termination 합니다"

✅ 시니어: "LB는 단일 제품이 아니라 layer마다 분산 배치된 추상 역할입니다. 우리 환경은 Cloudflare(edge) → ALB(region) → Nginx Ingress(cluster) → Istio sidecar(pod) 4 layer가 쌓여 있고, 각 layer가 다른 책임을 갖습니다. 어떤 layer 얘기인지에 따라 답이 달라집니다."

→ **분류 축을 먼저 명확히 하고 들어가는 게 시니어 톤**.

---

## 2. L4 vs L7 — 정확히 무엇이 다른가

### 2.1 시야 다이어그램

```
[L4의 시야]                       [L7의 시야]
┌─────────────┐                   ┌─────────────┐
│ Ethernet    │                   │ Ethernet    │
│ IP          │                   │ IP          │
│ TCP/UDP     │ ★ 여기까지        │ TCP         │
╞═════════════╡                   │ TLS         │ ← LB가 풀어냄
│ TLS (암호화)│                   │ HTTP        │ ★ method/path/header/
│ HTTP        │                   │  method     │   cookie/body까지
│ payload     │                   │  path       │
└─────────────┘                   │  headers    │
   passthrough만 가능              │  body       │
                                  └─────────────┘
                                  SSL termination 필수
```

### 2.2 핵심 차이 표

| | L4 | L7 |
|---|---|---|
| **보는 것** | TCP/UDP 헤더 (5-tuple) | HTTP 전체 (path/header/cookie/body) |
| **routing 단위** | per-connection | per-request |
| **SSL** | passthrough만 | termination 필수 |
| **HTTP path/header 분기** | 불가 | 가능 |
| **속도** | 매우 빠름 (wire-speed) | 느림 (parsing + TLS) |
| **AWS 대응** | NLB | ALB |
| **언제** | 게임/TCP/UDP, 극저 latency, 고정 IP | 일반 웹/API, gRPC, WebSocket |

### 2.3 시니어 함정 — "같은 connection의 모든 요청이 같은 백엔드?"

```
[L4: per-connection]
Client ───TCP conn #1 (5-tuple A)──→ LB ──→ Backend X
        └───── 이 conn의 모든 byte → 무조건 X ────┘
                                     X가 down 돼도 이 conn은 X에 (TCP RST)

[L7: per-request]
Client ───TCP conn #1───→ LB ──→ Backend X
              │ GET /a   →           → X
              │ GET /b   →           → Y    ← 같은 conn 다른 백엔드
              │ GET /c   →           → X
```

L4=Yes (5-tuple hash, 한 conn = 한 백엔드 무조건). L7=No — LB가 HTTP 경계를 parsing하니 LB↔백엔드에 별도 upstream keepalive pool을 두고 각 요청을 적절한 백엔드로 dispatch. HTTP/2 multiplex와 gRPC에선 한 conn 안 stream마다 분기 가능 — 이게 ALB가 gRPC를 지원하는 이유다.

### 2.4 NLB vs ALB 실전 매핑

| | NLB (L4) | ALB (L7) |
|---|---|---|
| layer | TCP/UDP | HTTP/HTTPS, gRPC, WebSocket |
| client IP 보존 | 자연스러움 | X-Forwarded-For 필요 |
| 고정 IP | 가능 (EIP attach) | 불가 (DNS 이름만) |
| 처리량 | 수백만 conn/s | 수만 req/s |
| 레이턴시 | 매우 낮음 | NLB+수 ms |
| WAF | 직접 X (앞에 ALB 둬야) | AWS WAF 직접 |

실무에선 **ALB(WAF/L7) + NLB(앞단 고정 IP)** 또는 단독 사용. gRPC는 ALB의 HTTP/2 지원 위에서.

---

## 3. 분산 알고리즘 — 어떻게 고르나

### 3.1 6종 비교표

| 알고리즘 | 핵심 동작 | 분산 LB 친화 | sticky | 언제 |
|---|---|---|---|---|
| **Round Robin** | 순서대로 (Weighted = 가중치) | ★★★ | × | 균질 트래픽, 단순 |
| **Least Connections** | active conn 가장 적은 곳 | △ (state 필요) | × | 요청 시간 들쭉날쭉 |
| **IP Hash** | `hash(client_ip) % N` | ★★★ | ○ (취약) | 단순 sticky |
| **Consistent Hash** | ring 위 배치, N 바뀌어도 1/N만 재배치 | ★★★ | ◎ | cache, shard, sticky |
| **Maglev** | Consistent hash + 미리 만든 lookup table (O(1)) | ★★★ | ◎ | Google Cloud LB, 대규모 글로벌 |
| **P2C (Power of Two Choices)** | 무작위 2개 중 더 한가한 쪽 | ★★★ | × | **모던 default** (Envoy/Linkerd/Finagle) |

**시니어 답변 한 줄**: "기본은 P2C 또는 Least Conn. sticky가 필요하면 Consistent Hash. 단순/균질하면 RR."

### 3.2 P2C가 의외로 강한 이유

max queue length가 random은 log N인데 P2C는 log log N (Mitzenmacher 1996). Least Conn처럼 정확하면서 **전역 state 불필요** — 분산 LB cluster에서 각 LB가 자기 view만으로 독립 결정. 구현도 `random.pick()` 2번 + 비교 1번이 끝. 그래서 Twitter Finagle, Envoy, Linkerd가 default로 채택.

### 3.3 Consistent Hash가 필요한 이유

단순 `hash(key) % N`은 N이 바뀌면 매핑 대부분 깨짐 → cache miss 폭발. Ring 구조는 백엔드 추가/제거 시 그 노드 영역만 재배치(1/N 정도). 대규모 cache cluster sticky의 핵심. **Maglev**(Google 2016)는 ring 대신 미리 큰 lookup table을 만들어 O(1) lookup — 백엔드 변경 시 table 재계산. Google Cloud LB / Envoy 채택.

---

## 4. 부가 책임 8가지 — "분산"이 전부가 아니다

| 책임 | 핵심 한 문장 |
|---|---|
| **① 트래픽 분산** | 3장 알고리즘으로 백엔드 선택 |
| **② SSL/TLS termination** | LB에서 풀어 cert 중앙 관리 + 백엔드 CPU 절약 + observability + ALPN 중앙화 |
| **③ Health check** | shallow(`/live`, process)와 deep(`/ready`, 의존성)로 분리 + passive(실제 5xx rate) + panic threshold |
| **④ Rate limiting** | per-IP/key/user/endpoint. Token bucket(burst) vs Leaky bucket(평탄화). 분산 환경은 Redis 중앙 또는 N/M 할당 |
| **⑤ Sticky session** | cookie/IP/consistent-hash. 가능하면 stateless로 외부화(Redis/JWT) — WebSocket·multipart upload·레거시 JSESSIONID·로컬 캐시 4경우에만 |
| **⑥ Routing** | path/host/header 기반. 마이크로서비스 분기, API versioning, multi-tenant, canary |
| **⑦ WAF** | OWASP Top 10(SQLi/XSS/CSRF/path traversal/RCE). ModSecurity + CRS, AWS WAF. Count Mode → tune → enforce(false positive 관리) |
| **⑧ DDoS 방어** | L3/L4 volumetric은 edge(Cloudflare/Shield/anycast scrubbing)에서. L7(Slowloris/HTTP Flood/Cache busting)은 in-front LB에서. LB는 last line이지 first line이 아님 |
| **⑨ Observability** | 모든 트래픽이 지나가는 hub → access log, RPS, P50/P90/P99, upstream_duration, 5xx rate, healthy upstream count, tls handshake duration. X-Request-Id / traceparent로 분산 추적 |

**Sticky session 4가지 정당한 경우**: (1) WebSocket — conn 자체가 stateful, 한 conn은 한 백엔드. (2) 파일 업로드 multipart — 같은 파일 chunk가 같은 백엔드로 가야 합치기 쉬움. (3) 레거시 JSESSIONID — 세션 메모리에 들고 있는 옛날 앱. (4) 로컬 캐시 — 한 사용자 데이터를 한 백엔드가 캐싱. Sticky 부작용: 백엔드 부하 불균형(IP 분포에 의존), 장애 시 그 세션만 손실, rolling deploy 어려움(옛 버전에 묶임). **시니어 권장**: 가능하면 stateless로 만들고 sticky를 피해라.

### 4.1 SSL termination 3 모드

```
(A) Passthrough (L4)
    Client ═══TLS═══→ LB ═══TLS═══→ Backend
    LB는 packet만 전달. 백엔드가 cert 보유 + CPU 부담.

(B) Termination
    Client ═══TLS═══→ LB ───plain───→ Backend
    LB가 TLS 풀고 plain HTTP로. cert 중앙, 백엔드 CPU 절약.
    단점: 내부 구간 평문 (내부망 안전 가정).

(C) Re-encryption (mTLS internal)
    Client ═══TLS═══→ LB ═══TLS'═══→ Backend
    LB가 풀고 새 TLS로 다시. zero-trust / PCI-DSS.
    단점: TLS 두 번 비용.
```

**SSL을 LB에서 풀어야 하는 4가지 이유**: (1) cert 중앙 관리(백엔드 100대 일일이 배포·갱신 불필요), (2) 백엔드 CPU 절약(TLS handshake는 비쌈), (3) observability(평문이라야 access log/WAF/body 검사), (4) HTTP/2 ALPN negotiation 중앙화(클라이언트와 h2 합의, 백엔드는 h1로 받아도 됨). SNI(ClientHello에 hostname 평문) 덕에 한 LB IP + cert 여러 개(multi-tenant) 가능. **ECH(Encrypted Client Hello)**가 SNI까지 암호화하는 차세대. Cert rotation은 옛날 수동 1년짜리 → 현재 **Let's Encrypt + ACME 프로토콜**로 90일 자동(cert-manager/Caddy/대부분 LB가 통합).

### 4.2 Health check 3 layer

```
(A) L4 (TCP)        LB → SYN → Backend → SYN-ACK  ★ 통과
    "TCP listen 중이면 OK" — 너무 얕음

(B) L7 (HTTP)       LB → GET /health → 200 OK     ★ 통과
    app process 살아있음

(C) Deep            LB → GET /health/deep
                       → app이 DB/Redis/Kafka ping
                       ← 200 (모두 OK) 또는 503 (하나라도 죽음)
    실제 의존성까지 검증
```

**Shallow vs Deep 트레이드오프**:

| | Shallow `/live` | Deep `/ready` |
|---|---|---|
| 검증 범위 | app process | + DB/cache/외부 의존 |
| false negative | ↑ (의존성 죽어도 통과) | ↓ |
| false positive | ↓ | ↑ (DB hiccup → 전체 unhealthy) |
| 운영 함정 | "health 통과인데 5xx" | "DB 깜빡임에 전체 down" |

**표준**: `/health/live`(shallow) + `/health/ready`(deep). Kubernetes liveness/readiness probe와 동일 사상. Active(주기 ping) + Passive(실제 5xx rate)를 같이.

**Panic threshold (Envoy)**: healthy/total < 50%면 모두 healthy로 간주(fail open). 의존성 hiccup으로 80% unhealthy 판정나면 남은 20%에 폭주 → cascading failure. "다 죽었으면 그냥 다 쓰자."

**Circuit breaker 통합**: LB가 백엔드별로 회로 차단(Hystrix 패턴을 LB가 흡수). Envoy `outlier_detection`: 연속 5xx 또는 latency 이상치 감지하면 일정 시간 격리(eject).

**Deep health 함정 해결**: 결과를 5~10초 cache(매번 DB ping 부담 ↓) + partial degradation(DB 죽어도 read-only 응답하면 health 통과).

### 4.3 Rate limit 알고리즘과 분산 환경

```
[Token Bucket]
- bucket 용량 N tokens
- 일정 비율로 refill (10 token/s)
- 요청마다 token 1개 소비, 빈 bucket이면 reject
→ burst 허용 (bucket 가득 차있으면 N개 즉시 처리)

[Leaky Bucket]
- queue에 요청 쌓임, 일정 비율로 leak
- queue 가득 차면 reject
→ 강제 평탄화, burst 흡수 없음
```

**분산 LB 함정**: instance 여러 대면 각자 counter 따로 → 실제 N배 통과. 해결은 **Redis 중앙 store**(느림) 또는 **각 LB에 N/M 할당**(대략). AWS ALB는 직접 안 하고 AWS WAF rate-based rules에 위임. Nginx는 `limit_req_zone` (IP 기반 leaky bucket). Envoy는 local rate limit + global rate limit(외부 RLS gRPC service). Cloudflare는 edge에서.

### 4.4 Connection draining (rolling deploy의 생명선)

```
[문제]                        [해결: Draining]
1. 백엔드 X에 새 버전 배포    1. X를 "draining" 표시
2. ASG/k8s가 X 제거 + SIGTERM 2. LB는 X에 새 요청 안 보냄
3. X 즉시 종료                3. X는 진행 중 요청 완료 대기
4. LB가 보내던 요청 → reset      (drain timeout 30~60s)
5. 클라이언트 → 503           4. timeout 내 못 끝낸 건 cut, X 종료
```

**해결 set**: `deregistration_delay`(AWS 기본 300s), 백엔드 SIGTERM 핸들러로 새 요청 거절 + 진행 중 완료(Spring Boot `server.shutdown=graceful`), Kubernetes `preStop` hook으로 readiness false + sleep. **시니어 표준**: `deregistration_delay = 백엔드 p99 × 2~3`. 너무 짧으면 잘림, 너무 길면 deploy 지연.

WebSocket 같은 long-lived는 drain timeout 안에 못 끝냄 → close frame 보내 graceful close → 클라이언트 exponential backoff reconnect(Slack/Discord 방식).

### 4.5 Backend keepalive — TLS handshake 비용 회피

요청마다 LB↔Backend 새 TCP + TLS handshake면 작은 요청에 handshake 비용이 더 큼(수십 ms) → 5xx 폭증의 흔한 원인. LB는 백엔드와 persistent conn pool을 유지해 요청 N개를 conn 1개로 재사용. Nginx `upstream { keepalive 32; keepalive_timeout 60s; keepalive_requests 1000; }`. Envoy는 `circuit_breakers`로 max_connections/max_pending_requests 제어.

HTTP/2 multiplex는 한 conn = 다중 stream → 요청 100개를 conn 1개로. LB에서 클라이언트 h2 ↔ 백엔드 h1 변환도 흔함(ALB 기본). TCP의 HoL blocking을 회피하려면 HTTP/3(QUIC) — UDP 기반이라 stream별 독립.

### 4.6 Routing & Canary 짧게

L7 LB는 path/host/header 기반 라우팅 가능 → 마이크로서비스 분기, API versioning(`/v1/`은 옛, `/v2/`는 새), multi-tenant(host별), canary(header 기반). Canary는 `hash(user_id) % 100 < 5` 같은 **deterministic split**이 핵심 — 단순 weighted random이면 같은 사용자가 새로고침마다 버전 바뀌어 UX 카오스. Istio VirtualService는 weight + header match 둘 다 지원. Blue-green은 빠른 rollback이 강점이지만 두 환경 동시 유지로 비용 2배.

### 4.7 WAF false positive 관리

ModSecurity + OWASP CRS는 정규식 rule 수천 개라 정상 요청도 차단 가능(한국어 본문에 SQL 키워드 정당 포함 등). 절차: **Count Mode 먼저**(차단 X, log만) → 통계 분석(rule ID별 trigger 빈도) → 정상 패턴 분류 → Exception rule(특정 endpoint body 검사 skip, IP whitelist) → Enforcement 전환 → 지속 모니터링. ML 기반(AWS Bot Control, Cloudflare ML)은 정적 rule보다 false positive ↓.

### 4.8 DDoS layer별 방어

```
L3/L4 (volumetric, edge에서 막아야)
- SYN Flood:    SYN Cookies(kernel), SYN proxy(LB)
- UDP/ICMP Flood: rate limit, blackhole, scrubbing center
→ anycast로 전 세계 PoP에 분산(Cloudflare/CloudFront/Shield)

L7 (application, in-front LB에서)
- Slowloris:    천천히 conn 유지 → client request timeout, max conn per IP
- HTTP Flood:   정상처럼 보이는 GET 폭격 → rate limit, captcha, JS challenge
- Cache busting: 매번 다른 query string → query string 정규화/무시
```

"L7 DDoS는 in-front LB로 막을 수 있지만 volumetric L3/L4는 edge(anycast scrubbing) 없이는 못 막는다. 백엔드 in-front LB는 last line이지 first line이 아님."

---

## 5. Observability — LB가 측정의 black box를 깬다

LB는 모든 트래픽이 지나가는 hub → 자연스러운 observability point.

| 메트릭 | 의미 | 진단 단서 |
|---|---|---|
| `request_count` (RPS) | 트래픽 패턴 | spike/drop 식별 |
| `request_duration` P50/P90/P99 | 응답 분포 | tail latency |
| `upstream_duration` | LB↔백엔드만 | LB 자체 오버헤드 분리 |
| `upstream_connect_time` | 새 conn 맺기 비용 | 큼 → keepalive pool 부족 |
| `tls_handshake_duration` | TLS cost | 큼 → session resumption 미적용 |
| `4xx_rate` | client error | bad request, auth 실패 |
| `5xx_rate` | server error | 백엔드 장애 |
| `healthy_upstream_count` | 살아있는 백엔드 수 | health check 상태 |
| `connection_count` | 동시 conn | 풀 포화 |

**Tracing**: LB가 incoming request에 trace ID 부여(또는 통과). X-Request-Id(단순), X-B3-TraceId(Zipkin), **traceparent(W3C, 현대 표준)**. 백엔드가 이 ID를 log에 남기면 LB log ↔ 백엔드 log ↔ DB log 매핑 가능.

```nginx
# Nginx — X-Request-Id 주입
proxy_set_header X-Request-Id $request_id;
log_format main '$request_id $remote_addr "$request" $status $upstream_response_time';
```

**P99 진단 핵심 3가지**:
1. `request_duration` vs `upstream_duration` 차이 → LB 자체 오버헤드.
2. 백엔드별 `upstream_duration` 분포 → 1대만 outlier인지 모두 느린지.
3. `upstream_connect_time` 큼 → keepalive pool 부족 → 매번 새 conn.

---

## 6. 운영 시나리오 — 실전 진단

### 6.1 시나리오 1 — "LB health는 통과인데 사용자는 5xx"

**증상**: ALB target health = healthy, 그런데 access log에 5xx 다수.

**원인**: Shallow health 함정. `/health`는 200 반환하지만 백엔드 내부에서 DB connection pool 고갈, downstream 호출 실패.

**진단 절차**:
```bash
# (1) 백엔드 메트릭 — DB pool / downstream
curl backend/metrics | grep -E "(hikari|dbcp).*active"
# health endpoint와 실제 logic의 분리도 확인

# (2) LB access log — upstream_response_time, retry
# (3) 백엔드 에러 log
tail -f /var/log/app/error.log | grep -E "5[0-9]{2}|Timeout|Pool"

# (4) JVM 상태 (Full GC 빈도 의심)
jstat -gc <pid> 1s
```

**해결**:
1. `/health/ready`를 deep check로 — DB ping, Redis ping, 외부 의존 정상성. Cache(5~10초) + partial degradation 같이.
2. Passive health 추가 — Envoy `outlier_detection`(연속 5xx 또는 latency 이상치 자동 격리), AWS ALB target group healthy/unhealthy threshold.
3. Circuit breaker로 downstream 격리(DB 죽으면 read-only 응답).

### 6.2 시나리오 2 — "Backend 1대에만 트래픽 몰림 (sticky 불균형)"

**증상**: 백엔드 5대 중 1대만 CPU 90%, 나머지는 한가.

**원인 후보**:
- **Sticky session 잘못 설정** — 일부 power user가 한 백엔드에 묶임.
- **IP Hash + NAT** — 회사/캠퍼스 사용자가 같은 NAT IP → 한 백엔드로.
- **Consistent Hash 불균형** — virtual node 수가 적어 ring 분포 편향.
- **Long-lived connection** — WebSocket/gRPC stream은 새 conn만 분산되고 기존 conn은 한쪽에 누적.

**진단**:
```bash
# 백엔드별 활성 conn / RPS 비교
for backend in b1 b2 b3 b4 b5; do
    echo -n "$backend: "
    ssh $backend "ss -tn state established | wc -l"
done

# ALB는 target별 RequestCount 메트릭
aws cloudwatch get-metric-statistics \
  --namespace AWS/ApplicationELB \
  --metric-name RequestCountPerTarget ...
```

**해결**:
1. 가능하면 sticky 끄고 stateless로(세션은 Redis/JWT).
2. Consistent Hash면 virtual node 수 ↑ — Envoy `minimum_ring_size`.
3. WebSocket은 max connection per backend 제한 + drain 시 강제 끊어 재분산 유도.
4. NAT 함정은 cookie-based sticky 또는 user_id-based Consistent Hash로 교체.

### 6.3 시나리오 3 — "Rolling deploy 시 503 폭증"

**증상**: 인스턴스 교체할 때마다 503 1~3%.

**원인**: Connection draining 미설정 또는 너무 짧음. 인스턴스 즉시 종료 → 진행 중 요청 connection reset.

**진단**:
```bash
# ALB target group deregistration delay 확인
aws elbv2 describe-target-group-attributes \
  --target-group-arn <arn> | grep deregistration_delay
# 기본 300s. 너무 짧으면 5xx, 너무 길면 deploy 지연.

# Spring Boot graceful shutdown 설정 유무
grep -E "server.shutdown|timeout-per-shutdown-phase" application.yml
```

**해결 절차**:
1. `deregistration_delay` = 백엔드 p99 × 2~3 (기본 300s).
2. 백엔드 SIGTERM 핸들러 — Spring Boot `server.shutdown=graceful` + `spring.lifecycle.timeout-per-shutdown-phase=30s`.
3. Kubernetes `preStop` hook으로 readiness false + sleep.
4. Idempotent GET은 LB retry policy로 다른 백엔드 시도(POST/PUT은 안 됨 — 중복 처리 위험).
5. WebSocket은 close frame 보내 graceful close → 클라이언트 exponential backoff reconnect.

---

### 6.4 (보너스) P99 spike 진단 메모

평소 P99 100ms인데 갑자기 1000ms, P50은 정상이면 → 백엔드 1대 outlier. 백엔드별 p99 비교(Datadog/Grafana) → 1대만 튀면 그 백엔드의 JVM Full GC(`jstat -gc <pid> 1s`)/DB lock contention(jstack)/disk hiccup 의심. 모두 튀면 downstream(DB slow query, 외부 API). 해결은 Envoy `outlier_detection`(연속 5xx 또는 latency 이상치 자동 격리), ALB target group `unhealthy_threshold` 낮게, 근본 원인(GC tuning, query 최적화) 처리. **LB 메트릭 핵심**: `upstream_connect_time` 큼 → keepalive pool 부족, `tls_handshake_duration` 큼 → session resumption 미적용, 백엔드별 `upstream_response_time` 분포 → outlier 식별.

### 6.5 학습 체크리스트 (요약)

- [ ] L4 vs L7 시야 다이어그램 + "같은 conn 다른 백엔드?" 정확히 답
- [ ] NLB vs ALB 매핑(고정 IP / WAF / 처리량 / latency / gRPC)
- [ ] 분산 알고리즘 6종(RR/LC/IP Hash/Consistent Hash/Maglev/P2C)과 default 권장
- [ ] SSL termination 3 mode와 각 선택 기준(PCI-DSS는 re-encryption)
- [ ] Health shallow/deep 분리 + panic threshold(fail open) + Envoy outlier detection
- [ ] Rate limit token vs leaky + 분산 환경(Redis 중앙 vs N/M 할당)
- [ ] Sticky 안티패턴 이유 + 어쩔 수 없는 4경우(WS/upload/JSESSIONID/cache)
- [ ] Connection draining 표준값(p99 × 2~3) + Spring Boot graceful + k8s preStop
- [ ] P99 진단 메트릭 3가지(request vs upstream / upstream_connect_time / outlier)
- [ ] 제품 비교표 HAProxy/Nginx/Envoy/ALB/NLB + Cloudflare 위치

---

## 7. 제품 비교

| | HAProxy | Nginx | Envoy | AWS ALB | AWS NLB |
|---|---|---|---|---|---|
| **Layer** | L4/L7 | L7 (L4 일부) | L7 (L4 일부) | L7 only | L4 only |
| **동적 설정** | Runtime API | reload (Plus 유료) | xDS API (탁월) | API | API |
| **HTTP/2 / gRPC** | ○ | ○ | ◎ native | ○ | TLS만 |
| **Service mesh** | × | × | ◎ (Istio sidecar) | × | × |
| **WAF** | × | ModSecurity | filter chain | AWS WAF 통합 | × |
| **DDoS L3/L4** | × | × | × | △ (Shield 연동) | △ |
| **운영 비용** | self-host | self-host | self-host + control plane | managed | managed |
| **러닝 커브** | 중 | 낮 | 높 | 낮 | 낮 |
| **언제** | 고성능 L4/L7 on-prem | 정적 + reverse proxy + L7 LB | mesh, gRPC, 동적/programmable | AWS 환경 L7 표준 | 게임/극저 latency/고정 IP |

**Cloudflare**는 edge 카테고리(anycast + DDoS + WAF + CDN + LB 통합) — 글로벌 트래픽과 volumetric DDoS 흡수가 필요할 때. AWS Shield는 ALB/NLB 앞 DDoS 방어 매니지드 서비스.

**제품 선택 기준**: AWS 환경 + 일반 웹/API면 ALB(+WAF). 고정 IP나 게임/극저 latency면 NLB. 마이크로서비스/gRPC/service mesh면 Envoy(+Istio). On-prem 고성능이면 HAProxy. 정적 파일 + reverse proxy + L7 LB를 한 곳에서면 Nginx. 글로벌 + DDoS면 앞단에 Cloudflare.

---

## 8. Multi-AZ / Failover / GSLB

```
                    DNS (Route53)
            ┌─────────────┴─────────────┐
            ▼                           ▼
        AZ-A LB (active)            AZ-B LB (active)
        ┌─┴─┐                       ┌─┴─┐
     B1 B2 B3                    B4 B5 B6
```

AWS ALB는 기본 multi-AZ(ENI를 여러 AZ에). **Cross-Zone**: ON이면 AZ-A LB가 AZ-B 백엔드에도 보냄(균형 ↑, inter-AZ 비용 ↑). OFF면 비용 ↓.

**Active-Passive**(LB-1 active + LB-2 standby, VRRP/keepalived로 heartbeat, 죽으면 virtual IP takeover) vs **Active-Active**(둘 다 트래픽, DNS 다중 A 또는 BGP anycast). 모던 표준은 Active-Active.

**GSLB**: 지역 단위 분산. Geo/Latency DNS(Route53)로 가까운 region 반환 또는 Anycast IP(Cloudflare/Global Accelerator)로 BGP가 가까운 곳으로. DNS TTL은 resolver caching 때문에 즉시 failover 어려움 — Anycast가 더 빠른 failover.

---

## 9. 꼬리질문

**Q1. L4 LB와 L7 LB 차이? 같은 connection의 모든 요청이 같은 백엔드?**
> L4는 TCP 헤더만 보고 5-tuple로 per-connection routing — 같은 conn의 모든 byte는 무조건 같은 백엔드. SSL passthrough만. L7은 HTTP payload를 풀어 per-request routing — 같은 conn 안 요청 #1과 #2가 다른 백엔드로 갈 수 있고 SSL termination 필수. HTTP/2 multiplex와 gRPC에서 stream마다 분기 가능한 게 ALB가 gRPC를 지원하는 이유.

**Q2. 분산 알고리즘 5개 비교, 시니어 권장 default는?**
> RR(균질), Least Conn(들쭉날쭉 + state 비용), IP Hash(NAT 함정), Consistent Hash(cache/shard/sticky의 표준, 1/N만 재배치), P2C(무작위 2개 중 한가한 쪽). 시니어 default는 **P2C** — log log N max queue, 전역 state 불필요, Envoy/Linkerd/Finagle 채택. Sticky 필요하면 Consistent Hash.

**Q3. SSL termination을 LB에서 왜? 3 모드는 언제?**
> Cert 중앙 관리 + 백엔드 CPU 절약 + observability + HTTP/2 ALPN 중앙화. **Passthrough**는 백엔드가 cert 직접 들 때(mTLS client cert 검증). **Termination**은 일반적 LB. **Re-encryption**은 zero-trust/PCI-DSS — LB↔백엔드도 mTLS.

**Q4. "LB health는 다 통과인데 사용자는 5xx 본다." 진단 절차?**
> Shallow health 함정 의심. 백엔드 메트릭(HikariCP active, downstream latency, Full GC) + LB access log(upstream_response_time, 5xx per backend) + 백엔드 에러 log 순. 해결은 `/health/ready` deep check + passive health(Envoy outlier_detection) + circuit breaker.

**Q5. Rolling deploy 503 폭증, 어디부터 손보나?**
> Connection draining 설정부터. `deregistration_delay = p99 × 2~3`(기본 300s), 백엔드 SIGTERM 핸들러로 새 요청 거절 + 진행 중 완료, k8s `preStop` hook으로 readiness false + sleep, idempotent GET은 retry 정책으로 다른 백엔드 시도(POST/PUT은 중복 위험). WebSocket은 close frame + 클라이언트 reconnect 패턴.

**Q6. "LB가 뭐냐"고 물으면 ALB? Cloudflare? Nginx? Istio? 어떤 기준으로 답하나?**
> "LB"는 단일 제품이 아니라 layer마다 분산 배치된 추상 역할이라 먼저 분류 축을 명확히 합니다. 한 요청이 보통 ① DNS LB(Route 53) → ② CDN/Edge(Cloudflare) → ③ Cloud LB(ALB) → ④ Cluster Ingress(Nginx) → ⑤ Service Mesh sidecar(Istio) → ⑥ Client-side(Spring Cloud) 6 layer를 거치고, 각 layer가 다른 책임(WAF/DDoS, SSL termination/path routing, mTLS/retry, downstream selection)을 갖습니다. 분류 축은 (1) OSI layer L4/L7, (2) 배치 위치 edge/regional/cluster/pod/app, (3) 운영 주체 managed/OSS/CDN. CDN은 본업이 캐싱이지만 edge에서 LB 역할을 겸하는 통합 제품. 면접 질문이 어느 layer를 가리키는지 되묻거나 우리 환경의 layered LB 구조를 먼저 그리는 게 시니어 답변입니다.

**Q7 (패턴 통찰). LB의 사상이 다른 어디서 반복되나?**
> "공유 자원 앞에 mediator를 두어 정책을 일원화" — Database의 connection pool(HikariCP가 DB 앞 LB), JVM의 TLAB(Eden 앞 per-thread buffer로 lock 회피), Kubernetes Ingress(cluster 외부 LB), Service Mesh sidecar(서비스 간 LB), CDN(origin 앞 edge), API Gateway(마이크로서비스 앞 통합 entrypoint). 모두 "여러 클라이언트 ↔ 여러 서버" 사이 mediator로 분산·격리·관측을 한곳에 모으는 패턴. 시니어가 "왜 LB가 필요한가"를 답할 때 이 추상 패턴까지 짚으면 한 수 위.

---

## 10. 마무리 — 한 문장 다시

> "LB는 클라이언트와 백엔드 사이의 reverse proxy로, **L4(TCP per-connection) vs L7(HTTP per-request)** 두 layer로 갈리고, 분산 알고리즘(default는 P2C, sticky는 Consistent Hash) 외에도 **SSL 종단·health(shallow/deep + passive + panic threshold)·rate limit·sticky·WAF·DDoS·observability**를 한 hub에서 처리한다. 운영 함정은 셋만 기억: ① shallow health로 5xx 실종, ② sticky/NAT 불균형, ③ draining 부족으로 rolling deploy 503. 시니어는 항상 'edge(volumetric DDoS)는 anycast, in-front LB(L7 정교한 정책)는 마지막 line'이라는 layer를 분리해서 본다."

> **Maglev hashing 풀버전, sticky session 불균형 케이스 풀버전, WAF false positive 사례, panic threshold 풀버전은 git 7e4a6c8 참조.**

---

## 다음 단계

- → [05. Nginx Internals](./05-nginx-internals.md): event loop / epoll / worker / upstream pool
- → [06. Tomcat Internals](./06-tomcat-internals.md): Acceptor → Poller → Executor
- → [07. Connection Pools Master](./07-connection-pools-master.md): 모든 풀의 위치와 한계

## 참고

- HAProxy: https://docs.haproxy.org/
- Nginx: https://nginx.org/en/docs/
- Envoy: https://www.envoyproxy.io/docs/envoy/latest/intro/arch_overview/arch_overview
- AWS ELB: https://docs.aws.amazon.com/elasticloadbalancing/
- Mitzenmacher — Power of Two Choices (1996): https://www.eecs.harvard.edu/~michaelm/postscripts/tpds2001.pdf
- Maglev (Google 2016): https://research.google/pubs/maglev-a-fast-and-reliable-software-network-load-balancer/
- OWASP Top 10: https://owasp.org/www-project-top-ten/
- W3C Trace Context: https://www.w3.org/TR/trace-context/
