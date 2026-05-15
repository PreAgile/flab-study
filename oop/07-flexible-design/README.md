# 07. Flexible Design — SOLID + 디자인 패턴

> **이 챕터의 한 줄 목표**: SOLID 5원칙을 외우는 게 아니라, **각 원칙이 어떤 변경에 대응하기 위한 것인가**를 매핑할 수 있다. GoF 23개 패턴을 외우지 말고 "변경 종류"별로 분류해 필요할 때 떠올린다.

## 📖 이론적 골격

| 책 | 핵심 |
|---|---|
| 조영호 『오브젝트』 9~14장 | 유연한 설계 + 디자인 패턴 |
| Robert Martin 『Clean Architecture』 | SOLID 5원칙 정의 |
| GoF 『Design Patterns』 (1994) | 23개 패턴의 원전 |
| Joshua Kerievsky 『Refactoring to Patterns』 | 패턴 도입 시점 |

## 학습 목표

1. **SOLID 5원칙**을 각각 **어떤 변경 종류에 대한 답**인지 매핑.
2. **OCP**의 진짜 의미 — "확장에 열려있고 수정에 닫혀있다"가 실제 코드에서.
3. **LSP**의 위반 사례 — `Rectangle/Square` 고전 + 현대 사례.
4. **핵심 디자인 패턴 10개**: Strategy, Template Method, Observer, Decorator, Adapter, Facade, Factory Method, Singleton, Command, Composite.
5. **Pattern 남용 안티패턴** — Anemic + Pattern Overdose.

## 파일 목록

| # | 파일 | 핵심 질문 |
|---|---|---|
| 01 | [01-solid-five.md](./01-solid-five.md) | SOLID 각 원칙의 정확한 의미 + 변경 매핑 |
| 02 | [02-open-closed-deep.md](./02-open-closed-deep.md) | OCP — 추상화의 비용/효익 |
| 03 | [03-liskov-substitution.md](./03-liskov-substitution.md) | LSP 위반 진단 + 사전/사후 조건 |
| 04 | [04-design-patterns-classified.md](./04-design-patterns-classified.md) | GoF 23개를 변경 종류로 분류 |
| 05 | [05-pattern-overdose.md](./05-pattern-overdose.md) | 패턴 남용 안티패턴 |

## 7단 학습 레이어

### 1단. 백지 그리기

```
[그림 1] SOLID와 변경 종류 매핑
   SRP (단일 책임)      → "한 클래스가 너무 많은 이유로 변경된다"
   OCP (개방-폐쇄)      → "새 종류 추가에 기존 코드 수정 필요"
   LSP (리스코프 치환)   → "하위 타입이 상위 타입의 계약을 깬다"
   ISP (인터페이스 분리) → "구현체가 안 쓰는 메서드를 강제 구현"
   DIP (의존성 역전)    → "상위 모듈이 하위 모듈 변경에 영향받음"

[그림 2] GoF 패턴 분류 (변경 종류별)
   알고리즘 변경       → Strategy, Template Method, Visitor
   객체 생성 변경      → Factory Method, Abstract Factory, Builder
   기능 추가         → Decorator, Chain of Responsibility
   인터페이스 변환     → Adapter, Facade, Proxy
   상태 변경 → 행위 변경 → State, Observer, Command
   계층 구조         → Composite, Iterator

[그림 3] OCP 적용 흐름
   1. 변경 종류 식별 ("새 할인 정책이 자주 추가됨")
   2. 변경 지점 캡슐화 (DiscountPolicy 인터페이스)
   3. 추상화 의존 (Movie는 DiscountPolicy만 알기)
   4. 새 기능 = 새 클래스 (AmountDiscountPolicy, RatioDiscountPolicy)
   → 기존 코드 변경 X (Closed), 확장 가능 (Open)
```

### 2단. 직관

