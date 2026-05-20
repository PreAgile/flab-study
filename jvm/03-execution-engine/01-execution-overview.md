# 03-01. Execution Engine 전체 흐름 — Bytecode가 native code가 되기까지

> JVM 시작 직후 5분간 P99가 2000ms, 그 후 50ms로 안정 — 이 곡선의 정체는 무엇인가?
> 한 메서드는 처음엔 인터프리터로 시작하고, ~1500회 호출되면 C1이 컴파일, ~10000회면 C2가 공격적 최적화. 가정이 깨지면 deopt로 인터프리터 복귀. 모든 게 시간에 따라 동적으로 일어난다.
> 시니어가 알아야 할 것: warmup 지연, P99 spike, "왜 같은 코드가 어떨 때는 빠르고 어떨 때는 느린가" — 모두 이 흐름의 어느 단계인지의 문제다.

---

## 이 문서의 사용법

이 문서는 **면접용 마인드맵**을 따라 선형으로 펼친 구조다. 학습 순서 = 면접 답변 순서 = 백지에 그리는 순서.

1. **0장 마인드맵을 먼저 외운다** — 루트 한 문장 + 5가지 가지 + 각 가지의 키워드 3개.
2. **1~5장을 순서대로 학습한다** — 각 장이 마인드맵의 한 가지에 정확히 대응.
3. **6장 면접 워크플로우로 검증** — 질문을 보면 어느 가지로 가야 하는지 매핑.
4. **7장 꼬리질문으로 깊이 점검**.

---

## 0. 마인드맵 — 면접 종이에 그릴 그림

### 루트 한 문장 (anchor)

> **"Execution Engine은 한 메서드를 시간에 따라 인터프리터 → C1 → C2로 동적 승격시키는 시스템이다. 시작은 즉시 실행 가능한 인터프리터, 정상 상태는 C2 native code, 가정 깨지면 deopt로 인터프리터 복귀. 5단계 라이프사이클이 한 메서드 안에서 일어난다."**

이 한 문장에서 모든 답변이 출발한다. 어떤 질문이 와도 이 문장부터 말하고 적절한 가지로 분기.

### 5개 가지 — 순서를 외운다

```
                 [ROOT: 한 메서드의 5단계 동적 승격]
                                │
       ┌──────────┬─────────────┼─────────────┬──────────┐
       │          │             │             │          │
      ① WHY    ② WHAT          ③ HOW         ④ 운영    ⑤ 진화
   왜 단계적    5단계 라이프   OSR + Deopt   (시니어    (-server→
   승격인가?    사이클         두 메커니즘   진단)     Tiered)
       │          │             │             │          │
       │     ┌────┼────┐    ┌───┼───┐    ┌────┼────┐    │
   즉시성/   T0    T3    T4 OSR  Deopt  Print  JFR  -server
   profile/  Int.  C1    C2 메   메     Compi  jdk.Comp  C2-only
   안전판    +MDO  +prof opt  서   카   lation lation   →Tiered
                              드    니   /Code  /Code   /Graal/
                              중   즘   Cache  Cache   Leyden
                              loop
```

### 가지별 핵심 키워드 (각 가지 3개씩만)

| 가지 | 키워드 1 | 키워드 2 | 키워드 3 |
|---|---|---|---|
| **① WHY 단계적 승격** | 즉시성 (인터프리터) | profile-guided opt | speculation 안전판 |
| **② WHAT 5단계 라이프사이클** | T0 Interpreter+MDO | T3 C1+profile | T4 C2 fully opt |
| **③ HOW OSR + Deopt** | OSR (긴 loop 진입) | Deopt (가정 깨짐) | 둘 다 stack frame 변환 |
| **④ 운영 진단** | PrintCompilation | JFR Compilation/Deopt | Code Cache 압박 |
| **⑤ 진화** | -server/-client | Tiered 기본 on (JDK8) | Graal/Leyden |

### 면접 답변 흐름

> 면접관 질문 → 루트 문장 → 질문에 맞는 가지 1개 선택 → 그 가지의 키워드 3개 순서대로 설명 → 듣는 사람의 관심에 따라 인접 가지로 확장

---

