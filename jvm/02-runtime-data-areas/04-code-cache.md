# 02-04. Code Cache & JIT Compiler — JVM 성능의 심장

> Code Cache는 단순한 메모리 영역이 아니다. **JIT 컴파일러가 만들어낸 native code의 보관소**이자, JVM이 "느린 인터프리터 언어"가 아닌 "C에 근접한 빠른 언어"로 작동하게 만드는 핵심 인프라다.
>
> 그래서 이 챕터의 진짜 주인공은 **JIT 컴파일러(C1, C2)** 다. Code Cache는 JIT의 산출물을 담는 그릇일 뿐.
>
> 시니어가 알아야 할 것: 왜 두 개의 컴파일러(C1, C2)가 필요한가, Tiered Compilation은 왜 등장했는가, JDK 8→9→11→17→21을 거치며 JIT는 어떻게 진화했는가, 그리고 production에서 `CodeCache is full` 한 줄이 뜨면 무엇이 무너지는가.

---

## 📍 학습 목표

이 챕터를 마치면 백지에서 다음을 모두 풀어 설명할 수 있어야 한다.

1. **JIT란 무엇이고 왜 필요한가** — 인터프리터의 한계와 AOT 컴파일의 비현실성 사이에서 JIT가 차지하는 위치.
2. **C1과 C2 컴파일러의 본질적 차이** — 왜 한 컴파일러가 아닌 두 개를 두는가.
3. **Tiered Compilation의 아이디어** — 두 컴파일러를 한 JVM에서 동시 활용하는 전략과 그 비용.
4. **Code Cache가 왜 별도 메모리 영역인가** — Heap에 두면 안 되는 본질적 이유 3가지.
5. **JDK 8/9/11/17/21에서 JIT·Code Cache가 어떻게 변했는가** — 각 LTS에서 무엇이 바뀌었고 왜 바뀌었는지.
6. **Code Cache가 가득 차면 무엇이 일어나는가** — `CodeCache is full` 메시지 이후의 도미노.
7. **Deoptimization이 무엇이고 왜 일어나는가** — C2의 가정이 깨지는 시나리오.
8. **운영 진단** — `jcmd Compiler.codecache`, `-XX:+PrintCompilation`, JFR 이벤트를 어떻게 읽는가.
9. **면접에서 묻는 깊이의 경계** — 무엇이 "마스터 질문"이고 무엇이 "구현자만 알 수준"인지.

---

## 🎨 1단계: 백지 그리기 가이드

### Step 1. JIT를 둘러싼 큰 그림

JVM이 한 메서드를 실행할 때 거치는 길을 한 장에 담는다.

```
[Java 소스] → javac → [Bytecode (.class)]
                              │
                              ▼
                    ┌─────────────────────┐
                    │  Interpreter (느림)  │  ← 처음엔 무조건 여기로
                    └──────────┬──────────┘
                               │ 호출 카운터 ↑
                               │ "이 메서드는 hot이다"
                               ▼
                    ┌─────────────────────┐
                    │   JIT Compiler      │
                    │   (C1 → C2)         │  ← Compile Broker가 백그라운드로
                    └──────────┬──────────┘
                               │ native code 생성
                               ▼
                    ┌─────────────────────┐
                    │    Code Cache       │  ← native code 저장
                    │  (executable mem)   │
                    └──────────┬──────────┘
                               │ 다음 호출부터
                               ▼
                          [CPU가 직접 실행]
```

핵심: **JIT의 산출물(native code)은 Heap이 아닌 Code Cache에 들어간다.** 이게 이 챕터의 출발점.

### Step 2. C1과 C2의 역할 분담

```
       호출 카운터
          │
   ┌──────┴──────────────────────────┐
   ▼ 임계 1 (≈1,500)                  ▼ 임계 2 (≈10,000)
┌──────┐                          ┌──────┐
│  C1  │  빠른 컴파일               │  C2  │  무거운 컴파일
│      │  적은 최적화               │      │  공격적 최적화
│      │  + profiling 코드 삽입     │      │  inline, escape, loop unroll
└──────┘                          └──────┘
   │                                  │
   ▼                                  ▼
 빠른 응답                        최고 처리량
 (warmup 단축)                     (peak performance)
```

C1은 "빠르게 적당히", C2는 "오래 걸려도 최고로". **두 개를 분리한 이유는 컴파일 비용과 최적화 품질의 trade-off** 때문.

### Step 3. Tiered Compilation의 5단계

```
Tier 0:  Interpreter        ← 모든 메서드 시작점
   │
   │ 호출 카운터 도달
   ▼
Tier 1:  C1 (no profiling)        ← C2 큐가 비어있고 inline 가능 등 단순 케이스
Tier 2:  C1 (limited profiling)   ← 호출 카운터만 측정
Tier 3:  C1 (full profiling)      ← 분기·타입 등 풀 profile (느림)
   │
   │ 충분한 profile 데이터 수집
   ▼
Tier 4:  C2 (fully optimized)     ← 최종 형태, profile 기반 공격적 최적화
```

→ "한 메서드는 인터프리터 → C1 (3가지 sub-tier) → C2 순으로 승급한다"

### Step 4. Code Cache 3 segment (JDK 9+)

```
┌──────────────────────────────────────────┐
│  ① Non-method (≈ 5MB)                    │  ← JIT 결과가 아닌 JVM 자체 stub
│     Interpreter loop, adapter, runtime    │
├──────────────────────────────────────────┤
│  ② Profiled (≈ 117MB)                    │  ← C1 tier 2/3 결과
│     코드 안에 측정 로직 박힘 (instrumented) │
│     short-lived, C2로 승격되면 free       │
├──────────────────────────────────────────┤
│  ③ Non-profiled (≈ 117MB)                │  ← C2 tier 4 + C1 tier 1
│     측정 없는 깨끗한 코드                  │
│     long-lived, 거의 sweep 안 함          │
└──────────────────────────────────────────┘
총 reserve = 240MB (기본, -XX:ReservedCodeCacheSize)
```

### ⚠️ 이름 함정 — Profiled / Non-profiled의 진짜 의미

이 이름은 처음 보면 무조건 헷갈린다. 기준은 다음 한 줄이다.

> **"profile을 *썼느냐*"가 아니라 "이 native code가 실행되면서 profile을 *측정하느냐*"**

| 용어 | 정확한 의미 |
|---|---|
| **Profiled** | 컴파일된 native code 자체에 **profiling instrumentation이 박혀 있음** (실행하며 측정) |
| **Non-profiled** | 컴파일된 native code에 **측정 로직 없음** (clean, 빠르게 실행만) |

**그래서 C2는 Non-profiled** — C2는 C1 tier 3가 모아둔 profile을 **입력으로 소비**하지만, 결과 코드에는 측정 로직이 없다. profile을 "썼지만 더는 만들지 않는다".

```
[C1 tier 3 = Profiled]                [C2 tier 4 = Non-profiled]
─────────────────────                ─────────────────────────
"풀면서 분석하는 모의고사"             "분석 끝, 본 시험만 빠르게"
─ 카운터·분기·타입 측정 코드 삽입       ─ 측정 코드 없음
─ 실행 자체가 느림 (overhead)          ─ 최고 성능
─ 임시 (C2로 승격되면 폐기)            ─ 최종 형태 (long-lived)
```

그리고 **C1 tier 1도 Non-profiled에 들어간다** — C1 tier 1은 profile 수집을 일부러 생략한 단순 컴파일 (C2 큐가 막혔거나 트리비얼한 메서드일 때 발생). 측정 안 함 = Non-profiled.

→ Profiled / Non-profiled 분리는 **"측정 코드를 포함한 short-lived"와 "측정 없는 long-lived"를 수명별로 가르는 segment**다.

### Step 5. 완성된 그림

```
JVM Process
═══════════════════════════════════════════════════════════════════

[Heap]        [Metaspace]       [Stacks]       [Direct Memory]
                                                                    ╲
                                                                     ╲ 분리된 이유:
                                                                     ╱  - executable 메모리
                                                                    ╱   - GC 정책 다름
[Code Cache]  ← JIT 컴파일러 산출물 전용 ────────────────────────  - 32-bit jump
  │
  ├─ ① Non-method   : Interpreter loop, Adapter, Runtime stub
  ├─ ② Profiled     : C1 nmethods (tier 2/3, instrumented)
  └─ ③ Non-profiled : C2 nmethods (tier 4) + tier 1 C1
        ▲                  ▲
        │                  │
   ┌────┴────────┐    ┌────┴───────┐
   │ C1 Compiler │    │ C2 Compiler │
   │ Threads     │    │ Threads      │
   └─────────────┘    └─────────────┘
        ▲                  ▲
        └──────┬───────────┘
               │
        Compile Broker
        (compile task 큐 관리)
               ▲
               │ "이 메서드는 hot"
               │
        [Interpreter + 호출 카운터]
```

---

## 🧠 2단계: 직관 — 왜 이렇게 설계됐는가

### 핵심 비유: 통역사 → 번역자 → 출판사

| 단계 | 비유 | JVM 실체 |
|---|---|---|
| Bytecode 한 줄씩 읽고 실행 | **동시 통역사** — 매번 듣고 그자리에서 통역 | Interpreter |
| 자주 쓰는 문장을 미리 번역해둠 | **번역 초안** — 빠르게 번역, 살짝 어색 | C1 컴파일 |
| 베스트셀러는 정식 출판 | **출판된 번역서** — 시간 많이 들였지만 완벽 | C2 컴파일 |
| 번역본 보관소 | **창고** — 한정된 공간 | Code Cache |

> 통역(인터프리터)은 **준비 시간 0**, 매번 비용 발생.
> 출판(C2)은 **준비 비용 큼**, 한 번 만들면 영원히 빠름.
> 그래서 **자주 쓰는 것만 번역**한다 (= JIT의 본질).

