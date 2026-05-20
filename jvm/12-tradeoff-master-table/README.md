# 12. Tradeoff Master Table — Cross-chapter 종합 비교

> 시니어 면접의 모든 질문은 "왜 X 대신 Y?"로 환원된다. G1 vs ZGC, synchronized vs ReentrantLock, JVM vs Native Image — 답은 항상 트레이드오프.
> 본 챕터는 책 전체의 트레이드오프를 한 표로 종합. 마인드맵의 5개 축 (GC / 컴파일 / Threading / JVM 구현 / 동기화) + 결정 트리.
> 시니어는 워크로드를 듣는 순간 결정 트리를 머릿속에서 돌려 권장안을 30초 안에 말한다.

---

## 이 문서의 사용법

이 문서는 **면접용 마인드맵**을 따라 선형으로 펼친 구조다. 학습 순서 = 면접 답변 순서 = 백지에 그리는 순서.

1. **0장 마인드맵을 먼저 외운다** — 루트 한 문장 + 3가지 가지 + 각 가지의 키워드.
2. **1~3장을 순서대로 학습한다** — 각 장이 마인드맵의 한 가지에 정확히 대응.
3. **4장 결정 트리와 매트릭스로 검증** — 워크로드를 보면 즉시 권장안을 말한다.
4. **5장 꼬리질문으로 깊이 점검**.

---

## 0. 마인드맵 — 면접 종이에 그릴 그림

### 루트 한 문장 (anchor)

> **"JVM 운영 결정은 5축 트레이드오프로 환원된다: GC / 컴파일 / Threading / JVM 구현 / 동기화. 각 축마다 워크로드별 최적이 다르고, 시니어는 결정 트리로 30초 안에 답한다."**

이 한 문장에서 모든 답변이 출발한다. 어떤 질문이 와도 이 문장부터 말하고 적절한 가지로 분기.

### 3개 가지 — 순서를 외운다

```
                  [ROOT: 트레이드오프 5축 + 결정 트리]
                                 │
        ┌──────────────┬─────────┴─────────┐
        │              │                   │
       ① 5축 매트릭스  ② 결정 트리          ③ Container 옵션
       (비교표)       (워크로드→권장)      (사이즈별)
        │              │                   │
     ┌──┼──┐        ┌──┼────┐           ┌──┼──┐
   GC 컴파일       startup latency      2c  4c  16c
   Threading      throughput            4GB 8GB 64GB
   JVM구현        I/O bound
   동기화
```

### 가지별 핵심 키워드

| 가지 | 키워드 1 | 키워드 2 | 키워드 3 |
|---|---|---|---|
| **① 5축 매트릭스** | GC 7종 / 컴파일 5종 | Threading 3종 / JVM 구현 4종 | 동기화 4종 |
| **② 결정 트리** | startup 우선? → Native/Serial | P99 < 10ms? → ZGC/GenZGC | throughput? → Parallel |
| **③ Container 옵션** | 2c4GB / 4c8GB / 16c64GB | Xmx + Metaspace + Direct + Code Cache | GC 선택 |

### 면접 답변 흐름

> 면접관 질문 → 루트 문장 → 질문에 맞는 축 1개 선택 → 그 축의 표 → 결정 트리로 권장안 → Container 옵션 예시

---

## 1. 가지 ①: 5축 매트릭스

### 1.1 핵심 질문

> "JVM 운영 결정을 어떤 축으로 나눠서 외우나요?"

### 1.2 축 1 — GC 7종

