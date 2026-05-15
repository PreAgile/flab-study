# 02-04. Code Cache — JIT가 만든 native code의 보관소

> JVM은 bytecode를 인터프리터로 실행하다가, 자주 호출되는 hot method를 JIT으로 **native machine code**로 컴파일한다.
> 그 컴파일 결과는 어디에 저장되나? Heap이 아니다. Metaspace도 아니다. **Code Cache** — JVM이 OS로부터 별도 reserve한 영역.
> 기본 크기 240MB. 가득 차면? **"CodeCache is full. Compiler has been disabled."** — 그 순간부터 JVM은 평생 인터프리터로 돌아간다. 성능 5~10배 저하.
> 시니어가 이 메시지를 한 번이라도 본 적이 있다면, 그날 production을 살린 사람이다.

---

## 📍 학습 목표

이 챕터를 마치면 다음을 모두 답할 수 있다.

1. JIT 컴파일된 native code가 Heap이 아닌 Code Cache에 저장되는 이유를 안다 — executable 메모리, GC 정책, dynamic linking.
2. **Segmented Code Cache** (JDK 9+) 의 3개 segment (Non-method / Profiled / Non-profiled) 각각의 역할을 안다.
3. 기본 크기(`ReservedCodeCacheSize = 240MB`)와 segment별 분배를 안다.
4. Code Cache가 가득 찼을 때 발생하는 일 — JIT 비활성, 인터프리터 fallback, **UseCodeCacheFlushing**의 동작.
5. Tiered Compilation이 Code Cache 사용량을 늘리는 이유와 트레이드오프.
6. `Compiler.codecache` jcmd 출력의 모든 필드를 해석할 수 있다.
7. Spring Boot 거대 앱, 동적 클래스 생성 많은 앱(Lambda, Hibernate proxy)에서 Code Cache 압박이 발생하는 패턴을 안다.
8. **Inline Cache**가 무엇이고 Code Cache의 한 부분으로 어떻게 저장되는지 안다.
9. **Deoptimization**이 일어나면 Code Cache의 native code가 어떻게 폐기되는지 안다.
10. `-XX:+PrintCodeCache`, `-XX:+PrintCompilation` 옵션으로 컴파일 활동을 추적할 수 있다.

---

## 🎨 1단계: 백지 그리기 가이드

### Step 1: JVM Process 전체에서 Code Cache의 위치

- 큰 사각형 안에 Heap / Metaspace / Stacks 박스 + **Code Cache** 박스 (별도).
- Code Cache 옆에 라벨: "executable 메모리, 기본 240MB reserve, native code 저장".

### Step 2: Code Cache를 세 영역으로 분할 (JDK 9+)

```
Code Cache (총 240MB, 기본)
━━━━━━━━━━━━━━━━━━━━━━━━━━━

┌────────────────────────────────┐
│ ① Non-method (~5.7MB 기본)      │  Adapter, Runtime stub, Interpreter 등
├────────────────────────────────┤
│ ② Profiled (~117MB)             │  C1 컴파일 결과 (profiling 포함)
├────────────────────────────────┤
│ ③ Non-profiled (~117MB)         │  C2 컴파일 결과 (fully optimized)
└────────────────────────────────┘
```

### Step 3: 한 메서드의 컴파일 흐름 화살표

```
Bytecode → 인터프리터 실행 (interpreter stub: Non-method)
            │
            ▼ 호출 횟수 ~ 임계
        C1 컴파일 → Profiled segment에 저장
            │
            ▼ 더 자주 호출 + profile 데이터 수집
        C2 컴파일 → Non-profiled segment에 저장
            │
            ▼ 가정 깨짐 (CHA 위반, class redefine 등)
        Deoptimize → C2 코드 폐기, 인터프리터 또는 C1로 복귀
```

### Step 4: Inline Cache 줌인

```
C2가 컴파일한 메서드 안의 invokevirtual 호출 위치
        │
        ▼
Inline Cache (IC) — 한 줄 patch 가능한 영역
        ├─ first call: monomorphic (단일 구현)
        │      ┌─────────────────────┐
        │      │ check klass == Foo  │
        │      │ jump to Foo.bar()   │  ← 직접 점프 (가장 빠름)
        │      └─────────────────────┘
        ├─ 다른 클래스 만남: bimorphic / polymorphic
        │      ┌─────────────────────┐
        │      │ check + branch table│
        │      └─────────────────────┘
        └─ 너무 많은 타입: megamorphic
               ┌─────────────────────┐
               │ vtable lookup       │  ← 일반 dispatch (느림)
               └─────────────────────┘
```

### 정답 그림 (ASCII)

```
JVM Process
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[Shared/Native 영역]                  [Code Cache (별도 reserve)]
                                      ┌──────────────────────────┐
[Java Heap]    [Metaspace]            │ ① Non-method (5~10MB)     │
   ↑               ↑                  │   - Adapter stub         │
   GC 대상         CLD chunk           │   - Interpreter loop     │
                                      │   - Runtime stub         │
[Threads]      [Direct Memory]        │   - Compiler 자체         │
                                      ├──────────────────────────┤
                                      │ ② Profiled (~117MB)       │
                                      │   - C1 컴파일된 메서드     │
                                      │   - profiling instrumented│
                                      │   - 짧게 살다 C2로 승격    │
                                      ├──────────────────────────┤
                                      │ ③ Non-profiled (~117MB)   │
                                      │   - C2 컴파일된 메서드     │
                                      │   - long-lived            │
                                      │   - 가장 빠른 native code  │
                                      └──────────────────────────┘
                                      총 reserve: 기본 240MB
                                      옵션: -XX:ReservedCodeCacheSize
```

---

## 🧠 2단계: 직관

### 핵심 비유

