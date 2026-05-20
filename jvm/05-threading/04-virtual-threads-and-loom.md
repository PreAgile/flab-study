# 05-04. Virtual Threads + Project Loom (JDK 21+)

> 1998년 JDK 1.2부터 Java thread = OS thread (1:1). 25년 후 JDK 21에서 그 모델이 깨졌다 — **M개 virtual : N개 carrier** 의 M:N 모델.
> Virtual Thread는 Heap의 stack chunk + Continuation freeze/thaw로 수십만 thread 가능. 그러나 **synchronized + blocking** 조합이 carrier를 잡는 **Pinning 함정**이 운영 사고의 단골.
> 시니어가 알아야 할 것: Virtual Thread는 만능 아니다. **I/O bound는 좋지만 CPU bound는 부적합**. Pinning 진단 능력 필수.

---

## 이 문서의 사용법

1. **0장 마인드맵을 먼저 외운다**.
2. **1~5장을 순서대로 학습한다**.
3. **6장 면접 워크플로우** + **7장 꼬리질문**.

---

## 0. 마인드맵 — 면접 종이에 그릴 그림

### 루트 한 문장 (anchor)

> **"Virtual Thread는 Heap의 stack chunk + Continuation freeze/thaw로 M:N (수십만 : 수 carrier)을 만든다. I/O bound에는 최적, CPU bound는 부적합. synchronized + blocking 조합이 Pinning을 일으켜 carrier를 잡는다."**

### 5개 가지 — 순서를 외운다

```
              [ROOT: M:N 모델 + Continuation + Pinning 함정]
                                  │
       ┌─────────┬──────────────────┼──────────────────┬─────────┐
       │         │                  │                  │         │
      ① M:N     ② Continuation    ③ Pinning           ④ vs       ⑤ ThreadLocal
   (왜 등장)    (freeze/thaw)      (4 트리거)        Platform   + ScopedValue
       │         │                  │                  │         │
   ┌───┼───┐  ┌──┼──┐           ┌───┼───┐         ┌────┼────┐
  1:1 한계 비동기  Heap     StackChunk synchronized JNI    수십만   ThreadLocal
  10만 thread color stack chunk        + blocking         vs       수십만 entry
  100GB Loom 약속  객체     ForkJoinPool                  수천      메모리 영향
                          carrier
```

### 가지별 핵심 키워드

| 가지 | 키워드 1 | 키워드 2 | 키워드 3 |
|---|---|---|---|
| **① M:N 등장** | 1:1 한계 (10만 = 100GB) | 비동기 코드 hell | Loom 약속 (sync code + 수십만) |
| **② Continuation** | Freeze (Heap chunk) | Thaw (carrier stack 복원) | ForkJoinPool carrier |
| **③ Pinning** | synchronized + blocking (JDK 21~23) | JNI native call | -Djdk.tracePinnedThreads |
| **④ vs Platform** | I/O bound vs CPU bound | 메모리 (수 KB vs 1MB) | 생성/switch 비용 |
| **⑤ ThreadLocal** | 수십만 × ThreadLocal 메모리 | ScopedValue (JDK 21+ preview) | 마이그레이션 함정 |

### 면접 답변 흐름

> 면접관 질문 → 루트 문장 → 해당 가지 → 키워드 3개 → 인접 가지로 확장

---

## 1. 가지 ①: M:N 모델 등장 — 왜 Virtual Thread가 필요했나

### 1.1 핵심 질문

> "Virtual Thread는 왜 도입되었나요? 기존 Platform Thread의 한계는?"

### 1.2 키워드 1 — 1:1 모델의 한계

```
[Platform Thread (1:1) 한계]
서버가 10만 connection 동시 처리:
   10만 thread × 1MB stack = 100GB 메모리 ← 불가능
   OS context switch ~수 us × 10만 = ~수 초/요청 ← 불가능
```

→ 1998년 JDK 1.2 native thread 도입 이후 25년 동안 이 모델이 한계였다.

### 1.3 키워드 2 — 비동기 코드의 "color of function" 문제

```
[기존 해결 — 비동기 코드]
Netty, CompletableFuture로 작성:
   - 코드 복잡 (callback hell, chained CompletableFuture)
   - 디버깅 어려움 (stack trace 잘림)
   - Synchronous 코드 패턴 못 씀
   - "Colored function" — sync/async 코드 분리

예: async 함수는 다른 async 함수만 호출 가능
   → 일반 메서드 호출 못 함
   → 라이브러리 생태계 분열
```

