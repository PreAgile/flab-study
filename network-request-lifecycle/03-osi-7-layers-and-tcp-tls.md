# 03. OSI 7계층 + TCP + TLS — 데이터가 7번 옷을 갈아입고 다시 7번 벗는 여행

> "OSI는 7계층" 이라고 외운 면접자는 절반은 모르는 것이다.
> **왜 7개로 쪼갰나? 각 계층이 무슨 PDU를 만드나? 헤더는 어떤 순서로 붙고 떨어지나? 3-way handshake가 끝나기 전에는 HTTP가 한 바이트도 못 가는 이유는? TLS 1.3이 왜 1 RTT만에 끝나나? QUIC는 왜 TCP를 버렸나?**
> 시니어가 진짜 알아야 할 것은: 이 흐름을 백지에서 줄줄 풀고, `tcpdump`/`wireshark`/`ss`/`openssl s_client`로 운영 장애를 진단할 수 있는 능력.

---

## 이 문서의 사용법

1. **0장 마인드맵을 먼저 외운다** — 면접 종이에 그릴 5개 가지.
2. **1~3장에서 OSI 7계층 + 캡슐화 풀버전**.
3. **4~6장에서 TCP의 모든 것** (handshake/흐름·혼잡 제어/close).
4. **7~9장에서 TLS + QUIC**.
5. **10장 운영 시나리오 + 진단 도구**.
6. **11장 꼬리질문**으로 자가 검증.

---

## 0. 마인드맵 — 면접 종이에 그릴 그림

### 루트 한 문장 (anchor)

> **"브라우저가 만든 HTTP 메시지는 7번 옷(헤더)을 입고 와이어를 건너간다. TCP가 신뢰성을 만들고, TLS가 비밀과 인증을 입힌다. 옷을 입히는 순서는 위→아래, 벗는 순서는 아래→위. 이 사이에 3-way handshake (TCP)와 TLS handshake가 끼어들어 추가 RTT를 소모한다. QUIC는 그 RTT를 없애려고 UDP 위에 TCP+TLS를 재발명했다."**

### 5개 가지 — 면접에서 이 순서로 풀어낸다

```
            [ROOT: 7번 옷 입히기 + TCP 신뢰성 + TLS 비밀/인증]
                                │
       ┌─────────┬──────────────┼──────────────┬─────────┐
       │         │              │              │         │
     ① OSI 7계층  ② 캡슐화       ③ TCP          ④ TLS     ⑤ QUIC/HTTP3
       (각 PDU)   (헤더 stack)   (3-way/close/  (1.2 vs    (UDP 재발명)
                                 흐름/혼잡)      1.3/0-RTT)
       │         │              │              │         │
   ┌───┼───┐  ┌──┼──┐         ┌─┼─┐         ┌──┼──┐
  L1~L4 책임  HTTP→TCP→IP    SYN ACK FIN    CHLO key    HOL blocking
  L5~L7 책임  → Eth → 비트    슬라이딩      ECDHE PFS    middlebox 문제
              (헤더 14+20+   윈도우 BBR     SNI ALPN
               20+ payload)   TIME_WAIT     인증서 체인
```

### 가지별 핵심 키워드

| 가지 | 키워드 1 | 키워드 2 | 키워드 3 |
|---|---|---|---|
| **① OSI 7계층** | 각 PDU (frame/packet/segment) | 책임 분리 | 5계층 vs 7계층 |
| **② 캡슐화** | 헤더 순서 (L7→L2) | MTU/MSS | 디캡슐화는 역순 |
| **③ TCP** | 3-way (SYN/SYN-ACK/ACK) | TIME_WAIT 2MSL | BBR vs CUBIC |
| **④ TLS** | 1.2 = 2 RTT, 1.3 = 1 RTT | SNI/ALPN | PFS / 인증서 체인 |
| **⑤ QUIC** | UDP + TCP기능 + TLS통합 | HOL blocking 제거 | 0-RTT replay |

### 면접 답변 흐름

> 면접관 질문 → 루트 문장 → 해당 가지 → 키워드 3개 → 인접 가지로 확장 → 측정 도구로 마무리

---

## 1. 가지 ①: OSI 7계층 — 왜 7개로 쪼갰나

### 1.1 백지 그리기 — 7층 빌딩

```
                       OSI 7-Layer Model
   ┌─────────────────────────────────────────────────────────────┐
   │ L7  Application   │ HTTP, gRPC, WS, SMTP, FTP, DNS, SSH      │
   │                   │ PDU: "data" (message)                     │
   ├─────────────────────────────────────────────────────────────┤
   │ L6  Presentation  │ TLS(때때로), ASN.1, JPEG, charset 변환    │
   │                   │ 직렬화 / 압축 / 암호화                       │
   ├─────────────────────────────────────────────────────────────┤
   │ L5  Session       │ TLS handshake, RPC session, NetBIOS       │
   │                   │ 연결 lifecycle / 인증                      │
   ├═════════════════════════════════════════════════════════════┤
   │ L4  Transport     │ TCP, UDP, QUIC(L4+L5+L6), SCTP            │
   │                   │ PDU: segment (TCP) / datagram (UDP)       │
   │                   │ 포트, 신뢰성, 흐름·혼잡 제어                  │
   ├─────────────────────────────────────────────────────────────┤
   │ L3  Network       │ IP(v4/v6), ICMP, IGMP                     │
   │                   │ PDU: packet                                │
   │                   │ 라우팅 (다른 네트워크 횡단)                   │
   ├─────────────────────────────────────────────────────────────┤
   │ L2  Data Link     │ Ethernet, Wi-Fi(802.11), ARP, MAC         │
   │                   │ PDU: frame                                 │
   │                   │ 같은 네트워크 내 노드-노드                    │
   ├─────────────────────────────────────────────────────────────┤
   │ L1  Physical      │ 광섬유, 구리(UTP/Coax), 무선 전파            │
   │                   │ PDU: bit                                   │
   │                   │ 신호 전달 (전압/광/전파)                     │
   └─────────────────────────────────────────────────────────────┘
                          ▲                            ▲
                  L5~L7 = "Host" 책임            L1~L4 = "Network" 책임
                  (애플리케이션이 신경 쓸 영역)    (커널/NIC/스위치/라우터)
```

> 외울 때: **"All People Seem To Need Data Processing"** (Application/Presentation/Session/Transport/Network/Data Link/Physical) — 위→아래.

### 1.2 직관 — 왜 계층화하나

**한 줄 비유**: 우편 시스템.
- L7: 편지 내용 ("안녕")
- L6: 편지지/봉투 규격 (한글로 쓸지 영어로 쓸지)
- L5: 우체국 창구 세션 (등기 vs 일반)
- L4: 우편번호로 어떤 우체국까지 갈지 (도시 단위)
- L3: 그 도시 안에서 어느 동
- L2: 그 동 안에서 어느 집 (집배원이 직접 배달)
- L1: 도로 / 트럭 / 비행기

**왜 계층화?** — **변화 격리**. L1이 구리에서 광섬유로 바뀌어도 L7의 HTTP는 한 줄도 안 바뀐다. Wi-Fi 표준이 5번 바뀌어도 IP는 그대로. 추상화의 힘.

**정확한 정의**: 각 계층은 **위 계층에 서비스를 제공**하고 **아래 계층의 서비스를 사용**한다. 계층 간 인터페이스만 고정되면 내부 구현은 자유.

### 1.3 각 계층의 책임 — 시니어가 외워야 할 것

| L | 이름 | PDU | 식별자 | 핵심 책임 | 대표 프로토콜 |
|---|---|---|---|---|---|
| **L7** | Application | data/message | (없음, app context) | 의미 있는 메시지 정의 | HTTP, gRPC, WebSocket, SMTP, FTP, DNS, SSH, IMAP |
| **L6** | Presentation | data | - | 직렬화·압축·암호화 | TLS(논쟁중), ASN.1, JPEG, MIME charset |
| **L5** | Session | data | - | 연결 lifecycle, 인증 | TLS handshake, RPC, NetBIOS, SOCKS |
| **L4** | Transport | segment/datagram | **포트번호** (16-bit) | 프로세스 식별, 신뢰성/흐름·혼잡 제어 | TCP, UDP, QUIC, SCTP |
| **L3** | Network | packet | **IP 주소** | 라우팅 (다른 네트워크 횡단), 단편화 | IP, ICMP, IGMP, IPsec |
| **L2** | Data Link | frame | **MAC 주소** | 같은 LAN 내 노드 식별, 오류 검출(CRC) | Ethernet, Wi-Fi, ARP, PPP, VLAN |
| **L1** | Physical | bit | - | 전기/광/전파 신호 | 1000BASE-T, 10G-SR, 802.11ax |

### 1.4 L6/L5의 모호함 — 실무에서는 사실상 사라진 두 계층

OSI 모델은 1984년 ISO가 만든 **참조 모델**. 그런데 인터넷은 OSI보다 먼저 진화한 **TCP/IP 모델**(1970s ARPANET)을 따랐고, TCP/IP는 5계층(혹은 4계층)이다.

- **L5 Session, L6 Presentation은 실무에서 별도 계층이 아니다.** 대부분의 책임이 **애플리케이션(L7) 안으로 흡수**되거나, **TLS가 L5/L6를 동시에 차지**한다.
- 시니어 면접에서 "TLS는 몇 계층인가?"는 트릭 질문. 정답: **"교과서적으로는 L5/L6 사이, 실무로는 그냥 'TLS layer'라 부른다. TCP 위, HTTP 아래."**

### 1.5 TCP/IP 5계층 모델 — 실무 표준

```
   OSI 7계층                      TCP/IP 5계층 (실무)
   ─────────                      ─────────────────
   L7  Application      ┐
   L6  Presentation     ├──────►   L5  Application  (HTTP/TLS 모두 여기)
   L5  Session          ┘
   L4  Transport        ──────►   L4  Transport
   L3  Network          ──────►   L3  Internet
   L2  Data Link        ──────►   L2  Link
   L1  Physical         ──────►   L1  Physical
```

> 4계층 모델(원조 TCP/IP RFC 1122)도 있다. L1+L2를 묶어 "Link"로 부르고 4계층으로 본다. 어차피 같은 이야기.

**왜 실무는 5계층(혹은 4계층)을 쓰나?**
- OSI는 **정치적으로 만들어진 표준** — ISO/ITU의 거대 위원회. 1990년대에 인터넷이 폭발하면서 OSI 스택(X.400, X.500 등)은 죽었다.
- TCP/IP는 **돌아가는 코드**가 먼저 있었고, 표준이 나중에 그걸 문서화 (RFC 793 TCP, 1981).
- 결국 "OSI 7"은 **개념 학습용 액자**, "TCP/IP 5"는 **실제 동작 모델**.

### 1.6 역사 — 왜 OSI가 졌나

| 연도 | 사건 |
|---|---|
| 1969 | ARPANET 시작 (TCP/IP의 조상) |
| 1974 | Vint Cerf + Bob Kahn의 TCP 논문 |
| 1981 | RFC 793 TCP, RFC 791 IP 표준화 |
| 1984 | OSI 7-layer 모델 ISO 7498 발표 |
| 1989 | Tim Berners-Lee가 HTTP/HTML 제안 (TCP/IP 위에) |
| 1990s | OSI 진영(X.400 메일, X.500 디렉토리)이 TCP/IP에 패배 |
| 2025 | OSI는 **교육용 모델**, 실무는 모두 TCP/IP |

**시니어 인사이트**: "OSI 모델"을 외우라는 면접관은 두 부류다. (1) 진짜 책 읽는 시니어 — 7층의 책임 분리를 이해하는지 보려는 것. (2) 책의 표면만 본 면접관 — 그냥 7개 이름 외웠는지 본다. (1)이면 이 챕터의 1.3을 줄줄 풀면 된다.

---

## 2. 가지 ②: 캡슐화 — 헤더 7개를 입히고 벗기

### 2.1 백지 그리기 — `GET /users/김면수`가 어떻게 와이어에 실리나

```
                  Client (브라우저)                                          Server
                  ─────────────────                                          ──────
   L7 (HTTP)     [GET /users/%EA%B9%80%EB%A9%B4%EC%88%98 HTTP/1.1            ▲
                  Host: example.com\r\nUser-Agent: ...\r\n\r\n]              │ L7
                                       │ TCP에게 넘김                        │ HTTP 파싱
                                       ▼                                     │
   L4 (TCP)      [TCP header 20+ bytes | HTTP payload                ]      │
                  src_port=51234 dst_port=443 seq=1 ack=0                    │ L4
                  flags=PSH+ACK win=65535 ...                                │ port로
                                       │ IP에게 넘김                          │  process 매핑
                                       ▼                                     │
   L3 (IP)       [IP header 20 bytes | TCP header | HTTP payload     ]      │
                  src=10.0.0.5 dst=93.184.216.34 ttl=64 proto=6(TCP)         │ L3
                  total_len=... checksum=...                                  │ routing 결과
                                       │ Ethernet에게 넘김                    │  최종 도착
                                       ▼                                     │
   L2 (Eth)      [Eth 14 | IP header | TCP header | HTTP payload | CRC 4 ]  │
                  dst_mac=aa:bb:cc:dd:ee:ff (next hop = 게이트웨이)            │ L2
                  src_mac=11:22:33:44:55:66 type=0x0800(IPv4)                │ MAC 검증
                                       │ NIC가 전기 신호로 변환                │
                                       ▼                                     │
   L1                          ─── bits on wire ───                          ▲
                            전압 변화 / 광 펄스 / 무선 전파                    │
                                       ▼                                     │
                              [라우터/스위치 N개 거쳐...]                       │
                                       ▼                                     │
                            서버 NIC가 비트 수신 → frame 복원
                            → L2 헤더 떼고 IP에 전달
                            → L3 헤더 떼고 TCP에 전달
                            → L4 헤더 떼고 process(:443)에 전달
                            → Nginx가 HTTP 파싱 → "GET /users/김면수"
```

### 2.2 헤더 사이즈 — 누가 얼마나 차지하나

```
┌────────┬───────────┬────────┬─────────────────────────┐
│ Eth 14 │ IP 20     │ TCP 20 │ HTTP payload (~500 bytes) │ + Eth CRC 4
└────────┴───────────┴────────┴─────────────────────────┘
   L2        L3         L4        L7
   ▲                    ▲
   │                    │
   "주소 헤더 3개"      "포트 + 시퀀스 헤더"

총 오버헤드: 14 + 20 + 20 + 4 = 58 bytes  (TLS 미포함, IPv4 + TCP 기본)
TLS 추가:    record header 5 + MAC/AEAD ~16 ≈ 21 bytes
IPv6:        IP 헤더 40 bytes (20 더 추가)
QUIC:        UDP 8 + QUIC variable + TLS 통합
```

**MTU = Maximum Transmission Unit**: 한 frame이 운반 가능한 **payload 최대 크기**. Ethernet은 보통 **1500 bytes**.

**MSS = Maximum Segment Size**: TCP segment의 payload 최대 크기. `MTU - IP_header(20) - TCP_header(20) = 1460 bytes` (IPv4).

```
   MTU 1500 (Ethernet payload)
   ┌──────────────────────────────────────────────┐
   │ IP 20 │ TCP 20 │      TCP payload = MSS 1460 │
   └──────────────────────────────────────────────┘

   * IPv6면 IP header 40 → MSS = 1440
   * VPN/IPsec 헤더 더해지면 MSS 더 작아짐 → fragmentation 위험
```

**MSS 협상**: SYN 패킷의 TCP option에 각자의 MSS를 광고. 더 작은 값을 채택.

### 2.3 각 계층 헤더의 핵심 필드 (시니어 운영 관점)

#### TCP 헤더 (20 bytes 기본, option 포함 시 최대 60)

```
   0                   1                   2                   3
   ┌──────────────────┬──────────────────┬──────────────────┬─────────┐
   │ Source Port (16) │ Dest Port (16)   │                            │
   ├──────────────────┴──────────────────┘                            │
   │ Sequence Number (32)                                              │
   ├──────────────────────────────────────────────────────────────────┤
   │ Acknowledgment Number (32)                                        │
   ├────┬────────┬──────────────────────────────────────────────────┐
   │HLen│Flags(9)│ Window Size (16)                                  │
   │  4 │SYN ACK │                                                   │
   │    │FIN RST │                                                   │
   │    │PSH URG │                                                   │
   │    │ECE CWR │                                                   │
   ├────┴────────┴──────────────────────────────────────────────────┤
   │ Checksum (16) │ Urgent Pointer (16)                              │
   ├──────────────────────────────────────────────────────────────────┤
   │ Options (variable: MSS, WScale, SACK, Timestamp, ...)             │
   └──────────────────────────────────────────────────────────────────┘
```

