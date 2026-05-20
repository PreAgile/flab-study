# 05-01. JMM + Happens-Before — 동시성 정확성의 안전판

> "synchronized를 쓰면 thread-safe" — 한 줄 답은 위험하다. **왜** synchronized가 thread-safe를 만드는가? 답은 **JMM의 happens-before 규칙**.
> JMM (Java Memory Model, JLS §17.4) 은 **컴파일러/CPU가 reorder할 수 있는 범위**를 정의한다. 13개 happens-before 관계가 그 reorder의 안전판.
> 시니어가 알아야 할 것: lock 없이도 정확한 동시성 코드를 쓸 수 있다 (volatile, CAS). 단, JMM 규칙을 명확히 이해해야.

---

## 이 문서의 사용법

1. **0장 마인드맵을 먼저 외운다**.
2. **1~5장을 순서대로 학습한다**.
3. **6장 면접 워크플로우** + **7장 꼬리질문**.

---

## 0. 마인드맵 — 면접 종이에 그릴 그림

### 루트 한 문장 (anchor)

> **"JMM은 CPU/컴파일러 reorder의 안전판이다. Happens-before 관계를 만들면 'A의 write가 B의 read에서 보임'이 보장된다. 13개 관계 중 실무는 4개 (program order, monitor lock, volatile, thread start/join)."**

### 5개 가지 — 순서를 외운다

```
              [ROOT: JMM = reorder의 안전판 + Happens-Before 13규칙]
                                  │
       ┌─────────┬──────────────────┼──────────────────┬─────────┐
       │         │                  │                  │         │
      ① 왜 JMM   ② Happens-Before   ③ 실무 4규칙       ④ 함정    ⑤ 패턴
   (4가지 함정)    정의               (Program/Monitor   (DCL,     (publication
                                       /Volatile/Thread)  partial   safety,
                                                          init)     final)
       │         │                  │                  │         │
   ┌───┼───┐  ┌──┼──┐           ┌───┼───┐         ┌────┼────┐
  Reorder  Caching SC vs        Volatile  Monitor  DCL의      SC-DRF
  Word     Partial Relaxed      의 happens 의 hb   3단계 reorder
  tearing  Constr  Memory        before          (allocate→init
                                                   →assign)
```

### 가지별 핵심 키워드

| 가지 | 키워드 1 | 키워드 2 | 키워드 3 |
|---|---|---|---|
| **① 왜 JMM** | Reordering | Caching (per-CPU) | Partial Construction |
| **② Happens-Before 정의** | A의 write가 B의 read에서 보임 | Transitivity | 13가지 |
| **③ 실무 4규칙** | Program Order | Monitor Lock (unlock→lock) | Volatile (write→read) |
| **④ 함정** | DCL (volatile 없으면) | Partial init (final 없으면) | this escape |
| **⑤ 패턴** | Publication Safety | Final fields | SC-DRF |

### 면접 답변 흐름

> 면접관 질문 → 루트 문장 → 해당 가지 → 키워드 3개 → 인접 가지로 확장

---

## 1. 가지 ①: 왜 JMM이 필요한가 — 4가지 동시성 함정

### 1.1 핵심 질문

> "Java가 왜 별도의 Memory Model을 정의했나요? 멀티스레드의 어떤 문제 때문?"

### 1.2 키워드 1 — Reordering (가장 핵심)

```
[코드]
Thread 1:        Thread 2:
x = 1;           if (ready)
ready = true;        print(x);

[기대]
Thread 2가 ready=true 보면 x=1 이어야

[실제 — 컴파일러/CPU가 reorder 가능]
ready = true;   // ② 먼저
x = 1;           // ① 나중

→ Thread 2가 ready=true 보고 x=0 읽음
→ 예상치 못한 버그
```

**왜 reorder가 일어나나**:
- 컴파일러 최적화 (independent statement 순서 변경).
- CPU out-of-order execution (pipeline 최적화).
- Cache write-back 순서 (per-CPU cache).

