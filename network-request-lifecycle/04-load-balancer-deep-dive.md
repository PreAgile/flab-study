# 04. Load Balancer Deep Dive — "트래픽 분산"은 시작일 뿐

> "LB는 트래픽 분산하는 장치다"라고 답하면 입문자.
> "LB는 클라이언트↔백엔드 사이에 끼어드는 reverse proxy로서 분산 알고리즘 + SSL 종단 + health check + rate limit + sticky session + WAF + DDoS 흡수 + observability + canary routing + connection pooling을 동시에 담당하는 데이터플레인 hub이고, L4는 TCP 헤더만 보고 per-connection으로 routing하며, L7은 HTTP payload를 풀어 per-request routing을 하면서 그 대가로 SSL termination을 수행한다" 라고 말할 수 있다면 그 다음 단계.
> 이 챕터의 목표는 후자다.

---

## 이 문서의 사용법

이 문서는 **면접용 마인드맵**을 따라 선형으로 펼친 구조다.

1. **0장 마인드맵을 먼저 외운다** — 루트 한 문장 + 6개 가지 + 각 키워드 3개.
2. **1~6장을 순서대로 학습한다** — 각 장이 마인드맵의 한 가지에 대응.
3. **7장 운영 장애 패턴**으로 시니어 진단 사고 점검.
4. **8장 비교표**(HAProxy/Nginx/Envoy/ALB/Cloudflare).
5. **9장 꼬리질문**으로 깊이 점검.

---

## 0. 마인드맵 — 면접 종이에 그릴 그림

### 루트 한 문장 (anchor)

> **"Load Balancer는 클라이언트와 백엔드 사이에 끼어드는 reverse proxy로, L4(TCP 헤더 per-connection)와 L7(HTTP payload per-request) 두 layer로 갈리고, 분산 알고리즘 외에도 SSL 종단·health check·rate limit·sticky session·WAF·DDoS·observability를 한 hub에서 처리한다."**

이 한 문장에서 모든 답변이 출발한다.

### 6개 가지 — 순서를 외운다

```
                  [ROOT: LB = 분산 + 보안 + 관측 + 종단 hub]
                                    │
       ┌─────────┬──────────────┬───┴───┬──────────────┬─────────┐
       │         │              │       │              │         │
      ① 위치    ② L4 vs L7     ③ 분산    ④ 부가책임    ⑤ 운영    ⑥ 비교
   (역사 진화) (Layer 구분)    알고리즘   (8가지)      (시나리오)  (제품군)
       │         │              │       │              │         │
   ┌───┼───┐  ┌──┼──┐       ┌───┼───┐ ┌─┼─┐──┐    ┌────┼────┐ ┌──┼──┐
  DNS  HW  SW Conn  Req     RR  LeastConn SSL Health  P99   Drain HAProxy
  F5   Nginx Envoy  per-conn per-req  Hash  Rate Sticky  503 spike  Nginx
  Mesh             SSL term unable                                  Envoy
                   하나로                                            ALB/NLB
                                                                   Cloudflare
```

### 가지별 핵심 키워드

| 가지 | 키워드 1 | 키워드 2 | 키워드 3 |
|---|---|---|---|
| **① 위치 · 진화** | reverse proxy 본질 | DNS LB → HW(F5) → SW(Nginx) → Mesh | 클라이언트와 백엔드의 경계 |
| **② L4 vs L7** | L4 per-connection | L7 per-request + SSL termination | NLB vs ALB |
| **③ 분산 알고리즘** | RR / Least Conn | Consistent Hash (sticky) | P2C (random of two) |
| **④ 부가 책임** | SSL term + Health check | Rate limit + Sticky + WAF | DDoS + Observability |
| **⑤ 운영 시나리오** | shallow health 함정 | 503 on rolling deploy (draining) | P99 spike + outlier detection |
| **⑥ 제품 비교** | HAProxy (L4/L7) / Nginx (L7) | Envoy (mesh sidecar) | AWS ALB/NLB / Cloudflare |

### 면접 답변 흐름

> 질문 → 루트 문장 → 해당 가지 → 키워드 3개 → 듣는 사람 표정 보고 인접 가지로

---

## 1. 가지 ①: LB의 위치와 진화 — "왜 끼어드는가"

### 1.1 핵심 질문

> "Load Balancer를 왜 두나요? 그냥 DNS에 IP 여러 개 박으면 안 되나요?"

### 1.2 키워드 1 — Reverse Proxy의 본질

```
[Forward Proxy] (클라이언트 측)
   Client → Proxy → Internet → Server
   Proxy가 "클라이언트 대신" 요청 (회사 방화벽, VPN, censorship 우회)

[Reverse Proxy] (서버 측)  ← Load Balancer가 여기
   Client → Internet → Proxy → Server
   Proxy가 "서버를 대신해" 받아냄
   - 서버 IP/내부 토폴로지 숨김
   - SSL 종단, 캐싱, 압축, 인증, 부하 분산을 한 곳에
```

LB는 **reverse proxy의 일종**. "분산" 하나만 보는 게 아니라 "**서버 군집 앞단의 통합 entrypoint**"라는 추상화가 본질.

→ 이 추상화 덕에 백엔드는 "혼자인 듯" 살고, LB가 모든 어수선한 일(SSL, retry, rate limit, etc.)을 흡수한다.

### 1.3 키워드 2 — 진화 4단계

```
1세대 (1990s)     2세대 (2000s)        3세대 (2010s)       4세대 (2020s~)
DNS Round-Robin   Hardware LB          Software LB         Service Mesh
                  (F5 BIG-IP,          (Nginx, HAProxy)    (Envoy + control
                   Cisco ACE)                              plane: Istio,
                                                          Linkerd)
   │                 │                    │                  │
   ▼                 ▼                    ▼                  ▼
DNS A 레코드       전용 ASIC chip       범용 x86 + epoll    sidecar proxy
TTL로 분산        L4/L7 wire-speed     OS kernel 활용      mTLS + traffic
                  10Gbps+              저렴, 유연          policy in-mesh
   │                 │                    │                  │
   ▼                 ▼                    ▼                  ▼
한계: TTL 무시,    한계: 비쌈 (수    한계: throughput     한계: 복잡도,
health check     억원), vendor       per box,             learning curve,
없음, sticky      lock-in            update 어려움        debugging hell
없음
```

**왜 진화했나** (각 단계의 트리거):

1. **DNS LB → HW LB**: TTL 무시 + health check 없음 + sticky 불가. health check 자동화와 wire-speed 분산이 필요했다.
2. **HW → SW**: x86이 충분히 빨라짐 + Linux epoll이 C10K 해결 + 클라우드 도래로 ASIC의 가성비 폭락.
3. **SW → Mesh**: 마이크로서비스에서 LB가 "엣지 한 대"가 아니라 "서비스마다 sidecar"가 필요해짐. mTLS + traffic policy + observability를 인프라 레이어로.

### 1.4 키워드 3 — 클라이언트·백엔드의 경계

LB가 **있는 것과 없는 것의 차이**:

| 책임 | LB 없이 | LB 있을 때 |
|---|---|---|
| **백엔드 IP 공개** | 직접 노출 | 숨김 (LB만 노출) |
| **SSL 인증서** | 모든 백엔드에 배포 + 갱신 | LB 한 곳 |
| **백엔드 추가/제거** | DNS 변경 + TTL 대기 | LB에 등록만 |
| **장애 격리** | 장애 백엔드도 트래픽 받음 | health check로 격리 |
| **rate limit** | 각 백엔드가 알아서 | LB에서 통합 |
| **A/B test** | 코드에서 분기 | LB의 traffic split |
| **DDoS** | 백엔드 직격 | LB가 흡수 |

→ LB는 "단일 결합점이라 위험"하다고 오해받지만, 실제론 **여러 위험을 한 곳에 모아 관리 가능한 형태로 격리**시키는 장치다. multi-AZ + active-active로 SPoF는 해소.

---

## 2. 가지 ②: L4 vs L7 — 정확히 무엇이 다른가

### 2.1 핵심 질문

> "L4 LB와 L7 LB의 차이가 뭔가요? 같은 connection의 모든 요청이 같은 백엔드로 가나요?"

