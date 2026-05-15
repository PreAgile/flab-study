# 03. Responsibility Assignment — GRASP 9원칙

> **이 챕터의 한 줄 목표**: 새 도메인을 받으면 "이 책임은 누구에게 줄까"를 GRASP 9원칙으로 30초 안에 결정할 수 있다. SOLID는 결과적 규칙, GRASP는 도착하는 사고법.

## 📖 이론적 골격

| 책 | 핵심 |
|---|---|
| Craig Larman 『Applying UML and Patterns』 | GRASP 9원칙 원전 |
| 조영호 『오브젝트』 5장 | 책임 할당 — 정보 전문가 + 영화 예매 사례 |
| Rebecca Wirfs-Brock 『Object Design』 | 책임 주도 설계의 시조 |

## 학습 목표

1. **GRASP 9원칙**을 외우지 않고 **유도**할 수 있다 (각 원칙은 "응집도+결합도"에서 파생).
2. **정보 전문가 패턴**을 적용해 새 메서드의 위치를 결정.
3. **창조자 패턴**으로 `new` 위치를 결정.
4. **Anemic Domain의 함정**을 책임 누출 관점에서 진단.
5. **GRASP와 SOLID의 관계** — GRASP는 사고법, SOLID는 결과 규칙임을 설명.

## 파일 목록

| # | 파일 | 핵심 질문 |
|---|---|---|
| 01 | [01-grasp-9-principles.md](./01-grasp-9-principles.md) | 9원칙 전체 — 각각의 기원과 사용 시점 |
| 02 | [02-information-expert.md](./02-information-expert.md) | 정보 전문가 — 책임 할당의 1순위 휴리스틱 |
| 03 | [03-creator-controller.md](./03-creator-controller.md) | Creator + Controller — 생성/통제 책임 |
| 04 | [04-low-coupling-high-cohesion.md](./04-low-coupling-high-cohesion.md) | 두 메타 원칙 — 다른 7원칙의 평가 기준 |
| 05 | [05-grasp-to-solid-mapping.md](./05-grasp-to-solid-mapping.md) | GRASP가 SOLID로 어떻게 이어지나 |

## 7단 학습 레이어

### 1단. 백지 그리기 — GRASP 9원칙 한 장 정리

```
┌──────────────────────────────────────────────────────────────────────┐
│                   GRASP (책임 할당의 일반 원칙)                          │
├──────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  메타 평가 기준                                                          │
│  ┌────────────────┐  ┌────────────────┐                              │
│  │ Low Coupling   │  │ High Cohesion  │                              │
│  └────────────────┘  └────────────────┘                              │
│                                                                       │
│  구체 휴리스틱                                                           │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐       │
│  │ Information     │  │ Creator         │  │ Controller      │       │
│  │ Expert          │  │ (생성 책임)       │  │ (시스템 진입점)   │       │
│  │ "정보 가진 자에게"│  └─────────────────┘  └─────────────────┘       │
│  └─────────────────┘                                                   │
│                                                                       │
│  변경 대응 휴리스틱                                                       │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐       │
│  │ Polymorphism   │  │ Pure Fabrication│  │ Indirection    │       │
│  │ (조건분기 → 다형)│  │ (책임 없는 클래스)│  │ (중간자 도입)    │       │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘       │
│                                                                       │
│  변경 보호 휴리스틱                                                        │
│  ┌────────────────────────────────────┐                              │
│  │ Protected Variations               │                              │
│  │ (변경 지점에 안정 인터페이스)         │                              │
│  └────────────────────────────────────┘                              │
└──────────────────────────────────────────────────────────────────────┘
```

### 2단. 직관

- **GRASP 첫 질문**: "이 정보를 가진 자가 누구인가?" → 그가 책임자.
- **GRASP 두 번째 질문**: "변경이 일어날 곳은 어디인가?" → 거기에 인터페이스.
- **응집도**: 한 클래스 안에서 메서드들이 같은 일을 하는 정도.
- **결합도**: 한 클래스가 다른 클래스를 얼마나 아는 정도.
- **이상**: 응집도 ↑, 결합도 ↓.

### 3단. 구조 — 책임 할당 의사결정 트리

```
새 책임이 생겼다
        │
        ▼
[정보를 가장 많이 가진 객체가 누구?]
        │ ─ "분명함" → 그에게 할당 (Information Expert)
        │
        ▼
[그 객체에 너무 많이 모인다 (응집도 ↓)?]
        │ ─ Yes → 새 객체 만들어 분리 (Pure Fabrication)
        │
        ▼
[조건 분기로 타입별 처리?]
        │ ─ Yes → Polymorphism으로 풀어내기
        │
        ▼
[변경 자주 발생할 곳?]
        │ ─ Yes → 인터페이스로 격리 (Protected Variations)
        │
        ▼
적용 완료 → 결합도/응집도 재평가
```

### 4단. 내부 구현 (조영호 영화 예매 사례)

조영호 책의 영화 예매 시스템 책임 할당:

```
"영화 할인을 계산하라"는 책임 → 누구?

후보 1: Reservation (예매)
  - 영화/할인 정보 들고 있나? → No (영화에 위임 필요)
  - 정보 전문가 X

후보 2: Movie
  - 영화의 기본 가격 들고 있음 ✓
  - 할인 정책 들고 있음 ✓
  - 정보 전문가 ✓
  - → Movie에 calculateFee() 책임

  하지만 할인 정책이 여러 종류 (금액/비율)
  → Polymorphism으로 DiscountPolicy 인터페이스 도입

후보 3: DiscountPolicy
  - 정책별 계산 로직 들고 있음 ✓
  - 정보 전문가 (정책에 한해서) ✓
  - → calculateDiscountAmount() 책임

결론:
  Movie.calculateFee()
    └─ DiscountPolicy.calculateDiscountAmount()
        └─ DiscountCondition.isSatisfiedBy()
```

