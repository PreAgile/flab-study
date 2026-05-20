# 08. GraalVM — Graal JIT + Native Image + Truffle

> Java 앱의 cold start 5초가 Native Image로 200ms로 바뀐다. Footprint 300MB가 70MB로 줄어든다. 그러나 peak throughput은 10% 떨어지고 reflection은 빌드 시 명시해야 한다.
> GraalVM 한 이름에 3가지 다른 도구: **Graal JIT** (C2 대체) / **Native Image** (AOT, JVM 없이 실행) / **Truffle** (polyglot framework). 각자 다른 운영 결정.
> 시니어가 알아야 할 것: serverless/microservice cold start 시대에 Native Image가 주요 무기다. 다만 closed-world 가정의 제약을 안다.

---

## 이 문서의 사용법

이 문서는 **면접용 마인드맵**을 따라 선형으로 펼친 구조다. 학습 순서 = 면접 답변 순서 = 백지에 그리는 순서.

1. **0장 마인드맵을 먼저 외운다** — 루트 한 문장 + 3가지 가지 + 각 가지의 키워드 3개.
2. **1~3장을 순서대로 학습한다** — 각 장이 마인드맵의 한 가지에 정확히 대응.
3. **4장 면접 워크플로우로 검증** — 질문을 보면 어느 가지로 가야 하는지 매핑.
4. **5장 꼬리질문으로 깊이 점검**.

---

## 0. 마인드맵 — 면접 종이에 그릴 그림

### 루트 한 문장 (anchor)

> **"GraalVM은 한 이름에 3가지: Graal JIT(C2 대체), Native Image(AOT, JVM 없음), Truffle(polyglot). cold start vs peak throughput 트레이드오프가 핵심 운영 결정이다."**

이 한 문장에서 모든 답변이 출발한다. 어떤 질문이 와도 이 문장부터 말하고 적절한 가지로 분기.

### 3개 가지 — 순서를 외운다

```
                  [ROOT: GraalVM = 3가지 도구]
                                 │
        ┌──────────────┬─────────┴─────────┐
        │              │                   │
       ① 3 components ② Native Image    ③ 운영 결정
       (구조)         (closed-world)     (tradeoff)
        │              │                   │
     ┌──┼──┐        ┌──┼──┐            ┌───┼───┐
   Graal Native Truffle  Build Runtime  startup throughput
   JIT  Image  polyglot  scan AOT       footprint maturity
   (JVMCI)(AOT)         reachability    serverless 일반
                       SVM/SubstrateVM  vs JVM ZGC
```

### 가지별 핵심 키워드 (각 가지 3개씩만)

| 가지 | 키워드 1 | 키워드 2 | 키워드 3 |
|---|---|---|---|
| **① 3 components** | Graal JIT (JVMCI 통해 C2 대체) | Native Image (AOT, JVM 없음) | Truffle (polyglot framework) |
| **② Native Image** | Closed-world 가정 | Build = scan + reachability + AOT | Runtime = SubstrateVM |
| **③ 운영 결정** | Serverless/CLI → Native Image | 일반 web → JVM + G1/ZGC | Reflection 제약 → hint files |

### 면접 답변 흐름

> 면접관 질문 → 루트 문장 → 질문에 맞는 가지 1개 선택 → 그 가지의 키워드 3개 순서대로 설명 → 듣는 사람의 관심에 따라 인접 가지로 확장

---

## 1. 가지 ①: 3 components — Graal JIT / Native Image / Truffle

### 1.1 핵심 질문

> "GraalVM이라는 한 이름에 어떤 도구들이 묶여 있나요?"

### 1.2 키워드 1 — Graal JIT (C2 대체)

```
HotSpot                       HotSpot + Graal JIT
━━━━━━━                       ━━━━━━━━━━━━━━━━━

bytecode → C1 → C2 → native   bytecode → C1 → Graal → native
              ↓                              ↓
              C++로 작성된 JIT              Java로 작성된 JIT
                                            (JVMCI 통해 plugin)
```

