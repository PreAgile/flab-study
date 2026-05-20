# 02-04. Code Cache & JIT Compiler — JVM 성능의 심장

> Code Cache는 단순한 메모리 영역이 아니다. **JIT 컴파일러(C1, C2)가 만들어낸 native code의 보관소**이자, JVM이 "느린 인터프리터 언어"가 아닌 "C에 근접한 빠른 언어"로 작동하게 만드는 핵심 인프라다.
> 그래서 이 챕터의 진짜 주인공은 **JIT 컴파일러**. Code Cache는 JIT의 산출물을 담는 그릇.
> Production에서 `CodeCache is full` 한 줄이 뜨면 무엇이 무너지는가, 그것이 시니어의 진짜 질문.

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

> **"Code Cache는 JIT가 만든 native code를 담는 executable 메모리 영역이다. 인터프리터 → C1 → C2로 hot 메서드가 자기보고로 승급되고, 결과 nmethod의 주소로 CPU가 직접 점프해서 실행한다 — lookup 아님."**

이 한 문장에서 모든 답변이 출발한다.

### 6개 가지 — 순서를 외운다

```
                                [ROOT: Code Cache = JIT 산출물의 executable mem]
                                                      │
          ┌─────────────┬─────────────┬─────────────┬─────────────┬─────────────┬─────────────┐
          │             │             │             │             │             │             │
          ①             ②             ③             ④             ⑤             ⑥
         WHY           WHAT           HOW           내부           운영           진화
      JIT 본질      별도 영역      자기 보고     IC + Deopt      진단         JDK 7 → 21
                   3 segment                     (런타임)       시나리오
          │             │             │             │             │             │
          ▼             ▼             ▼             ▼             ▼             ▼

      인터프리터    Non-method     카운터          IC 4단계       Compiler.      Tiered
      AOT vs JIT   Profiled        tier3 → C2      nmethod        codecache      Segmented
      C1 + C2      Non-profiled    비동기 큐       Deopt + CHA    PrintCompile   JVMCI / Graal
      Tiered       "조회 X"        + pickup        atomic 패치    JFR            Leyden
```

### 가지별 핵심 키워드 (각 가지 3개씩만)

| 가지 | 키워드 1 | 키워드 2 | 키워드 3 |
|---|---|---|---|
| **① WHY JIT** | 인터프리터/AOT/JIT 비교 | runtime profile 활용 | C1 + C2 (warmup vs peak) |
| **② WHAT Code Cache** | Executable memory (W^X) | 3 segment (JDK 9+) | "조회 X, 직접 점프" |
| **③ HOW 자기보고** | counter + 임계가 코드에 박힘 | application thread가 enqueue | Method._code atomic patch |
| **④ 내부 IC/Deopt** | Inline Cache (mono/bi/mega) | Deoptimization (CHA, speculative) | nmethod 회수 |
| **⑤ 운영** | jcmd Compiler.codecache | "CodeCache is full" 도미노 | Deopt 빈발 진단 |
| **⑥ 진화** | JDK 8 Tiered ON, 240MB | JDK 9 Segmented (JEP 197) | JDK 17 Graal 제거, Leyden |

### 면접 답변 흐름

> 면접관 질문 → 루트 문장 → 질문에 맞는 가지 1개 선택 → 그 가지의 키워드 3개 순서대로 설명 → 듣는 사람의 관심에 따라 인접 가지로 확장

---

## 1. 가지 ①: WHY — JIT는 왜 필요한가

### 1.1 핵심 질문

> "Java는 왜 JIT을 쓰는가? 인터프리터만, 또는 AOT만 쓰면 안 되는가?"

### 1.2 키워드 1 — 인터프리터 vs AOT vs JIT

```
[순수 인터프리터]        [AOT 컴파일]              [JIT (Java의 선택)]
─────────────────       ──────────────            ─────────────────
빠른 시작                 컴파일 후 배포              인터프리터로 시작
실행은 느림               실행 매우 빠름              hot path만 컴파일
profile 정보 없음         profile 못 씀              ★ runtime profile 활용

대표: 초기 BASIC           대표: C/C++, Go            대표: HotSpot JVM, V8
```

**JIT가 AOT보다 결정적으로 유리한 한 가지**: **runtime profile 기반 최적화**.
- 어느 분기가 자주 도는지, 어느 타입이 자주 등장하는지를 알고 컴파일
- → **AOT가 가정만 하는 것을 JIT는 알고 한다**
- 대표 예: monomorphic inline (한 가지 구현만 본 호출 사이트는 직접 점프)

### 1.3 키워드 2 — C1 vs C2 (왜 두 개인가)

```
[C1만 사용 시]                       [C2만 사용 시]
빠른 컴파일 → 빠른 warmup            느린 컴파일 → 느린 warmup
But, 최적화 약함 → peak ↓             But, 최적화 강함 → peak ↑

웹 서버 시작 5초만에 응답 OK          웹 서버 시작 30초 동안 인터프리터
But, 처리량 30% 손해                  But, 안정화 후 처리량 100%
```

**둘 다 가지면**: 시작은 C1 (warmup 빠름), 안정화는 C2 (peak 최적). 이게 **Tiered Compilation의 본질**.

| | C1 (Client) | C2 (Server) |
|---|---|---|
| IR | HIR → LIR | Sea-of-Nodes 그래프 |
| 패스 | 단일 패스 | 반복 최적화 |
| 최적화 | constant folding, simple inline | aggressive inline, escape analysis, loop unroll, vectorize, range check elim |
| profile | tier 2/3에서 측정 코드 삽입 | profile을 가정으로 소비 (speculative) |
| 시간 | 메서드당 수 ms~수십 ms | 수십 ms~수백 ms |

