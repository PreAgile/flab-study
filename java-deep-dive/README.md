# Java Deep Dive — 언어 기능의 내부 메커니즘

> "Java 제네릭? `List<String>` 같은 거" 라고 답하면 입문자.
> "javac이 컴파일 시점에 type erasure로 `List<Object>` + 캐스트로 변환해서 ClassFile에 Signature attribute로 원형 타입 정보를 남기고, bridge method를 자동 생성해 covariant return type을 처리하며, JIT은 type guard로 실제 타입을 inline cache에 기록한다" 라고 말할 수 있다면 그 다음 단계.
> 이 가이드의 목표는 후자다.

---

## 📍 학습 목표

이 챕터를 마치면 다음을 막힘없이 답할 수 있다.

1. 제네릭이 type erasure로 어떻게 ClassFile에 표현되고 런타임에 사라지는지, 그러나 Signature attribute에는 왜 남아있는지.
2. PECS 원칙(Producer Extends Consumer Super)이 왜 그렇게 생겼는지, 공변/반공변/불공변의 의미.
3. Reflection이 비싼 진짜 이유, MethodHandle은 왜 그것보다 빠른지, Dynamic Proxy/CGLIB은 어떻게 동작하나.
4. Thread의 platform vs virtual 차이, ThreadLocal이 어떻게 누수를 만드나, ExecutorService와 ForkJoinPool의 work-stealing.
5. Connection Timeout과 Read Timeout이 OS 수준에서 다르게 동작하는 이유 (TCP SYN vs `recv()` blocking) — 그리고 두 개 다 안 거는 코드가 production에서 어떻게 hang 거는가.
6. 위 모든 개념이 production에서 어떤 장애로 드러나는지 진단·해결.

---

## 📚 챕터 목록

| # | 파일 | 핵심 질문 | 상태 |
|---|---|---|---|
| 01 | [01-generics.md](./01-generics.md) | "제네릭의 type erasure가 ClassFile/JIT/런타임 각 계층에서 어떻게 다루어지나" | ✅ (1147 lines) |
| 02 | [02-reflection.md](./02-reflection.md) | "Reflection은 왜 느린가, MethodHandle/Dynamic Proxy/CGLIB는 어떻게 다른가" | ✅ (1171 lines) |
| 03 | [03-threads.md](./03-threads.md) | "Thread 객체부터 ExecutorService, ForkJoinPool, ThreadLocal, race condition 패턴, Virtual Thread까지" | ✅ (1775 lines) |
| 04 | [04-timeouts-connection-vs-read.md](./04-timeouts-connection-vs-read.md) | "connection / read / socket / write timeout — 각각 OS의 어느 단계에서 발생하나" | ✅ (1336 lines) |
| 05 | [05-hashing-and-hash-collections.md](./05-hashing-and-hash-collections.md) | "Object.hashCode/equals 5계약, HashMap JDK 8 treeify, ConcurrentHashMap per-bucket CAS, hash flooding, consistent hashing — Java 생태계 전체가 hash 위에 서 있다" | ✅ (2269 lines) |

---

## 🎯 학습 철학 (flab-study AGENTS.md 5룰)

1. **개념 누락 금지** — 모든 핵심 개념을 본질·왜·연결까지
2. **시니어 운영 마스터 관점** — production 장애 진단에 매핑
3. **표면 디테일 제외** — 옵션값보다 본질·왜·역사
4. **다이어그램 필수** — ASCII 시각화 + 손그림 가이드
5. **백지 마스터 수준** — 줄줄 풀어낼 수 있게

## 7단 레이어 (모든 sub-chapter)

| 단계 | 내용 |
|---|---|
| 1. 백지 그리기 | ASCII + 손그림 가이드 |
| 2. 직관 | 한 줄 비유 + 정확한 정의 |
| 3. 구조 | 컴포넌트 분해 |
| 4. 내부 구현 | OpenJDK 코드 / ClassFile 발췌 |
| 5. 역사 | JDK 5/8/9/17/21 진화 |
| 6. 트레이드오프 ⭐ | 대안 비교 |
| 7. 측정·진단 ⭐ | javap/JFR/async-profiler |
| + 꼬리질문 | 면접/실무 검증 |

---

## 🔗 다른 학습 영역과의 연결

| 외부 챕터 | 어떻게 이어지나 |
|---|---|
| `jvm/01-class-lifecycle/` | Generics의 Signature attribute, Reflection의 ClassFile constant pool |
| `jvm/03-execution-engine/` | Reflection이 왜 JIT inlining을 방해하나, MethodHandle은 왜 inline-friendly한가 |
| `jvm/05-threading/` | Thread 모델, JMM, synchronized, Virtual Thread Continuation |
| `network-request-lifecycle/04-load-balancer-deep-dive.md` | timeout이 LB/upstream과 어떻게 상호작용하는지 |
| `network-request-lifecycle/07-connection-pools-master.md` | HikariCP/HTTP client timeout이 Java timeout 위에 어떻게 쌓이는지 |

---

## 🏢 실무 시나리오 미리보기

```
1. "List<String>인데 Reflection으로 Integer 넣었는데 컴파일도 런타임도 OK?"
   → type erasure로 런타임에 타입 정보 사라짐. ClassCastException은 꺼낼 때 발생

2. "Spring Bean이 동적 proxy로 감싸지는데 final 메서드는 왜 안 되나?"
   → CGLIB이 subclass 생성으로 동작 → final은 override 불가

3. "ThreadLocal 썼는데 메모리 누수"
   → Tomcat ThreadPool은 스레드 재사용. remove() 안 부르면 다음 요청에도 살아있음

4. "HttpClient에서 connect timeout만 걸었더니 read에서 무한 대기"
   → connect timeout은 TCP SYN/SYN-ACK까지만. body 전송은 read timeout

5. "MethodHandle이 Reflection보다 빠른 이유?"
   → MethodHandle은 final 필드로 invoke → JIT이 inline. Reflection은 Method 객체의 method lookup 매번
```

---

## 진행 현황

- [x] README + 챕터 목록
- [x] 01-generics (1147 lines)
- [x] 02-reflection (1171 lines)
- [x] 03-threads (1775 lines)
- [x] 04-timeouts-connection-vs-read (1336 lines)
- [x] 05-hashing-and-hash-collections (2269 lines)

**총 7,698 라인** — 5개 챕터 모두 7단 레이어 + 시니어 운영 관점 + ASCII 다이어그램 + 꼬리질문 완성.

> 이 파일은 학습 진행에 따라 계속 업데이트된다.
