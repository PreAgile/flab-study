# 08. Inheritance vs Composition — "상속보다 합성을"

> **이 챕터의 한 줄 목표**: "코드 재사용 = 상속"이라는 통념을 깨고, Effective Java 18조 ("상속보다 컴포지션을 사용하라")의 모든 논거를 5분 안에 설명할 수 있다. Java/Kotlin/Scala의 mixin/trait/delegation 비교까지.

## 📖 이론적 골격

| 책 | 핵심 |
|---|---|
| 조영호 『오브젝트』 10~12장 | 상속과 코드 재사용, 합성과 유연성 |
| Effective Java 18조 | 상속보다 컴포지션 |
| Effective Java 19조 | 상속을 고려해 설계·문서화 또는 금지 |
| GoF Design Patterns | Decorator, Composite (합성 기반) |

## 학습 목표

1. **상속의 4대 위험** — 캡슐화 위반, 강한 결합, 깨지기 쉬운 기반 클래스, 다중 상속 불가.
2. **위임 (Delegation)** 패턴 — 합성의 구체 형태.
3. **Java/Kotlin/Scala mixin 메커니즘** 비교.
4. **언제 상속이 정당화되나** — Effective Java 19조의 4가지 조건.
5. **`final class` + `sealed class`의 의미** — 상속 제한의 도구.

## 파일 목록

| # | 파일 | 핵심 질문 |
|---|---|---|
| 01 | [01-four-problems-of-inheritance.md](./01-four-problems-of-inheritance.md) | 상속의 4대 위험 |
| 02 | [02-composition-over-inheritance.md](./02-composition-over-inheritance.md) | Effective Java 18조 풀버전 |
| 03 | [03-delegation-pattern.md](./03-delegation-pattern.md) | 위임 — 합성의 구체 형태 |
| 04 | [04-mixin-trait-comparison.md](./04-mixin-trait-comparison.md) | Java default / Kotlin delegate / Scala trait |
| 05 | [05-when-inheritance-is-ok.md](./05-when-inheritance-is-ok.md) | 19조 — 정당한 상속의 4 조건 |

## 7단 학습 레이어

### 1단. 백지 그리기

```
[그림 1] 상속의 4대 위험
   ┌─────────────────────────────────────────────────────────────┐
   │  1. 캡슐화 위반                                                │
   │     ┌─────────┐                                              │
   │     │ Parent   │ ◄── 자식이 부모 내부 구현에 의존              │
   │     └────▲────┘     부모 protected 메서드 사용                │
   │          │ extends                                            │
   │     ┌────┴────┐                                              │
   │     │ Child    │                                              │
   │     └─────────┘                                              │
   │                                                              │
   │  2. 강한 결합                                                  │
   │     부모 메서드 시그니처 변경 → 자식 깨짐                       │
   │                                                              │
   │  3. 깨지기 쉬운 기반 클래스 (Fragile Base Class)              │
   │     부모 메서드 구현 변경 → 자식의 자기 호출 흐름 깨짐           │
   │                                                              │
   │  4. 다중 상속 불가 (Java)                                     │
   │     A의 동작 + B의 동작 동시 재사용 불가                       │
   └─────────────────────────────────────────────────────────────┘

[그림 2] 합성 (Composition) = 위임
        ┌─────────────────┐
        │  Order           │
        │  - calculator    │ ──► PriceCalculator (합성)
        │                  │
        │  total() {        │
        │   return          │
        │   calculator.       │
        │   compute(items); │
        │  }                │
        └─────────────────┘
        Order는 PriceCalculator 인터페이스만 알면 됨
        구현체 교체 자유

[그림 3] Mixin 진화
   Java 7 이전     : 단일 상속, 다중 인터페이스 (행위 재사용 X)
   Java 8 default  : 인터페이스에 default method (행위 재사용 약함)
   Scala trait    : 다중 trait 상속 + linearization
   Kotlin by      : 인터페이스 위임 (`class Foo : I by impl`)
```

### 2단. 직관

