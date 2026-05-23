# Network Request Lifecycle — URL 입력부터 DB 응답까지

> "브라우저에 URL 치면 DNS → 라우팅 → 서버 → 응답" 이라고만 답하면 입문자.
> "브라우저가 IDN을 punycode로 변환한 후 OS resolver가 stub→recursive→authoritative를 거쳐 A 레코드를 받고, BGP가 AS path로 라우팅한 패킷이 ECMP로 분산되어 L4 LB의 DSR로 백엔드에 도달하면 Nginx worker가 epoll로 이벤트를 받아 upstream keepalive pool에서 Tomcat NIO Connector의 Acceptor → Poller → Executor 파이프라인을 통과한 후 HikariCP에서 빌려온 JDBC 커넥션의 wire protocol로 PostgreSQL에 도달한다" 라고 말할 수 있다면 그 다음 단계.
> 이 가이드의 목표는 후자다.

---

## 📍 학습 목표

이 챕터를 마치면 다음을 막힘없이 답할 수 있다.

1. 사용자가 주소창에 `https://example.com/users/김면수` 치고 Enter를 누른 순간부터 DB의 디스크 블록에서 row가 읽혀 돌아오기까지의 **전체 데이터 흐름**을 백지에 그릴 수 있다.
2. "김면수" 같은 한글이 어떻게 바이트로 직렬화되고 네트워크를 통과한 후 서버에서 다시 문자열로 복원되는지 단계별로 설명할 수 있다.
3. 데이터가 통과하는 **OSI 7계층 각각**에서 어떤 헤더가 붙고 떨어지는지(encapsulation/decapsulation), TCP/IP 5계층 모델과의 매핑까지.
4. **로드밸런서**가 단순 트래픽 분산이 아니라 SSL termination, health check, rate limit, sticky session, WAF, A/B test, observability, DDoS 방어까지 담당함을 안다. L4와 L7의 차이, DSR/SNAT/NAT 모드 차이.
5. **모든 커넥션 풀**의 위치와 역할 — Nginx upstream keepalive, Tomcat acceptor thread/executor pool, HikariCP DB pool, HTTP client pool, file descriptor 한계, kernel TCP backlog 등.
6. Nginx가 **수만 동시 연결**을 8개 worker로 처리하는 비결 (event loop + epoll + non-blocking I/O).
7. Tomcat이 **request를 어떻게 byte stream에서 객체로** 변환하는지 (Acceptor → Poller → Executor → Servlet).
8. JDBC 드라이버가 PostgreSQL/MySQL **wire protocol**로 어떻게 SQL을 직렬화하고 응답을 받는지.
9. Production에서 P99 latency spike가 발생했을 때 이 흐름의 어느 단계에서 병목이 생겼는지 진단·해결할 수 있다.

---

## 🌐 전체 흐름 큰 그림

```
[브라우저]
   │  1. URL 파싱 + IDN punycode + percent-encoding
   │  2. OS resolver에 hostname 질의
   ▼
[DNS 계층]                                      ← 02-dns-and-routing
   stub resolver → recursive → root/TLD/authoritative
   │  3. A/AAAA 레코드 반환 (IP 주소)
   ▼
[라우팅 계층]                                   ← 02-dns-and-routing
   호스트 라우팅 테이블 → 게이트웨이 → ISP → BGP/AS path → CDN edge → origin
   │  4. ECMP로 다수 경로 분산
   ▼
[L4/L7 Load Balancer]                          ← 04-load-balancer-deep-dive
   │  5. SSL termination, health check, rate limit
   │  6. backend 선택 (round-robin, least-conn, consistent hash)
   ▼
[Nginx]                                         ← 05-nginx-internals
   │  7. event loop / worker process
   │  8. upstream keepalive pool로 Tomcat 연결
   ▼
[Tomcat]                                        ← 06-tomcat-internals
   │  9. Acceptor → Poller → Executor → Servlet
   │ 10. HTTP 파싱 (byte → HttpServletRequest)
   ▼
[Spring Application]
   │ 11. HikariCP에서 DB 커넥션 차용                ← 07-connection-pools-master
   ▼
[JDBC Driver]                                   ← 08-db-connection-and-jdbc
   │ 12. PreparedStatement → wire protocol
   ▼
[PostgreSQL / MySQL]
   │ 13. Parser → Optimizer → Executor → Storage
   │ 14. Buffer Pool → 디스크 (필요시)
   ▼
[응답: 역순으로 돌아옴]
```

