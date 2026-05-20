# 03. JVM 아키텍처 — 4대 서브시스템 큰 그림

> 이 챕터의 그림 하나가 머리에 박히면, 이후 모든 챕터(GC, Threading, JIT)가 "이 그림의 어느 박스 안 얘기"로 정리된다.
> 반대로 이 그림 없이 GC를 공부하면 그냥 알고리즘 잡학사전이 된다.
> 핵심은 **per-process vs per-thread** + **메모리는 Heap만이 아니다** + **GC는 Execution Engine이 아닌 별도 책임**의 세 통찰이다.

---

## 이 문서의 사용법

이 문서는 면접용 마인드맵을 따라 선형으로 펼친 구조다. 학습 순서 = 면접 답변 순서 = 백지에 그리는 순서.

1. **0장 마인드맵을 먼저 외운다** — 루트 한 문장 + 4가지 가지 + 각 가지의 키워드 3개.
2. **1~4장을 순서대로 학습한다** — 각 장이 마인드맵의 한 가지에 정확히 대응.
3. **5장 면접 워크플로우로 검증** — 질문을 보면 어느 가지로 가야 하는지 매핑.
4. **6장 꼬리질문으로 깊이 점검**.

---

## 0. 마인드맵 — 면접 종이에 그릴 그림

### 루트 한 문장 (anchor)

> **"JVM은 4대 서브시스템이다 — ClassLoader / Runtime Data Areas / Execution Engine / Native Interface. Runtime Data Areas는 다시 per-process(공유)와 per-thread(스레드별)로 갈리고, Execution Engine과 GC는 별도 책임이며, OS에서 보면 한 JVM = libjvm.so를 로드한 한 프로세스다."**

이 한 문장에서 모든 답변이 출발한다. 어떤 질문이 와도 이 문장부터 말하고 적절한 가지로 분기.

### 4개 가지 — 순서를 외운다

```
                  [ROOT: JVM = 4대 서브시스템 + GC 별도]
                                  │
       ┌─────────────┬────────────┼────────────┬──────────────┐
       │             │            │            │              │
      ① ClassLoader ② Runtime   ③ Execution  ③-b GC        ④ JNI
                     Data Areas   Engine      (별도 책임)    Native
       │             │            │            │              │
       │       ┌─────┼─────┐      │            │              │
    Bootstrap  shared per-thread  Interp +    Heap 관리     C ABI
    Platform   Heap   JVM Stack   JIT (C1/C2) Safepoint    JNI 핸들
    App        Meta-  PC          Code Cache  TLAB         Panama
    Custom     space  Native      OSR/Deopt   STW           (대체)
    부모위임   TLAB   Stack
```

### 가지별 핵심 키워드

| 가지 | 키워드 1 | 키워드 2 | 키워드 3 |
|---|---|---|---|
| **① ClassLoader** | Bootstrap → Platform → App → Custom | 부모 위임 | Loading → Linking → Init |
| **② Runtime Data Areas** | Heap (Young/Old) + Metaspace = 공유 | JVM Stack + PC + Native Stack = per-thread | TLAB (Eden 안의 스레드별 buffer) |
| **③ Execution Engine** | Interpreter (Template) | JIT (C1/C2) | Code Cache |
| **③-b GC (별도)** | Heap 관리 책임 | Safepoint 메커니즘 | STW + Time To Safepoint |
| **④ Native Interface** | JNI Bridge | C ABI 변환 | Project Panama (FFM API) |

### 면접 답변 흐름

> 면접관 질문 → 루트 문장 → 질문에 맞는 가지 1개 선택 → 그 가지의 키워드 3개 순서대로 설명 → 듣는 사람의 관심에 따라 인접 가지로 확장

"메모리 구조?" → ② Runtime Data Areas. "GC가 뭐 하는지?" → ③-b. "JNI?" → ④. "RSS가 큰 이유?" → ② 종합.

---

## 1. 가지 ①: ClassLoader Subsystem

### 1.1 핵심 질문

> "ClassLoader는 정확히 무엇이고 왜 4단계로 쪼개졌나요?"

### 1.2 키워드 1 — 4종의 ClassLoader 계층

