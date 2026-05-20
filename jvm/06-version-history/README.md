# 06. Version History — JDK 8/11/17/21+ 마스터 타임라인

> 같은 코드가 JDK 8에서는 OOM, JDK 11에서는 멀쩡, JDK 21에서는 처리량 3배. 이 차이를 만드는 게 LTS별 GC default + 모듈 시스템 + Loom이다.
> JDK 8 (2014) PermGen 제거, JDK 11 G1 default, JDK 17 ZGC production, JDK 21 Virtual Thread — 시니어가 외워야 할 4개의 변곡점.
> "어느 JDK가 운영에 적합한가" + "마이그레이션 시 무엇이 깨지는가" — 이 두 질문에 답할 수 있어야 한다.

---

## 이 문서의 사용법

이 문서는 **면접용 마인드맵**을 따라 선형으로 펼친 구조다. 학습 순서 = 면접 답변 순서 = 백지에 그리는 순서.

1. **0장 마인드맵을 먼저 외운다** — 루트 한 문장 + 4가지 가지 + 각 가지의 키워드 3개.
2. **1~4장을 순서대로 학습한다** — 각 장이 마인드맵의 한 가지에 정확히 대응.
3. **5장 면접 워크플로우로 검증** — 질문을 보면 어느 가지로 가야 하는지 매핑.
4. **6장 꼬리질문으로 깊이 점검**.

---

## 0. 마인드맵 — 면접 종이에 그릴 그림

### 루트 한 문장 (anchor)

> **"JDK는 LTS(8/11/17/21) 중심으로 진화하며 각 LTS마다 언어/JVM/GC가 함께 변한다. 시니어는 변곡점 4개 (PermGen 제거, G1 default, ZGC production, Virtual Thread)를 알아야 한다."**

이 한 문장에서 모든 답변이 출발한다. 어떤 질문이 와도 이 문장부터 말하고 적절한 가지로 분기.

### 4개 가지 — 순서를 외운다

```
                  [ROOT: JDK 진화 = LTS별 변곡점 4개]
                                 │
        ┌──────────────┬─────────┴─────────┬──────────────┐
        │              │                   │              │
       ① LTS 4단계   ② 진화축          ③ 마이그레이션  ④ Future
       (역사)        (언어/GC/JVM)      (함정)         (Project)
        │              │                   │              │
     ┌──┼──┐        ┌──┼──┐            ┌───┼───┐       ┌──┼──┐
   8  11  17/21   언어 GC  JVM        8→11 11→17 17→21 Loom  Lilliput
   PermGen        Lambda  Parallel→  Module Encap  VT    Leyden
   →Metaspace     →Records→VT  G1→ZGC→GenZGC pinning   Valhalla
```

### 가지별 핵심 키워드 (각 가지 3개씩만)

| 가지 | 키워드 1 | 키워드 2 | 키워드 3 |
|---|---|---|---|
| **① LTS 4단계** | 8 = PermGen 제거 | 11 = G1 default | 17/21 = ZGC/VT |
| **② 진화축** | 언어 (Lambda→Records→VT) | GC (Parallel→G1→ZGC→GenZGC) | JVM (Module/AppCDS/Loom) |
| **③ 마이그레이션** | 8→11 = 가장 큰 jump | 11→17 = Strong Encap | 17→21 = VT pinning |
| **④ Future Project** | Loom (완료) | Leyden / Lilliput | Valhalla |

### 면접 답변 흐름

> 면접관 질문 → 루트 문장 → 질문에 맞는 가지 1개 선택 → 그 가지의 키워드 3개 순서대로 설명 → 듣는 사람의 관심에 따라 인접 가지로 확장

---

## 1. 가지 ①: LTS 4단계 — JDK 8/11/17/21

### 1.1 핵심 질문

> "JDK 8/11/17/21 각 LTS의 핵심 변화를 설명해보세요."

### 1.2 키워드 1 — JDK 8 (2014): PermGen 제거 + Lambda

**언어**:
- Lambda + Stream API — 사상 가장 큰 언어 변화.
- Method references, default methods in interfaces.

**JVM**:
- **PermGen → Metaspace** — class metadata가 Heap이 아닌 native memory로 이동. `PermGen OOM` 에러 사라짐.
- Tiered Compilation 기본 on.
- G1 사용 가능 (default 아님 — Parallel 유지).

