# 04-06. GC Tuning + 운영 — 종합 가이드

> GC 알고리즘을 알았다고 운영자가 되는 건 아니다. **production에서 사고가 났을 때** 어느 옵션을 어떻게 조정하고 어떤 메트릭으로 검증할지가 시니어의 역량.
> 본 챕터는 GC 7종을 운영 관점에서 종합 + 흔한 운영 시나리오 + 옵션 매트릭스. **01~05를 모두 읽은 후** 본 챕터로 마무리.

---

## 이 문서의 사용법

1. **0장 마인드맵을 먼저 외운다** — 운영의 4가지 차원.
2. **1~4장: 운영 4축 마스터**.
3. **5장 면접 워크플로우** + **6장 꼬리질문**.

---

## 0. 마인드맵 — 면접 종이에 그릴 그림

### 루트 한 문장 (anchor)

> **"GC 운영은 4가지 축이다. 선택 (워크로드→GC) / 진단 (8대 시나리오) / 도구 (GC log + JFR + MAT) / 마이그레이션 (canary + 메트릭 비교)."**

### 4개 가지 — 순서를 외운다

```
              [ROOT: GC 운영 = 선택 + 진단 + 도구 + 마이그레이션]
                                  │
       ┌──────────────────┬──────────────────┬──────────────────┐
       │                  │                  │                  │
     ① 선택 매트릭스    ② 8대 진단 시나리오  ③ 도구              ④ 마이그레이션
     (워크로드→GC)      (Full GC / spike    (GC log /          (G1→ZGC 절차)
                        / RSet / Humongous   JFR / MAT)
                        / OOM 등)
       │                  │                  │                  │
   ┌───┼───┐         ┌────┼────┐         ┌───┼───┐         ┌────┼────┐
  Heap크기 JDK버전   Full GC P99      GC log JFR        Canary  단계적
  Latency 컨테이너    Promo  Humong   MAT    NMT        1대→25→ 확대
  목표              Failure RSet     GCEasy            50→100
```

### 가지별 핵심 키워드

| 가지 | 키워드 1 | 키워드 2 | 키워드 3 |
|---|---|---|---|
| **① 선택 매트릭스** | Heap 크기 (4GB/32GB/100GB+) | JDK 버전 (11/17/21+) | Latency 목표 (P99) |
| **② 8대 진단 시나리오** | Full GC 빈발 / P99 spike | RSet 비대 / Humongous | OOM / Container OOM-kill |
| **③ 도구** | GC log (모든 production) | JFR (24/7 continuous) | MAT (heap dump) |
| **④ 마이그레이션** | Canary 1대 | 메트릭 비교 (RSS/P99/throughput) | 단계적 확대 |

### 면접 답변 흐름

> 면접관 질문 → 루트 문장 → 해당 가지 → 키워드 3개 → 인접 가지로 확장

---

## 1. 가지 ①: 선택 매트릭스 — 워크로드 → GC

### 1.1 핵심 질문

> "내 워크로드에 어떤 GC를 선택해야 하나요?"

### 1.2 키워드 1 — Heap 크기 축

```
< 512MB:         Serial GC (thread overhead 회피)
512MB ~ 4GB:    Parallel (batch) 또는 G1 (일반)
4GB ~ 32GB:     G1 (기본) 또는 Shenandoah (latency)
32GB ~ 128GB:   G1 또는 Generational ZGC (JDK 21+)
128GB+:         Generational ZGC 거의 필수
TB 단위:        Generational ZGC 유일 (16TB 한계)
```

### 1.3 키워드 2 — JDK 버전 축

```
JDK 8 (LTS):
   G1 stable. ZGC 없음. Parallel default.

JDK 11 (LTS):
   G1 default. ZGC experimental.

JDK 17 (LTS):
   G1 default. ZGC stable. Generational 없음.

JDK 21 (LTS):
   G1 default. Generational ZGC preview.

JDK 23+:
   Generational ZGC stable.
```

### 1.4 키워드 3 — Latency 목표 축

