# 03. OSI 7계층 + TCP + TLS — 데이터가 7번 옷을 갈아입고 다시 7번 벗는 여행

> "OSI는 7계층" 이라고 외운 면접자는 절반은 모르는 것이다.
> **왜 7개로 쪼갰나? 헤더는 어떤 순서로 붙고 떨어지나? 3-way handshake 끝나기 전에는 HTTP가 한 바이트도 못 가는 이유는? TLS 1.3이 왜 1 RTT만에 끝나나? QUIC는 왜 TCP를 버렸나?**
> 시니어가 진짜 알아야 할 것은: 이 흐름을 백지에서 줄줄 풀고, `tcpdump`/`ss`/`openssl s_client`로 운영 장애를 진단할 수 있는 능력.

---

## 0. 마인드맵 — 면접 종이에 그릴 그림

### 루트 한 문장

> **"브라우저가 만든 HTTP 메시지는 7번 옷(헤더)을 입고 와이어를 건너간다. TCP가 신뢰성을 만들고, TLS가 비밀과 인증을 입힌다. 옷을 입히는 순서는 위→아래, 벗는 순서는 아래→위. 사이에 3-way handshake와 TLS handshake가 끼어 추가 RTT를 소모한다. QUIC는 그 RTT를 없애려고 UDP 위에 TCP+TLS를 재발명했다."**

### 5개 가지

```
       [ROOT: 7번 옷 + TCP 신뢰성 + TLS 비밀/인증]
            │
   ┌────┬───┴────┬──────┬──────┐
   ① OSI  ② 캡슐화  ③ TCP  ④ TLS  ⑤ QUIC
```

---

## 1. OSI 7계층 — 책임 매트릭스 ⭐

| L | 이름 | PDU | 식별자 | 핵심 책임 | 검증 | 대표 프로토콜 |
|---|---|---|---|---|---|---|
| **L7** | Application | message | (app context) | end-user 의미론 | semantic | HTTP, gRPC, WS, DNS, SSH |
| **L6** | Presentation | message | - | 직렬화·압축·**암호화** | TLS HMAC/AEAD | TLS, JSON, ASN.1, gzip |
| **L5** | Session | - | session id | 연결 lifecycle, 인증 | session token | TLS handshake, RPC |
| **L4** | Transport | segment/datagram | **port** (16-bit) | 프로세스 식별, 신뢰성, 흐름/혼잡 제어 | TCP checksum + seq/ack | TCP, UDP, QUIC |
| **L3** | Network | packet | **IP** | 라우팅 (다른 LAN 횡단) | IP checksum + TTL | IPv4/v6, ICMP |
| **L2** | Data Link | frame | **MAC** | same-LAN 노드 식별, 오류 검출 | Ethernet FCS (CRC-32) | Ethernet, Wi-Fi, ARP |
| **L1** | Physical | bit | - | 전기/광/전파 신호 | 신호 무결성 | 1000BASE-T, 10G-SR |

> 외울 때: **"All People Seem To Need Data Processing"** (위→아래).

**왜 계층화?** — **변화 격리**. L1이 구리→광섬유 바뀌어도 L7 HTTP는 한 줄도 안 바뀐다.

**TCP/IP 5계층(실무)**: L7/L6/L5를 "Application"으로 묶음. OSI 7층은 개념 학습용 액자, TCP/IP 5층이 실제 동작 모델. OSI 진영(X.400 등)은 1990년대 인터넷 폭발에 졌다 — "rough consensus and running code"가 이김.

**TLS는 몇 계층?** — 교과서는 L5/L6 사이, 실무는 그냥 "TLS layer". TCP 위, HTTP 아래.

### "P99 latency 튀면 어느 계층?" — 시니어 사고법

```
   ├── L7 응답 자체가 느림         → 서버 코드 / DB / GC
   ├── L4 retransmit 多           → 손실 환경, BBR 전환
   ├── L4 cwnd 작음               → bufferbloat, 혼잡 제어 튜닝
   ├── L3 TTL 짧음                → multi-VPN/multi-hop 경로
   ├── L3 fragmentation           → MTU mismatch, PMTUD black hole
   ├── L2 frame error 증가        → NIC/케이블/스위치 하드웨어
   └── L1 신호 noise              → 광케이블/무선 환경
```

---

## 2. 캡슐화 — 헤더 7개를 입히고 벗기