> **요리책 비유**:
> - **Bytecode** = 평범한 레시피책 (모든 셰프가 같은 방식으로 읽음, 천천히).
> - **인터프리터** = 레시피를 한 줄씩 읽으며 요리 (느림).
> - **JIT 컴파일** = 자주 만드는 요리를 **개인 메모지(빠른 단축 노트)** 로 옮겨 적기.
> - **Code Cache** = 그 단축 노트들을 보관하는 책상 옆 서랍. 한정된 공간.
> - **Segmented**: 서랍이 3칸 — 임시 메모(non-method), 약식 메모(C1/Profiled), 완성판 메모(C2/Non-profiled).
> - **가득 차면**: 새 단축 노트 못 만듦 → 그 후부터 다 본책에서 한 줄씩 읽음(인터프리터로 회귀) → 매우 느려짐.

### 정확한 정의 (비유와 분리)

| 용어 | 정의 |
|---|---|
| **Code Cache** | JIT 컴파일러가 생성한 native machine code와 JVM 내부 runtime stub들을 저장하는 영역. `mmap`으로 OS에서 reserve. **executable 플래그 필요** — RWX 또는 W^X 메모리. |
| **Segmented Code Cache** (JDK 9+, JEP 197) | Code Cache를 3개 segment로 물리 분할. 각 segment가 독립적으로 관리됨. |
| **Non-method segment** | JIT가 아닌 JVM 자체의 native stub. Interpreter loop, Adapter (calling convention 변환), Runtime stub (safepoint poll, exception handler 등), Compiler 자체의 코드. 기본 ~5.7MB. |
| **Profiled segment** | C1 컴파일러가 만든 native code. **profiling instrumentation 포함** (호출 횟수, branch taken/not taken 등 측정). 보통 짧게 살고 C2로 승격되면 free. 기본 ~117MB. |
| **Non-profiled segment** | C2 컴파일러가 만든 fully optimized native code. profiling 없음. long-lived. 기본 ~117MB. |
| **NMethod** (Native Method) | 한 메서드를 컴파일한 결과를 표현하는 HotSpot C++ 객체. 메타데이터 + native instruction + dependency 정보. Code Cache의 할당 단위. |
| **Inline Cache (IC)** | 메서드 호출 사이트에 캐시된 dispatch 정보. monomorphic/bimorphic/polymorphic/megamorphic으로 발전. |
| **Deoptimization** | C2 컴파일 시 가정(예: "이 메서드는 monomorphic")이 깨졌을 때 native code를 폐기하고 인터프리터로 복귀하는 메커니즘. |
| **Code Sweeper** | Code Cache가 압박받을 때 cold nmethod를 회수하는 GC 같은 메커니즘. `-XX:+UseCodeCacheFlushing` (기본 on). |

### 왜 Code Cache가 별도 영역인가 — 3가지 본질적 이유

```
[Heap에 두면 (가상)]                        [별도 Code Cache (실제)]
━━━━━━━━━━━━━━━━━━                          ━━━━━━━━━━━━━━━━━━━━

1. Executable 플래그                          1. mmap PROT_EXEC 별도 영역
   Heap에 native code 두려면 RWX 필요          executable 메모리만 별도 (보안)
   → 보안 위협 (Heap 전체 실행 가능)             → Heap은 RW만 (XOR W^X)

2. GC 정책 충돌                               2. GC와 분리
   Heap의 일반 객체와 native code는            Code Sweeper가 nmethod 단위 회수
   수명/회수 정책이 다름                         (cold nmethod evict)
   - 일반 객체: 빠르게 죽음 (Young)
   - native code: 일단 만들면 오래 살아감

3. 메모리 layout 요구                          3. 연속된 executable 영역
   JIT는 jump 명령에 32-bit offset 사용         시작 시 한 번에 reserve →
   → 모든 native code가 4GB 안에 모여야 함       모든 점프가 32-bit relative로 가능
                                                (32-bit relative jump optimization)
```

→ **실행 가능한 메모리, GC와 분리된 회수 메커니즘, 점프 거리 최적화** 세 가지가 Code Cache가 별도여야 하는 이유.

### 왜 Segmented인가 — JDK 8 vs JDK 9+

**JDK 8 이전 (단일 Code Cache)**:
- C1, C2, runtime stub 모두 한 영역.
- C1으로 컴파일된 short-lived 코드와 C2의 long-lived 코드가 섞임.
- 결과: **fragmentation** — 군데군데 dead nmethod가 흩어져 새 컴파일 위한 연속 공간 못 찾음.
- Sweeper 비용 높음 (전체 cache 스캔).

**JDK 9+ (Segmented, JEP 197)**:
- Non-method, Profiled, Non-profiled 분리.
- Profiled (단명) 빈도 변화에 Non-profiled (장명) 영향 없음.
- 각 segment 독립 sweep → 빠름.
- Hot path의 instruction cache locality 향상 (long-lived code 모임).

### Tiered Compilation과 Code Cache의 관계

**Tiered Compilation** (JDK 7+ 기본 on):
```
Tier 0: 인터프리터 (Non-method의 Interpreter loop)
   ↓ (호출 횟수)
Tier 1/2/3: C1 컴파일 (Profiled segment에 저장)
   ↓ (더 호출 + profile 충분)
Tier 4: C2 컴파일 (Non-profiled segment에 저장)
```

→ Tiered Compilation은 **C1 + C2 모두** 사용 → Code Cache 사용량이 C2-only보다 큼.

**`-XX:-TieredCompilation`** 옵션 (Tiered 끄기):
- C2만 직접 사용.
- Code Cache 사용량 ↓ (Profiled segment 거의 안 씀).
- **그러나 warmup 시간 ↑** — C2가 무거워서 시작 시 응답 느림.
- Trade-off: 메모리 절약 vs warmup 속도.

---

## 🔬 3단계: 구조