**핵심**:
- Graal은 **Java로 작성된 JIT 컴파일러**. C2(C++)와 동일한 역할.
- HotSpot의 **JVMCI** (JEP 243) 인터페이스를 통해 plugin으로 동작.
- 활성화: `-XX:+UnlockExperimentalVMOptions -XX:+UseJVMCICompiler`.

**장점**:
- Java로 작성됨 → 개발/유지보수 쉬움.
- 일부 워크로드 (특히 Scala, Kotlin, Stream 무거운 코드)에서 C2 대비 throughput 향상.
- Polyglot 런타임 (Truffle)의 기반.

**단점**:
- JIT 자체가 Java라 startup 시 자신도 컴파일되어야 함 (cold path).
- 일부 워크로드에서 C2가 여전히 우세.

### 1.3 키워드 2 — Native Image (AOT, JVM 없음)

```
JVM 실행                       Native Image 실행
━━━━━━━━                      ━━━━━━━━━━━━━━━

[OS]                          [OS]
 ↓ java -jar app.jar           ↓ ./myapp (native binary)
[JVM 부트스트랩]              [실행 시작 즉시]
 ↓ class loading              [SubstrateVM (작은 runtime)]
 ↓ interpret + JIT warmup     ↓
 ↓ peak 도달 (수십 초)        peak 도달 (0초)
[application]                 [application]

Startup: 수 초                 Startup: 수십 ms
Footprint: 200~500MB           Footprint: 30~100MB
Peak: 100%                     Peak: 80~90%
```

**핵심**:
- **AOT (Ahead-Of-Time)** 컴파일 — 빌드 시점에 native code로 완성.
- JVM 없이 직접 실행되는 **native executable**.
- 내부에 **SubstrateVM (SVM)** — 작은 GC + threading runtime 포함.

**구성요소**:
- **Graal compiler** — bytecode를 AOT로 native code 변환.
- **SubstrateVM** — 빌드된 binary 안의 minimal JVM runtime (GC, threading 등).
- **빌드 도구** — `native-image MyApp`.

### 1.4 키워드 3 — Truffle (Polyglot framework)

```
GraalVM
 ├── Java/Kotlin/Scala (JVM bytecode)
 ├── JavaScript (Truffle GraalJS)
 ├── Python (Truffle GraalPython)
 ├── Ruby (TruffleRuby)
 ├── R (FastR)
 └── LLVM bitcode (Sulong) — C/C++/Rust
```

**핵심**:
- Truffle = **AST interpreter framework**. 새 언어를 빠르게 구현할 수 있는 framework.
- 각 언어가 Truffle 위에서 동작 → Graal JIT이 partial evaluation으로 native code 생성.
- **Polyglot interop** — Java에서 JavaScript 호출, Python에서 Java 객체 사용 등.

**시니어 관점**: 일반 운영에서는 거의 안 씀. Polyglot이 필요한 특수 케이스 (script 임베딩, 다언어 마이크로서비스)에서.

---

## 2. 가지 ②: Native Image — closed-world AOT

### 2.1 핵심 질문

> "Native Image는 어떻게 JVM 없이 동작하나요? 제약은?"

### 2.2 키워드 1 — Closed-world 가정

```
JVM (open-world)                Native Image (closed-world)
━━━━━━━━━━━━━━                  ━━━━━━━━━━━━━━━━━━━━

런타임에 새 class load 가능      빌드 시점에 모든 class 확정
런타임에 reflection 자유         reflection은 hint files로 명시
Dynamic proxy 자유               Proxy는 빌드 시 알려야 함
Class generation 가능            제한 (일부 지원)
```

**의미**:
- 빌드 시점에 **앱이 사용할 모든 코드를 알아야 함**.
- 미사용 코드 제거 (tree shaking) → 작은 binary.
- 런타임에 새 코드 추가 불가 → JIT warmup 없음.

