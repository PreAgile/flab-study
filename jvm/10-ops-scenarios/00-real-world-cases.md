# 10-00. 실전 JVM 장애 사례집 — 빅테크는 어떻게 다루나

> **JVM 명세를 외우는 능력**과 **prod 장애를 고치는 능력**은 다르다.
> 빅테크가 공개한 실제 사례를 8개 패턴으로 압축하면, 다음 장애가 우리 환경에 떨어졌을 때 "이건 Case N이다"라고 즉시 분류할 수 있다.
> Heap OOM, Metaspace 누수, Container OOM-killed, P99 spike — 증상은 달라도 진단 흐름은 4단(증상 → 진단도구 → 원인 → 트레이드오프)으로 동일.

---

## 이 문서의 사용법

이 문서는 **면접용 마인드맵**을 따라 선형으로 펼친 구조다. 학습 순서 = 면접 답변 순서 = 백지에 그리는 순서.

1. **0장 마인드맵을 먼저 외운다** — 루트 한 문장 + 6가지 가지 + 각 가지의 키워드 3개.
2. **1~6장을 순서대로 학습한다** — 각 장이 마인드맵의 한 가지에 정확히 대응.
3. **7장 면접 워크플로우로 검증** — 질문을 보면 어느 가지로 가야 하는지 매핑.
4. **8장 꼬리질문으로 깊이 점검**.

---

## 0. 마인드맵 — 면접 종이에 그릴 그림

### 루트 한 문장 (anchor)

> **"실전 JVM 장애는 8개 패턴으로 압축된다. 각 패턴은 증상 → 진단도구 → 원인 → 트레이드오프 4단 흐름으로 풀린다."**

이 한 문장에서 모든 답변이 출발한다. 면접관이 어떤 장애 시나리오를 던져도 8개 중 하나로 분류 → 4단 흐름으로 답변.

### 6개 가지 — 순서를 외운다

```
                  [ROOT: 8개 패턴 × 4단 흐름]
                              │
   ┌─────────┬─────────┬──────┴──────┬─────────┬─────────┐
   │         │         │             │         │         │
  ① 메모리  ② GC      ③ 컨테이너    ④ JIT     ⑤ 동시성   ⑥ 공통
   누수    pause      / 환경         Code      Loom      도구&
   (3종)   (2종)      (Case 4)      Cache     (Case 7)  원칙
   │         │         │             │         │         │
   │     ┌───┼───┐  ┌──┼──┐       ┌──┼──┐   ┌──┼──┐   ┌──┼──┐
  Heap  P99  Pre  -Xmx UCS       Code AOP  Pin  sync  jcmd  prod
  Meta  spike mature limit MAX   Cache 폭증 ning JNI   /JFR  설정
  Direct G1  Promo  Direct      Full       trace      MAT   JFR
        ZGC  tenur  Thread                            상시
```

### 가지별 핵심 키워드 (각 가지 3개씩만)

| 가지 | 키워드 1 | 키워드 2 | 키워드 3 |
|---|---|---|---|
| **① 메모리 누수** | Case 2 Heap (static/ThreadLocal) | Case 3 Metaspace (CL 누수) | Case 8 Direct (Netty ByteBuf) |
| **② GC pause** | Case 1 P99 spike (G1/ZGC) | Case 5 Premature Promotion | Tenuring / Humongous |
| **③ 컨테이너** | Case 4 OOM-killed | `-Xmx` = limit 50~70% | UseContainerSupport |
| **④ JIT / Code Cache** | Case 6 Cache Full | AOP/proxy 폭증 | ReservedCodeCacheSize |
| **⑤ 동시성 (Loom)** | Case 7 Pinning | synchronized → ReentrantLock | JDK 24 JEP 491 |
| **⑥ 공통 도구&원칙** | jcmd / JFR / MAT | 측정→단일변수→재측정 | JFR 상시 켜기 |

### 면접 답변 흐름

> 면접관이 장애 증상 제시 → 루트 문장(8개 패턴) → 어느 가지로 가는지 판단 → 그 가지의 키워드 3개 순서로 → 진단 도구로 검증 → 트레이드오프까지

---

## 1. 가지 ①: 메모리 누수 — Heap / Metaspace / Direct 3종

### 1.1 핵심 질문

> "Java 프로세스가 시간이 지나면서 메모리를 계속 먹는다. 어디서 새는지 어떻게 찾나요?"

**판단 기준**: 어느 영역이 새는가에 따라 진단 도구와 해결법이 완전히 다르다.

| 영역 | 증상 차이 | 주 진단 도구 |
|---|---|---|
| **Heap** | `OutOfMemoryError: Java heap space`, Old gen이 Full GC 후에도 안 줄어듦 | heap dump + MAT |
| **Metaspace** | `OutOfMemoryError: Metaspace`, hot deploy 환경에서 빈번 | `jcmd VM.classloader_stats` |
| **Direct Memory** | Heap은 안정인데 RSS 증가, `OutOfMemoryError: Direct buffer memory` | NMT + JMX BufferPoolMXBean |

### 1.2 키워드 1 — Case 2: Heap 누수

#### 증상

- 며칠 또는 몇 시간 운영 후 OOM.
- Heap 사용량이 톱니파 모양으로 **계단식 증가**.
- Full GC 후에도 Old gen 사용량 줄지 않음.

#### 빅테크 사례

- **우아한형제들**: 캐시 + ThreadLocal 누수 사례 (우아한기술블로그의 메모리 누수 분석 시리즈)
- **카카오**: Spring 환경의 ApplicationContext 누수 (tech.kakao.com)
- **네이버 D2**: Java Reference (WeakReference, SoftReference) 오해로 인한 누수

#### 진단 흐름

