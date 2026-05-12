# 10-00. 실전 JVM 장애 사례집 — 빅테크는 어떻게 다루나

> JVM 명세를 외우는 것과 실제 prod 장애를 고치는 것은 다른 능력이다.
> 이 챕터는 **국내/해외 빅테크가 공개한 실제 사례**를 패턴화해서, 같은 증상이 우리 환경에 나타났을 때 어떻게 진단하고 해결할지 매핑한다.

---

## 📚 참고 출처 — 빅테크 기술 블로그

이 사례집의 모든 패턴은 다음 출처에서 공개된 내용을 기반으로 재구성. 직접 읽어보면 훨씬 깊이 이해할 수 있다.

### 🇰🇷 국내 빅테크

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

### 🌍 해외 빅테크

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

### 🎓 권위 있는 개인 블로그 / 컨퍼런스

- **Cliff Click** (HotSpot C2 창시자) — [cliffc.org/blog](https://www.cliffc.org/blog)
- **Aleksey Shipilev** (RedHat, JMH 저자) — [shipilev.net](https://shipilev.net)
- **Gil Tene** (Azul Systems, C4 GC) — Azul 블로그
- **Per Liden** (ZGC 리드) — OpenJDK
- **Mark Stoodley** (OpenJ9) — IBM
- **Sangmin Park** (네이버 D2, Brian Goetz 등 자주 발표)
- **JavaOne / Devoxx / QCon / KubeCon** YouTube 채널

---

## 🎯 8대 운영 장애 패턴 — 사례 기반

각 패턴: **증상 → 진단 흐름 → 해결 + 트레이드오프 → 참조 자료**.

---

## Case 1. P99 latency가 갑자기 튄다 — GC pause

### 증상

- 평소 P99 = 50ms, 갑자기 1~2초 spike.
- 일정 간격(예: 30분~1시간)으로 반복.
- CPU/메모리 그래프에는 큰 변화 없음.

### 빅테크 사례

- **Netflix**: ZGC migration 전, G1로 운영하던 시기 P99 spike → ZGC 전환으로 sub-ms pause 달성. (Netflix Tech Blog의 ZGC 글)
- **LinkedIn**: Kafka broker JVM에서 GC pause가 consumer rebalance를 트리거 → "Garbage Collection Optimization for High-Throughput Apache Kafka"
- **토스**: 금융 거래의 P99.9 목표를 위해 ZGC 도입 (공개 발표 자료)
- **우아한형제들**: GC pause로 인한 주문 처리 지연 사례 → JFR 분석

### 진단 흐름

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

### 가능한 원인 & 해결

| 가능 원인 | 진단 단서 | 해결 |
|---|---|---|
| **G1 Mixed GC RSet scan 비대** | GC log "RSet Scan" 시간 길음 | `-XX:G1HeapRegionSize` 조정, 객체 그래프 재설계 |
| **Humongous Object** | `-Xlog:gc+humongous` 빈번 출력 | 큰 배열을 startup에 미리 할당 + 재사용 |
| **Old gen 압박 → Full GC** | Old usage > 70%, Full GC 시간 김 | `-Xmx` 증가, `-XX:InitiatingHeapOccupancyPercent` 조정 |
| **TTSP (Time To Safepoint)** | JFR `jdk.SafepointBegin` 길이 큼 | Counted loop 문제 — JDK 10+ Thread-Local Handshakes |
| **JIT 컴파일 대기** | `jdk.CompilerTask` 이벤트 길이 큼 | AppCDS로 warmup 가속, `-XX:CICompilerCount` 늘림 |
| **시스템 (cgroup, swap)** | CPU steal, swap activity | 호스트 진단 (vmstat, mpstat) |

### 트레이드오프

- **ZGC 전환**: P99 → 1ms 미만 가능, 단 메모리 ~10% 추가 사용, throughput 5~10% 감소 가능.
- **`-XX:MaxGCPauseMillis=50`**: 짧은 pause 목표 → GC 빈도 증가 → 처리량 감소.
- **Heap 키우기**: Full GC 빈도 ↓, 단 한 번 GC가 길어짐 + 컨테이너 비용 ↑.

---

## Case 2. OutOfMemoryError: Java heap space — 메모리 누수

### 증상

- 며칠 또는 몇 시간 운영 후 OOM.
- Heap 사용량이 톱니파 모양으로 계단식 증가.
- Full GC 후에도 Old gen 사용량 줄지 않음.

### 빅테크 사례

- **우아한형제들**: 캐시 + ThreadLocal 누수 사례 (우아한기술블로그의 메모리 누수 분석 시리즈)
- **카카오**: Spring 환경의 ApplicationContext 누수 (tech.kakao.com)
- **네이버 D2**: Java Reference (WeakReference, SoftReference) 오해로 인한 누수

### 진단 흐름

```bash
# 1. OOM 자동 heap dump 설정
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

### 흔한 누수 패턴

| 패턴 | 진단 단서 | 해결 |
|---|---|---|
| **static collection 무한 증가** | static Map/List 인스턴스 매우 큼 | TTL/크기 제한 + Caffeine 등 bounded cache |
| **ThreadLocal 누수** | Thread Pool 스레드들이 큰 객체 참조 | `try-finally`로 `remove()`, ThreadPoolExecutor afterExecute |
| **Listener 미해제** | EventListener 등록 후 unsubscribe 안 함 | WeakReference 또는 명시적 cleanup |
| **inner class implicit reference** | Anonymous/inner class가 outer 참조 | static class로 분리 또는 명시적 reference 끊기 |
| **String.intern() 남용** | StringTable 비대 (`-Xlog:stringtable`) | 인터닝 자제, JDK 7+ Heap pool 활용 |
| **JDBC connection / Statement 누수** | `try-with-resources` 미사용 | try-with-resources, connection pool 설정 |

### 트레이드오프

- **`-Xmx` 증가는 임시방편**: 누수의 근본 해결이 아님 — 시간 벌기.
- **WeakReference 사용**: 메모리 압박 시 자동 회수 — 캐시에 적합, 그러나 fragile.
- **Bounded cache**: 메모리 safe, 단 hit rate 감소 가능.

---

## Case 3. OutOfMemoryError: Metaspace — ClassLoader 누수

### 증상

- 운영 중 점진적 Metaspace 증가.
- 특히 hot deploy / Spring DevTools / Tomcat reload 환경에서 빈번.
- `jcmd VM.classloader_stats`에서 비정상적으로 많은 CL.

### 빅테크 사례

- **네이버**: 톰캣 hot redeploy 환경에서 WebappClassLoader 누수 — D2의 ClassLoader 누수 분석
- **카카오**: Spring DevTools restart classloader 누수
- **Tomcat 공식 문서**: ClassLoader leak detection (`clearReferencesXxx` 옵션)

### 진단 흐름

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

### 흔한 누수 원인

| 원인 | 진단 단서 | 해결 |
|---|---|---|
| **ThreadLocal 누수** | Thread Pool 재사용 + 옛 CL 객체 참조 | ServletContextListener.contextDestroyed에서 cleanup |
| **JDBC Driver 미해제** | DriverManager 안에 옛 CL의 Driver | `DriverManager.deregisterDriver()` 명시 호출 |
| **Logging cache** | log4j MDC, SLF4J marker | logging 라이브러리의 shutdown hook |
| **JMX MBean 미해제** | MBeanServer에 옛 CL의 MBean | MBean unregister |
| **Spring ApplicationContext** | context close 미호출 | `context.close()` 명시 |

### 트레이드오프

- **`-XX:MaxMetaspaceSize` 설정**: 무한 증가 차단, 단 적정값 측정 필요.
- **WebApp 격리 강화**: WebappClassLoader 각자 → 메모리 사용량 증가.
- **Hot deploy 포기**: 가장 안전, 단 개발 편의 손실.

---

## Case 4. Container OOM-killed — 호스트 메모리는 여유

### 증상

- 컨테이너가 갑자기 종료 (`docker logs`에 OOMKilled).
- 호스트 메모리는 여유 있음.
- JVM 내부 OOM 에러는 없음.

### 빅테크 사례

- **쿠팡**: 컨테이너 환경 Spring Boot의 메모리 limit과 `-Xmx` 미스매치 — Coupang Engineering Medium
- **Netflix**: Spinnaker JVM 컨테이너 환경 튜닝
- **OpenJDK JEP 248**: 컨테이너 인식 (`-XX:+UseContainerSupport`)

### 진단 흐름

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

### 일반적 원인

| 원인 | 진단 | 해결 |
|---|---|---|
| **`-Xmx`가 limit과 같거나 크게 설정** | Heap + 나머지 영역 합이 limit 초과 | `-Xmx` = limit의 50~70% |
| **Direct Memory 누수** | NMT의 Internal/Other 영역 비대 | DirectBuffer pool 사용, Netty 등 |
| **Native library 누수** | RSS는 큰데 NMT 영역 합과 차이 | JNI 코드, malloc 누수 (jemalloc + jeprof) |
| **Thread 폭증** | Thread Stack × N이 큼 | Thread Pool 크기 제한, Virtual Thread |
| **JDK 8 + 컨테이너** | UseContainerSupport 부재 | JDK 11+ 또는 옵션 명시 |

### 권장 설정 (JDK 17+ 컨테이너)

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

### 트레이드오프

- **`-Xmx` 작게**: 컨테이너 안전, 단 GC 빈번.
- **container limit 크게**: 안전성 ↑, 클라우드 비용 ↑.
- **여러 작은 컨테이너 vs 큰 컨테이너**: density vs efficiency.

---

## Case 5. Full GC 매분 발생 — Premature Promotion

### 증상

- Minor GC 자주 + 매번 Old gen 사용량 증가.
- Full GC가 1~5분 간격으로 발생.
- 처리량은 살아있지만 P99 spike + CPU 70%+ 항상.

### 빅테크 사례

- **LinkedIn**: Kafka broker premature promotion → Survivor 부족
- **네이버 D2**: G1 GC 튜닝 사례 + Tenuring Threshold 분석
- **Cliff Click** 블로그: 일반화된 premature promotion 패턴

### 진단 흐름

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

### 일반적 원인

| 원인 | 진단 | 해결 |
|---|---|---|
| **Survivor 너무 작음** | Survivor 즉시 가득 | `-XX:SurvivorRatio` 줄임 (Survivor 키움) |
| **MaxTenuringThreshold 너무 작음** | 객체가 일찍 promote | `-XX:MaxTenuringThreshold=15` (기본) 확인 |
| **객체 크기 큼 (Humongous)** | `-Xlog:gc+humongous` 빈번 | 큰 배열 startup 할당 + pool |
| **Young gen 부족** | Minor GC 매우 자주 | `-XX:NewRatio` 줄임 (Young 키움) |
| **객체 수명 패턴 (중기 객체 많음)** | 워크로드 분석 필요 | 캐시 디자인 재검토 |

### 트레이드오프

- **Young gen 키우기**: Minor GC 빈도 ↓, 단 Minor GC 시간 ↑.
- **Survivor 키우기**: promotion 지연, 단 Eden 줄어듦.
- **G1 → ZGC 전환**: generation 신경 안 써도 됨 (JDK 21 generational ZGC), 단 메모리 사용량 ↑.

---

## Case 6. JIT 컴파일 멈춤 — Code Cache Full

### 증상

- 운영 며칠 후 latency 점진적 증가 (5~10x).
- CPU 사용량 증가 (JIT 코드 대신 인터프리터).
- 로그에 `CodeCache is full. Compiler has been disabled.` 경고.

### 빅테크 사례

- **Spring Boot 대규모 앱**: AOP + dynamic proxy 빈번 — Code Cache 비대
- **JRebel + Spring DevTools**: hot reload로 인한 Code Cache 누수
- **Netflix**: Hollow 데이터 처리 시스템의 JIT optimization

### 진단 흐름

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

### 일반적 원인

| 원인 | 진단 | 해결 |
|---|---|---|
| **`-XX:ReservedCodeCacheSize` 너무 작음** | 240MB 기본값으로 한계 | `-XX:ReservedCodeCacheSize=512m` |
| **AOP / dynamic proxy 폭증** | Spring AOP 빈 많음 | proxy 제한, JIT 친화적 코드 |
| **Class redefinition (JRebel/JVMTI)** | dev에서만 — prod 영향 X | dev 환경에서만 hot reload |
| **`-XX:-UseCodeCacheFlushing`** | 기본 on, 옛 옵션이면 확인 | 기본값 유지 |

### 트레이드오프

- **Code Cache 키우기**: footprint 증가.
- **JIT 끄기 (`-Xint`)**: 안전하지만 5~10배 느림 (테스트용만).
- **GraalVM Native Image**: JIT 자체 없음 (AOT) — 콜드스타트 ms.

---

## Case 7. Virtual Thread Pinning — Loom 시대의 새 함정

### 증상

- JDK 21+ Virtual Thread 도입 후 일부 워크로드 성능 저하.
- carrier thread 부족 (`-Djdk.virtualThreadScheduler.parallelism` 임계).
- 일부 요청에서 P99 spike.

### 빅테크 사례

- **OpenJDK Project Loom**: 공식 사례 (JEP 444)
- **Spring Framework 6.1+**: Virtual Thread 지원과 함께 pinning 진단 가이드
- **JDK 24 JEP 491**: synchronized pinning 해결 (Per Liden 발표)

### 진단 흐름

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

### 일반적 pinning 원인

| 원인 | 해결 |
|---|---|
| **synchronized 블록 안에서 blocking** (JDK 21~23) | `ReentrantLock`으로 교체, 또는 JDK 24+ |
| **native 메서드 안에서 blocking** (JNI) | 라이브러리 업데이트, async 변형 사용 |
| **`Object.wait()` 안에서** (JDK 21~23) | `Condition.await()`으로 교체 |

### 트레이드오프

- **Virtual Thread 100% 채택**: 100만+ 동시성 가능, 단 pinning 검토 필수.
- **Platform Thread 유지**: 단순, 검증된 모델, 단 스케일 제한.
- **혼합**: I/O는 Virtual, CPU 집중은 Platform.

---

## Case 8. Direct Memory 누수 — Off-Heap 함정

### 증상

- Heap은 안정적인데 RSS 계속 증가.
- 결국 컨테이너 OOM-killed.
- `OutOfMemoryError: Direct buffer memory` (`-XX:MaxDirectMemorySize` 초과 시).

### 빅테크 사례

- **Netflix**: Spinnaker / Hollow의 DirectBuffer pool 관리
- **Netty 기반 시스템 (라인, 카카오)**: ByteBuf leak detection
- **OpenJDK 공식**: Cleaner 동작 변경 (JDK 9: sun.misc.Cleaner → java.lang.ref.Cleaner)

### 진단 흐름

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

### 일반적 원인

| 원인 | 해결 |
|---|---|
| **`ByteBuffer.allocateDirect()` 후 미해제** | `Cleaner` 자동 회수 대기 또는 명시적 `((DirectBuffer)buf).cleaner().clean()` |
| **Netty `ByteBuf` 미해제** | `referenceCount` 관리, `ReferenceCountUtil.release()` |
| **MappedByteBuffer + 큰 파일** | mapping 해제는 GC 의존 — `Cleaner` 사용 |
| **DirectBuffer pool 부족** | pool 크기 조정 (Netty의 `PooledByteBufAllocator`) |

### 트레이드오프

- **DirectBuffer 사용**: zero-copy I/O 가능, 단 관리 부담.
- **Heap ByteBuffer**: GC가 알아서 관리, 단 I/O 시 복사 발생.
- **Netty pool**: 재사용 효율, 단 max size 설정 필요.

---

## 💡 사례에서 배우는 일반 원칙

### 1. 빅테크의 공통 진단 도구 스택

```
필수: jcmd + jstat + jstack + JFR + GC log
보조: async-profiler + MAT + GCViewer / GCeasy.io
고급: NMT + JITWatch + perf
```

### 2. 빅테크가 공통으로 추천하는 prod 설정

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

### 3. 빅테크가 강조하는 운영 원칙

- **측정 없이 튜닝 없다** (Aleksey Shipilev): 모든 옵션 변경 전에 기준선 측정.
- **단일 변수 변경**: 한 번에 옵션 하나만 변경 + 측정.
- **JFR 상시 켜기**: prod에서도 1~3% 오버헤드, 사고 후 조사에 결정적.
- **컨테이너 limit과 `-Xmx` 명시적 매핑**: 자동 계산 의존 X.
- **autoscaling 트리거를 GC 메트릭과 연결**: P99이 SLO 초과 시 scale out.

---

## 🔗 다음 단계 (이 챕터의 다른 시나리오 sub-chapter)

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

## 📚 참고 자료 (전체)

### 한국 빅테크 (위 표 외 추가)

- 네이버 D2: "Java Reference와 GC" — Soft/Weak/Phantom 활용
- 네이버 D2: "JVM Internal" 시리즈
- 카카오 tech blog: JVM 튜닝 케이스
- 라인 engineering: Kafka + JVM
- 우아한기술블로그: "Spring Boot 메모리 누수 분석"
- 토스 tech: 결제 시스템 안정성

### 해외 빅테크

- Netflix Tech Blog: "Saving 0.5GB Memory on Netflix Studio" (예시)
- LinkedIn Engineering: "Garbage Collection Optimization for High-Throughput Kafka"
- Twitter Engineering: Finagle + Mesos JVM
- Cliff Click 블로그: HotSpot C2 내부
- Aleksey Shipilev: JMH, JCTools, 다양한 글
- Gil Tene Azul: pauseless GC 발표

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