### Code Cache의 메모리 레이아웃 (JDK 9+)

```
JVM 시작 시 OS에서 ReservedCodeCacheSize (기본 240MB) reserve
                            │
                            ▼
       3개 segment로 분할 (자동 또는 사용자 지정)
                            │
        ┌───────────────────┼───────────────────┐
        ▼                   ▼                   ▼
   Non-method           Profiled           Non-profiled
   (NonNMethodCodeHeapSize)  (ProfiledCodeHeapSize) (NonProfiledCodeHeapSize)
   기본: 5.7MB           기본: ~117MB        기본: ~117MB

각 segment 안에서:
  - nmethod (한 메서드의 컴파일 결과)들을 bump-the-pointer로 할당
  - sweep 시 dead nmethod들을 free list로
  - free list 재사용 또는 사용 안 되면 OS uncommit
```

### NMethod의 구조

위치: `src/hotspot/share/code/nmethod.hpp`

```cpp
class nmethod : public CompiledMethod {
private:
  // 1. 헤더
  int            _entry_bci;                // entry bytecode index
  Method*        _method;                   // 어느 Java 메서드의 컴파일인가
  int            _compile_id;               // 고유 ID
  CompileLevel   _comp_level;               // C1=3 또는 C2=4

  // 2. native instruction 영역 (실제 machine code)
  address        _entry_point;              // 일반 호출 진입점
  address        _verified_entry_point;     // type-check된 진입점

  // 3. 메타데이터 (GC, deopt 위해)
  PcDesc*        _scopes_pcs;               // pc → bytecode 매핑
  Dependencies*  _dependencies;             // CHA 의존성 (deopt 트리거)
  OopMap*        _oop_maps;                 // 각 pc에서 register/stack의 oop 위치

  // 4. 호출 사이트 정보
  RelocInfo*     _relocations;              // patch 가능 위치

  // 5. inline cache slots
  ICache*        _ic_slots;
};
```

→ NMethod 하나가 **native instruction + 풍부한 메타데이터**의 묶음. 메타데이터가 instruction 자체보다 크기도 함 (GC/deopt가 안전하려면).

### 메서드 컴파일 전체 흐름

```
1. 메서드 호출 횟수가 임계 도달 (C1: ~1500, C2: ~10000)
        │
        ▼
2. Compile Broker가 컴파일 task를 큐에 등록
   (`-XX:CICompilerCount=N`이 컴파일 스레드 수)
        │
        ▼
3. C1 또는 C2 compiler thread가 task pickup
        │
        ▼
4. Bytecode → IR (C1의 HIR/LIR 또는 C2의 Sea-of-Nodes)
        │
        ▼
5. 최적화 패스 (inlining, escape analysis, loop unrolling, ...)
        │
        ▼
6. Register allocation
        │
        ▼
7. Code emission — native instruction 생성
        │
        ▼
8. NMethod 객체 생성 + Code Cache에 nmethod 할당
   (Profiled segment 또는 Non-profiled segment)
        │
        ▼
9. Method의 `_code` 필드를 새 nmethod로 패치 (atomic)
   → 다음 호출부터 native code 실행
```

### Inline Cache의 진화

```
첫 호출 (monomorphic, 가장 빠름):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

call site: invokevirtual a.foo()
   │
   ▼
[IC slot]
   if (a.klass == FooImpl) {
       jump FooImpl.foo's nmethod entry
   } else {
       call IC miss handler  ← 새 클래스 발견 시 여기로
   }

bimorphic (다른 클래스 1개 더 발견):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[IC slot]
   if (a.klass == FooImpl) jump FooImpl.foo's nmethod;
   if (a.klass == BarImpl) jump BarImpl.foo's nmethod;
   else call IC miss handler

megamorphic (다양한 타입, ~3 이상):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[IC slot]
   vtable lookup (일반 디스패치)
```

→ **IC가 monomorphic일 때 거의 직접 호출 수준 성능**. 다형성이 늘면 점진적으로 느려짐. C2의 inlining도 IC가 monomorphic이어야 가능 (다음 챕터에서 더 깊게).

### Deoptimization — C2 코드의 폐기

**언제 일어나나**:
1. **CHA(Class Hierarchy Analysis) 가정 위반** — C2가 "이 메서드는 monomorphic"이라고 가정해 inline했는데, 새 subclass가 로드되어 다형성 등장.
2. **Speculative type check 실패** — Profile 기반 type guess가 틀림.
3. **Class redefinition** — JVMTI로 클래스가 다시 정의됨.
4. **Uncommon branch 도달** — C2가 "거의 안 일어남"으로 표시한 분기에 도달.

**흐름**:
```
1. Deopt 트리거 발생 (예: 새 subclass 로드)
        │
        ▼
2. 영향받는 nmethod들 식별 (Dependencies 정보 통해)
        │
        ▼
3. 그 nmethod들을 "not_entrant"로 표시 (이후 호출 시 인터프리터로)
        │
        ▼
4. 이미 실행 중인 스레드는 다음 safepoint에서 deoptimize
   - native frame → interpreter frame으로 변환 (OSR의 역방향)
   - register/stack 값을 interpreter slot에 복원
   - 적절한 bytecode index부터 인터프리터로 재개
        │
        ▼
5. 그 nmethod는 Code Cache에서 sweep 대상
        │
        ▼
6. Code Sweeper가 다음 cycle에 free
```

### Code Cache full → JIT 비활성 시나리오