### 1.4 키워드 3 — Loom의 약속 (Colorless async)

```
[Virtual Thread 약속]
"평범한 synchronous 코드를 쓰면서 수십만 thread"
   - sync 코드 그대로 (직관적)
   - 디버깅 자연스러움 (stack trace 정상)
   - I/O blocking 호출이 freeze/thaw로 처리
   - Erlang/Go의 lightweight thread를 Java에

Ron Pressler (Oracle) 주도, 2017년 시작, 2023년 JDK 21 stable
```

### 1.5 M:N 모델 그림

```
[Virtual Thread (M개, Heap 객체)]
VT-1, VT-2, ..., VT-1000000

[Carrier Thread (N개, OS)]
Carrier-1, Carrier-2, ..., Carrier-8

VT는 carrier 사이를 freeze/thaw로 이동
```

---

## 2. 가지 ②: Continuation — Freeze / Thaw 메커니즘

### 2.1 핵심 질문

> "Virtual Thread가 blocking 호출 시 정확히 어떤 일이 일어나나요?"

### 2.2 키워드 1 — Freeze (carrier → Heap chunk)

```
VT가 blocking 호출 (예: socket.read()):

1. JDK 21+ I/O API가 "이건 block될 작업"이라 인식
   - Continuation.yield() 호출

2. Continuation.yield():
   - 현재 stack의 frame들을 StackChunk 객체로 복사
   - StackChunk를 VT 객체의 _continuation 필드에 저장
   - Carrier의 OS stack을 base까지 unwind
   - Carrier가 ForkJoinPool로 돌아감

3. Carrier가 다른 VT 실행 (스케줄러)
```

→ **Carrier는 해제되어 다른 VT 실행 가능**. VT 입장에서는 단순 함수 호출 한 번.

### 2.3 키워드 2 — Thaw (Heap chunk → carrier)

```
I/O 완료 (OS의 epoll/kqueue 이벤트):

1. JDK 21+ NIO selector가 감지
   - 해당 VT를 runnable로 표시

2. 스케줄러가 VT를 어느 carrier에 할당:
   - StackChunk를 carrier OS stack에 복사 (thaw)
   - VT의 마지막 yield 지점부터 재개

3. socket.read() 다음 줄부터 실행 계속
```

→ VT 입장에서 그냥 함수 호출 한 번. 그 동안 carrier가 다른 일을 한 게 투명.

### 2.4 키워드 3 — Carrier로 ForkJoinPool 사용

```
기본 carrier pool:
   ForkJoinPool.commonPool() 변형 (default size = CPU 코어 수)
   각 carrier가 work-stealing으로 runnable VT 가져감

Lock-free 스케줄링:
   - VT 큐가 lock-free
   - Context switch가 JVM 영역 (~수 ns)
   - OS context switch (~수 us) 대비 매우 빠름

옵션: -Djdk.virtualThreadScheduler.parallelism=8
```

### 2.5 Stack Chunk의 효율

```
Platform Thread:
   1MB stack × 10만 thread = 100GB ← 불가능

Virtual Thread:
   실제 깊이만큼만 chunk 사용 (sparse 아님)
   평균 stack 깊이 ~10 frames × ~100 byte/frame ≈ 1 KB
   10만 vthread × 1 KB ≈ 100 MB ← 가능

GC와 통합:
   StackChunk는 일반 Java 객체 (jdk.internal.vm.StackChunk)
   VT unreachable이면 chunk도 회수
```

### 2.6 HotSpot 구현 (참고)

**Continuation::freeze** (`src/hotspot/share/runtime/continuation.cpp`):
```cpp
freeze_result Continuation::freeze(JavaThread* thread, ...) {
    for (frame f = thread->last_frame(); !f.is_continuation_entry(); f = f.sender()) {
        copy_frame_to_chunk(f);   // 각 frame을 StackChunk에 복사
    }
    unwind_stack();   // Stack을 base까지 unwind
    return freeze_ok;
}
```

---

## 3. 가지 ③: Pinning — Virtual Thread의 함정

### 3.1 핵심 질문

> "Pinning이 무엇이고 어떻게 진단하나요?"