## 1. 가지 ①: WHY — 왜 단계적 승격인가

### 1.1 핵심 질문

> "JVM이 그냥 C2로 바로 컴파일하면 가장 빠를 텐데, 왜 인터프리터부터 시작해 단계적으로 올라가나요?"

### 1.2 키워드 1 — 즉시성 (인터프리터로 시작)

```
[C2로 바로 컴파일하면 (가상)]
JVM 시작 → C2 컴파일 시작 (수십 ms × N 메서드)
       → 사용자 코드 실행까지 수 초~수십 초 지연 → warmup 불가

[Interpreter로 시작 (실제)]
JVM 시작 → 즉시 인터프리터 실행
       → 사용자 코드 즉시 응답 (느리지만)
       → 백그라운드에서 컴파일 → 점진적 가속
```

C2는 메서드당 수십~수백 ms 소요. 모든 메서드 C2로 컴파일하면 시작이 영원히 안 됨. **Interpreter는 즉시성, JIT은 궁극 성능**. 둘 다 필요.

### 1.3 키워드 2 — Profile-Guided Optimization

```
[C2 단독 (Tiered off)]                  [Tiered (T0 → T3 → T4)]
━━━━━━━━━━━━━━━━━                       ━━━━━━━━━━━━━━━━━━

profile 없이 컴파일                     T0 Interpreter + T3 C1에서 profile 수집
   ↓                                       ↓
type-guess 부정확 → deopt 빈발          C2가 정확한 profile로 컴파일
inlining 결정 보수적                    공격적 inlining + EA + speculation
```

C1은 단순히 "C2 전 단계"가 아니라 **profile 수집기**. type histogram, branch taken/not, call site receiver 등을 모아 C2의 의사결정 입력으로 흘려보냄.

### 1.4 키워드 3 — Speculation의 안전판이 deopt

C2는 "이 분기는 거의 안 일어남", "이 type은 항상 String" 같은 **가정**으로 inline + 분기 제거 같은 공격적 최적화를 한다. 가정이 항상 맞다는 보장은 없음. **안전판은 Deopt** — 가정 깨지면 native code를 폐기하고 인터프리터로 돌아간다.

→ Speculation + Deopt가 함께 동작해야 공격적 최적화 가능. Deopt 없으면 speculate도 못 함.

### 1.5 비유로 굳히기

> **학생의 성장 비유**: Interpreter = 교과서를 한 줄씩 읽음 (느리지만 즉시 시작). C1 = 자주 보는 챕터를 약식 노트로. C2 = 핵심 챕터를 완성판 노트로 (오래 걸리지만 가장 빠름). Deopt = 노트의 가정이 틀린 걸 발견 → 교과서로 돌아가 다시 공부.

---

## 2. 가지 ②: WHAT — 5단계 라이프사이클

### 2.1 핵심 질문

> "메서드 하나가 처음 호출되는 순간부터 native code로 실행되기까지 어떤 단계를 거치나요?"

### 2.2 키워드 1 — Tier 0: Cold Start (Interpreter + MDO)

```
호출 1~수십 회
  ↓
Template Interpreter가 bytecode 한 줄씩 실행
  ↓
호출 카운터 +1, MDO (Method Data Object) 점진 채움
  - call site별 type histogram
  - branch taken/not taken 비율
  - loop back-edge 카운트
```

이 단계의 인터프리터는 단순한 "느린 실행기"가 아니라 **JIT 컴파일러의 입력을 만드는 profiler**. (자세히는 [02-template-interpreter](./02-template-interpreter.md).)

### 2.3 키워드 2 — Tier 3: C1 + Profile

```
호출 카운터가 임계 (대략 1500) 도달
  ↓
Compile Broker에 task 등록 (Tier 3)
  ↓
CompilerThread가 pickup → C1 컴파일 (수 ms)
  ↓
nmethod를 Code Cache의 Profiled segment에 저장
  ↓
Method._code 필드 patch → 다음 호출부터 native code
  ↓
★ native code에 profile counter 내장 — 실행 중에도 profile 계속 수집
```

C1의 결과 코드는 약식 최적화 + profiling instrumented. 빠르게 만들어지지만 C2의 ~50% 성능. (자세히는 [03-tiered-compilation](./03-tiered-compilation.md).)