**운영 위치**:
- 2026년 기준 여전히 가장 많은 production system이 8에 머묾.
- 2030 premier support 종료 — 마이그레이션 데드라인.
- 옛 라이브러리 호환성 좋음.

### 1.3 키워드 2 — JDK 11 (2018): G1 default + Module System

**언어**:
- `var` keyword (JDK 10에서).
- Switch expression (preview JDK 12).
- HTTP Client API 표준.

**JVM**:
- **G1 default GC** — Parallel에서 전환. 일반 서비스의 STW pause 안정화.
- **ZGC experimental** — 큰 Heap latency-critical 워크로드용.
- **Module System (JEP 261)** — JDK 9에서 도입, 11에서 안정. JEE 모듈 분리.
- **Nest-based access control (JEP 181)** — inner class private 접근.
- AppCDS — startup 단축.
- `jlink` 기반 작은 custom runtime.

**운영 위치**:
- 가장 많은 마이그레이션 target.
- Spring Boot 2.x 지원.
- 8 → 11이 가장 큰 jump (Module System 영향).

### 1.4 키워드 3 — JDK 17/21 (2021/2023): ZGC production + Virtual Thread

**JDK 17 (2021)**:

언어:
- **Sealed classes (JEP 409)** — `sealed permits A, B, C`. CHA 친화 → JIT inlining 향상.
- **Records (JEP 395)** — `record Point(int x, int y)`. Boilerplate 제거.
- **Pattern matching for instanceof (JEP 394)**.
- Text blocks.

JVM:
- **ZGC production-ready** (JDK 15부터). Sub-ms STW.
- **Strong encapsulation** — `sun.misc.Unsafe` 등 internal API 봉인. `--add-opens` 명시 필요.
- macOS/AArch64 정식 지원.
- Spring Boot 3 require.

**JDK 21 (2023)**:

언어:
- **Pattern matching for switch (JEP 441)**.
- **Record patterns (JEP 440)**.
- **Sequenced collections (JEP 431)**.

JVM:
- **Virtual Threads (JEP 444)** — Loom 프로젝트의 결실. 수십만 동시 thread 가능.
- **Generational ZGC (JEP 439)** — ZGC에 generation 추가. 같은 sub-ms pause로 throughput G1 동등.
- **Scoped Values (preview)** — VT 친화 ThreadLocal 대안.
- **Foreign Function & Memory API (preview, JEP 442)** — JNI 대체.

**운영 위치**:
- 신규 프로젝트 default = JDK 21.
- Virtual Thread + Spring Boot 3.2+ 조합이 현재 최선.

### 1.5 한눈에 보는 변곡점

```
JDK 8 ━━━━━━━ 11 ━━━━━━━ 17 ━━━━━━━ 21 ━━━━━━━ 25(예상)
2014        2018       2021       2023       2025

  │           │          │           │
PermGen      G1         ZGC        Virtual Thread
제거       default    production    Loom 완료
Metaspace  Module      Strong       GenZGC
Lambda     System      Encap        Pattern Switch
```

---

## 2. 가지 ②: 진화축 — 언어 / GC / JVM 인프라

### 2.1 핵심 질문

> "JDK 진화를 어떤 축으로 분류해서 외우나요?"

### 2.2 키워드 1 — 언어 진화 (Lambda → Records → VT)

| 시기 | 기능 | 의미 |
|---|---|---|
| JDK 8 | Lambda + Stream | 함수형 패러다임 도입. 컬렉션 처리 혁명. |
| JDK 10 | `var` | 지역 타입 추론. |
| JDK 14 | Switch expression | 표현식으로서 switch. |
| JDK 16 | Records | 불변 데이터 클래스. Boilerplate 제거. |
| JDK 17 | Sealed | 닫힌 상속. CHA 친화. |
| JDK 17 | Pattern matching (instanceof) | 타입 검사 + 변수 바인딩. |
| JDK 21 | Pattern matching (switch) | switch의 표현력 극대화. |
| JDK 21 | Virtual Thread | 동시성 모델 변화. |

**큰 흐름**: 보일러플레이트 줄이기 + 함수형/패턴 매칭 + 동시성 단순화.

### 2.3 키워드 2 — GC 진화 (Parallel → G1 → ZGC → GenZGC)