```bash
# 1. OOM 자동 heap dump 설정 (prod에서 항상 켜두기)
java -XX:+HeapDumpOnOutOfMemoryError \
     -XX:HeapDumpPath=/var/log/heap/ \
     -XX:+ExitOnOutOfMemoryError ...

# 2. 의심 시점에 수동 dump
jcmd <pid> GC.heap_dump /tmp/heap.hprof

# 3. heap 통계 빠른 확인
jcmd <pid> GC.class_histogram | head -30
# 출력에서 상위 인스턴스 수가 비정상적으로 큰 클래스 식별

# 4. MAT (Eclipse Memory Analyzer)로 분석
#    - Histogram → 가장 많은 인스턴스 클래스
#    - Dominator Tree → 누가 들고 있나
#    - Path to GC Roots → 누가 GC 못 하게 막나
#    - Leak Suspects (자동 분석)

# 5. async-profiler allocation profile (의심 단계)
asprof -e alloc -d 60 -f alloc.html <pid>
```

#### 흔한 Heap 누수 패턴

| 패턴 | 진단 단서 | 해결 |
|---|---|---|
| **static collection 무한 증가** | static Map/List 인스턴스 매우 큼 | TTL/크기 제한 + Caffeine 등 bounded cache |
| **ThreadLocal 누수** | Thread Pool 스레드들이 큰 객체 참조 | `try-finally`로 `remove()`, ThreadPoolExecutor afterExecute |
| **Listener 미해제** | EventListener 등록 후 unsubscribe 안 함 | WeakReference 또는 명시적 cleanup |
| **inner class implicit reference** | Anonymous/inner class가 outer 참조 | static class로 분리 또는 명시적 reference 끊기 |
| **String.intern() 남용** | StringTable 비대 (`-Xlog:stringtable`) | 인터닝 자제, JDK 7+ Heap pool 활용 |
| **JDBC connection / Statement 누수** | `try-with-resources` 미사용 | try-with-resources, connection pool 설정 |

#### 트레이드오프

- **`-Xmx` 증가는 임시방편**: 누수의 근본 해결이 아님 — 시간 벌기.
- **WeakReference 사용**: 메모리 압박 시 자동 회수 — 캐시에 적합, 그러나 fragile.
- **Bounded cache**: 메모리 safe, 단 hit rate 감소 가능.

### 1.3 키워드 2 — Case 3: Metaspace 누수 (ClassLoader)

#### 증상

- 운영 중 점진적 Metaspace 증가.
- 특히 **hot deploy / Spring DevTools / Tomcat reload** 환경에서 빈번.
- `jcmd VM.classloader_stats`에서 비정상적으로 많은 CL.

#### 빅테크 사례

- **네이버**: 톰캣 hot redeploy 환경에서 WebappClassLoader 누수 — D2의 ClassLoader 누수 분석
- **카카오**: Spring DevTools restart classloader 누수
- **Tomcat 공식 문서**: ClassLoader leak detection (`clearReferencesXxx` 옵션)

#### 진단 흐름

```bash
# 1. ClassLoader 통계
jcmd <pid> VM.classloader_stats
# 출력: 각 CL이 들고 있는 클래스 수, 차지 메모리

# 2. heap dump + MAT 분석
jcmd <pid> GC.heap_dump /tmp/heap.hprof

# MAT에서:
# - Histogram → "java.lang.ClassLoader" 검색
# - 옛 WebappClassLoader가 살아있는지 확인
# - "Path to GC Roots" → 누가 들고 있나
# - 흔한 범인: Thread, ThreadLocal, MBeanServer, DriverManager

# 3. -Xlog로 unload 추적
java -Xlog:class+unload,class+loader+data=debug ...

# 4. NMT로 Metaspace commit 추적
jcmd <pid> VM.native_memory baseline
# (시간 경과 후)
jcmd <pid> VM.native_memory summary.diff
```

#### 흔한 누수 원인

| 원인 | 진단 단서 | 해결 |
|---|---|---|
| **ThreadLocal 누수** | Thread Pool 재사용 + 옛 CL 객체 참조 | ServletContextListener.contextDestroyed에서 cleanup |
| **JDBC Driver 미해제** | DriverManager 안에 옛 CL의 Driver | `DriverManager.deregisterDriver()` 명시 호출 |
| **Logging cache** | log4j MDC, SLF4J marker | logging 라이브러리의 shutdown hook |
| **JMX MBean 미해제** | MBeanServer에 옛 CL의 MBean | MBean unregister |
| **Spring ApplicationContext** | context close 미호출 | `context.close()` 명시 |

#### 트레이드오프

- **`-XX:MaxMetaspaceSize` 설정**: 무한 증가 차단, 단 적정값 측정 필요.
- **WebApp 격리 강화**: WebappClassLoader 각자 → 메모리 사용량 증가.
- **Hot deploy 포기**: 가장 안전, 단 개발 편의 손실.

### 1.4 키워드 3 — Case 8: Direct Memory 누수 (Off-Heap)

#### 증상

- Heap은 안정적인데 RSS 계속 증가.
- 결국 컨테이너 OOM-killed.
- `OutOfMemoryError: Direct buffer memory` (`-XX:MaxDirectMemorySize` 초과 시).

#### 빅테크 사례

- **Netflix**: Spinnaker / Hollow의 DirectBuffer pool 관리
- **Netty 기반 시스템 (라인, 카카오)**: ByteBuf leak detection
- **OpenJDK 공식**: Cleaner 동작 변경 (JDK 9: sun.misc.Cleaner → java.lang.ref.Cleaner)

#### 진단 흐름

```bash
# 1. Direct Memory 사용량
jcmd <pid> VM.native_memory summary | grep -i "internal\|direct"
# 또는 JMX BufferPoolMXBean
# - "direct" pool
# - "mapped" pool

# 2. JFR allocation 추적
jcmd <pid> JFR.start ...
# 이벤트:
# - jdk.DirectMemoryAllocation (있다면)
# - jdk.NativeMemoryAllocation

# 3. Netty 사용 시 leak detection
java -Dio.netty.leakDetection.level=PARANOID ...
# Netty가 ByteBuf 누수를 자동 추적
```