- **상속의 본질적 위험**: 부모와 자식이 **같은 변경 사이클을 공유**. 한 쪽 변경이 다른 쪽 깨뜨림.
- **합성의 본질적 안전성**: 위임 대상은 **인터페이스 뒤에 숨어** 변경 시 영향 격리.
- **"is-a" vs "has-a"** 시험: 상속은 진짜 "is-a"일 때만. "OrderEntity is Customer"는 우습지만 "Order has Customer"는 자연스러움.

### 3단. 구조 — 합성으로 리팩토링

```java
// === 안티패턴: 상속으로 코드 재사용 ===
public class HashSet<E> { /* ... */ }
public class InstrumentedHashSet<E> extends HashSet<E> {
    private int addCount;

    @Override
    public boolean add(E e) {
        addCount++;
        return super.add(e);
    }

    @Override
    public boolean addAll(Collection<? extends E> c) {
        addCount += c.size();
        return super.addAll(c);  // 내부에서 add를 호출함 → addCount 중복 카운트
    }
}
// 버그: addAll 호출 시 size + size 중복.
// 원인: HashSet 내부의 자기-호출(self-invocation) 패턴에 의존.

// === 해법: 합성 + 위임 ===
public class ForwardingSet<E> implements Set<E> {
    private final Set<E> s;
    public ForwardingSet(Set<E> s) { this.s = s; }

    @Override public boolean add(E e) { return s.add(e); }
    @Override public boolean addAll(Collection<? extends E> c) { return s.addAll(c); }
    // 모든 Set 메서드를 위임
}

public class InstrumentedSet<E> extends ForwardingSet<E> {
    private int addCount;

    public InstrumentedSet(Set<E> s) { super(s); }

    @Override
    public boolean add(E e) {
        addCount++;
        return super.add(e);
    }

    @Override
    public boolean addAll(Collection<? extends E> c) {
        addCount += c.size();
        return super.addAll(c);  // 이제는 위임만, 자기-호출 없음
    }
}
// 어떤 Set 구현체든 wrap 가능 (Decorator 패턴)
```

### 4단. 내부 구현 — Kotlin의 위임 키워드

```kotlin
// Java에서 ForwardingSet 같은 boilerplate를 Kotlin은 `by` 키워드로 자동
class InstrumentedSet<E>(private val s: MutableSet<E>) : MutableSet<E> by s {
    var addCount = 0
        private set

    override fun add(element: E): Boolean {
        addCount++
        return s.add(element)
    }

    override fun addAll(elements: Collection<E>): Boolean {
        addCount += elements.size
        return s.addAll(elements)
    }
}
// `by s` 한 줄로 위임. 나머지 모든 Set 메서드는 자동으로 s로 위임.
```

**Kotlin 컴파일 결과**: `by`는 컴파일러가 Java의 ForwardingSet 같은 wrapper 코드를 자동 생성. 런타임 성능 동일.

### 5단. 역사 — Mixin/Trait 진화

| 시점 | 언어 | 메커니즘 | 특징 |
|---|---|---|---|
| 1972 | Smalltalk | mixin (상속의 일종) | 다중 상속 허용 |
| 1985 | C++ | 다중 상속 | Diamond Problem |
| 1995 | Java | 단일 상속 + 인터페이스 | 행위 재사용 X (interface는 spec만) |
| 2003 | Scala | trait | linearization으로 Diamond 해결 |
| 2011 | Kotlin | `by` 위임 + interface default | Scala trait의 단순화 버전 |
| 2014 | Java 8 | default method | 약한 mixin |
| 2017 | Java 9 | private interface method | default method 헬퍼 |
| 2021 | Java 17 | sealed | 상속 제한 |

### 6단. 트레이드오프 — 상속 vs 합성 매트릭스