### 2.4 키워드 3 — Tier 4: C2 Fully Optimized

```
호출 카운터가 더 큰 임계 (대략 10000) 도달 + profile 안정
  ↓
Compile Broker에 task 등록 (Tier 4)
  ↓
CompilerThread가 C2 컴파일 (Sea-of-Nodes, 수십~수백 ms)
  ↓
공격적 최적화 적용:
  - Inlining (cross-method 최적화 활성)
  - Escape Analysis (Scalar Replacement)
  - Loop Unroll + SuperWord (SIMD)
  - Speculation + Uncommon Trap
  ↓
nmethod를 Code Cache의 Non-profiled segment
  ↓
옛 C1 nmethod → not_entrant → Sweeper가 회수
  ↓
정상: C2 native code로 계속 실행
가정 위반: Deopt → Interpreter 복귀 → 재컴파일
```

### 2.5 Tier 5종 (HotSpot 명세)

```
Tier 0: Interpreter (MDO 수집)
Tier 1: C1 (profiling 없음) — rare, fallback
Tier 2: C1 (제한적 profiling) — rare
Tier 3: C1 (전체 profiling) — Tiered의 기본 C1 단계
Tier 4: C2 (fully optimized) — 최종 단계
```

운영자는 **Tier 0, 3, 4** 만 의식하면 충분. Tier 1, 2는 HotSpot 내부 fallback.

### 2.6 Method._code 필드 patch — atomic transition

각 `Method` 객체는 `_from_compiled_entry` (컴파일된 코드 진입점), `_from_interpreted_entry` (인터프리터 stub), `_code` (현재 nmethod) 세 필드를 들고 있음.

흐름:
1. C1 컴파일 완료 → `_from_compiled_entry`를 C1 nmethod entry로 patch.
2. C2 완료 시 같은 방식 patch.
3. Deopt 시 다시 인터프리터 stub으로 patch.

**핵심**: patch는 **atomic word write** — 동시 실행 중인 다른 스레드도 안전. 다음 호출부터 새 entry 사용.

---

## 3. 가지 ③: HOW — OSR + Deopt 두 메커니즘

### 3.1 핵심 질문

> "메서드가 한 번만 호출되는데 그 안의 loop가 10억 번 도는 경우는? 또 C2가 컴파일한 코드의 가정이 깨지면?"

### 3.2 키워드 1 — OSR (On-Stack Replacement)

```java
void main() {
    for (int i = 0; i < 1_000_000_000; i++) {  // 10억 회
        process(i);
    }
}
```

- 메서드 호출은 1회 → invocation counter는 1.
- Loop body는 10억 회 → backedge counter 폭증.
- 호출 카운터로는 영원히 임계 미달 → 인터프리터로 영원히 실행 (10× 손실).

**OSR 메커니즘**:
1. 인터프리터가 loop back-edge 카운터도 수집.
2. 임계 도달 → OSR compilation 트리거.
3. C1/C2가 그 메서드의 OSR variant 컴파일 (entry point가 일반 entry와 다름 — 특정 bytecode index에서 진입 가능).
4. 다음 iteration에서 interpreter frame → native frame **stack 위에서 직접 교체**.
5. Loop 나머지를 native code로 실행.

→ OSR 없으면 long-running loop는 인터프리터에 갇힘. HotSpot의 가장 정교한 메커니즘 중 하나.

### 3.3 키워드 2 — Deoptimization (가정 깨짐)

C2는 가정 위에서 공격적 최적화. 깨지면 **deopt**:

```
[C2 nmethod 실행 중, 가정 위반 감지]
예: 인터페이스 메서드가 항상 FooImpl이라 가정하고 inline.
    새 BarImpl 등장 → CHA 위반.
  ↓
영향받는 nmethod에 _is_not_entrant 플래그 set
다음 호출은 인터프리터로
  ↓
이미 실행 중인 스레드: 다음 safepoint 도달 → JVM이 deopt 시작
  1. Native frame의 PC, register, stack 값을 OopMap으로 해석
  2. 대응하는 bytecode index 찾기
  3. Interpreter frame을 새로 만들고 local/operand stack 값 복원
  4. 그 interpreter frame부터 실행 재개
  ↓
다시 인터프리터, MDO 갱신, 시간 지나 재컴파일
```