```
Code Cache 사용량이 100%에 근접
        │
        ▼
JVM 경고 로그: "CodeCache is full. Compiler has been disabled."
"Try increasing the code cache size using -XX:ReservedCodeCacheSize="
        │
        ▼
Compile Broker가 더 이상 compile task 받지 않음
        │
        ▼
이미 컴파일된 메서드는 그대로 실행 (Code Cache의 nmethod 살아있음)
        │
        ▼
새로 호출되는 메서드는 컴파일 안 됨 → 영원히 인터프리터
        │
        ▼
성능 5~10배 저하 (인터프리터는 JIT보다 그만큼 느림)
        │
        ▼
UseCodeCacheFlushing 활성 시: Sweeper가 cold nmethod 회수 시도
        │
        ▼
공간 확보되면 컴파일 재개. 안 되면 영구 인터프리터 모드.
```

### `-XX:+UseCodeCacheFlushing` 메커니즘

기본 on. 가득 차면:
1. 사용 빈도 낮은 nmethod (LRU 기반)를 골라 `not_entrant`로 표시.
2. 다음 호출 시 인터프리터로 fallback.
3. 더 이상 실행 중인 스레드 없음 확인 후 Code Sweeper가 free.
4. 공간 확보되면 새 컴파일 가능.

**단점**: 자주 호출되는 메서드가 evict됐다가 다시 호출되면 재컴파일 비용. Steady state에서 hot/cold가 분리 안 된 워크로드는 thrash.

---

## 🧬 4단계: 내부 구현 — HotSpot

### CodeCache 클래스

위치: `src/hotspot/share/code/codeCache.cpp`

```cpp
class CodeCache : public AllStatic {
private:
  static GrowableArray<CodeHeap*>* _heaps;  // segment 별 CodeHeap
  static int      _number_of_blobs;
  static int      _number_of_nmethods;
  static int      _commited_size;

public:
  static void  initialize();
  static CodeBlob* allocate(int size, CodeBlobType type, ...);
  static void  free(CodeBlob* cb);
  static void  flush();   // emergency sweep
  static void  print_summary(outputStream* st);
};
```

### 초기화 — Segment 분배

```cpp
// codeCache.cpp (요약)
void CodeCache::initialize_heaps() {
  size_t total_size = ReservedCodeCacheSize;          // 240MB 기본
  size_t non_nmethod = NonNMethodCodeHeapSize;        // 5.7MB
  size_t profiled    = ProfiledCodeHeapSize;          // 117MB
  size_t non_profiled = NonProfiledCodeHeapSize;      // 117MB

  // 합이 total과 안 맞으면 자동 조정
  if (non_nmethod + profiled + non_profiled != total_size) {
    adjust_sizes(...);
  }

  // 각 segment를 별도 mmap reserve
  _non_nmethod_heap   = new CodeHeap(non_nmethod, ...);
  _profiled_heap      = new CodeHeap(profiled, ...);
  _non_profiled_heap  = new CodeHeap(non_profiled, ...);

  // OS에 PROT_READ | PROT_WRITE | PROT_EXEC 요청
  reserve_with_protection(...);
}
```

### NMethod 할당

```cpp
// codeCache.cpp
CodeBlob* CodeCache::allocate(int size, CodeBlobType type, ...) {
  CodeHeap* heap = get_heap(type);  // segment 선택

  CodeBlob* cb = (CodeBlob*) heap->allocate(size);
  if (cb == NULL) {
    // segment full
    if (UseCodeCacheFlushing) {
      flush_codeheap(heap);          // cold nmethod 회수
      cb = (CodeBlob*) heap->allocate(size);
    }
    if (cb == NULL) {
      report_codemem_full(type);     // "CodeCache is full" 경고
      disable_compiler();             // ★ JIT 비활성
      return NULL;
    }
  }
  return cb;
}
```

### Compile Broker — 컴파일 task 관리

위치: `src/hotspot/share/compiler/compileBroker.cpp`

```cpp
// 호출 시 카운터가 임계 도달
void CompileBroker::compile_method(methodHandle method, int level, ...) {
  CompileTask* task = create_compile_task(method, level);

  // task를 우선순위 큐에 추가
  CompileQueue* queue = compile_queue(level);
  queue->add(task);

  // 대기 중인 compiler thread를 깨움
  queue->notify_one();
}

// Compiler thread의 main loop
void CompilerThread::thread_main() {
  while (!is_terminating()) {
    CompileTask* task = queue->get();    // task pickup
    if (task == NULL) continue;

    // 컴파일러 호출
    if (task->level() <= 3) {
      _c1->compile_method(task);
    } else {
      _c2->compile_method(task);
    }

    // 결과 NMethod를 method에 install
    install_nmethod(task->method(), nm);
  }
}
```

### Code Sweeper

위치: `src/hotspot/share/sweeper/sweeper.cpp` (JDK 17 이전), 이후 deprecated되고 다른 메커니즘으로 대체.

```cpp
// 주기적으로 또는 압박 시 실행
void NMethodSweeper::sweep() {
  while (nmethod_iter.has_next()) {
    nmethod* nm = nmethod_iter.next();
    if (nm->is_cold()) {
      // 사용 안 한 지 오래됨
      nm->make_not_entrant();   // 이후 호출 시 인터프리터로
    }
    if (nm->is_not_entrant() && nm->can_be_freed()) {
      CodeCache::free(nm);
    }
  }
}
```

### Inline Cache 패치

위치: `src/hotspot/share/code/compiledIC.cpp`

```cpp
void CompiledIC::set_to_monomorphic(CompiledICInfo& info) {
  // IC slot의 instruction을 patch
  // (예: x86_64에서 mov rax, klass_check_addr; jmp target_address)
  NativeMovConstReg* mov = ...;
  mov->set_data((intptr_t) info.klass());

  NativeJump* jmp = ...;
  jmp->set_jump_destination(info.entry());
}
```

→ patch는 **atomic word write**로 이뤄짐. 다른 스레드가 동시에 호출 중이어도 안전.

---

## 📜 5단계: 역사

