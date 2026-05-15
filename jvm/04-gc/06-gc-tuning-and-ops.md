# 04-06. GC Tuning + 운영 — 종합 가이드

> GC 알고리즘을 알았다고 운영자가 되는 건 아니다. **production에서 실제 사고가 났을 때** 어느 옵션을 어떻게 조정하고 어떤 메트릭으로 검증할지가 시니어의 역량.
> 본 챕터는 GC 7종을 운영 관점에서 종합 + 8가지 흔한 운영 시나리오 + 옵션 매트릭스.

---

## 🗺️ JVM 아키텍처 안에서 이 챕터의 위치

04-gc 챕터의 **운영 종합**. 01~05를 읽었다면 본 챕터로 production 대응.

---

## 📍 학습 목표

1. **GC 선택 매트릭스** — 워크로드 + Heap 크기 + JDK 버전 + latency 목표.
2. **8대 운영 시나리오** — Full GC 빈발, P99 spike, Promotion failure, RSet 비대, Humongous 누적, OOM 후 회복 안 됨, Container OOM-killed, GC 마이그레이션.
3. **GC log 분석 워크플로** — 어떤 옵션으로 로깅하고 어떻게 읽나.
4. **JFR + GCViewer + GCEasy** 도구 활용.
5. **컨테이너 환경 GC 튜닝** — cgroup 인식, Heap 크기 결정 공식.
6. **GC 마이그레이션 절차** — canary, 메트릭 비교, 단계적 도입.
7. **알람 설정 기준** — GC time %, Full GC frequency, allocation rate.
8. **운영 자동화** — heap dump 자동 수집, JFR continuous recording.

---

## 🎯 GC 선택 매트릭스

```
┌─────────────────────┬───────────────┬────────────────┬──────────────────┐
│ 환경                 │ 1st choice    │ 2nd choice     │ 비고              │
├─────────────────────┼───────────────┼────────────────┼──────────────────┤
│ Heap < 512MB, 1코어 │ Serial        │ -              │ 개발/테스트       │
│ Heap < 4GB, batch   │ Parallel      │ G1             │ throughput 우선  │
│ Heap 4~32GB, web    │ G1 (기본)     │ Shenandoah     │ 일반 case        │
│ Heap 32~128GB       │ G1 또는 Gen ZGC│ Shenandoah     │ JDK 21+면 ZGC    │
│ Heap 128GB+         │ Gen ZGC       │ -              │ ZGC 거의 필수    │
│ Latency P99 < 10ms  │ ZGC/Shenandoah│ -              │ sub-ms STW       │
│ HFT, real-time      │ ZGC           │ Shenandoah     │ 최저 STW         │
│ Container 0.5 CPU   │ Serial        │ G1             │ thread overhead↓ │
│ JDK 11 (LTS)        │ G1            │ ZGC experimental│                  │
│ JDK 17 (LTS)        │ G1            │ ZGC stable     │                  │
│ JDK 21 (LTS)        │ G1 or Gen ZGC │ Shenandoah     │ Gen ZGC stable   │
└─────────────────────┴───────────────┴────────────────┴──────────────────┘
```

---

## 🛠️ 8대 운영 시나리오

### 시나리오 1: Full GC 빈발

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
- ClassLoader 누수 (chapter 02-02) 점검
- Heap 크기 ↑ (단, container limit 안에서)
- G1 → ZGC (큰 Heap이면)
```

### 시나리오 2: P99 latency spike

```
증상: 평소 P99 50ms, 1시간에 1~2회 P99 500ms+

진단:
1. JFR 시점별 이벤트:
   - jdk.GarbageCollection — STW 길었나?
   - jdk.Deoptimization — Deopt burst?
   - 둘 다 정상이면 application 자체?

2. GC log의 STW 시간:
   - 정상이면 GC 아님 — Chapter 03 (deopt) 또는 Chapter 05 (lock) 검토

조치 (GC 원인일 때):
- G1: -XX:MaxGCPauseMillis=100 (50ms이 너무 작으면 throughput ↓)
- ZGC/Shenandoah로 마이그레이션 (sub-ms STW)
- Allocation rate 줄이기 (EA 친화 코드, object pool)
```

### 시나리오 3: Promotion Failure

```
증상: GC log에 "promotion failed" 또는 "concurrent mode failure" (CMS)

원인: Young GC가 살아남은 객체를 Old로 옮기지 못함 — Old 공간 부족

조치:
- Heap 크기 ↑
- Young 크기 조정 (-XX:NewRatio, -Xmn) — Old 공간 확보
- G1: -XX:G1ReservePercent=20 (Old 예약 공간 ↑)
- Cache 누수 점검
```

### 시나리오 4: G1 RSet 비대화

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

### 시나리오 5: Humongous 누적

```
증상: GC log에 "Humongous Allocation" 빈도 ↑
       Old gen 사용량이 cache 크기를 초과

진단: -Xlog:gc+humongous=debug