### 2.2 키워드 1 — L4 (Transport Layer)

**보는 것**: TCP/UDP 헤더 (`src_ip`, `src_port`, `dst_ip`, `dst_port`, `protocol`).
**보지 않는 것**: payload 전체 (HTTP path, header, cookie, body). **암호화돼있어도 그대로 패스**.

```
[L4 LB의 시야]
  ┌─────────────┐
  │ Ethernet    │  ← MAC 주소
  ├─────────────┤
  │ IP          │  ← src/dst IP  ← L3
  ├─────────────┤
  │ TCP/UDP     │  ← src/dst port  ← L4 ★ 여기까지만 본다
  ╞═════════════╡
  │ TLS         │  ← 암호화 시작
  │ HTTP        │  ← L7, 안 봄
  │ payload     │
  └─────────────┘
```

**특성**:
- **per-connection routing**: 한 TCP connection 안의 모든 byte는 **같은 백엔드**로. 5-tuple(`src_ip:src_port` ↔ `dst_ip:dst_port` + protocol) hashing이 기본.
- **SSL termination 불가**: payload가 암호화되어 있어 LB가 풀 수 없음. **passthrough**만 가능.
- **빠름**: 헤더만 보니 처리 비용 작음. wire-speed (수십~수백 Gbps).
- **HTTP를 모름**: path-based routing, header-based 분기 불가.

### 2.3 키워드 2 — L7 (Application Layer)

**보는 것**: HTTP 전체 — method, path, host, header, cookie, query, 심지어 body.
**대가**: TLS를 **풀어야** (=termination) HTTP를 볼 수 있다. SSL termination 필수.

```
[L7 LB의 시야]
  ┌─────────────┐
  │ Ethernet    │
  ├─────────────┤
  │ IP          │
  ├─────────────┤
  │ TCP         │
  ├─────────────┤
  │ TLS         │  ← LB가 풀어냄 (termination)
  ├─────────────┤
  │ HTTP        │  ← ★ 여기까지 다 본다
  │  method     │     - path로 routing
  │  path       │     - cookie로 sticky
  │  headers    │     - header X-Canary로 split
  │  body       │     - body 검사 (WAF)
  └─────────────┘
```

**특성**:
- **per-request routing**: HTTP/1.1 keepalive나 HTTP/2 multiplex 위에서 **각 요청마다** 다른 백엔드로 보낼 수 있다.
- **SSL termination 필수** (또는 가능): LB에서 풀고 백엔드와는 plain 또는 re-encryption(internal mTLS).
- **느림**: parsing + TLS 처리 + 정책 평가 비용. 수~수십 Gbps 수준.
- **똑똑함**: path-based, host-based, header-based, query-based 라우팅 / canary / sticky / WAF.

### 2.4 키워드 3 — "같은 connection의 모든 요청이 같은 백엔드로 가는가?"

**시니어 함정 질문**. 답은 **L4=Yes, L7=No**.

```
[L4: per-connection]
Client ───TCP conn #1 (5-tuple A)──→ LB ──→ Backend X
        └───── 이 connection의 모든 byte → 무조건 X ────┘
                                                      │
                                                  중간에 X가 down 돼도
                                                  이 connection은 X에 계속 (TCP RST 발생)

[L7: per-request]
Client ───TCP conn #1───→ LB ──→ Backend X
              │ GET /a   →           → X
              │ GET /b   →           → Y    ← 같은 conn인데 백엔드 다름
              │ GET /c   →           → X
```

**왜 L7은 가능한가**: LB가 HTTP를 parsing하니 요청 경계를 안다. LB↔백엔드 사이엔 **별도의 connection pool** (upstream keepalive)을 두고 각 요청을 적절한 백엔드로 dispatch.

**HTTP/2 multiplex**에서는 한 connection 안에 여러 stream — 각 stream마다 백엔드 분기 가능. **gRPC**에서는 이게 핵심이다 (gRPC는 모두 한 connection 위에서 다중 RPC).

### 2.5 AWS NLB vs ALB — 실전 매핑

| | NLB (L4) | ALB (L7) |
|---|---|---|
| **layer** | TCP/UDP | HTTP/HTTPS, gRPC, WebSocket |
| **routing 단위** | connection | request |
| **SSL termination** | 가능 (TLS listener) | 기본 |
| **path-based 분기** | 불가 | 가능 |
| **client IP 보존** | 자연스러움 (proxy 안 함) | X-Forwarded-For 필요 |
| **고정 IP** | 가능 (EIP attach) | 불가 (DNS 이름만) |
| **처리량** | 수백만 conn/s | 수만 req/s |
| **레이턴시** | 매우 낮음 | NLB+수 ms |
| **WAF 통합** | 없음 (앞에 ALB 둬야) | AWS WAF 직접 |
| **언제 쓰나** | 게임 서버, TCP/UDP, 매우 낮은 latency | 일반 웹/API |

→ 실무에서 **앞단 ALB + WAF + 뒷단 NLB or 직접 backend** 조합이 흔하다. 또는 **gRPC**라면 ALB가 HTTP/2를 지원.

---

## 3. 가지 ③: 분산 알고리즘 — 어떻게 고르나

### 3.1 핵심 질문

> "백엔드가 5대 있을 때 LB는 어떻게 어디로 보낼지 정하나요? 알고리즘이 5~6개 있는데 차이가 뭔가요?"

### 3.2 키워드 1 — Round Robin / Weighted Round Robin

**가장 단순**. 순서대로 돌아가며 분배.

```
요청 1 → Backend A
요청 2 → Backend B
요청 3 → Backend C
요청 4 → Backend A
...
```

**Weighted RR**: 백엔드마다 weight. A=3, B=1, C=1이면 A : B : C = 3 : 1 : 1로 분배.

**장점**: 단순, 빠름 (state 없음, 그냥 counter modulo).
**단점**: 백엔드 성능/현재 부하 무시. 한 백엔드가 느려도 똑같이 보냄 → P99 악화.

**언제 쓰나**: 백엔드가 **균질**하고 요청도 **균질**할 때 (CPU bound, 처리 시간 비슷).

### 3.3 키워드 2 — Least Connections / Least Response Time

**Least Connections**: 현재 active connection이 가장 적은 백엔드로.

```
Backend A: 100 conn
Backend B:  50 conn  ← 새 요청은 여기로
Backend C:  80 conn
```

**장점**: 느린 백엔드(처리 오래 걸려 conn 적체)에 덜 보냄 — 자연스러운 load shedding.
**단점**: 모든 백엔드의 conn count를 LB가 실시간 추적해야 함. **분산 LB cluster**에서는 각 LB instance가 자기가 본 count만 알아서 부정확.

**Least Response Time**: 평균 응답 시간이 가장 짧은 곳. 더 똑똑하나 추적 비용 ↑.

**언제 쓰나**: 요청 크기가 들쭉날쭉 (어떤 건 빠르고 어떤 건 느림), 백엔드 성능 차이 있음.

### 3.4 키워드 3 — IP Hash / Consistent Hash

**IP Hash**: `hash(client_ip) mod N`으로 백엔드 선택. 같은 IP는 항상 같은 백엔드.

**문제**: 백엔드 추가/제거 시 N이 바뀜 → **거의 모든 매핑 깨짐**. cache miss 폭발.

**Consistent Hash (Ring Hash)**:

```
[Ring 위에 N개 백엔드를 배치]

          0
          ●─B1
       ╱     ╲
     ●─C1     ●─A1
   ╱             ╲
  ●               ●─B2
   ╲             ╱
     ●─A2     ●─C2
       ╲     ╱
          ●
          B3
        180

요청은 hash(key)로 ring 위 한 점 → 시계 방향 첫 노드.
백엔드 1대 추가/제거 시 → 그 노드의 영역만 재배치. 나머지 그대로.
```

**왜 좋은가**: N이 바뀌어도 **1/N 정도의 매핑만 깨짐**. 대규모 cache cluster의 sticky 핵심.

**Maglev (Google 2016)**: Consistent hash의 변형. 미리 큰 lookup table을 만들어두고 O(1)로 lookup. 백엔드 변경 시 table 재계산. **Google Cloud LB / Envoy**가 사용.