### 왜 JIT인가 — 세 가지 대안과의 비교

```
[순수 인터프리터]        [AOT 컴파일]              [JIT (Java의 선택)]
─────────────────       ──────────────            ─────────────────
빠른 시작                 컴파일 후 배포              인터프리터로 시작
실행은 느림               실행 매우 빠름              hot path만 컴파일
profile 정보 없음         profile 못 씀              ★ runtime profile 활용

대표: 초기 BASIC           대표: C/C++, Go            대표: HotSpot JVM, V8
```

**JIT가 AOT보다 유리한 결정적 한 가지**: **runtime profile 기반 최적화**.
- 어느 분기가 자주 도는지, 어느 타입이 자주 등장하는지를 알고 컴파일 → **AOT가 가정만 하는 것을 JIT는 알고 한다**.
- 대표 예: monomorphic inline (한 가지 구현만 본 호출 사이트는 직접 점프).

### 왜 C1, C2 두 개인가 — 한 개로는 안 되는가

**한 개 시나리오의 함정**:

```
[C1만 사용 시]                       [C2만 사용 시]
빠른 컴파일 → 빠른 warmup            느린 컴파일 → 느린 warmup
But, 최적화 약함 → peak 성능 ↓        But, 최적화 강함 → peak 성능 ↑

웹 서버 시작 5초만에 응답 OK          웹 서버 시작 30초 동안 인터프리터
But, 처리량 30% 손해                  But, 안정화 후 처리량 100%
```

**둘 다 가지면**: 시작은 C1 (warmup 빠름), 안정화는 C2 (peak 최적). 이게 **Tiered Compilation**의 본질.

**대가**: Code Cache 사용량 ≈ 2배 (C1, C2 결과 동시 보유). 그래서 JDK 9에서 segment로 나눠 관리.

### ⚠️ 결정적 오해 — Code Cache는 "조회하는 캐시"가 아니다

이름 때문에 처음 보면 거의 다 이런 그림을 그린다. **이게 틀린 모델**이다.

```
[잘못된 모델 — Redis/Memcached 비유]    [실제 — 직접 실행 모델]
─────────────────────────────────       ──────────────────────────
호출 발생                                호출 발생
   ↓                                       ↓
"native code 어디 있지?" lookup          Method 객체의 _code 포인터 읽음
   ↓                                       ↓                   (1 워드 dereferencing)
key로 찾아서 fetch                       CPU의 PC를 그 주소로 점프
   ↓                                       ↓
가져와서 어딘가에서 실행                  ★ Code Cache 안에서 직접 실행
                                          (그 메모리가 코드 그 자체)
```

핵심:

> **Code Cache의 메모리 = CPU가 실행하는 instruction 자체.**
> 어디로 복사·로드해서 실행하는 게 아니라, **CPU의 instruction pointer가 Code Cache 영역 안으로 들어가서 한 줄씩 읽어 실행한다.**

`gcc` 결과물의 `.text` 영역과 본질적으로 같은 성격이다. JVM은 단지 그걸 **runtime에 만들어 넣을 뿐**.

#### 실제 호출 메커니즘 — 한 단계씩

```
1. JIT 컴파일 완료
   ↓
2. Code Cache의 어떤 주소(예: 0x7fa1b8001234)에 native instruction 배치
   ↓
3. Method 객체의 _code 필드를 atomic write로 패치
   Method._code = 0x7fa1b8001234
   ↓
4. 다음 호출 시점
   caller code:  call [Method._code]
   CPU:          그 주소로 jump → Code Cache 안에서 실행 시작
   ↓
5. ret로 caller에 복귀
```

**lookup 없음, 자료구조 없음.** 포인터 한 번 dereferencing이 호출의 전부.

#### 그럼 왜 "Cache"라는 이름인가

`Cache` = "임시 보관소"라는 일반적 의미. **lookup cache(Redis)가 아니라 storage cache**.
- nmethod는 영구가 아님 — deopt/cold sweep으로 회수됨 → "임시 저장" 뉘앙스.
- "JIT가 만든 결과를 잠시 보관하는 영역" → Cache.

이름이 lookup 자료구조처럼 들리게 만들지만, 실체는 **executable 플래그가 붙은 raw memory region**.

#### 진짜 lookup 비슷한 동작은 Inline Cache (혼동 주의)

캐시처럼 보이는 동작은 **Code Cache가 아니라 Inline Cache(IC)** 에서 일어난다.

```
Code Cache 안의 한 메서드 (예: caller.foo의 nmethod)
   │
   ▼ 안쪽 어딘가에 invokevirtual 호출 사이트
   │
   ▼
[Inline Cache slot — patch 가능한 instruction 영역]
   if (receiver.klass == ArrayList) jump ArrayList.add 직접
   else fallback to slow path
```

- IC = **각 호출 사이트마다 dispatch 정보를 캐시**.
- monomorphic이면 1워드 비교 + 직접 점프 (캐시 hit).
- 다른 타입 등장 시 IC 업데이트 또는 megamorphic vtable lookup.

→ **IC는 진짜 캐시 동작이지만, Code Cache 자체가 아니라 Code Cache 안의 호출 사이트에 박힌 별도 메커니즘**이다.

#### 한 장으로 정리

```
JVM Process Memory
═══════════════════════════════════════════════════════════════

[Heap]
  ┌──────────────────┐
  │ Method 객체       │
  │  _code: ─────────┼──────┐  (한 워드 포인터)
  │  _name: ...      │      │
  └──────────────────┘      │
                            │
                            ▼ CPU 직접 점프 (조회 X, deref만)
[Code Cache]                ▼
  ┌────────────────────────────────────────────┐
  │ ┌────────────────────────────────────┐    │
  │ │ nmethod (해당 메서드의 native code)  │    │
  │ │   mov rax, ...                     │    │
  │ │   call [Inline Cache slot] ◀──────────── ★ 여기는 진짜 캐시 동작
  │ │   add rdi, rsi                     │    │
  │ │   ret                              │    │
  │ └────────────────────────────────────┘    │
  └────────────────────────────────────────────┘
```

### 왜 Code Cache가 별도 영역인가 — 본질적 이유 3가지

```
1. ★ Executable 메모리 (W^X 보안)
   ────────────────────────────
   native code는 CPU가 직접 실행 가능해야 함 (PROT_EXEC)
   Heap이 executable이면 = 모든 객체가 코드처럼 실행 가능 = 보안 재앙
   → 별도 영역에 executable flag, Heap은 RW만

2. ★ GC와 회수 정책 분리
   ────────────────────────────
   일반 객체: Young → Old, 빠르게 죽고 빠르게 회수
   native code: 한 번 만들면 길게 사용, deopt나 cold일 때만 회수
   → 별도 sweeper(Code Sweeper)로 관리. 일반 GC 알고리즘 적용 불가.

3. ★ 32-bit relative jump 가정
   ────────────────────────────
   JIT는 method 간 점프에 32-bit offset 사용 (명령 크기 절약)
   모든 native code가 4GB 범위 안에 모여야 함
   → 시작 시 한 번에 reserve. Heap 안에 흩어지면 불가능.
```

세 줄로: **(1) 보안 (2) GC 분리 (3) 점프 최적화**. 이걸 백지에서 답할 수 있어야 한다.

### Tiered Compilation의 비용 — 왜 항상 켜진 게 아닌가

| Tiered on (기본) | Tiered off |
|---|---|
| Warmup 빠름 (C1으로 즉시 컴파일) | Warmup 느림 (인터프리터 → C2 직행) |
| Code Cache 사용량 ≈ 2배 | Code Cache 사용량 절반 |
| Profile 수집 비용 있음 (instrumented C1) | Profile 비용 없음 |
| Peak 성능 동일 | Peak 성능 동일 |

→ **메모리가 빠듯한 컨테이너**나 **warmup 무관 batch job**에서는 끄는 게 합리적.

---

## 🔬 3단계: 구조 — JIT는 어떻게 작동하는가

### JIT 컴파일 트리거 — 어떻게 "hot"을 판단하는가

#### ⚠️ 가장 흔한 오해 — "감시자 모델"

처음 그림을 보면 거의 다 이렇게 상상한다. **틀린 모델**이다.

```
[잘못된 모델 — 감시자 모델]              [실제 — 자기보고 모델]
─────────────────────────                ─────────────────────────
   ┌──────────────┐                       [실행 중인 코드]
   │ Compiler     │ 관찰                    ↓
   │ Threads      │ ──→ [실행 코드]         "내가 N번 호출됨"
   │              │ 트래킹                  ↓ counter inc (코드에 박힘)
   └──────────────┘                         ↓ 임계 비교
                                            ↓ "신고합니다"
                                            ↓
                                         [CompileBroker 큐]
                                            ↓ 비동기 pickup
                                       [Compiler Thread (일꾼)]
```

핵심:

> **별도 감시 스레드는 없다.**
> **인터프리터·C1 tier 2/3 코드 자체에 counter·임계검사·큐등록 로직이 박혀 있고**, 그 코드를 실행하던 application thread가 직접 task를 enqueue한다.
> Compiler thread는 큐에서 task만 꺼내 컴파일하는 **일꾼**일 뿐, 어떤 코드도 관찰·트래킹하지 않는다.

#### 메서드별 두 종류 카운터

HotSpot은 **Method 객체마다 두 카운터**를 유지한다 (값은 인터프리터/tier 2/3 코드가 inc).

