# 04. Message & Interface — Tell Don't Ask, Demeter 법칙

> **이 챕터의 한 줄 목표**: `getter` chain을 보면 즉시 코드 냄새를 느끼고, "객체에게 묻지 말고 시켜라"가 왜 절대 원칙인지 한 줄 코드 비교로 보일 수 있다.

## 📖 이론적 골격

| 책 | 핵심 |
|---|---|
| 조영호 『오브젝트』 6장 | 메시지와 인터페이스 |
| Andy Hunt 『Pragmatic Programmer』 | Tell Don't Ask 원형 |
| Karl Lieberherr 1987 | Law of Demeter 논문 |
| Effective Java 22조 | 인터페이스는 타입을 정의하는 용도 |

## 학습 목표

1. **Tell Don't Ask**가 OOP의 진짜 핵심임을 코드로 보일 수 있다.
2. **디미터 법칙**의 4가지 허용 대상을 외운다.
3. **getter chain (a.getB().getC().doSomething())** 이 왜 안티패턴인지 즉시 진단.
4. **좋은 인터페이스의 6대 특성**을 안다 (의도를 드러냄, 사용 쉬움 등).
5. **명령-쿼리 분리 원칙 (CQS)** 와 그 진화 (CQRS).

## 파일 목록

| # | 파일 | 핵심 질문 |
|---|---|---|
| 01 | [01-tell-dont-ask.md](./01-tell-dont-ask.md) | "묻지 말고 시켜라" — Anemic Domain 해독제 |
| 02 | [02-law-of-demeter.md](./02-law-of-demeter.md) | 한 점만 허용 (one dot rule) |
| 03 | [03-interface-design.md](./03-interface-design.md) | 좋은 인터페이스의 6대 특성 |
| 04 | [04-command-query-separation.md](./04-command-query-separation.md) | CQS → CQRS 진화 |

## 7단 학습 레이어

### 1단. 백지 그리기

```
[그림 1] Ask vs Tell
        ── Ask (안티패턴) ──                  ── Tell (좋은 패턴) ──
        if (account.getBalance() >= amount) { account.withdraw(amount);
            account.setBalance(                  // Account 내부에서 검증+차감
                account.getBalance() - amount);
        }                                        // 한 메서드로 통합

        외부가 도메인 규칙을 안다 ✗            외부는 "출금해줘"만 안다 ✓
        Account 변경 시 외부도 변경 ✗          Account 안에서 변경 가능 ✓

[그림 2] Demeter 법칙 — 한 점만 허용
        ✗ 위반: order.getCustomer().getAddress().getCity()
                            └──────┴───────┴── 점 3개

        ✓ 준수: order.getDeliveryCity()
                     // Order가 알아서 위임 또는 보유

        허용 대상 4가지 (메서드 m 안에서):
        1. m이 속한 객체 자신 (this)
        2. m의 파라미터로 들어온 객체
        3. m 안에서 생성한 객체
        4. this의 직접 인스턴스 필드인 객체

[그림 3] 명령(Command) vs 쿼리(Query)
        Command: 상태 변경, void
        - account.withdraw(amount)
        - cart.addItem(product)

        Query: 상태 조회, 값 반환
        - account.getBalance() : long
        - cart.getTotalPrice() : Money

        같은 메서드가 둘 다 하면? 안티패턴
        예: long withdraw(amount) { ... return newBalance; }
            → "출금"인가 "잔액 조회"인가 모호
```

### 2단. 직관

- **Tell Don't Ask 한 줄**: "객체를 자판기처럼 다루지 말고 동료처럼 다뤄라." 데이터 빼서 처리하지 말고, "이거 해줘"라고 부탁.
- **Demeter 한 줄**: "친구의 친구를 직접 만지지 마라." 친구에게 부탁해서 처리.
- **CQS 한 줄**: "묻는 메서드와 시키는 메서드를 섞지 마라."

### 3단. 구조 — getter chain 위반 진단

```
[증상]
order.getCustomer().getAddress().getZipCode().equals("12345")

[냄새]
- Order, Customer, Address, ZipCode 4개 객체 노출
- 4개 중 어디 하나 바뀌면 호출처 변경
- 결합도 N개 폭발
- 캡슐화는 전부 깨짐 (Order는 내부 구조 다 노출)

[처방 1] 위임으로 점 하나로
order.getCustomerZipCode().equals("12345")
↓
order.hasCustomerInZipCode("12345")  // 더 좋음

[처방 2] 책임 이양
order.deliverableTo("12345")  // Order가 판단

[처방 3] 정말 ZipCode 비교가 필요하면 ZipCode 객체로 캡슐화
order.customerZipCode().matches("12345")  // VO 도입
```

### 4단. 내부 구현 — 좋은 인터페이스의 6대 특성

조영호 + Effective Java + Kent Beck의 종합:

| 특성 | 의미 | 위반 예 |
|---|---|---|
| **의도를 드러냄** | 메서드 이름이 무엇을 하는지 명확 | `process(order)`, `handle()` |
| **사용 쉬움** | 클라이언트가 적은 단계로 목적 달성 | builder 강제, 5단계 초기화 |
| **오용 어려움** | 잘못 쓰면 컴파일 에러 또는 런타임 즉시 실패 | int 두 개 받는 메서드 (순서 헷갈림) → VO로 |
| **충분히 풍부** | 필요한 기능 모두 노출 | API 호출 5번 해야 한 가지 기능 완성 |
| **최소 노출** | 필요 없는 것은 숨김 | List 반환하면 ArrayList 메서드까지 노출 → Collection |
| **추상화 수준 일관** | 한 인터페이스에 서로 다른 추상화 레벨 섞지 않음 | DAO와 Domain Service 메서드 혼재 |

