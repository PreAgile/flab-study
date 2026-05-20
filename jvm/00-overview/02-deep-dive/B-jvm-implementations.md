# 부록 B — JVM 구현체 비교 (HotSpot / GraalVM / OpenJ9 / Azul / ART)

> "JVM"이라고 부르는 것들의 정체. 대부분은 HotSpot 클론(같은 코드 다른 빌드). 진짜 다른 건 4개 — GraalVM, OpenJ9, Azul, Android ART. GraalVM이 "C2 자리만" 갈아끼운 이유를 모르면 polyglot/Native Image의 본질을 놓친다.

---

## 이 문서의 사용법

본문 → [02. 컴파일 흐름](../02-class-compilation-flow.md) 가지 ①(WHY)에서 진입. "Graal JIT은 HotSpot의 변형, Native Image는 별도 런타임"이라는 통찰을 위한 부록.

---

## 0. 마인드맵

### 루트 한 문장 (anchor)

> **"JVM 구현체는 4 카테고리다 — (1) HotSpot 그대로 빌드한 것들(Corretto/Temurin/Zulu), (2) C2만 Graal로 교체한 GraalVM, (3) 완전 다른 코드베이스(OpenJ9/Zing/ART), (4) 마이크로 JVM. 'C2만' 갈아끼우는 게 가능한 건 JVMCI(JEP 243) 인터페이스 덕분이고, 이게 Truffle + Native Image라는 polyglot 전략의 발판이 됐다."**

### 4개 가지

```
        [ROOT: JVM 구현체 = 4 카테고리]
                    │
       ┌────────┬───┼───┬────────┐
      ① 같음   ② 변형  ③ 다름   ④ 마이크로
   HotSpot클론 GraalVM  완전     임베디드
       │       │       다른      │
       │       │       코드      │
    Corretto  C2를     OpenJ9    Avian
    Temurin   Graal로  Zing      JamVM
    Zulu      교체     ART       Kaffe
    Oracle    JVMCI    
    Microsoft Truffle  
              Native   
              Image    
```

### 가지별 핵심 키워드

| 가지 | 키워드 1 | 키워드 2 | 키워드 3 |
|---|---|---|---|
| **① HotSpot 클론** | OpenJDK 같은 소스 | 빌드/패치 정책만 다름 | Corretto/Temurin/Zulu/MS/Oracle |
| **② GraalVM** | C2만 Graal로 교체 | JVMCI (JEP 243) | Truffle + Native Image |
| **③ 완전 다름** | OpenJ9 (메모리 1/2) | Azul Zing (C4 pauseless) | Android ART (register-based) |
| **④ 마이크로** | Avian/JamVM | 임베디드 | 대부분 deprecated |

---

## 1. 가지 ①: HotSpot 클론 — 사실상 같은 JVM

### 1.1 핵심 질문

> "Oracle JDK, Corretto, Temurin은 뭐가 다르죠?"

### 1.2 키워드 1 — OpenJDK 같은 소스, 다른 빌드

자주 혼동: **OpenJDK** = Java 표준의 오픈소스 구현체 (라이브러리 + 도구 + JVM 전부). **HotSpot** = 그 안의 JVM 부분 이름.

OpenJDK = HotSpot JVM + JDK 라이브러리 + javac 등 도구.

### 1.3 키워드 2 — 빌드/패치 정책만 다름

전부 OpenJDK 소스를 빌드한 결과물 → 인터프리터/JIT/GC 동일.

| 배포 | 만든 곳 | 특징 |
|---|---|---|
| **Oracle JDK** | Oracle | LTS 상업 지원, 라이선스 변동 잦음 |
| **Eclipse Temurin** (구 AdoptOpenJDK) | Adoptium | 가장 검증된 OpenJDK 빌드 |
| **Amazon Corretto** | Amazon | AWS 최적화 + 보안 패치 빠름 |
| **Microsoft OpenJDK** | Microsoft | Azure 최적화 |
| **Azul Zulu** | Azul | LTS 무료 |
| **Liberica JDK** | BellSoft | 임베디드/Alpine 빌드 |
| **Red Hat OpenJDK** | Red Hat | RHEL 통합 |