```
JDK 8       JDK 9/11      JDK 15        JDK 21
━━━━━       ━━━━━━━       ━━━━━         ━━━━━

Parallel    G1 default    ZGC           Generational
default     (8 GB+)       production    ZGC
            (CMS 제거       sub-ms       (G1 throughput
            예고 → 14)     <16TB         + ZGC pause)
                          STW
```

**핵심 흐름**:
1. **Parallel** — throughput만, pause는 큼. Batch용.
2. **G1** — pause 목표(MaxGCPauseMillis) 가능. 일반 서비스의 새 default.
3. **ZGC** — pause < 10ms (15부터), < 1ms (17부터). 큰 Heap latency-critical.
4. **Generational ZGC** — young/old 세대 도입. 같은 sub-ms로 G1 동등 throughput.

**시니어가 알아야 할 것**: 어느 GC를 언제 쓰는가는 [Chapter 04 GC](../04-garbage-collection/)와 [Chapter 12 Tradeoff](../12-tradeoff-master-table/)에서 풀버전.

### 2.4 키워드 3 — JVM 인프라 진화

| 변화 | 도입 | 의미 |
|---|---|---|
| **Tiered Compilation** | JDK 7+ (default JDK 8) | C1+C2 조합으로 startup + peak 동시 달성. |
| **Metaspace** | JDK 8 | PermGen 대체. Class metadata native memory로. |
| **Module System** | JDK 9 | jigsaw. JEE 분리, 강한 캡슐화 토대. |
| **AppCDS** | JDK 10 (commercial) → 12 (free) | Class metadata pre-shared. Startup 단축. |
| **JVMCI** | JDK 9 | 외부 JIT plugin. Graal 활용 기반. |
| **Container awareness** | JDK 10 | cgroup 인식. `-Xmx`가 container limit 반영. |
| **Strong encapsulation** | JDK 17 | `sun.misc.*` 봉인. `--add-opens` 명시. |
| **Virtual Thread** | JDK 21 | Loom. 동시성 모델 근본 변화. |
| **Generational ZGC** | JDK 21 | sub-ms + throughput 양립. |

---

## 3. 가지 ③: 마이그레이션 — 함정 + 절차

### 3.1 핵심 질문

> "JDK 마이그레이션 시 가장 자주 깨지는 게 뭔가요? 어떻게 진단·해결하나요?"

### 3.2 키워드 1 — 8 → 11 (가장 큰 jump)

**핵심 함정 5가지**:

1. **JEE 모듈 제거** — `javax.xml.bind`, `javax.annotation`, `javax.activation` 등이 JDK에서 사라짐. 별도 dependency 필요 (`jakarta.xml.bind-api`).
2. **`sun.misc.Unsafe` 직접 사용 코드** — 일부 deprecate, 일부 removed. Reflection 우회 라이브러리 깨짐.
3. **`--illegal-access`** — 9에서 `warn`, 점진적으로 strict로. 16에서 deny default. Reflection 깨짐.
4. **Tools 분리** — `jconsole`, `jvisualvm`, `javafx` 등이 JDK에서 분리. 별도 설치.
5. **Default GC 변경** — Parallel → G1. GC 옵션 재검토 필수.

**왜 가장 큰 jump인가**: Module System이 모든 internal API 접근을 봉인하기 시작. 옛 라이브러리들이 reflection으로 internal 접근하던 패턴이 일제히 깨짐.

### 3.3 키워드 2 — 11 → 17 (Strong Encapsulation)

**핵심 함정**:
- **Strong encapsulation** — `--add-opens java.base/java.lang=ALL-UNNAMED` 같은 명시 필요. Spring/Hibernate/Mockito가 reflection으로 internal 건드릴 때.
- **Removed**: Nashorn JavaScript engine, RMI Activation 등.
- **macOS/AArch64 native** — Apple Silicon 지원이 17부터 정식.

상대적으로 매끄러움 — 11에서 이미 Module System 준비가 끝났기 때문.

### 3.4 키워드 3 — 17 → 21 (Virtual Thread Pinning)

**핵심 함정**:
- **Virtual Thread + synchronized = pinning** — synchronized 블록 안에서 blocking I/O를 하면 carrier thread가 같이 block. 처리량 저하.
- **해결**: `synchronized` → `ReentrantLock`. 또는 JDK 24+ JEP 491 대기.
- **진단**: `-Djdk.tracePinnedThreads=full` 또는 JFR `jdk.VirtualThreadPinned`.