→ Deopt는 "단순 느려짐"이 아니라 **정확성 보존** — 잘못된 native code 결과를 막는 안전판. (풀버전은 [08-speculative-and-deopt](./08-speculative-and-deopt.md).)

### 3.4 키워드 3 — 둘 다 stack 위에서 frame 변환

| | OSR | Deopt |
|---|---|---|
| 방향 | Interpreter → Native | Native → Interpreter |
| 트리거 | Loop back-edge 카운터 | Speculation 위반 |
| Frame 변환 | Interpreter frame → Native frame | Native frame → Interpreter frame |
| 성능 영향 | 가속 (slow → fast) | 감속 (fast → slow) |

공통: ScopeDesc / OopMap 사용. Local/operand stack 값 보존. HotSpot이 stack 위의 frame을 통째로 다른 형태로 바꾸는 정교한 작업.

### 3.5 운영 시나리오와 5단계 매핑

| 운영 증상 | 5단계의 어디 | 원인 |
|---|---|---|
| JVM 시작 직후 응답 느림 | Tier 0+3 | 모든 메서드 인터프리터, C1 컴파일 진행 중 |
| 트래픽 시작 후 5분간 P99 ↑ | Tier 3~4 | C2 컴파일이 누적 |
| 정상 운영 중 P99 가끔 spike | Stage 5의 Deopt | speculation 깨짐 |
| 부하 변화 후 일시적 느려짐 | Tier 3 → 4 또는 Deopt | 새 코드 path가 hot, 재컴파일 진행 |
| 영원히 느린 메서드 | Tier 0 또는 3에 갇힘 | Code Cache full → 컴파일 비활성 또는 make_not_compilable |

---

## 4. 가지 ④: 운영 — 시니어 진단

### 4.1 핵심 질문

> "실무에서 JIT 관련 증상을 어떻게 진단하나요? Warmup 지연, P99 spike, 영구 느려짐 — 각각의 도구는?"

### 4.2 키워드 1 — `-XX:+PrintCompilation` (실시간 컴파일 로그)

```bash
java -XX:+PrintCompilation -jar app.jar 2>&1 | head -20
```

출력:
```
     38    1   n 0       java.lang.Object::<init> (1 bytes)
    140    2     3       java.lang.String::hashCode (49 bytes)
    142    3 %   4       MyApp::process @ 12 (123 bytes)
    150    4       4       MyApp::process (123 bytes)
   2100    5       3 made not entrant   MyApp::oldVersion (50 bytes)
```

필드 해석:
- **38** — JVM 시작 후 ms.
- **1** — compile ID.
- **n / s / ! / %** — flag: `n`=native, `s`=synchronized, `!`=exception handler, `%`=OSR.
- **0/3/4** — Tier.
- **made not entrant** — deopt 또는 superseded (C1 → C2 승격 후 옛 nmethod 회수).

운영 의미:
- Tier 3 → 4 승격이 보이면 정상 warmup.
- `made not entrant` 많음 → deopt 폭주 의심.
- 시간 지나도 새 컴파일 없음 → Code Cache 의심.

### 4.3 키워드 2 — JFR Events

```bash
jcmd <pid> JFR.start name=jit duration=300s settings=profile filename=jit.jfr
jfr summary jit.jfr | grep -E 'Compilation|Deoptimization|CodeCache'
```

핵심 이벤트:
- `jdk.Compilation` — 각 컴파일 task의 시간/결과/tier.
- `jdk.CompilerInlining` — inlining 결정.
- `jdk.Deoptimization` — deopt 발생 + reason.
- `jdk.CodeCacheStatistics` — 주기적 사용량.
- `jdk.OSREvent` — OSR 발생.

`reason` 필드의 주요 값: `unstable_if`, `class_check`, `unreached`, `null_check`, `range_check`.

### 4.4 키워드 3 — Code Cache 압박

```bash
jcmd <pid> Compiler.codecache | grep -E 'stopped|non-profiled|profiled'
```