각 단계마다 **OSI 7계층** (03번 챕터)이 동시에 동작하면서 헤더를 붙이고 뗀다.

---

## 📚 챕터 목록

| # | 파일 | 핵심 질문 | 상태 |
|---|---|---|---|
| 01 | [01-url-input-and-serialization.md](./01-url-input-and-serialization.md) | "`김면수`가 어떻게 0과 1로 직렬화되어 패킷에 실리고 서버에서 다시 복원되나" | ✅ (1344 lines) |
| 02 | [02-dns-and-routing.md](./02-dns-and-routing.md) | "hostname이 IP가 되는 4단계 + IP 패킷이 인터넷을 가로지르는 BGP/anycast/CDN" | ✅ (1289 lines) |
| 03 | [03-osi-7-layers-and-tcp-tls.md](./03-osi-7-layers-and-tcp-tls.md) | "OSI 7계층 각각이 무엇을 하나, TCP 3-way handshake, TLS handshake가 데이터에 어떻게 끼어드나" | ✅ (1416 lines) |
| 04 | [04-load-balancer-deep-dive.md](./04-load-balancer-deep-dive.md) | "L4/L7 LB의 모든 역할 — 트래픽 분산 + SSL term + health + rate limit + sticky + WAF + DDoS + observability" | ✅ (1206 lines) |
| 05 | [05-nginx-internals.md](./05-nginx-internals.md) | "Nginx가 8 worker로 수만 연결을 처리하는 비결 — event loop, epoll, non-blocking, upstream pool" | ✅ (1410 lines) |
| 06 | [06-tomcat-internals.md](./06-tomcat-internals.md) | "Tomcat이 byte stream을 HttpServletRequest 객체로 어떻게 변환하나 — Acceptor/Poller/Executor 파이프라인" | ✅ (1496 lines) |
| 07 | [07-connection-pools-master.md](./07-connection-pools-master.md) | "Nginx upstream / Tomcat thread / HikariCP / HTTP client / kernel TCP backlog / FD limit — 모든 풀 마스터" | ✅ (1867 lines) |
| 08 | [08-db-connection-and-jdbc.md](./08-db-connection-and-jdbc.md) | "JDBC 드라이버가 PostgreSQL/MySQL wire protocol로 어떻게 통신하나, prepared statement는 왜 빠른가" | ✅ (2161 lines) |

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

6. "한글이 깨져서 들어옴 (모지바케)"
   → percent-encoding charset 불일치, HTTP Content-Type charset, JDBC URL의 useUnicode/characterEncoding
```

---

## 진행 현황

- [x] README + 전체 흐름 그림 + 챕터 목록
- [x] 01-url-input-and-serialization (1344 lines)
- [x] 02-dns-and-routing (1289 lines)
- [x] 03-osi-7-layers-and-tcp-tls (1416 lines)
- [x] 04-load-balancer-deep-dive (1206 lines)
- [x] 05-nginx-internals (1410 lines)
- [x] 06-tomcat-internals (1496 lines)
- [x] 07-connection-pools-master (1867 lines)
- [x] 08-db-connection-and-jdbc (2161 lines)

**총 12,189 라인** — 8개 챕터 모두 시니어 운영 마스터 관점 + 7단 레이어 + ASCII 다이어그램 + 꼬리질문 3단까지 완성.

> 이 파일은 학습 진행에 따라 계속 업데이트된다.