| 연도 | 릴리스 | 변화 | 이유 |
|---|---|---|---|
| 1996 | JDK 1.0 | JIT 없음 (Sun JIT 별도 옵션) | 초기 |
| 1999 | HotSpot 1.0 | C1 (Client) JIT, 단일 Code Cache | 빠른 startup |
| 2000 | HotSpot 1.3 | C2 (Server) JIT 추가 | 처리량 |
| 2007 | JDK 6u20 | Tiered Compilation 실험 | C1 + C2 결합 |
| 2014 | JDK 8 | **Tiered Compilation 기본 on** | warmup + 최적화 양립 |
| 2017 | JDK 9 | **Segmented Code Cache (JEP 197)** | fragmentation 해결, sweep 효율 |
| 2018 | JDK 10 | AOT 도입 (`jaotc`) → 11에서 제거 | 실험 실패 |
| 2018 | JDK 9+ | Graal 실험 (별도 JIT 옵션) | 더 공격적 최적화 |
| 2020 | JDK 16 | Sweeper 개선 — concurrent sweeping | Sweeper의 STW 영향 ↓ |
| 2024+ | JDK 23+ | Project Leyden (AOT/CDS 통합) | startup 최적화 재시도 |

### Segmented Code Cache 도입의 동기 — JEP 197

JDK 8까지의 문제:
1. **Sweep 비효율**: 단일 cache 전체 스캔. C2의 long-lived nmethod와 C1의 short-lived nmethod가 섞여 사실상 모든 페이지 검사.
2. **Fragmentation**: short-lived가 가운데 군데군데 죽으면 큰 nmethod 할당 위한 연속 공간 부족.
3. **Cache locality 손상**: hot path와 cold path 코드가 섞여 instruction cache miss ↑.

JEP 197 해결:
- 3개 segment로 물리 분리 → 독립 sweep, segment 단위 evict 효율 ↑.
- Long-lived (C2) 영역은 거의 sweep 안 함 → 안정.
- Short-lived (C1) 영역만 자주 sweep.

### Tiered Compilation의 시대적 의미

JDK 8 이전 (`-server`/`-client` 분리):
- 서버: C2만, startup 느림, peak 빠름.
- 클라이언트: C1만, startup 빠름, peak 느림.

JDK 8+ (Tiered 기본):
- 한 JVM이 C1 + C2 모두 활용.
- 일찍 C1로 빠르게 컴파일 (warmup ↑), 나중에 hot method를 C2로 승격 (peak ↑).
- Trade-off: **Code Cache 2배 사용** (C1, C2 양쪽 결과 동시 존재).

이 변화가 JDK 9의 Segmented Code Cache 필요성을 만듦 — Tiered로 양쪽 코드 다 들고 있어야 하니 영역 분리가 합리적.

---

## ⚖️ 6단계: 트레이드오프

### `ReservedCodeCacheSize` 트레이드오프

| 작게 (~64MB) | 크게 (~512MB) |
|---|---|
| ✅ 메모리 footprint 작음 | ❌ footprint 큼 |
| ❌ "CodeCache is full" 위험 ↑ | ✅ 풍부한 공간 |
| ❌ Sweeper 자주 동작 | ✅ Sweeper 거의 안 함 |
| ❌ 거대 앱 (Spring Boot 등) 부적합 | ✅ 거대 앱 견딤 |
| ✅ 마이크로서비스 (소형) 적합 | △ 마이크로서비스에선 낭비 |

**경험칙**:
- 일반 웹 서버: 기본 240MB로 충분.
- Spring Boot 대형 앱 / 동적 클래스 많은 앱: 512MB.
- Lambda 폭주 + Hot reload 환경: 768MB ~ 1GB.

### Tiered Compilation 끄기 (`-XX:-TieredCompilation`)

| Tiered on (기본) | Tiered off (C2 only) |
|---|---|
| ✅ Warmup 빠름 (C1으로 일찍 컴파일) | ❌ Warmup 느림 (인터프리터 → C2 직접) |
| ❌ Code Cache 사용량 큼 (C1+C2 양쪽) | ✅ Code Cache 사용량 작음 |
| ✅ peak 성능 동일 | ✅ peak 성능 동일 |
| △ profile 데이터 수집 비용 | ✅ profile 비용 없음 |

**언제 끄나**:
- 메모리 매우 제한적 (컨테이너 limit ~512MB).
- Code Cache 압박 명백.
- Warmup이 중요하지 않은 batch / 데몬 워크로드.

### Code Cache Flushing 트레이드오프

| `+UseCodeCacheFlushing` (기본 on) | `-UseCodeCacheFlushing` |
|---|---|
| ✅ 가득 차도 계속 컴파일 가능 | ❌ 가득 차면 영원히 JIT 비활성 |
| ❌ Thrash 위험 (hot method가 evict됐다 재컴파일) | ✅ 안정적 (한번 컴파일된 거 영원) |
| ✅ 메모리 한정 환경 적합 | ✅ 메모리 충분 환경 적합 |

→ 기본 on이 거의 항상 맞음. 끄는 경우는 **컴파일 deterministic이 중요한 latency-critical 시스템**.

### `CICompilerCount` (컴파일 스레드 수)

| 작게 (1~2) | 크게 (8+) |
|---|---|
| ✅ 컴파일 백그라운드 비용 작음 | ❌ 컴파일러가 CPU 점유 |
| ❌ 컴파일 적체 (큐 길어짐) → warmup 느림 | ✅ 컴파일 빠름 |
| ✅ 코어 적은 환경 (1~2 vCPU 컨테이너) | ✅ 코어 많은 환경 |

기본값: `CICompilerCount = max(2, log2(cpu_count) + 1)`. 일반적으로 적정.

---

## 📊 7단계: 측정·진단

### `jcmd Compiler.codecache` — 현재 사용량

```bash
jcmd <pid> Compiler.codecache
```

