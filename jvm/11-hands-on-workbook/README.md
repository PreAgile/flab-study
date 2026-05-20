# 11. Hands-on Workbook — JMH/JFR/async-profiler/MAT/jcmd 실습

> P99 spike 알람이 오면 시니어는 5초 안에 `jcmd <pid> JFR.start` 또는 `asprof -e cpu`를 친다. 신입은 "어떤 도구를 써야 하지?"부터 검색한다.
> 도구를 **이론으로 안다**와 **손에 익었다**는 별개. 본 챕터는 도구별 실습 명령 + 시나리오별 첫 도구 매핑.
> 5도구: JMH(개발), JFR(상시), async-profiler(일시), MAT(사후), jcmd(라이브). 각자 다른 위치, 다른 overhead.

---

## 이 문서의 사용법

이 문서는 **면접용 마인드맵**을 따라 선형으로 펼친 구조다. 학습 순서 = 면접 답변 순서 = 백지에 그리는 순서.

1. **0장 마인드맵을 먼저 외운다** — 루트 한 문장 + 3가지 가지 + 각 가지의 키워드.
2. **1~3장을 순서대로 학습한다** — 각 장이 마인드맵의 한 가지에 정확히 대응.
3. **4장 면접/현장 워크플로우로 검증** — 시나리오를 보면 어느 도구로 가야 하는지 매핑.
4. **5장 꼬리질문으로 깊이 점검**.

---

## 0. 마인드맵 — 면접 종이에 그릴 그림

### 루트 한 문장 (anchor)

> **"JVM 진단 도구는 5종이고, 각자 다른 운영 위치와 overhead를 가진다: JMH(개발/CI), JFR(상시 ~1%), async-profiler(일시 ~수%), MAT(사후), jcmd(라이브 거의 0)."**

이 한 문장에서 모든 답변이 출발한다. 어떤 질문이 와도 이 문장부터 말하고 적절한 가지로 분기.

### 3개 가지 — 순서를 외운다

```
                  [ROOT: 진단 도구 5종 = 위치×overhead]
                                 │
        ┌──────────────┬─────────┴─────────┐
        │              │                   │
       ① 5도구 매트릭스 ② 도구별 실습       ③ 시나리오→도구
       (분류)         (명령)              (매핑)
        │              │                   │
     ┌──┼──┐        ┌──┼────┬──────┬─┐  ┌──┼──┐
   개발 상시 사후  JMH JFR  async-  MAT  P99 OOM lock
   JMH  JFR  MAT   bench profile profiler heap spike Code
        async-     함정  이벤트  flame  Leak 식별 Cache
        prof       회피  분류   graph  Suspect    VT
        jcmd                                      pin
        (live)
```

### 가지별 핵심 키워드

| 가지 | 키워드 1 | 키워드 2 | 키워드 3 |
|---|---|---|---|
| **① 5도구 매트릭스** | 개발(JMH) / 상시(JFR) / 사후(MAT) | live(jcmd) / 일시(async-profiler) | overhead별 운영 가능 위치 |
| **② 도구별 실습** | JMH 함정 4종 | JFR 이벤트 분류 | async/MAT/jcmd 핵심 명령 |
| **③ 시나리오→도구** | P99 spike → JFR | OOM → Heap dump+MAT | Lock contention → 3도구 조합 |

### 면접 답변 흐름

> 면접관 질문 → 루트 문장 → 질문에 맞는 가지 1개 선택 → 그 가지의 키워드 순서대로 설명 → 듣는 사람의 관심에 따라 인접 가지로 확장

---

## 1. 가지 ①: 5도구 매트릭스 — 위치와 overhead

### 1.1 핵심 질문

> "JVM 진단 도구 5종을 운영 위치와 overhead로 어떻게 분류하나요?"

### 1.2 매트릭스

