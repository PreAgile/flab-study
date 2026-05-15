# 10. Java Evolution — 7→8→16→17→21, 왜 이 순서였나

> **이 챕터의 한 줄 목표**: Java가 함수형을 흡수한 순서 (lambda → Optional → Stream → record → sealed → pattern → virtual thread) 의 **왜 그 순서였나**를 산업적 압력 + 언어 설계 제약으로 설명할 수 있다. 각 기능의 바이트코드 수준 구현까지.

## 📖 이론적 골격

| 자료 | 핵심 |
|---|---|
| JEPs (Java Enhancement Proposals) | 각 기능의 공식 설계 문서 |
| Brian Goetz, "Data Oriented Programming in Java" | Record + Sealed + Pattern의 통합 비전 |
| Joshua Bloch 『Effective Java 3rd』 | Java 9까지의 권장 |
| 『Java in Action』 (Manning) | Java 8 함수형 도입의 결정판 |

## 학습 목표

1. **Java 7 시대의 한계** — 함수형 부재의 비용.
2. **Java 8 람다/Stream/Optional** — 흡수 시작 + 바이트코드.
3. **Java 9~10 module + var** — 인프라 정비.
4. **Java 14~16 record/switch expression** — ADT의 시작.
5. **Java 17 sealed + 21 pattern matching** — ADT 완성 + Data-Oriented Programming.
6. **Java 21 virtual thread + structured concurrency** — 동시성 모델 진화.
7. 각 기능이 **OOP/FP 균형**에서 어디에 위치하나.

## 파일 목록

| # | 파일 | 핵심 질문 |
|---|---|---|
| 01 | [01-java-7-and-before.md](./01-java-7-and-before.md) | Java 7까지의 boilerplate 지옥 |
| 02 | [02-java-8-lambda-stream.md](./02-java-8-lambda-stream.md) | 람다/Stream/Optional + invokedynamic |
| 03 | [03-java-9-to-11-modules.md](./03-java-9-to-11-modules.md) | 모듈, var, LTS 사이클 |
| 04 | [04-java-14-to-16-record.md](./04-java-14-to-16-record.md) | switch expression + record |
| 05 | [05-java-17-sealed.md](./05-java-17-sealed.md) | sealed + ADT의 본격 도입 |
| 06 | [06-java-21-pattern-and-vthread.md](./06-java-21-pattern-and-vthread.md) | Pattern Matching + Virtual Thread |
| 07 | [07-data-oriented-programming.md](./07-data-oriented-programming.md) | Brian Goetz의 새 패러다임 비전 |

## 7단 학습 레이어

### 1단. 백지 그리기

```
[그림 1] Java 기능 진화 타임라인 (2014~2023)
   2014       2017      2018       2021       2023
   Java 8     Java 9    Java 10    Java 17    Java 21
   ─────      ─────     ─────      ─────      ─────
   Lambda     Module    var        Sealed     Pattern Match
   Stream     jshell    (local)    Record     Virtual Thread
   Optional   ─────                ─────      Record Pattern
   default    Java 11   Java 14    Switch     Sequenced Coll
   method     LTS       Switch     Expr       String Templates
              ─────     Expr       Text Block ─────────────
                        (preview)  ─────      Java 25? LTS
                                                (2025)

[그림 2] 각 기능의 패러다임 위치
                          OOP ← → FP
   Lambda (8)                   ●─────
   Stream (8)                   ●─────
   Optional (8)                 ●─────
   Module (9)            ●──────
   var (10)              ──●───
   Switch Expr (14)             ●─────
   Record (16)           ──●─── 
   Sealed (17)           ──●─── (Sum Type for OOP)
   Pattern Match (21)           ●───── (FP 완성)
   Virtual Thread (21)   ──●─── (동시성 OOP)
   Data Oriented (22+)   ─────── 둘 다

[그림 3] OOP + FP 통합 코드 예시 (Java 21)
   sealed interface Shape permits Circle, Square, Rectangle {}
   record Circle(double radius) implements Shape {}
   record Square(double side) implements Shape {}
   record Rectangle(double w, double h) implements Shape {}

   double area(Shape s) {
       return switch (s) {
           case Circle c -> Math.PI * c.radius() * c.radius();
           case Square q -> q.side() * q.side();
           case Rectangle r -> r.w() * r.h();
       };  // exhaustive — 새 Shape 추가시 컴파일 에러
   }
   // sealed (OOP) + record (ADT) + pattern matching (FP)
   // 한 호흡에 OOP/FP 결합
```