- `stopped_count > 0` → JIT 한 번이라도 멈춤.
- 각 segment 100% 도달 → full → 새 컴파일 거부 → 메서드들이 영원히 인터프리터.

자세한 건 [02-04 Code Cache](../02-runtime-data-areas/04-code-cache.md).

### 4.5 운영 시나리오 진단 매트릭스

| 증상 | 명령 | 가능 원인 | 조치 |
|---|---|---|---|
| 시작 직후 5분 응답 느림 | `-XX:+PrintCompilation` 컴파일 진행 확인 | 정상 warmup | K8s readiness probe에 합성 부하 |
| P99 가끔 spike | JFR `jdk.Deoptimization` burst | speculation 깨짐 | 코드 audit (polymorphic 줄이기) |
| 모든 게 느림 (영구) | `Compiler.codecache` stopped_count | Code Cache full | ReservedCodeCacheSize ↑ |
| 부하 변화 후 일시 느림 | `-XX:+PrintCompilation` 새 burst | 새 path가 hot, 재컴파일 | 정상 — 시간 후 안정 |
| `made not entrant` 폭주 | JFR `jdk.Deoptimization` reason | 잦은 deopt | code structure 단순화 |

### 4.6 Killer 시나리오 — "시작 후 5분간 P99 2000ms"

> **단계적 진단**:
>
> 1. **정상 warmup vs 비정상 구분**:
>    - `-XX:+PrintCompilation` 5분간 활발한 컴파일 → 정상 warmup.
>    - 컴파일 거의 없음 → 비정상 (Code Cache full, CompilerThread 부족 등).
>
> 2. **Code Cache 확인**:
>    ```
>    jcmd <pid> Compiler.codecache
>    # stopped_count > 0 → JIT 비활성
>    ```
>
> 3. **JFR로 시간대별**:
>    ```
>    jcmd <pid> JFR.start duration=300s filename=warmup.jfr
>    # jdk.Compilation, jdk.Deoptimization, jdk.GarbageCollection 분포
>    ```
>
> 4. **조치 옵션**:
>    - 정상 warmup → K8s readiness probe에 warmup 시뮬레이션, AppCDS, AOT 검토.
>    - Code Cache 부족 → `-XX:ReservedCodeCacheSize=512m`.
>    - Deopt 빈발 → 코드 audit.
>    - GC 길면 → GC 튜닝 (Chapter 04).

---

## 5. 가지 ⑤: 진화 — `-server`/`-client` → Tiered → Graal/Leyden

### 5.1 핵심 질문

> "JIT 컴파일 전략은 어떻게 변해왔고, 앞으로 어디로 가나요?"

### 5.2 키워드 1 — `-server` vs `-client` (JDK 7까지)

| | -server | -client |
|---|---|---|
| 컴파일러 | C2만 | C1만 |
| Startup | 느림 | 빠름 |
| Peak | 빠름 | 느림 |
| 대상 | 거대 서버 | 데스크탑 |

문제: 사용자가 둘 중 하나 선택. 거대 서버 앱은 startup도 peak도 둘 다 필요.

### 5.3 키워드 2 — Tiered Compilation (JDK 8 기본 on)

```
[Tiered]
한 JVM이 C1 + C2 둘 다 사용
시작은 C1으로 빠르게, hot method는 C2로 깊게
→ warmup 빠름 + peak 빠름 양립

-server/-client 옵션 사실상 의미 없음 (JDK 9+ deprecated)
```

이게 현대 JVM의 표준. (자세히는 [03-tiered-compilation](./03-tiered-compilation.md).)

### 5.4 키워드 3 — Graal / Leyden (미래)

| 연도 | 변화 | 의의 |
|---|---|---|
| 2018 | JDK 11 Graal 옵션 | C2의 Java 버전 (Partial EA 등 더 공격적) |
| 2023 | JDK 21 | Vector API stable, Loom |
| 2024+ | Project Leyden | AOT/CDS 통합 — startup 거의 instant |

- **Graal**: C2의 50,000줄 C++을 Java로 재작성. modular + 더 정교한 알고리즘. GraalVM의 Native Image는 AOT.
- **Leyden**: 런타임 정보를 빌드 시간으로 끌어와 startup 최적화. Spring Native, Quarkus 같은 트렌드.