| 도구 | 용도 | 운영 위치 | overhead | 형태 |
|---|---|---|---|---|
| **JMH** | Micro-benchmark | 개발/CI | N/A (별도 실행) | Java harness |
| **JFR** | Continuous recording | Production 상시 | ~1% | JVM 내장 |
| **async-profiler** | Flame graph | Production 일시 | ~수% | Native agent |
| **MAT** | Heap dump 분석 | 사후 (offline) | N/A (dump 분석) | GUI tool |
| **jcmd** | Live 다용도 | Production | 거의 0 | CLI |

### 1.3 키워드 1 — 개발 vs 상시 vs 사후

```
[개발/CI]               [Production 상시]        [사후 분석]
━━━━━━━━━━              ━━━━━━━━━━━━━━━         ━━━━━━━━━

JMH                    JFR (~1%)                MAT
- 코드 변경 영향        - 상시 켜둠              - Heap dump
- micro-benchmark      - P99 spike 시 dump      - Leak Suspects
- CI에 통합 가능        jcmd (~0)                - Dominator Tree
                       - 일상 명령
                       async-profiler (~수%)
                       - 일시 flame graph
                       - 의심 시 임시 실행
```

**시니어 선택 기준**:
- 코드 변경의 성능 영향 → JMH
- 매일 production 모니터 → JFR + jcmd
- 의심 발생 시 깊이 봄 → async-profiler
- 사고 후 dump 분석 → MAT

### 1.4 키워드 2 — overhead에 따른 사용 가능성

```
overhead 0   ━━━━ jcmd (live 명령, 잠깐만 측정)
overhead 1%  ━━━━ JFR (continuous, 상시 켜기)
overhead 수% ━━━━ async-profiler (일시 분석)
overhead N/A ━━━━ MAT (offline), JMH (별도 환경)
```

**Production에서 상시 켤 수 있는 건 JFR뿐**. async-profiler는 잠깐 켜고 끔.

### 1.5 키워드 3 — 도구의 한계

- **JMH**: Micro-benchmark만. 시스템 전체 측정 불가.
- **JFR**: sampling 기반 — rare event는 놓침.
- **async-profiler**: VT 환경에서 stack unwinding 부정확 가능.
- **MAT**: Live system 분석 불가. dump 시점 snapshot만.
- **jcmd**: 통계 위주, deep dive 어려움.

→ 시니어는 **여러 도구 조합**을 쓴다. 단일 도구 의존 X.

---

## 2. 가지 ②: 도구별 실습

### 2.1 핵심 질문

> "각 도구를 production에서 어떻게 켜고, 무엇을 봐야 하나요?"

### 2.2 키워드 1 — JMH (Micro-benchmark)

#### Hello World

```bash
mvn archetype:generate -DinteractiveMode=false \
    -DarchetypeGroupId=org.openjdk.jmh \
    -DarchetypeArtifactId=jmh-java-benchmark-archetype \
    -DgroupId=org.example \
    -DartifactId=jmh-test \
    -Dversion=1.0
```

```java
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.NANOSECONDS)
@State(Scope.Thread)
@Fork(value = 1, warmups = 1)
@Warmup(iterations = 3, time = 1)
@Measurement(iterations = 5, time = 1)
public class MyBench {
    int[] arr = new int[1000];

    @Benchmark
    public int sum() {
        int s = 0;
        for (int x : arr) s += x;
        return s;
    }
}
```

```bash
mvn clean package
java -jar target/benchmarks.jar
```

#### 4대 함정 회피

| 함정 | 의미 | 회피 |
|---|---|---|
| **Dead code elimination** | JIT이 결과 안 쓰는 코드 제거 | `return` 값 또는 `Blackhole.consume()` |
| **Constant folding** | 컴파일 타임에 상수 계산 | 입력을 `@State` 필드로 (runtime에 알게) |
| **Warmup 부족** | C2 컴파일 전에 측정 | `@Warmup(iterations = 5+)` |
| **Profile 종류** | 어떤 측면을 보나 | `-prof gc`, `-prof perfasm` (assembly) |

**시니어 관점**: JMH는 micro-benchmark 전용. 시스템 전체 측정 (web app throughput 등)에는 부적합.

