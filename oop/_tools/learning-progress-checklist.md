# 학습 진도 체크리스트 (16주 완전판)

> 각 주차의 학습 항목을 체크해가며 진행. README의 16주 학습 가이드와 매핑.

## Phase 1: 토대 (1~2주차)

### 1주차: 00-overview
- [ ] OOP의 한 줄 정의 (메시지·책임 중심)
- [ ] 절차지향의 한계 4가지 사례 학습
- [ ] Simula → Smalltalk → C++ → Java → Kotlin 타임라인 외움
- [ ] OOP vs FP vs 절차지향 트레이드오프 표 작성
- [ ] **실습**: 동일한 문제를 절차지향 C vs Java OOP로 작성 비교

### 2주차: 01-object-and-collaboration
- [ ] 객체 vs 클래스 구분 (객체가 본질, 클래스는 표현)
- [ ] 메시지 우선 사고 이해 (Alan Kay)
- [ ] CRC 카드 작성 방법
- [ ] 책임/역할/협력 (RRC) 모델
- [ ] **실습**: 영화 예매 시스템 CRC 카드 + 시퀀스 다이어그램

## Phase 2: 4대 기둥 (3~5주차)

### 3주차: 02-abstraction-and-encapsulation
- [ ] 추상화 vs 캡슐화 구분
- [ ] 캡슐화 4종류 (데이터/메서드/객체/서브타입)
- [ ] 다형성 3종류 (Subtype/Parametric/Ad-hoc)
- [ ] JVM `invokevirtual` + vtable + Inline Cache
- [ ] **실습**: `Comparable` vs `Comparator`, `instanceof` vs pattern matching

### 4주차: 03-responsibility-assignment
- [ ] GRASP 9원칙 외움 (또는 유도 가능)
- [ ] 정보 전문가 패턴
- [ ] 창조자 패턴
- [ ] Pure Fabrication vs 단순 클래스 추출
- [ ] **실습**: Anemic 코드를 Rich Domain으로 리팩토링

### 5주차: 04-message-and-interface
- [ ] Tell Don't Ask 원칙
- [ ] Demeter 법칙 4가지 허용 대상
- [ ] 좋은 인터페이스 6대 특성
- [ ] CQS → CQRS 진화
- [ ] **실습**: getter chain 코드를 Tell 방식으로 리팩토링

## Phase 3: 설계의 도구 (6~8주차)

### 6주차: 05-object-decomposition
- [ ] 절차 분해 vs 데이터 추상화 vs 책임 기반 비교
- [ ] Cargo Cult OOP (ADT만 있는) 진단
- [ ] **실습**: ATM 시스템 3가지 방식으로 작성

### 7주차: 06-dependency-management
- [ ] 의존성 5종류
- [ ] DIP의 정확한 의미
- [ ] DI 4방식 트레이드오프
- [ ] IoC vs DI vs Service Locator 구분
- [ ] **실습**: 30줄 자체 IoC 컨테이너 구현

### 8주차: 07-flexible-design
- [ ] SOLID 5원칙 변경 매핑
- [ ] OCP의 비용/효익
- [ ] LSP 위반 4조건
- [ ] GoF 패턴 변경 종류별 분류
- [ ] **실습**: Pattern Overdose 코드를 단순화

## Phase 4: 상속의 함정 (9주차)

### 9주차: 08-inheritance-vs-composition ⭐
- [ ] 상속의 4대 위험
- [ ] Forwarding 패턴
- [ ] Java/Kotlin/Scala mixin 비교
- [ ] sealed의 안전한 상속
- [ ] **실습**: `extends` 남용 코드를 합성 + `@Delegate`로

## Phase 5: 함수형 통합 (10~11주차)

### 10주차: 09-functional-paradigm ⭐
- [ ] 함수형 4대 기둥
- [ ] 모나드 직관 (Optional, Stream, CompletableFuture)
- [ ] 람다 칼큘러스 기원
- [ ] Functional Core, Imperative Shell 패턴
- [ ] **실습**: 비순수 코드의 순수 영역 추출