**시니어가 외울 필드 (4가지만)**:
- **Source/Dest Port**: 어느 프로세스의 socket인지 식별 (4-tuple = src_ip + src_port + dst_ip + dst_port).
- **Seq/Ack**: 신뢰성의 핵심. seq = 보낸 byte의 시작 번호, ack = "여기까지 받았으니 다음은 ack부터 보내달라".
- **Flags**: SYN(연결 시작), ACK(확인), FIN(정상 종료), RST(강제 종료), PSH(즉시 처리). 운영 진단의 90%는 이 5개 flag 조합.
- **Window**: 받을 수 있는 buffer 여유. 흐름 제어 (4.2).

> 디테일 (HLen 자릿수, checksum 알고리즘)은 시니어가 외울 필요 없다. flag와 의미만.

#### IP 헤더 (IPv4, 20 bytes 기본)

```
   ┌────┬─────┬─────────────┬──────────────────────────────────────┐
   │Ver │IHL  │ToS / DSCP   │ Total Length (16)                     │
   ├────┴─────┴─────────────┴──────────────────────────────────────┤
   │ Identification (16)     │ Flags(3) │ Fragment Offset (13)      │
   ├─────────────────────────┴──────────┴─────────────────────────┤
   │ TTL (8) │ Protocol (8) │ Header Checksum (16)                 │
   ├─────────┴──────────────┴────────────────────────────────────┤
   │ Source IP (32)                                                │
   ├──────────────────────────────────────────────────────────────┤
   │ Destination IP (32)                                           │
   └──────────────────────────────────────────────────────────────┘
```

**시니어가 외울 필드 (4가지)**:
- **Src/Dst IP**: 어떤 호스트인지.
- **TTL (Time To Live)**: 라우터 hop 하나당 1씩 감소. 0이 되면 패킷 drop + ICMP "Time Exceeded" 반환. **`traceroute`가 이걸 이용** (TTL 1, 2, 3... 보내며 누가 ICMP를 돌려보내는지로 경로 추적).
- **Protocol**: 위 계층 식별. **6 = TCP, 17 = UDP, 1 = ICMP**.
- **Fragmentation 필드**: MTU 초과 시 패킷 쪼개기 (현대는 PMTUD로 회피, IPv6는 fragmentation 자체가 라우터에서 금지).

#### Ethernet 헤더 (14 bytes + CRC 4)

```
   ┌──────────────────────┬──────────────────────┬─────────┬────────┐
   │ Dst MAC (6)          │ Src MAC (6)          │Type (2) │ payload│
   └──────────────────────┴──────────────────────┴─────────┴────────┘

   Type 필드:
     0x0800 = IPv4
     0x86DD = IPv6
     0x0806 = ARP
     0x8100 = VLAN tag
```

**시니어가 외울 것**: MAC 주소는 **같은 LAN 안에서만 의미**. 라우터를 넘으면 src/dst MAC이 매번 갱신 (next hop의 MAC). 반면 **IP는 종단까지 그대로** (NAT 제외).

### 2.4 인캡슐레이션의 순서 = 디캡슐레이션의 역순

```
   송신 (위→아래)              수신 (아래→위)
   ──────────────              ──────────────
   L7 message 생성             NIC가 비트 수신 → L2 frame 복원
        ↓                              ↓
   L4 header 붙임 (segment)    Eth 헤더 떼고 EtherType 확인 → IP로
        ↓                              ↓
   L3 header 붙임 (packet)     IP 헤더 떼고 Protocol 확인 → TCP로
        ↓                              ↓
   L2 header 붙임 (frame)      TCP 헤더 떼고 dst_port로 process 매핑
        ↓                              ↓
   NIC가 비트 전송              Nginx가 payload 받음 → HTTP 파싱
```

**핵심 통찰**: **상위 계층은 하위 계층 헤더의 존재를 모른다**. 브라우저가 HTTP를 만들 때 TCP/IP/Ethernet 헤더를 신경 쓰지 않는다. 추상화의 보상.

---

## 2-2. 🎯 한 요청을 따라가는 캡슐화 풀버전 — URL부터 MAC까지 (대규모 보강)

> 이 섹션은 한 줄의 요청 `GET /users/김면수`이 **L7부터 L1까지 어떻게 옷을 갈아입고**, **각 계층이 무엇을 검증**하며, **MAC 주소가 hop마다 어떻게 갱신**되는지를 byte 단위로 풀어낸다.
> 백지 면접에서 "OSI 7층을 처음부터 끝까지 풀어보세요"라는 요청을 받았을 때 막힘없이 풀 수 있는 분량.

### 2-2.1 OSI 7계층 책임 매트릭스 ⭐ (강화된 표)

| 계층 | 이름 | 책임 (한 줄) | PDU | 대표 헤더/프로토콜 | 주소 단위 | 검증 메커니즘 |
|---|---|---|---|---|---|---|
| **L7** | Application | end-user data **의미론** | message | HTTP, gRPC, FTP, SMTP, DNS | URL/path/method | semantic 검증 (Content-Length 일치, 비즈니스 규칙) |
| **L6** | Presentation | encoding / encryption / compression | message | TLS, JSON, ASN.1, gzip, MIME | n/a | TLS HMAC (1.2) / AEAD (1.3) |
| **L5** | Session | 세션 시작·유지·종료 | n/a | TLS handshake, NFS, RPC session | session id / ticket | session token 검증 |
| **L4** | Transport | end-to-end **신뢰성·순서·다중화** | segment (TCP) / datagram (UDP) | TCP, UDP, QUIC, SCTP | port | TCP checksum + seq/ack |
| **L3** | Network | end-to-end **라우팅** | packet | IPv4, IPv6, ICMP, IGMP | IP address | IP header checksum + TTL |
| **L2** | Data Link | next-hop **frame 전달** | frame | Ethernet, Wi-Fi, ARP, PPP, VLAN | MAC address | Ethernet FCS (CRC-32) + dst MAC 매치 |
| **L1** | Physical | **bit 전송** | bit | 광/구리/무선 | n/a | 신호 무결성 (이중 부호화, CSMA/CD) |

**시니어 사고법** — 이 표를 외우는 게 아니라, "어떤 책임이 어디서 처리되는가"를 본능적으로 매핑할 수 있어야 한다.

```
   "P99 latency가 튄다" → 어떤 계층?

   ├── L7 응답 자체가 느림           → 서버 코드 / DB / GC
   ├── L4 retransmit 多              → 손실 환경, BBR로 전환
   ├── L4 cwnd가 작음                → bufferbloat, 혼잡 제어 튜닝
   ├── L3 TTL 짧아 ICMP TIME_EXCEED  → VPN/multi-hop routing 검토
   ├── L3 fragmentation              → MTU mismatch, PMTUD 점검
   ├── L2 frame error 증가           → NIC/케이블/스위치 하드웨어
   └── L1 신호 noise                 → 광케이블·무선 환경
```

### 2-2.2 한 요청의 캡슐화 풀 시각화 — 헤더가 쌓이는 그림 ⭐

```
─────────────────────────────────────────────────────────────────────────────────
 STEP 1 — L7 (Application)
─────────────────────────────────────────────────────────────────────────────────
 브라우저가 만든 HTTP 메시지 (사람이 읽을 수 있는 텍스트):

   GET /users/%EA%B9%80%EB%A9%B4%EC%88%98 HTTP/1.1\r\n
   Host: example.com\r\n
   User-Agent: Mozilla/5.0 ...\r\n
   Accept: text/html\r\n
   \r\n

   ▶ 한글 '김면수'는 RFC 3986에 따라 percent-encoding (UTF-8 9 byte → 9 × %XX = 27 byte)
   ▶ method, path, version, headers, blank line(\r\n\r\n), body 구조
   ▶ 이게 L7의 PDU = "message"

─────────────────────────────────────────────────────────────────────────────────
 STEP 2 — L6 (Presentation / TLS)
─────────────────────────────────────────────────────────────────────────────────
 HTTPS이면 TLS record가 HTTP message를 감싼다:

   ┌───────────────────────┬─────────────────────────────────┬──────────────┐
   │ TLS Record Header (5) │ Encrypted Payload (HTTP bytes)  │ MAC / Auth   │
   ├───────────────────────┼─────────────────────────────────┼──────────────┤
   │ type=0x17 (app data)  │ AES-GCM 등으로 암호화된 HTTP    │ AEAD tag 16B │
   │ version=0x0303        │                                 │              │
   │ length (16bit)        │                                 │              │
   └───────────────────────┴─────────────────────────────────┴──────────────┘

   ▶ TLS 1.3 AEAD 사용 시 별도 MAC 필드는 없고 ciphertext 끝에 auth tag 16B
   ▶ 이 시점부터 path('/users/김면수')는 wire 상에서 암호화 → 도청자는 못 봄
   ▶ 다만 SNI(host)는 평문 (TLS 1.3 ECH 없으면 그대로 노출)

─────────────────────────────────────────────────────────────────────────────────
 STEP 3 — L4 (Transport / TCP)
─────────────────────────────────────────────────────────────────────────────────
 OS의 TCP stack이 TLS record bytes를 받아 TCP segment로 포장:

   ┌────────────────────────────────────────┬──────────────────────────────┐
   │ TCP Header (20~60 byte)                │ TLS record bytes (= payload) │
   └────────────────────────────────────────┴──────────────────────────────┘

   TCP header 핵심 (사용자가 외워야 할 4가지):
     ▶ src_port = 54321 (ephemeral, OS가 할당)
     ▶ dst_port = 443
     ▶ seq      = 1000   (이번 segment의 첫 byte 번호)
     ▶ ack      = 2000   (상대로부터 1999까지 잘 받았다)
     ▶ flags    = ACK+PSH
     ▶ window   = 65535  (내 recv buffer 여유)
     ▶ checksum = 0xABCD  ← L4 검증 (pseudo-header + 전체 segment)

   ▶ checksum 실패 시 segment 자체 폐기 → ACK 안 줌 → 재전송
   ▶ seq/ack 덕분에 손실·순서뒤바뀜 복구

─────────────────────────────────────────────────────────────────────────────────
 STEP 4 — L3 (Network / IP)
─────────────────────────────────────────────────────────────────────────────────
 OS의 IP layer가 TCP segment를 IP packet으로 포장:

   ┌──────────────────────────┬─────────────────────────────────────────────┐
   │ IP Header (20 byte)      │ TCP segment bytes (header + payload)         │
   └──────────────────────────┴─────────────────────────────────────────────┘

   IP header 핵심 (4가지):
     ▶ src_ip   = 10.0.0.5            (내 호스트 IP)
     ▶ dst_ip   = 142.250.0.0         (서버 IP, DNS 해결 결과)
     ▶ ttl      = 64                  (hop limit, router 한 번 거칠 때마다 -1)
     ▶ protocol = 6                   (= TCP, UDP는 17, ICMP는 1)
     ▶ checksum = 0x1234              ← L3 검증 (header 만! payload는 아님)

   ▶ IP header checksum 실패 → router가 즉시 polic. 통째로 drop
   ▶ TTL = 0이면 router가 ICMP TIME_EXCEEDED 회신 → traceroute의 동작 원리

─────────────────────────────────────────────────────────────────────────────────
 STEP 5 — L2 (Data Link / Ethernet)
─────────────────────────────────────────────────────────────────────────────────
 NIC(또는 NIC driver)가 IP packet을 Ethernet frame으로 포장:

   ┌──────────────────┬──────────────────────────────────────────┬──────────┐
   │ Eth Header (14)  │ IP packet bytes                          │ FCS (4)  │
   └──────────────────┴──────────────────────────────────────────┴──────────┘

   Ethernet header (14 byte):
     ▶ dst_mac   = AA:BB:CC:DD:EE:FF   ← 게이트웨이 MAC! (ARP로 알아냄)
     ▶ src_mac   = 00:1A:2B:3C:4D:5E   (내 NIC MAC)
     ▶ ethertype = 0x0800              (= IPv4, IPv6는 0x86DD, ARP는 0x0806)
   FCS (4 byte trailer):
     ▶ Frame Check Sequence — CRC-32, frame 전체 검증

   ⭐ 핵심: dst_mac은 "최종 서버의 MAC"이 아니라 "다음 hop의 MAC"
   ⭐ IP는 end-to-end, MAC은 hop-to-hop

─────────────────────────────────────────────────────────────────────────────────
 STEP 6 — L1 (Physical)
─────────────────────────────────────────────────────────────────────────────────
 NIC가 frame을 비트 스트림으로 변환 → 매체(구리/광/무선)에 신호로 송출:

   10101010 11110000 11001100 ...  (실제는 Manchester 같은 line code로 부호화)

   ▶ 이더넷은 frame 앞에 preamble (7 byte) + SFD (1 byte) 추가 → 수신측 클럭 동기
   ▶ frame 사이엔 IFG (Inter-Frame Gap, 96bit time) 두어 충돌 회피
```

**총 오버헤드 정리** (한 HTTPS GET 요청, IPv4):

```
   Eth 14 + IP 20 + TCP 20 + TLS record 5 + AEAD tag 16  =  75 byte 오버헤드
   + Eth FCS 4 + preamble/SFD 8 + IFG (gap)              =  실제 wire 86+ byte
   HTTP payload 500 byte 라면 → 약 14% 오버헤드
   payload가 짧을수록 오버헤드 비율 폭증 (small packet 문제 = Nagle)
```

### 2-2.3 헤더 byte 단위 풀 분해 (시각화)

#### TCP 헤더 풀 byte map (20 byte 기본)

```
  bit offset:   0           16          32          48          64
                ├───────────┼───────────┼───────────┼───────────┤
   byte 0~3   │  Source Port (16)        │  Dest Port (16)       │
              ├───────────────────────────┴───────────────────────┤
   byte 4~7   │  Sequence Number (32)                              │
              ├───────────────────────────────────────────────────┤
   byte 8~11  │  Acknowledgment Number (32)                        │
              ├──┬─────┬──────┬───────────────────────────────────┤
   byte 12~13 │HL│ rsv │flags │  Window Size (16)                  │
              │ 4│  6  │  6   │                                    │
              ├──┴─────┴──────┴───────────────────────────────────┤
   byte 14~15 │  Checksum (16)            │  Urgent Pointer (16)   │
              ├───────────────────────────┴───────────────────────┤
   byte 16~19 │  Options (MSS, WScale, SACK, Timestamp, ...)        │
              └───────────────────────────────────────────────────┘
```

| 필드 | 시니어가 외울 것 | 운영 의미 |
|---|---|---|
| src/dst port | 4-tuple의 절반 | 어느 process socket인가 |
| seq | 이번 byte 첫 번호 | 재전송·순서 보장 핵심 |
| ack | 다음에 받을 byte 번호 | 흐름 제어 핵심 |
| flags 6개 | SYN/ACK/FIN/RST/PSH/URG | 운영 진단 90%가 flag 조합 |
| window | recv buffer 여유 | 흐름 제어, 과부하 방지 |
| checksum | L4 검증 | pseudo-header 포함, payload 손상 감지 |

#### IP 헤더 풀 byte map (IPv4, 20 byte 기본)

```
   bit:        0     4     8        16            24           32
              ├─────┼─────┼────────┼─────────────┼────────────┤
   byte 0~3   │ Ver │ IHL │ ToS/DS │  Total Length (16)        │
              ├─────┴─────┴────────┼─────┬─────────────────────┤
   byte 4~7   │ Identification (16) │Flags│  Frag Offset (13)  │
              ├─────────────────────┴─────┴─────────────────────┤
   byte 8~11  │ TTL (8)  │ Protocol (8)  │  Header Checksum (16) │
              ├──────────┴───────────────┴────────────────────────┤
   byte 12~15 │ Source IP (32)                                     │
              ├───────────────────────────────────────────────────┤
   byte 16~19 │ Destination IP (32)                                │
              └───────────────────────────────────────────────────┘
```

| 필드 | 시니어 의미 | 운영 시그널 |
|---|---|---|
| src/dst IP | end-to-end 식별 | NAT 없으면 양 끝까지 그대로 |
| TTL | hop limit | traceroute가 이걸 이용 |
| protocol | 위 layer 식별 | 6=TCP, 17=UDP, 1=ICMP |
| total_len | IP packet 전체 | fragmentation 결정 기준 |
| frag 필드 | 분할 정보 | DF=1이면 분할 금지 → ICMP unreachable |
| header checksum | header 검증 | router가 매 hop 재계산 (TTL 변하므로) |