#### 일반적 원인

| 원인 | 해결 |
|---|---|
| **`ByteBuffer.allocateDirect()` 후 미해제** | `Cleaner` 자동 회수 대기 또는 명시적 `((DirectBuffer)buf).cleaner().clean()` |
| **Netty `ByteBuf` 미해제** | `referenceCount` 관리, `ReferenceCountUtil.release()` |
| **MappedByteBuffer + 큰 파일** | mapping 해제는 GC 의존 — `Cleaner` 사용 |
| **DirectBuffer pool 부족** | pool 크기 조정 (Netty의 `PooledByteBufAllocator`) |

#### 트레이드오프

- **DirectBuffer 사용**: zero-copy I/O 가능, 단 관리 부담.
- **Heap ByteBuffer**: GC가 알아서 관리, 단 I/O 시 복사 발생.
- **Netty pool**: 재사용 효율, 단 max size 설정 필요.

---

## 2. 가지 ②: GC pause — P99 spike와 Premature Promotion

### 2.1 핵심 질문

> "GC 때문에 latency가 튀고 처리량이 떨어진다. 어떻게 진단하고 안정화하나요?"

**판단 기준**: pause가 **드물게 길게 튀는지** vs **자주 발생하며 Full GC를 유발하는지**.

### 2.2 키워드 1 — Case 1: P99 latency spike (GC pause)

#### 증상

- 평소 P99 = 50ms, 갑자기 1~2초 spike.
- 일정 간격(예: 30분~1시간)으로 반복.
- CPU/메모리 그래프에는 큰 변화 없음.

#### 빅테크 사례

- **Netflix**: ZGC migration 전, G1로 운영하던 시기 P99 spike → ZGC 전환으로 sub-ms pause 달성. (Netflix Tech Blog의 ZGC 글)
- **LinkedIn**: Kafka broker JVM에서 GC pause가 consumer rebalance를 트리거 → "Garbage Collection Optimization for High-Throughput Apache Kafka"
- **토스**: 금융 거래의 P99.9 목표를 위해 ZGC 도입 (공개 발표 자료)
- **우아한형제들**: GC pause로 인한 주문 처리 지연 사례 → JFR 분석

#### 진단 흐름

```bash
# 1. GC log 확인
java -Xlog:gc*=info:file=gc.log:time,uptime,level,tags ...
# 또는 운영 중인 JVM에 dynamic attach
jcmd <pid> VM.log what="gc*=info" output="file=/tmp/gc.log"

# 2. JFR로 GC 이벤트 + safepoint 추적
jcmd <pid> JFR.start name=spike duration=120s filename=/tmp/spike.jfr

# 분석할 이벤트:
# - jdk.GarbageCollection: STW 길이
# - jdk.GCPhasePause: 단계별 분해
# - jdk.SafepointBegin / End: TTSP 포함 총 시간
# - jdk.G1HeapRegionTypeChange: Humongous 발생

# 3. GCViewer / GCeasy.io로 시각화
# 또는 JDK Mission Control (JMC)

# 4. async-profiler로 spike 시점 stack 캡처
asprof -e wall -d 30 -f spike.html <pid>
```

#### 가능한 원인 & 해결

| 가능 원인 | 진단 단서 | 해결 |
|---|---|---|
| **G1 Mixed GC RSet scan 비대** | GC log "RSet Scan" 시간 길음 | `-XX:G1HeapRegionSize` 조정, 객체 그래프 재설계 |
| **Humongous Object** | `-Xlog:gc+humongous` 빈번 출력 | 큰 배열을 startup에 미리 할당 + 재사용 |
| **Old gen 압박 → Full GC** | Old usage > 70%, Full GC 시간 김 | `-Xmx` 증가, `-XX:InitiatingHeapOccupancyPercent` 조정 |
| **TTSP (Time To Safepoint)** | JFR `jdk.SafepointBegin` 길이 큼 | Counted loop 문제 — JDK 10+ Thread-Local Handshakes |
| **JIT 컴파일 대기** | `jdk.CompilerTask` 이벤트 길이 큼 | AppCDS로 warmup 가속, `-XX:CICompilerCount` 늘림 |
| **시스템 (cgroup, swap)** | CPU steal, swap activity | 호스트 진단 (vmstat, mpstat) |

#### 트레이드오프

- **ZGC 전환**: P99 → 1ms 미만 가능, 단 메모리 ~10% 추가 사용, throughput 5~10% 감소 가능.
- **`-XX:MaxGCPauseMillis=50`**: 짧은 pause 목표 → GC 빈도 증가 → 처리량 감소.
- **Heap 키우기**: Full GC 빈도 ↓, 단 한 번 GC가 길어짐 + 컨테이너 비용 ↑.

### 2.3 키워드 2 — Case 5: Premature Promotion

#### 증상

- Minor GC 자주 + 매번 Old gen 사용량 증가.
- Full GC가 1~5분 간격으로 발생.
- 처리량은 살아있지만 P99 spike + CPU 70%+ 항상.

#### 빅테크 사례

- **LinkedIn**: Kafka broker premature promotion → Survivor 부족
- **네이버 D2**: G1 GC 튜닝 사례 + Tenuring Threshold 분석
- **Cliff Click** 블로그: 일반화된 premature promotion 패턴

#### 진단 흐름

```bash
# 1. GC log + Tenuring Distribution
java -Xlog:gc*=info,gc+age=trace:file=gc.log ...
# 또는
java -XX:+PrintTenuringDistribution ... (옛 옵션)

# 2. JFR로 GC 흐름 분석
jcmd <pid> JFR.start filename=gc.jfr duration=300s
# 이벤트:
# - jdk.GarbageCollection (전체 GC)
# - jdk.GCSurvivorAge (age별 분포)
# - jdk.PromoteObjectInNewPLAB
# - jdk.PromoteObjectOutsidePLAB

# 3. GCViewer로 시각화
# 핵심 그래프: Old gen 추세, promotion rate
```