**언제 쓰나**: **sticky session** (특정 사용자는 항상 같은 백엔드), **cache** (특정 key는 항상 같은 캐시 노드), **shard routing** (user_id 기반 DB shard).

### 3.5 키워드 추가 — P2C (Power of Two Choices)

**"무작위로 2개 골라서 더 한가한 쪽으로 보낸다."** 이게 끝.

```
backends = [A, B, C, D, E]
choice1 = random.pick()  → C (active=80)
choice2 = random.pick()  → A (active=30)
→ A로 보냄
```

**왜 이게 의외로 좋은가**:
- 완전 random보다 훨씬 좋음 (수학적으로 max queue length가 log log N 수준).
- Least Conn처럼 정확하지만 **전역 state 불필요** (분산 LB cluster에서 강함).
- 구현 단순 + 빠름 + 분산 친화적.

**Twitter (Finagle), Envoy, Linkerd 등 모던 LB의 기본 알고리즘**으로 자리잡음.

### 3.6 알고리즘 매트릭스

| 알고리즘 | state | 분산 LB 친화 | 백엔드 성능 차이 대응 | sticky | 언제 |
|---|---|---|---|---|---|
| Round Robin | 없음 | ★★★ | × | × | 균질, 가장 단순 |
| Weighted RR | weight | ★★★ | △ (수동 weight) | × | 백엔드 등급 다름 |
| Least Connections | conn count | △ | ○ | × | 요청 시간 들쭉날쭉 |
| Least Response Time | latency | △ | ◎ | × | latency 민감 |
| IP Hash | 없음 | ★★★ | × | ○ (취약) | 단순 sticky |
| Consistent Hash | ring | ★★★ | × | ◎ | cache, shard |
| Maglev | table | ★★★ | × | ◎ | 대규모 글로벌 LB |
| P2C | 없음 | ★★★ | ○ | × | **모던 default** |

→ 시니어 답변: "기본은 P2C 또는 Least Conn. sticky가 필요하면 Consistent Hash. 단순/균질하면 RR."

---

## 4. 가지 ④: 부가 책임 — "분산"이 아닌 7가지

### 4.1 핵심 질문

> "LB가 트래픽 분산만 하는 게 아니라면, 또 뭘 하나요?"

### 4.2 SSL/TLS Termination

```
[3가지 모드]

(A) Passthrough (L4)
    Client ═══TLS═══→ LB ═══TLS═══→ Backend
    LB는 packet만 전달, payload 안 봄
    → 백엔드가 cert 보유, CPU 부담

(B) Termination
    Client ═══TLS═══→ LB ───plain───→ Backend
    LB가 TLS 풀고 plain HTTP로 백엔드에
    → cert 중앙 관리, 백엔드 CPU 절약
    → 단점: LB↔Backend가 평문 (내부망 안전성 가정)

(C) Re-encryption (mTLS internal)
    Client ═══TLS═══→ LB ═══TLS'═══→ Backend
    LB가 풀고 새 TLS로 다시 (다른 cert)
    → zero-trust 환경, internal mTLS
    → 단점: TLS 두 번 비용
```

**왜 LB에서 종단하나**:
1. **인증서 중앙 관리** — 백엔드 100대에 cert 일일이 배포/갱신할 필요 없음.
2. **백엔드 CPU 절약** — TLS는 CPU 비쌈 (handshake 더 비쌈). 백엔드는 비즈니스 로직에 집중.
3. **Observability** — 평문이라야 access log, WAF, request body 검사 가능.
4. **HTTP/2 ALPN negotiation 중앙화** — 클라이언트와 ALPN으로 h2 합의, 백엔드는 h1로 받아도 됨.

**SNI (Server Name Indication)**:
- TLS handshake의 `ClientHello`에 평문으로 hostname 전달.
- 한 LB IP + cert 여러 개 (multi-tenant) 가능.
- **Encrypted Client Hello (ECH)** 가 SNI도 암호화하는 차세대.

**Cert Rotation / ACME**:
- 옛날: 수동 발급, 1년짜리.
- 현재: **Let's Encrypt + ACME 프로토콜**로 90일 cert 자동 갱신. cert-manager (k8s), Caddy, 대부분의 LB가 자동.

### 4.3 Health Check — "그냥 ping이 아니다"

```
[3가지 Layer]

(A) L4 Health (TCP)
    LB → SYN → Backend
         ← SYN-ACK ←   ★ 통과
    → "TCP listen 중이면 OK" — 너무 얕음

(B) L7 Health (HTTP)
    LB → GET /health → Backend
         ← 200 OK ←     ★ 통과
    → app process 살아있음 확인

(C) Deep Health
    LB → GET /health/deep → Backend
        → app이 DB/Redis/Kafka ping
         ← 200 (모두 OK) 또는 503 (하나라도 죽음) ←
    → 실제 의존성까지 검증
```

**Shallow vs Deep 트레이드오프**:

| | Shallow `/health` | Deep `/health/deep` |
|---|---|---|
| **검증 범위** | app process | + DB/cache/외부 의존 |
| **false negative** | ↑ (의존성 죽어도 통과) | ↓ |
| **false positive** | ↓ | ↑ (DB 잠시 hiccup → 모든 백엔드 unhealthy) |
| **운영 함정** | "health 통과인데 5xx" | "DB 깜빡임에 전체 down 판정" |

**시니어 표준**: `/health/live` (shallow, app 살아있음) + `/health/ready` (deep, 트래픽 받을 준비). Kubernetes liveness/readiness probe와 동일 사상.

**Passive Health Check**:
- 실제 트래픽 요청의 실패율 추적 → 임계 넘으면 백엔드 unhealthy.
- 5xx rate, connection error rate, latency P99 등.
- Active(주기적 ping) + Passive(실제 트래픽) 조합이 모범.

**Panic Threshold (Envoy)**:
```
healthy_backends / total_backends < 50% 면 모두 healthy로 간주
```
**왜?** 의존성 hiccup으로 80%가 일시 unhealthy 판정나면 남은 20%에 트래픽 폭주 → cascading failure. "다 죽었으면 그냥 다 쓰자" (fail open).

**Circuit Breaker 통합**:
- LB가 백엔드별로 회로 차단 (Hystrix 패턴을 LB가 흡수).
- Envoy `outlier_detection`: 연속 5xx 또는 latency 이상치 감지하면 일정 시간 격리 (eject).

### 4.4 Rate Limiting / Throttling

```
[차원]
- per-IP        (DDoS, scraping 방어)
- per-API key   (테넌트별 quota)
- per-user      (남용 방지)
- per-endpoint  (특정 API만 무거움)
- global        (백엔드 전체 보호)
```

**알고리즘**:

```
[Token Bucket]
- bucket 용량 N tokens
- 일정 비율로 refill (예: 10 token/s)
- 요청마다 token 1개 소비
- 빈 bucket이면 reject
→ burst 허용 (bucket 가득 차있으면 N개 즉시 처리)

[Leaky Bucket]
- queue에 요청 쌓임
- 일정 비율로 leak (예: 10 req/s 처리)
- queue 가득 차면 reject
→ 강제로 평탄화, burst 흡수 없음
```

**분산 환경에서**: LB instance가 여러 대면 각자 counter 따로 → 합쳐서 실제 N배 통과. **Redis** 같은 중앙 store로 token bucket 공유 (느림) 또는 **각 LB에 N/M 할당** (대략).

**제품별**:
- **AWS ALB**: 직접 안 함. **AWS WAF**의 rate-based rules에 위임.
- **Nginx**: `limit_req_zone` directive — IP 기반 leaky bucket이 표준.
- **Envoy**: local rate limit (in-process) + global rate limit (외부 RLS gRPC service).
- **Cloudflare**: edge에서 IP/cookie/API key 기반.

```nginx
# Nginx 예시 — IP당 10req/s, burst 20까지 허용
http {
    limit_req_zone $binary_remote_addr zone=mylimit:10m rate=10r/s;

    server {
        location /api/ {
            limit_req zone=mylimit burst=20 nodelay;
            proxy_pass http://backend;
        }
    }
}
```

