# 부록 E — AOT vs JIT + JIT의 5가지 실측 최적화

> AOT는 "예측 컴파일"이고 JIT은 "관측 컴파일"이다. JIT이 AOT가 절대 못 하는 5가지 일을 할 수 있는 것 — devirtualization, escape analysis, branch prediction, inlining, vectorization 모두 "실제 실행을 본 결과"를 기반으로 한다는 것 — 이 JVM이 30년째 살아남은 핵심 비결이다.

---

## 이 문서의 사용법

본문 → [02. 컴파일 흐름](../02-class-compilation-flow.md) 가지 ①(WHY)·⑤(JIT)에서 진입. "왜 두 번 컴파일하나"의 본격 답.

---

## 0. 마인드맵

### 루트 한 문장 (anchor)

> **"AOT(예측)와 JIT(관측)은 native code 변환 시점이 빌드냐 런타임이냐의 차이고, JVM이 두 번 컴파일하는(javac + JIT) 이유는 AOT가 절대 못 하는 5가지 실측 최적화(inline/devirt/branch/EA/vectorization)를 위해서다. 2020년대 클라우드 시대엔 콜드 스타트 비용이 비싸져 GraalVM Native Image처럼 JVM이 AOT로 회귀하는 흐름도 있다."**

### 4개 가지

```
        [ROOT: AOT(예측) vs JIT(관측) = 두 번 컴파일의 본질]
                    │
       ┌────────┬───┼────────┬────────┐
      ① WHAT     ② 5가지    ③ 어떻게  ④ 회귀
   AOT 정의    실측 최적화  hot 감지  AOT 다시
       │       (★ 핵심)       │       │
       │         │             │       Native
    축: 변환   Inline         카운터   Image
    시점      Devirt         MethodData jaotc
    AOT/JIT/  Branch pred    Tiered    CDS
    Interp    EA + Scalar    L0→L3→L4 Leyden
    비교표    Vectorization
```

### 가지별 핵심 키워드

| 가지 | 키워드 1 | 키워드 2 | 키워드 3 |
|---|---|---|---|
| **① WHAT** | 변환 시점 축 | AOT 장점/한계 | AOT vs JIT 트레이드오프 표 |
| **② 5가지 실측 ★** | Inline + Devirt | Branch + EA | Vectorization |
| **③ Hot 감지** | Invocation counter | Back-edge counter | MethodData (Metaspace) |
| **④ AOT 회귀** | GraalVM Native Image | CDS / AppCDS | Project Leyden |

---

## 1. 가지 ①: WHAT — AOT/JIT/Interpreter의 한 축

### 1.1 핵심 질문

> "AOT가 정확히 뭐고, JIT/Interpreter와 어떤 축으로 비교되나요?"

### 1.2 키워드 1 — 변환 시점 축

| 약자 | 풀어 쓰기 | 한 줄 의미 |
|---|---|---|
| **AOT** | Ahead-of-Time | 실행 전에 미리 native code로 변환 |
| **JIT** | Just-in-Time | 실행 도중 필요한 시점에 native code로 변환 |
| **Interpreter** | (약자 아님) | 매번 한 줄씩 읽고 그 자리에서 실행 |

> 세 단어가 정확히 **"native code로 변환하는 시점이 언제냐"**라는 한 축 위에 놓여 있다. AOT(미리) ←→ JIT(실행 중) ←→ Interpreter(변환 안 함).

작동 방식 한 그림:
```
AOT (C/Rust/Go/Native Image):
  [hello.c] ──(빌드)──> [hello.exe (x86 기계어)] ──> CPU 직접 실행
                              ↑
                              빌드 끝나면 이미 native. 런타임 변환 0.

JIT (JVM, .NET):
  [hello.java] ──(빌드)──> [hello.class (bytecode)]
                                   ↓
                          (실행 시작) JVM이 로드
                                   ↓
                          Interpreter로 시작 → 핫코드 감지 → JIT이 native 변환
                                   ↓
                                CPU 실행

Interpreter only (1995 Java, 옛 Python):
  [hello.py] ──> 인터프리터가 한 줄씩 읽어 실행 (native 변환 안 함)
```

### 1.3 키워드 2 — AOT 장점/한계

**장점**:
- **시작 빠름** — 변환 비용을 빌드 때 다 지불. 실행 시점엔 0.
- **결정론적** — 같은 입력 → 같은 결과. warmup 변동 없음.
- **메모리 적음** — 런타임에 컴파일러를 들고 있을 필요 없음.