언어 변화는 상대적으로 매끄러움. 동시성 모델 변화의 함정이 핵심.

### 3.5 마이그레이션 절차 (100대 서비스 기준)

```
1. 호환성 검증
   ├── 모든 dependency가 target JDK 지원?
   ├── Build tool (Maven/Gradle plugin) 호환?
   └── Framework (Spring/Hibernate) 버전 호환?

2. 단계 결정
   ├── 보수적: 8 → 11
   ├── 중간:   8 → 17
   └── 적극적: 8 → 21 (한 번에)

3. Canary rollout
   ├── 1대 → metric 비교 (throughput, P99, RSS, GC)
   ├── 10% → metric 비교
   ├── 50% → metric 비교
   └── 100%

4. 롤백 계획
   ├── Container image 옛 버전 보관
   ├── 옵션 차이 문서화
   └── 즉시 복귀 가능 상태 유지
```

**시니어의 판단**: 가능하면 21로 한 번에. 마이그레이션 비용은 한 번뿐이고, VT/GenZGC/Pattern matching의 이점이 큼.

### 3.6 운영 분포 (2026)

```
JDK 8:  여전히 많음 (~50%) — 옛 enterprise, 2030 EOL 임박
JDK 11: 보편       (~30%)
JDK 17: 현 주류    (~15%)
JDK 21: 신규 프로젝트 (~10%, 증가 중)
```

2026~2030 사이 8 → 17/21 마이그레이션의 큰 물결.

---

## 4. 가지 ④: Future — Project 로드맵

### 4.1 핵심 질문

> "JDK 21 이후 주목할 프로젝트는 뭔가요?"

### 4.2 키워드 1 — Loom (완료, JDK 21)

- **결과물**: Virtual Threads + Continuations.
- **모델**: M:N (수많은 vthread → 적은 carrier OS thread).
- **약속**: Synchronous 코드 스타일로 수십만 thread 가능. "Colored function" 문제 해소.
- **남은 과제**: synchronized pinning (JDK 24+ JEP 491에서 해소 예정).
- **연결**: [Chapter 02-03 Stack & PC & Native](../02-runtime-data-areas/03-stack-pc-native.md)의 가지 ⑤ Virtual Thread.

### 4.3 키워드 2 — Leyden / Lilliput (진행 중)

**Project Leyden** — AOT compilation 표준화:
- 빠른 startup (JIT warmup 없이 native code 즉시 실행).
- GraalVM Native Image와 통합 방향.
- Class data + JIT data를 build time에 미리 준비.
- **목표**: Cold start 시대(serverless, microservice)에서 HotSpot이 경쟁력 유지.

**Project Lilliput** — 객체 헤더 압축:
- Mark Word 64 → 8 bit 압축.
- 객체 헤더 12 byte → 4 byte.
- Heap footprint 5~10% 절감.
- 작은 객체가 많은 워크로드 (수많은 String, Integer)에서 큰 효과.

### 4.4 키워드 3 — Valhalla (장기, 진행 중)

- **Value Types** — primitive처럼 동작하는 객체 (`new Point(1, 2)`가 stack/inline 저장).
- **Generic specialization** — `List<int>` 직접 사용 가능 (현재는 `List<Integer>` autoboxing).
- **의미**: 메모리 효율 + 성능 + 표현력 동시 향상.
- **JVM에 미치는 영향**: 객체 모델의 근본 변화. 가장 야심찬 프로젝트, 가장 오래 걸림.

### 4.5 Other Projects

| 프로젝트 | 상태 | 핵심 |
|---|---|---|
| **Panama** | 완료, JDK 22+ | Foreign Function & Memory API. JNI 대체. C 라이브러리 직접 호출 안전. |
| **Amber** | 완료, 각 LTS에 흡수 | Pattern matching, sealed, records 등 언어 표현력. |
| **Loom** | 완료 (JDK 21) | Virtual Thread. |
| **Leyden** | 진행 중 | AOT 표준화. |
| **Lilliput** | 진행 중 | Mark Word 압축. |
| **Valhalla** | 진행 중 (장기) | Value types. |

---

## 5. 면접 답변 워크플로우

### 5.1 질문 → 가지 매핑

