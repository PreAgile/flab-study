# 부록 B — JVM 구현체 비교 (HotSpot / GraalVM / OpenJ9 / Azul / ART)

> **본문**: [02. 컴파일 흐름 — §2 직관](../02-class-compilation-flow.md#-2단계-직관)에서 "HotSpot은 Template Interpreter를 쓴다"고만 했다. 여기선 **"JVM"이라고 부르는 것들이 실제로 얼마나 다른가** — HotSpot 외에 어떤 구현체가 있고, 어디까지 같고 어디부터 다른지 — 를 본다.

---

## JVM 구현별 인터프리터·JIT 한눈 비교

| JVM | 인터프리터 | JIT |
|---|---|---|
| **HotSpot (OpenJDK)** | Template Interpreter | C1 + C2 (Tiered) |
| **OpenJDK** | = HotSpot (사실상 같은 코드) | = HotSpot |
| **GraalVM (Community/Enterprise)** | HotSpot Template Interpreter 그대로 | **Graal JIT**으로 C2를 교체 |
| **GraalVM Native Image** | **없음** (AOT 컴파일) | 없음 (AOT) |
| **Eclipse OpenJ9 (IBM)** | 자체 구현 (어셈블리 + JIT helper) | **Testarossa JIT** (TR) |
| **Azul Zing / Prime** | HotSpot fork (Template) | **Falcon** (LLVM 기반) |
| **Android ART** | 자체 (register-based) | **AOT + JIT 혼합** |
| **Dalvik (구 Android)** | register-based 인터프리터 | JIT (4.0~) |
| **Avian, JamVM** | switch 또는 threaded | 미니 JIT 또는 없음 |

---

## OpenJDK vs HotSpot — 사실상 같은 것

자주 혼동되는 지점:
- **OpenJDK** = "Java 표준의 오픈소스 구현체" (JDK 라이브러리 + 도구 + JVM 전부 포함)
- **HotSpot** = 그 OpenJDK 안에 들어있는 **JVM 부분의 이름**
- 즉 OpenJDK = HotSpot JVM + JDK 라이브러리 + javac 등 도구

Oracle JDK, Amazon Corretto, Azul Zulu, Adoptium Temurin, Microsoft OpenJDK 등은 전부 **OpenJDK 소스를 빌드한 결과물**이라 인터프리터가 동일하다 (Template Interpreter).

---

## GraalVM — 인터프리터는 같지만, JIT은 다름

### 세 가지 모드

**모드 A: HotSpot + Graal JIT (기본)**
- 인터프리터: HotSpot Template Interpreter **그대로**
- C1: HotSpot C1 **그대로**
- C2: **Graal JIT으로 교체** (Java로 작성된 컴파일러)
- 즉, "C2만 갈아끼운 HotSpot"

```
[Template Interpreter (HotSpot)] → [C1 (HotSpot)] → [Graal JIT (Java)]
```

Graal JIT의 장점:
- Java로 작성됨 → 디버깅/확장 쉬움
- Partial Escape Analysis가 C2보다 강력
- Stream/람다 최적화가 더 좋다고 알려짐

**모드 B: Native Image (AOT)**
- **인터프리터, JIT 둘 다 없음**
- 빌드 시점에 reachable한 모든 코드를 native binary로 AOT 컴파일
- closed-world assumption — reflection은 빌드 시점에 설정으로 알려줘야 함
- 시작 시간이 ms 단위 (HotSpot은 수백 ms ~ 수 초)

**모드 C: Truffle Framework**
Ruby(TruffleRuby), Python(GraalPy), JavaScript(GraalJS)를 GraalVM에서 돌릴 때 쓰는 방식:

```
1. 언어 구현자가 AST 인터프리터를 Java로 작성
2. Truffle이 AST의 각 노드에 "자기-프로파일링" 기능 추가
3. 핫한 AST 서브트리는 Graal JIT이 통째로 native code로 컴파일
4. 가정 깨지면 다시 AST 인터프리터로 폴백
```

**"AST 자체가 인터프리터이자 IR"**. AST를 직접 JIT한다. 일반적인 bytecode 인터프리터와는 차원이 다른 접근.

> 자세한 AST 정의는 [부록 C — AST 자료구조](./C-ast.md)에.

---

## GraalVM이 "C2 자리만" 갈아끼운 이유

### 어디까지 같고 어디부터 다른가

```
HotSpot (기본):
[Template Interpreter] → [C1] → [C2 (C++로 작성)]
                                 ↑
                                 1999년~2024년 동안 쌓인 C++ 코드

GraalVM (HotSpot 모드):
[Template Interpreter] → [C1] → [Graal JIT (Java로 작성)]
                                 ↑
                                 C2 자리에만 들어감
```

**HotSpot과 GraalVM의 차이는 "Tier 4 컴파일러"** 한 자리뿐. 인터프리터, C1, GC, classloader, JNI, 모든 게 동일하다. JVMCI(JVM Compiler Interface, JEP 243)라는 표준 API를 통해 **C2를 핫스왑하듯 갈아끼울 수 있게** 한 것.

### 왜 C2만 갈아끼웠나 — 3가지 이유

**(1) C2가 진짜 가치 있는 자리, 그리고 진짜 아픈 자리**

- **가치**: Peak 성능은 Tier 4에서 결정됨. 여기를 개선하면 throughput이 직접 좋아짐
- **고통**: C2는 1999년 Cliff Click 박사 논문(Sea of Nodes) 기반 C++ 코드. 25년 묵었고 손대기 무서움
- **확장 어려움**: 새 최적화 추가하려면 C++ + Sea of Nodes 내부를 깊이 알아야 함. 사내에 그걸 아는 사람이 손가락에 꼽힘

> Oracle 내부 농담: "C2를 이해하는 사람은 10명이고, 그중 5명은 은퇴했다."

**(2) Java로 컴파일러를 다시 쓰면 얻는 것**

- **자기 자신을 컴파일** (메타써큘러): Graal JIT 자체가 Java니까, Graal이 Graal을 컴파일한다. 디버깅·튜닝이 보통 Java 코드처럼 됨
- **모듈러**: Java 클래스/패키지 구조로 깔끔. 새 최적화 패스를 노드 클래스 추가로 끝낼 수 있음
- **확장 가능**: API가 깨끗해서 사외(Twitter, Renaissance Benchmark 등)에서도 기여 가능

**(3) Truffle을 위한 발판**

- Truffle(다국어 프레임워크, Ruby/Python/JS)이 작동하려면 **AST 인터프리터를 native로 컴파일하는 JIT**이 필요
- 그게 C2론 불가능 (C2는 JVM bytecode 전용). Graal은 Java API로 노출돼서 Truffle이 Graal을 라이브러리처럼 호출
- **Graal은 그냥 더 좋은 C2가 아니라, Truffle/polyglot/Native Image의 공용 컴파일 백엔드**

### 인터프리터와 C1은 왜 안 건드렸나

- **인터프리터**: 부팅 시 generate되는 단순한 어셈블리. 갈아끼울 가치 적음. 호환성 위험만 큼
- **C1**: warmup 단계라 빠르기만 하면 됨. 공격적 최적화 없어도 됨. 잘 동작 중
- **C2 = 최고 성능 자리**: 여기만 잘 만들면 peak throughput이 좋아짐

---

## Graal JIT의 장단점

### 장점

| 축 | Graal vs C2 |
|---|---|
| **Partial Escape Analysis** | ✅ C2보다 강력. 조건부로만 escape하는 객체도 제거 가능 |
| **Stream/람다 최적화** | ✅ 평균 5~30% 빠름 (Twitter 사례 유명) |
| **Scala/Kotlin 최적화** | ✅ 함수형 패턴(map/filter/reduce)에 강함 |
| **확장성** | ✅ Java로 작성돼서 새 최적화 추가 쉬움 |
| **Polyglot** | ✅ Truffle 통해 Ruby/Python/JS 가속 |
| **AOT** | ✅ Native Image의 백엔드 |

### 단점

| 축 | Graal vs C2 |
|---|---|
| **메모리** | ❌ Graal JIT 자체가 Java라 Code Cache + Graal의 힙 둘 다 사용. **메모리 사용량 1.5~2배** |
| **워밍업** | ❌ Graal JIT이 자기 자신을 컴파일하느라 처음엔 느림. **first-N 호출이 C2보다 느림** |
| **워크로드 의존** | ⚠️ 단순 CRUD/HTTP 서버는 차이 거의 없음. 함수형/스트림 무거운 데서만 유리 |
| **C2가 더 빠른 경우도 있음** | ⚠️ 정수 산술 heavy 워크로드에선 C2가 더 빠를 때도 |
| **안정성·접근성** | ⚠️ JDK 17에서 OpenJDK 트리에서 제거됨 (`-XX:+UseJVMCICompiler` 옵션). **GraalVM distribution을 별도로 받아야 함** |

---

## GraalVM을 언제 써야 하나

### 강하게 추천 — Native Image (AOT 모드)

| 시나리오 | 이유 |
|---|---|
| **AWS Lambda·Cloud Run·Knative** | 콜드 스타트가 ms 단위 (HotSpot은 수 초). 비용·UX 직결 |
| **CLI 도구** | `java -jar foo.jar`가 1초 걸리는 게 `./foo`로 10ms |
| **컨테이너 (CPU/메모리 제한 환경)** | 메모리 50~100MB로 끝 (HotSpot은 200~500MB) |
| **Spring Boot 3 native** | 공식 지원. `./gradlew nativeCompile` |
| **Quarkus / Micronaut** | 처음부터 GraalVM Native를 1순위로 설계된 프레임워크 |

대가:
- **빌드 시간 폭증** (5분~30분)
- **reflection·dynamic class loading 설정 필요** (빌드 시점에 알려줘야 함, `reflect-config.json`)
- **JFR/JMX 등 동적 관측 어려움**

### 조건부 추천 — Graal JIT (HotSpot 모드)

| 시나리오 | 이유 |
|---|---|
| **Scala 백엔드 (Spark, Akka, Play)** | 함수형 패턴이 많아서 Graal이 5~30% 더 빠를 때 많음 |
| **Twitter 식 마이크로서비스** | Twitter가 2018년에 사내 JVM을 Graal로 교체해서 11% CPU 절감 |
| **Stream/람다 무거운 데이터 처리** | Partial EA가 진가 발휘 |
| **Kotlin 백엔드 일부** | 코루틴/시퀀스 heavy 코드에선 유리 |

비추천:
- **단순 CRUD HTTP 서버** (DB가 병목, JIT 차이 의미 없음)
- **메모리 빡빡한 환경** (Graal 자체가 메모리 더 씀)
- **워밍업 짧아야 하는 곳** (서버리스인데 JIT 모드면 의미 없음 — 이땐 Native Image)

### Polyglot — Truffle

| 시나리오 |
|---|
| **JVM 위에서 Ruby/Python/JS 도구를 자바와 함께 쓰고 싶다** |
| **언어 자체를 설계 중 — DSL이나 새 언어를 만들고 싶다** (Truffle 프레임워크) |

실무에선 드물지만 학습/연구 가치 큼.

### 안 써도 됨

- **일반 Spring Boot 서버에서 부팅 후 안정 운영 중**: HotSpot이 검증됐고 메모리 절약됨. 굳이 Graal로 안 가도 됨
- **JDK 21 LTS 갓 도입한 팀**: 일단 표준 OpenJDK로 안정화 후 Graal 시도

---

## JVM 종류 — HotSpot과 뭐가 다른가

### 한눈에 보는 비교표

| JVM | 만든 곳 | 인터프리터 | JIT | GC 특징 | 강점 | 약점 |
|---|---|---|---|---|---|---|
| **HotSpot** | Oracle/OpenJDK | Template | C1+C2 | G1, ZGC, Shenandoah | 표준, 안정, 풍부한 문서 | 메모리 큼 |
| **GraalVM** | Oracle Labs | (HotSpot 빌림) | C1+Graal | (HotSpot 빌림) | Native Image, polyglot, peak 성능 | 메모리, warmup |
| **Eclipse OpenJ9** | Eclipse (구 IBM J9) | 자체 어셈블리 | Testarossa (TR) | Balanced, Metronome, gencon | **메모리 1/2~1/3**, 공유 클래스 캐시 | 생태계 작음, 문서 적음 |
| **Azul Zing/Prime** | Azul Systems | (HotSpot fork) | **Falcon (LLVM)** | **C4 Pauseless** | GC pause 1ms 미만, peak 성능 | 상용 (비쌈), 큰 메모리 필요 |
| **Amazon Corretto** | Amazon | (HotSpot 그대로) | (HotSpot) | (HotSpot) | AWS 최적화 + 보안 패치 빠름 | = HotSpot |
| **Eclipse Temurin** | Adoptium | (HotSpot 그대로) | (HotSpot) | (HotSpot) | 가장 검증된 OpenJDK 빌드 | = HotSpot |
| **Microsoft OpenJDK** | Microsoft | (HotSpot 그대로) | (HotSpot) | (HotSpot) | Azure 최적화 | = HotSpot |
| **Android ART** | Google | 자체 (Mterp) | AOT + JIT | 모바일용 GC | 앱 설치 시 AOT, 모바일 최적 | 표준 JVM 아님, register-based bytecode |
| **Avian / JamVM** | OSS | Switch/threaded | 없음 또는 미니 | 단순 | 작음 (수 MB) | 느림 |

### HotSpot 클론 vs 진짜 다른 JVM

**HotSpot의 빌드 배포본일 뿐인 것들** (실질적으로 같은 JVM):
- Oracle JDK
- Amazon Corretto
- Eclipse Temurin (구 AdoptOpenJDK)
- Microsoft OpenJDK
- Azul Zulu
- Liberica JDK (BellSoft)
- Red Hat OpenJDK

→ 전부 **OpenJDK 소스를 빌드한 결과물**. 인터프리터/JIT/GC는 동일. 차이는 **빌드 옵션, 보안 패치 속도, 지원 정책**뿐.

**진짜 다른 JVM**:
- **GraalVM**: C2를 Graal로 교체 + Native Image + Truffle
- **OpenJ9**: 완전 다른 코드베이스. 메모리 효율 강점
- **Azul Zing/Prime**: HotSpot fork지만 GC(C4)와 JIT(Falcon) 완전 교체. **GC pause가 거의 없는 게 특징**
- **Android ART**: register-based bytecode부터 다름. 사실상 별개 생태계

---

## Eclipse OpenJ9 — HotSpot과 깊은 비교

진짜 다른 두 JVM 중 하나. 자주 비교됨:

| 항목 | HotSpot | OpenJ9 |
|---|---|---|
| **메모리 사용량** | 기본 | **약 50~70% (1/2)** |
| **시작 속도** | 기본 | 비슷~약간 빠름 |
| **Peak throughput** | 기본 | 약간 느림 (5~10%) |
| **GC** | G1/ZGC/Shenandoah | gencon/balanced/metronome |
| **Class Data Sharing** | AppCDS (일부) | **Shared Class Cache (강력)** — 여러 JVM이 메타데이터 공유 |
| **컨테이너 적합도** | △ (JVM이 커서 작은 컨테이너에 부담) | ✅ (메모리 작아서 한 노드에 더 많이 띄움) |

**구조적 차이**:
- IBM J9가 오픈소스화된 것. HotSpot과 **소스 공유 전혀 없음**.
- **인터프리터**: HotSpot처럼 어셈블리 템플릿 기반이지만 구조가 다름. `bcInterp.asm` 같은 어셈블리 파일에 직접 작성.
- **JIT**: Testarossa (TR). HotSpot C1/C2와 완전히 다른 아키텍처.

**언제 OpenJ9**:
- 컨테이너를 빽빽하게 띄우는 환경 (Kubernetes 노드당 10~20개 pod)
- 메모리 빡빡한 환경 (저비용 인스턴스, 엣지 디바이스)
- IBM WebSphere 계열 (IBM이 표준으로 권장)

**언제 HotSpot**:
- 일반적 서버, peak 성능 중시
- 생태계/문서가 풍부해야 할 때
- 팀 학습 비용을 줄여야 할 때

---

## Azul Zing/Prime — 깊은 비교

상용 JVM. 비싸지만 **GC pause가 진짜로 없음**:

| 항목 | HotSpot ZGC | Azul C4 |
|---|---|---|
| **GC pause** | ~1ms (ZGC) | **< 1ms 보장 (C4 Pauseless)** |
| **힙 크기** | 16TB까지 | **8TB까지, 더 안정적** |
| **JIT** | C1+C2 | **Falcon (LLVM 기반)** — peak 성능 더 좋다고 알려짐 |
| **가격** | 무료 (OpenJDK) | 상용 (코어당 라이선스) |

**언제 Azul**:
- 초저지연 거래 시스템(금융 HFT)
- p99 latency가 SLA에 박혀 있는 시스템
- 큰 힙(수백 GB) 운용
- HotSpot ZGC로 안 되는 워크로드를 만났을 때

---

## Android ART/Dalvik — 모바일의 다른 길

Android는 자바를 쓰지만 **JVM이 아니다**:

| 항목 | HotSpot | Android ART |
|---|---|---|
| **Bytecode** | Stack-based (`.class`) | **Register-based (`.dex`)** |
| **컴파일 모델** | JIT 중심 | **AOT (앱 설치 시) + JIT 보강** |
| **출처** | OpenJDK 트리 | Google 자체 구현, OpenJDK 라이브러리만 사용 |
| **GC** | G1/ZGC | 모바일 특화 GC (Generational CC) |

**구조적 차이**:
- **register-based bytecode** (Dalvik bytecode, `.dex`)
- 처음엔 인터프리터로 시작 → hot 메서드는 **AOT로 디스크에 저장** (앱 설치/유휴 시) → 이후 실행 시 즉시 native
- HotSpot 식 "어셈블리 템플릿"이 아니라 **C++로 작성된 switch interpreter**가 기본. 단, "Mterp"라는 어셈블리 인터프리터를 별도로 갖고 있어 hot path에선 그걸 사용.

**Dalvik → ART 전환** (Android 5.0, 2014):
- Dalvik은 JIT만, 매 실행마다 JIT
- ART는 앱 설치 시 AOT로 디스크에 native code 저장 → 실행 즉시 빠름
- 배터리·성능 둘 다 좋아짐

> 자바 코드로 Android 앱을 만들지만 실제로 도는 건 ART다. JVM 책의 내용이 90% 적용되지만, **GC·컴파일 모델·bytecode 포맷**은 다르다는 점 주의.

---

## 한 그림 — 전체 정리

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
       └─ Native Image 모드 (AOT, 인터프리터·JIT 없음)

[3] 완전 다른 JVM
    ├─ Eclipse OpenJ9    — 메모리 효율, 컨테이너 강점
    ├─ Azul Zing/Prime   — GC pause 없음, 상용
    └─ Android ART/Dalvik — 모바일, register-based, 표준 JVM 아님

[4] 마이크로 JVM (학습용/임베디드)
    └─ Avian, JamVM, Kaffe (대부분 deprecated)
```

---

## 한 줄 요약

- **GraalVM이 C2만 갈아끼운 이유**: C2가 최고 성능 자리이자 손대기 어려운 자리. Java로 새로 쓰면 확장성·Truffle·Native Image까지 같이 얻음. 인터프리터·C1은 충분히 잘 동작 중이라 건드릴 가치 적음
- **Graal JIT 장단점**: Partial EA·Stream·Scala에 강하지만 메모리·warmup·워크로드 의존
- **Graal 쓸 때**: Native Image는 서버리스/CLI/컨테이너에서 강추, Graal JIT은 함수형 워크로드에서 조건부 추천
- **JVM 종류**: 대부분은 HotSpot 클론(같은 코드 다른 빌드). 진짜 다른 건 GraalVM·OpenJ9·Azul·Android ART **4개뿐**

---

## 관련 부록

- [부록 A — 인터프리터 구현 4가지 방식](./A-interpreter-implementations.md): 각 JVM이 (1)~(4) 중 어느 방식을 택했는가
- [부록 C — AST 자료구조](./C-ast.md): GraalVM Truffle이 AST를 IR로 쓰는 방식
- [부록 E — AOT vs JIT](./E-aot-jit-optimizations.md): Native Image가 택한 AOT의 트레이드오프