**한계**:
- **플랫폼 종속** — x86_64 Linux 바이너리는 ARM Mac에서 못 돔. 새 플랫폼마다 재컴파일.
- **동적 정보 0** — 컴파일 시점엔 "어떤 분기가 99% 잡힌다", "어떤 타입이 항상 들어온다"를 **알 길이 없음**. 보수적 최적화만 가능.
- **Dynamic feature 약함** — reflection, dynamic class loading, hot-swap이 본질적으로 어려움.

→ GraalVM Native Image가 정확히 이 길로 간 것. 시작 ms 단위지만 reflection을 빌드 설정으로 미리 알려줘야 함.

### 1.4 키워드 3 — AOT vs JIT 트레이드오프

| 축 | AOT 유리 | JIT 유리 |
|---|---|---|
| **시작 속도** | ms 단위 (변환 0) | warmup 필요 (수십 ms ~ 수 초) |
| **Peak 성능** | 정적 분석 한계 | **실측 프로파일 활용** |
| **메모리 사용** | 적음 | 큼 (JIT + Code Cache + MethodData) |
| **플랫폼 이식** | 플랫폼당 재빌드 | bytecode는 어디서나 |
| **동적 기능** | reflection/hot-swap 어려움 | 자연스러움 |
| **빌드 시간** | 김 (LTO 포함) | 빠름 (bytecode까지만) |
| **결정론** | 동일 입력 동일 결과 | warmup 변동 |

JVM이 AOT를 안 택한 이유: 1995년엔 **이식성·동적 로딩·메모리·보안** 네 축 모두에서 AOT가 불리. JIT을 택한 뒤로는 **peak 성능까지 AOT를 추월** — 실측 기반 devirtualization·EA가 정적 분석으로 못 얻는 것.

### 1.5 javac + JIT 분업 (두 번 컴파일의 본질)

**1차 컴파일 (javac, 빌드 시)**: `.java` → bytecode (`.class`).
- 가상 CPU의 명령어 → 플랫폼 독립.
- 아직 CPU 직접 실행 불가.

**2차 컴파일 (JVM, 런타임)**: bytecode → native code (Interpreter + JIT 조합).
- Interpreter: 즉시 시작, 한 줄씩 해석.
- JIT: hot한 메서드는 native code로 캐싱.

`.class`는 정확히 말하면 **"중간 표현(IR)이 디스크에 저장된 것"**. LLVM IR이 디스크에 남아있는 거라고 생각하면 비슷.

---

## 2. 가지 ②: 5가지 실측 최적화 (★ JIT의 핵심 가치)

### 2.1 핵심 질문

> "JIT이 AOT가 절대 못 하는 일이 정확히 뭔가요?"

### 2.2 키워드 1 — Inlining + Devirtualization (실측 1, 2)

#### Inlining: 자주 호출되는 작은 메서드 본문을 호출 사이트에 끼워넣기

```java
int square(int x) { return x * x; }

int sum() {
    int s = 0;
    for (int i = 0; i < 1000; i++) s += square(i);  // 1000번
    return s;
}
```

JIT 판단: `square`가 hot, 짧음 → `sum` 안에 통째로 삽입:
```java
// JIT이 만든 가상 코드
int sum() {
    int s = 0;
    for (int i = 0; i < 1000; i++) s += i * i;  // square 호출 사라짐
    return s;
}
```

→ 함수 호출 비용(스택 프레임, register save) 0. 그리고 이걸 발판으로 다음 최적화들이 가능.

#### Devirtualization: 가상 호출을 정적 호출로

```java
interface Animal { void speak(); }
class Dog implements Animal { void speak() {...} }
class Cat implements Animal { void speak() {...} }

void run(Animal a) { a.speak(); }
```

AOT는 vtable lookup 거쳐야 함. JIT은 1만 번 실측 보고: **"항상 Dog만 들어왔네"** → `Dog.speak()`로 가정 + inline:
```
[가정] a는 Dog다
[가드] if (a.getClass() != Dog) goto deopt;
[본문] Dog.speak()의 본문을 펼친 코드
[deopt] 가정 깨지면 인터프리터로 복귀
```

→ 가상 호출 비용 0. Cat이 들어오면 deopt 발생 → 인터프리터 → 재컴파일.

