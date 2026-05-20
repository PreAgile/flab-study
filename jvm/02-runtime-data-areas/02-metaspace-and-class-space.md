# 02-02. Metaspace & Class Space — Heap 밖에 사는 클래스 메타데이터

> JVM은 `Class<?>` 객체와 그 안의 모든 메타정보(필드 시그니처, 메서드 바이트코드, Constant Pool 등)를 어디에 저장하는가?
> 답: **Heap이 아니다. Heap 밖, OS가 직접 관리하는 native 메모리 — Metaspace.**
> 그래서 `-Xmx`를 아무리 크게 잡아도 `OutOfMemoryError: Metaspace`는 따로 난다. 그리고 그게 ClassLoader 누수의 신호다.

---

## 이 문서의 사용법

이 문서는 **면접용 마인드맵**을 따라 선형으로 펼친 구조다. 학습 순서 = 면접 답변 순서 = 백지에 그리는 순서.

1. **0장 마인드맵을 먼저 외운다** — 루트 한 문장 + 6가지 가지 + 각 가지의 키워드 3개.
2. **1~6장을 순서대로 학습한다** — 각 장이 마인드맵의 한 가지에 정확히 대응.
3. **7장 면접 워크플로우로 검증** — 질문을 보면 어느 가지로 가야 하는지 매핑.
4. **8장 꼬리질문으로 깊이 점검**.

---

## 0. 마인드맵 — 면접 종이에 그릴 그림

### 루트 한 문장 (anchor)

> **"Metaspace는 Heap 밖 native 메모리에 사는 클래스 메타데이터 저장소다. ClassLoaderData 단위로 chunk를 받고, ClassLoader unload 시 통째로 free된다."**

이 한 문장에서 모든 답변이 출발한다. 어떤 질문이 와도 이 문장부터 말하고 적절한 가지로 분기.

### 6개 가지 — 순서를 외운다

```
                    [ROOT: Metaspace = Heap 밖 native, CLD 단위]
                                    │
       ┌─────────┬──────────────┬───┴───┬──────────────┬─────────┐
       │         │              │       │              │         │
      ① WHY    ② WHAT         ③ HOW   ④ Klass        ⑤ 운영    ⑥ 진화
   PermGen     3단 구조        CLD     vs mirror     누수 진단  (역사)
   4 결함      위치            chunk   양방향          5대 패턴
       │         │              │       │              │         │
       │    ┌────┼────┐     ┌───┼───┐  ┌─┼─┐      ┌────┼────┐    │
    크기고정 Native 위치  VSpace Chunk  Heap의 Meta의 jcmd  MAT  PermGen
    GC충돌  Comp.Class  Block      Class  Klass  loaders unload→Meta
    CL비효율 1GB reserve unload→ free  Java객체 C++객체 N개  log  Elastic(387)
    Comp.Oops                          mirror  Klass*
    충돌
```

### 가지별 핵심 키워드 (각 가지 3개씩만)

| 가지 | 키워드 1 | 키워드 2 | 키워드 3 |
|---|---|---|---|
| **① WHY PermGen 죽음** | 크기 고정 | GC 정책 충돌 | CL unload 비효율 |
| **② WHAT 위치/구조** | Native 메모리 (mmap) | Compressed Class Space 1GB | Metaspace 무제한 |
| **③ HOW CLD chunk** | VirtualSpace → Chunk → Block | ClassLoaderData 소유 | CL unload → chunk 통째 free |
| **④ Klass vs mirror** | Heap의 `Class<?>` (mirror) | Metaspace의 `InstanceKlass` | 양방향 포인터 |
| **⑤ 운영 누수 진단** | jcmd VM.classloader_stats | 5대 누수 패턴 | -XX:MaxMetaspaceSize |
| **⑥ 진화** | PermGen → Metaspace (JEP 122) | Elastic Metaspace (JEP 387) | GC별 unload 시점 |

### 면접 답변 흐름

> 면접관 질문 → 루트 문장 → 질문에 맞는 가지 1개 선택 → 그 가지의 키워드 3개 순서대로 설명 → 듣는 사람의 관심에 따라 인접 가지로 확장

---

## 1. 가지 ①: WHY — PermGen이 왜 죽었는가

### 1.1 핵심 질문

> "JDK 8에서 PermGen이 제거되고 Metaspace로 바뀐 이유는?"

### 1.2 키워드 1 — 크기 고정 문제

PermGen은 Heap 안의 한 generation으로 `-XX:MaxPermSize=256m` 처럼 **미리 픽스**해야 했다.

```
2000년대 후반 ~ 2010년대 초:
  - Spring AOP, Hibernate proxy, CGLib, Mockito, Groovy ...
  - 모두 런타임에 동적으로 클래스를 생성
  - 그 양이 사전 예측 불가
  ↓
PermGen 가득 → OutOfMemoryError: PermGen space
  ↓
-XX:MaxPermSize 키움 → 또 가득 → 또 키움 ... 반복
```

### 1.3 키워드 2 — GC 정책 충돌