#### 일반적 원인

| 원인 | 진단 | 해결 |
|---|---|---|
| **Survivor 너무 작음** | Survivor 즉시 가득 | `-XX:SurvivorRatio` 줄임 (Survivor 키움) |
| **MaxTenuringThreshold 너무 작음** | 객체가 일찍 promote | `-XX:MaxTenuringThreshold=15` (기본) 확인 |
| **객체 크기 큼 (Humongous)** | `-Xlog:gc+humongous` 빈번 | 큰 배열 startup 할당 + pool |
| **Young gen 부족** | Minor GC 매우 자주 | `-XX:NewRatio` 줄임 (Young 키움) |
| **객체 수명 패턴 (중기 객체 많음)** | 워크로드 분석 필요 | 캐시 디자인 재검토 |

#### 트레이드오프

- **Young gen 키우기**: Minor GC 빈도 ↓, 단 Minor GC 시간 ↑.
- **Survivor 키우기**: promotion 지연, 단 Eden 줄어듦.
- **G1 → ZGC 전환**: generation 신경 안 써도 됨 (JDK 21 generational ZGC), 단 메모리 사용량 ↑.

### 2.4 키워드 3 — Tenuring / Humongous의 본질

```
Eden → Survivor 0/1 (age++ 반복) → Old gen (promote)
           │
           ▼
   age >= MaxTenuringThreshold (보통 15)
   또는 Survivor가 가득 차서 못 들어가면 → 강제 promote
   
   ↑ 강제 promote가 잦으면 "premature" — 짧은 생명 객체가 Old로 가서
     Old gen 압박 → Full GC 빈발

Humongous Object (G1):
   객체 크기 ≥ HeapRegion 크기의 50%
   → Eden 거치지 않고 바로 Old의 H 영역으로 할당
   → 큰 byte[] (1~16MB)가 빈번하면 Old gen 직접 압박
```

---

## 3. 가지 ③: 컨테이너 / 환경 — OOM-killed

### 3.1 핵심 질문

> "JVM 내부 OOM 에러는 없는데 컨테이너가 OOM-killed로 죽는다. 원인은?"

**판단 기준**: cgroup `memory.max`를 RSS가 초과한 순간. JVM 안에서 보이지 않는 외부 사망.

### 3.2 키워드 1 — Case 4: Container OOM-killed

#### 증상

- 컨테이너가 갑자기 종료 (`docker logs`에 OOMKilled).
- 호스트 메모리는 여유 있음.
- JVM 내부 OOM 에러는 없음.

#### 빅테크 사례

- **쿠팡**: 컨테이너 환경 Spring Boot의 메모리 limit과 `-Xmx` 미스매치 — Coupang Engineering Medium
- **Netflix**: Spinnaker JVM 컨테이너 환경 튜닝
- **OpenJDK JEP 248**: 컨테이너 인식 (`-XX:+UseContainerSupport`)

#### 진단 흐름

```bash
# 1. 컨테이너 OOM 확인
docker inspect <container> | grep -i OOMKilled
# 또는 k8s
kubectl describe pod <pod> | grep -i killed

# 2. 그 시점의 메모리 상태
# - cgroup memory.current vs memory.max
# - Heap (jstat)
# - Direct Memory (NMT)
# - Metaspace
# - Thread Stack × N

# 3. NMT 활성화 (재배포)
java -XX:NativeMemoryTracking=summary ...
jcmd <pid> VM.native_memory summary

# 4. JVM 옵션 확인
jcmd <pid> VM.flags | grep -E "UseContainer|MaxRAMPercentage|Xmx"
```

#### 일반적 원인

| 원인 | 진단 | 해결 |
|---|---|---|
| **`-Xmx`가 limit과 같거나 크게 설정** | Heap + 나머지 영역 합이 limit 초과 | `-Xmx` = limit의 50~70% |
| **Direct Memory 누수** | NMT의 Internal/Other 영역 비대 | DirectBuffer pool 사용, Netty 등 |
| **Native library 누수** | RSS는 큰데 NMT 영역 합과 차이 | JNI 코드, malloc 누수 (jemalloc + jeprof) |
| **Thread 폭증** | Thread Stack × N이 큼 | Thread Pool 크기 제한, Virtual Thread |
| **JDK 8 + 컨테이너** | UseContainerSupport 부재 | JDK 11+ 또는 옵션 명시 |

### 3.3 키워드 2 — `-Xmx` = limit의 50~70% 공식

```
Container memory.max = 2GB (예시)
            │
            ├── Java Heap (-Xmx) ........ 1.0~1.4 GB  ← 50~70%
            ├── Metaspace .............. 200~400 MB
            ├── Code Cache ............. 240 MB (reserved)
            ├── Thread Stack × N ....... thread 수 × 1MB
            ├── Direct Memory .......... NIO 사용량
            ├── GC bookkeeping ......... Heap의 약 1.5%
            └── Internal ............... 100~200 MB
                                        ─────────────
                                        합 ≤ 2GB

★ -Xmx만 보면 1GB 남는 것 같지만 다른 영역이 limit을 채워서 OOM-killed
```

### 3.4 키워드 3 — UseContainerSupport (JEP 248)

#### 권장 설정 (JDK 17+ 컨테이너)

```bash
java -XX:+UseContainerSupport \
     -XX:MaxRAMPercentage=70 \
     -XX:InitialRAMPercentage=70 \
     -XX:+ExitOnOutOfMemoryError \
     -XX:+HeapDumpOnOutOfMemoryError \
     -XX:HeapDumpPath=/var/log/heap/ \
     -XX:NativeMemoryTracking=summary \
     -jar app.jar
```

- **JDK 8u191+**: `UseContainerSupport` 기본 on.
- **JDK 10+**: cgroup v1 인식.
- **JDK 15+**: cgroup v2 인식.
- **JDK 8 이전**: 호스트 메모리를 그대로 봄 → `-Xmx` 명시 안 하면 폭주.