차이는 **빌드 옵션, 보안 패치 속도, 지원 정책**뿐. JVM 구조는 같음.

### 1.4 키워드 3 — 어떤 배포 받을지

- **표준 학습/dev**: Temurin (가장 자료 많음)
- **AWS 운영**: Corretto (AWS 통합/지원)
- **Azure 운영**: Microsoft OpenJDK
- **상업 지원 필요**: Oracle JDK (유료) 또는 Azul Zulu Prime (상업 SLA)

---

## 2. 가지 ②: GraalVM — C2만 갈아끼운 HotSpot 변형

### 2.1 핵심 질문

> "GraalVM은 JVM인가요? 왜 C2만 바꿨나요?"

### 2.2 키워드 1 — JVMCI를 통해 C2만 교체

```
HotSpot (기본):
[Template Interpreter] → [C1] → [C2 (C++로 작성, 1999년~)]

GraalVM (HotSpot 모드):
[Template Interpreter] → [C1] → [Graal JIT (Java로 작성)]
                                 ↑
                                 C2 자리에만 들어감
```

**HotSpot과 GraalVM의 차이는 Tier 4 컴파일러 한 자리뿐**. 인터프리터, C1, GC, classloader, JNI 모두 동일. **JVMCI (JVM Compiler Interface, JEP 243)** 표준 API를 통해 C2를 핫스왑하듯 갈아끼울 수 있게 한 것.

**왜 C2만 갈아끼웠나** — 3가지 이유:

**(1) C2가 가치 있는 자리이자 손대기 어려운 자리**
- Peak 성능은 Tier 4에서 결정됨 → 여기를 개선하면 throughput 직접 좋아짐.
- C2는 1999년 Cliff Click 박사 논문(Sea of Nodes) 기반 C++ 코드. 25년 묵었고 손대기 무서움.
- Oracle 내부 농담: "C2를 이해하는 사람은 10명이고, 그중 5명은 은퇴했다."

**(2) Java로 컴파일러를 다시 쓰면 얻는 것**
- 자기 자신 컴파일(메타써큘러): Graal이 Graal을 컴파일 → 디버깅·튜닝이 Java 코드 다루듯.
- 모듈러: 새 최적화 패스를 노드 클래스 추가로 끝.
- 확장 가능: API가 깨끗해서 사외(Twitter, Renaissance Benchmark)에서도 기여 가능.

**(3) Truffle을 위한 발판**
- Truffle(polyglot, Ruby/Python/JS)이 작동하려면 AST 인터프리터를 native로 컴파일하는 JIT이 필요.
- C2론 불가능(JVM bytecode 전용). Graal은 Java API로 노출돼서 Truffle이 라이브러리처럼 호출.
- **Graal은 그냥 더 좋은 C2가 아니라, Truffle/polyglot/Native Image의 공용 컴파일 백엔드**.

인터프리터·C1은 잘 동작 중 → 안 건드림.

### 2.3 키워드 2 — Native Image (AOT 모드)

빌드 시점에 reachable한 모든 코드를 native binary로 AOT 컴파일.
- **인터프리터, JIT 둘 다 없음** — SVM(Substrate VM)이라는 작은 런타임만.
- **Closed-world assumption** — reflection은 빌드 시점에 설정으로 알려줘야 함 (`reflect-config.json`).
- **시작 시간 ms 단위** (HotSpot은 수백 ms ~ 수 초).

대가:
- 빌드 시간 폭증 (5~30분)
- reflection/dynamic class loading 설정 필요
- JFR/JMX 등 동적 관측 어려움

### 2.4 키워드 3 — Truffle Framework (polyglot)