### 2.3 키워드 2 — Branch Prediction + Escape Analysis (실측 3, 4)

#### Branch Prediction: 자주 잡히는 분기 우선 배치

```java
if (x == null) { /* 에러 처리 */ }
else { /* hot path */ }
```

JIT이 본 결과: 99% null 아님 → 어셈블리에서 else 본문을 **fall-through**(점프 없이 다음에 바로)로 배치:
```asm
test    eax, eax       ; x가 null인지 검사
jz      error_handler  ; null이면 점프 (드뭄)
; hot path 본문이 바로 여기 옴 — 캐시 hit, predictor 정확
```

→ CPU 명령어 캐시 효율 + branch predictor 정확도 ↑.

#### Escape Analysis + Scalar Replacement: Heap 할당 제거

```java
int distance(int x1, int y1, int x2, int y2) {
    Point p1 = new Point(x1, y1);
    Point p2 = new Point(x2, y2);
    return Math.abs(p1.x - p2.x) + Math.abs(p1.y - p2.y);
}
```

JIT 분석: `p1`, `p2`가 메서드 밖으로 안 나감 ("escape" 안 함) → **Heap 할당 자체를 제거** + 필드를 register로 분해:
```java
// JIT이 만든 가상 코드 — 객체가 사라짐
int distance(int x1, int y1, int x2, int y2) {
    return Math.abs(x1 - x2) + Math.abs(y1 - y2);
}
```

→ GC 부담 0. allocation 0. **JVM이 "객체 마구 만들어도 빠른" 이유의 핵심**.

### 2.4 키워드 3 — Vectorization (SIMD, 실측 5)

#### Loop Unrolling + Vectorization

```java
for (int i = 0; i < 1000; i++) sum += arr[i];
```

JIT이 만드는 어셈블리:
```asm
; 8개씩 묶어 AVX SIMD 명령으로 한 번에 처리
vmovdqu  ymm0, [rax]       ; arr[i..i+7] 8개 정수를 한 번에 load
vpaddd   ymm1, ymm1, ymm0  ; 8개를 한 번에 더함
add      rax, 32
cmp      rax, rcx
jl       loop
```

→ 8개 정수를 한 명령으로 처리. 이론 8배 빠름. AVX-512는 16배까지.

→ 이게 가능한 이유: JIT이 **루프 회전 수, 배열 접근 패턴, 메모리 alignment**를 실측으로 확인한 뒤 안전하게 vectorize. AOT는 안전성 분석이 보수적이라 SIMD 적용에 제한.

### 2.5 5가지를 한 줄로

| # | 최적화 | 실측 정보 |
|---|---|---|
| 1 | **Inlining** | 호출 빈도가 임계치 초과 + 메서드 크기 |
| 2 | **Devirtualization** | virtual call의 receiver class 분포 |
| 3 | **Branch Prediction** | if/switch의 분기 빈도 |
| 4 | **Escape Analysis + Scalar Replace** | 객체 escape 여부 + 사용 패턴 |
| 5 | **Vectorization** | 루프 회전 수 + 메모리 접근 패턴 |

이 5가지 모두 **"실제 실행을 본 결과"가 필요**. AOT는 정적 분석으로 추측만 가능 → 보수적 적용 → 효과 제한.

---

## 3. 가지 ③: 어떻게 hot을 감지하나 — 동적 컴파일 라이프사이클

### 3.1 핵심 질문

> "JVM은 어느 메서드가 hot한지 어떻게 알아내나요?"

### 3.2 키워드 1 — 카운터 시스템

JVM은 메서드마다 두 카운터:

| 카운터 | 의미 |
|---|---|
| **Invocation counter** | 이 메서드가 호출된 횟수 |
| **Back-edge counter** | 이 메서드 안의 루프가 회전한 횟수 |

기본 임계치 (Tiered 기준, `-XX:Tier3InvocationThreshold` 등으로 조정):
- C1 컴파일 트리거: invocation ≥ ~200, back-edge ≥ ~1000
- C2 컴파일 트리거: invocation ≥ ~5000, back-edge ≥ ~10000

### 3.3 키워드 2 — MethodData (프로파일 데이터)

Interpreter와 C1이 메서드 실행 중 모으는 데이터:
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

Metaspace에 메서드마다 저장. C2가 컴파일할 때 이걸 읽어서 **"99% Dog면 Dog로 가정"** 같은 결정.