#### 트레이드오프

- **`-Xmx` 작게**: 컨테이너 안전, 단 GC 빈번.
- **container limit 크게**: 안전성 ↑, 클라우드 비용 ↑.
- **여러 작은 컨테이너 vs 큰 컨테이너**: density vs efficiency.

---

## 4. 가지 ④: JIT / Code Cache — Case 6

### 4.1 핵심 질문

> "운영 며칠 후 latency가 점진적으로 5~10배 증가했다. CPU도 올라간다. 원인은?"

### 4.2 키워드 1 — Code Cache Full

#### 증상

- 운영 며칠 후 latency 점진적 증가 (5~10x).
- CPU 사용량 증가 (JIT 코드 대신 인터프리터).
- 로그에 `CodeCache is full. Compiler has been disabled.` 경고.

#### 빅테크 사례

- **Spring Boot 대규모 앱**: AOP + dynamic proxy 빈번 — Code Cache 비대
- **JRebel + Spring DevTools**: hot reload로 인한 Code Cache 누수
- **Netflix**: Hollow 데이터 처리 시스템의 JIT optimization

#### 진단 흐름

```bash
# 1. Code Cache 상태 확인
jcmd <pid> Compiler.codecache
# 출력: 각 segment (non-profiled / profiled / non-method)의 used/free

# 2. Code Cache full 경고 + 컴파일 통계
java -XX:+PrintCodeCache \
     -XX:+UnlockDiagnosticVMOptions \
     -XX:+PrintCompilation ...

# 3. JFR `jdk.CodeCacheStatistics` 이벤트 추적
jcmd <pid> JFR.start filename=cc.jfr duration=300s

# 4. JMX MemoryPoolMXBean
# "CodeHeap 'non-profiled nmethods'" 등 모니터링
```

### 4.3 키워드 2 — AOP / dynamic proxy 폭증

| 원인 | 진단 | 해결 |
|---|---|---|
| **`-XX:ReservedCodeCacheSize` 너무 작음** | 240MB 기본값으로 한계 | `-XX:ReservedCodeCacheSize=512m` |
| **AOP / dynamic proxy 폭증** | Spring AOP 빈 많음 | proxy 제한, JIT 친화적 코드 |
| **Class redefinition (JRebel/JVMTI)** | dev에서만 — prod 영향 X | dev 환경에서만 hot reload |
| **`-XX:-UseCodeCacheFlushing`** | 기본 on, 옛 옵션이면 확인 | 기본값 유지 |

### 4.4 키워드 3 — 트레이드오프

- **Code Cache 키우기**: footprint 증가.
- **JIT 끄기 (`-Xint`)**: 안전하지만 5~10배 느림 (테스트용만).
- **GraalVM Native Image**: JIT 자체 없음 (AOT) — 콜드스타트 ms.

---

## 5. 가지 ⑤: 동시성 (Loom) — Case 7 Virtual Thread Pinning

### 5.1 핵심 질문

> "JDK 21 Virtual Thread 도입했는데 일부 워크로드 성능이 오히려 떨어졌다. 왜?"

### 5.2 키워드 1 — Pinning 증상

- JDK 21+ Virtual Thread 도입 후 일부 워크로드 성능 저하.
- carrier thread 부족 (`-Djdk.virtualThreadScheduler.parallelism` 임계).
- 일부 요청에서 P99 spike.

#### 빅테크 사례

- **OpenJDK Project Loom**: 공식 사례 (JEP 444)
- **Spring Framework 6.1+**: Virtual Thread 지원과 함께 pinning 진단 가이드
- **JDK 24 JEP 491**: synchronized pinning 해결 (Per Liden 발표)

#### 진단 흐름

```bash
# 1. pinning 추적
java -Djdk.tracePinnedThreads=full ...
# 또는 short:
java -Djdk.tracePinnedThreads=short ...

# 2. JFR에서 Virtual Thread 이벤트
jcmd <pid> JFR.start ...
# 이벤트:
# - jdk.VirtualThreadStart / End
# - jdk.VirtualThreadPinned ★
# - jdk.VirtualThreadSubmitFailed

# 3. jstack으로 carrier vs virtual 구분 확인
jstack <pid> | grep -A 5 "carrier"
```

### 5.3 키워드 2 — synchronized → ReentrantLock

| 원인 | 해결 |
|---|---|
| **synchronized 블록 안에서 blocking** (JDK 21~23) | `ReentrantLock`으로 교체, 또는 JDK 24+ |
| **native 메서드 안에서 blocking** (JNI) | 라이브러리 업데이트, async 변형 사용 |
| **`Object.wait()` 안에서** (JDK 21~23) | `Condition.await()`으로 교체 |

### 5.4 키워드 3 — JDK 24 JEP 491

- JEP 491: Synchronize Virtual Threads without Pinning (JDK 24+ 예정).
- synchronized로 인한 pinning이 사라지므로 코드 리팩토링 부담 감소.
- JNI native call로 인한 pinning은 여전히 남음.

#### 트레이드오프

- **Virtual Thread 100% 채택**: 100만+ 동시성 가능, 단 pinning 검토 필수.
- **Platform Thread 유지**: 단순, 검증된 모델, 단 스케일 제한.
- **혼합**: I/O는 Virtual, CPU 집중은 Platform.

---

## 6. 가지 ⑥: 공통 도구 & 운영 원칙

### 6.1 핵심 질문

> "빅테크는 prod JVM에 어떤 도구를 상시 켜두고, 어떤 옵션 set으로 운영하나요?"

### 6.2 키워드 1 — 진단 도구 스택

```
필수: jcmd + jstat + jstack + JFR + GC log
보조: async-profiler + MAT + GCViewer / GCeasy.io
고급: NMT + JITWatch + perf
```

