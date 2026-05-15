# 02-02. Metaspace & Class Space — Heap 밖에 사는 클래스 메타데이터

> JVM은 `Class<?>` 객체와 그 안의 모든 메타정보(필드 시그니처, 메서드 바이트코드, Constant Pool 등)를 어디에 저장하는가?
> 답: **Heap이 아니다. Heap 밖, OS가 직접 관리하는 native 메모리 — Metaspace.**
> 그래서 `-Xmx`를 아무리 크게 잡아도 `OutOfMemoryError: Metaspace`는 따로 난다. 그리고 그게 ClassLoader 누수의 신호다.

---

## 📍 학습 목표

이 챕터가 끝나면 다음을 모두 답할 수 있다.

1. Metaspace가 **Heap이 아니라 native 메모리**인 이유와 그 결과 (OOM 메시지 분리, GC 정책 분리).
2. PermGen의 4가지 본질적 결함과, Metaspace가 각각 어떻게 해결했는지.
3. **ClassLoaderData**가 무엇이고 왜 Metaspace의 할당 단위인지 — "ClassLoader 단위 chunk 할당 → CL unload 시 통째 free".
4. **Compressed Class Space**가 별도로 존재하는 이유 (Klass 포인터 32-bit 압축) + 1GB 기본 제한 + Class 수 많은 Spring Boot 앱의 함정.
5. `Class<?>` Java 객체(Heap)와 `Klass` 메타데이터(Metaspace)가 **서로 다른 두 개의 객체**이며, 어떻게 연결되어 있는지 (mirror).
6. Metaspace의 메모리 할당 모델 — **VirtualSpace → Chunk → Block** 3단 구조.
7. `-XX:MetaspaceSize`, `-XX:MaxMetaspaceSize`, `-XX:CompressedClassSpaceSize`의 의미와 운영 가이드라인.
8. ClassLoader 누수의 5대 패턴 (정적 캐시, ThreadLocal, JDBC driver, Logger, Hot deploy)을 식별하고 진단할 수 있다.

---

## 🎨 1단계: 백지 그리기 가이드

### Step 1: 가장 큰 박스 — JVM 프로세스 메모리

- 큰 사각형을 그리고 라벨: "JVM Process Memory (OS가 보는 RSS)"
- 이 박스 안에 두 개의 큰 영역을 분할: **Java Heap** (왼쪽 40%) | **Native Memory** (오른쪽 60%)
- 라벨 강조: "Heap 경계 ─ Heap 안은 Java oop, Heap 밖은 native pointer"

### Step 2: Native Memory 안에 Metaspace 영역

- Native Memory 안 윗부분에 **Metaspace** 박스
- 그 옆 또는 안쪽에 별도의 **Compressed Class Space** 박스 (기본 1GB, JVM 시작 시 reserve)
- 라벨: "Compressed Class Space ⊂ Metaspace (조건부 활성)"

### Step 3: Metaspace를 3단 구조로

```
Metaspace (개념)
  ├── VirtualSpaceList     ← OS로부터 받은 큰 가상 주소 공간 (수십 MB 단위)
  │     └── VirtualSpaceNode (각각 ~2MB ~ ?)
  │           └── Chunk     ← ClassLoaderData에 부여되는 단위 (Specialized/Small/Medium/Humongous)
  │                 └── Block ← 실제 메타데이터 한 조각 (Klass, Method, ConstantPool, ...)
```

### Step 4: ClassLoaderData 별 chunk 그리기

- 5~6개의 작은 박스를 그리고 라벨: `Bootstrap CLD`, `Platform CLD`, `App CLD`, `WebApp1 CLD`, `WebApp2 CLD` ...
- 각 CLD에서 화살표로 Metaspace의 chunk들을 가리킴 (한 CLD가 여러 chunk를 들고 있음)
- 화살표 라벨: "CL unload 시 이 chunk들 통째 free"

### Step 5: Klass와 mirror

- Metaspace 안의 한 박스 라벨: `InstanceKlass for java.lang.String`
- Heap 안의 한 박스 라벨: `Class<String> Java 객체 (mirror)`
- 둘을 양방향 화살표로 연결: `_java_mirror` ↔ `klass` 필드

### Step 6: 사용자 객체와의 연결

- Heap 안에 작은 `String "hello"` 객체 박스
- 그 안에 Mark Word + Klass Pointer 표시
- Klass Pointer → Metaspace의 `InstanceKlass for String`을 가리키는 화살표
- 라벨: "객체 헤더의 Klass Pointer가 Metaspace를 가리킴 → 객체는 Heap에, 클래스 정보는 Metaspace에"

### 정답 그림 (ASCII)

```
JVM Process (RSS)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

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
│                                  │   │  │  [Method "length"]              │
│                                  │   │  │  [ConstantPool 본체]             │
│                                  │   │  └────────┬────────────────────┘    │
│                                  │   │           │ 소유: ClassLoaderData    │
│                                  │   │  ┌────────▼────────────────────┐    │
│                                  │   │  │ Bootstrap CLD                │    │
│                                  │   │  │  ├ chunk 1 (Medium)          │    │
│                                  │   │  │  ├ chunk 2 (Medium)          │    │
│                                  │   │  │  └ ...                       │    │
│                                  │   │  ├──────────────────────────────┤    │
│                                  │   │  │ App CLD                       │    │
│                                  │   │  │  └ chunk N (Small)            │    │
│                                  │   │  └──────────────────────────────┘    │
└─────────────────────────────────┘   └───────────────────────────────────┘
       ↑ GC 대상 (G1, ZGC, ...)              ↑ GC와 별개. CL unload 시 chunk 단위 free
       ↑ -Xmx 제어                           ↑ -XX:MaxMetaspaceSize (기본 unlimited)
       ↑ OOM: Java heap space                ↑ OOM: Metaspace
```

---

## 🧠 2단계: 직관

### 핵심 비유

> **도서관 비유**:
> - **Heap** = 열람실. 사람(인스턴스 객체)들이 들어와 책을 읽고 떠남. 사람은 계속 들고 남.
> - **Metaspace** = 카탈로그실. 책의 종류·저자·목차 같은 메타정보가 카드 캐비닛에 정리됨. 책(클래스) 종류가 늘면 캐비닛도 늘지만, 책 자체보다는 훨씬 작음.
> - **ClassLoaderData** = 한 출판사가 기증한 책 묶음 + 그 카탈로그 묶음. 그 출판사와 절연하면(CL unload) 카탈로그도 통째 폐기.
> - **Compressed Class Space** = 카탈로그 카드의 위치를 4자리 번호로 줄인 색인 책. 1만 장까지만 표현 가능 — 책이 그보다 많으면 색인 부족.
> - **mirror (Class 객체)** = 카탈로그에 적힌 책 정보를 사람이 들고 다닐 수 있게 만든 휴대용 메모지. 열람실(Heap)에 있어서 사람(코드)이 reflection으로 만질 수 있음.