### 4.5 Sticky Session (Session Affinity)

**왜 필요한가**: 백엔드는 stateless가 권장이지만, 현실에서:
- **WebSocket** — connection 자체가 stateful. 한 connection은 한 백엔드.
- **파일 업로드 multipart** — 같은 파일의 chunk들이 같은 백엔드로 가야 합치기 쉬움.
- **JSESSIONID** (구식) — 세션 메모리에 들고 있는 레거시 앱.
- **로컬 캐시** — 한 사용자의 데이터를 한 백엔드가 캐싱.

**방식**:

```
(A) Cookie-based
    첫 응답에 LB가 cookie 세팅: AWSALB=BackendX
    이후 요청에 같은 cookie → 같은 백엔드
    + 클라이언트 IP 바뀌어도 OK
    - 클라이언트가 cookie를 받아야

(B) IP-based
    hash(client_ip) → backend
    + cookie 필요 없음
    - NAT 뒤 다수 사용자가 같은 IP → 한 백엔드에 몰림
    - 모바일 셀룰러 → IP 자주 바뀜 → sticky 깨짐

(C) Consistent Hash on app key (user_id, session_id)
    HTTP header나 query에서 키 추출 → consistent hash
    + 가장 안정적
    - app/LB 협의 필요
```

**Sticky의 부작용**:
- **백엔드 부하 불균형**: 트래픽이 IP 분포에 의존.
- **장애 시 영향**: sticky 백엔드 down → 그 세션들만 손실.
- **rolling deploy 어려움**: 같은 사용자가 계속 옛 버전에 묶일 수 있음.

→ 시니어 권장: **가능하면 stateless로 만들고 sticky를 피해라**. 세션은 Redis/JWT로 외부화.

### 4.6 Routing — Path-based / Host-based / Header-based

**L7 LB의 핵심**:

```nginx
# Nginx — path / host / header 기반
server {
    listen 80;
    server_name api.example.com;       # ← host 기반

    location /v1/users/ {                # ← path 기반
        proxy_pass http://users_v1;
    }
    location /v2/users/ {
        proxy_pass http://users_v2;
    }

    # ← header 기반 (canary)
    if ($http_x_canary = "true") {
        proxy_pass http://users_canary;
    }
}
```

**AWS ALB Rule**:
```
Rule 1: path = /api/users/*       → target group: users-service
Rule 2: header X-Canary = true    → target group: canary
Rule 3: host = admin.example.com  → target group: admin
Default                           → target group: web
```

**활용**:
- **마이크로서비스** — 한 도메인 안에서 path마다 다른 서비스.
- **API versioning** — `/v1/`은 옛 백엔드, `/v2/`는 새 백엔드.
- **multi-tenant** — host별 다른 백엔드 (test.example.com vs prod.example.com).
- **canary** — header가 있으면 새 버전으로.

### 4.7 A/B Test / Canary / Blue-Green — LB가 어떻게 지원

**Canary**:

```
[Traffic Split 1%]
              ┌──99%──→ Backend v1.0 (stable)
   Client ──→ LB
              └──1%───→ Backend v1.1 (canary)
              
   1%로 시작 → 메트릭 정상이면 5% → 25% → 50% → 100%
```

**Envoy / Istio VirtualService**:
```yaml
# Istio — header 또는 weight 기반 분기
http:
  - match:
      - headers:
          x-canary:
            exact: "true"
    route:
      - destination: { host: users, subset: v2 }
  - route:
      - destination: { host: users, subset: v1 }
        weight: 95
      - destination: { host: users, subset: v2 }
        weight: 5
```

**핵심 문제 — 세션 일관성**:
- "1% 사용자만 새 버전"이라면, **같은 사용자는 매번 같은 버전**으로 가야 한다 (UX 일관성).
- 단순 weighted random이면 사용자가 새로고침할 때마다 버전이 바뀜 → 카오스.
- 해결: `hash(user_id) % 100 < 5` 같은 deterministic split.

**Blue-Green**:
```
[전환 직전]                 [전환 후]
Client → LB → Blue (v1)    Client → LB → Green (v2)
              Green (v2)             Blue (v1) — standby
```
- 한 번에 switch (DNS 또는 LB target 변경).
- 빠른 rollback (다시 switch).
- 단점: 두 환경 동시 유지 (비용 2배).

### 4.8 WAF (Web Application Firewall)

**역할**: HTTP payload를 검사해 악성 요청 차단. LB의 L7 능력을 적극 활용.

**OWASP Top 10 방어**:
- **SQL Injection** — `OR 1=1`, `UNION SELECT` 패턴 감지
- **XSS** — `<script>`, `javascript:` 감지
- **CSRF** — origin/referer 검사
- **Path traversal** — `../` 감지
- **RCE** — shell 명령어 패턴 감지

**ModSecurity (오픈소스 WAF 엔진) + OWASP CRS (Core Rule Set)**:
- 정규식 기반 rule 수천 개.
- Nginx, Apache, Cloudflare 등에 plug-in.

**AWS WAF**:
- Managed rule groups (AWS, Marketplace).
- Custom rule (rate-based, geo, IP set, regex, etc.).
- ALB / API Gateway / CloudFront에 attach.

**False Positive 관리**:
- 너무 엄격한 rule → 정상 요청 차단 (e.g., 사용자가 SQL 키워드를 본문에 포함).
- **Count Mode** 먼저 → 통계 → tune → enforcement.
- IP whitelist / exception rule.

### 4.9 DDoS 방어

**Layer별**:

```
L3/L4 (volumetric)
- SYN Flood: SYN 폭격으로 backlog queue 고갈
  방어: SYN Cookies (kernel level), SYN proxy (LB)
- UDP Flood, ICMP Flood
  방어: rate limit, blackhole, scrubbing service

L7 (application)
- Slowloris: 천천히 connection 유지하며 슬롯 점유
  방어: client request timeout, max conn per IP
- HTTP Flood: 정상처럼 보이는 GET 폭격
  방어: rate limit, captcha, JS challenge, behavior analysis
- Cache busting: 매번 다른 query string으로 cache 우회
  방어: query string 정규화 또는 무시
```

**Edge Network (Cloudflare, AWS Shield, Akamai)**:
- **anycast** 로 트래픽을 전 세계 PoP에 분산 → volumetric attack이 한 곳에 안 몰림.
- **scrubbing center** — 트래픽을 검사 후 깨끗한 것만 origin으로.
- **Bot management** — JS challenge, ML 기반 사용자 vs bot 판별.

→ 시니어 답변: "L7 DDoS는 백엔드 앞 LB로 막을 수 있지만 volumetric L3/L4는 edge (Cloudflare/CloudFront/AWS Shield) 없이는 못 막는다. 백엔드 in front의 LB는 last line이지 first line이 아님."

### 4.10 Observability — LB가 측정의 black box를 깬다

**LB는 모든 트래픽이 지나가는 hub** → 자연스러운 observability point.

**Access Log**:
```
timestamp client_ip request_method path status response_time upstream_latency upstream_addr request_id
2026-05-23T10:00:00 1.2.3.4 GET /api/users 200 45ms 40ms backend-3:8080 abc123
```

**핵심 메트릭**:

| 메트릭 | 의미 | 진단 |
|---|---|---|
| `request_count` | RPS | 트래픽 패턴 |
| `request_duration_p50/p90/p99` | 응답 분포 | tail latency 진단 |
| `upstream_duration` | LB↔백엔드만 | LB 오버헤드 분리 |
| `4xx_rate` | client error | bad request, auth 실패 |
| `5xx_rate` | server error | 백엔드 장애 |
| `healthy_upstream_count` | 살아있는 백엔드 수 | health check 상태 |
| `connection_count` | 동시 conn | 풀 포화 진단 |
| `tls_handshake_duration` | TLS cost | keepalive 미설정 의심 |

**P99 latency 진단 핵심 메트릭**:
- **`request_duration` vs `upstream_duration` 차이** → LB 자체 오버헤드.
- **백엔드별 `upstream_duration` 분포** → 1대만 느린지(outlier) 모두 느린지.
- **`upstream_connect_time`** → 새 conn 맺는 시간이 큼 → keepalive pool 부족.