Single-thread 결과는 같지만 multi-thread는 깨짐.

### 1.3 키워드 2 — Caching (per-CPU)

```
Thread 1: CPU 1에서 x = 1 (CPU 1의 L1 cache)
Thread 2: CPU 2에서 x read (CPU 2의 L1 cache — 아직 0)

→ 캐시 동기화 시점 모름
→ Thread 2가 옛 값 봄
```

해결: Memory barrier로 강제 cache 동기화 (가지 ⑤에서 자세히, [02. Memory Barriers](./02-memory-barriers.md)).

### 1.4 키워드 3 — Partial Construction + Word Tearing

```
[Partial Construction]
Object o = new Object();
   ↓ 실제로는 3단계:
   1. allocate
   2. init (생성자 실행)
   3. assign ref to variable

다른 thread가 (3) 후 ref 받음:
   → 그러나 (2)가 reorder로 늦게 끝나면
   → 다른 thread가 init 안 된 객체 접근

[Word Tearing]
long, double의 read/write가 atomic 아닐 수 있음 (32-bit JVM)
   → 한 thread가 절반만 작성된 값 봄
   → volatile로 해결
```

### 1.5 4함정 요약

| 함정 | 발생 | 해결 |
|---|---|---|
| Reordering | 컴파일러/CPU 최적화 | Happens-before 만들기 |
| Caching | per-CPU L1/L2 cache | Memory barrier |
| Partial Construction | 생성자 reorder | final fields, publication 패턴 |
| Word Tearing | 64bit on 32bit JVM | volatile long/double |

→ JMM이 이 모두에 대한 명세. **운영자가 정확한 코드를 작성하려면 happens-before 이해 필수**.

### 1.6 Sequential Consistency를 안 쓰는 이유

```
[Sequential Consistency 강제하면]
   매 write에 모든 CPU 캐시 동기화 + memory barrier 풀
   → CPU 성능 50%+ 손실
   → 현대 CPU 아키텍처와 안 맞음

[Relaxed + Happens-Before 모델 (Java/C++)]
   기본은 reorder 자유
   특정 지점(volatile, lock 등)에서만 동기화 비용
   → CPU 성능 최대 활용 + 필요한 곳만 정확성
```

→ **JMM의 본질은 trade-off**: 정확성 vs 성능. 사용자가 happens-before로 필요한 곳만 동기화.

---

## 2. 가지 ②: Happens-Before 정의

### 2.1 핵심 질문

> "Happens-Before가 정확히 무엇인가요?"

### 2.2 키워드 1 — 정의 ("A의 결과가 B에서 보임")

```
A happens-before B 관계 = 
   A의 모든 메모리 효과 (write)가 B 시작 시점에 보임을 보장

예:
   Thread 1: x = 1 (A)
   ↓ happens-before
   Thread 2: print(x) (B)
   → Thread 2는 x = 1 을 봄 (0이 아님)
```

JLS §17.4.5의 공식 정의. **"순서"가 아니라 "결과의 가시성"**.

### 2.3 키워드 2 — Transitivity (가장 자주 쓰는 도구)

```
A hb B, B hb C → A hb C

활용:
   ① x = 1
   ② volatile_v = true   ← Thread 1
   ─────────────────────
   ③ if (volatile_v)     ← Thread 2
   ④ print(x)

   ① hb ② (program order)
   ② hb ③ (volatile rule)
   ③ hb ④ (program order)
   ∴ ① hb ④ (transitivity)
   → Thread 2의 x read는 1을 봄
```

**Transitivity 없이는 happens-before가 단편적**. 실무에서 가장 중요한 도구.

### 2.4 키워드 3 — 13가지 관계 분류