| 도구 | 용도 |
|---|---|
| **jcmd** | heap dump, NMT, GC trigger, thread dump — 만능 |
| **jstat** | GC 통계 실시간 (`jstat -gc <pid> 1s`) |
| **jstack** | 스레드 dump, 데드락 자동 감지 |
| **JFR** | 상시 켜두는 저오버헤드 프로파일러 (Flight Recorder) |
| **MAT** | heap dump 분석 — Path to GC Roots, Leak Suspects |
| **async-profiler** | wall/cpu/alloc profile, FlameGraph |
| **NMT** | Native Memory Tracking — Heap 외 영역 진단 |

### 6.3 키워드 2 — 빅테크 prod 설정

```bash
# 메모리
-XX:+UseContainerSupport
-XX:MaxRAMPercentage=70
-XX:+ExitOnOutOfMemoryError
-XX:+HeapDumpOnOutOfMemoryError
-XX:HeapDumpPath=/var/log/heap/

# 진단
-XX:NativeMemoryTracking=summary
-Xlog:gc*=info,gc+heap=debug:file=gc.log:time,uptime,tags
-XX:+UnlockDiagnosticVMOptions
-XX:+LogCompilation  # 필요 시

# JFR 상시 (낮은 오버헤드)
-XX:StartFlightRecording=settings=profile,maxsize=500M,filename=/var/log/jfr/app.jfr,dumponexit=true

# GC 선택
-XX:+UseG1GC  # 또는 -XX:+UseZGC for low latency
-XX:MaxGCPauseMillis=200
```

### 6.4 키워드 3 — 운영 원칙 5개

- **측정 없이 튜닝 없다** (Aleksey Shipilev): 모든 옵션 변경 전에 기준선 측정.
- **단일 변수 변경**: 한 번에 옵션 하나만 변경 + 측정.
- **JFR 상시 켜기**: prod에서도 1~3% 오버헤드, 사고 후 조사에 결정적.
- **컨테이너 limit과 `-Xmx` 명시적 매핑**: 자동 계산 의존 X.
- **autoscaling 트리거를 GC 메트릭과 연결**: P99이 SLO 초과 시 scale out.

---

## 7. 면접 답변 워크플로우

### 7.1 질문 → 가지 매핑

| 면접 질문 / 증상 | 진입 가지 | 인접 확장 |
|---|---|---|
| "Heap이 시간 지나면서 새는 것 같다" | ① 메모리 누수 (Case 2) | ② Premature Promotion |
| "Tomcat에서 Metaspace OOM이 났다" | ① 메모리 누수 (Case 3) | ⑥ jcmd VM.classloader_stats |
| "Netty 서버에서 RSS만 계속 큰다" | ① 메모리 누수 (Case 8) | ③ Container OOM-killed |
| "P99 latency가 갑자기 튄다" | ② GC pause (Case 1) | ⑥ JFR 상시 |
| "Full GC가 매분 발생한다" | ② Premature Promotion (Case 5) | Survivor/Tenuring 분석 |
| "컨테이너가 OOMKilled되는데 Heap dump 정상" | ③ 컨테이너 (Case 4) | ① Direct, Native |
| "운영 며칠 후 latency가 5배" | ④ Code Cache (Case 6) | jcmd Compiler.codecache |
| "Virtual Thread 도입했는데 느려졌다" | ⑤ Pinning (Case 7) | synchronized → ReentrantLock |
| "빅테크는 prod에 뭘 켜두나" | ⑥ 공통 도구&원칙 | JFR 상시, NMT |

### 7.2 답변 템플릿 (4단 흐름)

> **루트 문장(8개 패턴) → 어느 패턴인지 분류 → 진단도구로 확인 → 원인 매트릭스 → 트레이드오프**

예: "컨테이너가 OOMKilled되는데 JVM 안에는 OOM 에러가 없다"

> "실전 JVM 장애는 8개 패턴으로 압축되는데, 이 증상은 **Case 4 Container OOM-killed**입니다. (← 패턴 분류)
> 진단 흐름은 4단입니다.
> **1단 증상 확인**: `docker inspect`나 `kubectl describe`로 OOMKilled 확인.
> **2단 진단 도구**: NMT를 켜서 `jcmd VM.native_memory summary`로 Heap/Metaspace/Thread/Direct/Internal 합계를 봅니다.
> **3단 원인**: 가장 흔한 건 `-Xmx`가 limit과 너무 가까워서 다른 영역(Thread × N, Direct, Metaspace)이 limit을 채운 경우입니다.
> **4단 트레이드오프**: `-Xmx`를 limit의 50~70%로 잡으면 안전하지만 GC가 자주 돕니다. `UseContainerSupport`를 켜야 cgroup을 인식합니다."

→ 면접관이 "Direct Memory가 의심된다" 하면 **가지 ①의 Case 8**로 자연스럽게 분기.

---

## 8. 꼬리질문 트리 (가지별)

### Q1 [가지 ①]. Heap 누수와 Metaspace 누수를 어떻게 구분하나요?

> 에러 메시지(`Java heap space` vs `Metaspace`)로 1차 구분. 진단 도구도 다름: Heap은 heap dump + MAT, Metaspace는 `jcmd VM.classloader_stats`로 살아있는 CL 수. 누수 원인도 다름: Heap은 static collection/ThreadLocal, Metaspace는 hot deploy 환경의 옛 WebappClassLoader 잔존.

**🪝 Q1-1: MAT에서 Path to GC Roots를 보는 이유는?**
> GC가 회수하지 못하는 객체는 GC Root(static 필드, Thread stack, JNI ref 등)에서 도달 가능한 경로가 있다는 뜻. Path를 따라가면 "누가 이 객체를 들고 있는가"가 나옴. 흔한 범인: ThreadLocal, static Map, ApplicationContext.

