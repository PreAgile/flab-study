# 09. Mock Interviews — Junior / Senior / Principal 시뮬레이션

> 면접 시뮬레이션. 레벨별 질문 + 모범 답안.

---

## 🎯 Junior (1~3년)

### Q1. JVM이 뭐고 JRE/JDK와 차이는?

> JVM: bytecode 실행 가상 머신 (HotSpot, OpenJ9 등).
> JRE: JVM + 표준 라이브러리.
> JDK: JRE + 개발 도구 (javac, jcmd 등).
> 단, JDK 9+부터 JRE 별도 배포 종료. 개념적으로만 구분.

### Q2. Heap vs Stack 차이는?

> Heap: 모든 thread 공유, 객체 인스턴스 저장, GC 대상.
> Stack: per-thread, Stack Frame (메서드 호출) 저장, GC 대상 아님.

### Q3. GC가 뭐고 왜 필요한가요?

> 사용 안 하는 객체 자동 회수. C/C++의 manual memory 관리 회피.
> Reachability 기반: GC Roots에서 도달 불가능한 객체 = 죽음.

### Q4. ArrayList vs LinkedList?

> ArrayList: 배열 기반, 임의 접근 O(1), 끝 add/remove O(1) amortized.
> LinkedList: 노드 기반, 임의 접근 O(n), 양끝 add/remove O(1).
> 일반: ArrayList 우세 (cache locality).

### Q5. synchronized와 volatile의 차이?

> synchronized: mutual exclusion + visibility + atomicity.
> volatile: visibility + happens-before (atomicity 없음).
> 단순 flag = volatile, 복합 mutate = synchronized.

---

## 🎯 Senior (3~10년)

### Q1. JDK 8 → 17 마이그레이션 경험은?

> 1. 모든 dependency 17 호환 확인 (Spring Boot 3+).
> 2. `sun.misc.Unsafe` 사용처 제거.
> 3. JEE 모듈 (`javax.xml.bind` 등) 별도 dependency.
> 4. Strong encapsulation: `--add-opens` 필요한 라이브러리.
> 5. Default GC 변경 (Parallel → G1) — 옵션 재검토.
> 6. 단계적 canary 배포로 메트릭 비교.

### Q2. G1 vs ZGC 선택 기준?

> Heap 크기:
> - <32GB: G1 충분.
> - 32~128GB: ZGC 권장 (sub-ms STW).
> - 100GB+: Generational ZGC (JDK 21+).
> 
> Latency:
> - P99 < 50ms 목표: G1.
> - P99 < 10ms 목표: ZGC.
> 
> Throughput: G1과 Generational ZGC 동등. Single-gen ZGC는 G1 대비 15% ↓.

### Q3. Production OOM이 났습니다. 진단 절차는?

> 1. **Heap dump 확보** (`-XX:+HeapDumpOnOutOfMemoryError` 사전 필수).
> 2. **MAT 분석**:
>    - Leak Suspects 자동 분석.
>    - Dominator Tree로 큰 객체.
>    - GC Roots 추적.
> 3. **5대 누수 패턴 점검**:
>    - 정적 컬렉션, ThreadLocal, Listener, Cache, JDBC Driver.
> 4. **코드 수정** + 알람 (Old gen 사용량 80% 임계).
> 5. **사후 보강**: GC log 활성화, JFR continuous, NMT.

### Q4. Container 환경 JVM 메모리 설정 가이드는?

> Container limit 5GB 기준:
> - `-Xmx`: 2g (40%).
> - `-XX:MaxDirectMemorySize`: 1g (20%).
> - `-XX:MaxMetaspaceSize`: 512m (10%).
> - `-XX:ReservedCodeCacheSize`: 256m.
> - Thread stacks (500 thread × 1MB): 500m.
> - 여유: 700m (JVM internal, kernel, libs).
> 
> 모니터링: cgroup memory.current (RSS), NMT.

---

## 🎯 Principal (10년+)

### Q1. JDK 25 (다음 LTS)의 책임자라면 어떤 변화를 우선할까요?

> 1. **synchronized pinning 해소** (JEP 491) — VT 본격 채택의 마지막 장벽.
> 2. **Project Lilliput stable** — Mark Word 압축, footprint 5~10% ↓.
> 3. **Vector API stable** — SuperWord의 보완, SIMD 표준화.
> 4. **Project Leyden 진전** — AOT 통합, Native Image 표준화.
> 5. **Generational ZGC default 검토** — G1 대체 가능성 평가.
> 6. **Project Valhalla preview 확대** — value types, generic specialization.

### Q2. 차세대 default GC를 결정한다면 어떤 기준으로?