### 정확한 정의 (비유와 분리)

| 용어 | 정의 |
|---|---|
| **Metaspace** | JVM이 클래스 메타데이터를 저장하는 **native 메모리 영역**. Heap 밖. 기본 무제한. JDK 8에서 PermGen을 대체. |
| **PermGen (Permanent Generation)** | JDK 7까지 클래스 메타데이터·String Pool·static 필드를 저장하던 **Heap 안의 영역**. 크기 고정, GC 대상. JDK 8에서 제거. |
| **Compressed Class Space** | Metaspace 중 `Klass*` 포인터 압축을 활성화한 별도 reserved 영역. 기본 1GB. `-XX:+UseCompressedClassPointers`. |
| **Klass / InstanceKlass** | Metaspace에 저장되는 클래스 메타데이터 객체 (HotSpot C++ 객체). bytecode·vtable·itable·constant pool·필드/메서드 정보 보유. Java 코드에선 직접 못 봄. |
| **mirror (`_java_mirror`)** | `InstanceKlass`에 대응하는 **Heap 안의 `Class<?>` Java 객체**. reflection이 만지는 그것. Metaspace의 Klass와 양방향 포인터로 연결. |
| **ClassLoaderData (CLD)** | 한 ClassLoader 인스턴스가 로드한 모든 클래스의 메타데이터를 묶는 단위. Metaspace의 chunk 소유권 단위. **CL이 unload되면 CLD 통째 free**. |
| **Chunk** | Metaspace가 CLD에 할당하는 메모리 덩어리. 크기 등급: Specialized / Small / Medium / Humongous. |
| **Block** | Chunk 안의 실제 한 객체(Klass·Method·ConstantPool 등)를 위한 메모리 조각. |
| **Constant Pool (runtime)** | 클래스의 상수·심볼릭 참조 테이블. resolve된 후 형태가 변함. Metaspace에 있음. |
| **vtable / itable** | 가상 메서드 / 인터페이스 메서드 dispatch 테이블. Metaspace의 Klass 뒤에 붙어 있음. |

### 왜 Heap 밖이어야 하나 — Heap에 두면 발생하는 4가지 문제

```
[Heap 안에 두면 (PermGen 시대)]            [Heap 밖에 두면 (Metaspace)]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━           ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. 크기 미리 못 잡음                          1. 동적 확장
   동적 클래스 생성(Spring AOP, Mockito,         OS의 가상 주소 공간만큼 자랄 수 있음
   Hibernate proxy) 양 예측 불가
   → -XX:MaxPermSize 미리 픽스
   → OOM:PermGen 빈발

2. GC 정책 충돌                               2. GC 분리
   PermGen은 일반 객체와 다른 수명을 가짐         ClassLoader 단위 chunk free
   (대부분 영구 보존)                            (별도 메커니즘)
   그런데 GC는 같은 정책 적용

3. ClassLoader unload 비효율                  3. CLD 단위 통째 free
   PermGen 안에 흩어진 객체들                    chunk들이 CLD에 소유됨
   각각 sweep해야 함                            CL unload = chunk 통째 free (O(1))

4. Compressed Oops 제약                       4. 별도 Compressed Class Space
   Klass 포인터 압축 위치가 Heap 안에            Heap과 독립적으로 압축 가능
   고정 → 압축 전략 제약
```

→ JEP 122의 motivation. 이 4가지가 PermGen 폐기의 본질.

### 왜 ClassLoaderData가 핵심인가 — chunk 회수의 단위

```
ClassLoader가 로드한 클래스들의 메타데이터는 어디로 모이나?
                  │
                  ▼
         같은 ClassLoaderData(CLD)에 묶인다
                  │
                  ▼
         CLD는 자기만의 chunk 리스트를 가짐
                  │
                  ▼
   ClassLoader가 unreachable해지면?
                  │
                  ▼
        그 CLD도 unreachable
                  │
                  ▼
        CLD가 가진 chunk들을 통째 free
        (개별 Klass 단위 sweep 필요 없음)
```

**그래서 ClassLoader 누수가 그토록 위험한 것**: 사용자 코드 한 줄(`Thread.currentThread().setContextClassLoader(webappCL)`)이 안 풀리면 그 CL의 모든 메타데이터(클래스 수천 개)가 영원히 못 풀림.

### 왜 Compressed Class Space는 따로 있나

```
일반 Klass 포인터 (64-bit):  8 byte
                              ↓
Compressed Klass Pointer:    4 byte
                              ↓
실제 주소 = base + (compressed << 3)
                              ↓
4G × 8 = 최대 32GB까지 표현 가능... 인가? NO.

★ Compressed Klass는 Heap의 Compressed Oops와 별개의 메커니즘.
   - Compressed Oops: Heap 내부 객체 참조용. 32GB 제한.
   - Compressed Class: Metaspace의 Klass 참조용. 별도 1GB reserve 영역.

Klass는 양이 적음(클래스 수 ≈ 수만 ~ 수십만 개) → 1GB로도 충분.
포인터 압축에 필요한 base를 만들기 위해 별도 reserve.
```

`-XX:CompressedClassSpaceSize=1g` (기본). Class 수가 많은 Spring Boot 거대 앱에서 이 한계가 OOM:Metaspace의 원인이 되기도 함 (특히 ClassLoader 누수 + 동적 클래스 생성 조합).

---

## 🔬 3단계: 구조

### Metaspace의 3단 메모리 모델

```
[1단: VirtualSpaceList]
━━━━━━━━━━━━━━━━━━━━━━
OS로부터 큰 가상 주소 공간을 reserve (mmap)
기본 unit: 2MB ~ 그 이상
여러 개의 VirtualSpaceNode를 linked list로 보유

  VirtualSpaceList
    └── Node 1 (2MB)
    └── Node 2 (2MB)
    └── Node 3 (4MB)
    └── ...

[2단: Chunk]
━━━━━━━━━━━
각 VirtualSpaceNode를 chunk로 분할
chunk 크기 등급:
  - Specialized chunk : 1KB    (작은 Klass용)
  - Small chunk       : 4KB    (일반 클래스용)
  - Medium chunk      : 64KB   (대부분의 일반 클래스)
  - Humongous chunk   : 가변    (큰 클래스/메서드)

  VirtualSpaceNode (2MB)
    └── Medium Chunk (64KB)  ← App CLD가 소유
    └── Medium Chunk (64KB)  ← App CLD가 소유 (2번째)
    └── Small Chunk  (4KB)   ← 작은 라이브러리 CLD가 소유
    └── ...

[3단: Block]
━━━━━━━━━━
Chunk 안에 실제 메타데이터 객체를 bump-the-pointer로 할당
TLAB의 Metaspace 버전. 단, per-CLD가 아닌 per-chunk.

  Medium Chunk (64KB), owned by App CLD
    ┌──────────────────────────────────────┐
    │ [InstanceKlass for com.foo.Bar]      │
    │ [Method "doIt"]                      │
    │ [Method "doThat"]                    │
    │ [ConstantPool for Bar]               │
    │ [InstanceKlass for com.foo.Baz]      │
    │ ─── top ───                          │
    │ (free)                                │
    └──────────────────────────────────────┘
```

