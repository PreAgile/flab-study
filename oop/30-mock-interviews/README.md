# 30. Mock Interviews — Junior/Senior/Principal

> **이 챕터의 한 줄 목표**: 카카오/네이버/쿠팡/토스/당근의 실제 OOP 면접 질문 패턴을 시뮬레이션. 40분 안에 즉석 도메인 모델링 + 꼬리질문 3단까지 답할 수 있다.

## 학습 목표

1. **레벨별 면접 시나리오** — Junior 30분 / Senior 45분 / Principal 60분.
2. **즉석 도메인 모델링** — 40분 안에 CRC → 시퀀스 → 코드.
3. **꼬리질문 3단** 대응 — 한 답변에서 더 깊이 들어가기.
4. **시스템 설계 + OOP 통합** — MSA, DDD, 도메인 이벤트.

## 파일 목록

| # | 파일 | 레벨 |
|---|---|---|
| 01 | [01-junior-30min.md](./01-junior-30min.md) | Junior 30분 시나리오 5개 |
| 02 | [02-senior-45min.md](./02-senior-45min.md) | Senior 45분 시나리오 5개 |
| 03 | [03-principal-60min.md](./03-principal-60min.md) | Principal 60분 시나리오 5개 |
| 04 | [04-instant-domain-modeling.md](./04-instant-domain-modeling.md) | 즉석 도메인 모델링 카타 |
| 05 | [05-tail-question-handling.md](./05-tail-question-handling.md) | 꼬리질문 3단 대응법 |

## 레벨별 평가 기준

### Junior (3~5년)
- OOP 4대 기둥 정의 + 코드 예시
- SOLID 5원칙 정의
- 상속 vs 합성 차이
- 람다와 Stream 기본 사용
- Spring DI 기본
- 면접 시간: 30분

### Senior (5~10년)
- 위 +
- 즉석 도메인 모델링 (예: 도서관, 주차장, 호텔)
- 안티패턴 진단 + 리팩토링 제안
- JVM 다이내믹 디스패치
- 함수형 (모나드, 합성)
- Kotlin 트레이드오프
- 면접 시간: 45분

### Principal (10년+)
- 위 +
- 시스템 설계 (MSA, DDD)
- 아키텍처 결정 + 트레이드오프 정량 분석
- 팀 리더십 (코드 리뷰 문화, 학습 강좌)
- 미래 기술 통찰 (Loom, Data-Oriented Programming, GraalVM Native 등)
- 면접 시간: 60분

## Junior 면접 샘플 (3개)

### 시나리오 J-1: OOP 기본

**Q1**: 객체지향이 뭔가요? 절차지향과 어떻게 다른가요?
→ (기대: 자율적 객체, 메시지, 책임 + 데이터/함수 분리 vs 통합)

**꼬리**: "데이터와 메서드를 묶는 것"이라고 답하면, "그럼 C struct + 함수도 OOP인가요?" 반박.

### 시나리오 J-2: SOLID

**Q1**: SOLID 5원칙 각각 설명해주세요.
→ (기대: 5개 다 명확히)

**꼬리**: SRP의 "단일 책임"의 단위가 뭔가요? → "변경의 이유"

### 시나리오 J-3: 상속

**Q1**: 상속이 왜 위험한가요?
→ (기대: 캡슐화 위반, 강한 결합)

**꼬리**: 그럼 언제 상속을 쓰나요? → 진짜 is-a + 안정적 부모.

## Senior 면접 샘플 (3개)

### 시나리오 S-1: 즉석 도메인 모델링 — 도서관 시스템

**Q1**: 도서관 대출 시스템을 모델링해보세요. 책, 회원, 대출, 연체. 15분.
→ (기대: CRC → 객체 식별 → 책임 분배 → 인터페이스 도출)

**평가**:
- 객체 vs 클래스 구분
- Anemic 함정 회피 (도서관 Service가 모든 책임 X)
- 다형성 활용 (회원 등급별 대출 한도 등)
- 도메인 이벤트 ("연체 발생", "반납 완료") 식별

