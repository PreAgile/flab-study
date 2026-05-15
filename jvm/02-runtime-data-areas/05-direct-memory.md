# 02-05. Direct Memory — Heap 밖, GC 너머의 메모리

> `ByteBuffer.allocate(1024)`는 Heap에 1KB 할당.
> `ByteBuffer.allocateDirect(1024)`는 어디에 1KB를 할당하는가? **Heap이 아니다. OS의 native 메모리.**
> 이 메모리는 GC가 직접 관리하지 않는다. DirectByteBuffer 객체(Heap에 있음)가 unreachable이 되어 GC될 때, 그 객체의 **Cleaner**(PhantomReference의 일종)가 `free()`를 호출한다.
> "DirectByteBuffer 객체는 GC됐는데 native memory는 아직 살아 있는" 순간이 길어지면 — Direct Memory 누수, 컨테이너 OOM-killed의 흔한 원인.
> Netty, Kafka, gRPC 같은 라이브러리가 Direct Memory를 적극 쓰는 이유와 누수 패턴을 모르면 production에서 길게 헤맨다.

---

## 📍 학습 목표

이 챕터를 마치면 다음을 모두 답할 수 있다.

1. Heap Buffer vs Direct Buffer의 차이 — 메모리 위치, GC 정책, I/O 성능.
2. **Direct Memory가 Heap 밖**이라는 사실의 운영 함의 — `-Xmx`와 무관, `-XX:MaxDirectMemorySize`로 별도 제어, `OutOfMemoryError: Direct buffer memory` 별도.
3. **Cleaner 메커니즘** — PhantomReference 기반으로 DirectByteBuffer 객체 GC 시점에 native `free()` 호출되는 흐름.
4. **Zero-copy I/O** — 왜 NIO에서 Direct Buffer가 성능 이득이 있는지 (커널 버퍼와의 메모리 복사 없음).
5. **MappedByteBuffer**와 `FileChannel.map()` — mmap이 무엇이고 일반 read/write와 어떻게 다른지.
6. **Page cache vs Direct Buffer** — OS page cache가 자동 캐싱하는 영역과 JVM이 직접 관리하는 영역의 차이.
7. Netty의 PooledByteBufAllocator, Kafka의 buffer pool 같은 **풀링 패턴**이 왜 필요한지.
8. Direct Memory 누수의 5가지 패턴 (해제 누락, Cleaner 트리거 지연, MappedByteBuffer 누수, Netty 누수, JNI 직접 할당).
9. `jcmd VM.native_memory` 의 Internal/Other 영역에서 Direct Memory 추적, `-XX:NativeMemoryTracking=detail`의 한계.
10. 컨테이너 OOM-killed인데 Heap dump가 정상일 때 Direct Memory를 의심하는 사고 흐름.

---

## 🎨 1단계: 백지 그리기 가이드

### Step 1: JVM Process 안에서 Direct Memory 위치

- 큰 사각형 안에 [Java Heap] | [Native: Metaspace, Code Cache, Thread Stacks, ...] | [★ Direct Memory ★] 분리.
- Direct Memory 박스에 라벨: "Off-heap, mmap/malloc, GC 직접 관리 안 함".

### Step 2: Heap의 DirectByteBuffer 객체와 native 메모리 연결

```
[Java Heap]                              [Native Memory]
┌────────────────────────────┐           ┌──────────────────────┐
│ DirectByteBuffer 객체        │           │ Native allocated     │
│  ├── address (long)         │           │ buffer (예: 1MB)     │
│  │       │                  │           │                       │
│  │       └──────────────────┼──────────►│ ◄── 실제 데이터        │
│  ├── capacity, position, ...│           │                       │
│  └── Cleaner (PhantomRef)   │           └──────────────────────┘
└────────────────────────────┘                      ▲
         │                                          │
         │ GC됨                                      │ free() 호출
         ▼                                          │
    [Cleaner.clean()] ────────────────────────────────┘
```

### Step 3: Cleaner 흐름 추가

```
DirectByteBuffer 생성 시:
   1. Native 메모리 malloc/mmap (예: 1MB)
   2. Java 객체 DirectByteBuffer 생성, address = native 주소
   3. Cleaner.create(this, () -> free(address)) 등록
                  │
                  ▼
DirectByteBuffer 사용 중: read/write는 native 주소에 직접 접근
                  │
                  ▼
DirectByteBuffer 객체가 unreachable이 됨
                  │
                  ▼
GC가 PhantomReference (Cleaner)를 발견
                  │
                  ▼
ReferenceHandler thread가 Cleaner를 enqueue
                  │
                  ▼
Cleaner.clean() 호출 → free(address)
                  │
                  ▼
Native 메모리 해제
```

### Step 4: MappedByteBuffer vs DirectByteBuffer

```
DirectByteBuffer:                      MappedByteBuffer:
━━━━━━━━━━━━━━━━━                      ━━━━━━━━━━━━━━━━

malloc(size) 또는                       mmap(file, ...) — 파일을 메모리로 매핑
calloc(size)                            
                                        커널이 page cache로 자동 캐싱
프로세스 anonymous memory               파일과 메모리가 1:1 매핑
                                        write 시 lazy로 디스크 sync
```

### 정답 그림

```
JVM Process Memory
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[Shared]                  [Native managed by JVM]    [★ Direct ★ — JVM 직접 관리]

┌────────────┐            ┌────────────┐             ┌─────────────────────┐
│ Java Heap   │            │ Metaspace   │             │ DirectByteBuffer     │
│  -Xmx 2g    │            │             │             │  buffers             │
│  GC 대상    │            │             │             │  - malloc된 영역     │
└────────────┘            └────────────┘             │  - GC 간접 (Cleaner) │
                                                      │  -XX:MaxDirectMem    │
┌────────────┐            ┌────────────┐             ├─────────────────────┤
│ Stacks     │            │ Code Cache  │             │ MappedByteBuffer     │
└────────────┘            └────────────┘             │  - mmap된 파일       │
                                                      │  - OS page cache 사용 │
                                                      │  - -XX:MaxDirectMem  │
                                                      │     에 카운트 안 됨!  │
                                                      └─────────────────────┘

      ↑ GC 대상                ↑ JVM 자체 메모리             ↑ DirectByteBuffer는
                                                              -XX:MaxDirectMemorySize
                                                              MappedByteBuffer는 OS 영역
```