```
1. Invocation Counter (호출 카운터)
   - 메서드 진입 시점에 +1
   - 임계 도달: 메서드 전체를 컴파일 (일반 컴파일)

2. Back-edge Counter (백엣지 카운터)
   - 루프 백워드 점프마다 +1
   - 임계 도달: 메서드 실행 중이어도 컴파일 시작
   - = OSR (On-Stack Replacement)
   - 거대 루프 한 번 안에서 hot이 되는 경우 대비
```

기본 임계 (Tiered 기준 참고용):
- C1 (tier 3): 호출 200, 백엣지 5,250
- C2 (tier 4): 호출 5,000, 백엣지 35,000

표면 숫자는 외울 필요 없다. **두 종류 카운터가 있다 + 코드에 박힌 inc/check 로직이 신고한다**가 핵심.

#### 자기보고 흐름 — step by step

```
[Application Thread가 메서드 X 실행 중]
   ↓
1. 인터프리터로 X 진입
   ↓
2. counter++ ← 인터프리터 stub에 박힌 명령
   ↓
3. if (counter > threshold) ← 역시 stub에 박힌 비교
   ↓ 임계 도달
4. ★ application thread 자기가 직접 CompileBroker.enqueue(task)
   ↓
5. enqueue 후에도 같은 thread는 계속 인터프리터로 X 실행
   (block 안 함! 컴파일 끝날 때까지 인터프리터 계속)
   ↓
─────────── 비동기로 별도 thread에서 ────────────
   ↓
6. C1 Compiler Thread가 큐에서 task pickup
   ↓
7. C1 컴파일 (수 ms ~ 수십 ms)
   ↓
8. nmethod → Code Cache의 Profiled segment에 배치
   ↓
9. Method._code 포인터를 atomic write로 nmethod 주소로 교체
   ↓
─────────── application thread 입장 ────────────
   ↓
10. 다음 X 호출 시 call [Method._code]
    → nmethod 주소로 자동 점프 → native 실행 시작
```

#### tier 3 → C2 승급도 같은 원리

C1 tier 2/3 코드 안에도 instrumentation이 박혀 있다 (그래서 "Profiled"라 부른다).

```
tier 3 native code (Profiled segment):
  ┌────────────────────────────────────────┐
  │ counter++                              │
  │ if (counter > C2_threshold &&          │
  │     profile is mature) {               │
  │     CompileBroker.enqueue(C2 task)    │
  │ }                                      │
  │ // 실제 메서드 로직                     │
  └────────────────────────────────────────┘
```

→ tier 3 코드가 실행되면서 **자기 자신을 C2로 승급 신청**. 외부 감시 없음.

#### 한 줄 요약

> JIT는 **감시 시스템이 아니라 자기보고 시스템**.
> 실행되는 코드 자체에 카운터·임계검사·큐등록이 박혀 있고,
> Compiler thread는 큐에서 task만 꺼내는 일꾼이다.

### Tier → Segment 매핑 (정확한 표)

Tiered Compilation의 5개 tier가 Code Cache 3 segment 중 어디로 가는지 — 면접에서 자주 헷갈리는 부분.

```
Tier 0  Interpreter         → Code Cache 미저장
                              (인터프리터 loop 자체는 Non-method에 있음)

Tier 1  C1, profile 없음     → Non-profiled  ★
                              (C2 큐 막힘 / 트리비얼 메서드 / inline 결정 단순)

Tier 2  C1, 카운터만 측정    → Profiled
                              (호출 횟수만, 가벼운 instrumentation)

Tier 3  C1, full profile     → Profiled      ★ (가장 흔함)
                              (분기·타입·null 등 모든 profile)

Tier 4  C2                   → Non-profiled  ★
                              (profile 소비, instrumentation 없음, 최종 형태)
```

**왜 헷갈리나**: "profile 데이터를 가장 많이 활용한 게 C2인데 왜 Profiled가 아닌가?" — 이름의 기준은 **소비가 아니라 생산(측정)**.

**실무 메모리 점유 패턴**:
- Profiled segment ≈ tier 2/3 코드 → C2로 승격되면 곧 free.
- Non-profiled segment ≈ tier 1 + tier 4 → 거의 영구.
- 시작 직후 Profiled 사용량 급증 → 안정화되며 점차 Non-profiled로 이동.

### C1과 C2의 내부 차이 (개념 수준)

```
[C1 (Client Compiler)]
─────────────────────
- HIR (High-level IR) → LIR (Low-level IR) → 머신 코드
- 빠른 단일 패스
- 최적화: constant folding, simple inlining, basic register allocation
- profiling code 삽입 가능 (tier 2/3)
- 컴파일 시간: 메서드당 수 ms ~ 수십 ms

[C2 (Server Compiler)]
─────────────────────
- Sea-of-Nodes IR (그래프 기반)
- 여러 패스, 반복 최적화
- 최적화: aggressive inlining, escape analysis, loop unrolling,
          range check elimination, vectorization, scalar replacement
- profile 데이터를 가정에 활용 (speculative)
- 컴파일 시간: 메서드당 수십 ms ~ 수백 ms
```

**왜 C2는 느린가**: Sea-of-Nodes는 노드들이 데이터/제어 의존성으로 얽힌 그래프 — 최적화 한 번에 그래프 전체 재배치 가능. 비싸지만 깊다.

> ⚠️ **면접에서 안 묻는 영역**: Sea-of-Nodes의 노드 종류, IR 변환 단계, register allocation 알고리즘. 이건 컴파일러 작성자 수준.

#### 📚 용어·최적화 풀이 (필요할 때 펼쳐보기)

각 용어를 한 번씩만 정확히 이해해두면, 면접에서 "C2가 왜 좋아요?" 같은 질문에 구체적 사례로 답할 수 있다.

<details>
<summary><b>HIR (High-level Intermediate Representation)</b> — "사람이 읽을 만한 중간 언어"</summary>

**본질**: bytecode를 바로 machine code로 못 만든다. 그 사이를 잇는 **추상도 높은 중간 표현**이 HIR.
- bytecode보다 분석하기 좋게 정돈된 형태 (메서드 호출, 분기, 변수 등이 노드)
- 아직 머신과는 거리 멈 — 레지스터·주소 없음, "변수 a, 메서드 호출" 같은 추상 단위

**비유**: Java 소스와 어셈블리 사이의 중간 언어. Java의 의미는 유지하되 컴파일러가 분석·최적화하기 좋게 표현.

**왜 필요한가**: HIR 단계에서 constant folding, simple inlining 같은 **소스 레벨에 가까운 최적화**를 적용한 뒤 LIR로 내려간다.

</details>

<details>
<summary><b>LIR (Low-level Intermediate Representation)</b> — "거의 어셈블리"</summary>

**본질**: machine code 직전 단계. 레지스터·메모리 주소·명령 단위로 표현.
- HIR의 추상 "변수"가 LIR에서는 "레지스터 R1" 또는 "stack slot [rbp-8]"로 구체화
- CPU 명령에 거의 1:1로 매핑됨

**C1 흐름 한 줄**: `bytecode → HIR (최적화) → LIR (register allocation, 명령 매핑) → machine code`

**왜 두 단계로 나누나**: HIR은 의미 단위 최적화에 좋고, LIR은 머신 단위 최적화(register, instruction scheduling)에 좋다. 한 단계로 하면 둘 다 어색.

</details>

<details>
<summary><b>Sea-of-Nodes IR</b> — "그래프로 보는 코드" (C2의 무기)</summary>

**본질**: 데이터 흐름과 제어 흐름을 **하나의 그래프**로 표현. 명령 "순서"가 사라지고 **노드 간 의존성**만 남는다.

```
[전통 IR — 명령 시퀀스]            [Sea-of-Nodes — 그래프]
  a = x + y                       (+)
  b = a * 2                      ╱   ╲
  c = b + z                     x     y
                                 │
                                 ▼
                               (*) ← 2
                                 │
                                 ▼
                               (+) ← z
                                 │
                                 ▼
                                 c
```

**왜 강력한가**: 명령 순서 제약이 없다. 의존성만 보존하면 **자유롭게 재배치·복제·삭제 가능**. 그래서 escape analysis, loop unrolling 같은 복잡한 최적화가 자연스럽게 풀린다.

**대가**: 그래프 분석은 비싸다. C2가 메서드당 수십~수백 ms 걸리는 이유.

**면접에서 한 줄로**: "C2는 Sea-of-Nodes로 명령 순서 제약 없이 그래프 재구성하면서 최적화. 비싸지만 깊은 최적화 가능."

</details>

<details>
<summary><b>Constant Folding</b> — "컴파일 타임에 미리 계산"</summary>

**본질**: 컴파일 시점에 계산 가능한 상수 표현을 **미리 계산해서 결과로 치환**.

```java
// Before
int x = 3 * 4 + 5;
int len = "hello".length();
boolean b = (1 + 2) > 0;

// After (compile time에 계산됨)
int x = 17;
int len = 5;
boolean b = true;
```

**왜 좋은가**: 런타임 계산 0번. 가장 기본적이고 거의 모든 컴파일러가 함. C1도 함.

**시니어 관점**: 같은 효과를 위해 사람이 코드에서 `final` 상수 잘 쓰면 JIT가 더 적극적으로 fold함. 매직 넘버 직접 박는 게 가독성·최적화 둘 다에서 손해.

</details>

<details>
<summary><b>Simple Inlining (C1)</b> — "작은 메서드는 호출자 안에 펼치기"</summary>

**본질**: 메서드 호출 자체를 없애고, 호출 대상의 코드를 호출자 안에 **복사해 넣음**.

```java
// Before
int getX() { return x; }
int total = getX() + getY();

// After (inline)
int total = this.x + this.y;
```

**왜 빨라지나**: 호출 비용(스택 프레임 생성, 인자 전달, 리턴 점프) 제거.

**C1의 특징**: 보수적. 매우 작은 메서드(~수십 bytecode)만 inline. 호출 사이트가 monomorphic일 때만.