PermGen은 Heap 안의 generation이라 일반 GC 정책에 끼어듦.

| | 일반 객체 (Young/Old) | PermGen 클래스 메타데이터 |
|---|---|---|
| 수명 | 짧음~중간 (generational) | 거의 영구 |
| 처리 단위 | 객체 단위 | 메타데이터 한 덩어리 |
| sweep 비용 | 객체 수만큼 | 흩어진 메타 다 훑어야 |

세대별 GC 알고리즘이 PermGen에는 부적합 — 거의 다 살아있는 영역을 Young GC처럼 자주 청소할 수도, Old GC처럼 promotion 처리할 수도 없음.

### 1.4 키워드 3 — ClassLoader unload 비효율 & Compressed Oops 충돌

**CL unload 비효율**:
- PermGen 안에 흩어진 객체들을 각각 sweep해야 함.
- ClassLoader 하나가 잡고 있는 메타데이터를 통째로 회수할 메커니즘이 약함.

**Compressed Oops 충돌**:
- JDK 6u23 이후 Compressed Oops로 Klass 포인터를 압축하려는데, PermGen의 Heap 내 위치가 압축 base 결정에 제약.
- Heap 밖으로 빼면 압축 메커니즘이 독립적으로 설계 가능.

→ **JEP 122**의 4가지 motivation. PermGen 폐기의 본질. 추가 배경: 2008년 Oracle이 BEA(JRockit)를 인수했고, JRockit은 이미 메타데이터를 native에 두고 있었음.

---

## 2. 가지 ②: WHAT — Metaspace의 위치와 구조

### 2.1 핵심 질문

> "Metaspace를 그려보세요. Heap과 어떻게 다른가요?"

### 2.2 키워드 1 — Heap과 Native Memory의 경계

```
JVM Process (RSS)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

┌─────────────────────────────────┐   ┌───────────────────────────────────┐
│ Java Heap (-Xmx)                 │   │ Native Memory                      │
│                                  │   │                                    │
│  [String "hello"]                │   │  ┌─────────────────────────────┐   │
│   ├── Mark Word                  │   │  │ Metaspace                    │   │
│   ├── Klass Ptr ─────────────────┼───┼──┤ ┌─────────────────────────┐ │   │
│   └── value, hash, ...           │   │  │ │ Compressed Class Space   │ │   │
│                                  │   │  │ │ (기본 1GB reserve)        │ │   │
│  [Class<String> mirror]          │   │  │ │  [InstanceKlass String]◄┼─┘   │
│   └── _klass ────────────────────┼───┼──┤ │   ├ Constant Pool        │     │
│                                  │   │  │ │   ├ vtable / itable      │     │
│                                  │   │  │ │   └ _java_mirror ────────┼─────┘
│                                  │   │  │ └─────────────────────────┘     │
└─────────────────────────────────┘   └───────────────────────────────────┘
       ↑ GC 대상                              ↑ CLD chunk 단위 free
       ↑ -Xmx 제어                            ↑ -XX:MaxMetaspaceSize (기본 unlimited)
       ↑ OOM: Java heap space                 ↑ OOM: Metaspace
```

**Native 메모리란?**: JVM(Java)의 관리 영역이 아니라 OS가 직접 관리하는 메모리. JVM은 OS 시스템 콜 `mmap`으로 받음. C/C++ 프로그램이 쓰는 그 메모리와 같은 성격.

### 2.3 키워드 2 — Compressed Class Space (1GB의 함정)

```
일반 Klass 포인터 (64-bit):  8 byte
                              ↓
Compressed Klass Pointer:    4 byte
                              ↓
실제 주소 = base + (compressed << shift)
                              ↓
포인터 압축에 필요한 base를 만들기 위해 별도 reserve 영역
```

**핵심 사실**:
- Heap의 Compressed Oops와 **별개의 메커니즘**.
- Compressed Oops: Heap 내부 객체 ref용. 32GB 제한.
- Compressed Class: Metaspace의 Klass ref용. 별도 **1GB** reserve.
- Klass는 양이 적어 1GB로 충분... 하지만 거대 Spring Boot 모놀리스에서는 한계.

`-XX:CompressedClassSpaceSize=1g` (기본). Class 수 10만 개 이상이면 `OutOfMemoryError: Compressed class space` 별도 발생.

### 2.4 키워드 3 — Metaspace 무제한 vs PermGen 픽스

| | PermGen (JDK ≤ 7) | Metaspace (JDK 8+) |
|---|---|---|
| 위치 | Heap 안 | Native 메모리 |
| 크기 제한 | 미리 픽스 (`-XX:MaxPermSize`) | 기본 unlimited |
| GC 정책 | Heap GC와 통합 | CLD chunk 단위 |
| CL unload | 비효율 | 효율 (chunk 통째) |
| OOM 메시지 | `OOM: PermGen space` | `OOM: Metaspace` |
| Compressed Oops 호환 | ❌ | ✅ |
| 동적 클래스 생성 친화 | ❌ | ✅ |

→ Metaspace는 모든 면에서 우위. PermGen은 시대적 제약의 산물.

---