```
P99 < 1ms:        Generational ZGC (sub-ms STW)
P99 < 10ms:       ZGC, Shenandoah
P99 < 100ms:      G1 (MaxGCPauseMillis 조정)
P99 < 500ms OK:   Parallel (throughput 우선)
Latency 무관:     Parallel (batch)
```

### 1.5 통합 선택 매트릭스

| 환경 | 1st 선택 | 2nd 선택 | 비고 |
|---|---|---|---|
| Heap < 512MB, 1코어 | Serial | - | 개발/테스트 |
| Heap < 4GB, batch | Parallel | G1 | throughput 우선 |
| Heap 4~32GB, web | G1 (기본) | Shenandoah | 일반 case |
| Heap 32~128GB | G1 또는 Gen ZGC | Shenandoah | JDK 21+면 ZGC |
| Heap 128GB+ | Gen ZGC | - | ZGC 거의 필수 |
| Latency P99 < 10ms | ZGC/Shenandoah | - | sub-ms STW |
| HFT, real-time | ZGC | Shenandoah | 최저 STW |
| Container 0.5 CPU | Serial | G1 | thread overhead ↓ |
| JDK 11 (LTS) | G1 | - | |
| JDK 17 (LTS) | G1 | ZGC | |
| JDK 21 (LTS) | G1 or Gen ZGC | Shenandoah | Gen ZGC stable |

---

## 2. 가지 ②: 8대 진단 시나리오

### 2.1 핵심 질문

> "production에서 흔한 GC 사고는 무엇이고 어떻게 진단하나요?"

### 2.2 시나리오 1 — Full GC 빈발

```
증상: 분당 5+ Full GC, 평소 0~1회
       GC log: "Pause Full" 메시지 다수

진단:
1. GC log의 Full GC cause 확인:
   - "Allocation Failure" — Old 공간 부족
   - "Metadata GC Threshold" — Metaspace 압박
   - "System.gc()" — 명시적 호출 (RMI, DirectMemory 등)

2. Heap dump (jcmd <pid> GC.heap_dump):
   - Old gen 분석 — 어떤 객체가 누적?
   - Cache 누수? Connection pool? Listener?

3. JFR jdk.GarbageCollection 이벤트의 발생 분포

조치:
- Cache 크기 제한 또는 LRU eviction
- ClassLoader 누수 점검 (Chapter 02-02)
- Heap 크기 ↑ (단, container limit 내)
- G1 → ZGC (큰 Heap이면)
```

### 2.3 시나리오 2 — P99 latency spike

```
증상: 평소 P99 50ms, 1시간에 1~2회 P99 500ms+

진단:
1. JFR 시점별 이벤트:
   - jdk.GarbageCollection — STW 길었나?
   - jdk.Deoptimization — Deopt burst?
   - jdk.JavaMonitorWait — Lock 경합?
   - jdk.SafepointBegin — TTSP가 길었나?

2. GC log의 STW 시간:
   - 정상이면 GC 아님 — Chapter 03 (deopt) 또는 Chapter 05 (lock) 검토

조치 (GC 원인일 때):
- G1: -XX:MaxGCPauseMillis=100 (50ms 너무 작으면 throughput ↓)
- ZGC/Shenandoah로 마이그레이션 (sub-ms STW)
- Allocation rate 줄이기 (EA 친화 코드, object pool)
```

### 2.4 시나리오 3 — Promotion Failure

```
증상: GC log에 "promotion failed" 또는 "concurrent mode failure" (CMS)

원인: Young GC가 살아남은 객체를 Old로 옮기지 못함 — Old 공간 부족

조치:
- Heap 크기 ↑
- Young 크기 조정 (-XX:NewRatio, -Xmn) — Old 공간 확보
- G1: -XX:G1ReservePercent=20 (Old 예약 공간 ↑)
- Cache 누수 점검
```

### 2.5 시나리오 4 — G1 RSet 비대화