### 2.3 키워드 2 — JFR (Continuous Recording, Production 상시)

#### 즉시 시작

```bash
jcmd <pid> JFR.start name=r duration=60s settings=profile filename=rec.jfr
```

#### Continuous (production 권장)

```bash
java -XX:StartFlightRecording=disk=true,maxage=24h,maxsize=500M,settings=default \
     -XX:FlightRecorderOptions=stackdepth=128 \
     -jar app.jar
```

→ 최근 24시간 / 500MB가 디스크에 항상 있음. P99 spike 알람 오면 dump 받아서 분석.

#### 분석

```bash
# CLI
jfr summary rec.jfr
jfr print --events jdk.GarbageCollection rec.jfr
jfr print --events jdk.Deoptimization rec.jfr | head -50

# JMC (JDK Mission Control) GUI
jmc rec.jfr
```

#### 핵심 이벤트 매핑 (어떤 문제 → 어떤 이벤트)

| 영역 | 이벤트 | 분석 포인트 |
|---|---|---|
| **GC** | `jdk.GarbageCollection`, `jdk.GCHeapSummary` | pause 분포, Heap 추세 |
| **JIT** | `jdk.Deoptimization`, `jdk.Compilation` | deopt 빈도 (가정 깨짐), 컴파일 시간 |
| **Lock** | `jdk.JavaMonitorEnter`, `jdk.JavaMonitorWait` | contention 위치 |
| **I/O** | `jdk.SocketRead`, `jdk.SocketWrite` | 느린 외부 호출 |
| **CPU** | `jdk.ExecutionSample` | sampling profile |
| **Alloc** | `jdk.ObjectAllocationInNewTLAB` | allocation rate |
| **Class** | `jdk.ClassLoad`, `jdk.ClassUnload` | CL 누수 |
| **VT (JDK 21+)** | `jdk.VirtualThreadPinned`, `jdk.VirtualThreadSubmitFailed` | pinning |
| **Code Cache** | `jdk.CodeCacheStatistics` | 사용량 추세 |

**시니어 표준**: production에 JFR continuous를 켜둔다. 사고 시 사후 분석이 가능.

### 2.4 키워드 3 — async-profiler / MAT / jcmd

#### async-profiler (Flame Graph)

```bash
# 설치 (Linux)
wget https://github.com/async-profiler/async-profiler/releases/download/v3.0/async-profiler-3.0-linux-x64.tar.gz
tar xzf async-profiler-*.tar.gz

# CPU flame graph (60초)
asprof -e cpu -d 60 -f cpu.html <pid>

# Allocation flame graph (어디서 객체 많이 만드나)
asprof -e alloc -d 60 -f alloc.html <pid>

# Lock contention
asprof -e lock -d 60 -f lock.html <pid>
```

**함정**:
- VT 환경에서 stack unwinding 오류 가능 → `--cstack vm` 옵션.
- Warmup 후에 측정 (인터프리터 frame은 정확도 ↓).

#### MAT (Eclipse Memory Analyzer) — Heap dump 분석

```bash
# Heap dump 생성
jcmd <pid> GC.heap_dump /tmp/heap.hprof

# OOM 시 자동 (사전 설정 필요)
java -XX:+HeapDumpOnOutOfMemoryError -XX:HeapDumpPath=/var/log/heap.hprof -jar app.jar

# MAT 시작
mat /tmp/heap.hprof
```

**핵심 분석 뷰 5종**:

| 뷰 | 용도 |
|---|---|
| **Leak Suspects** | 자동 분석 — 의심 큰 객체 + 점유 비율. 시작점. |
| **Dominator Tree** | 어느 객체가 가장 많은 메모리 점유 |
| **GC Roots** | 어떤 root chain이 객체를 잡고 있는지 (왜 GC 안 됨) |
| **Histogram** | 클래스별 인스턴스 수 |
| **OQL (Object Query Language)** | SQL-like 객체 검색 |