**대가**: Code Cache 사용량 ≈ 2배 (C1, C2 결과 동시 보유). 그래서 JDK 9에서 segment로 나눠 관리.

### 1.4 키워드 3 — Tiered Compilation 5 단계

```
Tier 0:  Interpreter                  ← 모든 메서드 시작점
   │ 호출 카운터 도달
   ▼
Tier 1:  C1 (no profiling)            ← C2 큐가 비거나 trivial 메서드
Tier 2:  C1 (limited profiling)       ← 호출 카운터만 측정
Tier 3:  C1 (full profiling)          ← 분기·타입·null 풀 profile (느림)
   │ 충분한 profile 데이터 수집
   ▼
Tier 4:  C2 (fully optimized)         ← 최종 형태, profile 기반 공격적 최적화
```

→ "한 메서드는 인터프리터 → C1 (3가지 sub-tier) → C2 순으로 승급"

### 1.5 통역사 비유

| 단계 | 비유 | JVM 실체 |
|---|---|---|
| Bytecode 한 줄씩 실행 | **동시 통역사** | Interpreter |
| 자주 쓰는 문장 미리 번역 | **번역 초안** (빠름, 살짝 어색) | C1 |
| 베스트셀러는 정식 출판 | **번역서** (시간 많이, 완벽) | C2 |
| 번역본 보관소 | **창고** (한정 공간) | Code Cache |

> 통역(인터프리터)은 준비 시간 0, 매번 비용. 출판(C2)은 준비 비용 큼, 한 번 만들면 영원히 빠름. 그래서 **자주 쓰는 것만 번역** (= JIT의 본질).

---

## 2. 가지 ②: WHAT — Code Cache의 위치와 구조

### 2.1 핵심 질문

> "Code Cache는 어디에 있고 왜 별도인가요? Heap에 두면 안 되나요?"

### 2.2 키워드 1 — 별도 영역인 본질적 이유 3가지

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

세 줄로: **(1) 보안 (2) GC 분리 (3) 점프 최적화**.

### 2.3 키워드 2 — 3 segment (JDK 9+, JEP 197)

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

**이름 함정 — Profiled / Non-profiled의 진짜 의미**:

> "profile을 *썼느냐*"가 아니라 "이 native code가 실행되면서 profile을 *측정하느냐*"

| 용어 | 정확한 의미 |
|---|---|
| **Profiled** | 컴파일된 native code 자체에 **측정 코드 박힘** (실행하며 측정) |
| **Non-profiled** | 컴파일된 native code에 **측정 로직 없음** (clean, 빠르게 실행만) |

**그래서 C2는 Non-profiled** — C2는 C1 tier 3가 모아둔 profile을 **입력으로 소비**하지만, 결과 코드에는 측정 로직이 없다. C1 tier 1도 Non-profiled (profile 수집 일부러 생략).

**Tier → Segment 매핑**:

```
Tier 0  Interpreter         → Code Cache 미저장
Tier 1  C1, profile 없음     → Non-profiled  ★
Tier 2  C1, 카운터만 측정    → Profiled
Tier 3  C1, full profile     → Profiled      ★ (가장 흔함)
Tier 4  C2                   → Non-profiled  ★
```

→ 본질은 **수명 분리** — short-lived(Profiled)와 long-lived(Non-profiled)를 segment로 가른 것.

### 2.4 키워드 3 — "조회하는 캐시"가 아니다 (이름 함정)

이름 때문에 거의 다 처음에 이런 그림을 그린다. **이게 틀린 모델**:

```
[잘못된 모델 — Redis/Memcached 비유]    [실제 — 직접 실행 모델]
─────────────────────────────────       ──────────────────────────
호출 발생                                호출 발생
   ↓                                       ↓
"native code 어디 있지?" lookup          Method 객체의 _code 포인터 읽음
   ↓                                       ↓
key로 찾아서 fetch                       CPU의 PC를 그 주소로 점프
   ↓                                       ↓
가져와서 어딘가에서 실행                  ★ Code Cache 안에서 직접 실행
                                          (그 메모리가 코드 그 자체)
```

> **Code Cache의 메모리 = CPU가 실행하는 instruction 자체.**
> 어디로 복사·로드해서 실행하는 게 아니라, **CPU의 instruction pointer가 Code Cache 영역 안으로 들어가서 한 줄씩 읽어 실행한다.**

`gcc` 결과물의 `.text` 영역과 본질적으로 같은 성격. JVM은 단지 그걸 **runtime에 만들어 넣을 뿐**.

**호출 메커니즘**:
1. JIT 컴파일 완료 → Code Cache의 어떤 주소(예 0x7fa1b8001234)에 native instruction 배치
2. Method 객체의 `_code` 필드를 atomic write로 패치 → `Method._code = 0x7fa1b8001234`
3. 다음 호출: caller code의 `call [Method._code]` → CPU가 그 주소로 jump → Code Cache 안에서 실행
4. `ret`로 caller에 복귀

**lookup 없음, 자료구조 없음**. 포인터 한 번 dereferencing이 호출의 전부.

**그럼 왜 "Cache"라는 이름?**: `Cache` = "임시 보관소"라는 일반적 의미. nmethod는 영구가 아님 — deopt/cold sweep으로 회수됨. **lookup cache가 아니라 storage cache**.