### 3.4 키워드 3 — 전체 라이프사이클

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
        │ inline + EA + vectorization + devirt + branch pred
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

## 4. 가지 ④: JVM이 AOT로 회귀하는 흐름

### 4.1 핵심 질문

> "JVM이 JIT을 자랑하던 그 30년 동안 왜 AOT 기술이 다시 들어오나요?"

### 4.2 키워드 1 — 콜드 스타트 비용의 재발견

2020년대 들어 "JIT의 warmup 비용"이 클라우드/서버리스에서 너무 비싸짐:
- AWS Lambda 콜드 스타트 = 사용자 첫 응답 지연 + 비용
- 짧게 도는 CLI = warmup 끝나기 전에 프로세스 종료
- 컨테이너 = 메모리당 비용 직결 → JVM이 큰 게 부담

1995년의 "이식성/동적/메모리/보안" 제약은 해결됐고, 2020년대의 "콜드 스타트" 제약이 새로 생겼다.

### 4.3 키워드 2 — JVM AOT 기술 타임라인

| 기술 | 년도 | 위치 |
|---|---|---|
| **`jaotc`** | 2017 (JDK 9) | 실험적 AOT — 실패해서 JDK 17에서 제거 |
| **CDS / AppCDS** | 2010, 2018 | Class Data Sharing — bytecode 파싱 결과를 디스크에 저장 (부분 AOT) |
| **GraalVM Native Image** | 2019~ | 빌드 시점에 전체 AOT. 시작 ms 단위, 메모리 1/10. Spring Boot 3.0+ 공식 지원 |
| **Project Leyden** | 2022~ | OpenJDK 공식 AOT 로드맵. JDK 24부터 단계별 도입 |
| **AOT Method Profiling** (JEP 483) | JDK 24 (2025) | 이전 실행의 프로파일을 저장해 다음 실행에 재사용 |
| **AOT Code Caching** (JEP 514) | JDK 25 (2025) | JIT 결과를 디스크에 저장해 다음 실행에 재사용 |

### 4.4 키워드 3 — 트레이드오프

GraalVM Native Image가 대표적. 시작 ms / 메모리 1/10이라는 큰 장점이 있지만:
- **빌드 시간 폭증** (5~30분)
- **Closed-world assumption** — reflection을 빌드 시점에 명시 (`reflect-config.json`)
- **JFR/JMX/dynamic 진단 도구 제한**
- **Peak 성능은 JIT C2/Graal보다 낮음** (실측 정보 없으니까)

> 아이러니: JVM이 AOT를 거부했다가 다시 부분 AOT를 도입하고 있다. 1995년 제약은 사라졌고 2020년대 제약이 새로 생겼기 때문.

---

## 5. 면접 답변 워크플로우

### 5.1 질문 → 가지 매핑

| 면접 질문 | 진입 가지 |
|---|---|
| "AOT가 뭐?" | ① WHAT |
| "AOT vs JIT 차이?" | ① 변환 시점 |
| "Java가 두 번 컴파일하는 이유?" | ② 5가지 실측 |
| "JIT이 AOT보다 빠를 수 있는 이유?" | ② 실측 정보 |
| "Escape Analysis가 뭐?" | ② EA |
| "어떻게 hot 메서드를 알아내나?" | ③ 카운터 + MethodData |
| "MethodData가 뭐?" | ③ 프로파일 |
| "GraalVM Native Image의 의미?" | ④ AOT 회귀 |
| "Project Leyden?" | ④ Leyden |

### 5.2 답변 템플릿

> "AOT와 JIT는 native code 변환 시점이 빌드냐 런타임이냐의 차이입니다 (← 루트).
> JVM이 두 번 컴파일하는(javac + JIT) 이유는 **AOT가 절대 못 하는 5가지 실측 최적화**를 위해서입니다.
> 첫째 **Inlining** — 핫한 작은 메서드를 호출 사이트에 펼침. 둘째 **Devirtualization** — 가상 호출의 receiver가 99% Dog면 Dog로 가정 + inline + 가드. 셋째 **Branch Prediction** — 자주 잡히는 분기를 fall-through로. 넷째 **Escape Analysis** — 안 새는 객체는 Heap 할당 자체를 제거. 다섯째 **Vectorization** — 루프를 SIMD로.
> 다섯 가지 모두 '실제 실행을 본 결과'가 필요한데, AOT는 정적 분석으로 보수적 추측만 가능합니다.
> 단, 2020년대 클라우드 시대엔 콜드 스타트 비용이 커서 GraalVM Native Image나 Project Leyden 같은 AOT 회귀 흐름도 강해지고 있습니다 — 시나리오별 트레이드오프 선택의 문제입니다."