#### Ethernet header + FCS (14 + 4 byte)

```
   ┌──────────────────────────┬──────────────────────────┬──────────────┐
   │ Destination MAC (48bit)  │ Source MAC (48bit)       │ EtherType(16)│
   ├──────────────────────────┴──────────────────────────┴──────────────┤
   │ Payload (46~1500 byte)                                              │
   ├────────────────────────────────────────────────────────────────────┤
   │ Frame Check Sequence (CRC-32, 32bit)                                │
   └────────────────────────────────────────────────────────────────────┘

   EtherType:
     0x0800 = IPv4         0x86DD = IPv6
     0x0806 = ARP          0x8100 = VLAN tag (802.1Q)
     0x88CC = LLDP         0x8847 = MPLS unicast
```

### 2-2.4 각 계층의 검증·체크 메커니즘 ⭐⭐ (사용자 요청 핵심)

```
                    "패킷이 위조되거나 손상되면?"
                    각 계층이 독립적으로 검증한다.
                    ────────────────────────────

   L7  ┃ 비즈니스 검증 (서버 코드)
       ┃   ▶ Content-Length 일치
       ┃   ▶ JSON 스키마 / header 유효성
       ┃   ▶ 인증 토큰 / CSRF
       ┃   실패 → 4xx 응답
       ┃
   L6  ┃ TLS HMAC / AEAD tag
       ┃   ▶ 1.2: HMAC-SHA256으로 record 무결성
       ┃   ▶ 1.3: AES-GCM 같은 AEAD로 confidentiality + integrity 한 번에
       ┃   실패 → fatal alert → connection 종료
       ┃
   L4  ┃ TCP checksum + seq/ack
       ┃   ▶ checksum: pseudo-header(src/dst IP, proto, len) + TCP header + payload
       ┃           1's complement sum (16bit). 실패 → segment 폐기 → ACK 없음 → 재전송
       ┃   ▶ seq: 손실/순서 뒤바뀜 감지
       ┃   ▶ ack: 수신 확인. RTO 안에 못 받으면 재전송
       ┃   ▶ window: 받을 buffer 부족하면 0 win 광고 → 송신 정지
       ┃
   L3  ┃ IP header checksum + TTL + fragmentation
       ┃   ▶ checksum: header만 검증 (payload는 L4 책임)
       ┃           ★ router가 매 hop마다 재계산 (TTL이 변하니까)
       ┃   ▶ TTL: 0 되면 ICMP TIME_EXCEEDED 회신 + drop
       ┃           → 무한 routing loop 방지
       ┃   ▶ DF + MTU 초과 → ICMP "Fragmentation Needed" → PMTUD
       ┃
   L2  ┃ FCS (CRC-32) + dst MAC match
       ┃   ▶ FCS: frame 전체 (header+payload) CRC. 실패 → NIC가 즉시 drop
       ┃           통계에 'RX errors' 증가
       ┃   ▶ dst_mac이 내 MAC / broadcast / 가입한 multicast 아니면 NIC 폐기
       ┃           (promiscuous mode면 통과)
       ┃
   L1  ┃ 신호 무결성
       ┃   ▶ Manchester / 8b/10b 같은 line code → DC balance, clock recovery
       ┃   ▶ CSMA/CD (half-duplex): 충돌 감지 시 jam signal + 백오프
       ┃   ▶ 광/구리: BER (Bit Error Rate)이 높으면 L2 FCS 실패 폭증
```

**시니어 통찰** — 왜 같은 데이터를 **여러 계층에서 중복 검증**할까?

```
   "TCP checksum이 있으면 Ethernet FCS는 왜 또 있나?"

   계층별 책임 분리:
     ▶ FCS는 link-local 에러 (NIC 결함, 케이블 누전, 광 노이즈)를 즉시 폐기
        → router가 손상된 frame을 IP layer까지 올리지 않게
     ▶ TCP checksum은 end-to-end 에러 (router의 메모리 손상,
        kernel buffer 오염 등 link 이외 원인)를 잡음
     ▶ TLS HMAC/AEAD는 악의적 변조 (active attacker)를 잡음
        → checksum/FCS는 우연한 손상만 잡지, 적대적 변경은 못 잡음

   각 계층은 다른 신뢰 모델을 가정한다 — defense in depth.
```

### 2-2.5 MAC 주소가 hop마다 어떻게 바뀌는가 ⭐⭐⭐ (★ 사용자 명시 요청)

> "IP는 end-to-end, MAC은 hop-to-hop" — 이 한 문장이 네트워크 흐름의 핵심.

#### 그림: 3-hop 경로에서 IP/MAC 변화

```
   ┌────────────┐       ┌─────────────┐      ┌─────────────┐      ┌──────────┐
   │  Client    │       │  Router1    │      │  Router2    │      │  Server  │
   │ 10.0.0.5   │       │ 10.0.0.1    │      │ 192.0.2.1   │      │142.250.. │
   │ 00:1A:..   │       │ AA:BB:..1A  │      │ DD:EE:..2A  │      │ 99:88:.. │
   │            │       │   ..1B (out)│      │   ..2B (out)│      │          │
   └─────┬──────┘       └──────┬──────┘      └──────┬──────┘      └────┬─────┘
         │                     │                    │                  │
         │  ┌──────────────────────────────────────────────────────┐   │
         │  │ Hop 1: Client → Router1                              │   │
         │  │   IP   src=10.0.0.5     dst=142.250.0.0  (end-to-end)│   │
         │  │   MAC  src=00:1A:..     dst=AA:BB:..1A  ← Router1 MAC│   │
         │  └──────────────────────────────────────────────────────┘   │
         │                                                              │
         │                ┌─────────────────────────────────────────┐   │
         │                │ Hop 2: Router1 → Router2                │   │
         │                │   IP   src=10.0.0.5  dst=142.250.0.0     │   │
         │                │            (그대로!)                      │   │
         │                │   MAC  src=AA:BB:..1B  dst=DD:EE:..2A    │   │
         │                │            (Router1 OUT → Router2 IN)    │   │
         │                │   TTL: 64 → 63                            │   │
         │                │   IP checksum: 재계산                     │   │
         │                └─────────────────────────────────────────┘   │
         │                                          │                   │
         │                          ┌──────────────────────────────┐    │
         │                          │ Hop 3: Router2 → Server      │    │
         │                          │   IP   src=10.0.0.5          │    │
         │                          │        dst=142.250.0.0        │    │
         │                          │   MAC  src=DD:EE:..2B         │    │
         │                          │        dst=99:88:..  ← Server│    │
         │                          │   TTL: 63 → 62               │    │
         │                          └──────────────────────────────┘    │
         │                                                              │
         ▼                                                              ▼

   ★ IP src/dst: 처음부터 끝까지 동일 (NAT 없으면)
   ★ MAC src/dst: 매 hop마다 변경
   ★ TTL: hop마다 -1
   ★ IP header checksum: TTL이 변하니 매 hop 재계산
   ★ L4 이상은 router가 절대 건드리지 않음 (그게 router의 본질)
```

**왜 MAC이 hop마다 변하나?**

```
   MAC 주소는 같은 LAN(broadcast domain) 안에서만 의미가 있다.
   Router는 LAN의 경계.

   ┌─────────────────────┐         ┌──────────────────────┐
   │  LAN A              │ Router  │  LAN B               │
   │  10.0.0.0/24        │  ┌──┐   │  192.0.2.0/24        │
   │                     │  │  │   │                      │
   │  10.0.0.5 ──────────┼──┤  ├───┼─────  192.0.2.10     │
   │  (00:1A:..)         │  └──┘   │  (44:55:..)           │
   │                     │ 10.0.0.1│  192.0.2.1            │
   │                     │ AA:BB..1A│  AA:BB..1B           │
   └─────────────────────┘         └──────────────────────┘

   ▶ 10.0.0.5가 192.0.2.10에게 보낼 때:
     LAN A 안에선 dst_mac = 게이트웨이(10.0.0.1)의 MAC = AA:BB..1A
   ▶ Router가 frame을 받음 → MAC 헤더 떼버림
   ▶ Router의 라우팅 테이블에서 192.0.2.0/24는 LAN B 인터페이스로
   ▶ LAN B 인터페이스의 MAC(AA:BB..1B)을 src로, 192.0.2.10의 MAC(44:55..)을 dst로
     하여 새 Ethernet frame 조립
   ▶ 그래서 매 hop마다 MAC 갱신
```

#### Router의 일 — 한 frame이 들어와서 나갈 때까지

```
   ┌────────────────────────────────────────────────────────────┐
   │ Router 내부 처리                                              │
   ├────────────────────────────────────────────────────────────┤
   │                                                              │
   │ 1. NIC가 frame 수신                                           │
   │    ▶ FCS 검증                                                 │
   │    ▶ dst_mac == 내 MAC인지 확인                              │
   │    ▶ OK면 Ethernet header/FCS 떼버림 → IP packet만 남김       │
   │                                                              │
   │ 2. IP packet 검사                                             │
   │    ▶ IP header checksum 검증                                  │
   │    ▶ TTL > 1 인지 (1이면 -1 후 0 → ICMP TIME_EXCEEDED 회신)  │
   │    ▶ TTL -= 1                                                 │
   │    ▶ dst_ip로 routing table 조회                              │
   │       └ 다음 hop의 IP + outgoing interface 결정              │
   │                                                              │
   │ 3. 다음 hop MAC 조회                                          │
   │    ▶ ARP cache에 next-hop IP 있나? 있으면 그 MAC 사용         │
   │    ▶ 없으면 ARP request broadcast → 응답받아 cache 저장      │
   │                                                              │
   │ 4. 새 Ethernet frame 조립                                     │
   │    ▶ src_mac = outgoing interface MAC                         │
   │    ▶ dst_mac = next hop MAC                                   │
   │    ▶ ethertype = 0x0800 (IPv4 그대로)                         │
   │    ▶ IP header checksum 재계산 (TTL 바뀌었으니까)             │
   │    ▶ FCS 재계산                                               │
   │                                                              │
   │ 5. outgoing NIC로 frame 전송                                  │
   │                                                              │
   │ ★ TCP 이상은 절대 건드리지 않음 (그게 "router"의 정의)        │
   │   * NAT/firewall이 있으면 src_ip/src_port를 바꿀 수도 있지만 │
   │     그건 "router의 본업"이 아니라 부가 기능                   │
   └────────────────────────────────────────────────────────────┘
```

### 2-2.6 ARP — 같은 LAN에서 IP → MAC 알아내기 ⭐ (사용자 명시 요청)

> "내가 10.0.0.1(게이트웨이)에게 frame을 보내고 싶은데, 걔 MAC을 모른다. 어떻게 알아내지?"

#### ARP 동작 시퀀스

```
   상황: 클라이언트 10.0.0.5가 처음으로 게이트웨이 10.0.0.1과 통신하려 함
        ARP cache는 비어 있음

   STEP 1 — ARP Request (broadcast)
   ────────────────────────────────────────────────────────────
   클라이언트가 같은 LAN의 모든 호스트에게 외친다.

   Ethernet frame:
     ┌──────────────────────────────────────────────────────────┐
     │ dst_mac = FF:FF:FF:FF:FF:FF   ← broadcast                │
     │ src_mac = 00:1A:2B:3C:4D:5E   ← 내 MAC                   │
     │ ethertype = 0x0806            ← ARP                       │
     ├──────────────────────────────────────────────────────────┤
     │ ARP payload:                                              │
     │   htype = 1 (Ethernet)                                    │
     │   ptype = 0x0800 (IPv4)                                   │
     │   hlen = 6, plen = 4                                      │
     │   operation = 1 (request)                                 │
     │   sender_mac = 00:1A:2B:3C:4D:5E                          │
     │   sender_ip  = 10.0.0.5                                   │
     │   target_mac = 00:00:00:00:00:00  (모름)                  │
     │   target_ip  = 10.0.0.1                                   │
     │                                                            │
     │   "Who has 10.0.0.1? Tell 10.0.0.5"                       │
     └──────────────────────────────────────────────────────────┘

   STEP 2 — LAN 모든 호스트가 frame 받음
   ────────────────────────────────────────────────────────────
     ▶ broadcast이므로 NIC는 통과시킴
     ▶ 각 호스트는 ARP target_ip == 자기 IP인지 확인
     ▶ 자기 거 아니면 그냥 drop (단 sender 정보는 cache할 수도)

   STEP 3 — 10.0.0.1이 ARP Reply (unicast)
   ────────────────────────────────────────────────────────────
     ┌──────────────────────────────────────────────────────────┐
     │ dst_mac = 00:1A:2B:3C:4D:5E   ← 클라이언트                │
     │ src_mac = AA:BB:CC:DD:EE:FF   ← 게이트웨이                │
     │ ethertype = 0x0806                                         │
     ├──────────────────────────────────────────────────────────┤
     │ ARP payload:                                               │
     │   operation = 2 (reply)                                    │
     │   sender_mac = AA:BB:CC:DD:EE:FF                           │
     │   sender_ip  = 10.0.0.1                                    │
     │   target_mac = 00:1A:2B:3C:4D:5E                           │
     │   target_ip  = 10.0.0.5                                    │
     │                                                             │
     │   "10.0.0.1 is at AA:BB:CC:DD:EE:FF"                       │
     └──────────────────────────────────────────────────────────┘

   STEP 4 — 클라이언트 ARP cache 저장
   ────────────────────────────────────────────────────────────
     10.0.0.1 → AA:BB:CC:DD:EE:FF (expire in 60s ~ default)

     이후 같은 LAN의 frame은 cache로 즉시 보냄.
     expire되면 다시 ARP request.
```

#### ARP는 몇 계층? — "L2.5"

```
   ARP는 L2(MAC)와 L3(IP) 사이를 잇는다.

   ┌─────────────────────────────────────────────────────────┐
   │ ARP는 L3 정보(IP)를 알지만, 자기 자신은 L2 frame으로 전송 │
   │ 보통 'L2.5' 또는 'L2와 L3 사이'라고 부른다                │
   │                                                          │
   │ TCP/IP 모델에선 link layer에 포함 (실용주의 분류)        │
   └─────────────────────────────────────────────────────────┘
```

#### ARP의 흥미로운 변형 — Gratuitous ARP

```
   "Gratuitous ARP" — 묻지도 않았는데 자기 IP의 MAC을 알리는 broadcast.

   언제 쓰나?
     1. failover: VRRP/keepalived가 가상 IP를 새 노드로 옮길 때
        → "이제 10.0.0.100은 내 MAC이야!"라고 LAN 전체에 알림
        → 다른 호스트들 ARP cache 즉시 갱신
     2. IP 충돌 감지: 시작 시 자기 IP에 대해 broadcast → 응답 오면 충돌
     3. 일부 NIC가 link up 시 자동 발송
```

#### ARP의 보안 함정 — ARP Spoofing / Cache Poisoning

```
   ARP는 인증이 없다. 누구나 reply를 보낼 수 있다.

   공격 시나리오:
     ▶ 공격자가 LAN에서 "10.0.0.1(게이트웨이)는 내 MAC이야"라고 거짓 reply
     ▶ 피해자 ARP cache가 오염되어 게이트웨이 향한 frame이 공격자에게 감
     ▶ 공격자는 sniff/MITM 후 진짜 게이트웨이로 forward
     ▶ 평문 통신 노출 (HTTPS는 TLS 덕분에 그래도 안전)

   방어:
     ▶ static ARP entry (소수 중요 호스트)
     ▶ DAI (Dynamic ARP Inspection) — 엔터프라이즈 스위치 기능
     ▶ TLS 강제 (어차피 L7부터 암호화면 sniff 무력화)
```

### 2-2.7 한 frame이 NIC를 떠나 wire에 비트로 나가는 그림