**C2와의 차이**: C2는 큰 메서드도 inline + 가상 호출도 inline (CHA로 monomorphic 증명되면).

</details>

<details>
<summary><b>Basic Register Allocation (C1)</b> — "변수를 CPU 레지스터에 매핑"</summary>

**본질**: 모든 변수를 stack에 두면 메모리 접근이 매번 필요 → 느림. CPU 레지스터(rax, rbx 등)에 두면 **메모리 접근보다 100배 빠름**.

```
변수 a, b, c, d  + CPU 레지스터 (~16개)
   ↓
어떤 변수를 어떤 레지스터에 둘지 결정해야 함
   ↓
변수가 레지스터 수보다 많으면 일부는 stack으로 "spill"
```

**C1의 알고리즘**: **Linear scan** — 변수의 life range를 한 번 쭉 훑어 배치. 빠르지만 비최적.
**C2의 알고리즘**: **Graph coloring** 변형 — 더 정밀하지만 느림.

**왜 중요**: hot loop 안에서 매번 stack 접근하면 코드가 5~10배 느려진다.

</details>

<details>
<summary><b>Aggressive Inlining (C2)</b> — "monomorphic 가상 호출도 inline"</summary>

**본질**: C1의 inlining이 보수적인 반면, C2는 **큰 메서드도 inline + 가상 호출도 inline**.

```java
// 일반적으로 가상 호출 — vtable lookup 필요
List<Integer> list = ...;
list.add(1);  // ArrayList? LinkedList?

// 그러나 profile상 ArrayList만 들어옴 (monomorphic)
// → C2가 ArrayList.add를 직접 inline
// → vtable lookup 사라짐
```

**효과**: inline 후 **메서드 경계가 사라져서** 다른 최적화(escape analysis, loop unrolling)가 호출 너머까지 확장됨.

**전제**: Inline Cache가 monomorphic이어야 함. 다형성 남발하면 C2가 손 못 댐.

</details>

<details>
<summary><b>Escape Analysis</b> — "이 객체 메서드 밖으로 나가나?"</summary>

**본질**: 객체가 만들어진 메서드 밖으로 **참조가 새어나가는지(escape)** 분석.
- 안 나가면 → heap 할당 불필요 → **stack 할당 또는 scalar replacement**

```java
// Before
public int dist() {
    Point p = new Point(3, 4);  // heap 할당?
    return p.x * p.x + p.y * p.y;
}
// p는 메서드 밖으로 안 나감 → "no escape"
// → heap에 안 만들어도 됨

// After (scalar replacement까지 적용)
public int dist() {
    int p_x = 3, p_y = 4;  // 그냥 지역 변수
    return p_x * p_x + p_y * p_y;
}
```

**효과**: heap 할당 사라짐 → **GC 압박 ↓**, allocation 비용 ↓.

**시니어 관점**: 짧게 사는 wrapper 객체(`Integer`, `Optional` 등)도 EA 덕에 실제로는 안 만들어지는 경우 많음. "객체 만들면 무조건 GC 비용"이라는 통념은 C2 시대엔 정확하지 않다.

</details>

<details>
<summary><b>Scalar Replacement</b> — "객체를 아예 만들지 말고 필드만 변수로"</summary>

**본질**: Escape Analysis 결과 "도망 안 가는 객체"는 **객체 자체를 안 만들고 필드를 그냥 지역 변수**로 펼침.

```java
// Before
Point p = new Point(1, 2);
return p.x + p.y;

// After (scalar replacement)
int p_x = 1;  // 객체 안 만들고
int p_y = 2;  // 필드를 그냥 변수로
return p_x + p_y;
```

**EA와의 관계**: EA는 "분석", Scalar Replacement는 "그 분석 결과를 활용한 실제 변환".

**효과**: heap 할당 완전 제거. JMH 벤치에서 객체 할당이 0번으로 찍히는 게 이 효과.

</details>

<details>
<summary><b>Loop Unrolling</b> — "루프 본체를 여러 번 펼치기"</summary>

**본질**: 루프 한 iteration의 실제 작업 대비 **루프 오버헤드(카운터 inc, 비교, 점프)** 비율을 줄이려고 본체를 여러 번 복사.

```java
// Before
for (int i = 0; i < 100; i++) sum += arr[i];

// After (4x unroll)
for (int i = 0; i < 100; i += 4) {
    sum += arr[i];
    sum += arr[i+1];
    sum += arr[i+2];
    sum += arr[i+3];
}
```

**효과**:
- 루프 오버헤드 1/4로 줄임
- **vectorization 가능해짐** (한 번에 4개 처리하니 SIMD 명령 매핑 쉬워짐)
- CPU pipeline 활용 증가

**대가**: 코드 크기 증가. 너무 큰 unroll은 I-cache miss로 역효과.

</details>

<details>
<summary><b>Range Check Elimination</b> — "배열 bounds check 제거"</summary>

**본질**: Java는 안전을 위해 **모든 배열 접근에 bounds check 자동 삽입** (`ArrayIndexOutOfBoundsException` 던지려고). 이 check는 매번 실행됨.

```java
// 사용자 코드
for (int i = 0; i < arr.length; i++) {
    arr[i] = i;
}

// JVM이 실제 만드는 코드 (개념적)
for (int i = 0; i < arr.length; i++) {
    if (i < 0 || i >= arr.length) throw new AIOOBE();  // ← 매번 실행
    arr[i] = i;
}
```

C2의 분석: "`i`가 `0`부터 `arr.length-1`까지만 도는 게 자명함" → **check 제거**.

**효과**: 단순 배열 루프 30~50% 빨라질 수 있음.

**시니어 관점**: 인덱스를 `int`로 깔끔히 쓸수록 C2가 증명하기 쉬움. 복잡한 인덱스 계산(`arr[i*2 + offset]` 등)은 증명 실패로 check 남음.

</details>

<details>
<summary><b>Vectorization (SIMD)</b> — "한 명령으로 여러 데이터 동시 처리"</summary>

**본질**: 현대 CPU는 **SIMD 명령**(AVX, NEON 등) 지원 — 한 명령으로 4~8개 데이터 동시 처리.

```java
// 사용자 코드
for (int i = 0; i < arr.length; i++) sum += arr[i];

// 일반 컴파일: 한 번에 1개씩
// SIMD: 한 명령으로 8개 int 동시 합산 (AVX-512)
// → 8배 빠름
```

**조건**:
- 루프가 단순 (분기 없음)
- bounds check 제거됨
- 데이터 정렬 좋음

**시니어 관점**: 핫 루프에서 분기 박으면 vectorization 깨짐. `Arrays.stream(arr).sum()` 같은 단순 루프가 빠른 이유 중 하나.

</details>

<details>
<summary><b>Speculative Compilation</b> — "profile은 가정, 가정 깨지면 deopt"</summary>

**본질**: C2는 profile 데이터를 **확률적 가정**으로 받아 공격적으로 최적화.
- "이 호출 사이트는 99% ArrayList" → ArrayList로 가정해 inline
- "이 분기는 99% true" → false 쪽은 cold path로 미루기
- "이 변수는 99% non-null" → null check 제거

```java
// 사용자 코드
list.add(item);

// profile: 100% ArrayList
// → C2가 ArrayList.add를 inline, 가상 호출 제거

// 만약 어느 시점 LinkedList가 들어오면?
// → 가정 깨짐 → deopt → 인터프리터로 복귀
// → 다시 profile 모아서 새로 컴파일
```

**대가**: 가정이 깨지면 **deoptimization** 발생. 잦으면 성능 저하.

**시니어 관점**: 코드의 다형성(Strategy 패턴, dynamic proxy)이 많으면 가정이 자주 깨져 deopt 폭주. 그래서 sealed class·monomorphic 코드 패턴이 JIT 친화적.

</details>

### Compile Broker — 큐 매니저, 그 이상도 이하도 아님

Compile Broker는 **task 큐를 관리하는 단순 컴포넌트**다. 어떤 코드도 감시하지 않는다.

```
[Application Thread]                          [Compiler Thread]
─────────────────                              ─────────────────
메서드 진입
  ↓
counter++ (인터프리터 stub에 박힘)
  ↓
임계 도달 비교 (역시 stub에 박힘)
  ↓ 임계 도달
★ 자기가 직접 CompileTask 생성
  ↓
CompileBroker.enqueue(task)  ─→  [Compile Queue]
  ↓                                      ↓ (잠자던 compiler thread 깨움)
계속 인터프리터로 실행                    pickup
(block 안 함)                            ↓
                                       C1 또는 C2 호출
                                         ↓
                                       native code 생성
                                         ↓
                                       Code Cache에 nmethod 배치
                                         ↓
                                       Method._code 패치 (atomic write)
                                         ↓
                                       다시 큐 대기
                                       
[다음 X 호출 시점부터]        ─────────────
call [Method._code] → 자동 native 점프
```

핵심:
- **트리거는 application thread가, 컴파일은 compiler thread가**. 역할 분리.
- 컴파일러 스레드는 큐만 본다. 코드 감시 X.
- 컴파일은 **백그라운드**. application thread 블록 안 됨.
- 컴파일러 스레드 수: `-XX:CICompilerCount` (기본 ≈ `log2(cpu) + 1`).
- Method 객체의 entry pointer 한 워드 atomic write → race 없음.

#### "Method._code 패치"의 진짜 의미

위 흐름의 마지막 단계를 풀어보면 호출 메커니즘의 핵심이 드러난다.

```
[컴파일 전]
  Method._code = interpreter_entry_address
      ↑ 호출 시 인터프리터 진입점으로 점프

[컴파일 완료 후, atomic write]
  Method._code = nmethod_entry_address (Code Cache 안의 주소)
      ↑ 호출 시 native code 진입점으로 점프
```

