# 02. Abstraction & Encapsulation — OOP의 4대 기둥

> **이 챕터의 한 줄 목표**: "캡슐화는 데이터 은닉이다"라는 통념을 깨고, **변경의 캡슐화**라는 진짜 정의로 사고를 전환한다. 다형성의 JVM 구현(`invokevirtual` + vtable + Inline Cache)까지 한 호흡에 설명할 수 있게 된다.

## 📖 이론적 골격

| 책 / 장 | 핵심 |
|---|---|
| 조영호 오브젝트 5장 | 책임 할당 + 추상화 |
| Effective Java 3rd 16조 | 접근 메서드 vs public 필드 |
| Effective Java 3rd 22조 | 인터페이스는 타입을 정의하는 용도 |
| GoF Design Patterns | Strategy, Template Method, Decorator (다형성 활용) |

## 학습 목표

1. **추상화와 캡슐화의 차이**를 한 줄로 구분.
2. **`getter/setter` 남발이 캡슐화를 깬다**는 이유를 코드로 증명.
3. **다형성의 3종류** (Subtype, Parametric, Ad-hoc)를 예시로 구분.
4. **다이내믹 디스패치의 JVM 구현** (`invokevirtual`, vtable, IC)을 설명.
5. **상속의 4대 위험**과 그 대안 (인터페이스, 합성)을 안다.

## 파일 목록

| # | 파일 | 핵심 질문 |
|---|---|---|
| 01 | [01-abstraction.md](./01-abstraction.md) | 추상화의 본질 — 본질 추출 + 일반화 |
| 02 | [02-encapsulation.md](./02-encapsulation.md) | 캡슐화 = 데이터 은닉? 아니다. 변경의 캡슐화 |
| 03 | [03-polymorphism.md](./03-polymorphism.md) | 다형성 3종류 + JVM `invokevirtual` 내부 |
| 04 | [04-inheritance-and-interface.md](./04-inheritance-and-interface.md) | 상속 vs 인터페이스 — 언제 무엇을 |

## 7단 학습 레이어

### 1단. 백지 그리기

```
[그림 1] 추상화 vs 캡슐화 분리
       추상화 (Abstraction)               캡슐화 (Encapsulation)
       ──────────────────────             ──────────────────────
       "본질만 남기고 나머지 무시"          "변경 가능성 있는 것을 외부와 격리"
       관점: 외부에서 본 모습              관점: 내부 구현 숨김
       도구: 인터페이스, 추상클래스         도구: private, 메서드 노출
       예: Shape (구체 도형은 모름)         예: List 내부 배열 → 외부는 add()만 봄

[그림 2] 다형성의 3종류
        Subtype Polymorphism
        ─────────────────────
        interface Animal { speak(); }
        Dog implements Animal → "멍멍"
        Cat implements Animal → "야옹"
        animal.speak() // 런타임 디스패치

        Parametric Polymorphism (Generic)
        ─────────────────────
        List<T>  ← T가 무엇이든 동작
        Function<A, B>

        Ad-hoc Polymorphism
        ─────────────────────
        오버로딩: print(int), print(String), print(double)
        Kotlin 확장 함수
        Haskell 타입 클래스

[그림 3] 다이내믹 디스패치 (JVM)
        animal.speak()              // bytecode: invokevirtual Animal.speak
              ▼
        ┌─────────────────────┐
        │ Inline Cache (IC)    │ ← 자주 본 타입 캐싱 (monomorphic ≤ 1, bimorphic ≤ 2)
        └─────────┬───────────┘
                  │ cache miss
                  ▼
        ┌─────────────────────┐
        │ vtable lookup        │ ← Klass의 method table에서 슬롯 찾기
        │ Klass*               │
        │ → vtable[slot]       │
        │ → 실제 method 진입    │
        └─────────────────────┘
```

### 2단. 직관