| 면접 질문 | 진입 가지 | 인접 확장 |
|---|---|---|
| "JDK 8과 11의 차이는?" | ① LTS 4단계 | ③ 마이그레이션 함정 |
| "JDK 17/21에 새로 들어간 게 뭔가요?" | ① LTS 4단계 | ② 진화축 |
| "Virtual Thread는 어느 JDK?" | ① 21 | ④ Loom |
| "Default GC 변천?" | ② 진화축 (GC) | [Chapter 04] |
| "Module System은 왜 도입?" | ② 진화축 (JVM) | ③ 8→11 함정 |
| "8→11 마이그레이션의 함정?" | ③ 마이그레이션 | ② Module System |
| "신규 프로젝트는 어느 JDK?" | ① 21 + ③ 매트릭스 | ④ Future |
| "ZGC와 Generational ZGC 차이?" | ② GC 진화 | [Chapter 04] |
| "Loom 외에 주목할 프로젝트?" | ④ Future | — |

### 5.2 답변 템플릿

> **루트 문장 한 줄 → 해당 가지 키워드 3개 순서대로 → 듣는 사람 표정 보고 인접 가지로**

예: "JDK 8과 11의 차이는?"

> "JDK는 LTS 중심으로 진화하며 각 LTS마다 변곡점이 있습니다. 8과 11의 가장 큰 차이는 세 가지입니다.
> 첫째, **GC default 변경** — 8은 Parallel, 11은 G1. 일반 서비스의 STW 안정화.
> 둘째, **Module System** — 9에서 도입, 11에서 안정. JEE 모듈이 JDK에서 분리되었습니다. javax.xml.bind 같은 게 별도 dependency가 됩니다.
> 셋째, **언어 기능** — `var`, HTTP Client API, switch expression 등.
> 마이그레이션 함정은 주로 두 번째에서 나옵니다. sun.misc.Unsafe 직접 사용 코드, illegal-access reflection 등이 깨집니다."

→ 면접관이 "그럼 17로 점프하면?"이면 가지 ③의 17→21로, "Module System은 왜?"면 가지 ②의 JVM 진화로.

---

## 6. 꼬리질문 트리 (가지별)

### Q1 [가지 ①]. JDK 8의 가장 큰 변화는?

> Lambda + Stream API (언어), PermGen → Metaspace (JVM). PermGen은 Heap 영역으로 class metadata를 두던 옛 설계로 `PermGen OOM` 에러의 원흉이었음. Metaspace는 native memory로 옮겨 동적 클래스 로딩이 많은 시스템(JSP, Groovy)에서 안정성 향상.

**🪝 Q1-1: Metaspace는 무한히 자라나요?**
> 기본은 unlimited. `-XX:MaxMetaspaceSize`로 제한. 안 잡으면 native memory leak 시 호스트 전체 OOM 위험.

### Q2 [가지 ①]. JDK 21에서 가장 큰 변화는?

> 두 가지: Virtual Thread (JEP 444) + Generational ZGC (JEP 439). VT는 동시성 모델 변화 (수십만 thread 가능, sync 코드 스타일 유지). GenZGC는 sub-ms pause를 유지하면서 G1 동등 throughput.

**🪝 Q2-1: Virtual Thread를 도입하면 항상 좋은가요?**
> No. I/O bound에서 좋고, CPU bound에서는 platform thread가 나음. synchronized 안에서 blocking I/O 하면 pinning으로 처리량 저하. JDK 24+ 해소 예정 (JEP 491).

### Q3 [가지 ③]. 8 → 11 마이그레이션의 가장 큰 함정은?

> 5가지: (1) JEE 모듈 제거 (`javax.xml.bind` 등 별도 dependency), (2) `sun.misc.Unsafe` 일부 deprecate, (3) `--illegal-access` 점진적 strict, (4) Tools 분리 (jconsole 등), (5) Default GC Parallel → G1. 모두 Module System의 영향.

**🪝 Q3-1: 점진적 마이그레이션이 더 안전하지 않나?**
> 마이그레이션 비용은 한 번뿐. 21로 한 번에 가는 게 VT/GenZGC/Pattern matching 이점 + 2030 EOL 회피로 ROI가 좋음. 단, dependency 호환성 확인이 전제.

### Q4 [가지 ②]. Default GC가 Parallel → G1으로 바뀐 이유는?

> Parallel은 throughput 최적이지만 STW pause가 큼 (수백 ms). 일반 web service에서 P99 latency가 받아들이기 어려움. G1은 `MaxGCPauseMillis` 목표를 가지고 region 단위로 incremental하게 동작 → pause 안정화. 11에서 default가 된 이유.