```
증상: G1 사용 중, Mixed GC pause 점진적 ↑

진단:
1. -Xlog:gc+phases=debug
   "Scan RS" 시간이 대부분이면 RSet 비대
2. -Xlog:gc+remset=info
   "fine->coarse transitions" 빈발

조치:
- -XX:G1HeapRegionSize=32m (region 수 ↓)
- cache 크기 제한 (cross-region ref ↓)
- ZGC 검토 (cross-gen RSet이 더 효율)
```

### 2.6 시나리오 5 — Humongous 누적

```
증상: GC log에 "Humongous Allocation" 빈도 ↑
       Old gen 사용량이 cache 크기를 초과

진단: -Xlog:gc+humongous=debug

조치:
- 큰 buffer 크기를 region 크기의 50% 미만으로
- -XX:G1HeapRegionSize=32m (region ↑ → humongous threshold ↑)
- Buffer pool 사용 (Netty PooledByteBufAllocator)
```

### 2.7 시나리오 6 — OOM 후 회복 안 됨

```
증상: OutOfMemoryError 발생 후 응답 매우 느림. 재시작해도 같은 현상.

원인: ClassLoader 누수 (Chapter 02-02) — Metaspace 영구 증가
       Heap dump 없음 — -XX:+HeapDumpOnOutOfMemoryError 꺼져 있음

조치:
1. -XX:+HeapDumpOnOutOfMemoryError -XX:HeapDumpPath=/tmp/heap.hprof
2. Heap dump를 MAT로 분석 — 누구의 누수?
3. 코드 수정 + 재배포
```

### 2.8 시나리오 7 — Container OOM-killed

```
증상: 컨테이너 OOM-killed인데 Heap dump는 정상

원인: Heap 외 영역 합이 container limit 초과
   - Metaspace
   - Code Cache
   - Direct Memory
   - Native libraries
   - Thread stacks

진단: jcmd <pid> VM.native_memory summary (NMT 활성 필요)

조치:
- container limit의 50~70%로 -Xmx
- -XX:MaxDirectMemorySize, MaxMetaspaceSize 명시
- Thread 수 제한
- (Chapter 02-05 참조)
```

### 2.9 시나리오 8 — GC 마이그레이션 (G1 → ZGC)

→ 가지 ④에서 자세히.

### 2.10 시나리오 요약 표

| # | 증상 | 진단 명령 | 조치 |
|---|---|---|---|
| 1 | Full GC 빈발 | GC log cause + heap dump | Cache 제한, Heap ↑ |
| 2 | P99 spike | JFR 시점 이벤트 | GC 튜닝 또는 ZGC |
| 3 | Promotion Failure | GC log "promotion failed" | -Xmn 조정, G1ReservePercent |
| 4 | G1 RSet 비대 | gc+phases=debug, "Scan RS" | region size ↑, cache 제한 |
| 5 | Humongous 누적 | gc+humongous=debug | buffer 크기 ↓, region size ↑ |
| 6 | OOM 후 회복 안 됨 | Heap dump + MAT | ClassLoader 누수 수정 |
| 7 | Container OOM-killed | NMT summary | -Xmx 조정, MaxDirect, Thread 수 |
| 8 | GC 마이그레이션 | canary + 메트릭 비교 | 가지 ④ 참조 |

---

## 3. 가지 ③: 도구 — GC log + JFR + MAT

### 3.1 핵심 질문

> "어떤 도구를 어떤 상황에 쓰나요?"

### 3.2 키워드 1 — GC log (모든 production 활성)

```bash
java \
  -Xlog:gc*,gc+phases=debug,gc+heap=debug:file=gc.log:time,uptime,level,tags:filesize=100M,filecount=10 \
  -XX:+HeapDumpOnOutOfMemoryError -XX:HeapDumpPath=/var/log/heap.hprof \
  -jar app.jar
```

옵션 설명:
- `file=gc.log` — 파일 출력.
- `filesize=100M` — 100MB 후 rotate.
- `filecount=10` — 10개 보관 (1GB 보존).
- `time,uptime` — 타임스탬프.
- `gc+phases=debug` — phase별 시간 (Scan RS, Object Copy 등).
- `gc+heap=debug` — heap 영역별 사용량.