### 2.1 한 다이어그램으로 보는 캡슐화 ⭐

```
─────────────────────────────────────────────────────────────
 L7 (HTTP)   GET /users/김면수 HTTP/1.1\r\nHost: ...\r\n\r\n
                          │
                          ▼
 L6 (TLS)    [TLS rec hdr 5 | AEAD-encrypted HTTP | tag 16]
                          │
                          ▼
 L4 (TCP)    [TCP hdr 20 | TLS record bytes               ]
              src=54321 dst=443 seq/ack flags=PSH+ACK
                          │
                          ▼
 L3 (IP)     [IP hdr 20 | TCP segment                      ]
              src=10.0.0.5 dst=142.250.0.0 ttl=64 proto=6
                          │
                          ▼
 L2 (Eth)    [Eth 14 | IP packet | FCS 4                    ]
              dst_mac=게이트웨이 MAC (ARP로 알아냄)
              src_mac=내 NIC, ethertype=0x0800
                          │
                          ▼
 L1          ─── bits on wire ───
              preamble 8 + frame + IFG (96 bit time)
─────────────────────────────────────────────────────────────

 수신측: 비트 → frame → packet → segment → TLS → HTTP (역순 디캡)
 각 계층은 자기 헤더만 보고 다음 계층으로 넘김 (추상화)
```

**오버헤드** (HTTPS GET 1개, IPv4):
- Eth 14 + IP 20 + TCP 20 + TLS 5 + AEAD 16 = **75 byte**
- 실제 wire에는 +FCS 4 + preamble 8 + IFG ≈ **86+ byte**
- payload 500 byte → ~14% 오버헤드. payload가 짧을수록 비율 폭증 (Nagle 문제).

**MTU/MSS**: Ethernet payload 최대 1500 → MSS = MTU - IP(20) - TCP(20) = 1460 (IPv4). SYN 패킷의 TCP option에서 양쪽이 광고 → 작은 값 채택.

### 2.2 각 계층 헤더 — 시니어가 외울 필드만

| 계층 | 헤더 사이즈 | 외울 필드 (4개) | 운영 의미 |
|---|---|---|---|
| **TCP** | 20 byte 기본 (max 60) | src/dst port, seq/ack, flags(SYN/ACK/FIN/RST/PSH), window | 진단 90%는 flag 조합 |
| **IP** | 20 byte (v4) / 40 (v6) | src/dst IP, TTL, protocol (6=TCP/17=UDP/1=ICMP), checksum | TTL은 traceroute 원리 |
| **Eth** | 14 + FCS 4 | dst/src MAC, ethertype (0x0800=IPv4, 0x86DD=v6, 0x0806=ARP), FCS | MAC은 hop-to-hop |

### 2.3 다층 검증 — defense in depth

```
 L7 비즈니스          (Content-Length, 인증, CSRF) → 4xx 응답
 L6 TLS HMAC/AEAD   → 실패 시 fatal alert + connection 종료
 L4 TCP checksum    → segment drop → 재전송
    seq/ack         → 손실/순서 복구
    window=0        → 송신 정지 (zero window)
 L3 IP checksum     → router가 매 hop 재계산 (TTL 변하므로)
    TTL=0           → ICMP TIME_EXCEEDED + drop (loop 방지)
    DF + MTU 초과    → ICMP Fragmentation Needed → PMTUD
 L2 FCS (CRC-32)    → NIC가 즉시 drop, RX errors 증가
    dst MAC mismatch → NIC 폐기 (promisc 제외)
 L1 line code       → DC balance, clock recovery
```

**왜 같은 데이터를 여러 계층에서?** — 다른 신뢰 모델. FCS는 link-local 우연 손상, TCP checksum은 end-to-end 우연 손상, TLS HMAC/AEAD는 **악의적 변조**. checksum은 random 손상만 잡지 적대적 변경 못 잡음.

---

## 3. IP는 end-to-end, MAC은 hop-to-hop ⭐⭐⭐