- **추상화**: "수많은 도형이 있어도, 면적을 계산하는 인터페이스 하나로 본다" → 본질만 남김.
- **캡슐화**: "방 안에 뭐가 있는지는 모르겠고, 문 두드리면 음식이 나온다" → 내부 모름.
- **둘의 관계**: 추상화는 **밖에서 보는 관점**, 캡슐화는 **안을 숨기는 행위**. 같은 동전의 양면.
- **다형성**: "같은 명령에 다른 반응" — 강아지/고양이/소가 모두 `speak()`에 응답하지만 소리가 다름.
- **상속**: "is-a" 관계. 단, **코드 재사용 목적 상속은 거의 항상 안티패턴**.

### 3단. 구조 — 캡슐화의 4가지 종류 (조영호)

| 종류 | 무엇을 숨기나 | 예시 |
|---|---|---|
| **데이터 캡슐화** | 필드 → private | `private balance` |
| **메서드 캡슐화** | 내부 메서드 → private | `private validate()` |
| **객체 캡슐화** | 객체 그래프 → 노출 금지 | 컬렉션을 외부에 직접 노출 X |
| **서브타입 캡슐화** | 구체 타입을 인터페이스 뒤에 숨김 | `List` 반환 (`ArrayList` 숨김) |

→ 흔히 데이터 캡슐화만 떠올리지만, 실무에서는 **객체 캡슐화 + 서브타입 캡슐화**가 더 중요.

### 4단. 내부 구현 — JVM Dynamic Dispatch

```
[Java 코드]
Animal animal = new Dog();
animal.speak();

[Bytecode]
new           Dog
dup
invokespecial Dog.<init>
astore_1
aload_1
invokevirtual Animal.speak

[JVM 런타임]
1. invokevirtual은 컴파일 타임에 어떤 메서드를 호출할지 모름
2. animal 객체의 Klass*를 가져와서
3. vtable에서 speak의 슬롯을 lookup
4. JIT은 이 호출 지점을 모니터링 → 항상 Dog만 본다면 monomorphic
5. Inline Cache가 Dog.speak를 직접 호출로 변환 (가상 호출 비용 제거)
6. 만약 Cat이 등장 → bimorphic, 두 타입 다 보면 megamorphic → IC 폐기
```

**중요한 실무 함의**:
- `final class` 또는 `sealed class`로 단형성을 보장하면 JIT 최적화 극대화.
- 무분별한 인터페이스 + 다중 구현은 megamorphic call site를 만들어 P99 latency 악화 가능.
- 이는 JVM 챕터 03-execution-engine과 cross-reference.

### 5단. 역사

- **1967 Simula**: 단일 상속 + 가상 메서드.
- **1972 Smalltalk**: 모든 메서드가 가상 (다형성 기본).
- **1985 C++**: 가상 메서드를 `virtual` 키워드로 명시 + 다중 상속 + Diamond Problem.
- **1995 Java**: 단일 상속 + 인터페이스 다중 구현 (Diamond Problem 회피).
- **2014 Java 8 default method**: 인터페이스가 구현을 가질 수 있음 → 약한 다중 상속 부활 + 새로운 Diamond Problem.
- **2017 Java 9 private interface method**: default method 헬퍼 메서드.
- **2021 Java 17 sealed class/interface**: 상속 가능 타입 명시 제한 → ADT + pattern matching 토대.

### 6단. 트레이드오프 — 상속 vs 인터페이스 vs 합성

| 축 | 상속 (extends) | 인터페이스 구현 | 합성 (Composition) |
|---|---|---|---|
| **재사용** | 부모 코드 그대로 | 코드 재사용 X (Java 8 이전) | 위임 메서드로 명시 |
| **결합도** | 매우 강함 (부모 변경에 영향) | 매우 약함 | 약함 (인터페이스 통해 의존) |
| **다중 상속** | X (Java) | O (다중 구현) | O (여러 객체 보유) |
| **런타임 교체** | X | O (다른 구현 주입) | O |
| **테스트 용이성** | 낮음 (mock 어려움) | 매우 높음 | 매우 높음 |
| **언제** | 진짜 is-a 관계 + 안정적 부모 | 행위 계약 | 거의 모든 코드 재사용 |

→ **결론**: "상속은 제일 마지막에 선택지". Effective Java 18조.

### 7단. 운영 진단

(이후 챕터에서 풀버전 + 08-inheritance-vs-composition)

