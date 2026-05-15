# 07-01. SOLID 5원칙 — 변경 종류별 매핑

> SOLID는 5개의 별도 원칙이 아니라 **변경 종류별 대응 전략**.

## 📍 5 원칙 + 변경 매핑

### ① SRP (Single Responsibility Principle)

> "변경의 이유 1개 = 클래스 1개".

**변경 종류**: 비즈니스 책임의 변경.

```java
// Bad: 2가지 이유로 변경 가능
class User {
    void save();           // DB 변경 시 수정
    void validateEmail();   // 검증 규칙 변경 시 수정
}

// Good
class User { /* 도메인 */ }
class UserRepository { void save(); }
class EmailValidator { void validate(); }
```

### ② OCP (Open-Closed Principle)

> "확장에 열려있고, 변경에 닫혀있어야".

**변경 종류**: 새 종류 추가.

```java
// Bad — 새 종류 추가 시 기존 코드 수정
class PaymentProcessor {
    void process(Payment p) {
        if (p.type == CARD) processCard(p);
        else if (p.type == PAYPAL) processPaypal(p);
        else if (p.type == STRIPE) processStripe(p);    // ← 매번 if 추가
    }
}

// Good — 새 구현체 추가만
interface PaymentMethod { void process(Payment p); }
class CardPayment implements PaymentMethod { ... }
class PaypalPayment implements PaymentMethod { ... }
class StripePayment implements PaymentMethod { ... }   // ← 추가
// PaymentProcessor 변경 없음
```

### ③ LSP (Liskov Substitution Principle)

> "Subtype은 supertype을 대체 가능".

**변경 종류**: 상속 관계의 함정.

```java
// Bad — Square is-not-a Rectangle (LSP 위반)
class Rectangle {
    void setWidth(int w);
    void setHeight(int h);
}
class Square extends Rectangle {
    void setWidth(int w) { super.setWidth(w); super.setHeight(w); }
    // ← Rectangle의 invariant 위반 (w, h 독립 변경)
}

Rectangle r = new Square();
r.setWidth(5); r.setHeight(10);
assert r.getWidth() == 5;   // ★ Square이면 실패
```

### ④ ISP (Interface Segregation Principle)

> "큰 인터페이스보다 작은 여러 개".

**변경 종류**: 클라이언트별 다른 요구사항.

```java
// Bad — 큰 인터페이스
interface Worker {
    void work();
    void eat();      // robot worker는 불필요
    void sleep();    // robot worker는 불필요
}

// Good — 분리
interface Workable { void work(); }
interface Eatable { void eat(); }
interface Sleepable { void sleep(); }
class Human implements Workable, Eatable, Sleepable { ... }
class Robot implements Workable { ... }
```

### ⑤ DIP (Dependency Inversion Principle)

> "추상에 의존, 구체에 의존 X".

[Chapter 06](../06-dependency-management/) 참조.

## 📊 변경 종류 매트릭스

| 변경 종류 | 대응 원칙 |
|---|---|
| 비즈니스 책임 변경 | SRP |
| 새 종류 추가 (결제, 알림 등) | OCP + Polymorphism |
| 상속 함정 | LSP (또는 composition) |
| 클라이언트별 요구사항 | ISP |
| 외부 시스템 변경 (DB, API) | DIP |

## ⚔️ 꼬리질문

### Q. SOLID 5원칙 중 가장 중요한 것은?

> 컨텍스트별:
> - 작은 시스템: SRP가 가장 직관적.
> - 확장성 중요: OCP.
> - 외부 의존성 많음: DIP.
> - 일반: **OCP + DIP** 가 가장 가치 큼 — 변경 격리.

### Q. SOLID와 KISS의 충돌?

> 둘이 충돌하면 KISS 우선.
> SOLID 적용은 비용 — 인터페이스, 추가 클래스.
> 작은 시스템에 무리하게 적용하면 over-engineering.
> 판단: "이 변경이 정말 일어날 가능성?"

## 🔗 다음

- → [08. Inheritance vs Composition](../08-inheritance-vs-composition/)
