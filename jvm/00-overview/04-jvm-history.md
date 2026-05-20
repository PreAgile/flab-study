# 04. JVM 역사 — 30년 진화, "왜" 중심으로

> 역사를 모르면 "왜 PermGen이 사라졌나", "왜 G1이 나왔나", "왜 Module System이 필요했나"에 답할 수 없다.
> 현재의 설계는 과거의 상처다. 각 결정의 **트리거가 된 사건**을 기억하라.
> "JDK X에서 Y가 추가됐다"고만 말하지 말고 **"무슨 문제를 풀기 위해 Y가 만들어졌는가"**를 말하면 한 단계 위로 보인다.

---

## 이 문서의 사용법

이 문서는 면접용 마인드맵을 따라 선형으로 펼친 구조다. 학습 순서 = 면접 답변 순서 = 백지에 그리는 순서.

1. **0장 마인드맵을 먼저 외운다** — 루트 한 문장 + 5가지 가지 + 각 가지의 키워드 3개.
2. **1~5장을 순서대로 학습한다** — 각 장이 마인드맵의 한 가지에 정확히 대응.
3. **6장 면접 워크플로우로 검증** — 질문을 보면 어느 가지로 가야 하는지 매핑.
4. **7장 꼬리질문으로 깊이 점검**.

---

## 0. 마인드맵 — 면접 종이에 그릴 그림

### 루트 한 문장 (anchor)

> **"JVM 30년은 3시대로 나뉜다 — 1기(1991~2005) 'Java is Slow'를 JIT으로 극복, 2기(2006~2017) Oracle 인수와 4년 공백 후 Java 8 함수형으로 폭발, 3기(2018~) 6개월 주기 + GC 혁신 + 클라우드 적응. 각 변화는 '시대의 화두에 대한 응답'이고, 그 화두를 모르면 설계 의도를 못 본다."**

이 한 문장에서 모든 답변이 출발한다. 어떤 질문이 와도 이 문장부터 말하고 적절한 가지로 분기.

### 5개 가지 — 순서를 외운다

```
                  [ROOT: JVM 30년 = 3시대 × 5축의 진화]
                                  │
       ┌─────────┬────────┬───────┼────────┬──────────┐
       │         │        │       │        │          │
      ① 3시대   ② 언어/   ③ GC   ④ JIT   ⑤ 라이선스
                  Runtime  진화    진화      /배포
       │         │        │       │        │
       │      ┌──┼──┐    Serial   Sun JIT  Sun→Oracle
    1기     1.0  5  8     Parallel HotSpot  OpenJDK
    Slow    1.4 21         CMS    C1+C2    BCL→
    →JIT   2.0    LTS     G1     Tiered   No-Fee
    2기                    ZGC              Temurin/
    공백후                Shenandoah        Corretto/
    Lambda                Generat'l ZGC     Zulu
    3기                                    GraalVM
    클라우드
```

### 가지별 핵심 키워드

| 가지 | 키워드 1 | 키워드 2 | 키워드 3 |
|---|---|---|---|
| **① 3시대** | 1기 1991~2005 "느림" | 2기 2006~2017 "정체→폭발" | 3기 2018~ "모던 Java" |
| **② 언어/Runtime** | Java 1.0 (1996) | Java 5/8 (Generics/Lambda) | Java 21 (Virtual Thread) |
| **③ GC 진화** | Serial → Parallel → CMS | G1 (region 기반) | ZGC / Shenandoah / Gen ZGC |
| **④ JIT 진화** | Sun JIT (1998) | HotSpot C1/C2 (1999/2000) | Tiered (JDK 7→8) |
| **⑤ 라이선스/배포** | OpenJDK (2006, GPLv2) | Oracle BCL 폭탄 (2018) | No-Fee + Temurin/Corretto |

### 면접 답변 흐름

> 면접관 질문 → 루트 문장 → 질문에 맞는 가지 1개 선택 → 그 가지의 키워드 3개 순서대로 설명 → 듣는 사람의 관심에 따라 인접 가지로 확장

"왜 PermGen 사라졌나?" → ② Java 8. "CMS 왜 죽었나?" → ③. "Virtual Thread 왜?" → ② Java 21. "JDK 11 라이선스 문제?" → ⑤.

---

## 1. 가지 ①: 3시대 — JVM 30년의 큰 흐름