**🪝🪝 Q1-1-1: ThreadLocal 누수가 왜 Thread Pool에서 특히 위험한가?**
> Thread Pool은 스레드를 재사용하므로 ThreadLocal이 stale 상태로 다음 요청에 잔존. `try-finally`로 `remove()` 호출하거나 ThreadPoolExecutor의 `afterExecute`에서 cleanup.

### Q2 [가지 ②]. P99 spike와 Premature Promotion의 차이는?

> P99 spike는 **드물게 길게 튀는 pause**(Full GC, RSet scan, Humongous). Premature Promotion은 **자주 발생하는 Minor GC + 매번 Old gen 증가** → 결국 Full GC 빈발. 진단: GC log의 pause 분포 vs Old gen 추세 그래프.

**🪝 Q2-1: G1에서 Humongous Object가 왜 위험한가?**
> Region 크기의 50% 이상 객체는 Eden을 거치지 않고 바로 Old의 H 영역으로 할당. Young 세대 가설을 우회하므로 단명 객체조차 Old를 압박. 큰 byte[]가 빈번하면 Full GC 트리거.

### Q3 [가지 ②]. ZGC로 전환하면 모든 latency 문제가 해결되나요?

> 아님. ZGC는 sub-ms pause를 약속하지만 throughput은 G1 대비 5~10% 감소, 메모리 ~10% 추가 사용. CPU bound 워크로드에는 G1이 더 나을 수 있음. 또한 P99 spike의 원인이 GC가 아닌 JIT 컴파일이나 TTSP라면 ZGC로도 안 풀림.

### Q4 [가지 ③]. `-Xmx` = container limit × 70%가 공식인 이유는?

> JVM 메모리는 Heap만이 아님. Metaspace, Code Cache(240MB), Thread Stack × N, Direct Memory, GC bookkeeping(Heap의 1.5%), Internal까지 합쳐야 RSS. 이 모두가 limit 안에 들어가야 하므로 Heap은 50~70%로 제한. NMT로 실측해서 더 정확히 조정 가능.

**🪝 Q4-1: JDK 8u191 이전 컨테이너에서 무슨 일이 있었나?**
> JVM이 호스트 메모리를 그대로 봐서 `-Xmx`가 컨테이너 limit을 무시. 컨테이너 limit 1GB여도 JVM이 16GB 호스트 보고 `-Xmx`를 자동 계산 → 즉시 OOM-killed. JEP 248로 `UseContainerSupport` 도입.

### Q5 [가지 ④]. Code Cache가 가득 차면 어떻게 되나요?

> JIT 컴파일이 멈추고 새 메서드는 인터프리터로 실행 → 5~10배 느려짐. 이미 컴파일된 코드는 동작하지만 새 hot code path가 컴파일 못 됨. 로그에 `CodeCache is full. Compiler has been disabled.` 경고. 해결: `-XX:ReservedCodeCacheSize=512m`로 확장.

### Q6 [가지 ⑤]. Virtual Thread Pinning이 왜 위험한가?

> Pinning은 vthread가 carrier thread에 묶여 freeze 불가. blocking 호출 시 carrier도 같이 block → 다른 vthread 실행 못 함 → 처리량 저하. 트리거: synchronized (JDK 21~23), JNI. 해결: ReentrantLock 사용, 또는 JDK 24+의 JEP 491 도입.

**🪝 Q6-1: Pinning 진단은 어떻게?**
> `-Djdk.tracePinnedThreads=full` 옵션을 켜면 pinning 발생 시 stack trace 출력. 또는 JFR `jdk.VirtualThreadPinned` 이벤트. 출력에 `<== monitors:1` 같은 표식이 보이면 pinning.

### Q7 (Killer) [가지 ⑥]. 빅테크가 prod에서 항상 켜두는 설정은?

> 5가지 핵심:
> 1. **컨테이너**: `UseContainerSupport`, `MaxRAMPercentage=70`
> 2. **OOM 대응**: `HeapDumpOnOutOfMemoryError`, `HeapDumpPath`, `ExitOnOutOfMemoryError`
> 3. **진단**: `NativeMemoryTracking=summary`, `-Xlog:gc*=info`
> 4. **JFR 상시**: `StartFlightRecording=settings=profile,maxsize=500M,dumponexit=true` — 1~3% 오버헤드로 사고 조사 결정적
> 5. **GC**: `UseG1GC` 또는 `UseZGC` (latency target에 따라)

**🪝 Q7-1: JFR 상시 켜기의 장단점은?**
> 장점: prod에서 사고 발생 시 직전 N분의 GC/JIT/Thread/I/O 데이터 확보. 사후 reproduction 불필요. 단점: 1~3% CPU 오버헤드, 디스크 공간 사용. `maxsize=500M`으로 ring buffer 제한.

### Q8 [가지 ⑥]. "측정 없이 튜닝 없다"가 무슨 뜻인가요?

> JVM 옵션 변경 시 항상 기준선 측정 → 한 번에 한 옵션만 변경 → 재측정. 여러 옵션 동시 변경 시 어느 게 효과/역효과인지 분리 불가. Aleksey Shipilev가 강조하는 원칙. 측정 지표: P50/P99, throughput, GC time/freq, RSS.

---

## 9. 학습 체크리스트

면접 전 백지에서 다음을 다 해낼 수 있어야 마스터:

- [ ] 0장 마인드맵을 종이에 1분 이내로 그릴 수 있다 (루트 + 6가지 + 각 키워드 3개)
- [ ] 8개 Case의 증상을 듣자마자 어느 가지인지 분류한다
- [ ] 가지 ① 메모리 누수: Heap/Metaspace/Direct 3종의 진단 도구 차이를 말한다
- [ ] 가지 ② GC: P99 spike와 Premature Promotion의 증상/원인 차이를 그린다
- [ ] 가지 ③ 컨테이너: `-Xmx` = limit × 50~70% 공식과 영역 분포를 설명한다
- [ ] 가지 ④ Code Cache Full의 증상과 해결을 말한다
- [ ] 가지 ⑤ Virtual Thread Pinning의 트리거 3가지를 말한다
- [ ] 가지 ⑥ 빅테크 prod 설정 5종을 백지에서 적는다
- [ ] 4단 흐름(증상 → 진단도구 → 원인 → 트레이드오프)을 임의의 Case로 시연한다
- [ ] 8장 꼬리질문 8개에 막힘없이 답한다