Ruby(TruffleRuby), Python(GraalPy), JS(GraalJS)를 GraalVM에서 돌릴 때:
```
1. 언어 구현자가 AST 인터프리터를 Java로 작성
2. Truffle이 각 AST 노드에 "자기-프로파일링" 기능 추가
3. 핫한 AST 서브트리는 Graal JIT이 통째로 native code 컴파일
4. 가정 깨지면 다시 AST 인터프리터로 폴백
```

**AST 자체가 인터프리터이자 IR**. AST를 직접 JIT. 일반 bytecode 인터프리터와 차원이 다른 접근.

→ AST IR의 본격 설명 → [부록 C](./C-ast.md).

### 2.5 Graal JIT 장단점

| 축 | Graal vs C2 |
|---|---|
| **Partial Escape Analysis** | C2보다 강력. 조건부로만 escape하는 객체도 제거 가능 |
| **Stream/람다 최적화** | 평균 5~30% 빠름 (Twitter 사례 유명) |
| **Scala/Kotlin 함수형** | map/filter/reduce 패턴에 강함 |
| **확장성** | Java로 작성돼서 새 최적화 추가 쉬움 |
| **Polyglot/AOT 백엔드** | Truffle + Native Image의 공용 백엔드 |
| **메모리** | Graal JIT 자체가 Java라 사용량 1.5~2배 |
| **워밍업** | Graal이 자기 자신 컴파일하느라 첫 호출 C2보다 느림 |
| **워크로드 의존** | 단순 CRUD는 차이 거의 없음. 함수형 무거운 데서만 유리 |

### 2.6 GraalVM 운영 가이드

**Native Image 강추**:
- AWS Lambda / Cloud Run / Knative — 콜드 스타트 ms (HotSpot은 수 초)
- CLI 도구 (`./foo`로 10ms)
- 컨테이너 (메모리 50~100MB로 끝)
- Spring Boot 3 native, Quarkus, Micronaut

**Graal JIT 조건부**:
- Scala 백엔드 (Spark, Akka, Play) — 5~30% 더 빠를 때 많음
- Twitter 사례: 2018년 사내 JVM을 Graal로 교체해서 11% CPU 절감
- Stream/람다 무거운 데이터 처리

**Polyglot Truffle**: 학습/연구 가치 큼, 실무에선 드묾.

**안 써도 됨**: 일반 Spring Boot 안정 운영, JDK LTS 막 도입한 팀.

---

## 3. 가지 ③: 완전 다른 코드베이스

### 3.1 핵심 질문

> "OpenJ9, Azul Zing, Android ART는 HotSpot과 뭐가 다른가요?"

### 3.2 키워드 1 — Eclipse OpenJ9 (메모리 효율)

IBM J9가 오픈소스화. **HotSpot과 소스 공유 전혀 없음**.

| 항목 | HotSpot | OpenJ9 |
|---|---|---|
| **메모리 사용량** | 기본 | **약 50~70% (1/2)** |
| **Peak throughput** | 기본 | 약간 느림 (5~10%) |
| **GC** | G1/ZGC/Shenandoah | gencon/balanced/metronome |
| **Class Data Sharing** | AppCDS (일부) | **Shared Class Cache (강력)** — 여러 JVM이 메타데이터 공유 |
| **컨테이너 적합도** | JVM이 커서 작은 컨테이너 부담 | 메모리 작아서 한 노드에 더 많이 |

**인터프리터**: HotSpot처럼 어셈블리 템플릿 기반이지만 구조 다름. `bcInterp.asm` 같은 파일에 직접 작성. **JIT**: Testarossa (TR). HotSpot C1/C2와 완전히 다른 아키텍처.

**언제 OpenJ9**:
- 컨테이너 빽빽한 환경 (K8s 노드당 10~20개 pod)
- 메모리 빡빡 (저비용 인스턴스, 엣지)
- IBM WebSphere 계열