**핵심 통찰 한 문단**: MAC 주소는 같은 LAN(broadcast domain) 안에서만 의미가 있다. Router는 LAN의 경계. 매 hop마다 router가 Ethernet frame을 떼고 새로 조립하면서 src/dst MAC을 갱신하지만, IP 주소는 처음부터 끝까지 그대로(NAT 없으면). 다음 hop MAC은 **ARP**로 알아낸다 — "Who has 10.0.0.1? Tell 10.0.0.5" broadcast(`dst_mac=FF:FF:FF:FF:FF:FF`) → 해당 호스트가 unicast reply → 60초 cache. ARP는 **L2.5** (IP를 알지만 L2 frame으로 전송, TCP/IP 모델은 link layer에 포함). 인증이 없어서 **ARP spoofing/cache poisoning**으로 MITM 가능: 공격자가 "10.0.0.1은 내 MAC이야" 거짓 reply → 피해자 cache 오염 → 게이트웨이 향한 frame이 공격자에게. 방어는 DAI(Dynamic ARP Inspection, 엔터프라이즈 스위치) / static ARP / **TLS 강제**(어차피 L7 암호화면 sniff 무력화).

### 3-hop 경로에서 필드 변화

```
   ┌──────┐  Hop1   ┌────┐  Hop2   ┌────┐  Hop3   ┌──────┐
   │Client├────────►│ R1 ├────────►│ R2 ├────────►│Server│
   └──────┘         └────┘         └────┘         └──────┘

   필드             Hop1       Hop2       Hop3
   ─────────────────────────────────────────────
   src_ip          C          C          C        ← 불변
   dst_ip          S          S          S        ← 불변
   src_mac         C          R1_out     R2_out   ← 변동
   dst_mac         R1_in      R2_in      S_mac    ← 변동
   TTL             64         63         62       ← 감소
   IP checksum     A          B          C        ← 재계산
   TCP/payload     ★          ★          ★        ← 불변
```

**Router의 일**: ① FCS 검증 + dst_mac match → ② Eth 헤더 떼기 → ③ IP checksum 검증 + TTL -1 → ④ routing table 조회 → ⑤ next-hop ARP 조회 → ⑥ 새 Eth frame 조립 + IP checksum 재계산 + FCS 재계산 → ⑦ 송출. **TCP 이상은 절대 안 건드림**(그게 router 정의). NAT/firewall은 본업 넘어 L4까지 보는 부가 기능.

---

## 4. TCP — 3-way / state / 흐름·혼잡 / close

### 4.1 3-way handshake ⭐

```
   Client                           Server (LISTEN)
   ──────                           ──────
      │ ① SYN seq=x
      │ ────────────────────────►   SYN_RECV
   SYN_SENT
      │           ② SYN+ACK seq=y, ack=x+1
      │ ◄────────────────────────
      │ ③ ACK seq=x+1, ack=y+1
      │ ────────────────────────►
   ESTABLISHED                      ESTABLISHED
      │
      │ ◄═══ 양방향 데이터 ═══►
```

**왜 3-way?** 양쪽이 각자 초기 seq를 보내고 상대가 ACK해야 함. SYN×2 + ACK×2 = 4번 같지만, 가운데를 SYN+ACK로 묶어 3번. 2-way로는 server가 client의 ACK 수신 여부를 모름 → half-open.

**초기 seq random?** TCP sequence prediction attack 방어 (1995 Mitnick 공격). RFC 6528.

### 4.2 TCP state — 운영 시 보는 것

```
                       CLOSED
                       │   │
              connect()│   │listen()
                       ▼   ▼
                   SYN_SENT  LISTEN
                       │       │ recv SYN
                       │       ▼
                       │   SYN_RECV
                       ▼       ▼
                     ESTABLISHED
                       │
                       │ (close 측)              (passive 측)
                       │ send FIN                recv FIN, send ACK
                       ▼                        ▼
                   FIN_WAIT_1               CLOSE_WAIT
                       │ recv ACK                │ close()
                       ▼                        ▼ send FIN
                   FIN_WAIT_2               LAST_ACK
                       │ recv FIN, send ACK      │ recv ACK
                       ▼                        ▼
                   TIME_WAIT                 CLOSED
                       │ 2MSL
                       ▼
                     CLOSED
```

| 상태 | 의미 | 폭증 시 |
|---|---|---|
| **ESTABLISHED** 多 | 정상 트래픽 | - |
| **TIME_WAIT** 多 | active close 측에 누적 (보통 client/LB) | ephemeral port 고갈 위험 |
| **CLOSE_WAIT** 多 | 애플리케이션이 close() 안 함 | **거의 항상 코드 버그** (FD leak) |
| **SYN_RECV** 多 | SYN flood or backlog 부족 | tcp_syncookies, somaxconn |
| **FIN_WAIT_2** 多 | 상대가 FIN 안 보냄 | firewall/NAT idle 끊김 |