- **SOLID**: "변경에 강한 설계의 5가지 시그널". 위반하면 변경 비용 ↑.
- **디자인 패턴**: "재발하는 설계 문제의 정형 답안". 새로 발명할 필요 없음.
- **변경의 종류를 모르면 SOLID/패턴은 over-engineering**. 변경이 한 번 일어났을 때 비로소 추상화 (YAGNI + Rule of Three).

### 3단. 구조 — SOLID 5원칙 코드 매핑

```java
// === SRP 위반 ===
class Order {
    void calculateTotal() {...}
    void saveToDatabase() {...}        // 영속성 책임
    void sendEmailNotification() {...} // 알림 책임
}
// → 분리: Order, OrderRepository, OrderNotifier

// === OCP 위반 ===
class PriceCalculator {
    long calculate(Order o) {
        if (o.getType().equals("VIP")) ...
        else if (o.getType().equals("NORMAL")) ...
        // 새 타입 = 이 메서드 수정
    }
}
// → Strategy: PricingPolicy 인터페이스 + 구현체들

// === LSP 위반 (고전) ===
class Rectangle { void setWidth(int w); void setHeight(int h); }
class Square extends Rectangle {
    void setWidth(int w) { super.setWidth(w); super.setHeight(w); } // 사이드 이펙트
}
// 클라이언트가 Rectangle 가정으로 코드 작성 → Square로 치환 시 깨짐

// === ISP 위반 ===
interface Worker { void work(); void eat(); void sleep(); }
class Robot implements Worker {
    void work() {...}
    void eat() { throw new UnsupportedOperationException(); }  // 강제 구현
    void sleep() { throw new UnsupportedOperationException(); }
}
// → 분리: Workable, Eatable, Sleepable

// === DIP 위반 ===
class OrderService {
    private MySqlOrderRepository repository;  // 구체에 의존
}
// → 추상화 의존: private OrderRepository repository;
```

### 4단. 내부 구현 — 디자인 패턴이 JVM에서 어떻게 보이는지

- **Strategy** = 다형성 + 위임. `invokevirtual` + vtable.
- **Template Method** = 상속의 hook. 추상 메서드 호출.
- **Observer** = 함수 리스트 보유 + 순회. Java의 `EventListener`, Spring `ApplicationEvent`.
- **Decorator** = 위임 + 추가 행위. Java I/O의 `BufferedInputStream(new FileInputStream(...))`.
- **Adapter** = 위임 + 인터페이스 변환. Spring `HandlerAdapter`.
- **Singleton** = static field + private constructor. JVM의 ClassLoader가 클래스 단위 단일성 보장.
- **Factory Method** = static 생성 메서드 + 추상화. `Optional.of(x)`, `List.of(...)`.

### 5단. 역사

- **1987 Christopher Alexander 『A Pattern Language』 (건축)**: 디자인 패턴 사상의 원전.
- **1994 GoF 『Design Patterns』**: SW 디자인 패턴 출현.
- **2000 Robert Martin SOLID**: 1996년 SRP/OCP 글들 종합.
- **2004 Joshua Kerievsky 『Refactoring to Patterns』**: 미래 추측이 아닌 리팩토링 결과로 패턴 도입.
- **2019 조영호 오브젝트 9~14장**: 영화 예매 시스템 안에서 패턴 자연스럽게 도출.
- **2014~ Java 8+**: 람다로 GoF 패턴 중 일부 (Strategy, Command, Observer)가 함수로 대체 가능해짐.

### 6단. 트레이드오프 — Pattern Trade-off

| 패턴 | 이득 | 비용 |
|---|---|---|
| **Strategy** | 알고리즘 교체 용이 | 추상화 비용, 클래스 폭발 |
| **Observer** | 결합도 ↓ | 이벤트 흐름 추적 어려움 |
| **Decorator** | 기능 조합 자유 | 스택이 깊어지면 디버깅 어려움 |
| **Factory Method** | 객체 생성 격리 | 단순한 경우엔 over-engineering |
| **Singleton** | 자원 단일성 | 테스트 어려움, 전역 상태 (안티패턴 측면) |