### 5.5 역사 타임라인

| 연도 | 릴리스 | 변화 |
|---|---|---|
| 1995 | Sun JIT | 첫 JIT |
| 1999 | HotSpot 1.0 | C1 |
| 2000 | HotSpot 1.3 | C2 |
| 2007 | JDK 6u20 | Tiered 실험 |
| 2014 | JDK 8 | **Tiered 기본 on** |
| 2018 | JDK 11+ | Graal 옵션 |
| 2020 | JDK 16+ | Sweeper concurrent 개선 |
| 2024+ | JDK 22+ | Project Leyden (AOT/CDS) |

---

## 6. 면접 답변 워크플로우

### 6.1 질문 → 가지 매핑

| 면접 질문 | 진입 가지 | 인접 확장 |
|---|---|---|
| "JVM이 메서드를 어떻게 실행하나요?" | ② WHAT | ① WHY로 단계 이유 |
| "왜 인터프리터부터 시작?" | ① WHY (즉시성) | ② WHAT 5단계 |
| "OSR이 뭔가요?" | ③ HOW (OSR) | ② WHAT의 Tier 진행 |
| "Deoptimization은?" | ③ HOW (Deopt) | ① WHY (안전판) |
| "Warmup 지연 진단" | ④ 운영 | ② WHAT의 어느 단계 |
| "P99 spike 원인" | ④ 운영 (Deopt) | ③ HOW |
| "Tiered 왜 만들었나" | ⑤ 진화 | ① WHY (profile-guided) |
| "Graal과 C2의 차이" | ⑤ 진화 | ② WHAT (T4) |

### 6.2 답변 템플릿

> **루트 문장 → 해당 가지 키워드 3개 → 듣는 사람 표정 보고 인접 가지로**

예: "JVM이 메서드를 어떻게 실행하나요?"

> "Execution Engine은 한 메서드를 시간에 따라 인터프리터에서 C2로 동적 승격시키는 시스템입니다. (← 루트)
> 5단계 라이프사이클로 흘러갑니다.
> 첫째, **Tier 0**: Template Interpreter가 bytecode를 한 줄씩 실행하면서 동시에 MDO에 type/branch profile을 모읍니다.
> 둘째, **Tier 3 (C1)**: 호출이 ~1500회 도달하면 Compile Broker가 C1 컴파일을 트리거합니다. C1은 수 ms 안에 약식 최적화 + profiling instrumented native code를 만듭니다.
> 셋째, **Tier 4 (C2)**: ~10000회 + profile이 안정되면 C2가 Sea-of-Nodes 기반 공격적 최적화를 적용합니다. Inlining, EA, Loop Unroll, Speculation까지.
> 정상 상태에서는 C2 native code로 계속 실행하지만, 가정이 깨지면 Deopt로 인터프리터에 복귀해 재컴파일을 기다립니다."

→ 면접관이 "OSR은요?" 물으면 ③의 OSR로, "어떻게 진단?"이면 ④로.

---

## 7. 꼬리질문 트리 (가지별)

### Q1 [가지 ①]. 왜 인터프리터부터 시작하나요? C2로 바로 가면 안 되나요?

> C2는 메서드당 수십~수백 ms. 모든 메서드를 C2로 컴파일하면 JVM 시작에 수 초~수십 초 지연. 인터프리터는 즉시 시작 가능 (느리지만). Tier별 점진 승격이 startup + peak를 양립.
> 또한 C2는 정확한 profile이 있어야 잘 최적화 — Interpreter+C1에서 profile 수집한 후 C2가 그걸 활용 (profile-guided optimization).

**🪝 Q1-1: Profile 없이 C2가 컴파일하면 어떻게 되나요?**
> Type guess가 부정확해 deopt 빈발. Inlining 결정이 보수적 (megamorphic 가정). 결과적으로 peak 성능이 낮음. Tiered가 도입된 이유의 절반이 profile 가치.

### Q2 [가지 ②]. 한 메서드의 5단계 라이프사이클을 설명해보세요.

