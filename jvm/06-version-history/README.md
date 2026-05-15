# 06. Version History — JDK 8/11/17/21+ 마스터 타임라인

> JDK 8 (2014) 부터 30년의 진화. LTS 중심 + 운영 영향 중심.
> 시니어가 알아야 할 것: 어느 JDK가 현재 운영에 적합한가 + 마이그레이션 시 무엇이 깨지는가.

---

## 🗺️ 위치

![timeline](./_excalidraw/timeline.svg)

---

## 📍 학습 목표

1. **LTS 4개**: JDK 8 / 11 / 17 / 21 의 핵심 변화.
2. **언어 기능 진화**: Lambda → var → Records/Sealed → Virtual Thread.
3. **GC 변천**: Parallel → G1 → ZGC → Generational ZGC.
4. **JVM 인프라**: Tiered Compilation → Module System → AppCDS → Loom.
5. **마이그레이션 함정**: 8→11이 가장 큰 jump (Module System).
6. **현재 (2025) 운영 분포**: 11/17이 보편, 21이 신규.
7. **Project 마스터**: Loom, Lilliput, Leyden, Valhalla.
8. **Native Image (GraalVM)** 의 위치.
9. **2030 JDK 8 EOL** 대비 마이그레이션 계획.
10. JDK 선택 결정 매트릭스.

---

## 🎨 LTS 4단계 핵심

### JDK 8 (2014) — 옛 LTS, 여전히 가장 많이 운영 중

**언어**:
- Lambda + Stream API (사상 가장 큰 변화).
- Method references, default methods in interfaces.

**JVM**:
- **PermGen 제거 → Metaspace**.
- Tiered Compilation 기본 on.
- G1 사용 가능 (default 아님 — Parallel 유지).

**운영**:
- 가장 많은 production system이 여전히 여기.
- 2030 premier support 종료 → 마이그레이션 시급.
- 옛 라이브러리 호환성 좋음.

### JDK 11 (2018) — 현 보편 LTS

**언어**:
- `var` keyword (10에서).
- Switch expression (preview 12).
- HTTP Client API (표준).

**JVM**:
- **G1 default GC**.
- **ZGC experimental**.
- **Nest-based access control** (JEP 181) — inner class private 접근.
- Application Class Data Sharing (AppCDS).
- 작은 footprint (`jlink` 기반 custom runtime).

**운영**:
- 가장 많은 마이그레이션 target.
- Spring Boot 2.x 지원.
- 8 → 11이 가장 큰 jump (Module System 영향).

**8 → 11 마이그레이션 함정**:
- `sun.misc.Unsafe` 사용 코드 — 일부 깨짐.
- `--illegal-access=warn` → 점진적 deprecate.
- JEE 모듈 제거 (`javax.xml.bind`, `javax.activation` 등) — 별도 dependency.
- Tools 분리 (`jconsole`, `jvisualvm` 등).

### JDK 17 (2021) — 현 주류 LTS

**언어**:
- **Sealed classes** (JEP 409) — `sealed permits A, B, C`.
- **Records** (JEP 395) — `record Point(int x, int y)`.
- **Pattern matching for instanceof** (JEP 394).
- Text blocks.

**JVM**:
- **ZGC production-ready** (15에서).
- **Strong encapsulation of JDK internals** — `--add-opens` 명시 필요.
- macOS/AArch64 정식 지원.
- `random()` 개선.

**운영**:
- Spring Boot 3 require.
- 안정 + 최신 기능.
- Latency-critical 시스템은 ZGC 검토.

**11 → 17 마이그레이션**:
- 비교적 매끄러움.
- Strong encapsulation 영향 — `--add-opens` 필요한 라이브러리.

### JDK 21 (2023) — 차세대 LTS

**언어**:
- **Pattern matching for switch** (JEP 441).
- **Record patterns** (JEP 440).
- **Sequenced collections** (JEP 431).

**JVM**:
- **Virtual Threads (Loom)** (JEP 444) ★.
- **Generational ZGC** (JEP 439).
- **Scoped Values** (preview) — VT 친화 ThreadLocal 대안.
- **Foreign Function & Memory API** (preview, JEP 442).

**운영**:
- 신규 프로젝트의 default 권장.
- Virtual Thread + Spring Boot 3.2+ 조합.
- 가장 진보된 GC (Generational ZGC).

**17 → 21 마이그레이션**:
- 매끄러움.
- VT 도입 시 라이브러리 호환성 확인 (synchronized + I/O = pinning).

### JDK 25 (예상 2025) — 다음 LTS

**예상 핵심**:
- **synchronized pinning 해소** (JEP 491).
- **Project Lilliput** stable (Mark Word 압축, footprint ↓).
- **Vector API stable**.
- **Project Leyden** 진전 (AOT, startup 빠르게).
- **Project Valhalla** preview (value types).

---

## 🏢 현재 (2026) 운영 분포

```
JDK 8:  여전히 많음 (50%?) — 옛 enterprise
JDK 11: 보편 (30%)
JDK 17: 현 주류 (15%)
JDK 21: 신규 프로젝트 (10%, 증가 중)
```

→ 2026~2030 사이 8 → 17/21 마이그레이션 큰 물결 예상.

---

## 🛠️ 마이그레이션 체크리스트