→ **Joshua Kerievsky 권고**: 패턴을 처음부터 도입하지 말고, **변경이 발생한 후** 리팩토링으로 도입.

### 7단. 운영 진단

- **Pattern Overdose 진단**:
  - 한 도메인에 5개 이상의 패턴 적용 → over-engineering 의심
  - 추상화가 비즈니스 어휘와 다름 (`AbstractOrderProcessorFactoryBean`) → 의도 가림
  - → 그냥 클래스/메서드로 재작성 (Inline Class)
- **Anemic + Pattern 혼합 진단**:
  - "Service + Strategy + Factory" 잔뜩 + 도메인 Entity는 Getter만
  - 패턴은 행위에 적용되어야 하는데 행위가 Service에 흩어짐
  - → 도메인 객체에 행위 모으고 패턴 적용
- **람다로 단순화 가능 진단**:
  - 1개 메서드 인터페이스 (`Strategy`, `Command`, `Comparator`) → 람다로 대체

## 꼬리질문

### Junior
1. **Q**: SRP의 "단일 책임"이 너무 추상적이지 않나요?
   → Robert Martin은 "**변경의 이유**"로 정의. 한 클래스가 두 stakeholder의 요구로 변경되면 SRP 위반.

### Senior
2. **Q**: LSP를 위반하지 않으려면 상속을 어떻게 써야 하나요?
   → 4가지 조건:
   1. 하위 타입 사전 조건이 상위 타입보다 **약하거나** 같다 (Contravariant).
   2. 하위 타입 사후 조건이 상위 타입보다 **강하거나** 같다 (Covariant).
   3. 상위 타입 불변식을 깨지 않는다.
   4. 사이드 이펙트가 새로 생기면 안 됨 (History constraint).
3. **꼬리**: 그렇다면 `equals`가 LSP 위반의 단골 사례인 이유는?
   → 대칭성(symmetry). `a.equals(b)`와 `b.equals(a)`가 같아야 하는데, 상속이 끼면 깨진다.
   `Point p; ColorPoint cp;`에서 `p.equals(cp)`와 `cp.equals(p)`가 다른 비교 기준을 가질 수 있음.
   → Effective Java 11조: "구현하기 어렵다면 상속 대신 합성".

### Principal
4. **Q**: Java 8 람다 도입 후 GoF 패턴 중 무엇이 "구식"이 되었나요?
   → Strategy (단일 메서드 인터페이스 → 람다), Command (Runnable + 람다), Observer (메서드 참조 + 함수형 인터페이스), Template Method (default method 또는 high-order function). 본질은 살아있지만 **클래스 boilerplate가 사라짐**.
5. **꼬리**: 그럼 Visitor 패턴은 어떻게 되었나요? sealed + pattern matching이 대체할 수 있나요?
   → 그렇다. Java 17 sealed + 21 pattern matching은 Visitor를 **거의 완전히 대체**. ADT + exhaustive matching이 가능해져 새 케이스 추가 시 컴파일 에러로 강제. → Visitor 패턴이 OOP의 한계를 함수형 디스패치로 보완하던 우회로였는데, 언어가 직접 지원.
6. **꼬리의 꼬리**: 그렇다면 GoF 23개 중 현재도 유효한 것과 사라진 것은?
   → **유효**: Composite (트리 구조), Adapter (외부 시스템), Facade (복잡도 숨김), Iterator (Stream의 기반), State (객체 상태 머신).
   **거의 람다로 대체**: Strategy, Command, Observer, Template Method.
   **언어 기능으로 흡수**: Visitor (pattern matching), Singleton (enum 또는 DI Container).
   **여전히 필요하지만 주의**: Factory Method, Builder (Record/Kotlin data class가 일부 대체).

## 다음 챕터로

- [08-inheritance-vs-composition](../08-inheritance-vs-composition/) — 상속의 함정