## 3. 가지 ③: HOW — CLD 단위 chunk 메커니즘

### 3.1 핵심 질문

> "Metaspace는 클래스 메타데이터를 어떻게 할당하고 회수하나요?"

### 3.2 키워드 1 — VirtualSpace → Chunk → Block 3단 구조

```
[1단: VirtualSpaceList]
OS로부터 큰 가상 주소 공간을 mmap reserve (수 MB 단위)
여러 VirtualSpaceNode를 linked list로 보유

  VirtualSpaceList
    └── Node 1 (2MB)
    └── Node 2 (2MB)
    └── ...

[2단: Chunk]
각 Node를 chunk로 분할. 크기 등급:
  - Specialized chunk : 1KB (작은 Klass)
  - Small chunk       : 4KB
  - Medium chunk      : 64KB (대부분의 일반 클래스)
  - Humongous chunk   : 가변

[3단: Block]
Chunk 안에 실제 메타데이터를 bump-the-pointer로 할당
TLAB의 Metaspace 버전, 단 per-CLD가 아닌 per-chunk

  Medium Chunk (64KB), owned by App CLD
    ┌──────────────────────────────────────┐
    │ [InstanceKlass for com.foo.Bar]      │
    │ [Method "doIt"]                      │
    │ [ConstantPool for Bar]               │
    │ ─── top ───                          │
    │ (free)                                │
    └──────────────────────────────────────┘
```

### 3.3 키워드 2 — ClassLoaderData (CLD) 소유권

```
ClassLoader 인스턴스 ←─── (1:1) ───→ ClassLoaderData
                                      ├── _chunks : [Chunk*, Chunk*, ...]
                                      ├── _klasses: [Klass*, Klass*, ...]
                                      ├── _dictionary: name → Klass
                                      └── _next: 전역 CLD 리스트의 일원

ClassLoaderDataGraph (전역)
  ├── Bootstrap CLD       (struct, not Java object)
  ├── Platform CLD
  ├── App CLD
  ├── WebApp1 CLD         (Tomcat WebappClassLoader #1)
  ├── WebApp2 CLD
  └── (anonymous CLD)     (LambdaForm용)
```

**핵심 규칙**:
- 모든 ClassLoader 인스턴스(Bootstrap 제외)는 정확히 하나의 CLD를 가짐.
- 같은 CL이 로드한 모든 클래스의 Klass·Method·CP는 그 CLD의 chunk에 들어감.
- CL이 unreachable → CLD도 unreachable → CLD 자체와 chunk가 free.

### 3.4 키워드 3 — ClassLoader unload 흐름 (chunk 통째 free)

```
ClassLoader 객체가 unreachable
        │
        ▼
Heap GC의 mark phase에서 CL을 못 따라감
        │
        ▼
GC의 Class Unloading sub-phase:
  ClassLoaderDataGraph 순회
   "각 CLD의 ClassLoader oop이 마킹됐는지?"
        │
        ▼
마킹 안 된 CLD를 dead로 표시
        │
        ▼
ClassLoaderData::unload():
  - 모든 Klass의 mirror(Heap의 Class 객체)도 unreachable
  - CLD가 가진 모든 chunk를 free list로 반환
  - _dictionary, _klasses 정리
  - CLD 자체도 free
        │
        ▼
다음 GC cycle: 빈 VirtualSpaceNode가 있으면 OS에 uncommit (JEP 387 이후 적극화)
```

**가장 중요한 사실 — 같은 GC cycle 안에서**: "Metaspace는 GC 대상이 아니다"라는 표현이 흔히 혼동을 부르는데, 정확히는:

> "Metaspace 자체는 직접 GC 대상이 아니지만, **Heap GC와 같은 cycle의 sub-phase(Class Unloading phase)에서 같이 처리**된다. Heap GC의 mark phase에서 ClassLoader의 reachability가 결정되고, unreachable한 CL의 CLD chunk가 그 cycle 안에서 통째로 free된다. 회수 단위가 객체(Heap)가 아니라 CLD(Metaspace)라는 게 PermGen과의 본질적 차이."

**GC별 Class Unloading 시점**:

| GC | Class Unloading 시점 | 특이사항 |
|---|---|---|
| Serial / Parallel | Full GC (STW)에서만 | Young GC 안 함 |
| G1 | Concurrent Mark Cycle 끝의 Cleanup | JDK 10+ Young GC도 일부 |
| ZGC | Concurrent Class Unloading (JDK 14+) | STW 없음 |
| Shenandoah | Concurrent | STW 없음 |

→ 잦은 hot reload 워크로드면 Serial/Parallel은 함정. G1+ 또는 ZGC 권장.

---

## 4. 가지 ④: Klass vs mirror — 같은 클래스의 두 표현

### 4.1 핵심 질문

> "`String.class`는 어디에 있나요? `InstanceKlass for String`과의 관계는?"

### 4.2 키워드 1 — Heap의 mirror