| ClassLoader | 구현 언어 | 로드 대상 |
|---|---|---|
| **Bootstrap** | C++ (HotSpot 내장) | `$JAVA_HOME/lib/modules` 핵심 모듈 (java.base, java.sql, ...). `getClassLoader()` 결과는 `null` |
| **Platform** | Java | 표준이지만 핵심 아닌 모듈. JDK 9+. 구 ExtensionClassLoader 대체 |
| **Application** | Java | `-classpath`, `CLASSPATH` env, 모듈 path |
| **User-defined** | Java | Tomcat WebappCL, OSGi BundleCL, Spring DevTools, JRebel |

### 1.3 키워드 2 — 부모 위임 모델

```
[Application CL] ──"이 클래스 로드해줘"──→ [Platform CL] ──→ [Bootstrap CL]
                                                                    │
                ┌─────────"못 찾았으면 너가 찾아"───────────────────┘
                ▼
        [Application CL] 직접 검색
```

자식이 부모에게 먼저 묻고, 부모가 못 찾으면 자기가 찾음.

**왜**:
- **보안**: 사용자가 `java.lang.String`을 위조해도 Bootstrap이 먼저 로드해버리니 안전.
- **공유**: `java.lang.Object`는 어디서나 같은 인스턴스 → 메모리 절약.
- **격리**: Tomcat이 웹앱마다 다른 CL을 주어 같은 클래스의 다른 버전을 같은 JVM에서.

위임 모델을 깨는 케이스: **Tomcat WebappCL은 자기가 먼저 찾고 없으면 부모** — 웹앱별 격리. JDBC DriverManager + ServiceLoader는 Thread Context ClassLoader 사용.

### 1.4 키워드 3 — Loading → Linking → Initialization

JVM 스펙 §5의 3단계:
- **Loading**: byte[]를 얻어서 Method Area에 적재
- **Linking** (3 부속):
  - **Verification**: bytecode 안전성 점검 (실패 시 `VerifyError`)
  - **Preparation**: static 필드를 기본값으로 (`x=0`, `name=null`) — 아직 초기화 코드 실행 안 함
  - **Resolution**: Constant Pool 심볼 참조 → 실제 참조 (HotSpot은 lazy)
- **Initialization**: `<clinit>` 실행 — static 초기화 블록 + static 필드 할당

**중요**: 클래스 **로드 ≠ 초기화**. Loading은 한참 전에, Initialization은 처음 쓸 때까지 미뤄짐.

→ ClassLoader 상세는 → `jvm/01-class-lifecycle/`.

---

## 2. 가지 ②: Runtime Data Areas — 메모리 영역 전체

### 2.1 핵심 질문

> "JVM의 메모리 영역을 다 그려보세요. Per-process와 per-thread를 구분해서."

### 2.2 키워드 1 — Per-process (공유) 영역

```
┌────────────────────────────────────────────────────┐
│  Heap (모든 스레드 공유, GC가 관리)                  │
│  ┌─────────────────────┐  ┌──────────────────────┐ │
│  │  Young Generation   │  │  Old Generation       │ │
│  │  ┌──┬──┬──┐         │  │  (Tenured)            │ │
│  │  │E │S0│S1│         │  │                       │ │
│  │  └──┴──┴──┘         │  │                       │ │
│  │  Eden + Survivor    │  │  오래된 객체             │ │
│  │  (TLAB 여기)         │  │                       │ │
│  └─────────────────────┘  └──────────────────────┘ │
│        Minor GC                Major / Full GC      │
└────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────┐
│  Metaspace (네이티브 메모리, Heap 밖!)             │
│                                                   │
│  Klass 메타데이터:                                  │
│  ├─ Field 정보                                     │
│  ├─ Method 정보 (bytecode, line number table)      │
│  ├─ Constant Pool                                  │
│  ├─ Method counters (profiling 데이터)             │
│  └─ Klass*-Mirror Klass (java.lang.Class 인스턴스)  │
│                                                   │
│  ClassLoaderData 단위로 묶임 → CL unload 시 통째 free │
└───────────────────────────────────────────────────┘
```

**Compressed Class Space** (Metaspace 하위): Klass 포인터를 32비트로 압축. 기본 1GB.

### 2.3 키워드 2 — Per-thread (스레드별) 영역

스레드 하나당 OS가 따로 할당해주는 3종 세트:

| 영역 | 무엇 | 크기 |
|---|---|---|
| **JVM Stack** | Java 메서드 호출의 Stack Frame들 (LIFO) | `-Xss` (보통 512KB~1MB) |
| **PC Register** | 현재 실행 중인 bytecode 명령의 주소 | native word 1개 |
| **Native Method Stack** | JNI 등 native 호출 시의 C Frame | OS thread stack과 공유 |

3개 모두 스레드 생성 시 OS가 할당, 종료 시 반환. **물리적으로는 OS thread stack 1개에 통합**되며, JVM Stack/Native Stack은 논리적 분류.

Stack Frame의 내부:
- **Local Variable Array** — 파라미터 + 지역 변수 (32비트 슬롯, long/double은 2슬롯). 크기 = `max_locals`.
- **Operand Stack** — bytecode 명령(iadd 등)의 임시 계산 공간. 깊이 = `max_stack`.
- **Frame Data** — Constant Pool 참조, return PC, 이전 Frame 포인터.

→ 깊이는 → [02-runtime-data-areas/03-stack-pc-native.md](../02-runtime-data-areas/03-stack-pc-native.md).

### 2.4 키워드 3 — TLAB (Thread-Local Allocation Buffer)

각 스레드가 Eden 안에 가진 작은 영역(기본 ~수 KB). 객체 할당 시 lock 없이 **bump-the-pointer**:

```cpp
HeapWord* allocate(size_t size) {
    HeapWord* obj = _top;
    HeapWord* new_top = _top + size;
    if (new_top <= _end) {
      _top = new_top;
      return obj;       // 성공 — lock-free, 3 instruction
    }
    return NULL;        // TLAB full, slow path
}
```

**핵심**: 3개 instruction으로 객체 할당 — Java의 `new`가 C++ `new`보다 빠른 이유. TLAB이 다 차면 새 TLAB 또는 Eden 직접 할당으로 fallback.

큰 객체(TLAB보다 크거나 G1 region의 절반 이상 = **Humongous**)는 TLAB 우회 + 가능하면 Old gen 직접.

### 2.5 "메모리는 다 Heap이다?" — 아니다

> JVM이 OS에게 받는 메모리는 크게 셋:
> 1. **Java Heap** — `-Xmx`로 제어. GC가 관리.
> 2. **Metaspace** — `-XX:MaxMetaspaceSize`. Native 메모리. 클래스 메타데이터.
> 3. **Code Cache** — `-XX:ReservedCodeCacheSize`. Native 메모리. JIT 결과.
>
> 그 외 **DirectByteBuffer**(NIO), **JNI에서 malloc**, **스레드 스택**도 JVM 프로세스 메모리지만 Heap이 아님.
>
> 그래서 `top`의 RSS는 `-Xmx`보다 훨씬 클 수 있다.

### 2.6 "어느 영역이 GC 대상인가?"

| 영역 | GC 대상? | 비고 |
|---|---|---|
| Java Heap (Young/Old) | 주된 대상 | GC의 무대 |
| Metaspace | ClassLoader 단위 unload만 | 객체 단위 GC 아님 |
| Code Cache | UseCodeCacheFlushing으로 unload | 별개 GC 아님 |
| JVM Stack | 아님 | 메서드 리턴 시 pop |
| PC Register | 아님 | 4~8바이트 |
| Native Method Stack | 아님 | OS 스택 |
| DirectByteBuffer 영역 | 아님 | Cleaner 또는 명시적 해제 |

---

## 3. 가지 ③: Execution Engine + ③-b GC (별도)

### 3.1 핵심 질문

> "Execution Engine과 GC를 왜 별도로 보나요?"

### 3.2 키워드 1 — Execution Engine = Interpreter + JIT

**책임**: bytecode를 실제로 실행해서 결과를 만드는 부분.

| 컴포넌트 | 무엇을 |
|---|---|
| **Interpreter** | bytecode를 직접 실행. HotSpot은 **Template Interpreter** — 부팅 시 어셈블리 generate, 점프 테이블로 디스패치 |
| **JIT (C1/C2)** | hot method를 native code로 컴파일 → Code Cache 저장 |

> GC는 여기 속하지 않는다. GC는 "코드를 실행하는" 책임이 아니라 **메모리 관리** 책임 → 별도.

**Code Cache** (JDK 9+ Segmented, 기본 240MB):
```
┌────────────────┐
│ Non-profiled   │  → C2 결과 (최종 컴파일, 안정)
├────────────────┤
│ Profiled       │  → C1 결과 (profile 수집)
├────────────────┤
│ Non-methods    │  → interpreter, stub, adapter
└────────────────┘
```