**시나리오 — ClassLoader 누수**:
```
1. Histogram에서 ClassLoader subclass 검색
2. 같은 이름의 CL 인스턴스 수 확인 — 비정상 다수면 누수
3. 인스턴스 → "Show in Dominator Tree" → 그 CL이 잡고 있는 객체들
4. GC Roots 추적 → 어디서 누가 잡고 있는지
```

#### jcmd (Live, 모든 시니어의 일상 도구)

```bash
# 1. JVM 상태
jcmd <pid> VM.version
jcmd <pid> VM.flags
jcmd <pid> VM.command_line

# 2. 메모리
jcmd <pid> VM.native_memory summary   # NMT (사전 활성화 필요)
jcmd <pid> GC.heap_info
jcmd <pid> GC.class_histogram | head -30
jcmd <pid> VM.metaspace summary
jcmd <pid> VM.classloader_stats

# 3. JIT
jcmd <pid> Compiler.codecache
jcmd <pid> Compiler.queue
jcmd <pid> Compiler.directives_print

# 4. Thread
jcmd <pid> Thread.print | head -100
jcmd <pid> Thread.dump_to_file /tmp/threads.txt

# 5. GC / Heap
jcmd <pid> GC.run                     # System.gc() 강제 (운영 권장 X)
jcmd <pid> GC.heap_dump /tmp/h.hprof

# 6. JFR 제어
jcmd <pid> JFR.start name=r duration=60s settings=profile
jcmd <pid> JFR.dump name=r filename=r.jfr
jcmd <pid> JFR.stop name=r
```

**시니어 일상**: SSH 들어가서 `jcmd <pid> GC.heap_info` 같은 명령을 즉시 친다. 외워야 함.

---

## 3. 가지 ③: 시나리오 → 도구 매핑

### 3.1 핵심 질문

> "특정 증상을 봤을 때 어느 도구를 먼저 잡나요?"

### 3.2 매핑 테이블

| 시나리오 | 첫 도구 | 보조 | 결정 근거 |
|---|---|---|---|
| **P99 spike** | JFR (continuous) | async-profiler (cpu) | 사후 분석 + 일시 deep dive |
| **Full GC 빈발** | GC log + JFR `jdk.GarbageCollection` | MAT (사후) | GC 분포 → leak 의심 시 dump |
| **OOM** | Heap dump + MAT | jcmd (사고 직전 상태) | Leak Suspects가 시작점 |
| **Container OOM-killed** | NMT (`jcmd VM.native_memory`) | jcmd `Thread.print` | Heap 외 영역 의심 — Thread/Metaspace/Direct |
| **Code Cache full** | `jcmd Compiler.codecache` | JFR `jdk.CodeCacheStatistics` | 사용량 + nmethod sweep |
| **Lock contention** | `jstack` + JFR `jdk.JavaMonitor*` | async-profiler (`-e lock`) | thread state + monitor 위치 |
| **Hot path 식별** | async-profiler (cpu) | JFR `jdk.ExecutionSample` | flame graph |
| **Allocation rate ↑** | async-profiler (alloc) | JFR `jdk.ObjectAllocationInNewTLAB` | 어디서 객체 만드나 |
| **코드 변경 영향** | JMH | — | 별도 환경 micro-benchmark |
| **VT pinning** | `-Djdk.tracePinnedThreads=full` | JFR `jdk.VirtualThreadPinned` | log + 이벤트 |
| **Deopt 빈발** | JFR `jdk.Deoptimization` | `Compiler.directives_print` | reason 분류 |
| **Metaspace OOM** | `jcmd VM.metaspace summary` | MAT (CL 누수) | 사이즈 + ClassLoader 인스턴스 |

### 3.3 시나리오 1 — P99 latency spike