### 3.2 키워드 1 — Pinning 메커니즘

```
정상 VT 동작:
  VT-1 blocks → freeze → carrier 실행 VT-2
  VT-2 blocks → freeze → carrier 실행 VT-3
  ...
  carrier 1대로 수많은 VT 처리

Pinning 발생:
  VT-1 synchronized 안 blocking → pinning
  carrier도 같이 block
  → carrier-1에서 다른 VT 실행 불가
  → 다른 VT들은 다른 carrier를 기다림
  → carrier 부족 시 throughput 급감

결과: Virtual Thread의 이점 상실
```

### 3.3 키워드 2 — 4가지 Pinning 트리거

```
1. synchronized + blocking (JDK 21~23 핵심 함정):
   synchronized (lock) {           // ← carrier의 OS mutex 잡음
       Thread.sleep(1000);          // ← blocking — freeze 시도
       // 그러나 carrier mutex 풀 수 없음
       // → pinning
   }
   해결: JDK 24+ (JEP 491)에서 해소

2. JNI native call:
   nativeMethod();   // OS stack 위에 native frame
                     // freeze 불가 (native 코드는 stack 의존)

3. Deeply nested call (드물게):
   매우 깊은 reflection chain (1000+ frames)
   → StackChunk 너무 큼 → 일부 케이스 pinning

4. Class initialization (드물게):
   클래스 정적 초기화 중 동기 대기
```

### 3.4 키워드 3 — 진단 도구

```bash
# 방법 1: -Djdk.tracePinnedThreads
java -Djdk.tracePinnedThreads=full -jar app.jar
```

Pinning 발생 시 stack trace 출력:
```
Thread[#23,virtual=Lambda$1234, ...]
   java.base/java.lang.VirtualThread.runWith
   java.base/java.lang.Thread.sleep
   ...
   <== monitors:1   ← ★ synchronized 안 pinning
   at MyService.process(MyService.java:42)
```

`<== monitors:N` = synchronized N개 holding 중.

```bash
# 방법 2: JFR
jcmd <pid> JFR.start name=vt duration=300s settings=profile
jfr summary vt.jfr | grep -i 'Pinned'
```

이벤트:
- `jdk.VirtualThreadPinned` — pinning 발생.
- `jdk.VirtualThreadStart/End` — VT lifecycle.

### 3.5 Pinning 해결

```
synchronized + blocking → ReentrantLock + blocking
   ReentrantLock은 Java-level lock → carrier 안 잡음 → freeze 가능

JNI native → 가능하면 Java로 대체
   불가능하면 platform thread로 분리

JDK 24+ 업그레이드:
   JEP 491에서 synchronized pinning 해소
   automatic — 코드 변경 불필요
```

### 3.6 HotSpot Pinning 감지 (참고)

```cpp
freeze_result Continuation::freeze(...) {
    if (thread->held_monitor_count() > 0) {
        return freeze_pinned_monitor;   // ★ pinning
    }
    if (has_native_frames(thread)) {
        return freeze_pinned_native;     // ★ pinning
    }
    // ... freeze 진행
}
```

---

## 4. 가지 ④: vs Platform Thread — I/O bound vs CPU bound

### 4.1 핵심 질문

> "Virtual Thread와 Platform Thread 중 무엇을 언제 써야 하나요?"

### 4.2 키워드 1 — 비교 표

| | Virtual Thread | Platform Thread |
|---|---|---|
| 메모리 (per thread) | ~수 KB (Heap chunk) | 1MB (OS stack) |
| 최대 수 | 수십만~수백만 | ~수천 |
| 생성 비용 | ~수 us (Heap object) | ~수 ms (OS syscall) |
| Context switch | ~수 ns (JVM) | ~수 us (OS) |
| I/O bound | 최적 (auto freeze/thaw) | 나쁨 (thread 점유) |
| CPU bound | 부적합 (carrier 점유) | 좋음 |
| synchronized + I/O | Pinning (JDK 21~23) | 정상 |
| native call | Pinning | 정상 |
| 디버깅 | stack trace 정상 | 정상 |

### 4.3 키워드 2 — I/O bound에 최적인 이유