### 2단. 직관

- Java 8 → "**람다와 Stream으로 함수형 한 발 들임**".
- Java 9~10 → "**준비 (모듈, var) — 다음 큰 진화를 위한**".
- Java 14~17 → "**ADT 도입 (record, sealed) — Data로의 회귀**".
- Java 21 → "**Pattern Matching + Virtual Thread — 표현식 + 동시성 완성**".

### 3단. 구조 — 산업적 압력과 응답

```
산업 압력                          Java 응답
─────────────                    ─────────────────
2010s 멀티코어 시대                Java 8 Stream parallel
함수형 언어(Scala) 약진             Java 8 lambda
"왜 Java는 Optional 없냐"          Java 8 Optional
"왜 Java는 immutable record 없냐"   Java 16 record (Kotlin이 6년 먼저)
"왜 Java는 sealed 없냐"            Java 17 sealed (Scala가 20년 먼저)
"왜 Java는 pattern matching 없냐"   Java 21 pattern (Haskell이 30년 먼저)
"왜 Java thread는 expensive하냐"    Java 21 virtual thread
```

→ **Java의 일관된 전략**: "검증된 기능을 신중하게 흡수, 호환성 유지". 늦지만 빠짐없이.

### 4단. 내부 구현 — 주요 기능의 바이트코드

#### Lambda (Java 8)
```
bytecode: invokedynamic LambdaMetafactory.metafactory(
    MethodType target, MethodType signature, MethodHandle impl)
런타임에 LambdaMetafactory가 람다 클래스를 동적 생성 + 캐시
```

#### Record (Java 16)
```java
record Point(int x, int y) {}
// 컴파일러가 자동 생성:
// - private final int x; private final int y;
// - public int x(); public int y();
// - public boolean equals(Object); public int hashCode(); public String toString();
// - public Point(int x, int y);

// ACC_FINAL 클래스 + ACC_RECORD attribute
// Reflection: Class.getRecordComponents() — 분해 가능
```

#### Sealed (Java 17)
```java
sealed interface Shape permits Circle, Square {}
// ClassFile attribute: PermittedSubclasses
// 컴파일러 + JVM이 permitted list 외 구현체 거부
```

#### Pattern Matching (Java 21)
```java
switch (shape) {
    case Circle c -> ...
    case Square s -> ...
}
// bytecode: invokedynamic + SwitchBootstraps.typeSwitch
// 컴파일러가 type pattern을 효율적 dispatch로 변환
```

#### Virtual Thread (Java 21)
```
- Project Loom의 결과
- Continuation 기반 (JVM 내부 메커니즘)
- OS thread 1개 = JVM virtual thread N개 (M:N)
- 동기 코드 작성 + 비동기 성능
- 자세히: ../jvm/ 챕터
```

### 5단. 역사

| 연도 | 버전 | 핵심 기능 | 트리거 |
|---|---|---|---|
| 2014 | Java 8 | Lambda, Stream, Optional, default method | 함수형 언어 약진 + 멀티코어 |
| 2017 | Java 9 | Modules (Jigsaw), jshell | 거대 jar 의존성 지옥 |
| 2018 | Java 10 | var (local type inference) | boilerplate 감소 |
| 2018 | Java 11 LTS | HTTP Client, String 메서드 | 6개월 릴리스 첫 LTS |
| 2020 | Java 14 | switch expression GA, record preview | 표현식 기반 + ADT |
| 2021 | Java 16 | record GA, sealed preview | Kotlin/Scala 패턴 흡수 |
| 2021 | Java 17 LTS | sealed GA, pattern matching for instanceof | LTS + 함수형 ADT |
| 2022 | Java 19 | virtual thread preview | Loom 첫 공개 |
| 2023 | Java 21 LTS | Virtual Thread GA, Pattern Matching for switch GA, Record Pattern GA | Loom + ADT 완성 |
| 2024 | Java 22 | Stream Gatherers (preview) | Stream 표현력 확장 |

### 6단. 트레이드오프 — Java의 점진적 진화 선택

