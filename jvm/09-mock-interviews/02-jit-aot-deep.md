# 09-02. JIT + AOT — 시니어 깊이 답변 8문항

> JIT/AOT는 "Java가 왜 빠른가"의 답이자, production tail latency·warmup·cold start·메모리 footprint를 결정하는 축.
> 시니어 면접에서 묻는 본질 8개 — 각 질문을 한 줄 정의로 시작해, 도식·코드·운영 진단·한 줄 요약 순으로 답한다.
>
> 답변 원칙: **표면(개념) → 깊이(내부 동작) → 운영(진단/해결) → 함정(트레이드오프)** 4단.

---

## 목차

1. [JIT vs AOT 차이와 HotSpot JIT 최적화 기법](#1-jit-vs-aot-차이와-hotspot-jit-최적화-기법)
2. [JIT 옵티마이저 단계별 동작 원리와 튜닝 포인트](#2-jit-옵티마이저-단계별-동작-원리와-튜닝-포인트)
3. [C1, C2의 차이와 장단점](#3-c1-c2의-차이와-장단점)
4. [JIT 프로파일링 데이터 수집과 코드 최적화 영향](#4-jit-프로파일링-데이터-수집과-코드-최적화-영향)
5. [AOT 컴파일이 대규모 서비스에 미치는 장단점](#5-aot-컴파일이-대규모-서비스에-미치는-장단점)
6. [Deoptimization 상황과 원인](#6-deoptimization-상황과-원인)
7. [JIT 동작 실시간 모니터링 방법](#7-jit-동작-실시간-모니터링-방법)
8. [JIT와 GC의 상호작용이 성능에 미치는 영향](#8-jit와-gc의-상호작용이-성능에-미치는-영향)

---

## 1. JIT vs AOT 차이와 HotSpot JIT 최적화 기법

### 한 줄 정의

> **JIT = 런타임 프로파일을 입력으로 hot 메서드만 native로 번역하는 컴파일러. AOT = 빌드 시점에 모든 reachable 코드를 native로 번역하는 컴파일러. 본질 차이는 "프로파일을 입력으로 쓸 수 있느냐"와 "speculative optimization을 할 수 있느냐".**

### 본질 — 두 컴파일러의 정체성

```
[JIT]                              [AOT]
런타임에 도착                        빌드 시점에 도착
    │                                  │
    bytecode + 실측 profile             bytecode (or 소스)
    │ ("ArrayList만 들어옴")            │ (정적 분석만)
    ↓                                  ↓
hot 메서드만 native 컴파일               모든 reachable 코드 native
    │                                  │
    Code Cache 적재                     OS 실행 파일
    │                                  │
    가정 깨지면 deopt → 인터프리터       가정 없음 → deopt 없음
```

핵심 비대칭:

| 항목 | JIT | AOT |
|---|---|---|
| **컴파일 시점** | 런타임 (호출 ≥ N회 누적되면) | 빌드 시점 |
| **입력** | bytecode + 런타임 프로파일 | bytecode (정적 분석만) |
| **Speculation 가능?** | ★ Yes — "monomorphic이라 가정", "null 아니라 가정" | No |
| **Devirtualization** | profile로 monomorphic 확인 후 인라인 | closed-world로 type 확정 시에만 |
| **Cold start** | 워밍업 비용 (수 초~분) | ms 단위 |
| **Peak throughput** | 깊이 최적화로 최고 | profile 없어 ~80~95% |
| **메모리 footprint** | Code Cache + profile data + JIT 자체 | native binary만 |
| **Reflection / 동적 로딩** | 자유 | 빌드 시점에 등록 필요 |

### HotSpot JIT의 핵심 최적화 기법 — 9가지

> 시니어가 알아야 할 건 "기법 나열"이 아니라 **이 기법들이 서로 어떻게 사슬로 연결되는지**.

#### 1.1 Inlining — 최적화의 출발점

호출 대상의 코드를 호출 위치에 펼침. 표면적으로는 호출 오버헤드 제거지만 진짜 가치는 **그 뒤 모든 최적화의 문**.

```java
// 인라인 전
int compute(int x) { return helper(x) + 1; }
int helper(int x)  { return x * 2; }

// 인라인 후 (JIT IR 수준)
int compute(int x) { return (x * 2) + 1; }
// → 상수 전파, dead code elimination, type narrowing이 cross-method로 가능
```

기본 한계: `-XX:MaxInlineSize=35` bytes (cold), `-XX:FreqInlineSize=325` bytes (hot). monomorphic + hot이면 거의 항상 인라인.

#### 1.2 Loop Unrolling — 분기 비용 줄이고 SIMD 기회 생성

```java
// 원본
for (int i = 0; i < n; i++) a[i] = b[i] + c[i];

// 4× unroll
for (int i = 0; i < n - 3; i += 4) {
    a[i]   = b[i]   + c[i];
    a[i+1] = b[i+1] + c[i+1];
    a[i+2] = b[i+2] + c[i+2];
    a[i+3] = b[i+3] + c[i+3];
}
// → loop overhead 4배 감소 + SuperWord가 SIMD로 합칠 기회
```

#### 1.3 Escape Analysis + Scalar Replacement

객체가 메서드 밖으로 escape하는지 분석 → NoEscape면 객체를 만들지 않고 필드를 레지스터로 분해.

```java
// 원본
Point p = new Point(x, y);
return p.x + p.y;

// EA 적용 후 (개념)
int p_x = x;
int p_y = y;
return p_x + p_y;
// → heap allocation 0, GC가 볼 일 없음
```

운영 효과: 짧은 라이프사이클의 임시 객체(`Optional`, 작은 wrapper)가 사실상 **할당 0**. allocation rate 그래프가 EA on/off에 따라 크게 달라짐.

#### 1.4 Speculation — "흔한 케이스가 늘 흔하다"는 가정

profile에서 "이 call site는 99% `ArrayList`만 들어왔다" → 가정하고 인라인 + devirtualize. 가정 깨지면 deopt.

```
[Speculative inline]
    if (receiver.klass == ArrayList) {
        // ArrayList의 add 코드를 인라인한 빠른 path
    } else {
        // uncommon_trap → deopt → 인터프리터 fall back + 재컴파일
    }
```

#### 1.5 SuperWord / SIMD Vectorization

Loop의 연속 연산을 AVX/NEON 같은 SIMD 명령어 하나로 합침.

```java
// 원본
for (int i = 0; i < n; i++) a[i] = b[i] + c[i];

// SuperWord (개념적 결과 — x86 AVX2)
vpaddd ymm0, [b+i], [c+i]    ; 8개 int를 한 번에 더함
vmovdqu [a+i], ymm0
```

조건: 연산이 순차·균일·alias 없음. `-XX:+UseSuperWord` (기본 on). JDK 16+ Vector API는 같은 결과를 명시적 코드로.

#### 1.6 Lock Elision / Coarsening

```java
// 원본
synchronized(localObject) { ... }   // localObject가 NoEscape

// EA + Lock Elision 적용 후
{ ... }   // synchronized 자체 제거
```

```java
// 원본
sync(o) { a(); }
sync(o) { b(); }

// Coarsening
sync(o) { a(); b(); }   // 두 lock을 하나로 합침
```

#### 1.7 Devirtualization (CHA + Inline Cache)

monomorphic call site의 virtual 호출을 static 호출로 변환 후 인라인.

- **CHA (Class Hierarchy Analysis)**: 현재 로드된 클래스만 보면 단 한 구현만 있다 → static으로.
- **Inline Cache**: 첫 호출의 receiver klass를 캐시 → 다음 호출이 같으면 바로 점프.

#### 1.8 Branch Prediction Hint

profile 기반으로 hot branch는 fall-through, cold branch는 jump로 배치 → CPU branch predictor 친화적.

#### 1.9 Dead Code Elimination + Constant Folding + Copy Propagation

```java
int x = 3 + 4;        // → 7
int y = x * 2;        // → 14
if (y == 14) {...}    // → if (true) {...} → 분기 제거
else {DEAD}           // → 제거
```

각 패스는 단순하지만 **인라인 + EA가 만든 입력 품질**에 의존. 인라인이 안 되면 이 사슬이 끊긴다.

### 운영 진단

```bash
# 인라인 결정/실패 이유 확인
-XX:+UnlockDiagnosticVMOptions -XX:+PrintInlining

# 어느 메서드가 어느 tier까지 갔는지
-XX:+PrintCompilation

# JFR로 컴파일 통계
jcmd <pid> JFR.start name=jit duration=60s filename=jit.jfr settings=profile
jfr print --events jdk.CompilerStatistics,jdk.CompilerInlining jit.jfr
```

흔한 함정:
- 메서드가 너무 커서 인라인 실패 → "too big" 메시지 → 메서드 분할 필요.
- profile pollution (`MethodHandle` reflection heavy) → polymorphic으로 분류 → devirtualization 실패.
- Code Cache 가득 → JIT 중단 → 인터프리터 fall back → throughput 절반 이하.

### 시니어 한 줄

> **"JIT의 본질은 profile-guided speculative optimization이다. 인라인이 사슬의 시작이고, EA·devirtualization·SIMD가 그 위에 쌓인다. AOT는 이 사슬의 입력(프로파일)을 못 받아 peak에서 손해 보지만, cold start와 footprint를 얻는다."**

---

## 2. JIT 옵티마이저 단계별 동작 원리와 튜닝 포인트

### 한 줄 정의

> **C2 옵티마이저는 7-phase pipeline — Parse → IterGVN → Inline+EA → Loop opts → Macro+CCP → Sched+RA → Output. 각 phase가 앞 phase의 결과를 입력으로 받아 IR을 단계적으로 lower하며, fixpoint까지 반복하는 패스(IterGVN, Loop)는 한 번의 변화가 다음 변화의 trigger가 된다.**

### C2 phase 7단계 — 흐름 도식

```
bytecode
   │
   ▼
[1] Parse                          bytecode → Sea-of-Nodes
   │                                각 bytecode가 노드로
   │                                data dependency만, basic block 미정
   ▼
[2] IterGVN                        같은 값 통합 + constant folding
   │                                ★ fixpoint까지 반복
   │                                cascade 잡음 (한 폴딩이 다른 폴딩 trigger)
   ▼
[3] Inlining + Escape Analysis     callee를 caller에 펼침
   │                                Escape 안 하는 객체 → Scalar Replacement
   │                                inline 후 다시 IterGVN
   ▼
[4] Loop Optimizations             LICM, RCE, Unroll, SuperWord (SIMD)
   │                                루프 안 / 밖 코드 이동
   │                                범위 체크 제거
   ▼
[5] Macro Expand + CCP             고수준 노드 lowering (ArrayAlloc 등)
   │                                Conditional Constant Propagation
   │                                분기 결과 기반 상수성 추론
   ▼
[6] Scheduling (GCM) + RA          노드를 basic block에 배치
   │                                Global Code Motion (schedule_early/late)
   │                                Graph Coloring Register Allocation
   ▼
[7] Output                         x86/ARM native instruction
                                    nmethod, Code Cache 저장
```

### Phase별 동작 — 깊이

#### [1] Parse

bytecode 한 명령어를 Sea-of-Nodes의 한 노드로 변환. `iadd` → `AddINode`, `invokevirtual` → `CallNode`, `if_icmplt` → `IfNode`.

이때 노드들은 **basic block에 묶이지 않음** — dependency edge로만 연결. 위치는 마지막 Scheduling phase까지 미뤄짐.

#### [2] IterGVN (Iterative Global Value Numbering)

가장 자주 호출되는 패스. 같은 값 계산을 한 노드로 통합 + constant fold.

```
초기: a = 3 + 4 ; b = a * 2 ; c = 3 + 4 ; d = b + 1

1차 (constant fold):
    a = 7 ; b = 14 ; c = 7 ; d = 15

2차 (GVN, hash로 같은 값 찾기):
    c == a → c를 a로 통합

최종: a = 7 ; b = 14 ; d = 15
```

**왜 iterative**: 한 폴딩이 dead branch를 만들면 그 안의 모든 계산이 또 dead → 또 폴딩 가능. fixpoint(변화 없음)까지 반복.

#### [3] Inlining + EA

profile 기반 인라인 결정 → 펼친 뒤 다시 IterGVN으로 새 폴딩 기회 잡음. EA는 인라인된 객체의 escape 여부 분석 → Scalar Replacement, Lock Elision으로 연결.

#### [4] Loop Opts

```
LICM (Loop Invariant Code Motion):
    for (i = 0; i < n; i++) { x = a * b; result[i] = i + x; }
    →
    x = a * b;  // loop 밖으로
    for (i = 0; i < n; i++) { result[i] = i + x; }

RCE (Range Check Elimination):
    for (i = 0; i < a.length; i++) { sum += a[i]; }
    → 범위 체크가 loop bound로 흡수 → 매 iteration의 check 제거

Unroll + SuperWord:
    위 1.2, 1.5 참조
```

#### [5] Macro Expand + CCP

`new int[n]`처럼 한 노드로 표현된 고수준 연산을 "TLAB top 가져오기 + bump + header 초기화 + zero-fill"의 native 명령에 가까운 노드들로 풀어 씀.

CCP는 `if (x == 0)` 안에서는 `x = 0`이라는 사실을 다음 노드에 전파.

#### [6] Scheduling + Register Allocation

```
Scheduling (Global Code Motion):
    schedule_early(node): 의존성이 허용하는 가장 이른 위치
    schedule_late(node):  가장 늦은 위치
    → 둘 사이에서 "loop 밖", "use 직전" 같은 자유 배치
    → 자동 LICM, lazy computation

Register Allocation (Chaitin's Graph Coloring):
    virtual register → physical register 매핑
    interference graph 색칠로 NP-hard 휴리스틱
    spill 최소화 → memory access 최소화
```

#### [7] Output

native instruction emit → nmethod 객체로 wrap → Code Cache의 non-profiled segment에 저장. relocation 정보, deopt info, oop map 함께 기록.

### 실전 튜닝 포인트

| 옵션 | 효과 | 언제 |
|---|---|---|
| `-XX:ReservedCodeCacheSize=512m` | Code Cache 크기. 가득 차면 JIT 중단 | JIT compilation 멈춤 경고 시 |
| `-XX:CICompilerCount=N` | 컴파일러 스레드 수 | CPU 많은데 warmup 느릴 때 |
| `-XX:CompileThreshold=10000` | Tier 4 진입 임계 | 거의 건드리지 말 것 |
| `-XX:+TieredCompilation` (기본 on) | 끄면 C2 직행 | 끄면 워밍업 느려짐 — 끄지 말 것 |
| `-XX:MaxInlineSize=35` | cold call site inline 상한 | 거대 메서드 인라인 문제 시 ↓ |
| `-XX:FreqInlineSize=325` | hot call site inline 상한 | 신중히 조정 |
| `-XX:MaxInlineLevel=9` | 인라인 깊이 | 깊이가 폭발할 때 ↓ |
| `-XX:CompileCommand=exclude,Class::method` | 특정 메서드 컴파일 제외 | 그 메서드의 C2 컴파일이 1초+ 걸릴 때 |
| `-XX:TieredStopAtLevel=3` | C1까지만 | 컴파일 비용 회피 (peak 손해) |

### 운영 진단 — C2 컴파일 자체가 느린 경우

```bash
# 1. 메서드별 컴파일 시간 추출
jcmd <pid> JFR.start name=jit duration=300s settings=profile
jfr print --events jdk.Compilation jit.jfr | sort -k 4 -n -r | head

# 2. 컴파일 큐 길이 (적체 확인)
jcmd <pid> Compiler.queue

# 3. Code Cache 사용량
jcmd <pid> Compiler.codecache

# 4. 인라인 결정 분석
-XX:+UnlockDiagnosticVMOptions -XX:+PrintInlining
```

### Killer 시나리오 — Spring 큰 컨트롤러 메서드의 C2 컴파일 시간 1초

```
환경: 거대 컨트롤러 메서드 (100+ lines, deep service call graph)
증상: P99 spike. PrintCompilation 로그에서 그 메서드 C2 컴파일 1.2초.

진단:
  1. javap -v로 Code attribute size 확인 (>10KB이면 위험)
  2. PrintInlining으로 깊이 확인 — 9단계까지 다 인라인
  3. JFR jdk.Compilation duration 정렬

원인: deep inlining → IR 노드 수 폭발 → IterGVN/Loop opts가 큰 그래프 위에서 O(n²) 동작

조치:
  - 메서드 분할 (controller → application service → domain service)
  - -XX:MaxInlineLevel=6 으로 깊이 제한 (peak 약간 손해, 컴파일 시간 ↓)
  - 그 메서드만 -XX:CompileCommand=exclude (인터프리터 영원, 최후 수단)
```

### 시니어 한 줄

> **"C2 pipeline은 IterGVN과 Loop opts의 fixpoint 반복이 cascade를 잡는 게 핵심. 인라이닝이 입력 품질을 키우면 그 뒤 phase 전체의 결과가 좋아진다. 튜닝은 'Code Cache 크기 + 인라인 깊이' 두 노브에 집중하고, 그 외에는 코드 분할로 풀어야 한다."**

---

## 3. C1, C2의 차이와 장단점

### 한 줄 정의

> **C1 = CFG(HIR/LIR) + Linear Scan RA로 수 ms에 ~50% 성능의 baseline. C2 = Sea-of-Nodes + Graph Coloring RA로 수십~수백 ms에 peak 성능. 본질 차이는 IR과 RA — 두 컴파일러의 사명이 다르니 IR도 다르고, 그 분리가 Tiered의 양립을 만든다.**

### 사명 비대칭

```
C1의 사명                              C2의 사명
━━━━━━━━━━━━━━━━━━━━━━━━              ━━━━━━━━━━━━━━━━━━━━━━━━
"수 ms 안에 baseline 성능"              "peak. 시간 비싸도 좋다"
+ Tiered profile 수집기                 한 번 컴파일 → 평생 실행
↓                                      ↓
단순 + 빠름 우선                         자유 + 공격 우선
↓                                      ↓
CFG (HIR/LIR) + Linear Scan RA          Sea-of-Nodes + Graph Coloring RA
```

### 비교 매트릭스

| 항목 | C1 (Client) | C2 (Server) |
|---|---|---|
| **IR** | HIR + LIR, CFG 기반 | Sea-of-Nodes |
| **컴파일 시간** | ~수 ms | ~수십~수백 ms |
| **메모리 (per task)** | ~수 MB | ~수십~수백 MB |
| **코드 라인 수** | ~3,000 줄 C++ | ~50,000 줄 C++ |
| **최적화 강도** | 가벼움 (간단 GVN, dead code, simple inline) | 공격적 (EA, deep inline, SIMD, speculation) |
| **Register Allocation** | Linear Scan O(n log n) | Graph Coloring O(n²~n³), Chaitin |
| **Profile** | Tier 2/3에서 수집 | 입력으로 사용 |
| **Speculation / Deopt** | 거의 없음 | 자주 (profile 기반) |
| **결과 코드 품질 (vs interpreter)** | ~10~30× | ~50~100× |
| **결과 코드 품질 (vs C2)** | ~50% | 100% |

### IR 차이의 본질

#### C1: CFG(HIR/LIR)

```
basic block 명시
   ↓
각 instruction이 한 block에 묶임
   ↓
분석/변환이 단순 → 빠른 컴파일
   ↓
단점: cross-block 최적화 (LICM, code motion) 별도 패스 + 제약 많음
```

흐름: bytecode → **HIR** (자바 의미 가까움, SSA) → **LIR** (CPU instruction 가까움) → Linear Scan RA → native.

#### C2: Sea-of-Nodes

```
basic block 미명시
   ↓
노드 간 dependency edge만
   ↓
노드 위치는 Scheduling phase에서 결정
   ↓
장점: 자유 code motion (LICM이 Scheduling 하나로), GVN cascade,
      EA 자연 (use-def chain 한 방), inlining 후 cross-method 자유
```

### Register Allocation 차이의 결과

```
[C1 Linear Scan 결과]               [C2 Graph Coloring 결과]
mov  rax, [rbp-8]    ; spill load   add  rax, rbx        ; register only
add  rax, rbx                        add  rcx, rax
mov  [rbp-16], rax   ; spill store   ...
... memory access 빈번               ... memory access 거의 없음
```

C1은 빠르게 끝내려고 spill을 더 자주 허용. C2는 시간을 더 써서 interference graph를 정밀하게 색칠 → spill 최소화 → register 안에서 거의 모든 계산.

### 어느 메서드가 C1에서 멈추나

```
1. 너무 작은 메서드 — C2가 어차피 inline해버림
2. 너무 큰 메서드 — C2 IR 노드 한계 초과로 거부
3. C2 컴파일 실패 (NULL ptr, type error 등 내부 에러)
4. -XX:CompileCommand=exclude / dontcompile 명시 제외
5. 반복 deopt — C2가 안정 보장 못 함
6. C2 큐 적체 + 우선순위 낮음
```

### Tiered가 두 컴파일러 분리를 요구하는 이유

```
가정 1: 둘 다 CFG라면
   → T4가 peak를 못 냄 → C2 무력화 → -client only와 동일

가정 2: 둘 다 Sea-of-Nodes라면
   → T3 컴파일이 ~수십 ms로 폭증 → 워밍업 우위 상실
   → -server only와 동일

→ 두 IR 분리가 Tiered 양립의 핵심
```

### 운영 진단

```bash
# 메서드별 tier 확인
java -XX:+PrintCompilation ...

# 출력 해석
142    3       4       com.MyClass::compute (123 bytes)
       ↑ Tier 3 (C1 with profiling)
142    4       4       com.MyClass::compute (123 bytes)
       ↑ Tier 4 (C2)
142    %       4       com.MyClass::compute @ 12 (123 bytes)
       ↑ % = OSR (On-Stack Replacement)

# 같은 메서드에 Tier 3는 보이는데 Tier 4가 안 보이면 → C1에서 멈춤
```

### GraalVM JIT 위치

GraalVM의 Graal Compiler는 **Java로 작성된 C2 대체 JIT**. Tier 4 자리에 끼움.
- 장: 유지보수 쉬움, partial escape analysis, 더 공격적 인라인.
- 단: 자기도 JIT 대상 → 시작 느림. 일부 워크로드는 C2가 여전히 빠름.
- 켜는 법: `-XX:+UseJVMCICompiler -XX:+EnableJVMCI` (GraalVM 배포본).

### 시니어 한 줄

> **"C1은 CFG + Linear Scan으로 빠른 baseline + profile 수집기, C2는 Sea-of-Nodes + Graph Coloring으로 peak. 두 IR이 다른 게 우연이 아니라 사명이 다르기 때문이고, 그 분리가 Tiered가 startup과 peak를 동시에 잡는 본질이다."**

---

## 4. JIT 프로파일링 데이터 수집과 코드 최적화 영향

### 한 줄 정의

> **JIT 프로파일은 Tier 0(인터프리터)와 Tier 3(C1)이 수집해 `MethodData(MDO)`에 누적하는 런타임 통계. invocation counter, backedge counter, type histogram, branch profile, null check stats가 C2의 speculative optimization 입력으로 쓰인다. 프로파일이 없으면 C2는 정적 분석만 할 수 있어 AOT와 별 차이 없는 코드를 만든다.**

### 프로파일 데이터 5종

```
[MethodData (MDO) — 메서드 하나당 1개]
    │
    ├── Invocation Counter      메서드 호출 횟수
    │       → C2 진입 임계 (CompileThreshold) 결정
    │
    ├── Backedge Counter        루프 반복 횟수
    │       → OSR(On-Stack Replacement) 트리거
    │
    ├── Type Profile            virtual/interface call site의 receiver 타입 분포
    │       → monomorphic / bimorphic / polymorphic 판정
    │       → Devirtualization, Speculative inline
    │
    ├── Branch Profile          if/switch의 taken / not-taken 빈도
    │       → Branch prediction hint, dead branch elimination
    │
    └── Null Check Stats        NPE 발생 횟수
            → Implicit null check (SIGSEGV trap) 사용 결정
```

### 수집 메커니즘

```
[Tier 0 — Template Interpreter]
    각 invoke 명령 실행 시 MDO의 counter ++
    type profile은 receiver klass를 BCI(bytecode index) 단위로 누적

[Tier 3 — C1 with profiling]
    C1이 native 코드에 counter 증가 명령 직접 박음
    예: invokevirtual call site 직전에
        mov rax, [receiver + klass_offset]
        cmp [mdo + type_offset], rax
        je already_seen
        ... 새 타입 기록 ...

[Tier 4 — C2]
    수집 안 함. MDO를 입력으로 읽음.
    speculation 위에 컴파일하므로 깨지면 deopt → 새 프로파일로 재컴파일
```

### 각 프로파일이 만드는 최적화

#### 4.1 Invocation Counter → C2 진입

`-XX:CompileThreshold=10000`(기본). 누적 호출 횟수가 임계 넘으면 컴파일 큐에 enqueue.

#### 4.2 Backedge Counter → OSR

```java
public static void main(String[] args) {
    for (int i = 0; i < Integer.MAX_VALUE; i++) {  // 메서드 첫 호출이지만 루프가 hot
        compute(data[i]);
    }
}
```

메서드 자체는 한 번만 호출되지만 루프가 hot. backedge counter가 임계 넘으면 **루프 중간에 컴파일된 코드로 점프해 들어감(OSR)**.

#### 4.3 Type Profile → Devirtualization + Inline

```java
List<String> list = ...;
list.add("foo");   // virtual call — receiver가 늘 ArrayList면?

// type profile 후 C2가 본 그림
if (list.klass == ArrayList) {
    // ArrayList.add 코드를 그대로 인라인
    ensureCapacity(size + 1);
    elementData[size++] = "foo";
} else {
    uncommon_trap;  // 다른 타입 들어오면 deopt
}
```

분류:
- **Monomorphic**: 한 타입만 → 인라인 + speculation.
- **Bimorphic**: 두 타입 → 두 path 각각 인라인.
- **Polymorphic (≥3 타입)**: Inline Cache(PIC) — vtable lookup 캐시.
- **Megamorphic**: 너무 많은 타입 → 일반 vtable 호출, 인라인 포기.

#### 4.4 Branch Profile → Branch Prediction Hint + Dead Branch

```java
if (rare_condition) {       // profile에서 0.1%만 taken
    handleException();
}
process();
```

C2 결과 native code: `process()` 코드를 fall-through에 두고 `handleException()`을 멀리 jump로 배치. CPU branch predictor가 fall-through를 default로 예측 → 거의 안 틀림.

100% 한쪽이면 cold branch는 **dead branch로 제거 + uncommon_trap** — 다시 들어오면 deopt.

#### 4.5 Null Check Stats → Implicit Null Check

NPE가 한 번도 안 났으면 명시 `if (obj == null) throw NPE` 제거 → **SIGSEGV trap을 NPE로 변환**(OS 시그널 핸들러). 명령어 ≥ 3개 절약.

한 번이라도 NPE 나면 deopt → 명시 검사로 재컴파일.

### Profile Pollution — 실전 함정

```java
// 같은 call site를 여러 타입이 통과 → polymorphic 분류
Object[] arr = ...;
for (Object o : arr) {
    o.toString();   // arr가 다양한 타입이면 megamorphic
}
```

특히 위험한 패턴:
- **`MethodHandle.invokeExact`**: reflection-heavy 코드 — call site에 온갖 타입이 통과.
- **Map의 generic 값 처리**: `Map<String, Object>` 값을 instanceof 체인.
- **테스트가 production과 다른 타입 분포**: warmup이 모집단을 대표 안 함.

결과: devirtualization 실패 → 인라인 실패 → 최적화 사슬 절단 → peak throughput 30~50% 손해.

### 운영 진단

```bash
# Type profile 직접 보기
-XX:+UnlockDiagnosticVMOptions -XX:+PrintMethodData

# 인라인 실패 이유 (profile pollution이면 "type_profile_polluted" 등)
-XX:+PrintInlining

# JFR로 컴파일 + deopt 이벤트
jcmd <pid> JFR.start name=jit duration=60s settings=profile
jfr print --events jdk.Compilation,jdk.Deoptimization jit.jfr
```

워밍업 함정:
- 짧은 micro-benchmark는 profile 부족 → C2 최적화 약함 → 실제보다 느린 결과.
- 해결: JMH(`@Fork`, `@Warmup`)로 충분 워밍업 후 측정.

### 시니어 한 줄

> **"JIT의 위력은 profile-guided speculation. profile이 깨끗하면 C2가 monomorphic으로 보고 인라인 + devirtualize → 사슬 시작. polluted면 C2가 보수적으로 가 AOT 수준으로 떨어진다. production에서 P99 spike의 절반은 'warmup 부족' 아니면 'profile pollution'이다."**

---

## 5. AOT 컴파일이 대규모 서비스에 미치는 장단점

### 한 줄 정의

> **AOT는 빌드 시점에 모든 reachable 코드를 native로 미리 컴파일하는 방식. GraalVM Native Image는 closed-world 가정으로 풀 AOT, Project Leyden은 selective shifting(클래스 로딩·링킹·일부 컴파일을 빌드 시점으로 옮기되 동적성 유지)로 절충. 본질 트레이드오프는 'cold start + footprint' vs 'peak throughput + 동적성'.**

### 두 AOT 접근

```
[GraalVM Native Image — 풀 AOT, closed-world]
    빌드 시점에 정적 분석으로 reachable한 모든 메서드 발견
    → 그것들만 native로 컴파일
    → JIT 자체 제거, JVM 런타임 최소 (Substrate VM)
    결과: 부팅 ms 단위, 메모리 ~수십 MB
    제약: reflection / 동적 로딩 / 일부 동적 API 사전 등록 필요

[Project Leyden — selective shifting, JDK 24+ preview]
    "어느 단계를 빌드 시점으로 미리 옮길지" 선택적
    - Class loading 미리 (AppCDS, 이미 존재)
    - Class linking 미리
    - Method profile 미리 (학습 실행 후 저장)
    - 일부 메서드 컴파일 미리
    결과: 동적성 유지 + cold start 크게 단축
    제약: 풀 AOT만큼 빠르진 않음
```

### 장점

| 항목 | 효과 |
|---|---|
| **부팅 시간** | JIT 워밍업 없음 → 수 초~수십 초 → ms~수백 ms |
| **메모리 footprint** | Code Cache, profile data, JIT 자체 제거 → ~50~80% ↓ |
| **컨테이너 이미지** | JRE 없이 native binary → 수십 MB |
| **예측 가능성** | 첫 요청부터 풀스피드, P99 spike 없음 (deopt 없음) |
| **보안** | 사용 안 하는 reflection / 동적 코드 제거 → attack surface ↓ |
| **Serverless 적합** | Lambda cold start가 500ms → 50ms 수준 |

### 단점

| 항목 | 효과 |
|---|---|
| **Peak throughput** | profile 없음 → speculative optimization 못 함 → ~80~95% of JIT |
| **Reflection 제약** | 사용할 클래스/메서드를 `reachability-metadata.json`에 사전 등록 |
| **동적 로딩 불가** | `URLClassLoader.loadClass` 같은 plugin 시스템 부적합 |
| **빌드 시간** | 메서드 수십만 개 한 번에 분석 → 5~15분 |
| **빌드 메모리** | 8~16GB+ |
| **디버깅 어려움** | jstack/JFR/Heap dump 등 JVM 도구 제한 |
| **라이브러리 호환성** | reflection 많은 라이브러리는 별도 설정 |

### 워크로드별 매트릭스

```
[부팅 시간 critical]                   [Long-running peak critical]
- Serverless (Lambda, Knative)         - Trading 엔진
- CLI 도구                              - 큰 웹 서버 (수십 분 워밍업)
- 사이드카 (Envoy 동반 등)              - 배치 잡 (Spark, Flink)
- 마이크로서비스 빠른 scale-out         - 광고 입찰 (RTB)
    ↓                                       ↓
GraalVM Native Image 강함                JIT (특히 C2 / Graal JIT) 강함
또는 Project Leyden 절충

[중간]
- Spring Boot 일반 웹 앱:
   Native Image (Spring Native, AOT processing 자동화)
   또는 Leyden CDS+AOT (peak 95% + cold start 30%)
```

### Project Leyden — 시니어가 알아야 할 selective shifting

```
JVM 실행 단계
    │
    1. Class Loading       ──┐
    2. Class Linking       ──┤
    3. Class Initialization──┤ ← 각 단계를 빌드 시점으로 "옮길지" 선택
    4. Profile collection  ──┤
    5. JIT compilation     ──┘
    │
    6. Run

기존 AppCDS:    1만 빌드 시점으로 (class data 캐시)
JDK 21 AppCDS+: 1+2 빌드 시점으로
Leyden Phase 1: 1+2+4(일부) — 학습 실행으로 profile 저장 → 다음 부팅에 재사용
Leyden Phase 2: 1+2+4+5(선택적) — profile 기반 일부 메서드 AOT
풀 AOT:         모든 단계를 빌드 시점으로 (GraalVM Native)
```

Leyden의 핵심 통찰: **풀 AOT가 줄 수 있는 cold start 단축의 80%는 "class loading + linking + profile 재사용"으로 달성 가능, 동적성을 잃지 않고도**.

### Closed-World vs Open-World

```
[Closed-World (Native Image)]
    빌드 시점에 모든 코드를 안다고 가정
    → 정적 분석으로 reachable 메서드 / type hierarchy 확정
    → 사용 안 하는 코드 제거 (tree shaking)
    → 새 클래스 런타임 추가 불가
    제약: reflection / Proxy / 동적 로딩 사전 등록

[Open-World (HotSpot, Leyden)]
    런타임에 새 클래스 로드 가능
    → CHA로 현재 본 hierarchy로만 최적화
    → 새 클래스 로드되면 가정 깨짐 → deopt
    이점: 풀 동적성 유지
```

### 운영 시나리오 매트릭스

| 시나리오 | 추천 | 이유 |
|---|---|---|
| AWS Lambda Java 함수 | GraalVM Native Image | Cold start 비용이 throughput보다 critical |
| Spring Boot REST API, 트래픽 안정 | HotSpot + AppCDS + 충분 워밍업 | JIT peak이 더 빠름, 운영 도구 풍부 |
| Spring Boot, scale-out 빈번 | Spring Native (GraalVM) 또는 Leyden | 새 인스턴스 빠른 ready |
| Kafka Streams 같은 long-running 스트림 | HotSpot | JIT가 깊이 최적화할 시간 충분 |
| Apache Spark Executor | HotSpot | 같은 이유 |
| CLI 도구 (`jbang`, `picocli`) | GraalVM Native | 매 호출이 cold start |
| Quarkus 마이크로서비스 | GraalVM Native (Quarkus가 자동화) | Quarkus AOT framework 사용 |

### 운영 진단 / 결정 체크리스트

```
1. Cold start 시간이 SLO에 들어가는가? (yes → AOT 후보)
2. 메서드 reflection 사용량? (많음 → AOT 어려움)
3. 동적 클래스 로딩? (yes → AOT 불가)
4. Peak throughput vs cold start 우선순위?
5. JIT warmup이 trafic 패턴 안에서 끝나는가? (no → AOT 후보)
6. 운영 도구 (JFR, async-profiler) 의존도? (높음 → HotSpot 유리)
```

### 시니어 한 줄

> **"AOT의 본질은 'profile + speculation' 우위를 'cold start + footprint'로 바꾸는 거래. 단기 함수는 Native Image, 장기 서버는 HotSpot, 그 사이는 Leyden의 selective shifting이 답을 찾고 있다. closed-world의 reflection 제약이 진짜 비용이지 빌드 시간이 아니다."**

---

## 6. Deoptimization 상황과 원인

### 한 줄 정의

> **Deoptimization = JIT가 speculation 기반으로 만든 native code의 가정이 깨졌을 때, 그 native frame을 인터프리터 frame으로 재구성해 fall back하는 동작. 원인은 unstable_if, class_check, unreached, null_check, range_check 등 uncommon trap. P99 spike의 흔한 원인.**

### 본질 — Speculation의 동전 양면

```
JIT의 우위           ↔        대가
━━━━━━━━━━━━              ━━━━━━━━━━━━
profile 기반 가정에           가정 깨지면 deopt:
공격적 최적화                  - native code 폐기
(devirtualize, inline,         - 인터프리터 frame 재구성
 implicit null check,          - fall back 후 재컴파일
 dead branch elimination)      - 비용 ~수십 μs ~ 수 ms
```

### Deopt Reason — 시니어가 외워야 할 5종

#### 6.1 `unstable_if` — branch 가정 깨짐

```java
if (rare_cond) { handleException(); }   // profile: 0.1% taken
// C2가 본 그림: cold branch는 uncommon_trap

// 런타임에 rare_cond가 자주 true가 되기 시작
// → uncommon_trap 발동 → deopt
// → 재컴파일 시에는 양쪽 branch 다 native code로
```

언제: trafic 패턴이 바뀜(시즌, A/B 테스트), 비정상 입력 증가.

#### 6.2 `class_check` — type speculation 깨짐

```java
List<String> list = ...;   // profile: 99% ArrayList
list.add("foo");
// C2 그림: ArrayList.add 인라인 + class_check
//   if (list.klass != ArrayList) → uncommon_trap

// 런타임에 LinkedList instance가 들어옴
// → class_check 실패 → deopt
// → 재컴파일 시 bimorphic으로 둘 다 인라인 시도
```

언제: 새 구현체 로드, 새 코드 path 활성화, polymorphism 증가.

#### 6.3 `unreached` — dead branch 진입

```java
switch (kind) {
    case A: ... break;   // profile: 100%
    case B: ... break;   // profile: 0% → unreached로 분류
    case C: ... break;   // profile: 0% → unreached로 분류
}
// C2 그림: A path만 native code, B/C는 uncommon_trap

// 런타임에 kind == B 도착
// → unreached trap → deopt
```

언제: 처음 보는 enum 값, lazy 초기화된 코드 path 첫 진입.

#### 6.4 `null_check` — implicit null check 깨짐

```java
obj.field   // profile: NPE 없음 → implicit null check (SIGSEGV trap) 사용
            // C2: 명시 if (obj == null) 없이 직접 [obj + offset] load

// 런타임에 obj == null 도달
// → SIGSEGV → signal handler가 deopt + NPE throw
// → 재컴파일 시 명시 null check 추가
```

언제: nullable 객체에 처음 null 들어옴, 잘못된 입력.

#### 6.5 `range_check` — array bound check 가정 깨짐

```java
for (int i = 0; i < n; i++) a[i] = ...;
// C2 그림: RCE (Range Check Elimination) — 매 iteration의 check 제거
//   if (n > a.length) uncommon_trap;   // 한 번만 체크

// 런타임에 n > a.length
// → range_check trap → deopt → ArrayIndexOutOfBoundsException
```

언제: 입력 검증 미흡, off-by-one 버그.

### Deopt 동작 — 내부 메커니즘

```
1. native code 실행 중 uncommon_trap에 도달
   │
   ▼
2. 현재 native frame의 상태를 dump:
   - register 값들
   - stack slot 값들
   - 현재 BCI (bytecode index)
   │
   ▼
3. "OopMap"을 보고 어느 슬롯이 oop인지 식별
   (GC root를 유지하기 위해)
   │
   ▼
4. 인터프리터 frame을 그 BCI로 재구성:
   - local variable 슬롯 채움
   - operand stack 채움
   - return address를 인터프리터의 normal_continuation로
   │
   ▼
5. native code의 nmethod를 "not entrant"로 표시
   (다음 호출은 인터프리터로)
   │
   ▼
6. 인터프리터 fall back으로 계속 실행
   │
   ▼
7. 그 메서드가 다시 hot해지면 재컴파일 (이번엔 새 profile 반영)
```

비용: deopt 자체는 수 μs~수십 μs. 인터프리터로 잠시 머무는 동안의 throughput 손해가 진짜 비용 — P99 spike.

### Deopt 유형

```
Action별:
  - reinterpret      : 인터프리터로 fall back, MDO는 유지
  - make_not_entrant : nmethod 폐기, 다음 호출도 인터프리터
  - make_not_compilable : 영원히 컴파일 안 함 (반복 deopt 방지)
                          → -XX:PerMethodRecompilationCutoff (기본 400) 초과 시
```

반복 deopt가 누적되면 그 메서드는 영원히 인터프리터로 — 성능 절벽.

### 운영 진단

```bash
# 1. Deopt 이벤트 추적
-XX:+UnlockDiagnosticVMOptions -XX:+TraceDeoptimization -XX:+PrintCompilation

# 출력 예
COMPILE SKIPPED: com.MyClass::method (already compiled)
Deoptimization (reason=unstable_if, action=reinterpret, ...)
  com.MyClass::method (bci=42)

# 2. JFR로 deopt 빈도
jcmd <pid> JFR.start name=deopt duration=60s settings=profile
jfr print --events jdk.Deoptimization deopt.jfr

# 출력 예
jdk.Deoptimization {
    startTime = ...
    compileId = 1234
    compiler = "c2"
    method = com.MyClass.method()
    lineNumber = 42
    bci = 42
    reason = "unstable_if"
    action = "reinterpret"
}

# 3. 메서드별 deopt 횟수 집계
jfr print --events jdk.Deoptimization deopt.jfr | grep method | sort | uniq -c | sort -rn
```

### Killer 시나리오 — P99 spike의 deopt 원인 진단

```
환경: e-commerce 상품 페이지 API
증상: 평균 latency 50ms, P99가 가끔 500ms로 spike. CPU/GC는 평온.

진단:
  1. JFR continuous로 jdk.Deoptimization 추적
  2. P99 spike 시각과 deopt 발생 시각 cross-check
  3. spike마다 동일 메서드에서 class_check deopt 발견
  4. -XX:+PrintInlining 으로 그 call site 확인
  5. 보니 List<Product> 였는데 99% ArrayList + 1% Collections.singletonList
     → profile은 ArrayList 단일 type으로 잘못 인식 (1%는 outlier로 처리됨)
     → 런타임에 singletonList 만나면 class_check 깨져 deopt

원인: monomorphic speculation이 실제로는 bimorphic이었음

조치:
  - 코드 단일화: 항상 ArrayList로 wrap (rare path도)
  - 또는 PerMethodRecompilationCutoff 후 stable해지면 OK
  - 또는 -XX:TypeProfileLevel=222 으로 더 정밀한 type profile 강제

교훈: profile은 "warmup 구간의 분포"를 표본. production의 long-tail이 다르면 deopt.
```

### Deopt 자체를 끄는 옵션 (거의 안 씀)

```
-XX:-UseTypeSpeculation       # type speculation 비활성
-XX:CompileCommand=dontinline # 특정 메서드 인라인 금지 → speculation도 줄어듦
```

쓰지 말 것. peak performance를 거의 다 잃음. 대신 코드를 단순화해 profile이 stable해지게 만들어라.

### 시니어 한 줄

> **"Deopt는 JIT의 버그가 아니라 speculation의 정상 비용. P99 spike에서 GC가 무죄면 deopt를 의심하라. 진짜 해결은 코드의 type/branch 분포를 stable하게 만드는 것 — profile pollution 제거가 핵심이지 옵션 노브가 아니다."**

---

## 7. JIT 동작 실시간 모니터링 방법

### 한 줄 정의

> **JIT 모니터링은 5층 — (1) `-XX:+PrintCompilation` (메서드별 이벤트 로그), (2) JITWatch (`+LogCompilation` XML 시각화), (3) `+PrintAssembly` + hsdis (native disassembly), (4) `+PrintIdealGraph` (C2 IR XML → IdealGraphVisualizer), (5) JFR `jdk.Compilation` (production-safe). 운영에서는 JFR이 기본이고 디버깅엔 JITWatch + PrintAssembly.**

### 5층 도구 — 깊이 순

#### 7.1 `-XX:+PrintCompilation` — 가장 가벼움, 항상 켜둠

```bash
java -XX:+PrintCompilation -jar app.jar
```

출력 형식:
```
142    3       4       com.MyClass::process (123 bytes)
└─ts   └─id   └─tier  └─method (size)

flag 컬럼 추가 가능:
  s = synchronized
  ! = exception handler
  % = OSR
  n = native
  made not entrant   ← nmethod 폐기 (deopt or 재컴파일)
  made zombie        ← 회수 대기
```

상시 켜둬도 부담 거의 없음. 로그가 커지면 `-XX:+LogCompilation`로 파일에.

#### 7.2 `-XX:+LogCompilation` + JITWatch — 시각화

```bash
java -XX:+UnlockDiagnosticVMOptions \
     -XX:+TraceClassLoading \
     -XX:+LogCompilation \
     -XX:+PrintAssembly \
     -jar app.jar
# → hotspot_pid<n>.log (XML)
```

JITWatch에서 그 XML 열기:
- 메서드별 컴파일 결과 (tier, 시간)
- **Inlining tree** — 어느 메서드가 인라인됐고 어디서 실패했는지
- **Deopt 위치** — BCI 매핑
- HIR/LIR/Assembly 동시 보기

운영보다 디버깅용. 큰 로그 (~GB) 생성.

#### 7.3 `-XX:+PrintAssembly` + hsdis — native disassembly 직접 보기

```bash
# 1. hsdis 플러그인 설치 (hsdis-amd64.so, hsdis-aarch64.so)
sudo cp hsdis-amd64.so $JAVA_HOME/lib/

# 2. 실행
java -XX:+UnlockDiagnosticVMOptions \
     -XX:+PrintAssembly \
     -XX:CompileCommand=print,com.MyClass::hotMethod \
     -jar app.jar
```

출력:
```
# {method} {0x...} 'hotMethod' '(I)I' in 'com/MyClass'
# parm0:    rsi       = int
#           [sp+0x40]  (sp of caller)
0x... : mov    %eax,-0x14000(%rsp)
0x... : push   %rbp
0x... : sub    $0x10,%rsp
0x... : vpaddd %ymm0,%ymm1,%ymm2   ; ★ SIMD!
...
```

용도:
- SIMD 적용 확인 (vpaddd, vmovdqu 등 AVX 명령어)
- 인라인 결과 확인 (호출 없이 callee 코드가 펼쳐졌는지)
- spill 빈도 확인 (mov register↔memory)

#### 7.4 `-XX:+PrintIdealGraph` — C2 IR 시각화

```bash
java -XX:+UnlockDiagnosticVMOptions \
     -XX:PrintIdealGraphLevel=4 \
     -XX:PrintIdealGraphFile=/tmp/ig.xml \
     -jar app.jar
```

XML을 **IdealGraphVisualizer (Oracle Labs)**로 열기. Sea-of-Nodes 그래프를 phase별로 시각화:
- Parse 직후 그래프
- IterGVN 후 (constant folding된 모습)
- Inlining 후 (caller + callee 한 그래프)
- Loop opts 후 (LICM된 노드 위치)
- Scheduling 후 (basic block 배치)

C2 phase 동작을 직접 보고 싶을 때.

#### 7.5 JFR `jdk.Compilation` — production-safe, 가장 실용

```bash
# 시작
jcmd <pid> JFR.start name=jit duration=300s filename=/tmp/jit.jfr settings=profile

# 분석
jfr print --events jdk.Compilation,jdk.CompilerInlining,jdk.Deoptimization /tmp/jit.jfr
```

JFR 이벤트:
- `jdk.Compilation` — 메서드별 컴파일 이벤트 (compileId, method, tier, duration, codeSize)
- `jdk.CompilerInlining` — 인라인 성공/실패 + 이유
- `jdk.CompilerStatistics` — 시간당 집계
- `jdk.Deoptimization` — deopt 이벤트 (reason, action)
- `jdk.CompilerPhase` — phase별 시간 (C2 phase 어디서 오래 걸리나)

**JMC (JDK Mission Control)**로 열어 시각화 — 메서드별 컴파일 시간 막대그래프, deopt heatmap.

### `jcmd` 즉시 조회

```bash
# Code Cache 사용량
jcmd <pid> Compiler.codecache
# 출력:
#   CodeCache: size=245760Kb used=43210Kb max_used=45123Kb free=202550Kb
#   bounds [0x..., 0x...]
#   total_blobs=12345 nmethods=10000 adapters=2345

# 컴파일 큐 (적체 확인)
jcmd <pid> Compiler.queue
# 출력:
#   Contents of C1 compile queue: 0 methods
#   Contents of C2 compile queue: 5 methods
#     [bci=42, level=4] com.MyClass::method

# 현재 JIT 옵션
jcmd <pid> VM.flags | grep -i compile
```

### Linux `perf` + perf-map-agent — CPU 프로파일 + JIT 메서드 이름

```bash
# 1. perf-map-agent 빌드 + 첨부
java -agentpath:libperfmap.so -jar app.jar
# → /tmp/perf-<pid>.map 생성 (JIT 메서드 주소 → 이름 매핑)

# 2. perf로 CPU 프로파일
sudo perf record -F 99 -p <pid> -g -- sleep 30
sudo perf report

# JIT가 만든 메서드 이름까지 표시됨 (그게 없으면 그냥 [unknown])
```

운영의 hot path 분석 시 표준 조합.

### async-profiler — production에서 가장 많이 씀

```bash
# 다운로드 후
./profiler.sh -d 30 -f /tmp/profile.html <pid>
```

장점:
- Sampling 기반, 부하 거의 없음
- JIT 메서드 이름 자동 (자체 perf-map 통합)
- Flame graph 즉시 생성
- `-e alloc`으로 allocation profile, `-e wall`로 wall-clock

### 운영 결정 매트릭스

| 상황 | 도구 |
|---|---|
| 항상 켜둠 | `-XX:+PrintCompilation` (가벼움) |
| Production tail latency 분석 | JFR `jdk.Compilation` + `jdk.Deoptimization` |
| Production CPU hot path | async-profiler / perf + perf-map-agent |
| 인라인 실패 원인 | `-XX:+PrintInlining` + JITWatch |
| SIMD 적용 확인 | `+PrintAssembly` + hsdis |
| C2 phase 동작 학습 | `+PrintIdealGraph` + IdealGraphVisualizer |
| Code Cache 차는지 | `jcmd Compiler.codecache` 주기 polling |
| 컴파일 큐 적체 | `jcmd Compiler.queue` |

### Killer 시나리오 — production warmup이 너무 길다

```
환경: Spring Boot 큰 monolith, JIT warmup이 10분
증상: scale-out 후 새 인스턴스가 10분간 throughput 절반

진단:
  1. JFR JFR.start name=warmup duration=600s 켜놓고 부팅
  2. jfr print --events jdk.Compilation | sort -k duration -n -r | head -50
     → 시간 ↑ 메서드 top 50 식별
  3. async-profiler로 CPU profile — JIT 자체가 CPU를 먹는지, 인터프리터 코드인지
  4. -XX:+PrintInlining 로그에서 "too big" / "not inlineable" 빈도

원인 후보:
  - 너무 많은 메서드가 컴파일 큐에 쌓임 → CICompilerCount 부족
  - 거대 메서드들 C2 컴파일 자체가 오래 걸림
  - Profile pollution → 재컴파일 반복

조치:
  - CDS (Class Data Sharing) + AppCDS 활성화 → class loading 단축
  - -XX:CICompilerCount=N 늘림 (CPU 많을 때)
  - 큰 메서드 분할
  - JDK 21+ Leyden CDS+AOT으로 profile 재사용
```

### 시니어 한 줄

> **"JIT 모니터링의 기본 조합은 'JFR continuous + async-profiler ad-hoc'. PrintCompilation/PrintInlining은 디버그용, PrintAssembly/PrintIdealGraph는 학습용. production에서 답을 찾는 도구는 JFR과 flame graph 두 개로 충분하다."**

---

## 8. JIT와 GC의 상호작용이 성능에 미치는 영향

### 한 줄 정의

> **JIT와 GC는 같은 RSS 안에서 공존하며 5가지 접점에서 서로 영향. Safepoint(STW 동기화), OopMap(GC root 식별), Code Cache vs Heap(메모리 경쟁), Write Barrier(JIT 최적화 비용), 그리고 EA(GC 부담 직접 절감). 시니어가 알아야 할 핵심은 "JIT가 GC를 도와줄 수도, 발목 잡을 수도 있다"는 양면성.**

### 5가지 접점

```
[1] Safepoint Polling — STW 동기화 비용
[2] OopMap — GC root 식별 메타데이터
[3] Code Cache vs Heap — 메모리 경쟁
[4] Write Barrier — Generational GC를 위한 JIT 코드의 추가 instruction
[5] Escape Analysis — JIT가 GC 부담을 직접 줄임
```

### 8.1 Safepoint Polling — JIT 코드의 STW 도달 비용

```
GC 시작 전 모든 application thread가 safepoint에 도달해야 STW 가능
   │
   ▼
JIT가 native code에 "safepoint poll" 명령을 박아둠:
   - 루프 backedge마다
   - 메서드 entry / return마다
   - call site마다
   │
   ▼
poll = global "safepoint requested" 비트 확인 → 요청 있으면 park
```

```
[Safepoint poll의 모양 (x86 example)]
0x... : test %eax, [safepoint_polling_page]    ; 1 instruction
       └─ 그 페이지가 protected면 SIGSEGV → safepoint handler 진입
       
0x... : (loop body)
0x... : jne loop_start
0x... : test %eax, [safepoint_polling_page]    ; ★ 매 iter
```

트레이드오프:
- **너무 빽빽이 박으면**: 매 iteration 1 instruction → throughput ↓
- **너무 드물게 박으면**: 큰 루프가 끝날 때까지 STW 못 시작 → "time-to-safepoint" 길어짐 → STW pause가 길어 보임

옵션:
- `-XX:+UseCountedLoopSafepoints` (JDK 10+ default): counted loop에도 poll 박음.
- 옛날엔 큰 `for (int i = 0; i < BILLION; i++)`이 safepoint 안 박혀서 GC가 그 루프 끝까지 기다림 → P99 spike의 흔한 원인.

진단:
```bash
# Time-to-safepoint 추적
-XX:+PrintSafepointStatistics -XX:PrintSafepointStatisticsCount=1

# JFR
jfr print --events jdk.SafepointBegin,jdk.SafepointStateSynchronization profile.jfr
```

### 8.2 OopMap — JIT 코드의 GC root 식별

```
GC가 root scan할 때 "이 스택 슬롯이 oop(reference)인지 primitive(int 등)인지" 알아야 함
   │
   ▼
JIT가 컴파일 시 메서드의 각 safepoint마다 OopMap 생성:
   - 어느 register가 oop인지
   - 어느 stack slot이 oop인지
   - 메타데이터로 nmethod에 저장
   │
   ▼
GC root scan: safepoint에 멈춘 스레드의 PC → 해당 OopMap → 정확한 oop만 mark
```

비용:
- OopMap 자체가 메모리를 차지 (nmethod의 ~10~30%)
- safepoint를 더 박을수록 OopMap 더 많이 생성
- 컴파일 시간 ↑

이게 인터프리터보다 JIT의 root scan을 무겁게 만드는 본질 — 다만 OopMap이 미리 있어 빠르게 처리 가능.

### 8.3 Code Cache vs Heap — 메모리 경쟁

```
JVM 프로세스의 RSS:
    Heap (200MB ~ TB)
    Metaspace (수십~수백 MB)
    Code Cache (수십~수백 MB)
    Thread stacks
    Direct memory
    GC bookkeeping
    └─ 모두 같은 OS 메모리에서 경쟁

Code Cache 차면:
    JIT compilation 중단
    "CodeCache is full. Compiler has been disabled."
    → 새 메서드 인터프리터로만 → throughput 절반 이하

GC가 클래스 unload하면:
    그 클래스에 의존하던 nmethod 모두 invalidate
    → "made not entrant" → 다음에 새로 컴파일
    → 이 청소를 "nmethod sweeper"가 수행
```

옵션:
- `-XX:ReservedCodeCacheSize=512m` (기본 240MB) — 대규모 앱은 키워야 함
- `-XX:+UseCodeCacheFlushing` (기본 on) — 사용 안 되는 nmethod 회수

진단:
```bash
jcmd <pid> Compiler.codecache
# used/max_used/free + segment별 사용량 (non-profiled, profiled, non-nmethods)
```

### 8.4 Write Barrier — Generational GC를 위한 JIT 코드의 추가 instruction

```
Generational GC는 "Old → Young 참조" 추적이 필요 (Card Table / Remembered Set)
   │
   ▼
모든 reference store 명령 후에 barrier 코드를 박아야 함:
   field = newRef;
   → JIT 컴파일된 native:
       mov [obj + offset], newRef       ; 1. store
       mov [card_table + obj>>9], 0     ; 2. ★ write barrier — 카드 dirty 표시
```

GC별 barrier 비용:
| GC | Write Barrier | 비용 |
|---|---|---|
| Serial / Parallel | Card Table mark | 1 store |
| G1 | Card Table + SATB pre-barrier | ~3 instructions |
| ZGC | Load Barrier (포인터 mask check) | ~2 instructions per load |
| Shenandoah | Brooks Pointer indirection | load 시 추가 dereference |

총 비용: 일반적으로 throughput의 ~5~15%. JIT가 이 barrier를 어떻게 잘 펼치느냐가 중요.

```
G1 barrier 최적화 예:
- 같은 객체에 연속 store하면 barrier 한 번만
- non-reference store는 barrier 생략
- thread-local 객체는 barrier 생략 (EA로 결정)
```

### 8.5 Escape Analysis — JIT가 GC 부담을 직접 줄임

```
EA가 NoEscape로 판정한 객체:
    new Point(x, y) → Scalar Replacement
    → heap allocation 없음
    → GC가 볼 일 없음
    → allocation rate ↓
    → Minor GC 빈도 ↓
    → 결과: JIT가 GC 부담을 직접 줄임

allocation rate가 1GB/s → 500MB/s가 되면
Minor GC 빈도가 절반으로 떨어짐 → throughput +10~20%
```

운영 확인:
```bash
# Allocation rate (JFR)
jfr print --events jdk.ObjectAllocationInNewTLAB,jdk.ObjectAllocationOutsideTLAB

# EA on/off 비교
-XX:-DoEscapeAnalysis   # off로 실행해서 allocation rate 비교
```

EA가 깨지는 흔한 패턴:
- 객체를 collection에 넣음 (ArgEscape)
- 객체를 instance field에 저장 (GlobalEscape)
- `synchronized(thisLocalObj)` 자체는 OK지만 그 객체 reference가 escape하면 EA 깨짐
- 리플렉션 / `Object.getClass()` 호출 (구버전 JVM에선 escape 유발)

### 통합 그림 — JIT가 GC를 도와주는 / 발목 잡는 경로

```
[JIT가 GC를 도와주는 경로]
    Escape Analysis → Scalar Replacement → heap allocation ↓
    Inline + DCE → 죽은 코드의 allocation 제거
    Lock Elision → synchronized 자체 제거 → GC와 무관하지만 throughput ↑

[JIT가 GC를 무겁게 하는 경로]
    OopMap 생성 비용 (메모리 + 컴파일 시간)
    Safepoint poll instruction (매 backedge)
    Write Barrier instruction (모든 ref store)
    Code Cache 점유 (Heap 외 메모리 압박)
    Deopt 시 GC root 변동 (인터프리터 frame으로 재구성)

→ 순효과: EA가 잡힌 hot path는 throughput +20~40%, GC 빈도 절반.
   EA 깨진 hot path는 barrier 비용 + allocation 부담의 풀 cost.
```

### Killer 시나리오 — GC 자주 도는데 JIT가 원인

```
환경: 대용량 처리 서버, allocation rate 2GB/s, Minor GC 2초마다
증상: GC time 비율 15%, P99 spike

진단 1. JFR로 allocation 발생 메서드 top:
  jfr print --events jdk.ObjectAllocationInNewTLAB profile.jfr | head -30
  → 특정 hot path에서 allocation 집중

진단 2. EA 동작 확인:
  -XX:+UnlockDiagnosticVMOptions -XX:+PrintEscapeAnalysis
  → "GlobalEscape: this escapes via field store"

진단 3. 원인 코드:
  - 객체를 ConcurrentHashMap에 put → GlobalEscape → EA 깨짐
  - Optional.of(x).get() 같은 wrapping이 escape 분석 한계

조치:
  - hot path에서 wrapping 객체를 primitive로 대체
  - ThreadLocal 객체 pool (단, EA가 더 빠를 수 있어 측정 필요)
  - 큰 byte[] reuse (clear() 후 재사용)
  - 결과: allocation rate 500MB/s로 ↓ → Minor GC 8초마다로 ↓ → GC time 4%로 ↓

교훈: GC 튜닝의 80%는 "allocation rate 줄이기"고, 그건 JIT의 EA가 잡히도록 코드 짜기.
```

### 운영 진단 표

| 증상 | JIT × GC 접점 | 진단 |
|---|---|---|
| STW pause가 길어 보임 (실제 GC는 짧음) | Safepoint 도달 지연 | `-XX:+PrintSafepointStatistics`, time-to-safepoint |
| GC root scan이 큰 비중 | OopMap / Code Cache 크다 | JFR `jdk.GCPhasePauseLevel*` |
| JIT compilation 중단됨 | Code Cache 부족 | `jcmd Compiler.codecache` |
| Allocation rate 높음 | EA 깨짐 | `-XX:+PrintEscapeAnalysis`, JFR allocation |
| Reference store 비싼 hot path | Write Barrier | JIT assembly 직접 보기, G1 → Parallel 비교 |
| Deopt 자주 + GC root 변동 | Deopt | JFR `jdk.Deoptimization` |

### 시니어 한 줄

> **"JIT와 GC는 같은 RSS 안에서 공존한다. EA는 JIT가 GC를 도와주는 유일한 큰 무기 — allocation rate를 직접 줄이고, 그게 GC 빈도를 절반으로 만든다. 반대로 Safepoint poll, Write Barrier, Code Cache 점유는 JIT가 GC에 내는 세금이다. production에서 GC pause가 길다면 답의 절반은 'EA가 잡히도록 코드 짜기'고, 옵션 노브는 그다음이다."**

---

## 종합 — 8문항 한 줄 정리표

| # | 질문 | 한 줄 답 |
|---|---|---|
| 1 | JIT vs AOT | profile + speculation의 우위(JIT) vs cold start + footprint의 우위(AOT). 본질은 "프로파일 입력 가능 여부" |
| 2 | C2 옵티마이저 단계 | Parse → IterGVN → Inline+EA → Loop → Macro+CCP → Sched+RA → Output. fixpoint cascade가 핵심 |
| 3 | C1 vs C2 | 사명이 다르니 IR도 다르다 — CFG(C1) 단순·빠름, Sea-of-Nodes(C2) 자유·공격. Tiered 양립의 본질 |
| 4 | 프로파일링 데이터 | invocation/backedge counter, type histogram, branch profile, null stats — speculative optimization 입력. pollution이 가장 큰 적 |
| 5 | AOT 장단점 | 부팅 ms + footprint ↓ vs peak ~80~95% + reflection 제약. 단기 함수는 Native Image, 장기 서버는 HotSpot, 절충은 Leyden |
| 6 | Deoptimization | unstable_if, class_check, unreached, null_check, range_check 5종 trap. P99 spike의 흔한 원인. 해결은 코드 단순화 |
| 7 | JIT 모니터링 | PrintCompilation 상시 + JFR jdk.Compilation/Deopt + async-profiler가 production 기본 조합 |
| 8 | JIT × GC 상호작용 | Safepoint·OopMap·Write Barrier가 JIT의 GC 세금, EA가 JIT의 GC 보너스. allocation rate가 GC 튜닝의 80% |

---

## 다음 단계

- → [01-execution-overview](../03-execution-engine/01-execution-overview.md): 실행 엔진 전체 그림
- → [03-tiered-compilation](../03-execution-engine/03-tiered-compilation.md): Tier 0~4 흐름
- → [04-c1-and-c2](../03-execution-engine/04-c1-and-c2.md): C1/C2 IR과 phase 깊이
- → [05-inlining-and-ic](../03-execution-engine/05-inlining-and-ic.md): 인라인의 사슬
- → [06-escape-analysis](../03-execution-engine/06-escape-analysis.md): EA × Scalar Replacement
- → [07-loop-and-vector](../03-execution-engine/07-loop-and-vector.md): Loop opts × SIMD
- → [08-speculative-and-deopt](../03-execution-engine/08-speculative-and-deopt.md): Speculation × Deopt 풀버전
- → [08-graalvm](../08-graalvm/README.md): GraalVM JIT + Native Image
- → [10-ops-scenarios](../10-ops-scenarios/): 실전 운영 시나리오