### 1.1 핵심 질문

> "Java 30년을 한 호흡에 정리하면?"

### 1.2 키워드 1 — 1기 (1991~2005): "Java is Slow" 시대

**시대 정신**: "C++ 너무 위험 → GC + Bytecode 검증" + "C++과의 속도 격차 좁히기".

- **1991 Green Project** (Sun, James Gosling) — 가전/셋톱박스용 언어 Oak. C++은 플랫폼별 컴파일 + 메모리 위험. 가전 CPU가 너무 다양 → "bytecode + interpreter" 답.
- **1995 Java 1.0** — Mosaic/Netscape 인터넷 붐 만나 방향 전환. **applet**으로 "웹 동적 콘텐츠" 시도. pure interpreter, C++ 대비 20~50배 느림.
- **1996 JDK 1.0 (Classic VM)** — 스택 기반 인터프리터, AWT.
- **1997 Sun, Animorphic 인수** — Strongtalk VM 만든 팀 영입. 후에 HotSpot 핵심 개발자 (Lars Bak이 V8 만든 사람).
- **1999 HotSpot 1.0 (JDK 1.3)** — JIT 등장. **"10%의 코드가 90% 실행 시간을 차지한다"** (Pareto). 그 10%만 컴파일하면 충분.
- **2002 JDK 1.4** — Parallel GC, CMS GC, NIO, assert.
- **2004 Java 5** — Generics, Annotation, Autoboxing, Enhanced for, Enum, **JMM 명세화 (JSR-133)** — 멀티스레드 코드의 동작이 JVM 구현마다 달랐던 시대 종결.

이 시기까지 C++ 따라잡기. JSR-133 이후 모든 `java.util.concurrent`가 그 위에 만들어짐.

### 1.3 키워드 2 — 2기 (2006~2017): 오픈소스화와 정체 → 폭발

**시대 정신**: Sun 재정난 → Oracle 인수 → Apache Harmony 종말 → 그 후 Java 8 lambda로 폭발.

- **2006 OpenJDK 출범** — GPLv2 + Classpath Exception. IBM, Red Hat 등 합류. Apache Harmony는 의미 잃음.
- **2006 Java 6** — 성능 안정화. "이미 성숙한 언어" 평가.
- **2009 Sun 재정난** — 닷컴 버블 후유증, MySQL 인수. Java 개발 정체.
- **2010 Oracle, Sun 인수** — 56억 달러. Apache Harmony 종말 (Oracle이 TCK 접근 거부). Google과의 소송(Java API 저작권)은 10년 끌다 2021 대법원 Google 승소.
- **2011 Java 7** (4년 공백 후) — try-with-resources, diamond `<>`, multi-catch, **invokedynamic (JSR 292)** — JRuby/Scala용 새 bytecode → 나중에 Java 8 lambda의 인프라. **G1 GC experimental**.
- **2014 Java 8 LTS** — **현재까지도 가장 많이 쓰이는 버전**. Lambda + Stream + default method + Optional + java.time + **PermGen 제거 → Metaspace**. 함수형 패러다임 도입의 분기점.
- **2017 Java 9** — Module System (Jigsaw), jlink, JShell, **6개월 릴리스 주기 시작**.

### 1.4 키워드 3 — 3기 (2018~현재): 모던 Java

**시대 정신**: 클라우드 네이티브 + GC 혁신 + 동시성 모델 재발명.

- **2018.10 Oracle JDK 라이선스 폭탄** — JDK 11부터 상업적 사용 유료. 시장 충격. Temurin/Corretto/Zulu 폭발.
- **2018 Java 11 LTS** — HTTP Client, **ZGC experimental**, Epsilon GC.
- **2020 Java 14, 15** — Records, Pattern Matching, Text Blocks, **CMS 제거 (JDK 14)**, ZGC production-ready (JDK 15).
- **2021 Java 17 LTS** — Sealed Classes, Pattern Matching for switch (preview), macOS M1 정식 지원, **Oracle JDK No-Fee Terms** 재무료화.
- **2022 JDK 19** — Virtual Threads (preview, Loom).
- **2023 Java 21 LTS** — **Virtual Thread stable**, **Generational ZGC**, Record Patterns, Sequenced Collections.
- **2024 JDK 22+** — Foreign Function & Memory API stable (Panama), Class File API.
- **2025 Java 25 LTS (예정)** — Project Leyden (AOT 가속), Valhalla (value types).