```
I/O bound 워크로드 (DB, HTTP call):
   Platform Thread:
      thread가 I/O 대기로 90%+ 시간 idle
      그래도 thread 점유 (1MB stack, OS slot)
      thread 수 제한으로 동시성 제한
      
   Virtual Thread:
      I/O 대기 → freeze → carrier 다른 VT 실행
      Thread는 logical 객체 (수 KB)
      수십만 동시 connection 처리 가능
```

### 4.4 키워드 3 — CPU bound에 부적합한 이유

```
CPU bound 워크로드 (image processing, ML inference):
   VT가 CPU만 사용 → freeze 없음 → carrier 점유 지속
   
   carrier 수 = CPU 코어 수
   → 다른 VT 못 돌림
   → throughput 제한 (Platform Thread와 동일)
   
   추가로 ForkJoinPool 스케줄링 overhead
   → 오히려 Platform Thread보다 약간 느림
```

**시니어 가이드**:
- I/O bound web service (DB, HTTP): **VT 적극 사용**.
- CPU bound (image, ML): **Platform thread (제한된 수)**.
- Hybrid: VT + dedicated CPU pool 분리.

### 4.5 Virtual Thread per task 패턴

```java
// JDK 21+ 표준 패턴
try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
    IntStream.range(0, 10_000).forEach(i -> {
        executor.submit(() -> doWork(i));   // 각 task가 자기 VT
    });
}

// 비교: 전통적 ThreadPool
try (var executor = Executors.newFixedThreadPool(200)) {
    IntStream.range(0, 10_000).forEach(i -> {
        executor.submit(() -> doWork(i));   // 10,000 task가 200 thread 공유
    });
}
```

→ VT per task: 무제한 동시성. blocking I/O 자유.
→ Fixed pool: 동시성 200 제한. Blocking 시 throughput 제한.

---

## 5. 가지 ⑤: ThreadLocal + ScopedValue — VT 환경의 함정

### 5.1 핵심 질문

> "Virtual Thread 수십만이 있을 때 ThreadLocal은 안전한가요?"

### 5.2 키워드 1 — ThreadLocal 메모리 폭증

```java
private static final ThreadLocal<Object> TL = new ThreadLocal<>();

// 100,000 VT가 각자 TL 사용:
for (int i = 0; i < 100_000; i++) {
    Thread.startVirtualThread(() -> {
        TL.set(new BigObject(1MB));   // ← 각 VT의 ThreadLocal에 객체
    });
}

// 결과: 100,000 × 1MB = 100GB 메모리 사용
```

**원인**:
- ThreadLocal은 thread당 1개 entry.
- Platform thread 수 (수천)에는 OK였지만 VT 수 (수십만)에는 폭증.

### 5.3 키워드 2 — ScopedValue (JDK 21+ preview, JDK 23 stable)

```java
// 새로운 대안 (JDK 21+)
final static ScopedValue<User> CURRENT_USER = ScopedValue.newInstance();

// 사용
ScopedValue.where(CURRENT_USER, user).run(() -> {
    // 이 lambda 안에서만 CURRENT_USER 접근 가능
    processRequest();
});
```

**차이점**:
- ThreadLocal: thread 종료까지 살아있음. 명시적 remove() 필요.
- ScopedValue: 명시적 scope 끝나면 자동 해제. immutable.
- VT 친화적 — scope 안에서만 존재.

### 5.4 키워드 3 — 마이그레이션 함정

```
[기존 라이브러리의 ThreadLocal 사용 (예: Spring MDC, security context)]
   - Platform thread 시절 안전
   - VT 환경에서 메모리 폭증 가능
   - 일부 라이브러리는 inheritableThreadLocal 사용 → VT마다 복사

진단:
   - jcmd <pid> Thread.print | grep -c "virtual=" — VT 수
   - Heap dump에서 ThreadLocal 인스턴스 수

해결:
   - 라이브러리 업그레이드 (ScopedValue 채택 버전)
   - 일부 ThreadLocal을 ScopedValue로 마이그레이션
   - VT 수 제한 (의미가 줄지만)
```

### 5.5 Spring Boot + VT 운영 시나리오