**제약**:
- Reflection 사용 시 `reflect-config.json` 같은 metadata로 미리 선언.
- Spring Boot 3는 이 metadata를 자동 생성하는 **Spring AOT engine**을 가짐.

### 2.3 키워드 2 — Build process (scan + reachability + AOT)

```
[Build]
1. native-image MyApp
2. 모든 class를 scan (classpath)
3. Static reachability 분석:
   - main()부터 시작
   - 호출 가능한 모든 메서드 그래프 구축
   - reachable 클래스/메서드만 binary에 포함
4. AOT 컴파일 (Graal compiler가 일괄)
5. SubstrateVM (작은 GC + threading) 통합
6. 결과: native executable (~수십 MB)

[빌드 시간]
- ~수 분 (Reachability 분석이 무거움)
- CPU + 메모리 많이 씀
```

**Reachability 분석의 효과**:
- 사용 안 하는 JDK 클래스 제거.
- 사용 안 하는 라이브러리 코드 제거.
- 결과: 30~100MB binary (JVM의 1/10).

### 2.4 키워드 3 — Runtime (SubstrateVM)

```
Native Image binary 내부
━━━━━━━━━━━━━━━━━━━━━

┌─────────────────────────┐
│ AOT 컴파일된 native code │  ← 앱 + 사용된 JDK
├─────────────────────────┤
│ SubstrateVM (SVM)        │  ← 작은 runtime
│  ├── GC (Serial / G1)    │
│  ├── Threading           │
│  ├── Class metadata      │
│  └── Heap management     │
└─────────────────────────┘

OS → 직접 실행 (JVM 부트스트랩 없음)
```

**SubstrateVM 특성**:
- HotSpot보다 훨씬 작은 runtime.
- GC는 Serial 또는 G1 비슷한 단순한 구현 (ZGC 없음).
- **JIT 없음** — 이미 AOT 컴파일됨.

**결과**:
- Startup ~수십 ms (JVM 부트스트랩 없음).
- Footprint 30~100MB (작은 runtime + tree-shaken code).
- Peak는 약간 낮음 (~80~90% of JVM) — JIT의 profile-guided 최적화 부재.

### 2.5 Spring Boot 3 + Native Image

```bash
# Spring Boot 3+가 Native Image 직접 지원
./mvnw -Pnative native:compile

# 결과: target/myapp (native executable)
# Startup: 200ms (vs JVM 3초)
# Footprint: 70MB (vs JVM 300MB)
```

**Spring AOT engine**:
- 빌드 시점에 Spring application context를 분석.
- Reflection metadata 자동 생성.
- 옛 Spring의 reflection-heavy 코드가 Native Image 친화로 자동 변환.

---

## 3. 가지 ③: 운영 결정 — 언제 GraalVM을 쓰나

### 3.1 핵심 질문

> "어떤 워크로드에서 Native Image를 도입하고, 어디서는 JVM을 유지하나요?"

### 3.2 키워드 1 — Native Image가 답인 경우

| 워크로드 | 이유 |
|---|---|
| **Serverless (AWS Lambda 등)** | Cold start가 비용 직결. 5초 → 200ms. |
| **CLI tool** (`mvn`, `kubectl` 류) | 매 실행마다 JVM warmup이 사용자 경험 망침. |
| **Microservice cold start 중요** | K8s에서 scale-up 빠름. |
| **Container memory 제한적** | Footprint 1/4~1/10. |

### 3.3 키워드 2 — JVM이 답인 경우

| 워크로드 | 이유 |
|---|---|
| **일반 web service (오래 떠 있음)** | JIT warmup이 한 번뿐 → peak가 곧 default. |
| **Latency-critical 큰 Heap** | ZGC가 sub-ms STW 보장. SubstrateVM은 못 함. |
| **Throughput 최우선 (batch)** | C2의 peak가 AOT보다 약간 높음. |
| **Reflection 무거운 옛 라이브러리** | hint files 작성이 부담. |

