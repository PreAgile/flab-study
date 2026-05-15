# 05. Object Decomposition — 절차 vs 데이터 vs 객체 분해

> **이 챕터의 한 줄 목표**: 동일한 ATM 시스템을 세 가지 방식 (절차 분해 / 데이터 추상화 / 책임 기반 객체지향) 으로 분해하고, 왜 책임 기반 분해가 변경에 가장 강한지 코드로 증명할 수 있다.

## 📖 이론적 골격

| 책 / 장 | 핵심 |
|---|---|
| 조영호 『오브젝트』 7장 | 객체 분해 — 절차/데이터/책임 3가지 비교 |
| 『The Mythical Man-Month』 | 큰 시스템을 어떻게 나눌 것인가의 고전 |
| David Parnas 1972 | "정보 은닉" 논문 — 데이터 추상화의 기원 |

## 학습 목표

1. **절차 분해**의 한계 — 변경의 파급 효과 분석.
2. **데이터 추상화 (ADT)** — Java에서 흔히 보는 "OOP인 척하는 ADT" 식별.
3. **책임 기반 분해** — 진짜 OOP. 조영호식 사고.
4. 세 방식의 **변경 비용**을 정량적으로 비교.

## 파일 목록

| # | 파일 | 핵심 질문 |
|---|---|---|
| 01 | [01-procedural-decomposition.md](./01-procedural-decomposition.md) | C 스타일 함수 분해 — 코드와 한계 |
| 02 | [02-data-abstraction.md](./02-data-abstraction.md) | ADT — Java의 흔한 함정 |
| 03 | [03-object-decomposition.md](./03-object-decomposition.md) | 책임 기반 분해 — 조영호식 |
| 04 | [04-comparison-atm.md](./04-comparison-atm.md) | 동일 ATM 시스템 3방식 비교 |

## 7단 학습 레이어

### 1단. 백지 그리기

```
[그림 1] 같은 문제, 세 가지 분해
                                 영화 예매 시스템

  ── 절차 분해 ──              ── 데이터 추상화 ──            ── 책임 기반 객체지향 ──
                                                            
   main()                       MovieData                    Movie
     ├ readMovie()               ├ title                       └ calculateFee(screening)
     ├ readDiscount()             ├ basePrice                  
     ├ calculatePrice()           ├ ...                       DiscountPolicy
     ├ printReceipt()           PolicyData                     └ calculateDiscountAmount()
                                  ├ type                      
                                  ├ amount                    Reservation
                                MovieService                    └ create(customer, screening, count)
                                  ├ getMovie()                 
                                  ├ applyDiscount()            
                                  └ ...                        

   "흐름이 객체"                "데이터가 객체"                "협력이 객체"
   변경 비용: 절차 변경시 다 영향   변경 비용: 데이터 변경시 다 영향   변경 비용: 행위 변경시 해당 객체만

[그림 2] 변경 영향도 비교 (영화 예매 시스템에서 "비율 할인" 추가 시)
  방식                  영향받는 모듈 수
  절차 분해              5개 (계산 함수 + 모든 caller)
  데이터 추상화           3개 (Data 구조 + Service + caller)
  책임 기반              1개 (새 DiscountPolicy 구현체 추가)
```

### 2단. 직관

- **절차 분해**: "이 일을 어떻게 하지?" → 순서대로 단계 나열 → 각 단계가 함수.
- **데이터 추상화**: "어떤 데이터가 있지?" → 데이터 모으기 → Getter/Setter + Service.
- **책임 기반**: "누가 이 일을 해야 하지?" → 책임자 식별 → 책임자에게 메서드.

→ **결론**: 객체지향의 정수는 "흐름"이나 "데이터"가 아닌 "**책임**".

### 3단. 구조

```
절차 분해 (Functional Decomposition)
─────────────────────────────────────
- 한계: 시스템 흐름이 바뀌면 함수 트리 전부 재배치
- 사례: legacy COBOL, 초기 C 프로그램

데이터 추상화 (Abstract Data Type)
────────────────────────────────────
- 한계: 데이터 형식 변경 시 모든 사용처 영향
- 흔한 함정: Java에서 class + getter/setter만 만들고 "OOP 한다"고 착각
- 조영호: "Cargo Cult OOP" — OOP 흉내만 낸 ADT

책임 기반 객체지향 (Responsibility-Driven OOP)
──────────────────────────────────────────────
- 강점: 행위가 변경되어도 해당 객체 내부만 수정 (캡슐화)
- 새 행위 종류 추가는 새 구현체 추가 (OCP)
- 단점: 학습 곡선 + 초기 모델링 비용
```

### 4단. 내부 구현 — 동일한 "가격 계산" 코드 세 가지 버전