```
환경: Spring Boot, JDK 21, VT executor 도입
증상: 평소 1000 req/s → 800 req/s (throughput 20% 감소)

진단:
1. -Djdk.tracePinnedThreads=full → pinning 빈번?
2. JFR VirtualThreadPinned 이벤트 분포
3. synchronized 사용처 audit (Spring DI, 라이브러리)

원인 후보:
- synchronized + DB call (HikariCP, JDBC driver)
- synchronized + HTTP client (옛 Apache HttpClient)
- ThreadLocal 메모리 폭증

조치:
- DB/HTTP client 라이브러리 업그레이드 (VT 친화)
- synchronized → ReentrantLock 변경
- JDK 24+ 대기 (synchronized pinning 해소, JEP 491)
- ThreadLocal → ScopedValue 마이그레이션
```

### 5.6 역사 + JDK 24+ 변화

| 연도 | 변화 |
|---|---|
| 1998 | JDK 1.2 — Native Thread (1:1) |
| 2017 | Project Loom 시작 |
| 2019 | JDK 13 — Continuation 실험 (internal) |
| 2022 | JDK 19 — Virtual Thread (preview) |
| 2023 | **JDK 21 — Virtual Thread stable** (JEP 444) |
| 2024 | JDK 23 — VT 개선 + ScopedValue stable |
| 2025 | JDK 24+ (예상) — synchronized pinning 해소 (JEP 491) |

---

## 6. 면접 답변 워크플로우

### 6.1 질문 → 가지 매핑

| 면접 질문 | 진입 가지 | 인접 확장 |
|---|---|---|
| "Virtual Thread 왜 도입?" | ① M:N 등장 | 1:1 한계 |
| "Continuation freeze/thaw?" | ② Continuation | Heap chunk |
| "Pinning이 뭐?" | ③ Pinning | 4 트리거 |
| "Pinning 진단?" | ③ 진단 | -Djdk.tracePinnedThreads |
| "VT vs Platform?" | ④ 비교 | I/O vs CPU |
| "Spring Boot + VT throughput ↓?" | ⑤ + ③ | 라이브러리 audit |
| "ThreadLocal 함정?" | ⑤ ThreadLocal | ScopedValue |

### 6.2 답변 템플릿

예: "Virtual Thread와 Platform Thread의 차이는?"

> "Virtual Thread는 Heap의 stack chunk + Continuation freeze/thaw로 M:N (수십만 : 수 carrier)을 만듭니다 (← 루트).
> 가지 ④의 비교 표로 답하면:
> 첫째, **메모리** — VT는 수 KB (Heap chunk), Platform은 1MB (OS stack).
> 둘째, **최대 수** — VT는 수십만, Platform은 수천.
> 셋째, **워크로드 적합성** — VT는 I/O bound 최적 (auto freeze/thaw), Platform은 CPU bound 적합.
> 함정: VT는 synchronized + blocking 조합에서 Pinning 발생 (가지 ③). JDK 21~23은 ReentrantLock으로 회피, JDK 24+에서 JEP 491로 해소 예정."

---

## 7. 꼬리질문 트리

### Q1 [가지 ①]. Virtual Thread는 왜 도입되었나요?

> 25년간 Java thread = OS thread (1:1) → 10만 connection 처리 시 100GB 메모리 + OS context switch 비용.
> 기존 비동기 코드 (Netty, CompletableFuture)는 colored function 문제 (sync/async 분리).
> Loom의 약속: "평범한 synchronous 코드를 쓰면서 수십만 thread."
> M:N 모델로 I/O bound 워크로드 동시성 ↑.

### Q2 [가지 ②]. Continuation의 freeze/thaw가 어떻게 동작?

> Freeze: VT가 blocking 호출 시 현재 stack frames를 StackChunk (Heap 객체)로 복사. Carrier의 OS stack을 unwind. Carrier는 다른 VT 실행.
> Thaw: I/O 완료 시 StackChunk를 carrier OS stack에 복원. yield 지점부터 재개.
> VT 입장에서는 단순 함수 호출 한 번 — 그 동안 carrier가 다른 일을 한 게 투명.

### Q3 [가지 ③]. Pinning이 무엇이고 어떻게 진단하나요?

> VT가 carrier에 묶여 freeze 못 함. carrier도 같이 block → 다른 VT 실행 불가.
> 트리거: synchronized 안 blocking (JDK 21~23), JNI, deeply nested call.
> 진단: `-Djdk.tracePinnedThreads=full` 또는 JFR `jdk.VirtualThreadPinned`.
> 해결: synchronized → ReentrantLock, JDK 24+ 업그레이드 (JEP 491).

### Q4 [가지 ④]. Virtual Thread를 CPU bound에 쓰면?