---

## 🧠 2단계: 직관

### 핵심 비유

> **택배 비유**:
> - **Heap Buffer (`ByteBuffer.allocate`)** = 회사 창고(Heap) 안의 임시 상자. 회사 직원(GC)이 정기적으로 청소.
> - **Direct Buffer (`ByteBuffer.allocateDirect`)** = 회사 밖의 별도 임대 창고. 회사 직원이 청소 안 함. 별도 계약(Cleaner)으로 해제.
> - **MappedByteBuffer (`FileChannel.map`)** = 외부 데이터 센터의 원본 파일을 회사 사무실에서 직접 들여다보는 윈도우. 변경하면 즉시 데이터 센터에 반영.
> - **Cleaner** = 임대 창고 사용자가 죽으면 자동으로 계약 해지를 통보하는 변호사. 효력 시점은 변호사가 통지 받은 후.
> - **누수** = 임대 창고 사용자(DirectByteBuffer)는 죽었는데 변호사(Cleaner)가 늦게 통지 → 임대료(메모리)가 계속 발생.

### 정확한 정의 (비유와 분리)

| 용어 | 정의 |
|---|---|
| **Direct Memory** | JVM Heap 밖, OS의 native 메모리(malloc/mmap). NIO API를 통해 할당. GC가 직접 관리하지 않음. |
| **DirectByteBuffer** | `java.nio.DirectByteBuffer` 클래스. Heap 객체이지만 데이터 영역은 native. `ByteBuffer.allocateDirect(N)`으로 생성. |
| **Heap ByteBuffer** | `java.nio.HeapByteBuffer`. 데이터 영역도 Heap. `ByteBuffer.allocate(N)`으로 생성. |
| **MappedByteBuffer** | `FileChannel.map()`이 반환. mmap된 파일을 메모리로 매핑. 디스크와 메모리가 페이지 단위 동기. |
| **Cleaner** | `jdk.internal.ref.Cleaner` (JDK 9+) — PhantomReference 기반. DirectByteBuffer가 GC될 때 native free 호출. JDK 8까지는 `sun.misc.Cleaner`. |
| **Zero-copy I/O** | NIO에서 Direct Buffer 사용 시 커널과 JVM 사이 메모리 복사 단계를 생략. read/write 시 Heap → 커널 복사 없이 Direct Buffer가 그대로 syscall 대상. |
| **Page cache** | OS 커널이 자동 관리하는 디스크 캐시. 일반 file I/O와 mmap 모두 page cache 경유. JVM 입장에서는 RSS에 포함되어 보이지만 메모리 압박 시 OS가 자동 회수. |
| **`-XX:MaxDirectMemorySize`** | DirectByteBuffer 총 할당 한계. **MappedByteBuffer는 포함 안 됨**. 기본은 -Xmx와 비슷한 크기. |

### 왜 Direct Memory가 따로 있나 — Zero-copy의 본질

#### 일반 Heap Buffer로 파일 read 시 (3번 복사)

```
[디스크]                                    
   │  (1) DMA로 커널 page cache로
   ▼
[커널 page cache] ────────────────────────►  (2) 커널 → JVM Heap 복사 (CPU)
                                                              │
                                                              ▼
                                              [Java Heap의 byte[] / HeapByteBuffer]
                                                              │
                                              (3) JVM이 사용자 코드에 전달
                                                              │
                                                              ▼
                                              [사용자 코드의 처리]

총 메모리 복사: 2회 (DMA 제외)
```

#### Direct Buffer로 read 시 (1번 복사)

```
[디스크]
   │  (1) DMA로 Direct Buffer로 직접
   ▼
[Direct Buffer (native 메모리)] ◄────────  사용자 코드가 직접 접근
                                            (Heap 복사 없음)

총 메모리 복사: 1회 (DMA 제외)
```

→ **고처리량 I/O 시스템(Netty, Kafka, gRPC, Cassandra)이 Direct Buffer를 쓰는 이유**. 메모리 복사 50% 절감 + cache pollution 감소.

#### 트레이드오프 — Direct Buffer가 항상 빠른가?

NO. 할당 비용이 Heap Buffer보다 비싸다:
- Heap Buffer: TLAB에서 bump-the-pointer (~3 instruction).
- Direct Buffer: native malloc + Cleaner 등록 + 메모리 페이지 commit (~수 us ~ 수십 us).

→ **수명이 긴 버퍼만 Direct로**. Short-lived는 Heap이 더 빠름. 그래서 Netty의 PooledByteBufAllocator 같은 풀링이 필요.

### Cleaner의 핵심 메커니즘 — PhantomReference

```
일반 객체 lifecycle:
   생성 → 사용 → unreachable → GC가 회수 → 메모리 free

DirectByteBuffer lifecycle:
   생성 → native malloc → Cleaner 등록 → 사용
        → unreachable → GC가 객체 회수
        → 그러나 native 메모리는 아직 살아있음 ★
        → ReferenceHandler가 PhantomReference 발견
        → Cleaner.clean() 호출 → native free()
        → 비로소 native 메모리 해제
```

**왜 두 단계인가**:
- finalize는 deprecated (예측 불가, 성능 영향).
- PhantomReference는 객체 GC 후에도 Cleaner가 살아있어 native free를 보장.
- 단점: **GC와 native free 사이에 지연**. 짧은 시간에 DirectByteBuffer 폭주 시 native 메모리가 GC를 못 따라가 OOM.

### `OutOfMemoryError: Direct buffer memory`의 안전판

JVM이 `DirectByteBuffer` 할당 시도할 때:
1. 현재 Direct Memory 사용량 + 새 할당 ≤ `MaxDirectMemorySize` 인가?
2. 아니면 **System.gc() 강제 호출** → 일반 GC 트리거 → PhantomReference 처리 → 일부 free.
3. 그래도 부족하면 `OutOfMemoryError: Direct buffer memory` throw.

