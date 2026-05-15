# 20. Ops Scenarios — 안티패턴 → 진단 → 리팩토링

> **이 챕터의 한 줄 목표**: 레거시 코드를 보면 5초 안에 안티패턴을 명명하고, 어떤 리팩토링 기법으로 어떻게 해소할지 3단계 계획을 댈 수 있다. 시니어 코드 리뷰의 핵심 역량.

## 학습 목표

1. **빅테크 7대 안티패턴**을 코드로 식별 + 명명.
2. 각 안티패턴의 **OOP 원칙 위반 근거**.
3. **점진적 리팩토링** 3단계 계획 (Mikado Method).
4. 실제 **공개 사례** (우아한기술블로그, 카카오 tech, Netflix 등) 참조.

## 파일 목록

| # | 파일 | 안티패턴 |
|---|---|---|
| 00 | [00-real-world-cases.md](./00-real-world-cases.md) | 빅테크 7대 안티패턴 종합 + 출처 |
| 01 | [01-god-object.md](./01-god-object.md) | God Object — 한 클래스가 모든 책임 |
| 02 | [02-anemic-vs-rich-domain.md](./02-anemic-vs-rich-domain.md) | Anemic Domain — DTO + Service 안티패턴 |
| 03 | [03-feature-envy.md](./03-feature-envy.md) | Feature Envy — 다른 객체의 데이터에 과도 접근 |
| 04 | [04-inheritance-abuse.md](./04-inheritance-abuse.md) | 상속 남용 — `extends` 4단 이상 |
| 05 | [05-spring-annotation-hell.md](./05-spring-annotation-hell.md) | `@Autowired` 필드 + `getBean` + 어노테이션 폭발 |
| 06 | [06-shotgun-surgery.md](./06-shotgun-surgery.md) | 산탄총 수술 — 한 변경이 10곳 수정 |
| 07 | [07-circular-dependency.md](./07-circular-dependency.md) | 순환 의존 — A → B → A |

## 7대 안티패턴 한 줄 요약

| # | 안티패턴 | 위반 원칙 | 진단 신호 |
|---|---|---|---|
| 1 | God Object | SRP | 클래스 1000줄+, 메서드 30개+ |
| 2 | Anemic Domain | Tell Don't Ask, 정보 전문가 | Entity에 getter만, Service에 로직 |
| 3 | Feature Envy | 정보 전문가, Demeter | 다른 객체 getter 5회+ 사용 |
| 4 | Inheritance 남용 | Effective Java 18조 | extends 깊이 4단 이상 |
| 5 | Spring 어노테이션 지옥 | DIP, SRP | 한 클래스에 어노테이션 10개+ |
| 6 | 산탄총 수술 | OCP | 한 변경 → 10곳 수정 |
| 7 | 순환 의존 | DIP, ADP (Acyclic Dependencies) | 빈 생성 실패, A↔B import |

## 7단 학습 레이어

### 1단. 백지 그리기

```
[그림 1] 안티패턴 진단 → 리팩토링 흐름
   ┌─────────────────────────────────────────────────────────┐
   │  1. 냄새 탐지 (Code Smell)                                │
   │     - 메트릭: 길이, 복잡도, 결합도                          │
   │     - 도구: SonarQube, IntelliJ Inspect                  │
   │  2. 안티패턴 명명                                          │
   │     - "이건 God Object", "이건 Feature Envy"             │
   │  3. 위반 원칙 매핑                                          │
   │     - SRP/OCP/Tell Don't Ask 어느 것을 깼나                │
   │  4. 리팩토링 패턴 선택 (Fowler)                              │
   │     - Extract Class, Move Method, Replace Conditional   │
   │       with Polymorphism, ...                            │
   │  5. 안전한 적용 (Mikado Method)                            │
   │     - 작은 단계로 분해 + 각 단계 테스트 통과                  │
   │     - main 브랜치 항상 green                              │
   └─────────────────────────────────────────────────────────┘

[그림 2] God Object 진단 (영화 예매 시스템 예시)
   Before:                              After:
   ┌──────────────────┐                ┌──────────────┐
   │ MovieService      │                │ Movie        │
   │ - 영화 조회        │                │ - 가격 계산    │
   │ - 가격 계산        │   →  분해 →   ├──────────────┤
   │ - 예매 생성        │                │ Reservation  │
   │ - 결제 처리        │                │ - 예매 생성    │
   │ - 이메일 발송      │                ├──────────────┤
   │ - 통계 집계        │                │ Payment      │
   │ - PDF 생성        │                │ - 결제 처리    │
   │  ... 메서드 35개  │                ├──────────────┤
   └──────────────────┘                │ Notifier     │
   책임 7개+                            │ - 이메일      │
                                       ├──────────────┤
                                       │ Statistics   │
                                       │ - 통계        │
                                       └──────────────┘

[그림 3] Anemic → Rich Domain 리팩토링
   Anemic:                              Rich:
   ┌──────────────┐                    ┌──────────────────┐
   │ Order        │                    │ Order            │
   │ - id         │                    │ - id             │
   │ - status     │                    │ - status         │
   │ - items[]     │                    │ - items[]         │
   │ getter*       │   →              │ + pay(payment)   │
   │ setter*       │                    │ + cancel()       │
   └──────────────┘                    │ + addItem(item)  │
   ┌──────────────────┐                │ + totalPrice()   │
   │ OrderService     │                └──────────────────┘
   │ + pay(o, p)      │                ┌──────────────────┐
   │ + cancel(o)      │                │ OrderService     │
   │ + addItem(o,i)   │                │ + processOrder() │
   │ + total(o)       │                │   - 트랜잭션      │
   │  로직 다 여기       │                │   - 이벤트 발행    │
   └──────────────────┘                │   - DB 저장      │
                                       └──────────────────┘
```