**Tracing (분산 추적)**:
- LB가 incoming request에 trace ID 부여 (또는 통과시키기).
- 표준 헤더:
  - **X-Request-Id** (Nginx, Heroku 등) — 단순 고유 ID
  - **X-B3-TraceId / X-B3-SpanId** (Zipkin B3)
  - **traceparent** (W3C Trace Context) — 현대 표준
- 백엔드는 이 ID를 로그에 남김 → LB log ↔ 백엔드 log ↔ DB log 매핑 가능.

```nginx
# Nginx — X-Request-Id 주입
proxy_set_header X-Request-Id $request_id;
log_format main '$request_id $remote_addr "$request" $status';
```

---

## 5. 가지 ⑤: Connection Management — keepalive와 draining

### 5.1 Backend Keepalive Pool

```
[안 좋은 모델]
요청마다 LB↔Backend 새 TCP + TLS handshake
→ 작은 요청에 handshake 비용이 더 큼 (수십 ms)
→ 5xx 폭증의 흔한 원인

[좋은 모델]
LB가 백엔드와 persistent conn 풀 유지
요청 N개 = conn 1개 재사용
```

**Nginx upstream keepalive**:
```nginx
upstream backend {
    server 10.0.0.1:8080;
    server 10.0.0.2:8080;
    keepalive 32;          # ← worker당 idle conn 32개 유지
    keepalive_timeout 60s;
    keepalive_requests 1000;
}
```

**Envoy**: `circuit_breakers`로 max_connections, max_pending_requests, max_requests per conn 제어.

### 5.2 Client Keepalive

클라이언트 ↔ LB도 마찬가지. HTTP/1.1은 keepalive 기본 on, HTTP/2는 한 conn에 multiplex.

### 5.3 HTTP/2 Multiplexing — LB의 새로운 책임

```
HTTP/1.1                    HTTP/2
─────────                   ──────
한 conn = 한 요청 동시       한 conn = 다중 stream
(pipelining은 사실상 실패)    각 stream = 한 요청
                            
요청 100개 = conn 100개      요청 100개 = conn 1개 + stream 100개
```

**LB의 변화**:
- 한 conn 안의 stream마다 다른 백엔드로 분기 가능 (L7 LB).
- HoL blocking 회피 — TCP는 여전히 HoL 문제 있어서 HTTP/3 (QUIC) 등장.
- **HTTP/1↔HTTP/2 conversion** — 클라이언트는 h2로 받고 백엔드는 h1로 전달 (ALB 기본).

### 5.4 Connection Draining (Graceful Shutdown) — rolling deploy의 생명선

**문제 시나리오**:
```
1. Backend X에 새 버전 deploy 시작
2. Kubernetes/ASG가 X를 LB에서 제거 + X에 SIGTERM
3. X가 즉시 종료
4. LB가 아직 X에 전송 중인 요청들 → connection reset → 클라이언트에 503
```

**해결 — Draining**:
```
1. Backend X "draining" 표시 — LB가 새 요청 안 보냄
2. X는 진행 중인 요청 완료 대기 (drain timeout = 30~60s)
3. timeout 내 못 끝낸 요청은 어쩔 수 없이 cut
4. X 종료
```

**AWS ALB / NLB**: `deregistration_delay` (기본 300s).
**Kubernetes**: `preStop` hook + `terminationGracePeriodSeconds`.
**Nginx**: `proxy_next_upstream` + upstream weight 0으로 변경.

**Connection Draining vs Request Draining**:
- Connection drain: 새 conn 안 받음.
- Request drain: 새 request 안 받음 (HTTP/2 multiplex 시 다름).

→ 시니어 표준: **deregistration delay = 백엔드 p99 latency × 2** 정도. 너무 짧으면 잘림, 너무 길면 deploy 느림.

---

## 6. 가지 ⑥: 글로벌 / Failover / Multi-AZ

### 6.1 Multi-AZ

```
                    DNS (Route53)
                          │
            ┌─────────────┴─────────────┐
            ▼                           ▼
        AZ-A LB                     AZ-B LB
       (active)                    (active)
        ┌─┴─┐                       ┌─┴─┐
     B1 B2 B3                    B4 B5 B6
```

**AWS ALB는 기본 Multi-AZ**: ALB 한 개가 여러 AZ에 ENI를 가짐. 한 AZ down 시 다른 AZ로 자동 failover.

**Cross-Zone Load Balancing**:
- ON: AZ-A의 LB가 AZ-B의 백엔드에도 보낼 수 있음. 균형 좋음. inter-AZ 네트워크 비용 ↑.
- OFF: AZ-A LB는 AZ-A 백엔드만. 비용 ↓, 균형 ↓.

### 6.2 Active-Passive vs Active-Active

```
[Active-Passive]
LB-1 (active) ──→ Backends
LB-2 (standby)
   ↑ Heartbeat (VRRP, keepalived)
   
LB-1 down → LB-2 takes virtual IP

[Active-Active]
LB-1 ─┐
       ├──→ Backends (양쪽 다 분산)
LB-2 ─┘
   ↑ DNS 다중 A 레코드 또는 BGP anycast
```

**Active-Active**가 모던 표준. cluster 내 LB가 모두 트래픽 받음. 1대 down 시 나머지로 분산.

### 6.3 Global Server Load Balancing (GSLB)

```
[Region 단위 분산]
Client(서울) ─→ DNS ─→ asia.example.com (Tokyo LB)
Client(LA) ──→ DNS ─→ us.example.com (Virginia LB)
```

**방식**:
- **Geo DNS / Latency-based DNS** (Route53): 클라이언트 IP의 지리/지연 기준으로 가까운 region 반환.
- **Anycast IP** (Cloudflare, AWS Global Accelerator): 같은 IP를 여러 region이 광고 → BGP가 가까운 곳으로.

**Region failover**:
- Route53 + Health Check: 한 region down 시 DNS가 다른 region으로.
- TTL 짧게 해도 클라이언트 resolver caching으로 즉시 X. **Anycast가 더 빠른 failover** (DNS 안 거침).

---

## 7. 가지 ⑦: 운영 시나리오 — 실전 장애 패턴

### 7.1 시나리오 1 — "LB health는 통과인데 실제 요청 5xx"

**증상**: ALB target health = healthy, 그런데 access log에 5xx 다수.

**원인**:
- **Shallow health 함정**: `/health`는 200 반환하지만 백엔드 내부에서 DB connection pool 고갈, downstream 호출 실패.

**진단**:
```bash
# 백엔드 메트릭
curl backend/metrics | grep -E "(hikari|dbcp).*active"
# health endpoint와 실제 logic 분리 정도 확인

# 백엔드 log
tail -f /var/log/app/error.log
```

**해결**:
- `/health/ready`를 deep check로 — DB ping, Redis ping, 외부 호출 정상성.
- Application의 실제 endpoint에 가까운 logic 호출.
- Passive health check 추가 (Envoy outlier detection, ALB target group의 healthy/unhealthy threshold).

### 7.2 시나리오 2 — "Backend 1대에만 트래픽 몰림"

**증상**: 백엔드 5대인데 1대만 CPU 90%, 나머지는 한가.

**원인 후보**:
- **Sticky session 잘못 설정**: 일부 power user가 한 백엔드에 묶임.
- **IP Hash + NAT**: 회사 사용자가 다 같은 NAT IP → 한 백엔드로.
- **Consistent Hash 불균형**: virtual node 수가 적어 ring 분포 편향.
- **Long-lived connection (WebSocket)**: 새 conn은 RR로 잘 분산되지만 기존 conn이 한쪽에.

**진단**:
```bash
# 백엔드별 conn / RPS 비교
for backend in b1 b2 b3 b4 b5; do
    ssh $backend "ss -tn state established | wc -l"
done

# LB의 분배 메트릭
aws cloudwatch get-metric-statistics ... TargetGroup=... Metric=RequestCount
```

**해결**:
- 가능하면 sticky 끄고 stateless로.
- Consistent Hash라면 virtual node 수 ↑ (Envoy `minimum_ring_size`).
- WebSocket 같은 long-lived는 max connection 제한 + drain 시 강제 끊기.