```
Java 코드에서 String.class
   │
   ▼
Heap의 Class<String> 객체 (= mirror)
   ├── 모든 Java reflection API의 진입점
   ├── classLoader, name, modifiers 등을 getter로 노출
   ├── 일반 Java 객체이므로 일반 GC 대상
   │
   └── _klass 필드 ──→ Metaspace의 InstanceKlass
```

**이름의 유래**: "mirror"는 Metaspace의 Klass(HotSpot 내부 C++ 객체)를 Java 세계에서 들여다보는 거울. reflection이 만지는 게 이것.

### 4.3 키워드 2 — Metaspace의 InstanceKlass

```
InstanceKlass for "java.lang.String" (Metaspace)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

┌─────────────────────────────────────────────────┐
│ Klass 공통 헤더                                   │
│  ├ _layout_helper (객체 사이즈/타입 힌트)          │
│  ├ _super (상위 클래스 Klass*)                    │
│  ├ _name (Symbol*: "java/lang/String")          │
│  ├ _class_loader_data (CLD 역참조)               │
│  └ _java_mirror ──────────────────────────────┐ │
├─────────────────────────────────────────────────┤ │
│ InstanceKlass 추가 필드                          │ │
│  ├ _methods (Array<Method*>)                    │ │
│  ├ _fields (Array<u2>)                          │ │
│  ├ _constants (ConstantPool*)                   │ │
│  ├ _itable (interface dispatch table)           │ │
│  └ _vtable (virtual dispatch table)             │ │
├─────────────────────────────────────────────────┤ │
│ Embedded vtable / itable / OopMap blocks        │ │
└─────────────────────────────────────────────────┘ │
                                                    │
   ┌────────────────────────────────────────────────┘
   ▼
Heap의 Class<String> 객체 (mirror)
  └ _klass ──→ 위의 InstanceKlass (양방향)
```

### 4.4 키워드 3 — 양방향 포인터 + 객체 헤더의 Klass Ptr 정체

```
객체 인스턴스 (Heap):
  String "hello"
   ├ Mark Word
   ├ Klass Pointer ──→ Metaspace의 InstanceKlass (★ mirror가 아니라 직접 Klass!)
   └ value, hash, ...

InstanceKlass (Metaspace) ←──→ Class<String> mirror (Heap)
        _java_mirror              _klass
```

**자주 묻는 디테일**:
1. 객체 헤더의 Klass Pointer는 **mirror가 아니라 InstanceKlass**를 직접 가리킴.
2. reflection이 `getMethod()` 부르면 mirror의 `_klass`를 통해 InstanceKlass에 접근.
3. 두 객체는 서로 다른 메모리 영역, 다른 GC 정책, 다른 수명 (mirror는 Heap GC, Klass는 CLD unload).

**reflection 호출 메커니즘**:
1. `Method.invoke()` → JDK 내부에서 mirror의 `_klass` → InstanceKlass 접근.
2. `_methods` 배열에서 Method 메타데이터 lookup.
3. 인터프리터 또는 JIT 컴파일된 native code의 entry point로 jump.
4. 처음 N번은 native 호출 → 임계 이상이면 동적 bytecode 어댑터 생성 (`MethodAccessorImpl`) → invokevirtual 직접 호출. **Inflation**이라 부름.

---

## 5. 가지 ⑤: 운영 — ClassLoader 누수 진단

### 5.1 핵심 질문

> "`OutOfMemoryError: Metaspace`가 발생합니다. 어떻게 진단하나요?"

### 5.2 키워드 1 — 진단 도구 (jcmd 3종)

```bash
# 요약: chunk 등급별 사용량
jcmd <pid> VM.metaspace summary

# 출력 예시:
# Total Usage - 5023 loaders, 25341 classes (153 shared):
#   Non-Class: reserved 156Mb, committed 154Mb, used 152Mb
#   Class:     reserved 1Gb,   committed 24Mb,  used 22Mb
```

판독:
- **loaders** — 살아있는 CLD 개수. **수만 개면 누수 확정**.
- **classes** — 로드된 클래스 총 수.
- **Non-Class / Class** — Class는 Compressed Class Space, Non-Class는 일반 Metaspace.

```bash
# CLD별 클래스 수
jcmd <pid> VM.classloader_stats

# 출력 예 (같은 이름 CL이 누적되어 있으면 누수):
# ClassLoader        Parent    Classes  ChunkSz  BlockSz  Type
# 0x00007fxxxx       ---       4        4096     1024     com.example.LeakingCL
```

```bash
# Class 로드/언로드 추적
java -Xlog:class+unload=info -Xlog:class+load=info ...

# JFR
jcmd <pid> JFR.start name=meta duration=300s settings=profile filename=meta.jfr
# 핵심 이벤트: jdk.ClassLoad / jdk.ClassUnload / jdk.ClassLoaderStatistics
```

### 5.3 키워드 2 — ClassLoader 누수 5대 패턴