### 4.3 4-way close + TIME_WAIT 2MSL

TCP는 **half-close** 허용. client FIN → server ACK (CLOSE_WAIT) → server는 남은 데이터 보낸 후 자기 close()에서 FIN → client ACK (TIME_WAIT) → 2MSL 후 CLOSED.

**TIME_WAIT 2MSL의 이유 2가지** (면접 단골):
1. **마지막 ACK 손실 대비**: 상대가 FIN 재전송하면 다시 ACK 보내야 함.
2. **옛 segment 격리**: 같은 4-tuple로 즉시 새 연결 만들면 지연 segment가 새 연결로 흘러옴. 2MSL 후엔 다 죽었다.

**TIME_WAIT 해결**:
- `net.ipv4.tcp_tw_reuse=1` (안전한 재사용)
- `net.ipv4.ip_local_port_range` 확장
- **HTTP keepalive** (가장 정석 — 연결 재사용으로 close 빈도 감소)
- `tcp_tw_recycle`은 NAT에서 망함 → 4.12부터 삭제. **절대 쓰지 마라**.

### 4.4 흐름 제어 + 혼잡 제어

**흐름 제어 (Sliding Window)** — receiver-driven:
```
   Sender의 보낼 데이터:
   [이미 ack됨][전송됨, ack 대기][아직 전송 안 함]
                ◄─── window ───►

   Receiver가 win=10000 → window 10000으로 갱신
   Receiver가 win=0     → sender 정지 (zero window)
```
receiver buffer overflow 방지. 16-bit field는 max 64KB → 100Gbps × 100ms RTT엔 너무 작음 → **Window Scaling**(RFC 7323)의 SYN option에서 shift factor 협상 → 실효 max 1GB.

**혼잡 제어 진화 (한 문단)** — sender-driven, "**네트워크 중간 router의 혼잡**" 다룸:
1986년 ARPANET이 혼잡 붕괴(throughput 1/1000로 폭락) → Van Jacobson이 **Tahoe**(1988): Slow Start(cwnd ×2/RTT)로 시작, ssthresh 넘으면 Congestion Avoidance(+1 MSS/RTT), loss 시 cwnd→1. **Reno**(1990): Fast Recovery 추가 — loss 시 cwnd→cwnd/2(덜 가혹). **CUBIC**(2006, Linux 기본): cwnd를 시간의 3차 함수로 → 고RTT/고대역에서 빠른 회복. **BBR**(2016, Google): 게임체인저 — 기존 모든 알고리즘이 "loss = 혼잡" 가정인데, 무선/모바일에선 loss 대부분이 noise(혼잡 아님)이고 bufferbloat은 loss 전에 latency 폭발. BBR은 **min RTT + max bandwidth** 측정해 `BW × RTT`만 보냄. YouTube: throughput +14%, P95 latency -33%. 단 CUBIC과 같이 쓰면 BBR이 점유율 독점(공정성 문제, BBR v2/v3 개선중). **외부 트래픽엔 BBR, 데이터센터 내부엔 CUBIC**.

활성화: `sysctl net.ipv4.tcp_congestion_control=bbr` + `net.core.default_qdisc=fq`.

### 4.5 RTO / Fast Retransmit / SACK / RST / Nagle

**RTO (Retransmission Timeout)**: `RTO = smoothed_RTT + 4 × RTT_variance` (Jacobson/Karels). 손실 반복 시 exponential backoff (RTO → 2× → 4×).

**Fast Retransmit**: 3 dupACK 받으면 RTO 안 기다리고 즉시 재전송.
```
   pkt1 pkt2 pkt3 pkt4 pkt5
        ✗    ✓    ✓    ✓     (pkt2 손실)
   ACK2 ACK2 ACK2 ACK2        ← 3 dupACK → 즉시 pkt2 재전송
```

**SACK** (RFC 2018): "pkt2 외엔 3,4,5 다 받았다" 광고 → pkt2만 재전송. Reno는 cumulative ACK 한계로 pkt2부터 전체 재전송.