### 시나리오 S-2: 안티패턴 진단

**Q1**: 다음 코드를 보고 안티패턴 진단 + 리팩토링 제안:

```java
@Service
public class OrderService {
    @Autowired private OrderRepository orderRepo;
    @Autowired private UserRepository userRepo;
    @Autowired private PaymentService paymentService;
    @Autowired private NotificationService notificationService;
    @Autowired private InventoryService inventoryService;
    @Autowired private DiscountService discountService;

    public void processOrder(Long userId, List<Long> productIds) {
        User user = userRepo.findById(userId).get();
        List<Product> products = productIds.stream()
            .map(id -> inventoryService.getProduct(id))
            .collect(Collectors.toList());
        long total = 0;
        for (Product p : products) {
            total += p.getPrice();
        }
        if (user.getMembership().equals("VIP")) {
            total = total * 9 / 10;
        } else if (user.getMembership().equals("GOLD")) {
            total = total * 95 / 100;
        }
        Order order = new Order();
        order.setUserId(userId);
        order.setProductIds(productIds);
        order.setTotal(total);
        order.setStatus("PENDING");
        orderRepo.save(order);
        paymentService.charge(user.getCardId(), total);
        order.setStatus("PAID");
        orderRepo.save(order);
        notificationService.send(user.getEmail(), "Order processed");
    }
}
```

→ (기대 진단):
1. Anemic Domain (Order, User 빈약)
2. Feature Envy (User.getMembership 분기)
3. Spring 어노테이션 필드 주입
4. Demeter 위반 (user.getMembership().equals())
5. Magic String ("VIP", "GOLD", "PENDING")
6. 트랜잭션 누락
7. SRP 위반 (한 메서드가 검증/계산/저장/결제/알림 모두)

→ (기대 리팩토링):
1. Constructor 주입
2. User에 `Membership` 객체 + `applyDiscount(total)`
3. `Order.pay(payment)` 메서드로 캡슐화
4. `OrderStatus` enum
5. `@Transactional`
6. 결제 실패 시 보상 트랜잭션
7. 알림은 Domain Event로 분리

### 시나리오 S-3: Java vs Kotlin

**Q1**: 동일한 결제 도메인을 Java와 Kotlin으로 작성하면 무엇이 다른가요?
→ (기대: data class, sealed, null safety, copy(), DSL, Coroutine 등 6가지+)

**꼬리**: Kotlin이 모든 면에서 더 좋은데 왜 아직 Java를 쓰나요?
→ 호환성, 컴파일 속도, 산업 표준성, 팀 학습 비용.

## Principal 면접 샘플 (2개)

### 시나리오 P-1: 마이크로서비스 분할

**Q1**: 모노리스 e-커머스를 MSA로 분할하라는 요구가 왔습니다. 어떻게 시작하나요?

→ (기대):
1. **Bounded Context 식별** (DDD) — Catalog, Order, Payment, Shipping, Customer 등.
2. **Strangler Fig 패턴** — 점진적 추출. 트래픽 라우팅으로 신/구 공존.
3. **데이터 일관성 모델** — Strong consistency 필수 영역 vs Eventual consistency 허용 영역.
4. **분산 트랜잭션** — Saga 패턴 (Choreography vs Orchestration 트레이드오프).
5. **공유 데이터** — Anti-Corruption Layer + Domain Event.
6. **운영 가능성** — Circuit Breaker, Distributed Tracing, Idempotency.
7. **팀 토폴로지** — Team Topologies 패턴 (Stream-aligned, Platform, Enabling, Complicated Subsystem).

**꼬리**: Order 서비스와 Payment 서비스 사이 데이터 일관성을 어떻게 보장하나요?
→ Saga + Outbox 패턴. 또는 2PC (사용 안 권장).

**꼬리의 꼬리**: Outbox 패턴 구현 시 메시지 순서 보장이 어떻게 되나요?
→ DB에 sequence 컬럼 + 발행자 단일 thread + Kafka partition key. 또는 Debezium CDC.

### 시나리오 P-2: 미래 기술 결정