```
기본 (5개):
   1. Program Order — 같은 thread 내 코드 순서
   2. Monitor Lock — unlock(M) → lock(M) 같은 monitor
   3. Volatile — volatile write → volatile read 같은 변수
   4. Thread Start — t.start() → t의 모든 액션
   5. Thread Join — t의 마지막 액션 → t.join() 후

파생 (8개):
   6. Transitivity
   7. Thread Interrupt — t.interrupt() → InterruptedException 감지
   8. Constructor Finish — 생성자 종료 → finalize() 시작
   9. Final Fields — 생성자 내 final write → 외부 read
   10. Lock-free 동기화 — CAS, Atomic
   11. External Actions — I/O 작업
   12. Default Read — 모든 read는 어떤 write를 봄
   13. Synchronization Actions
```

실무는 1~5 + 9 (Final) + 10 (CAS)이 거의 전부. 나머지는 corner case.

---

## 3. 가지 ③: 실무 4규칙 — Program / Monitor / Volatile / Thread

### 3.1 핵심 질문

> "실무에서 가장 자주 쓰는 happens-before 규칙은?"

### 3.2 키워드 1 — Program Order

```
같은 thread 안의 코드 순서:
   A1; A2; A3;  → A1 hb A2 hb A3

단, 단일 thread 결과가 같으면 reorder 허용:
   x = 1; y = 2;  → 컴파일러가 순서 바꿔도 OK
   print(x); print(y);  → 사용자가 본 순서는 같음
```

기본 규칙. 모든 happens-before 분석의 출발점.

### 3.3 키워드 2 — Monitor Lock (synchronized)

```
unlock(M) → lock(M)  (같은 monitor M)

예:
class Counter {
    int count = 0;
    
    synchronized void inc() {
        count++;        // ① 안의 write
    }                   // ② unlock M
    
    synchronized int get() {  // ③ lock M
        return count;          // ④
    }
}

- Thread A가 inc() 호출 (①, ② 순서)
- Thread B가 get() 호출 (③, ④ 순서)
- ② hb ③ (monitor lock)
- ∴ ① hb ④ (transitivity)
→ count의 최신 값 보장
```

**synchronized의 본질 = monitor lock의 happens-before**.

### 3.4 키워드 3 — Volatile

```
volatile write → volatile read  (같은 변수)

예:
class Foo {
    int x = 0;
    volatile boolean ready = false;
    
    void publish() {        // Thread 1
        x = 1;              // ①
        ready = true;       // ② volatile write
    }
    
    void consume() {        // Thread 2
        if (ready) {        // ③ volatile read
            print(x);       // ④
        }
    }
}

- ① hb ② (program order, same thread)
- ② hb ③ (volatile)
- ③ hb ④ (program order)
- ∴ ① hb ④ (transitivity)
- ∴ ④의 x read는 1을 봄
```

**핵심**: volatile은 단순 visibility가 아니라 **happens-before를 만든다**. 그래서 **다른 변수(`x`)의 publication도 보장**.

### 3.5 Thread Start / Join

```
[Thread Start]
t.start()  hb  t의 모든 액션 (run 메서드 등)

→ start() 전 main thread의 모든 write가 t에서 보임

[Thread Join]
t의 마지막 액션  hb  t.join() return 후

→ t 종료 후 main thread가 t의 모든 write 봄

활용:
   - 초기화 thread + worker thread 패턴
   - join으로 결과 수집
```

### 3.6 4규칙 요약 표

| 규칙 | 관계 | 활용 |
|---|---|---|
| Program Order | 같은 thread 내 순서 | 기본 |
| Monitor Lock | unlock → lock | synchronized |
| Volatile | write → read | flag, single-writer |
| Thread Start/Join | start/마지막 → 액션/join | thread 초기화/수집 |

---

## 4. 가지 ④: 함정 — DCL, Partial Init, this escape

### 4.1 핵심 질문

> "실무 동시성 코드의 가장 흔한 함정은?"