### 1.5 한눈에 보는 마일스톤 테이블

| 연도 | 릴리스 | 핵심 이유 |
|---|---|---|
| 1995 | Java 1.0 발표 | applet으로 웹 동적 콘텐츠 |
| 1996 | JDK 1.0 GA | 첫 정식 JVM |
| 1999 | JDK 1.3 (HotSpot) | JIT으로 성능 격차 좁힘 |
| 2002 | JDK 1.4 | NIO, Parallel/CMS GC |
| 2004 | Java 5 | Generics, JMM (JSR-133) |
| 2006 | Java 6 / OpenJDK | 오픈소스화 |
| 2011 | Java 7 | invokedynamic, G1 (exp) |
| 2014 | Java 8 LTS | Lambda, Stream, Metaspace |
| 2017 | Java 9 | Module System, 6개월 주기 |
| 2018 | Java 11 LTS | HTTP Client, ZGC (exp), 라이선스 격동 |
| 2021 | Java 17 LTS | Sealed, Pattern matching, No-Fee |
| 2023 | Java 21 LTS | Virtual Thread, Generational ZGC |

---

## 2. 가지 ②: 언어/Runtime — 메이저 릴리스의 "왜"

### 2.1 핵심 질문

> "Java 8/9/17/21의 메이저 변화를 그 동기와 함께 설명?"

### 2.2 키워드 1 — Java 8 (2014): 함수형 + Metaspace

> 가장 많이 채택된 LTS. 모든 면접의 기준.

- **Lambda + Stream API** — 함수형 패러다임. 5년 작업(Brian Goetz, Project Lambda 2009 시작).
- **default method** — Stream과 기존 Collection 통합용. 인터페이스에 구현체 가능.
- **Optional, java.time** — null 안전성, Date/Calendar 악몽 종결.
- **PermGen 제거 → Metaspace (JEP 122)** — PermGen은 크기 고정으로 OOM 빈번 (Spring AOP, Hibernate proxy 등 동적 클래스). Metaspace는 Heap 밖 native + ClassLoader chunk 단위.
- **Nashorn** — JavaScript 엔진 (나중에 GraalVM JS로 대체, JDK 15에서 제거).

**왜 함수형?**: 멀티코어 시대 + 빅데이터(Stream/Map-Reduce 패턴) 적응. 그리고 익명 클래스의 boilerplate 해소.

### 2.3 키워드 2 — Java 9 (2017): Module System + 6개월 주기

- **JPMS (JEP 261)** — `module-info.java`로 명시적 의존성/공개 패키지. **왜**: `rt.jar` 60MB 비대화, 임베디드/IoT 부담, 내부 API 누출 (`sun.misc.*` 같은 것).
- **JEP 282 jlink** — 필요한 모듈만 골라 커스텀 런타임 빌드 → 표준 JRE 별도 배포 축소. JRE **개념 자체는 살아있음**, Oracle은 JDK 11부터 standalone JRE 배포 중단.
- **JShell** — REPL.
- **6개월 릴리스 주기 시작** — 그 전 3~5년 메이저. **왜**: "전부 다 들어가야 한다"는 압박 → 일정 슬립 (Java 8이 lambda 때문에 1.5년 지연, 9가 Module 때문에 2년 지연). 6개월 = 준비된 기능만 들어가고 나머진 다음. LTS는 2~3년에 한 번 (11, 17, 21, 25).

### 2.4 키워드 3 — Java 17 LTS (2021): Strong Encapsulation

> Java 8 다음으로 가장 많이 채택될 LTS. 많은 기업이 8 → 17로 점프.

- **Sealed Classes (JEP 409)** — `sealed`/`permits`로 상속 제한.
- **Pattern Matching for switch** preview, **Records** stable, **Text Blocks** stable.
- **JEP 396** — JDK internal API 기본 inaccessible. `sun.misc.Unsafe`, `jdk.internal.*` 접근 차단. Reflection으로 쓰던 라이브러리(Hibernate, Lombok 일부)가 깨짐.
- **JEP 411** — Security Manager deprecated for removal. 1995 애플릿 시대의 흔적 정리.
- **macOS AArch64 (M1) 정식 지원**.
- **Oracle JDK No-Fee Terms** — 다시 무료화 (2026까지 보장).