### 3.3 키워드 2 — Azul Zing/Prime (Pauseless GC)

상용. 비싸지만 **GC pause가 진짜로 없음**.

| 항목 | HotSpot ZGC | Azul C4 |
|---|---|---|
| **GC pause** | ~1ms (ZGC) | **< 1ms 보장 (C4 Pauseless)** |
| **힙 크기** | 16TB까지 | 8TB까지, 더 안정적 |
| **JIT** | C1+C2 | **Falcon (LLVM 기반)** — peak 성능 더 좋다고 |
| **가격** | 무료 | 코어당 라이선스 (비쌈) |

**언제 Azul**:
- 초저지연 거래 시스템 (금융 HFT)
- p99 latency가 SLA에 박힌 시스템
- 큰 힙(수백 GB) 운용
- HotSpot ZGC로 안 되는 워크로드

### 3.4 키워드 3 — Android ART/Dalvik (register-based)

Android는 자바를 쓰지만 **JVM이 아니다**.

| 항목 | HotSpot | Android ART |
|---|---|---|
| **Bytecode** | Stack-based (`.class`) | **Register-based (`.dex`)** |
| **컴파일 모델** | JIT 중심 | **AOT (앱 설치 시) + JIT 보강** |
| **출처** | OpenJDK 트리 | Google 자체 구현, OpenJDK 라이브러리만 사용 |
| **GC** | G1/ZGC | 모바일 특화 (Generational CC) |

**Dalvik → ART 전환** (Android 5.0, 2014):
- Dalvik은 JIT만, 매 실행마다 JIT
- ART는 앱 설치 시 AOT로 디스크에 native code → 실행 즉시 빠름
- 배터리/성능 둘 다 좋아짐

> 자바 코드로 Android 앱을 만들지만 실제 도는 건 ART. JVM 책 내용이 90% 적용되지만 GC·컴파일 모델·bytecode 포맷은 다름.

---

## 4. 가지 ④: 마이크로 JVM (임베디드)

### 4.1 키워드 — Avian, JamVM, Kaffe

| JVM | 특징 |
|---|---|
| **Avian** | 작은 footprint, 임베디드용. Switch 인터프리터 + 미니 JIT |
| **JamVM** | 학습용. Switch 또는 threaded 인터프리터, JIT 없음 |
| **Kaffe** | OSS 초기 JVM. 대부분 deprecated |

**언제**: 학습/연구. 실무에서는 거의 안 씀.

---

## 5. 한 그림 — 전체 정리

```
"JVM"이라고 부르는 것들의 분류

[1] HotSpot 계열 (사실상 같은 JVM, 빌드만 다름)
    ├─ Oracle JDK
    ├─ Eclipse Temurin
    ├─ Amazon Corretto
    ├─ Microsoft OpenJDK
    ├─ Azul Zulu
    └─ ...

[2] HotSpot 변형 (C2를 갈아끼운 것)
    └─ GraalVM
       ├─ HotSpot 모드 (C1 + Graal JIT)
       └─ Native Image 모드 (AOT, 인터프리터·JIT 없음, SVM 런타임)

[3] 완전 다른 JVM
    ├─ Eclipse OpenJ9    — 메모리 효율, 컨테이너 강점
    ├─ Azul Zing/Prime   — GC pause 없음, 상용
    └─ Android ART       — 모바일, register-based, 표준 JVM 아님

[4] 마이크로 JVM (학습용/임베디드)
    └─ Avian, JamVM, Kaffe (대부분 deprecated)
```

---

## 6. 면접 답변 워크플로우

### 6.1 질문 → 가지 매핑

| 면접 질문 | 진입 가지 |
|---|---|
| "Oracle JDK vs Corretto vs Temurin?" | ① HotSpot 클론 |
| "GraalVM은 JVM인가?" | ② |
| "왜 C2만 갈아끼웠나?" | ② JVMCI |
| "Native Image의 장단점?" | ② AOT |
| "OpenJ9이 메모리 적게 쓰는 이유?" | ③ Shared Class Cache |
| "Azul Zing은 왜 비싸나?" | ③ C4 Pauseless |
| "Android는 JVM인가?" | ③ ART (register-based) |