### 4.2 키워드 1 — Double-Checked Locking (DCL)

```java
class Singleton {
    private static Singleton instance;  // ★ volatile 없으면 위험
    
    public static Singleton getInstance() {
        if (instance == null) {           // ① check
            synchronized (Singleton.class) {
                if (instance == null) {    // ② re-check
                    instance = new Singleton();   // ③
                }
            }
        }
        return instance;
    }
}
```

**volatile 없으면 위험**:
- ③에서 `new Singleton()`는 사실 3단계:
  - `m = allocate();`
  - `init m;`
  - `instance = m;`
- Reorder 가능: allocate → instance = m → init m.
- 다른 thread가 ① check 통과해 init 안 된 m 받음.

**해결**: `private static volatile Singleton instance;`
- volatile write → volatile read의 happens-before가 init 완료 보장.

### 4.3 키워드 2 — Partial Initialization

```java
class Service {
    private int[] data;
    
    Service() {
        data = new int[10];   // ① allocation
        for (int i = 0; i < 10; i++) {
            data[i] = i * 2;   // ② init
        }
    }
}

// 다른 thread가 ref 받기:
Service s = new Service();
publishGlobally(s);   // ← 위험!

// 다른 thread:
print(s.data[5]);   // 10을 기대하지만 0 받을 수 있음
```

**원인**: 생성자 안의 ②가 reorder로 ref publication 후에 끝날 수 있음.

**해결**: `data`를 `final`로 선언 → JMM의 Final fields 규칙으로 안전 publication 보장.

### 4.4 키워드 3 — this escape (생성자 안에서)

```java
class Listener {
    Listener() {
        // 생성자가 끝나기 전에 this를 외부에 노출
        EventBus.register(this);   // ← 위험!
        
        this.config = loadConfig();   // 아직 안 됨
    }
}

// 다른 thread가 EventBus 통해 this.handleEvent 호출:
//   this.config가 null인 시점에 접근 가능
```

**원칙**: 생성자 안에서 `this`를 외부에 노출 금지. 별도 init 메서드 사용.

### 4.5 함정 요약 표

| 함정 | 원인 | 해결 |
|---|---|---|
| DCL | new 3단계 reorder | volatile field |
| Partial Init | 생성자 reorder | final fields |
| this escape | 생성자 안 this 노출 | 별도 init 메서드 |

---

## 5. 가지 ⑤: 패턴 — Publication Safety, Final, SC-DRF

### 5.1 핵심 질문

> "객체를 다른 thread에 안전하게 공개하려면?"

### 5.2 키워드 1 — Publication Safety

```
안전 publication 4가지:
   1. final field에 저장 (Immutable 패턴)
   2. volatile field에 저장
   3. AtomicReference에 저장
   4. synchronized로 보호된 field에 저장
   5. Concurrent collection에 저장 (ConcurrentHashMap 등)

위험한 publication:
   - 일반 field에 저장 후 다른 thread가 읽음
   - 생성자 안에서 this 노출
```

### 5.3 키워드 2 — Final fields의 특수 보장

```java
class Immutable {
    final int x;
    final List<String> items;
    
    Immutable() {
        this.x = 42;
        this.items = List.of("a", "b");
    }
}

// 어디서나 안전:
Immutable obj = new Immutable();
publishGlobally(obj);   // ← 다른 thread가 즉시 봐도 OK

// 다른 thread:
Immutable obj = getGlobal();
print(obj.x);          // 42 보장
print(obj.items);      // 정상 list 보장
```

JMM의 특수 보장:
- **생성자 내 final write가 생성자 종료 시점에 publish 완료**.
- 다른 thread가 publish된 ref를 보면 final field는 항상 정확한 값.
- → **Immutable 객체의 안전 publication 기반**.

내부 구현: 생성자 종료 시 implicit `StoreStore barrier` (다음 챕터).

### 5.4 키워드 3 — SC-DRF (Sequential Consistency for Data Race Free)