### 5단. 역사

- **1987 Karl Lieberherr (Northeastern University)**: "Law of Demeter" 논문. 원래 Demeter 프로젝트의 일부 (그리스 추수의 여신, 모듈성 강조).
- **1990s Eiffel + Bertrand Meyer**: CQS 명문화. "Command-Query Separation".
- **1999 Andy Hunt 『Pragmatic Programmer』**: "Tell, Don't Ask" 슬로건화.
- **2003 Greg Young**: CQS → CQRS (Command Query Responsibility Segregation). 한 객체가 두 책임을 갖지 말고, 명령 모델과 쿼리 모델을 분리.
- **2019 조영호 오브젝트 6장**: 인터페이스 설계의 한국어 결정판.

### 6단. 트레이드오프 — Tell vs Ask, 언제 Ask가 정당한가

| 상황 | 권장 | 이유 |
|---|---|---|
| 도메인 행위 (출금, 예매, 취소) | **Tell** | 검증/규칙이 도메인 객체에 있어야 |
| UI에 표시할 데이터 추출 | **Ask 허용** | Display는 Query, 도메인 무관 |
| 외부 API 응답 매핑 | **Ask 허용** | DTO는 본질적으로 데이터 컨테이너 |
| 영속성 (JPA Entity Mapping) | **Ask 허용 (필드 수준)** | ORM이 reflection으로 접근 |
| 비즈니스 규칙 검증 | **Tell** | 규칙은 도메인 객체의 책임 |

→ **결론**: 도메인 객체는 Tell, DTO/View Model은 Ask 허용.

### 7단. 운영 진단

(20-ops-scenarios에서 풀버전)

- **getter chain 정규식 진단**: `\\.\\get\\w+\\(\\).get\\w+\\(\\)` grep으로 검출.
- **Service 비대화 진단**: Service 메서드 길이 > 30줄 + getter 호출 > 5회 → 도메인 메서드로 추출 후보.
- **JPA Lazy Loading 함정**: Tell Don't Ask를 적용하면 lazy loading 호출 시점이 도메인 객체 안 → `LazyInitializationException` 위험 → fetch join 또는 DTO projection 필요.

## 꼬리질문 (Junior → Senior → Principal)

### Junior 레벨
1. **Q**: Tell Don't Ask 원칙이 뭔가요?
   → 객체에게 데이터를 묻지 말고 일을 시켜라.
2. **꼬리**: 그럼 모든 getter를 없애야 하나요?
   → No. 도메인 행위가 아닌 단순 조회(UI 표시 등)는 getter가 필요. 핵심은 **비즈니스 규칙**을 외부에서 계산하지 말 것.

### Senior 레벨
3. **Q**: Demeter 법칙이 빌더 패턴이나 Fluent API에는 어떻게 적용되나요?
   → `Stream.of(1,2,3).filter(...).map(...).collect(...)`처럼 점이 여러 개여도 위반이 아니다. **빌더의 반환 객체는 같은 타입** (this 반환) → 한 객체와의 대화. Demeter 위반은 "**다른 객체의 다른 객체**"에 접근할 때.
4. **꼬리**: 그럼 JPA QueryDSL의 `select(qOrder).from(qOrder).join(qOrder.customer)...`도 괜찮은가요?
   → DSL이라는 특수 컨텍스트에서는 OK. 단, **도메인 로직 영역**에서는 안 됨. 영속성 영역에 한정.
5. **꼬리의 꼬리**: CQRS를 도입하면 Tell Don't Ask가 어떻게 변하나요?
   → Command 측은 Tell 엄격 적용 (집합체에 일을 시킨다). Query 측은 ReadModel/Projection에서 **자유로운 데이터 노출 허용** (View 전용). 두 모델이 분리되어 있어서 충돌 없음.

### Principal 레벨
6. **Q**: Hexagonal Architecture에서 Port/Adapter 패턴이 Tell Don't Ask와 어떻게 연결되나요?
   → Port는 **도메인이 외부에게 명령하는 인터페이스**. 도메인이 "OutboundPort에게 일을 시킨다" → Adapter가 실제 외부 시스템과 통신. 도메인이 외부에 묻지 않음 (Pull 모델 X). → Tell Don't Ask의 아키텍처 레벨 적용.
7. **꼬리**: 그럼 도메인 객체에서 비동기 이벤트를 발행할 때 Tell이 어떻게 되나요?
   → Domain Event 패턴. `order.cancel()` 안에서 `DomainEvents.raise(new OrderCancelled(...))`. 호출자는 이벤트를 누가 받는지 모름 → 의존 역전 + Tell 유지. Spring `ApplicationEventPublisher` 또는 메시지큐로 비동기화.
8. **꼬리의 꼬리**: 이벤트 발행이 트랜잭션 안에서 발생할 때 발행 실패하면? Tell이 깨지나요?
   → Transactional Outbox 패턴. 이벤트를 같은 트랜잭션의 outbox 테이블에 INSERT → 별도 publisher가 outbox를 읽어 발행. 도메인은 여전히 Tell, 신뢰성은 인프라가 책임. → Tell Don't Ask와 분산 시스템 신뢰성의 결합 지점.

## 다음 챕터로

- [05-object-decomposition](../05-object-decomposition/) — 절차/데이터/객체 분해 비교