```
   ┌──────────────────────────────────────────────────────────────┐
   │ Kernel space                                                  │
   │                                                                │
   │  TCP segment 생성 (kernel TCP stack)                          │
   │       ↓                                                        │
   │  IP packet 생성 (kernel IP stack)                              │
   │       ↓ (routing table 조회 → outgoing interface 결정)         │
   │  Netfilter hooks (iptables, nftables)                          │
   │       ↓                                                        │
   │  qdisc (queueing discipline: pfifo, fq, fq_codel)              │
   │       ↓                                                        │
   │  Driver TX ring                                                │
   │       ↓                                                        │
   └───────│───────────────────────────────────────────────────────┘
           ▼ (DMA로 NIC가 직접 메모리 읽음)
   ┌──────────────────────────────────────────────────────────────┐
   │ NIC hardware                                                  │
   │                                                                │
   │  1. Ethernet header 부착 (kernel이 미리 만들어 둠)             │
   │  2. FCS 계산 + 부착                                            │
   │  3. preamble (7B 0x55 반복) + SFD (1B 0xD5) 부착               │
   │  4. PHY 칩이 비트를 line code(예: 4B/5B, 8b/10b)로 부호화       │
   │  5. 전기 신호 / 광 펄스 / 무선 전파로 변환 → wire 송출         │
   │                                                                │
   │  ★ TCP/IP checksum offload, TSO/GRO, RSS 등은 NIC가 가속      │
   │     커널이 큰 segment 하나 넘기면 NIC가 MTU로 잘게 쪼개기      │
   └──────────────────────────────────────────────────────────────┘
           ▼
        ─── wire (구리/광/무선) ───
           ▼
   ┌──────────────────────────────────────────────────────────────┐
   │ 수신측 NIC                                                     │
   │                                                                │
   │  1. PHY가 line code 복호화 → bit stream                        │
   │  2. preamble로 clock 동기                                      │
   │  3. SFD 만나면 frame 시작                                      │
   │  4. FCS 검증 → 실패면 즉시 drop ('RX errors' 증가)             │
   │  5. dst_mac 매치 확인 → 아니면 drop (promisc 제외)             │
   │  6. DMA로 kernel buffer에 frame 적재                           │
   │  7. IRQ 또는 NAPI poll로 커널에 통지                            │
   │                                                                │
   │  ★ kernel은 GRO로 여러 frame을 합쳐 한 segment로               │
   │  ★ XDP가 있으면 user space보다 빨리 packet 처리·drop 가능      │
   └──────────────────────────────────────────────────────────────┘
```

### 2-2.8 IP는 end-to-end / MAC은 hop-to-hop — 한 그림 요약 ⭐

```
   ┌──────────────────────────────────────────────────────────────┐
   │ "이 패킷의 어떤 필드가 변하고, 어떤 게 그대로인가?"             │
   └──────────────────────────────────────────────────────────────┘

            Hop 1            Hop 2            Hop 3            Hop 4
   ┌──────┐  │   ┌──────┐    │   ┌──────┐    │   ┌──────┐    │
   │Client├──┼──►│  R1  ├────┼──►│  R2  ├────┼──►│  R3  ├────┼──► Server
   └──────┘  │   └──────┘    │   └──────┘    │   └──────┘    │

   ─────────────────────────────────────────────────────────────────
   필드            Hop 1       Hop 2       Hop 3       Hop 4
   ─────────────────────────────────────────────────────────────────
   src_ip          C           C           C           C           ← 불변
   dst_ip          S           S           S           S           ← 불변
   src_mac         C           R1_out      R2_out      R3_out      ← 변동
   dst_mac         R1_in       R2_in       R3_in       S_mac       ← 변동
   TTL             64          63          62          61          ← 감소
   IP checksum     A           B           C           D           ← 재계산
   TCP seq         1000        1000        1000        1000        ← 불변
   TCP checksum    X           X           X           X           ← 불변
   payload         ★           ★           ★           ★           ← 불변 (암호화)
   ─────────────────────────────────────────────────────────────────

   ★ NAT 박스가 있으면 src_ip / src_port도 hop 어디선가 바뀜
     - 그래서 NAT는 "L4 inspection을 하는 무거운 router"
```

### 2-2.9 캡슐화 풀버전 면접 답변 흐름 (백지 4분)

```
  면접관: "URL을 입력했을 때 패킷이 어떻게 만들어져서 서버까지 가는지 OSI 관점에서 설명하세요"

  ▶ 1분 — 큰 그림
    "L7부터 L1까지 단계마다 header를 입히는 캡슐화 과정이고,
     수신측은 반대로 한 층씩 벗기는 디캡슐레이션입니다."

  ▶ 2분 — 단계별
    "L7에서 HTTP 메시지가 생기고, HTTPS면 L6에서 TLS record로 암호화,
     L4(TCP)에서 src/dst port + seq/ack를 붙여 segment,
     L3(IP)에서 src/dst IP + TTL을 붙여 packet,
     L2(Ethernet)에서 src/dst MAC + ethertype + FCS를 붙여 frame,
     L1에서 NIC가 비트로 변환해 와이어로 송출합니다."

  ▶ 3분 — 검증
    "각 계층마다 독립적인 검증이 있습니다.
     L2 FCS는 link error, L3 checksum은 header 무결성 + TTL로 무한루프 방지,
     L4 TCP checksum + seq/ack로 end-to-end 신뢰성, L6 TLS는 변조 감지,
     L7은 비즈니스 검증입니다."

  ▶ 4분 — MAC이 변하는 이유
    "여기서 핵심은 IP는 end-to-end, MAC은 hop-to-hop이라는 점입니다.
     router는 LAN의 경계이고, MAC은 같은 LAN에서만 의미가 있습니다.
     매 hop마다 router가 Ethernet frame을 떼고 새로 조립하면서
     src/dst MAC을 갱신합니다. 다음 hop의 MAC은 ARP로 알아냅니다.
     ARP는 'IP를 가진 사람 누구?'라고 broadcast로 묻고 unicast로 답받는
     L2.5 프로토콜이고, 60초 정도 cache합니다."
```

---

## 3. 가지 ③ 진입 전 — 각 계층의 실제 프로토콜 한눈에

### 3.1 계층별 프로토콜 매트릭스

| 계층 | 신뢰성 영역 | 비신뢰성/특수 | 보안 |
|---|---|---|---|
| **L7** | HTTP/1.1, HTTP/2, gRPC | DNS(UDP기반), DHCP, NTP | SSH, HTTPS |
| **L6** | (압축/직렬화) | JPEG, MPEG, ASN.1 | (TLS는 여기 걸침) |
| **L5** | RPC, NetBIOS | - | **TLS handshake** |
| **L4** | **TCP** | **UDP**, **QUIC** (UDP 기반) | DTLS (UDP+TLS) |
| **L3** | (재전송 없음) | **IP**, ICMP, IGMP | IPsec |
| **L2** | (재전송 없음, CRC만) | **Ethernet**, **Wi-Fi**, ARP | WPA3, MACsec |
| **L1** | (단순 신호) | 광/구리/무선 | (물리 보안) |

### 3.2 L4의 4총사 — TCP / UDP / QUIC / SCTP

| 프로토콜 | 신뢰성 | 순서보장 | 흐름/혼잡 제어 | 용도 |
|---|---|---|---|---|
| **TCP** | ✅ | ✅ | ✅ | 웹, DB, SSH — 정확성 |
| **UDP** | ❌ | ❌ | ❌ | DNS, 게임, 영상 — 속도 |
| **QUIC** | ✅ | stream별 ✅ | ✅ (BBR 등) | HTTP/3 — 0-RTT + multiplexing |
| **SCTP** | ✅ | partial | ✅ | 통신사 SS7, WebRTC data channel |

> 시니어 면접 트릭: "왜 DNS는 UDP를 쓰나?" 답: "(1) RTT 절약 — TCP handshake 없이 한 번 왕복으로 끝, (2) 응답이 작아서 단편화 걱정 없음, (3) stateless — 서버 부하 적음. 단 응답이 512 bytes 넘으면 TCP fallback (RFC 5966), DNSSEC면 사실상 항상 TCP."

### 3.3 L3 — IP가 전부

- **IPv4**: 32-bit 주소 (43억 개). 이미 고갈 → NAT로 연명.
- **IPv6**: 128-bit (340 unde**c**illion 개). 전개는 30년째 진행 중.
- **ICMP**: 진단/오류 (ping, traceroute, "Destination Unreachable").
- **IGMP**: 멀티캐스트 그룹 관리.

### 3.4 L2 — Ethernet의 압도적 승리

1973년 Xerox PARC에서 Bob Metcalfe가 만든 Ethernet이 LAN 시장을 평정. Wi-Fi(802.11)는 사실상 "무선 Ethernet" — frame 포맷도 Ethernet 호환.

**ARP (Address Resolution Protocol)**: "이 IP에 해당하는 MAC 누구야?" 같은 LAN에서 브로드캐스트 질의. 결과는 ARP 캐시(`arp -a`)에 저장.

---

## 4. 가지 ③: TCP의 모든 것 — 3-way handshake부터 4-way close까지

### 4.1 백지 그리기 — TCP 3-way handshake

```
   Client                                  Server
   ──────                                  ──────
   CLOSED                                  LISTEN  (서버는 미리 accept 대기)
      │
      │ ① SYN  seq=x                              ┐
      │        flags=[SYN]                        │
      │  ─────────────────────────────────────►   │ "연결 요청
      │                                           │  내 시작 seq = x"
   SYN_SENT                                       │
                                                  ▼
                                          SYN_RECV (혹은 SYN_RECEIVED)
                                                  │
                                          ② SYN+ACK seq=y, ack=x+1
                                             flags=[SYN, ACK]            ┐
                                          ◄─────────────────────────     │ "OK, 받았다
                                                                          │  내 seq = y
                                                                          │  너의 다음은 x+1"
      │                                                                  │
   ESTABLISHED ◄────────                                                  │
      │                                                                  │
      │ ③ ACK   seq=x+1, ack=y+1                                         │
      │        flags=[ACK]                                                │
      │  ─────────────────────────────────────►                          │
      │                                                                  │
      │                                          ESTABLISHED ◄───────────┘
      │                                                  │
      │ ◄═══════ 양방향 데이터 송수신 가능 ═══════════►  │
      │                                                  │
```

**왜 3-way? 2-way로는 안 되나?**
- 둘 다 "**상대가 내 seq를 받았는지**"를 확인해야 한다. 그래서 각자 한 번씩 SYN을 보내고 상대가 ACK해야 한다. 그게 총 SYN×2 + ACK×2 = 4번처럼 보이지만, 가운데 두 개를 합쳐 SYN+ACK 1번으로 묶어서 **3번**.
- **2-way로는 server가 client의 ACK 수신 여부를 모름** → 옛 ESTABLISHED 흔적이 남는 문제(half-open).

**왜 초기 seq는 random?**
- **TCP sequence number prediction attack** 방지. 1995년 Kevin Mitnick이 이걸로 침입. 지금은 RFC 6528 — 암호학적 random + 4-tuple 해시.

### 4.2 TCP state diagram — 11개 상태

```
                              CLOSED
                                │
                  (client connect)│  │(server listen)
                                ▼  ▼
                            SYN_SENT  LISTEN
                                │  │
                  (recv SYN+ACK)│  │(recv SYN)
                       send ACK │  │send SYN+ACK
                                ▼  ▼
                          ESTABLISHED  SYN_RECV
                                  │
                  ┌───────────────┼───────────────┐
                  │ (close call)  │ (recv FIN)    │
                  │ send FIN      │ send ACK      │
                  ▼               ▼               │
              FIN_WAIT_1     CLOSE_WAIT           │
                  │ (recv ACK)    │ (close call)  │
                  ▼               │ send FIN      │
              FIN_WAIT_2          ▼               │
                  │           LAST_ACK            │
                  │ (recv FIN)    │ (recv ACK)    │
                  │ send ACK      ▼               │
                  ▼            CLOSED             │
              TIME_WAIT                           │
                  │ (2MSL timeout)                │
                  ▼                               │
              CLOSED ◄────────────────────────────┘
```

**시니어 관점 — 운영 시 보는 상태들**:
- **ESTABLISHED** 다수: 정상 트래픽.
- **TIME_WAIT** 폭증: active close 측에 누적 (보통 client 또는 LB). 2MSL(보통 60초) 동안 유지. 포트 고갈 위험 (10절).
- **CLOSE_WAIT** 폭증: 애플리케이션이 close() 안 호출. **거의 항상 코드 버그** (응답 후 socket.close() 누락 등).
- **SYN_RECV** 폭증: SYN flood 공격 or backlog 부족 (10절).
- **FIN_WAIT_2** 폭증: 상대가 FIN 안 보냄. 보통 firewall/NAT에서 idle 끊김.

### 4.3 SYN cookie / SYN flood 공격

**SYN flood 공격**: 공격자가 SYN만 잔뜩 보내고 ACK는 안 보냄.
- 서버는 SYN_RECV 상태로 대기. backlog queue가 가득 차면 정상 SYN도 거부.
- 1996년 Panix.com 사건이 시초 — 일주일간 마비.

**SYN cookie 방어 (RFC 4987)**:
- 서버가 SYN_RECV 상태를 **기억하지 않음**. 대신 SYN+ACK의 초기 seq에 **암호학적으로 인코딩된 정보**를 박아 보냄.
- 정상 client는 ACK 응답에 그 seq+1을 담아 보냄 → 서버가 디코드해서 검증 → 그제서야 ESTABLISHED.
- 효과: backlog가 무한대처럼 동작. 단점: TCP option(SACK, WScale 등) 일부 손실 가능.
- 활성화: `sysctl net.ipv4.tcp_syncookies=1` (Linux 기본).

### 4.4 TCP Fast Open (TFO, RFC 7413)

**문제**: 3-way handshake가 1 RTT를 소모. 짧은 요청(GET 1개)에는 핸드셰이크가 본 데이터보다 비싸다.

**TFO**: 처음 연결 시 서버가 **TFO cookie** 발급 → 다음 연결에서 client가 SYN에 그 cookie + payload를 함께 실어 보냄 → 서버가 cookie 검증되면 즉시 데이터 처리.

```
   일반 TCP:                    TFO:
   ─────────                    ────
   SYN ──►                      SYN + data + cookie ──►
   ◄─ SYN+ACK                   ◄─ SYN+ACK + data
   ACK + data ──►               ACK ──►
   (1 RTT 후에야 data 시작)      (0 RTT! data가 SYN과 동시)
```

**현실**: Chrome/Firefox 지원 종료 또는 비활성. 이유: middlebox(방화벽, NAT)가 TFO option 모르면 SYN을 drop. QUIC가 이 역할을 대신함 (8절).

### 4.5 흐름 제어 (Flow Control) — Sliding Window

**문제**: 빠른 sender → 느린 receiver. Receiver buffer overflow.

**해결**: TCP header의 **Window** 필드 (16-bit, 즉 64KB).
- Receiver: "내 buffer에 들어갈 수 있는 byte 수 = N. 더 보내지 마." → ACK에 win=N 광고.
- Sender: 광고된 window 안에서만 unacked byte 유지.

```
   Sender의 보낼 데이터:
   [이미 ack됨][전송됨, ack 대기중][아직 전송 안 함]
                ◄─── window ───►

   Receiver가 ACK + win=10000 보내면 → window 10000으로 갱신
   Receiver가 ACK + win=0 보내면     → sender 멈춤 (zero window)
```

**Window Scaling (RFC 7323)**: 16-bit는 max 64KB. 100Gbps × 100ms RTT면 너무 작음. SYN option에서 window scale factor (max 14) 협상 → 실효 window = `win << scale` (max 1GB).

**시니어 진단**: `ss -tin`으로 cwnd / rwnd / rcv_space 확인.

### 4.6 혼잡 제어 (Congestion Control) — Tahoe → Reno → CUBIC → BBR

**문제**: 흐름 제어는 sender-receiver 양자 간만. 그러나 **네트워크 중간 라우터가 혼잡**하면? → 패킷 drop → retransmit → 더 혼잡 → **혼잡 붕괴(congestion collapse)**.

**1986년 사건**: ARPANET이 32 kbps로 떨어졌다. Van Jacobson이 진단 → 혼잡 제어 알고리즘 발명.

#### 진화 타임라인

| 연도 | 알고리즘 | 핵심 아이디어 | 트리거 |
|---|---|---|---|
| 1988 | **TCP Tahoe** | Slow Start + Congestion Avoidance + Fast Retransmit. 손실 시 cwnd → 1 | Van Jacobson 논문 |
| 1990 | **TCP Reno** | + Fast Recovery. 손실 시 cwnd → cwnd/2 (덜 가혹) | Tahoe의 회복 속도 개선 |
| 2006 | **CUBIC** | cwnd를 시간의 3차 함수로 — 고속·고지연 망에 유리 | Linux 2.6.19 기본 (지금도) |
| 2016 | **BBR** | **손실이 아닌 RTT + bandwidth로 cwnd 결정** ⭐ | Google이 YouTube 적용, P50 latency 14% 감소 |