### 2.5 Java 21 LTS (2023): Virtual Thread

> 클라우드 시대를 위한 LTS.

- **JEP 444 Virtual Threads stable** — OS 스레드 1:1 매핑 종결. JVM이 직접 스케줄링. 100만 vthread 가능.
- **JEP 441 Pattern Matching for switch** stable.
- **JEP 440 Record Patterns** stable.
- **JEP 439 Generational ZGC** — ZGC가 Young/Old 분리. ZGC + 일반 워크로드 효율 ↑.
- **JEP 451 Sequenced Collections** — `List`/`Deque`에 일관된 first/last API.

**Virtual Thread의 작동 원리**: blocking I/O 직전에 현재 stack을 Heap으로 swap-out (Continuation 저장) → carrier thread 해제. I/O 완료 시 다른 carrier에서 swap-in.

**Pinning** 한계: `synchronized` 블록 안, JNI 안에선 unmount 불가. JDK 24 (JEP 491)에서 synchronized pinning 해결.

### 2.6 8 → 17 마이그레이션 함정

1. **Strong Encapsulation** — `sun.misc.Unsafe`, `jdk.internal.*` 접근 막힘. `--add-opens` 회피.
2. **Removed API** — Nashorn, Java EE 모듈(`java.xml.ws`, `javax.activation`) 삭제. 별도 dependency 추가.
3. **Default GC 변경** — Parallel → G1. tuning 달라짐.
4. **reflection default deny** — `--illegal-access=permit` 옵션 사라짐.

깨지는 라이브러리: Hibernate 5.x → 6.x, Lombok 1.18.22+, Mockito 4.x+, MapStruct 1.5.x+, Spring 5.3+ (6.x는 JDK 17 필수). 진단: `jdeps --jdk-internals my-app.jar`.

---

## 3. 가지 ③: GC 진화 — Serial → Generational → Region → Colored Pointer

### 3.1 핵심 질문

> "GC 30년 진화를 시대 흐름으로 설명? CMS는 왜 죽었나?"

### 3.2 키워드 1 — Serial → Parallel → CMS (멀티코어 시대)

**Serial (1996)** — Single-threaded mark-sweep. STW 동안 전부 정지.

**Parallel (2002, JDK 1.4)** — Young Gen을 멀티스레드로 수집. CPU 코어 활용 → 처리량 ↑.

**CMS (2002, JDK 1.4)** — Old Gen 동시 마킹. STW ↓.

**Generational GC**의 핵심: **Weak Generational Hypothesis** — "대부분의 객체는 일찍 죽는다". Young만 자주 수집하면 충분. Eden(allocation) + Survivor(생존자 임시) + Old(살아남은 자) 구조.

### 3.3 키워드 2 — G1 (region 기반, 예측 가능한 STW)

**G1 (2012, JDK 7u4 → 2017 JDK 9 기본)** — Heap을 region(1~32MB)으로 쪼개고, **쓰레기 많은 region만** 골라 수집. STW 시간 예측 가능.

- `-XX:MaxGCPauseMillis=200` 같은 옵션으로 목표 STW 지정.
- **PausePrediction** 모듈이 이전 GC 통계(region copy 비용, RSet 스캔 비용)를 EMA/linear regression으로 누적.
- 새 GC 결정 시 이 모델로 "X개 region을 수집하면 Y ms" 예측.
- Hard guarantee 아님 — "최선의 노력".

**CMS의 짧은 생애 — 왜 죽었나** (JDK 9 deprecated, JDK 14 제거):
1. **Concurrent Mode Failure** — 동시 마킹 중 Old gen 꽉 차면 Serial Old GC로 fallback → 매우 긴 STW.
2. **압축 안 함** — mark-sweep만. fragmentation 누적되어 큰 객체 OOM 위험.
3. **유지보수 부담** — HotSpot에서 가장 복잡한 GC 코드.
4. **G1이 완성** — 동시 마킹 + 압축 + 예측 가능성 모두 제공.

### 3.4 키워드 3 — ZGC / Shenandoah / Generational ZGC