→ 그래서 `-XX:+DisableExplicitGC` 옵션 켜면 위 step 2가 사라져 OOM 더 쉽게 발생. **NIO 사용 앱에서는 함부로 켜면 안 됨**.

---

## 🔬 3단계: 구조

### DirectByteBuffer의 내부 구조

`java.nio.DirectByteBuffer` (간략화):

```java
class DirectByteBuffer extends MappedByteBuffer {
    // Heap에 있는 메타데이터
    long address;          // ★ Native 메모리 시작 주소
    int  capacity;         // 버퍼 크기
    int  position, limit, mark;
    Cleaner cleaner;       // GC 시 native free 호출자

    DirectByteBuffer(int cap) {
        // 1. Native 메모리 할당
        long addr = UNSAFE.allocateMemory(cap);
        // 2. 0으로 초기화 (옵션)
        UNSAFE.setMemory(addr, cap, (byte) 0);
        // 3. Heap 객체 필드 설정
        this.address = addr;
        this.capacity = cap;
        // 4. Cleaner 등록
        this.cleaner = Cleaner.create(this, new Deallocator(addr, cap));
    }

    public byte get(int index) {
        // Heap 객체 → native 주소 → 직접 메모리 접근
        return UNSAFE.getByte(address + index);
    }

    static class Deallocator implements Runnable {
        long address;
        int  size;
        public void run() {
            UNSAFE.freeMemory(address);
            // -XX:MaxDirectMemorySize 카운터 감소
            Bits.unreserveMemory(size);
        }
    }
}
```

→ **Heap에 작은 객체, Native에 큰 데이터**. 둘이 `address` 필드로 연결.

### `Bits` 클래스 — Direct Memory 회계 (accounting)

위치: `java.nio.Bits` (JDK 내부 비공개 클래스)

```java
class Bits {
    // 전역 카운터
    private static final AtomicLong RESERVED_MEMORY = new AtomicLong();
    private static final AtomicLong TOTAL_CAPACITY = new AtomicLong();

    static void reserveMemory(long size, int cap) {
        // -XX:MaxDirectMemorySize 한계 체크
        long max = maxMemory();
        if (RESERVED_MEMORY.get() + size > max) {
            // System.gc() 트리거하여 Cleaner들 처리
            System.gc();
            try { Thread.sleep(100); } catch (...) {}
            // 다시 체크 - 여전히 부족하면 OOM
            if (RESERVED_MEMORY.get() + size > max) {
                throw new OutOfMemoryError("Direct buffer memory");
            }
        }
        RESERVED_MEMORY.addAndGet(size);
    }

    static void unreserveMemory(long size, int cap) {
        RESERVED_MEMORY.addAndGet(-size);
    }
}
```

**핵심 관찰**:
- DirectByteBuffer 생성 시 `reserveMemory` 호출 — Direct Memory 한계 체크.
- 한계 초과 시 **System.gc() 강제 호출** — Cleaner 트리거. `-XX:+DisableExplicitGC` 시 이 호출이 무력화 → OOM 위험.
- Deallocator가 `unreserveMemory` 호출 — 한계 카운터 감소.

### Cleaner 처리 흐름 (JDK 9+)

위치: `jdk.internal.ref.Cleaner` (JDK 9+) / `java.lang.ref.Cleaner` (public API)

```
[Application Thread]
DirectByteBuffer buf = ByteBuffer.allocateDirect(1MB);
  → Bits.reserveMemory(1MB)
  → UNSAFE.allocateMemory(1MB) → native pointer P
  → new DirectByteBuffer(P, 1MB)
  → Cleaner.create(buf, new Deallocator(P, 1MB))
       → Deallocator를 PhantomReference로 ReferenceQueue에 등록
       → buf와 Deallocator 연결

[Application Thread]
buf = null;   // unreachable

[GC Thread]
- Young GC: buf 객체 처리
- buf가 unreachable → Cleaner (PhantomRef)가 enqueue 대상

[Reference Handler Thread]
- ReferenceQueue 모니터링
- Cleaner를 발견 → Cleaner.clean() 호출
       → Deallocator.run()
            → UNSAFE.freeMemory(P)  ← Native 메모리 해제
            → Bits.unreserveMemory(1MB)
```

→ **세 스레드 협력**: Application(생성), GC(객체 회수), Reference Handler(Cleaner 실행). 마지막 단계까지 지연 시 native 메모리 잠시 살아있음.

### MappedByteBuffer의 구조

`FileChannel.map()`이 반환하는 buffer:

```java
RandomAccessFile raf = new RandomAccessFile("data.bin", "rw");
FileChannel ch = raf.getChannel();
MappedByteBuffer mb = ch.map(FileChannel.MapMode.READ_WRITE, 0, 1024 * 1024);
// → mmap syscall로 1MB를 파일에 매핑
// → 메모리 read/write가 즉시 파일에 반영
```

내부:
```java
class MappedByteBuffer extends DirectByteBuffer {
    // Direct와 같은 구조 + 파일 매핑 정보
    long address;       // mmap된 주소
    int  capacity;
    FileDescriptor fd;  // 매핑 대상 파일
}
```

**`mmap` vs `malloc`**:
- `malloc`: 익명 메모리, 파일과 무관. 프로세스 종료 시 사라짐. (DirectByteBuffer)
- `mmap`: 파일과 매핑. 페이지 단위 lazy 로드. 페이지 변경 시 lazy로 디스크 sync. (MappedByteBuffer)

**중요한 사실**: MappedByteBuffer는 `-XX:MaxDirectMemorySize` 카운터에 **포함되지 않는다**. OS의 page cache 영역에 들어가므로 별도 한계 없음 (가상 메모리 한계와 OS의 page cache 정책에 의존).

### Page Cache vs Direct Memory

```
[일반 file read/write]
read(fd, buf, size)
  └→ 커널이 디스크 → page cache 로 가져옴
  └→ page cache → 사용자 buf로 copy

[MappedByteBuffer + read]
mb.get(i)
  └→ 페이지 fault if 첫 접근
  └→ 커널이 디스크 → page cache 로 가져옴
  └→ 사용자가 page cache 메모리에 직접 read (copy 없음)

[DirectByteBuffer + Channel.read]
ch.read(directBuf)
  └→ DMA가 디스크 → directBuf의 native 메모리로
  └→ JVM이 directBuf로 사용자 코드에 노출
```