| 축 | 상속 | 합성 |
|---|---|---|
| **코드 재사용** | 자동 (부모 메서드 그대로) | 명시적 (메서드마다 위임) |
| **결합도** | 매우 강함 | 약함 (인터페이스 통해) |
| **유연성 (런타임 교체)** | X (컴파일 타임 고정) | O |
| **테스트 (Mock)** | 어려움 | 쉬움 |
| **자기-호출 함정** | 위험 | 없음 |
| **다중 재사용** | X (Java) | O (여러 객체 보유) |
| **API 노출 통제** | 약함 (모든 protected 노출) | 강함 (필요한 것만 위임) |
| **개발 속도 (초기)** | 빠름 | 약간 느림 (boilerplate) |

→ **Effective Java 18조**: "상속은 같은 패키지 안에서만, 또는 명시적으로 설계된 클래스만". 그 외는 합성.

### 7단. 운영 진단

- **상속 깊이 진단**:
  - 4단 이상 상속 → 깨지기 쉬운 기반 클래스 위험
  - `JpaRepository → CrudRepository → Repository` 같이 프레임워크 제공은 OK
  - 자체 도메인에서 4단 → 분해 검토
- **`super.method()` 의존 진단**:
  - 자식이 부모 메서드를 호출하는 코드가 많으면 결합 강함
  - 합성 + 위임으로 전환 검토
- **JPA `@Inheritance` 진단**:
  - SINGLE_TABLE: nullable column 폭발
  - JOINED: 조인 비용
  - TABLE_PER_CLASS: ID 충돌 위험
  - 종종 합성 (`@Embedded`) + Discriminator 컬럼이 더 깔끔

## 꼬리질문

### Junior
1. **Q**: 상속이 왜 위험한가요?
   → 부모 변경이 자식으로 전파됨. 캡슐화 깨짐.

### Senior
2. **Q**: Joshua Bloch가 든 `HashSet` 예시에서, 왜 `addAll` 안에서 `add`가 호출되는 게 문제인가요?
   → 자기-호출(self-invocation) 패턴은 부모의 **내부 구현 디테일**. 자식이 그것에 의존하면 부모가 내부적으로 `addAll`을 다른 방식으로 구현 (예: bulk insert)으로 바꾸는 순간 자식이 깨짐. → 상속은 부모의 **공개 명세**뿐 아니라 **내부 구현**에도 의존하게 함.
3. **꼬리**: Spring AOP가 `@Transactional`을 self-invocation 시 무효화하는 것도 같은 원인인가요?
   → 정확히 같은 패밀리의 문제. AOP는 프록시 객체로 가로채는데, 클래스 내부의 self-invocation은 프록시를 거치지 않고 직접 호출. → 위임 기반(프록시) 메커니즘과 self-invocation의 충돌.

### Principal
4. **Q**: `sealed class`가 상속 vs 합성 논쟁에 어떤 영향을 주나요?
   → sealed는 "**제한된 상속**"을 안전하게 만든다. 컴파일 타임에 모든 하위 타입을 알고 있어 LSP 검증 가능, pattern matching의 exhaustiveness 보장. → 상속이 "위험"한 이유는 미지의 확장이었는데, sealed는 그걸 제거. → ADT (Sum Type)로서의 상속은 안전, 코드 재사용 목적 상속은 여전히 위험.
5. **꼬리**: 그럼 sealed + record + pattern matching이 결합되면 OOP가 함수형 ADT처럼 보이는데, 이게 OOP의 미래인가요?
   → 그렇게 보는 시각이 있다 (Java Brian Goetz의 "Data Oriented Programming"). 도메인 객체 중 일부는 ADT로 모델링 (e.g., `sealed Order { Pending, Paid, Cancelled }`), 행위 객체는 전통 OOP. 두 가지 표현을 같은 언어에서 다 쓰는 게 21세기 OOP.
6. **꼬리의 꼬리**: 그렇다면 Domain-Driven Design의 Aggregate는 ADT인가, OOP인가?
   → 보통 **Aggregate Root는 OOP (행위 가진 자율 객체), Value Object는 ADT 친화** (불변 record). Kotlin: data class + sealed로 표현 가능. Java: record + sealed. 둘은 적대적이지 않다.

## 다음 챕터로

- [09-functional-paradigm](../09-functional-paradigm/) — OOP의 보완 패러다임