### 6.2 답변 템플릿

> "JVM 구현체는 4 카테고리입니다 (← 루트).
> 대부분의 배포(Oracle JDK, Corretto, Temurin)는 **같은 OpenJDK 소스를 빌드한 것**이라 본질적으로 같습니다.
> 진짜 다른 JVM은 4개 — GraalVM은 **JVMCI 인터페이스로 C2 자리만** 갈아끼웠고, OpenJ9은 IBM이 처음부터 다른 코드베이스로 만들었으며, Azul Zing은 C4 Pauseless GC + Falcon JIT, Android ART는 register-based bytecode로 완전히 다른 길을 갔습니다."

---

## 7. 꼬리질문 트리

### Q1 [가지 ②]. GraalVM이 C2만 갈아끼운 이유?

> Peak 성능 자리이자 손대기 어려운 자리(C++ Sea of Nodes 25년 코드). Java로 새로 쓰면 확장성·Truffle·Native Image까지 같이 얻음. 인터프리터·C1은 충분히 동작 중이라 건드릴 가치 적음. JVMCI(JEP 243) 표준 API로 핫스왑 가능.

**🪝 Q1-1: Native Image가 인터프리터·JIT 둘 다 없다는 게 무슨 뜻?**
> 빌드 시점에 모든 reachable 코드를 native로 AOT 컴파일 → 런타임에는 SVM이라는 작은 런타임만 동작. HotSpot 자체를 안 씀. GC만 SVM이 담당.

**🪝🪝 Q1-1-1: Closed-world assumption이 뭐?**
> 빌드 시점에 모든 클래스/메서드/reflection 대상이 알려져야 한다는 전제. dynamic class loading은 제한적. `reflect-config.json`으로 명시.

### Q2 [가지 ③]. OpenJ9이 메모리 절반 쓰는 이유?

> (1) **Shared Class Cache** — 여러 JVM이 같은 머신에서 클래스 메타데이터를 공유. (2) JIT(Testarossa) 코드 크기가 작음. (3) 자료구조 자체가 메모리 효율 우선으로 설계됨. K8s에서 노드당 pod 수를 늘릴 수 있어 빽빽한 컨테이너 환경에 강점.

### Q3 [가지 ③]. Android ART가 JVM이 아닌 이유?

> bytecode 포맷부터 다름 — `.class`(stack-based) vs `.dex`(register-based). Dalvik bytecode는 JVMS를 따르지 않음. 컴파일 모델도 다름 — JIT 중심이 아니라 AOT (앱 설치 시) + JIT 보강. JVMS 미준수 → "JVM"이라 부르면 안 됨, "Java 호환 VM".

---

## 8. 학습 체크리스트

- [ ] JVM 구현체 4 카테고리를 한 줄씩 구분한다
- [ ] HotSpot 클론들(Corretto/Temurin/Zulu)이 본질적으로 같다는 걸 설명한다
- [ ] GraalVM이 C2만 갈아끼운 3가지 이유를 말한다
- [ ] JVMCI (JEP 243)의 역할을 설명한다
- [ ] Native Image와 Graal JIT의 차이를 구분한다
- [ ] OpenJ9 / Azul Zing / Android ART가 HotSpot과 어떻게 다른지 설명한다

---

## 관련 부록

- [부록 A — 인터프리터 구현 4가지 방식](./A-interpreter-implementations.md): 각 JVM이 어느 방식을 택했나
- [부록 C — AST 자료구조](./C-ast.md): Truffle의 AST IR
- [부록 E — AOT vs JIT](./E-aot-jit-optimizations.md): Native Image가 택한 AOT의 트레이드오프