**RST 발생 5가지**: ① 비존재 포트 SYN(서버 미기동/firewall), ② half-open(reboot 후 옛 연결 도착), ③ `SO_LINGER(0)` 강제 abort, ④ firewall `iptables -j REJECT --reject-with tcp-reset`, ⑤ application crash(JVM OOM-killed 등, 커널이 강제 close하며 RST). 진단: `tcpdump 'tcp[tcpflags] & tcp-rst != 0'` + `dmesg | grep -i kill`.

**Nagle vs TCP_NODELAY**: Nagle(1984, RFC 896)은 작은 segment를 buffer에 모음 — 1 byte 작성에 41 byte 오버헤드(=작은 패킷 폭증) 방지. Delayed ACK(200ms)와 결합 시 양쪽이 서로 기다림 → 200ms 지연(대화형에 치명적). **HTTP/gRPC는 거의 항상 NODELAY**, bulk 전송은 Nagle 유지가 효율.

---

## 5. TLS — 비밀과 인증

### 5.1 3가지 보장

1. **Confidentiality**: 중간자가 못 봄 (AES 대칭).
2. **Integrity**: 변조 들킴 (MAC/AEAD).
3. **Authenticity**: 서버 신원 (인증서 + CA 체인).

**대칭 vs 비대칭의 본질**: 대칭(AES)은 빠르지만 키 교환이 문제, 비대칭(RSA/ECDHE)은 키 교환 가능하지만 느림. → **비대칭으로 키 교환 → 대칭으로 데이터 전송** = TLS의 본질.

### 5.2 TLS 1.2 vs 1.3 — 한 표 ⭐

| 항목 | TLS 1.2 | TLS 1.3 |
|---|---|---|
| **Handshake RTT** | 2 | **1** |
| **0-RTT** | ❌ | ✅ (replay 위험) |
| **PFS** | optional | **강제** (ECDHE만) |
| **Legacy cipher** | RSA KEX, CBC, SHA1 허용 | **모두 제거** |
| **AEAD** | optional | **강제** (AES-GCM, ChaCha20-Poly1305) |
| **인증서** | cleartext | **encrypted** (ServerHello부터) |
| **handshake 흐름** | CHello → SHello+Cert → CKE+Finished → Finished | CHello+key_share → SHello+key_share+Cert+Finished → Finished |
| **2025 배포율** | 30% | 70%+ |

**1.3이 1 RTT로 줄인 비결**: ClientHello에 **추측한 key share를 미리 박음**(X25519 등). 서버가 그 그룹을 받으면 ServerHello에 자기 key share + Finished 한 번에. 추측 실패 시 HelloRetryRequest로 2 RTT.

```
   TLS 1.2 (2 RTT)                       TLS 1.3 (1 RTT)
   ──────────────                        ──────────────
   ClientHello ──►                       ClientHello+key_share ──►
   ◄── ServerHello+Cert+SKE+SHelloDone   ◄── ServerHello+key_share
   ClientKE+CCS+Finished ──►                  +Cert+CertVerify+Finished
   ◄── CCS+Finished                      Finished+app_data ──►
   app_data ──►                          ◄── app_data
   
   ★ 1.2: 키 재료를 주고받는 2 round 필요
   ★ 1.3: 클라이언트가 key_share 추측 미리 박음 → 1 round 끝
   ★ ServerHello부터 encrypted (1.2는 Cert까지 cleartext였음)
```

### 5.3 PFS / SNI / ALPN / 0-RTT 위험

- **PFS (Perfect Forward Secrecy)**: server private key 미래 유출돼도 옛 트래픽 복호화 불가. ECDHE의 ephemeral key가 메모리에서 사라진 지 오래라서. RSA KEX는 PFS 없음 → 1.3에서 제거.
- **SNI**: ClientHello에 도메인 평문 → vhost 라우팅. ECH(Encrypted Client Hello)로 1.3+ 에서 암호화 가능(2024~).
- **ALPN**: HTTP/2 vs HTTP/1.1 협상. h2 negotiation의 사실상 유일 메커니즘.
- **0-RTT 위험**: 재방문 시 PSK로 ClientHello에 application data 동봉 → server replay 검증 불완전. `POST /transfer?to=bob&amount=100` 캡처 후 재전송 → 2번 송금. → **0-RTT는 idempotent(GET)만**, 민감 요청 금지.

### 5.4 인증서 체인 검증