### 3.4 키워드 3 — JVM vs Native Image 트레이드오프

| | JVM (HotSpot) | Native Image |
|---|---|---|
| Startup | 수 초 (warmup) | 수십 ms |
| Footprint | 200MB+ | 30~100MB |
| Peak throughput | 100% | 80~90% |
| Build 시간 | < 1분 | ~수 분 |
| Reflection | 자유 | 빌드 시 명시 (hint files) |
| Dynamic class | 자유 | 제한적 |
| JIT 최적화 | continuous (profile-guided) | 빌드 시 한 번 |
| GC 옵션 | Serial/Parallel/G1/ZGC/Shenandoah | Serial/G1 (SVM) |
| Production maturity | 매우 성숙 | 성숙 중 |
| 적합 워크로드 | 일반 long-running service | Serverless, CLI, cold-start critical |

### 3.5 운영 결정 매트릭스

```
┌────────────────────────────┬───────────────────────────┐
│ 워크로드/조건                │ 권장                     │
├────────────────────────────┼───────────────────────────┤
│ Serverless (Lambda 등)      │ Native Image              │
│ CLI tool                    │ Native Image              │
│ Microservice cold start ↑↑  │ Native Image              │
│ Container memory 제한적      │ Native Image 검토         │
│ 일반 web service            │ JVM (HotSpot)             │
│ Latency-critical 큰 Heap   │ JVM + ZGC                 │
│ Peak throughput 최우선      │ JVM + Graal JIT 검토      │
│ Polyglot 필요 (JS, Python)  │ Truffle                   │
└────────────────────────────┴───────────────────────────┘
```

### 3.6 Project Leyden과의 관계

- **Project Leyden** (OpenJDK 진행 중): AOT compilation을 표준 JDK에 통합.
- 목표: GraalVM Native Image의 이점을 표준 JDK로 가져오기.
- 현재 (2026): preview 단계, JDK 25~30 사이에 안정화 예상.
- **시니어 관점**: GraalVM Native Image는 현재 유일한 production-ready AOT 옵션. Leyden이 성숙하면 선택지 다양화.

---

## 4. 면접 답변 워크플로우

### 4.1 질문 → 가지 매핑

| 면접 질문 | 진입 가지 | 인접 확장 |
|---|---|---|
| "GraalVM이 뭔가요?" | ① 3 components | ② Native Image |
| "Native Image와 JVM 차이?" | ② Native Image | ③ Tradeoff |
| "Closed-world 가정이 뭔가요?" | ② Closed-world | ② Build process |
| "Native Image의 단점?" | ② 제약 | ③ 운영 결정 |
| "Lambda cold start 줄이려면?" | ③ Serverless | ② Native Image |
| "Graal JIT은 C2랑 뭐가 다른가요?" | ① Graal JIT | [Chapter 07 JVMCI] |
| "Spring Boot 3가 Native 지원?" | ② Spring AOT | ③ 운영 |
| "Truffle은 언제 쓰나요?" | ① Truffle | Polyglot |

### 4.2 답변 템플릿

> **루트 문장 한 줄 → 해당 가지 키워드 3개 순서대로 → 듣는 사람 표정 보고 인접 가지로**

예: "Native Image와 JVM의 차이?"

> "GraalVM은 한 이름에 3가지 도구이고, 그 중 Native Image가 JVM의 대안입니다.
> JVM은 open-world — 런타임에 class loading, reflection이 자유로워서 JIT warmup이 필요합니다. Startup 수 초, footprint 200~500MB, peak 100%.
> Native Image는 closed-world — 빌드 시점에 모든 class를 알고 reachability 분석으로 미사용 코드 제거 + AOT 컴파일. Startup 수십 ms, footprint 30~100MB, peak 80~90%.
> 트레이드오프: cold start와 footprint를 얻고, peak throughput과 reflection 자유를 잃습니다. 그래서 serverless/CLI에는 Native Image, 일반 long-running web service는 JVM이 답입니다."