**ZGC (2018 JDK 11 experimental → 2020 JDK 15 production)** — sub-ms pause 목표.
- **Colored Pointers** — 포인터의 unused bit를 색깔로 사용 (mark/remap).
- **Load Barrier** — 모든 reference load가 barrier를 거쳐 forwarding 처리.
- Self-healing — barrier가 옛 위치 → 새 위치로 forward + field 갱신.

**Shenandoah (2019 JDK 12, Red Hat)** — Brooks Pointer → Load Reference Barrier. 동시 압축.

**Generational ZGC (2023 JDK 21, JEP 439)** — ZGC가 Young/Old 분리. Weak Generational Hypothesis를 ZGC도 활용 → 일반 워크로드 효율 ↑.

### 3.5 GC 진화 한 그림

```
1996 │ Serial GC                — Single-threaded
1999 │ HotSpot 통합
2002 │ Parallel + CMS (JDK 1.4) — 멀티코어 + 동시 마킹
2012 │ G1 (JDK 7u4)             — Region 기반, 예측 가능
2017 │ G1이 기본 GC (JDK 9)
2018 │ ZGC experimental (JDK 11)— Colored Pointer + Load Barrier
2019 │ Shenandoah (JDK 12)
2020 │ CMS 제거 (JDK 14) / ZGC production (JDK 15)
2023 │ Generational ZGC (JDK 21)
```

---

## 4. 가지 ④: JIT 진화

### 4.1 핵심 질문

> "JIT의 진화를 설명? Sun JIT → HotSpot → Tiered."

### 4.2 키워드 1 — Sun JIT (1998): 확장된 인터프리터

```cpp
void compile_method(method* m) {
  for (bytecode bc : m->bytecodes) {
    emit_naive_assembly(bc);  // bytecode 한 줄마다 asm 한두 줄
  }
}
```

→ 기본적으로 "확장된 인터프리터". 빠르지만 최적화 없음.

### 4.3 키워드 2 — HotSpot Client (C1) + Server (C2)

**HotSpot 1.0 (1999, JDK 1.3)** — Animorphic의 Strongtalk VM 팀이 만듦. "Hot Spot" 의미: 자주 실행되는 코드만 컴파일.

- **Client VM (C1, 1999)** — 작고 빠른 JIT. 데스크탑 클라이언트 앱(스윙)용. HIR + LIR + Linear Scan RA.
- **Server VM (C2, 2000)** — 공격적 JIT. 서버용. **Sea of Nodes** (1999 Cliff Click 박사 논문) — Control flow와 Data flow가 한 그래프에 통합된 IR.

C2의 최적화 패스 (20개 이상):
```
Parse → IterGVN → PhaseIdealLoop (unrolling, vectorization)
     → Escape::do_analysis → PhaseMacroExpand
     → PhaseCFG::do_global_code_motion → PhaseChaitin::Register_Allocate
     → Output
```

### 4.4 키워드 3 — Tiered Compilation (JDK 7→8)

JDK 7 이전: `-client` 또는 `-server` 중 하나만.
JDK 7 (2011): Tiered 도입 (실험).
JDK 8 (2014): **기본 활성화**. C1과 C2가 한 JVM 안에 공존.

```
Level 0: Interpreter
Level 1: C1 no profile (trivial 메서드)
Level 2: C1 with counters (C2 큐 막힘 시)
Level 3: C1 full profile (MethodData 채움)
Level 4: C2 (profile-guided)
```

→ "빠른 1차 컴파일(C1) + 천천히 더 좋은 2차 컴파일(C2)" 파이프라인.

**GraalVM (2019)** — JVMCI(JEP 243)로 C2를 Graal JIT(Java로 작성)으로 교체. Partial Escape Analysis 등 C2보다 강력한 최적화. Native Image는 별도 SVM 런타임으로 AOT 지원.

---

## 5. 가지 ⑤: 라이선스/배포 — 격동의 OpenJDK 생태계

### 5.1 핵심 질문

> "Java 라이선스 변화와 OpenJDK 생태계 분화를 시대 흐름으로?"

### 5.2 키워드 1 — Sun → Oracle → OpenJDK

**2006 OpenJDK 출범** — Sun이 JDK를 GPLv2 (with Classpath Exception)로 공개. IBM, Red Hat 합류. Apache Harmony는 의미 잃음.