#### Slow Start + Congestion Avoidance (Tahoe/Reno 공통)

```
   cwnd
    │            ╱ Congestion Avoidance (linear: +1/RTT)
    │          ╱╱
    │        ╱╱
    │      ╱╱
    │    ╱╱ ◄── ssthresh (한계 도달)
    │  ╱╱
    │╱╱        Slow Start (exponential: ×2/RTT)
    │
    └───────────────────────────────► time
```

**Slow Start**: cwnd를 RTT마다 2배. 즉 1 → 2 → 4 → 8 → 16... 이름과 달리 **매우 빠름**. "당시(1988)의 다른 알고리즘 대비 느리다"는 의미.

**Congestion Avoidance**: ssthresh 넘으면 linear 증가 (+1 MSS per RTT). 조심스럽게.

**Loss event**: ssthresh = cwnd/2, cwnd = 1 (Tahoe) or cwnd/2 (Reno).

#### CUBIC — 왜 Linux 기본인가

- Reno는 RTT가 길수록 회복이 느림 (1 RTT당 +1 MSS). 100ms RTT, 10Gbps 망에서는 거의 회복 불가.
- CUBIC: 시간 함수로 cwnd 증가. 손실 후 W_max에서 빠르게 W_max 직전까지 도달 → 그 후 천천히.

#### BBR — 게임체인저

**기존 모든 알고리즘은 "loss-based"**: 패킷 손실 = 혼잡 신호. 그러나:
- 무선 망: 손실의 대부분이 noise (혼잡 아님).
- Bufferbloat: 라우터 buffer가 너무 커서 손실 전에 latency가 폭발.

**BBR**: 손실을 보지 않는다. 대신:
- **Bottleneck Bandwidth** (max BW 측정)
- **Round-trip propagation Time** (min RTT 측정)
- 보낼 양 = `BW × RTT`. 그 이상은 단순히 buffer를 채우는 것 (latency 증가만).

**효과**:
- Google YouTube: throughput +14%, latency -33% (P95).
- Spotify: rebuffering -23%.
- 단점: BBR vs CUBIC 같이 쓰면 BBR이 점유율을 너무 가져감 (공정성 문제). BBR v2/v3에서 개선 중.

**활성화 (Linux)**:
```bash
sudo modprobe tcp_bbr
sudo sysctl net.ipv4.tcp_congestion_control=bbr
sudo sysctl net.core.default_qdisc=fq
```

### 4.7 Nagle 알고리즘 vs TCP_NODELAY

**Nagle (1984, RFC 896)**: 작은 segment를 모아서 보냄. 작은 패킷(1 byte 작성에 41 byte 오버헤드)이 망을 마비시키는 것을 방지.

**규칙**: 미확인 segment가 있으면 작은 데이터를 buffer에 모음. 큰 데이터 or ACK 도착 시 전송.

**Delayed ACK** (1989)와 결합 시 문제: 양쪽이 서로 기다림. 200ms 지연 발생 (대화형 앱에 치명적).

**TCP_NODELAY**: Nagle 끄기. **HTTP 클라이언트는 거의 항상 NODELAY** (대화형, latency 우선). Bulk transfer(파일 업로드)는 NODELAY 끄는 게 효율적.

```c
// Linux/BSD
int flag = 1;
setsockopt(fd, IPPROTO_TCP, TCP_NODELAY, &flag, sizeof(flag));
```

```java
// Java
socket.setTcpNoDelay(true);
```

### 4.8 TCP 4-way close

```
   Client                                  Server
   ──────                                  ──────
   ESTABLISHED                             ESTABLISHED
      │
      │ ① FIN  seq=u                              ┐
      │  ─────────────────────────────────────►   │ "보낼 거 끝"
   FIN_WAIT_1                                     │
                                                  ▼
                                          CLOSE_WAIT
                                                  │
                                          ② ACK   ack=u+1
                                          ◄─────────────────────  ┐
                                                                  │ "알겠음. 잠깐
   FIN_WAIT_2 ◄─────────                                          │  나도 정리할 게 있음"
                                                                  │
                                              [server 측에서                    
                                               남은 데이터 송신,              
                                               application close()]            
                                                  │                            
                                          ③ FIN  seq=v                         
                                          ◄────────────────────              
                                                  │
   TIME_WAIT ◄──────────                          ▼                         
      │                                  LAST_ACK
      │ ④ ACK  ack=v+1
      │  ─────────────────────────────────────►
      │                                  CLOSED
      │
      │ [2MSL 대기 (보통 60초)]
      ▼
   CLOSED
```

**왜 4-way?** TCP는 **half-close**를 허용. Client가 FIN 보냈다고 server도 즉시 FIN을 보내는 게 아니라, server는 남은 데이터를 다 보낸 후 자기 close를 호출한 시점에 FIN. 그래서 ACK와 FIN이 분리.

**TIME_WAIT 2MSL의 이유 (시니어 면접 단골)**:
- **MSL (Maximum Segment Lifetime)**: 패킷이 네트워크에 떠다닐 수 있는 최대 시간 (RFC 793: 2분, Linux 기본: 30초).
- **2MSL을 기다리는 이유 2가지**:
  1. **마지막 ACK 손실 대비**: 만약 ④의 ACK가 손실되면 서버는 ③의 FIN을 재전송. 그때 client는 다시 ACK를 보내야 함. 즉시 CLOSED로 가면 못함.
  2. **옛 segment 격리**: 같은 4-tuple로 즉시 새 연결 만들면, 이전 연결의 지연된 segment가 새 연결로 흘러들어옴. 2MSL 후엔 그런 segment는 다 죽었다.

**TIME_WAIT 운영 함정**: client/LB가 active close 측이면 TIME_WAIT 누적. ephemeral port range (보통 32768~60999)가 고갈되면 새 연결 못 만듦.

해결책:
- `net.ipv4.ip_local_port_range` 확장.
- `net.ipv4.tcp_tw_reuse=1` (Linux): 안전한 경우 TIME_WAIT socket 재사용.
- `SO_REUSEADDR`: bind 시 TIME_WAIT socket 무시. (주의: 데이터 혼선 가능, 같은 4-tuple은 회피.)
- **keepalive HTTP 사용** — 연결을 만들고 재사용 → close 빈도 감소.

### 4.9 RST 패킷 — 5가지 발생 케이스

RST = 강제 종료. FIN과 달리 데이터 손실 가능, 즉시 CLOSED.

| 케이스 | 시나리오 |
|---|---|
| 1. 비존재 포트로 SYN | listen 안 하는 포트 → 서버가 RST 회신 |
| 2. half-open 감지 | 한쪽이 reboot/crash 후 옛 연결로 데이터 옴 → 받은 쪽이 RST |
| 3. `SO_LINGER(0)`로 close | 애플리케이션이 강제 abort 요청 |
| 4. 방화벽 차단 | iptables `-j REJECT --reject-with tcp-reset` |
| 5. application crash | 프로세스 죽으면 커널이 socket을 강제 close하며 RST |

**진단**: `tcpdump 'tcp[tcpflags] & tcp-rst != 0'`로 RST 추적.

### 4.10 Retransmission, RTO, Fast Retransmit, SACK

**RTO (Retransmission Timeout)**: ACK 안 오면 재전송할 시간.
- 추정: `RTO = smoothed_RTT + 4 × RTT_variance` (Jacobson/Karels 알고리즘).
- 손실 시 exponential backoff: RTO → 2×RTO → 4×RTO ... (RFC 6298).

**Fast Retransmit**: 3개의 dupACK 받으면 RTO 안 기다리고 즉시 재전송.
```
   Sender:  pkt1 pkt2 pkt3 pkt4 pkt5
                  ✗   ✓   ✓   ✓     (pkt2 손실)
   Receiver: ACK2 ACK2 ACK2 ACK2    (모두 "다음에 pkt2 줘")
                          ▲
                  3 dupACK → 즉시 pkt2 재전송
```

**SACK (Selective ACK, RFC 2018)**: "pkt2 외엔 3,4,5 다 받았어"를 알릴 수 있게. Reno는 pkt2 손실 시 pkt2부터 전체 재전송 (cumulative ACK 한계). SACK은 pkt2만 재전송.

**TCP Keepalive (RFC 1122)**:
- TCP level: 2시간 idle 후 keepalive probe → 9회 실패면 socket dead. 너무 길어서 거의 안 씀.
- 운영 실무: application layer keepalive (HTTP keep-alive, gRPC PING) 사용.

---

## 5. 가지 ④: TLS — 비밀과 인증

### 5.1 직관 — 왜 TLS인가

**3가지 보장**:
1. **Confidentiality (기밀성)**: 중간자가 내용을 못 봄. (대칭 암호 — AES)
2. **Integrity (무결성)**: 중간자가 내용을 바꾸면 들킴. (MAC/AEAD)
3. **Authenticity (인증)**: 서버가 자기가 주장하는 그 서버 맞음. (인증서 + CA 체인)

**TLS = Transport Layer Security**. SSL 1.0/2.0/3.0의 후계 (이름만 바뀜, 본질은 같은 라인). 2025년 현재 TLS 1.2, 1.3이 운용.

### 5.2 백지 그리기 — TLS 1.2 handshake (2 RTT)

```
   Client                                  Server
   ──────                                  ──────
   [TCP 3-way 완료 후]
      │
      │ ① ClientHello
      │   - TLS version: 1.2
      │   - cipher suites: [AES-256-GCM, CHACHA20, ...]
      │   - client_random (32 bytes)
      │   - SNI: example.com   ◄── 서버는 vhost 라우팅
      │   - ALPN: [h2, http/1.1] ◄── 위 계층 협상
      │  ─────────────────────────────────────►
      │
      │   ② ServerHello + Certificate + ServerKeyExchange + ServerHelloDone
      │     - 선택된 cipher: AES-256-GCM
      │     - server_random
      │     - 인증서 체인 (leaf + intermediate)
      │     - ECDHE public key + 서명
      │  ◄─────────────────────────────────────
      │     
      │ [Client가 인증서 체인 검증: leaf → intermediate → root CA]
      │
      │ ③ ClientKeyExchange + ChangeCipherSpec + Finished
      │   - client ECDHE public key
      │   - "이제부터 암호화"
      │   - 지금까지 메시지의 MAC (검증용)
      │  ─────────────────────────────────────►
      │
      │   ④ ChangeCipherSpec + Finished
      │     - "나도 암호화"
      │     - MAC
      │  ◄─────────────────────────────────────
      │
      │ ═══════ 암호화된 application data 시작 ═══════
      │
      │ ⑤ GET / HTTP/1.1 ... (암호화됨)
      │  ─────────────────────────────────────►

   총 RTT: 3-way(1) + TLS 1.2(2) = 3 RTT before first byte
```

### 5.3 TLS 1.3 — 1 RTT (RFC 8446, 2018)

**핵심 아이디어**: ClientHello에 **추측한 key share를 미리 박아 보냄**. 서버가 그 그룹을 받아들이면 한 번에 끝.

```
   Client                                  Server
   ──────                                  ──────
      │
      │ ① ClientHello + key_share (X25519, P-256 후보)
      │   + signature_algorithms + ALPN + SNI
      │  ─────────────────────────────────────►
      │
      │   ② ServerHello + key_share (선택된 그룹)
      │     + Certificate + CertificateVerify + Finished
      │     [이 메시지부터 이미 암호화됨]
      │  ◄─────────────────────────────────────
      │
      │ [인증서 검증]
      │
      │ ③ Finished + application data
      │  ─────────────────────────────────────►

   총 RTT: 3-way(1) + TLS 1.3(1) = 2 RTT before first byte
   (TLS만 보면 1 RTT)
```

**TLS 1.3의 6대 변화**:
1. **1 RTT 기본** (위).
2. **0-RTT (early data)**: 재방문 시 PSK(Pre-Shared Key)로 ClientHello에 application data를 즉시 실어 보냄 → 0 RTT.
3. **legacy 제거**: RSA key exchange, 3DES, MD5, SHA-1, RC4 모두 삭제. **PFS(Perfect Forward Secrecy) 강제** (ECDHE만).
4. **AEAD 강제**: GCM, ChaCha20-Poly1305 — MAC과 암호화 통합 cipher만 허용.
5. **ServerHello부터 암호화**: 1.2에서는 cleartext였던 Certificate가 1.3에서는 암호화 (덜 metadata leak).
6. **handshake 메시지 인증** 강화: signed transcript.

### 5.4 0-RTT의 위험 — Replay Attack

**문제**: 0-RTT는 client가 보낸 데이터를 server가 "본 적 있는지" 모름. 공격자가 그 데이터를 캡처해서 다시 보내면 서버는 또 처리 (=replay).

**예**: `POST /transfer?to=bob&amount=100` 0-RTT로 보냄 → 공격자가 캡처 → 다시 보냄 → 100원 또 송금.

**완화**:
- 0-RTT 데이터는 **idempotent**한 것만 (GET 정도).
- Server-side anti-replay: PSK + obfuscated_ticket_age 기반 nonce 검사. 단 완벽하지 않음.
- 운영 권장: **민감 요청은 0-RTT 금지**. CDN(Cloudflare/Fastly)도 0-RTT를 GET에만 허용.

### 5.5 인증서 체인 검증

```
   ┌──────────────────────────────────────────────────┐
   │           Root CA  (브라우저/OS trust store)       │
   │           예: ISRG Root X1, DigiCert Root         │
   │           서명자: 자기자신 (self-signed)           │
   └──────────────────────────────────────────────────┘
                          ▲
                          │ 서명
                          │
   ┌──────────────────────────────────────────────────┐
   │           Intermediate CA                          │
   │           예: Let's Encrypt R3                     │
   │           서명자: Root CA                          │
   └──────────────────────────────────────────────────┘
                          ▲
                          │ 서명
                          │
   ┌──────────────────────────────────────────────────┐
   │           Leaf Certificate (서버 인증서)            │
   │           예: example.com                          │
   │           서명자: Intermediate CA                  │
   │           공개키 + 도메인 + 유효기간 + SAN          │
   └──────────────────────────────────────────────────┘
```

**검증 흐름**:
1. Server가 leaf + intermediate를 보냄.
2. Client가 leaf의 서명을 intermediate 공개키로 검증.
3. Intermediate의 서명을 root CA 공개키로 검증 (브라우저 trust store에 root가 있어야).
4. 모든 단계 OK + leaf의 도메인이 SNI와 일치 + 유효기간 + revocation 미체크 → 신뢰.