```
[알람] P99 > 1초 (목표 < 100ms)
   ↓
1. 즉시: jcmd <pid> GC.heap_info  → 메모리/GC 상태 quick check
2. 사전 JFR continuous에서 spike 시점 dump
3. JFR 분석:
   - jdk.GarbageCollection — GC pause가 원인?
   - jdk.JavaMonitorEnter — Lock contention?
   - jdk.SocketRead — 외부 호출 느림?
   - jdk.Deoptimization — JIT deopt 폭주?
4. JFR로 root cause 식별 안 되면 async-profiler 일시 실행
5. 가설 검증 → 수정 → 재배포 → 메트릭 확인
```

### 3.4 시나리오 2 — Container OOM-killed (Heap dump 정상)

```
[알람] Container OOM-killed, JVM은 자체 OOM 안 함
   ↓
원인: Heap 외 영역 합이 container limit 초과
   ↓
1. NMT 활성화 재배포: -XX:NativeMemoryTracking=summary
2. 정상 시 jcmd VM.native_memory summary 매번 측정
3. 영역별 committed 확인:
   - Java Heap (Xmx)
   - Thread (스레드 수 × 1MB) ★ 가장 흔한 원인
   - Metaspace (CL 누수)
   - Code Cache
   - Direct Memory (NIO)
   - Internal
4. Thread 큼? → jcmd Thread.print | grep -c '^"' → pool 폭증 확인
5. Metaspace 큼? → MAT로 ClassLoader 누수 분석
6. Code Cache 큼? → ReservedCodeCacheSize 재검토
7. Direct 큼? → MaxDirectMemorySize 측정 + NIO 누수
```

→ [Chapter 02-03 Stack & PC & Native](../02-runtime-data-areas/03-stack-pc-native.md)의 가지 ④ Killer 시나리오와 연결.

### 3.5 시나리오 3 — Code Cache full

```
[증상] Peak throughput 떨어짐, CompileQueue stalled
   ↓
1. jcmd <pid> Compiler.codecache
   → 각 세그먼트 (non-nmethods, profiled, non-profiled) 사용량
2. JFR jdk.CodeCacheStatistics
3. -XX:ReservedCodeCacheSize 증가 검토
4. 또는 JIT compile 줄이기 (-XX:CompileThreshold ↑)
```

### 3.6 시나리오 4 — Lock contention 의심

```
[증상] CPU 사용률 낮은데 throughput 안 오름
   ↓
1. jstack <pid> | grep -A 3 BLOCKED — 얼마나 많은 thread가 BLOCKED?
2. JFR jdk.JavaMonitorEnter — 어느 monitor에서 대기 시간 큰가?
3. async-profiler -e lock — flame graph로 어느 stack에서
4. 가설:
   - 같은 lock에 다수 thread 대기 → fine-grained lock으로 분할
   - synchronized 안에서 I/O → lock 밖으로 빼기
   - VT 환경 + synchronized → pinning, ReentrantLock으로 교체
```

---

## 4. 면접/현장 답변 워크플로우

### 4.1 질문 → 가지 매핑

| 질문 | 진입 가지 | 인접 확장 |
|---|---|---|
| "JVM 진단 도구 뭐 쓰세요?" | ① 매트릭스 | ② 도구별 |
| "P99 spike 어떻게 진단?" | ③ 시나리오 1 | ② JFR |
| "OOM 분석 절차?" | ③ OOM 시나리오 | ② MAT |
| "Container OOM-killed?" | ③ 시나리오 2 | NMT 풀버전 |
| "JFR을 production에 켜도 되나?" | ② JFR | ① overhead |
| "Lock contention 진단?" | ③ 시나리오 4 | jstack/JFR/async 조합 |
| "JMH 함정?" | ② JMH | 4종 함정 |
| "Heap dump 어떻게 분석?" | ② MAT | Leak Suspects 흐름 |
| "VT pinning 진단?" | ③ VT pinning | jdk.tracePinnedThreads + JFR |

### 4.2 답변 템플릿

> **루트 문장 한 줄 → 해당 가지 키워드 순서대로 → 듣는 사람 표정 보고 인접 가지로**

예: "P99 spike 어떻게 진단?"