> 평가 차원:
> 1. **Latency**: P99 STW 분포.
> 2. **Throughput**: 동일 워크로드 대비 비율.
> 3. **Footprint**: Heap 외 메모리 부담.
> 4. **Maintenance**: 코드 복잡도, 커뮤니티 지원.
> 5. **호환성**: 다양한 워크로드/OS/CPU.
> 6. **운영 도구**: 모니터링, debugging 성숙도.
> 
> 후보:
> - G1: 안정, throughput 우수, STW 예측 가능.
> - Generational ZGC: 차세대, 모든 면에서 G1 동등 + sub-ms STW.
> 
> 결정: JDK 25에서 Generational ZGC 검증 + JDK 27에서 default 전환 검토.

### Q3. 100대 규모 Production Java 서비스의 메모리/GC 최적화 전략을?

> 1. **메트릭 표준화**:
>    - Prometheus + Grafana로 통일.
>    - JFR continuous recording 표준화.
>    - 알람 기준 표준화 (GC time %, Full GC freq, Allocation rate).
> 
> 2. **JDK 버전 통일**:
>    - 8 → 17/21 마이그레이션 로드맵.
>    - LTS 위주 (8/11/17/21).
> 
> 3. **GC 선택 표준**:
>    - 일반 서비스: G1 + MaxGCPauseMillis=200.
>    - Latency-critical: ZGC.
>    - 큰 Heap: Generational ZGC.
> 
> 4. **자동화**:
>    - Heap dump auto on OOM.
>    - Container limit ↔ JVM 옵션 자동 매핑 (template).
>    - GC log retention policy.
> 
> 5. **운영 능력**:
>    - 시니어 엔지니어 매 팀 1+ 명.
>    - 사고 시나리오 playbook.
>    - Quarterly performance review.

### Q4. JVM에서 30년 만에 도입된 Virtual Thread의 영향을 평가해보세요.

> 긍정적:
> - "Color of function" 문제 해결 — sync 코드로 수십만 thread.
> - Reactive 프로그래밍의 복잡도 회피.
> - 디버깅 자연스러움 (stack trace 정상).
> - Spring Boot 3.2+ 기본 지원.
> 
> 부정적/주의:
> - Pinning 함정 (synchronized + I/O).
> - 옛 라이브러리 호환성 (JDBC driver, HTTP client).
> - CPU-bound 부적합.
> - ThreadLocal 대량 사용 시 메모리 ↑.
> 
> 운영 영향:
> - Microservice 동시성 한계 ↑.
> - Connection pool 크기 재검토.
> - 모니터링 도구 확장 (VT 추적).
> 
> 장기:
> - 비동기 프레임워크 (Reactor, RxJava)의 의미 약화.
> - Reactive 프로젝트 → Virtual Thread 마이그레이션 추세.

### Q5. (Killer) 글로벌 fintech 서비스의 JVM 인프라 책임자입니다. 첫 100일 plan은?

> Day 1-30: **진단**
> - 현재 인프라 audit (JDK 버전, GC, 메트릭).
> - 사고 history 분석 (P99 spike, OOM, downtime).
> - 핵심 서비스의 부하 패턴 모델링.
> - 팀 역량 평가.
> 
> Day 31-60: **표준화**
> - JVM 옵션 template 작성.
> - 메트릭 + 알람 표준 도입.
> - GC log + JFR retention.
> - 사고 playbook 작성.
> 
> Day 61-90: **개선**
> - 가장 큰 risk 서비스부터 마이그레이션.
> - Canary 배포 절차 도입.
> - 모니터링 dashboard 통합.
> - 시니어 엔지니어 hire/train.
> 
> Day 91-100: **최적화**
> - 메트릭 기반 GC/JIT 튜닝.
> - 비용 최적화 (Native Image 검토).
> - 차세대 JDK 마이그레이션 plan.

---

## ⚔️ 종합 면접 시나리오

### 1시간 시뮬레이션

**0-10분: Self-intro + 기본**
- "JVM 메모리 영역을 그려보세요" (Chapter 02).
- "GC 알고리즘 중 하나를 깊이 설명해주세요" (Chapter 04).

**10-30분: Deep dive**
- "JIT 컴파일 흐름을 설명하세요" (Chapter 03).
- "Virtual Thread는 어떻게 동작하나요?" (Chapter 05-04).

**30-50분: Production 시나리오**
- "P99 latency spike 진단 절차" (Chapter 10).
- "Container OOM-killed 분석" (Chapter 10).

**50-60분: 시스템 설계**
- "100대 서비스의 JVM 표준화 전략" (Principal level).

---

## 📚 자료

- 모든 챕터 (00~12) cross-reference.
- 본 챕터는 종합 평가.