JMM의 핵심 보장:
- **Data race가 없는 프로그램**(모든 shared access가 happens-before로 정렬됨)에서는 Sequential Consistency처럼 동작.
- 즉, **"올바르게 sync된 프로그램"은 직관적 의미**.
- Reorder는 race 있는 곳에서만 표출.

**시니어 관점**: SC-DRF가 JMM의 약속. "lock 잘 쓰면 reorder 걱정 없음."

### 5.5 HotSpot 내부 (참고)

**Volatile의 JIT 구현** (자세히는 [02. Memory Barriers](./02-memory-barriers.md)):
```
// volatile int v;

// volatile write
v = 42;
[StoreStore barrier]
[StoreLoad barrier]   ← mfence (~30 cycles)

// volatile read
int x = v;
[LoadLoad barrier]    ← x86은 자동
[LoadStore barrier]
```

**Final Fields 구현**:
```
constructor body... 
[StoreStore barrier]   ← 생성자 종료 시 implicit
return new object
```

---

## 6. 면접 답변 워크플로우

### 6.1 질문 → 가지 매핑

| 면접 질문 | 진입 가지 | 인접 확장 |
|---|---|---|
| "왜 JMM이 필요?" | ① 4함정 | reorder/caching |
| "Happens-Before가 뭐?" | ② 정의 | transitivity |
| "synchronized 동작?" | ③ Monitor Lock | unlock→lock |
| "volatile 정확한 의미?" | ③ Volatile | publication도 보장 |
| "DCL 왜 volatile 필요?" | ④ DCL | new 3단계 |
| "Immutable 안전성?" | ⑤ Final fields | publication safety |
| "Heisenbug 진단?" | ① + ④ | reorder/partial init |

### 6.2 답변 템플릿

예: "volatile의 정확한 의미는?"

> "JMM은 reorder의 안전판이고 volatile은 그 도구 중 하나입니다 (← 루트).
> volatile의 의미는 가지 ③의 키워드 3개.
> 첫째, **Visibility**: write가 즉시 다른 thread에 보임.
> 둘째, **Happens-Before 형성**: volatile write → volatile read가 hb 관계.
> 셋째, **다른 변수의 publication도 보장** — 단순 visibility가 아닙니다.
> 예를 들어 `x = 1; volatile_v = true;` 후 다른 thread가 `if (volatile_v) print(x)`에서 1을 봄. Transitivity로 x publish까지 보장.
> 추가로 long/double의 word tearing 방지도 포함."

---

## 7. 꼬리질문 트리

### Q1 [가지 ①]. JMM이 왜 필요한가요?

> 멀티스레드 4함정: Reordering (컴파일러/CPU 최적화), Caching (per-CPU L1), Partial Construction (생성자 reorder), Word Tearing (long/double atomic 아님).
> JMM이 이 모두에 대한 명세 — happens-before로 안전판 제공.

### Q2 [가지 ②]. Happens-Before가 무엇이고 왜 중요한가요?

> A happens-before B 관계. A의 write가 B의 read에서 보임을 보장 (단순 순서가 아닌 "결과의 가시성").
> 13가지 관계 (program order, monitor lock, volatile, thread start/join, transitivity 등).
> 중요성: JMM은 reorder 광범위 허용. happens-before만이 동시성 정확성의 안전판.

### Q3 [가지 ③]. volatile의 정확한 의미는?

> 1. Visibility — write가 즉시 다른 thread에 보임.
> 2. Happens-before — volatile write → volatile read가 hb 관계.
> 3. **다른 변수의 publication도 보장** (단순 visibility가 아님).
> 4. Atomicity — long/double의 word tearing 방지.

**🪝 Q3-1: volatile vs synchronized 선택?**
> 단순 flag (single-writer, multi-reader): volatile.
> 복잡 mutate (compound action): synchronized.
> Compare-and-set: AtomicXxx (CAS).