### 모든 마이그레이션

1. **Dependency**: 모든 라이브러리가 target JDK 지원?
2. **GC 옵션**: 옛 deprecated 옵션 제거.
3. **JVM 옵션**: 새 권장 옵션 적용.
4. **Build tool**: Maven/Gradle plugin 호환.
5. **CI/CD**: Build container, runtime container.

### 8 → 11 (가장 큰 jump)

- `sun.misc.Unsafe` 직접 사용 금지 권장.
- JEE 모듈 (`javax.*.bind` 등) 별도 dependency.
- `--illegal-access` 점진 도입.

### 11 → 17

- Strong encapsulation: `--add-opens` 필요 시.
- Removed: Nashorn JavaScript engine (옛 옵션).

### 17 → 21

- 비교적 매끄러움.
- VT 도입 시 pinning 측정.

---

## ⚖️ JDK 선택 매트릭스

```
┌────────────────────────┬─────────────────┐
│ 워크로드/조건           │ 권장 JDK        │
├────────────────────────┼─────────────────┤
│ 신규 프로젝트            │ JDK 21          │
│ 기존 8 → 마이그레이션   │ JDK 11 또는 17  │
│ Spring Boot 3+         │ JDK 17+        │
│ Spring Boot 2          │ JDK 8/11/17    │
│ Virtual Thread 활용     │ JDK 21+         │
│ ZGC                     │ JDK 17+ (stable)│
│ Generational ZGC        │ JDK 21+         │
│ Native Image (GraalVM)  │ 모든 JDK        │
│ Latency-critical        │ JDK 17/21 + ZGC │
│ Cloud cost ↓            │ JDK 21 + Native │
└────────────────────────┴─────────────────┘
```

---

## 🚀 Project 마스터

### Loom (완료, JDK 21)
- Virtual Threads + Continuations.
- M:N 모델.
- Synchronous 코드로 수십만 thread.

### Lilliput (진행 중)
- Mark Word 64 → 8 bit 압축.
- 객체 헤더 12 byte → 4 byte.
- Heap footprint 5~10% 절감.

### Leyden (진행 중)
- AOT compilation 표준화.
- 빠른 startup (JIT warmup 없이).
- GraalVM Native Image와 통합 방향.

### Valhalla (장기, 진행 중)
- Value Types (primitive 객체).
- Generic specialization (`List<int>` 가능).
- 메모리 효율 + 성능.

### Panama (완료, JDK 22+)
- Foreign Function & Memory API.
- JNI 대체.
- C 라이브러리 직접 호출 안전.

### Amber (완료, 각 LTS에 흡수)
- Pattern matching, sealed, records 등.
- 언어 표현력 ↑.

---

## ⚔️ 꼬리질문

### Q1. 8 → 11 마이그레이션의 가장 큰 함정은?

> 1. JEE 모듈 제거 (`javax.xml.bind`, `javax.annotation` 등) — 별도 dependency.
> 2. `sun.misc.Unsafe` 직접 사용 코드 — 일부 deprecate.
> 3. `--illegal-access=warn` → 점진적 strict.
> 4. Tools 분리 (jconsole 등 별도).
> 5. Default GC 변경 (Parallel → G1) — 옵션 재검토.

### Q2. JDK 21을 신규 프로젝트에 권장하는 이유는?

> 1. **Virtual Threads** — I/O bound 코드 폭발적 동시성.
> 2. **Generational ZGC** — sub-ms STW + G1 동등 throughput.
> 3. **Pattern matching for switch** — 코드 표현력 ↑.
> 4. **Sealed classes** — CHA 친화 + JIT 최적화 향상.
> 5. **LTS** — 장기 지원.
> 6. Spring Boot 3.2+, modern 라이브러리 친화.

### Q3. (Killer) 8에서 운영 중인 100대 규모 서비스를 어느 JDK로 마이그레이션할지?

> 단계적 접근:
> 
> 1. **호환성 검증**:
>    - 모든 dependency가 11+ 지원?
>    - Build tool, framework 호환?
> 
> 2. **단계 결정**:
>    - 보수적: 8 → 11 (가장 작은 jump).
>    - 적극적: 8 → 17 (한 번에).
>    - 최신: 8 → 21 (가장 큰 jump, VT 활용).
> 
> 3. **권장**: 21로 한 번에 (가능하면).
>    - 마이그레이션 비용 = 한 번.
>    - VT, Generational ZGC, Pattern matching 등 신기능 활용.
>    - 2030 EOL 회피.
> 
> 4. **실행**:
>    - Canary 1대 → staging → 25% → 50% → 100%.
>    - 각 단계 메트릭 비교 (throughput, P99, footprint, GC).
> 
> 5. **롤백 계획**: 문제 시 즉시 옛 버전 복귀.

---

## 🔗 다음 단계

- → [Chapter 07. HotSpot Internals](../07-hotspot-internals/)
- → [Chapter 08. GraalVM](../08-graalvm/)
- → [Chapter 10. Ops Scenarios](../10-ops-scenarios/)

## 📚 참고

- **JEP Process**: https://openjdk.org/jeps/0
- **Oracle JDK Release Notes**: https://www.oracle.com/java/technologies/javase/jdk-relnotes-index.html
- **Java Almanac**: https://javaalmanac.io/