> 1. Tier 0: Template Interpreter, 호출 카운터 + MDO 수집.
> 2. Tier 3 (C1): ~1500회 → Compile Broker → C1 컴파일 → Code Cache Profiled segment. native code 안에서도 profile 계속 수집.
> 3. Tier 4 (C2): ~10000회 + 안정 profile → C2 컴파일 → Non-profiled segment. Inlining, EA, Loop opt, Speculation 적용.
> 4. Steady state: C2 native code 실행.
> 5. Deopt: 가정 위반 시 인터프리터로 복귀, 재컴파일.

**🪝 Q2-1: Method._code 필드의 atomic patch가 왜 안전한가요?**
> Atomic word write는 x86_64, ARM64에서 단일 instruction. 진행 중인 호출은 옛 nmethod로 정상 완료하고, 다음 호출부터 새 entry 사용. 동시 실행 중인 다른 스레드에 안전한 호출 전이.

### Q3 [가지 ③]. OSR이 무엇이고 왜 필요한가요?

> On-Stack Replacement. 실행 중인 메서드의 interpreter frame을 native frame으로 stack 위에서 직접 교체.
> 필요 이유: `void main() { for (int i = 0; i < 1e9; i++) ... }` 같은 코드는 메서드 호출 1회뿐이라 invocation counter로는 영원히 임계 미달. 그러나 loop body가 hot.
> 메커니즘: 인터프리터의 backward branch template이 backedge counter 수집 → 임계 도달 → OSR variant 컴파일 (특정 bytecode index에서 진입 가능한 nmethod) → 다음 iteration에서 stack frame 교체 → 나머지 loop를 native로 실행.

**🪝 Q3-1: OSR variant nmethod와 일반 nmethod의 차이는?**
> 일반 nmethod의 entry는 메서드 시작 (bytecode index 0). OSR variant의 entry는 특정 bytecode index (보통 loop start). OSR은 stack frame 위의 local/operand stack 값을 native register/stack에 mapping하는 prologue가 필요 — 일반 entry보다 복잡.

### Q4 [가지 ③]. Deoptimization이 일어나면 정확히 무슨 일이 일어나나요?

> C2의 speculation 가정이 깨졌을 때 native code 폐기 + 인터프리터 복귀.
> 흐름: 가정 위반 감지 → 영향받는 nmethod에 `not_entrant` 표시 → 이미 실행 중인 스레드는 다음 safepoint에서 처리 → Native frame의 register/stack을 OopMap + ScopeDesc로 해석해 Interpreter frame 새로 만들고 local/operand 복원 → 적절한 bytecode index부터 인터프리터 재개 → 시간 지나 재컴파일.

**🪝 Q4-1: Deopt의 흔한 reason은?**
> `unstable_if` (branch speculation 빗나감), `class_check` (monomorphic 가정 깨짐, 새 구현체 등장), `unreached` (도달 안 함 표시한 path 도달), `null_check`, `range_check`. JFR `jdk.Deoptimization` 이벤트의 `reason` 필드로 확인.

### Q5 [가지 ④]. Warmup 후 P99 latency가 가끔 튀는 이유는?

> 가장 흔한 두 원인:
> 1. **Deoptimization**: C2의 speculation이 깨져 잠시 인터프리터로. JFR `jdk.Deoptimization` burst 확인.
> 2. **GC pause**: STW. JFR `jdk.GarbageCollection`.
> 진단 절차: JFR로 spike 시점 이벤트 확인 → Deopt면 코드 audit, GC면 GC 튜닝.

### Q6 [가지 ⑤]. Tiered Compilation을 끄면 어떤 효과인가요?

> `-XX:-TieredCompilation`:
> - C2만 직접 사용 (Tier 0 → 4).
> - Code Cache 사용량 ↓ (Profiled segment 거의 안 씀).
> - **Warmup 느림** — 인터프리터 → 바로 C2 → 큰 컴파일 비용.
> - Peak 성능 동일 (최종 C2).
> 언제: 메모리 제한적인 컨테이너, batch 워크로드 (warmup 무시 가능).

### Q7 (Killer) [가지 ④]. Spring Boot 앱이 시작 후 5분간 P99가 2000ms입니다. 어떻게 진단하시겠어요?