→ JIT 메커니즘 자세히는 → [02-class-compilation-flow.md](./02-class-compilation-flow.md) 가지 ⑤.

### 3.3 키워드 2 — GC는 별도 책임 (③-b)

**책임**: ② Runtime Data Areas 중 **Heap**(과 일부 native 영역)을 관리.

| 항목 | 내용 |
|---|---|
| **위치** | 개념적으로 ②(메모리)와 ③(실행) 사이에 걸쳐 있음 |
| **하는 일** | unreachable 객체 식별·회수, 살아있는 객체 재배치, allocation 경로 제공 |
| **종류** | Serial, Parallel, G1, ZGC, Shenandoah, Epsilon |
| **실행 엔진과의 접점** | safepoint 메커니즘, JIT이 emit하는 write barrier, OopMap |

> "Interpreter / JIT / GC"를 한 줄에 나열하면 셋 다 "코드 실행 방식"처럼 보이지만, 실제로는 **Interpreter/JIT은 실행, GC는 메모리 관리**다.

### 3.4 키워드 3 — Safepoint (모든 것의 동기화 지점)

**Safepoint (개념)**: JVM이 Java 스레드들의 메모리/스택 상태가 일관됨을 보장할 수 있는 지점.

**Safepoint가 필요한 작업**:
- GC (Heap을 일관된 상태로 검사)
- Deoptimization (스택 재구성)
- Stack walking (`jstack`, JFR)
- Class redefinition
- Biased Lock revoke (JDK 15+에서 deprecated)

**HotSpot의 polling 메커니즘**:
1. 모든 메서드 epilogue / 일부 loop back-edge에 **safepoint polling instruction** 삽입.
2. 정지가 필요하면 JVM이 polling page를 **읽기 불가**로 만든다 (`mprotect`).
3. 다음 polling 명령에서 SEGV → JVM signal handler가 catch → 스레드를 safepoint blocking으로 전환.

> **STW (Stop-The-World)의 본질**: JVM이 스레드를 강제 정지가 아니라 **각 스레드가 다음 polling 지점에서 자발적으로 멈춤**. 그래서 **TTSP (Time To Safepoint)** — 큰 메서드 / counted loop가 길면 STW 전체가 늘어진다.

**JDK 10 JEP 312 — Thread-Local Handshakes**: 글로벌 polling page 대신 스레드별 polling word. 모든 안전 작업이 STW 전체 동기화를 요구하지 않게 됨.

### 3.5 운영 진단

| 증상 | 진단 |
|---|---|
| GC pause가 길다 | `-Xlog:gc*` 또는 JFR `jdk.GarbageCollection` |
| STW 길어짐 (TTSP 의심) | `-XX:+PrintSafepointStatistics`, JFR `jdk.SafepointBegin/End` |
| Counted loop가 정지 안 함 | JDK 10+ Thread-Local Handshakes 도움 |

---

## 4. 가지 ④: Native Interface (JNI)

### 4.1 핵심 질문

> "JNI는 왜 비싸고, Panama가 뭘 개선하나요?"

### 4.2 키워드 1 — JNI Bridge의 책임

JNI 호출의 책임:
- Java 객체 핸들 관리 (Local/Global/Weak Global Reference)
- Exception 전파 (`(*env)->ExceptionCheck`)
- 호출 규약 변환 (Java calling convention ↔ C ABI)

```c
JNIEXPORT jstring JNICALL
Java_com_example_MyClass_nativeMethod(JNIEnv* env, jobject this, jstring arg) {
    const char* utf = (*env)->GetStringUTFChars(env, arg, NULL);
    // ...
    return (*env)->NewStringUTF(env, "result");
}
```

### 4.3 키워드 2 — Calling Convention 변환

Java JIT 코드와 C 코드는 다른 calling convention을 따른다. JNI 진입/탈출 시 변환 + safepoint sync 필요 → 호출 비용이 일반 메서드 호출보다 비싸다 (수십 ~ 수백 ns).

또 JNI 안에서는 Java GC가 객체를 못 옮기게 **GCLocker**가 작동 → 큰 객체를 JNI에서 오래 잡고 있으면 GC 지연.

### 4.4 키워드 3 — Project Panama (FFM API)