### 7.3 시나리오 3 — "Rolling deploy 시 503 폭증"

**증상**: 백엔드 인스턴스 교체할 때마다 잠깐 503 1~3%.

**원인**: **Connection draining 미설정** 또는 너무 짧음.
1. Deploy 시작 → 인스턴스 LB에서 제거.
2. 인스턴스 즉시 종료.
3. LB가 아직 그 인스턴스로 보내던 요청 → connection reset.

**진단**:
```bash
# ALB target group deregistration delay 확인
aws elbv2 describe-target-group-attributes ...
# 기본 300s. 너무 짧으면 5xx, 너무 길면 deploy 지연.

# 백엔드 graceful shutdown 핸들러 유무
# Spring Boot: server.shutdown=graceful, spring.lifecycle.timeout-per-shutdown-phase=30s
```

**해결**:
- `deregistration_delay` = p99 latency × 2 ~ 3.
- 백엔드는 SIGTERM 받으면 **새 요청 거절 + 진행 중 요청 완료**.
- Kubernetes: `preStop` hook으로 sleep + readiness false.
- 503 → LB가 retry policy로 다른 백엔드 시도 가능 (idempotent한 GET만).

### 7.4 시나리오 4 — "P99 latency가 1초로 spike. P50은 정상"

**증상**: 평소 P99 100ms인데 갑자기 1000ms. P50은 50ms로 정상.

**원인 후보**:
- **백엔드 1대만 slow** — JVM Full GC, DB lock contention, disk hiccup.
- LB의 **outlier detection 미동작**.

**진단**:
```bash
# 백엔드별 P99 분포
# Datadog/Grafana로 each backend's p99 비교
# 1대만 튀는지 모두 튀는지

# 그 백엔드 JVM 상태
jstat -gc <pid> 1s   # Full GC 빈도
jstack <pid>          # 스레드 dump
# DB connection pool 상태

# LB 메트릭
# upstream_response_time per backend
```

**해결**:
- Envoy `outlier_detection`: 연속 5xx 또는 latency 이상 백엔드 자동 격리.
- AWS ALB: target group health check `unhealthy_threshold` 낮게.
- 백엔드 자체 문제 해결 (GC 튜닝, query 최적화).

### 7.5 시나리오 5 — "TLS handshake 비용 폭증"

**증상**: CPU 부하 높고 latency가 평소보다 30% 더 걸림.

**원인**: 클라이언트가 매 요청마다 새 conn + 새 TLS handshake.

**진단**:
```bash
# Nginx access log에서 $ssl_session_reused
# 0이 많으면 session resumption 안 됨

# LB 메트릭: tls_handshake_duration, new_connections_per_second
```

**해결**:
- **HTTP keepalive** 활성화 (Connection: keep-alive).
- **TLS session resumption** (session ticket 또는 session ID).
- **HTTP/2** 강제 (한 conn에 multiplex).
- 클라이언트 ↔ LB 사이 keepalive 강화.

### 7.6 시나리오 6 — "WAF가 정상 요청까지 차단"

**증상**: 사용자 신고: "한국어 게시글 작성하면 에러 떠요."

**원인**: WAF rule이 본문의 한글/SQL키워드를 SQL Injection으로 오인.

**진단**:
- WAF block log 확인. matched rule ID.
- 어떤 패턴이 trigger했나.

**해결**:
- 해당 rule을 count-only mode로.
- Exception rule: 이 endpoint는 본문 검사 skip.
- 또는 더 정밀한 rule로 교체.

### 7.7 시나리오 7 — "RPS는 정상인데 5xx 폭증"

**증상**: 트래픽은 평소 수준인데 5xx rate가 갑자기 10%.

**원인 후보**:
- 한 백엔드만 down (다른 백엔드로 retry되지 않음).
- LB↔백엔드 keepalive pool 고갈 → connect timeout.
- 백엔드의 thread pool 포화.
- 의존성 (DB, 외부 API) 응답 시간 ↑.

**진단**:
```bash
# 어느 백엔드에서 5xx 나는지
# Datadog Logs: status:5xx | top backend
# 모든 백엔드에서 균일? → 의존성 문제
# 1대에서만? → 그 백엔드 자체 문제
```

---

## 8. 가지 ⑧: 제품 비교 — 누가 어디 강한가

### 8.1 HAProxy

- **출시**: 2001, Willy Tarreau (개인 프로젝트).
- **장점**: L4/L7 모두 강함. 매우 빠름. 안정성 검증. 단일 바이너리, 설정 명확.
- **단점**: 동적 설정 (백엔드 추가/제거 시 reload 필요했음, 최근 Runtime API로 개선).
- **언제**: 고성능 L4/L7 LB, on-prem 환경, 단순한 구성.

### 8.2 Nginx

- **출시**: 2004, Igor Sysoev (Apache의 C10K 문제 해결).
- **장점**: web server + LB 겸용. event-driven (epoll). 풍부한 모듈. 운영 사례 압도적.
- **단점**: L4 능력은 HAProxy보다 약함. 동적 설정 (Nginx Plus는 유료).
- **언제**: 정적 파일 + reverse proxy + L7 LB 한 곳에서. 가장 흔한 선택.

### 8.3 Envoy

- **출시**: 2016, Lyft (마이크로서비스 + service mesh).
- **장점**: HTTP/2/gRPC native. 동적 설정 (xDS API). 풍부한 observability. extension 모델 (WASM).
- **단점**: 설정이 복잡 (JSON/YAML 수백 줄). 단독 사용보다 control plane (Istio, Consul Connect)과 함께.
- **언제**: Service mesh, gRPC 환경, 마이크로서비스 sidecar, 동적/programmable LB.

### 8.4 AWS ALB

- **L7 only**. HTTP/HTTPS/gRPC/WebSocket.
- **장점**: 매니지드, multi-AZ 기본, WAF 통합, ACM cert 자동, target group 추상화.
- **단점**: L4 안 됨 (NLB 별도). 비용 (capacity 단위). 일부 고급 기능 부재 (e.g., 복잡한 routing).
- **언제**: AWS 환경의 표준 L7 LB.

### 8.5 AWS NLB

- **L4 only**. TCP/UDP/TLS.
- **장점**: 매우 빠름 (수백만 conn/s), 고정 IP, source IP 보존.
- **단점**: L7 기능 없음, WAF 직접 X.
- **언제**: 게임 서버, 매우 낮은 latency, TCP/UDP, 고정 IP 필요.

### 8.6 Cloudflare

- **Edge + WAF + CDN + DDoS + LB 통합**.
- **장점**: anycast 글로벌 PoP, volumetric DDoS 흡수, 무료 tier 강력, Argo로 백엔드까지 빠름.
- **단점**: vendor lock-in, 일부 기능은 enterprise 전용.
- **언제**: 글로벌 트래픽, 강력한 DDoS 방어 필요, CDN과 통합.

### 8.7 비교표

| | HAProxy | Nginx | Envoy | ALB | NLB | Cloudflare |
|---|---|---|---|---|---|---|
| **Layer** | L4/L7 | L7 (L4 일부) | L7 (L4 일부) | L7 | L4 | L7 |
| **동적 설정** | Runtime API | reload (OSS), plus | xDS (탁월) | API | API | API |
| **HTTP/2/gRPC** | ○ | ○ | ◎ | ○ | TLS만 | ○ |
| **service mesh** | × | × | ◎ (Istio) | × | × | × |
| **WAF** | × | ModSec | filter | AWS WAF | × | ◎ 기본 |
| **DDoS L3/L4** | × | × | × | △ (Shield) | △ | ◎ |
| **observability** | log/stats | log | metrics + tracing | CloudWatch | CloudWatch | dashboard |
| **운영 비용** | self host | self host | self+mesh | managed | managed | managed |
| **러닝 커브** | 중 | 낮 | 높 | 낮 | 낮 | 낮 |
| **언제** | high-perf on-prem | 정적+LB | mesh, gRPC | AWS L7 표준 | AWS L4 표준 | 글로벌 edge |

---

## 9. 면접 답변 워크플로우

### 9.1 질문 → 가지 매핑

