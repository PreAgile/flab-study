# 22. Tradeoff Master Table — cross-chapter 종합 비교

> **이 챕터의 한 줄 목표**: "X vs Y, 언제 무엇을?" 류 질문에 30초 안에 매트릭스로 답한다. 각 결정의 **컨텍스트 의존성** (도메인 복잡도, 팀 성숙도, 변경 빈도)을 명확히 함.

## 학습 목표

1. **5대 핵심 결정**을 한 표로 종합.
2. 각 결정의 **컨텍스트 의존 변수** 식별.
3. "맞는 답"이 없고 "맞는 트레이드오프"가 있음을 안다.

## 파일 목록

| # | 파일 | 비교 축 |
|---|---|---|
| 01 | [01-oop-vs-fp.md](./01-oop-vs-fp.md) | OOP vs FP |
| 02 | [02-inheritance-vs-composition.md](./02-inheritance-vs-composition.md) | 상속 vs 합성 |
| 03 | [03-anemic-vs-rich-domain.md](./03-anemic-vs-rich-domain.md) | Anemic vs Rich Domain |
| 04 | [04-di-four-ways.md](./04-di-four-ways.md) | DI 4 방식 |
| 05 | [05-java-vs-kotlin.md](./05-java-vs-kotlin.md) | Java 21 vs Kotlin 1.9 |
| 06 | [06-decision-matrix.md](./06-decision-matrix.md) | 컨텍스트별 의사결정 매트릭스 |

## 종합 트레이드오프 마스터 표

### 1. OOP vs FP

| 축 | OOP | FP | 결정 변수 |
|---|---|---|---|
| **도메인 모델링** | ✓✓ | ~ | 도메인 복잡도 |
| **상태 변화** | ✓ (캡슐화) | ~ (Monad) | 도메인의 상태성 |
| **데이터 변환** | ~ | ✓✓ | 데이터 처리 비중 |
| **동시성** | ~ (락) | ✓✓ (불변) | 동시 처리 요구 |
| **테스트** | ~ (Mock) | ✓✓ | 테스트 자동화 수준 |
| **러닝 커브** | 낮음 | 높음 | 팀 성숙도 |

**결론**: 도메인 = OOP, 데이터 = FP, 둘 다 쓰는 하이브리드가 현실.

### 2. 상속 vs 합성

| 축 | 상속 (extends) | 합성 (composition) | 결정 변수 |
|---|---|---|---|
| **결합도** | 강함 | 약함 | 변경 빈도 |
| **재사용 비용** | 낮음 | 중간 (위임 boilerplate) | 코드 양 |
| **런타임 교체** | X | O | 유연성 요구 |
| **다중 재사용** | X (Java 단일 상속) | O | 재사용 종류 |
| **테스트 용이성** | 낮음 | 높음 | 테스트 자동화 |
| **자기-호출 함정** | 위험 | 없음 | 프레임워크 사용 |

**결론**: 진짜 is-a + 안정적 부모일 때만 상속. 그 외 합성. (Effective Java 18조)

### 3. Anemic vs Rich Domain

| 축 | Anemic | Rich | 결정 변수 |
|---|---|---|---|
| **단순 CRUD** | ✓ | ~ | 도메인 복잡도 |
| **복잡 규칙** | ✗ (Service 비대) | ✓ | 비즈니스 규칙 수 |
| **JPA 친화** | ✓ | ~ (영속성 분리 필요) | ORM 사용 |
| **테스트** | Service mock 지옥 | 도메인 단위 테스트 | 테스트 양 |
| **러닝 커브** | 낮음 | 높음 | 팀 성숙도 |
| **MSA 친화** | ~ | ✓ (Aggregate) | 아키텍처 |

**결론**: CRUD 50%+ 시스템은 Anemic OK. 복잡 도메인은 Rich 필수. **단, 같은 시스템 안에 둘이 공존 가능** (Aggregate는 Rich, 단순 lookup은 Anemic).

### 4. DI 4 방식

| 축 | Constructor | Setter | Field | Method |
|---|---|---|---|---|
| **불변성** | ✓ | ✗ | ✗ | ~ |
| **필수 의존성 강제** | ✓ | ✗ | ✗ | ~ |
| **순환 의존 감지** | ✓ (생성 시) | ✗ | ✗ | ✗ |
| **테스트 (Spring 없이)** | ✓ | ✓ | ✗ | ✗ |
| **DI 컨테이너 종속성** | X | X | ✓ | ✓ |
| **코드 길이** | 길음 | 중 | 짧음 | 짧음 |
| **Spring 공식 권장** | ✓✓ | △ | ✗ | 특수 케이스만 |

**결론**: Constructor 기본. Lombok `@RequiredArgsConstructor` 또는 Kotlin primary constructor 활용.

### 5. Java 21 vs Kotlin 1.9

