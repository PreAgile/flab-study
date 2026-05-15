# 08-01. 상속보다 합성을 — Effective Java 18조

> 코드 재사용 ≠ 상속.
> 상속은 강한 결합 + Fragile Base Class 함정.

## 📍 학습 목표

1. **Fragile Base Class** 문제.
2. **Composition + Forwarding** 패턴.
3. **상속이 정당한 경우** — is-a + 같은 invariant.
4. Java/Kotlin/Scala의 mixin/trait/delegation 비교.

## 💥 Fragile Base Class

```java
// 1.0
class Account {
    private int balance;
    public void deposit(int amount) {
        balance += amount;
    }
}

class LoggingAccount extends Account {
    public void deposit(int amount) {
        log(amount);
        super.deposit(amount);
    }
}

// 2.0 — 라이브러리가 Account 변경
class Account {
    public void deposit(int amount) {
        deposit2(amount);  // ← 내부 함수로 위임
    }
    public void deposit2(int amount) {   // ★ 추가됨
        balance += amount;
    }
}

// 결과: LoggingAccount는 log() 한 번만 (이제 super.deposit이 deposit2 호출)
// → 부모 변경이 자식 동작 깨뜨림
```

→ "Fragile Base Class" 문제. 부모 변경이 자식에 예측 못 한 영향.

## ✅ Composition + Forwarding

```java
// 합성 + 위임
class LoggingAccount {
    private final Account account;   // 합성
    
    public LoggingAccount(Account account) {
        this.account = account;
    }
    
    public void deposit(int amount) {
        log(amount);
        account.deposit(amount);   // 위임
    }
    
    public int balance() {
        return account.balance();
    }
}
```

장점:
- Account 내부 변경이 LoggingAccount에 영향 없음.
- Account가 final이어도 LoggingAccount 가능.
- LSP 위반 위험 없음.

## 📊 상속이 정당한 경우

```java
// "is-a" + 같은 invariant
class Animal { void breathe(); }
class Dog extends Animal { void bark(); }
// Dog is-a Animal. invariant 공유.
```

조건:
1. **is-a 관계 성립**.
2. **부모의 모든 invariant를 자식이 유지**.
3. **부모 변경이 자식에 영향 없도록 설계** (final 메서드, Template Method 패턴).

대부분의 코드 재사용은 이 조건 만족 안 함 → 합성.

## 🌐 언어별 비교

### Java
- Single inheritance.
- Interface (multiple).
- Default method (Java 8+) — 약한 mixin.

### Kotlin
- Single inheritance.
- Interface + default method.
- **Delegation by `by` keyword**:
```kotlin
class LoggingAccount(account: Account) : Account by account {
    override fun deposit(amount: Int) {
        log(amount)
        account.deposit(amount)
    }
}
```

### Scala
- **Trait** — mixin (multiple).
- Linearization 규칙.
```scala
trait Logging { def log(msg: String) }
trait Account { def deposit(amount: Int) }
class LoggingAccount extends Account with Logging
```

## ⚔️ 꼬리질문

### Q. 모든 상속은 나쁜가요?

> 아니. is-a + 같은 invariant + 부모가 상속 위해 설계되었으면 OK.
> Java의 Exception, Java의 collection 계층 (List, AbstractList, ArrayList) 등은 정당한 상속.

### Q. (Killer) Java 8 Default Method는 mixin인가요?

> 부분적으로 yes.
> Interface가 메서드 구현 가짐 → 다중 상속 효과.
> 단:
> - State 못 가짐 (필드 없음).
> - 충돌 시 explicit override 필수.
> 
> 진짜 mixin (Scala trait)는 state까지 — 더 강력.

## 🔗 다음

- → [09. Functional Paradigm](../09-functional-paradigm/)