이게 조영호식 책임 분배의 결정판이다.

### 5단. 역사

- **1990 Wirfs-Brock**: 책임 주도 설계(RDD) + CRC 카드. 객체보다 책임 우선.
- **1996 Larman 1판**: 『Applying UML and Patterns』 — GRASP 9원칙 명명.
- **2000 GoF Patterns**: GRASP의 구체 패턴들.
- **2001 Robert Martin**: SOLID 5원칙 (GRASP를 단순화/규범화).
- **2019 조영호 오브젝트**: 한국어권 RDD + DDD 결합판.

### 6단. 트레이드오프 — GRASP vs SOLID

| 비교 축 | GRASP | SOLID |
|---|---|---|
| **수** | 9 | 5 |
| **성격** | 휴리스틱 (어떻게 도착할까) | 규칙 (도착 후 검증) |
| **추상도** | 구체적 (정보 전문가 등) | 추상적 (단일 책임 등) |
| **언제** | 설계 중 (책임 분배) | 리뷰 (위반 검사) |
| **저자 의도** | Larman: "선택 가능한 도구" | Martin: "지켜야 할 원칙" |

→ **결론**: 둘 다 안다. GRASP로 만들고 SOLID로 검증.

### 7단. 운영 진단

(20-ops-scenarios에서 풀버전)

- **Anemic Domain 진단 (Feature Envy)**:
  - `OrderService.cancel(order)` 안에 `order.getStatus()`, `order.setStatus()`, `order.getItems().forEach(...)` 잔뜩 → Order의 정보를 OrderService가 다 만지고 있다.
  - 정보 전문가 위반. `order.cancel()`로 책임 이양.
- **God Object 진단**:
  - 한 클래스가 7개 이상의 책임 → 응집도 ↓.
  - Pure Fabrication으로 책임을 새 클래스로 추출.
- **순환 의존 진단**:
  - A가 B 알고, B가 A 알면 결합도 ↑↑.
  - Indirection으로 중간자 도입 또는 이벤트로 풀기.

## 꼬리질문 (Junior → Senior → Principal)

### Junior 레벨
1. **Q**: 단일 책임 원칙(SRP)의 의미는?
   → 한 클래스는 한 가지 책임만 가져야 한다.
2. **꼬리**: "책임"의 단위가 뭔가요? "한 가지 일"이라는 게 너무 추상적이지 않나요?
   → Robert Martin은 "**변경의 이유**(reason to change)"로 정의. 같은 이유로 변경되는 코드는 한 클래스에. 다른 이유로 변경되는 코드는 분리. → **변경 주체(stakeholder)** 별로 분리하는 것이 실용적 기준.

### Senior 레벨
3. **Q**: 정보 전문가 원칙을 따랐는데 응집도가 너무 높아져서 한 클래스가 비대해졌습니다. 어떻게 풀까요?
   → Pure Fabrication 적용. 책임은 그대로 정보 전문가에게 두되, **수행 도구(헬퍼)** 를 별도 클래스로 추출. 예: `Order`가 가격 계산을 책임지지만, 실제 계산 로직은 `PriceCalculator`에 위임.
4. **꼬리**: 그렇다면 결과적으로 책임이 둘로 갈라진 것 아닌가요?
   → 그렇지 않다. **외부에서 본 책임**은 여전히 `Order.calculateTotal()`. 내부적으로 `PriceCalculator`에 위임할 뿐. 캡슐화 안에서 책임 분해가 일어남.
5. **꼬리의 꼬리**: 그럼 `PriceCalculator`는 Spring Bean인가요? Domain Service인가요?
   → 도메인 로직이라면 **Domain Service** (POJO, Spring 무관). 외부 시스템 호출이 필요하면 **Application Service**. 구분 기준: 도메인 어휘에 등장하는 개념인가, 기술적 어댑터인가.

### Principal 레벨
6. **Q**: GRASP의 Protected Variations와 OCP의 차이는?
   → Larman의 PV는 "변경 가능한 부분을 안정적 인터페이스로 감싼다" — 추상화 도구 (Adapter, Strategy 등). OCP는 결과 — "확장에 열려있고 수정에 닫혀있다". PV는 **방법**, OCP는 **상태**.
7. **꼬리**: 그럼 모든 변경 지점에 인터페이스를 두는 것이 좋은가요? Over-engineering 아닌가요?
   → No. **YAGNI** + **DRY** 트레이드오프. 변경이 한 번 일어났을 때 인터페이스 도입 (Rule of Three). 미래의 추측보다 "지금 변경 패턴"이 명확한 곳에만 PV 적용.
8. **꼬리의 꼬리**: MSA에서 Bounded Context 경계의 인터페이스는 PV의 거시 버전인가요?
   → 그렇다. Anti-Corruption Layer (ACL)가 PV의 가장 큰 단위. 외부 BC의 변경이 내부로 전파되지 않게 안정적 인터페이스 + 변환기. → 코드 안의 PV가 자라서 시스템 경계가 됨.

## 다음 챕터로

- [04-message-and-interface](../04-message-and-interface/) — Tell Don't Ask, Demeter 법칙