→ MappedByteBuffer가 page cache 사용 = OS가 메모리 압박 시 자동 evict 가능. Direct Buffer는 JVM 책임.

### Netty의 PooledByteBufAllocator — 풀링의 필요성

Netty는 매 connection마다 buffer를 생성/해제하면 비용이 큼:
- 생성: `UNSAFE.allocateMemory` (~수 us).
- 해제: Cleaner를 통한 free (delay 있음).

**Pooled 모델** (Netty 4+ 기본):
```
Allocator의 풀
  ├── Chunk (16MB 단위로 OS에서 받음)
  │     ├── PoolSubpage (작은 buffer용, 한 chunk를 8KB 페이지로)
  │     │     └── small allocation (≤ 8KB)
  │     └── normal allocation (8KB ~ 16MB)
  └── 사용자는 풀에서 buffer를 받았다 반환

장점:
- 빈번한 malloc/free 회피
- Cleaner 트리거 안 함 (풀이 직접 관리)
- TLB pressure ↓

단점:
- 풀 자체가 메모리 점유 (idle 상태에도)
- 풀 누수 가능 (ref count 잘못 관리)
```

### Direct Memory 누수의 5가지 패턴

#### 패턴 1: Cleaner 트리거 지연 (Young GC만 도는 경우)

```
- DirectByteBuffer 객체가 Young Gen에서 빨리 죽음 → Young GC가 처리
- 하지만 Young GC만 너무 자주 도는 동안에는 Cleaner thread가 못 따라감
  (또는 Cleaner를 트리거하는 GC가 Major여야 하는 구현)
- 결과: Heap의 객체는 사라졌는데 native 메모리는 잠시 살아있음

해결: GC 튜닝 또는 명시적 `((DirectBuffer) buf).cleaner().clean()` 호출
       (JDK 9+ 에서는 `jdk.internal.ref.Cleaner` API)
```

#### 패턴 2: MappedByteBuffer 해제 불가

```java
RandomAccessFile raf = new RandomAccessFile("big.bin", "rw");
MappedByteBuffer mb = raf.getChannel().map(MapMode.READ_WRITE, 0, 10_000_000_000L); // 10GB
// 사용 후 raf.close() 해도 mmap은 즉시 해제 안 됨
// → mb가 GC돼야 unmap, 그 전까지는 OS 가상 메모리 점유
```

**해결**:
- JDK 9+: 명시적 unmap API 없음 (보안 이유). `sun.misc.Cleaner`로 강제 invoke 가능했지만 internal API.
- 대안: `try { mb = null; System.gc(); } catch ...` — 비결정적.
- 정공법: 작은 단위로 분할 mmap 후 사용 후 명시적 해제.

#### 패턴 3: Netty 누수 — ReferenceCountUtil 누락

```java
ByteBuf buf = allocator.directBuffer(1024);
// ... 처리
// release() 호출 안 함 → 풀로 반환 안 됨
// 충분히 누적되면 풀이 새 chunk 계속 할당 → 메모리 ↑
```

Netty의 안전판: `-Dio.netty.leakDetection.level=PARANOID` — 누수 시 stack trace 출력.

#### 패턴 4: JNI 라이브러리의 직접 native allocation

```c
// JNI 코드
JNIEXPORT jlong JNICALL Java_Foo_native_1alloc(JNIEnv *env, jclass cls, jlong size) {
    void *p = malloc(size);
    return (jlong) p;   // ★ Java 코드가 free 호출 안 하면 영원히 누수
}
```

NMT가 이걸 못 봄 — JVM이 모르는 malloc.

#### 패턴 5: `-XX:+DisableExplicitGC` + DirectByteBuffer 폭주

```java
// Bits.reserveMemory가 한계 도달 시 System.gc() 호출
// -XX:+DisableExplicitGC 켜져 있으면 이 호출 무력화
// → Cleaner trigger 못 함 → OOM: Direct buffer memory
```

### `OutOfMemoryError: Direct buffer memory` 정확한 메시지

```
java.lang.OutOfMemoryError: Cannot reserve 1048576 bytes of direct buffer memory
  (allocated: 1073741824, limit: 1073741824)
    at java.base/java.nio.Bits.reserveMemory(Bits.java:175)
    at java.base/java.nio.DirectByteBuffer.<init>(DirectByteBuffer.java:118)
    at java.base/java.nio.ByteBuffer.allocateDirect(ByteBuffer.java:317)
```

→ **`allocated`가 `limit`에 도달**. 한계는 `-XX:MaxDirectMemorySize`.

---

## 🧬 4단계: 내부 구현 — HotSpot 및 JDK

### Bits.reserveMemory — JDK 17+ 버전

위치: `src/java.base/share/classes/java/nio/Bits.java`

```java
static void reserveMemory(long size, long cap) {
    if (!MEMORY_LIMIT_SET && VM.initLevel() >= 1) {
        MAX_MEMORY = VM.maxDirectMemory();
        MEMORY_LIMIT_SET = true;
    }

    // 1. 빠른 path: 카운터 ≤ MAX
    if (tryReserveMemory(size, cap)) return;

    // 2. 한계 초과 — pending Reference 처리 시도
    JLA.runFinalization();  // Reference queue 처리 강제

    // 3. 그래도 안 되면 System.gc()
    System.gc();

    // 4. 짧게 sleep 후 재시도
    boolean interrupted = false;
    try {
        long sleepTime = 1;
        int sleeps = 0;
        while (true) {
            if (tryReserveMemory(size, cap)) return;
            if (sleeps >= MAX_SLEEPS) break;
            try {
                if (!jla.processPendingReferences()) {
                    Thread.sleep(sleepTime);
                    sleepTime <<= 1;
                    sleeps++;
                }
            } catch (InterruptedException e) {
                interrupted = true;
            }
        }
        // 5. 최종 실패 — OOM
        throw new OutOfMemoryError
            ("Cannot reserve " + size + " bytes of direct buffer memory (allocated: " + ...);
    } finally {
        if (interrupted) Thread.currentThread().interrupt();
    }
}
```