**Java가 선택한 길**:
- 호환성 유지 (옛 코드가 새 JDK에서 작동)
- 점진적 도입 (preview → GA)
- 의미 충돌 회피 (`var`는 키워드 아닌 reserved type name 등)

**비용**:
- 다른 언어(Kotlin, Scala)보다 늦음
- 일부 기능이 어색 (Optional이 모나드인데 syntax 지원 없음)
- 호환성을 위해 어색한 결정 (`record`의 inheritance 금지 등)

**이득**:
- 산업 채택 압도적
- 옛 시스템도 점진적 현대화 가능
- 검증된 기능만 들어옴

### 7단. 운영 진단 — Java 버전별 마이그레이션 함정

- **8 → 11 (LTS to LTS)**:
  - sun.misc.Unsafe 제거 — 일부 라이브러리 깨짐
  - JEE 모듈 제거 (`javax.xml.bind` 등) — 의존성 추가 필요
- **11 → 17 (LTS to LTS)**:
  - 강한 캡슐화 (`--add-opens` 필요한 경우 증가)
  - GC: ZGC/Shenandoah 사용 가능
- **17 → 21 (LTS to LTS)**:
  - Virtual Thread 도입 시 `synchronized` 블록의 pinning 주의 (`-Djdk.tracePinnedThreads`)
  - synchronized → ReentrantLock 전환 검토 (JEP 491에서 개선 진행 중)

## 꼬리질문

### Junior
1. **Q**: Java 8의 람다는 익명 클래스와 같나요?
   → No. 익명 클래스는 매번 새 클래스 + 객체 생성. 람다는 `invokedynamic` + LambdaMetafactory로 첫 호출 시 동적 클래스 생성 + 캐시. 메모리/성능 차이.

### Senior
2. **Q**: `record`는 Kotlin `data class`와 무엇이 다른가요?
   → 5가지:
   1. record는 **상속 금지** (final), data class는 open 가능
   2. record는 **불변 강제** (모든 컴포넌트 final), data class는 var 가능
   3. record는 `equals/hashCode/toString`만 자동, data class는 `copy()`도 자동
   4. record는 Pattern Matching과 결합 (Java 21 record pattern), data class는 destructuring (`val (x, y) = point`)
   5. record는 어노테이션으로 component 위치 조정 가능, data class는 단순 primary constructor
3. **꼬리**: 그럼 Java도 `copy()`가 있으면 더 좋지 않을까요? 왜 안 넣었나요?
   → 설계 회의에서 논의됨. `copy(x=10)` 같은 named argument 문법이 Java에 없어서 표현력 한계. Java는 builder 패턴 권장 또는 record 자체가 immutable이라 부분 복사 시 명시적 새 record 생성 (`new Point(p.x() + 1, p.y())`). → "named/default arguments 없는 한 copy도 우아하지 않다"는 설계 판단.

### Principal
4. **Q**: Brian Goetz의 "Data Oriented Programming"이란?
   → "모든 것을 객체로 모델링" 대신 "**데이터는 데이터로, 행위는 함수로**"의 사상. record(데이터) + sealed(폐쇄된 데이터 종류) + pattern matching(데이터별 분기). → 도메인 객체 중 일부는 DOP로, 일부는 OOP로. 한 언어 안에 두 패러다임 공존.
5. **꼬리**: 그럼 OOP가 죽는 것 아닌가요?
   → No. DOP는 "**데이터가 자율성을 필요로 하지 않는 경우**"에 적합. 예: `sealed Result { Success, Failure }` 같은 결과 표현. 도메인 핵심 (`Order`, `Account`)은 여전히 OOP가 자연. DOP는 OOP를 보완.
6. **꼬리의 꼬리**: 그렇다면 미래의 Java 개발자는 두 패러다임을 어떻게 구분해서 쓸 수 있어야 하나요?
   → 결정 기준:
   - 데이터가 **상태 변화의 주체**이고 자율적 행위를 가지나? → OOP (class + methods)
   - 데이터가 **값**이고 변화는 변환(새 값 생성)인가? → DOP (record + sealed + pattern)
   → Order는 OOP, OrderStatus는 sealed (Pending|Paid|Cancelled). 같은 도메인 안에 공존.

## 다음 챕터로

- [11-kotlin-paradigm](../11-kotlin-paradigm/) — Java를 넘어선 균형