| # | 패턴 | 원인 | 진단 |
|---|---|---|---|
| 1 | **정적 캐시 누수** | `static Map<String, Class<?>>` 가 외부 CL의 클래스를 잡음 | Heap dump → static 필드 추적 |
| 2 | **ThreadLocal 누수** | 톰캣 스레드풀의 영구 스레드가 ThreadLocal로 외부 CL의 객체 보유 | jstack + Heap dump |
| 3 | **JDBC DriverManager** | `registerDriver()` 했는데 `deregister`를 안 함 → JDK가 driver 잡고 driver는 자기 CL 잡음 | shutdown hook 점검 |
| 4 | **Logger context** | Log4j2/Logback의 LoggerContext가 자기 CL을 잡음 | shutdown 호출 누락 확인 |
| 5 | **Reflection cache** | `Field.setAccessible(true)` 등이 만든 캐시가 CL 보유 | reflection 정적 캐시 비우기 |

### 5.4 키워드 3 — OOM:Metaspace 진단 플로우 + 누수 재현

```
"OutOfMemoryError: Metaspace" 발생
              │
              ▼
1. jcmd <pid> VM.metaspace summary
   ├── loaders 수 비정상 (수만+)?  → ClassLoader 누수
   └── loaders 정상, classes 폭증?  → dynamic codegen
              │
              ▼
2. jcmd <pid> VM.classloader_stats
   ├── 같은 이름 CL 누적?  → Hot deploy 누수 (Tomcat, DevTools)
   └── 한 CL이 비정상 클래스 수?  → Dynamic proxy / CGLib 폭주
              │
              ▼
3. Heap dump + Eclipse MAT
   "GC Roots" → ClassLoader 추적
   "Classloader Explorer" 뷰로 누가 잡고 있는지
              │
              ▼
4. 원인 코드 수정
```

**의도적 재현 — 정적 캐시 누수**:
```java
public class LeakDemo {
    private static final Map<String, Class<?>> LEAK = new HashMap<>();

    public static void main(String[] args) throws Exception {
        for (int i = 0; i < 1000; i++) {
            URL[] urls = { new File("plugin.jar").toURI().toURL() };
            URLClassLoader cl = new URLClassLoader(urls);
            Class<?> c = cl.loadClass("com.foo.PluginImpl");
            LEAK.put("plugin-" + i, c);  // ★ cl이 영원히 unreachable 안 됨
        }
        Thread.sleep(Long.MAX_VALUE);
    }
}
```

```bash
java -XX:MaxMetaspaceSize=128m -Xlog:class+unload LeakDemo
# → 잠시 후 OOM:Metaspace
# → class+unload 로그가 거의 없음 → unload 안 됨 확정
```

### 5.5 운영 옵션 트레이드오프

**`-XX:MaxMetaspaceSize`**:
| 설정 | 안 함 (기본) |
|---|---|
| 누수 시 빠르게 터짐 → 발견 빠름 | OS 전체 메모리 압박할 때까지 안 보임 |
| 컨테이너 친화 (예측 가능) | 컨테이너 OOM-killed 위험 |
| Legit 동적 클래스 막힐 수도 | Dynamic codegen 자유 |

경험칙: Container 환경은 반드시 설정 (512m~1g). Spring Boot 거대 모놀리스는 측정 후 600~800m. Hot deploy 환경(Tomcat, JBoss)은 더 크게 + 누수 모니터링 필수.

**Class 수 추정**: 클래스 1개 ≈ 5~10KB → Spring Boot 일반 1만 개 ≈ 50~100MB / 거대 모놀리스 10만 개 ≈ 500MB~1GB.

---

## 6. 가지 ⑥: 진화 — Metaspace의 역사

### 6.1 핵심 질문

> "Metaspace는 도입 후 어떻게 더 발전했나요?"

### 6.2 키워드 1 — PermGen → Metaspace (JEP 122, JDK 8)

| 연도 | 릴리스 | 변화 | 이유 |
|---|---|---|---|
| 1996 | JDK 1.0 | Heap 안 PermGen | 초기 설계 |
| 2010 | JDK 7 | **String Pool을 Heap의 일반 영역으로** | PermGen 정리 1단계 |
| 2014 | JDK 8 | **PermGen 제거 → Metaspace (JEP 122)** | OOM:PermGen, 동적 클래스, JRockit 통합 |
| 2014 | JDK 8 | **Compressed Class Space 도입** | Klass 포인터 압축용 별도 reserve |

**JDK 7의 String Pool 이동**: 이전 PermGen에 있던 interned String이 Heap의 일반 영역으로 이동. 결과: 일반 GC 대상이 됨, `String.intern()` 남용이 OOM:PermGen으로 이어지는 사고가 사라짐. (단, 너무 많이 intern하면 Heap의 String Pool 해시 충돌 → `-XX:StringTableSize`로 조정)

### 6.3 키워드 2 — Elastic Metaspace (JEP 387, JDK 15)

**옛 Metaspace의 문제**:
- chunk를 OS에서 받은 후 **거의 OS에 반환하지 않음**.
- 단명 ClassLoader(hot deploy, lambda anonymous)가 많으면 chunk가 free list에 쌓이고 RSS는 그대로.