```
   Root CA (브라우저/OS trust store, self-signed)
      ▲ 서명
   Intermediate CA (Let's Encrypt R3 등)
      ▲ 서명
   Leaf Certificate (example.com, 공개키+도메인+SAN+유효기간)
```

검증 흐름: ① server가 leaf + intermediate 송신 → ② client가 leaf의 서명을 intermediate 공개키로 검증 → ③ intermediate의 서명을 root CA 공개키로 검증 (브라우저 trust store에 root 있어야) → ④ leaf의 도메인이 SNI 일치 + 유효기간 OK + revocation 미체크 → 신뢰.

**Revocation 체크**:
- **CRL** (Certificate Revocation List): 무거움, 거의 안 씀.
- **OCSP**: 매 연결마다 CA에 질의 → privacy/latency 문제.
- **OCSP Stapling**: 서버가 미리 OCSP 응답 받아 TLS handshake에 첨부 → 빠름.
- 브라우저는 점점 revocation 검사 생략 → **단명 인증서(90일, Let's Encrypt)** 의존.

### 5.5 TLS encapsulation 위치

```
   ┌──────────────────────────────────────┐
   │ HTTP/2 (h2)                           │
   ├──────────────────────────────────────┤
   │ TLS Record (5B hdr + AEAD)            │
   │  ContentType: Handshake/AppData/Alert │
   ├──────────────────────────────────────┤
   │ TCP (20B)                             │
   ├──────────────────────────────────────┤
   │ IP (20B) / Ethernet (14+4)            │
   └──────────────────────────────────────┘

   ★ wireshark로 TCP segment 보면 payload는 암호화
   ★ SNI는 ClientHello 평문이라 보임 (ECH 전까지)
```

---

## 6. QUIC / HTTP/3 — 한 문단

TCP의 4대 한계 — ① **TCP HOL blocking**(HTTP/2 multiplexing도 한 segment loss에 모든 stream stall), ② **handshake 2~3 RTT**(3-way + TLS), ③ **IP 바뀌면 끊김**(Wi-Fi → 4G), ④ **OS kernel에 박혀** 진화가 10년 단위. **QUIC**(2012 Google → 2021 RFC 9000)는 **UDP 위에 TCP 기능 + TLS 1.3 통합**, userspace 구현으로 app과 함께 배포, **Connection ID**(64-bit)로 IP 바뀌어도 같은 connection 유지, stream별로 독립 재전송 → HOL blocking 제거. HTTP/3 = HTTP over QUIC. RTT: 일반 HTTPS 3 RTT(TCP 1 + TLS 1.3 1 + first byte 1) → QUIC 2 RTT(handshake 1 통합 + first byte 1), 재방문 시 0-RTT. 단점: UDP 차단 middlebox 5%(HTTP/2 fallback, Alt-Svc로 자동), userspace이라 OS zero-copy/offload 활용 어려워 CPU↑, tcpdump 디코딩 어려움(암호화 영역 多). 외부 트래픽엔 QUIC, 내부(MySQL wire, SSH, FTP)는 TCP가 충분.

---

## 7. 운영 시나리오 ⭐

### 7.1 TIME_WAIT 폭증 → ephemeral port 고갈

**증상**: `connect() failed: EADDRNOTAVAIL`. `ss -t state time-wait | wc -l` 결과 30000+.

**원인**: 짧은 HTTP 연결 多, active close = client. 1초당 1000 신규 × 60초(2MSL) = 60000 → ephemeral port range 32768~60999 (28232개) 고갈.

**해결**:
1. **HTTP keepalive** (가장 정석) — connection pool로 close 빈도 감소 (HikariCP, Apache HttpClient pool).
2. `sysctl net.ipv4.tcp_tw_reuse=1` (안전한 재사용).
3. `sysctl net.ipv4.ip_local_port_range="10000 65535"`.
4. `tcp_tw_recycle` 절대 금지 (NAT 환경 망함, 4.12 삭제됨).

### 7.2 PMTUD black hole — 대용량 응답 hang

**증상**: 대용량 응답(PDF, 큰 JSON) hang. 작은 요청은 정상. VPN 환경에서 흔함.

**원인 한 줄**: **DF=1 큰 packet이 작은 MTU 구간을 만남 → ICMP "Fragmentation Needed"가 방화벽에 차단 → 송신자가 모르고 무한 재전송**.

```
   Client (MTU 1500) ─── VPN tunnel (MTU 1400) ─── Server (MTU 1500)
   서버가 1500 DF=1 → tunnel router drop + ICMP unreachable
   → 방화벽이 ICMP 차단 → 서버는 응답 없음 → hang
```

**진단**: `ping -M do -s 1472 host` (1472+28=1500), `tracepath host`.

**해결**:
- **MSS clamping**: `iptables -t mangle -A FORWARD -p tcp --tcp-flags SYN,RST SYN -j TCPMSS --clamp-mss-to-pmtu`
- 방화벽에서 **ICMP type 3 code 4** (Fragmentation Needed) 통과 허용 — 보안 명분으로 ICMP 전체 차단 금지.
- **PLPMTUD**(RFC 4821) 활성화: `net.ipv4.tcp_mtu_probing=1`.

### 7.3 ARP spoofing / 게이트웨이 MAC 이상

**증상**: 같은 LAN 호스트 통신 끊김 또는 응답 느려짐. `arp -a`에 게이트웨이 MAC이 평소와 다름.

**원인**: ① ARP spoofing 공격, ② keepalived gratuitous ARP race, ③ 가상화 MAC 중복.

**진단**:
```bash
arp -an                      # 현재 cache
tcpdump -i eth0 -nn arp      # 누가 어떤 IP를 광고하는지
# 같은 IP를 여러 MAC이 광고하면 충돌 또는 공격
```

**해결**:
- 단기: `arp -d <ip>` 후 재학습, 또는 static `arp -s 10.0.0.1 AA:BB:..`.
- 장기: 스위치 **DAI (Dynamic ARP Inspection)** + DHCP snooping.
- **TLS 강제** — MITM 되어도 평문 노출 차단.

---

## 8. 진단 도구 — 한 화면 정리

```bash
# TCP 상태 카운트
ss -t -a | awk 'NR>1 {print $1}' | sort | uniq -c

# 활성 connection의 cwnd/rtt
ss -tin

# 3-way 캡처
sudo tcpdump -i en0 -nn -vv 'host example.com and tcp port 443'
#  flag: [S]=SYN [S.]=SYN+ACK [.]=ACK [P.]=PSH+ACK [F.]=FIN+ACK [R]=RST

# RST 추적
sudo tcpdump 'tcp[tcpflags] & tcp-rst != 0'

# 인증서 체인 + cipher
openssl s_client -connect example.com:443 -servername example.com -showcerts

# TLS 1.3 강제 / cipher 강제
openssl s_client -connect example.com:443 -tls1_3
openssl s_client -connect example.com:443 -cipher 'ECDHE-RSA-AES256-GCM-SHA384'

# 종합 진단
sslscan example.com
testssl.sh example.com

# CLOSE_WAIT FD leak 추적
lsof -p <pid> | grep CLOSE_WAIT

# SYN flood 진단
dmesg | grep -i syn
nstat -az TcpExtListenOverflows
```

**HTTPS GET 한 번의 wire 시퀀스**:
```
   #1~3: TCP 3-way (~1 RTT)
   #4~6: TLS handshake (~1 RTT)        ← 1.3이면 1 RTT, 1.2면 2 RTT
   #7:   첫 HTTP 데이터 (TTFB ≈ 200ms)
   #N~:  FIN, FIN+ACK, ACK ... (4-way close)
```

---

## 9. 꼬리질문

1. **"TCP 3-way가 왜 3번이지 2번이 아닌가?"** — 양쪽이 각자 초기 seq를 보내고 ACK받아야 함(SYN×2+ACK×2). 가운데 ACK+SYN을 묶어 3번. 2-way는 server가 client ACK 수신 여부 모름 → half-open. 초기 seq random은 prediction attack 방어.

2. **"TIME_WAIT가 왜 2MSL인가? 줄이는 안전한 방법은?"** — (1) 마지막 ACK 손실 시 상대 FIN 재전송에 다시 ACK, (2) 같은 4-tuple 새 연결에 옛 segment 혼선 방지. 안전한 해결: HTTP keepalive > `tcp_tw_reuse` > `SO_REUSEADDR`. `tcp_tw_recycle`은 NAT 망함, 4.12 삭제 — 절대 금지.

3. **"TLS 1.3이 어떻게 1 RTT로 줄였나? 0-RTT는 왜 위험한가?"** — ClientHello에 추측한 key_share 미리 박음. 서버가 받으면 ServerHello에 자기 key_share+Cert+Finished 한 번에. 0-RTT는 재방문 PSK로 application data 동봉 → server replay 검증 불완전, POST 같은 non-idempotent에 쓰면 송금 2번. 0-RTT는 GET만.

4. **"MAC은 hop마다 변하는데 IP는 안 변한다. 왜?"** — MAC은 same-LAN next-hop 주소, IP는 end-to-end 식별자. Router는 LAN 경계 → 매 hop마다 Eth 헤더 떼고 다음 hop MAC으로 재조립(ARP로 알아냄). NAT는 router가 본업을 넘어 L4까지 inspect → src_ip/src_port 갈아치움 (end-to-end 원칙 깨짐).

5. **"TCP checksum 있는데 Ethernet FCS는 왜 또?"** — defense in depth. FCS는 link-local 우연 손상(NIC/케이블), TCP checksum은 end-to-end 우연 손상(router 메모리 오염), TLS HMAC/AEAD는 **악의적 변조**. 각 계층 다른 신뢰 모델. checksum은 random 손상만 잡고 적대적 변경 못 잡음 — 그래서 TLS 필수.

---

---

## 10. 백지 마스터 체크리스트

이 챕터 끝났다면 종이에 그릴 수 있어야 한다.

- [ ] OSI 7계층 책임 매트릭스 (각 PDU/식별자/검증/대표 프로토콜).
- [ ] `GET /users/김면수`의 캡슐화 (HTTP→TLS→TCP→IP→Eth→bits) + 오버헤드 75B.
- [ ] MTU 1500 vs MSS 1460의 관계 + SYN option 광고.
- [ ] 다층 검증 (FCS / IP checksum+TTL / TCP checksum / TLS AEAD / L7 비즈니스) — 왜 중복.
- [ ] IP는 end-to-end, MAC은 hop-to-hop — 3-hop에서 어떤 필드가 변하는지.
- [ ] Router 내부 일 (FCS검증→Eth떼기→TTL-1→routing→ARP→재조립→재checksum).
- [ ] ARP 동작 (broadcast request / unicast reply / L2.5) + spoofing + 방어.
- [ ] TCP 3-way handshake + 왜 3번인지 + 초기 seq random 이유.
- [ ] TCP state 5개 핵심 (ESTABLISHED/TIME_WAIT/CLOSE_WAIT/SYN_RECV/FIN_WAIT_2) + 폭증 시 의미.
- [ ] TIME_WAIT 2MSL 두 가지 이유 + 해결책 우선순위(keepalive > tw_reuse > REUSEADDR).
- [ ] 흐름 제어(window) vs 혼잡 제어(cwnd) 차이 + BBR이 게임체인저인 이유.
- [ ] Fast Retransmit / SACK / RST 5가지 케이스.
- [ ] TLS 1.2 vs 1.3 비교표 + 1.3이 어떻게 1 RTT로 줄였나.
- [ ] 0-RTT replay 위험 + 인증서 체인 검증 흐름.
- [ ] PFS / SNI / ALPN의 의미.
- [ ] QUIC가 TCP를 버린 4대 이유 + Connection Migration.
- [ ] 운영 3대 시나리오 진단·해결 (TIME_WAIT 고갈 / PMTUD black hole / ARP spoofing).
- [ ] `ss -tin` / `tcpdump` flag / `openssl s_client` 출력 해석.

---

## 다음 챕터로의 연결

- **04-load-balancer-deep-dive**: TCP/TLS가 L4/L7 LB에서 종단·재시작. SSL termination, DSR, sticky session, WAF.
- **05-nginx-internals**: TCP 연결이 Nginx에 도착한 후 epoll 처리.
- **06-tomcat-internals**: HTTP가 Java 객체(HttpServletRequest)로 변환.
- **07-connection-pools-master**: TIME_WAIT 회피와 keepalive 실제 운영 — Nginx upstream / HikariCP / kernel backlog.

---

> **부록 참조 (slim 이전 풀버전)**: byte 단위 헤더 layout, TLS handshake 시퀀스 풀버전, MAC hop-to-hop 3-hop 그림, kernel→wire 비트 변환 풀버전은 git **7e4a6c8** commit 참조.