### ClassLoaderData (CLD)와 chunk 소유권

```
ClassLoader 인스턴스 ←─────── (1:1) ───────→ ClassLoaderData
                                              ├── _chunks : [Chunk*, Chunk*, ...]
                                              ├── _klasses: [Klass*, Klass*, ...]
                                              ├── _dictionary: name → Klass
                                              └── _next: 다음 CLD (전체 CLD 리스트의 일원)

ClassLoaderDataGraph (전역)
  ├── Bootstrap CLD       (struct, not Java object)
  ├── Platform CLD        (corresponds to PlatformClassLoader)
  ├── App CLD             (corresponds to AppClassLoader)
  ├── WebApp1 CLD         (corresponds to Tomcat WebappClassLoader #1)
  ├── WebApp2 CLD         ...
  └── (anonymous CLD)     (Unsafe.defineAnonymousClass 등 LambdaForm용)
```

핵심 규칙:
- **모든 ClassLoader 인스턴스(Bootstrap 제외)는 정확히 하나의 CLD를 가진다**.
- 같은 CL이 로드한 모든 클래스의 Klass·Method·CP는 그 CLD의 chunk에 들어간다.
- CL이 unreachable해지면 CLD도 unreachable → 다음 GC에서 CLD가 회수되고 chunk들이 free pool로 반환.

### Klass의 내부 구조 (InstanceKlass)

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
│  ├ _fields (Array<u2>: name_idx, sig_idx, ...)  │ │
│  ├ _constants (ConstantPool*)                   │ │
│  ├ _itable (interface dispatch table)           │ │
│  └ _vtable (virtual dispatch table)             │ │
├─────────────────────────────────────────────────┤ │
│ Embedded vtable [size_t × N]                    │ │
├─────────────────────────────────────────────────┤ │
│ Embedded itable [...]                           │ │
├─────────────────────────────────────────────────┤ │
│ OopMap blocks (GC가 어디서 ref인지 알아야)        │ │
└─────────────────────────────────────────────────┘ │
                                                    │
   ┌────────────────────────────────────────────────┘
   ▼
Heap의 Class<String> 객체 (mirror)
  ├ _klass ─────────────→ 위의 InstanceKlass (양방향)
  └ Java reflection이 보는 모든 것
```

### Klass와 mirror — 같은 클래스에 대한 두 개의 표현

```
Java 코드에서 String.class
   │
   ▼
Heap의 Class<String> 객체 (= mirror)
   ├── 모든 Java reflection API의 진입점
   ├── classLoader, name, modifiers 등을 getter로 노출
   ├── 일반 Java 객체이므로 GC 대상
   │
   └── _klass 필드 ──→ Metaspace의 InstanceKlass
                        ├── 실제 메타데이터 (vtable, itable, methods, ...)
                        ├── HotSpot 내부 코드만 직접 접근
                        ├── GC는 CLD chunk 단위로 처리
                        └── _java_mirror 필드 ──→ 위의 Class<String>로 역참조
```

→ **두 개의 별도 객체, 양방향 포인터, 다른 메모리 영역, 다른 GC 정책**. 면접에서 자주 묻는 디테일.

### Klass의 ClassLoader 추적

```
Klass._class_loader_data → CLD → CLD._class_loader (Java ClassLoader 객체)
                              ↑
                              └── CL이 unreachable이면 CLD도 unreachable
```

이게 ClassLoader unload가 가능한 메커니즘. CL → CLD → chunk → Klass 모두 같은 운명.

### Metaspace allocate 흐름

```
새 클래스 로드: defineClass(...) 호출
        │
        ▼
ClassLoader가 ClassFile bytes를 파싱
        │
        ▼
JVM이 InstanceKlass를 위한 메모리 요청
        │
        ▼
이 CL에 해당하는 CLD를 lookup (없으면 생성)
        │
        ▼
CLD의 현재 chunk에 공간 있나?
   ├── Yes: bump-the-pointer로 Block 할당
   └── No:  새 chunk 요청
            ├── chunk free list에 적당한 크기 있나?
            │   ├── Yes: 가져옴
            │   └── No: VirtualSpaceList에서 새 chunk 분할
            │           ├── 현재 Node에 공간 있나?
            │           │   ├── Yes: 분할
            │           │   └── No: OS에서 새 Node mmap
        │
        ▼
InstanceKlass를 그 Block에 placement new
        │
        ▼
CLD._klasses에 추가, CLD._dictionary에 등록
```

### ClassLoader unload 흐름

```
ClassLoader 객체가 unreachable
        │
        ▼
GC가 mark phase에서 CL을 못 따라감
        │
        ▼
GC가 ClassLoaderDataGraph를 walk
   "각 CLD의 CL_oop이 마킹됐는지?"
        │
        ▼
마킹 안 된 CLD를 dead로 표시
        │
        ▼
ClassLoaderData::unload() 호출
   ├── CLD가 가진 모든 Klass의 mirror (Heap의 Class 객체)도 unreachable
   │   → 일반 Heap GC가 회수
   ├── CLD가 가진 모든 chunk를 free list로 반환
   ├── _dictionary, _klasses 정리
   └── CLD 자체도 free
        │
        ▼
다음 GC cycle에서 빈 VirtualSpaceNode가 있으면 OS에 반환 (uncommit)
```

핵심: **CLD 단위 통째 free**. 개별 Klass를 하나씩 GC하는 것보다 훨씬 빠르고 정확.

### 시대별 변화 — PermGen vs Metaspace

```
[JDK 7까지]                                  [JDK 8+]
━━━━━━━━━━━                                  ━━━━━━━━━━
Java Heap                                    Java Heap
├── Young Gen                                ├── Young Gen
├── Old Gen                                  ├── Old Gen
└── PermGen ★                                └── String Pool (일반 영역)
    ├── Class 메타데이터                       
    ├── interned String                      Native Memory
    ├── static 필드                          ├── Metaspace ★
    └── method 코드                            │   ├── Class 메타데이터
                                              │   └── method 코드
                                              ├── Compressed Class Space ★ (옵션)
                                              │   └── Compressed Klass 포인터용 reserve
                                              └── ...

