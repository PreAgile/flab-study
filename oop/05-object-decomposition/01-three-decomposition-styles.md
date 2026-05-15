# 05-01. 세 가지 분해 방식 — 절차 / 데이터 / 책임

> 같은 시스템을 세 방식으로 분해 가능. **책임 기반**이 변경에 가장 강함.

## 📍 학습 목표

1. **절차 분해** — 큰 함수를 작은 함수로.
2. **데이터 분해** — 데이터 구조 중심.
3. **책임 분해** — 객체에 책임 할당 (OOP).
4. 같은 도메인 (ATM)을 3가지로 분해 비교.

## 🛠️ ATM 시스템 — 3가지 분해

### ① 절차 분해 (Functional Decomposition)

```java
class ATM {
    public void execute() {
        Card card = readCard();
        if (!authenticate(card)) return;
        int amount = readAmount();
        if (!checkBalance(card, amount)) return;
        dispenseCash(amount);
        updateBalance(card, amount);
        printReceipt(card, amount);
    }
    
    private Card readCard() { ... }
    private boolean authenticate(Card c) { ... }
    private int readAmount() { ... }
    // ...
}
```

문제:
- 모든 책임이 ATM 한 클래스.
- 새 기능 (다국어, 다른 카드 종류) 추가 시 ATM 수정.
- 테스트 어려움 (의존성 모두 ATM 내부).

### ② 데이터 분해 (Data-centric)

```java
class Card {
    String number;
    String pin;
    int balance;
}

class ATM {
    Card readCard() { ... }
    boolean authenticate(Card c) { return c.pin.equals(input); }
    boolean checkBalance(Card c, int amount) { return c.balance >= amount; }
    void deduct(Card c, int amount) { c.balance -= amount; }
}
```

문제:
- Card는 데이터 컨테이너 (anemic).
- 행위 모두 ATM에.
- Card 자체의 invariant 강제 어려움.

### ③ 책임 분해 (OOP)

```java
class Card {
    private int balance;
    private String pin;
    
    public boolean authenticate(String inputPin) {
        return this.pin.equals(inputPin);
    }
    
    public boolean canWithdraw(int amount) {
        return balance >= amount;
    }
    
    public void withdraw(int amount) {
        if (!canWithdraw(amount)) throw new InsufficientFundsException();
        balance -= amount;
    }
}

class CashDispenser {
    public void dispense(int amount) { ... }
}

class ReceiptPrinter {
    public void print(Card c, int amount) { ... }
}

class ATM {
    private CashDispenser dispenser;
    private ReceiptPrinter printer;
    
    public void execute() {
        Card card = readCard();
        if (!card.authenticate(input())) return;
        int amount = readAmount();
        card.withdraw(amount);     // Card가 자기 책임
        dispenser.dispense(amount); // Dispenser가 자기 책임
        printer.print(card, amount); // Printer가 자기 책임
    }
}
```

장점:
- 각 객체가 자기 책임 보유.
- 새 카드 종류 추가 = 새 Card 구현체.
- 테스트: 각 객체 독립 mock 가능.

## 📊 3가지 비교

| | 절차 분해 | 데이터 분해 | 책임 분해 |
|---|---|---|---|
| 단위 | 함수 | 데이터 구조 | 객체 |
| 행위 위치 | 외부 함수 | 외부 함수 | 객체 내부 |
| 변경 영향 | 큼 | 큼 | 격리 |
| 재사용 | 함수 단위 | 데이터 + 외부 | 객체 |
| 테스트 | 함수 단위 | 외부 의존 | 객체 단위 |
| 적합 | 작은 스크립트 | 단순 CRUD | 복잡 도메인 |

## ⚔️ 꼬리질문

### Q. CRUD app도 책임 분해해야 하나요?

> 작은 CRUD는 데이터 분해 (Entity + Service)로 OK.
> 복잡 도메인은 책임 분해 필수.
> 판단: 비즈니스 로직 복잡도가 일정 임계 이상이면 책임 분해.

### Q. (Killer) MVC가 책임 분해의 예인가요?

> 부분적으로.
> M (Model): 데이터 + 행위 (책임 분해의 시작).
> V (View): 화면 책임.
> C (Controller): 조율 책임.
> 
> 단, Anemic Domain Model이면 사실 데이터 분해.
> Rich Domain Model이어야 진짜 책임 분해.

## 🔗 다음

- → [06. Dependency Management](../06-dependency-management/)
