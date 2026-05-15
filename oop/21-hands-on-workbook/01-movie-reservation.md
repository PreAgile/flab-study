# 21-01. 영화 예매 시스템 — 조영호 『오브젝트』 예제

> 같은 도메인을 절차/데이터/책임 분해 3가지로 비교 + 책임 기반 완성.

## 📋 요구사항

영화관에서 영화 예매:
- 영화 가격은 시간/요일/회차에 따라 할인.
- 할인 정책: 금액 할인, 비율 할인.
- 할인 조건: 시간대 (10:00~11:00은 10% off), 회차 (10번째 상영은 5,000원 off), 요일 (월 50% off).
- 한 영화는 한 종류의 할인만 적용.

## 🏗️ 책임 기반 모델링

### CRC 카드

```
Class: Movie
Responsibility:
 • 기본 가격 보유
 • 할인 정책 적용
Collaborators:
 • DiscountPolicy

Class: Screening (상영 일정)
Responsibility:
 • 영화 + 상영 시작 시각 + 회차
 • 가격 계산 (Movie + 조건)
Collaborators:
 • Movie, DiscountPolicy

Class: DiscountPolicy (할인 정책)
Responsibility:
 • Screening 받아 할인 금액 계산
Collaborators:
 • DiscountCondition

Class: DiscountCondition (할인 조건)
Responsibility:
 • Screening이 조건 만족하는지 판단
```

### 코드

```java
class Movie {
    private String title;
    private Money fee;
    private DiscountPolicy discountPolicy;
    
    public Money calculateFee(Screening screening) {
        return fee.minus(discountPolicy.calculateDiscount(screening));
    }
}

interface DiscountPolicy {
    Money calculateDiscount(Screening screening);
}

class AmountDiscountPolicy implements DiscountPolicy {
    private Money discountAmount;
    private List<DiscountCondition> conditions;
    
    public Money calculateDiscount(Screening screening) {
        for (DiscountCondition c : conditions) {
            if (c.isSatisfiedBy(screening)) return discountAmount;
        }
        return Money.ZERO;
    }
}

class PercentDiscountPolicy implements DiscountPolicy {
    private double percent;
    private List<DiscountCondition> conditions;
    
    public Money calculateDiscount(Screening screening) {
        for (DiscountCondition c : conditions) {
            if (c.isSatisfiedBy(screening)) {
                return screening.getMovieFee().times(percent);
            }
        }
        return Money.ZERO;
    }
}

interface DiscountCondition {
    boolean isSatisfiedBy(Screening screening);
}

class SequenceCondition implements DiscountCondition {
    private int sequence;
    public boolean isSatisfiedBy(Screening s) {
        return s.getSequence() == sequence;
    }
}

class PeriodCondition implements DiscountCondition {
    private DayOfWeek dayOfWeek;
    private LocalTime startTime;
    private LocalTime endTime;
    
    public boolean isSatisfiedBy(Screening s) {
        return s.getStart().getDayOfWeek() == dayOfWeek &&
               s.getStart().toLocalTime().compareTo(startTime) >= 0 &&
               s.getStart().toLocalTime().compareTo(endTime) <= 0;
    }
}

class Screening {
    private Movie movie;
    private int sequence;
    private LocalDateTime start;
    
    public Money getFee() {
        return movie.calculateFee(this);
    }
    public Money getMovieFee() { return movie.getFee(); }
    public int getSequence() { return sequence; }
    public LocalDateTime getStart() { return start; }
}

class Customer {
    public Reservation reserve(Screening screening) {
        Money fee = screening.getFee();
        return new Reservation(screening, fee);
    }
}
```

### 새 할인 정책 추가 — OCP 검증

요구: "공휴일에 30% 할인" 추가.

```java
class HolidayCondition implements DiscountCondition {
    private List<LocalDate> holidays;
    public boolean isSatisfiedBy(Screening s) {
        return holidays.contains(s.getStart().toLocalDate());
    }
}
```

기존 코드 변경 0. 새 condition만 추가.

## 📊 절차 분해와 비교

### 절차 분해 버전

```java
class MovieReservationSystem {
    public Money calculateFee(Movie movie, Screening screening) {
        Money fee = movie.getFee();
        Money discount = Money.ZERO;
        
        if (movie.getDiscountType() == AMOUNT) {
            if (isSequenceCondition(screening, movie) || isPeriodCondition(screening, movie)) {
                discount = movie.getDiscountAmount();
            }
        } else if (movie.getDiscountType() == PERCENT) {
            if (isSequenceCondition(screening, movie) || isPeriodCondition(screening, movie)) {
                discount = fee.times(movie.getDiscountPercent());
            }
        }
        
        return fee.minus(discount);
    }
    
    private boolean isSequenceCondition(Screening s, Movie m) { ... }
    private boolean isPeriodCondition(Screening s, Movie m) { ... }
}
```

→ 새 할인 종류 추가 = if-else 추가. OCP 위반.

## ⚔️ 학습 포인트

1. **책임 기반 분해의 OCP 효과**: 새 종류 추가 = 새 구현체. 기존 코드 변경 0.
2. **다형성**: DiscountPolicy, DiscountCondition.
3. **합성**: Movie has-a DiscountPolicy. Policy has-a Conditions.
4. **응집도**: 각 클래스가 자기 책임만.
5. **결합도**: 인터페이스 통한 의존.

## 🔗 다음

- 조영호 『오브젝트』의 다른 예제 (요금제 청구 시스템 등)도 같은 방식으로 모델링 연습.
- → [22. Tradeoff Master Table](../22-tradeoff-master-table/)