JNI를 대체하려는 시도. **Foreign Function & Memory API** (JDK 22 stable, JEP 454).

| 비교 | JNI | Panama FFM |
|---|---|---|
| 사용 인터페이스 | C 함수 + JNI 매크로 | 순수 Java API |
| 호출 비용 | 비쌈 (수십~수백 ns) | 작음 (수 ns 수준) |
| 메모리 안전성 | 수동 | Arena 자동 관리 |
| 학습 곡선 | 가파름 | 완만 |

→ 신규 프로젝트에서는 Panama 권장. 기존 JNI 코드는 천천히 마이그레이션.

---

## 5. 면접 답변 워크플로우

### 5.1 질문 → 가지 매핑

| 면접 질문 | 진입 가지 | 인접 확장 |
|---|---|---|
| "JVM 아키텍처?" | ROOT → 4가지 | 모두 |
| "JVM 메모리 영역?" | ② Runtime Data Areas | 공유/per-thread |
| "Heap 외에 어떤 메모리가 있나?" | ② (Metaspace/CodeCache) | RSS 진단 |
| "TLAB이 뭐죠?" | ② TLAB | Humongous |
| "ClassLoader 부모 위임?" | ① | Tomcat WebappCL |
| "JIT 컴파일된 코드 어디 저장?" | ③ Code Cache | Segmented |
| "GC는 Execution Engine인가?" | ③-b (별도 책임) | Safepoint |
| "Safepoint가 왜 필요한가?" | ③-b | STW + TTSP |
| "Stop-the-World는 어떻게?" | ③-b polling | Thread-Local Handshakes |
| "JNI 호출이 왜 비싼가?" | ④ Calling convention | Panama |
| "RSS가 -Xmx보다 큰 이유?" | ② 종합 | NMT 진단 |

### 5.2 답변 템플릿

> "JVM은 4대 서브시스템입니다 (← 루트).
> **ClassLoader**가 .class를 부모 위임으로 메모리에 적재하고,
> **Runtime Data Areas**가 메모리를 들고 있는데 공유(Heap, Metaspace)와 per-thread(JVM Stack, PC, Native Stack)로 나뉘며,
> **Execution Engine**(Interpreter + JIT)이 그걸 실행하고,
> **GC**가 별도 책임으로 Heap을 관리합니다.
> 마지막으로 **JNI**가 외부 native 코드와의 창구입니다.
> OS에서 보면 한 JVM = libjvm.so를 로드한 한 프로세스고, 메모리는 Heap만이 아니라 Metaspace, Code Cache, Thread Stack, Direct Memory 모두 합쳐서 RSS를 만듭니다."

---

## 6. 꼬리질문 트리 (가지별)

### Q1 [가지 ②]. JVM의 메모리 구조를 설명?

> 4 카테고리. (1) **스레드 공유**: Heap (Young/Old), Metaspace (네이티브). (2) **스레드별**: JVM Stack, PC Register, Native Method Stack. (3) **JVM 내부**: Code Cache, Compressed Class Space. (4) **외부**: DirectByteBuffer, JNI native 메모리, OS 스레드 스택.

**🪝 Q1-1: Metaspace는 왜 Heap 밖?**
> PermGen 시절 문제 — (1) 크기 고정 → OOM 빈번 (Spring AOP, Hibernate proxy의 동적 클래스), (2) Heap GC 정책에 묶임, (3) Compressed Oops 충돌. Metaspace는 ClassLoaderData chunk 단위로 CL unload 시 통째 free.

**🪝🪝 Q1-1-1: Metaspace OOM 원인?**
> 가장 흔한 건 **ClassLoader 누수**. 웹앱 reload 시 옛 WebappClassLoader가 GC되지 않음 (어딘가에서 reference) → 옛 클래스가 Metaspace에서 못 빠짐. 진단: `jcmd VM.classloader_stats`, heap dump + Eclipse MAT.

**🪝 Q1-2: Direct Memory 왜 쓰나?**
> Zero-copy I/O — Heap의 byte[]는 OS가 직접 접근 못 함. DirectByteBuffer는 OS가 read/write 직접 가능 → 복사 한 번 제거. JNI/Panama interop, MappedByteBuffer 큰 파일 매핑에도. GC 대상은 아니고 `Cleaner`가 DirectByteBuffer 객체 GC 시 native 메모리를 free.