출력 예:
```
CodeHeap 'non-profiled nmethods': size=120000Kb used=45032Kb max_used=46100Kb free=74968Kb
 bounds [0x00007fa1b8000000, 0x00007fa1bb000000, 0x00007fa1bf500000]
CodeHeap 'profiled nmethods': size=120000Kb used=8512Kb max_used=8612Kb free=111488Kb
 bounds [0x00007fa1bf500000, 0x00007fa1bfa00000, 0x00007fa1c6a00000]
CodeHeap 'non-nmethods': size=5760Kb used=2840Kb max_used=2841Kb free=2920Kb
 bounds [0x00007fa1c6a00000, 0x00007fa1c6e00000, 0x00007fa1c6fa0000]
 
 total_blobs=12345 nmethods=8765 adapters=987
 compilation: enabled
              stopped_count=0, restarted_count=0
```

**해석 포인트**:
- `enabled` — JIT 정상.
- `stopped_count > 0` — Code Cache full로 한 번이라도 멈춤 → **운영 사고 신호**.
- 각 segment의 `used / size` 비율 — 80% 넘으면 압박.

### `-XX:+PrintCompilation` — 컴파일 활동 실시간 로그

```bash
java -XX:+PrintCompilation -jar app.jar
```

출력:
```
     38    1   n 0       java.lang.Object::<init> (1 bytes)
    140    2     3       java.lang.String::hashCode (49 bytes)
    142    3 %   4       MyApp::process @ 12 (123 bytes)
    150    4       4       MyApp::process (123 bytes)
   ...
```

필드:
1. 시작 후 시간 (ms)
2. compile ID
3. 플래그: `n`=native, `s`=synchronized, `!`=exception handler, `%`=OSR
4. tier: 0=interpreter, 1~3=C1, 4=C2
5. 메서드 시그니처

### `-XX:+PrintInlining` — Inlining 결정 추적

```bash
java -XX:+UnlockDiagnosticVMOptions -XX:+PrintInlining -jar app.jar
```

출력:
```
                            @ 5   java.lang.String::length (5 bytes)   inline (hot)
                            @ 12  java.lang.Integer::valueOf (32 bytes)   inline (hot)
                            @ 25  MyClass::expensive (200 bytes)   too big
```

→ JIT이 어느 호출을 inline하고 어느 호출을 안 했는지. "too big", "callee is too large" 같은 메시지가 inlining 막힘 신호.

### JFR Code Cache 이벤트

```bash
jcmd <pid> JFR.start name=cc duration=300s settings=profile filename=cc.jfr
jfr summary cc.jfr | grep -iE 'CodeCache|Compilation|Deoptimization'
```

**핵심 이벤트**:
- `jdk.CodeCacheStatistics` — 주기적 사용량.
- `jdk.CodeCacheFull` — 가득 참 발생 (이게 보이면 즉시 대응).
- `jdk.Compilation` — 컴파일 발생.
- `jdk.CompilerInlining` — inlining 결정.
- `jdk.Deoptimization` — deopt 발생.
- `jdk.CodeSweeperStatistics` — sweep 통계.

### Code Cache 시각화 (JITWatch)