크기: -XX:MaxPermSize=256m (기본)             크기: 기본 unlimited (-XX:MaxMetaspaceSize)
관리: Heap GC가 같이 처리                       관리: ClassLoaderData 단위 chunk
OOM: OutOfMemoryError: PermGen space          OOM: OutOfMemoryError: Metaspace
```

---

## 🧬 4단계: 내부 구현 — HotSpot

### Metaspace 초기화

위치: `src/hotspot/share/memory/metaspace.cpp`

```cpp
// Metaspace::global_initialize() (요약)
void Metaspace::global_initialize() {
  // 1. Compressed Class Space의 base 결정
  //    Heap base 위쪽 또는 별도 위치에 1GB reserve
  if (UseCompressedClassPointers) {
    size_t reserve_size = CompressedClassSpaceSize;  // 기본 1GB
    char* base = ...;  // 가상 주소 결정
    _class_space_list = new VirtualSpaceList(reserve_size, base);
    _narrow_klass_base = base;
    _narrow_klass_shift = ...;
  }

  // 2. 일반 Metaspace VirtualSpaceList
  _space_list = new VirtualSpaceList(VIRTUAL_SPACE_SIZE);

  // 3. Chunk manager (free chunk 재활용 풀)
  _chunk_manager_metadata = new ChunkManager(...);
  _chunk_manager_class    = new ChunkManager(...);
}
```

### ClassLoaderData 할당

위치: `src/hotspot/share/classfile/classLoaderData.cpp`

```cpp
// ClassLoaderData::add_class (요약)
void ClassLoaderData::add_class(Klass* k) {
  // 1. _klasses 리스트에 추가 (LinkedList)
  k->set_next_link(_klasses);
  Atomic::store(&_klasses, k);

  // 2. dictionary에 이름으로 등록 (resolve용)
  if (k->is_instance_klass()) {
    _dictionary->add_klass(...);
  }
}

// allocate 시 (요약)
Metablock* ClassLoaderData::metaspace_non_null()->allocate(size_t word_size, ...) {
  // 1. 현재 chunk에 공간 있나?
  Metablock* result = current_chunk()->allocate(word_size);
  if (result != NULL) return result;

  // 2. 없으면 새 chunk 요청
  Metachunk* new_chunk = ChunkManager::chunk_freelist_allocate(...);
  if (new_chunk == NULL) {
    new_chunk = VirtualSpaceList::get_new_chunk(...);
  }

  // 3. 새 chunk를 CLD의 chunk 리스트에 추가
  _chunks.add(new_chunk);
  return new_chunk->allocate(word_size);
}
```

### ClassLoader unload 감지

위치: `src/hotspot/share/classfile/classLoaderDataGraph.cpp`

```cpp
// ClassLoaderDataGraph::do_unloading (요약)
bool ClassLoaderDataGraph::do_unloading() {
  bool seen_dead_loader = false;

  // 1. 전체 CLD 리스트를 순회하며 mirror가 살아있는지 확인
  ClassLoaderData* data = _head;
  ClassLoaderData* prev = NULL;
  while (data != NULL) {
    if (data->is_alive()) {
      // 살아있음 → 다음 CLD로
      prev = data;
      data = data->next();
    } else {
      // 죽음 → unload 처리
      seen_dead_loader = true;

      // 2. mirror oop들을 weak handle에서 제거
      data->unload();

      // 3. CLD가 가진 chunk들을 free list로 반환
      data->free_deallocate_list();
      data->classes_do(&unload_klasses_closure);

      // 4. CLD 자체를 unlink
      if (prev == NULL) _head = data->next();
      else prev->set_next(data->next());

      ClassLoaderData* dead = data;
      data = data->next();
      delete dead;
    }
  }
  return seen_dead_loader;
}
```

### Klass와 mirror 연결

위치: `src/hotspot/share/oops/klass.cpp`, `src/hotspot/share/classfile/javaClasses.cpp`

```cpp
// java_lang_Class::create_mirror (요약)
oop java_lang_Class::create_mirror(Klass* k, Handle classLoader, ...) {
  // 1. Heap에 Class<?> 객체 할당 (일반 객체 할당과 동일)
  oop mirror = InstanceKlass::cast(SystemDictionary::Class_klass())
                  ->allocate_instance(CHECK);

  // 2. Klass → mirror 포인터 설정 (Metaspace → Heap 방향)
  k->set_java_mirror(mirror);

  // 3. mirror → Klass 포인터 설정 (Heap → Metaspace 방향)
  java_lang_Class::set_klass(mirror, k);

  // 4. mirror에 추가 필드 설정 (classLoader, protectionDomain, ...)
  java_lang_Class::set_class_loader(mirror, classLoader());
  ...

  return mirror;
}
```

→ Heap의 mirror와 Metaspace의 Klass는 이 함수에서 한 번에 묶임. 이후 GC는 mirror가 reachable한 한 Klass도 살린다는 invariant를 가정.

### Compressed Klass Pointer 인코딩/디코딩

위치: `src/hotspot/share/oops/compressedOops.hpp` (와 비슷한 패턴)

```cpp
// 인코딩: Klass* → narrowKlass (4 byte)
inline narrowKlass CompressedKlassPointers::encode(Klass* k) {
  uint64_t pd = (uint64_t)k - (uint64_t)_narrow_klass_base;
  return (narrowKlass)(pd >> _narrow_klass_shift);
}