---

## 3. 가지 ③: HOW — 자기보고 컴파일 트리거

### 3.1 핵심 질문

> "JIT 컴파일은 누가 트리거하나요? 컴파일러 스레드가 감시하나요?"

### 3.2 키워드 1 — 자기보고 시스템 (감시 시스템 아님)

처음 보면 거의 다 "감시자 모델"을 상상한다. **틀린 모델**.

```
[잘못된 모델 — 감시자 모델]              [실제 — 자기보고 모델]
─────────────────────────                ─────────────────────────
   ┌──────────────┐                       [실행 중인 코드]
   │ Compiler     │ 관찰                    ↓
   │ Threads      │ ──→ [실행 코드]         "내가 N번 호출됨"
   └──────────────┘ 트래킹                  ↓ counter inc (코드에 박힘)
                                            ↓ 임계 비교
                                            ↓ "신고합니다"
                                         [CompileBroker 큐]
                                            ↓ 비동기 pickup
                                       [Compiler Thread (일꾼)]
```

> **별도 감시 스레드는 없다.**
> 인터프리터·C1 tier 2/3 코드 자체에 **counter inc + 임계 비교 + 큐 등록 로직이 박혀 있고**, 그 코드를 실행하던 application thread가 직접 task를 enqueue.
> Compiler thread는 큐에서 task만 꺼내 컴파일하는 **일꾼**.

### 3.3 키워드 2 — 두 종류 카운터 + step-by-step 흐름

HotSpot은 Method 객체마다 두 카운터를 유지 (값은 인터프리터/tier 2/3 코드가 inc).

```
1. Invocation Counter — 메서드 진입 시 +1
   임계 도달 → 메서드 전체 컴파일 (일반 컴파일)

2. Back-edge Counter — 루프 백워드 점프마다 +1
   임계 도달 → 메서드 실행 중에도 컴파일 시작
   = OSR (On-Stack Replacement)
   거대 루프 한 번 안에서 hot이 되는 경우 대비
```

표면 숫자(C1 200, C2 5,000)는 외울 필요 없다. **두 종류 카운터 + 코드에 박힌 inc/check가 신고**가 핵심.

**자기보고 흐름**:
```
[Application Thread가 메서드 X 실행 중]
   ↓
1. 인터프리터로 X 진입
2. counter++ ← 인터프리터 stub에 박힌 명령
3. if (counter > threshold) ← 역시 stub에 박힌 비교
4. ★ application thread 자기가 직접 CompileBroker.enqueue(task)
5. enqueue 후에도 같은 thread는 계속 인터프리터로 X 실행 (block 안 함!)
   ─────── 비동기로 별도 thread에서 ────────
6. C1 Compiler Thread가 큐에서 task pickup
7. C1 컴파일 (수 ms ~ 수십 ms)
8. nmethod → Code Cache의 Profiled segment에 배치
9. Method._code 포인터를 atomic write로 nmethod 주소로 교체
   ─────── application thread 입장 ────────
10. 다음 X 호출 시 call [Method._code] → nmethod 주소로 자동 점프
```

**tier 3 → C2 승급도 같은 원리**: tier 3 코드 안에도 instrumentation이 박혀 있어서(그래서 Profiled segment), 그 코드가 실행되면서 **자기 자신을 C2로 승급 신청**.

### 3.4 키워드 3 — Method._code 패치 (포인터 바꿔치기)

호출 메커니즘의 핵심은 단 한 줄:

```
[컴파일 전]
  Method._code = interpreter_entry_address
      ↑ 호출 시 인터프리터 진입점으로 점프

[컴파일 완료 후, atomic write]
  Method._code = nmethod_entry_address (Code Cache 안의 주소)
      ↑ 호출 시 native code 진입점으로 점프
```

호출자가 하는 일은 항상 같다 — `call [Method._code]`. **달라지는 건 그 포인터가 가리키는 주소뿐**. lookup도, 디스패치 테이블 검색도 없음.

**Compile Broker의 역할**:
- task 큐를 관리하는 단순 컴포넌트. 어떤 코드도 감시하지 않음.
- Compiler thread 수: `-XX:CICompilerCount` (기본 ≈ `log2(cpu) + 1`).
- 컴파일은 백그라운드, application thread 블록 안 됨.

---

## 4. 가지 ④: 내부 메커니즘 — Inline Cache & Deoptimization

### 4.1 핵심 질문

> "JIT 컴파일된 native code 안에서 가상 호출은 어떻게 처리되나요? C2의 가정이 깨지면?"

### 4.2 키워드 1 — Inline Cache (호출 사이트 진화)

```java
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

**Inline Cache의 위치**:
```
Code Cache 안의 한 메서드 (caller.foo의 nmethod)
   │ 안쪽 어딘가에 invokevirtual 호출 사이트
   ▼
[Inline Cache slot — patch 가능한 instruction 영역]
   if (receiver.klass == ArrayList) jump ArrayList.add 직접
   else fallback to slow path