**JEP 387 해결**:
1. **Buddy allocator** — chunk 크기 등급을 power-of-2로 통일 → fragmentation 감소.
2. **Uncommit 적극화** — 사용 안 하는 chunk의 페이지를 `madvise(MADV_DONTNEED)`로 OS에 반환 (commit만 해제, reserve 유지).
3. 결과: footprint **10~20% 감소**.

→ JDK 15+에서 Metaspace 메모리 증가가 옛 버전보다 완만 → 누수 진단이 더 정확.

### 6.4 키워드 3 — GC별 Class Unloading 시점의 진화

| GC | 도입 | Unload 시점 | STW |
|---|---|---|---|
| Serial / Parallel | JDK 1.0 / 1.4 | Full GC에서만 | Yes |
| G1 | JDK 7u4 / 9 default | Concurrent Mark Cycle 끝 Cleanup | 일부 |
| CMS | JDK 1.4 / **제거 JDK 14** | Sweep + `CMSClassUnloadingEnabled` 옵션 | 일부 |
| ZGC | JDK 11 / **Concurrent Class Unloading JDK 14** | Concurrent | No |
| Shenandoah | JDK 12 | Concurrent | No |

→ "더 빠른 unload + STW 없음" 방향으로 일관되게 진화. 잦은 동적 클래스 생성 워크로드에서는 GC 선택 자체가 운영 안정성을 좌우.

---

## 7. 면접 답변 워크플로우

### 7.1 질문 → 가지 매핑

| 면접 질문 | 진입 가지 | 인접 확장 |
|---|---|---|
| "Metaspace가 Heap 안인가 밖인가?" | ② WHAT | ① WHY (왜 옮겼나) |
| "PermGen이 왜 죽었나요?" | ① WHY | ⑥ 진화 (JEP 122) |
| "ClassLoaderData가 뭔가요?" | ③ HOW | ⑤ 운영 (누수) |
| "Class<String>과 InstanceKlass 관계?" | ④ Klass vs mirror | ③ HOW (Metaspace 위치) |
| "Compressed Class Space 왜 별도?" | ② WHAT | ⑤ 운영 (1GB 한계) |
| "OOM:Metaspace 진단 절차?" | ⑤ 운영 | ③ HOW (CLD 흐름) |
| "Class Unloading 언제 일어나나?" | ③ HOW (GC sub-phase) | ⑥ 진화 (GC별) |
| "Elastic Metaspace는 뭐를 해결?" | ⑥ 진화 | ⑤ 운영 (footprint) |

### 7.2 답변 템플릿

> **루트 문장 한 줄 → 해당 가지 키워드 3개 → 듣는 사람 표정 보고 인접 가지로**

예: "ClassLoader 누수가 왜 위험한가요?"

> "Metaspace는 Heap 밖 native이고 ClassLoaderData 단위로 chunk를 받습니다. (← 루트)
> 첫째, 한 ClassLoader가 외부에서 strong reference로 잡히면 **그 CLD 전체가 영원히 unload 안 됩니다**.
> 둘째, 한 CL이 보통 수천~수만 클래스를 로드 → 한 누수 = 메가바이트 단위 chunk leak.
> 셋째, Hot deploy 환경(Tomcat, Spring DevTools)에서 매 reload마다 새 CL → leak 누적되면 며칠 안에 **OOM:Metaspace**.
> 진단은 `jcmd VM.classloader_stats`로 같은 이름 CL 누적을 보고, Heap dump + MAT의 ClassLoader Explorer로 누가 잡고 있는지 추적합니다."

---

## 8. 꼬리질문 트리 (가지별)

### Q1 [가지 ②]. Metaspace는 Heap 안인가요, 밖인가요?

> 밖. Native 메모리. JVM이 OS로부터 별도 `mmap`으로 받음. `-Xmx`로 제어 안 됨, `-XX:MaxMetaspaceSize`로 따로 제어(기본 unlimited). OOM도 별도 메시지: `OutOfMemoryError: Metaspace`.

**🪝 Q1-1: 그럼 Metaspace는 GC 대상인가요?**
> 정확히는 "Heap GC와 같은 cycle의 sub-phase(Class Unloading phase)에서 같이 처리"됨. Heap GC의 mark phase에서 ClassLoader의 reachability가 결정되고, unreachable한 CL의 CLD chunk가 그 cycle 안에서 통째로 free. 회수 단위가 객체(Heap)가 아니라 CLD(Metaspace)라는 게 PermGen과의 차이. `-Xlog:gc*`에는 안 보이고 `-Xlog:class+unload` 또는 JFR `jdk.ClassUnload`로 추적.

**🪝🪝 Q1-1-1: ClassLoader unload는 어떤 GC에서 일어나나요?**
> Serial/Parallel은 Full GC에서만. G1은 Concurrent Mark Cycle 끝 Cleanup. ZGC는 Concurrent Class Unloading (JDK 14+ STW 없음). Shenandoah는 Concurrent. → 잦은 hot reload 워크로드면 Serial/Parallel은 함정.

### Q2 [가지 ①]. PermGen이 왜 Metaspace로 바뀌었나요?