즉 호출자가 하는 일은 항상 같다 — `call [Method._code]`. **달라지는 건 그 포인터가 가리키는 주소뿐**.

- 컴파일 전: 인터프리터 진입점(Non-method segment 안의 stub)을 가리킴.
- 컴파일 후: Code Cache 안의 nmethod 진입점을 가리킴.

→ "조회"가 아닌 이유가 여기서 드러난다. **포인터 하나 atomic하게 바꿔치기**하면 그 다음 호출부터 CPU가 자동으로 새 주소로 점프한다. lookup 자료구조도, 디스패치 테이블 lookup도 없음.

### Inline Cache — 호출 사이트 진화

```java
// Java 코드
List<String> list = ...;
list.add("hi");  // ← invokevirtual 호출 사이트
```

이 한 줄의 호출 사이트가 native code에서 어떻게 진화하는가:

```
[1st 호출 — Monomorphic]
  if (receiver.klass == ArrayList) jump ArrayList.add 직접
  else fallback
  → 가장 빠름. C2 inlining의 전제.

[다른 클래스 1개 만남 — Bimorphic]
  klass 두 개 check + 분기

[~3개 이상 — Megamorphic]
  vtable lookup (일반 가상 호출)
  → 가장 느림. C2 inlining 불가.
```

**시니어 관점**: 같은 호출 사이트가 `ArrayList`와 `LinkedList` 둘 다 받으면 inline이 깨진다. **다형성을 남발하면 JIT가 손 못 댄다**.

### Deoptimization — C2가 자기 결과를 버릴 때

C2는 "**낙관적 가정**"으로 공격적 최적화한다. 가정이 깨지면 native code 폐기.

```
가정의 종류:
1. CHA (Class Hierarchy Analysis): "이 메서드는 monomorphic"
   → 새 subclass 로드되면 깨짐.

2. Speculative type guess: "이 변수는 99% Integer"
   → 다른 타입 등장 시 깨짐.

3. Uncommon branch: "이 if는 거의 false"
   → true 분기 도달 시 깨짐.

4. JVMTI class redefinition: 디버거가 클래스 재정의
```

Deopt 흐름:
```
가정 위반 감지
   ↓
nmethod를 'not_entrant' 표시 (이후 호출 차단)
   ↓
실행 중인 스레드는 safepoint에서 deopt
   - native frame → interpreter frame 복원
   - register/stack → interpreter slot 매핑
   - 적절한 bytecode index부터 재시작
   ↓
Code Sweeper가 nmethod 회수
```

**시니어 신호**: JFR `jdk.Deoptimization` 이벤트가 분당 수백 건 → 코드의 다형성 패턴이 JIT를 괴롭히는 중. Strategy 패턴 남발, reflection, dynamic proxy를 살펴봐야 한다.

### Code Cache full 시나리오

```
ReservedCodeCacheSize 거의 도달
   ↓
"CodeCache is full. Compiler has been disabled."
   ↓
Compile Broker 멈춤 (새 task 안 받음)
   ↓
[이미 컴파일된 메서드]  계속 native로 실행
[새로 hot이 되는 메서드] 영원히 인터프리터로
   ↓
시간 지남 → 점진적 성능 5~10배 저하
   ↓
UseCodeCacheFlushing 켜져 있으면 (기본 on)
   → Sweeper가 cold nmethod 회수 → 공간 확보 → 컴파일 재개
[하지만 hot/cold 분리 안 된 워크로드면 thrash]
```

---

## 📜 4단계: JDK 버전별 변천사 — JIT는 어떻게 진화했는가

이 섹션이 이 문서의 핵심. **면접에서 "JDK 8과 17의 JIT 차이는?" 같은 질문이 자주 나온다.**

### 전체 흐름 한눈에

```
JDK 7   JDK 8    JDK 9       JDK 10    JDK 11    JDK 17       JDK 21
  │      │        │            │         │         │            │
  │   Tiered   Segmented    Graal     Graal      Graal       Leyden
  │   기본 on  Code Cache    실험     계속 실험   제거         시작
  │           (JEP 197)    (JEP 317)              (JEP 410)
  │            JVMCI                              Concurrent  Generational
실험          (JEP 243)                           class       ZGC
                                                  unload
                                                  성숙
```

### JDK 7 (2011) — Tiered Compilation 실험 도입

- 그 이전: `-client` (C1만) / `-server` (C2만) 분리. 사용자가 선택.
- JDK 7부터 `-XX:+TieredCompilation` 옵션 추가 (기본 off, 실험).
- 단일 Code Cache (segment 분리 없음). 기본 ~48MB.

### JDK 8 (2014) — Tiered Compilation 기본 ON, Code Cache 크기 점프

**가장 큰 변화**: `-XX:+TieredCompilation` 기본 on.
- 한 JVM에서 C1, C2 모두 사용 → Code Cache 사용량 2배.
- 따라서 **기본 ReservedCodeCacheSize**: 48MB → **240MB**.

**부작용**:
- Code Cache가 단일 영역인데 C1(short-lived) + C2(long-lived)가 섞임.
- Sweeper 비효율, fragmentation 발생 → JDK 9에서 해결.

**면접 포인트**: "JDK 8에서 JIT 무엇이 가장 바뀌었나" → **Tiered가 기본 on 되면서 Code Cache 기본 크기가 5배로 늘었다**.

### JDK 9 (2017) — Segmented Code Cache (JEP 197) + JVMCI (JEP 243)

**JEP 197: Segmented Code Cache**

JDK 8의 fragmentation 문제 해결:
- Code Cache를 3 segment로 물리 분리.
  - Non-method (JIT 결과 아닌 stub)
  - Profiled (C1, short-lived)
  - Non-profiled (C2 + tier 1 C1, long-lived)
- 각 segment 독립 sweep → short-lived 빈번 sweep, long-lived 거의 안 함.
- I-cache locality 향상 (hot code끼리 모임).

**JEP 243: JVMCI (Java-level JVM Compiler Interface)**

- JVM이 외부 컴파일러를 Java 인터페이스로 받아들일 수 있게 됨.
- C2를 Java로 다시 짤 수 있는 길 열림 = **Graal의 기반**.
- 일반 사용자에게는 직접 영향 없지만, JIT의 미래를 결정한 사건.

**면접 포인트**: "Segmented Code Cache는 왜 도입됐나" → **Tiered 기본 on으로 C1/C2가 섞여 fragmentation·sweep 비효율 발생. 수명별 segment 분리로 해결.**

### JDK 10 (2018) — Experimental Graal JIT (JEP 317)

- C2를 대체할 후보로 Graal JIT 도입 (`-XX:+UseJVMCICompiler`).
- 장점: Java로 작성 → 유지보수 쉬움, 공격적 최적화 (partial escape analysis 등).
- 단점: 메모리 사용 ↑, 일부 워크로드에서 C2보다 느림.
- **실험 상태**. 일반 production에서 사용 권장 안 됨.

### JDK 11 (2018, LTS) — Graal 그대로 experimental

- JDK 10의 Graal 그대로 유지. 큰 변화 없음.
- ZGC experimental 도입 (Code Cache와 직접 관련 없지만 GC와 sweeper의 통합 흐름 시작).

**면접 포인트**: "JDK 8과 11의 Code Cache 차이" → **Segmented Code Cache (JDK 9에서 도입된 게 11까지 이어짐)**. JDK 11 자체에서 JIT 변경은 미미.

### JDK 12-16 — 점진적 개선

- **JDK 14**: NUMA-aware Code Heap 할당 개선.
- **JDK 16**: AOT 컴파일러(`jaotc`) 제거 (JEP 410의 전조).
- Sweeper의 STW 영향 점진적 감소.

### JDK 17 (2021, LTS) — Graal 제거 (JEP 410), Sweeper 성숙

**JEP 410: Removal of the Experimental AOT and JIT Compiler**

- Graal JIT (`-XX:+UseJVMCICompiler`)와 AOT (`jaotc`) 모두 OpenJDK에서 제거.
- 이유: 유지 비용 ↑, 사용자 적음, 별도 프로젝트인 GraalVM으로 분리.
- 그래도 JVMCI 인터페이스는 남음 → GraalVM 같은 외부 컴파일러 여전히 plug-in 가능.

**Code Sweeper의 GC 통합 흐름**:
- 일부 GC(ZGC, Shenandoah)가 nmethod unloading을 concurrent로 처리하기 시작.
- Sweeper의 STW 영향 거의 사라짐.

**면접 포인트**: "JDK 17에서 JIT 무엇이 바뀌었나" → **OpenJDK에서 Graal JIT 제거(JEP 410). 원하면 GraalVM으로 가야 함. JVMCI 인터페이스는 유지.**

### JDK 21 (2023, LTS) — Generational ZGC, Leyden 준비

- **Generational ZGC** (JEP 439): ZGC가 generational 모델 지원. Code Cache는 직접 영향 없지만 nmethod unloading 효율 더 향상.
- **NMethodSweeper deprecated 흐름 마무리**: 별도 sweeper thread보다 GC와 통합된 unloading이 표준이 됨.
- **Project Leyden 시작**: AOT(CDS + AOT compile)를 통해 startup 시간 단축 시도. JIT를 대체하는 게 아니라 **JIT가 워밍업하기 전을 메우는 보완**.

**면접 포인트**: "JDK 21에서 JIT 변화" → **(1) GC와 통합된 nmethod unloading이 표준. (2) Leyden으로 AOT가 다시 등장하지만 JIT 대체가 아닌 보완 역할.**

### JDK 23+ (참고) — Leyden 본격화