| | Serial | Parallel | CMS (제거) | G1 | ZGC (single) | Shenandoah | Gen ZGC |
|---|---|---|---|---|---|---|---|
| JDK | 1.0+ | 1.4+ | 1.4~13 | 7+, 9 default | 11~ | 12~ | 21+ |
| Young algo | Copying | Parallel Copy | Parallel Copy | Region Evac | Concurrent | Concurrent | Concurrent |
| Old algo | Mark-Compact | Mark-Compact | Concurrent MS | Region Evac | Concurrent | Concurrent | Concurrent |
| STW pause | 수백 ms ~ 수초 | 수십 ~ 수백 ms | ~100 ms (CMF 시 김) | 10~200 ms (목표) | < 1 ms | ~10 ms | < 1 ms |
| Throughput | 보통 | 높음 | 보통 | 보통~높음 | 85% (G1 대비) | 85% | 100% (G1 동등) |
| Heap 한계 | <512MB | ~수십 GB | ~수십 GB | ~수백 GB | 16TB | ~수백 GB | 16TB |
| 메모리 효율 | 좋음 | 좋음 | 단편화 | 좋음 | 부담 (~20%) | 좋음 | 좋음 |
| 적합 | 작은 Heap, 단일코어 | Batch, throughput | (제거) | 일반 서비스 | 큰 Heap latency | Latency portable | 신규 default |
| 옵션 | `-XX:+UseSerialGC` | `-XX:+UseParallelGC` | (제거) | `-XX:+UseG1GC` | `-XX:+UseZGC` | `-XX:+UseShenandoahGC` | `-XX:+UseZGC -XX:+ZGenerational` |

**시니어 핵심**: G1이 일반 default, ZGC는 큰 Heap latency, Generational ZGC가 JDK 21+ 신규 default 후보.

### 1.3 축 2 — 컴파일 모델 5종

| | Interpreter only | C1 only | C2 only | Tiered (기본) | AOT/Native Image |
|---|---|---|---|---|---|
| Startup | 즉시 | 빠름 | 매우 느림 | 빠름 | 가장 빠름 (수십 ms) |
| Peak throughput | 매우 낮음 | 보통 | 최고 | 최고 | 약간 낮음 (~90%) |
| Code Cache | 0 | 작음 | 보통 | 큼 | 0 (binary에 포함) |
| 옵션 | `-Xint` | `-XX:TieredStopAtLevel=1` | `-XX:-TieredCompilation` | (기본) | `native-image` |
| 적합 | 디버깅, 재현 | 컨테이너 작음 | Batch | 일반 | Serverless, CLI |

**시니어 핵심**: Tiered가 99% 케이스의 답. C1-only는 작은 컨테이너 cold start 단축용. Native Image는 serverless.

### 1.4 축 3 — Threading 모델 3종

| | Platform Thread (1:1) | Virtual Thread (M:N) | Async (CompletableFuture) |
|---|---|---|---|
| Memory | 1MB/thread (OS stack) | ~수 KB (Heap chunk) | 0 (continuation 없음) |
| 최대 수 | ~수천 | 수십만~수백만 | 무제한 |
| 생성 비용 | ~수 ms | ~수 us | ~수 us |
| Synchronous 코드 | yes | yes | no (async only) |
| Blocking I/O | no (thread 점유) | yes (freeze) | no |
| CPU-bound | yes | 보통 (carrier 점유) | 보통 |
| synchronized | yes | pinning (JDK 21~23) | yes |
| 디버깅 | 정상 | 정상 (stack trace) | 어려움 (callback hell) |

**시니어 핵심**: I/O bound → Virtual Thread, CPU bound → Platform Thread. JDK 24+ pinning 해소 후엔 VT가 default.

### 1.5 축 4 — JVM 구현 4종

| | HotSpot | OpenJ9 | GraalVM | Native Image |
|---|---|---|---|---|
| Author | Oracle | IBM Eclipse | Oracle | Oracle |
| Compiler | C2 (C++) | TR (C++) | Graal (Java) | AOT Graal |
| Footprint | 보통 | 작음 (~30% ↓) | 보통 | 작음 (~70% ↓) |
| Startup | 보통 | 빠름 | 보통 | 가장 빠름 |
| Peak throughput | 최고 | 약간 ↓ | 일부 ↑ | 약간 ↓ |
| 운영 maturity | 매우 성숙 | 성숙 | 성숙 중 | 성숙 중 |
| 적합 | 일반 | 메모리 제약 | Polyglot, 큰 throughput | Serverless |

### 1.6 축 5 — 동기화 메커니즘 4종

