# 11. Hands-on Workbook — JMH/JFR/async-profiler/MAT 실습

> 도구를 **이론으로 안다**와 **손에 익었다**는 별개.
> 이 챕터는 직접 따라 칠 수 있는 실습 워크북.

---

## 📍 학습 목표

이 워크북을 끝내면:
- JMH로 정확한 벤치마크를 작성하고 warmup/iteration 함정을 피한다
- JFR을 prod에 켜놓고 사고 시점의 이벤트를 분석한다
- async-profiler로 flame graph를 만들고 hot path를 찾는다
- MAT으로 heap dump를 열고 leak suspect를 추적한다
- GC log를 한 줄씩 해석한다

---

## 실습 카탈로그 (작성 예정)

### Lab 1. JMH 벤치마크 정확히 작성하기

- `@Benchmark`, `@State`, `@Setup`, `@TearDown`
- Warmup iterations vs Measurement iterations
- `Blackhole`로 dead code elimination 회피
- `@Fork`로 JIT 영향 분리
- 흔한 함정: loop unrolling, constant folding, autoboxing

**과제**:
- StringBuilder vs String concatenation 정확히 측정
- ArrayList vs LinkedList 순회 비용
- ConcurrentHashMap vs HashMap + synchronized 비교

### Lab 2. JFR (Java Flight Recorder) 마스터

- `jcmd <pid> JFR.start name=myrec duration=60s filename=out.jfr`
- JDK Mission Control으로 분석
- 핵심 이벤트:
  - `jdk.GarbageCollection`
  - `jdk.ExecutionSample` (CPU profile)
  - `jdk.JavaMonitorWait` (lock 대기)
  - `jdk.SafepointBegin/End`
  - `jdk.Allocation*`
  - `jdk.CompilerTask`

**과제**:
- 의도적으로 만든 GC pressure 앱의 JFR 분석
- Lock contention 분석
- JFR streaming API로 실시간 수집

### Lab 3. async-profiler — Flame Graph

- 설치: `https://github.com/async-profiler/async-profiler`
- CPU profile: `asprof -e cpu -d 30 <pid>`
- Wall clock: `asprof -e wall -d 30 <pid>` (I/O 대기 포함)
- Allocation: `asprof -e alloc -d 30 <pid>`
- Lock: `asprof -e lock -d 30 <pid>`

**과제**:
- Spring Boot 앱에 attach, flame graph 생성
- Top method 분석 → 최적화 → 재측정

### Lab 4. MAT (Eclipse Memory Analyzer) — Heap Dump

- Heap dump 생성: `jcmd <pid> GC.heap_dump /tmp/dump.hprof`
- MAT 열기 + 분석:
  - Histogram
  - Dominator Tree
  - Path to GC Roots
  - Leak Suspects (자동)

**과제**:
- 의도적 ClassLoader leak을 만든 앱의 heap dump 분석
- 옛 WebappClassLoader가 어디서 잡혀있는지 추적

### Lab 5. GC Log 한 줄씩 해석

- `-Xlog:gc*=info,gc+heap=debug,gc+phases=debug:file=gc.log:time,uptime,level,tags`
- G1 / ZGC / Parallel 로그 비교
- GCViewer 또는 GCEasy.io로 시각화

**과제**:
- 주어진 GC log에서 P99 pause 식별
- Mixed GC 비율 / RSet scan 시간 분석

### Lab 6. jcmd 전체 마스터

```bash
jcmd <pid> help
jcmd <pid> VM.flags                    # 현재 -XX 옵션
jcmd <pid> VM.native_memory summary    # NMT
jcmd <pid> VM.classloader_stats        # CLD 통계
jcmd <pid> GC.heap_info
jcmd <pid> GC.heap_dump <file>
jcmd <pid> Thread.print                # = jstack
jcmd <pid> JFR.start ...
jcmd <pid> Compiler.codecache
jcmd <pid> VM.command_line
```

### Lab 7. JITWatch — C2 컴파일 그래프 시각화

- `-XX:+UnlockDiagnosticVMOptions -XX:+TraceClassLoading -XX:+LogCompilation`
- JITWatch로 hotspot.log 열기
- Inline 결정, deopt 추적, 어셈블리 출력

**과제**:
- 특정 메서드가 C2 컴파일되었는지 확인
- Inline 안 된 이유 파악

---

## 환경 준비

```bash
# JDK 21 (Eclipse Temurin 또는 Liberica)
java --version

# JMH archetype
mvn archetype:generate \
  -DinteractiveMode=false \
  -DarchetypeGroupId=org.openjdk.jmh \
  -DarchetypeArtifactId=jmh-java-benchmark-archetype \
  -DgroupId=com.example -DartifactId=jmh-lab -Dversion=1.0

# async-profiler
curl -L -O https://github.com/async-profiler/async-profiler/releases/download/v3.0/async-profiler-3.0-macos.zip
unzip async-profiler-3.0-macos.zip

# MAT
# https://www.eclipse.org/mat/downloads.php
```

---

## 작성 진행 상황

⏳ 각 Lab은 별도 폴더에 실습 코드 + step-by-step 가이드로 작성 예정.
선행 학습: 03, 04, 05 챕터 권장.