→ 면접관이 "closed-world 제약 구체적으로?"면 ②의 Build process로, "Spring Boot는?"면 Spring AOT로.

---

## 5. 꼬리질문 트리 (가지별)

### Q1 [가지 ①]. GraalVM의 3가지 component는?

> Graal JIT (C2 대체, JVMCI로 plugin), Native Image (AOT, JVM 없이 실행), Truffle (polyglot framework). 한 이름에 묶여 있지만 각자 다른 도구이고 다른 운영 결정.

**🪝 Q1-1: Graal JIT은 어떻게 HotSpot에 들어가나요?**
> JVMCI (JEP 243, JDK 9+) 인터페이스. HotSpot이 외부 JIT compiler를 plugin으로 받음. `-XX:+UnlockExperimentalVMOptions -XX:+UseJVMCICompiler`로 활성화. [Chapter 07 HotSpot Internals](../07-hotspot-internals/)의 JVMCI 섹션.

### Q2 [가지 ②]. Native Image의 closed-world 가정이 무엇인가요?

> 빌드 시점에 앱이 사용할 모든 class + method가 알려져 있다는 가정. Static reachability 분석으로 미사용 코드 제거 (tree shaking) → 작은 binary. Dynamic class loading, runtime reflection 자유는 잃음.

**🪝 Q2-1: 그럼 reflection을 못 쓰나요?**
> 쓸 수 있음. 단 빌드 시 `reflect-config.json` 같은 hint files로 미리 선언해야 함. Spring Boot 3는 **Spring AOT engine**이 이 metadata를 자동 생성 — 옛 reflection-heavy 코드가 자동으로 Native Image 친화로 변환됨.

### Q3 [가지 ②]. Native Image의 단점은?

> 1. **Reflection** — 빌드 시 명시 필요 (hint files).
> 2. **Build 시간** — Reachability 분석이 무거워서 수 분.
> 3. **Peak throughput** — JIT의 profile-guided 최적화 없어서 JVM 대비 ~10% 낮음.
> 4. **Dynamic class loading** 제한.
> 5. **일부 라이브러리** 미지원 (Native Image 친화 작업 필요).
> 6. **GC 옵션** 적음 — SubstrateVM은 Serial/G1만, ZGC 없음.

### Q4 [가지 ②]. SubstrateVM이 무엇인가요?

> Native Image binary 안에 들어가는 minimal runtime. HotSpot보다 훨씬 작음. GC (Serial 또는 G1 비슷), threading, class metadata, Heap management 포함. JIT는 없음 (이미 AOT 컴파일됨). 결과: 작은 footprint + 빠른 startup.

### Q5 [가지 ③]. 어떤 워크로드에서 Native Image를 도입하나요?

> Cold start 비용이 큰 워크로드:
> - **Serverless** (Lambda) — 매 invocation cold start.
> - **CLI tool** (kubectl, mvn) — 매 실행 cold start.
> - **Microservice scale-up** — K8s에서 빠른 응답 필요.
> - **Container memory 제한** — footprint 1/4~1/10.
>
> 반대로 long-running web service는 JVM warmup이 한 번뿐이라 peak를 그대로 누리는 게 유리.

**🪝 Q5-1: 일반 web service에서도 Native Image가 매력적이지 않나?**
> Footprint는 매력적이지만 peak throughput 10% 손해 + reflection metadata 작업 부담 + build 시간 길어 CI/CD 비용 ↑. 트레이드오프 검토 필요. ZGC + AppCDS 조합으로 JVM 쪽 startup/footprint도 많이 개선 가능.

### Q6 [가지 ①]. Graal JIT이 C2보다 좋은가요?

