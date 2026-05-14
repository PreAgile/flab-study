# 부록 E — AOT vs JIT + JIT이 활용하는 5가지 실측 최적화

> **본문**: [02. 컴파일 흐름 — §2 직관](../02-class-compilation-flow.md#-2단계-직관)의 "왜 두 번 컴파일하나?"에서 옵션 A~D를 짧게만 비교했다. 여기선 **AOT가 정확히 뭐고, JIT이 AOT가 못 하는 어떤 일을 하는지** — 5가지 실측 최적화를 — 본다.

---

## 1. AOT (Ahead-of-Time) 컴파일이란

### 약자 풀어쓰기

| 약자 | 풀어 쓰기 | 한국어 | 한 줄 의미 |
|---|---|---|---|
| **AOT** | **A**head-**o**f-**T**ime | "(실행) 시간보다 **앞서서**" | 실행 전에 미리 native code로 변환 |
| **JIT** | **J**ust-**i**n-**T**ime | "(실행) 시간에 **딱 맞춰서**" | 실행 도중 필요한 시점에 native code로 변환 |
| **Interpreter** | (약자 아님) | 통역사/해석기 | 매번 한 줄씩 읽고 그 자리에서 실행 |

> 세 단어가 정확히 **"native code로 변환하는 시점이 언제냐"** 라는 한 축 위에 놓여 있다.
> AOT (미리) ←→ JIT (실행 중) ←→ Interpreter (변환 안 함)

### 작동 방식 — 한 그림

```
AOT (C/C++/Rust/Go):
  [hello.c] ──(컴파일 시점)──> [hello.exe (x86_64 기계어)] ──> CPU가 바로 실행
                                       ↑
                                       빌드 끝나면 이미 native. 런타임 변환 0.

JIT (JVM, .NET):
  [hello.java] ──(빌드)──> [hello.class (bytecode)]
                                   ↓
                          (실행 시작) JVM이 로드
                                   ↓
                          인터프리터로 시작 → 핫코드 감지 → JIT이 native 변환
                                   ↓
                                CPU 실행

Interpreter only (1995 Java, 옛 Python):
  [hello.py] ──> 인터프리터가 한 줄씩 읽어서 실행 (native 변환 안 함)
```

핵심 차이: **언제 native machine code가 만들어지느냐**.
- AOT: 빌드 시점 (개발자 PC, CI 서버)
- JIT: 런타임 (사용자 PC, 프로덕션 서버)
- Interpreter: 만들어지지 않음

### 대표 예시

| 방식 | 대표 언어/런타임 |
|---|---|
| **AOT only** | C, C++, Rust, Go, Swift, **GraalVM Native Image**, Kotlin/Native |
| **JIT only / JIT 중심** | (순수 JIT만 있는 건 드뭄. 대부분 인터프리터 + JIT 조합) |
| **Interpreter + JIT** | **JVM (HotSpot)**, .NET CLR, V8 (Chrome JS), CPython 3.13+, LuaJIT |
| **Interpreter only** | 옛 Python (3.10 이하), PHP (Zend 옛 버전), 1995년 Java 1.0 |
| **AOT + JIT 혼합** | Android ART (앱 설치 시 AOT, 실행 중엔 JIT 보강), .NET ReadyToRun |

---

## 2. AOT의 장단점

**장점**:
- **시작이 빠름**: 변환 비용을 빌드 때 다 지불했으니 실행 시점엔 0
- **결정론적**: 같은 입력 → 같은 결과 (워밍업 변동 없음)
- **메모리 적음**: 런타임에 컴파일러를 들고 있을 필요 없음

**한계**:
- **플랫폼 종속**: x86_64 Linux 바이너리는 ARM Mac에서 못 돈다. 새 플랫폼마다 재컴파일/포팅
- **동적 정보 0**: 컴파일 시점엔 "어떤 분기가 99% 잡힌다", "어떤 타입이 항상 들어온다"를 **알 길이 없음**. 그래서 보수적 최적화만 가능
- **Dynamic feature 약함**: reflection, dynamic class loading, 코드 hot-swap이 본질적으로 어렵다

> GraalVM Native Image가 정확히 이 길로 간 것. 시작 ms 단위지만 reflection을 빌드 설정으로 미리 알려줘야 함.

---

## 3. AOT vs JIT — 트레이드오프 한 표

| 축 | AOT 유리 | JIT 유리 |
|---|---|---|
| **시작 속도** | ✅ ms 단위 (변환 비용 0) | ❌ warmup 필요 (수십 ms~수 초) |
| **Peak 성능** | ⚠️ 정적 분석 한계 | ✅ 실측 프로파일 활용 |
| **메모리 사용** | ✅ 적음 (컴파일러 없음) | ❌ 큼 (JIT + Code Cache + MethodData) |
| **플랫폼 이식** | ❌ 플랫폼당 재빌드 | ✅ bytecode는 어디서나 |
| **동적 기능** | ❌ reflection·hot-swap 어려움 | ✅ 자연스러움 |
| **빌드 시간** | ❌ 김 (특히 LTO) | ✅ 빠름 (bytecode까지만) |
| **결정론** | ✅ 동일 입력 동일 결과 | ⚠️ warmup 변동 |
| **대표 사례** | C, C++, Rust, Go | Java, Kotlin, Scala |

JVM이 AOT를 안 택한 이유: 1995년엔 **이식성·동적 로딩·메모리·보안** 네 축 모두에서 AOT가 불리. JIT을 택한 뒤로는 **peak 성능까지 AOT를 추월**해버렸다 (실측 기반 devirtualization·EA가 정적 분석으로 못 얻는 것).

---

## 4. JVM 모델 — javac + JIT의 분업

JVM은 **컴파일을 두 단계로 쪼개서** AOT의 한계를 우회한다.

### 1차 컴파일: `javac` (정적, 빌드 시점)

`javac`가 하는 일: **`.java` → 바이트코드 (`.class`)**.

바이트코드는 **"가상의 CPU"가 이해하는 명령어**다. 실제 x86이나 ARM과 무관한 추상 명령어 집합.

**예시 — 한 줄짜리 자바를 javac가 어떻게 바이트코드로 만드는가**:

```java
int c = a + b;
```

```
iload_1       // 지역변수 1번(a)을 operand stack에 push
iload_2       // 지역변수 2번(b)을 operand stack에 push
iadd          // stack top 두 정수를 pop해서 더한 뒤 결과를 push
istore_3      // pop해서 지역변수 3번(c)에 저장
```

핵심 포인트:
- 이 4개 명령어는 **x86이든 ARM이든 RISC-V든 똑같다** → 플랫폼 독립
- 이건 아직 CPU가 직접 실행 못 함. **JVM이 해석해줘야 한다**
- "stack-based" 가상 머신: register 없이 operand stack에서만 연산

> 그래서 `.class`는 정확히 말하면 **"중간 표현(IR)이 디스크에 저장된 것"** 이다. C 컴파일러의 LLVM IR이 디스크에 남아있는 거라고 생각하면 비슷하다.

### 2차 컴파일: JVM이 런타임에 — Interpreter + JIT

JVM이 `.class`를 받으면 두 가지 방법으로 실행한다:

**(A) Interpreter** — 바이트코드를 한 줄씩 해석해서 실행:

```
프로그램 시작
 ↓
Interpreter가 iload_1 만남 → "지역변수 1번을 stack에 push해야 하는구나" → 실행
 ↓
다음 명령어 iload_2 만남 → 실행
 ↓ ... (한 줄씩 해석 반복)
```

- 변환 비용 0 → **즉시 시작 가능**
- 하지만 같은 코드가 100만 번 실행되면 100만 번 해석함 → 느림

**(B) JIT** — 자주 실행되는 메서드는 **native code로 변환해서 캐싱**:

```
이 메서드가 1만 번 호출됨 → "hot하다" → JIT 컴파일러 호출
                                          ↓
                              바이트코드 → x86_64 어셈블리 변환
                                          ↓
                              Code Cache에 저장
                                          ↓
                              다음 호출부터는 어셈블리로 직접 점프 (해석 안 함)
```

---

## 5. JIT이 활용하는 5가지 "실측 정보" — AOT가 절대 못 하는 일

> 핵심: **JIT은 "실제 실행을 본 결과"를 가지고 컴파일한다.** AOT 컴파일러는 코드를 정적으로 보면서 "최선의 추측"으로 최적화한다. 그런데 실제 프로그램의 동적 특성은 코드만 봐선 알 수 없다.

### (1) Inlining — 자주 호출되는 작은 메서드 본문을 호출 사이트에 끼워넣기

```java
int square(int x) { return x * x; }

int sum() {
    int s = 0;
    for (int i = 0; i < 1000; i++) {
        s += square(i);   // 1000번 호출
    }
    return s;
}
```

JIT 판단: `square`가 hot, 짧음 → `sum` 안에 통째로 삽입:

```java
// JIT이 만든 가상 코드
int sum() {
    int s = 0;
    for (int i = 0; i < 1000; i++) {
        s += i * i;   // square 호출 사라짐
    }
    return s;
}
```

→ 함수 호출 비용(스택 프레임, register save) 0. 그리고 이걸 발판으로 다음 최적화들이 가능해진다.

### (2) Devirtualization — 가상 호출을 정적 호출로

```java
interface Animal { void speak(); }
class Dog implements Animal { void speak() { ... } }
class Cat implements Animal { void speak() { ... } }

void run(Animal a) {
    a.speak();   // 어느 구현이 호출될지 정적으로는 모름
}
```

AOT는 가상 호출 테이블 조회를 거쳐야 함 (vtable lookup).

JIT은 1만 번 실측을 보고: **"항상 Dog만 들어왔네"** → `Dog.speak()`로 가정 + inline:

```
[가정] a는 Dog다
[가드] if (a.getClass() != Dog) goto deopt;
[본문] Dog.speak()의 본문을 펼친 코드
[deopt] 가정 깨지면 인터프리터로 복귀
```

→ 가상 호출 비용 0. 만약 어느 날 Cat이 들어오면 deopt 발생 → 인터프리터 → 재컴파일.

### (3) Branch Prediction — 자주 잡히는 분기 우선 배치

```java
if (x == null) { /* 에러 처리 */ }
else { /* hot path */ }
```

JIT이 본 결과: 99% null 아님 → 어셈블리에서 else 본문을 **fall-through**(점프 없이 다음에 바로 오는 경로)로 배치:

```asm
test    eax, eax       ; x가 null인지 검사
jz      error_handler  ; null이면 점프 (드뭄)
; hot path 본문이 바로 여기 옴 — CPU 캐시 hit, branch predictor 정확
...
```

→ CPU 명령어 캐시 효율 + branch predictor 정확도 ↑.

### (4) Escape Analysis + Scalar Replacement — Heap 할당 제거

```java
int distance(int x1, int y1, int x2, int y2) {
    Point p1 = new Point(x1, y1);
    Point p2 = new Point(x2, y2);
    return Math.abs(p1.x - p2.x) + Math.abs(p1.y - p2.y);
}
```

JIT 분석: `p1`, `p2`가 메서드 밖으로 안 나감("escape" 안 함) → **Heap 할당 자체를 제거** + 필드를 register로 분해:

```java
// JIT이 만든 가상 코드 — 객체가 사라짐
int distance(int x1, int y1, int x2, int y2) {
    return Math.abs(x1 - x2) + Math.abs(y1 - y2);
}
```

→ GC 부담 0. allocation 0. 이게 JVM이 "객체 마구 만들어도 빠른" 이유의 핵심.

### (5) Loop Unrolling + Vectorization

```java
for (int i = 0; i < 1000; i++) sum += arr[i];
```

JIT이 만드는 어셈블리:

```asm
; 4개씩 묶어 SIMD 명령으로 한 번에 처리
vmovdqu  ymm0, [rax]       ; arr[i..i+7] 8개 정수를 한 번에 load
vpaddd   ymm1, ymm1, ymm0  ; 8개를 한 번에 더함
add      rax, 32
cmp      rax, rcx
jl       loop
```

→ 8개 정수를 한 명령으로 처리. 이론적으로 8배 빠름.

---

## 6. JVM은 어떻게 "hot 코드"를 알아내는가 — 동적 컴파일의 실제 흐름

JIT의 메커니즘은 결국 **세 가지**다:
1. **카운터로 hot 판정**
2. **인터프리터에서 프로파일 수집**
3. **임계치 넘으면 JIT 큐에 제출**

### 카운터 시스템

JVM은 메서드마다 두 카운터를 둔다:

| 카운터 | 의미 |
|---|---|
| **Invocation counter** | 이 메서드가 호출된 횟수 |
| **Back-edge counter** | 이 메서드 안의 루프가 회전한 횟수 |

기본 임계치 (Tiered Compilation 기준):
- C1 컴파일 트리거: invocation ≥ ~200, back-edge ≥ ~1000
- C2 컴파일 트리거: invocation ≥ ~5000, back-edge ≥ ~10000
- (정확한 값은 `-XX:Tier3InvocationThreshold` 등으로 조정)

### 프로파일 데이터 수집 — `MethodData`

인터프리터와 C1이 메서드 실행 중에 모으는 데이터:

```
MethodData {
    invocation_count
    backedge_count

    // 각 가상 호출 site별로
    receiver_class_distribution: { Dog: 9990, Cat: 10 }

    // 각 if/switch별로
    branch_taken_count
    branch_not_taken_count

    // 각 null check별로
    null_seen_count

    // 각 메서드 인자별로
    type_profile: { String: 9999, Object: 1 }
}
```

이게 Metaspace에 메서드마다 저장된다. C2가 컴파일할 때 이걸 읽어서 **"99% Dog면 Dog로 가정"** 같은 결정을 내린다.

### 전체 라이프사이클

```
[새 메서드 호출됨]
        │
        ▼
[Level 0: 인터프리터 실행]
        │ invocation/backedge 카운터 ++
        │
        │ 카운터 ≥ 임계치
        ▼
[Level 3: C1 컴파일 (with full profiling)]
        │ Code Cache에 native code 저장
        │ 호출 시 어셈블리로 직접 점프
        │ MethodData에 profile 누적
        │
        │ 카운터 더 누적
        ▼
[Level 4: C2 컴파일 (profile-guided)]
        │ MethodData를 읽어서 공격적 최적화
        │ inline + EA + vectorization
        │ Code Cache에 새 native code 저장 (L3 코드 폐기)
        │
        │ ← 가정 깨짐 (예: 갑자기 Cat 들어옴)
        ▼
[Deoptimization]
        │ register/stack 상태를 인터프리터 frame으로 재구성
        │
        ▼
[Level 0으로 복귀 → 다시 카운터 누적 → 재컴파일]
```

---

## 7. JVM 세계가 AOT로 다시 가는 흐름

2020년대 들어 "JIT의 warmup 비용"이 클라우드/서버리스에서 너무 비싸지자, **JVM이 AOT를 다시 도입**하고 있다:

| 기술 | 년도 | 위치 |
|---|---|---|
| **`jaotc`** | 2017 (JDK 9) | 실험적 AOT — 실패해서 JDK 17에서 제거 |
| **GraalVM Native Image** | 2019~ | 빌드 시점에 전체 AOT. 시작 ms 단위, 메모리 1/10. Spring Boot 3.0+ 공식 지원 |
| **CDS / AppCDS** | 2010, 2018 | Class Data Sharing — bytecode 파싱 결과를 디스크에 미리 저장 (부분 AOT) |
| **Project Leyden** | 2022~ | OpenJDK 공식 AOT 로드맵. JDK 24부터 단계별 도입 중 |
| **AOT Method Profiling** (JEP 483) | JDK 24 (2025) | 이전 실행의 프로파일을 저장해 다음 실행에 재사용 |
| **AOT Code Caching** (JEP 514) | JDK 25 (2025) | JIT 결과를 디스크에 저장해 다음 실행에 재사용 |

> 아이러니: **JVM이 AOT를 거부했다가 다시 부분 AOT를 도입**하고 있다. 1995년의 "이식성" 제약은 사라졌고, 2020년대의 "콜드 스타트" 제약이 새로 생겼기 때문.

---

## 한 줄 비유

> **AOT = "출국 전에 미리 환전"** — 공항 도착하자마자 바로 쓸 수 있지만, 환율이 미래에 어떻게 바뀔지 모름.
> **JIT = "현지에서 그때그때 환전"** — 처음엔 줄 서서 기다리지만, 실제 환율을 보고 환전 가능.
> **Interpreter = "결제 때마다 한국 카드로 그 자리에서 환산"** — 환전 자체를 안 함. 매번 비용 발생.

---

## 한 줄 요약

> **AOT는 "예측 컴파일"이고, JIT은 "관측 컴파일"이다.**

- AOT는 코드만 보고 "이렇게 돌아갈 것이다"를 가정한다
- JIT은 실제로 돌아가는 걸 보고 "이렇게 돌아간다"를 알아낸 다음 컴파일한다
- 그래서 JIT은 **AOT가 절대 할 수 없는 최적화** — devirtualization, escape analysis, branch prediction에 실측 적용 — 를 한다
- 대가는 **warmup**(처음엔 인터프리터로 느리게 시작) + **메모리**(JIT 컴파일러 + Code Cache + MethodData)

이게 "javac가 한 번, JIT이 한 번, 그 사이엔 인터프리트"라는 본문 도입부 문장의 본질이다. 같은 코드를 **두 번 컴파일**하는 이유는 — **정적 컴파일러가 알 수 없는 정보를, 동적 컴파일러가 실측으로 알아낸 뒤 더 깊이 최적화하기 위해서**다.

---

## 관련 부록

- [부록 A — 인터프리터 구현 4가지 방식](./A-interpreter-implementations.md): Template Interpreter가 왜 "매우 단순한 JIT"인가
- [부록 B — JVM 구현체 비교](./B-jvm-implementations.md): GraalVM Native Image가 택한 AOT의 트레이드오프
- [부록 D — opcode 디스패치 메커니즘](./D-opcode-dispatch.md): 인터프리터가 bytecode를 어떻게 디스패치하는가