- AOT 캐시 (`-XX:AOTCacheOutput`, `-XX:AOTCache`) 등장 (JDK 24부터 정식).
- 첫 실행에서 컴파일한 결과를 다음 실행에 재사용 → "**JIT의 warmup을 cache로 건너뛴다**" 아이디어.
- 즉, JIT는 사라지지 않지만 **AOT cache + JIT** 조합으로 진화.

### 한 줄 요약표

| JDK | 가장 중요한 변화 | 면접에서 묻기 좋은 한 줄 |
|---|---|---|
| 7 | Tiered 실험 도입 | "옛날엔 -client/-server 둘 중 골랐다" |
| 8 | Tiered 기본 on, CodeCache 240MB | "JIT 양쪽 다 쓰니까 메모리도 5배" |
| 9 | Segmented Code Cache (JEP 197), JVMCI (JEP 243) | "C1/C2 섞임 문제를 영역 분리로 해결" |
| 10 | Graal JIT 실험 (JEP 317) | "C2 대체 시도 시작" |
| 11 | LTS, 큰 변화 없음 | "9의 변화를 안정화한 LTS" |
| 17 | Graal/AOT 제거 (JEP 410) | "OpenJDK는 C1/C2로 회귀, Graal은 GraalVM으로" |
| 21 | Generational ZGC, Leyden 시작 | "nmethod 회수가 GC와 합쳐짐, AOT 재시도" |

---

## ⚖️ 5단계: 트레이드오프 — 옵션 튜닝의 본질

### `-XX:ReservedCodeCacheSize`

| 작게 (~64MB) | 기본 (240MB) | 크게 (512MB ~ 1GB) |
|---|---|---|
| 메모리 ↓ | 일반 웹 서버 적정 | Spring Boot 거대 앱·동적 클래스 많은 앱 |
| Full 위험 ↑ | | 시작 시 reserve 양 ↑ |

**경험칙**: 일반 API 서버는 기본 OK. Spring + Hibernate + 동적 proxy 많으면 512MB 이상.

### `-XX:-TieredCompilation`

| Tiered ON (기본) | Tiered OFF |
|---|---|
| Warmup 빠름 | Warmup 느림 |
| Code Cache 2배 | Code Cache 절반 |
| Profile 수집 비용 | Profile 없음 |
| Peak 성능 동일 | Peak 성능 동일 |

**언제 끄나**: 컨테이너 메모리 제한 빠듯 (512MB limit) + warmup 무관한 batch.

#### 왜 Tiered ON이 warmup 빠른가 — 표만 보면 안 풀리는 핵심

> **warmup = "메서드가 native로 빨라지기까지 걸리는 시간"**. 그 동안은 인터프리터로 느리게 돌아간다.

타임라인으로 비교하면 본질이 보인다.

```
[Tiered OFF (C2 only)]
═══════════════════════════════════════════════════════════════
시간 ──────────────────────────────────────────────────────►
│  인터프리터 (느림, ~50배 느림)             [C2 컴파일 중]
│  10,000번 호출 임계 도달까지              (수십~수백 ms)
│  ~ 수초 ~ 수십 초                         그동안도 인터프리터
└─────────────────────────────────────────────────────────────
                                                       ↑
                                           이 순간 갑자기 빨라짐
                                           (계단형 변화)

[Tiered ON (C1 → C2)]
═══════════════════════════════════════════════════════════════
시간 ──────────────────────────────────────────────────────►
│ 인터프  │ C1 native (그럭저럭 빠름)         │  C2 native (peak)
│ 짧음    │ ↑                                │
│ ~200번  │ 빠르게 도달                       │
│         │ ★ 이 동안 background에서 C2 컴파일 │
└─────────────────────────────────────────────────────────────
            ↑                                  ↑
            "응답 그럭저럭"부터 시작              자연스럽게 최고로
            (부드러운 곡선)
```

→ Tiered OFF는 **"매우 느리다 → 한순간에 최고"**.
→ Tiered ON은 **"곧 그럭저럭 빨라짐 → 점진적으로 최고"**.

체감 응답속도 안정화 시점이 **수십 초 vs 1초 미만**.

#### C1이 효과적인 3가지 이유

**① C1 임계가 50배 낮다 — 더 빨리 트리거**
```
C1 (tier 3): 호출 200
C2 (tier 4): 호출 5,000 ~ 10,000
```
같은 트래픽에서 **C1은 50배 빨리 컴파일 시작**.

**② C1 컴파일이 10배 빠르다**
```
C1: HIR→LIR 단일 패스, 단순 최적화 → 메서드당 수 ms ~ 수십 ms
C2: Sea-of-Nodes 그래프, 반복 패스, 공격적 최적화 → 수십 ms ~ 수백 ms
```
트리거된 후 **native code 만들기까지 시간도 10배 빠름**.

**③ ★ 가장 중요 — C2 대기를 C1이 메운다 (다리 역할)**
```
[Tiered OFF — C2 대기 동안 메서드는 그대로 인터프리터]
인터프리터 (느림) ─────────► [C2 컴파일 중에도 메서드는 인터프리터로 느림]

[Tiered ON — C1이 다리를 놔준다]
인터프 │ C1 native │ ★ 여기 ★
짧음   │           │ C2 컴파일 중에도 메서드는 C1 native로 빠르게 돌아감
                    (C2 완성되면 자동 교체)
```

**C1 = "C2 완성을 기다리는 동안 메서드를 빠르게 돌릴 임시 native code"**.

#### 식당 비유로 한번 더

| | Tiered OFF | Tiered ON |
|---|---|---|
| 인력 | **정식 셰프(C2)만** | **알바(C1) + 셰프(C2)** |
| 셰프가 익히는 동안 | 손님은 음식 못 받음 (= 인터프리터) | 알바가 빠르게 응대 (= C1 native) |
| 셰프 익히고 나면 | 최고 품질 | 자연스럽게 알바와 교대, 최고 품질 |

→ **C1의 본질 = "C2가 준비되는 동안 손님 받아주는 알바"**.

#### 정량적 감각 — 실제 production

웹 서버 단일 endpoint 예시 (대략적 감각):

```
[Tiered OFF]
시작 0초:   P99 200ms (인터프리터)
시작 10초:  P99 200ms (아직 임계 미도달)
시작 20초:  C2 컴파일 시작 — 그래도 P99 200ms
시작 21초:  C2 완성 — P99 5ms (★ 계단형 점프)

[Tiered ON]
시작 0초:    P99 200ms
시작 0.5초:  C1 임계 도달
시작 0.6초:  C1 완성 — P99 20ms (★ 일찍 좋아짐)
시작 10초:   C2 임계 도달
시작 10.3초: C2 완성 — P99 5ms (★ 부드럽게 최고로)
```

→ 사용자 입장에서 **"빠른 응답을 얼마나 일찍 받기 시작했는가"** 가 warmup 품질. Tiered ON은 곡선이 훨씬 일찍·부드럽게 올라간다.

#### 한 줄 결론

> **Tiered ON이 warmup 빠른 진짜 이유**:
> ① C1 임계 50배 낮음 → 빨리 트리거 +
> ② C1 컴파일 10배 빠름 → 빨리 완성 +
> ③ ★ **C2 대기 동안 C1 native가 메서드를 받쳐줌** → 인터프리터 구간 거의 없음.
>
> **C1 = "C2가 준비되는 동안 손님 받아주는 알바"**.

### `-XX:TieredStopAtLevel=N`

`N=1`: tier 1까지만 (단순 C1, no profiling).
- Code Cache 최소.
- Peak 성능 낮음.
- 가장 절약적이지만 단점 큼.

### `-XX:CompileThreshold`

컴파일 임계 조정. 크게 잡으면 컴파일 횟수 ↓, Code Cache 사용 ↓, 그러나 warmup 더 길어짐.

> ⚠️ 표면 옵션값을 외우지 말 것. **"메모리 빠듯 → Tiered 끄거나 size 조정", "warmup이 중요 → Tiered on 유지"** 같은 **결정 룰**만 갖고 있으면 된다.

---

## 📊 6단계: 운영 진단 — production에서 무엇을 보는가

### 1. 현재 상태 스냅샷

```bash
jcmd <pid> Compiler.codecache
```

핵심 보는 곳:
- `used / size` 비율 (각 segment). **80% 넘으면 압박 신호**.
- `compilation: enabled / disabled`. **disabled면 사고**.
- `stopped_count`. **1 이상이면 한 번이라도 멈춤 → 즉시 조사**.

### 2. 컴파일 활동 실시간 추적

```bash
java -XX:+PrintCompilation -jar app.jar
```

출력 한 줄 읽는 법:
```
   142    3 %   4       MyApp::process @ 12 (123 bytes)
   ───   ─── ─── ─       ──────────────  ──   ─────
    │    │   │  │             │          │     │
    │    │   │  │             │          │     bytecode size
    │    │   │  │             │          OSR entry bytecode index
    │    │   │  │             메서드 시그니처
    │    │   │  tier (0=interp, 1~3=C1, 4=C2)
    │    │   flags (% = OSR, n = native, ! = exception)
    │    compile ID
    JVM 시작 후 시간 (ms)
```

### 3. JFR 핵심 이벤트

```bash
jcmd <pid> JFR.start name=cc duration=300s settings=profile filename=cc.jfr
```

봐야 할 이벤트:
- `jdk.CodeCacheStatistics` — 주기적 사용량.
- `jdk.CodeCacheFull` — **가득 참 발생. 보이면 즉시 size 증가**.
- `jdk.Compilation` — 어떤 메서드가 컴파일됐는지.
- `jdk.Deoptimization` — deopt reason까지 — 빈발 시 코드의 다형성 점검.
- `jdk.CompilerInlining` — inlining 결정. "too big" "callee large" 같은 reason 확인.