**2010 Oracle, Sun 인수** — 56억 달러. Apache Harmony 종말 (Oracle TCK 접근 거부). Google과의 Java API 저작권 소송 10년 끌다 2021 대법원 Google 승소.

이 시기까지 "Oracle JDK ≠ OpenJDK"였음 — Oracle JDK에 추가 상용 기능 (JFR, JMC).

### 5.3 키워드 2 — 2018 라이선스 폭탄 → 대안 빌드 폭발

**2018.09 Oracle JDK 11** — 상업적 사용 유료화. 무료는 6개월 보안 패치만. 시장 충격.

**대안 빌드 폭발**:
- **AdoptOpenJDK** (커뮤니티) → 2021 **Eclipse Adoptium / Temurin**으로 이전
- **Amazon Corretto** — 무료, 무제한, 장기 지원
- **Azul Zulu** — Azul Systems
- **SapMachine** — SAP
- **Red Hat OpenJDK** — RHEL용
- **Microsoft Build of OpenJDK** — Azure
- **Liberica JDK** — BellSoft

### 5.4 키워드 3 — 2021 No-Fee + GraalVM

**2019 GraalVM 1.0 GA** — Oracle Labs. Graal compiler (Java) + Native Image (AOT) + Truffle (polyglot).

**2021.09 Oracle JDK No-Fee** — JDK 17 LTS부터 다시 무료화 (2026까지 보장). 하지만 시장은 이미 분화. Temurin/Corretto 점유율이 매우 큼.

**2024 라이선스 추가 조정** — 항상 최신 약관 확인 필요.

### 5.5 시대별 화두 → JVM의 응답

| 시대 | 화두 | JVM 응답 |
|---|---|---|
| 90년대 | "C++ 너무 위험, 메모리 누수" | GC, Bytecode 검증 |
| 2000s 초 | "멀티코어 시대 도래" | Parallel GC, JMM, j.u.concurrent |
| 2000s 후 | "RIA, 동적 언어" | invokedynamic, scripting API |
| 2010s 초 | "Java is bloated" | Module System, Compact Profiles |
| 2010s 중 | "함수형, 빅데이터" | Lambda, Stream, ForkJoin |
| 2010s 후 | "GC pause 못 견딘다" | G1 기본, ZGC, Shenandoah |
| 2020s | "클라우드 네이티브, 콜드스타트" | GraalVM Native Image, Leyden |
| 2020s | "동시성 100만 연결" | Virtual Thread (Loom) |

---

## 6. 면접 답변 워크플로우

### 6.1 질문 → 가지 매핑

| 면접 질문 | 진입 가지 | 인접 확장 |
|---|---|---|
| "Java 30년을 요약?" | ① 3시대 | 전부 |
| "JDK 8과 17 차이?" | ② 언어/Runtime | ⑤ 라이선스 |
| "PermGen이 왜 사라졌나?" | ② Java 8 | ③ GC |
| "Module System 도입 이유?" | ② Java 9 | jlink |
| "Virtual Thread 왜?" | ② Java 21 | 클라우드 시대 |
| "8 → 17 마이그레이션 함정?" | ② Strong Encapsulation | jdeps |
| "CMS 왜 죽었나?" | ③ GC | G1 |
| "G1 'predictable STW' 의미?" | ③ G1 | PausePrediction |
| "ZGC가 어떻게 sub-ms?" | ③ ZGC | Colored Pointer |
| "HotSpot이 어떻게 등장?" | ④ JIT | Animorphic |
| "Tiered Compilation 의미?" | ④ JIT | C1+C2 협업 |
| "Sea of Nodes 뭐?" | ④ C2 | Cliff Click |
| "JDK 11 라이선스 문제?" | ⑤ 라이선스 | Temurin/Corretto |
| "GraalVM이 왜 등장?" | ⑤ 배포 | Native Image |

### 6.2 답변 황금 패턴

> "JDK X에서 Y가 추가됐다"고만 말하지 말고 **"무슨 문제를 풀기 위해 Y가 만들어졌는가"**를 같이 말하면 한 단계 위로 보인다.

예: "JDK 9에 Module System이 들어간 이유?"