### Q5 [가지 ②]. Module System이 도입된 이유는?

> 두 가지: (1) JDK 자체 모듈화 — `jlink`로 작은 custom runtime 만들기, (2) Strong encapsulation — internal API(`sun.*`) 접근 차단, 호환성 약속 명확화. 결과: 작은 footprint + 안전한 진화.

**🪝 Q5-1: 일반 application에서 모듈 시스템을 꼭 써야 하나?**
> No. application은 그냥 classpath로 써도 됨. 단 JDK internal에 reflection 접근하면 `--add-opens` 명시 필요.

### Q6 [가지 ④]. Loom 외에 주목할 Project는?

> Leyden (AOT 표준화 — cold start), Lilliput (Mark Word 압축 — Heap footprint), Valhalla (Value types — primitive 객체). Leyden은 GraalVM Native Image와 통합 방향. Lilliput은 작은 객체 많은 워크로드에 효과. Valhalla는 가장 야심차고 가장 오래 걸림.

### Q7 (Killer) [가지 ③]. 8에서 운영 중인 100대 규모 서비스를 어느 JDK로 마이그레이션할지?

> 단계적 접근:
>
> 1. **호환성 검증** — 모든 dependency가 target JDK 지원? Build tool, framework 호환?
> 2. **단계 결정** — 보수적(11) / 중간(17) / 적극적(21).
> 3. **권장: 21로 한 번에** (가능하면) — 마이그레이션 비용은 한 번, VT/GenZGC/Pattern matching 이점, 2030 EOL 회피.
> 4. **Canary**: 1대 → staging → 25% → 50% → 100%. 각 단계 metric 비교 (throughput, P99, RSS, GC).
> 5. **롤백 계획**: 문제 시 즉시 옛 버전 복귀.

**🪝 Q7-1: 메트릭 비교에서 무엇을 봐야?**
> Throughput (RPS), P99 latency, RSS (특히 GC default 변경 영향), GC pause 분포 (jdk.GarbageCollection JFR 이벤트), Code Cache 사용량 (Tiered 동작 변경). 모든 차이를 root cause까지 추적.

---

## 7. 학습 체크리스트

면접 전 백지에서 다음을 다 해낼 수 있어야 마스터:

- [ ] 0장 마인드맵을 종이에 1분 이내로 그릴 수 있다 (루트 + 4가지 + 각 키워드 3개)
- [ ] 가지 ① LTS: 8/11/17/21 각각의 변곡점 1줄로 말한다 (PermGen / G1 / ZGC / VT)
- [ ] 가지 ② 진화축: 언어/GC/JVM 각각의 흐름을 1줄로 말한다
- [ ] 가지 ③ 마이그레이션: 8→11 함정 5가지를 외운다
- [ ] 가지 ③ 마이그레이션: 17→21에서 VT pinning 시나리오를 설명한다
- [ ] 가지 ④ Future: Loom/Leyden/Lilliput/Valhalla 각자 한 줄 정의
- [ ] 100대 마이그레이션 절차 5단계를 말한다
- [ ] 7장 꼬리질문 7개에 막힘없이 답한다

---

## 다음 단계

- → [Chapter 07. HotSpot Internals](../07-hotspot-internals/): JVM 구현 소스 투어
- → [Chapter 08. GraalVM](../08-graalvm/): AOT/Native Image 대안
- → [Chapter 10. Ops Scenarios](../10-ops-scenarios/): 실전 운영
- ← [Chapter 04. GC](../04-garbage-collection/): GC 진화 풀버전
- ← [Chapter 02-03. Stack & VT](../02-runtime-data-areas/03-stack-pc-native.md): Virtual Thread 풀버전

## 참고

- **JEP Process**: https://openjdk.org/jeps/0
- **Oracle JDK Release Notes**: https://www.oracle.com/java/technologies/javase/jdk-relnotes-index.html
- **Java Almanac**: https://javaalmanac.io/
- **JEP 444 Virtual Threads**: https://openjdk.org/jeps/444
- **JEP 439 Generational ZGC**: https://openjdk.org/jeps/439
- **JEP 491 Synchronize Virtual Threads without Pinning**: https://openjdk.org/jeps/491
- **OpenJDK Projects**: https://openjdk.org/projects/