| | synchronized | ReentrantLock | volatile | CAS (AtomicXxx) |
|---|---|---|---|---|
| 메커니즘 | JVM Mark Word | Java AQS | Memory barrier | lock cmpxchg |
| 비용 (no contention) | ~수십 cycles | ~수십 cycles | ~30 cycles (write) | ~10 cycles |
| 비용 (contention) | OS park/unpark | OS park/unpark | N/A | retry |
| 정확성 | 모든 mutate | 모든 mutate | visibility만 | atomicity 보장 |
| Try-lock | no | yes | N/A | yes |
| Interruption | no | yes | N/A | N/A |
| Condition | wait/notify | 여러 Condition | N/A | N/A |
| VT pinning (JDK 21~23) | yes | no | no | no |

**시니어 핵심**:
- VT 환경 → ReentrantLock 우선 (pinning 회피).
- visibility만 필요 → volatile.
- counter/flag 등 atomicity → AtomicXxx.
- 일반 mutate → synchronized (간결) or ReentrantLock (기능 풍부).

---

## 2. 가지 ②: 결정 트리 — 워크로드 → 권장

### 2.1 핵심 질문

> "워크로드 설명을 들으면 즉시 권장안을 말할 수 있나요?"

### 2.2 결정 트리

```
1. Startup이 가장 중요? (serverless, CLI, K8s scale-up)
   YES → Native Image (GraalVM) 또는 -XX:TieredStopAtLevel=1
   NO  → 2번

2. P99 latency 목표 < 10ms? (latency-critical API)
   YES → ZGC (JDK 17+) 또는 Generational ZGC (JDK 21+)
   NO  → 3번

3. Throughput 최우선 (batch, ETL)?
   YES → Parallel GC + -XX:-TieredCompilation (C2 only)
   NO  → 4번

4. I/O bound 동시성 ↑↑ (수만 connection)?
   YES → Virtual Thread (JDK 21+) + ReentrantLock
   NO  → 5번

5. 일반 서비스 (대부분):
   → G1 (기본) + Tiered Compilation (기본) + Platform Thread
```

### 2.3 결정 트리의 사고 흐름

> **시니어가 워크로드 질문을 받으면**:
> 1. "이 워크로드가 startup-critical인가?" 묻고 답 받는다.
> 2. 아니면 "latency 목표가 얼마인가?" 묻는다.
> 3. 그 다음 "throughput vs 동시성 어느 쪽이 중요한가?" 묻는다.
> 4. 마지막에 5축 매트릭스에서 권장 조합을 도출.

### 2.4 시나리오 예시

**시나리오 A — 신규 microservice (REST API, JDK 21)**:
- Startup-critical: 아님 (long-running)
- P99 목표: 100ms (일반)
- I/O bound: yes (DB, HTTP)
- **권장**: G1 + Tiered + Virtual Thread + ReentrantLock

**시나리오 B — AWS Lambda Java**:
- Startup-critical: yes (cold start 비용)
- **권장**: Native Image (GraalVM) + Spring Boot 3 AOT

**시나리오 C — 야간 batch (ETL, 큰 Heap)**:
- Throughput 최우선: yes
- 큰 Heap: 32GB+
- **권장**: Parallel GC + C2 only (`-XX:-TieredCompilation`) + Platform Thread

**시나리오 D — Trading system (latency-critical, 100GB Heap)**:
- P99 목표: < 5ms
- 큰 Heap
- **권장**: Generational ZGC (JDK 21+) + Tiered + Platform Thread, lock-free 자료구조 위주

**시나리오 E — K8s에서 scale-up 자주 발생하는 web service**:
- Startup-critical: 중간 (수 초가 사용자 영향 큼)
- Container 작음
- **권장**: HotSpot + AppCDS + ReservedCodeCacheSize 작게. 또는 Native Image 검토.

---

## 3. 가지 ③: Container 옵션 매트릭스

### 3.1 핵심 질문

> "Container 사이즈가 정해지면 JVM 옵션을 어떻게 설정하나요?"

### 3.2 옵션 매트릭스