→ **모든 production JVM에 활성화 권장**. CPU 비용 1% 미만.

### 3.3 키워드 2 — JFR (24/7 continuous recording)

```bash
# 단발 측정
jcmd <pid> JFR.start name=app duration=300s settings=profile filename=/tmp/app.jfr

# 지속 측정 (production)
java -XX:StartFlightRecording=name=continuous,settings=default,maxsize=500M -jar app.jar
```

**핵심 이벤트**:
- `jdk.GarbageCollection` — 각 GC 발생.
- `jdk.GCHeapSummary` — heap 사용량 추이.
- `jdk.ObjectAllocationInNewTLAB` — allocation rate.
- `jdk.Deoptimization` — JIT deopt.
- `jdk.JavaMonitorEnter/Wait` — lock 분석.
- `jdk.SafepointBegin` — TTSP.

### 3.4 키워드 3 — MAT (Eclipse Memory Analyzer)

```
용도:
   Heap dump 분석. OOM/누수 진단의 표준 도구.

워크플로우:
1. -XX:+HeapDumpOnOutOfMemoryError로 자동 dump
2. 또는 jcmd <pid> GC.heap_dump /tmp/heap.hprof
3. MAT에서 열기
4. Histogram / Dominator Tree / Path To GC Roots 분석

특히 유용:
   - ClassLoader 누수 — Dominator Tree에서 ClassLoader 인스턴스 수 확인
   - Cache 누수 — 가장 큰 객체 추적
```

### 3.5 도구 매트릭스

| 도구 | 용도 | 비용 |
|---|---|---|
| **GC log** | 모든 production. 사고 첫 분석. | < 1% |
| **JFR** | 24/7 continuous. 사후 분석. | ~1~3% |
| **JFR Mission Control** | JFR GUI 분석. | (offline) |
| **GCViewer** | GC log 시각화 (free). | (offline) |
| **GCEasy** | GC log online 분석 (commercial). | (offline) |
| **MAT** | Heap dump 분석. ClassLoader 누수 추적. | (offline) |
| **VisualVM** | Live monitoring. 개발/테스트. | (live) |
| **async-profiler** | Allocation/CPU flame graph. | low |
| **jcmd** | Live JVM 조작 (heap dump, NMT 등). | low |
| **jstack** | Thread dump (lock 분석). | low |

### 3.6 알람 설정 기준 (Prometheus + JMX)

```
# GC time 비율 (전체 시간 대비)
jvm_gc_collection_seconds_sum / time > 5%   # 5% 이상이면 경고

# Full GC frequency
rate(jvm_gc_collection_count_total{gc="Full"}[1m]) > 1   # 분당 1회+

# Allocation rate
rate(jvm_memory_allocation_bytes_total[1m]) > 1GB/s   # 비정상 폭증

# Old gen 사용량
jvm_memory_pool_used_bytes{pool="Tenured"} / jvm_memory_pool_max_bytes{pool="Tenured"} > 0.85
```

→ 모든 production에 기본 설정.

---

## 4. 가지 ④: 마이그레이션 — G1 → ZGC 절차

### 4.1 핵심 질문

> "G1에서 ZGC로 어떻게 안전하게 마이그레이션하나요?"

### 4.2 키워드 1 — 사전 점검

```
환경: JDK 21, Spring Boot, 50GB Heap, P99 latency 100ms 목표

체크:
1. JDK 21+ 사용 가능? (Generational ZGC는 JDK 21+)
2. 메트릭이 RSS 기준 (cgroup memory.current)? (pmap 함정 회피)
3. Read barrier 비용 수용 (throughput ~5% 감소)?
4. GC log 형식 변경 대비 (알람 재작성)?
5. Container limit이 RSS 기준?
```

### 4.3 키워드 2 — Canary 1대

```bash
# Canary pod에 적용
-XX:+UseZGC -XX:+ZGenerational

# 모니터링할 메트릭
- Throughput (req/s)
- P99 latency
- Footprint (RSS, not pmap)
- GC time %
- GC log: Y: / O: 빈도

# 24시간 안정 확인
```