[JITWatch](https://github.com/AdoptOpenJDK/jitwatch) — `-XX:+UnlockDiagnosticVMOptions -XX:+TraceClassLoading -XX:+LogCompilation` 로그를 시각화.
- 어느 메서드가 C1/C2로 컴파일됐는지.
- Inlining 트리.
- Deopt 발생 위치.

### 운영 시나리오 진단 매트릭스

| 증상 | 진단 명령 | 가능 원인 |
|---|---|---|
| "CodeCache is full" 경고 | `jcmd Compiler.codecache` | ReservedCodeCacheSize 부족 |
| 시간 지나면 응답 느려짐 | JFR `jdk.CodeCacheFull` 이벤트 | JIT 비활성 |
| 컴파일 멈춤 (`stopped_count > 0`) | `Compiler.codecache` | Code Cache full |
| Hot reload 후 점진적 느려짐 | `-XX:+PrintCompilation` + `jcmd Compiler.codecache` | 옛 nmethod 누적 |
| Spring Boot 거대 앱 OOM 아닌데 느림 | NMT의 Code 영역 | Code Cache 부족 |
| Deopt 빈발 | JFR `jdk.Deoptimization` | CHA 가정 위반, polymorphism ↑ |

### 시나리오 1: Spring Boot 거대 앱 — Code Cache 부족

```
증상:
- 시작 후 30분 이후 P99 latency 점진적 ↑
- 로그: "CodeCache is full. Compiler has been disabled."

진단:
$ jcmd <pid> Compiler.codecache | grep -A 1 compilation
compilation: disabled (not enough memory)
stopped_count=1

해결:
-XX:ReservedCodeCacheSize=512m   # 240MB → 512MB
-XX:InitialCodeCacheSize=128m    # 시작 시 commit 양
```

### 시나리오 2: Lambda 폭주 + 동적 클래스로 인한 Code Cache 압박

```
증상:
- 시간이 지나면 컴파일 횟수가 비정상적으로 많음
- jcmd VM.classloader_stats에 hidden class 수천 개

원인:
- 매 lambda 호출 사이트마다 hidden class 1개 생성
- 각 hidden class의 method가 자체 nmethod 차지
- 코드 패턴: Stream API 남용 + reflection 기반 framework

조치:
1. Lambda 사이트 수 audit (코드 검토)
2. ReservedCodeCacheSize 증가
3. -XX:+UseCodeCacheFlushing 확인 (기본 on)
```

### 시나리오 3: Deopt 폭주 — Megamorphic call site

```
증상:
- JFR jdk.Deoptimization 이벤트가 분당 수백 건
- P99 latency 튐

원인:
- 한 호출 사이트가 너무 많은 구현체를 만남
- C2가 monomorphic 가정으로 inline했다가 깨짐 → deopt

조치:
1. 코드에서 polymorphic call site 식별 (Strategy 패턴 등)
2. 일부 경우는 sealed class로 구현체 제한
3. -XX:+PrintInlining으로 inlining 실패 확인
```

---

## ⚔️ 8단계: 꼬리질문 트리

### Q1. JIT 컴파일된 native code는 어디에 저장되나요?

**예상 답변**:
> Code Cache. Heap이 아니고 Metaspace도 아닌 별도 영역.
> JVM이 OS로부터 `mmap`으로 reserve. 기본 240MB (`-XX:ReservedCodeCacheSize`).
> Executable 플래그 필요 — Heap과 분리되어야 하는 보안적 이유.
> JDK 9+에서는 3개 segment(Non-method / Profiled / Non-profiled)로 분할.

#### 🪝 Q1-1: 왜 Heap에 두면 안 되나요?

> 3가지 본질적 이유:
> 1. **Executable 메모리**: native code는 executable이어야 함 — Heap이 executable이면 보안 위협 (W^X 위반).
> 2. **GC 정책 분리**: 일반 객체는 Young/Old gen으로 짧게 죽고 길게 사는 모델인데 native code는 다른 수명 패턴. Code Sweeper로 별도 관리.
> 3. **32-bit relative jump**: JIT이 점프 명령에 32-bit offset 사용 → 모든 native code가 4GB 범위 안에 모여야 함. 별도 reserve로 보장.

### Q2. Segmented Code Cache의 3개 segment는 무엇이고 각각 무엇을 저장하나요?

**예상 답변**:
> 1. **Non-method**: JIT 결과가 아닌 JVM 자체의 native stub. Interpreter loop, Adapter, Runtime stub, Compiler 자체. 기본 ~5.7MB.
> 2. **Profiled**: C1 컴파일 결과 + profiling instrumentation. 보통 short-lived (C2로 승격되면 free). 기본 ~117MB.
> 3. **Non-profiled**: C2 컴파일 결과, fully optimized. Long-lived. 기본 ~117MB.
> 
> 도입: JDK 9 JEP 197. 옛 단일 cache의 fragmentation/sweep 비효율 해결.

#### 🪝 Q2-1: 왜 C1과 C2 결과를 분리해서 저장하나요?

> 수명/특성이 다르기 때문:
> - C1: 빠르게 만들어졌다 곧 C2로 승격 → short-lived.
> - C2: 한 번 만들어지면 거의 영구 → long-lived.
> 둘이 섞이면:
> - Sweep 시 long-lived 영역도 매번 스캔 → 비용 ↑.
> - Fragmentation — short-lived가 죽은 자리에 long-lived가 들어가기 어려움.
> 분리하면 short-lived만 자주 sweep, long-lived는 거의 건드리지 않음 → 효율.

### Q3. "CodeCache is full" 경고가 나오면 무슨 일이 일어나나요?

**예상 답변**:
> 1. JVM이 더 이상 새 컴파일을 진행하지 않음. Compile Broker가 task 받지 않음.
> 2. 이미 컴파일된 메서드는 그대로 native code로 실행 (살아있음).
> 3. **새로 호출되는 메서드는 영원히 인터프리터** — 성능 5~10배 저하.
> 4. `-XX:+UseCodeCacheFlushing` 기본 on이면 Sweeper가 cold nmethod 회수 시도 → 공간 확보되면 컴파일 재개.
> 5. flushing 실패하면 영구 인터프리터 모드 → 재시작 필요.
> 
> 진단: `jcmd Compiler.codecache` 의 `stopped_count`. 1 이상이면 한 번이라도 멈춤.

#### 🪝 Q3-1: 그럼 ReservedCodeCacheSize를 무한정 크게 잡으면 되지 않나요?

> 큰 trade-off 없이는 안 됨:
> 1. JVM 시작 시 reserve 양 ↑ → 가상 메모리 사용 ↑ (container limit 압박).
> 2. 실제 commit은 사용량 따라 점진적이지만, container 환경에선 reserve도 limit에 포함되는 경우 있음.
> 3. 32-bit relative jump를 위한 연속 공간이 너무 크면 OS가 적절한 위치 못 찾을 가능성.
> 
> 일반적으로 512MB ~ 1GB가 거대 앱의 sweet spot. 그 이상은 진짜 필요한 경우만.

### Q4. Tiered Compilation을 끄면 어떤 효과가 있나요?

**예상 답변**:
> `-XX:-TieredCompilation` 또는 `-XX:TieredStopAtLevel=N`:
> 
> 효과:
> - **Code Cache 사용량 ↓**: C1 결과(Profiled segment)를 거의 안 만듦. Non-profiled만 사용.
> - **Warmup 느림**: 인터프리터 → 바로 C2 직접 컴파일. C2가 무거워서 시작 응답 느림.
> - **Peak 성능 동일**: 최종적으로 같은 C2 결과.
> - **Profile 비용 없음**: instrumented C1 코드 안 실행.
> 
> 언제 적절한가:
> - 메모리 제한 컨테이너 (~512MB limit).
> - Code Cache 압박 명백.
> - Batch / 데몬 워크로드 (warmup 무시).

### Q5. Deoptimization이 무엇이고 언제 발생하나요?

**예상 답변**:
> C2가 컴파일 시 한 가정이 깨졌을 때 native code를 폐기하고 인터프리터로 복귀하는 메커니즘.
> 
> 트리거:
> 1. **CHA 위반**: "이 메서드는 monomorphic"이라고 가정해 inline했는데 새 subclass 로드 → 다형성 등장.
> 2. **Speculative type check 실패**: profile 기반 type guess 틀림.
> 3. **Class redefinition**: JVMTI로 클래스 재정의.
> 4. **Uncommon branch 도달**: C2가 "거의 안 일어남"으로 표시한 분기.
> 
> 흐름:
> 1. 영향받는 nmethod → not_entrant 표시.
> 2. 실행 중 스레드는 다음 safepoint에서 native frame → interpreter frame 변환.
> 3. Code Sweeper가 그 nmethod 회수.

#### 🪝 Q5-1: Deopt가 빈발하면 어떻게 진단하나요?

> JFR `jdk.Deoptimization` 이벤트 — 어느 메서드에서, 어떤 reason으로 deopt했는지.
> reason 예시:
> - `unstable_if`: speculative branch가 자주 다른 쪽 감.
> - `class_check`: monomorphic 가정 깨짐.
> - `predicate`: hoisted check 실패.
> 
> 해결:
> - polymorphic call site 식별 (Strategy 패턴 등).
> - sealed class로 구현체 제한 → CHA가 안정.
> - JIT 친화적 코드 패턴 (가능한 monomorphic, hot path 단순).

### Q6. Inline Cache가 무엇이고 어떻게 진화하나요?

**예상 답변**:
> 메서드 호출 사이트에 캐시된 dispatch 정보. 호출이 어떻게 분기되어야 하는지 직접 patch된 instruction.
> 
> 4단계 진화:
> 1. **Monomorphic** (단일 구현): klass check 1번 + 직접 점프. 가장 빠름.
> 2. **Bimorphic** (구현 2개): klass check 2번 + 분기.
> 3. **Polymorphic** (구현 ~3개): branch table.
> 4. **Megamorphic** (구현 많음): vtable lookup으로 fallback. 가장 느림.
> 
> C2의 inlining은 monomorphic IC에 의존 — IC가 monomorphic이어야 callee를 caller에 inline 가능.

### Q7. (Killer) Spring Boot 거대 앱이 시작 30분 후 응답이 느려집니다. 어떻게 진단하시겠어요?

**예상 답변**:
> 단계적 진단:
> 
> 1. **Code Cache 의심**:
>    ```
>    jcmd <pid> Compiler.codecache | grep -A 1 compilation
>    ```
>    `compilation: disabled` 또는 `stopped_count > 0` 이면 Code Cache full 확정.
> 
> 2. **사용량 추세**:
>    ```
>    JFR.start name=cc duration=600s settings=profile
>    # 또는 jcmd <pid> Compiler.codecache 를 5분 간격으로 비교
>    ```
>    각 segment의 `used/size` 비율 추세.
> 
> 3. **원인 추정**:
>    - Spring AOP/Hibernate proxy/Mockito 등 동적 클래스 생성 많음?
>    - Lambda 폭주? (`-Xlog:class+load`에 hidden class 다수)
>    - Hot reload 환경? (ClassLoader 누수 + Code Cache 누적)
> 
> 4. **조치**:
>    - `-XX:ReservedCodeCacheSize=512m` (240 → 512MB).
>    - 동적 클래스 생성 audit (Spring AOP unnecessary proxy 제거).
>    - Lambda 사용 패턴 검토 (capture 줄이기, 재사용).
>    - `-XX:+PrintCompilation` 로 어떤 메서드가 컴파일되는지 식별.
> 
> 5. **장기 모니터링**:
>    - JFR `jdk.CodeCacheStatistics` 주기 로깅.
>    - Prometheus + jvm_classloader_loaded, jvm_jit_compilations 지표.

#### 🪝 Q7-1: 컴파일 자체를 줄여서 Code Cache 사용을 줄이는 옵션이 있나요?

> 1. `-XX:-TieredCompilation` — C1 결과 거의 안 만듦. Profiled segment 사용 ↓ (절반 가까이 절약).
> 2. `-XX:TieredStopAtLevel=1` — C1까지만, C2 안 함. Non-profiled 거의 안 씀.
> 3. `-XX:CompileThreshold=20000` — 더 늦게 컴파일 (호출 횟수 임계 ↑).
> 4. `-XX:MaxInlineSize=N` 작게 → inlining 줄임 → nmethod 크기 ↓.
> 
> 단점: 모두 peak 성능 또는 warmup에 영향. **trade-off 명시 후 측정해야 함**.

---

## 🔗 다음 단계

- → [05. Direct Memory](./05-direct-memory.md): Off-heap NIO buffer
- → [06. GC bookkeeping](./06-gc-bookkeeping-and-others.md): Card Table, RSet, Mark Bitmap
- ← [03. Stack & PC & Native](./03-stack-pc-native.md): Per-thread 메모리
- ← [02. Metaspace](./02-metaspace-and-class-space.md): Class 메타데이터
- 관련: 추후 03-execution-engine 챕터 — JIT 컴파일러 내부 (C1/C2, Sea-of-Nodes, Escape Analysis 등)

## 📚 참고

- **JEP 197 Segmented Code Cache**: https://openjdk.org/jeps/197
- **HotSpot `codeCache.cpp`**: https://github.com/openjdk/jdk/blob/master/src/hotspot/share/code/codeCache.cpp
- **HotSpot `nmethod.hpp`**: https://github.com/openjdk/jdk/blob/master/src/hotspot/share/code/nmethod.hpp
- **HotSpot `compileBroker.cpp`**: https://github.com/openjdk/jdk/blob/master/src/hotspot/share/compiler/compileBroker.cpp
- **Oracle — Tiered Compilation Notes**: https://docs.oracle.com/en/java/javase/21/vm/java-hotspot-virtual-machine-performance-enhancements.html
- **JITWatch (시각화 도구)**: https://github.com/AdoptOpenJDK/jitwatch
- **Aleksey Shipilëv — JIT Compilation Watcher**: https://shipilev.net/jvm/anatomy-quarks/
- **Cliff Click — A JVM Does What?**: 컨퍼런스 발표, Sea-of-Nodes의 원작자가 본 컴파일 흐름