```

- IC = **각 호출 사이트마다 dispatch 정보를 캐시**.
- monomorphic이면 1워드 비교 + 직접 점프 (캐시 hit).
- 다른 타입 등장 시 IC 업데이트 또는 megamorphic vtable lookup.

→ **IC는 진짜 캐시 동작이지만, Code Cache 자체가 아니라 Code Cache 안의 호출 사이트에 박힌 별도 메커니즘**.

**시니어 관점**: 같은 호출 사이트가 `ArrayList`와 `LinkedList` 둘 다 받으면 inline이 깨진다. **다형성 남발하면 JIT가 손 못 댄다**.

### 4.3 키워드 2 — Deoptimization (C2가 자기 결과를 버릴 때)

C2는 "**낙관적 가정**"으로 공격적 최적화. 가정이 깨지면 native code 폐기.

**가정의 종류**:
1. **CHA (Class Hierarchy Analysis)**: "이 메서드는 monomorphic" → 새 subclass 로드되면 깨짐.
2. **Speculative type guess**: "이 변수는 99% Integer" → 다른 타입 등장 시 깨짐.
3. **Uncommon branch**: "이 if는 거의 false" → true 분기 도달 시 깨짐.
4. **JVMTI class redefinition**: 디버거가 클래스 재정의.

**Deopt 흐름**:
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

### 4.4 키워드 3 — 주요 C2 최적화 (개념만)

| 최적화 | 의미 | 한 줄 효과 |
|---|---|---|
| **Aggressive Inlining** | monomorphic 가상 호출도 inline | 호출 비용 0 + 다른 최적화 확장 |
| **Escape Analysis** | 객체가 메서드 밖으로 안 나가면 분석 | scalar replacement 가능 |
| **Scalar Replacement** | EA 결과로 객체를 안 만들고 필드만 변수로 | heap 할당 완전 제거, GC 압박 ↓ |
| **Loop Unrolling** | 루프 본체를 N번 복사 | 오버헤드 ↓ + vectorization 가능 |
| **Range Check Elimination** | 배열 bounds check 제거 | 단순 배열 루프 30~50% ↑ |
| **Vectorization (SIMD)** | 한 명령으로 여러 데이터 처리 (AVX, NEON) | 4~8배 빨라짐 |
| **Speculative Compilation** | profile을 확률적 가정으로 받아 공격적 최적화 | 가정 깨지면 deopt |

**시니어 신호**: JFR `jdk.Deoptimization` 분당 수백 건 → 코드의 다형성 패턴이 JIT를 괴롭히는 중. Strategy 패턴 남발, reflection, dynamic proxy 살펴봐야 함.

> ⚠️ **면접에서 안 묻는 영역**: Sea-of-Nodes 노드 종류, IR 변환 단계, register allocation 알고리즘 — 컴파일러 작성자 수준.

---

## 5. 가지 ⑤: 운영 — 시니어 진단

### 5.1 핵심 질문

> "Code Cache 관련 문제를 어떻게 진단하고 해결하나요?"

### 5.2 키워드 1 — 진단 도구 (jcmd / PrintCompilation / JFR)

```bash
# 현재 상태 스냅샷
jcmd <pid> Compiler.codecache
```
보는 곳:
- `used / size` 비율 (각 segment). **80% 넘으면 압박 신호**.
- `compilation: enabled / disabled`. **disabled면 사고**.
- `stopped_count`. **1 이상이면 한 번이라도 멈춤 → 즉시 조사**.

```bash
# 컴파일 활동 실시간 추적
java -XX:+PrintCompilation -jar app.jar
```
출력 한 줄:
```
   142    3 %   4       MyApp::process @ 12 (123 bytes)
   ───   ─── ─── ─       ──────────────  ──   ─────
    │    │   │  │             │          │     bytecode size
    │    │   │  │             │          OSR entry bci
    │    │   │  │             메서드 시그니처
    │    │   │  tier (0=interp, 1~3=C1, 4=C2)
    │    │   flags (% = OSR, n = native, ! = exception)
    │    compile ID
    JVM 시작 후 시간 (ms)
```

```bash
# JFR
jcmd <pid> JFR.start name=cc duration=300s settings=profile filename=cc.jfr
```
핵심 이벤트:
- `jdk.CodeCacheStatistics` — 주기적 사용량
- `jdk.CodeCacheFull` — **가득 참 발생, 보이면 즉시 size 증가**
- `jdk.Compilation` — 어떤 메서드가 컴파일됐는지
- `jdk.Deoptimization` — deopt reason까지
- `jdk.CompilerInlining` — inlining 결정 ("too big" 등 reason)

### 5.3 키워드 2 — "CodeCache is full" 도미노

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

**시나리오 1: 대형 Spring Boot — "CodeCache is full"**
- 증상: 로그 + P99 점진 ↑
- 진단: `jcmd Compiler.codecache | grep compilation` → `disabled (not enough memory)`, `stopped_count=1`
- 조치: `-XX:ReservedCodeCacheSize=512m` + 동적 클래스 audit (AOP unnecessary proxy 제거) + Lambda capture 점검

**시나리오 2: Deopt 폭주 — Megamorphic call site**
- 증상: JFR `jdk.Deoptimization` 분당 수백 건, reason: class_check 다수
- 원인: Strategy 패턴으로 한 호출 사이트가 5+ 구현체 받음 → C2 monomorphic inline → 매번 깨짐
- 조치: sealed class로 구현체 제한 (CHA 안정), 일부 사이트는 if-else 평탄화, `-XX:+PrintInlining`으로 실패 메시지 확인

### 5.4 키워드 3 — 옵션 트레이드오프

**`-XX:ReservedCodeCacheSize`**:
| 작게 (~64MB) | 기본 (240MB) | 크게 (512MB~1GB) |
|---|---|---|
| 메모리 ↓ | 일반 웹 적정 | Spring Boot 거대 앱·동적 클래스 많은 앱 |
| Full 위험 ↑ | | reserve 양 ↑ |

**`-XX:-TieredCompilation`**:
| Tiered ON (기본) | Tiered OFF |
|---|---|
| Warmup 빠름 | Warmup 느림 |
| Code Cache 2배 | Code Cache 절반 |
| Profile 수집 비용 | Profile 없음 |
| Peak 성능 동일 | Peak 성능 동일 |

언제 끄나: 메모리 빠듯 컨테이너 + warmup 무관 batch.

**왜 Tiered ON이 warmup 빠른가** (표만 보면 본질 안 풀림):
```
[Tiered OFF (C2 only)]
시간 ──────────────────────────────────►
│  인터프리터 (느림, ~50배)        [C2 컴파일 중]
│  ~ 수초 ~ 수십 초                 (수십~수백 ms)
└────────────────────────────────────────────
                                        ↑ 이 순간 갑자기 빨라짐 (계단형)