### 4.4 키워드 3 — 단계적 확대

```
1. Canary 1대 → 24시간 모니터링
2. 안정 → 25% pod 확대
3. 24시간 안정 → 50%
4. 24시간 안정 → 100%

알람 재설정:
   - GC time % 기준 변경 (ZGC는 매우 작음, < 1%)
   - RSS 기준 (가상 메모리 알람 끄기)
   - STW pause 기준 < 5ms로
   - Full GC 알람은 그대로 (Gen ZGC는 Full GC 거의 없음)
```

### 4.5 마이그레이션 실패 시 롤백

```
실패 신호:
   - Throughput 10%+ 감소
   - Pinning 빈발 (가지 ⑤ Threading 04 참조 — VT 환경)
   - 메모리 사용량 알람 폭주 (메트릭이 가상 주소 기준)
   - Read barrier 비용 워크로드 부적합

롤백:
   - JVM 옵션 원복 (-XX:+UseG1GC)
   - 알람 원복
   - 메트릭 시스템 재확인
   - 원인 분석 후 재시도
```

---

## 5. 면접 답변 워크플로우

### 5.1 질문 → 가지 매핑

| 면접 질문 | 진입 가지 | 인접 확장 |
|---|---|---|
| "내 워크로드에 어떤 GC?" | ① 선택 매트릭스 | Heap/JDK/Latency |
| "Full GC 빈발 진단?" | ② 시나리오 1 | 도구 (MAT) |
| "P99 spike 원인?" | ② 시나리오 2 | JFR 이벤트 |
| "Container OOM-killed?" | ② 시나리오 7 | NMT |
| "어떤 도구를 써야?" | ③ 도구 | GC log + JFR + MAT |
| "G1 → ZGC 마이그?" | ④ 마이그레이션 | canary 단계 |
| "알람 설정 기준?" | ③ 알람 설정 | Prometheus 쿼리 |

### 5.2 답변 템플릿

예: "Spring Boot 50GB Heap 앱이 갑자기 분당 5 Full GC. 진단하세요."

> "GC 운영은 선택/진단/도구/마이그레이션 4축인데, 이건 진단 시나리오 1입니다 (← 루트, 가지 ②).
> 진단 순서는 키워드 3개 흐름:
> 첫째, **GC log Full cause** 확인:
>    - 'Allocation Failure' — Old 가득.
>    - 'Metadata GC' — Metaspace 가득.
>    - 'System.gc()' — 명시 호출.
> 둘째, **Heap dump + MAT** — Old에 무엇이 누적?
>    - Cache 누수? Listener 누수? ClassLoader 누수?
> 셋째, **변경 점 확인** — 최근 배포 코드? 트래픽 패턴?
> 단기 조치: JVM 재시작 (긴급), Heap 크기 ↑ (container limit 내).
> 장기 조치: 누수 코드 수정, ZGC 마이그레이션 검토 (가지 ④로 연결)."

---

## 6. 꼬리질문 트리

### Q1 [가지 ①]. GC 선택의 첫 기준은?

> Heap 크기 + Latency 목표 + JDK 버전:
> - <4GB + throughput 우선: Parallel.
> - 4~32GB + 일반: G1.
> - 32GB+ + latency 중요: ZGC.
> - 100GB+ + latency: Generational ZGC (JDK 21+).

### Q2 [가지 ②]. P99 spike 진단 첫 단계는?

> JFR로 시점 이벤트 확인:
> 1. jdk.GarbageCollection — GC pause 길었나?
> 2. jdk.Deoptimization — Deopt burst?
> 3. jdk.JavaMonitorWait — Lock 경합?
> 4. jdk.SafepointBegin — TTSP가 길었나?
> GC가 아니면 다른 chapter (deopt/threading)로.

### Q3 [가지 ②]. Container OOM-killed인데 Heap dump 정상이면?