> 4가지 본질적 결함:
> 1. **크기 미리 픽스** — 동적 클래스 생성(Spring AOP, Mockito, CGLib) 많은 앱에서 OOM 빈발.
> 2. **GC 정책 충돌** — Heap의 generational GC와 메타데이터의 영구 보존 성격이 안 맞음.
> 3. **CL unload 비효율** — Heap 안에 흩어진 객체를 일일이 sweep.
> 4. **Compressed Oops 제약** — Klass 포인터 압축이 PermGen 위치에 묶임.
> 
> Metaspace는 native로 옮겨 모두 해결. 추가 배경: 2008년 Oracle의 JRockit 인수(JRockit은 이미 메타데이터를 native에 보관)가 직접 동기.

**🪝 Q2-1: JDK 8에서 String Pool은 어떻게 됐나요?**
> JDK 7부터 Heap의 일반 영역으로 이동. interned String이 일반 GC 대상이 됨. `String.intern()` 남용이 OOM:PermGen으로 이어지는 사고는 사라짐. 다만 너무 많이 intern하면 Heap의 String Pool 해시 충돌 → `-XX:StringTableSize`로 조정.

### Q3 [가지 ③]. ClassLoaderData가 뭐고 왜 중요한가요?

> 한 ClassLoader 인스턴스가 로드한 모든 클래스의 메타데이터를 묶는 단위. CLD는 자기만의 chunk 리스트를 보유. CL이 unreachable → CLD도 unreachable → 같은 GC cycle 안에서 chunk 통째 free. **개별 Klass를 sweep하지 않고 chunk를 통째로 free**하는 것이 Metaspace 효율의 핵심.

**🪝 Q3-1: 그럼 ClassLoader 누수가 왜 그렇게 위험한가요?**
> 한 CL이 외부에서 strong reference로 잡히면 그 CLD 전체가 영원히 unload 안 됨. 한 CL이 수천~수만 클래스 로드 → 한 누수 = 메가바이트 단위 chunk leak. Hot deploy 환경에서 매 reload마다 새 CL → leak 누적되면 며칠 안에 OOM:Metaspace.

**🪝🪝 Q3-1-1: 누수의 가장 흔한 패턴은?**
> 5대 패턴: ① 정적 캐시 (`static Map<..., Class<?>>`), ② ThreadLocal (톰캣 영구 스레드가 외부 CL 객체 보유, 톰캣 9+는 자동 detect/clean), ③ JDBC DriverManager (deregister 누락), ④ Logger context (Log4j2/Logback shutdown 누락), ⑤ Reflection cache. 진단: Heap dump → Eclipse MAT의 "Leak Suspects" → ClassLoader 추적.

### Q4 [가지 ②]. Compressed Class Space가 뭐고 왜 별도인가요?

> Klass 포인터를 32-bit로 압축하기 위한 별도 reserve 영역. 기본 1GB. 실제 주소 = `narrow_klass_base + (compressed << shift)`. Heap의 Compressed Oops와 별개 메커니즘 — Compressed Oops는 Heap 내부 ref용(32GB 제한), Compressed Class는 Metaspace의 Klass ref용(별도 1GB). Klass는 양이 적어 1GB로 충분.

**🪝 Q4-1: Compressed Class Space가 가득 차면?**
> `OutOfMemoryError: Compressed class space`. 해결: `-XX:CompressedClassSpaceSize=2g`로 키움, 또는 `-XX:-UseCompressedClassPointers`로 꺼서 일반 8-byte Klass Ptr 사용(객체당 4B 추가). 진짜 원인이 누수면 그것부터 고침 — Class 수 10만 이상이면 누수 의심.

### Q5 [가지 ④]. `Class<String>` 객체와 `InstanceKlass for String`은 같은 건가요?

> 다른 두 개의 객체.
> - `Class<String>` mirror — **Heap**의 일반 Java 객체. reflection이 만짐. `String.class`로 접근.
> - `InstanceKlass for String` — **Metaspace**의 HotSpot C++ 객체. vtable, itable, constant pool, method 코드.
> 
> 양방향 포인터: mirror의 `_klass` ↔ InstanceKlass의 `_java_mirror`. 객체 헤더의 Klass Pointer는 **mirror가 아니라 InstanceKlass**를 직접 가리킴.

**🪝 Q5-1: reflection이 `Method.invoke`할 때 실제 디스패치는?**
> ① `Method.invoke` → JDK 내부에서 mirror의 `_klass` → InstanceKlass 접근. ② `_methods` 배열에서 Method 메타데이터 lookup. ③ 인터프리터 또는 JIT 컴파일된 native code entry point로 jump. 처음 N번은 native 호출 → 임계 이상이면 동적 bytecode 어댑터 생성(`MethodAccessorImpl`)해서 invokevirtual 직접 호출. **Inflation**.

### Q6 (Killer) [가지 ⑤]. Spring Boot 앱이 hot reload할 때마다 RSS가 100MB씩 늘어납니다. 진단?