> 단계적:
> 1. **정상 warmup vs 비정상**: `-XX:+PrintCompilation` 로그에 5분간 활발한 컴파일이 보이면 정상.
> 2. **Code Cache**: `jcmd Compiler.codecache | grep stopped` — stopped_count > 0이면 비활성.
> 3. **JFR 시간대별**: `jdk.Compilation`, `jdk.Deoptimization`, `jdk.GarbageCollection` 분포.
> 4. **조치**:
>    - 정상 warmup → K8s readiness probe에 합성 부하 추가, AppCDS, AOT (Leyden, GraalVM Native Image).
>    - Code Cache 부족 → `ReservedCodeCacheSize=512m`.
>    - Deopt 빈발 → 코드 audit (polymorphic call site, branch instability).
>    - GC 길면 → GC 튜닝.

**🪝 Q7-1: K8s readiness probe로 warmup을 어떻게 시뮬레이션하나요?**
> 1. 합성 부하 — 컨테이너 시작 시 hot path를 N번 호출하는 warmup script.
> 2. Probe 지연 — `initialDelaySeconds`를 warmup 예상 시간만큼 (예: 60s).
> 3. Probe 콘텐츠 — 단순 healthcheck 대신 실제 비즈니스 endpoint 호출 → JIT 컴파일 유도.
> 4. AppCDS — `-XX:SharedArchiveFile=app.jsa`로 클래스 미리 로드.
> 5. AOT — JDK 22+ Leyden 또는 GraalVM Native Image.

---

## 8. 학습 체크리스트

면접 전 백지에서 다음을 다 해낼 수 있어야 마스터:

- [ ] 0장 마인드맵을 종이에 1분 이내로 그릴 수 있다 (루트 + 5가지 + 각 키워드 3개)
- [ ] 가지 ① WHY: 단계적 승격의 3가지 이유 (즉시성, profile-guided, speculation 안전판) 말한다
- [ ] 가지 ② WHAT: 5단계 라이프사이클을 그리고 각 Tier의 결과물을 설명한다
- [ ] 가지 ③ HOW: OSR과 Deopt를 둘 다 "stack 위에서 frame 변환"으로 통합 설명한다
- [ ] 가지 ④ 운영: PrintCompilation 로그 한 줄을 해석한다 (시간, ID, flag, tier, 메서드, 상태)
- [ ] 가지 ④ 운영: Warmup 지연 진단 4단계를 말한다
- [ ] 가지 ⑤ 진화: `-server`/`-client` → Tiered (JDK 8) → Graal/Leyden 흐름을 설명한다
- [ ] 7장 꼬리질문 7개에 막힘없이 답한다

---

## 다음 단계

- → [02. Template Interpreter](./02-template-interpreter.md): Tier 0 깊이 — 인터프리터가 어떻게 빠르게 동작하는가
- → [03. Tiered Compilation](./03-tiered-compilation.md): Compile Broker + Tier 결정 + CompilerThread
- → [04. C1 and C2](./04-c1-and-c2.md): 두 컴파일러의 IR/phase 비교
- → [08. Speculative and Deopt](./08-speculative-and-deopt.md): Deopt 풀버전
- ← [Chapter 02-04 Code Cache](../02-runtime-data-areas/04-code-cache.md): 컴파일 결과가 어디 저장되는지

## 참고

- **HotSpot src `tieredThresholdPolicy.cpp`**: https://github.com/openjdk/jdk/blob/master/src/hotspot/share/compiler/tieredThresholdPolicy.cpp
- **HotSpot src `compileBroker.cpp`**: https://github.com/openjdk/jdk/blob/master/src/hotspot/share/compiler/compileBroker.cpp
- **HotSpot src `deoptimization.cpp`**: https://github.com/openjdk/jdk/blob/master/src/hotspot/share/runtime/deoptimization.cpp
- **JEP 317 Experimental Java-Based JIT (Graal)**: https://openjdk.org/jeps/317
- **JITWatch**: https://github.com/AdoptOpenJDK/jitwatch
- **Aleksey Shipilëv — JIT Internals**: https://shipilev.net/jvm/anatomy-quarks/