### 11주차: 10-java-evolution ⭐
- [ ] Java 8 lambda + `invokedynamic`
- [ ] record 바이트코드
- [ ] sealed의 ClassFile attribute
- [ ] Pattern Matching for switch 동작
- [ ] Virtual Thread 기본
- [ ] Brian Goetz의 Data Oriented Programming 이해
- [ ] **실습**: Java 7 코드를 Java 21 표현식 기반으로

## Phase 6: Kotlin 균형 (12주차)

### 12주차: 11-kotlin-paradigm ⭐
- [ ] Kotlin이 Java를 뒤집은 6가지
- [ ] Null Safety 타입 시스템
- [ ] data class vs record 5가지 차이
- [ ] 확장 함수, 스코프 함수, `by` 위임
- [ ] Coroutine vs Virtual Thread
- [ ] **실습**: 동일 도메인을 Java/Kotlin으로 작성 비교

## Phase 7: 운영 가능한 OOP (13주차)

### 13주차: 12-spring-and-framework
- [ ] Spring IoC 컨테이너 내부 (BeanDefinition → ApplicationContext)
- [ ] 빈 생성 라이프사이클 10단계
- [ ] JDK Dynamic Proxy vs CGLIB
- [ ] `@Transactional` 5대 함정
- [ ] Hexagonal Architecture + Spring
- [ ] **실습**: Spring 없이 동일 동작 순수 Java로

## Phase 8: 보강 (14~15주차) ⭐

### 14주차: 20-ops-scenarios + 21-hands-on-workbook
- [ ] 7대 안티패턴 진단 능력
- [ ] Mikado Method 리팩토링
- [ ] 조영호 영화 예매 시스템 직접 구현 (Java + Kotlin)
- [ ] 요금제 청구 시스템 직접 구현
- [ ] 도메인 모델링 카타 3개 이상

### 15주차: 22-tradeoff-master-table
- [ ] OOP vs FP 매트릭스
- [ ] 상속 vs 합성 매트릭스
- [ ] Anemic vs Rich Domain 매트릭스
- [ ] DI 4방식 매트릭스
- [ ] Java 21 vs Kotlin 1.9 매트릭스
- [ ] 컨텍스트 변수 8가지

## Phase 9: 종합 (16주차)

### 16주차: 30-mock-interviews ⭐
- [ ] Junior 면접 시나리오 5개 풀이
- [ ] Senior 면접 시나리오 5개 풀이
- [ ] Principal 면접 시나리오 5개 풀이
- [ ] 즉석 도메인 모델링 카타 5개 (각 15분)
- [ ] 꼬리질문 3단 대응 연습
- [ ] **자가 평가**: README 첫 문장을 3분 안에 풀어 설명

## 최종 자가 평가 (가이드 졸업 시험)

다음 모두 가능하면 "객체지향 설계 권위자" 수준:

- [ ] README 오프닝 인용 문장을 청중 레벨별(Junior/Senior/Principal)로 3가지 깊이로 답변
- [ ] 처음 보는 도메인을 30분 안에 CRC + 시퀀스 + 핵심 코드까지
- [ ] 레거시 코드 한 페이지를 보고 5초 안에 안티패턴 3개 명명
- [ ] 코드 리뷰에서 SOLID 위반 근거를 정확한 원칙명으로 지적
- [ ] Java/Kotlin/Scala 중 한 언어로 동일 도메인을 다른 패러다임 강조로 재구현 가능
- [ ] Spring `@Transactional` 함정 5가지 즉답
- [ ] DI 4방식 트레이드오프 30초 발표
- [ ] OOP vs FP 결정 컨텍스트 변수 5가지+ 즉답
- [ ] 다이내믹 디스패치의 JVM 구현 (vtable + IC + CHA) 설명
- [ ] sealed + record + pattern matching 결합 사례 코드 작성
- [ ] Hexagonal Architecture + DDD + MSA에서 도메인 객체의 위치 설명
- [ ] 신규 프로젝트의 Java vs Kotlin, Spring vs Quarkus 결정 5가지 변수로 논증