| 축 | Java 21 | Kotlin 1.9 | 결정 변수 |
|---|---|---|---|
| **Null Safety** | Optional + 어노테이션 | 타입 시스템 | 신뢰성 |
| **불변 데이터** | record | data class | 양쪽 OK |
| **Sealed/Pattern** | sealed + pattern (21+) | sealed + when (오래) | 동일 |
| **확장 함수** | X | O | DSL 필요성 |
| **동시성** | Virtual Thread | Coroutine | 비동기 사고법 |
| **컴파일 속도** | 빠름 | 느림 (K2 개선) | CI 시간 |
| **에코시스템** | 압도적 | 모바일+백엔드 | 라이브러리 |
| **러닝 커브** | 낮음 | 중간 | 팀 |
| **빅테크 채택 (한국)** | 보편 | 카카오/토스/당근 등 증가 | 시장 |

**결론**: Greenfield + 모바일 → Kotlin. 레거시 + 보수적 환경 → Java. **공존 가능** (점진적 Kotlin 도입).

## 컨텍스트별 의사결정 매트릭스

### 시나리오 1: 신규 백엔드 서비스 (스타트업, 도메인 명확하지 않음)

| 결정 | 선택 | 이유 |
|---|---|---|
| 패러다임 | OOP + FP 하이브리드 | 도메인 진화 중 |
| 도메인 스타일 | Anemic 시작 → Rich로 진화 | Premature optimization 회피 |
| 언어 | Kotlin | 표현력 + Coroutine |
| DI | Constructor | 기본 |
| 상속/합성 | 합성 | 변화 잦음 |
| 프레임워크 | Spring Boot 또는 Ktor | 에코시스템 |

### 시나리오 2: 레거시 모노리스 리팩토링

| 결정 | 선택 | 이유 |
|---|---|---|
| 패러다임 | OOP 강화 | 기존 베이스 유지 |
| 도메인 스타일 | Anemic → Rich 점진적 | Strangler Fig 패턴 |
| 언어 | Java 17/21 | 호환성 |
| DI | Constructor (기존 field → 점진 변경) | 점진 안정성 |
| 상속/합성 | 합성으로 점진 마이그레이션 | 기존 상속 위험 분해 |
| 프레임워크 | Spring (기존) | 변경 없음 |

### 시나리오 3: 금융/결제 시스템 (높은 신뢰성, 동시성)

| 결정 | 선택 | 이유 |
|---|---|---|
| 패러다임 | FP 강화 (불변성) | 동시성 안전 |
| 도메인 스타일 | Rich + Aggregate (DDD) | 복잡 규칙 |
| 언어 | Kotlin 또는 Scala | 함수형 친화 |
| DI | Constructor | 불변 보장 |
| 상속/합성 | 합성 + sealed class | ADT |
| 프레임워크 | Spring + Arrow / ZIO | 효과 관리 |

### 시나리오 4: 데이터 파이프라인 (ETL, 분석)

| 결정 | 선택 | 이유 |
|---|---|---|
| 패러다임 | FP 중심 | 변환 위주 |
| 도메인 스타일 | Record/data class만 | 데이터가 본질 |
| 언어 | Scala 또는 Kotlin | Stream/Sequence 풍부 |
| DI | 필요 없거나 간단 | 도메인 객체 적음 |
| 상속/합성 | sealed class | ADT 패턴 매칭 |
| 프레임워크 | Spark/Flink + Spring (선택) | 데이터 처리 위주 |

## 안티 결정 체크리스트

다음은 거의 항상 잘못된 선택:

- ❌ "Spring `@Field` 주입이 더 짧으니까 그것 사용" → 4가지 단점 (테스트, 불변, NPE, 의존성 숨김)
- ❌ "코드 재사용 위해 상속" → Effective Java 18조 위반, Fragile Base Class
- ❌ "모든 도메인 객체 빈으로 등록" → 빈 폭발, 도메인-Spring 결합
- ❌ "모든 메서드 `@Transactional`" → self-invocation 함정 + 성능
- ❌ "Anemic + Pattern Overdose" → 외형만 OOP, 본질은 절차지향
- ❌ "Null 안 쓰겠다고 모든 반환을 Optional<X>" → 가독성 ↓, 모나드 남용
- ❌ "FP 도입한다고 forEach 안에 부작용" → 진짜 FP가 아님
- ❌ "Kotlin 쓴다고 `!!` 남발" → null safety의 이점 폐기

## 컨텍스트 변수 정리

결정에 영향을 주는 핵심 변수 8가지:

1. **도메인 복잡도** — CRUD 위주 vs 복잡 규칙
2. **변경 빈도** — 안정적 vs 잦은 변경
3. **팀 성숙도** — 시니어 비율, 학습 시간
4. **테스트 자동화** — 0% vs 80%+
5. **동시성 요구** — 단일 스레드 vs 고동시성
6. **레거시 여부** — Greenfield vs Brownfield
7. **시스템 규모** — 단일 모놀리스 vs 분산 MSA
8. **신뢰성 요구** — 일반 vs 금융/의료

→ 같은 질문에도 8개 변수 조합에 따라 답이 다름.

## 다음 챕터로

- [30-mock-interviews](../30-mock-interviews/) — 종합 면접