> "JVM 진단 도구는 5종이고 시나리오마다 다른 도구를 씁니다. P99 spike는 사후 분석이 핵심이라 JFR continuous에 의존합니다.
> 절차:
> 1. 사전: production에 JFR continuous를 disk=true, maxage=24h로 켜둡니다. overhead ~1%.
> 2. 알람 시: spike 시점의 JFR을 dump.
> 3. 분석: jdk.GarbageCollection(GC pause), jdk.JavaMonitorEnter(lock), jdk.SocketRead(외부 호출), jdk.Deoptimization(deopt 폭주) 4개 이벤트를 본다.
> 4. JFR로 root cause 식별 안 되면 async-profiler를 일시로 실행해 flame graph.
> 핵심: continuous JFR이 사고 시 'time machine' 역할. 사전 준비 없으면 재현이 어려움."

→ 면접관이 "JFR overhead?"면 ① 매트릭스로, "lock 자세히?"면 ③ 시나리오 4로.

---

## 5. 꼬리질문 트리

### Q1 [가지 ①]. JVM 진단 도구 5종은?

> JMH (개발/CI), JFR (상시 ~1%), async-profiler (일시 ~수%), MAT (사후 dump 분석), jcmd (live 거의 0). 각자 운영 위치와 overhead가 다름.

**🪝 Q1-1: Production에 상시 켤 수 있는 건?**
> JFR뿐. overhead ~1%로 안전. async-profiler는 ~수%라 일시만. jcmd는 명령 실행 때만 잠깐 부담.

### Q2 [가지 ②]. JFR의 핵심 이벤트는?

> 영역별로:
> - GC: `jdk.GarbageCollection`, `jdk.GCHeapSummary`
> - JIT: `jdk.Deoptimization`, `jdk.Compilation`
> - Lock: `jdk.JavaMonitorEnter`, `jdk.JavaMonitorWait`
> - I/O: `jdk.SocketRead`, `jdk.SocketWrite`
> - CPU: `jdk.ExecutionSample`
> - Alloc: `jdk.ObjectAllocationInNewTLAB`
> - Class: `jdk.ClassLoad`, `jdk.ClassUnload`
> - VT: `jdk.VirtualThreadPinned`, `jdk.VirtualThreadSubmitFailed`
> - Code Cache: `jdk.CodeCacheStatistics`

**🪝 Q2-1: JFR을 어떻게 production에 켜나요?**
> `java -XX:StartFlightRecording=disk=true,maxage=24h,maxsize=500M,settings=default ...`. 최근 24시간 / 500MB가 디스크에 항상 있고, 사고 시 `jcmd JFR.dump`로 추출.

### Q3 [가지 ②]. JMH의 4대 함정은?

> 1. **Dead code elimination** — 결과 안 쓰면 JIT이 코드 제거. `return` 또는 `Blackhole.consume()`.
> 2. **Constant folding** — 컴파일 타임 상수 계산. `@State` 필드로 input.
> 3. **Warmup 부족** — C2 컴파일 전 측정. `@Warmup(iterations=5+)`.
> 4. **Profile 종류** — 무엇을 보나. `-prof gc`, `-prof perfasm`.

### Q4 [가지 ②]. MAT의 핵심 분석 뷰는?

> 5가지: Leak Suspects(시작점, 자동 분석), Dominator Tree(누가 가장 많이 차지), GC Roots(왜 GC 안 됨), Histogram(클래스별 수), OQL(SQL-like 검색). ClassLoader 누수 의심 시: Histogram에서 CL 검색 → 인스턴스 수 비정상 → Dominator Tree → GC Roots 순서.

### Q5 [가지 ③]. P99 spike 어떻게 진단?

> JFR continuous 의존. 사전에 `-XX:StartFlightRecording=disk=true,maxage=24h,maxsize=500M`. 알람 시 spike 시점 dump. 4개 이벤트 분석: GC pause / Lock / 외부 I/O / Deopt. JFR로 안 잡히면 async-profiler 일시 실행.