```java
// === 1) 절차 분해 ===
public class PriceCalculator {
    public static long calculate(String type, long base, long discount) {
        if (type.equals("AMOUNT")) return base - discount;
        if (type.equals("PERCENT")) return base * (100 - discount) / 100;
        return base;
    }
}
// 변경: 새 정책 추가 → if 분기 추가 (모든 caller에 영향 없음, but 응집도 ↓)

// === 2) 데이터 추상화 (Anemic Domain) ===
public class Movie {
    private long basePrice;
    private DiscountType type;
    private long discountValue;
    // 모든 필드 getter/setter
}
public class MovieService {
    public long calculate(Movie movie) {
        // 위와 동일한 분기 로직, 단지 데이터를 객체에서 꺼냄
    }
}
// 변경: 새 정책 추가 → Service의 분기 + Movie 필드 추가

// === 3) 책임 기반 (조영호식) ===
public class Movie {
    private Money basePrice;
    private DiscountPolicy policy;

    public Money calculateFee(Screening screening) {
        return basePrice.minus(policy.calculateDiscountAmount(screening));
    }
}
public interface DiscountPolicy {
    Money calculateDiscountAmount(Screening screening);
}
// 변경: 새 정책 추가 → 새 구현체 클래스 1개. Movie 변경 X.
```

### 5단. 역사

- **1972 David Parnas**: "On the Criteria To Be Used in Decomposing Systems into Modules" — 정보 은닉이 분해 기준.
- **1980s Wirfs-Brock**: 책임 주도 설계 (RDD).
- **1994 GoF**: Strategy 패턴 — 절차의 분기를 객체 다형성으로 풀어내는 표준.
- **2010s DDD 확산**: Aggregate 단위 분해.

### 6단. 트레이드오프

| 분해 방식 | 적합한 상황 | 부적합한 상황 |
|---|---|---|
| **절차 분해** | 1회성 스크립트, 데이터 변환 파이프라인 | 도메인 복잡, 장기 유지보수 |
| **데이터 추상화** | 단순 CRUD, DTO/API 응답 매핑 | 비즈니스 규칙이 많은 도메인 |
| **책임 기반** | 복잡한 도메인, 빈번한 요구사항 변경 | 1회성 스크립트, 데이터 변환만 |

→ **현실**: 한 시스템 안에 셋 다 공존. 도메인 계층은 책임 기반, DTO 계층은 ADT, 데이터 변환은 절차 분해 (Stream).

### 7단. 운영 진단

- **"OOP인 척하는 ADT" 진단**:
  - 도메인 클래스에 비즈니스 메서드 없음
  - 모든 메서드가 `getX()`, `setX()`
  - Service에 거대한 if/switch 분기 → 진짜 도메인 로직이 거기에 있음
  - → 해결: 분기를 다형성으로 (Strategy 패턴 또는 sealed + pattern matching)
- **God Service 진단**:
  - `OrderService`에 메서드 30개 이상 → 사실은 여러 객체의 책임이 모임
  - → 추출: Order 자신의 책임, OrderItem 책임, OrderPaymentPolicy 책임 등으로 분해

## 꼬리질문

### Junior
1. **Q**: 클래스를 만들면 객체지향 아닌가요?
   → No. 클래스 + getter/setter만 있으면 데이터 추상화(ADT)이지 객체지향이 아니다. 책임 + 행위가 있어야 OOP.

### Senior
2. **Q**: 그럼 JPA Entity가 데이터 매핑인데, 진짜 OOP가 가능한가요?
   → 가능. JPA Entity에 비즈니스 메서드를 두면 됨. `@Entity` Order 클래스 안에 `cancel()`, `addItem()` 메서드. 다만 영속성 관심사와 도메인 관심사 분리가 어려워 DDD의 "POJO Domain + Persistence Adapter" 패턴 권장.
3. **꼬리**: Spring `@Service`는 본질적으로 절차 분해를 강제하는 구조 아닌가요?
   → 부분적으로 맞다. `@Service` 메서드가 절차의 단위가 되기 쉽다. 해결: Service는 **얇게** (조율만), 도메인 행위는 도메인 객체에. "Service는 trigger, Domain은 logic".

### Principal
4. **Q**: 함수형 패러다임에서는 객체 분해 대신 무엇이 분해 단위인가요?
   → **함수 합성**. `pipe(parse, validate, calculate, persist)` 같은 작은 함수들의 합성. 데이터는 불변, 변환만 일어남. → 사실 책임 기반 OOP와 함수형 합성은 **같은 모듈성 추구**의 다른 표현.

## 다음 챕터로

- [06-dependency-management](../06-dependency-management/) — DIP, DI, IoC