조치:
- 큰 buffer 크기를 region 크기의 50% 미만으로
- -XX:G1HeapRegionSize=32m (region ↑ → humongous threshold ↑)
- Buffer pool 사용 (Netty PooledByteBufAllocator)
```

### 시나리오 6: OOM 후 회복 안 됨

```
증상: OutOfMemoryError 발생 후 응답 매우 느림. 재시작해도 같은 현상.

원인: ClassLoader 누수 (Chapter 02-02) — Metaspace 영구 증가
       Heap dump 없음 — -XX:+HeapDumpOnOutOfMemoryError 꺼져 있음

조치:
1. -XX:+HeapDumpOnOutOfMemoryError -XX:HeapDumpPath=/tmp/heap.hprof
2. Heap dump를 MAT로 분석 — 누구의 누수?
3. 코드 수정 + 재배포
```

### 시나리오 7: Container OOM-killed

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

### 시나리오 8: GC 마이그레이션 (G1 → ZGC)

```
환경: JDK 21, Spring Boot, 50GB Heap, P99 latency 100ms 목표

절차:
1. 사전 점검:
   - JDK 21+ 사용 가능?
   - 메트릭이 RSS 기준 (cgroup memory)?
   - Read barrier 비용 수용?

2. Canary (1대):
   -XX:+UseZGC -XX:+ZGenerational
   메트릭 비교: throughput, P99, footprint, GC time, RSS

3. 24시간 안정 후 25% pod로 확대
4. 안정 후 50%, 100%

5. 알람 재설정:
   - GC time % 기준 변경 (ZGC는 매우 작음)
   - RSS 기준 (가상 메모리 알람 끄기)
   - STW pause 기준 < 5ms로
```

---

## 🔧 GC log 활성화 (모든 운영 권장)

```bash
java \
  -Xlog:gc*,gc+phases=debug,gc+heap=debug:file=gc.log:time,uptime,level,tags:filesize=100M,filecount=10 \
  -XX:+HeapDumpOnOutOfMemoryError -XX:HeapDumpPath=/var/log/heap.hprof \
  -XX:+PrintFlagsFinal \
  -jar app.jar
```

옵션:
- `file=gc.log` — 파일 출력.
- `filesize=100M` — 100MB 후 rotate.
- `filecount=10` — 10개 보관.
- `time,uptime` — 타임스탬프.
- `level` — debug/info 레벨.

→ **모든 production JVM에 활성화 권장**.

## 📊 알람 설정 기준 (Prometheus + JMX)

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

---

## 🛠️ 도구 매트릭스

| 도구 | 용도 |
|---|---|
| **GC log** | 모든 production 활성화. 사고 시 첫 분석. |
| **JFR** | 24/7 continuous recording. 사후 분석. |
| **JFR Mission Control** | JFR GUI 분석. |
| **GCViewer** | GC log 시각화 (free). |
| **GCEasy** | GC log online 분석 (commercial). |
| **MAT** | Heap dump 분석. ClassLoader 누수 추적. |
| **VisualVM** | Live monitoring. 개발/테스트. |
| **async-profiler** | Allocation flame graph. |
| **jcmd** | Live JVM 조작 (heap dump, NMT 등). |

---

## ⚔️ 꼬리질문

### Q1. GC 선택의 첫 기준은?

> Heap 크기 + Latency 목표:
> - <4GB + throughput: Parallel.
> - 4~32GB + 일반: G1.
> - 32GB+ + latency: ZGC.
> - 100GB+ + latency: Generational ZGC.

### Q2. P99 spike 진단 첫 단계?

> JFR로 시점 이벤트:
> 1. jdk.GarbageCollection — GC pause 길었나?
> 2. jdk.Deoptimization — Deopt burst?
> 3. jdk.JavaMonitorWait — Lock 경합?
> 4. jdk.SafepointBegin — TTSP (Time-To-Safepoint)?

### Q3. (Killer) Spring Boot 50GB Heap 앱이 갑자기 분당 5 Full GC. 진단하세요.

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
>    - Heap 크기 ↑ (단, container limit).
> 
> 5. **장기 조치**:
>    - 누수 코드 수정.
>    - ZGC 마이그레이션 검토.

---

## 🔗 다음 단계

04-gc 챕터 종료. 다음:
- → [Chapter 05. Threading](../05-threading/) — JMM, Memory Barriers, Loom
- → [Chapter 10. Ops Scenarios](../10-ops-scenarios/) — 운영 시나리오 풀버전

## 📚 참고

- **Oracle GC Tuning Guide (JDK 21)**: https://docs.oracle.com/en/java/javase/21/gctuning/
- **GCEasy**: https://gceasy.io/
- **GCViewer**: https://github.com/chewiebug/GCViewer
- **Eclipse MAT**: https://www.eclipse.org/mat/
- **Netflix GC tuning posts**: 여러 blog
- **LinkedIn Engineering — G1 tuning**: blog posts