// 디코딩: narrowKlass → Klass*
inline Klass* CompressedKlassPointers::decode(narrowKlass v) {
  return (Klass*)((uint64_t)_narrow_klass_base + ((uint64_t)v << _narrow_klass_shift));
}
```

→ 객체 헤더의 4-byte Klass Pointer가 매 메서드 호출/필드 접근마다 디코딩됨. shift는 보통 3 (8바이트 정렬).

---

## 📜 5단계: 역사

| 연도 | 릴리스 | 변화 | 트리거/이유 |
|---|---|---|---|
| 1996 | JDK 1.0 | Heap 안에 PermGen, 메타데이터·String·static 보관 | 초기 설계 |
| 2003 | JDK 1.4 | Compressed Oops 도입 (실험) | 64-bit 이행 시 메모리 부담 |
| 2009 | JDK 6u14 | Compressed Oops 기본 활성 | |
| 2010 | JDK 7 | **String Pool을 Heap의 일반 영역으로 이동** | PermGen 정리의 1단계 — interned String이 GC 대상 됨 |
| 2014 | JDK 8 | **PermGen 제거 → Metaspace** ([JEP 122](https://openjdk.org/jeps/122)) | OOM:PermGen 빈발, 동적 클래스 생성 대응, JRockit 통합 |
| 2014 | JDK 8 | **Compressed Class Space 도입** | Compressed Klass Pointer를 위한 별도 reserve |
| 2017 | JDK 9 | Metaspace 메모리 회수 개선 | ClassLoader unload 시 더 적극적인 uncommit |
| 2020 | JDK 15 | **Elastic Metaspace** ([JEP 387](https://openjdk.org/jeps/387)) | 단편화 감소, OS로 메모리 반환 개선, 메모리 footprint ↓ |
| 2023 | JDK 21 | Metaspace 안정화 | 별 큰 변화 없음, JEP 387 결과 정착 |

### JEP 122 — PermGen 제거의 진짜 배경

> 2008년 Oracle이 BEA Systems(JRockit)를 인수.
> JRockit은 이미 PermGen이 없었고 (메타데이터를 native에 보관), 두 JVM의 통합이 목표 중 하나.
> Hotspot도 같은 방향으로 옮겨감 → JDK 8 Metaspace.

### JEP 387 — Elastic Metaspace의 동기

- 옛 Metaspace는 chunk를 OS에서 받아가지만, **거의 OS에 반환하지 않음**.
- 결과: 단명 ClassLoader(예: hot deploy, lambda anonymous)가 많이 생기면 chunk들이 free list에 쌓이고 RSS는 그대로.
- JEP 387:
  - **Buddy allocator** 도입 (chunk size 등급을 power-of-2로 통일).
  - **uncommit** 적극화 (사용 안 하는 chunk의 메모리 페이지를 OS에 반환).
  - 결과: 동일 워크로드에서 Metaspace footprint **10~20% 감소**.

### "JRE 폐기"와 Metaspace의 관계 (보너스)

JDK 9에서 전통적인 JRE 별도 배포가 종료됐는데, Metaspace는 그 이전 (JDK 8)에 이미 도입. 두 변화는 독립적이지만, 둘 다 "더 작고 모듈화된 런타임" 방향성의 일부.

---

## ⚖️ 6단계: 트레이드오프

### Metaspace 크기 제한 — 두면 vs 안 두면

| `-XX:MaxMetaspaceSize=N` 설정 | 설정 안 함 (기본) |
|---|---|
| ✅ ClassLoader 누수 시 빠르게 터짐 → 발견 빠름 | ❌ 누수가 OS 전체 메모리 압박할 때까지 안 보임 |
| ✅ 컨테이너 친화 (메모리 예측 가능) | ❌ 컨테이너 OOM-killed 위험 (RSS 폭증) |
| ❌ legitimate한 동적 클래스 생성 막힐 수 있음 | ✅ Dynamic codegen 자유 |
| ❌ 크기 결정에 측정 필요 | ✅ 안 잡고도 동작 |

**경험칙**:
- Container 환경: 반드시 설정 (`512m` ~ `1g` 사이가 일반적).
- Spring Boot 거대 모놀리스: 측정 후 600~800m.
- Hot deploy 환경 (Tomcat, JBoss): 더 크게 + ClassLoader 누수 모니터링 필수.

### Compressed Class Pointer 켜기 vs 끄기

| `-XX:+UseCompressedClassPointers` (기본) | `-XX:-UseCompressedClassPointers` |
|---|---|
| ✅ 객체당 4 byte 절약 | ❌ 객체당 8 byte Klass Ptr |
| ✅ 일반 Spring Boot에서 footprint 5~10% ↓ | ✅ 별도 1GB reserve 영역 없음 |
| ❌ Compressed Class Space가 1GB 추가 reserve | ✅ Metaspace 단일 통합 |
| ❌ Class 수 ≥ 수십만이면 1GB 한계 OOM | ✅ Class 수 한계 없음 |

→ 99%는 default(켬)가 정답. **Class 수가 10만 개 이상**인 거대 앱(거대 마이크로서비스 모놀리스, 동적 codegen 많은 앱)에서만 끄거나 `-XX:CompressedClassSpaceSize=2g` 조정.

### Metaspace vs PermGen의 트레이드오프 (역사적 비교)

| | PermGen (JDK ≤ 7) | Metaspace (JDK 8+) |
|---|---|---|
| 위치 | Heap 안 | Native 메모리 |
| 크기 제한 | 미리 픽스 (`-XX:MaxPermSize`) | 기본 unlimited |
| GC 정책 | Heap GC와 통합 | CLD chunk 단위 별도 |
| ClassLoader unload | 비효율 (sweep 단위) | 효율적 (chunk 통째 free) |
| OOM 메시지 | `OutOfMemoryError: PermGen space` | `OutOfMemoryError: Metaspace` |
| Compressed Oops 호환 | ❌ (위치 제약) | ✅ 독립적 |
| 동적 클래스 생성 친화 | ❌ (예측 못 함) | ✅ |
| 단점 | 모든 면에서 한계 | OS 메모리 보호 직접 안 됨 (-Xmx 무관) |

→ 결과적으로 **모든 면에서 Metaspace가 우위**. PermGen은 시대적 제약의 산물.

### Class 수 vs Metaspace 메모리 추정

```
일반 클래스 1개당 메타데이터 footprint (Compressed Class 활성):
  - InstanceKlass + vtable + itable: ~500 byte ~ 수 KB
  - ConstantPool: 클래스 복잡도 따라 수 KB
  - Method 1개당: ~100 byte ~ 수 백 byte
  - 평균적으로 클래스 1개 ≈ 5~10 KB

→ Spring Boot 일반 앱: 클래스 1만 개 ≈ 50~100 MB
→ 거대 모놀리스: 클래스 10만 개 ≈ 500MB ~ 1GB
→ Dynamic proxy/AOP 폭주 시 +200~500 MB
```

이 값을 기반으로 `-XX:MaxMetaspaceSize` 결정.

---

## 📊 7단계: 측정·진단

### Metaspace 사용 현황 즉시 확인

```bash
# 요약 (chunk 등급별 사용량 포함)
jcmd <pid> VM.metaspace summary

# 상세 (CLD별 분해)
jcmd <pid> VM.metaspace