**Revocation 체크**:
- **CRL (Certificate Revocation List)**: 무거움, 거의 안 씀.
- **OCSP (Online Certificate Status Protocol)**: 매 연결마다 CA에 질의 → privacy/latency 문제.
- **OCSP Stapling**: 서버가 미리 OCSP 응답을 받아 TLS handshake에 첨부 → 빠름.
- **현실**: 브라우저들이 점점 revocation 검사를 미루거나 생략. 단명 인증서(90일) 의존 (Let's Encrypt).

### 5.6 SNI — Server Name Indication

**문제**: 한 IP에 여러 도메인 (vhost). 서버는 어느 도메인의 인증서를 보낼지 어떻게 아나? TLS handshake는 HTTP 요청 전이라 Host 헤더 못 봄.

**SNI**: ClientHello의 extension에 도메인 평문으로 박아 보냄 → 서버가 그걸 보고 인증서 선택.

**Encrypted SNI / ECH (Encrypted Client Hello, RFC 9180)**: SNI도 metadata leak. ECH는 SNI까지 암호화. 2024년부터 Cloudflare/Firefox 지원 시작.

### 5.7 ALPN — Application Layer Protocol Negotiation

**문제**: HTTPS로 연결한 후 HTTP/1.1인지 HTTP/2인지 어떻게 정하나?

**ALPN**: ClientHello에 후보 protocol 목록 (예: `[h2, http/1.1]`), 서버가 ServerHello에서 하나 선택.

**왜 중요**: HTTP/2 negotiation은 ALPN이 사실상 유일한 메커니즘. (HTTP/1.1 Upgrade도 있지만 거의 안 씀.)

### 5.8 PFS — Perfect Forward Secrecy

**문제 시나리오**: 서버의 private key가 5년 후 유출. 공격자가 5년 전 캡처해둔 모든 TLS 트래픽을 복호화할 수 있나?

- **RSA key exchange (옛 방식)**: ✅ 복호화 가능 — RSA private key로 session key 복원. **Forward Secrecy 없음**.
- **ECDHE key exchange**: ❌ 불가능. Session key가 양쪽 ephemeral key로 만들어졌고, 그 ephemeral key는 메모리에서 사라진 지 오래. **PFS 보장**.

**TLS 1.3은 PFS를 강제** (ECDHE/DHE만 허용). 1.2는 옵션이지만 모던 cipher suite는 모두 PFS.

### 5.9 암호학 짧게 — 시니어가 외워야 할 것

| 종류 | 대표 | 용도 |
|---|---|---|
| **대칭 암호** (symmetric) | AES-128/256, ChaCha20 | 빠름. session 동안 본 데이터 암호화. 같은 key로 암/복호화 |
| **비대칭 암호** (asymmetric) | RSA, ECDSA, Ed25519 | 느림. handshake에서 인증/서명. 공개키/개인키 짝 |
| **키 교환** | ECDHE, X25519 | 양쪽이 안 만나고 같은 session key 만들기. PFS 핵심 |
| **해시** | SHA-256, SHA-384 | 무결성, MAC, 인증서 서명 입력 |
| **AEAD** | AES-GCM, ChaCha20-Poly1305 | 암호화 + 무결성 한 번에. TLS 1.3 강제 |

**핵심 인사이트**: **대칭은 빠르지만 키 교환이 문제**, **비대칭은 키 교환 가능하지만 느림**. 그래서 **비대칭으로 키 교환 → 대칭으로 데이터 전송** = TLS의 본질.

### 5.10 TLS의 인캡슐레이션 위치

```
   ┌────────────────────────────────────────────────────────────┐
   │ HTTP/2 (h2)                                                 │
   ├────────────────────────────────────────────────────────────┤
   │ TLS Record (5 byte header + AEAD)                          │
   │  - ContentType (1): Handshake / Application / Alert / CCS   │
   │  - Version (2)                                              │
   │  - Length (2)                                               │
   ├────────────────────────────────────────────────────────────┤
   │ TCP (20 byte header)                                        │
   ├────────────────────────────────────────────────────────────┤
   │ IP (20 byte header)                                         │
   ├────────────────────────────────────────────────────────────┤
   │ Ethernet (14 + 4)                                           │
   └────────────────────────────────────────────────────────────┘
```

TLS는 TCP 위에서 payload를 통째로 감쌈. **wireshark로 TCP segment를 봐도 내용은 암호화**. 다만 SNI는 ClientHello 평문이라 보임 (ECH 전).

---

## 6. 가지 ⑤: QUIC + HTTP/3 — TCP를 버린 이유

### 6.1 직관 — 왜 새로 만들었나

TCP의 4대 한계:
1. **Head-of-Line Blocking (HOL)**: HTTP/2는 multiplexing이지만 TCP 위라서 segment 하나 loss → 그 뒤 모든 stream blocked.
2. **Handshake RTT**: TCP 3-way + TLS handshake = 2~3 RTT.
3. **Connection migration 불가**: IP 바뀌면 (Wi-Fi → 4G) 연결 끊김.
4. **OS kernel에 박혀 있음**: 신기능 배포에 OS upgrade 필요 → 10년 단위 진화.

QUIC (2012 Google → 2021 RFC 9000):
- **UDP 위에** TCP의 기능(재전송, 흐름·혼잡 제어) + TLS 1.3 통합.
- **userspace 구현**: app과 함께 배포 → 빠른 진화.
- **Connection ID**: IP가 바뀌어도 같은 connection.

### 6.2 백지 그리기 — TCP+TLS vs QUIC

```
   기존 HTTPS (HTTP/2 over TLS over TCP):
   ─────────────────────────────────────
                                            
        TCP SYN ──────►
   ◄── TCP SYN+ACK
        TCP ACK ──────►                     ┐ 1 RTT (TCP)
                                            ┘
        ClientHello ──►
   ◄── ServerHello + Cert + Finished        ┐ 1 RTT (TLS 1.3)
        Finished + GET /  ──►               ┘
                                            
   ◄── 200 OK ...                           ┐ 1 RTT (first byte)
                                            ┘
   총: 3 RTT


   QUIC (HTTP/3):
   ──────────────
                                            
        Initial + ClientHello + key_share ──►
                                                    ┐ 1 RTT
   ◄── Initial + ServerHello + cert + Finished      │ (TCP + TLS 동시)
        Handshake + GET / ──►                       ┘
                                            
   ◄── 200 OK ...                           ┐ 1 RTT (first byte)
                                            ┘
   총: 2 RTT (재방문 시 0-RTT 가능)
```

### 6.3 QUIC의 stream-level HOL blocking 제거

```
   HTTP/2 over TCP:
   ────────────────
   stream A: pkt1 pkt2 pkt3
   stream B: pkt4 pkt5 pkt6

   wire 순서: pkt1 pkt2 ✗ pkt4 pkt5 pkt6   (pkt3 손실)
                       ▲
              TCP가 "순서 보장" 하느라
              pkt4,5,6 받았지만 app에 안 줌
              → stream B도 blocking
   
   QUIC:
   ─────
   wire 순서: pkt1 pkt2 ✗ pkt4 pkt5 pkt6
                       ▲
              QUIC가 stream별로 분리
              → stream B는 그대로 app에 전달
              → stream A의 pkt3만 retransmit 대기
```

### 6.4 운영 함정 — middlebox 문제

QUIC는 UDP 위. 그러나 일부 ISP/방화벽이 **UDP를 차별**한다 (DDoS 우려, 비대칭 라우팅 등).
- 비율: 글로벌 95%+ UDP 통과, 그러나 5%는 차단 → 그 경우 HTTP/3 fallback to HTTP/2.
- 브라우저는 Alt-Svc 헤더로 HTTP/3 endpoint를 알고, 실패 시 자동 fallback.

### 6.5 QUIC vs HTTP/3 vs HTTP/2

| 항목 | HTTP/2 over TLS over TCP | HTTP/3 over QUIC |
|---|---|---|
| Transport | TCP | QUIC (UDP) |
| 핸드셰이크 | 3 RTT (3-way + TLS 1.3 1 RTT) | 1 RTT (0-RTT 재방문) |
| HOL blocking | TCP-level | stream별로 격리 |
| Connection migration | ❌ | ✅ (Connection ID) |
| Multiplexing | ✅ (TCP에 갇힘) | ✅ (진짜 독립) |
| 배포 | OS 의존 | userspace, app과 함께 |
| 점유율 (2025) | 50%+ 의 HTTPS | 30%+ (Cloudflare/Google) |

---

## 7. 가지 ②-실전: tcpdump/wireshark로 캡슐화 직접 보기

### 7.1 tcpdump — 3-way handshake 캡처

```bash
# port 443, host 지정
sudo tcpdump -i en0 -nn -vv 'host example.com and tcp port 443'

# 출력 예 (3-way):
# 14:23:01.111 IP 10.0.0.5.51234 > 93.184.216.34.443: Flags [S], seq 1234567890, win 65535, length 0
# 14:23:01.211 IP 93.184.216.34.443 > 10.0.0.5.51234: Flags [S.], seq 9876543210, ack 1234567891, win 28960, length 0
# 14:23:01.211 IP 10.0.0.5.51234 > 93.184.216.34.443: Flags [.], ack 9876543211, win 65535, length 0
```

**flag 약어**:
- `[S]` = SYN
- `[S.]` = SYN + ACK
- `[.]` = ACK
- `[P.]` = PSH + ACK (data 있음)
- `[F.]` = FIN + ACK
- `[R]` = RST

### 7.2 tcpdump — TLS ClientHello/ServerHello

```bash
sudo tcpdump -i en0 -nn -s 0 -w tls.pcap 'tcp port 443'
# Wireshark로 열어서 → Filter: tls.handshake.type == 1 (ClientHello)
```

Wireshark에서 ClientHello를 클릭하면:
```
   TLS Record Layer: Handshake Protocol: Client Hello
       Content Type: Handshake (22)
       Version: TLS 1.0 (legacy)
       Length: 512
       Handshake Type: Client Hello (1)
       Version: TLS 1.2
       Random: <32 bytes>
       Cipher Suites Length: 32
       Cipher Suites: [TLS_AES_256_GCM_SHA384, ...]
       Extension: server_name
           Server Name: example.com  ◄── 평문 SNI
       Extension: application_layer_protocol_negotiation
           ALPN Protocol: h2
           ALPN Protocol: http/1.1
       Extension: key_share (TLS 1.3)
           ...
```

### 7.3 ss — socket 상태

```bash
# 모든 TCP 연결 상태
ss -t -a

# State        Recv-Q  Send-Q  Local Address:Port  Peer Address:Port
# LISTEN       0       128     0.0.0.0:443         0.0.0.0:*
# ESTAB        0       0       10.0.0.5:51234      93.184.216.34:443
# TIME-WAIT    0       0       10.0.0.5:51235      93.184.216.34:443

# 상태별 카운트
ss -t -a | awk 'NR>1 {print $1}' | sort | uniq -c
# 1024 ESTAB
#  234 TIME-WAIT
#    5 LISTEN

# 혼잡 제어 정보 (cwnd, rtt 등)
ss -tin
# State  Recv-Q  Send-Q  Local Address:Port  Peer Address:Port
# ESTAB  0       0       10.0.0.5:51234      93.184.216.34:443
#        cubic wscale:7,7 rto:204 rtt:0.234/0.123 mss:1448 cwnd:10 ssthresh:7
```

### 7.4 netstat — 옛 도구지만 익숙

```bash
netstat -tan | awk 'NR>2 {print $6}' | sort | uniq -c
# 1024 ESTABLISHED
#  234 TIME_WAIT
#    5 LISTEN
```

### 7.5 openssl s_client — TLS 직접 검증

```bash
# 인증서 체인 + cipher 확인
openssl s_client -connect example.com:443 -servername example.com -showcerts

# 출력 발췌:
# CONNECTED(00000005)
# Certificate chain
#  0 s:CN=example.com
#    i:C=US, O=Let's Encrypt, CN=R3
#  1 s:C=US, O=Let's Encrypt, CN=R3
#    i:C=US, O=Internet Security Research Group, CN=ISRG Root X1
# ---
# SSL handshake has read 4234 bytes and written 401 bytes
# New, TLSv1.3, Cipher is TLS_AES_256_GCM_SHA384
# Server public key is 2048 bit
# Verification: OK

# TLS 1.3만 시도
openssl s_client -connect example.com:443 -tls1_3

# 특정 cipher 강제
openssl s_client -connect example.com:443 -cipher 'ECDHE-RSA-AES256-GCM-SHA384'

# SNI 다르게 시도 (vhost 라우팅 확인)
openssl s_client -connect 1.2.3.4:443 -servername other.com
```

### 7.6 sslscan / testssl.sh — 종합 진단

```bash
# 서버가 지원하는 모든 TLS 버전과 cipher
sslscan example.com

# 출력:
# Supported Server Cipher(s):
# Preferred TLSv1.3  256 bits  TLS_AES_256_GCM_SHA384      Curve 25519 DHE 253
# Accepted  TLSv1.3  128 bits  TLS_AES_128_GCM_SHA256      Curve 25519 DHE 253
# Accepted  TLSv1.2  256 bits  ECDHE-RSA-AES256-GCM-SHA384 Curve P-256 DHE 256
# ...
# 
# SSL Certificate:
# Signature Algorithm: sha256WithRSAEncryption
# Subject:  example.com
# Issuer:   R3 (Let's Encrypt)
# Not valid before: ...
# Not valid after:  ...

# 더 상세: testssl.sh (취약점 포함)
./testssl.sh example.com
```

---

## 8. 추가 — Wireshark 출력으로 보는 풀 흐름

### 8.1 HTTPS GET 요청의 wire-level packet 시퀀스

```
   #  Time     Source        Dest           Protocol  Info
   ─────────────────────────────────────────────────────────────────
   1  0.000   10.0.0.5      93.184.216.34  TCP       51234 → 443 [SYN] seq=0 win=65535
   2  0.100   93.184.216.34 10.0.0.5       TCP       443 → 51234 [SYN,ACK] seq=0 ack=1 win=28960
   3  0.100   10.0.0.5      93.184.216.34  TCP       51234 → 443 [ACK] seq=1 ack=1 win=65535
   ─── TCP ESTABLISHED ───
   4  0.101   10.0.0.5      93.184.216.34  TLSv1.3   ClientHello (517 bytes)
   5  0.201   93.184.216.34 10.0.0.5       TLSv1.3   ServerHello, Cert, EncExt, CertVerify, Finished (4234 bytes)
   6  0.202   10.0.0.5      93.184.216.34  TLSv1.3   ChangeCipherSpec, Finished (80 bytes)
   ─── TLS established ───
   7  0.202   10.0.0.5      93.184.216.34  HTTP2     Magic, SETTINGS, HEADERS (GET /)
   8  0.302   93.184.216.34 10.0.0.5       HTTP2     SETTINGS, HEADERS, DATA (200 OK + body)
   9  0.303   10.0.0.5      93.184.216.34  TCP       ACK
   ...
   --- 응답 다 받음 ---
   N    10.0.0.5      93.184.216.34  TCP       FIN,ACK
   N+1  93.184.216.34 10.0.0.5       TCP       ACK
   N+2  93.184.216.34 10.0.0.5       TCP       FIN,ACK
   N+3  10.0.0.5      93.184.216.34  TCP       ACK
   ─── TCP CLOSED ───
```

**시니어 분석 포인트**:
- packet 1~3: TCP 3-way, 약 1 RTT (100ms).
- packet 4~6: TLS handshake, 약 1 RTT.
- packet 7: 드디어 첫 HTTP 데이터. **TTFB = 200ms** (3-way + TLS).
- HTTP/3였으면 packet 1~6이 한 번에 압축돼 **TTFB = 100ms**.

---

## 9. 운영 시나리오 매핑 ⭐

### 9.1 시나리오 1: P99 latency가 5초로 튐

**증상**: 정상 P99 200ms → 5000ms. 4xx/5xx는 없음.

**진단 순서**:
1. `tcpdump`로 한 요청 캡처 → 3-way가 5초 → DNS or routing 문제일 가능성.
2. `dig example.com`로 DNS lookup 시간 확인. 정상이면 다음.
3. `ss -tin`으로 활성 connection의 rtt 확인. RTT가 갑자기 길면 네트워크 문제.
4. `tcpdump` 출력에서 retransmit 확인. `[TCP Retransmission]` 메시지 多면 패킷 손실.
5. 손실 원인: ISP 혼잡 / 라우터 buffer 부족 / Wi-Fi 노이즈.

**해결**:
- 단기: BBR 활성화 (4.6) → 손실 환경에서 throughput 회복.
- 중기: keepalive 사용 → 3-way 회피.
- 장기: HTTP/3 도입 → connection migration + 더 나은 손실 대응.

### 9.2 시나리오 2: TIME_WAIT 폭증 + ephemeral port 고갈

**증상**: `connect() failed: EADDRNOTAVAIL` 에러. `ss -t state time-wait | wc -l` 결과 30000+.

**원인**: 짧은 HTTP 연결 多 (active close = client). 1초당 새 연결 1000개, TIME_WAIT 60초 → 60000개 누적. ephemeral port range 32768~60999 = 28232개 → 고갈.

**해결**:
- `sysctl net.ipv4.tcp_tw_reuse=1` (안전한 재사용).
- `sysctl net.ipv4.ip_local_port_range="10000 65535"` (range 확장).
- **HTTP keepalive** 사용 — 연결 재사용으로 close 빈도 감소 (가장 정석).
- 클라이언트 측 connection pool (HikariCP, Apache HttpClient pool).

> 주의: `tcp_tw_recycle`은 NAT 환경에서 문제 → Linux 4.12에서 삭제됨. **절대 쓰지 마라**.

### 9.3 시나리오 3: SYN_RECV 폭증

**증상**: `ss -t state syn-recv | wc -l` 결과 5000+. 일부 client는 연결 못 함.

**원인 2가지**:
1. **SYN flood 공격** (실제 공격).
2. **backlog 부족** + 정상 트래픽 spike — 서버 accept가 느려서 SYN_RECV에 누적.

**진단**:
- `dmesg | grep -i syn` → "TCP: drop open request from X.X.X.X" 메시지.
- `nstat -az TcpExtListenOverflows` 확인 → backlog 넘침 카운터.

**해결**:
- SYN cookie 활성: `sysctl net.ipv4.tcp_syncookies=1` (대부분 기본).
- backlog 확장: `sysctl net.core.somaxconn=4096` + 애플리케이션 listen backlog도 같이.
- accept 처리 가속: thread/event loop 튜닝 (5장 Nginx 챕터).

### 9.4 시나리오 4: CLOSE_WAIT 폭증

**증상**: `ss -t state close-wait | wc -l` 결과 1000+. FD leak.

**원인**: **거의 항상 애플리케이션 버그**. 응답을 받고 close()를 안 호출.

**진단**:
- `lsof -p <pid> | grep CLOSE_WAIT` → 어떤 socket이 leak?
- 코드에서 try-with-resources 누락, finally의 close() 빠짐 등.

**해결**: 코드 수정. JVM이면 HikariCP 등 connection pool 사용으로 자동 close 보장.

### 9.5 시나리오 5: TLS handshake 실패

**증상**: 클라이언트에서 `SSL_ERROR_SYSCALL`, `certificate verify failed`, `unsupported protocol`.

**진단 순서**:
1. `openssl s_client -connect host:443 -servername host` → handshake 어디서 실패하는지.
2. 인증서 만료? `openssl x509 -in cert.pem -text -noout | grep "Not After"`.
3. 인증서 체인 incomplete (intermediate 누락)? `sslscan` 출력에서 chain 확인.
4. TLS 버전 mismatch (서버 TLS 1.3만, 클라이언트 1.0/1.1)? `openssl s_client -tls1_2` 등으로 강제.
5. cipher mismatch? cipher 명시 시도.
6. SNI hostname 불일치? `-servername` 옵션과 인증서 CN/SAN 비교.

### 9.6 시나리오 6: RST 패킷이 끊는다

**증상**: 응답 중간에 connection reset. `Connection reset by peer`.

**진단**:
- `tcpdump 'tcp[tcpflags] & tcp-rst != 0'`로 누가 RST를 보내는지.
- 4.9의 5가지 케이스 중 어디?
  1. 비존재 포트 → 서버 미기동 / firewall.
  2. half-open → 한쪽 reboot.
  3. SO_LINGER(0) → 강제 abort.
  4. firewall REJECT.
  5. 프로세스 crash → JVM OOM-killed? `dmesg | grep -i kill`.

### 9.7 시나리오 7: HTTP/3가 안 켜진다

**증상**: 브라우저에서 HTTP/2만 사용. `Protocol: h2` 표시.

**원인**:
- 서버가 Alt-Svc 헤더 미설정 (`Alt-Svc: h3=":443"`).
- ISP/방화벽이 UDP 443 차단.
- 클라이언트 첫 방문 → Alt-Svc 캐시 없음 → 다음 방문부터 h3.

**진단**: Chrome `chrome://net-export/` 또는 `nginx -V 2>&1 | grep quic` (서버 빌드 확인).

### 9.8 시나리오 8: MTU 1500 초과 응답이 깨진다 (PMTUD 실패)

**증상**: 대용량 응답 (PDF, 큰 JSON) 다운로드 중 hang. 작은 요청은 정상. VPN 환경에서 자주 발생.

**원인** (한 줄): **DF(Don't Fragment) 비트가 켜진 큰 packet이 작은 MTU 구간을 만남 → ICMP "Fragmentation Needed"가 차단되어 송신자가 모름**.

```
   클라이언트 (MTU 1500) ──── VPN tunnel (MTU 1400) ──── 서버 (MTU 1500)
                                  │
                                  ▼
   서버가 1500 byte segment를 DF=1로 보냄
   → tunnel router가 "MTU 초과! DF니까 못 자름" → drop + ICMP unreachable 회신
   → 그런데 방화벽이 ICMP를 막아버림 (보안 정책으로 흔함)
   → 서버는 응답 없음만 받음 → 무한 재전송 → hang

   이게 PMTU Discovery black hole.
```

**진단**:
```bash
# 다양한 size로 ping 보내 어디서 잘리는지
ping -M do -s 1472 example.com   # 1472 + 28(ICMP/IP header) = 1500
ping -M do -s 1372 example.com   # 작은 MTU에서 통과하는 size
# tracepath: PMTU 자동 측정
tracepath example.com
```

**해결**:
- **MSS clamping**: VPN/iptables에서 SYN 패킷의 MSS option을 낮춰 처음부터 작은 segment 강제
  ```
  iptables -t mangle -A FORWARD -p tcp --tcp-flags SYN,RST SYN \
     -j TCPMSS --clamp-mss-to-pmtu
  ```
- **방화벽에서 ICMP "Fragmentation Needed" (type 3, code 4) 통과 허용** — 보안 명분으로 ICMP 전체 차단하지 말 것
- **PLPMTUD (RFC 4821)** 활성화 — ICMP 의존 안 하고 packet 손실로 PMTU 추정 (Linux: `net.ipv4.tcp_mtu_probing=1`)

### 9.9 시나리오 9: ARP cache poisoning / 게이트웨이 MAC 이상

**증상**: 같은 LAN 내 호스트의 통신이 갑자기 끊기거나, 외부 통신은 되는데 응답이 느려짐. `arp -a`에 게이트웨이 MAC이 평소와 다름.

**원인**:
1. **ARP spoofing 공격** — 누군가 게이트웨이를 사칭하는 ARP reply broadcast
2. **gratuitous ARP race** — 같은 VIP를 여러 노드가 동시에 claim (잘못 설정된 keepalived)
3. **NIC MAC duplicate** — 가상화 환경에서 MAC 중복 (드물지만 발생)

**진단**:
```bash
# 현재 ARP cache
arp -an

# 정상 게이트웨이 MAC과 비교 (관리자 기록 필요)
# 의심되면 tcpdump로 ARP 캡처
tcpdump -i eth0 -nn arp

# 어떤 MAC이 어떤 IP를 광고하는지 분석
# 같은 IP를 여러 MAC이 광고하면 충돌 또는 공격
```

**해결**:
- **단기**: `arp -d <ip>`로 cache 비우고 다시 학습. static ARP entry 강제
  ```
  arp -s 10.0.0.1 AA:BB:CC:DD:EE:FF
  ```
- **장기**: 스위치의 **DAI (Dynamic ARP Inspection)** 활성화 — DHCP snooping과 연동해 위조 ARP 자동 차단
- 중요 서버는 **L7 TLS 강제** — MITM이 되어도 평문 노출 막음

### 9.10 시나리오 10: TTL 소진 → 도달 못 함

**증상**: 특정 외부 서비스만 unreachable. `ping`은 가는데 application은 timeout. `traceroute`가 중간에 `* * *` 무한.

**원인** (한 줄): **VPN/SD-WAN/clouds를 거치며 hop이 누적되어 TTL이 0이 되어 drop**.

```
   현대 클라우드/멀티 VPN 환경:
     사용자 → corporate VPN → cloud VPN → service mesh sidecar → another vpc peering → 최종 서버
     hop 수가 25~30+ 되는 경우 흔함

   기본 TTL:
     ▶ Linux: 64
     ▶ Windows: 128
     ▶ macOS: 64

   64 hop 안에 못 도달하면 마지막 router가 ICMP TIME_EXCEEDED 회신 + drop
   → 송신자는 "Time exceeded" 또는 그냥 timeout
```

**진단**:
```bash
# hop 수 추적
traceroute -n example.com
# 또는 mtr (real-time)
mtr example.com

# 마지막에 도달하기 전 끊기면 그 hop 이후가 문제
# * * * 가 끝까지 가면 ICMP 차단된 경로
```

**해결**:
- **TTL 키우기**:
  ```
  sysctl -w net.ipv4.ip_default_ttl=128
  ```
  (default 64로는 글로벌 멀티 VPN 환경에서 부족할 수 있음)
- **경로 최적화** — 불필요한 hop 줄이기. service mesh의 sidecar 1 hop도 무시 못 함
- **MTR로 모니터링** — 평소 패킷 loss와 hop 변화 트래킹

---

## 10. 트레이드오프 종합표 ⭐

### 10.1 L4 프로토콜 선택

| 항목 | TCP | UDP | QUIC |
|---|---|---|---|
| 신뢰성 | ✅ | ❌ | ✅ |
| 순서 보장 | ✅ (전체) | ❌ | ✅ (stream별) |
| 흐름·혼잡 제어 | ✅ | ❌ | ✅ |
| 핸드셰이크 | 1 RTT (3-way) | 0 RTT | 1 RTT 통합 (0 RTT 재방문) |
| HOL blocking | ✅ (문제) | - | ❌ (해결) |
| Connection migration | ❌ | - | ✅ |
| OS 의존성 | 강함 | 약함 | 거의 없음 (userspace) |
| 적합 용도 | 웹, DB, SSH, FTP | DNS, NTP, 게임, 영상 | HTTP/3, 모바일 |

### 10.2 혼잡 제어 알고리즘

| 알고리즘 | 시그널 | 강점 | 약점 | 권장 환경 |
|---|---|---|---|---|
| Reno | loss | 단순, 공정 | 고RTT/고대역 한계 | 레거시 |
| CUBIC | loss | 고대역 망 OK | bufferbloat 취약 | Linux 기본, 일반 데이터센터 |
| BBR | RTT + BW | 손실 환경 강함, 저latency | CUBIC와 공정성 문제 | YouTube, 무선/모바일, 글로벌 CDN |

### 10.3 TLS 1.2 vs 1.3

| 항목 | TLS 1.2 | TLS 1.3 |
|---|---|---|
| Handshake RTT | 2 | 1 |
| 0-RTT | ❌ | ✅ (위험 동반) |
| PFS | optional | **강제** |
| Legacy cipher | 허용 (RSA KEX, CBC, SHA1) | **모두 제거** |
| AEAD 강제 | ❌ | ✅ |
| 인증서 평문 노출 | ✅ (cleartext) | ❌ (encrypted) |
| 배포율 (2025) | 30% | 70%+ |

### 10.4 HTTP 버전 선택

| 항목 | HTTP/1.1 | HTTP/2 | HTTP/3 |
|---|---|---|---|
| Transport | TCP | TCP+TLS | QUIC (UDP+TLS) |
| Multiplexing | ❌ (pipelining 깨짐) | ✅ (TCP HOL) | ✅ (진짜) |
| Header 압축 | ❌ | HPACK | QPACK |
| Server push | ❌ | ✅ (deprecated) | ✅ |
| Connection migration | ❌ | ❌ | ✅ |
| 점유율 | 20% | 50% | 30% (성장중) |

---

## 11. 꼬리질문 트리 (면접 시뮬레이션)

### Q1. "OSI는 7계층이라던데, 실무에서 정말 7개 다 쓰나요?"

**예상답**:
- 실무는 TCP/IP 5계층(또는 4계층). OSI는 개념 학습용 액자.
- L5/L6는 사실상 애플리케이션이나 TLS에 흡수. 별도 구현체 없음.
- 다만 7계층 모델은 "각 책임을 어디서 처리하나"를 분리해서 보는 데 유용 — 운영 진단에서 "L3 문제? L7 문제?"라고 layer로 좁히는 사고에 쓰임.

**꼬리 1-1**: "그럼 TLS는 정확히 몇 계층인가요?"
- → 교과서적으로는 L5(Session)와 L6(Presentation) 사이. 실무로는 그냥 'TLS layer'.
- → TCP 위, HTTP 아래. 데이터 평문은 TLS 위에 있고 평문은 TLS 아래.

**꼬리 1-2**: "QUIC는 몇 계층?"
- → TCP를 대체했으니 L4. 그러나 TLS와 통합되어 L5/L6 책임도 가짐. 그래서 "L4+L5 통합" 또는 그냥 "QUIC layer"라고 표현.

### Q2. "TCP 3-way handshake가 왜 3번이지 2번이 아닌가요?"

**예상답**:
- 양쪽이 각자 초기 seq를 보내고 상대가 ACK해야 함. SYN×2 + ACK×2 = 4번 같지만, 가운데 ACK와 SYN을 합쳐서 SYN+ACK 1개로 = 3번.
- 2-way로 줄이면 server는 client의 ACK 수신 여부를 모르고 ESTABLISHED 진입 → half-open 문제.
- 보안 측면: initial seq를 random하게 → seq prediction attack 방어.

**꼬리 2-1**: "그럼 4-way close는 왜 4번이죠? half-close 때문이라고만 답하면 깊이가 부족합니다."
- → TCP는 **simplex 쌍방향**으로 모델됨. 보낼 쪽과 받을 쪽이 독립 — 한쪽이 FIN 보냈다고 반대편도 즉시 닫는 게 아니다.
- → 서버는 client의 FIN을 ACK한 후, 자기가 보낼 데이터를 다 보내고 application이 close() 호출한 시점에야 자기 FIN을 보냄. 그래서 ACK와 FIN이 분리.
- → 일부 경우는 서버도 즉시 close → ACK와 FIN을 한 packet에 합침 → 사실상 3-way close.

**꼬리 2-2**: "TIME_WAIT가 왜 2MSL이죠?"
- → (1) 마지막 ACK 손실 시 상대의 FIN 재전송을 받아 다시 ACK 보낼 수 있게.
- → (2) 같은 4-tuple로 새 연결이 즉시 만들어지면, 이전 연결의 지연된 segment가 잘못 흘러올 수 있음. 2MSL 후엔 그런 segment 다 죽었다.

**꼬리 2-3**: "TIME_WAIT 줄이는 방법은? 그 중 가장 안전한 건?"
- → `tcp_tw_reuse` (안전), `SO_REUSEADDR` (조심), HTTP keepalive (가장 정석).
- → `tcp_tw_recycle`은 NAT 환경 망함. 4.12부터 삭제. 절대 쓰지 마라.

### Q3. "TLS 1.2는 2 RTT인데 1.3은 1 RTT라고요. 어떻게 줄였죠?"

**예상답**:
- 1.2: ClientHello → ServerHello + Cert → ClientKeyExchange → Finished. 양쪽이 키 재료를 주고받는 데 2 round.
- 1.3: ClientHello에 **추측한 key share를 미리 박음** (X25519 등). 서버가 그 그룹을 받으면 ServerHello에 자기 key share + Finished. 1 round 끝.
- 핵심은 "서버가 어떤 그룹을 선택할지" 클라이언트가 잘 추측해야 한다는 것. 실패하면 HelloRetryRequest로 한 round 추가 → 다시 2 RTT.

**꼬리 3-1**: "0-RTT는 어떻게 동작하고, 왜 위험한가요?"
- → 재방문 시 PSK(이전 session ticket 기반)로 ClientHello에 application data를 즉시 동봉. server가 PSK 검증 후 즉시 처리.
- → 위험: replay attack. 공격자가 0-RTT data를 캡처 후 다시 보내면 server는 또 처리. POST 같은 non-idempotent에 쓰면 송금 두 번 같은 사고.

**꼬리 3-2**: "PFS가 뭔지, 왜 1.3은 강제하나요?"
- → Perfect Forward Secrecy: server private key가 미래에 유출돼도 옛 트래픽 복호화 불가능. ECDHE처럼 ephemeral key 쓰면 session key 재구성 불가.
- → RSA key exchange는 PFS 없음 — server private key로 session key 복원 가능. 1.3은 RSA KEX 자체를 제거해서 강제.

**꼬리 3-3**: "그럼 RSA 인증서는 1.3에서 의미가 있나요?"
- → 있다. 키 교환은 ECDHE로 하지만, server의 신원 증명(서명)은 인증서의 RSA/ECDSA private key로. 즉 "키 교환용 키"와 "인증용 키"가 분리된 것.

### Q4. "BBR이 CUBIC보다 좋다고 하는데, 항상 좋은가요?"

**예상답**:
- 손실 환경(무선, 글로벌)에서 BBR이 압도. YouTube 14% 개선이 그 증거.
- 그러나 BBR과 CUBIC가 같은 망에서 경쟁하면 BBR이 점유율을 너무 많이 가져감 → 공정성 문제. BBR v2/v3에서 개선 중.
- 데이터센터 내부(저손실, 일정한 RTT)에서는 CUBIC이 충분.
- 결론: 외부 트래픽(클라이언트 ↔ 서버)에 BBR, 내부(서버 ↔ DB)는 CUBIC도 OK.

**꼬리 4-1**: "Bufferbloat이 뭔지, BBR이 그걸 어떻게 해결하나요?"
- → 라우터 buffer가 크면 패킷 손실 전에 latency가 폭발. 손실 기반 알고리즘(CUBIC)은 손실이 안 나니 계속 전송 → buffer 채우기만 → P99 latency 폭증.
- → BBR은 RTT 증가를 감지 → cwnd를 줄임. buffer를 비워두는 방향.

### Q5. "QUIC가 TCP를 대체할 거라고요. 어디까지 가능할까요?"

**예상답**:
- HTTP/3는 사실상 QUIC가 표준. 글로벌 CDN(Cloudflare, Akamai, Fastly) + Google/YouTube/Facebook가 채택.
- 그러나 DB 프로토콜(MySQL, PostgreSQL wire), SSH, FTP 등은 여전히 TCP. 변경 비용 크고 손실율도 낮음.
- 사내망/데이터센터는 TCP가 충분. QUIC가 의미 있는 건 **glob client → server** 트래픽.
- 5~10년 후엔 외부 트래픽 80%+ QUIC, 내부는 TCP.

**꼬리 5-1**: "QUIC의 단점은 뭔가요?"
- → (1) UDP 차단하는 middlebox 일부 존재 → HTTP/2 fallback 필요.
- → (2) userspace이라 OS의 zero-copy/offload 활용 어려움 → CPU 사용 TCP보다 큼.
- → (3) 표준이 더 자주 바뀜 → 안정성 검증 어려움.
- → (4) 운영 도구(tcpdump, wireshark)도 QUIC 디코딩이 더 어렵다 (암호화 영역 多).

**꼬리 5-2**: "Connection migration이 정확히 뭔가요?"
- → TCP는 4-tuple(src_ip+port+dst_ip+port)이 connection 식별자. IP가 바뀌면 connection 끊김.
- → QUIC는 **Connection ID** (64-bit) 별도 도입. IP가 바뀌어도 같은 ID면 같은 connection.
- → 예: 모바일이 Wi-Fi → 4G로 전환 시 TCP는 connect 다시. QUIC는 끊김 없음.

### Q6. "운영에서 P99 latency가 갑자기 튀었다. 어떻게 진단할 건가요?"

**예상답** (시나리오 흐름):
1. **layer 좁히기**: client측? LB? 서버측? — 각 stage timing 측정 (DNS, TCP, TLS, TTFB, response, total).
2. **TCP 의심**: `ss -tin`으로 활성 connection의 rtt/cwnd 확인. `tcpdump`로 retransmit 카운트.
3. **TLS 의심**: handshake 시간 분리. `openssl s_client -msg`로 단계별.
4. **혼잡 제어**: `sysctl net.ipv4.tcp_congestion_control` 현재 알고리즘 확인. CUBIC이면 BBR 시도.
5. **bufferbloat**: 라우터 queue 길이 확인 (가능하면). `sch_fq` qdisc 적용.
6. **GC pause** (서버 측 Java): jvm/04-gc 챕터 참조.

**꼬리 6-1**: "측정 도구를 어떤 순서로?"
- → 위에서 아래로: 우선 `curl -w` 같은 클라이언트 도구 (DNS/connect/TLS/TTFB 분리) → 의심 단계에서 `tcpdump`/`ss`/`openssl s_client`.

### Q7. "OSI 7계층 모델과 TCP/IP 모델의 차이는?"

**예상답**:
- OSI: ISO/ITU가 1984년 표준화한 7계층 추상 모델. 교육·이론적 분류용.
- TCP/IP: IETF가 실제 인터넷을 구현하며 자라난 4~5계층 모델. 실무 표준.

```
   OSI 7층 ↔ TCP/IP 4~5층 매핑
   ─────────────────────────────────
   L7 Application  ┐
   L6 Presentation │  → Application
   L5 Session      ┘
   L4 Transport     → Transport
   L3 Network       → Internet
   L2 Data Link    ┐
   L1 Physical     │  → Link (or Network Access)
   ─────────────────────────────────
```

- **왜 TCP/IP가 이겼나**: OSI는 표준이 먼저 나오고 구현이 따라가는 방식, TCP/IP는 구현이 먼저 (BSD/Berkeley) 표준화는 나중. "rough consensus and running code" 정신.
- **실무에서 OSI를 쓰는 이유**: 7계층 분류가 "어디서 문제 났나"를 분리해서 보는 데 유용. 운영 진단 시 "L3 문제? L7 문제?"로 좁히는 사고법.

**꼬리 7-1**: "그럼 OSI는 죽은 모델인가?"
- → 모델 자체는 살아 있음. ISO OSI 프로토콜 스택(X.25, X.400)은 죽었음. 모델은 개념적 분류 도구로 영구.
- → 7계층이 5계층보다 더 세밀해서 trouble-shoot할 때 유용.

### Q8. "L4 LB와 L7 LB의 차이는?"

**예상답** (한 줄): L4는 **port까지만 보고 분산**, L7은 **HTTP path/header/cookie까지 보고 분산**.

```
   L4 LB (Layer 4, Transport)
   ─────────────────────────────────
   ▶ TCP/UDP 헤더의 src/dst IP + port만 inspect
   ▶ TLS 종단 안 함 (pass-through)
   ▶ packet 단위 forwarding (DSR 가능)
   ▶ 빠름 (수십만 connection/sec), 가벼움
   ▶ 알고리즘: round-robin, least-conn, hash
   ▶ 예: AWS NLB, HAProxy (TCP mode), IPVS

   L7 LB (Layer 7, Application)
   ─────────────────────────────────
   ▶ HTTP method, path, header, cookie까지 본다
   ▶ TLS 종단 (인증서 보유)
   ▶ "GET /api/* → backend A, /static/* → backend B"
   ▶ sticky session (cookie 기반), WAF, compression
   ▶ 느림 (TLS+parsing 비용), 풍부함
   ▶ 예: AWS ALB, Nginx, Envoy, HAProxy (HTTP mode)
```

**꼬리 8-1**: "둘 다 운영하면 어떤 토폴로지?"
- → 외부에 L4 (DDoS 흡수, SSL passthrough)→ 내부에 L7 (path routing).
- → AWS는 NLB → ALB 또는 ALB 단독.

**꼬리 8-2**: "DSR(Direct Server Return)이 뭔지?"
- → L4 LB의 특수 기법. client → LB → server까지는 LB 경유, 응답은 server → client 직행 (LB 안 거침).
- → trick: server가 LB의 VIP를 loopback에 추가 + ARP 응답 안 함. 응답 packet src=VIP로 그대로 client 도달.
- → 응답 트래픽이 LB를 안 거치니 throughput 폭증. 단점: TLS 종단·L7 inspection 불가.

### Q9. "MAC 주소는 hop마다 변하는데 IP는 안 변한다. 왜?"

**예상답** (한 줄): **MAC은 same-LAN(broadcast domain) 안에서만 유효**한 next-hop 주소이고, **IP는 end-to-end 식별자**라서.

- MAC은 NIC 제조사가 박은 hardware 주소. 같은 LAN의 호스트끼리만 직접 통신 가능.
- LAN을 넘는 순간 (router) MAC 헤더는 떼버리고 다음 LAN의 next-hop MAC으로 다시 조립.
- IP는 논리적 주소. routing table을 통해 어느 LAN을 거치든 끝까지 동일.

**꼬리 9-1**: "그럼 NAT에선 IP도 변하는가?"
- → 네. NAT는 router가 본업을 넘어 L4까지 inspection하면서 src_ip/src_port를 갈아치움.
- → 본래 IP의 end-to-end 원칙이 깨진 케이스 — IPv6는 충분한 주소로 NAT 불필요하게 설계.
- → NAT 너머에선 진짜 client IP는 안 보임 → X-Forwarded-For, PROXY protocol로 우회.

**꼬리 9-2**: "그럼 MAC 주소는 영원히 안 변하나?"
- → 영구 MAC(BIA, Burned-In Address)은 NIC 제조 시 박힘. 그러나 OS 레벨에서 변경 가능:
  ```
  ip link set eth0 address 02:11:22:33:44:55
  ```
- → 가상화/컨테이너는 가상 MAC 발급. 사생활 보호 모드(MAC randomization)는 Wi-Fi에서 매번 다른 MAC 사용.

### Q10. "TCP checksum이 있으면 Ethernet FCS는 왜 또 있나? 중복 아닌가?"

**예상답** (한 줄): **계층별 책임 분리** — FCS는 link-local 에러, TCP checksum은 end-to-end 에러, TLS HMAC은 의도적 변조를 잡는다.

```
   defense in depth — 각 계층이 다른 신뢰 모델 가정
   ─────────────────────────────────────────────────
   L1 신호 자체:       광 노이즈, 전기 간섭
                       → L2 FCS가 link error로 잡음
   L2 FCS:            link-local 에러 (NIC 결함, 케이블)
                       → router/스위치가 손상 frame을 IP까지 안 올림
   L3 IP checksum:    header만 (TTL 등 router가 만지는 부분)
                       → 손상된 routing 정보가 침투 안 함
   L4 TCP checksum:   pseudo-header + 전체 segment
                       → router 메모리 손상, kernel buffer 오염 같은
                         link 이외 원인 잡음
   L6 TLS HMAC/AEAD:  암호학적 검증
                       → 적대적 active attacker의 의도적 변조 잡음
                       (checksum은 random 손상만 잡지 의도적 변경 못 잡음)
```

**꼬리 10-1**: "TCP checksum이 약하다고 들었는데?"
- → 16bit 1's complement sum. 충분히 강하진 않음. 일부 burst error는 통과 가능.
- → 그래서 진짜 안전이 필요하면 TLS HMAC/AEAD 필수.

**꼬리 10-2**: "TLS가 있으면 TCP checksum은 필요 없나?"
- → 필요함. checksum 실패는 즉시 재전송 트리거. TLS 실패는 fatal alert + connection 종료.
- → checksum이 random 손상을 일찍 잡아주면 TLS layer 부담 감소.

### Q11. "URL을 입력하면 어떻게 서버까지 가나? 7계층으로 풀어보세요" ⭐

**예상답** (4분 답변 — 2-2.9 참조):
1. **L7**: 브라우저가 HTTP 메시지 생성. `GET /users/김면수 HTTP/1.1` + Host + headers.
2. **L6 (TLS)**: HTTPS면 TLS record로 암호화. AEAD tag 16B로 무결성 보장.
3. **L4 (TCP)**: src/dst port + seq/ack 붙여 segment. checksum 계산.
4. **L3 (IP)**: src/dst IP + TTL 붙여 packet. header checksum.
5. **L2 (Ethernet)**: src/dst MAC + ethertype + FCS 붙여 frame. **dst MAC은 다음 hop(게이트웨이) MAC, ARP로 알아낸 것**.
6. **L1**: NIC가 비트로 변환, line code(예: 4B/5B) 부호화 후 wire에 송출.
7. **hop마다**: router가 L2/L1 헤더 떼고 IP 보고 routing, 새 MAC으로 frame 재조립, TTL -1, IP checksum 재계산.
8. **수신측**: 역순으로 디캡슐레이션. 각 계층에서 검증 (FCS → IP checksum + TTL → TCP checksum + seq/ack → TLS AEAD → HTTP semantic).

**꼬리 11-1**: "ARP가 어떻게 다음 hop MAC을 알아내나?"
- → broadcast로 "Who has 10.0.0.1? Tell 10.0.0.5" 외침. dst_mac=FF:FF:FF:FF:FF:FF.
- → 해당 IP의 호스트가 unicast reply. 60초 cache.

**꼬리 11-2**: "DNS는 언제 발생하나?"
- → L7 단계 이전. 브라우저가 `example.com → 142.250.0.0` 변환을 위해 resolver에게 DNS 쿼리.
- → 02 챕터(DNS) 참조.

### Q12. "각 계층에서 어떤 검증을 하는지 모두 말해보세요" ⭐

**예상답**:
- **L1**: 신호 무결성 (line code의 DC balance, clock recovery).
- **L2**: FCS (CRC-32, frame 전체) + dst MAC match (자기 MAC/broadcast/multicast 아니면 drop).
- **L3**: IP header checksum (header만, payload는 L4) + TTL > 0 + fragmentation 정합성.
- **L4 (TCP)**: TCP checksum (pseudo-header + segment 전체) + seq/ack 일관성 + window 검증.
- **L5/L6 (TLS)**: AEAD tag (AES-GCM 등) 또는 HMAC-SHA256 (TLS 1.2 CBC) + 인증서 chain 검증 + SNI 일치.
- **L7**: Content-Length 일치, JSON 스키마, 인증 토큰, CSRF token, 비즈니스 규칙.

**시니어 통찰**: 검증이 실패했을 때 layer마다 반응이 다르다.

| Layer | 실패 시 동작 |
|---|---|
| L2 FCS | NIC가 즉시 drop. `RX errors` 카운터 증가 |
| L3 checksum | router가 즉시 drop. 통계만 |
| L3 TTL=0 | drop + ICMP TIME_EXCEEDED 회신 |
| L4 checksum | segment drop. ACK 없으니 sender 재전송 |
| L4 seq 이상 | 재정렬 또는 재전송 트리거 |
| L6 TLS auth fail | fatal alert → connection 종료 |
| L7 fail | HTTP 4xx/5xx 응답 |

---

## 12. 백지 마스터 체크리스트

이 챕터를 마쳤다면 다음을 종이에 그릴 수 있어야 한다.

- [ ] OSI 7계층 + 각 PDU 이름 + 대표 프로토콜 (1.3 표).
- [ ] OSI 7계층 책임 매트릭스 + 계층별 검증 메커니즘 (2-2.1, 2-2.4).
- [ ] `GET /users/김면수`의 캡슐화 (HTTP→TCP→IP→Eth→bits) + 헤더 사이즈 (2.2, 2-2.2).
- [ ] TCP/IP/Ethernet 헤더 byte 단위 풀 분해 (2-2.3).
- [ ] MAC은 hop-to-hop, IP는 end-to-end — 매 hop마다 어떤 필드가 변하는지 (2-2.5, 2-2.8).
- [ ] Router 내부 동작 (frame 수신 → IP routing → 새 frame 재조립) (2-2.5).
- [ ] ARP 동작 (request broadcast / reply unicast / L2.5 위치) + spoofing (2-2.6).
- [ ] 한 frame이 NIC를 떠나는 과정 (kernel → driver TX ring → NIC → wire) (2-2.7).
- [ ] PMTUD black hole 진단·해결 (MSS clamping, ICMP allow) (9.8).
- [ ] TTL 소진 진단 (traceroute, mtr, default TTL 변경) (9.10).
- [ ] TCP 3-way handshake 상태 전이 + 각 단계 seq/ack/flag (4.1).
- [ ] TCP state diagram 11개 상태 (4.2).
- [ ] TIME_WAIT 2MSL의 이유 2가지 (4.8).
- [ ] RST 발생 5가지 케이스 (4.9).
- [ ] TCP 흐름 제어 (sliding window) + 혼잡 제어 4세대 (Tahoe→Reno→CUBIC→BBR).
- [ ] BBR이 왜 게임체인저인지 (4.6).
- [ ] TLS 1.2 handshake 2 RTT vs TLS 1.3 1 RTT의 차이 (5.2, 5.3).
- [ ] 0-RTT의 replay 위험 (5.4).
- [ ] 인증서 체인 검증 (5.5).
- [ ] SNI / ALPN / PFS의 의미 (5.6/5.7/5.8).
- [ ] QUIC가 TCP를 버린 4가지 이유 (6.1).
- [ ] tcpdump flag 약어 + `ss -tin` 출력 해석 (7.1/7.3).
- [ ] `openssl s_client`로 인증서 체인 확인 (7.5).
- [ ] 운영 7대 시나리오 진단·해결 (9장).

이 모든 걸 면접관 앞에서 막힘없이 풀면 **시니어 운영 마스터 수준**. 다음 챕터(04 Load Balancer)로 진행.

---

## 다음 챕터로의 연결

- **04-load-balancer-deep-dive**: 이 챕터에서 본 TCP/TLS가 L4/L7 LB에서 어떻게 종단되고 재시작되는지. **SSL termination, DSR, health check, sticky session, WAF**.
- **05-nginx-internals**: TCP 연결이 Nginx에 도착한 후 **epoll로 어떻게 처리되나**.
- **06-tomcat-internals**: HTTP 메시지가 Java 객체(HttpServletRequest)로 어떻게 변환되나.
- **07-connection-pools-master**: TIME_WAIT 회피와 keepalive의 실제 운영 — **Nginx upstream / HikariCP / kernel backlog**.

> 이 챕터의 깊이는 **백지에서 줄줄 풀 수 있을 때까지** 반복. 시니어 면접의 30%는 이 챕터에서 나온다.