---

## 6. 꼬리질문 트리

### Q1 [가지 ②]. JIT이 AOT보다 어떻게 더 빠를 수 있나?

> 5가지 실측 정보(호출 빈도/receiver class 분포/분기 빈도/escape 여부/루프 패턴)를 활용한 공격적 최적화. AOT는 정적 분석 한계로 보수적 적용만 가능. 단, warmup 비용 + 메모리 + 결정성 손실이 대가.

**🪝 Q1-1: Devirtualization이 어떻게 가능?**
> MethodData에 가상 호출의 receiver class 분포가 누적됨. 99% Dog면 C2가 "Dog로 가정 + 가드 + inline" 패턴 생성. Cat이 들어오면 가드 실패 → deopt.

**🪝 Q1-2: Escape Analysis가 객체를 어떻게 없애나?**
> 메서드 안에서만 쓰이고 밖으로 안 나가는 객체 발견 → Heap 할당 대신 객체 필드를 register/스택 slot으로 분해(Scalar Replacement). GC 부담 0, allocation 0.

### Q2 [가지 ③]. JIT은 어느 메서드가 hot한지 어떻게 알아내나?

> 카운터 시스템 — Invocation counter (호출 횟수) + Back-edge counter (루프 회전). 임계치 넘으면 컴파일 큐 제출. 동시에 MethodData에 receiver class 분포/분기 빈도/null 빈도/타입 프로파일을 누적해서 C2가 공격적 가정을 깔 재료로 사용.

### Q3 [가지 ④]. GraalVM Native Image가 AOT인데 왜 JVM 진영에서 다시?

> 콜드 스타트 비용이 클라우드/서버리스에서 너무 비싸짐. AWS Lambda나 짧게 도는 CLI에서는 JIT warmup이 끝나기 전에 프로세스가 종료될 수도. Native Image는 시작 ms 단위 + 메모리 1/10이지만 reflection을 빌드 시점에 명시해야 하고 peak 성능은 JIT보다 낮음 — 시나리오 선택.

---

## 7. 학습 체크리스트

- [ ] AOT/JIT/Interpreter를 "변환 시점" 축으로 비교 그림을 그린다
- [ ] AOT의 장단점과 한계(특히 "동적 정보 0")를 설명한다
- [ ] AOT vs JIT 트레이드오프 표를 적는다
- [ ] javac + JIT의 두 번 컴파일 분업을 설명한다
- [ ] **5가지 실측 최적화**(Inline/Devirt/Branch/EA/Vec)를 한 줄씩 설명한다
- [ ] 5가지 모두에 "실측 정보 없으면 안 됨"의 본질을 연결한다
- [ ] 카운터 + MethodData + L0→L3→L4 라이프사이클을 그린다
- [ ] AOT 회귀 흐름(jaotc, CDS, Native Image, Leyden)을 시대순으로 말한다
- [ ] GraalVM Native Image의 트레이드오프(콜드 스타트 vs peak)를 설명한다

---

## 한 줄 비유

> **AOT** = "출국 전에 미리 환전" — 공항 도착하자마자 바로 쓸 수 있지만, 환율이 미래에 어떻게 바뀔지 모름.
> **JIT** = "현지에서 그때그때 환전" — 처음엔 줄 서서 기다리지만, 실제 환율을 보고 환전 가능.
> **Interpreter** = "결제 때마다 한국 카드로 그 자리에서 환산" — 환전 자체를 안 함. 매번 비용 발생.

---

## 관련 부록

- [부록 A — 인터프리터 구현 4가지 방식](./A-interpreter-implementations.md): Template Interpreter가 왜 "매우 단순한 JIT"인가
- [부록 B — JVM 구현체 비교](./B-jvm-implementations.md): GraalVM Native Image가 택한 AOT의 트레이드오프
- [부록 D — opcode 디스패치 메커니즘](./D-opcode-dispatch.md): 인터프리터가 bytecode를 어떻게 디스패치하는가