[Tiered ON (C1 → C2)]
시간 ──────────────────────────────────►
│ 인터프 │ C1 native (그럭저럭)  │  C2 native (peak)
│ 짧음    │ ★ 이 동안 background C2 │
└────────────────────────────────────────────
            ↑ 빨리 그럭저럭         ↑ 부드럽게 최고로
```

C1이 효과적인 이유 3가지:
1. **C1 임계 50배 낮음** (200 vs 10,000) → 빨리 트리거
2. **C1 컴파일 10배 빠름** (수 ms vs 수십~수백 ms)
3. **C2 대기 동안 C1 native가 메서드를 받쳐줌** (다리 역할)

**식당 비유**: Tiered OFF = 정식 셰프(C2)만, 익히는 동안 손님 못 받음. Tiered ON = 알바(C1) + 셰프(C2), 알바가 빠르게 응대하고 셰프 익으면 교대.

> ⚠️ 표면 옵션값을 외우지 말 것. **"메모리 빠듯 → Tiered 끄거나 size 조정", "warmup 중요 → Tiered on 유지"** 같은 결정 룰만 갖고 있으면 된다.

---

## 6. 가지 ⑥: 진화 — JDK 7→21의 JIT 변천사

### 6.1 핵심 질문

> "JDK 8과 17의 JIT 차이는?"

### 6.2 키워드 1 — 전체 흐름 (JDK 7→8→9→17→21)

```
JDK 7   JDK 8    JDK 9       JDK 10    JDK 11    JDK 17       JDK 21
  │      │        │            │         │         │            │
실험   Tiered  Segmented    Graal     Graal      Graal       Leyden
       기본 on Code Cache    실험     계속 실험   제거         시작
              (JEP 197)    (JEP 317)              (JEP 410)
              JVMCI                              Concurrent  Generational
              (JEP 243)                          class       ZGC
                                                  unload
                                                  성숙
```

**한 줄 요약표**:

| JDK | 가장 중요한 변화 | 면접 한 줄 |
|---|---|---|
| 7 | Tiered 실험 도입 | "옛날엔 -client/-server 둘 중 골랐다" |
| 8 | Tiered 기본 on, CodeCache 240MB | "JIT 양쪽 다 쓰니 메모리도 5배" |
| 9 | Segmented Code Cache (JEP 197), JVMCI (JEP 243) | "C1/C2 섞임을 영역 분리로 해결" |
| 10 | Graal JIT 실험 (JEP 317) | "C2 대체 시도 시작" |
| 11 | LTS, 큰 변화 없음 | "9의 안정화" |
| 17 | Graal/AOT 제거 (JEP 410) | "OpenJDK는 C1/C2 회귀, Graal은 GraalVM으로" |
| 21 | Generational ZGC, Leyden 시작 | "nmethod 회수가 GC와 합쳐짐, AOT 재시도" |

### 6.3 키워드 2 — 핵심 JEP들의 "왜"

**Tiered 기본 ON (JDK 8)**:
- 그전: `-client` (C1만) / `-server` (C2만) 양자택일. 사용자가 잘못 고르면 손해.
- 해결: "둘 다 쓰자" — 시작은 C1, 안정화는 C2.
- 대가: Code Cache 2배 (48MB → 240MB).

**Segmented Code Cache (JEP 197, JDK 9)**:
- 문제: Tiered 기본 ON 후 C1(short-lived)와 C2(long-lived)가 단일 영역에 섞임 → sweep 비효율 + fragmentation + I-cache locality 손상.
- 해결: 3 segment로 물리 분리 → 각 영역 독립 sweep, locality 향상.

**JVMCI (JEP 243, JDK 9)**:
- 문제: C2가 C++로 작성되어 유지보수 위기. 외부 컴파일러 plug-in 길 필요.
- 해결: Java 인터페이스로 외부 JIT 받아들임. **Graal의 기반**.

**Graal JIT 등장 및 제거 (JEP 317 → 410)**:
- 등장 이유: C2의 C++ 유지보수 한계, Java로 새 JIT 작성.
- 제거 이유: 메모리 footprint ↑, 모든 워크로드에서 C2 압도 못 함, experimental 사용자 적음, OpenJDK 유지 비용.
- **GraalVM으로 분리** — "안정의 본체 vs 혁신의 별도 프로젝트". GraalVM의 차별화는 **Native Image (AOT)** — 서버리스·CLI에서 결정적 우위.
- **JVMCI는 남음** — GraalVM이 plug-in으로 여전히 OpenJDK에 붙을 수 있는 길.

**nmethod unloading의 GC 통합 (JDK 16~21)**:
- 문제: 옛 NMethodSweeper의 STW.
- 해결: ZGC, Shenandoah의 concurrent unloading. nmethod도 객체와 함께 reachability 분석.

**Project Leyden (JDK 21~)**:
- 문제: JIT의 영원한 한계 = warmup. 서버리스·컨테이너 재시작에서 매번 비용.
- 옛 시도 실패: JDK 9 AOT(jaotc) → JDK 16 제거. GraalVM Native Image → peak 손해.
- Leyden 접근: **기존 JIT 결과를 cache해 다음 실행에 재사용**. JIT 대체가 아닌 **보완**.
- JDK 24+ AOT Cache 정식. "JIT는 사라지지 않는다, 시작은 cache로 건너뛴다".

### 6.4 키워드 3 — 두 층으로 보기 (개념층 vs 구현층)

```
[개념층 — JDK 7 ~ 21 거의 동일]
─────────────────────────────────
C1 = 빠른 컴파일, 약한 최적화
C2 = 무거운 컴파일, 공격적 최적화
Tiered = 인터프리터 → C1 → C2 승급
Code Cache = JIT 산출물 보관 + executable memory