> "**Java 30년은 3시대로 나뉘는데**, JDK 9는 2기 끝 3기 시작의 분기점입니다 (← 루트).
> JDK 9에 Module System(JPMS, JEP 261)이 들어간 이유는 **`rt.jar`가 60MB로 비대해지면서 임베디드/IoT 적합성이 떨어졌고**, `sun.misc.*` 같은 **내부 API가 무분별하게 노출되어 의존성 관리가 어려웠기** 때문입니다.
> Project Jigsaw가 그 답이고, 부수효과로 **jlink가 가능해져서 표준 JRE 별도 배포가 의미를 잃었습니다** — JRE 개념 자체가 사라진 건 아니고, '내 앱 전용 런타임 이미지'로 형태가 바뀐 거죠.
> 같은 시기에 **6개월 릴리스 주기**가 시작된 이유도 비슷합니다 — 그 전 3~5년 주기는 '전부 다 들어가야 한다'는 압박 때문에 일정 슬립이 잦았고(Java 8 lambda 1.5년 지연, 9 Module 2년 지연), 6개월 주기는 '준비된 기능만'으로 그걸 회피하는 답이었습니다."

---

## 7. 꼬리질문 트리 (가지별)

### Q1 [가지 ②]. JDK 8과 17의 가장 큰 차이?

> 언어: lambda는 이미 8에. 17은 sealed/records/pattern matching/text blocks. 런타임: 9의 Module System, GC가 G1 기본 (8은 Parallel), ZGC/Shenandoah production. 라이선스: 8 무료 → 11 유료 → 17 No-Fee.

**🪝 Q1-1: 8 → 17 마이그레이션 함정?**
> Strong Encapsulation (`--add-opens`), Removed API (Nashorn, Java EE 모듈), Default GC 변경, reflection default deny. Hibernate 5→6, Lombok 1.18.22+, Mockito 4+, Spring 5.3+. 진단: `jdeps --jdk-internals`.

### Q2 [가지 ③]. CMS GC는 왜 사라졌나?

> 네 가지. (1) Concurrent Mode Failure — Old gen 동시 마킹 중 가득 차면 Serial Old fallback → 매우 긴 STW. (2) 압축 안 함 — mark-sweep만, fragmentation 누적. (3) 유지보수 부담 — HotSpot 최복잡 GC. (4) G1이 완성. JDK 9 deprecated, JDK 14 제거.

**🪝 Q2-1: G1의 '예측 가능한 STW' 의미?**
> `-XX:MaxGCPauseMillis=200`으로 목표 STW 지정. G1은 region 단위 수집 → 동적으로 "이 STW에 몇 region 수집할지" 조정. PausePrediction 모듈이 이전 GC의 region copy/RSet 스캔 비용을 EMA로 누적, 새 GC에 예측 모델 적용. Hard guarantee 아닌 best effort.

### Q3 [가지 ②]. Virtual Thread는 왜 만들어졌고, 어떻게 동작?

> 그 전엔 OS 스레드 = Java 스레드 1:1. OS 스레드는 비싸다 (1MB 스택, context switch). 10,000 connection = 10GB 스택 → 비현실. Reactive Programming은 callback hell. Virtual Thread는 OS 스레드 의존을 끊고 JVM이 직접 스케줄링. 100만 vthread 메모리 GB 단위. 작동 원리: blocking I/O 직전에 stack을 Heap으로 swap-out(Continuation) → carrier thread 해제 → I/O 완료 시 다른 carrier에서 swap-in.

**🪝 Q3-1: swap-out 안 되는 케이스?**
> **Pinning**. (1) synchronized 블록 안 (JDK 21 기준, JDK 24 JEP 491에서 해결), (2) JNI/native 안. Pinning되면 carrier도 같이 막혀 효과 상실. 진단: `-Djdk.tracePinnedThreads=full`. 권장: synchronized → ReentrantLock.

### Q4 [가지 ①]. 6개월 릴리스 주기는 왜?

> 그 전 3~5년 주기는 "모든 기능 다 넣자" 압박 → 일정 슬립 (Java 8 lambda 1.5년 지연, 9 Module 2년 지연). 6개월은 "준비된 기능만, 나머진 다음 6개월". LTS는 2~3년 한 번 (11, 17, 21, 25)으로 prod 안정 베이스. preview/experimental feature가 활발해진 부수효과.