### Q4 [가지 ⑤]. Final field의 특수 보장은?

> 생성자 안의 final write가 생성자 종료 시점에 publish 완료.
> 다른 thread가 publish된 ref를 보면 final field는 항상 정확한 값.
> 내부 구현: 생성자 종료 시 implicit StoreStore barrier.
> → Immutable 객체의 안전 publication 기반.

### Q5 [가지 ④]. DCL이 volatile 없이 안 되는 이유는?

> `new Singleton()`이 3단계 (allocate / init / assign). Reorder 가능: 1 → 3 → 2.
> 다른 thread가 `instance != null` 보고 init 안 된 객체 받음.
> 해결: `volatile Singleton instance` — happens-before가 init 완료 보장.

### Q6 (Killer) [모든 가지]. 동시성 코드에 occasional bug가 있는데 reproduction이 어렵습니다. 어떻게 진단?

> 1. **코드 audit**:
>    - 모든 shared variable이 volatile/synchronized/Atomic?
>    - 생성자에서 this escape (Listener 등록 등)?
>    - 잘못된 partial init?
>
> 2. **`-Xcomp` 옵션** (모든 메서드 즉시 컴파일):
>    - 같은 버그 재현되나? 컴파일 단계의 reorder 영향 확인.
>
> 3. **JFR jdk.JavaMonitorEnter/Wait**:
>    - Lock contention 패턴 확인.
>    - Deadlock 여부.
>
> 4. **stress test**:
>    - 같은 코드를 multi-thread + heavy load → 확률 ↑.
>    - JCStress 도구 사용.
>
> 5. **defensive 조치**:
>    - 의심 shared variable에 volatile 추가.
>    - 의심 객체에 final 강화.
>    - Lock 적용.
>
> 6. **검증**:
>    - 변경 후 stress test 통과 시 가설 정확.

---

## 8. 학습 체크리스트

- [ ] 0장 마인드맵을 1분 이내로 그릴 수 있다 (루트 + 5가지 + 키워드 3개)
- [ ] 가지 ①: 4함정 (Reordering, Caching, Partial Init, Word Tearing)을 인용한다
- [ ] 가지 ①: SC vs Relaxed의 trade-off (성능 vs 정확성)를 설명한다
- [ ] 가지 ②: Happens-Before 정의 ("A의 write가 B의 read에서 보임")를 외운다
- [ ] 가지 ②: Transitivity로 ① hb ④ 도출 예시를 적는다
- [ ] 가지 ③: 4실무 규칙 (Program / Monitor / Volatile / Thread)을 표로 그린다
- [ ] 가지 ③: synchronized의 monitor lock hb 예시를 적는다
- [ ] 가지 ④: DCL의 3단계 reorder 함정을 설명한다
- [ ] 가지 ④: Partial Init / this escape의 위험을 그린다
- [ ] 가지 ⑤: Final fields가 Immutable 안전성을 어떻게 보장하는지 설명한다
- [ ] 가지 ⑤: SC-DRF의 약속을 인용한다
- [ ] 7장 꼬리질문 6개에 답한다

---

## 다음 단계

- → [02. Memory Barriers](./02-memory-barriers.md): happens-before의 CPU 구현
- → [03. Synchronized + Mark Word](./03-synchronized-and-mark-word.md): synchronized의 3단계 lock
- → [04. Virtual Threads + Loom](./04-virtual-threads-and-loom.md): M:N 모델

## 참고

- **JLS §17.4 (Memory Model)**: https://docs.oracle.com/javase/specs/jls/se21/html/jls-17.html#jls-17.4
- **JSR-133 Cookbook (Brian Goetz)**: https://www.cs.umd.edu/~pugh/java/memoryModel/
- **Brian Goetz — "Java Concurrency in Practice"**: 책
- **JCStress (race detector)**: https://github.com/openjdk/jcstress