## 7대 안티패턴 상세 (요약, 풀버전은 sub-file에)

### 1. God Object
**증상**: 1000줄 넘는 `*Service`, `*Manager`, `*Util`. 메서드 30개.
**진단**: 책임의 종류를 세어보면 5개 이상.
**리팩토링**: Extract Class. CRC 카드로 책임 재배치.

### 2. Anemic Domain
**증상**: Entity에 `get`/`set`만, Service에 비즈니스 로직.
**진단**: Entity 메서드 중 비즈니스 동사가 0개.
**리팩토링**: Move Method (Service → Entity). Tell Don't Ask 적용.

### 3. Feature Envy
**증상**: `b.getX().getY().doSomething()`, Service가 Entity getter 5회+.
**진단**: Demeter 위반, 정보 전문가 위반.
**리팩토링**: Move Method 또는 Entity에 위임 메서드 추가.

### 4. Inheritance 남용
**증상**: 4단 이상 상속, `protected` 메서드에 자식이 의존.
**진단**: Fragile Base Class 위험.
**리팩토링**: Replace Inheritance with Delegation. Forwarding 패턴 (Effective Java 18조).

### 5. Spring 어노테이션 지옥
**증상**: 한 클래스에 `@Service @Transactional @Validated @Cacheable @Async @EventListener` 동시.
**진단**: 한 메서드가 너무 많은 횡단 관심사 + 비즈니스 로직.
**리팩토링**: 관심사 분리. 트랜잭션은 Application Service, 캐시는 별도 Decorator, 비동기는 Event.

### 6. 산탄총 수술 (Shotgun Surgery)
**증상**: 새 할인 정책 추가 시 10개 파일 수정.
**진단**: OCP 위반. 변경 지점이 흩어짐.
**리팩토링**: Strategy 패턴 또는 sealed + pattern matching으로 한 곳에 응집.

### 7. 순환 의존
**증상**: `BeanCurrentlyInCreationException` 또는 `Circular reference detected`.
**진단**: A → B → A 의존.
**리팩토링**: 책임 분리 (제3의 클래스 추출), 이벤트 도입, `@Lazy` (임시).

## 공개 사례 참조

### 🇰🇷 국내
| 출처 | 사례 | 키워드 |
|---|---|---|
| **우아한기술블로그** | 배달의민족 도메인 모델링 / 결제 도메인 | DDD, Aggregate, Anemic 탈출 |
| **카카오 tech** | 카카오페이 결제 / 메신저 채팅 도메인 | 분산 트랜잭션, 도메인 이벤트 |
| **네이버 D2** | 검색 랭킹 / 쇼핑 추천 모델 | 도메인 분리, MSA |
| **토스 tech** | 송금 / 카드 도메인 | 금융 도메인, 불변성 |
| **쿠팡 engineering** | 주문 / 배송 추적 | 이벤트 소싱 |
| **컬리 helloworld** | 새벽배송 도메인 | 도메인 이벤트, Saga |
| **당근 team** | 중고거래 / 채팅 도메인 | DDD bounded context |

### 🌍 해외
| 출처 | 사례 | 키워드 |
|---|---|---|
| **Martin Fowler refactoring.com** | Refactoring 2nd 예제 | 표준 리팩토링 기법 |
| **Netflix Tech Blog** | 영상 추천 / API Gateway 도메인 | MSA, 도메인 이벤트 |
| **Uber Engineering** | 매칭 / 결제 도메인 | DDD, Event Sourcing |
| **Stripe Engineering** | 결제 / 청구 도메인 | API 설계, 이벤트 |

## 다음 챕터로

- [21-hands-on-workbook](../21-hands-on-workbook/) — 직접 구현