| 면접 질문 | 진입 가지 | 인접 확장 |
|---|---|---|
| "LB가 뭐고 왜 필요한가요?" | ① 위치 | ② L4/L7 |
| "L4 LB와 L7 LB 차이?" | ② L4 vs L7 | ④ SSL termination |
| "백엔드 어떻게 고르나요?" | ③ 분산 알고리즘 | ④ Sticky |
| "SSL을 LB에서 풀면 좋은 이유?" | ④ SSL term | ⑤ 운영 |
| "Sticky session 왜 안티패턴?" | ④ Sticky | ① stateless 권장 |
| "Health check 어떻게 설계?" | ④ Health | ⑤ shallow 함정 |
| "Rate limit 분산 환경에서?" | ④ Rate | ⑥ 제품 비교 |
| "Canary deploy LB로 어떻게?" | ④ Canary | ⑤ 일관성 |
| "Rolling deploy에서 503 폭증" | ⑤ 운영 (drain) | ④ Connection mgmt |
| "P99 spike 어디부터?" | ⑤ 운영 | ④ outlier detection |
| "ALB vs NLB 언제?" | ⑥ 제품 비교 | ② L4 vs L7 |

### 9.2 답변 템플릿

> **루트 문장 한 줄 → 해당 가지 키워드 3개 → 듣는 사람 표정 보고 인접 가지로**

예: "L4 LB와 L7 LB 차이가 뭔가요?"

> "LB는 클라이언트와 백엔드 사이의 reverse proxy인데, 어느 layer까지 풀어보느냐로 L4와 L7이 갈립니다. (← 루트)
> 첫째, **L4는 TCP 헤더만** — 5-tuple로 per-connection routing. 같은 connection의 모든 byte는 무조건 같은 백엔드. SSL termination 불가, payload가 암호화돼있어 그대로 통과 (passthrough). 빠르고 (NLB가 수백만 conn/s) 똑똑하진 않음.
> 둘째, **L7은 HTTP payload까지** — TLS 풀어서 path, header, cookie를 보고 per-request routing. 같은 connection 안의 요청들이 다른 백엔드로 갈 수 있어요. SSL termination 필수, 그래서 cert 중앙 관리하고 백엔드 CPU 절약하고 WAF/observability도 가능. 대신 느림.
> 셋째, **AWS로 매핑하면 NLB가 L4, ALB가 L7**. 게임 서버처럼 TCP/UDP에 매우 낮은 latency 필요하면 NLB, 일반 웹/API면 ALB가 표준입니다.
> 그래서 시니어 면접에서 'gRPC는 어디 쓰냐' 물으면 ALB — HTTP/2 multiplex 위에서 stream 분기가 가능해서요."

---

## 10. 꼬리질문 트리

### Q1 [가지 ②]. L4 LB와 L7 LB의 차이?

> L4는 TCP/UDP 헤더만 보고 per-connection으로 routing. payload 모름. SSL passthrough만 가능. 빠르고 단순. L7은 HTTP payload를 풀어 per-request routing. SSL termination 필수. path/header/cookie로 분기 가능. WAF, observability, canary 모두 L7에서. 같은 TCP connection이라도 L7은 요청마다 다른 백엔드로 보낼 수 있다.

**🪝 Q1-1: 그럼 같은 connection의 모든 요청이 같은 백엔드로 가는 게 보장되나요?**
> L4는 yes, L7은 no. L7 LB는 HTTP 요청 경계를 파싱해서 각 요청을 적절한 백엔드로 dispatch. LB↔백엔드 사이엔 별도 upstream keepalive pool. HTTP/2 multiplex나 gRPC에서는 한 conn 안의 stream마다 백엔드가 다를 수 있음.

**🪝🪝 Q1-1-1: WebSocket은 어느 layer로 처리?**
> WebSocket은 HTTP Upgrade로 시작해 그 conn이 영구 stream이 됨 — L7 LB가 받아도 일단 upgrade 후엔 connection 자체가 stateful. 그래서 sticky session처럼 한 conn은 한 백엔드. 새 WebSocket conn마다 분산. AWS ALB가 WebSocket 지원하는 게 이 사상.

### Q2 [가지 ③]. 분산 알고리즘 5개 비교?

> Round Robin은 순서대로, state 없음, 균질 트래픽. Least Connections는 현재 conn 적은 백엔드, 분산 LB cluster에서 부정확 가능. IP Hash는 같은 IP→같은 백엔드지만 NAT 함정. Consistent Hash는 ring 위 배치로 백엔드 변경 시 1/N만 재배치, sticky/cache/shard에 강함. **P2C (Power of Two Choices)**는 무작위 2개 중 더 한가한 쪽 — 단순한데 수학적으로 좋고 분산 친화. Twitter Finagle, Envoy, Linkerd가 default로 채택.

**🪝 Q2-1: P2C가 왜 의외로 좋은가요?**
> max queue length가 random은 log N, P2C는 log log N으로 줄어듦 (Mitzenmacher 논문). Least Conn처럼 정확하지만 전역 state 불필요 — 분산 LB cluster에서 각 LB가 독립적으로 결정할 수 있다. 구현도 random.pick() 2번이면 끝.

### Q3 [가지 ④]. SSL termination을 왜 LB에서 하나요?

> 4가지 이유. ① **cert 중앙 관리** — 백엔드 100대에 cert 배포/갱신 불필요. ② **백엔드 CPU 절약** — TLS handshake가 CPU 비쌈. ③ **observability** — 평문이라야 access log, WAF, request body 검사 가능. ④ **HTTP/2 ALPN negotiation 중앙화** — 클라이언트와 h2 합의, 백엔드는 h1로 받아도 됨. 단점은 LB↔백엔드 구간이 평문 — 내부망 안전 가정 또는 re-encryption (internal mTLS).

**🪝 Q3-1: SNI가 뭔가요?**
> Server Name Indication. TLS handshake의 ClientHello에 hostname을 평문으로 포함 → 같은 IP에 cert 여러 개를 호스팅 가능. multi-tenant LB의 핵심. 단점: hostname이 평문이라 privacy leak. 차세대 ECH(Encrypted Client Hello)가 이걸 암호화.

**🪝🪝 Q3-1-1: passthrough vs termination vs re-encryption 언제?**
> Passthrough는 백엔드가 cert를 직접 들어야 할 때 (e.g., mTLS로 client cert를 백엔드가 직접 검증). Termination은 일반적 LB. Re-encryption은 zero-trust 환경 — LB↔백엔드 사이도 mTLS로. PCI-DSS 같은 컴플라이언스 환경에서 필요.

### Q4 [가지 ④]. Health check를 어떻게 설계하나요?

> 두 레벨로 분리. **/health/live** (shallow) — process 살아있음만, fast, 운영 hiccup에 둔감. **/health/ready** (deep) — DB/Redis/외부 의존 ping, 트래픽 받을 준비 됐는지. Kubernetes의 liveness/readiness probe와 동일 사상. Active(주기적 ping) + Passive(실제 요청 5xx rate)도 함께. Envoy `outlier_detection`처럼 자동 격리. 그리고 **panic threshold** — 너무 많이 unhealthy면 fail open으로 다 보내야 cascading failure 막음.

**🪝 Q4-1: deep health의 함정?**
> DB가 잠시 hiccup하면 모든 백엔드가 동시에 unhealthy 판정 → 트래픽 전체 차단 → cascading failure. 또 deep health 자체가 DB에 부담을 줘 부하 ↑. 그래서 deep은 cache (e.g., 5초 결과 캐시)하거나 partial degradation (DB 죽어도 read-only로 응답).

### Q5 [가지 ④]. Sticky session이 왜 안티패턴인가요? 그래도 써야 할 때는?

> 기본적으로 백엔드는 stateless 권장 — sticky가 깨지면 세션 손실, 부하 불균형, rolling deploy 어려움. 그래도 필요한 경우: ① **WebSocket** — connection 자체가 stateful. ② **파일 업로드 multipart chunk** — 합치기 편함. ③ **레거시 JSESSIONID** — 세션을 메모리로. ④ **로컬 캐시** — 한 사용자 데이터를 한 백엔드가 캐싱. 가능하면 세션은 **Redis/JWT로 외부화**해서 stateless로 만들고, 어쩔 수 없을 때만 cookie-based 또는 Consistent Hash on user_id.