→ JVM이 **OOM 직전 마지막 보루로 9번까지 sleep + retry**. 그래도 안 되면 throw.

### Cleaner 메커니즘 (JDK 9+)

위치: `src/java.base/share/classes/jdk/internal/ref/Cleaner.java`

```java
public class Cleaner extends PhantomReference<Object> {
    private static final ReferenceQueue<Object> queue = new ReferenceQueue<>();

    public static Cleaner create(Object referent, Runnable thunk) {
        return new Cleaner(referent, thunk);
    }

    public void clean() {
        // synchronized로 한 번만 실행 보장
        synchronized (this) {
            if (cleaned) return;
            cleaned = true;
        }
        thunk.run();
    }

    // ReferenceHandler thread가 호출
    public static boolean processPendingCleaners() {
        Cleaner ref = (Cleaner) queue.poll();
        if (ref != null) {
            ref.clean();
            return true;
        }
        return false;
    }
}
```

→ `Cleaner` = PhantomReference. `referent` (DirectByteBuffer)가 GC되면 자동 enqueue. Reference Handler thread가 queue를 polling하며 `clean()` 호출.

### UNSAFE.allocateMemory의 내부

위치: `src/hotspot/share/prims/unsafe.cpp`

```cpp
JVM_ENTRY_NO_ENV(jlong, Unsafe_AllocateMemory(JNIEnv *env, jobject unsafe, jlong size))
  size_t sz = (size_t)size;
  // OS의 malloc/aligned_alloc 호출
  void* p = os::malloc(sz, mtOther);
  if (p == NULL) {
    THROW_0(vmSymbols::java_lang_OutOfMemoryError());
  }
  return addr_to_java(p);
JVM_END
```

→ JVM 입장에선 그냥 OS malloc. Native Memory Tracking에 `mtOther`로 카운트.

### Native Memory Tracking과 Direct Memory

```bash
java -XX:NativeMemoryTracking=summary -jar app.jar
jcmd <pid> VM.native_memory summary
```

출력 예시:
```
Native Memory Tracking:

Total: reserved=4128931KB, committed=2870883KB
-                 Java Heap (reserved=2097152KB, committed=2097152KB)
                            (mmap: reserved=2097152KB, committed=2097152KB)

-                     Class (reserved=1059905KB, committed=20929KB)
                            (classes #4321)
                            (instance classes #4112, array classes #209)
                            (malloc=6913KB #16234)
                            (mmap: reserved=1052992KB, committed=13016KB)

-                    Thread (reserved=521728KB, committed=521728KB)
                            (thread #509)
                            (stack: reserved=520192KB, committed=520192KB)

-                     Other (reserved=240234KB, committed=240234KB)   ← ★ Direct Memory 일부
                            (malloc=240234KB #234)
```

**핵심**: Direct Memory가 NMT에서 **`Other` 또는 `Internal`** 카테고리에 들어감. 별도 카테고리 아님. 그래서 정확한 추적은 BufferPool MBean을 함께 봐야 함.

### BufferPool MBean

```bash
jcmd <pid> ManagementAgent.start
# JMX로 BufferPool 정보 조회
```

또는 직접 Java 코드:
```java
List<BufferPoolMXBean> pools = ManagementFactory.getPlatformMXBeans(BufferPoolMXBean.class);
for (BufferPoolMXBean pool : pools) {
    System.out.println(pool.getName() + ": " + pool.getCount() + " buffers, "
                       + pool.getMemoryUsed() + " bytes");
}
// 출력:
// direct: 1234 buffers, 567890123 bytes
// mapped: 5 buffers, 1073741824 bytes
```

→ `direct` pool은 DirectByteBuffer 합계. `mapped` pool은 MappedByteBuffer 합계.

---

## 📜 5단계: 역사

| 연도 | JDK | 변화 | 이유 |
|---|---|---|---|
| 2002 | 1.4 | NIO 도입 (`java.nio`) + Direct Buffer | 고처리량 I/O |
| 2004 | 5 | `MaxDirectMemorySize` 옵션 | 무제한 할당 사고 방지 |
| 2014 | 8 | `sun.misc.Cleaner` 정착 | finalize 회피 |
| 2017 | 9 | `jdk.internal.ref.Cleaner` (모듈화) | sun.misc 폐기 단계 |
| 2017 | 9 | `java.lang.ref.Cleaner` public API | 사용자도 Cleaner 사용 가능 |
| 2019 | 12+ | Buffer API의 covariant return | 사용성 |
| 2021 | 17 | `sun.misc.Unsafe.invokeCleaner` 폐기 시작 | 보안 |
| 2024 | 22+ | **Foreign Function & Memory API stable** (JEP 454) | Direct Memory의 modern 대체 |

### Foreign Memory API — Direct Buffer의 미래

JDK 22 (JEP 454):
```java
try (Arena arena = Arena.ofConfined()) {
    MemorySegment seg = arena.allocate(1024);  // Direct Memory 할당
    seg.set(ValueLayout.JAVA_INT, 0, 42);
    int x = seg.get(ValueLayout.JAVA_INT, 0);
}  // Arena가 자동 unmap — try-with-resources로 명시적 해제
```

→ **deterministic free**. Cleaner의 비결정적 free 문제 해결. DirectByteBuffer를 점진적으로 대체할 것.

---

## ⚖️ 6단계: 트레이드오프

### Heap Buffer vs Direct Buffer

| 항목 | Heap Buffer | Direct Buffer |
|---|---|---|
| 할당 비용 | ~3 instruction (TLAB) | ~수 us (malloc) |
| 사용 비용 | 정상 | 정상 |
| I/O 성능 | ❌ 커널 복사 1번 추가 | ✅ Zero-copy |
| GC 영향 | 일반 객체 (Young GC) | Heap 객체 매우 작음, native는 GC와 별개 |
| 해제 비용 | GC 자동 | Cleaner 비결정적 |
| 한계 | -Xmx | -XX:MaxDirectMemorySize |
| 용도 | 단명 처리 데이터 | 장명, 큰 I/O |