### 4. 운영 시나리오 매트릭스

| 증상 | 첫 진단 | 가능 원인 |
|---|---|---|
| 시작 후 점진적 응답 ↓ | `jcmd Compiler.codecache` | Code Cache full |
| 컴파일이 자꾸 멈춤 | `stopped_count` 추세 | size 부족 + flushing thrash |
| Hot reload 환경 점진 느려짐 | NMT의 Code 영역 | ClassLoader 누수 + nmethod 누적 |
| Deopt 분당 수백 건 | `jdk.Deoptimization` | 호출 사이트 megamorphic |
| Spring Boot 대형 앱 OOM 없이 느려짐 | Compiler.codecache | size 240MB로 부족 |

### 5. 시나리오 1: "CodeCache is full" — 대형 Spring Boot

```
증상:
  로그: "CodeCache is full. Compiler has been disabled."
  P99 latency 점진 ↑.

진단:
  $ jcmd <pid> Compiler.codecache | grep -A 1 compilation
  compilation: disabled (not enough memory)
  stopped_count=1

조치:
  -XX:ReservedCodeCacheSize=512m
  + 동적 클래스 audit (AOP unnecessary proxy 제거)
  + Lambda capture 패턴 점검
```

### 6. 시나리오 2: Deopt 폭주 — Megamorphic call site

```
증상:
  JFR jdk.Deoptimization 분당 수백 건.
  reason: class_check 다수.

원인:
  Strategy 패턴으로 한 호출 사이트가 5+ 구현체 받음.
  C2가 monomorphic 가정 inline → 매번 깨짐.

조치:
  - sealed class로 구현체 제한 → CHA 안정
  - 일부 사이트는 if-else로 평탄화
  - -XX:+PrintInlining으로 실패 메시지 확인
```

---

## ⚔️ 7단계: 면접 깊이별 질문 — 무엇을 묻고 무엇을 안 묻나

여기가 이 문서의 두 번째 핵심. **무엇이 합리적 면접 질문이고, 무엇이 컴파일러 작성자만 알 수준인지** 구분해야 한다.

### Tier A: 표면 (안 묻는 수준)

> 외워서 답하면 의미 없는 질문. 시니어 면접에서는 안 묻거나 패스.

- "ReservedCodeCacheSize 기본값은?"
- "C1 tier 3 임계는?"
- "Sea-of-Nodes의 노드 타입은?"
- "nmethod 구조체 필드를 말해보라"

→ **답할 줄 알아도 점수 안 됨**. 검색하면 나오는 정보.

### Tier B: 개념 이해 (3~5년차에게 묻는 수준)

> 메커니즘과 trade-off를 이해했는지 확인하는 질문. **여기를 확실히 답해야 한다**.

#### B1. JIT는 무엇이고 왜 필요한가
> 인터프리터는 시작 빠르나 매번 비용. AOT는 빠르나 runtime 정보 못 씀.
> JIT = 인터프리터로 시작 → hot path만 native code로 컴파일.
> **결정적 장점은 runtime profile 기반 최적화** (monomorphic inline 등).
> AOT가 가정만 하는 것을 JIT는 알고 한다.

#### B2. C1과 C2는 왜 두 개인가
> 컴파일 비용과 최적화 품질의 trade-off.
> C1 = 빠른 컴파일, 약한 최적화 → warmup 단축.
> C2 = 무거운 컴파일, 공격적 최적화 → peak 성능.
> 하나만 쓰면 한쪽을 잃음. Tiered Compilation이 둘을 결합.

#### B3. Tiered Compilation의 비용은
> Code Cache 2배 사용 (C1, C2 결과 동시 보유).
> Profile 수집 비용 (instrumented C1 코드 실행 비용).
> 이게 JDK 9에서 Segmented Code Cache 필요해진 이유.

#### B4. Code Cache가 왜 별도 영역인가
> 세 가지: (1) executable 메모리 분리 (보안), (2) GC와 회수 정책 다름, (3) 32-bit relative jump 가정.

#### B5. 컴파일은 어떻게 트리거되나 — 누가 "이 메서드 hot"이라고 판단하나
> **자기보고 시스템**. 별도 감시 스레드 없음.
> - 인터프리터 stub과 C1 tier 2/3 native code 안에 **counter inc + 임계 비교 로직이 박혀 있음**.
> - 실행하던 application thread가 임계 도달 시점에 **자기가 직접** `CompileBroker.enqueue(task)` 호출.
> - enqueue 후에도 같은 thread는 block 안 하고 계속 인터프리터로 실행.
> - 비동기로 별도 Compiler Thread가 큐에서 task pickup → 컴파일 → Code Cache에 nmethod 배치 → Method._code 패치.
> - 다음 호출부터 자동으로 native 진입.
>
> Compiler Thread는 어떤 코드도 감시·트래킹하지 않는 **큐 일꾼**.

#### B7. Code Cache는 어떻게 "조회"되는가 (이름 함정 질문)
> 핵심을 뒤집어야 하는 질문. **Code Cache는 조회하는 캐시가 아님**.
> CPU가 그 메모리 영역 안으로 직접 점프해서 instruction을 한 줄씩 실행함. `gcc` 결과물의 `.text` 영역과 본질적으로 같음.
>
> 호출 메커니즘:
> 1. Method 객체의 `_code` 필드(한 워드 포인터)를 읽음.
> 2. `call [_code]` — 그 주소로 점프.
> 3. Code Cache 안의 nmethod에서 바로 실행.
>
> JIT 컴파일 완료 = `_code` 포인터를 nmethod 주소로 atomic write. **포인터 바꿔치기 한 번**으로 그 다음 호출부터 native 실행.
>
> 진짜 lookup 같은 동작은 **Inline Cache** — 호출 사이트마다 박힌 dispatch 캐시. 이건 Code Cache 자체가 아니라 그 안에 든 메커니즘.

#### B8. Profiled / Non-profiled segment 차이는 (이름 함정 질문)
> 이름이 헷갈리지만 기준은 **"profile 데이터를 입력으로 썼느냐"가 아니라 "이 native code가 실행되며 profile을 측정하느냐"**.
> - **Profiled** = 컴파일된 코드 자체에 instrumentation 박힘 (C1 tier 2/3).
> - **Non-profiled** = 측정 로직 없는 깨끗한 코드 (C2 tier 4 + C1 tier 1).
>
> C2는 profile을 **소비**할 뿐 결과 코드에는 측정 없음 → Non-profiled.
> 본질은 **수명 분리** — short-lived(Profiled)와 long-lived(Non-profiled)를 segment로 가른 것. JEP 197의 핵심 의도.

#### B9. Code Cache가 가득 차면 무엇이 일어나는가
> "CodeCache is full" → Compile Broker 멈춤 → 새 hot method는 인터프리터 영구 실행 → 5~10배 성능 저하.
> UseCodeCacheFlushing이 on이면 sweeper가 cold 회수 시도.

### Tier C: 운영 마스터 (시니어/리드 수준)

> 실제 production에서 한 번이라도 만난 사람만 답하는 질문.

#### C1. JDK 8과 17의 JIT 차이를 설명하라
> 8: Tiered 기본 on, Code Cache 240MB. 그러나 단일 영역으로 fragmentation 있음.
> 9: Segmented Code Cache (JEP 197). 수명별 segment 분리.
> 10~16: Graal JIT 실험 등장.
> 17: JEP 410으로 Graal/AOT OpenJDK에서 제거. 원하면 GraalVM으로.
> 17부터 nmethod unloading이 GC와 통합되기 시작 → STW 영향 ↓.

#### C2. "CodeCache is full" 경고가 나왔다. 어떻게 진단하고 해결하나
> 1. `jcmd Compiler.codecache`로 `stopped_count`와 segment별 used 확인.
> 2. JFR `jdk.CodeCacheFull`로 시점 특정.
> 3. 원인 분류:
>    - 일반 부족 → `ReservedCodeCacheSize` 증가
>    - 동적 클래스 누적 → AOP/proxy/lambda audit
>    - Hot reload 환경 → ClassLoader 누수 같이 의심
> 4. 모니터링 — Prometheus jvm_jit 지표, JFR 상시.

#### C3. Deopt가 빈발한다. 무엇을 의심하고 어떻게 해결하나
> 가장 흔한 원인: 한 호출 사이트가 megamorphic이 됨 (구현체 3개 이상).
> 진단: JFR `jdk.Deoptimization`의 reason 분포.
> 해결:
> - Strategy 패턴 남발하는 곳 sealed class로 제한 → CHA 안정.
> - 핫 패스에서 reflection/dynamic proxy 줄임.
> - `-XX:+PrintInlining`으로 inline 실패 메시지 확인.

#### C4. 메모리 제한 컨테이너에서 JIT 어떻게 튜닝하나
> 우선순위:
> 1. `ReservedCodeCacheSize` 적정 추정 (jcmd로 사용량 측정 후 1.5배).
> 2. Warmup 무관하면 `-XX:-TieredCompilation` 검토 (Code Cache 절반).
> 3. 그래도 모자라면 `-XX:TieredStopAtLevel=1` (peak 손해 감수).
> 4. AOT cache (JDK 24+) 검토.

#### C5. Tiered Compilation을 끄면 어떤 일이 일어나는가
> Code Cache 사용량 ≈ 절반 (Profiled segment 거의 안 씀).
> Warmup 느려짐 (인터프리터 → C2 직행, C2가 무거워서 시작 응답 느림).
> Peak 성능 동일.
> 적합한 경우: 메모리 제한 강한 환경 + warmup 무관 batch.

### Tier D: 안 묻는 수준 (컴파일러 작성자 영역)

> 시니어 면접에서도 안 묻는다. 만약 묻는다면 잘못된 면접.