# 출력 예시 (summary):
# Total Usage - 5023 loaders, 25341 classes (153 shared):
#   Non-Class: ... reserved 156Mb, committed 154Mb, used 152Mb
#   Class: ... reserved 1Gb, committed 24Mb, used 22Mb
#   Both: ... reserved 1Gb, committed 178Mb, used 174Mb
```

판독:
- **loaders** — 살아있는 CLD 개수. **수만 개면 ClassLoader 누수 의심**.
- **classes** — 로드된 클래스 총 수. 갑자기 증가하면 dynamic codegen 폭주.
- **Non-Class / Class** — Class는 Compressed Class Space, Non-Class는 일반 Metaspace.
- **reserved / committed / used** — committed가 used에 비해 너무 크면 단편화 (JEP 387 이전).

### ClassLoader별 클래스 수

```bash
jcmd <pid> VM.classloader_stats
```

출력 예:
```
ClassLoader        Parent           Classes  ChunkSz  BlockSz  Type
0x00007fxxxxxxxx   ---              4        4096    1024    com.example.LeakingCL
0x00007fxxxxxxxx   <bootstrap>     150       65536   45000   sun.misc.Launcher$AppClassLoader
...
```

핵심:
- 같은 이름의 CL 인스턴스가 수십~수천 개 보이면 **ClassLoader 누수 확정**.
- 특히 Tomcat WebappClassLoader, Spring DevTools 환경에서 hot reload 누적.

### Metaspace 추세 모니터링

```bash
# 1초 간격으로 Metaspace 사용량
jstat -gc <pid> 1s | awk '{print $13, $14, $15, $16}'
# MC(Metaspace Capacity), MU(Used), CCSC(CompressedClass Capacity), CCSU(Used)
```

또는 JFR:

```bash
jcmd <pid> JFR.start name=meta duration=300s settings=profile filename=meta.jfr
```

핵심 이벤트:
- `jdk.MetaspaceSummary` — 매 GC 후 Metaspace 상태
- `jdk.MetaspaceGCThreshold` — Metaspace 압박으로 GC 트리거된 케이스
- `jdk.ClassLoaderStatistics` — CLD 별 통계
- `jdk.ClassLoad` / `jdk.ClassUnload` — 클래스 로드/언로드 추적

### OutOfMemoryError: Metaspace 진단 플로우

```
"OutOfMemoryError: Metaspace" 발생
              │
              ▼
1. jcmd <pid> VM.metaspace summary
   ├── loaders 수가 비정상 (수만 ~ 수십만)?
   │     ▼
   │     ClassLoader 누수 가능성
   │
   └── loaders 수는 정상 (수백~수천)?
         ▼
         Class 수 폭증 가능성 (dynamic codegen)
              │
              ▼
2. jcmd <pid> VM.classloader_stats
   ├── 같은 이름의 CL이 수십 개 이상?
   │     ▼
   │     Hot deploy 누수 (Tomcat, Spring DevTools)
   │
   └── 한 CL이 비정상적으로 많은 클래스?
         ▼
         Dynamic proxy / CGLib 폭주 (Hibernate, Spring AOP, Mockito)
              │
              ▼
3. Heap dump + MAT로 leak suspect
   "GC Roots" → ClassLoader 추적
   "Classloader Explorer" 뷰
              │
              ▼
4. 원인 코드 식별 후 수정:
   - 정적 캐시에 외부 CL의 클래스 보관 중인가?
   - ThreadLocal이 CL 종료 시 정리 안 되는가?
   - JDBC DriverManager.deregisterDriver() 누락?
   - SLF4J / Log4j logger context 누수?
```

### ClassLoader 누수의 5대 패턴

| # | 패턴 | 원인 | 진단 |
|---|---|---|---|
| 1 | **정적 캐시 누수** | `static Map<String, Class<?>>` 가 외부 CL의 클래스를 잡고 있음 | Heap dump → static 필드 추적 |
| 2 | **ThreadLocal 누수** | 톰캣 스레드풀의 스레드가 죽지 않고 ThreadLocal이 외부 CL의 객체를 잡음 | jstack + Heap dump 교차 |
| 3 | **JDBC DriverManager** | `DriverManager.registerDriver()` 했는데 `deregister`를 안 함. JDK가 driver를 잡고 있어 그 클래스의 CL 못 회수 | shutdown hook에서 `deregisterDriver` |
| 4 | **Logger context** | Log4j2 / Logback이 자기 CL을 통해 클래스를 잡음 | Logger context shutdown 호출 누락 확인 |
| 5 | **Reflection cache** | `Class.getMethod()`, `Field.setAccessible()`가 만든 캐시가 CL 보유 | reflection의 정적 캐시 비우기 |

### 운영 함정 진단 매트릭스

| 증상 | 진단 명령 | 가능 원인 |
|---|---|---|
| `OOM: Metaspace` 주기적 발생 | `jcmd VM.classloader_stats` | ClassLoader 누수 |
| `OOM: Compressed class space` | `jcmd VM.metaspace summary` Class 영역 reserved 확인 | Class 수 1GB 한계 초과 |
| RSS가 Heap 크기와 무관하게 증가 | `jcmd VM.native_memory summary` | Metaspace 비대 |
| Hot deploy 후 응답 느림 | `jstat -gc 1s` MU 증가 추세 | CLD가 정리 안 됨 |
| Lambda heavy 코드의 메모리 ↑ | `-Xlog:class+load=info`로 anonymous 클래스 추적 | LambdaForm 누적 |

### 의도적 재현 — ClassLoader 누수를 만들어 보는 코드

```java
// 정적 캐시가 외부 CL의 클래스를 잡는 케이스 (재현용)
public class LeakDemo {
    private static final Map<String, Class<?>> LEAK = new HashMap<>();