### Q6 [가지 ⑤]. Rolling deploy 시 503 폭증 — 진단과 해결?

> 원인: **Connection draining 미설정** 또는 너무 짧음. 인스턴스 종료 시 진행 중 요청이 connection reset. 해결 절차: ① AWS ALB의 `deregistration_delay`를 백엔드 p99 latency × 2~3으로 (기본 300s). ② 백엔드는 SIGTERM 받으면 새 요청 거절 + 진행 중 요청 완료 (Spring Boot `server.shutdown=graceful`, `spring.lifecycle.timeout-per-shutdown-phase=30s`). ③ Kubernetes `preStop` hook으로 readiness false + sleep. ④ Idempotent GET은 LB retry로 다른 백엔드 시도 가능.

**🪝 Q6-1: WebSocket 같은 long-lived connection의 drain은?**
> Drain timeout 안에 끝낼 수 없음 — WebSocket은 영구적이라. 두 옵션: ① drain timeout 내 강제 종료 (클라이언트가 reconnect, 새 백엔드로). ② close frame을 보내 graceful close 시그널 후 클라이언트가 새로 연결. Slack/Discord 같은 곳은 close frame + exponential backoff reconnect 패턴.

### Q7 [가지 ⑤]. P99 latency가 1초로 spike. 어디부터?

> P50은 정상인데 P99만 튄다면 **백엔드 1대가 outlier**. 진단: ① 백엔드별 p99 분포 비교 — 1대만 튀는지 모두 튀는지. ② 1대만이면 그 백엔드 JVM (Full GC), DB lock, disk hiccup 의심. jstat/jstack 확인. ③ 모두 튀면 downstream 의존성 (DB slow query, 외부 API). 해결: ① Envoy outlier_detection으로 자동 격리 (연속 5xx 또는 latency 이상). ② AWS ALB target group의 health check threshold 낮게. ③ 근본 원인 (GC tuning, query 최적화) 처리.

**🪝 Q7-1: LB 메트릭 중 P99 진단에 가장 유용한 것?**
> ① `request_duration` vs `upstream_duration` 차이 → LB 자체 오버헤드 분리. ② `upstream_connect_time` 큼 → keepalive pool 부족 → 매번 새 conn. ③ `tls_handshake_duration` → session resumption 안 됨. ④ 백엔드별 `upstream_response_time` 분포 → outlier 식별. ⑤ `5xx_rate` per backend.

### Q8 [가지 ④]. WAF false positive를 어떻게 줄이나?

> 단계: ① 초기엔 **Count Mode**로 (차단 안 함, log만). ② 통계 분석 — 어떤 rule이 어떤 endpoint에서 trigger하는지. ③ 정상 사용자 패턴 분류 (한국어 본문 포함, SQL 키워드 정당 포함 등). ④ Exception rule 추가 — 특정 endpoint는 body 검사 skip, 특정 IP whitelist. ⑤ Enforcement로 전환 + 지속 모니터링. ⑥ ML 기반 WAF (AWS Bot Control, Cloudflare ML)는 정적 rule보다 false positive 적음.

### Q9 (Killer) [가지 ⑤]. "LB health는 다 통과인데 사용자는 5xx 본다." 진단?

> 단계:
> 1. **Shallow health 의심**: `/health`가 너무 얕음 — DB pool 고갈, downstream 실패 무시.
> 2. **백엔드 메트릭**: HikariCP active connection, downstream call latency, JVM Full GC 확인.
> 3. **LB access log**: status code 분포, upstream_response_time, retry 여부.
> 4. **백엔드 에러 log**: exception type, stack trace.
> 5. **해결**: `/health/ready`를 deep check로 (DB ping, 외부 의존 ping). passive health (Envoy outlier_detection)으로 보강. circuit breaker로 downstream 격리.

**🪝 Q9-1: deep health endpoint가 DB에 부담을 주면?**
> Cache 또는 throttle. 결과를 5~10초 cache (TTL 짧게)해서 매 health check마다 DB ping 안 함. 또는 health check 주기를 길게. 그리고 **partial degradation** — DB 죽어도 read-only로 응답하면 health는 통과시킴 (UX 우선).

### Q10 (패턴 통찰) [가지 ①]. LB의 사상이 다른 어디서 반복되나요?

> **"공유 자원 앞에 mediator를 두어 정책을 일원화"** — Database의 connection pool (HikariCP가 DB 앞 LB), JVM의 TLAB (Eden 앞 per-thread buffer로 lock 회피), Kubernetes의 Ingress (cluster 외부 LB), Service Mesh의 sidecar (서비스 간 LB), CDN (origin 앞 edge), API Gateway (마이크로서비스 앞 통합 entrypoint). 모두 "**여러 클라이언트 ↔ 여러 서버**" 사이에 mediator를 두어 분산·격리·관측을 한곳에 모으는 패턴. 시니어가 "왜 LB가 필요한가"를 답할 때 이 추상 패턴까지 짚으면 한 수 위.

---

## 11. 학습 체크리스트

면접 전 백지에서 다음을 다 해낼 수 있어야 마스터:

- [ ] 0장 마인드맵을 종이에 1분 이내로 그릴 수 있다 (루트 + 6가지 + 키워드 3개)
- [ ] 가지 ①: reverse proxy 본질 + LB 진화 4단계 (DNS→HW→SW→Mesh)
- [ ] 가지 ②: L4 vs L7 시야 다이어그램 + "같은 conn 다른 백엔드?" 정확히 답
- [ ] 가지 ②: NLB vs ALB 매핑
- [ ] 가지 ③: 알고리즘 5종 비교 (RR/LC/Hash/Consistent/P2C) + 언제 무엇
- [ ] 가지 ④: SSL termination 3 mode (passthrough/term/re-encryption)
- [ ] 가지 ④: Health shallow vs deep 함정 + panic threshold
- [ ] 가지 ④: Rate limit 분산 환경 어려움 + token vs leaky bucket
- [ ] 가지 ④: Sticky session 안티패턴 이유 + 어쩔 수 없는 경우
- [ ] 가지 ④: WAF / DDoS 방어 — L3/L4 edge vs L7 in front of backend
- [ ] 가지 ⑤: Connection draining 설정 + rolling deploy 503 진단
- [ ] 가지 ⑤: P99 spike 진단 절차 (upstream_response_time per backend → outlier detection)
- [ ] 가지 ⑥: HAProxy/Nginx/Envoy/ALB/NLB/Cloudflare 비교표
- [ ] 9장 꼬리질문 10개에 막힘없이 답한다

---

## 다음 단계

- → [05. Nginx Internals](./05-nginx-internals.md): Nginx의 event loop / epoll / worker process / upstream pool
- → [06. Tomcat Internals](./06-tomcat-internals.md): Acceptor → Poller → Executor 파이프라인
- → [07. Connection Pools Master](./07-connection-pools-master.md): 모든 풀의 위치와 한계

## 참고

- **HAProxy Configuration Manual**: https://docs.haproxy.org/
- **Nginx Documentation**: https://nginx.org/en/docs/
- **Envoy Architecture Overview**: https://www.envoyproxy.io/docs/envoy/latest/intro/arch_overview/arch_overview
- **AWS ALB / NLB Documentation**: https://docs.aws.amazon.com/elasticloadbalancing/
- **Cloudflare Learning Center — Load Balancing**: https://www.cloudflare.com/learning/performance/what-is-load-balancing/
- **Mitzenmacher — "The Power of Two Choices in Randomized Load Balancing"** (1996): https://www.eecs.harvard.edu/~michaelm/postscripts/tpds2001.pdf
- **Maglev — Google's Network Load Balancer** (2016): https://research.google/pubs/maglev-a-fast-and-reliable-software-network-load-balancer/
- **OWASP Top 10**: https://owasp.org/www-project-top-ten/
- **W3C Trace Context**: https://www.w3.org/TR/trace-context/
- **Istio Traffic Management**: https://istio.io/latest/docs/concepts/traffic-management/