[구현층 — 매 JDK 조용히 진화]
─────────────────────────────────
어떤 최적화가 추가됐나
어떤 intrinsic이 새로 들어갔나
SIMD/vectorization 적용 범위
escape analysis 정밀도
default 임계·heuristic
GC와의 통합 수준
```

→ **"개념은 같지만 같은 코드가 다르게 빠르다"** — JDK 업그레이드만으로 5~30% 성능 개선이 흔히 보고되는 이유.

**대표 진화 예시**:
- **Intrinsic** — `Math.max`를 CPU의 SSE/AVX 1명령으로 치환. JDK 8: `Math.fma`, JDK 9: `String.compareTo`, JDK 16+: `Reference.refersTo`, JDK 21: 더 많은 Math.
- **Partial Escape Analysis** — Graal이 가져온 개념. 일부 경로만 escape하는 경우 경로별로 다르게 처리 (escape 경로만 heap, no escape는 scalar).
- **SuperWord/Auto-Vectorization** — 루프 여러 iteration을 SIMD로 묶기. 매 JDK 진화.

---

## 7. 면접 답변 워크플로우

### 7.1 질문 → 가지 매핑

| 면접 질문 | 진입 가지 | 인접 확장 |
|---|---|---|
| "JIT는 왜 필요한가요?" | ① WHY | ② WHAT (별도 영역) |
| "C1과 C2의 차이?" | ① WHY | ⑥ 진화 (Tiered) |
| "Code Cache는 어디에?" | ② WHAT | ③ HOW (호출 메커니즘) |
| "조회는 어떻게?" (이름 함정) | ② WHAT | ③ HOW (Method._code) |
| "Profiled / Non-profiled 차이?" | ② WHAT (segment) | ⑥ 진화 (JEP 197) |
| "컴파일은 누가 트리거?" | ③ HOW | ② WHAT |
| "Deopt가 왜 일어나나?" | ④ 내부 | ⑤ 운영 (진단) |
| "CodeCache is full!" | ⑤ 운영 | ② WHAT (size) |
| "JDK 8과 17 JIT 차이?" | ⑥ 진화 | 전 가지 |

### 7.2 답변 템플릿

> **루트 문장 한 줄 → 해당 가지 키워드 3개 → 듣는 사람 표정 보고 인접 가지로**

예: "Code Cache는 어떻게 호출되나요? Redis처럼 조회해서?"

> "아니요, Code Cache는 lookup 자료구조가 아니라 **executable memory 영역**입니다. (← 루트)
> 첫째, JIT가 native instruction을 Code Cache의 어떤 주소에 배치합니다 — `gcc` 결과의 `.text`와 같은 성격.
> 둘째, Method 객체의 `_code` 필드(포인터 한 워드)를 그 주소로 atomic write 패치합니다.
> 셋째, 호출자는 `call [Method._code]`로 그냥 점프합니다 — CPU의 instruction pointer가 Code Cache 안으로 들어가서 한 줄씩 실행. lookup 자료구조 없음.
> 진짜 lookup 같은 동작은 **Inline Cache** — 각 호출 사이트에 박힌 dispatch 캐시인데, 이건 Code Cache 자체가 아니라 그 안에 든 별도 메커니즘입니다."

---

## 8. 꼬리질문 트리 (가지별)

### Q1 [가지 ②]. JIT 컴파일된 코드는 어디 저장되나요?

> Code Cache. Heap도 Metaspace도 아닌 별도 영역. 별도인 이유 3가지: (1) executable 메모리(W^X 보안), (2) GC와 회수 정책 다름 (별도 sweeper), (3) 32-bit relative jump를 위해 4GB 안에 모여야 함.

**🪝 Q1-1: 그 코드는 어떻게 호출되나? Redis처럼 조회하나?**
> 아니요. **조회 자료구조가 아닌 executable memory 영역**. CPU가 그 주소로 직접 점프해서 실행. `gcc`의 `.text` 영역과 같은 성격. Method 객체의 `_code` 필드(포인터 한 워드)를 읽어 `call [_code]`로 점프. JIT 완료는 그 포인터를 nmethod 주소로 atomic write로 바꿔치는 것. lookup 없음.

**🪝🪝 Q1-1-1: 왜 "Cache"라는 이름인가요?**
> `Cache`의 일반적 의미 — **임시 보관소(storage cache)**. Redis 같은 lookup cache가 아니라 nmethod가 deopt/cold sweep으로 회수될 수 있는 임시 저장 영역. 진짜 lookup 비슷한 동작은 **Inline Cache** — 호출 사이트마다 박힌 dispatch 캐시인데, 이건 Code Cache 자체가 아니라 그 안에 든 별도 메커니즘.

### Q2 [가지 ②]. Code Cache 구성은 어떻게?

> JDK 9 이후 3 segment. Non-method (JVM stub), Profiled (C1 tier 2/3 결과, instrumented short-lived), Non-profiled (C2 tier 4 + C1 tier 1, 측정 없는 long-lived). 수명/특성 분리.

**🪝 Q2-1: Profiled segment에는 C1 결과만, Non-profiled에는 C2 결과만 들어가나요?**
> 정확히는 아님. 기준은 **"측정 로직(instrumentation) 포함 여부"**. Profiled = C1 tier 2/3 (코드에 측정 박힘). Non-profiled = C2 tier 4 **+ C1 tier 1** (둘 다 측정 없음). C2가 Non-profiled인 이유: C2는 profile을 입력으로 소비하지만 결과 코드에는 측정 없음 — "profile을 썼지만 더는 만들지 않는다".

**🪝🪝 Q2-1-1: 왜 컴파일러별로(C1/C2) 가르지 않고 측정 여부로 가르나?**
> 본질이 **수명 분리**라서. C1 tier 1은 단순 컴파일이라 long-lived → Non-profiled로 가는 게 맞음. 컴파일러 기준이 아니라 **수명 + 측정 여부** 기준이라 segment 효율(sweep 빈도, I-cache locality)이 더 좋다.

### Q3 [가지 ③]. 컴파일은 누가 트리거하나요? Compiler thread가 감시?

> 아니요. **별도 감시 스레드 없음**. 인터프리터 stub과 tier 2/3 C1 코드 안에 counter inc + 임계 비교 로직이 박혀 있고, **실행하던 application thread가 자기가 직접** `CompileBroker.enqueue(task)` 호출. Compiler thread는 큐 pickup만 하는 일꾼.

**🪝 Q3-1: application thread가 enqueue하면 컴파일 끝까지 기다리나요?**
> 아니요. enqueue 후 **계속 인터프리터로 실행**. 컴파일은 비동기. 끝나면 `Method._code`가 atomic write로 갱신되고, **다음 호출 시점부터** 자동으로 native 점프. 호출자 입장에서는 `call [Method._code]` 한 줄이라 포인터가 바뀐 줄도 모름.

**🪝🪝 Q3-1-1: tier 3 → C2 트리거도 같은가요?**
> 같다. C1 tier 2/3 결과 코드 안에도 instrumentation이 박혀 있어서(그래서 Profiled segment), 그 코드가 실행되면서 자기 자신을 C2로 승급 신청. 외부 감시 없음.

### Q4 [가지 ①]. Tiered Compilation이 뭔지 설명해보세요.

> C1과 C2를 한 JVM에서 모두 활용. 인터프리터 → C1 (tier 1/2/3) → C2 (tier 4) 순으로 hot 메서드를 승급. JDK 8부터 기본 ON.

**🪝 Q4-1: 왜 5단계인가, 그냥 C1 → C2면 안 되나?**
> C1도 3가지로 나뉜다. tier 1 (no profile, C2 큐 막혔거나 단순한 경우), tier 2 (호출 카운터만), tier 3 (full profile, 가장 느린 C1). profile 비용 vs 정확도의 점진적 trade-off.

**🪝 Q4-2: Tiered의 비용은? 끄면 어떻게 되나?**
> Code Cache 2배 (C1, C2 결과 동시). Profile 수집 overhead. 그래서 JDK 9에서 Segmented Code Cache 필요해졌다. 끄면: Code Cache 절반, Warmup 느림(인터프리터→C2 직행), Peak 동일. 메모리 빠듯 + warmup 무관 batch에 적합.

### Q5 [가지 ④]. Deopt가 왜 일어나고 어떻게 진단하나요?

> C2는 낙관적 가정(CHA, speculative type, uncommon branch)으로 공격적 최적화. 가정 깨지면 nmethod를 not_entrant 표시 → safepoint에서 native→interpreter frame 복원 → bytecode 재시작. 진단: JFR `jdk.Deoptimization`의 reason 분포. 빈발 시 호출 사이트의 megamorphic 의심.

**🪝 Q5-1: Deopt 폭주의 흔한 원인과 해결?**
> Strategy 패턴으로 한 호출 사이트가 5+ 구현체 받음 → C2 monomorphic inline → 매번 깨짐. 해결: sealed class로 구현체 제한(CHA 안정), 일부 사이트는 if-else 평탄화, 핫 패스에서 reflection/dynamic proxy 제거, `-XX:+PrintInlining`으로 실패 메시지 확인.

### Q6 (Killer) [가지 ⑤]. "CodeCache is full" 메시지를 production에서 봤습니다. 진단?

> 다섯 단계:
> 1. `jcmd Compiler.codecache`로 segment별 used/size + `stopped_count` 확인.
> 2. JFR `jdk.CodeCacheFull`로 시점/주기 확인.
> 3. 원인 분류:
>    - 일반 부족 → `-XX:ReservedCodeCacheSize` 증가
>    - 동적 클래스 누적 → AOP/proxy/lambda audit
>    - Hot reload 환경 → ClassLoader 누수 동반 의심
> 4. 즉시 조치: size 증가 + 재시작.
> 5. 장기 모니터링 셋업 (Prometheus jvm_jit, JFR 상시).

**🪝 Q6-1: size만 무한정 늘리면 안 되나요?**
> 안 됨. (1) 가상 메모리 사용 ↑ → 컨테이너 limit 압박. (2) reserve가 클수록 32-bit jump 범위 보장 어려움. 일반적으로 512MB~1GB가 거대 앱의 sweet spot.

### Q7 [가지 ⑥]. JDK 8과 21 JIT의 가장 큰 변화 3가지?

> ① **JDK 9 Segmented Code Cache (JEP 197)** — C1/C2 결과 분리로 fragmentation 해결. ② **JDK 17 Graal/AOT 제거 (JEP 410)** — OpenJDK는 C1/C2 회귀, GraalVM은 별도 프로젝트로 (Native Image 차별화). JVMCI는 남아 plug-in 길 유지. ③ **JDK 21 GC 통합 nmethod unloading** — 별도 Sweeper thread 시대 끝, ZGC/Shenandoah가 concurrent로 회수. STW 영향 거의 사라짐.

**🪝 Q7-1: Leyden은 뭔가요?**
> JIT 대체가 아닌 보완. 첫 실행에서 컴파일한 결과를 AOT cache로 저장, 다음 실행은 warmup 거의 없이 시작. 추가 hot 발견되면 새로 컴파일해 cache 업데이트. JDK 24부터 AOT cache 정식. "JIT는 사라지지 않는다, 시작은 cache로 건너뛴다".

**🪝 Q7-2: Graal이 왜 OpenJDK 본체에서 빠졌나요?**
> 메모리 footprint ↑, 모든 워크로드에서 C2 압도 못 함, experimental 사용자 적음, OpenJDK 유지 비용. **별도 프로젝트 GraalVM으로 분리** — "안정의 본체 vs 혁신의 별도 프로젝트". GraalVM의 진짜 차별화는 **Native Image (AOT)** — 서버리스·CLI에서 결정적 우위. JVMCI는 OpenJDK에 남아 GraalVM이 plug-in으로 붙을 수 있음.

---

## 9. 학습 체크리스트

면접 전 백지에서 다음을 다 해낼 수 있어야 마스터:

- [ ] 0장 마인드맵을 종이에 1분 이내로 그릴 수 있다 (루트 + 6가지 + 각 키워드 3개)
- [ ] 가지 ① WHY: 인터프리터/AOT/JIT 비교와 C1+C2 trade-off
- [ ] 가지 ① WHY: Tiered Compilation 5단계 (Tier 0~4)
- [ ] 가지 ② WHAT: Code Cache 별도 영역인 이유 3가지 (보안/GC분리/32-bit jump)
- [ ] 가지 ② WHAT: 3 segment 그림과 Profiled/Non-profiled의 진짜 의미
- [ ] 가지 ② WHAT: "조회 X, 직접 점프" — Method._code 패치 메커니즘
- [ ] 가지 ③ HOW: 자기보고 시스템 (감시 X) + 두 종류 카운터
- [ ] 가지 ③ HOW: step-by-step 흐름 (counter→enqueue→pickup→nmethod→_code patch)
- [ ] 가지 ④ 내부: Inline Cache의 mono/bi/megamorphic 진화
- [ ] 가지 ④ 내부: Deopt 흐름과 가정 4종 (CHA/speculative/uncommon/JVMTI)
- [ ] 가지 ⑤ 운영: jcmd Compiler.codecache의 stopped_count 해석
- [ ] 가지 ⑤ 운영: "CodeCache is full" 5단계 진단
- [ ] 가지 ⑤ 운영: Tiered ON warmup 빠른 진짜 이유 (C1이 다리 역할)
- [ ] 가지 ⑥ 진화: JDK 7→8→9→17→21 진화의 한 줄 정리
- [ ] 가지 ⑥ 진화: 각 JEP의 "왜" — Tiered, Segmented, JVMCI, Graal, Leyden
- [ ] 8장 꼬리질문 7개에 막힘없이 답한다

---

## 다음 단계

- → [05. Direct Memory](./05-direct-memory.md): Off-heap NIO buffer
- → [06. GC bookkeeping](./06-gc-bookkeeping-and-others.md): Card Table, RSet, Mark Bitmap
- ← [03. Stack & PC & Native](./03-stack-pc-native.md): Per-thread 메모리
- ← [02. Metaspace](./02-metaspace-and-class-space.md): Class 메타데이터
- 관련: 추후 03-execution-engine 챕터 — C1/C2 내부 동작과 최적화 기법 상세

## 참고

- **JEP 197 Segmented Code Cache**: https://openjdk.org/jeps/197
- **JEP 243 JVMCI**: https://openjdk.org/jeps/243
- **JEP 317 Experimental Graal JIT**: https://openjdk.org/jeps/317
- **JEP 410 Removal of AOT/Graal JIT**: https://openjdk.org/jeps/410
- **JEP 439 Generational ZGC**: https://openjdk.org/jeps/439
- **Oracle — HotSpot VM Performance Enhancements**: https://docs.oracle.com/en/java/javase/21/vm/java-hotspot-virtual-machine-performance-enhancements.html
- **JITWatch (시각화)**: https://github.com/AdoptOpenJDK/jitwatch
- **Aleksey Shipilëv — JVM Anatomy Quarks**: https://shipilev.net/jvm/anatomy-quarks/