> 워크로드 의존. Java로 작성되어 유지보수 쉬움. Scala/Kotlin/Stream 무거운 코드에서는 C2 대비 throughput 향상 케이스 있음. 일반 Java 코드는 C2와 비슷하거나 약간 낮음. 일부 워크로드는 C2가 여전히 우세. 실측 후 결정.

### Q7 (Killer) [가지 ③]. Lambda 함수로 배포 중인 Java app의 cold start가 5초입니다. 어떻게 줄이나요?

> 옵션 우선순위:
>
> 1. **Native Image (GraalVM)**: 5초 → 200ms. 가장 큰 효과.
>    - Spring Boot 3 사용 시 `native-image` 빌드 지원.
>    - Quarkus, Micronaut도 Native friendly.
>    - 비용: Reflection metadata, build 시간 증가, peak 약간 ↓.
>
> 2. **AppCDS (JVM)**: 5초 → 2초. 적용 쉬움.
>    - Class data sharing — 클래스 metadata pre-loaded.
>    - Native Image보다 효과는 작지만 변경 비용 거의 0.
>
> 3. **Project Leyden** (JDK 22+, 진행 중): AOT 표준. 미래 옵션.
>
> 4. **Lambda Provisioned Concurrency**: 인프라 비용 ↑로 cold start 회피.
>
> **권장**: Spring Boot 3면 Native Image부터 시도, 아니면 AppCDS 먼저 적용 후 Native Image 검토.

**🪝 Q7-1: Native Image 도입 후 무엇을 측정하나요?**
> Startup time (ms 단위), peak throughput (RPS), memory footprint (RSS), error rate (reflection 누락으로 NoSuchMethodException 등), build 시간 (CI/CD 영향). 특히 reflection 누락은 production에서 터지면 큰 사고 — staging에서 부하 + reflection-heavy path 모두 통과 확인 필수.

---

## 6. 학습 체크리스트

면접 전 백지에서 다음을 다 해낼 수 있어야 마스터:

- [ ] 0장 마인드맵을 종이에 1분 이내로 그릴 수 있다 (루트 + 3가지 + 각 키워드 3개)
- [ ] 가지 ① 3 components: Graal JIT / Native Image / Truffle 각자 1줄 정의
- [ ] 가지 ① Graal JIT: JVMCI 통해 plugin 동작 설명
- [ ] 가지 ② Native Image: closed-world 가정과 그 의미를 말한다
- [ ] 가지 ② Native Image: Build 흐름 (scan → reachability → AOT → SVM 통합) 4단계
- [ ] 가지 ② Native Image: SubstrateVM이 무엇인지 1줄
- [ ] 가지 ③ 운영: JVM vs Native Image 트레이드오프 표를 그린다
- [ ] 가지 ③ 운영: Serverless/CLI vs Web service 결정 기준을 말한다
- [ ] Lambda cold start 5초 → 줄이는 4가지 옵션을 우선순위 순서로 말한다
- [ ] 5장 꼬리질문 7개에 막힘없이 답한다

---

## 다음 단계

- → [Chapter 10. Ops Scenarios](../10-ops-scenarios/): 실전 운영 시나리오
- → [Chapter 12. Tradeoff Master Table](../12-tradeoff-master-table/): 모든 트레이드오프 종합
- ← [Chapter 03. Execution Engine](../03-execution-engine/): JIT 동작 원리
- ← [Chapter 07. HotSpot Internals](../07-hotspot-internals/): JVMCI 인터페이스

## 참고

- **GraalVM**: https://www.graalvm.org/
- **Spring Boot 3 Native**: https://spring.io/blog/2022/11/22/spring-boot-3-0-goes-ga
- **Project Leyden**: https://openjdk.org/projects/leyden/
- **JEP 243 JVMCI**: https://openjdk.org/jeps/243
- **Quarkus**: https://quarkus.io/
- **Micronaut**: https://micronaut.io/
- **GraalVM Native Image Reference**: https://www.graalvm.org/latest/reference-manual/native-image/