```
[2 CPU, 4GB limit]
━━━━━━━━━━━━━━━━━━
-Xms2g -Xmx2g                          # Heap ~ 50% of limit
-XX:MaxMetaspaceSize=256m
-XX:MaxDirectMemorySize=512m
-XX:ReservedCodeCacheSize=128m
-XX:+UseG1GC -XX:MaxGCPauseMillis=200

[4 CPU, 8GB limit]
━━━━━━━━━━━━━━━━━━
-Xms4g -Xmx4g
-XX:MaxMetaspaceSize=512m
-XX:MaxDirectMemorySize=1g
-XX:ReservedCodeCacheSize=256m
-XX:+UseG1GC -XX:MaxGCPauseMillis=100

[16 CPU, 64GB limit]
━━━━━━━━━━━━━━━━━━━
-Xms32g -Xmx32g
-XX:MaxMetaspaceSize=1g
-XX:MaxDirectMemorySize=4g
-XX:ReservedCodeCacheSize=512m
-XX:+UseZGC -XX:+ZGenerational          # JDK 21+
# 또는 -XX:+UseG1GC
```

### 3.3 사이즈 결정 원리

| 영역 | 일반 비율 | 이유 |
|---|---|---|
| Heap (`-Xmx`) | container limit의 50~70% | Heap 외 영역(Thread, Metaspace, Code Cache, Direct, Internal)에 30~50% 여유 |
| Metaspace | 100MB~1GB | 일반 256MB, Spring/대형 ORM은 512MB+ |
| Direct Memory | 512MB~4GB | NIO buffer pool 크기 |
| Code Cache | 128MB~512MB | JIT 컴파일 코드량 |
| Thread | 스레드 수 × 1MB | `-Xss` 기본 1MB, pool 크기에 따라 다름 |

→ [Chapter 02-03 Stack & PC & Native](../02-runtime-data-areas/03-stack-pc-native.md)의 가지 ④ Killer 시나리오에서 풀버전.

### 3.4 GC 선택 매트릭스

| Heap | 권장 GC | 이유 |
|---|---|---|
| < 1GB | Serial | overhead 최소 |
| 1~4GB | G1 (or Parallel) | 일반 default, batch면 Parallel |
| 4~32GB | G1 | 안정적, MaxGCPauseMillis 가능 |
| 32~256GB | G1 (throughput) or ZGC (latency) | latency-critical이면 ZGC |
| 256GB~16TB | ZGC / Generational ZGC | sub-ms STW + 거대 Heap |

### 3.5 옵션 관련 체크리스트 (Production)

- `-Xms == -Xmx` — startup 시 Heap 한 번에 reserve, OS와 협상 비용 없음.
- `-XX:+HeapDumpOnOutOfMemoryError -XX:HeapDumpPath=/var/log/heap.hprof` — OOM 시 dump.
- `-XX:+ExitOnOutOfMemoryError` — OOM 시 즉시 종료 (orchestrator가 재시작).
- `-XX:NativeMemoryTracking=summary` — NMT 켜기.
- `-XX:StartFlightRecording=disk=true,maxage=24h,maxsize=500M` — JFR continuous.
- Container awareness 확인 — JDK 10+ default (cgroup 인식).

---

## 4. 면접 답변 워크플로우

### 4.1 질문 → 가지 매핑

| 면접 질문 | 진입 가지 | 인접 확장 |
|---|---|---|
| "G1 vs ZGC 언제?" | ① 축 1 GC | ② 결정 트리 |
| "synchronized vs ReentrantLock?" | ① 축 5 동기화 | VT pinning |
| "VT는 항상 좋은가?" | ① 축 3 Threading | ② 결정 트리 |
| "Native Image 도입 기준?" | ① 축 4 JVM 구현 | ② startup 가지 |
| "신규 프로젝트 추천 조합?" | ② 결정 트리 | ① 5축 |
| "2 CPU 4GB container 옵션?" | ③ Container | ① GC 선택 |
| "Batch job 옵션?" | ② Throughput 가지 | ① Parallel + C2 |
| "Lambda Java cold start?" | ② Startup 가지 | ① Native Image |

### 4.2 답변 템플릿

> **루트 문장 한 줄 → 결정 트리 → 권장 조합 → Container 옵션 예시**

예: "신규 microservice JDK 21로 만드는데 권장 조합?"