### Q2 [가지 ②]. TLAB이 뭐고 어떻게 동작?

> Thread-Local Allocation Buffer. 각 스레드가 Eden 안에 가진 작은 영역. lock 없이 bump-the-pointer로 즉시 할당 (3 instruction). TLAB이 차면 새 TLAB 또는 slow path. Java의 `new`가 빠른 본질적 이유.

**🪝 Q2-1: 큰 객체도 TLAB?**
> 안 들어감. TLAB보다 크면 Eden 직접. G1/ZGC에서는 region 절반 이상이면 **Humongous** → Old gen 직접 + region 통째로 차지 → fragmentation 위험. 4MB+ 배열은 setup 단계에 신중히.

**🪝 Q2-2: TLAB 가득 차면?**
> 두 옵션. (1) Retire & Allocate New — 남은 자투리를 dummy filler로 채워서 buried, 새 TLAB. (2) Fall back to Eden — 객체 하나만 Eden 직접. 휴리스틱. filler object는 Heap walking 일관성 유지용.

### Q3 [가지 ③-b]. Safepoint가 뭐고 왜 필요?

> 모든 Java 스레드를 동시 정지시킬 수 있는 상태. GC/Deopt/Stack walking/Biased lock revoke에 필요. "정지" = JVM이 polling page를 막아두면 각 스레드가 polling instruction에서 SEGV → safepoint blocking.

**🪝 Q3-1: 왜 강제 못 멈추고 polling?**
> 강제 중단하면 스레드 상태가 일관적이지 않을 수 있음 (half-initialized 객체). Polling은 일관된 지점에서만 멈춤 보장. 모든 polling 위치에서 JVM이 register/stack의 oop 위치를 정확히 앎 (OopMap). 이 정보 없으면 GC가 어떤 메모리가 객체 참조인지 모름.

**🪝🪝 Q3-1-1: TTSP가 길어지는 케이스?**
> **Time To Safepoint** — 정지 신호 후 모든 스레드 도달까지. 길어지는 경우: (1) **Counted Loop**가 매우 큰 N — JIT이 성능 이유로 safepoint poll을 안 넣음. (2) 긴 JNI 호출. (3) Heap dump 중. 진단: `-XX:+PrintSafepointStatistics`, JFR `jdk.SafepointBegin/End`.

**🪝🪝🪝 Q3-1-1-1: JEP 312 Thread-Local Handshakes?**
> 그 전 "정지 = 모두 동시" → 한 스레드 느리면 모두 대기. 312는 **개별 스레드만 정지** 가능. polling page를 스레드별로. 적용: stack sampling, biased lock revoke, JFR. 전체 STW가 필요한 GC에는 영향 적음.

### Q4 [가지 ①]. 클래스가 메모리에 로드되는 과정?

> (1) **Loading**: ClassLoader가 .class 바이트를 읽음. (2) **Linking**: a. Verification(bytecode 안전성, StackMapTable), b. Preparation(static 필드 default), c. Resolution(symbolic ref → direct ref, lazy). (3) **Initialization**: `<clinit>` 실행 — static init + 부모 먼저 + 단 한 번.

**🪝 Q4-1: Resolution이 lazy하면 언제?**
> HotSpot은 처음 그 reference를 쓸 때(예: invokevirtual 실행 시). 결과 caching → 두 번째부터 즉시 사용.

**🪝🪝 Q4-1-1: NoClassDefFoundError vs ClassNotFoundException?**
> **CNFE**: `Class.forName` 같은 명시적 로딩 실패. checked exception. **NCDFE**: 컴파일엔 있었는데 실행 시점 사라짐. Resolution 단계 실패. 흔한 시나리오 — static initializer 실패해서 클래스가 broken 상태. 첫 stacktrace의 `ExceptionInInitializerError`가 핵심 단서. 이후 모든 접근에서 NCDFE.

### Q5 (Killer) [가지 ② 종합]. JVM 프로세스가 OS에 요청하는 메모리 영역들?

