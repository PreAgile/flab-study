# 02-01. Encapsulation의 진짜 의미 — 데이터 은닉이 아니라 변경 캡슐화

> "캡슐화 = private 필드"는 절반의 답.
> 본질은 **변경의 캡슐화** — 한 곳의 변경이 다른 곳에 전파되지 않도록 경계를 두는 것.

## 📍 학습 목표

1. **Abstraction** — 본질만 추출.
2. **Encapsulation** — 변경의 캡슐화.
3. **Polymorphism** — 같은 메시지, 다른 응답. JVM의 `invokevirtual` 구현.
4. **Inheritance** — is-a 관계. 단, "상속보다 합성을".
5. **4대 기둥의 실제 적용**.

## 🧠 Abstraction — 본질만

```java
// Bad: 구현 detail이 인터페이스에
interface Stack {
    void push(int x);
    int pop();
    int getTopIndex();      // ← 구현 detail
    int[] getInternalArray();  // ← 구현 detail
}

// Good: 본질만
interface Stack {
    void push(int x);
    int pop();
    boolean isEmpty();
}
```

추상화의 정도:
- **너무 추상**: `Object`처럼 모든 것 표현 가능 — 정보 부족.
- **너무 구체**: 구현 detail 노출 — 변경 전파.
- **적정**: 본질적 메시지만 (3~7개 메서드).

## 🔒 Encapsulation — 변경의 캡슐화

### 통념: "private 필드"

```java
class Account {
    private int balance;
    
    public int getBalance() { return balance; }
    public void setBalance(int b) { balance = b; }
}
```

→ getter/setter 있으면 사실상 public. 이건 캡슐화 아님.

### 진짜 캡슐화: 행위 위주

```java
class Account {
    private int balance;
    
    public void deposit(int amount) {
        if (amount <= 0) throw new IllegalArgumentException();
        balance += amount;
    }
    
    public void withdraw(int amount) {
        if (amount <= 0 || amount > balance) throw new IllegalArgumentException();
        balance -= amount;
    }
    
    public int balance() { return balance; }   // read-only 노출 OK
}
```

특징:
- `balance` 직접 set 못 함.
- `deposit`/`withdraw`만 노출 → invariant (잔액 ≥ 0) 강제.
- balance 표현 변경 (int → long → BigDecimal)이 외부 영향 없음.

### 변경의 캡슐화 = 인터페이스 안정성

```java
// 변경 전
class Account {
    private int balance;  // int
    public int balance() { return balance; }
}

// 변경 후 — 외부 코드는 그대로
class Account {
    private BigDecimal balance;  // BigDecimal로 변경
    public int balance() { return balance.intValue(); }
}
```

→ 내부 구현 변경이 인터페이스에 영향 안 줌 = 캡슐화 성공.

## 🎭 Polymorphism — JVM 구현

### Subtype Polymorphism (가장 흔함)

```java
Animal a = new Dog();
a.makeSound();   // "멍" (Dog의 메서드)

a = new Cat();
a.makeSound();   // "야옹"
```

JVM 구현:
- `invokevirtual` bytecode.
- vtable lookup (Klass의 가상 메서드 테이블).
- Inline Cache 최적화 (Chapter 03-05 JVM 참조).
- Monomorphic call site는 사실상 직접 호출 수준 빠름.

### Parametric Polymorphism (Generics)

```java
List<String> strs = new ArrayList<>();
List<Integer> ints = new ArrayList<>();
```

JVM 구현: erasure — 런타임에 type 정보 사라짐. Signature attribute에만 남음 (Chapter 01-01 JVM 참조).

### Ad-hoc Polymorphism (Operator overloading)

Java는 없음. Kotlin/C++/Scala는 있음.

## 🌳 Inheritance — 함정과 한계

### 잘못된 사용: 코드 재사용

```java
class Stack<T> extends ArrayList<T> {   // ← LSP 위반
    void push(T x) { add(x); }
    T pop() { return remove(size() - 1); }
}

Stack<Integer> s = new Stack<>();
s.add(0, 42);   // ← ArrayList API 노출 — push가 아닌데 가능
```

→ "Stack is-a ArrayList"가 진짜 아님 (LSP 위반).

### 올바른 사용: is-a + 같은 invariant

```java
class Animal { ... }
class Dog extends Animal { ... }   // Dog is-a Animal — OK
```

### 권장: 합성

```java
class Stack<T> {
    private final ArrayList<T> internal = new ArrayList<>();
    
    public void push(T x) { internal.add(x); }
    public T pop() { return internal.remove(internal.size() - 1); }
    // ArrayList API 노출 안 함
}
```

Effective Java 18조: "상속보다 컴포지션을". 자세히는 [Chapter 08](../08-inheritance-vs-composition/).

## 🛠️ 운영 관점

### Anemic Domain의 신호

```java
// 모든 필드가 public getter/setter
class Order {
    public Long id;
    public String status;
    public List<OrderLine> lines;
    public BigDecimal total;
    public LocalDateTime createdAt;
    // ... 30개 getter/setter
}
```

→ 절차지향 모드. Service에 모든 로직.

조치:
- 행위를 Order로 이동 (`Order.checkout()`, `Order.applyDiscount()`).
- private 필드 + 행위 메서드 위주.

### 다형성을 통한 OCP

```java
// 결제 방식 추가 시 기존 코드 변경 없이
interface PaymentMethod {
    void pay(Money amount);
}
class CreditCardPayment implements PaymentMethod { ... }
class PaypalPayment implements PaymentMethod { ... }
class StripePayment implements PaymentMethod { ... }   // ← 새 추가
```

→ 새 결제 방식 추가 = 새 class만. Order, Customer 등 기존 코드 영향 0.

## ⚔️ 꼬리질문

### Q. getter/setter가 캡슐화 위반인가요?

> 항상은 아님.
> - **Read-only getter** (불변 표현): OK.
> - **Setter (modifier)**: 대부분 안티패턴 — 행위 메서드로 대체 (`deposit` vs `setBalance`).
> - DTO/Record는 데이터 컨테이너이므로 OK.

### Q. (Killer) JVM의 invokevirtual은 어떻게 다형성을 구현하나요?

> 1. 각 객체 헤더의 Klass Pointer (Chapter 02-02 JVM).
> 2. invokevirtual 시 Klass의 vtable에서 메서드 lookup.
> 3. JIT의 Inline Cache가 monomorphic 시 직접 점프 (Chapter 03-05 JVM).
> 4. 다형성 비용은 IC monomorphic 가정 시 ~0.

## 🔗 다음

- → [03. Responsibility Assignment](../03-responsibility-assignment/)
- ← [JVM Chapter 03-05 Inlining + IC](../../jvm/03-execution-engine/05-inlining-and-ic.md)