**Q1**: 신규 서비스를 시작합니다. Java 21 vs Kotlin 1.9 + Spring 6 vs Quarkus + Virtual Thread vs Coroutine. 어떻게 결정하나요?

→ (기대):
1. **팀 컨텍스트** — 기존 Java 팀이면 Java 21 + Spring. 모바일 팀과 공유면 Kotlin.
2. **시작 시간** — 컨테이너에 자주 배포되면 Quarkus + GraalVM Native (sub-second start).
3. **동시성 모델** — 도메인이 IO-bound면 Virtual Thread (Java) 또는 Coroutine (Kotlin). 둘 다 가능.
4. **에코시스템** — Spring 라이브러리 의존성 많음 → Spring + Java 21.
5. **미래 진화** — Project Valhalla (value type) 도입 시 Java 우위 가능성.

**꼬리**: Valhalla가 도입되면 record와 data class에 어떤 영향이 있나요?
→ Java record가 inline class (value type)으로 변환 가능 → 객체 헤더 + 박싱 비용 제거. Kotlin은 value class (inline class)로 이미 일부 지원, but JVM 레벨 inline은 Valhalla 필요.

## 즉석 도메인 모델링 카타 (5개)

각 15분 안에 CRC + 시퀀스 + 핵심 코드:

1. **도서관 대출 시스템** — 회원 등급, 대출 한도, 연체 페널티
2. **주차장 시스템** — 자리, 차량, 요금 계산 (시간/할인), 결제
3. **호텔 예약** — 객실 종류, 시즌 요금, 취소 정책
4. **음식 주문 배달** — 메뉴, 옵션, 배달 경로, 쿠폰
5. **컨퍼런스 일정** — 트랙, 세션, 발표자, 충돌 검증

## 꼬리질문 3단 대응법

면접관의 꼬리는 보통 다음 5가지 방향:

1. **정의 검증**: "방금 말한 X의 정확한 정의는?"
2. **반례**: "그럼 Y는 X에 해당하나요?"
3. **트레이드오프**: "그 결정의 단점은?"
4. **응용**: "실제 운영 환경에서 어떻게 적용하나요?"
5. **미래**: "기술이 진화하면 어떻게 변할까요?"

각 방향별 답변 템플릿:

```
정의 검증 → "엄밀히는 ___ 입니다. 예: ___"
반례 → "Y는 X에 해당하지 않습니다. 왜냐하면 ___. X의 핵심은 ___이고 Y는 ___."
트레이드오프 → "단점 3가지: ① ② ③. 다만 ___ 컨텍스트에서는 가치가 더 큼."
응용 → "운영 사례: ___. 진단 도구: ___. 함정: ___."
미래 → "기술 X가 안정화되면 ___. 다만 ___ 한계 여전히."
```

## 자가 평가 — README 첫 문장 풀어 말하기

이 가이드의 README 첫 문장:

> "객체지향은 자율적인 객체들이 메시지로 협력하여 책임을 분담하는 패러다임이고, 절차지향이 데이터와 프로세스를 분리하면서 발생한 의존성 폭발 문제를 캡슐화·다형성·다이내믹 디스패치로 해결했지만 가변 상태 공유라는 부작용을 남겼기에 함수형의 불변성·순수함수가 보완 패러다임으로 부상했고, Java는 람다/Stream/Record/Sealed/Pattern Matching으로 점진적 하이브리드화되었으며 Kotlin은 처음부터 불변성/널 안전성/표현식 기반 설계로 그 균형을 언어 차원에 박았다"

학습 완료 후 자가 평가:

- [ ] 위 문장을 3분 안에 자유롭게 풀어 설명할 수 있다
- [ ] 각 절(짤린 부분)이 어느 챕터와 매핑되는지 즉답 가능
- [ ] 청중 레벨에 따라 (Junior/Senior/Principal) 다른 깊이로 답변 가능
- [ ] 꼬리질문 3단 모두 대응 가능

위 4개를 모두 통과하면 **"객체지향 설계 권위자"** 수준. README 학습 목표 달성.