**경험칙**:
- < 1KB + 단명: Heap.
- > 1MB + I/O: Direct.
- 중간: 풀링 사용.

### `-XX:MaxDirectMemorySize` 트레이드오프

| 작게 (예: 256MB) | 크게 (예: 4GB) |
|---|---|
| ✅ 누수 빨리 발견 | ❌ 누수 늦게 발견 |
| ❌ 정상 워크로드도 OOM 위험 | ✅ 정상 워크로드 견딤 |
| ✅ 컨테이너 friendly | ❌ 컨테이너 limit 압박 |

**경험칙**: `-Xmx`와 비슷한 크기. Netty 사용 시 1~2GB. Container 환경에서는 limit의 30~50%를 -Xmx, 20~30%를 MaxDirect.

### `-XX:+DisableExplicitGC` 함정

| 켰을 때 | 껐을 때 (기본) |
|---|---|
| ✅ 사용자가 `System.gc()` 호출해도 무시 | ❌ 사용자가 강제 GC 가능 |
| ❌ **DirectByteBuffer 폭주 시 OOM 빨리 발생** | ✅ Bits.reserveMemory가 트리거하는 자동 GC 가능 |
| ❌ NMT/JFR이 GC 강제하는 path 무력화 | ✅ 정상 |

→ **NIO/Netty 쓰는 앱에서 절대 켜지 말 것**. 옛 자료 중 `+DisableExplicitGC` 권장이 있어도 무시.

### MappedByteBuffer vs DirectByteBuffer

| | MappedByteBuffer | DirectByteBuffer |
|---|---|---|
| 메모리 출처 | mmap (파일) | malloc (anonymous) |
| -XX:MaxDirectMemorySize | ❌ 카운트 안 됨 | ✅ 카운트 |
| 디스크 sync | 자동 (페이지 단위 lazy) | 수동 (FileChannel.write) |
| 메모리 압박 시 | OS가 page cache evict (자동) | JVM이 직접 |
| 적합 워크로드 | 큰 파일 random access | 네트워크 I/O |

---

## 📊 7단계: 측정·진단

### BufferPool 사용량 (JMX/jcmd)

```bash
# JMX 활성화 필요
java -Dcom.sun.management.jmxremote -jar app.jar

# 또는 jconsole/JFR
```

JFR:
```bash
jcmd <pid> JFR.start name=buf duration=60s settings=profile filename=buf.jfr
jfr summary buf.jfr | grep -i 'BufferStatistics'
```

핵심 이벤트:
- `jdk.DirectBufferStatistics` — 주기적 Direct Buffer pool 통계.
- `jdk.JavaMonitorEnter` — pinning 같은 lock 이벤트.

### `jcmd VM.native_memory` 의 한계

```bash
java -XX:NativeMemoryTracking=detail -jar app.jar
jcmd <pid> VM.native_memory detail
```

`detail` 옵션:
- Stack trace까지 포함된 정밀 추적.
- 각 영역의 caller 확인 가능.

**한계**:
- JNI native 라이브러리의 직접 malloc은 NMT가 못 봄 (mtOther로 들어가지만 stack trace 없음).
- 옛 sun.misc.Unsafe.allocateMemory도 mtOther.
- 별도 도구 필요: `jemalloc` 또는 Linux `pmap`.

### `pmap` — OS 레벨 메모리 맵

```bash
pmap -x <pid> | head -30

# 출력 예:
# Address           Kbytes     RSS   Dirty Mode  Mapping
# 00007f7e8c000000   65536   65532   65532 rw-p- [anon]   ← Heap
# 00007f7e90000000  240000  240000  240000 rw-p- [anon]   ← Code Cache
# 00007f7ea0000000   65536   65532   65532 rw-p- [anon]   ← Direct Buffer 후보
# 00007f7eb0000000 1048576   23456   23456 r--s- big.bin  ← MappedByteBuffer
```

`[anon]` 큰 영역이 RSS와 일치한다면 DirectByteBuffer 가능성. 파일 매핑은 파일명 표시.

### Netty 누수 추적

```java
// 시작 시 옵션
java -Dio.netty.leakDetection.level=PARANOID -jar app.jar
```

레벨:
- `DISABLED`: 추적 안 함.
- `SIMPLE` (기본): 1% 샘플링.
- `ADVANCED`: 더 많은 정보 + 1% 샘플링.
- `PARANOID`: 100% 추적, **운영 환경에서는 느림**.

누수 발견 시 stack trace 출력 — 어디서 `release()` 안 한지 식별.

### MappedByteBuffer unmap 강제

JDK 9+에서는 표준 API 없음. internal API 사용 (위험):
```java
import jdk.internal.misc.Unsafe;

void unmap(MappedByteBuffer buf) {
    Unsafe unsafe = Unsafe.getUnsafe();
    unsafe.invokeCleaner(buf);
}
```

**경고**: JDK 17+ Strong Encapsulation에서 막힘 (`--add-opens` 필요). 권장 안 함.

### 운영 시나리오 진단 매트릭스

| 증상 | 진단 명령 | 가능 원인 |
|---|---|---|
| `OOM: Direct buffer memory` | `BufferPoolMXBean.getMemoryUsed()` | DirectByteBuffer 한계 도달 |
| Container OOM-killed인데 Heap dump 정상 | `pmap -x <pid>` + `NMT detail` | Direct Buffer 또는 Mapped 누수 |
| RSS는 큰데 NMT 합과 안 맞음 | `jemalloc` 또는 `pmap` | JNI 라이브러리 누수 |
| Netty 앱이 시간 지나 메모리 ↑ | `-Dio.netty.leakDetection.level=PARANOID` | ReferenceCountUtil 누락 |
| MappedByteBuffer 해제 안 됨 | `pmap` 에 파일 매핑 누적 | mmap unmap 누락 |
| `System.gc()` 호출 후에도 누적 | `-XX:+DisableExplicitGC` 켜진 게 의심 | 옵션 점검 |

### 시나리오 1: Container OOM-killed, Heap dump 정상