> 단계:
> 1. `jcmd VM.metaspace summary` — loaders 수가 reload 후 줄어드는지. 안 줄어들면 누수 확정.
> 2. `jcmd VM.classloader_stats` — 같은 이름 CL이 reload 횟수만큼 누적되어 있는지.
> 3. `-Xlog:class+unload:file=/tmp/unload.log` — reload 후 unload가 거의 없으면 누수.
> 4. Heap dump + MAT — "Histogram" → ClassLoader로 필터, 인스턴스 수가 reload 횟수와 같으면 누수, "GC Roots" 추적.
> 5. 흔한 범인 5종 점검: Spring DevTools RestartCL, 정적 캐시, JDBC driver deregister, Log4j2 shutdown, ThreadLocal.
> 6. 조치: 임시로 `-XX:MaxMetaspaceSize=512m` + 재시작 주기 짧게, 영구로 식별된 leak suspect 코드 수정.

**🪝 Q6-1: Heap dump 분석 없이 빠르게 좁히려면?**
> JFR을 짧게 켜고 `jdk.ClassLoad`, `jdk.ClassUnload`, `jdk.ClassLoaderStatistics` 이벤트 분석. ClassUnload가 거의 없음 → unload 메커니즘 자체 실패. 시간순 CLD 추세에서 줄어들어야 할 시점에 안 줄어들면 그 시점의 다른 이벤트(thread, lock 등)에서 단서.

### Q7 [가지 ⑥]. JEP 387 Elastic Metaspace가 뭐를 해결했나요?

> JDK 15. 옛 Metaspace는 chunk를 OS에 거의 반환 안 함 → 단명 CL이 많은 환경에서 chunk가 free list에 쌓이고 RSS는 그대로. 해결: ① Buddy allocator로 chunk 크기 등급 통일 → fragmentation ↓, ② Uncommit 적극화 — `madvise(MADV_DONTNEED)`로 OS에 페이지 반환(commit만 해제, reserve 유지), ③ footprint 10~20% 감소. 운영자에게 의미: JDK 15+에서 누수 진단이 더 정확.

---

## 9. 학습 체크리스트

면접 전 백지에서 다음을 다 해낼 수 있어야 마스터:

- [ ] 0장 마인드맵을 종이에 1분 이내로 그릴 수 있다 (루트 + 6가지 + 각 키워드 3개)
- [ ] 가지 ① WHY: PermGen의 4가지 결함을 차례로 말한다
- [ ] 가지 ② WHAT: Heap vs Native Memory 경계 그림을 그리고 Metaspace + Compressed Class Space 위치 표시
- [ ] 가지 ③ HOW: VirtualSpace → Chunk → Block 3단 구조와 CLD 소유권
- [ ] 가지 ③ HOW: ClassLoader unload 흐름을 GC sub-phase로 정확히 설명
- [ ] 가지 ④ Klass vs mirror: 두 객체의 위치, 양방향 포인터, 객체 헤더 Klass Ptr이 어느 쪽을 가리키는지
- [ ] 가지 ⑤ 운영: 5대 ClassLoader 누수 패턴
- [ ] 가지 ⑤ 운영: OOM:Metaspace 진단 플로우 4단계
- [ ] 가지 ⑥ 진화: PermGen→Metaspace (JEP 122) 동기, Elastic Metaspace (JEP 387)의 효과
- [ ] 가지 ⑥ 진화: GC별 Class Unloading 시점 매트릭스
- [ ] 8장 꼬리질문 7개에 막힘없이 답한다

---

## 다음 단계

- → [03. Stack & PC & Native Method Stack](./03-stack-pc-native.md): Per-Thread 영역
- → [04. Code Cache](./04-code-cache.md): JIT 결과 native code 저장소
- → [05. Direct Memory](./05-direct-memory.md): Off-heap NIO
- ← [01. Heap & TLAB](./01-heap-and-tlab.md): Heap의 세대 구조와 TLAB
- ← [01 class-lifecycle / 02 ClassLoader hierarchy](../01-class-lifecycle/02-classloader-hierarchy.md): ClassLoader 위임 모델

## 참고

- **JEP 122 (Remove PermGen)**: https://openjdk.org/jeps/122
- **JEP 387 (Elastic Metaspace)**: https://openjdk.org/jeps/387
- **HotSpot Glossary - Metaspace**: https://openjdk.org/groups/hotspot/docs/HotSpotGlossary.html
- **HotSpot `metaspace.cpp`**: https://github.com/openjdk/jdk/blob/master/src/hotspot/share/memory/metaspace.cpp
- **HotSpot `classLoaderData.cpp`**: https://github.com/openjdk/jdk/blob/master/src/hotspot/share/classfile/classLoaderData.cpp
- **JVMS §2.5.4 (Method Area)**: https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-2.html#jvms-2.5.4
- **Aleksey Shipilëv — Metaspace Tracking**: https://shipilev.net/blog/2014/oom-pseudo-jvm/
- **Tomcat ClassLoader Memory Leak Prevention**: https://wiki.apache.org/tomcat/MemoryLeakProtection
- **Eclipse MAT — ClassLoader Explorer**: https://www.eclipse.org/mat/documentation/