- **Getter 폭격 진단**: 도메인 객체에 `get*`만 잔뜩 → 외부가 데이터를 꺼내서 직접 처리 → Tell Don't Ask 위반.
- **상속 깊이**: 클래스 계층 4단 이상 → 깨지기 쉬운 기반 클래스 위험.
- **Megamorphic call**: P99 latency가 spike 시, JIT log (`-XX:+PrintInlining`)로 megamorphic call 식별.

## 꼬리질문 (Junior → Senior → Principal)

### Junior 레벨
1. **Q**: 캡슐화의 정의는?
   → 데이터를 숨기고 메서드로만 접근하게 하는 것.
2. **꼬리**: 그럼 모든 필드를 private로 만들고 모든 필드에 getter/setter를 만들면 캡슐화가 잘된 건가요?
   → No. 그건 단지 "field access를 method call로 바꾼 것"일 뿐, 외부는 여전히 내부 구현(필드 존재 여부)을 안다. 진짜 캡슐화는 **변경 가능성이 있는 것을 외부와 격리**하는 것 — 객체에게 일을 시키는 메서드(`order.cancel()`)가 답.

### Senior 레벨
3. **Q**: 다형성을 위해 인터페이스를 만들 때, 어떤 메서드를 인터페이스에 둘지 어떻게 결정하나요?
   → 클라이언트가 **사용하는 메서드만**. ISP (인터페이스 분리 원칙). 한 구현체에만 필요한 메서드를 공통 인터페이스에 넣으면 다른 구현체가 빈 메서드를 강제로 가짐.
4. **꼬리**: Java 8 default method가 나오기 전과 후, 인터페이스 설계가 어떻게 달라졌나요?
   → 전: 메서드 추가 = 모든 구현체 깨짐. → 인터페이스를 매우 작게 유지 (`Runnable`, `Comparable`).
   → 후: default method로 호환성 유지하며 메서드 추가 가능 (`Stream`, `Iterable.forEach`).
   → but: default method가 상태를 가질 수 없고 다중 상속 시 Diamond Problem 부활 → 신중히 사용.
5. **꼬리의 꼬리**: Kotlin은 인터페이스에 프로퍼티도 둘 수 있는데, Java와 어떻게 다른가요?
   → Kotlin 인터페이스 프로퍼티는 abstract 또는 getter 구현만 가능 (필드 백업 없음). Java의 default method보다 풍부하지만 여전히 상태 보관 X.

### Principal 레벨
6. **Q**: JVM의 `invokevirtual`이 `invokestatic`보다 느린 이유와 JIT이 그걸 어떻게 회복하나요?
   → `invokevirtual`은 런타임 타입 lookup 필요 → 분기 + 메모리 접근. `invokestatic`은 컴파일 타임 결정.
   → JIT 회복: **Inline Cache** (1~2개 타입 캐싱) + **Class Hierarchy Analysis (CHA)** (구현체가 하나면 단형성으로 추론 + 인라이닝). 단형성 확인 후 `invokevirtual`을 인라인된 직접 호출로 변환. 만약 새 구현체 로드되면 **Deoptimization**으로 인라인 해제.
7. **꼬리**: `sealed interface`가 도입되면서 이 JIT 최적화는 어떻게 강화되나요?
   → 컴파일 타임에 구현체 집합이 닫혀 있음 → JIT이 CHA 결과를 더 강하게 신뢰 가능. 새 구현체 동적 로드를 무시할 수 있어 deoptimization 가드 단순화. Pattern matching `switch` 컴파일도 `tableswitch`로 최적화 가능.
8. **꼬리의 꼬리**: Kotlin `sealed class`와 Scala `sealed trait`의 차이는?
   → 둘 다 같은 컴파일 단위(파일/패키지) 안에서만 상속 허용. Scala는 전통적으로 `case class`와 결합해 ADT + pattern matching의 원조. Kotlin은 그걸 흡수했고, Java 17에서 `sealed` 키워드로 표준화. **세 언어 모두 Sum Type을 OOP 안에 통합한 결과**.

## 다음 챕터로

- [03-responsibility-assignment](../03-responsibility-assignment/) — GRASP 9원칙