---

## 10. 다음 단계 (이 챕터의 sub-chapter)

본 챕터의 8대 패턴을 각각 자세히 다루는 별도 sub-chapter는 추후 작성:
- `01-p99-spike-diagnosis.md` — Case 1 풀버전 + Mermaid timeline
- `02-heap-oom-with-mat.md` — Case 2 풀버전 + MAT 실습
- `03-metaspace-leak-tomcat.md` — Case 3 풀버전 + Tomcat 케이스
- `04-container-oom-killed.md` — Case 4 풀버전 + Kubernetes 케이스
- `05-premature-promotion.md` — Case 5 풀버전 + tenuring 분석
- `06-code-cache-full.md` — Case 6 풀버전
- `07-vthread-pinning.md` — Case 7 풀버전 + Loom 가이드
- `08-direct-memory-leak.md` — Case 8 풀버전 + Netty 사례

---

## 참고 — 빅테크 기술 블로그 출처

### 국내 빅테크

| 회사 | 블로그 / 채널 | 주요 JVM 콘텐츠 |
|---|---|---|
| **네이버** | [D2](https://d2.naver.com) | "Java Reference와 GC", "JVM Internal" 시리즈, G1 톺아보기, GC 알고리즘 |
| **카카오** | [tech.kakao.com](https://tech.kakao.com) | JVM 튜닝, Spring Boot 성능, 메모리 누수 분석 |
| **라인** | [engineering.linecorp.com](https://engineering.linecorp.com) | Kafka + JVM GC, JVM 모니터링, Verda(자체 클라우드) JVM |
| **쿠팡** | [coupang-engineering on Medium](https://medium.com/coupang-engineering) | 대규모 Spring Boot, JVM tuning, GC 최적화 |
| **배민 / 우아한형제들** | [우아한기술블로그](https://techblog.woowahan.com) | Spring Boot + JVM, 메모리 누수, JFR/JMX 활용 |
| **당근** | [team blog (Medium)](https://medium.com/daangn) | Kotlin/Java 백엔드, SRE, GC 튜닝 |
| **토스** | [toss.tech](https://toss.tech) | 결제 시스템 안정성, ZGC, 모니터링 |
| **야놀자** | [yanolja tech](https://yanolja.dev) | 마이크로서비스, JVM 운영 |
| **무신사** | [musinsa tech](https://medium.com/musinsa-tech) | Spring Boot 성능, JVM |
| **컬리** | [helloworld.kurly.com](https://helloworld.kurly.com) | 백엔드 성능, JVM |
| **NHN** | [meetup.toast.com / NHN Cloud](https://meetup.nhncloud.com) | JVM 튜닝, GC |
| **삼성 SDS / 삼성리서치** | 다수 | Java 백엔드 일반 |

### 해외 빅테크

| 회사 | 블로그 | 주요 JVM 콘텐츠 |
|---|---|---|
| **Netflix** | [netflixtechblog.com](https://netflixtechblog.com) | Hollow, "Saving Memory on Netflix Studio", ZGC migration |
| **LinkedIn** | [engineering.linkedin.com](https://engineering.linkedin.com) | Kafka GC 이슈, "GC Optimization for High-Throughput..." |
| **Twitter (X)** | engineering blog | Finagle, Mesos JVM, JIT warmup |
| **Spotify** | [engineering.atspotify.com](https://engineering.atspotify.com) | Backend Java, GC |
| **Uber** | [eng.uber.com](https://eng.uber.com) | JVM in Mesos, ZGC migration |
| **Slack** | [slack.engineering](https://slack.engineering) | Java backend at scale |
| **Airbnb** | [medium.com/airbnb-engineering](https://medium.com/airbnb-engineering) | JVM performance |
| **Pinterest** | engineering blog | Memcache + JVM, GC |
| **Square / Block** | [developer.squareup.com](https://developer.squareup.com) | JVM monitoring |

### 권위 있는 개인 블로그 / 컨퍼런스

- **Cliff Click** (HotSpot C2 창시자) — [cliffc.org/blog](https://www.cliffc.org/blog)
- **Aleksey Shipilev** (RedHat, JMH 저자) — [shipilev.net](https://shipilev.net)
- **Gil Tene** (Azul Systems, C4 GC) — Azul 블로그
- **Per Liden** (ZGC 리드) — OpenJDK
- **Mark Stoodley** (OpenJ9) — IBM
- **Sangmin Park** (네이버 D2)
- **JavaOne / Devoxx / QCon / KubeCon** YouTube 채널

### OpenJDK 공식

- JEP 248: Make G1 the Default GC
- JEP 333: ZGC
- JEP 379: Shenandoah Production
- JEP 444: Virtual Threads
- JEP 491: Synchronize Virtual Threads without Pinning (JDK 24)

### 컨퍼런스 (YouTube)

- **JavaOne / Oracle CodeOne** — Brian Goetz, Per Liden 등 발표
- **Devoxx** — Aleksey Shipilev, GC 관련 다수
- **QCon** — 빅테크 운영 사례
- **JCrete / JCrete4Kids** — 깊이 있는 JVM 토픽
- **KubeCon** — JVM in containers
- **JCO (JavaCommunity)** — 한국 컨퍼런스
- **NAVER ENGINEERING DAY / Kakao if(kakao)** — 한국 빅테크

---

> **이 사례집의 가치**: 개념만 아는 것과 "이걸 본 적 있고 고쳐본 적 있다"는 다른 차원. 각 패턴은 다음 챕터들과 cross-reference되며, 실제 prod 환경에서의 진단 능력을 기르는 게 목표.