> 부적합. VT가 CPU만 사용 → freeze 없음 → carrier 점유 지속.
> Carrier 수 = CPU 코어 수 → 다른 VT 못 돌림 → throughput 제한.
> 추가 ForkJoinPool 스케줄링 overhead로 오히려 Platform Thread보다 약간 느림.
> 가이드: I/O bound는 VT, CPU bound는 Platform thread.

### Q5 [가지 ⑤]. VT + ThreadLocal의 문제는?

> ThreadLocal은 thread당 1 entry. VT 수십만 × ThreadLocal entry = 메모리 폭증.
> 일부 라이브러리는 inheritableThreadLocal로 더 심함.
> 해결: ScopedValue (JDK 21+ preview, JDK 23 stable)로 마이그레이션. Scope 끝나면 자동 해제, immutable.

### Q6 (Killer) [모든 가지]. Spring Boot에 VT 도입했더니 throughput이 줄었습니다. 진단하세요.

> 1. **Pinning 의심**:
>    - `-Djdk.tracePinnedThreads=full`로 즉시 확인.
>    - 출력에서 `<== monitors:N` 빈도.
>
> 2. **Pinning 원인**:
>    - 옛 라이브러리 (synchronized + I/O).
>    - JDBC driver 일부 (HikariCP, Oracle JDBC 일부).
>    - HTTP client (Apache HttpClient 옛 버전).
>
> 3. **조치**:
>    - 라이브러리 업그레이드 (VT 친화 버전).
>    - synchronized → ReentrantLock 변경.
>    - JDK 24+ 대기 (synchronized pinning 자동 해소).
>    - 다시 측정.
>
> 4. **검증**:
>    - JFR `jdk.VirtualThreadPinned` 이벤트로 pinning rate 0 확인.
>    - 부하 테스트로 throughput 회복.
>
> 5. **ThreadLocal 검토**:
>    - Heap dump에서 ThreadLocal 인스턴스 수.
>    - ScopedValue 마이그레이션 후보 식별.

---

## 8. 학습 체크리스트

- [ ] 0장 마인드맵을 1분 이내로 그릴 수 있다 (루트 + 5가지 + 키워드 3개)
- [ ] 가지 ①: 1:1 모델의 한계 (10만 × 1MB = 100GB)를 설명한다
- [ ] 가지 ①: Colored function 문제와 Loom의 약속을 인용한다
- [ ] 가지 ②: Continuation freeze 흐름을 그린다 (frames → StackChunk → unwind)
- [ ] 가지 ②: Continuation thaw 흐름을 그린다 (StackChunk → carrier OS stack)
- [ ] 가지 ②: ForkJoinPool carrier pool과 work-stealing을 설명한다
- [ ] 가지 ③: 4가지 Pinning 트리거를 외운다 (synchronized + blocking, JNI, deeply nested, class init)
- [ ] 가지 ③: `-Djdk.tracePinnedThreads=full` 출력의 `<== monitors:N`을 인식한다
- [ ] 가지 ④: VT vs Platform 비교 표를 그린다
- [ ] 가지 ④: I/O bound = VT, CPU bound = Platform 가이드를 말한다
- [ ] 가지 ⑤: ThreadLocal × VT 수의 메모리 폭증을 설명한다
- [ ] 가지 ⑤: ScopedValue가 VT 친화적인 이유를 설명한다
- [ ] 7장 꼬리질문 6개에 답한다

---

## 다음 단계

05-threading 종료. 다음:
- → [Chapter 06. Version History](../06-version-history/)
- → [Chapter 10. Ops Scenarios](../10-ops-scenarios/)

## 참고

- **JEP 444 — Virtual Threads**: https://openjdk.org/jeps/444
- **JEP 491 — Synchronize Virtual Threads without Pinning**: https://openjdk.org/jeps/491
- **JEP 446 — Scoped Values (preview)**: https://openjdk.org/jeps/446
- **HotSpot `continuation.cpp`**: https://github.com/openjdk/jdk/blob/master/src/hotspot/share/runtime/continuation.cpp
- **VirtualThread.java**: https://github.com/openjdk/jdk/blob/master/src/java.base/share/classes/java/lang/VirtualThread.java
- **Ron Pressler — Loom presentations**: JavaOne 2018+, Devoxx
- **Oracle — Virtual Threads guide**: https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html