**🪝 Q4-1: preview vs experimental vs incubator?**
> **Preview**: 언어/API 기능. 명세 거의 완성, 피드백 단계. `--enable-preview`. Switch Expression/Records가 거침. **Experimental**: JVM 기능. ZGC가 11→15. `-XX:+UnlockExperimentalVMOptions`. **Incubator**: 새 모듈/API. `jdk.incubator.*` 패키지.

### Q5 (Killer) [가지 ④, ⑤]. 만약 당신이 JDK 22를 책임진다면 우선순위?

> 정답 없음, 논리 보는 질문. 워크로드에 따라.
> - **클라우드 네이티브**: GraalVM Native Image 표준화, Leyden 가속, FFM API 안정화.
> - **AI/ML**: Vector API stable (현재 incubator), JNI 대체.
> - **개발자 경험**: Pattern matching 완성, String Templates stable, Structured Concurrency (Loom + scope-based 에러).
> - **운영 효율**: Generational ZGC 완전화, JFR streaming, CRaC (Checkpoint Restore).
> 개인 의견으로는 **Structured Concurrency**가 가장 큰 잠재력 — Virtual Thread + scope-based 에러 처리로 동시성 모델 근본 단순화.

**🪝 Q5-1: Leyden과 GraalVM Native Image의 차이?**
> 둘 다 AOT지만. **GraalVM Native Image**: closed-world 가정. reflection/dynamic class loading을 빌드 시 명시. standalone 바이너리, JVM 없음. **Leyden**: partial AOT. JVM 위에서 동작하면서 가능한 부분만 미리 컴파일. JIT은 존재. dynamic 기능 보존. Leyden은 "Java 동적성 유지하며 startup만 가속" 노선 → Spring처럼 동적 로딩 많은 앱에 유리.

---

## 8. 학습 체크리스트

면접 전 백지에서 다음을 다 해낼 수 있어야 마스터:

- [ ] 0장 마인드맵을 종이에 1분 이내로 그릴 수 있다 (루트 + 5가지 + 각 키워드 3개)
- [ ] 가지 ① 3시대를 한 줄씩 구분하고 각 시대의 화두를 말한다
- [ ] 가지 ② JDK 8/9/17/21의 메이저 변화를 동기와 함께 말한다
- [ ] 가지 ② 8 → 17 마이그레이션 4가지 함정과 깨지는 라이브러리를 답한다
- [ ] 가지 ② Virtual Thread의 swap-out/in 메커니즘과 Pinning을 설명한다
- [ ] 가지 ③ GC 진화 한 그림 (Serial→Parallel→CMS→G1→ZGC→Generational ZGC)
- [ ] 가지 ③ CMS가 죽은 4가지 이유를 말한다
- [ ] 가지 ③ G1의 PausePrediction 모듈 동작을 설명한다
- [ ] 가지 ④ Sun JIT → HotSpot C1/C2 → Tiered의 진화를 말한다
- [ ] 가지 ④ Sea of Nodes의 의미와 Cliff Click의 1999 논문을 안다
- [ ] 가지 ⑤ 2018 라이선스 폭탄 + 대안 빌드 폭발 + 2021 No-Fee 흐름을 말한다
- [ ] 가지 ⑤ GraalVM의 등장 배경과 3가지 모드(JIT/Native Image/Truffle)를 설명한다

---

## 다음 단계

00-overview 챕터가 끝났다. 다음:
- **01-class-lifecycle**: ClassFile 포맷, ClassLoader, Linking 풀버전
- **02-runtime-data-areas**: Heap, Metaspace 깊이
- **03-execution-engine**: Interpreter, JIT 풀버전
- **04-gc**: 각 GC 알고리즘 + 구현
- **06-version-history**: 본 챕터의 풀버전 (각 JDK 버전 풀 JEP 분석)

## 참고

- **JEP Index**: https://openjdk.org/jeps/0
- **Java Almanac (모든 JDK 버전 비교)**: https://javaalmanac.io/
- **The History of Java Technology**: https://www.oracle.com/java/moved-by-java/timeline/
- **Brian Goetz on Project Lambda**: https://www.youtube.com/results?search_query=brian+goetz+lambda
- **Cliff Click on HotSpot history**: https://www.cliffc.org/blog/
- **JEP 444 Virtual Threads**: https://openjdk.org/jeps/444
- **JEP 491 Synchronize Virtual Threads without Pinning**: https://openjdk.org/jeps/491