> (1) **Heap**: 시작 시 `-Xms` commit, `-Xmx` reserve, mmap. (2) **Metaspace**: 클래스 로드 시 동적 chunk. (3) **Compressed Class Space**: 32비트 Klass 포인터, Metaspace 하위, 기본 1GB. (4) **Code Cache**: 240MB reserve. (5) **Thread stacks**: 스레드당 `-Xss` (보통 1MB). (6) **Direct Memory**: `ByteBuffer.allocateDirect`. (7) **JIT scratch**: 컴파일 중 임시. (8) **GC bookkeeping**: card table, RSet, mark bitmap.
>
> `top`의 RSS가 -Xmx보다 큰 이유. 컨테이너에서 limit=10g인데 -Xmx=8g면 OOM-killed 위험. 보통 `-Xmx`는 limit의 50~70%.

**🪝 Q5-1: NMT는 어떻게 켜고 보나?**
> ```
> java -XX:NativeMemoryTracking=summary
> jcmd <pid> VM.native_memory summary
> jcmd <pid> VM.native_memory baseline
> jcmd <pid> VM.native_memory summary.diff
> ```
> 영역별 reserved/committed 확인. 운영자 필수 도구. 오버헤드 summary는 ~5% 메모리, prod 상시 켜둘 만함.

---

## 7. 학습 체크리스트

면접 전 백지에서 다음을 다 해낼 수 있어야 마스터:

- [ ] 0장 마인드맵을 종이에 1분 이내로 그릴 수 있다 (루트 + 4가지 + 각 키워드 3개)
- [ ] 가지 ① ClassLoader: 4종 계층 + 부모 위임 + 3단계(Load/Link/Init)를 그린다
- [ ] 가지 ② Runtime Data Areas: per-process vs per-thread 분리 그림을 그린다
- [ ] 가지 ② TLAB의 bump-the-pointer 코드 흐름을 설명한다
- [ ] 가지 ② "메모리는 다 Heap이다"가 왜 틀린지 8가지 영역으로 답한다
- [ ] 가지 ③ Execution Engine과 ③-b GC의 책임이 다름을 명확히 한다
- [ ] 가지 ③ Code Cache 3분할(non-profiled/profiled/non-methods) 의미를 설명한다
- [ ] 가지 ③-b Safepoint polling 메커니즘 + TTSP + Thread-Local Handshakes를 말한다
- [ ] 가지 ④ JNI의 비용 + Panama FFM API의 개선을 말한다
- [ ] Killer 질문: RSS 5GB의 영역별 분해 진단 절차를 그린다

---

## 진화 — 시대별 변화

### PermGen → Metaspace (JDK 8)

JDK 7까지는 PermGen (Heap의 일부, 크기 고정). 동적 클래스 생성 많으면 `OOM: PermGen space`. JDK 8에서 **Metaspace**(Heap 밖 네이티브 메모리)로 폐기. 이유: (1) 크기 고정 OOM, (2) Heap GC 정책에 묶임, (3) Compressed Oops 충돌.

### Tiered Compilation 통합 (JDK 7→8)

JDK 7 이전: `-client` 또는 `-server`. JDK 7부터 Tiered(실험), JDK 8부터 기본 활성화. C1과 C2 한 JVM 공존.

### Code Cache Segmentation (JDK 9)

3분할. non-profiled는 GC root scan 제외 가능 → latency 개선.

### Project Loom — Virtual Thread (JDK 21)

Virtual Thread는 OS 스레드 1:1 매핑 끊음. **Stack chunk를 Heap에 저장** — Virtual Thread의 JVM Stack은 Heap 안의 객체. 큰 패러다임 변화.

---

## 다음 단계

이 챕터를 완벽히 이해했으면 다음 챕터부터는 "어느 박스 안 이야기인지"가 자동으로 매핑된다.

- **01-class-lifecycle** → ① ClassLoader Subsystem의 상세
- **02-runtime-data-areas** → ② Runtime Data Areas의 상세
- **03-execution-engine** → ③ Execution Engine의 상세
- **04-gc** → ③-b GC만 깊이
- **05-threading** → ② Per-Thread + ③-b Safepoint

## 참고

- **JVMS §2 (JVM Structure)**: https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-2.html
- **HotSpot Runtime Overview**: https://openjdk.org/groups/hotspot/docs/RuntimeOverview.html
- **JEP 122 (Remove PermGen)**: https://openjdk.org/jeps/122
- **JEP 312 (Thread-Local Handshakes)**: https://openjdk.org/jeps/312
- **JEP 197 (Segmented Code Cache)**: https://openjdk.org/jeps/197
- **JEP 454 (Foreign Function & Memory API)**: https://openjdk.org/jeps/454