### Q6 [가지 ③]. Container OOM-killed인데 Heap dump가 정상이라면?

> Heap 외 영역 합이 container limit 초과. NMT 켜고 영역별 committed 확인. 의심 순서: Thread(스레드 수 × 1MB) → Metaspace(CL 누수) → Code Cache → Direct Memory → JNI native lib(NMT 못 봄). [Chapter 02-03 Stack & PC & Native]의 Killer 시나리오.

**🪝 Q6-1: NMT를 미리 안 켰으면?**
> 재배포 필요. 그래서 NMT는 production에 처음부터 켜두는 게 시니어 표준. overhead 거의 0.

### Q7 (Killer) [가지 ③]. Lock contention 의심 시 도구 조합?

> 3개 조합:
> 1. **jstack** — `BLOCKED` thread 수와 어느 lock 대기인지 즉시 확인.
> 2. **JFR `jdk.JavaMonitorEnter`** — monitor별 대기 시간 + stack.
> 3. **async-profiler `-e lock`** — flame graph로 hot lock contention path.
>
> 가설:
> - 같은 lock 다수 대기 → fine-grained lock으로 분할
> - synchronized 안에서 I/O → lock 밖으로
> - VT + synchronized → pinning, ReentrantLock으로 교체
>
> 단일 도구 의존 X. 시니어는 도구 조합으로 root cause를 추적.

---

## 6. 학습 체크리스트

면접 전 백지에서 다음을 다 해낼 수 있어야 마스터:

- [ ] 0장 마인드맵을 종이에 1분 이내로 그릴 수 있다 (루트 + 3가지 + 키워드)
- [ ] 가지 ① 매트릭스: 5도구를 운영 위치와 overhead로 분류한다
- [ ] 가지 ② JMH: 4대 함정과 회피 방법을 말한다
- [ ] 가지 ② JFR: 핵심 이벤트 9개 영역을 외운다
- [ ] 가지 ② JFR: production continuous 옵션을 외운다 (`disk=true,maxage=24h,maxsize=500M`)
- [ ] 가지 ② async-profiler: cpu/alloc/lock 3가지 모드를 안다
- [ ] 가지 ② MAT: 분석 뷰 5종을 외운다
- [ ] 가지 ② jcmd: 일상 명령 (VM.flags, VM.native_memory, GC.heap_info, Thread.print, Compiler.codecache)을 외운다
- [ ] 가지 ③ 시나리오: P99 spike / OOM / Container OOM / Lock contention / VT pinning 각자 첫 도구를 말한다
- [ ] 가지 ③ Killer: Container OOM-killed 진단 절차 6단계를 말한다
- [ ] 5장 꼬리질문 7개에 막힘없이 답한다

---

## 다음 단계

- → [Chapter 12. Tradeoff Master Table](../12-tradeoff-master-table/): 모든 트레이드오프 종합
- ← [Chapter 10. Ops Scenarios](../10-ops-scenarios/): 시나리오별 풀버전
- ← [Chapter 02-03. Stack & PC & Native](../02-runtime-data-areas/03-stack-pc-native.md): Container OOM 풀버전
- ← [Chapter 04. GC](../04-garbage-collection/): GC log 분석
- ← [Chapter 05. JVM Tuning](../05-jvm-tuning/): JVM 옵션

## 참고

- **JMH**: https://github.com/openjdk/jmh
- **JFR Guide**: https://docs.oracle.com/en/java/javase/21/jfapi/flight-recorder-api-programmers-guide.pdf
- **JDK Mission Control**: https://www.oracle.com/java/technologies/jdk-mission-control.html
- **async-profiler**: https://github.com/async-profiler/async-profiler
- **Eclipse MAT**: https://eclipse.dev/mat/
- **jcmd reference**: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html
- **NMT**: https://docs.oracle.com/en/java/javase/21/troubleshoot/diagnostic-tools.html#GUID-3FAF1B71-2630-4D4E-8FB7-93404A6E51C2
