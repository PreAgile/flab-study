# 10. Ops Scenarios — 운영 시나리오 매핑집

> "안다"와 "다뤄봤다"의 경계.
> 면접관이 "그럼 prod에서 P99가 갑자기 200ms → 2s로 튀면 어떻게 진단하실래요?" 라고 물었을 때,
> 단계별 진단 절차를 자연스럽게 풀어낼 수 있어야 한다.

---

## 📍 학습 목표

이 챕터를 끝내면 다음 시나리오 각각에 대해 **"증상 → 가설 → 진단 명령 → 해결"** 흐름을 자연스럽게 풀어낼 수 있다.

---

## 시나리오 카탈로그 (작성 예정)

### 🔥 Latency 관련

| # | 시나리오 | 핵심 진단 도구 |
|---|---|---|
| 01 | P99 latency가 갑자기 튄다 | JFR, async-profiler, GC log |
| 02 | TTSP(Time To Safepoint) 가 김 | `-XX:+SafepointTimeout`, JFR `jdk.SafepointBegin` |
| 03 | JIT 컴파일 지연으로 warmup이 길다 | `-XX:+PrintCompilation`, AppCDS |

### 💥 메모리 관련

| # | 시나리오 | 핵심 진단 도구 |
|---|---|---|
| 04 | OutOfMemoryError: Java heap space | heap dump + MAT |
| 05 | OutOfMemoryError: Metaspace (ClassLoader leak) | `jcmd VM.classloader_stats`, MAT |
| 06 | OutOfMemoryError: Direct buffer memory | NMT, `-XX:MaxDirectMemorySize` |
| 07 | Container OOM-killed (Java heap 안 찼는데 죽음) | NMT, off-heap 분석 |
| 08 | Native memory leak (JNI 또는 DirectByteBuffer) | NMT `summary.diff`, pmap |

### 🗑️ GC 관련

| # | 시나리오 | 핵심 진단 도구 |
|---|---|---|
| 09 | Full GC 매분 발생 | GC log, GCViewer |
| 10 | Concurrent Mode Failure (CMS 시절) | GC log |
| 11 | Mixed GC 시간이 길다 (RSet 비대화) | `-Xlog:gc+phases=debug` |
| 12 | Humongous Object 잦은 할당 | `-Xlog:gc+humongous=debug` |
| 13 | ZGC가 STW가 길다 | JFR `jdk.ZAllocationStall` |

### ⚙️ JIT 관련

| # | 시나리오 | 핵심 진단 도구 |
|---|---|---|
| 14 | Code Cache full → JIT 멈춤 | `jcmd Compiler.codecache` |
| 15 | Deoptimization 빈발 | `-XX:+PrintDeoptimization` |
| 16 | Inline 안 됨 (큰 메서드) | `-XX:+PrintInlining` |

### 🧵 Threading 관련

| # | 시나리오 | 핵심 진단 도구 |
|---|---|---|
| 17 | 데드락 | `jstack`, JFR `jdk.JavaMonitorWait` |
| 18 | Lock contention 심함 | async-profiler `--lock` |
| 19 | Virtual Thread pinning | `-Djdk.tracePinnedThreads=full` |
| 20 | ThreadLocal 누수 (ClassLoader 누수의 원인) | heap dump, MAT |

### 📦 ClassLoader 관련

| # | 시나리오 | 핵심 진단 도구 |
|---|---|---|
| 21 | Tomcat hot redeploy 시 OOM Metaspace | MAT, "Path to GC Roots" |
| 22 | JDBC Driver 누수 | deregisterDriver 패턴 |
| 23 | `--add-opens` 없으면 깨지는 라이브러리 | `jdeps --jdk-internals` |

---

## 각 시나리오의 구조

```markdown
### #01 P99 latency 튐

**증상**
- 평소 P99 = 50ms, 갑자기 2초 spike
- spike는 30분 ~ 1시간 간격

**가설 (체크리스트)**
1. GC pause? → GC log 확인
2. Safepoint 길어짐? → JFR
3. JIT 컴파일? → -XX:+PrintCompilation 시점 매칭
4. Lock contention? → async-profiler --lock
5. 외부 의존성 (DB/HTTP)? → trace ID로 분리

**진단 명령**
```bash
jcmd <pid> JFR.start duration=60s filename=spike.jfr
jstack <pid>
async-profiler -e wall -d 30 <pid>
```

**해결 패턴**
- GC pause면 → -XX:MaxGCPauseMillis 조정 또는 ZGC 전환
- Lock contention이면 → 핫스팟 분석 후 lock granularity 조정
- ...

**재현 코드** (학습용)
```java
// 의도적으로 spike 발생시키는 예시
```
```

---

## 작성 진행 상황

⏳ 모든 시나리오 작성 예정.
선행 학습: 02 ~ 08 챕터 완료 권장.