```
증상: container 5GB limit, -Xmx 2GB 인데 OOM-killed
       Heap dump 분석은 정상 (2GB 못 채우고 죽음)

진단 단계:
1. jcmd VM.native_memory summary
   - Heap: 2GB
   - Metaspace: 200MB
   - Threads: 500MB (500 thread)
   - Code Cache: 240MB
   - Other(Direct + 기타): ???MB ← 의심

2. BufferPoolMXBean 확인
   - direct: 2.5GB ← ★ MaxDirectMemorySize 설정 안 했고 -Xmx 만큼 자동 부여됨

3. 원인 식별 (Netty 사용 중)
   - PARANOID 모드 → release 누락 1곳 발견

4. 조치
   - 코드 수정
   - -XX:MaxDirectMemorySize=512m 명시
   - 컨테이너 환경에서 명시적 한계 강제
```

### 시나리오 2: MappedByteBuffer 누수

```
증상: 큰 파일 처리 후 RSS가 안 줄어듦
       pmap에 큰 r--s- 매핑 누적

원인: 파일 처리 후 MappedByteBuffer 참조를 명시적 null로 못 만듦
       또는 `try-with-resources`로 RandomAccessFile만 닫고
       MappedByteBuffer는 GC 기다림

조치:
- 작은 단위(예: 100MB)로 분할 mmap → 사용 → null → System.gc()
- JDK 22+ Foreign Memory API의 Arena 사용 (deterministic unmap)
```

### 시나리오 3: JNI 라이브러리 누수

```
증상: NMT 합계와 RSS 차이가 큼 (수백MB 격차)
       BufferPool, Heap 모두 정상

진단: jemalloc 또는 Valgrind
   $ LD_PRELOAD=libjemalloc.so java ...
   $ jemalloc-prof 출력 분석

원인: JNI 라이브러리의 native malloc 후 free 누락
       또는 native 라이브러리의 자체 buffer 풀

조치:
- 라이브러리 버전 업그레이드
- JNI 메서드 사용량 감사
- 가능하면 표준 NIO로 대체
```

---

## ⚔️ 8단계: 꼬리질문 트리

### Q1. ByteBuffer.allocate와 allocateDirect의 차이는?

**예상 답변**:
> - `allocate(N)`: Heap 안에 byte[] 가진 HeapByteBuffer. GC 대상. TLAB에서 빠르게 할당.
> - `allocateDirect(N)`: Heap 밖 native 메모리 + Heap의 작은 DirectByteBuffer 객체. Cleaner로 해제. malloc 호출 비싸지만 I/O 시 zero-copy.
> 
> 사용 기준:
> - 작고 단명: Heap.
> - 크고 장명 + I/O: Direct.

#### 🪝 Q1-1: Zero-copy가 무엇이고 왜 Direct에서만 가능한가요?

> 일반 file read: 디스크 → 커널 page cache → JVM Heap (2번 복사).
> Direct Buffer + Channel.read: 디스크 → Direct Buffer (1번 복사, DMA).
> 
> Heap Buffer는 GC가 객체를 옮길 수 있어 커널이 직접 그 주소를 쓸 수 없음 — pinning 필요. JVM이 syscall 직전 임시 Direct Buffer로 복사 후 syscall. 그래서 Heap Buffer로 NIO 호출하면 내부적으로 Direct로 한 번 더 복사.
> 
> Direct Buffer는 native 주소가 변하지 않음 → 커널이 직접 read/write.

### Q2. Cleaner는 무엇이고 어떻게 동작하나요?

**예상 답변**:
> PhantomReference 기반의 자동 해제 메커니즘.
> 
> 흐름:
> 1. DirectByteBuffer 생성 시 Cleaner.create(buf, deallocator) 등록.
> 2. buf가 unreachable → GC가 처리 → Cleaner가 ReferenceQueue에 enqueue.
> 3. Reference Handler thread가 queue 모니터링 → Cleaner.clean() 호출.
> 4. deallocator.run() → UNSAFE.freeMemory(address) → native free.
> 
> 한계: GC와 native free 사이 지연. 짧은 시간 폭주 시 OOM.

#### 🪝 Q2-1: Cleaner와 finalize의 차이는?

> finalize:
> - 객체에 `finalize()` 메서드 정의.
> - GC가 객체를 회수하기 전 finalize 호출.
> - 비결정적 + 성능 영향 + 보안 위험 (JDK 9+ deprecated).
> 
> Cleaner:
> - PhantomReference 기반 — 객체 GC 후 별도 thread에서 호출.
> - 객체와 cleanup 로직 분리 (인스턴스 누수 위험 ↓).
> - 표준화된 API (`java.lang.ref.Cleaner`).
> - 더 안전, 더 빠름.

### Q3. `OutOfMemoryError: Direct buffer memory`가 발생하는 메커니즘은?

**예상 답변**:
> Bits.reserveMemory에서 검사:
> 1. 새 할당 + 현재 사용량 > MaxDirectMemorySize?
> 2. 그렇다면 System.gc() + Reference 처리 강제.
> 3. 9번까지 sleep 후 재시도.
> 4. 그래도 안 되면 OOM throw.
> 
> 함정:
> - `-XX:+DisableExplicitGC` 켜져 있으면 System.gc()가 무력화 → 같은 워크로드에서 OOM 더 쉽게.
> - NIO 앱에서는 절대 켜지 말 것.

#### 🪝 Q3-1: MaxDirectMemorySize 기본값은?

> 명시 안 하면 **-Xmx와 비슷** (정확히는 Runtime.maxMemory() 기반).
> 즉 -Xmx 2g면 Direct도 최대 2g까지 — Heap과 합치면 컨테이너 limit 초과 가능.
> 
> Container 환경에서는 명시 권장:
> ```
> -Xmx2g -XX:MaxDirectMemorySize=512m
> ```

### Q4. MappedByteBuffer와 DirectByteBuffer의 차이는?