> Heap 외 영역 합이 container limit 초과. NMT로 영역별 committed 합산.
> 의심 순서: Thread (수 × 1MB) → Metaspace (CL 누수) → Code Cache → Direct Memory → JNI native lib (NMT가 못 봄).
> 조치: Container limit의 50~70%로 -Xmx 조정.

### Q4 [가지 ③]. GC log를 production에 켜야 하나요?

> 켜야 합니다. CPU 비용 1% 미만이고 사고 시 첫 분석 자료. JFR도 24/7 continuous로 권장.
> 모든 production JVM에 표준 설정:
> ```
> -Xlog:gc*,gc+phases=debug:file=gc.log:filesize=100M,filecount=10
> -XX:+HeapDumpOnOutOfMemoryError -XX:HeapDumpPath=/var/log/heap.hprof
> ```

### Q5 [가지 ④]. ZGC 마이그레이션 후 메모리 사용량 알람 폭주?

> pmap 함정. ZGC의 Multi-mapping이 가상 주소를 3배로 보고함. RSS는 1배 (정상).
> 알람을 RSS 기준 메트릭으로 변경:
> - cgroup memory.current
> - process_resident_memory_bytes (Prometheus)
> - container_memory_working_set_bytes

### Q6 (Killer) [모든 가지]. Spring Boot 50GB Heap 앱이 갑자기 분당 5 Full GC. 진단하세요.

> 1. **GC log Full cause**:
>    - "Allocation Failure" — Old 가득.
>    - "Metadata GC" — Metaspace 가득.
>    - "System.gc()" — 명시 호출.
>
> 2. **Heap dump** + MAT — Old에 무엇이 누적?
>    - Cache 누수?
>    - Listener 누수?
>    - ClassLoader 누수?
>
> 3. **변경 점**:
>    - 최근 배포 코드 변경?
>    - 트래픽 패턴 변화?
>
> 4. **단기 조치**:
>    - JVM 재시작 (긴급).
>    - Heap 크기 ↑ (단, container limit 내).
>
> 5. **장기 조치**:
>    - 누수 코드 수정.
>    - ZGC 마이그레이션 검토 (가지 ④ 절차).

---

## 7. 학습 체크리스트

- [ ] 0장 마인드맵을 1분 이내로 그릴 수 있다 (운영 4축)
- [ ] 가지 ①: Heap 크기 / JDK 버전 / Latency 목표 3축 매트릭스를 그린다
- [ ] 가지 ②: 8대 시나리오 표를 적는다 (증상 → 진단 → 조치)
- [ ] 가지 ②: Killer 시나리오 (50GB Spring Boot Full GC 빈발)에 답한다
- [ ] 가지 ③: GC log 옵션 (Xlog, filesize, filecount, gc+phases)을 외운다
- [ ] 가지 ③: JFR 핵심 이벤트 5개 (GC, Deopt, MonitorWait, Safepoint, Allocation)를 인용한다
- [ ] 가지 ③: Prometheus 알람 4가지 (GC time %, Full GC freq, alloc rate, Old usage)를 적는다
- [ ] 가지 ④: G1 → ZGC 마이그레이션 단계 (사전점검 → canary → 25/50/100%)를 말한다
- [ ] 가지 ④: pmap 함정 + RSS 메트릭 전환을 설명한다
- [ ] 6장 꼬리질문 6개에 답한다

---

## 다음 단계

04-gc 챕터 종료. 다음:
- → [Chapter 05. Threading](../05-threading/) — JMM, Memory Barriers, Loom
- → [Chapter 10. Ops Scenarios](../10-ops-scenarios/) — 운영 시나리오 풀버전

## 참고

- **Oracle GC Tuning Guide (JDK 21)**: https://docs.oracle.com/en/java/javase/21/gctuning/
- **GCEasy**: https://gceasy.io/
- **GCViewer**: https://github.com/chewiebug/GCViewer
- **Eclipse MAT**: https://www.eclipse.org/mat/
- **Netflix GC tuning posts**: 여러 blog
- **LinkedIn Engineering — G1 tuning**: blog posts
