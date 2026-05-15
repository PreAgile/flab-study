# 22-01. OOP 설계 결정 매트릭스

> "X vs Y, 언제 무엇을?" 류 질문에 30초 안에 매트릭스로 답.

## 📊 OOP 설계 결정 매트릭스

### 1. 상속 vs 합성

| | 상속 (extends) | 합성 (has-a) |
|---|---|---|
| 결합도 | 강함 | 약함 |
| Fragile Base Class | 위험 | 없음 |
| 다중 상속 | Java 불가 | 자유롭게 가능 |
| 코드 재사용 | 제약 많음 | 유연 |
| 런타임 변경 | 불가 | 가능 |
| 적합 | is-a + 같은 invariant | 코드 재사용 일반 |
| 권장 | 신중 | ✅ 일반 권장 |

### 2. Interface vs Abstract Class

| | Interface | Abstract Class |
|---|---|---|
| 다중 상속 | ✅ | ❌ |
| 상태 | ❌ (Java 8+ default method 일부) | ✅ |
| 강제 메서드 | 모두 abstract (or default) | 일부 abstract |
| 적합 | 능력 (Capability) | 부분 구현 + state |
| 예 | Comparable, Runnable | AbstractList |

### 3. DI 방식

| | Constructor | Setter | Field | Method |
|---|---|---|---|---|
| Final | ✅ | ❌ | ❌ | - |
| 필수 명시 | ✅ | ❌ | ❌ | - |
| 순환 의존 | 컴파일 | 런타임 | 런타임 | - |
| 테스트 | 쉬움 | 보통 | Spring 필요 | 어려움 |
| 권장 | ✅ | △ optional only | ❌ | ❌ |

### 4. Service vs Domain

| | Service | Domain |
|---|---|---|
| 책임 | 객체 간 조율 + tx 경계 | 비즈니스 로직 |
| 상태 | Stateless | Stateful |
| 위치 | Application layer | Domain layer |
| Bean 등록 | ✅ (Spring) | ❌ (POJO) |
| 예 | OrderService | Order, Money |

### 5. 다형성 vs Sealed + Pattern Matching

| | 다형성 (Subtype) | Sealed + Pattern |
|---|---|---|
| 분기 위치 | 객체 안 (자율) | 외부 코드 (switch) |
| 새 종류 추가 | 새 class만 | switch 추가 + sealed 변경 |
| OCP | ✅ | △ |
| 데이터 + 동작 | 묶임 | 분리 |
| 적합 | 동작 다형성 | 데이터 종류 분기 |

### 6. Mutable vs Immutable

| | Mutable | Immutable |
|---|---|---|
| 메모리 | 효율 | 매번 새 객체 |
| Thread safety | 어려움 | 자동 |
| 추론 | 어려움 | 쉬움 |
| 캐시/해시 | 위험 (변경 시 hash 깨짐) | 안전 |
| 예 | List, StringBuilder | String, Record |
| 권장 | △ (큰 자료구조) | ✅ 일반 권장 |

## 🎯 결정 트리

```
1. 도메인 복잡도 ↑?
   YES → 책임 기반 분해 + Rich Domain
   NO → 단순 CRUD (Anemic 도 OK)

2. 새 종류 추가가 자주?
   YES → Polymorphism (Strategy)
   NO → Simple if-else 도 OK

3. 변경이 한 곳에 응집?
   YES → SRP 적용 강화
   NO → 책임 분리

4. 외부 시스템 의존?
   YES → DIP + Adapter
   NO → 직접 사용

5. 함수형 적합? (Stateless transformation)
   YES → Stream, Optional, Record
   NO → OOP 위주

6. 동시성 필요?
   YES → Immutable + Virtual Thread (or Coroutine)
   NO → 일반 OOP
```

## 🔗 다음

- → [30. Mock Interviews](../30-mock-interviews/)