    public static void main(String[] args) throws Exception {
        for (int i = 0; i < 1000; i++) {
            URL[] urls = { new File("plugin.jar").toURI().toURL() };
            URLClassLoader cl = new URLClassLoader(urls);
            Class<?> c = cl.loadClass("com.foo.PluginImpl");
            LEAK.put("plugin-" + i, c);  // ★ 이 한 줄로 cl이 영원히 unreachable 안 됨
            // cl.close()를 해도 c가 살아있으면 cl도 살아있음
        }
        Thread.sleep(Long.MAX_VALUE);
    }
}
```

```bash
java -XX:MaxMetaspaceSize=128m -Xlog:class+unload LeakDemo
# → 잠시 후 OutOfMemoryError: Metaspace
# → class+unload 로그가 거의 안 찍힘 → unload 안 되고 있음 확정
```

---

## ⚔️ 8단계: 꼬리질문 트리

### Q1. Metaspace는 Heap 안에 있나요, 밖에 있나요?

**예상 답변**:
> 밖. Native 메모리 영역.
> JVM이 OS로부터 별도 mmap으로 받음.
> 그래서 `-Xmx`로 제어 안 됨. `-XX:MaxMetaspaceSize`로 따로 제어 (기본 unlimited).
> OOM도 별도 메시지: `OutOfMemoryError: Metaspace`.

#### 🪝 꼬리 Q1-1: "그럼 Metaspace는 GC 대상인가요?"

**예상 답변**:
> 일반 Heap GC와는 다른 메커니즘.
> Heap GC가 mark phase에서 ClassLoader 객체를 못 따라가면, 그 CL에 해당하는 CLD가 dead로 표시되고 다음 GC cycle에 CLD의 chunk들이 통째 free됨.
> 즉, **CLD 단위로 처리**되지 개별 Klass 단위로 sweep하지 않음.
> 일반 GC log(`-Xlog:gc*`)에서는 안 보이고, `-Xlog:class+unload` 또는 JFR `jdk.ClassUnload`로 추적.

##### 🪝 꼬리 Q1-1-1: "ClassLoader unload는 어떤 GC에서 일어나나요?"

**예상 답변**:
> 일반적으로 **major / mixed GC 또는 concurrent cycle**에서.
> G1: Mixed GC 또는 Remark 단계.
> CMS (제거됨): Concurrent Sweep 중.
> ZGC: Concurrent Mark End.
> Shenandoah: Final Mark.
> 단순 Young GC만 도는 동안에는 CLD가 dead로 검사 안 됨 → ClassLoader 누수의 메모리 증가는 Major GC 사이에서 보임.

### Q2. PermGen이 왜 Metaspace로 바뀌었나요?

**예상 답변**:
> PermGen의 4가지 본질적 결함:
> 1. **크기 미리 픽스** — 동적 클래스 생성(Spring AOP, Mockito, CGLib) 많은 앱에서 OOM 빈발.
> 2. **GC 정책 충돌** — Heap의 generational GC와 메타데이터의 영구 보존 성격이 안 맞음.
> 3. **CL unload 비효율** — Heap 안에 흩어진 객체를 일일이 sweep.
> 4. **Compressed Oops 제약** — Klass 포인터 압축이 PermGen 위치에 묶임.
> 
> Metaspace는 native 메모리로 옮겨서 모두 해결:
> - 크기: OS 가상 주소 공간만큼 동적 확장.
> - GC: CLD 단위 chunk 통째 free.
> - 압축: Compressed Class Space 별도 reserve.
> 
> 추가로 **JEP 122**의 직접 동기는 Oracle의 JRockit 통합 (JRockit은 이미 PermGen이 없었음).

#### 🪝 꼬리 Q2-1: "JDK 8에서 String Pool은 어떻게 됐나요?"

**예상 답변**:
> JDK 7부터 이미 Heap의 일반 영역으로 이동했음 (PermGen 정리의 1단계).
> JDK 8에서는 그 결정이 굳어짐.
> 결과: interned String이 일반 GC 대상이 됨 → `String.intern()`을 남용해도 OOM:PermGen 같은 사고는 안 남.
> 단, 너무 많이 intern하면 Heap의 String Pool 해시 충돌 → 응답 느려질 수 있음 (`-XX:StringTableSize`로 조정).

### Q3. ClassLoaderData가 뭐고 왜 중요한가요?

**예상 답변**:
> 한 ClassLoader 인스턴스가 로드한 모든 클래스의 메타데이터를 묶는 단위.
> CLD는 자기만의 chunk 리스트를 들고 있음.
> ClassLoader가 unreachable해지면 → 그 CLD도 unreachable → 다음 GC에서 chunk들 통째 free.
> **개별 Klass를 sweep하지 않고 chunk를 통째로 free**하는 것이 Metaspace 효율의 핵심.

#### 🪝 꼬리 Q3-1: "그럼 ClassLoader 누수가 왜 그렇게 위험한가요?"

**예상 답변**:
> 한 ClassLoader가 외부 어디선가 strong reference로 잡혀 있으면 그 CL의 CLD 전체가 영원히 unload 안 됨.
> 한 CL이 보통 수천~수만 개 클래스를 로드 → 한 누수 = 메가바이트 단위 chunk leak.
> Hot deploy 환경(Tomcat, Spring DevTools)에서 매 reload마다 새 CL 생성 → leak이 누적되면 며칠 안에 OOM:Metaspace.

##### 🪝 꼬리 Q3-1-1: "ClassLoader 누수의 가장 흔한 패턴은?"

**예상 답변**:
> 5대 패턴:
> 1. **정적 캐시** — `static Map<..., Class<?>>` 또는 `static List` 가 외부 CL의 객체를 잡음.
> 2. **ThreadLocal** — 톰캣 스레드풀의 영구 스레드가 ThreadLocal로 외부 CL의 객체 보유. 톰캣 9+가 이 누수를 자동 detect/clean.
> 3. **JDBC DriverManager** — driver 등록 후 `deregisterDriver` 누락. JDK의 `DriverManager`가 driver를 잡고, driver는 자기 CL 잡음.
> 4. **Logger context** — Log4j2 / Logback의 LoggerContext가 자기를 로드한 CL을 잡음. shutdown hook 필요.
> 5. **Reflection cache** — `Field.setAccessible(true)` 등으로 만들어진 캐시.
> 
> 진단: heap dump → Eclipse MAT의 "Leak Suspects" → ClassLoader 추적.

### Q4. Compressed Class Space가 뭐고 왜 별도인가요?

**예상 답변**:
> Klass 포인터(객체 헤더의 4-byte 필드)를 32-bit로 압축하기 위한 별도 reserve 영역. 기본 1GB.
> 압축 메커니즘:
> - 실제 주소 = `narrow_klass_base + (compressed << narrow_klass_shift)`.
> - shift는 보통 3 (8바이트 정렬).
> 
> 왜 Heap의 Compressed Oops와 별도인가:
> - Compressed Oops는 Heap 내부 ref용. 32GB 제한.
> - Compressed Klass는 Metaspace의 Klass ref용. 별도 1GB.
> - 두 메커니즘 독립. Klass는 양이 적어서 1GB로 충분.

#### 🪝 꼬리 Q4-1: "Compressed Class Space가 가득 차면?"

**예상 답변**:
> `OutOfMemoryError: Compressed class space`.
> 해결:
> - `-XX:CompressedClassSpaceSize=2g` 로 키움.
> - 또는 `-XX:-UseCompressedClassPointers` 로 끄고 일반 8-byte Klass Ptr 사용 (객체당 4 byte 추가).
> - 진짜 원인이 누수면 그것부터 고침 — Class 수 10만 개를 적정으로 보고 그보다 크면 누수 의심.

### Q5. `Class<String>` 객체와 `InstanceKlass for String`은 같은 건가요?

**예상 답변**:
> 아니, 서로 다른 두 개의 객체.
> - `Class<String>` mirror — **Heap**에 있는 일반 Java 객체. reflection이 만지는 그것. `String.class`로 접근.
> - `InstanceKlass for String` — **Metaspace**에 있는 HotSpot C++ 객체. vtable, itable, constant pool, method 코드 등 실제 메타데이터.
> 
> 양방향 포인터로 연결:
> - mirror에 `_klass` 필드 → Metaspace의 InstanceKlass.
> - InstanceKlass에 `_java_mirror` 필드 → Heap의 mirror.
> 
> 객체 헤더의 Klass Pointer는 mirror가 아니라 **InstanceKlass**를 가리킴.

#### 🪝 꼬리 Q5-1: "그럼 reflection이 `Method.invoke`할 때 실제 호출 디스패치는 누가 하나요?"

**예상 답변**:
> 1. `Method.invoke` → JDK 내부에서 mirror의 `_klass` 필드를 통해 InstanceKlass 접근.
> 2. InstanceKlass의 `_methods` 배열에서 해당 Method 메타데이터 lookup.
> 3. 인터프리터 또는 JIT 컴파일된 native code의 entry point로 jump.
> 
> reflection invoke는 처음 N번은 native 호출(약 비싸짐) → 임계 이상이면 JDK가 동적으로 bytecode 어댑터 생성 (`MethodAccessorImpl`)해서 직접 invokevirtual로 호출하게 만듦. Inflation이라 부름.

### Q6. (Killer) Spring Boot 앱이 hot reload할 때마다 RSS가 100MB씩 늘어납니다. 어디서 누가 누수되고 있는지 어떻게 찾으시겠어요?

**예상 답변**:
> 단계적 진단:
> 
> 1. **현상 확인**:
>    ```bash
>    jcmd <pid> VM.metaspace summary
>    # loaders 수가 reload 후 줄어드는지 안 줄어드는지 확인
>    # 안 줄어들면 → ClassLoader 누수 확정
>    ```
> 
> 2. **CL 인스턴스 확인**:
>    ```bash
>    jcmd <pid> VM.classloader_stats | grep -i webapp
>    # 같은 이름의 CL이 reload 횟수만큼 누적되어 있는지
>    ```
> 
> 3. **클래스 unload 로그**:
>    ```bash
>    -Xlog:class+unload:file=/tmp/unload.log
>    # reload 후 unload가 거의 안 일어나면 → 누수
>    ```
> 
> 4. **Heap dump + MAT**:
>    ```bash
>    jcmd <pid> GC.heap_dump /tmp/heap.hprof
>    # MAT에서 "Histogram" → ClassLoader로 필터
>    # → 인스턴스 수가 reload 횟수와 같으면 누수
>    # → "GC Roots" 추적해 누가 잡고 있는지 식별
>    ```
> 
> 5. **흔한 범인 5종 점검**:
>    - Spring DevTools의 RestartClassLoader는 자체적으로 reload 메커니즘 — 정상이면 unload돼야 함.
>    - 정적 캐시: `static Map`에 외부 CL의 클래스 보관?
>    - JDBC: HikariCP 등이 shutdown 시 driver deregister 호출하는가?
>    - Log4j2: `LogManager.shutdown()` 호출되는가?
>    - ThreadLocal: 톰캣 스레드가 영구라면 외부 CL의 객체 잡지 않는가?
> 
> 6. **조치**:
>    - 임시: `-XX:MaxMetaspaceSize=512m` 로 한계 설정, 재시작 주기 짧게.
>    - 영구: 식별된 leak suspect 코드 수정.

#### 🪝 꼬리 Q6-1: "Heap dump 분석 없이 빠르게 leak suspect를 좁히는 방법은?"

**예상 답변**:
> JFR을 짧은 시간 켜고:
> ```bash
> jcmd <pid> JFR.start name=ml duration=300s settings=profile filename=ml.jfr
> # 300초 동안 hot reload 한 번 실행
> jcmd <pid> JFR.stop name=ml
> jfr summary ml.jfr | grep -i "ClassLoad\|ClassUnload"
> ```
> 
> 이벤트 분석:
> - `jdk.ClassLoad` 이벤트의 ClassLoader name이 anomaly?
> - `jdk.ClassUnload`가 거의 없음 → unload 메커니즘 자체 실패.
> 
> 또한 `jdk.ClassLoaderStatistics` 이벤트로 시간순 CLD 추세 확인. 줄어들어야 할 시점에 안 줄어들면 그 시점의 다른 이벤트(thread, lock 등)에서 누가 CL을 잡았는지 단서.

### Q7. JEP 387 Elastic Metaspace가 뭐를 해결했나요?

**예상 답변**:
> JDK 15에서 도입.
> 문제: 옛 Metaspace는 한 번 OS에서 받은 chunk를 거의 OS에 반환 안 함 → 단명 CL이 많은 환경에서 chunk가 free list에 쌓이고 RSS는 그대로.
> 
> 해결:
> 1. **Buddy allocator** — chunk 크기 등급을 power-of-2로 통일해 fragmentation 감소.
> 2. **Uncommit 적극화** — 사용 안 하는 chunk의 페이지를 `madvise(MADV_DONTNEED)` 등으로 OS에 반환 (commit만 해제, reserve는 유지).
> 3. 결과: 동일 워크로드에서 footprint 10~20% 감소, 메모리 압박 ↓.
> 
> 운영자에게 의미: JDK 15+에서 Metaspace 메모리 증가가 옛 버전보다 완만 — 누수 진단이 더 정확.

---

## 🔗 다음 단계

- → [03. Stack & PC & Native Method Stack](./03-stack-pc-native.md): Per-Thread 영역의 정확한 구조
- → [04. Code Cache](./04-code-cache.md): JIT 결과 native code 저장소
- → [05. Direct Memory](./05-direct-memory.md): Off-heap NIO
- ← [01. Heap & TLAB](./01-heap-and-tlab.md): Heap의 세대 구조와 TLAB
- ← [01 class-lifecycle / 02 ClassLoader hierarchy](../01-class-lifecycle/02-classloader-hierarchy.md): ClassLoader 위임 모델 (CLD의 상위 개념)

## 📚 참고

- **JEP 122 (Remove PermGen)**: https://openjdk.org/jeps/122
- **JEP 387 (Elastic Metaspace)**: https://openjdk.org/jeps/387
- **HotSpot Glossary - Metaspace**: https://openjdk.org/groups/hotspot/docs/HotSpotGlossary.html
- **HotSpot `metaspace.cpp`**: https://github.com/openjdk/jdk/blob/master/src/hotspot/share/memory/metaspace.cpp
- **HotSpot `classLoaderData.cpp`**: https://github.com/openjdk/jdk/blob/master/src/hotspot/share/classfile/classLoaderData.cpp
- **JVMS §2.5.4 (Method Area)**: https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-2.html#jvms-2.5.4
- **Aleksey Shipilëv — Metaspace Tracking**: https://shipilev.net/blog/2014/oom-pseudo-jvm/ (and follow-up posts)
- **Tomcat ClassLoader Memory Leak Prevention**: https://wiki.apache.org/tomcat/MemoryLeakProtection
- **Eclipse MAT — ClassLoader Explorer**: https://www.eclipse.org/mat/documentation/