- Sea-of-Nodes의 노드 종류와 변환 단계
- C2의 register allocation 알고리즘 (linear scan vs graph coloring)
- Escape analysis의 IFDS 변형
- IR 패스 순서와 fixed-point 종결 조건
- nmethod의 메모리 layout과 patch 가능 영역

이걸 묻는 면접 = OpenJDK 컨트리뷰터 채용 면접. 일반 백엔드 채용에서는 부적절.

### 꼬리질문 트리 — 압박 면접 시뮬레이션

#### Q. "JIT 컴파일된 코드는 어디 저장되나요?"
- A: Code Cache. Heap도 Metaspace도 아닌 별도 영역.

##### 🪝 그 코드는 어떻게 호출되나? Redis처럼 조회해서 가져오나?
- A: 아니다. **조회 자료구조가 아닌 executable memory 영역**. CPU가 그 주소로 직접 점프해서 실행한다. `gcc` 결과물의 `.text` 영역과 같은 성격.
- 메커니즘: Method 객체의 `_code` 필드(포인터 한 워드)를 읽어 `call [_code]`로 점프. JIT 완료는 그 포인터를 nmethod 주소로 atomic write로 바꿔치는 것. lookup 자료구조 없음.

##### 🪝 그러면 "Cache"는 왜 Cache인가? lookup 안 하는데 왜 이름이 Cache지?
- A: `Cache`의 일반적 의미 — **"임시 보관소(storage cache)"**. Redis 같은 lookup cache가 아니라, nmethod가 deopt/cold sweep으로 회수될 수 있는 임시 저장 영역이라서 그렇게 부른다.
- 진짜 lookup 비슷한 동작은 **Inline Cache** — 호출 사이트마다 박힌 dispatch 캐시. 이건 Code Cache 자체가 아니라 Code Cache 안에 든 별도 메커니즘.

##### 🪝 왜 Heap에 두면 안 되나?
- A: 세 가지. (1) executable 메모리는 보안상 분리 (W^X), (2) native code의 회수 정책이 일반 객체와 달라 별도 sweeper 필요, (3) 32-bit relative jump를 위해 4GB 안에 모여야 함.

##### 🪝 그럼 그 Code Cache는 어떻게 구성돼 있나?
- A: JDK 9 이후 3 segment. Non-method (JVM stub), Profiled (C1 결과), Non-profiled (C2 결과). 수명/특성이 달라 분리.

##### 🪝 왜 그렇게 segment를 나눴나?
- A: JDK 8까지 단일 영역에서 C1(short-lived)와 C2(long-lived)가 섞여 fragmentation과 sweep 비효율 발생. JEP 197로 영역 분리.

##### 🪝 그러면 segment 분리는 무엇이 좋아지나?
- A: short-lived만 자주 sweep, long-lived는 안정. I-cache locality도 향상.

##### 🪝 Profiled segment에는 C1 결과만, Non-profiled에는 C2 결과만 들어가나?
- A: 정확히는 아님. **기준은 "측정 로직(instrumentation) 포함 여부"**.
  - Profiled = C1 tier 2/3 (코드에 측정 박힘).
  - Non-profiled = C2 tier 4 **+ C1 tier 1** (둘 다 측정 없음).
- C2가 Non-profiled인 이유: C2는 profile을 **입력으로 소비**하지만 결과 코드에는 측정 없음. "profile을 썼지만 더는 만들지 않는다".

##### 🪝 왜 이렇게 나눴나, 그냥 컴파일러별로(C1/C2) 가르면 안 되나?
- A: 본질이 **수명 분리**라서 그렇다. C1 tier 1은 단순 컴파일이라 short-lived가 아닌 long-lived → Non-profiled로 가는 게 맞음. 컴파일러 기준이 아니라 **수명 + 측정 여부** 기준이라 segment 효율이 더 좋다.

#### Q. "그 컴파일은 누가 트리거하나요? 컴파일러 스레드가 감시하고 있다가 컴파일하나요?"
- A: 아니다. **별도 감시 스레드 없음**. 인터프리터 stub과 tier 2/3 C1 코드 안에 counter inc + 임계 비교 로직이 박혀 있고, **실행하던 application thread가 자기가 직접** CompileBroker 큐에 task를 enqueue한다.
- Compiler thread는 큐 pickup만 하는 일꾼.

##### 🪝 application thread가 enqueue하면 그 thread는 컴파일 끝날 때까지 기다리나?
- A: 아니다. enqueue 후 **계속 인터프리터로 실행**. 컴파일은 비동기. 끝나면 Method._code가 atomic write로 갱신되고, **다음 호출 시점부터** 자동으로 native로 점프. 호출자 입장에서는 `call [Method._code]` 한 줄이라 포인터가 바뀐 줄도 모름.

##### 🪝 tier 3에서 C2로 넘어가는 트리거도 같은 방식인가?
- A: 같다. C1 tier 2/3 결과 코드 안에도 instrumentation이 박혀 있어서 (그래서 Profiled segment에 들어감), 그 코드가 실행되면서 자기 자신을 C2로 승급 신청한다. 외부 감시 없음.

#### Q. "Tiered Compilation이 뭔지 설명해보세요"
- A: C1과 C2를 한 JVM에서 모두 활용. 인터프리터 → C1 (tier 1/2/3) → C2 (tier 4) 순으로 hot 메서드를 승급.

##### 🪝 왜 5단계인가, 그냥 C1 → C2면 안 되나?
- A: C1도 3가지로 나뉜다. tier 1 (no profile, C2 큐 막혔거나 단순한 경우), tier 2 (호출 카운터만), tier 3 (full profile, 가장 느린 C1). profile 비용 vs 정확도의 점진적 trade-off.

##### 🪝 Tiered의 비용은?
- A: Code Cache 2배 (C1, C2 결과 동시). Profile 수집 overhead. 그래서 JDK 9에서 Segmented Code Cache가 필요해졌다.

##### 🪝 Tiered를 끄면 어떻게 되나?
- A: Code Cache 절반. Warmup 느림. Peak 성능 동일. 메모리 빠듯 + warmup 무관 환경에 적합.

#### Q. "JDK 8과 21을 비교해 JIT에서 무엇이 가장 바뀌었는지 설명해보세요"
- A: 세 가지 큰 변화.
  1. **JDK 9의 Segmented Code Cache**: C1/C2 결과 분리로 fragmentation 해결.
  2. **JDK 17의 Graal/AOT 제거 (JEP 410)**: OpenJDK 본체는 C1/C2로 회귀, GraalVM은 별도 프로젝트로.
  3. **JDK 21의 GC 통합 nmethod unloading**: 별도 Sweeper thread 시대 끝, GC와 함께 concurrent로 회수. STW 영향 거의 사라짐.

##### 🪝 Leyden은 뭔가?
- A: JIT를 대체하는 게 아니라 보완. 첫 실행에서 컴파일한 결과를 cache해 다음 실행의 warmup을 줄이는 시도. JDK 24부터 AOT cache 정식.

#### Q. "production에서 'CodeCache is full' 메시지를 본 적 있다고 가정해봅시다. 무엇부터 보겠어요?"
- A: 다섯 단계.
  1. `jcmd Compiler.codecache`로 segment별 used / size + `stopped_count` 확인.
  2. JFR로 시점/주기 확인 (`jdk.CodeCacheFull`).
  3. 원인 분류:
     - 일반 부족 → size 증가
     - 동적 클래스 누적 → 코드 audit (AOP, lambda, reflection)
     - ClassLoader 누수 의심
  4. 즉시 조치: `-XX:ReservedCodeCacheSize` 증가 + 재시작.
  5. 장기 모니터링 셋업.

##### 🪝 size만 무한정 늘리면 안 되나?
- A: 안 됨. (1) 가상 메모리 사용 ↑ → 컨테이너 limit 압박. (2) reserve가 클수록 32-bit jump 범위 보장 어려움. 일반적으로 512MB ~ 1GB가 거대 앱의 sweet spot.

##### 🪝 만약 코드의 다형성이 너무 많아서 컴파일이 비정상적으로 많은 거라면?
- A: Deopt 빈발 의심. JFR `jdk.Deoptimization`으로 reason 분포 확인. megamorphic call site 식별 → sealed class, if-else 평탄화, 핫 패스에서 reflection 제거.

---

## 🔗 다음 단계

- → [05. Direct Memory](./05-direct-memory.md): Off-heap NIO buffer
- → [06. GC bookkeeping](./06-gc-bookkeeping-and-others.md): Card Table, RSet, Mark Bitmap
- ← [03. Stack & PC & Native](./03-stack-pc-native.md): Per-thread 메모리
- ← [02. Metaspace](./02-metaspace-and-class-space.md): Class 메타데이터
- 관련: 추후 03-execution-engine 챕터 — C1/C2 내부 동작과 최적화 기법 상세

## 📚 참고

- **JEP 197 Segmented Code Cache**: https://openjdk.org/jeps/197
- **JEP 243 JVMCI**: https://openjdk.org/jeps/243
- **JEP 317 Experimental Graal JIT**: https://openjdk.org/jeps/317
- **JEP 410 Removal of AOT/Graal JIT**: https://openjdk.org/jeps/410
- **JEP 439 Generational ZGC**: https://openjdk.org/jeps/439
- **Oracle — HotSpot VM Performance Enhancements**: https://docs.oracle.com/en/java/javase/21/vm/java-hotspot-virtual-machine-performance-enhancements.html
- **JITWatch (시각화)**: https://github.com/AdoptOpenJDK/jitwatch
- **Aleksey Shipilëv — JVM Anatomy Quarks**: https://shipilev.net/jvm/anatomy-quarks/
- **Project Leyden 개요**: https://openjdk.org/projects/leyden/