> "JVM 운영 결정은 5축 트레이드오프로 환원되고, 결정 트리로 답합니다.
> 1. Startup-critical인가? — long-running web service라 아닙니다.
> 2. P99 < 10ms 목표인가? — 일반 100ms 목표라 아닙니다.
> 3. Throughput 최우선인가? — 일반 service라 아닙니다.
> 4. I/O bound 동시성 ↑인가? — DB와 HTTP 호출 많아서 yes.
>
> 권장:
> - **GC**: G1 (기본, JDK 21에서도 충분). 큰 Heap 가면 Generational ZGC 검토.
> - **컴파일**: Tiered (기본).
> - **Threading**: Virtual Thread.
> - **동기화**: ReentrantLock 우선 (VT pinning 회피).
> - **JVM 구현**: HotSpot.
>
> Container 4 CPU 8GB라면: `-Xms4g -Xmx4g -XX:MaxMetaspaceSize=512m -XX:MaxDirectMemorySize=1g -XX:ReservedCodeCacheSize=256m -XX:+UseG1GC -XX:MaxGCPauseMillis=100`."

→ 면접관이 "왜 ReentrantLock?"이면 ① 축 5로, "Heap 비율?"이면 ③ 사이즈 결정 원리로.

---

## 5. 꼬리질문 트리

### Q1 [가지 ①]. G1과 ZGC를 언제 다르게 쓰나요?

> Heap 크기와 P99 latency 목표로 갈림.
> - Heap < 32GB + 일반 service → G1 (기본).
> - Heap 32GB+ 또는 P99 < 10ms 목표 → ZGC.
> - JDK 21+ → Generational ZGC (sub-ms + G1 throughput 동등).
> 메모리 부담 ~20%는 ZGC의 비용.

### Q2 [가지 ①]. synchronized vs ReentrantLock?

> 일반 mutate면 synchronized가 간결. 다음 경우 ReentrantLock 필수:
> - try-lock, interruptible lock, fair lock 필요.
> - 여러 Condition 필요 (producer/consumer 등).
> - **Virtual Thread + blocking I/O** — synchronized는 pinning, ReentrantLock은 freeze 가능 (JDK 21~23).
> - JDK 24+ JEP 491 후엔 synchronized pinning 해소 예정.

### Q3 [가지 ①]. Virtual Thread를 항상 써야 하나요?

> No. I/O bound 동시성 ↑ 워크로드에서 좋음. CPU bound면 platform thread가 carrier 점유 회피로 더 나음. 또 synchronized가 코드 곳곳에 있으면 pinning으로 처리량 저하 — 리팩토링 부담.

**🪝 Q3-1: Hybrid는?**
> CPU 작업을 platform pool로 위임, 나머지는 VT. 예: VT 핸들러 안에서 `executorService.submit(cpu-task)`로 platform thread에 위임.

### Q4 [가지 ②]. Startup이 가장 중요할 때 옵션은?

> 우선순위:
> 1. **Native Image (GraalVM)** — 수십 ms startup, footprint 1/4~1/10.
> 2. **-XX:TieredStopAtLevel=1** — C1만 사용, C2 disable. Peak는 ↓이지만 cold start 빠름.
> 3. **AppCDS** — class metadata pre-shared.
> 4. **-Xint** (절대 production X) — 디버깅용.

### Q5 [가지 ②]. Throughput 최우선 batch job의 옵션?

> - GC: Parallel (`-XX:+UseParallelGC`) — STW 길지만 throughput 최고.
> - 컴파일: C2 only (`-XX:-TieredCompilation`) — C1 skip, peak 빠름. 단 warmup 길어짐.
> - Heap: 크게, young/old 비율 워크로드별 조정.
> - JIT inline: `-XX:MaxInlineSize`, `-XX:FreqInlineSize` 늘릴 수 있음.

### Q6 [가지 ③]. Container limit의 몇 %를 Heap으로 줘야 하나요?

> 일반 50~70%. 이유: Heap 외 영역(Thread × N + Metaspace + Code Cache + Direct + Internal)이 30~50% 차지. 너무 크게 잡으면 Container OOM-killed. 너무 작게 잡으면 GC 빈발. NMT로 실측 후 조정.