**예상 답변**:
> - DirectByteBuffer: malloc된 anonymous native memory. 프로세스 종료 시 사라짐. -XX:MaxDirectMemorySize 카운트.
> - MappedByteBuffer: mmap된 파일 매핑. 메모리와 디스크 동기. OS page cache 사용. **MaxDirectMemorySize에 카운트 안 됨**.
> 
> 결과:
> - Direct: 네트워크 I/O 같은 단명 큰 버퍼.
> - Mapped: 큰 파일 random access (DB, log).

#### 🪝 Q4-1: MappedByteBuffer는 어떻게 해제하나요?

> 표준 API 없음 (보안 + 복잡도).
> 옵션:
> 1. **null로 두고 GC 기다림** — 비결정적.
> 2. **internal API** `Unsafe.invokeCleaner(buf)` — JDK 17+ Strong Encapsulation 제약.
> 3. **JDK 22+ Foreign Memory API** — `Arena.ofConfined()`로 deterministic 해제.
> 4. **작은 단위 분할 매핑** — 일찍 unreachable 만들기.

### Q5. Netty가 Direct Buffer를 풀링하는 이유는?

**예상 답변**:
> Direct Buffer 할당/해제 비용:
> - 할당: `UNSAFE.allocateMemory` ~ 수 us (Heap의 TLAB 할당 대비 1000배).
> - 해제: Cleaner를 통한 비결정적 free.
> 
> Connection 수만 대 + 매 패킷 ByteBuf 생성/해제하면 비용 폭주.
> 
> Netty의 PooledByteBufAllocator:
> - 16MB Chunk 단위로 OS에서 받음.
> - Chunk 안에서 SubPage로 분할.
> - 사용자가 buffer를 풀에서 받았다 release()로 반환.
> - 결과: malloc/free 최소화, TLB pressure ↓.
> 
> 단점: 풀이 idle 시에도 메모리 점유. 누수(release 누락) 시 풀이 계속 chunk 추가.

#### 🪝 Q5-1: Netty 누수를 어떻게 진단하나요?

> `-Dio.netty.leakDetection.level=PARANOID` JVM 옵션.
> 100% 추적 (운영에선 느림), 누수 발견 시 stack trace 출력.
> 일반적으로:
> - 개발/staging: PARANOID.
> - production: SIMPLE (1% 샘플).
> 
> 출력 예: `LEAK: ByteBuf.release() was not called before ... at io.netty.buffer.AbstractByteBufAllocator.directBuffer(...)`.

### Q6. (Killer) `-Xmx 2g`로 시작한 JVM의 컨테이너가 5GB limit인데 OOM-killed 됐습니다. Heap dump는 정상이에요. 어떻게 진단하시겠어요?

**예상 답변**:
> Heap이 원인 아님 — 다른 native 영역의 합이 5GB 초과.
> 
> 단계적 진단:
> 
> 1. **NMT summary**:
>    ```
>    jcmd <pid> VM.native_memory summary
>    ```
>    Heap 2GB + Metaspace + Threads + Code Cache + Other의 합산.
>    Other가 비정상적으로 크면 → Direct Memory 의심.
> 
> 2. **BufferPool 확인**:
>    ```java
>    ManagementFactory.getPlatformMXBeans(BufferPoolMXBean.class)
>    ```
>    `direct` 또는 `mapped` pool 사용량.
> 
> 3. **`pmap` OS 레벨**:
>    ```
>    pmap -x <pid> | sort -k 2 -n -r | head
>    ```
>    큰 anonymous 영역 또는 파일 매핑 확인.
> 
> 4. **NMT detail + Netty PARANOID**:
>    - NMT가 추적하는 영역인가? Other에서 caller 확인.
>    - Netty 누수면 PARANOID 모드에서 stack trace.
> 
> 5. **JNI 의심**:
>    - NMT 합과 RSS 차이 크면 JNI 직접 malloc 가능성.
>    - `jemalloc` 또는 Valgrind로 정확한 추적.
> 
> 6. **조치**:
>    - 누수 코드 수정 + 명시적 한계 (`-XX:MaxDirectMemorySize`).
>    - 컨테이너 limit의 30~50% Heap, 20~30% Direct, 나머지 여유.
>    - 정기 NMT/JFR 모니터링 정착.

#### 🪝 Q6-1: 그럼 컨테이너 environment에서 메모리 분배 가이드라인은?

> 5GB limit 기준 예시:
> - `-Xmx`: 2g (40%)
> - `-XX:MaxDirectMemorySize`: 1g (20%)
> - `-XX:MaxMetaspaceSize`: 512m (10%)
> - `-XX:ReservedCodeCacheSize`: 256m
> - Thread stacks (500 thread × 1MB): 500m
> - 여유: ~700m (JVM 내부, page cache, JNI)
> 
> = 약 5GB. 여유분 줄이지 말 것 (커널, page cache, lib).

---

## 🔗 다음 단계

- → [06. GC bookkeeping](./06-gc-bookkeeping-and-others.md): Card Table, RSet, Mark Bitmap
- ← [04. Code Cache](./04-code-cache.md): JIT 결과 저장소
- ← [03. Stack & PC & Native](./03-stack-pc-native.md): Per-thread 메모리
- ← [02. Metaspace](./02-metaspace-and-class-space.md): Class 메타데이터
- ← [01. Heap & TLAB](./01-heap-and-tlab.md): Heap의 세대 구조

## 📚 참고

- **JEP 454 Foreign Function & Memory API**: https://openjdk.org/jeps/454
- **JDK 9 `java.lang.ref.Cleaner`**: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ref/Cleaner.html
- **`java.nio.Bits`** (소스): https://github.com/openjdk/jdk/blob/master/src/java.base/share/classes/java/nio/Bits.java
- **HotSpot `unsafe.cpp`**: https://github.com/openjdk/jdk/blob/master/src/hotspot/share/prims/unsafe.cpp
- **Netty PooledByteBufAllocator**: https://github.com/netty/netty/blob/4.1/buffer/src/main/java/io/netty/buffer/PooledByteBufAllocator.java
- **Netty Leak Detection Guide**: https://netty.io/wiki/reference-counted-objects.html
- **Linux mmap(2)**: `man 2 mmap`
- **Aleksey Shipilëv — Direct Memory Internals**: https://shipilev.net/jvm/anatomy-quarks/