**🪝 Q6-1: Heap을 80%로 줬더니 OOM-killed가 나는데?**
> Heap 외 영역 합이 limit 초과. NMT로 확인: Thread(스레드 수 × 1MB), Metaspace, Code Cache, Direct Memory 합산. 가장 흔한 원인은 Thread pool 폭증. [Chapter 02-03]의 Killer 시나리오.

### Q7 (Killer) [가지 ②]. 다음 워크로드의 권장 조합은?
> "JDK 21, 4 CPU 8GB container, REST API, DB 호출 많음, P99 200ms 목표, 평균 RPS 500."

> 결정 트리:
> 1. Startup-critical? — 아님.
> 2. P99 < 10ms? — 아님 (200ms 목표).
> 3. Throughput 최우선? — 아님.
> 4. I/O bound? — yes (DB 많음).
>
> 권장:
> - **GC**: G1 (`-XX:+UseG1GC -XX:MaxGCPauseMillis=100`).
> - **컴파일**: Tiered (기본).
> - **Threading**: Virtual Thread.
> - **동기화**: ReentrantLock 우선.
> - **JVM**: HotSpot.
>
> 옵션:
> ```
> -Xms4g -Xmx4g
> -XX:MaxMetaspaceSize=512m
> -XX:MaxDirectMemorySize=1g
> -XX:ReservedCodeCacheSize=256m
> -XX:+UseG1GC -XX:MaxGCPauseMillis=100
> -XX:+HeapDumpOnOutOfMemoryError -XX:HeapDumpPath=/var/log/heap.hprof
> -XX:NativeMemoryTracking=summary
> -XX:StartFlightRecording=disk=true,maxage=24h,maxsize=500M
> ```
>
> Production rollout: canary 1대 → metric 비교 (P99, throughput, RSS, GC pause) → 점진 확장.

---

## 6. 학습 체크리스트

면접 전 백지에서 다음을 다 해낼 수 있어야 마스터:

- [ ] 0장 마인드맵을 종이에 1분 이내로 그릴 수 있다 (루트 + 3가지 + 키워드)
- [ ] 가지 ① 5축: GC 7종 / 컴파일 5종 / Threading 3종 / JVM 구현 4종 / 동기화 4종을 외운다
- [ ] 가지 ① 각 축의 적합 워크로드를 한 줄로 말한다
- [ ] 가지 ② 결정 트리: 5단계 질문 순서를 외운다 (startup → latency → throughput → I/O → 일반)
- [ ] 가지 ② 시나리오 5종 (microservice / Lambda / batch / trading / K8s scale)에 각자 권장안을 말한다
- [ ] 가지 ③ Container: 2c4GB / 4c8GB / 16c64GB 옵션 세트를 외운다
- [ ] 가지 ③ Container: Heap이 limit의 50~70%인 이유를 말한다
- [ ] Heap 사이즈별 권장 GC를 말한다 (<1GB Serial / 1~32GB G1 / 32~256GB G1 or ZGC / 256GB+ ZGC)
- [ ] Production 체크리스트 5개 옵션을 외운다 (HeapDump / ExitOnOOM / NMT / JFR / Xms=Xmx)
- [ ] 5장 꼬리질문 7개에 막힘없이 답한다

---

## 다음 단계

- → [Chapter 09. Mock Interviews](../09-mock-interviews/): 면접 시뮬레이션
- 모든 챕터의 cross-reference 종착점

## 참고

- [Chapter 02 Memory Regions](../02-runtime-data-areas/): 메모리 영역 풀버전
- [Chapter 03 Execution Engine](../03-execution-engine/): 컴파일 모델 풀버전
- [Chapter 04 GC](../04-garbage-collection/): GC 풀버전
- [Chapter 05 JVM Tuning](../05-jvm-tuning/): 옵션 풀버전
- [Chapter 06 Version History](../06-version-history/): JDK별 default
- [Chapter 08 GraalVM](../08-graalvm/): Native Image
- [Chapter 11 Hands-on Workbook](../11-hands-on-workbook/): 도구 매핑
